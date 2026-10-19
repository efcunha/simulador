"""Assessments de seguranca do Defender for Cloud -- o corpo de um ``GET`` em ``assessments.list``.

Surface: ``specs/azure/security-assessments-list.schema.json`` -- 36 columns in TWO named sets
(``assessment``, 34, and ``assessmentList``, 2), all of them emittable/generatable. The two sets
are DISJOINT: ``value`` is the pagination envelope and ``SecurityAssessmentResponse`` is the
record, and a ``value`` inside each assessment would be a field the resource does not have --
the same treatment ``NetworkSecurityListResult`` gets in ``azure_nsg_rules``.

WHAT THIS DELIVERES
-------------------
One ``SecurityAssessmentList`` document per AZURE SUBSCRIPTION, at the path the documented URI
itself addresses
(``subscriptions/{subscriptionId}/providers/Microsoft.Security/assessments/assessments.json``).
This is NOT an export: it is the body of an ARM control-plane GET, like
``arm-resource-representation``, and no blob path, partitioning, compression or manifest is
invented for it.

The subscription token is read from the ARM id the model itself composes
(``arm_id_token(segment_id, "subscriptions")``), not recomposed from ``scope_id``: the file path
and the ``id`` inside the document are then incapable of disagreeing about which subscription
they name.

THE VALUES, AND WHERE THEY COME FROM
------------------------------------
``id`` and ``resourceDetails.id`` are the ARM id of the assessed VNet -- the segment's own
``segment_id``, the same id ``azure_vnet_flow_logs`` already delivers. The assessment ``id`` is
that id plus ``/providers/Microsoft.Security/assessments/`` plus ``AzureDefenderAssessment.assessment_id``,
in the exact form the page's response example shows; ``name`` is the same GUID, and ``type`` is
the ``Microsoft.Security/assessments`` the same example publishes.

``status.code`` is ``AzureDefenderAssessment.health`` -- one of the three literals
``AssessmentStatusCode`` publishes. ``metadata.severity`` is the state's severity normalized
into the documented ``Low|Medium|High`` domain, and it is populated ONLY on the ``Unhealthy``
posture: there is no finding severity to project onto a healthy or not-applicable assessment.

``status.firstEvaluationDate``/``statusChangeDate`` are the model's own instants, rendered in the
form the page documents ("UTC time in ISO 8601 format") and in the ``...Z`` spelling of the
response example.

WHAT IS DELIBERATELY EMPTY, AND WHY
-----------------------------------
Everything that belongs to the Defender's own assessment CATALOG stays empty, because the
canonical estate does not model it and inventing a catalog would be asserting something no
consulted page states: ``displayName`` and ``description`` (both levels), ``categories``,
``threats``, ``implementationEffort``, ``userImpact``, ``policyDefinitionId`` and ``preview``.

``status.cause`` is empty too, and this one is a close call: the page's response example shows
``"cause": "OffByPolicy"``. A payload example fixes the SHAPE of a field, not its vocabulary --
publishing the one literal the page happens to show would be inventing a domain out of a sample.
The spec registers it under ``unverified``.

``nextLink`` is empty: the page publishes the pagination member and never publishes a page size
or a cursor example, so a ``nextLink`` here would be a made-up transport token.

THE DIVERGENCE THE CONSUMER HAS WITH THE WIRE (measured, not fixed here)
------------------------------------------------------------------------
``AzureSecurityScanner`` reads the severity as ``assessment.properties.severity``. There is no
``properties.severity`` in this response -- the severity is published at
``properties.metadata.severity``. Worse, measured against the SDK the consumer actually uses
(``azure-mgmt-security`` 7.0.0): ``SecurityCenter(cred, sub).assessments`` resolves to
api-version 2021-06-01 and yields ``SecurityAssessmentResponse``, which FLATTENS ``properties.*``
into top-level attributes and therefore has NO ``properties`` attribute at all --
``assessment.properties`` raises ``AttributeError``, the consumer's ``except Exception`` swallows
it, and the whole check returns ``[]`` while logging ``azure_defender_scan_failed``. Its
``"MEDIUM"`` fallback is dead code: the attribute is evaluated before ``getattr`` ever runs.

This renderer writes the severity to the DOCUMENTED path and leaves the consumer's bug where it
is -- ``FinOps`` is read-only for this work. See ``docs/INGESTAO-D3-SEGURANCA.md``.

ONE MORE THING THE CONSUMER GETS WRONG
--------------------------------------
The consumer discards only ``status.code == "Healthy"``. ``NotApplicable`` is therefore NOT the
discarded branch: the page describes it as "Assessment for this resource did not happen", and an
assessment that never ran still becomes a DEFENDER finding. The estate ships the three codes so
that the one that is actually discarded (``Healthy``) is also the one exercised here.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime
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
from tools.synthetic_clouds.model.native import AzureDefenderAssessment
from tools.synthetic_clouds.model.network import NetworkSegment
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    arm_id_token,
    documented_document,
    documented_projection,
    emittable_columns,
    not_generated,
    provenance,
    write_json,
)
from tools.synthetic_clouds.render.base import RenderError

#: The normative spec path INSIDE ``specs/`` (provenance cites this text).
_SPEC_FILE = "azure/security-assessments-list.schema.json"

#: The normative spec of this surface (source of truth; NEVER edited here).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: The named sets of this surface, as the ``.schema.json`` names them.
ASSESSMENT_SCOPE = "assessment"
ASSESSMENT_LIST_SCOPE = "assessmentList"

#: The resource type the response example publishes for every assessment's ``type``.
_ASSESSMENT_TYPE = "Microsoft.Security/assessments"

#: The provider segment of the assessment ARM id, as the response example publishes it.
_ASSESSMENT_PROVIDER_SEGMENT = "providers/Microsoft.Security/assessments"

#: The envelope prefix the ``assessment`` set carries on every column name: the record lives
#: in ``value[]``, and a path relative to the record alone is not resolvable against the body
#: the consumer reads.
_ENVELOPE_PREFIX = "value[]."

#: The only ``source`` this estate can produce: ``AzureResourceDetails`` publishes it as a
#: LITERAL in the type itself ("source | string: Azure"), and the response example carries
#: ``"source": "Azure"``. The two other variants the union allows are OnPremise.
_AZURE_RESOURCE_SOURCE = "Azure"


@cache
def _spec() -> SurfaceSpec:
    """Load this surface's normative spec, once."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:  # pragma: no cover - defensive
        raise RenderError(f"spec invalida: {exc}") from exc


