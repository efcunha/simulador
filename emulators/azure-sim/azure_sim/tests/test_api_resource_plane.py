"""Resource-plane router tests: the seven ``Microsoft.*`` services (Phase 6).

Each service is asserted on what a caller actually reads off the wire — the
``{value:[...]}`` envelope, the ARM id it parses back out
(``service_discovery.py (modulo do consumidor):413`` takes ``server.id.split("/")[4]``), and the one
member its own collector reads (``vm.hardware_profile.vm_size``, ``sa.sku.name``,
``server.state``) — plus the assertion a shape check cannot make: that every served row
belongs to the Azure estate. The estate is multi-cloud, so a projection that lost its
provider filter would keep its envelope and change only its contents, and an Azure endpoint
answering with an AWS resource is the fidelity requirement inverted.

Absence is asserted as absence where the estate has nothing to derive a row from: the
network security groups are empty because no ``resource_type`` in the estate is one, and
the check below fails if that ever stops being true, so the empty answer stays a fact about
the estate rather than a stale stub.
"""

from __future__ import annotations

from typing import Any

import pytest
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.render.markers import SYNTH_NAME_PREFIX, unmarked_name

from azure_sim.estate import build_simulated_estate
from azure_sim.projections import scope

_SCOPE_LABEL = "sub-01"
_SCOPE = f"/subscriptions/{_SCOPE_LABEL}"

_VM_VERSION = "2025-11-01"
_DISK_VERSION = "2025-01-02"
_AKS_VERSION = "2025-01-01"
_NSG_VERSION = "2025-05-01"
_SQL_SERVER_VERSION = "2024-11-01-preview"
_SQL_DATABASE_VERSION = "2023-02-01-preview"
_STORAGE_VERSION = "2025-06-01"
_SITE_VERSION = "2024-04-01"
_SUBSCRIPTION_VERSION = "2016-06-01"

_VM_PATH = f"{_SCOPE}/providers/Microsoft.Compute/virtualMachines"
_DISK_PATH = f"{_SCOPE}/providers/Microsoft.Compute/disks"
_AKS_PATH = f"{_SCOPE}/providers/Microsoft.ContainerService/managedClusters"
_NSG_PATH = f"{_SCOPE}/providers/Microsoft.Network/networkSecurityGroups"
_SQL_SERVER_PATH = f"{_SCOPE}/providers/Microsoft.Sql/servers"
_STORAGE_PATH = f"{_SCOPE}/providers/Microsoft.Storage/storageAccounts"
_SITE_PATH = f"{_SCOPE}/providers/Microsoft.Web/sites"

#: Every resource-plane path with the api-version its own call site sends.
_GATED_PATHS = (
    (f"{_VM_PATH}?api-version={_VM_VERSION}"),
    (f"{_DISK_PATH}?api-version={_DISK_VERSION}"),
    (f"{_AKS_PATH}?api-version={_AKS_VERSION}"),
    (f"{_NSG_PATH}?api-version={_NSG_VERSION}"),
    (f"{_SQL_SERVER_PATH}?api-version={_SQL_SERVER_VERSION}"),
    (f"{_STORAGE_PATH}?api-version={_STORAGE_VERSION}"),
    (f"{_SITE_PATH}?api-version={_SITE_VERSION}"),
    (f"/subscriptions/sub-01?api-version={_SUBSCRIPTION_VERSION}"),
)


def _subscription_ids(app) -> set[str]:
    """The ids the estate's own subscriptions are served under (the FOCUS GUIDs)."""
    estate = app.state.estate
    return {
        azure_subscription_guid(estate.seed, subscription.subscription_id)
        for group in estate.azure_mgmt_groups
        for subscription in group.subscriptions
    }


