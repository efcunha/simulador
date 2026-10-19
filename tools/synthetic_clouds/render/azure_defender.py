"""Microsoft Defender for Cloud — continuous export (security surface).

Surface: ``specs/azure/defender-for-cloud-continuous-export.schema.json`` — 114 columns in
4 named sets, 93 emittable/generatable, all of them in the three sets this renderer
delivers: ``SecurityAlert`` (35), ``SecurityRecommendation`` (23) and
``Microsoft.Security/automations`` (35).

WHAT THE DESTINATIONS ARE (and what they are NOT)
-------------------------------------------------
The spec's ``delivery.kind`` is ``log-analytics+event-hub``. The documented destinations are
a Log Analytics workspace, Azure Event Hubs and Azure Logic Apps; **Azure Storage is NOT a
destination** — no consulted page says continuous export writes to a storage account, and
the spec registers that as its own delivery note. There is likewise no documented
``path_template``, ``format`` or ``compression`` for this surface, because the documented
unit is the TABLE the records land in, not the path of a file.

The delivered artifact is therefore ONE JSON document per destination table, carrying the
records in the shape the table defines — the same JSON body the documented destinations
receive ("Defender for Cloud sends data in JavaScript Object Notation (JSON) format"). No
container, no partition and no manifest is invented for it. The Event Hubs destination
carries the same record JSON; its message envelope, headers and partition key are recorded
as UNVERIFIED by the spec, so no envelope is emitted.

WHAT HAS A PUBLISHED SCHEMA
---------------------------
Only ``SecurityAlert`` and ``SecurityRecommendation`` are published tables. Secure score,
regulatory compliance, sub-assessments and attack paths have NO documented destination
table, so no record is emitted for them; ``securityresources/microsoft.security/attackpaths``
is additionally ``author-classification`` in every column (no type, no evidence), and the
correct artifact for that set is *no artifact at all*.

``Microsoft.Security/automations`` is the export's CONFIGURATION resource, not an exported
record. It is delivered so that the configuration that CAUSES the two streams exists in the
documented shape; the estate models no automation object, so every one of its 35 columns is
emitted empty.

THE VALUES, AND WHERE THEY COME FROM
------------------------------------
``estate.findings`` (provider ``azure``) is the source of the alerts and
``estate.recommendations`` (provider ``azure``) of the recommendations. Filled:
``SystemAlertId``/``RecommendationId`` (the estate's own deterministic ids),
``TimeGenerated``, the two documented constant columns (``Type``; ``ProductName`` on the
alert), and ``AlertSeverity`` through a case-normalization onto the documented literals
``High``/``Medium``/``Low`` — a model severity with no documented counterpart (``CRITICAL``)
stays EMPTY rather than being mapped by a rule no page states.

The model's finding ALSO carries name, description and provenance, and the alert columns that
mean those things are filled from them: ``AlertName``/``DisplayName`` (the two columns the
documentation describes with the same "display name" meaning) from ``title``, ``Description``
from ``description``, ``VendorName`` from ``company_name`` and ``TimeGenerated`` from
``first_observed_at``. What the model has but the Microsoft schema does NOT publish stays
EMPTY, deliberately: ``AlertType`` (no alert-type enumeration is published, and the model's
``types`` is the ASFF's ``namespace/category/classifier`` shape), ``ConfidenceScore`` and
``ConfidenceLevel`` (neither the numeric scale nor the ``High``/``Low`` enum is published,
so the model's 0-100 ``confidence`` is NOT mapped by analogy with the ASFF), ``ProviderName``
(the documentation itself describes the column as unused) and ``criticality``/``generator_id``
(no corresponding column exists at all).

Everything else is empty because the model carries nothing for it: no ARM resource id (so
``ResourceId`` and ``AssessedResourceId`` — the join keys — are empty), no alert link, no
recommendation display name/severity/state, and no workspace coordinates.

The estate's ``evidence_json``/``detail_json`` marker bags (``synthetic``, ``rule``, ``kind``)
are FinOps-side keys that exist in no Defender schema, so they are NOT spread into
``ExtendedProperties``/``Properties``/``RecommendationAdditionalData``: those stay empty.
"""

from __future__ import annotations

import json
from datetime import UTC
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    Column,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding, NativeRecommendation
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    documented_document,
    documented_projection,
    emittable_columns,
    not_generated,
    provenance,
    write_json,
)
from tools.synthetic_clouds.render.base import RenderError

#: O caminho da especificação normativa DENTRO de ``specs/`` (a proveniência cita este texto).
_SPEC_FILE = "azure/defender-for-cloud-continuous-export.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: Escopos (nomes de conjunto) desta superfície, tal como o ``.schema.json`` os nomeia.
ALERT_SCOPE = "SecurityAlert"
RECOMMENDATION_SCOPE = "SecurityRecommendation"
AUTOMATION_SCOPE = "Microsoft.Security/automations"
ATTACK_PATH_SCOPE = "securityresources/microsoft.security/attackpaths"

