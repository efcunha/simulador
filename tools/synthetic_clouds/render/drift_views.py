"""Wire artifacts for the two native drift/plan representations.

Surfaces
--------
* ``gcp/infrastructure-manager-resource-drift`` — ``ResourceDrift`` items;
* ``azure/deployment-stacks-what-if`` — ``deploymentStacksWhatIfResults``.

Both artifacts are projections of :func:`tools.synthetic_clouds.model.drift.project_drift_views`,
the same function the two emulators call. There is no second copy of the mapping: the JSON
file and the HTTP response are the same document by construction.

Artifact and report are separate files, always
-----------------------------------------------
``resource_drifts.json`` / ``what_if_results.json`` carry ONLY documented provider fields.
Everything about the C11 input (which resource, which tag was omitted, what the fixture
version is) lives in the SIBLING ``_provenance.json``. An ingester of the artifact must
never see a key no cloud documents.

The ``field_projection/`` files are the audit view: the flat paths the spec enumerates.
They are derived from the same dataclasses, not from a hand-written list, so a change in
the projection cannot silently desynchronize the two.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.synthetic_clouds.model.drift import (
    azure_flat_rows,
    azure_what_if_document,
    gcp_flat_rows,
    gcp_resource_drift_document,
    project_drift_views,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.azure_arm_instances import PROVENANCE_FILE, write_json

_GCP_ARTIFACT = "resource_drifts.json"
_AZURE_ARTIFACT = "what_if_results.json"
_PROJECTION_DIR = "field_projection"


class DriftViewsRenderer:
    """Write both native representations from one frozen estate."""

    name = "drift_views"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        views = project_drift_views(estate)
        gcp = [gcp_resource_drift_document(item) for item in views.gcp_resource_drifts]
        azure = [azure_what_if_document(item) for item in views.azure_what_if_results]
        gcp_flat = gcp_flat_rows(views.gcp_resource_drifts)
        azure_flat = azure_flat_rows(views.azure_what_if_results)

        written: list[Path] = [
            write_json(out_dir / _GCP_ARTIFACT, gcp),
            write_json(out_dir / _AZURE_ARTIFACT, azure),
            write_json(out_dir / _PROJECTION_DIR / _GCP_ARTIFACT, gcp_flat),
            write_json(out_dir / _PROJECTION_DIR / _AZURE_ARTIFACT, azure_flat),
        ]

        provenance: dict[str, Any] = {
            "kind": "provenance",
            "surface": [
                "gcp/infrastructure-manager-resource-drift",
                "azure/deployment-stacks-what-if",
            ],
            "spec": [
                "specs/gcp/infrastructure-manager-resource-drift.schema.json",
                "specs/azure/deployment-stacks-what-if.schema.json",
            ],
            "artifacts": [
                _GCP_ARTIFACT,
                _AZURE_ARTIFACT,
                f"{_PROJECTION_DIR}/{_GCP_ARTIFACT}",
                f"{_PROJECTION_DIR}/{_AZURE_ARTIFACT}",
                PROVENANCE_FILE,
            ],
            "mechanism": {
                "kind": "c11-consumer-projection",
                "note": (
                    "Drift is NOT a generator verdict. The generator emits the inputs "
                    "(inventory.managed_by_iac + iac_snapshots.declared_config); this "
                    "renderer projects them into the provider-native representations. "
                    "The modelled property is the tag/label map, not the C11 firewall case."
                ),
                "gcp_api": (
                    "GET https://config.googleapis.com/v1/projects/{project}/locations/"
                    "{location}/previews/{preview}/resourceDrifts"
                ),
                "azure_api": (
                    "GET https://management.azure.com/subscriptions/{subscriptionId}/"
                    "resourceGroups/{resourceGroupName}/providers/Microsoft.Resources/"
                    "deploymentStacksWhatIfResults/{name}?api-version=2025-07-01"
                ),
            },
            "counts": {
                "gcp_resource_drifts": len(gcp),
                "gcp_property_drifts": len(gcp_flat),
                "azure_results": len(azure),
                "azure_resource_changes": sum(
                    len(item.resource_changes) for item in views.azure_what_if_results
                ),
            },
            "derivation": {
                "modified": (
                    "declared_config['tags'] vs Resource.tags; the key omitted from the "
                    "snapshot is the first in sorted order, chosen deterministically"
                ),
                "unmanaged": "InventoryAsset.managed_by_iac == false",
                "gcp_address": "google_compute_instance.<sanitized resource name>",
                "azure_id": "ARM id from azure_subscription_guid + synthetic-rg-<scope[:8]>",
            },
            "not_generated": [
                "deploymentScopeChange",
                "denySettingsChange",
                "the full DeploymentStacksWhatIfResult envelope",
            ],
        }
        written.append(write_json(out_dir / PROVENANCE_FILE, provenance))
        return written