def _names(app, resource_type: str, scope_label: str | None = None) -> set[str]:
    """The distinct names the estate's own Azure resources of a type carry.

    Distinct, not counted: the generator restarts its per-scope counter for every scope
    (``generate/estate_builder.py:292``), so one name repeats once per subscription that
    carries it. :func:`_count` is the row-wise count.

    ``scope_label`` narrows to one subscription's rows, for the lists that narrow on the
    scope they are asked under.
    """
    return {
        resource.resource_name
        for resource in app.state.estate.resources
        if resource.resource_type == resource_type
        and resource.identity.provider == "azure"
        and (scope_label is None or resource.parent_scope_id == scope_label)
    }


def _count(app, resource_type: str, scope_label: str | None = None) -> int:
    """How many Azure resources of ``resource_type`` the estate carries, row-wise."""
    return sum(
        1
        for resource in app.state.estate.resources
        if resource.resource_type == resource_type
        and resource.identity.provider == "azure"
        and (scope_label is None or resource.parent_scope_id == scope_label)
    )


def _assert_azure_rows_of_type(
    app,
    rows,
    resource_type: str,
    scope_label: str | None = None,
) -> None:
    """Every row is one of the estate's Azure rows of ``resource_type``."""
    subscriptions = _subscription_ids(app)
    mine = _names(app, resource_type, scope_label)
    foreign = {
        resource.resource_name
        for resource in app.state.estate.resources
        if resource.identity.provider != "azure"
    }
    assert rows, f"the small estate carries {resource_type} resources"
    assert {row["name"] for row in rows} == mine
    for row in rows:
        # The subscription segment is what ties a row to an Azure subscription at all —
        # and the ids are GUIDs, so a scope label leaking into a served id shows up here.
        assert str(row["id"]).split("/")[2] in subscriptions
        assert "/resourceGroups/" in str(row["id"])
        assert str(row["id"]).endswith(f"/{row['name']}")
        assert row["name"] not in foreign
        assert isinstance(row["tags"], dict)
        assert row["location"]


# ── Compute ──────────────────────────────────────────────────────────────────────


