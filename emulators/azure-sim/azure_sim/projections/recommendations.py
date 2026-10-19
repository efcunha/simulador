"""Advisor projection (design §5).

Projects ``estate.recommendations`` into Azure Advisor ``recommendations`` rows.
A native recommendation is a cloud INPUT; FinOps computes any opportunity or
savings ranking from these (P1). This projection never emits a FinOps-computed
output.

TODO-verificar §11.10: the exact Advisor ``recommendations`` envelope keys
(``category``/``impact``/``shortDescription``/``properties``) and the category/
impact vocabularies are NOT offline-verifiable. Rows are emitted official-shaped
and flagged.

``resourceId`` is the recommended resource's ARM id (``arm.resource_id_of_uuid``): Advisor
names the resource, not the estate, and that is the id every other Azure surface in this
package publishes for it.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeRecommendation

from azure_sim.projections import arm, scope


def _recommendation_row(estate: CanonicalEstate, rec: NativeRecommendation) -> dict[str, object]:
    """Project one native recommendation into an Advisor row.

    ``properties`` is EMPTY, and stays empty: ``NativeRecommendation.detail_json`` is a
    FinOps-side marker bag (``synthetic`` + ``kind``, ``generate/estate_builder.py:504``)
    whose keys the official Advisor shape does not define, so spreading it wrote a
    ``synthetic`` key into every recommendation. The estate models no Advisor property
    (``impact``/``shortDescription``/``resourceMetadata``/...), and absence is absence.

    ``recommendationModel`` is likewise blank: the estate's value for it is
    ``markers.RECOMMENDATION_MODEL`` (``synthetic.seed.v1``), the generator's own model
    tag rather than anything an Advisor row carries. The key stays so the row keeps the
    shape its consumers and tests describe.
    """
    # TODO-verificar §11.10: official Advisor row key names/casing.
    return {
        "id": rec.recommendation_id,
        "resourceId": arm.resource_id_of_uuid(estate, rec.resource_uuid) or rec.resource_uuid,
        "category": rec.kind,
        "recommendationModel": "",
        "properties": {},
    }


def project_recommendations(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Advisor ``recommendations`` rows for THIS provider, ordered by id."""
    rows = [_recommendation_row(estate, rec) for rec in scope.recommendations(estate)]
    return sorted(rows, key=lambda row: str(row["id"]))