#: Literais CONSTANTES que a própria documentação fixa para a coluna. Não são um valor
#: plausível escolhido aqui: a tabela oficial afirma o valor ("constant ('Azure Security
#: Center')" / "constant ('SecurityAlert')"), e uma coluna constante só tem esse valor.
_PRODUCT_NAME = "Azure Security Center"
_ALERT_TABLE = "SecurityAlert"
_RECOMMENDATION_TABLE = "SecurityRecommendation"

#: ``AlertSeverity`` documenta o domínio ``High``/``Medium``/``Low``/``Informational``
#: (alerts-schemas, aba *Continuous export*). ``NativeFinding.severity`` é o vocabulário
#: NATIVO em maiúsculas (``CRITICAL|HIGH|MEDIUM|LOW``, ``model/native.py``): a entrada
#: abaixo é a normalização de caixa para o literal documentado, e ``CRITICAL`` fica de fora
#: de propósito -- a Azure não publica o literal correspondente, e inventar um seria pior do
#: que deixar o campo vazio.
_ALERT_SEVERITY: dict[str, str] = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}


@cache
def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada uma vez; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _blank_record(columns: tuple[Column, ...]) -> dict[str, Any]:
    """O registo com EXATAMENTE as colunas documentáveis do conjunto, todas vazias."""
    return dict.fromkeys((column.name for column in columns), None)


def azure_findings(estate: CanonicalEstate) -> list[NativeFinding]:
    """Os achados nativos do provedor Azure, em ordem determinística."""
    return sorted(
        (finding for finding in estate.findings if finding.provider == _AZURE),
        key=lambda finding: finding.finding_id,
    )


def azure_recommendations(estate: CanonicalEstate) -> list[NativeRecommendation]:
    """As recomendações nativas do provedor Azure, em ordem determinística."""
    return sorted(
        (recommendation for recommendation in estate.recommendations if recommendation.provider == _AZURE),
        key=lambda recommendation: recommendation.recommendation_id,
    )


def alert_record(finding: NativeFinding) -> dict[str, Any]:
    """Um registo da tabela ``SecurityAlert`` a partir de ``finding``.

    Cada coluna preenchida tem o significado documentado e um campo do modelo:

    * ``AlertName``/``DisplayName`` — as DUAS colunas que a documentação descreve como "the
      alert's display name" recebem o MESMO ``title`` do achado; o modelo tem um nome só, e a
      especificação nomeia duas colunas com o mesmo facto (não se inventa um segundo nome);
    * ``Description`` — ``description``;
    * ``VendorName`` — "the name of the vendor that provided the alert": ``company_name``, que é
      exatamente a procedência do achado (``model/native.py``);
    * ``TimeGenerated`` — "UTC timestamp on which the assessment took place (Security Center's
      scan time)": ``first_observed_at``, o instante (com fuso) em que o problema foi observado.
      Uma finding construída sem o instante cai na meia-noite do seu ``raised_on`` -- a
      granularidade que ela realmente tem, e nunca uma hora inventada;
    * ``SystemAlertId``, ``Type`` e ``ProductName`` — como antes (o id do achado e as duas
      CONSTANTES que a documentação fixa);
    * ``AlertSeverity`` — a normalização de caixa para os literais publicados.

    NÃO preenchidas, e por quê: ``AlertType`` (a Azure não publica a enumeração de tipos de
    alerta, e ``types`` do modelo tem a forma ``namespace/category/classifier`` do ASFF — outro
    vocabulário); ``ConfidenceScore``/``ConfidenceLevel`` (a escala numérica e o enum
    ``High``/``Low`` não são publicados: preencher com o ``confidence`` 0-100 do modelo seria
    preencher por analogia com o ASFF); ``ProviderName`` (a própria documentação o descreve como
    "unused"); ``Status``/``IsIncident``/``StartTime``/``EndTime``/``RemediationSteps``/``Entities``
    e os sacos ``Extended*`` (nenhum deles tem campo no modelo, e os sacos de marcadores do
    FinOps não são chaves de schema nenhum). ``product_name`` do modelo também não entra em
    ``ProductName``: essa coluna é uma CONSTANTE documentada.
    """
    record = _blank_record(emittable_columns(_spec(), ALERT_SCOPE))
    record["SystemAlertId"] = finding.finding_id
    record["AlertName"] = finding.title or None
    record["DisplayName"] = finding.title or None
    record["Description"] = finding.description or None
    record["VendorName"] = finding.company_name or None
    record["AlertSeverity"] = _ALERT_SEVERITY.get(finding.severity)
    record["TimeGenerated"] = _observation_instant(finding)
    record["Type"] = _ALERT_TABLE
    record["ProductName"] = _PRODUCT_NAME
    return record


