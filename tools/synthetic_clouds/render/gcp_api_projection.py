"""Projecao de resposta de API no nivel que a spec enumera (G11).

Companheiro de ``azure_arm_instances.documented_projection`` para as superficies de resposta REST:
o corpo de uma API e ANINHADO (``timeSeries[].resource.labels.project_id``) e a spec enumera
CAMINHOS PONTUADOS, entao entregar o corpo cru faria o auditor comparar chave de topo com caminho
-- e acusar de ausente tudo o que esta aninhado.

A PROFUNDIDADE E DECIDIDA PELA SPEC, E ISSO NAO E UM DETALHE
------------------------------------------------------------
Descer sempre produziria ``labels.app``, ``labels.env``... e o auditor acusaria de inventado cada
campo do MAPA, porque a spec nomeia o mapa como uma coluna so. Nao descer nunca produziria
``stateInfo`` no lugar de ``stateInfo.state``, e o auditor acusaria ausencia do filho declarado.
Nenhuma das duas funciona sozinha, e a unica fonte que sabe a diferenca e o CONTRATO:

* desce num objeto quando a spec declara um caminho que passa por dentro dele;
* para no objeto quando a spec o nomeia como coluna (um mapa, um ``Struct``, um objeto opaco).

Isso tambem mantem a projecao sendo o ACHATAMENTO DO ARQUIVO ENTREGUE -- ela le os bytes gravados
e nao uma segunda copia em memoria --, que e o que ancora a auditoria ao artefato.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _descendentes(prefixo: str, nomes: set[str]) -> set[str]:
    """As chaves que a spec declara DENTRO de ``prefixo``, normalizadas.

    Duas formas de caminho aparecem na mesma spec, e as duas precisam ser entendidas aqui:

    * ``timeSeries[].points`` ``->`` ``timeSeries[].points[].interval.endTime``: o prefixo JA e o
      dos itens (termina em ```[]```), entao o resto comeca com ```[]``` e isso NAO e uma chave --
      e a continuacao do caminho do item. Sem pular esse marcador, a chave vinha vazia e a funcao
      respondia "nao desce" para todo objeto dentro de uma lista.
    * ``timeSeries[].resource`` ``->`` ``timeSeries[].resource.labels.project_id``: o resto comeca
      com um ponto, que tambem nao e chave.

    Uma chave que a propria spec declara como lista (``a.b[]``) e normalizada para a chave emitida
    (``a.b``), porque e assim que o valor aparece no objeto entregue.
    """
    profundos: set[str] = set()
    for nome in nomes:
        if not nome.startswith(prefixo) or nome == prefixo:
            continue
        resto = nome[len(prefixo) :].lstrip(".")
        while resto.startswith("[]"):
            resto = resto[2:].lstrip(".")
        if not resto:
            continue
        chave = resto.split(".")[0]
        profundos.add(chave[:-2] if chave.endswith("[]") else chave)
    return profundos


def _walk(node: Any, prefix: str, fields: dict[str, Any], declarados: set[str]) -> None:
    """Achata um objeto: cada chave vira um caminho, e o valor aninhado so desce se a spec quiser."""
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        path = f"{prefix}{key}"
        fields[path] = value
        if isinstance(value, list):
            for item in value:
                _walk(item, f"{path}[].", fields, declarados)
        elif isinstance(value, dict) and _descendentes(path, declarados):
            _walk(value, f"{path}.", fields, declarados)


def document_row(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Uma linha com os campos do ENVELOPE, sem descer para dentro dos itens.

    O envelope e o nivel do DOCUMENTO: os seus campos sao o array de resultados e o token de
    paginacao. Os caminhos de dentro de um item pertencem ao escopo do ITEM, que
    :func:`project_rows` entrega numa linha propria -- misturar os dois faria um dos escopos
    acusar ausencia de tudo o que pertence ao outro.

    Um objeto aninhado no envelope mantem-se como UMA coluna, pela mesma razao que um mapa de item.
    """
    return {key: value for key, value in payload.items()}


def project_rows(
    payload: Mapping[str, Any], array_path: str, declarados: Sequence[str] | set[str]
) -> list[dict[str, Any]]:
    """Uma linha por POSICAO de ``array_path``, com as chaves no caminho que a spec usa.

    ``declarados`` sao os caminhos que a spec enumera para o ITEM deste array: e por eles que a
    projecao decide a profundidade (ver o docstring do modulo). O prefixo de cada linha e
    ``<array_path>[].``, que e exatamente a forma da spec -- o auditor compara o conjunto de
    chaves com ``spec.columns_for(escopo)`` sem traducao no meio.
    """
    nomes = set(declarados)
    items: Any = payload
    for segmento in array_path.split("."):
        items = items[segmento]
    linhas: list[dict[str, Any]] = []
    for item in items:
        fields: dict[str, Any] = {}
        _walk(item, f"{array_path}[].", fields, nomes)
        linhas.append(fields)
    return linhas


def project_object(
    payload: Mapping[str, Any], prefixo: str, declarados: Sequence[str] | set[str]
) -> list[dict[str, Any]]:
    """Uma linha com as chaves de um OBJETO achatadas a partir de ``prefixo``.

    Irmao de :func:`project_rows`, para o caso em que a linha nao vem de um ARRAY. Um pedido de
    API (``request.name``, ``request.interval.startTime``) e um objeto, nao uma lista de itens, e
    passar por ``project_rows`` iteraria os VALORES do mapa -- um objeto tem chaves, nao itens --
    e devolveria uma linha vazia por chave, que e o que produz um artefato com ``{}`` e nenhum
    campo.

    O prefixo entra uma unica vez no caminho de cada coluna (``request`` + ``.name``), e a
    profundidade segue a mesma regra da spec: desce num objeto quando ha caminho declarado
    dentro dele, para num mapa quando a spec o nomeia como coluna so.
    """
    campos: dict[str, Any] = {}
    _walk(payload, f"{prefixo}.", campos, set(declarados))
    return [campos]


def write_projection(target: Path, name: str, linhas: Sequence[Mapping[str, Any]]) -> Path:
    """Escreve a projecao em ``<target>/field_projection/<name>`` e devolve o caminho."""
    pasta = target / "field_projection"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / name
    caminho.write_text(json.dumps(list(linhas), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return caminho


__all__ = ["document_row", "project_object", "project_rows", "write_projection"]
