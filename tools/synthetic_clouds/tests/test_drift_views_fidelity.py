"""Golden fidelity for the two native drift/plan representations.

Surfaces:

* ``gcp/infrastructure-manager-resource-drift`` — ``ResourceDrift``;
* ``azure/deployment-stacks-what-if`` — ``deploymentStacksWhatIfResults``.

The projection is the ARTIFACT: the test renders the registered ``drift_views`` renderer,
reads the files back from disk and compares the flat field projection with the spec. The
nested artifact is also read, to prove the harness did not flatten the delivered payload
into the audit shape (the real API body must stay nested; ``field_projection/`` is the
audit view, not the delivered body).

The drift itself is derived from the drift inputs (IaC snapshot tags vs inventory), not from
a hard-coded scenario. The C11 catalogue's firewall case is not modelled. The test therefore also asserts that the estate yields at least one
GCP modified drift and at least one Azure ``modify`` + ``detach`` — an empty artefact
would satisfy "no invented column" while delivering nothing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.artifacts import columns_of
from tools.synthetic_clouds.fidelity.checker import check
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.drift import project_drift_views
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.base import get_renderer

SPEC_FILES = (
    "gcp/infrastructure-manager-resource-drift.schema.json",
    "azure/deployment-stacks-what-if.schema.json",
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def delivered(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    destination = tmp_path_factory.mktemp("drift_views")
    get_renderer("drift_views").render(estate, destination)
    return destination


def _spec(spec_file: str) -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / spec_file)


def test_the_two_surfaces_are_declared_as_implemented() -> None:
    for spec_file in SPEC_FILES:
        surface = spec_file.removesuffix(".schema.json")
        coverage = matrix.coverage_for(surface)
        assert coverage is not None, surface
        assert coverage.status == matrix.STATUS_IMPLEMENTED, surface
        assert coverage.renderer == "drift_views", surface


def test_the_project_invariants_hold() -> None:
    assert report.staleness() == ()
    assert report.golden_gaps() == ()


@pytest.mark.parametrize(
    ("spec_file", "artifact", "projection"),
    [
        (
            "gcp/infrastructure-manager-resource-drift.schema.json",
            "resource_drifts.json",
            "field_projection/resource_drifts.json",
        ),
        (
            "azure/deployment-stacks-what-if.schema.json",
            "what_if_results.json",
            "field_projection/what_if_results.json",
        ),
    ],
)
def test_the_delivered_projection_matches_the_contract(
    spec_file: str, artifact: str, projection: str, delivered: Path
) -> None:
    spec = _spec(spec_file)
    projection_path = delivered / projection
    rows = json.loads(projection_path.read_text(encoding="utf-8"))
    assert rows, f"{projection}: nenhum registro"
    assert set(columns_of(projection_path)) == set(spec.names)
    assert check(spec, columns_of(projection_path)) == ()


@pytest.mark.parametrize(
    ("artifact", "expected_top"),
    [
        ("resource_drifts.json", {"name", "terraformInfo", "propertyDrifts"}),
        ("what_if_results.json", {"id", "type", "name", "location", "properties"}),
    ],
)
def test_the_delivered_body_is_nested(delivered: Path, artifact: str, expected_top: set[str]) -> None:
    payload = json.loads((delivered / artifact).read_text(encoding="utf-8"))
    assert isinstance(payload, list) and payload
    assert set(payload[0]) == expected_top


def test_the_estate_produces_modified_and_unmanaged_drift(estate: CanonicalEstate) -> None:
    views = project_drift_views(estate)
    assert views.gcp_resource_drifts, "nenhum ResourceDrift GCP"
    assert any(item.property_drifts for item in views.gcp_resource_drifts)

    changes = [change for result in views.azure_what_if_results for change in result.resource_changes]
    assert any(change.change_type == "modify" and change.delta for change in changes)
    assert any(change.change_type == "detach" for change in changes)
    # Cada modificação carrega um delta de tag real; um path vazio seria um diff sem campo.
    assert all(item.path.startswith("labels.") for drift in views.gcp_resource_drifts for item in drift.property_drifts)
    assert all(
        item.path.startswith("tags.") for change in changes for item in change.delta
    )
