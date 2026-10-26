"""Security Command Center routes (design sec. 5.1, sec. 5.2) and the SCC gRPC plane.

REST (the shape this service always served):
    ``GET /v1/organizations/*/sources``
    ``GET /v1/projects/*/sources``
    ``GET /v1/{parent=organizations/*|projects/*}/sources/*/findings`` -- native
    findings (status open, UPPERCASE severity) from the estate.

gRPC (P76):
    ``google.cloud.securitycenter.v1.SecurityCenter/ListFindings``.

WHY THE gRPC PLANE EXISTS
    The client library the CloudPilot scanner uses -- ``google-cloud-securitycenter``
    -- registers its transports as ``("grpc", "grpc_asyncio", "rest")`` and picks
    the FIRST one when the caller does not name a transport, so the scanner speaks
    **gRPC** to ``securitycenter.googleapis.com`` and the REST route above is never
    reached by it. The plane serves the SAME rendered fixture over gRPC, so both
    clients see the same findings. TODO-verificar #7: official REST shape +
    transport support.

THE WIRE CONTRACT
    The field numbers and the enum values below are read off the installed
    ``google-cloud-securitycenter`` package -- the very library that deserialises
    the response -- and not guessed::

        from google.cloud import securitycenter_v1
        d = securitycenter_v1.types.Finding.pb().DESCRIPTOR
        [(f.number, f.name) for f in d.fields]

    That package is NOT a dependency of this service (the REST plane must not
    require the client package), so the messages are declared here with those
    numbers. The descriptors keep this module's package name, which keeps them
    distinct from the client's: the wire format depends on the field numbers and
    the types, not on the names.
"""

from __future__ import annotations

import json
import os
import sys
from concurrent import futures
from dataclasses import dataclass
from typing import Any

import grpc
import proto
from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer, validate_prefix
from gcp_sim.fixtures import fixtures_dir
from gcp_sim.routers import store

router = APIRouter(tags=["scc"])

#: The parents the findings list accepts. The organization level is the one the
#: sim always served; the project level is the one the CloudPilot scanner asks
#: for (``projects/<project>/sources/-``).
_PARENT_PREFIXES = ("organizations/", "projects/")

#: The gRPC service the Security Center client library calls, verbatim.
_SCC_SERVICE = "google.cloud.securitycenter.v1.SecurityCenter"

#: The environment variable that carries the plane's port; ``off`` disables it.
_PORT_ENV = "GCP_SIM_SCC_GRPC_PORT"

#: The port the plane binds when nothing else is configured. The TLS front
#: forwards ``securitycenter.googleapis.com`` to it.
DEFAULT_PORT = 8088

#: The worker threads the plane serves on.
_MAX_WORKERS = 8

#: The rendered fixture both planes publish.
_FINDINGS_FIXTURE = "scc_findings.json"


# ── the wire contract ────────────────────────────────────────────────────────


class SccValue(proto.Message):
    """``google.protobuf.Value`` -- the value type of ``Finding.source_properties``.

    The contract publishes ``map<string, google.protobuf.Value>``; the JSON form
    of a ``Value`` is the bare scalar, which is what the rendered fixture carries.
    Only the member this contract can carry is declared: the fixture's values are
    strings, and ``string_value`` is the member a ``Value`` holds them in.
    """

    string_value = proto.Field(proto.STRING, number=3)


class SccState(proto.Enum):
    """``Finding.State``."""

    STATE_UNSPECIFIED = 0
    ACTIVE = 1
    INACTIVE = 2


class SccSeverity(proto.Enum):
    """``Finding.Severity``."""

    SEVERITY_UNSPECIFIED = 0
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4


class SccFindingClass(proto.Enum):
    """``Finding.FindingClass``."""

    FINDING_CLASS_UNSPECIFIED = 0
    THREAT = 1
    VULNERABILITY = 2
    MISCONFIGURATION = 3
    OBSERVATION = 4
    SCC_ERROR = 5
    POSTURE_VIOLATION = 6
    TOXIC_COMBINATION = 7
    SENSITIVE_DATA_RISK = 8
    CHOKEPOINT = 9
    EXTERNAL_EXPOSURE = 10