def _iso_z(momento: datetime | None) -> str | None:
    """An instant in the form the page documents: UTC, ISO 8601, ``Z`` spelling.

    The same spelling ``azure_defender`` uses for ``TimeGenerated``; the response example
    carries ``"2021-04-12T09:07:18.6759138Z"``.
    """
    if momento is None:
        return None
    return momento.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _record_columns() -> tuple[Column, ...]:
    """The ``assessment`` columns RELATIVE to one record, i.e. without the ``value[]`` prefix.

    The spec names each assessment field as ``value[].properties.status.code`` because that is
    where the field lives in the delivered body: the envelope has a ``value[]`` collection, and
    a path relative to the record alone cannot be resolved against the artifact the consumer
    reads. :func:`documented_document` uses exactly that prefix to seed the collection, so the
    record is assembled from the same names with the prefix removed.
    """
    return tuple(replace(column, name=column.name[len(_ENVELOPE_PREFIX) :]) for column in emittable_columns(_spec(), ASSESSMENT_SCOPE))


def assessment_values(
    assessment: AzureDefenderAssessment, segmento: NetworkSegment, columns: tuple[Column, ...]
) -> dict[str, Any]:
    """The values this model can source, keyed by the documented COLUMN PATH.

    Every path absent from this mapping leaves the artifact with the documented EMPTY value
    (``null`` for a scalar, ``[]`` for an enumerated collection, ``{}`` for an object whose
    members the page does not enumerate). Nothing here is chosen for plausibility.
    """
    allowed = {column.name for column in columns}
    assessed_arm_id = segmento.segment_id
    assessment_arm_id = (
        f"{assessed_arm_id}/{_ASSESSMENT_PROVIDER_SEGMENT}/{assessment.assessment_id}"
    )
    valores: dict[str, Any] = {
        # A FORMA do caminho vem do exemplo de resposta da propria pagina.
        "id": assessment_arm_id,
        "name": assessment.assessment_id,
        "type": _ASSESSMENT_TYPE,
        # `resourceDetails` e o id ARM VERBATIM do recurso avaliado -- o mesmo que a
        # azure_vnet_flow_logs entrega, e nao uma segunda composicao do mesmo caminho.
        "properties.resourceDetails.id": assessed_arm_id,
        "properties.resourceDetails.source": _AZURE_RESOURCE_SOURCE,
        "properties.status.code": assessment.health,
        "properties.status.firstEvaluationDate": _iso_z(assessment.first_evaluated_at),
        "properties.status.statusChangeDate": _iso_z(assessment.status_changed_at),
        # A severidade so aparece no ramo Unhealthy: nao ha severidade de achado para projetar
        # sobre um assessment saudavel ou nao aplicavel.
        "properties.metadata.severity": assessment.severity or None,
        # Enumeracoes com membros publicados e NENHUM valor atribuivel: vazias, nao inventadas.
        "properties.metadata.categories": [],
        "properties.metadata.threats": [],
        # `additionalData` e 'object' e a pagina nunca enumera os membros -- {} sem chave inventada.
        "properties.additionalData": {},
    }
    return {caminho: valor for caminho, valor in valores.items() if caminho in allowed}


