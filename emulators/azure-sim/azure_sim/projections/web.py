"""Azure Web Apps resource plane: ``sites`` (Phase 6).

``web_apps.list`` is consumed — ``service_discovery.py (modulo do consumidor):374``
reads ``app.name`` and ``app.location`` — and that pair is the whole row this estate backs
honestly. It models an ``app_service`` as identity, region, tags and a plan SKU
(``azure-app-plan-b1``); it carries no App Service plan resource, no runtime stack, no
hostname binding, no site configuration and no deployment slot, so none of those appear.
``serverFarmId`` in particular is omitted rather than derived: it would point at a plan the
estate does not carry, and a caller that followed it would find nothing on the other end.

``properties.state`` is ``Running`` — Azure's own vocabulary for a live site, and the reading
of an estate that bills for it — and it is emitted because it is the one site attribute the
estate's fact (the site is owned and metered) actually determines. The plan SKU is not
promoted to an ARM plan name for the reason the AKS projection gives: nothing reads it.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate

from azure_sim.projections import arm, scope

APP_SERVICE = "app_service"

#: Azure's state vocabulary for a site that is serving (``Stopped`` is the other value, and
#: the estate has no way to express it).
SITE_STATE_RUNNING = "Running"


def project_sites(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``web_apps.list`` rows: this provider's App Services, ordered by name."""
    return [
        arm.arm_row(
            estate,
            resource,
            arm_type=arm.SITE_TYPE,
            properties={
                "state": SITE_STATE_RUNNING,
                "provisioningState": arm.PROVISIONING_SUCCEEDED,
            },
        )
        for resource in scope.of_type(estate, APP_SERVICE)
    ]