class Finding(proto.Message):
    """``google.cloud.securitycenter.v1.Finding`` -- the members the contract publishes."""

    name = proto.Field(proto.STRING, number=1)
    parent = proto.Field(proto.STRING, number=2)
    resource_name = proto.Field(proto.STRING, number=3)
    state = proto.Field(proto.ENUM, number=4, enum=SccState)
    category = proto.Field(proto.STRING, number=5)
    source_properties = proto.MapField(proto.STRING, proto.MESSAGE, number=7, message=SccValue)
    severity = proto.Field(proto.ENUM, number=12, enum=SccSeverity)
    finding_class = proto.Field(proto.ENUM, number=17, enum=SccFindingClass)
    description = proto.Field(proto.STRING, number=37)


class ListFindingsResult(proto.Message):
    """``ListFindingsResponse.ListFindingsResult``."""

    finding = proto.Field(proto.MESSAGE, number=1, message=Finding)


class ListFindingsResponse(proto.Message):
    """``google.cloud.securitycenter.v1.ListFindingsResponse``."""

    list_findings_results = proto.RepeatedField(proto.MESSAGE, number=1, message=ListFindingsResult)
    next_page_token = proto.Field(proto.STRING, number=3)
    total_size = proto.Field(proto.INT32, number=4)


class ListFindingsRequest(proto.Message):
    """``google.cloud.securitycenter.v1.ListFindingsRequest``."""

    parent = proto.Field(proto.STRING, number=1)
    filter = proto.Field(proto.STRING, number=2)
    order_by = proto.Field(proto.STRING, number=3)


#: The fixture's spellings mapped to the contract's enum members. A name the
#: contract does not publish is an error, never a silent default.
_STATE_BY_NAME = {
    "ACTIVE": SccState.ACTIVE,
    "INACTIVE": SccState.INACTIVE,
}
_SEVERITY_BY_NAME = {
    "CRITICAL": SccSeverity.CRITICAL,
    "HIGH": SccSeverity.HIGH,
    "MEDIUM": SccSeverity.MEDIUM,
    "LOW": SccSeverity.LOW,
}
_FINDING_CLASS_BY_NAME = {
    "THREAT": SccFindingClass.THREAT,
    "VULNERABILITY": SccFindingClass.VULNERABILITY,
    "MISCONFIGURATION": SccFindingClass.MISCONFIGURATION,
    "OBSERVATION": SccFindingClass.OBSERVATION,
    "SCC_ERROR": SccFindingClass.SCC_ERROR,
    "POSTURE_VIOLATION": SccFindingClass.POSTURE_VIOLATION,
    "TOXIC_COMBINATION": SccFindingClass.TOXIC_COMBINATION,
    "SENSITIVE_DATA_RISK": SccFindingClass.SENSITIVE_DATA_RISK,
    "CHOKEPOINT": SccFindingClass.CHOKEPOINT,
    "EXTERNAL_EXPOSURE": SccFindingClass.EXTERNAL_EXPOSURE,
}


def _finding_of(record: dict[str, Any]) -> Finding:
    """One rendered finding as the wire message.

    The mapping is explicit -- the fixture is proto-JSON and the contract's
    members are named differently in it (``resourceName`` for ``resource_name``,
    ``findingClass`` for ``finding_class``) -- so the translation is written
    down instead of being guessed by a generic parser.
    """
    state = record.get("state")
    severity = record.get("severity")
    finding_class = record.get("findingClass")
    return Finding(
        name=record.get("name", ""),
        parent=record.get("parent", ""),
        resource_name=record.get("resourceName", ""),
        state=_STATE_BY_NAME[state] if state else SccState.STATE_UNSPECIFIED,
        category=record.get("category", ""),
        source_properties={
            key: SccValue(string_value=value)
            for key, value in (record.get("sourceProperties") or {}).items()
        },
        severity=_SEVERITY_BY_NAME[severity] if severity else SccSeverity.SEVERITY_UNSPECIFIED,
        finding_class=_FINDING_CLASS_BY_NAME[finding_class] if finding_class else SccFindingClass.FINDING_CLASS_UNSPECIFIED,
        description=record.get("description", ""),
    )


def _response_of(body: dict[str, Any]) -> ListFindingsResponse:
    """The rendered findings body as the wire response."""
    results = [
        ListFindingsResult(finding=_finding_of(record["finding"]))
        for record in body.get("listFindingsResults", [])
    ]
    total = body.get("totalSize")
    return ListFindingsResponse(
        list_findings_results=results,
        next_page_token=body.get("nextPageToken") or "",
        total_size=int(total) if total is not None else len(results),
    )


# ── the gRPC plane ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class GrpcPlane:
    """The running SCC gRPC plane: the server and the port it bound."""

    server: grpc.Server
    port: int

    def stop(self) -> None:
        """Stop the plane and release the port."""
        self.server.stop(0)


