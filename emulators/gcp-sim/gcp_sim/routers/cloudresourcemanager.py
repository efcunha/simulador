"""Cloud Resource Manager routes (Phase 6).

``GET /v1/projects`` -- ``projects.list``, serving the org/folder/project tree the estate
models in ``model/hierarchy.py``. This is the first call FinOps makes with a GCP
credential: ``connection_validator.py (modulo do consumidor)`` lists projects to prove
the service account works and to report how many projects it can see.

Every member is a value the estate holds, or a stated baseline:

* ``projectId`` and ``name`` are the project's own (``GcpProject.project_id`` / ``.name``);
* ``parent`` is the folder that owns it, which only the tree walk knows
  (``scope.ProjectScope``);
* ``lifecycleState`` is ``ACTIVE`` because a project the estate bills for exists and is
  serving. That is a baseline claim, not a value read off the estate -- the same class of
  claim ``emulators/aws-sim/aws_sim/projections/ec2.py`` makes when it reports a billed
  instance as ``running``.
* ``projectNumber`` is deliberately **absent**. GCP assigns a numeric id at creation; the
  estate mints a UUID instead, so a number emitted here would be a fabricated identity
  that a caller could store and later fail to match. Absence is absence.

``scope.projects`` is the only reader of the hierarchy, so a project that belongs to
another provider cannot appear here no matter what the estate carries.

``pageSize`` is validated (clamped to [1, 1000], like every sibling router in this
package) and the whole tree is served as one page with ``nextPageToken`` empty: the
estate's project tree is bounded and small, and the fixture-backed routers beside this
one serve one page for the same reason.

TODO-verificar #7: the official CRM v1 ``projects.list`` envelope is unverifiable
offline; the response is best-effort official-shaped.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim import scope
from gcp_sim.deps import clamp_page_size, require_bearer
from gcp_sim.routers import estate

router = APIRouter(tags=["cloudresourcemanager"])

#: CRM's lifecycle vocabulary; the estate bills its projects, so they are serving.
LIFECYCLE_STATE_ACTIVE = "ACTIVE"


def _project(owned: scope.ProjectScope) -> dict[str, Any]:
    """One ``projects`` entry for an estate project."""
    return {
        "projectId": owned.project.project_id,
        "name": owned.project.name,
        "lifecycleState": LIFECYCLE_STATE_ACTIVE,
        "parent": {"type": "folder", "id": owned.folder_id},
    }


@router.get("/v1/projects")
async def list_projects(request: Request, pageSize: int | None = Query(default=None)) -> dict[str, Any]:  # noqa: N803 - GCP query param casing
    """Cloud Resource Manager projects list (TODO-verificar #7)."""
    require_bearer(request)
    clamp_page_size(pageSize)
    return {
        "projects": [_project(owned) for owned in scope.projects(estate(request))],
        "nextPageToken": "",
    }