def assessment_document(
    assessment: AzureDefenderAssessment,
    segmento: NetworkSegment,
    columns: tuple[Column, ...] | None = None,
) -> dict[str, Any]:
    """One ``SecurityAssessmentResponse``, built from the spec's own field paths."""
    if columns is None:
        columns = _record_columns()
    return documented_document(columns, assessment_values(assessment, segmento, columns))


def assessment_list_document(
    assessments: list[AzureDefenderAssessment],
    segmentos: dict[str, NetworkSegment],
    columns: tuple[Column, ...] | None = None,
) -> dict[str, Any]:
    """The ``SecurityAssessmentList`` envelope: ``value[]`` plus the pagination member.

    The collection is assembled HERE, one position per assessment -- ``documented_document`` on
    the envelope columns seeds ONE position, which is what the pagination member needs and
    not what the record list needs (the same reason ``nsg_document`` assembles ``securityRules``
    itself).
    """
    if columns is None:
        columns = emittable_columns(_spec(), ASSESSMENT_LIST_SCOPE)
    registros = [
        assessment_document(assessment, segmentos[assessment.segment_uuid])
        for assessment in assessments
    ]
    # `nextLink` fica com o valor vazio documentado (null): a pagina publica o membro da
    # paginacao e nunca publica o tamanho de pagina nem um cursor de exemplo.
    return documented_document(columns, {"value": registros})


def _azure_segments(estate: CanonicalEstate) -> list[NetworkSegment]:
    """The Azure segments, in a deterministic order."""
    return sorted(
        (segment for segment in estate.network_segments if segment.provider == _AZURE),
        key=lambda segment: (segment.scope_id, segment.region_id, segment.segment_uuid),
    )


def _por_assinatura(estate: CanonicalEstate) -> list[tuple[str, list[AzureDefenderAssessment]]]:
    """Group the estate's assessments by SUBSCRIPTION, in deterministic order.

    The scope is the subscription because that is the scope the documented URI addresses and
    the one the consumer queries; the management-group scope the page also allows is not
    modeled.
    """
    segmentos = {segment.segment_uuid: segment for segment in _azure_segments(estate)}
    por_chave: dict[str, list[AzureDefenderAssessment]] = {}
    for assessment in estate.azure_defender_assessments:
        segmento = segmentos.get(assessment.segment_uuid)
        if segmento is None:  # pragma: no cover - o gate de integridade ja rejeita
            continue
        assinatura = arm_id_token(segmento.segment_id, "subscriptions") or segmento.scope_id
        por_chave.setdefault(assinatura, []).append(assessment)
    return [
        (assinatura, sorted(lista, key=lambda item: (item.posture, item.assessment_id)))
        for assinatura, lista in sorted(por_chave.items())
    ]


