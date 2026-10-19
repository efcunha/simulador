"""Caminhos da spec com valor: a metrica que nao subconta artefato aninhado.

O defeito que estes testes trancam e de MEDICAO, e ele engana para baixo: o
artefato de billing do GCP guarda os campos dentro de ``invoice``/``service``/
``project``, enquanto a spec enumera CAMINHOS pontuados. Comparar chave de topo
com caminho pontuado dizia 17 campos preenchidos onde havia 35 (e 58 com os
cenarios aplicados) -- ou seja, o relatorio fazia parecer que a superficie entrega
menos dado do que entrega.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.synthetic_clouds.fidelity.artifacts import populated_of, populated_paths

NOMES = ("billing_account_id", "invoice.month", "invoice.publisher_type", "service.id", "cost")


def _escrever(tmp_path: Path, payload: object) -> Path:
    caminho = tmp_path / "rows.json"
    caminho.write_text(json.dumps(payload), encoding="utf-8")
    return caminho


def test_resolve_caminho_aninhado(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"billing_account_id": "a", "invoice": {"month": "2026-01"}, "cost": 1.5}])

    achados = populated_paths(caminho, NOMES)

    assert "invoice.month" in achados
    assert "billing_account_id" in achados
    assert "cost" in achados


def test_nao_conta_caminho_ausente(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"billing_account_id": "a", "invoice": {"month": "2026-01"}}])

    achados = populated_paths(caminho, NOMES)

    assert "invoice.publisher_type" not in achados
    assert "service.id" not in achados


def test_nao_conta_caminho_presente_porem_vazio(tmp_path: Path) -> None:
    """``{}`` e ``""`` sao ausencia de conteudo, nao conteudo."""
    caminho = _escrever(
        tmp_path,
        [{"billing_account_id": "", "invoice": {"month": "2026-01", "publisher_type": {}}}],
    )

    achados = populated_paths(caminho, NOMES)

    assert "billing_account_id" not in achados
    assert "invoice.publisher_type" not in achados
    assert "invoice.month" in achados


def test_percorre_lista_sem_marcador_de_array(tmp_path: Path) -> None:
    """A spec escreve ``labels.key`` e ``labels`` e uma LISTA de structs.

    Foi o terceiro defeito desta funcao: descer so quando o nome traz ``[]``
    escondia 11 caminhos na tabela standard do GCP, 11 na detailed e 4 na de
    precos -- contava como vazio o que tinha valor.
    """
    caminho = _escrever(
        tmp_path,
        [{"labels": [{"key": "env", "value": "prod"}, {"key": "owner", "value": "x"}]}],
    )

    assert populated_paths(caminho, ("labels.key", "labels.value")) == ("labels.key", "labels.value")


def test_lista_sem_marcador_porem_sem_o_campo_nao_conta(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"labels": [{"key": "env"}]}])

    assert populated_paths(caminho, ("labels.ausente",)) == ()


def test_lista_de_escalares_nao_vira_falso_positivo(tmp_path: Path) -> None:
    """Descer em lista nao pode inventar valor onde o item nao e um struct."""
    caminho = _escrever(tmp_path, [{"tags": ["a", "b"]}])

    assert populated_paths(caminho, ("tags.key",)) == ()
    assert populated_paths(caminho, ("tags",)) == ("tags",)


def test_percorre_lista_com_o_marcador_de_array(tmp_path: Path) -> None:
    """A forma ``networkInterfaces[].id`` e a que as specs da Azure usam."""
    caminho = _escrever(
        tmp_path,
        [{"networkProfile": {"networkInterfaces": [{"id": ""}, {"id": "/subscriptions/x"}]}}],
    )

    achados = populated_paths(caminho, ("networkProfile.networkInterfaces[].id",))

    assert achados == ("networkProfile.networkInterfaces[].id",)


def test_lista_sem_o_campo_nao_conta(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"networkProfile": {"networkInterfaces": [{"mac": "x"}]}}])

    assert populated_paths(caminho, ("networkProfile.networkInterfaces[].id",)) == ()


def test_basta_uma_linha_ter_o_valor(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"invoice": {"month": ""}}, {"invoice": {"month": "2026-02"}}])

    assert "invoice.month" in populated_paths(caminho, NOMES)


def test_formato_plano_delega_para_populated_of(tmp_path: Path) -> None:
    caminho = tmp_path / "flat.csv"
    caminho.write_text("a,b,c\n1,,3\n", encoding="utf-8")

    assert populated_paths(caminho, ("a", "b", "c")) == ("a", "c")


def test_percorre_lista_com_indice_numerico(tmp_path: Path) -> None:
    """A forma ``flowTuples[0]`` indexa a POSICAO -- o NSG publica 13 delas.

    Tratar ``flowTuples[0]`` como nome literal de chave devolvia nada, e a coluna
    obrigatoria aparecia vazia onde havia valor.
    """
    caminho = _escrever(
        tmp_path,
        [{"records": [{"properties": {"flows": [{"flows": [{"flowTuples": ["a,b,c", "d,e,f"]}]}]}}]}],
    )

    achados = populated_paths(
        caminho,
        (
            "records[].properties.flows[].flows[].flowTuples[0]",
            "records[].properties.flows[].flows[].flowTuples[1]",
        ),
    )

    assert achados == (
        "records[].properties.flows[].flows[].flowTuples[0]",
        "records[].properties.flows[].flows[].flowTuples[1]",
    )


def test_indice_fora_da_lista_nao_conta(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"tuplos": ["unico"]}])

    assert populated_paths(caminho, ("tuplos[3]",)) == ()


def test_indice_em_posicao_vazia_nao_conta(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"tuplos": ["", "valor"]}])

    assert populated_paths(caminho, ("tuplos[0]", "tuplos[1]")) == ("tuplos[1]",)


def test_chave_achatada_com_ponto_tambem_conta(tmp_path: Path) -> None:
    """O SCC e o flow log do GCP gravam a chave literal ``"finding.name"``.

    Resolver so o aninhamento zerava o SCC -- como se ele nao entregasse nada --
    e resolver so a chave literal zerava o billing do GCP. As duas formas contam.
    """
    caminho = _escrever(
        tmp_path,
        [{"finding.name": "projects/p/sources/s/findings/f1", "finding": {"category": "X"}}],
    )

    achados = populated_paths(caminho, ("finding.name", "finding.category"))

    assert achados == ("finding.name", "finding.category")


def test_chave_achatada_vazia_nao_conta(tmp_path: Path) -> None:
    caminho = _escrever(tmp_path, [{"finding.name": ""}])

    assert populated_paths(caminho, ("finding.name",)) == ()


def test_aninhado_conta_mais_caminhos_que_topo(tmp_path: Path) -> None:
    """A razao de a metrica existir: topo esconde o que o caminho revela."""
    caminho = _escrever(
        tmp_path,
        [{"billing_account_id": "a", "invoice": {"month": "2026-01", "publisher_type": "GCP"}, "cost": 2}],
    )

    topo = set(populated_of(caminho))
    caminhos = populated_paths(caminho, NOMES)

    assert len(caminhos) > len(set(topo) & set(NOMES))
    assert "invoice" in topo, "o container aparece no topo"
    assert "invoice.month" not in topo, "e o campo dentro dele NAO aparece -- e o defeito"
    assert "invoice.month" in caminhos
