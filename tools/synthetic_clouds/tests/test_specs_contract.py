"""O contrato das especificacoes, verificado pela suite e nao por inspecao manual.

Se uma spec perder evidencia, citar dominio nao-oficial ou declarar geravel uma
coluna sem tipo, isso tem de quebrar a suite -- nao depender de alguem lembrar de
rodar o auditor.
"""

from __future__ import annotations

from tools.synthetic_clouds.fidelity.sources import is_official_url
from tools.synthetic_clouds.fidelity.spec import STATUS_VERIFIED, load_all_specs

SPECS = load_all_specs()


def test_ha_especificacoes_carregadas() -> None:
    # As 21 superficies dos tres provedores.
    assert len(SPECS) >= 20


def test_todas_as_specs_carregam_e_se_identificam() -> None:
    # load_all_specs levanta SpecError em qualquer spec invalida: chegar aqui ja
    # prova que as 21 passam pelo validador estrutural.
    assert all(spec.surface and spec.provider for spec in SPECS)
    assert len({spec.surface for spec in SPECS}) == len(SPECS), "surfaces duplicadas"


def test_todo_campo_cita_documentacao_oficial() -> None:
    offenders = [
        f"{spec.surface}:{column.name} -> {column.source_url!r}"
        for spec in SPECS
        for column in spec.columns
        if not is_official_url(column.source_url or "")
    ]

    assert not offenders, "campo apoiado em fonte nao-oficial:\n" + "\n".join(offenders)


def test_referencia_de_cada_spec_e_oficial_e_datada() -> None:
    for spec in SPECS:
        assert is_official_url(str(spec.reference.get("url", ""))), spec.surface
        assert spec.reference.get("consulted_at"), spec.surface


def test_coluna_geravel_tem_tipo_evidencia_e_url() -> None:
    for spec in SPECS:
        for column in spec.columns:
            if not column.is_generatable:
                continue
            assert column.type, f"{spec.surface}:{column.name} sem tipo"
            assert column.status == STATUS_VERIFIED, f"{spec.surface}:{column.name}"
            assert column.source_url, f"{spec.surface}:{column.name} sem URL"
            assert (column.evidence or "declared") == "declared", f"{spec.surface}:{column.name}"
            assert (column.type_source or "documented") in {"documented", "format-observed"}


def test_spec_vazia_precisa_declarar_o_motivo() -> None:
    for spec in SPECS:
        assert spec.columns or spec.unverified, spec.surface


def test_conjuntos_e_nao_comprovadas_nao_se_sobrepoem() -> None:
    for spec in SPECS:
        sobrepostos = sorted(set(spec.names) & set(spec.unverified))
        assert not sobrepostos, f"{spec.surface}: {sobrepostos}"


def test_toda_superficie_tem_coluna_ou_motivo_por_superficie() -> None:
    """Nenhuma superficie pode ser um arquivo vazio sem explicacao."""
    for spec in SPECS:
        assert spec.columns or spec.unverified, spec.surface