def _list_path(target: Path, assinatura: str) -> Path:
    """The file path, mirroring the documented request path."""
    return (
        target
        / "subscriptions"
        / assinatura
        / "providers"
        / "Microsoft.Security"
        / "assessments"
        / "assessments.json"
    )


def _model_gaps() -> list[dict[str, Any]]:
    """The gaps that keep fields empty in this response -- the provenance report's payload."""
    return [
        {
            "item": "``displayName``/``description`` (nos dois niveis) e o catalogo de ``metadata``",
            "reason": (
                "o texto de uma avaliacao e do CATALOGO do Defender for Cloud, e o estado canonico nao o "
                "modela: nenhum campo deste estate diz qual verificacao o Defender aplicou a uma VNet. "
                "Escrever um nome de avaliacao seria afirmar sobre o provedor algo que nenhuma pagina "
                "consultada sustenta -- e o consumidor usa display_name como titulo do achado, entao a "
                "titulacao vazia e uma lacuna REAL e nomeada, nao um detalhe cosmetico"
            ),
        },
        {
            "item": "``categories``/``threats``/``implementationEffort``/``userImpact``/``preview``",
            "reason": (
                "os DOMINIOS estao publicados (tabelas de enumeracao), mas a pagina nao afirma a qual "
                "valor CADA avaliacao pertence, e o estado nao tem o catalogo que responderia. Escolher um "
                "valor seria inventar a associacao; as colecoes saem vazias e os escalares nulos"
            ),
        },
        {
            "item": "``properties.status.cause``",
            "reason": (
                "a pagina publica o tipo ('string') e a descricao, mas nao publica dominio fechado; o "
                "unico valor observavel e o do exemplo de resposta ('OffByPolicy'). Um exemplo de payload "
                "fixa a forma do campo, nao o vocabulario -- entao o membro sai vazio"
            ),
        },
        {
            "item": "``properties.metadata.policyDefinitionId``",
            "reason": (
                "o membro e publicado como 'Azure resource ID of the policy definition that turns this "
                "assessment calculation on', mas nenhuma pagina consultada exemplifica o valor e uma "
                "avaliacao EMBUTIDA do Defender nao tem definicao de politica ARM para apontar"
            ),
        },
        {
            "item": "``properties.additionalData`` e os campos de parceiro",
            "reason": (
                "'additionalData' e tipado 'object' e a pagina nunca enumera seus membros (o exemplo mostra "
                "um 'linkedWorkspaceId', o que nao fixa o conjunto); os tres campos de parceiro tem tipo "
                "publicado, mas nenhuma verificacao deste estado e de terceiro. Todos saem vazios"
            ),
        },
        {
            "item": "``properties.partnersData.secret`` e ``properties.metadata.partnerData.secret``",
            "reason": (
                "a pagina marca os dois como 'write only'. Um membro explicitamente de ESCRITA nao pertence "
                "a uma resposta de leitura, entao eles nem entram na spec -- emiti-los seria publicar um "
                "campo que a documentacao diz que nao volta"
            ),
        },
        {
            "item": "``properties.links.azurePortalUri``",
            "reason": (
                "o tipo e o significado estao publicados ('Link to assessment in Azure Portal'), mas "
                "nenhuma pagina consultada publica o TEMPLATE da URI nem da um exemplo; montar uma URL de "
                "portal por regra seria inventar o transporte"
            ),
        },
        {
            "item": "``nextLink``",
            "reason": (
                "a resposta e uma pagina de uma colecao e a pagina nao publica o tamanho de pagina nem um "
                "cursor de exemplo. O envelope e entregue como pagina unica -- todos os assessments do "
                "escopo cabem nela -- com o membro presente e vazio"
            ),
        },
        {
            "item": "escopo por grupo de gerenciamento",
            "reason": (
                "a pagina publica que 'scope' pode ser assinatura OU grupo de gerenciamento; o consumidor "
                "consulta a assinatura e o estado canonico nao modela grupo de gerenciamento da Azure, entao "
                "um envelope por grupo seria um recorte que o modelo nao tem"
            ),
        },
    ]