def _observation_instant(finding: NativeFinding) -> str | None:
    """O instante documentado do achado: ``first_observed_at``, ou o dia de ``raised_on``.

    O fuso é preservado (``+00:00`` -> ``Z``) e a fração de segundo não é descartada quando o
    modelo a tem: o valor entregue é o MESMO instante que o gate valida no modelo.
    """
    if finding.first_observed_at is not None:
        return finding.first_observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if finding.raised_on is not None:
        return f"{finding.raised_on.isoformat()}T00:00:00Z"
    return None


def recommendation_record(recommendation: NativeRecommendation, estate: CanonicalEstate) -> dict[str, Any]:
    """Um registo da tabela ``SecurityRecommendation`` a partir de ``recommendation``.

    ``TimeGenerated`` é aqui "Instante de geração do registo" (o instante em que a
    exportação produziu a linha), e o modelo não carrega data para uma recomendação: a
    projeção é o último dia da janela simulada. ``DiscoveredTimeUTC`` -- a data da
    *descoberta* -- não é o mesmo facto e fica vazio.
    """
    record = _blank_record(emittable_columns(_spec(), RECOMMENDATION_SCOPE))
    record["RecommendationId"] = recommendation.recommendation_id
    record["TimeGenerated"] = f"{estate.sim_now.isoformat()}T00:00:00Z"
    record["Type"] = _RECOMMENDATION_TABLE
    return record


def automation_document() -> dict[str, Any]:
    """O recurso ``Microsoft.Security/automations`` na forma documentada, sem valor nenhum.

    O estado canônico não modela objeto de automação: ele não sabe para onde a exportação
    aponta, nem quais ``EventSource`` avalia. Emitir a FORMA (os 35 caminhos documentados)
    com todos os valores vazios diz exatamente isso; preencher ``properties.actions[].actionType``
    com um literal do enum documentado afirmaria uma configuração que ninguém modelou.
    """
    return documented_document(emittable_columns(_spec(), AUTOMATION_SCOPE), {})


