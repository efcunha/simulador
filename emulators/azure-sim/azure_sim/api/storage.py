"""Storage resource plane: ``storageAccounts`` (Phase 6).

The read ``resources.py (modulo do consumidor):70`` makes; the SKU mapping and
the fields the estate can honestly back are documented on ``projections/storage.py``.

The api-version and the URL template are read off the installed ``azure-mgmt-storage``
24.0.1 ``build_storage_accounts_list_request``, not guessed — the same method
``api/monitor.py`` documents.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from azure_sim.api.common import get_estate, require_api_version, value_page
from azure_sim.projections.storage import project_storage_accounts

router = APIRouter()

#: Read off the installed ``azure-mgmt-storage`` 24.0.1 operation builder.
_STORAGE_ACCOUNT_VERSIONS: frozenset[str] = frozenset({"2025-06-01"})


@router.get("/{scope:path}/providers/Microsoft.Storage/storageAccounts")
async def storage_accounts(request: Request, scope: str = "") -> dict[str, Any]:
    """Return ``storage_accounts.list`` rows for the scope (``{value:[...]}``)."""
    require_api_version(request, _STORAGE_ACCOUNT_VERSIONS)
    return value_page(request, project_storage_accounts(get_estate(request)))
