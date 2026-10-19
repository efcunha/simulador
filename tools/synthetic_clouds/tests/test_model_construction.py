"""Smoke-build one instance of each canonical dataclass with marker fields set.

Proves the model layer is import-clean and the frozen dataclasses accept the
documented field shapes (design sec. 4). Not an AC test — a Step-3 guard.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from tools.synthetic_clouds.model.billing import (
    BillingLine,
    ContractedPrice,
    DailyConsumption,
    ListPrice,
)
from tools.synthetic_clouds.model.capacity import CapacityReservation
from tools.synthetic_clouds.model.commitments import Commitment, Credit, Tax
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.hierarchy import (
    AzureMgmtGroup,
    AzureSubscription,
    BillingAccount,
    GcpFolder,
    GcpOrg,
    GcpProject,
)
from tools.synthetic_clouds.model.iac import IacResourceState, IacStateSnapshot, InventoryAsset
from tools.synthetic_clouds.model.identity import IdentityFactory, ResourceIdentity
from tools.synthetic_clouds.model.invoice import Invoice, InvoiceLine
from tools.synthetic_clouds.model.metrics import MetricPoint, MetricSeries
from tools.synthetic_clouds.model.native import NativeFinding, NativeRecommendation
from tools.synthetic_clouds.model.resource import Resource

_DAY = date(2026, 1, 5)
_TS = datetime(2026, 1, 6, 0, 0, 0, tzinfo=UTC)


def _identity() -> ResourceIdentity:
    return IdentityFactory(seed=123).for_path("azure/sub-01/rg/vm/web-01", "azure")


def test_identity_factory_is_deterministic() -> None:
    f = IdentityFactory(seed=123)
    a = f.for_path("azure/sub-01/rg/vm/web-01", "azure")
    b = f.for_path("azure/sub-01/rg/vm/web-01", "azure")
    assert a == b
    assert a.uuid == b.uuid
    other = IdentityFactory(seed=999).for_path("azure/sub-01/rg/vm/web-01", "azure")
    assert other.uuid != a.uuid


def test_build_one_of_each_entity() -> None:
    ident = _identity()
    resource = Resource(
        identity=ident,
        parent_scope_id="sub-01",
        service_name="Virtual Machines",
        service_category="Compute",
        resource_type="virtual_machine",
        resource_name="web-01",
        region_id="eastus",
        region_name="East US",
        tags=(("env", "prod"),),
        sku_id="Standard_D2s_v5",
        capacity_reservation=CapacityReservation(
            reservation_id="cr-0123456789abcdef0",
            resource_uuid=ident.uuid,
            scope_id="sub-01",
            period_start=_DAY,
            period_end=_DAY,
            status="Used",
        ),
    )
    consumption = DailyConsumption(
        resource_uuid=ident.uuid,
        usage_date=_DAY,
        export_time=_TS,
        quantity=Decimal("24.000000"),
        unit="Hours",
        is_restatement=False,
        restates_date=None,
    )
    line = BillingLine(
        line_id="line-1",
        resource_uuid=ident.uuid,
        billing_account_id="ba-azure-1",
        sub_account_id="sub-01",
        invoice_id=None,
        service_name="Virtual Machines",
        service_category="Compute",
        charge_category="Usage",
        charge_period_start=_TS,
        charge_period_end=_TS,
        billing_period_start=_DAY,
        billing_period_end=_DAY,
        export_time=_TS,
        is_restatement=False,
        restates_date=None,
        billed_cost=Decimal("1.000000"),
        effective_cost=Decimal("1.000000"),
        list_cost=Decimal("1.200000"),
        contracted_cost=Decimal("1.000000"),
        pricing_quantity=Decimal("24.000000"),
        pricing_unit="Hours",
        pricing_category="Standard",
        region_id="eastus",
        region_name="East US",
        tags=(("env", "prod"),),
        commitment_discount_id=None,
        commitment_discount_status=None,
        currency="USD",
        service_provider_name="Microsoft Azure",
        is_duplicate=False,
        source_fingerprint="synth:line-1",
    )
    estate = CanonicalEstate(
        seed=123,
        profile="small",
        currency="USD",
        currency_conversion_rate=None,
        sim_start=_DAY,
        sim_now=_DAY,
        billing_accounts=(
            BillingAccount(ident, "azure", "ba-azure-1", "[SYNTH] Azure Billing", "USD"),
        ),
        azure_mgmt_groups=(
            AzureMgmtGroup(
                ident,
                "tenant-contoso",
                "[SYNTH] Root MG",
                (AzureSubscription(ident, "sub-01", "ba-azure-1", "[SYNTH] Prod"),),
            ),
        ),
        gcp_orgs=(
            GcpOrg(
                ident,
                "organizations/1",
                "contoso.example",
                (GcpFolder(ident, "folders/1", (GcpProject(ident, "contoso-prod", "ba-gcp-1", "[SYNTH] Prod"),)),),
            ),
        ),
        aws_orgs=(),
        resources=(resource,),
        consumption=(consumption,),
        billing_lines=(line,),
        list_prices=(ListPrice("Standard_D2s_v5", "Hours", Decimal("0.050000"), "USD"),),
        contracted_prices=(ContractedPrice("Standard_D2s_v5", "Hours", Decimal("0.042000"), "USD", None),),
        commitments=(
            Commitment(
                ident,
                "reservation",
                "sub-01",
                _DAY,
                _DAY,
                Decimal("100.000000"),
                "Used",
                "[SYNTH] Reserved Instance sub-01",
                Decimal("720.000000"),
                "Hours",
            ),
        ),
        credits=(Credit(ident, "sub-01", "promo", Decimal("10.000000"), Decimal("50.000000"), _DAY, _DAY),),
        taxes=(Tax("sub-01", _DAY, Decimal("5.000000"), "USD"),),
        invoices=(
            Invoice(
                "inv-1",
                "ba-azure-1",
                _DAY,
                _DAY,
                "Estimated",
                Decimal("1.000000"),
                "USD",
                (InvoiceLine("inv-1", "line-1", Decimal("1.000000")),),
            ),
        ),
        inventory=(InventoryAsset(ident.uuid, "Microsoft.Compute/virtualMachines", {"synthetic": True}, True),),
        findings=(
            NativeFinding(
                "find-1",
                ident.uuid,
                "azure",
                "NETWORK",
                "HIGH",
                "open",
                _DAY,
                "synthetic",
                {"synthetic": True},
            ),
        ),
        recommendations=(
            NativeRecommendation("rec-1", ident.uuid, "azure", "rightsize", "synthetic.seed.v1", {"synthetic": True}),
        ),
        metrics=(MetricSeries(ident.uuid, "cpu_utilization", (MetricPoint(_TS, 0.1),)),),
        iac_snapshots=(
            IacStateSnapshot(
                "snap-1",
                "sub-01",
                _TS,
                (IacResourceState(ident.uuid, {"declared": True}),),
                {"synthetic": True},
            ),
        ),
        scenario_ids=("C01",),
    )
    assert estate.resource_uuids() == frozenset({ident.uuid})
    assert estate.billing_lines[0].source_fingerprint.startswith("synth:")
    reservation = estate.resources[0].capacity_reservation
    assert reservation is not None
    assert reservation.resource_uuid == ident.uuid
