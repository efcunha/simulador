"""Synthetic-provenance markers test (FEAT-003, plan item 12; AC-18 style).

Every emitted artifact must prove it is synthetic — a reader (and this test)
can tell the data references no real estate/secret. Markers reused verbatim from
``tools/synthetic_clouds/render/markers.py`` (design §9); no new scheme invented.

Covered artifacts:
  * manifest.json              -> ``synthetic: true`` + ``synth:``-prefixed schemaFingerprint
  * token endpoint             -> ``synthetic: true`` + a ``synth:``-prefixed bearer
  * /healthz                   -> ``synthetic: true``
  * API list/table envelopes   -> served from the gated synthetic estate; account
                                   names keep the ``[SYNTH]`` prefix, identities
                                   live under ``contoso.example``
  * versioned fixtures         -> ``synthetic: true``
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tools.synthetic_clouds.render.markers import (
    FICTIONAL_DOMAIN,
    SOURCE_FINGERPRINT_PREFIX,
    SYNTH_NAME_PREFIX,
)

from azure_sim.exporter.layout import PeriodWindow
from azure_sim.exporter.manifest import build_manifest

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Manifest marker (exporter artifact).
# ---------------------------------------------------------------------------
def test_manifest_proves_synthetic() -> None:
    period = PeriodWindow(
        start=datetime(2025, 1, 1, tzinfo=UTC).date(),
        end=datetime(2025, 1, 31, tzinfo=UTC).date(),
    )
    manifest = build_manifest(
        export_name="focus-cost",
        export_type="focus",
        export_format="csv",
        agreement="mca",
        period=period,
        columns=["BilledCost", "BillingPeriodStart"],
        parts=[],
        run_id="0" * 16,
        export_time=datetime(2025, 2, 1, tzinfo=UTC),
        dataset_version="1.2",
        seed=42,
        profile="small",
        currency="USD",
    )
    # synthetic: true marker (§9).
    assert manifest["synthetic"] is True
    # synth:-prefixed source fingerprint (§4.2/§9).
    assert manifest["schemaFingerprint"].startswith(SOURCE_FINGERPRINT_PREFIX)


# ---------------------------------------------------------------------------
# Token endpoint marker (API auth artifact).
# ---------------------------------------------------------------------------
def test_token_endpoint_proves_synthetic(api_client) -> None:
    client, _app = api_client
    resp = client.post("/contoso-tenant/oauth2/v2.0/token", data={"grant_type": "client_credentials"})
    assert resp.status_code == 200
    body = resp.json()
    # The issued bearer is plainly synthetic (never a real secret, §9).
    assert body["synthetic"] is True
    assert body["access_token"].startswith(SOURCE_FINGERPRINT_PREFIX)


# ---------------------------------------------------------------------------
# Healthz marker (API liveness artifact).
# ---------------------------------------------------------------------------
def test_healthz_proves_synthetic(api_client) -> None:
    client, _app = api_client
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["synthetic"] is True


# ---------------------------------------------------------------------------
# Estate-sourced artifact markers: account names keep [SYNTH], identities live
# under contoso.example (design §9). Checked on the shared gated estate.
# ---------------------------------------------------------------------------
def test_estate_account_names_prove_synthetic(api_client) -> None:
    _client, app = api_client
    estate = app.state.estate
    # Every billing account display name keeps the [SYNTH] prefix (markers.synth_name).
    account_names = [acct.name for acct in estate.billing_accounts]
    assert account_names, "estate must have at least one billing account"
    assert all(name.startswith(SYNTH_NAME_PREFIX) for name in account_names), (
        f"all account names must carry the {SYNTH_NAME_PREFIX!r} marker"
    )


def test_fictional_domain_constant_is_contoso() -> None:
    # Identities are fictional and live under contoso.example (design §9).
    assert FICTIONAL_DOMAIN == "contoso.example"


# ---------------------------------------------------------------------------
# Fixture markers: every versioned fixture declares itself synthetic.
# ---------------------------------------------------------------------------
def test_every_fixture_proves_synthetic() -> None:
    fixtures = sorted(_FIXTURES_DIR.glob("*.json"))
    assert fixtures, f"no fixtures under {_FIXTURES_DIR}"
    for path in fixtures:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.get("synthetic") is True, f"{path.name} must carry synthetic: true"
