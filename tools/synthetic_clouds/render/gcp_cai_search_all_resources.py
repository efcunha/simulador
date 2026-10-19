"""Cloud Asset Inventory ``searchAllResources`` — o contrato auditado (G11).

Superficie: ``specs/gcp/asset-search-all-resources.schema.json``.

POR QUE ESTE RENDERER EXISTE AO LADO DO ``gcp_rest_fixtures``
------------------------------------------------------------
O ``gcp_rest_fixtures`` (Phase 3, 590 linhas, 13 fixtures) entrega os corpos de API como
``best-effort official-shaped``: o proprio docstring dele registra que o envelope REST de CAI,
SCC, Recommender, Catalog, Monitoring e Budgets e ``TODO-verificar #7``. E ele emite, dentro de
cada resultado, uma chave de juncao sintetica -- ``resourceUuid`` -- que o ``.proto`` oficial do
``ResourceSearchResult`` **nao declara**.

Este modulo entrega a MESMA superficie CAI conforme ao contrato publicado, e faz tres coisas
que o antigo nao faz:

* **os campos sao so os do proto**, sem a chave de juncao sintetica;
* **a projecao acompanha o artefato** (``field_projection/``), que e o que permite o auditor
  comparar o arquivo entregue com o caminho que a spec enumera;
* **a proveniencia nomeia o que saiu e por que**, incluindo a chave que o artefato antigo
  carrega.

O ``gcp_rest_fixtures`` **nao foi tocado**: ele alimenta o emulador e tem testes que o fixam, e
aposenta-lo e uma decisao de produto (registrada em ``docs/DECISOES-PENDENTES.md``, item E2), nao
um efeito colateral desta auditoria.

O QUE NAO E EMITIDO, E POR QUE
------------------------------
``resourceUuid``: chave de juncao entre planos que o proto nao declara. O consumidor constroi os
clientes dessas APIs por **gRPC** com o proto gerado, e o proprio codigo do renderer antigo
registra o efeito medido para a familia de alert policies: *"ParseDict fails with has no field
named resourceUuid"*. Entregar aqui a forma conforme e o que permite medir a diferenca entre as
duas, em vez de supor que ela e inofensiva.

``assetType``: emitido, com o valor composto pelo gerador (``<resource_type>.googleapis.com``),
porque o TIPO do campo e publicado. A FORMA do valor nao esta comprovada e a spec a registra em
``unverified`` -- o valor entra, a duvida fica dita.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.azure_arm_instances import PROVENANCE_FILE, provenance, write_json
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.gcp_api_projection import document_row, project_rows, write_projection

#: O caminho da especificacao normativa DENTRO de ``specs/`` (a proveniencia cita este texto).
_SPEC_FILE = "gcp/asset-search-all-resources.schema.json"

#: A especificacao normativa desta superficie (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_GCP = "gcp"

#: O escopo do envelope e o escopo do item. Conferir um artefato contra a UNIAO dos dois
#: acusaria ausencia de tudo o que pertence ao outro -- sao contratos em niveis diferentes.
RESPONSE_SCOPE = "response"
ITEM_SCOPE = "resourceSearchResult"

#: O array do corpo que hospeda os resultados (``SearchAllResourcesResponse.results[]``).
RESULTS_ARRAY = "results"

_ARTIFACT_NAME = "search_all_resources.json"


def _spec() -> SurfaceSpec:
    """A spec normativa, carregada a cada chamada; falha FECHADO se nao servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _asset_path(resource: Resource) -> str:
    """O FULL RESOURCE NAME que o campo ``name`` documenta.

    O proto fixa a FORMA (``//SERVICE/projects/.../...``) e exemplifica com
    ``//compute.googleapis.com/...``. O service-host e derivado do tipo do recurso; o segmento
    ``projects/<project>/`` e o que torna o nome unico entre projetos (o gerador reinicia o
    contador por escopo, entao ``compute_instance-0000`` existe em tres projetos).
    """
    return (
        f"//{resource.resource_type}.googleapis.com"
        f"/projects/{resource.parent_scope_id}/{resource.resource_type}/{resource.resource_name}"
    )


