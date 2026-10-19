"""EKS over the AWS REST-JSON protocol.

EKS does not speak Query and is not JSON-1.1: the client hits a **path** and reads a JSON
body (``GET /clusters``, ``GET /clusters/{name}``), so it routes through an ``APIRouter``
like SSO rather than through the one endpoint in ``api/app.py``.

An unknown cluster is refused with EKS's own ``ResourceNotFoundException`` and an HTTP 404
— not with an empty body, which a caller would read as "clusters exist but have no
node groups".

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

from aws_sim.projections import eks

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


@router.get("/clusters")
async def list_clusters(request: Request) -> Any:
    """``eks.ListClusters`` — the cluster names this account owns."""
    return {"clusters": list(eks.clusters(_estate(request)))}


@router.get("/clusters/{name}")
async def describe_cluster(request: Request, name: str) -> Any:
    """``eks.DescribeCluster`` — one cluster's document."""
    estate = _estate(request)
    cluster = eks.find_cluster(estate, name)
    if cluster is None:
        return _not_found(name)
    return {"cluster": eks.cluster_document(estate, cluster)}


@router.get("/clusters/{name}/node-groups")
async def list_nodegroups(request: Request, name: str) -> Any:
    """``eks.ListNodegroups`` — the node group names on one cluster."""
    estate = _estate(request)
    if eks.find_cluster(estate, name) is None:
        return _not_found(name)
    return {"nodegroups": list(eks.node_groups(estate, name))}


@router.get("/clusters/{name}/addons")
async def list_addons(request: Request, name: str) -> Any:
    """``eks.ListAddons`` — the add-on names on one cluster."""
    estate = _estate(request)
    if eks.find_cluster(estate, name) is None:
        return _not_found(name)
    return {"addons": list(eks.addons(estate, name))}
