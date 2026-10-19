"""SQL resource plane: ``servers`` and ``servers/{server}/databases`` (Phase 6).

The two reads ``service_discovery.py (modulo do consumidor):412`` and
``resources.py (modulo do consumidor):91`` make, and they are one conversation:
that caller takes the resource group out of a served server id (``server.id.split("/")[4]``)
and passes it, plus the server name, straight back into ``databases.list_by_server``. The
derivation behind the servers the estate never modelled is documented on
``projections/sql.py``; what belongs here is the routing and the two gates.

The databases path is served under ``{scope:path}`` like the rest, so ONE route answers both
the resource-group-scoped call the SDK builds and a subscription-scoped one. The server name
is read out of the path and the subscription out of the scope, because a server name is not
unique across the estate's subscriptions.

**The api-version strings are read off the installed client, not guessed**: they are the
defaults of ``azure-mgmt-sql`` 4.0.0b24's ``build_servers_list_request``
(``2024-11-01-preview``) and ``build_databases_list_by_server_request``
(``2023-02-01-preview``) — different per operation, so each endpoint carries its own gate.
(Those two builders live in that wheel's ``operations/_servers_operations.py`` and
``operations/_databases_operations.py``.)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.arm import subscription_in_scope
from azure_sim.projections.sql import project_databases, project_servers

router = APIRouter()

#: Read off the installed ``azure-mgmt-sql`` 4.0.0b24 operation builders.
_SERVER_VERSIONS: frozenset[str] = frozenset({"2024-11-01-preview"})
_DATABASE_VERSIONS: frozenset[str] = frozenset({"2023-02-01-preview"})


@router.get("/{scope:path}/providers/Microsoft.Sql/servers")
async def servers(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``servers.list`` rows for the scope (``{value:[...]}``)."""
    require_api_version(request, _SERVER_VERSIONS)
    return value_page(request, project_servers(get_estate(request)))


@router.get("/{scope:path}/providers/Microsoft.Sql/servers/{server_name}/databases")
async def databases(request: Request, server_name: str, scope: str = "") -> dict[str, Any]:
    """Return the databases of ``server_name`` under ``scope`` (``{value:[...]}``)."""
    require_api_version(request, _DATABASE_VERSIONS)
    return value_page(
        request,
        project_databases(
            get_estate(request),
            server_name,
            subscription_id=subscription_in_scope(scope),
        ),
    )
