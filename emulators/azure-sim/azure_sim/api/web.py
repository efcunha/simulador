"""Web resource plane: ``sites`` (Phase 6).

The read ``service_discovery.py (modulo do consumidor):374`` makes through
``WebSiteManagementClient.web_apps.list()``; what the estate backs is documented on
``projections/web.py``.

**The api-version strings could NOT be verified in this environment**: ``azure-mgmt-web`` is
not installed here (it is imported lazily inside the discovery function's ``try`` and is not
a declared backend dependency), so unlike the Compute/Network/SQL/Storage gates these are not
read off a client. They are a tolerance set of the stable versions the service has shipped,
flagged below; the catalogue row this belongs to is ``docs/synthetic-clouds/UNVERIFIED.md``
(Phase 6 — Azure resource plane), outside the package this change was scoped to.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.web import project_sites

router = APIRouter()

# TODO-verificar: NOT read off an installed client (azure-mgmt-web is absent); stable
# versions of the sites list, pending confirmation.
_SITE_VERSIONS: frozenset[str] = frozenset({"2023-12-01", "2024-04-01"})


@router.get("/{scope:path}/providers/Microsoft.Web/sites")
async def web_apps(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``web_apps.list`` rows for the scope (``{value:[...]}``)."""
    require_api_version(request, _SITE_VERSIONS)
    return value_page(request, project_sites(get_estate(request)))