class AzureDefenderAssessmentsRenderer:
    """One ``SecurityAssessmentList`` per Azure subscription, in the documented shape."""

    name = "azure_defender_assessments"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Writes ``<out>/azure_defender_assessments/subscriptions/<id>/.../assessments.json``."""
        target = out_dir / self.name
        segmentos = {segment.segment_uuid: segment for segment in _azure_segments(estate)}
        colunas_avaliacao = emittable_columns(_spec(), ASSESSMENT_SCOPE)
        colunas_envelope = emittable_columns(_spec(), ASSESSMENT_LIST_SCOPE)
        escritos: list[Path] = []
        por_arquivo: list[tuple[str, Path]] = []
        saude: Counter[str] = Counter()
        total = 0

        for assinatura, avaliacoes in _por_assinatura(estate):
            documento = assessment_list_document(avaliacoes, segmentos, colunas_envelope)
            caminho = _list_path(target, assinatura)
            write_json(caminho, documento)
            escritos.append(caminho)
            por_arquivo.append((assinatura, caminho))
            for avaliacao in avaliacoes:
                saude[avaliacao.health] += 1
                total += 1

        # A projecao conferida e o achatamento do arquivo REAL lido de volta do disco, por um
        # caminhante independente deste renderer: conferir uma lista em memoria provaria apenas
        # que duas copias do mesmo erro concordam. O nome da projecao carrega a ASSINATURA --
        # um nome unico sobrescreveria as projecoes das demais assinaturas, e o artefato ficaria
        # com a projecao de uma so.
        projecoes: list[Path] = []
        for assinatura, caminho in por_arquivo:
            destino = target / "field_projection" / f"{assinatura}.json"
            write_json(destino, documented_projection(_read(caminho), colunas_avaliacao))
            projecoes.append(destino)

        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=[
                    "subscriptions/**/providers/Microsoft.Security/assessments/assessments.json",
                    "field_projection/*.json",
                    PROVENANCE_FILE,
                ],
                mechanism={
                    "kind": "arm-rest-api",
                    "endpoint": (
                        "GET https://management.azure.com/{scope}/providers/Microsoft.Security/assessments"
                        "?api-version=2021-06-01"
                    ),
                    "api_version": "2021-06-01",
                    "scope": "subscription (a pagina tambem aceita grupo de gerenciamento, que nao e modelado)",
                    "responses": {"200": "SecurityAssessmentList", "other": "CloudError"},
                    "blob_path": None,
                    "partitioning": None,
                    "compression": None,
                    "manifest": None,
                    "note": (
                        "corpo de resposta de um GET do plano de controle ARM, nao um export: a propria "
                        "pagina nao publica caminho de blob, particionamento, compactacao nem manifesto "
                        "para esta superficie"
                    ),
                },
                columns={
                    "spec": len(_spec().columns),
                    "assessment": len(colunas_avaliacao),
                    "assessmentList": len(colunas_envelope),
                    "generatable": _spec().generatable_count,
                },
                counts={
                    "envelopes": len(escritos),
                    "assessments": total,
                    "saude": dict(sorted(saude.items())),
                },
                model_gaps=_model_gaps(),
                not_generated=not_generated(_spec(), ASSESSMENT_SCOPE)
                + not_generated(_spec(), ASSESSMENT_LIST_SCOPE),
                extra={
                    "consumer_divergence": {
                        "read_by_consumer": "assessment.properties.severity",
                        "published_by_provider": "properties.metadata.severity",
                        "measured": (
                            "azure-mgmt-security 7.0.0: SecurityCenter(cred, sub).assessments resolve para a "
                            "api 2021-06-01 e devolve SecurityAssessmentResponse, que achata properties.* em "
                            "atributos de topo e NAO tem atributo 'properties'. 'assessment.properties.severity' "
                            "levanta AttributeError, o 'except Exception' do consumidor engole e o check devolve "
                            "[] registrando azure_defender_scan_failed; o fallback 'MEDIUM' e codigo morto."
                        ),
                        "fixed_here": False,
                        "owner": "FinOps",
                    }
                },
            ),
        )
        return escritos


def _read(caminho: Path) -> Any:
    """Lê o JSON entregue de volta do disco (a proveniência depende dos BYTES, não da memória)."""
    return json.loads(caminho.read_text(encoding="utf-8"))