def test_compute_virtual_machines_serve_the_row_the_collector_reads(api_client) -> None:
    """``resources.py:49`` reads id/name/location and ``hardware_profile.vm_size``."""
    client, app = api_client
    resp = client.get(f"{_VM_PATH}?api-version={_VM_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]
    _assert_azure_rows_of_type(app, rows, "virtual_machine")

    for row in rows:
        assert row["type"] == "Microsoft.Compute/virtualMachines"
        # The size the estate's SKU names, nested where the SDK's attribute map looks.
        assert row["properties"]["hardwareProfile"]["vmSize"] == "Standard_D2s_v5"
        assert row["properties"]["provisioningState"] == "Succeeded"


def test_compute_disks_serve_the_sku_beside_properties(api_client) -> None:
    """A disk's ``sku`` is a top-level block, not a ``properties`` member."""
    client, app = api_client
    resp = client.get(f"{_DISK_PATH}?api-version={_DISK_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]
    _assert_azure_rows_of_type(app, rows, "managed_disk")

    for row in rows:
        assert row["type"] == "Microsoft.Compute/disks"
        assert row["sku"] == {"name": "Premium_LRS", "tier": "Premium"}
        # P10 is the 128 GiB band of Azure's Premium SSD catalogue, read off the SKU.
        assert row["properties"]["diskSizeGB"] == 128


def test_compute_matches_the_estate_row_for_row(api_client) -> None:
    """One served row per estate resource: no row invented, none dropped."""
    client, app = api_client
    for path, version, resource_type, scope_label in (
        (_VM_PATH, _VM_VERSION, "virtual_machine", None),
        (_DISK_PATH, _DISK_VERSION, "managed_disk", None),
        # The AKS list narrows on the scope it is asked under: every subscription of the
        # estate reuses the cluster names, so an unnarrowed answer would serve another
        # subscription's rows under this subscription's id.
        (_AKS_PATH, _AKS_VERSION, "aks_cluster", _SCOPE_LABEL),
        (_STORAGE_PATH, _STORAGE_VERSION, "storage_account", None),
        (_SITE_PATH, _SITE_VERSION, "app_service", None),
    ):
        rows = client.get(f"{path}?api-version={version}").json()["value"]
        assert len(rows) == _count(app, resource_type, scope_label)


# ── Container Service ────────────────────────────────────────────────────────────


def test_managed_clusters_serve_the_name_and_region_discovery_reads(api_client) -> None:
    """``service_discovery.py:393`` reads ``cluster.name`` and ``cluster.location``."""
    client, app = api_client
    resp = client.get(f"{_AKS_PATH}?api-version={_AKS_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]
    # The list answers the scope's clusters, not the estate's: the names repeat across
    # the subscriptions, so the subscription is what identifies the row.
    _assert_azure_rows_of_type(app, rows, "aks_cluster", _SCOPE_LABEL)

    for row in rows:
        assert row["type"] == "Microsoft.ContainerService/managedClusters"
        assert row["location"]
        # No node pool is claimed: the estate models none, and an empty list would assert
        # a cluster that has no pools.
        assert "agentPoolProfiles" not in row["properties"]


def test_managed_clusters_serve_the_fqdn_and_nothing_else(api_client) -> None:
    """The typed list publishes ``properties.fqdn`` -- the only property added.

    ``fqdn`` is the endpoint ``_list_aks_clusters`` reads and ``get_cluster_health``
    hands back, so the typed list carries it too. It is the ONLY addition: the
    properties of a managed cluster are exactly the provisioning state and the FQDN,
    and a field that appears empty is a claim about the cluster the estate does not
    make.
    """
    client, app = api_client
    resp = client.get(f"{_AKS_PATH}?api-version={_AKS_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]

    for row in rows:
        properties = row["properties"]
        assert set(properties) == {"provisioningState", "fqdn"}
        fqdn = properties["fqdn"]
        assert fqdn, f"an empty fqdn published for {row['name']!r}"
        assert fqdn.endswith(".azmk8s.io"), f"not an AKS host: {fqdn!r}"
        assert "://" not in fqdn, f"the FQDN is a host, not a URL: {fqdn!r}"


# ── Network ──────────────────────────────────────────────────────────────────────


def test_network_security_groups_are_empty_and_the_estate_has_none(api_client) -> None:
    """The empty answer is a fact about the estate, not an unimplemented endpoint."""
    client, app = api_client
    resp = client.get(f"{_NSG_PATH}?api-version={_NSG_VERSION}")
    assert resp.status_code == 200
    assert resp.json()["value"] == []

    assert not [
        resource
        for resource in app.state.estate.resources
        if resource.identity.provider == "azure"
        and (
            "security_group" in resource.resource_type
            or "security_group" in resource.service_name.lower()
        )
    ], "an Azure NSG in the estate would make the empty list above wrong"


# ── SQL ──────────────────────────────────────────────────────────────────────────


def _sql_server_rows(client) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = client.get(
        f"{_SQL_SERVER_PATH}?api-version={_SQL_SERVER_VERSION}"
    ).json()["value"]
    return rows


def test_sql_servers_are_derived_from_the_estates_databases(api_client) -> None:
    """One server per ``sql_database`` resource, named after it (see projections/sql.py)."""
    client, app = api_client
    rows = _sql_server_rows(client)
    _assert_azure_rows_of_type(app, rows, "sql_database")

    for row in rows:
        assert row["type"] == "Microsoft.Sql/servers"
        # The member ``resources.py:99`` reads: ``server.state or "active"``.
        assert row["properties"]["state"] == "Ready"
        assert row["properties"]["fullyQualifiedDomainName"] == (
            f"{row['name']}.database.windows.net"
        )


def test_sql_databases_join_on_the_server_name_the_list_published(api_client) -> None:
    """The caller's own two-step read: resource group out of the id, then databases."""
    client, app = api_client
    server = _sql_server_rows(client)[0]
    server_id = str(server["id"])
    resource_group = server_id.split("/")[4]
    subscription_id = server_id.split("/")[2]

    resp = client.get(
        f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Sql/servers/{server['name']}/databases"
        f"?api-version={_SQL_DATABASE_VERSION}"
    )
    assert resp.status_code == 200
    rows = resp.json()["value"]
    assert len(rows) == 1  # one server per database, so exactly one database under it

    row = rows[0]
    assert row["id"] == f"{server_id}/databases/{row['name']}"
    assert row["type"] == "Microsoft.Sql/servers/databases"
    assert row["sku"] == {"name": "GP_Gen5_2", "tier": "GeneralPurpose", "capacity": 2}
    assert row["properties"]["status"] == "Online"
    # ``databaseId`` is the estate's own uuid: it must be one of the Azure resources and
    # never a foreign one, which the ARM ids (name-based) cannot show by themselves.
    azure_uuids = {
        resource.identity.uuid
        for resource in app.state.estate.resources
        if resource.identity.provider == "azure"
    }
    foreign_uuids = {
        resource.identity.uuid
        for resource in app.state.estate.resources
        if resource.identity.provider != "azure"
    }
    assert row["properties"]["databaseId"] in azure_uuids
    assert row["properties"]["databaseId"] not in foreign_uuids


def test_sql_databases_for_an_unknown_server_are_empty(api_client) -> None:
    """A server the estate does not carry answers no databases, as ARM does."""
    client, _ = api_client
    resp = client.get(
        f"{_SCOPE}/providers/Microsoft.Sql/servers/not-a-server/databases"
        f"?api-version={_SQL_DATABASE_VERSION}"
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == []


def test_sql_databases_narrow_on_the_subscription_in_the_scope(api_client) -> None:
    """A server name is not unique across the estate, so the scope must disambiguate."""
    client, app = api_client
    server = _sql_server_rows(client)[0]
    name = server["name"]
    # The caller's own two segments, both read back out of the served id.
    subscription_id = str(server["id"]).split("/")[2]
    scope_label = str(server["id"]).split("/")[4]

    by_guid = client.get(
        f"/subscriptions/{subscription_id}/providers/Microsoft.Sql/servers/{name}/databases"
        f"?api-version={_SQL_DATABASE_VERSION}"
    ).json()["value"]
    by_label = client.get(
        f"/subscriptions/{scope_label}/providers/Microsoft.Sql/servers/{name}/databases"
        f"?api-version={_SQL_DATABASE_VERSION}"
    ).json()["value"]
    # Another subscription's scope must not answer with this one's database.
    foreign = client.get(
        f"/subscriptions/{azure_subscription_guid(app.state.estate.seed, 'sub-99')}"
        f"/providers/Microsoft.Sql/servers/{name}/databases"
        f"?api-version={_SQL_DATABASE_VERSION}"
    ).json()["value"]

    assert len(by_guid) == 1
    assert by_label == by_guid
    assert foreign == []
    # The database answered is the one of the server asked about, in that subscription.
    assert str(by_guid[0]["id"]).startswith(str(server["id"]) + "/databases/")


# ── Storage ──────────────────────────────────────────────────────────────────────


def test_storage_accounts_serve_the_sku_the_inventory_reader_reads(api_client) -> None:
    """``resources.py:80`` reads ``sa.sku.name``; the estate's SKU maps to one ARM SKU."""
    client, app = api_client
    resp = client.get(f"{_STORAGE_PATH}?api-version={_STORAGE_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]
    _assert_azure_rows_of_type(app, rows, "storage_account")

    for row in rows:
        assert row["type"] == "Microsoft.Storage/storageAccounts"
        assert row["sku"] == {"name": "Standard_LRS", "tier": "Standard"}
        assert row["kind"] == "StorageV2"
        assert row["properties"]["accessTier"] == "Hot"


# ── Subscriptions ────────────────────────────────────────────────────────────────


def test_subscriptions_get_answers_the_id_the_account_is_configured_with(api_client) -> None:
    """``connection_validator.py:117`` calls ``subscriptions.get`` with the GUID it holds."""
    client, app = api_client
    for group in app.state.estate.azure_mgmt_groups:
        for subscription in group.subscriptions:
            guid = azure_subscription_guid(app.state.estate.seed, subscription.subscription_id)
            resp = client.get(f"/subscriptions/{guid}?api-version={_SUBSCRIPTION_VERSION}")
            assert resp.status_code == 200
            body = resp.json()
            assert body["id"] == f"/subscriptions/{guid}"
            assert body["subscriptionId"] == guid
            # The name the validator keeps as the account's display name, WITHOUT the
            # FinOps ``[SYNTH] `` marker: that prefix is FinOps own storage
            # discriminator and a real ``subscriptions.get`` never carries it.
            assert body["displayName"] == unmarked_name(subscription.name)
            assert body["state"] == "Enabled"


def test_subscriptions_get_accepts_a_scope_label_but_never_serves_one(api_client) -> None:
    """The estate's own label is an accepted alias; the ids served stay GUIDs.

    The display name is likewise the subscription's own: the label's ``[SYNTH] `` marker
    stays on the estate (it is how the seed recognises its own rows) and out of the export.
    """
    client, app = api_client
    resp = client.get(f"/subscriptions/sub-01?api-version={_SUBSCRIPTION_VERSION}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subscriptionId"] == azure_subscription_guid(app.state.estate.seed, "sub-01")
    assert body["displayName"] == "Azure Sub 1"
    assert SYNTH_NAME_PREFIX not in body["displayName"]
    assert "sub-01" not in body["id"]


def test_subscriptions_get_unknown_id_is_a_404_envelope(api_client) -> None:
    """A misconfigured subscription id must fail the connection, not answer an empty row."""
    client, _ = api_client
    resp = client.get(f"/subscriptions/does-not-exist?api-version={_SUBSCRIPTION_VERSION}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "SubscriptionNotFound"


# ── Web ──────────────────────────────────────────────────────────────────────────


def test_sites_serve_the_name_and_region_discovery_reads(api_client) -> None:
    """``service_discovery.py:374`` reads ``app.name`` and ``app.location``."""
    client, app = api_client
    resp = client.get(f"{_SITE_PATH}?api-version={_SITE_VERSION}")
    assert resp.status_code == 200
    rows = resp.json()["value"]
    _assert_azure_rows_of_type(app, rows, "app_service")

    for row in rows:
        assert row["type"] == "Microsoft.Web/sites"
        assert row["properties"]["state"] == "Running"
        # No plan to point at: the estate models no App Service plan resource.
        assert "serverFarmId" not in row["properties"]


# ── The api-version gate, shared by every one of them ────────────────────────────


@pytest.mark.parametrize("path", _GATED_PATHS)
def test_every_resource_plane_endpoint_gates_the_api_version(api_client, path: str) -> None:
    """An unsupported version is a 400 Azure envelope, never a silently served answer."""
    client, _ = api_client
    without_version = client.get(path.split("?")[0])
    unsupported = client.get(f"{path.split('?')[0]}?api-version=1999-01-01")
    for resp in (without_version, unsupported):
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "InvalidApiVersion"


# ── The boundary itself ──────────────────────────────────────────────────────────


def test_scope_of_type_answers_only_this_providers_rows() -> None:
    """``scope.of_type`` is what every new projection selects through (design P1)."""
    estate = build_simulated_estate(seed=42, profile="small", currency="USD")
    azure = {r.identity.uuid for r in estate.resources if r.identity.provider == "azure"}
    foreign = {r.identity.uuid for r in estate.resources if r.identity.provider != "azure"}
    assert azure and foreign, "the estate must be multi-cloud for this test to mean anything"

    azure_types = {r.resource_type for r in estate.resources if r.identity.provider == "azure"}
    foreign_types = {r.resource_type for r in estate.resources if r.identity.provider != "azure"}
    for resource_type in sorted(azure_types | foreign_types):
        uuids = {resource.identity.uuid for resource in scope.of_type(estate, resource_type)}
        assert uuids <= azure
        assert not (uuids & foreign)

    # A type only a foreign provider carries must answer nothing at all: the type filter
    # sits on top of the provider filter, so it can never reach a foreign row.
    foreign_only = foreign_types - azure_types
    assert foreign_only
    for resource_type in sorted(foreign_only):
        assert scope.of_type(estate, resource_type) == ()
