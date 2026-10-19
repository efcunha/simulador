"""Apis GCP do plano de fixtures — uma superficie por endpoint, dirigida por dados (G11).

Onze fixtures do ``gcp_rest_fixtures`` (Phase 3) entregam corpos de API que o proprio renderer
declara ``best-effort official-shaped``, com ``TODO-verificar #7`` em quase todo campo. Aqui cada
uma delas vira uma superficie CONFORME ao contrato publicado, e a diferenca entre as duas passa a
ser medivel.

POR QUE UM DRIVER, E NAO ONZE MODULOS
-------------------------------------
As familias diferem em DADOS, nao em forma: cada uma tem um nome de array no envelope, um conjunto
de caminhos de item, e uma funcao que projeta um item do estado. Onze copias do mesmo renderer
divergiriam na primeira correcao -- e a licao deste repositorio e que duas copias do mesmo contrato
acabam discordando (e o que o item E2 registra sobre `gcp_bigquery` x `gcp_bigquery_topology`).
Entao a forma vive uma vez, em :class:`GcpApiFixtureRenderer`, e cada familia entra como uma
entrada de :data:`SURFACES`.

AS COLUNAS SAO CONFERIDAS NO NIVEL DO ITEM, E POR ISSO O DRIVER NAO AS CONHECE
------------------------------------------------------------------------------
Os caminhos que a spec enumera vivem na spec -- o renderer nao os repete. Ele emite o artefato e
entrega as duas projecoes (envelope e item) derivadas dos BYTES gravados; quem compara com o
contrato e o teste golden, lendo a spec. Um renderer que carregasse a lista de campos junto
poderia "conferir" a si mesmo.

O QUE NAO E EMITIDO, E POR QUE
------------------------------
* **``resourceUuid``** (e o irmao ``resource.labels.resourceUuid``): chave de juncao entre planos
  que nenhum dos seis contratos oficiais declara -- medido: zero ocorrencias nos documentos
  completos. Ver ``docs/CONTRATO-APIS-GCP.md`` para o risco por transporte (JSON->proto rejeita
  campo desconhecido por padrao; gRPC binario preserva).
* **``projects/-/``** nos nomes do Recommender: AIP-159 exige, no CORPO da resposta, o nome
  canonico com o projeto real -- ``-`` e curinga de URI de REQUISICAO, nao de resposta.
* **``resource.labels.resourcePath``** do Monitoring: o mapa aceita a chave, mas o contrato diz que
  os labels sao os declarados no descritor do tipo de recurso, e ``resourcePath`` nao e um deles.
* Os valores derivados do nome interno do tipo (``assetType``/``name`` do CAI) continuam marcados
  como nao comprovados NA SPEC, e nao silenciados aqui.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding, NativeRecommendation
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.azure_arm_instances import PROVENANCE_FILE, provenance, write_json
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.gcp_api_projection import (
    document_row,
    project_object,
    project_rows,
    write_projection,
)

_GCP = "gcp"

#: UUIDv5 namespace fixo (sem seed): as chaves ja carregam o seed pelo id do estado, entao o id
#: derivado fica deterministico sem depender da ordem de iteracao.
_NS = uuid.UUID("3c9d1a54-6f8b-4a2c-9d31-0b7e5f4a8c62")

#: O numero de organizacao/projeto usado nos nomes de recurso que a API mintaria. Sintetico na
#: FORMA e nao o id de ninguem -- o mesmo tratamento que o renderer antigo ja registrava.
_SCC_ORG = "900900900"
_SCC_SOURCE = f"organizations/{_SCC_ORG}/sources/9009009000000000001"

ItemBuilder = Callable[[CanonicalEstate], list[dict[str, Any]]]


def _gcp_resources(estate: CanonicalEstate) -> list[Resource]:
    return sorted((r for r in estate.resources if r.identity.provider == _GCP), key=lambda r: r.identity.uuid)


def _gcp_project(estate: CanonicalEstate) -> str:
    """Um projeto representativo (o primeiro), para os nomes que a API escopa por projeto."""
    orgs = estate.gcp_orgs
    if orgs and orgs[0].folders and orgs[0].folders[0].projects:
        return orgs[0].folders[0].projects[0].project_id
    return "unknown-project"


def _gcp_findings(estate: CanonicalEstate) -> list[NativeFinding]:
    return sorted((f for f in estate.findings if f.provider == _GCP), key=lambda f: f.finding_id)


def _gcp_recommendations(estate: CanonicalEstate) -> list[NativeRecommendation]:
    return sorted((r for r in estate.recommendations if r.provider == _GCP), key=lambda r: r.recommendation_id)


# -- Cloud Asset Inventory -------------------------------------------------------------


def _cai_iam_policies(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """``searchAllIamPolicies``: uma politica por projeto, com o binding que o estado sustenta.

    Uma politica por ESCOPO (e nao por recurso): o campo ``resource`` do resultado e o full
    resource name do recurso ao qual a politica esta associada, e o estado modela a associacao no
    nivel do projeto.
    """
    projetos = sorted({r.parent_scope_id for r in _gcp_resources(estate)})
    return [
        {
            "resource": f"//cloudresourcemanager.googleapis.com/projects/{projeto}",
            "project": f"projects/{projeto}",
            "policy": {
                "bindings": [
                    {
                        "role": "roles/viewer",
                        "members": ["serviceAccount:security-audit@example.invalid"],
                    }
                ]
            },
        }
        for projeto in projetos
    ]


# -- Security Command Center -----------------------------------------------------------


def _scc_sources(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "name": _SCC_SOURCE,
            "displayName": "Security Health Analytics",
            "description": "Built-in SCC service that scans for misconfigurations.",
        }
    ]


def _scc_findings(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """``findings.list``: cada item e um ``ListFindingsResult`` que EMBRULHA o ``finding``.

    O envelope do contrato e ``listFindingsResults[]``, e cada posicao carrega o finding sob a
    chave ``finding`` -- por isso os caminhos da spec sao ``listFindingsResults[].finding.name``.
    Emitir os findings soltos seria achatamento, e o auditor acusaria (corretamente) que
    ``listFindingsResults[].finding`` nao existe no artefato.

    ``resourceName`` e o full resource name do recurso do achado, resolvido a partir do
    ``resource_uuid`` do estado -- nao um UUID cru embrulhado num host, que e o que o artefato
    antigo entregava. Um achado cujo recurso nao esta no estado fica FORA da lista, em vez de
    receber um nome inventado.

    ``description`` (incremento 5, GCP SCC) e o ``NativeFinding.description`` -- o mesmo fato que
    o renderer irmao da tabela do BigQuery projeta em ``finding.description``
    (:mod:`tools.synthetic_clouds.render.gcp_scc_findings`). Ele entrou aqui por AUDITORIA DE
    FIDELIDADE, e nao por construcao: o consumidor do FinOps le ``f.description``
    (``security.py:94``) e monta a descricao do finding com ``f.description or
    f.resource_name``. Sem esta chave, todo item da superficie cairia no fallback e o artefato
    nunca exercitaria o campo que o consumidor projeta -- a superficie seria fiel ao formato e
    desleal ao contrato. O proto declara ``string description = 37;`` e o discovery do v1 publica
    a propriedade, entao aqui nao ha valor a inventar: o valor e o que o estado carrega, e uma
    finding sem descricao emite a string vazia em vez de prosa montada (mesma convencao do irmao).
    """
    por_uuid = {r.identity.uuid: r for r in _gcp_resources(estate)}
    itens: list[dict[str, Any]] = []
    for finding in _gcp_findings(estate):
        recurso = por_uuid.get(finding.resource_uuid)
        if recurso is None:
            continue
        regra = str(finding.evidence_json.get("rule", "")).strip() or finding.category.lower()
        itens.append(
            {
                "finding": {
                    "name": f"{_SCC_SOURCE}/findings/{finding.finding_id}",
                    "parent": _SCC_SOURCE,
                    "resourceName": (
                        f"//{recurso.resource_type}.googleapis.com/projects/{recurso.parent_scope_id}"
                        f"/{recurso.resource_type}/{recurso.resource_name}"
                    ),
                    "state": "ACTIVE",
                    "category": finding.category,
                    "severity": finding.severity,
                    "description": finding.description,
                    "findingClass": "MISCONFIGURATION",
                    "sourceProperties": {
                        "Explanation": f"{regra} condition detected on the resource ({finding.category}).",
                        "Recommendation": f"Review and remediate the {regra} condition.",
                    },
                }
            }
        )
    return itens


# -- Recommender -----------------------------------------------------------------------


def _recommender_recommendations(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """A recomendacao com o nome canonico: ``projects/<projeto real>/locations/global/...``.

    O projeto vem do RECURSO alvo, porque e ele que a recomendacao se refere; ``projects/-`` e
    curinga de requisicao e nao pode aparecer no corpo (AIP-159).
    """
    por_uuid = {r.identity.uuid: r for r in _gcp_resources(estate)}
    itens: list[dict[str, Any]] = []
    for rec in _gcp_recommendations(estate):
        recurso = por_uuid.get(rec.resource_uuid)
        if recurso is None:
            continue
        itens.append(
            {
                "name": (
                    f"projects/{recurso.parent_scope_id}/locations/global/recommenders/"
                    f"google.compute.instance.MachineTypeRecommender/recommendations/{rec.recommendation_id}"
                ),
                "recommenderSubtype": rec.kind,
                "stateInfo": {"state": "ACTIVE"},
                "content": {},
            }
        )
    return itens


def _recommender_insights(estate: CanonicalEstate) -> list[dict[str, Any]]:
    por_uuid = {r.identity.uuid: r for r in _gcp_resources(estate)}
    itens: list[dict[str, Any]] = []
    for rec in _gcp_recommendations(estate):
        recurso = por_uuid.get(rec.resource_uuid)
        if recurso is None:
            continue
        itens.append(
            {
                "name": (
                    f"projects/{recurso.parent_scope_id}/locations/global/insightTypes/"
                    f"google.compute.instance.MachineTypeInsight/insights/{rec.recommendation_id}"
                ),
                "insightSubtype": rec.kind,
                "stateInfo": {"state": "ACTIVE"},
                "content": {},
            }
        )
    return itens


# -- Cloud Billing Catalog -------------------------------------------------------------


def _catalog_services(estate: CanonicalEstate) -> list[dict[str, Any]]:
    return [
        {
            "name": f"services/{nome.replace(' ', '-').upper()}",
            "serviceId": nome.replace(" ", "-").upper(),
            "displayName": nome,
        }
        for nome in sorted({r.service_name for r in _gcp_resources(estate)})
    ]


def _catalog_skus(estate: CanonicalEstate) -> list[dict[str, Any]]:
    vistos: dict[str, Resource] = {}
    for recurso in _gcp_resources(estate):
        vistos.setdefault(recurso.sku_id, recurso)
    return [
        {
            "name": f"services/{res.service_name.replace(' ', '-').upper()}/skus/{sku_id}",
            "skuId": sku_id,
            "description": res.service_name,
            "category": {
                "serviceDisplayName": res.service_name,
                "resourceFamily": res.service_category,
            },
        }
        for sku_id, res in sorted(vistos.items())
    ]


# -- Cloud Monitoring ------------------------------------------------------------------


def _monitored(estate: CanonicalEstate) -> list[tuple[Any, Resource, str, str]]:
    """As series que o renderer pode publicar: ``(serie, recurso, tipo de metrica, tipo monitorado)``.

    Uma serie cujo tipo de recurso nao tem namespace publicado fica FORA (o tipo monitorado dos
    outros tipos do catalogo nao esta comprovado): omitir e a resposta correta, rotular errado nao.
    """
    tipos = {
        "compute_instance": ("compute.googleapis.com/instance", "gce_instance"),
        "cloud_sql": ("cloudsql.googleapis.com/database", "cloudsql_database"),
    }
    por_uuid = {r.identity.uuid: r for r in _gcp_resources(estate)}
    publicaveis: list[tuple[Any, Resource, str, str]] = []
    for serie in sorted(estate.metrics, key=lambda s: (s.resource_uuid, s.metric_name)):
        recurso = por_uuid.get(serie.resource_uuid)
        if recurso is None:
            continue
        namespace = tipos.get(recurso.resource_type)
        if namespace is None:
            continue
        publicaveis.append((serie, recurso, f"{namespace[0]}/{serie.metric_name}", namespace[1]))
    return publicaveis


def _monitoring_time_series(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Os pontos da serie, com os labels que o catalogo declara PARA O TIPO monitorado.

    ``resource.labels`` e um mapa, entao o schema aceita qualquer chave; o CONTRATO diz que os
    valores sao os labels "listados no descritor do recurso monitorado", e o catalogo os publica
    POR TIPO: ``gce_instance`` tem ``project_id``/``instance_id``/``zone`` e ``cloudsql_database``
    tem ``project_id``/``database_id``/``region``. Os dois conjuntos **nao coexistem** numa linha,
    e e por isso que a spec os declara em conjuntos nomeados distintos
    (``gce_instance_labels``, ``cloudsql_database_labels``) em vez de exigir a uniao num registro.

    **Sem o label do tipo, a serie nao e atribuivel.** Um leitor que resolva a metrica pelo label
    do recurso (``instance_id``, ``database_id``) nao acha o recurso por aqui -- o achado que
    abriu o item E4. Emitir apenas o ``project_id`` comum deixava o artefato fiel e inutil.
    """
    itens: list[dict[str, Any]] = []
    for serie, recurso, tipo_metrica, tipo_monitorado in _monitored(estate):
        if tipo_monitorado == "gce_instance":
            labels = {
                "project_id": recurso.parent_scope_id,
                "instance_id": recurso.resource_name,
                "zone": recurso.region_id,
            }
        else:
            labels = {
                "project_id": recurso.parent_scope_id,
                "database_id": recurso.resource_name,
                "region": recurso.region_id,
            }
        itens.append(
            {
                "metric": {"type": tipo_metrica},
                "resource": {"type": tipo_monitorado, "labels": labels},
                "points": [
                    {"interval": {"endTime": ponto.ts.isoformat()}, "value": {"doubleValue": ponto.value}}
                    for ponto in serie.points
                ],
            }
        )
    return itens


