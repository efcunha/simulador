"""Azure SQL resource plane: ``servers.list`` and ``databases.list_by_server`` (Phase 6).

The estate models a **database** and nothing above it: ``sql_database`` is one of the nine
Azure ``resource_type`` values (``generate/constants.py:53``) and there is no server
resource. ARM has no such shape — a database is only reachable as
``/servers/<server>/databases/<database>`` — so a server has to be derived, and this
projection derives as little as possible: **one server per database**, named after its
database. ``servers.list`` then returns exactly the estate's ``sql_database`` rows, each
carrying exactly one database, and a server name the estate does not carry answers ``[]``
(the answer ARM gives for a server with no databases).

The alternative — one server per subscription holding that subscription's databases — was
rejected for the reason ``aws_sim/projections/ec2.py:307`` rejects one reservation per
account: it asserts a grouping (these databases share a server) that no estate row records.
Name reuse is a second reason: the generator restarts its per-scope counter for every scope
(``generate/estate_builder.py:292``), so ``sql_database-0003`` exists in all three
subscriptions, and a server per database keeps the caller's ``server_name`` unambiguous
within the resource group it passes.

The price of that choice is visible in one consumer and is stated rather than hidden:
``service_discovery.py:422`` labels each discovered service ``f"{server.name}/{db.name}"``,
so the pair reads identically. A ``-srv`` suffix would read better — ``alerts.rule_name_for``
mints such a name for a rule the estate does not model — but that rule is keyed on an opaque
uuid, whereas a database has a name the estate chose, and a second name for a named row is
an authored value: the estate names each resource once.

That caller is what pins the wire shapes (``service_discovery.py (modulo do consumidor):412``):

    rg_name = server.id.split("/")[4]
    sql_client.databases.list_by_server(resource_group_name=rg_name, server_name=server.name)

so a server row must carry the full ARM id — the resource group is read out of segment 4 —
and the databases read is answered under whatever scope the caller then asks under.
``project_databases`` narrows on that scope's subscription when it names one, because a
server name alone is not unique across the estate; a request that is not subscription-scoped
answers every server with that name rather than inventing a preference.

Two derived members, each named here so a reader can tell them from estate data: the server
state is ``Ready`` and the database status ``Online`` — Azure's own vocabularies for a live
server/database, and the caller reads ``server.state or "active"``
(``resources.py:99``) — and the server's fully-qualified name is its own name under Azure's
SQL DNS suffix. The database SKU name and tier come from a closed map on the estate's
``sku_id`` (``azure-sql-gp-2`` -> ``GP_Gen5_2``/``GeneralPurpose``), the same rule the
Compute projection uses; ``properties.databaseId`` is the database's estate uuid, the
stable identity threaded through the canonical model.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, scope

DATABASE = "sql_database"

#: Azure's vocabularies for a live server and database. A server the estate bills for is
#: serving; ``Disabled`` and the database's ``Paused`` belong to states the estate has no
#: way to express.
SERVER_STATE_READY = "Ready"
DATABASE_STATUS_ONLINE = "Online"

#: The domain a server's ``fullyQualifiedDomainName`` lives under. Azure's SQL DNS suffix,
#: not estate data: the FQDN is the server name plus this, which is what makes the row a
#: server a client could address rather than a bare name.
SQL_DNS_SUFFIX = ".database.windows.net"

#: ``sku_id`` -> (service objective, tier, capacity). Closed, like the Compute maps: the
#: generator names one SQL SKU per resource, so an unmapped SKU is a code change upstream
#: and must raise instead of reaching a caller as a plausible-looking database size.
DATABASE_SKUS: dict[str, tuple[str, str, int]] = {
    "azure-sql-gp-2": ("GP_Gen5_2", "GeneralPurpose", 2),
}


def server_name_for(database_name: str) -> str:
    """The server a database is reached through: the database's own name.

    One name per resource. A suffix (``-srv``) would be a second name for a row the estate
    names once, and this function is the join key between the two endpoints — the databases
    read looks a server up by the name ``servers.list`` published.
    """
    return database_name


def project_servers(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``servers.list`` rows: one server per estate database, ordered by name."""
    return [
        arm.arm_row(
            estate,
            resource,
            arm_type=arm.SQL_SERVER_TYPE,
            name=server_name_for(resource.resource_name),
            properties={
                "state": SERVER_STATE_READY,
                "fullyQualifiedDomainName": (
                    f"{server_name_for(resource.resource_name)}{SQL_DNS_SUFFIX}"
                ),
                "provisioningState": arm.PROVISIONING_SUCCEEDED,
            },
        )
        for resource in scope.of_type(estate, DATABASE)
    ]


def _database_row(
    estate: CanonicalEstate,
    resource: Resource,
    server_name: str,
) -> dict[str, object]:
    """One ``databases.list_by_server`` row, nested under its server's ARM id."""
    server_id = arm.resource_id(estate, resource, arm_type=arm.SQL_SERVER_TYPE, name=server_name)
    objective, tier, capacity = DATABASE_SKUS[resource.sku_id]
    return {
        "id": f"{server_id}/databases/{resource.resource_name}",
        "name": resource.resource_name,
        "type": arm.SQL_DATABASE_TYPE,
        "location": resource.region_id,
        "tags": dict(resource.tags),
        # ``sku`` sits beside ``properties`` for the reason ``projections/arm.py`` records.
        "sku": {"name": objective, "tier": tier, "capacity": capacity},
        "properties": {
            "status": DATABASE_STATUS_ONLINE,
            "currentServiceObjectiveName": objective,
            # The estate's own uuid for this database (P2) — the one value on the row that
            # ties it back to the canonical model rather than to a name.
            "databaseId": resource.identity.uuid,
        },
    }


def project_databases(
    estate: CanonicalEstate,
    server_name: str,
    subscription_id: str | None = None,
) -> list[dict[str, object]]:
    """Return the databases of ``server_name``, oldest-first by name.

    ``subscription_id`` is the subscription named in the request scope, when it names one.
    A server name is not unique across the estate (three subscriptions reuse every name),
    so the scope is what disambiguates the caller's question — it always has one, having
    read the resource group out of a server id served by :func:`project_servers`. Both
    spellings are accepted, the GUID the served ids carry and the generator's own scope
    label, so a request built either way is answered rather than silently emptied.

    An unknown or empty ``server_name`` returns ``[]``: that is what the caller receives
    for a server with no databases, and it iterates the answer without branching on it.
    """
    rows: list[dict[str, object]] = []
    for resource in scope.of_type(estate, DATABASE):
        if server_name_for(resource.resource_name) != server_name:
            continue
        if subscription_id is not None and subscription_id not in (
            resource.parent_scope_id,
            arm.subscription_id(estate, resource.parent_scope_id),
        ):
            continue
        rows.append(_database_row(estate, resource, server_name))
    return rows

