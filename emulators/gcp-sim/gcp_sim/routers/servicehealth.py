"""Service Health routes (Phase 6).

``GET /v1/projects/{project}/locations/{location}/events`` (``events.list``) -- read by
FinOps cloud-health collector (``gcp_collector.py (modulo do consumidor)``, which
calls the parent ``projects/<p>/locations/-`` with ``filter=state="ACTIVE"``) to surface
GCP incidents and maintenance windows.

**The answer is an empty page, and that is the estate's own answer.** The canonical estate
models no health event -- no incident, no maintenance window, no category, no affected
service -- so there is nothing to project, and nothing is invented. This is the one place
where inventing a row would be worse than an empty list: the collector turns each event
into an ``HealthEvent`` with a severity, a recommended action and affected resources, so a
synthesized outage would raise a false incident in the owner's Operations center about a
fictional cloud. Serving ``{"events": []}`` states exactly what the estate knows: no known
events, which is also what GCP returns for a project with none.

The route still takes project and location and still requires a bearer, so the call shape
is the real one; an unimplemented route would have taught a client the wrong shape.
``filter`` (which the collector always sends) is ignored rather than parsed: there is
nothing for it to narrow, and a half-implemented filter language would reject the caller's
real filter string. ``pageSize`` is validated like every other list in this package.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from gcp_sim.deps import clamp_page_size, require_bearer

router = APIRouter(tags=["servicehealth"])


@router.get("/v1/projects/{project}/locations/{location}/events")
async def list_events(
    project: str,
    location: str,
    request: Request,
    pageSize: int | None = Query(default=None),  # noqa: N803 - GCP query param casing
) -> dict[str, Any]:
    """Service Health events list -- always empty; the estate models no health event."""
    require_bearer(request)
    clamp_page_size(pageSize)
    return {"events": [], "nextPageToken": ""}
