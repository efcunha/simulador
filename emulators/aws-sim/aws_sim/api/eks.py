"""EKS over the AWS REST-JSON protocol.

EKS does not speak Query and is not JSON-1.1: the client hits a **path** and reads a JSON
body (``GET /clusters``, ``GET /clusters/{name}``), so it routes through an ``APIRouter``
like SSO rather than through the one endpoint in ``api/app.py``.

An unknown cluster is refused with EKS's own ``ResourceNotFoundException`` and an HTTP 404
— not with an empty body, which a caller would read as "clusters exist but have no
node groups".

**The surface is scoped by the account of the credentials.** The real EKS resolves a
name inside the account that signed the request; this one decodes the account from the
SigV4 credential the same way the rest of the package does (``projections/sts.py``:
``parse_access_key`` + ``account_from_access_key`` — the rule ``sts.GetCallerIdentity``
and the IAM credential report already follow) and falls back to the estate's first
account when the request presents no decodable credential. **No header of its own is
invented**: the account is the one the caller signed with.

The four routes are the four FinOps EKS collector calls first (``list_clusters``,
``describe_cluster``, ``list_nodegroups``, ``list_addons``). The two ``Describe*`` detail
operations for a node group or an add-on are NOT served: the estate models neither, and
this module does not answer a question it has no data for.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim.projections import eks, sts

router = APIRouter()

#: The REST-JSON error prefix EKS uses in ``__type``, and the header botocore reads when
#: the body carries no code of its own.
_ERROR_PREFIX = "ResourceNotFoundException"


def _not_found(name: str) -> JSONResponse:
    return JSONResponse(
        {"message": f"No cluster found for name: {name}", "__type": _ERROR_PREFIX},
        status_code=404,
        headers={"x-amzn-errortype": _ERROR_PREFIX},
    )


def _estate(request: Request) -> CanonicalEstate:
    estate: CanonicalEstate = request.app.state.estate
    return estate


def _account(request: Request) -> str:
    """The account the request speaks for, decoded from its SigV4 credential.

    The same decoding the STS and IAM routes do (``projections.sts``): the access key
    id the request was signed with carries the account, and a request that presents no
    decodable one falls back to the estate's first account.
    """
    access_key = sts.parse_access_key(request.headers.get("authorization"))
    account = sts.account_from_access_key(access_key) if access_key else None
    return account or eks.covered_account(_estate(request), "")


@router.get("/clusters")
async def list_clusters(request: Request) -> Any:
    """``eks.ListClusters`` — the cluster names this account owns."""
    estate = _estate(request)
    return {"clusters": list(eks.clusters(estate, _account(request)))}


@router.get("/clusters/{name}")
async def describe_cluster(request: Request, name: str) -> Any:
    """``eks.DescribeCluster`` — one cluster's document."""
    estate = _estate(request)
    cluster = eks.find_cluster(estate, name, _account(request))
    if cluster is None:
        return _not_found(name)
    return {"cluster": eks.cluster_document(estate, cluster)}


@router.get("/clusters/{name}/node-groups")
async def list_nodegroups(request: Request, name: str) -> Any:
    """``eks.ListNodegroups`` — the node group names on one cluster."""
    estate = _estate(request)
    account = _account(request)
    if eks.find_cluster(estate, name, account) is None:
        return _not_found(name)
    return {"nodegroups": list(eks.node_groups(estate, name, account))}


@router.get("/clusters/{name}/addons")
async def list_addons(request: Request, name: str) -> Any:
    """``eks.ListAddons`` — the add-on names on one cluster."""
    estate = _estate(request)
    account = _account(request)
    if eks.find_cluster(estate, name, account) is None:
        return _not_found(name)
    return {"addons": list(eks.addons(estate, name, account))}
