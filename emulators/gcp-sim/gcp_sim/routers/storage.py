"""Cloud Storage routes (Phase 6).

``GET /storage/v1/b?project=PROJECT`` (``buckets.list``) -- one row per ``gcs_bucket``
resource of that project, read by FinOps GCP inventory
(``resources.py (modulo do consumidor)``: ``list_buckets()`` then ``name``,
``location`` and ``storage_class``), which is the ``STORAGE`` token of that client.

``project`` is a **query parameter** here, not a path segment, because that is the real
GCS shape. The API requires it, so it is checked by hand and answered with the GCP error
envelope (``errors.py``) rather than declared required, which FastAPI would reject with a
bare 422 -- the one response shape this sim must never send (``errors.py`` docstring).

``name`` and ``location`` are the estate's ``resource_name`` and ``region_id``;
``storageClass`` comes from the SKU the bucket is billed under, through a closed map (the
SKU catalog is the generator's, so an unmapped SKU is a code change upstream and the
``KeyError`` names it). ``timeCreated`` and ``metageneration``/``iamConfiguration`` are
deliberately absent: the estate asserts no creation time and no bucket configuration, and
neither is substituted -- a clock-derived timestamp would read as a real bucket age.

A project this estate does not carry selects nothing: an empty ``items`` list rather than
a 404, matching the sibling sims (the emulator answers about what it owns instead of
inventing a row for something it does not).

``maxResults`` is GCS's own page-size parameter and is clamped like every other list in
this package; the whole list is served as one page.

The exhausted page carries **no** ``nextPageToken`` field, and that is not cosmetic: real
GCS omits it on the last page, while ``google-cloud-storage``'s iterator reads the field
and keeps paging for as long as it is not ``None`` -- so a present-but-empty token (the
convention the gRPC-shaped fixture routers beside this one use, where an empty proto string
stops the pager) makes ``list_buckets()`` loop forever. Measured against this sim with
google-cloud-storage 3.10.1: the client re-requested the same page indefinitely.

TODO-verificar #7: the official GCS ``buckets.list`` envelope is unverifiable offline; the
response is best-effort official-shaped.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope
from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.errors import GcpError
from gcp_sim.routers import estate

router = APIRouter(tags=["storage"])

BUCKET = "gcs_bucket"

#: ``sku_id`` -> the storage class it names (``gcp-gcs-standard`` really does say standard).
STORAGE_CLASSES_BY_SKU: dict[str, str] = {
    "gcp-gcs-standard": "STANDARD",
}


def _bucket(resource: Resource) -> dict[str, Any]:
    """One ``items`` entry for an estate bucket."""
    return {
        "name": resource.resource_name,
        "location": resource.region_id,
        "storageClass": STORAGE_CLASSES_BY_SKU[resource.sku_id],
        "labels": dict(resource.tags),
    }


def _buckets(estate_: CanonicalEstate, project_id: str) -> tuple[dict[str, Any], ...]:
    """This project's bucket rows, ordered by name."""
    return tuple(_bucket(resource) for resource in scope.resources_of_type(estate_, BUCKET, project_id=project_id))


@router.get("/storage/v1/b")
async def list_buckets(
    request: Request,
    project: str | None = Query(default=None),
    maxResults: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Cloud Storage ``buckets.list`` for one project (TODO-verificar #7)."""
    require_bearer(request)
    if project is None or not project.strip():
        raise GcpError(400, "project is required")
    clamp_page_size(maxResults)
    # No nextPageToken on the exhausted page -- see the module docstring for the client
    # that loops forever on an empty one.
    return {"items": list(_buckets(estate(request), project))}
