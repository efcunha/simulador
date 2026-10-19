"""Network resource plane: ``networkSecurityGroups`` (Phase 6).

The read ``security.py (modulo do consumidor):107`` makes, and the one
endpoint in this package whose correct answer is an empty list: the estate models no
network security group at all, so the projector returns no rows. The reasons both
directions of invention are worse than an empty answer are on
``projections/network.py``, next to the projector that makes the choice.

The api-version is read off the installed ``azure-mgmt-network`` 30.2.0
``build_network_security_groups_list_all_request`` default, and the URL template of that
same builder is the one served below — neither is a guess.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.network import project_network_security_groups

router = APIRouter()

#: Read off the installed ``azure-mgmt-network`` 30.2.0 operation builder.
_NETWORK_SECURITY_GROUP_VERSIONS: frozenset[str] = frozenset({"2025-05-01"})


@router.get("/{scope:path}/providers/Microsoft.Network/networkSecurityGroups")
async def network_security_groups(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``network_security_groups.list_all`` rows — empty, as the estate has none."""
    require_api_version(request, _NETWORK_SECURITY_GROUP_VERSIONS)
    return value_page(request, project_network_security_groups(get_estate(request)))