class AzureDefenderRenderer:
    """Entrega os registos da exportação contínua do Defender: alertas, recomendações e a configuração."""

    name = "azure_defender"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve os três documentos JSON e o relatório sob ``out_dir/azure_defender``."""
        target = out_dir / self.name
        alerts = target / "SecurityAlert.json"
        recommendations = target / "SecurityRecommendation.json"
        automations = target / "Microsoft.Security_automations.json"
        findings = azure_findings(estate)
        recs = azure_recommendations(estate)
        write_json(alerts, [alert_record(finding) for finding in findings])
        write_json(recommendations, [recommendation_record(recommendation, estate) for recommendation in recs])
        write_json(automations, automation_document())
        # A projeção é derivada dos BYTES entregues (lidos de volta do disco): o recurso de
        # automação é o único documento ANINHADO destes três, e carrega os 35 caminhos que a
        # spec enumera -- os contêineres ``properties``/``systemData`` não são colunas dela.
        projection = target / "field_projection" / "Microsoft.Security_automations.json"
        write_json(
            projection,
            documented_projection(
                json.loads(automations.read_text(encoding="utf-8")), emittable_columns(_spec(), AUTOMATION_SCOPE)
            ),
        )
        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=[
                    "SecurityAlert.json",
                    "SecurityRecommendation.json",
                    "Microsoft.Security_automations.json",
                    "field_projection/Microsoft.Security_automations.json",
                    PROVENANCE_FILE,
                ],
                mechanism={
                    "kind": "log-analytics + event-hub",
                    "destinations": ["Log Analytics workspace (Azure Monitor)", "Azure Event Hubs", "Azure Logic Apps"],
                    "tables": {"SecurityAlert": "alertas", "SecurityRecommendation": "avaliacoes/recomendacoes"},
                    "format": "json",
                    "storage_destination": None,
                    "storage_note": (
                        "Azure Storage NAO e destino documentado da exportacao continua: nenhum contentor, "
                        "particao ou caminho de blob e emitido"
                    ),
                    "path_template": None,
                    "compression": None,
                    "manifest": None,
                    "event_hub_envelope": None,
                    "event_hub_envelope_note": (
                        "a spec registra o envelope/headers/partition key da mensagem de Event Hubs como UNVERIFIED: "
                        "o mesmo JSON do registro e o que se entrega, sem envelope"
                    ),
                    "cadence": (
                        "streaming quando o estado de saude muda (Assessment) e snapshot semanal por assinatura, "
                        "identificado por ``IsSnapshot``"
                    ),
                },
                columns={
                    "documented": len(_spec().columns),
                    "emittable": len(_spec().emittable_names),
                    "per_set": {
                        scope: {
                            "documented": len(_spec().columns_for(scope)),
                            "emittable": len(emittable_columns(_spec(), scope)),
                        }
                        for scope in (ALERT_SCOPE, RECOMMENDATION_SCOPE, AUTOMATION_SCOPE, ATTACK_PATH_SCOPE)
                    },
                    "generated": len(emittable_columns(_spec(), ALERT_SCOPE))
                    + len(emittable_columns(_spec(), RECOMMENDATION_SCOPE))
                    + len(emittable_columns(_spec(), AUTOMATION_SCOPE)),
                },
                counts={
                    "alerts": len(findings),
                    "recommendations": len(recs),
                    "automations": 1,
                    "attack_path_records": 0,
                    "alert_columns": len(emittable_columns(_spec(), ALERT_SCOPE)),
                    "recommendation_columns": len(emittable_columns(_spec(), RECOMMENDATION_SCOPE)),
                    "automation_columns": len(emittable_columns(_spec(), AUTOMATION_SCOPE)),
                    "alert_columns_with_value": len(
                        [name for name, value in alert_record(findings[0]).items() if value is not None]
                    )
                    if findings
                    else 0,
                    "alert_columns_with_value_note": (
                        "colunas da tabela de alertas que recebem valor do modelo ou de uma constante "
                        "documentada (``Type``/``ProductName``)"
                    ),
                },
                not_generated=not_generated(_spec(), AUTOMATION_SCOPE) + not_generated(_spec(), ATTACK_PATH_SCOPE),
                model_gaps=[
                    {
                        "item": "ARM resource id do recurso afetado (``ResourceId``/``AssessedResourceId``)",
                        "reason": (
                            "o modelo nao carrega o ARM id do recurso (a NIC tem o dela): as duas colunas que ligam "
                            "o registro ao recurso avaliado ficam vazias"
                        ),
                    },
                    {
                        "item": "nome, tipo e ligacao do alerta",
                        "reason": (
                            "``NativeFinding.title``/``description`` preenchem ``AlertName``/``DisplayName``/``Description``; "
                            "``AlertType`` continua VAZIO porque a Azure nao publica a enumeracao de tipos de alerta e o "
                            "``types`` do modelo tem a forma ``namespace/category/classifier`` do ASFF (outro vocabulario); "
                            "``AlertLink``/``RemediationSteps`` nao existem no modelo"
                        ),
                    },
                    {
                        "item": "procedencia e escalas do achado sem coluna documentada",
                        "reason": (
                            "``generator_id`` e ``criticality`` nao tem coluna correspondente na tabela ``SecurityAlert``; "
                            "``product_name`` nao entra em ``ProductName`` (constante documentada) e ``ProviderName`` e "
                            "descrito pela propria documentacao como unused; ``confidence`` (0-100) nao preenche "
                            "``ConfidenceScore``/``ConfidenceLevel``, cuja escala/enum a Microsoft nao publica -- preencher "
                            "por analogia com o ASFF seria inventar vocabulario"
                        ),
                    },
                    {
                        "item": "nome de exibicao, severidade e estado da recomendacao",
                        "reason": (
                            "``NativeRecommendation.kind`` e vocabulario do simulador (rightsize/idle/sku_change), "
                            "nao um display name publicado, e o modelo nao carrega estado nem severidade"
                        ),
                    },
                    {
                        "item": "coordenadas do workspace / do Event Hub",
                        "reason": "o modelo nao tem workspace, resource group nem subscription de destino",
                    },
                    {
                        "item": "objeto de automacao (``Microsoft.Security/automations``)",
                        "reason": (
                            "nenhuma entidade modela a configuracao da exportacao: a FORMA sai com os 35 membros "
                            "vazios, e ``actionType`` nao recebe um literal do enum so para parecer configurado"
                        ),
                    },
                    {
                        "item": "payload de attack path",
                        "reason": (
                            "todas as 21 colunas do conjunto sao ``author-classification`` (sem tipo, sem evidencia): "
                            "o artefato correto para esse conjunto e NENHUM"
                        ),
                    },
                    {
                        "item": "vocabulario de gravidade",
                        "reason": (
                            "``NativeFinding.severity`` e maiusculo (CRITICAL/HIGH/MEDIUM/LOW) e o dominio documentado "
                            "e High/Medium/Low/Informational: HIGH/MEDIUM/LOW sao normalizados para o literal publicado "
                            "e CRITICAL fica VAZIO, porque a Azure nao publica o correspondente"
                        ),
                    },
                ],
            ),
        )
        return [alerts, recommendations, automations, projection, target / PROVENANCE_FILE]
