"""Defender for Cloud projections (design §5, §8 C09).

Projects ``estate.findings`` into Defender ``assessments`` rows, a ``secureScores``
summary, and ``alerts`` rows. All native inputs: a finding is a cloud INPUT, so
``severity`` stays UPPERCASE (``CRITICAL|HIGH|MEDIUM|LOW``) exactly as the estate
models it — never lowercased to match FinOps drift output (see
``model/native.py`` Finding-7 note). FinOps computes posture verdicts from
these; this emits only native assessment records (P1).

TODO-verificar §11.9: the exact Defender assessment/secureScore/alert envelope
keys and the ``status.code`` vocabulary (``Healthy``/``Unhealthy``) are NOT
offline-verifiable. Rows are emitted official-shaped and flagged.

``resourceId`` is the ASSESSED resource's ARM id (``arm.resource_id_of_uuid``), which is what
Defender reports and what the resource plane published for that resource; a finding whose
resource this provider does not own carries the estate's own uuid instead, because no ARM id
exists for it to carry. The estate's ``resource_name`` is not used: it is a display name
reused across subscriptions, and a finding keyed by one would be a finding about several
resources.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding

from azure_sim.projections import arm, scope

# TODO-verificar §11.9: official Defender assessment status vocabulary.
_STATUS_UNHEALTHY = "Unhealthy"

#: ``properties.resourceDetails.source`` vocabulary, keyed by the estate's operational
#: provider key (``ResourceIdentity.provider``). A value the estate cannot express
#: resolves to the empty string rather than to a guess.
_RESOURCE_DETAILS_SOURCE: dict[str, str] = {"azure": "Azure", "aws": "AWS", "gcp": "GCP"}


def _resource_id(estate: CanonicalEstate, finding: NativeFinding) -> str:
    """The ARM id of the resource a finding sits on (the estate uuid if it has none)."""
    return arm.resource_id_of_uuid(estate, finding.resource_uuid) or finding.resource_uuid


def _assessment_properties(estate: CanonicalEstate, finding: NativeFinding) -> dict[str, object]:
    """Return the ARM ``properties`` block for one Defender assessment.

    Only REAL assessment property keys are emitted, verified against the installed
    ``azure-mgmt-security`` deserializer rather than assumed. ``SecurityAssessmentResponse.
    _attribute_map`` maps exactly ``properties.resourceDetails`` (``ResourceDetails``:
    ``source``/``id``/``connectorId``), ``properties.displayName``,
    ``properties.additionalData``, ``properties.links``, ``properties.metadata``,
    ``properties.partnersData`` and ``properties.status`` (``AssessmentStatus``:
    ``code``/``cause``/``description``).

    ``NativeFinding.evidence_json`` is a FinOps-side marker bag (``synthetic`` +
    ``rule`` + optional ``scenario``, ``generate/estate_builder.py:485``): spreading it
    put a ``synthetic`` key -- which the official shape never defines -- inside every
    assessment. It is NOT projected: the estate carries no ``displayName``, ``links`` or
    ``metadata`` for an assessment, and absence is absence.
    """
    return {
        "resourceDetails": {
            "source": _RESOURCE_DETAILS_SOURCE.get(finding.provider, ""),
            "id": _resource_id(estate, finding),
        },
        "status": {"code": _STATUS_UNHEALTHY},
    }


def _assessment_row(estate: CanonicalEstate, finding: NativeFinding) -> dict[str, object]:
    """Project one native finding into a Defender assessment row.

    Severity casing is preserved verbatim (UPPERCASE input convention).

    No ``source`` key is emitted: ``NativeFinding.source`` is the seed's provenance
    marker (``markers.SOURCE_SYNTHETIC``, the literal string ``synthetic``) and an
    assessment has no such field -- the provider it came from is ``resourceDetails``.
    """
    return {
        "id": finding.finding_id,
        "resourceId": _resource_id(estate, finding),
        "category": finding.category,
        # UPPERCASE preserved on purpose (native input convention, Finding-7).
        "severity": finding.severity,
        "status": {"code": _STATUS_UNHEALTHY},
        "properties": _assessment_properties(estate, finding),
    }


def project_assessments(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Defender ``assessments`` rows for THIS provider, ordered by id."""
    rows = [_assessment_row(estate, finding) for finding in scope.findings(estate)]
    return sorted(rows, key=lambda row: str(row["id"]))


def project_secure_scores(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return a native ``secureScores`` summary (counts per severity).

    This is a native COUNT of findings per severity, not a FinOps posture
    score. The ``current``/``max`` fields are the raw finding tallies Azure's
    secure-score surface exposes; FinOps derives any verdict (P1).
    """
    per_severity: dict[str, int] = {}
    for finding in scope.findings(estate):
        per_severity[finding.severity] = per_severity.get(finding.severity, 0) + 1
    total = sum(per_severity.values())
    # TODO-verificar §11.9: official secureScores envelope key names.
    return [
        {
            "id": "ascScore",
            "properties": {
                "score": {"current": total, "max": total},
                "bySeverity": dict(sorted(per_severity.items())),
            },
        }
    ]


def project_alerts(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return Defender ``alerts`` rows — the CRITICAL/HIGH subset of findings.

    Alerts are the native high-severity finding records; the severity casing is
    preserved. FinOps owns alert triage (P1).
    """
    rows: list[dict[str, object]] = []
    for finding in scope.findings(estate):
        if finding.severity in {"CRITICAL", "HIGH"}:
            rows.append(
                {
                    "id": finding.finding_id,
                    "resourceId": _resource_id(estate, finding),
                    "alertSeverity": finding.severity,
                    "category": finding.category,
                }
            )
    return sorted(rows, key=lambda row: str(row["id"]))