def search_all_resources(estate: CanonicalEstate) -> dict[str, Any]:
    """O corpo de ``searchAllResources``: um resultado por recurso GCP do estado.

    Ordem deterministica por uuid, e as chaves na ordem em que o proto as declara -- o artefato
    e comparavel byte a byte entre execucoes.
    """
    resultados: list[dict[str, Any]] = []
    for resource in sorted(
        (r for r in estate.resources if r.identity.provider == _GCP),
        key=lambda r: r.identity.uuid,
    ):
        resultados.append(
            {
                "name": _asset_path(resource),
                "assetType": f"{resource.resource_type}.googleapis.com",
                "project": f"projects/{resource.parent_scope_id}",
                "displayName": resource.resource_name,
                "location": resource.region_id,
                "labels": dict(resource.tags),
            }
        )
    return {"results": resultados, "nextPageToken": ""}


def _excluded_fields() -> list[dict[str, Any]]:
    """O que o artefato do ``gcp_rest_fixtures`` carrega e este NAO carrega, com o motivo."""
    return [
        {
            "item": "``resourceUuid``",
            "reason": (
                "chave de juncao entre planos que o proto oficial de ResourceSearchResult nao declara; "
                "o consumidor le essas APIs pelo proto (gRPC), e um campo de topo nao declarado faz o "
                "cliente recusar a resposta -- efeito ja medido na familia alertPolicies do mesmo "
                "renderer. A juncao entre planos continua possivel pelo campo ``name``, que e o id "
                "que a propria CAI publica"
            ),
        }
    ]


class GcpCaiSearchAllResourcesRenderer:
    """Entrega o corpo de ``searchAllResources`` conforme ao proto, com projecao e proveniencia."""

    name = "gcp_cai_search_all_resources"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve o corpo, a projecao dos dois niveis e o relatorio sob ``out_dir/<name>``."""
        target = out_dir / self.name
        corpo = search_all_resources(estate)
        artefato = target / _ARTIFACT_NAME
        write_json(artefato, corpo)

        entregue = json.loads(artefato.read_text(encoding="utf-8"))
        spec = _spec()
        linhas_item = project_rows(entregue, RESULTS_ARRAY, [c.name for c in spec.columns_for(ITEM_SCOPE)])
        linhas_envelope = [document_row(entregue)]

        itens = write_projection(target, "results.json", linhas_item)
        envelope = write_projection(target, "response.json", linhas_envelope)

        spec = _spec()
        write_json(
            target / PROVENANCE_FILE,
            provenance(
                spec,
                spec_file=_SPEC_FILE,
                artifacts=[_ARTIFACT_NAME, "field_projection/response.json", "field_projection/results.json", PROVENANCE_FILE],
                mechanism={
                    "kind": "rest-api",
                    "method": "cloudasset.searchAllResources",
                    "path_template": "https://cloudasset.googleapis.com/v1/{scope}:searchAllResources",
                    "format": "json",
                    "compression": None,
                    "compression_note": "resposta de API: a compressao e negociada no transporte HTTP, nao no corpo",
                    "encoding": "UTF-8 (JSON)",
                    "root": "results[]",
                    "manifest": None,
                    "manifest_note": "resposta de API: nao ha manifesto",
                    "cadence": None,
                    "delivery_note": (
                        "o artefato e o CORPO da resposta, nao um lote de export: por isso a auditoria "
                        "tem dois niveis (o envelope e o item) e uma projecao por nivel"
                    ),
                    "item_identity": (
                        "``name`` e o full resource name que a CAI publica; e ele que identifica o "
                        "recurso entre planos. O id interno do estado (uuid) NAO e emitido: o proto "
                        "nao declara esse campo"
                    ),
                },
                columns={
                    "documented": len(spec.columns),
                    "generated": len(spec.columns),
                    "sets": list(spec.set_names),
                    "item_columns": len(spec.columns_for(ITEM_SCOPE)),
                    "response_columns": len(spec.columns_for(RESPONSE_SCOPE)),
                },
                counts={
                    "results": len(linhas_item),
                    "next_page_token": "vazio (ultima pagina)",
                    "resources_gcp_no_estado": len(linhas_item),
                },
                model_gaps=_excluded_fields(),
            ),
        )
        return [artefato, envelope, itens, target / PROVENANCE_FILE]
