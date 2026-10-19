"""Compute resource plane: ``virtualMachines`` and ``disks`` (Phase 6).

Both reads are subscription-scoped members of ``Microsoft.Compute`` and both are served
here, so they share one router. ``virtual_machines.list_all`` is the read
``resources.py (modulo do consumidor):49`` makes; ``disks`` has no consumer
yet and is served so the two halves of the estate's Compute footprint answer together.

**The api-version strings are read off the installed client, not guessed.**
``azure-mgmt-compute`` 38.0.0's ``build_virtual_machines_list_all_request`` defaults to
``2025-11-01`` and ``build_disks_list_request`` to ``2025-01-02`` (both in that wheel's
``operations/_operations.py``), and those are the versions a caller using the installed
package sends — the same method ``api/monitor.py`` documents for its own paths. The two
operations carry different versions, so each endpoint gets its own gate; the gate is what
makes an unsupported version a 400 Azure envelope rather than a silently served answer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.compute import project_disks, project_virtual_machines

router = APIRouter()

#: Read off the installed ``azure-mgmt-compute`` 38.0.0 operation builders.
_VIRTUAL_MACHINE_VERSIONS: frozenset[str] = frozenset({"2025-11-01"})
_DISK_VERSIONS: frozenset[str] = frozenset({"2025-01-02"})


@router.get("/{scope:path}/providers/Microsoft.Compute/virtualMachines")
async def virtual_machines(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``virtualMachines.list_all`` rows for the scope (``{value:[...]}``)."""
    require_api_version(request, _VIRTUAL_MACHINE_VERSIONS)
    return value_page(request, project_virtual_machines(get_estate(request)))


@router.get("/{scope:path}/providers/Microsoft.Compute/disks")
async def disks(request: Request, scope: str = "") -> dict[str, Any]:
    """Return the subscription's managed disks (``{value:[...]}``)."""
    require_api_version(request, _DISK_VERSIONS)
    return value_page(request, project_disks(get_estate(request)))