def _monitoring_metric_descriptors(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Um descritor por TIPO de metrica que o estado realmente reporta -- e nada mais."""
    projeto = _gcp_project(estate)
    por_tipo: dict[str, set[str]] = {}
    for _serie, _recurso, tipo_metrica, tipo_monitorado in _monitored(estate):
        por_tipo.setdefault(tipo_metrica, set()).add(tipo_monitorado)
    itens: list[dict[str, Any]] = []
    for tipo in sorted(por_tipo):
        curto = tipo.rsplit("/", 1)[-1]
        itens.append(
            {
                "name": f"projects/{projeto}/metricDescriptors/{tipo}",
                "type": tipo,
                "displayName": " ".join(palavra.capitalize() for palavra in curto.split("_")),
                "metricKind": "GAUGE",
                "valueType": "DOUBLE",
                "monitoredResourceTypes": sorted(por_tipo[tipo]),
            }
        )
    return itens


def _monitoring_alert_policies(estate: CanonicalEstate) -> list[dict[str, Any]]:
    itens: list[dict[str, Any]] = []
    for serie, recurso, tipo_metrica, _tipo_monitorado in _monitored(estate):
        rotulo = " ".join(p.capitalize() for p in tipo_metrica.rsplit("/", 1)[-1].split("_"))
        policy_id = uuid.uuid5(_NS, f"gcp/alert-policy/{serie.resource_uuid}/{serie.metric_name}")
        itens.append(
            {
                "name": f"projects/{recurso.parent_scope_id}/alertPolicies/{policy_id}",
                "displayName": f"{recurso.resource_name}: {rotulo}",
                "combiner": "AND",
                "enabled": True,
                "conditions": [
                    {
                        "displayName": f"{rotulo} stops reporting",
                        "conditionAbsent": {
                            "filter": f'metric.type = "{tipo_metrica}"',
                            "duration": "600s",
                        },
                    }
                ],
            }
        )
    return itens


# -- Cloud Billing Budgets -------------------------------------------------------------


def _budgets(estate: CanonicalEstate) -> list[dict[str, Any]]:
    conta = next((b for b in estate.billing_accounts if b.provider == _GCP), None)
    ba_id = conta.billing_account_id if conta else "unknown"
    return [
        {
            "name": f"billingAccounts/{ba_id}/budgets/{uuid.uuid5(_NS, f'gcp/budget/{ba_id}')}",
            "displayName": "Monthly Budget",
            "budgetFilter": {"projects": [f"projects/{_gcp_project(estate)}"]},
            "amount": {"specifiedAmount": {"currencyCode": estate.currency, "units": "1000"}},
        }
    ]


# -- Cloud Monitoring: a MESMA leitura, pedida num escopo largo e respondida em parte ----


#: O curinga de projeto do lado da REQUISICAO. Ele nao aparece no corpo de NENHUMA resposta
#: desta superficie: no corpo, um nome de recurso e o nome canonico com o projeto real.
GCP_PROJECT_WILDCARD = "projects/-"


def _observability_partial_items(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """As series de UM projeto do estate, e nao todas -- o subconjunto que um escopo largo devolve.

    Um pedido com o escopo de projeto inteiro (``projects/-``) alcanca todos os projetos, e a
    API ainda assim devolve um SUB-CONJUNTO: ``pageSize``, ``view`` e ``filter`` recortam o
    resultado sem produzir erro nenhum. E essa a forma da pergunta que o diagnostico
    retrospectivo precisa fazer ao GCP -- "se a leitura fosse concedida num escopo largo, o
    que voltaria, e o que nao voltaria?".

    O recorte e o PRIMEIRO projeto por ``project_id``: deterministico, e o unico criterio que
    nao faz a escolha depender do estado de uma pagina. A resposta nao se apresenta como
    completa -- ver ``missing.json``, que e o inventario do que sobrou de fora.
    """
    series = _monitoring_time_series(estate)
    if not series:
        return []
    projetos = sorted(
        {item["resource"]["labels"]["project_id"] for item in series if "project_id" in item["resource"]["labels"]}
    )
    if not projetos:
        return series
    escolhido = projetos[0]
    return [item for item in series if item["resource"]["labels"].get("project_id") == escolhido]


def _observability_missing(estate: CanonicalEstate, devolvidas: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """O inventario do que a resposta parcial NAO carrega.

    Nao vai para o corpo: ``ListTimeSeriesResponse`` nao declara um campo de itens ausentes, e
    publicar um ``missing`` ali seria um campo inventado. Vai num artefato IRMAO, com o motivo
    declarado no ``_provenance``.
    """
    completas = _monitoring_time_series(estate)
    devolvidos = sorted(
        {
            item["resource"]["labels"]["project_id"]
            for item in devolvidas
            if "project_id" in item["resource"]["labels"]
        }
    )
    todos = sorted(
        {
            item["resource"]["labels"]["project_id"]
            for item in completas
            if "project_id" in item["resource"]["labels"]
        }
    )
    return {
        "scope": GCP_PROJECT_WILDCARD,
        "returned_projects": devolvidos,
        "missing_projects": [projeto for projeto in todos if projeto not in devolvidos],
        "missing_series": len(completas) - len(devolvidas),
        "total_series": len(completas),
    }


#: O pedido ANONIMO como FORMATO: os valores sao strings e integers porque o contrato e um
#: proto com esses tipos, e NAO porque o pedido foi capturado. O que o torna anonimo e a
#: ausencia de qualquer campo de credencial -- ver o conjunto ``request-parameters`` da spec.
def _anonymous_request(estate: CanonicalEstate) -> dict[str, Any]:
    return {
        "name": GCP_PROJECT_WILDCARD,
        "filter": 'metric.type = starts_with("compute.googleapis.com/")',
        "interval": {
            "startTime": estate.sim_start.isoformat(),
            "endTime": estate.sim_now.isoformat(),
        },
        "view": "HEADERS",
        "pageSize": len(_observability_partial_items(estate)),
        "pageToken": "",
    }


# -- O catalogo de superficies ---------------------------------------------------------


class SurfaceFixture:
    """Uma superficie de resposta de API: o arquivo, a spec e os escopos de conferencia."""

    __slots__ = (
        "artifact",
        "item_scope",
        "missing_scope",
        "renderer",
        "request_scope",
        "response_scope",
        "spec_file",
        "surface",
        "subject",
    )

    def __init__(
        self,
        surface: str,
        renderer: str,
        artifact: str,
        response_scope: str,
        item_scope: str,
        spec_file: str,
        subject: str,
        request_scope: str = "",
        missing_scope: str = "",
    ) -> None:
        self.surface = surface
        self.renderer = renderer
        self.artifact = artifact
        self.response_scope = response_scope
        self.item_scope = item_scope
        self.spec_file = spec_file
        self.subject = subject
        #: O conjunto de parametros de REQUISICAO, quando a superficie declara um pedido
        #: anonimo. Vazio nas onze superficies de chamada simples, que nao modelam pedido.
        self.request_scope = request_scope
        #: O conjunto que descreve o que a resposta NAO carrega, quando a resposta e parcial.
        #: Vazio nas superficies completas.
        self.missing_scope = missing_scope



#: O motor de cada familia: recebe o estado e devolve os itens do array do envelope.
ITEMS: dict[str, ItemBuilder] = {
    "gcp/asset-search-all-iam-policies": _cai_iam_policies,
    "gcp/scc-sources": _scc_sources,
    "gcp/scc-findings": _scc_findings,
    "gcp/recommender-recommendations": _recommender_recommendations,
    "gcp/recommender-insights": _recommender_insights,
    "gcp/catalog-services": _catalog_services,
    "gcp/catalog-skus": _catalog_skus,
    "gcp/monitoring-time-series": _monitoring_time_series,
    "gcp/monitoring-metric-descriptors": _monitoring_metric_descriptors,
    "gcp/monitoring-alert-policies": _monitoring_alert_policies,
    "gcp/billing-budgets": _budgets,
    "gcp/observability-partial": _observability_partial_items,
}

#: Superficie -> (arquivo do artefato, escopo do envelope, escopo do item, arquivo da spec).
SURFACES: dict[str, SurfaceFixture] = {
    "gcp/asset-search-all-iam-policies": SurfaceFixture(
        "gcp/asset-search-all-iam-policies",
        "gcp_asset_search_all_iam_policies",
        "search_all_iam_policies.json",
        "response",
        "iamPolicySearchResult",
        "gcp/asset-search-all-iam-policies.schema.json",
        "the IAM policy results array that the estate's projects support",
    ),
    "gcp/scc-sources": SurfaceFixture(
        "gcp/scc-sources",
        "gcp_scc_sources",
        "sources.json",
        "response",
        "source",
        "gcp/scc-sources.schema.json",
        "the SCC source the findings are attributed to",
    ),
    "gcp/scc-findings": SurfaceFixture(
        "gcp/scc-findings",
        "gcp_api_scc_findings",
        "findings.json",
        "response",
        "finding",
        "gcp/scc-findings.schema.json",
        "one finding per GCP native finding whose resource is in the estate",
    ),
    "gcp/recommender-recommendations": SurfaceFixture(
        "gcp/recommender-recommendations",
        "gcp_recommender_recommendations",
        "recommendations.json",
        "response",
        "recommendation",
        "gcp/recommender-recommendations.schema.json",
        "one recommendation per GCP native recommendation",
    ),
    "gcp/recommender-insights": SurfaceFixture(
        "gcp/recommender-insights",
        "gcp_recommender_insights",
        "insights.json",
        "response",
        "insight",
        "gcp/recommender-insights.schema.json",
        "one insight per GCP native recommendation",
    ),
    "gcp/catalog-services": SurfaceFixture(
        "gcp/catalog-services",
        "gcp_catalog_services",
        "services.json",
        "response",
        "service",
        "gcp/catalog-services.schema.json",
        "one billing catalog service per service name in the estate",
    ),
    "gcp/catalog-skus": SurfaceFixture(
        "gcp/catalog-skus",
        "gcp_catalog_skus",
        "skus.json",
        "response",
        "sku",
        "gcp/catalog-skus.schema.json",
        "one SKU per distinct sku_id in the estate",
    ),
    "gcp/monitoring-time-series": SurfaceFixture(
        "gcp/monitoring-time-series",
        "gcp_monitoring_time_series",
        "time_series.json",
        "response",
        "timeSeries",
        "gcp/monitoring-time-series.schema.json",
        "one series per metered GCP resource whose monitored type is published",
    ),
    "gcp/monitoring-metric-descriptors": SurfaceFixture(
        "gcp/monitoring-metric-descriptors",
        "gcp_monitoring_metric_descriptors",
        "metric_descriptors.json",
        "response",
        "metricDescriptor",
        "gcp/monitoring-metric-descriptors.schema.json",
        "one descriptor per metric type the estate actually reports",
    ),
    "gcp/monitoring-alert-policies": SurfaceFixture(
        "gcp/monitoring-alert-policies",
        "gcp_monitoring_alert_policies",
        "alert_policies.json",
        "response",
        "alertPolicy",
        "gcp/monitoring-alert-policies.schema.json",
        "one policy per metered series, derived from the series the estate reports",
    ),
    "gcp/billing-budgets": SurfaceFixture(
        "gcp/billing-budgets",
        "gcp_billing_budgets",
        "budgets.json",
        "response",
        "budget",
        "gcp/billing-budgets.schema.json",
        "the native budget definition of the GCP billing account",
    ),
    "gcp/observability-partial": SurfaceFixture(
        "gcp/observability-partial",
        "gcp_observability_partial",
        "time_series.json",
        "response",
        "timeSeries",
        "gcp/observability-partial.schema.json",
        "the series of ONE project, from a request scoped to the whole project set",
        request_scope="request-parameters",
        missing_scope="missing",
    ),
}


def _spec_fixture(fixture: SurfaceFixture) -> SurfaceSpec:
    try:
        return load_spec(DEFAULT_SPECS_ROOT / fixture.spec_file)
    except SpecError as exc:
        raise RenderError(f"{fixture.spec_file}: {exc}") from exc


def _response_envelope(estate: CanonicalEstate, fixture: SurfaceFixture, itens: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """O envelope: o array de itens e o token de paginacao.

    O nome do array e derivado da SPEC e nao repetido aqui: o conjunto de resposta tem dois
    campos, e o que nao e ``nextPageToken`` e o array.
    """
    spec = _spec_fixture(fixture)
    nomes = [c.name for c in spec.columns_for(fixture.response_scope)]
    array = next((n for n in nomes if n != "nextPageToken"), "items")
    return {array: list(itens), "nextPageToken": ""}


class GcpApiFixtureRenderer:
    """Base das superficies deste modulo: a FORMA do renderer, sem ``name``.

    **``name`` e atributo de CLASSE em cada subclasse, e isso nao e estilo.** A descoberta de
    renderers le ``getattr(classe, "name")`` -- o atributo de INSTANCIA nao existe ali --, entao
    uma classe que so definisse ``self.name`` no ``__init__`` seria ignorada em silencio. Foi o
    que aconteceu na primeira versao deste modulo: as onze superficies nao entraram no registro e
    o defeito so apareceu quando o teste conferiu a matriz contra o registro.
    """

    fixture: SurfaceFixture
    #: O nome registrado do renderer. Declarado na base (e definido em cada subclasse, como
    #: atributo de CLASSE) para que o verificador de tipos o veja -- a descoberta o le na classe.
    name: str

    def __init__(self, surface: str) -> None:
        if surface not in SURFACES:
            raise RenderError(f"superficie sem fixture: {surface!r}")
        self.surface = surface
        self.fixture = SURFACES[surface]
        self._items = ITEMS[surface]

    def build_body(self, estate: CanonicalEstate) -> dict[str, Any]:
        return _response_envelope(estate, self.fixture, self._items(estate))

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        # Os artefatos IRMAOS, declarados antes da escrita para que a lista devolvida seja o
        # inventario completo do que existe em disco.
        extras: list[Path] = []
        # O diretorio e o nome REGISTRADO do renderer, e nao um derivado da superficie: a
        # superficie ``gcp/scc-findings`` registra ``gcp_api_scc_findings`` (o nome
        # ``gcp_scc_findings`` ja e o renderer dedicado da tabela do BigQuery), e derivar aqui
        # fazia os dois escreverem em diretorios diferentes.
        target = out_dir / self.name
        corpo = self.build_body(estate)
        artefato = target / self.fixture.artifact
        write_json(artefato, corpo)

        entregue = json.loads(artefato.read_text(encoding="utf-8"))
        spec = _spec_fixture(self.fixture)
        nomes = [c.name for c in spec.columns_for(self.fixture.response_scope)]
        array = next((n for n in nomes if n != "nextPageToken"), "items")

        envelope = write_projection(target, "response.json", [document_row(entregue)])
        # A projecao e dirigida pela SPEC: e ela que diz a que profundidade descer (um objeto com
        # caminho declarado dentro desce; um mapa nomeado como coluna para). Ver
        # ``gcp_api_projection`` para por que nenhuma das duas regras fixas funciona sozinha.
        itens = write_projection(
            target,
            f"{array}.json",
            project_rows(entregue, array, [c.name for c in spec.columns_for(self.fixture.item_scope)]),
        )

        # O pedido ANONIMO e o inventario do que FALTA, quando a superficie os declara. Os dois
        # sao artefatos IRMAOS do corpo, nunca campos dele: nem o pedido pertence a resposta, nem
        # o contrato publica um campo de itens ausentes. As duas projecoes passam pela mesma
        # maquinaria do resto do driver, para que o auditor compare caminho com caminho.
        if self.fixture.request_scope:
            pedido = write_projection(
                target,
                "request_parameters.json",
                project_object(
                    _anonymous_request(estate),
                    "request",
                    [c.name for c in spec.columns_for(self.fixture.request_scope)],
                ),
            )
            extras.append(pedido)
        if self.fixture.missing_scope:
            faltando = write_projection(
                target, "missing.json", [_observability_missing(estate, entregue[array])]
            )
            extras.append(faltando)

        write_json(
            target / PROVENANCE_FILE,
            provenance(
                spec,
                spec_file=self.fixture.spec_file,
                artifacts=[
                    self.fixture.artifact,
                    "field_projection/response.json",
                    f"field_projection/{array}.json",
                    *(
                        ["field_projection/request_parameters.json"]
                        if self.fixture.request_scope
                        else []
                    ),
                    *(["field_projection/missing.json"] if self.fixture.missing_scope else []),
                    PROVENANCE_FILE,
                ],
                mechanism={
                    "kind": "rest-api",
                    "surface": self.surface,
                    "format": "json",
                    "compression": None,
                    "compression_note": "resposta de API: a compressao e negociada no transporte HTTP",
                    "encoding": "UTF-8 (JSON)",
                    "root": f"{array}[]",
                    "manifest": None,
                    "manifest_note": "resposta de API: nao ha manifesto",
                    "cadence": None,
                    "delivery_note": (
                        "o artefato e o CORPO da resposta; a auditoria tem dois niveis (o envelope e o "
                        "item) e uma projecao por nivel"
                    ),
                    "subject": self.fixture.subject,
                },
                columns={
                    "documented": len(spec.columns),
                    "generated": len(spec.columns),
                    "sets": list(spec.set_names),
                    "response_columns": len(spec.columns_for(self.fixture.response_scope)),
                    "item_columns": len(spec.columns_for(self.fixture.item_scope)),
                },
                counts={"items": len(entregue[array]), "next_page_token": "vazio (ultima pagina)"},
                model_gaps=[
                    {
                        "item": "``resourceUuid`` (chave de juncao entre planos)",
                        "reason": (
                            "nenhum dos seis contratos oficiais declara esse campo (zero ocorrencias nos "
                            "documentos completos); a juncao entre planos usa os ids que a propria nuvem "
                            "publica. Ver docs/CONTRATO-APIS-GCP.md para o risco por transporte"
                        ),
                    },
                    *(
                        [
                            {
                                "item": "campo de itens ausentes no corpo da resposta",
                                "reason": (
                                    "AUSENTE DO CONTRATO E DECLARADO POR ISSO. "
                                    "ListTimeSeriesResponse declara 'timeSeries', 'nextPageToken' e "
                                    "'executionErrors' -- nenhum campo que diga o que o escopo NAO "
                                    "devolveu. Publicar um 'missing' no corpo seria um campo "
                                    "inventado, entao o inventario vai em "
                                    "field_projection/missing.json, ao lado do corpo. Um "
                                    "nextPageToken vazio significa 'ultima pagina' e NAO 'todos os "
                                    "dados', entao ele nao pode substituir o inventario."
                                ),
                            },
                            {
                                "item": "credencial no pedido",
                                "reason": (
                                    "AUSENTE POR CONTRATO, E A RAZAO DO PEDIDO SER ANONIMO. O "
                                    "conjunto request-parameters carrega o escopo em DADOS -- o "
                                    "curinga de projeto, o filtro e a janela de tempo -- e nenhum "
                                    "campo de credencial. Numa API REST a credencial vai no cabecalho "
                                    "HTTP e nao no corpo da requisicao; declarar 'accessToken', "
                                    "'apiKey' ou 'Authorization' aqui afirmaria que o GCP os aceita "
                                    "como parametro de consulta, o que o contrato nao diz. E o "
                                    "contraste com a API de diagnostico do FinOps, cujo "
                                    "request_parameters PREENCHE com um token: um 'unverified' de "
                                    "la se tornaria um fato inventado aqui."
                                ),
                            },
                        ]
                        if self.fixture.missing_scope
                        else []
                    ),
                ],
            ),
        )
        # A lista devolvida e o INVENTARIO do que foi gravado, e por isso inclui os artefatos
        # irmaos quando a superficie os declara. Devolver so o corpo faria um consumidor que
        # rely na lista nao enxergar o pedido anonimo nem o inventario do que faltou.
        return [artefato, envelope, itens, target / PROVENANCE_FILE, *extras]


def _renderer_name(surface: str) -> str:
    """``gcp/scc-findings`` -> ``gcp_scc_findings`` (o nome que a matriz e o ``--emit`` usam)."""
    return "gcp_" + surface.split("/", 1)[1].replace("-", "_")


# -- As superficies: uma classe POR endpoint, definida aqui (a descoberta exige isso) ---------
#
# Cada uma e uma linha de codigo a mais que a versao dinamica teria, e e o preco de ser
# DESCOBERTA: o registro varre o modulo procurando classe definida nele, instanciavel sem
# argumentos e com ``name`` textual. Uma classe fabricada por ``type()`` tem outro ``__module__``
# e seria ignorada em silencio -- o pior dos modos de falha para um registro.


class GcpAssetSearchAllIamPoliciesRenderer(GcpApiFixtureRenderer):
    name = "gcp_asset_search_all_iam_policies"

    def __init__(self) -> None:
        super().__init__("gcp/asset-search-all-iam-policies")


class GcpSccSourcesRenderer(GcpApiFixtureRenderer):
    name = "gcp_scc_sources"

    def __init__(self) -> None:
        super().__init__("gcp/scc-sources")


class GcpSccFindingsRenderer(GcpApiFixtureRenderer):
    name = "gcp_api_scc_findings"

    def __init__(self) -> None:
        super().__init__("gcp/scc-findings")


class GcpRecommenderRecommendationsRenderer(GcpApiFixtureRenderer):
    name = "gcp_recommender_recommendations"

    def __init__(self) -> None:
        super().__init__("gcp/recommender-recommendations")


class GcpRecommenderInsightsRenderer(GcpApiFixtureRenderer):
    name = "gcp_recommender_insights"

    def __init__(self) -> None:
        super().__init__("gcp/recommender-insights")


class GcpCatalogServicesRenderer(GcpApiFixtureRenderer):
    name = "gcp_catalog_services"

    def __init__(self) -> None:
        super().__init__("gcp/catalog-services")


class GcpCatalogSkusRenderer(GcpApiFixtureRenderer):
    name = "gcp_catalog_skus"

    def __init__(self) -> None:
        super().__init__("gcp/catalog-skus")


class GcpMonitoringTimeSeriesRenderer(GcpApiFixtureRenderer):
    name = "gcp_monitoring_time_series"

    def __init__(self) -> None:
        super().__init__("gcp/monitoring-time-series")


class GcpMonitoringMetricDescriptorsRenderer(GcpApiFixtureRenderer):
    name = "gcp_monitoring_metric_descriptors"

    def __init__(self) -> None:
        super().__init__("gcp/monitoring-metric-descriptors")


class GcpMonitoringAlertPoliciesRenderer(GcpApiFixtureRenderer):
    name = "gcp_monitoring_alert_policies"

    def __init__(self) -> None:
        super().__init__("gcp/monitoring-alert-policies")


class GcpBillingBudgetsRenderer(GcpApiFixtureRenderer):
    name = "gcp_billing_budgets"

    def __init__(self) -> None:
        super().__init__("gcp/billing-budgets")


class GcpObservabilityPartialRenderer(GcpApiFixtureRenderer):
    """A MESMA leitura de series, pedida num escopo de projeto INTEIRO e respondida em parte.

    E a unica superficie do driver que escreve os dois artefatos irmaos: o pedido anonimo e o
    inventario do que a resposta nao carrega. Nenhum dos dois entra no corpo, e cada um esta
    com a razao declarada no ``_provenance``.
    """

    name = "gcp_observability_partial"

    def __init__(self) -> None:
        super().__init__("gcp/observability-partial")


__all__ = ["SURFACES", "GcpApiFixtureRenderer"]

