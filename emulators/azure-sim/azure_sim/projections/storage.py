"""Azure Storage resource plane: ``storageAccounts`` (Phase 6).

``storage_accounts.list`` is consumed: ``resources.py (modulo do consumidor):70``
reads ``sa.id``, ``sa.name``, ``sa.location`` and ``sa.sku.name``, so ``sku`` is emitted as
a top-level block — that is where ``StorageAccount._attribute_map`` (checked against the
installed ``azure-mgmt-storage`` 24.0.1) looks for it, and a row that nested it under
``properties`` would deserialize with ``sku = None`` while still looking right in a
browser.

The estate names one SKU per resource (``azure-blob-hot``, the account's access tier) and
no storage configuration at all — no endpoint, no network rule, no redundancy setting — so
the closed map below is the whole authored surface here: it turns that SKU into the ARM
account SKU, its kind and its access tier, and it raises on an unmapped SKU rather than
guessing (the rule ``aws_sim/projections/ec2.py:82`` applies to volume types). Everything
else stays absent, deliberately: ``primaryEndpoints`` would be an invented client endpoint
and ``networkAcls`` a fabricated network rule, and both are read by real callers as
configuration.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, scope

STORAGE_ACCOUNT = "storage_account"

#: ``sku_id`` -> (ARM sku name, sku tier, account kind, access tier). One entry per SKU the
#: generator emits; ``azure-blob-hot`` names a hot-tier block blob account, which is
#: standard locally-redundant storage.
STORAGE_SKUS: dict[str, tuple[str, str, str, str]] = {
    "azure-blob-hot": ("Standard_LRS", "Standard", "StorageV2", "Hot"),
}


def _storage_account_row(estate: CanonicalEstate, resource: Resource) -> dict[str, object]:
    """One ``storageAccounts`` row for an estate storage account."""
    sku_name, tier, kind, access_tier = STORAGE_SKUS[resource.sku_id]
    return arm.arm_row(
        estate,
        resource,
        arm_type=arm.STORAGE_ACCOUNT_TYPE,
        properties={
            "accessTier": access_tier,
            "provisioningState": arm.PROVISIONING_SUCCEEDED,
        },
        top_level={
            "sku": {"name": sku_name, "tier": tier},
            "kind": kind,
        },
    )


def project_storage_accounts(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``storage_accounts.list`` rows: this provider's accounts, by name."""
    return [
        _storage_account_row(estate, resource) for resource in scope.of_type(estate, STORAGE_ACCOUNT)
    ]