def configured_port() -> int | None:
    """Return the port from ``GCP_SIM_SCC_GRPC_PORT``; ``None`` disables the plane.

    Unset is the default and keeps the plane ON at :data:`DEFAULT_PORT`: the
    Security Center client speaks gRPC, so a simulator that did not serve the
    plane would send the caller's request to the real Google. ``off`` (or any
    non-numeric value) disables it loudly rather than binding a port the
    operator did not ask for.
    """
    raw = os.environ.get(_PORT_ENV, "").strip()
    if raw.lower() in {"off", "none", "disabled"}:
        return None
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        print(f"warning: {_PORT_ENV}={raw!r} is not a port; SCC gRPC plane disabled", file=sys.stderr)
        return None


def _load_findings() -> dict[str, Any]:
    """Read the rendered findings fixture the REST plane also publishes."""
    path = fixtures_dir() / _FINDINGS_FIXTURE
    if not path.is_file():
        raise FileNotFoundError(f"SCC findings fixture not found: {path}")
    body: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return body


def _handler(response: ListFindingsResponse) -> Any:
    """Return the unary handler for ``ListFindings``, serving ``response``."""

    def _serve(request: Any, context: grpc.ServicerContext) -> ListFindingsResponse:
        return response

    return _serve


def start_grpc_plane(port: int | None = None) -> GrpcPlane:
    """Start the SCC gRPC plane and return it.

    The plane serves the rendered fixture, so the gRPC client and the REST
    client publish the same findings.
    """
    response = _response_of(_load_findings())
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=_MAX_WORKERS))
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                _SCC_SERVICE,
                {
                    "ListFindings": grpc.unary_unary_rpc_method_handler(
                        _handler(response),
                        request_deserializer=ListFindingsRequest.deserialize,
                        response_serializer=ListFindingsResponse.serialize,
                    )
                },
            ),
        )
    )
    wanted = configured_port() if port is None else port
    bound = server.add_insecure_port(f"0.0.0.0:{wanted}")
    if bound == 0:
        raise RuntimeError(f"could not bind the SCC gRPC plane to port {wanted}")
    server.start()
    return GrpcPlane(server=server, port=bound)


def stop_grpc_plane(plane: GrpcPlane | None) -> None:
    """Stop the plane, if there is one."""
    if plane is not None:
        plane.stop()


#: The plane this process runs, started with the app and stopped with it.
PLANE: GrpcPlane | None = None


def _start_plane() -> None:
    """Start the plane when the app boots; a failure must not stop the service."""
    global PLANE
    port = configured_port()
    if port is None:
        return
    try:
        PLANE = start_grpc_plane(port)
    except Exception as exc:  # noqa: BLE001 - the REST plane must survive it
        print(f"warning: SCC gRPC plane not started: {exc}", file=sys.stderr)


def _stop_plane() -> None:
    """Stop the plane when the app shuts down."""
    global PLANE
    stop_grpc_plane(PLANE)
    PLANE = None


# FastAPI forwards a router's startup/shutdown handlers to the app that
# includes it, so the plane follows the service's own lifecycle.
router.on_startup.append(_start_plane)
router.on_shutdown.append(_stop_plane)


# ── REST routes ──────────────────────────────────────────────────────────────


@router.get("/v1/organizations/{org}/sources")
async def list_sources(org: str, request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """SCC sources list (TODO-verificar #7)."""
    require_bearer(request)
    validate_prefix(f"organizations/{org}", ("organizations/",), "parent")
    clamp_page_size(pageSize)
    return store(request).get("scc_sources.json")


@router.get("/v1/projects/{project}/sources")
async def list_project_sources(
    project: str, request: Request, pageSize: int | None = Query(default=None)  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """SCC sources list at the project level -- the level the scanner asks for."""
    require_bearer(request)
    validate_prefix(f"projects/{project}", ("projects/",), "parent")
    clamp_page_size(pageSize)
    return store(request).get("scc_sources.json")


@router.get("/v1/{parent:path}/findings")
async def list_findings(parent: str, request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """SCC findings list under ``organizations/*/sources/*`` or ``projects/*/sources/*``.

    Both levels publish the same findings: the level is the only difference, and
    the finding carries the source it came from in ``parent``.
    """
    require_bearer(request)
    validate_prefix(parent, _PARENT_PREFIXES, "parent")
    clamp_page_size(pageSize)
    return store(request).get(_FINDINGS_FIXTURE)
