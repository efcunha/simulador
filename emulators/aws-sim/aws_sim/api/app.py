"""FastAPI app factory for aws-sim (mirrors azure-sim's ``create_app``).

The estate is built ONCE at app-create time through the fail-closed gate and shared
read-only on ``app.state``, so a request never rebuilds it and every route projects from
the same frozen source.

One endpoint serves every AWS service, because the endpoint override sets ONE
``endpoint_url``. The protocol is told apart the way AWS does: a request carrying
``X-Amz-Target`` is **JSON-1.1** (Cost Explorer, Organizations, ECS, DynamoDB, the
tagging API, Config, Health); otherwise it is the **Query** protocol, disambiguated by ``Action``
(CloudFormation, STS, RDS, ELBv2, IAM, EC2). EC2 rides that same route and the same
``Action`` dispatch but renders the **ec2** variant of the XML envelope — no
``{Operation}Result`` wrapper, model-named tags, lowercase ``requestId``
(``query_xml.EC2Wire``); its errors need no special case, since the ec2 parser reads the
``<ErrorResponse>`` envelope above like any other. Query errors render as the XML
``<ErrorResponse>`` envelope and JSON errors as ``{"__type": …}``, so a failure reaches
boto3 as a real ``ClientError`` with a readable code either way.

CloudWatch rides that same ``X-Amz-Target`` route — its target prefix is
``GraniteServiceVersion20100801`` and it posts to the endpoint root like the other two —
but renders **JSON-1.0** rather than JSON-1.1 (``smithy_rpc.CONTENT_TYPE_JSON``), so it is
dispatched by :func:`_smithy_rpc_response` and not by the JSON-1.1 loop. Its other framing,
RPC-v2 CBOR, does NOT reach the root: ``BaseRpcV2Serializer`` replaces the operation's
``/`` with ``/service/<targetPrefix>/operation/<Operation>``, so that framing gets its own
path route (:func:`rpc_v2_endpoint`). One service, two framings, two routes.

The remaining services are **REST-JSON** and route by path rather than by header or form
(SSO/SSO-OIDC, EKS, Lambda), so they get their own routers — the one endpoint cannot
dispatch them. S3 is path-routed too, but on a fourth wire: **REST-XML**, with no
``Action`` form field and no ``X-Amz-Target`` header, so it also gets its own router
(``api/s3.py``). Its router is registered **last**, because ``GET
/federation/credentials``, ``GET /clusters`` and Lambda's paths are ``/{bucket}`` or
``/{bucket}/{key}`` as far as a path template is concerned and Starlette resolves in
registration order.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from starlette.exceptions import HTTPException as StarletteHTTPException

# ``lambda`` is a Python keyword, so its module carries the PEP 8 trailing underscore and
# is imported under the name the router is registered with.
import aws_sim.api.lambda_ as lambda_service
from aws_sim import json_wire, query_xml, smithy_rpc
from aws_sim.api import (
    ce,
    cloudformation,
    cloudwatch,
    config_service,
    dynamodb,
    ec2,
    ecs,
    eks,
    elbv2,
    health,
    iam,
    organizations,
    rds,
    resourcegroupstaggingapi,
    s3,
    sso,
    sts,
)
from aws_sim.api.cloudformation import (
    CODE_INVALID_ACTION,
    CODE_MISSING_PARAMETER,
    AwsApiError,
    parse_query_body,
)
from aws_sim.config import Settings
from aws_sim.estate import build_simulated_estate
from aws_sim.json_wire import JsonApiError
from aws_sim.smithy_rpc import SmithyRpcError

_XML = "text/xml"


def _error_response(code: str, message: str, status_code: int) -> Response:
    return Response(
        content=query_xml.render_error(code, message, f"synth-{uuid.uuid4().hex[:8]}"),
        media_type=_XML,
        status_code=status_code,
    )


def create_app(settings: Settings) -> FastAPI:
    """Build the FastAPI app for ``settings`` (estate built once, routes registered)."""
    app = FastAPI(title="aws-sim", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.estate = build_simulated_estate(
        seed=settings.seed,
        profile=settings.profile,
        currency=settings.currency,
    )

    @app.exception_handler(AwsApiError)
    async def _aws_api_error(request: Request, exc: AwsApiError) -> Response:
        return _error_response(exc.code, exc.message, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> Response:
        return _error_response(cloudformation.CODE_VALIDATION_ERROR, "The request is invalid.", 400)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        code = CODE_INVALID_ACTION if exc.status_code == 404 else cloudformation.CODE_VALIDATION_ERROR
        return _error_response(code, str(exc.detail), exc.status_code)

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Liveness probe, JSON like the sibling sims (this route is not part of the AWS API)."""
        return {"status": "ok", "synthetic": True}

    _cf_actions = frozenset(cloudformation.supported_actions())
    _sts_actions = frozenset(sts.supported_actions())
    _rds_actions = frozenset(rds.supported_actions())
    _elbv2_actions = frozenset(elbv2.supported_actions())
    _iam_actions = frozenset(iam.supported_actions())
    _ec2_actions = frozenset(ec2.supported_actions())
    _query_actions = (
        _cf_actions | _sts_actions | _rds_actions | _elbv2_actions | _iam_actions | _ec2_actions
    )
    _json_services = (
        ce,
        organizations,
        ecs,
        dynamodb,
        resourcegroupstaggingapi,
        config_service,
        health,
    )

    def _query_response(region: str, headers: Any, form: dict[str, str]) -> Response:
        estate = app.state.estate
        action = form.get("Action", "").strip()
        if not action:
            raise AwsApiError(CODE_MISSING_PARAMETER, "Action is required.")
        if action in _cf_actions:
            body = cloudformation.dispatch_form(estate, region, form)
        elif action in _sts_actions:
            body = sts.dispatch_form(
                estate,
                region,
                form,
                authorization=headers.get("authorization"),
                denied_account=settings.denied_account,
            )
        elif action in _rds_actions:
            body = rds.dispatch_form(estate, region, form)
        elif action in _elbv2_actions:
            body = elbv2.dispatch_form(estate, region, form)
        elif action in _iam_actions:
            # IAM's credential report is per-account, so it reads the caller's credential
            # the same way STS does.
            body = iam.dispatch_form(estate, region, form, authorization=headers.get("authorization"))
        elif action in _ec2_actions:
            # EC2 rides this same route — it posts an Action to the endpoint root too — but
            # answers with the ec2-protocol XML envelope (``query_xml.EC2Wire``).
            body = ec2.dispatch_form(estate, region, form)
        else:
            supported = ", ".join(sorted(_query_actions))
            raise AwsApiError(
                CODE_INVALID_ACTION,
                f"Action {action} is not served by this simulator. Supported: {supported}.",
            )
        return Response(content=body, media_type=_XML)

    def _json_response(target: str, body: dict[str, Any]) -> Response:
        estate = app.state.estate
        for service in _json_services:
            if service.WIRE.operation_for_target(target) is not None:
                try:
                    payload = service.render(estate, target, body)
                except JsonApiError as exc:
                    return Response(
                        content=service.WIRE.render_error(exc.code, exc.message),
                        media_type=json_wire.CONTENT_TYPE,
                        status_code=exc.status_code,
                    )
                return Response(content=payload, media_type=json_wire.CONTENT_TYPE)
        payload = json.dumps(
            {
                "__type": "UnknownOperationException",
                "message": f"Target {target!r} is not served by this simulator.",
            },
            separators=(",", ":"),
        )
        return Response(content=payload, media_type=json_wire.CONTENT_TYPE, status_code=400)

    def _smithy_rpc_response(wire: smithy_rpc.SmithyRpcWire, target: str | None, body: dict[str, Any]) -> Response:
        """Answer an RPC-v2 service request in the framing ``wire`` names.

        The two framings share one dispatch and differ only in codec and content type, so
        the error envelope is rendered by the same ``wire`` the success body would have
        used — a CBOR request gets a CBOR error, which is what its parser reads.
        """
        operation = cloudwatch.operation_for_target(target)
        if operation is None:
            return Response(
                content=wire.render_error(
                    "UnknownOperationException",
                    f"Target {target!r} is not served by this simulator.",
                ),
                media_type=wire.content_type,
                status_code=400,
            )
        try:
            result = cloudwatch.dispatch(app.state.estate, operation, body)
        except SmithyRpcError as exc:
            return Response(
                content=wire.render_error(exc.code, exc.message),
                media_type=wire.content_type,
                status_code=exc.status_code,
            )
        return Response(content=wire.render_result(result), media_type=wire.content_type)

    @app.post("/")
    async def endpoint(request: Request) -> Response:
        """The single AWS endpoint: JSON-1.1 by ``X-Amz-Target``, else the Query protocol."""
        target = request.headers.get("x-amz-target")
        if target:
            raw = await request.body()
            if cloudwatch.operation_for_target(target) is not None:
                # CloudWatch: same target header and same root path as JSON-1.1, but the
                # model's jsonVersion is 1.0 and its parser expects the matching type.
                return _smithy_rpc_response(cloudwatch.WIRE, target, cloudwatch.WIRE.parse_request(raw))
            return _json_response(target, json.loads(raw) if raw else {})
        form = parse_query_body(await request.body())
        return _query_response(settings.region, request.headers, form)

    @app.post("/service/{target_prefix}/operation/{operation}")
    async def rpc_v2_endpoint(target_prefix: str, operation: str, request: Request) -> Response:
        """The RPC-v2 CBOR transport: the path the client posts to when it speaks CBOR.

        ``BaseRpcV2Serializer`` builds this path from the model's target prefix and the
        operation name, so the operation is carried by the path rather than by a header and
        a CBOR request never reaches ``/``. The prefix is still validated against the model,
        through the same target lookup the root route uses, so a path naming a service this
        emulator does not serve is refused instead of resolved.

        The framing marker is checked here rather than on the root route for the same
        reason: this path is the CBOR transport, so a request that does not declare CBOR is
        mis-framed, and saying so beats handing a JSON body to the CBOR decoder.
        """
        if not smithy_rpc.is_cbor_request(request.headers):
            return Response(
                content=cloudwatch.CBOR_WIRE.render_error(
                    "SerializationException",
                    f"{smithy_rpc.SMITHY_PROTOCOL_HEADER}: {smithy_rpc.SMITHY_PROTOCOL_CBOR} is required on this path.",
                ),
                media_type=cloudwatch.CBOR_WIRE.content_type,
                status_code=400,
            )
        target = f"{target_prefix}.{operation}"
        return _smithy_rpc_response(cloudwatch.CBOR_WIRE, target, cloudwatch.CBOR_WIRE.parse_request(await request.body()))

    # REST-JSON services route by path, so they get their own routers: SSO/SSO-OIDC, EKS
    # and Lambda.
    app.include_router(sso.router)
    app.include_router(eks.router)
    app.include_router(lambda_service.router)
    # S3 (REST-XML) is path-routed as well, and it is registered LAST on purpose: its
    # ``/{bucket}`` and ``/{bucket}/{key}`` templates also describe the REST-JSON paths
    # above, and Starlette takes the first route that matches.
    app.include_router(s3.router)

    return app
