"""Lambda over the AWS REST-JSON protocol.

The service is named ``lambda``, which is a Python keyword, so the module carries the PEP
8 trailing underscore and is imported as ``from aws_sim.api import lambda_``.

``list_functions`` is ``GET /2015-03-31/functions`` (the model's ``requestUri``; the
trailing-slash form the AWS docs print is registered too, so a caller that writes the
documented URI reaches the same handler instead of a redirect).

Only ``ListFunctions`` is served — ``GetFunction`` and ``Invoke`` would need code and
configuration the estate does not carry.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from tools.synthetic_clouds.model.estate import CanonicalEstate

from aws_sim.projections import lambda_ as projection

router = APIRouter()

_PATH = "/2015-03-31/functions"


@router.get(_PATH)
@router.get(f"{_PATH}/")
async def list_functions(request: Request) -> Any:
    """``lambda.ListFunctions`` — the functions this account owns."""
    estate: CanonicalEstate = request.app.state.estate
    return {"Functions": list(projection.functions(estate))}
