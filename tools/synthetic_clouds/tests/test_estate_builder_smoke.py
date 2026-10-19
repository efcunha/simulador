"""Build a tiny estate and assert end-to-end identity reuse (P2) and markers.

Step-4 guard: proves the generator orchestration produces non-empty tuples and
that one resource identity is reused across resource/consumption/billing/
inventory/metric (P2 threading).
"""

from __future__ import annotations

from tools.synthetic_clouds.generate.estate_builder import build_estate


def test_small_estate_builds_nonempty() -> None:
    estate = build_estate(seed=123, profile="small", currency="USD")
    assert estate.resources
    assert estate.consumption
    assert estate.billing_lines
    assert estate.inventory
    assert estate.invoices  # closed periods exist in a 45-day window spanning Jan->Feb
    # 3 Azure subs + 3 GCP projects (FR-A1).
    assert len(estate.azure_mgmt_groups[0].subscriptions) == 3
    assert len(estate.gcp_orgs[0].folders[0].projects) == 3
    # 2 billing accounts per provider.
    assert sum(1 for b in estate.billing_accounts if b.provider == "azure") == 2
    assert sum(1 for b in estate.billing_accounts if b.provider == "gcp") == 2


def test_identity_threads_end_to_end() -> None:
    estate = build_estate(seed=123, profile="small", currency="USD")
    # Pick a resource that has metrics (VM/compute/sql).
    metered = {m.resource_uuid for m in estate.metrics}
    assert metered
    uuid = next(iter(metered))
    assert uuid in estate.resource_uuids()
    assert any(c.resource_uuid == uuid for c in estate.consumption)
    assert any(b.resource_uuid == uuid for b in estate.billing_lines)
    assert any(a.resource_uuid == uuid for a in estate.inventory)


def test_null_resource_line_present_and_unique() -> None:
    estate = build_estate(seed=123, profile="small", currency="USD")
    null_lines = [b for b in estate.billing_lines if b.resource_uuid is None]
    assert len(null_lines) == 1
    assert null_lines[0].charge_category == "Tax"


def test_brl_currency_sets_conversion_rate() -> None:
    estate = build_estate(seed=123, profile="small", currency="BRL")
    assert estate.currency == "BRL"
    assert estate.currency_conversion_rate is not None
    assert all(b.currency == "BRL" for b in estate.billing_lines)
