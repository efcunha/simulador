"""azure-sim: the network security group api-version the installed SDK sends.

P76. ``azure-mgmt-network`` 33.1.0 builds ``network_security_groups.list_all``
with ``api-version=2026-03-01``; the service accepted only ``2025-05-01`` and
answered ``InvalidApiVersion``, which failed the CloudPilot Azure security
check. The versions are read off the installed client, not guessed:

    podman exec cloudpilot_backend python -c "
    import inspect
    from azure.mgmt.network.operations import _operations as op
    src = inspect.getsource(op)
    print([l.strip() for l in src.splitlines() if '2026-' in l][:3])"
    -> api_version: str = kwargs.pop("api_version", _params.pop("api-version", "2026-03-01"))
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

_SCOPE = "subscriptions/00000000-0000-0000-0000-000000000000"
_NSG_PATH = f"/{_SCOPE}/providers/Microsoft.Network/networkSecurityGroups"


def test_nsg_list_accepts_the_api_version_the_installed_sdk_sends(azure_api_client: TestClient) -> None:
    """2026-03-01 -- what azure-mgmt-network 33.1.0 sends -- is accepted."""
    resp = azure_api_client.get(_NSG_PATH, params={"api-version": "2026-03-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert "value" in body
    assert isinstance(body["value"], list)


def test_nsg_list_keeps_accepting_the_previous_api_version(azure_api_client: TestClient) -> None:
    """2025-05-01 -- the version the service already served -- still works."""
    resp = azure_api_client.get(_NSG_PATH, params={"api-version": "2025-05-01"})
    assert resp.status_code == 200
    assert "value" in resp.json()


def test_nsg_list_rejects_an_unknown_api_version(azure_api_client: TestClient) -> None:
    """An api-version the service never published is still refused."""
    resp = azure_api_client.get(_NSG_PATH, params={"api-version": "1999-01-01"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "InvalidApiVersion"


def test_nsg_list_requires_an_api_version(azure_api_client: TestClient) -> None:
    """The version is mandatory -- the error envelope says so."""
    resp = azure_api_client.get(_NSG_PATH)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "InvalidApiVersion"
