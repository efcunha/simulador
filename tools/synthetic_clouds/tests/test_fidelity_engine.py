"""Testes do nucleo de fidelidade: da especificacao citada ao artefato emitido."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tools.synthetic_clouds.fidelity.artifacts import (
    ArtifactError,
    columns_of,
    is_empty_value,
    populated_of,
)
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_ORDER,
    KIND_POPULATED_EMPTY,
    KIND_UNVERIFIED,
    ScopeError,
    check,
    check_artifact,
    check_values,
    is_faithful,
    summarize,
)
from tools.synthetic_clouds.fidelity.spec import (
    SpecError,
    load_all_specs,
    load_spec,
)

URL = "https://docs.example.invalid/export/schema#column"


def _spec_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "surface": "demo/focus-1.2",
        "provider": "demo",
        "reference": {
            "title": "Demo export schema",
            "url": "https://docs.example.invalid/export/schema",
            "consulted_at": "2026-10-14",
        },
        "delivery": {"kind": "s3", "format": "parquet"},
        "columns": [
            {"name": "BilledCost", "type": "decimal", "required": True, "unit": "USD", "source_url": URL},
            {"name": "ChargePeriodStart", "type": "timestamp", "required": True, "source_url": URL},
            {"name": "Tags", "type": "json", "required": False, "source_url": URL},
        ],
        "unverified": [],
    }
    payload.update(overrides)
    return payload


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "demo.schema.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# --- spec: carregamento e evidencia -----------------------------------------


def test_carrega_spec_valida(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert spec.provider == "demo"
    assert spec.names == ("BilledCost", "ChargePeriodStart", "Tags")
    assert spec.required_names == ("BilledCost", "ChargePeriodStart")
    assert spec.generatable_names == frozenset({"BilledCost", "ChargePeriodStart", "Tags"})
    assert spec.forbidden_names == frozenset()


def test_coluna_verificada_sem_source_url_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [{"name": "BilledCost", "type": "decimal", "required": True}]

    with pytest.raises(SpecError, match="source_url"):
        load_spec(_write(tmp_path, payload))


def test_reference_sem_titulo_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["reference"] = {"url": "https://docs.example.invalid/x", "consulted_at": "2026-10-14"}

    with pytest.raises(SpecError, match="reference.title"):
        load_spec(_write(tmp_path, payload))


def test_colunas_duplicadas_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [
        {"name": "BilledCost", "type": "decimal", "required": True, "source_url": URL},
        {"name": "BilledCost", "type": "decimal", "required": True, "source_url": URL},
    ]

    with pytest.raises(SpecError, match="duplicadas"):
        load_spec(_write(tmp_path, payload))


def test_nome_em_columns_e_unverified_ao_mesmo_tempo_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload(unverified=["Tags"])

    with pytest.raises(SpecError, match="unverified"):
        load_spec(_write(tmp_path, payload))


def test_load_all_specs_sem_diretorio_devolve_vazio(tmp_path: Path) -> None:
    assert load_all_specs(tmp_path / "inexistente") == ()


def test_load_all_specs_le_por_provider(tmp_path: Path) -> None:
    for provider in ("aws", "gcp"):
        target = tmp_path / provider
        target.mkdir()
        payload = _spec_payload(provider=provider, surface=f"{provider}/demo")
        (target / "demo.schema.json").write_text(json.dumps(payload), encoding="utf-8")

    specs = load_all_specs(tmp_path)

    assert [spec.provider for spec in specs] == ["aws", "gcp"]


# --- checker: os quatro modos de falha --------------------------------------


def test_emissao_exata_e_fiel(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))
    observed = ["BilledCost", "ChargePeriodStart", "Tags"]

    assert is_faithful(check(spec, observed))


def test_campo_inventado_e_denunciado(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))
    findings = check(spec, ["BilledCost", "ChargePeriodStart", "Tags", "CampoInventado"])

    assert [f.kind for f in findings] == [KIND_INVENTED]
    assert findings[0].column == "CampoInventado"


def test_coluna_obrigatoria_ausente_e_denunciada(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))
    findings = check(spec, ["BilledCost", "Tags"])

    assert [f.kind for f in findings] == [KIND_MISSING]
    assert findings[0].column == "ChargePeriodStart"


def test_coluna_obrigatoria_sem_tipo_e_cobrada_como_ausente(tmp_path: Path) -> None:
    """O residual da spec aparece em vez de ser escondido.

    Uma coluna obrigatoria cujo tipo o provedor nao publica nao pode ser escrita
    num alvo tipado sem inventar o tipo -- entao ela sai ausente do artefato. O
    auditor acusa `missing`, e isso e CORRETO: nao culpa o renderer, mostra que a
    spec exige uma coluna que ela mesma nao deixa emitir. Quem nomeia a causa e o
    relatorio `untyped_required`; silenciar aqui esconderia a lacuna.
    """
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        {"name": "SemTipo", "required": True, "source_url": URL},
    ]
    spec = load_spec(_write(tmp_path, payload))

    findings = check(spec, ["BilledCost"])

    assert [(f.kind, f.column) for f in findings] == [(KIND_MISSING, "SemTipo")]


def test_coluna_opcional_ausente_nao_e_falha(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert is_faithful(check(spec, ["BilledCost", "ChargePeriodStart"]))


def test_emitir_campo_nao_comprovado_e_falha(tmp_path: Path) -> None:
    payload = _spec_payload(unverified=["SkuPriceDetails"])
    spec = load_spec(_write(tmp_path, payload))
    findings = check(spec, ["BilledCost", "ChargePeriodStart", "Tags", "SkuPriceDetails"])

    assert [f.kind for f in findings] == [KIND_UNVERIFIED]
    assert findings[0].column == "SkuPriceDetails"


def test_ordem_divergente_e_denunciada_quando_posicional(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))
    findings = check(spec, ["ChargePeriodStart", "BilledCost", "Tags"], ordered=True)

    assert [f.kind for f in findings] == [KIND_ORDER]


def test_ordem_so_importa_quando_pedido(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert is_faithful(check(spec, ["Tags", "BilledCost", "ChargePeriodStart"]))


def test_provedor_ausente_nao_obriga_colunas_ausentes(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))
    findings = check(spec, [])

    assert sorted(f.kind for f in findings) == [KIND_MISSING, KIND_MISSING]


def test_summarize_traz_contagens(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert summarize(spec, ["BilledCost"]) == "demo/demo/focus-1.2: especificado=3 emitido=1 obrigatorias=2"


# --- artifacts: o conjunto de campos vem do arquivo -------------------------


def test_columns_of_le_cabecalho_csv(tmp_path: Path) -> None:
    path = tmp_path / "custo.csv"
    path.write_text("BilledCost,ChargePeriodStart,Tags\n1,2026-10-01,a=b\n", encoding="utf-8")

    assert columns_of(path) == ("BilledCost", "ChargePeriodStart", "Tags")


def test_columns_of_le_json_de_objetos(tmp_path: Path) -> None:
    path = tmp_path / "linhas.json"
    path.write_text(json.dumps([{"a": 1, "b": 2}]), encoding="utf-8")

    assert columns_of(path) == ("a", "b")


def test_columns_of_rejeita_formato_desconhecido(tmp_path: Path) -> None:
    path = tmp_path / "saida.xlsx"
    path.write_bytes(b"nao e planilha")

    with pytest.raises(ArtifactError, match="nao suportado"):
        columns_of(path)


def test_columns_of_rejeita_arquivo_ausente(tmp_path: Path) -> None:
    with pytest.raises(ArtifactError, match="nao encontrado"):
        columns_of(tmp_path / "fantasma.csv")


# --- entrega comprimida: JSON gzipado e formato documentado ------------------


def test_columns_of_le_json_gzipado(tmp_path: Path) -> None:
    """O snapshot do AWS Config chega como .json.gz.

    Ler com ``read_text()`` estoura UnicodeDecodeError, e o efeito e cruel: a
    ferramenta fica cega para o arquivo entregue e um campo AUSENTE passa a
    parecer campo que o renderer nao emitiu. Aconteceu, e gerou um falso
    diagnostico contra um renderer correto.
    """
    caminho = tmp_path / "snapshot.json.gz"
    with gzip.open(caminho, "wt", encoding="utf-8") as handle:
        json.dump({"fileVersion": "1.3", "configurationItems": []}, handle)

    assert columns_of(caminho) == ("fileVersion", "configurationItems")


def test_populated_of_le_json_gzipado(tmp_path: Path) -> None:
    caminho = tmp_path / "snapshot.json.gz"
    with gzip.open(caminho, "wt", encoding="utf-8") as handle:
        json.dump([{"a": 1, "b": None, "c": "{}"}], handle)

    assert populated_of(caminho) == ("a",)


def test_columns_of_le_jsonl_gzipado(tmp_path: Path) -> None:
    caminho = tmp_path / "linhas.jsonl.gz"
    with gzip.open(caminho, "wt", encoding="utf-8") as handle:
        handle.write('{"x": 1}\n{"y": 2}\n')

    assert columns_of(caminho) == ("x",)


# --- sets: varios esquemas numa superficie -----------------------------------


def _sets_payload(sets: list[dict[str, object]]) -> dict[str, object]:
    payload = _spec_payload()
    payload.pop("columns")
    payload["sets"] = sets
    return payload


def _column(name: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {"name": name, "type": "string", "required": False, "source_url": URL}
    base.update(extra)
    return base


def test_mesmo_nome_em_conjuntos_diferentes_e_legitimo(tmp_path: Path) -> None:
    payload = _sets_payload(
        [
            {"name": "resources", "columns": [_column("Id"), _column("name")]},
            {"name": "securityresources", "columns": [_column("Id"), _column("name")]},
        ]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert spec.names == ("Id", "name", "Id", "name")
    assert len(spec.sets) == 2
    # O nome do conjunto vira o scope de cada coluna.
    assert [column.scope for column in spec.sets[0].columns] == ["resources", "resources"]
    assert [column.scope for column in spec.sets[1].columns] == ["securityresources", "securityresources"]


def test_nome_repetido_dentro_do_mesmo_conjunto_e_erro(tmp_path: Path) -> None:
    payload = _sets_payload([{"name": "top", "columns": [_column("Id"), _column("Id")]}])

    with pytest.raises(SpecError, match="duplicadas"):
        load_spec(_write(tmp_path, payload))


def test_scope_explicito_permite_lista_plana(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [_column("Id", scope="resources"), _column("Id", scope="attackpaths")]

    spec = load_spec(_write(tmp_path, payload))

    assert spec.names == ("Id", "Id")


def test_conjunto_sem_colunas_e_erro(tmp_path: Path) -> None:
    payload = _sets_payload([{"name": "vazio", "columns": []}])

    with pytest.raises(SpecError, match="nao vazio"):
        load_spec(_write(tmp_path, payload))


# --- evidence: a nuance que separa documentado de contratual ------------------


def test_evidence_example_only_nao_gera(tmp_path: Path) -> None:
    """Documentado apenas por exemplo nao e contrato: descreve, nao gera."""
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        _column("manifestVersion", evidence="example-only"),
    ]
    spec = load_spec(_write(tmp_path, payload))

    assert "BilledCost" in spec.generatable_names
    assert "manifestVersion" not in spec.generatable_names
    assert "manifestVersion" in spec.forbidden_names

    findings = check(spec, ["BilledCost", "manifestVersion"])

    assert [finding.kind for finding in findings] == [KIND_UNVERIFIED]
    assert findings[0].column == "manifestVersion"


def test_evidence_desconhecida_falha_fechado(tmp_path: Path) -> None:
    """Qualificador que o projeto nao conhece nao vira permissao para gerar."""
    payload = _spec_payload()
    payload["columns"] = [_column("Suspeito", evidence="provavelmente-ok")]
    spec = load_spec(_write(tmp_path, payload))

    assert spec.generatable_names == frozenset()


def test_status_com_qualificador_embutido_e_rejeitado(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [_column("X", status="verified-example-only")]

    with pytest.raises(SpecError, match="status invalido"):
        load_spec(_write(tmp_path, payload))


# --- type: nao se inventa tipo ----------------------------------------------


def test_coluna_sem_tipo_documentado_nao_gera(tmp_path: Path) -> None:
    """Sem tipo publicado, a coluna fica descrita e NAO-geravel."""
    payload = _spec_payload()
    payload["columns"] = [{"name": "SemTipo", "required": False, "source_url": URL}]
    spec = load_spec(_write(tmp_path, payload))

    assert spec.names == ("SemTipo",)
    assert spec.generatable_names == frozenset()
    assert "SemTipo" in spec.forbidden_names


# --- superficie sem schema publicado ----------------------------------------


def test_columns_vazio_e_aceito_quando_o_motivo_esta_registrado(tmp_path: Path) -> None:
    payload = _spec_payload(columns=[], unverified=["a Microsoft nao publica tipos"])

    spec = load_spec(_write(tmp_path, payload))

    assert spec.schema_published is False
    assert spec.names == ()
    # Nada pode ser emitido: qualquer campo seria invencao.
    assert check(spec, ["QualquerCoisa"])[0].kind == KIND_INVENTED


def test_columns_vazio_sem_motivo_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload(columns=[], unverified=[])

    with pytest.raises(SpecError, match="especificacao vazia"):
        load_spec(_write(tmp_path, payload))


def test_ausencia_de_columns_e_sets_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload.pop("columns")

    with pytest.raises(SpecError, match="columns.*ou.*sets"):
        load_spec(_write(tmp_path, payload))


# --- nomes repetidos entre conjuntos: a contagem e por coluna ----------------


def test_nome_geravel_num_conjunto_nao_e_proibido_por_outro(tmp_path: Path) -> None:
    """O artefato e conferido por nome, entao UMA ocorrencia geravel basta.

    Sem isso, `Id` geravel no topo do ASFF seria dado como nao-comprovado por
    causa de um `Id` apenas exemplificado em outro conjunto -- falso positivo.
    """
    payload = _sets_payload(
        [
            {"name": "top", "columns": [_column("Id", required=True)]},
            {"name": "exemplo", "columns": [_column("Id", evidence="example-only")]},
        ]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert spec.generatable_names == frozenset({"Id"})
    assert "Id" not in spec.forbidden_names
    assert spec.generatable_count == 1
    assert spec.non_generatable_count == 1
    assert is_faithful(check(spec, ["Id"], scope="top"))


def test_contagem_de_geraveis_conta_colunas_e_nao_nomes(tmp_path: Path) -> None:
    payload = _sets_payload(
        [
            {"name": "a", "columns": [_column("Id"), _column("name")]},
            {"name": "b", "columns": [_column("Id"), _column("name")]},
        ]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert spec.generatable_count == 4
    assert len(spec.generatable_names) == 2


def test_nome_sem_contrato_em_todos_os_conjuntos_continua_proibido(tmp_path: Path) -> None:
    payload = _sets_payload(
        [
            {"name": "a", "columns": [_column("Fraco", evidence="example-only")]},
            {"name": "b", "columns": [_column("Fraco", evidence="name-only")]},
        ]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert "Fraco" in spec.forbidden_names
    assert check(spec, ["Fraco"], scope="a")[0].kind == KIND_UNVERIFIED


# --- escopo: contratos disjuntos nao se comparam contra a uniao --------------


def _dois_contratos() -> dict[str, object]:
    """Dois contratos sem UM nome em comum -- como os acordos da Microsoft."""
    return _sets_payload(
        [
            {
                "name": "EA",
                "columns": [_column("a1", required=True), _column("a2", required=True)],
            },
            {
                "name": "MCA",
                "columns": [_column("b1", required=True), _column("b2", required=True)],
            },
        ]
    )


def test_varios_conjuntos_sem_escopo_e_recusado(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _dois_contratos()))

    with pytest.raises(ScopeError, match="conjuntos"):
        check(spec, ["a1", "a2"])


def test_escopo_evita_ausencia_falsa(tmp_path: Path) -> None:
    """Emitir um contrato nao pode acusar ausencia das colunas do outro."""
    spec = load_spec(_write(tmp_path, _dois_contratos()))

    assert is_faithful(check(spec, ["a1", "a2"], scope="EA"))
    assert is_faithful(check(spec, ["b1", "b2"], scope="MCA"))


def test_contra_o_conjunto_errado_o_resultado_e_ruido(tmp_path: Path) -> None:
    """Documenta o defeito que o escopo existe para impedir."""
    spec = load_spec(_write(tmp_path, _dois_contratos()))
    errados = check(spec, ["a1", "a2"], scope="MCA")

    assert {finding.kind for finding in errados} == {KIND_MISSING, KIND_INVENTED}


def test_escopo_desconhecido_e_erro(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _dois_contratos()))

    with pytest.raises(ScopeError, match="desconhecido"):
        check(spec, ["a1"], scope="PAYG")


def test_conjunto_unico_dispensa_escopo(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert is_faithful(check(spec, ["BilledCost", "ChargePeriodStart", "Tags"]))


# --- pertencer ao formato vs poder receber valor -----------------------------


def test_coluna_sempre_vazia_pertence_ao_formato_mas_nao_recebe_valor(tmp_path: Path) -> None:
    """`null-empty`: a documentacao afirma que a coluna existe e que nunca tem valor.

    Omitir a coluna seria infiel ao formato; preenche-la seria infiel ao
    contrato. Emiti-la vazia e o unico resultado correto -- por isso ela nao pode
    ser tratada como campo nao comprovado.
    """
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        _column("CapacityReservationId", evidence="null-empty", required=True),
    ]
    spec = load_spec(_write(tmp_path, payload))

    coluna = spec.columns[1]
    assert coluna.belongs_to_schema is True
    assert coluna.is_generatable is False
    assert "CapacityReservationId" in spec.emittable_names
    assert "CapacityReservationId" not in spec.forbidden_names
    assert spec.null_empty_names == frozenset({"CapacityReservationId"})

    # Emitir a coluna vazia e fiel.
    assert is_faithful(check(spec, ["BilledCost", "CapacityReservationId"]))
    # Omiti-la e falta de coluna obrigatoria do formato.
    assert [f.kind for f in check(spec, ["BilledCost"])] == [KIND_MISSING]


def test_coluna_so_de_exemplo_nao_pertence_ao_formato(tmp_path: Path) -> None:
    """`example-only` e diferente de `null-empty`: nao ha contrato de schema."""
    payload = _spec_payload()
    payload["columns"] = [_column("manifestVersion", evidence="example-only")]
    spec = load_spec(_write(tmp_path, payload))

    assert spec.columns[0].belongs_to_schema is False
    assert "manifestVersion" in spec.forbidden_names
    assert check(spec, ["manifestVersion"])[0].kind == KIND_UNVERIFIED


def test_contagem_de_emitveis_conta_colunas(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [
        _column("a"),
        _column("b", evidence="null-empty"),
        _column("c", evidence="example-only"),
    ]
    spec = load_spec(_write(tmp_path, payload))

    assert spec.emittable_count == 2
    assert spec.generatable_count == 1


# --- valores: coluna declarada vazia nao pode sair preenchida ----------------


def test_is_empty_value_reconhece_ausencia_e_nao_confunde_zero(tmp_path: Path) -> None:
    vazios: tuple[object, ...] = (None, "", "   ", "{}", "[]", "null", "None", [], {})
    for vazio in vazios:
        assert is_empty_value(vazio) is True, vazio

    # Zero e falso sao valores legitimos, nao ausencia.
    com_valor: tuple[object, ...] = (0, 0.0, False, "abc", "0", [1], {"a": 1})
    for preenchido in com_valor:
        assert is_empty_value(preenchido) is False, preenchido


def test_populated_of_ignora_coluna_vazia_e_ve_coluna_cheia(tmp_path: Path) -> None:
    path = tmp_path / "custo.csv"
    path.write_text(
        "BilledCost,CapacityReservationId,SkuPriceDetails\n"
        "10.5,,{}\n"
        "0,,\n",
        encoding="utf-8",
    )

    assert populated_of(path) == ("BilledCost",)


def test_check_values_acusa_coluna_declarada_vazia_preenchida(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        _column("CapacityReservationId", evidence="null-empty"),
    ]
    spec = load_spec(_write(tmp_path, payload))

    findings = check_values(spec, ["BilledCost", "CapacityReservationId"])

    assert [f.kind for f in findings] == [KIND_POPULATED_EMPTY]
    assert findings[0].column == "CapacityReservationId"


def test_check_values_aceita_coluna_declarada_vazia_de_fato_vazia(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        _column("CapacityReservationId", evidence="null-empty"),
    ]
    spec = load_spec(_write(tmp_path, payload))

    assert is_faithful(check_values(spec, ["BilledCost"]))


def test_check_artifact_confere_nomes_e_valores(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [
        _column("BilledCost", required=True),
        # Obrigatoria: a coluna faz parte do formato, mesmo que nunca tenha valor.
        _column("CapacityReservationId", evidence="null-empty", required=True),
    ]
    spec = load_spec(_write(tmp_path, payload))

    fiel = tmp_path / "fiel.csv"
    fiel.write_text("BilledCost,CapacityReservationId\n10.5,\n", encoding="utf-8")
    assert is_faithful(check_artifact(spec, fiel))

    inventado = tmp_path / "inventado.csv"
    inventado.write_text("BilledCost,CapacityReservationId\n10.5,cr-123\n", encoding="utf-8")
    assert [f.kind for f in check_artifact(spec, inventado)] == [KIND_POPULATED_EMPTY]

    faltando = tmp_path / "faltando.csv"
    faltando.write_text("BilledCost\n10.5\n", encoding="utf-8")
    assert KIND_MISSING in {f.kind for f in check_artifact(spec, faltando)}


def test_columns_for_devolve_apenas_o_conjunto_pedido(tmp_path: Path) -> None:
    spec = load_spec(_write(tmp_path, _dois_contratos()))

    assert [column.name for column in spec.columns_for("EA")] == ["a1", "a2"]
    assert spec.set_names == ("EA", "MCA")


# --- type_source: de onde veio o tipo ---------------------------------------


def test_tipo_derivado_do_formato_documentado_gera(tmp_path: Path) -> None:
    """Campo declarado cujo formato oficial fixa a representacao."""
    payload = _spec_payload()
    payload["columns"] = [
        _column(
            "time",
            type="string",
            type_source="format-observed",
            type_note='exemplo oficial: "time": "2017-09-14T13:32:52.9820227Z"',
        )
    ]
    spec = load_spec(_write(tmp_path, payload))

    assert spec.generatable_names == frozenset({"time"})
    assert spec.columns[0].type_source == "format-observed"


def test_tipo_derivado_do_formato_exige_campo_declarado(tmp_path: Path) -> None:
    """Nao se deriva a forma de um exemplo para um campo que so existe no exemplo."""
    payload = _spec_payload()
    payload["columns"] = [
        _column("manifestVersion", type="string", evidence="example-only", type_source="format-observed")
    ]

    with pytest.raises(SpecError, match="format-observed"):
        load_spec(_write(tmp_path, payload))


def test_type_source_desconhecido_falha_fechado(tmp_path: Path) -> None:
    payload = _spec_payload()
    payload["columns"] = [_column("X", type="string", type_source="chute")]

    assert load_spec(_write(tmp_path, payload)).generatable_names == frozenset()


def test_ausencia_de_type_source_equivale_a_documentado(tmp_path: Path) -> None:
    """Specs anteriores a este campo continuam gerando normalmente."""
    spec = load_spec(_write(tmp_path, _spec_payload()))

    assert spec.generatable_count == 3


# --- entradas de 'unverified': string ou objeto com motivo -------------------


def test_unverified_aceita_objeto_com_nome_e_motivo(tmp_path: Path) -> None:
    payload = _spec_payload(
        unverified=[{"name": "x_PricingCurrency", "reason": "consta na pagina, ausente no metadado"}]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert spec.unverified == ("x_PricingCurrency",)
    assert spec.unverified_fields[0].reason == "consta na pagina, ausente no metadado"


def test_objeto_em_unverified_nao_vira_acusacao_de_inventado(tmp_path: Path) -> None:
    """Regressao: achatar o objeto com str() perdia o nome e acusava INVENTADO.

    Um campo que a propria spec registra como nao comprovado tem de ser
    classificado como nao comprovado -- nunca como campo inventado, que e uma
    acusacao diferente e mais grave.
    """
    payload = _spec_payload(
        unverified=[{"name": "x_PricingCurrency", "reason": "divergencia entre fontes oficiais"}]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert "x_PricingCurrency" in spec.forbidden_names
    findings = check(spec, ["BilledCost", "ChargePeriodStart", "Tags", "x_PricingCurrency"])

    assert [finding.kind for finding in findings] == [KIND_UNVERIFIED]
    assert findings[0].column == "x_PricingCurrency"


def test_unverified_aceita_variacoes_de_chave(tmp_path: Path) -> None:
    payload = _spec_payload(unverified=[{"field": "a", "note": "x"}, {"column": "b"}])
    spec = load_spec(_write(tmp_path, payload))

    assert spec.unverified == ("a", "b")
    assert spec.unverified_fields[0].reason == "x"


def test_objeto_em_unverified_sem_nome_e_erro(tmp_path: Path) -> None:
    payload = _spec_payload(unverified=[{"reason": "esqueci o nome"}])

    with pytest.raises(SpecError, match="sem nome de campo"):
        load_spec(_write(tmp_path, payload))


def test_lacuna_de_topico_nao_vira_nome_de_campo_proibido(tmp_path: Path) -> None:
    """Particionamento e clustering sao lacunas, nao campos.

    Trata-las como nomes de campo poluiria a lista de proibidos e poderia acusar
    uma coluna real so por coincidencia de nome.
    """
    payload = _spec_payload(
        unverified=[
            {"name": "x_PricingCurrency", "reason": "divergencia entre fontes"},
            {"item": "clustering", "target": "cloud_pricing_export", "reason": "nao declarado"},
        ]
    )
    spec = load_spec(_write(tmp_path, payload))

    assert spec.unverified == ("x_PricingCurrency",)
    assert len(spec.unverified_topics) == 1
    assert spec.unverified_topics[0].name == "clustering [cloud_pricing_export]"
    assert "clustering" not in spec.forbidden_names


def test_sobreposicao_com_objeto_em_unverified_e_detectada(tmp_path: Path) -> None:
    payload = _spec_payload(unverified=[{"name": "Tags", "reason": "duvida"}])

    with pytest.raises(SpecError, match="ao mesmo tempo"):
        load_spec(_write(tmp_path, payload))
