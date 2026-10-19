"""As garantias do processo de fidelidade, exigidas pela suite.

Dois modos de o projeto mentir para si mesmo, e ambos ja aconteceram:

* a matriz de cobertura dizer que uma superficie esta bloqueada quando a
  documentacao passou a sustenta-la (aconteceu quando `format-observed` foi
  aplicado: Resource Graph, NSG e ARM ficaram obsoletos sem ninguem notar);
* uma superficie declarada como gerada nao ter nenhum teste que a confronte com
  a especificacao -- fidelidade presumida.

Aqui eles deixam de ser relatorio e passam a ser invariante: um projeto que se
diz fiel sem provar nao esta fiel.
"""

from __future__ import annotations

from pathlib import Path

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.audit_renderers import SurfaceAudit, readiness


def test_a_matriz_nao_contradiz_as_especificacoes() -> None:
    problemas = report.staleness()

    assert not problemas, "matriz desatualizada:\n" + "\n".join(problemas)


def test_toda_superficie_gerada_tem_teste_que_cita_a_sua_spec() -> None:
    problemas = report.golden_gaps()

    assert not problemas, "fidelidade nao verificada:\n" + "\n".join(problemas)


def test_staleness_denuncia_superficie_bloqueada_que_ja_e_geravel(tmp_path: Path) -> None:
    """Prova que a invariante sabe falhar, em vez de passar por vacuidade."""
    import json

    from tools.synthetic_clouds.fidelity import matrix as matriz

    # Especificacao minima de uma superficie declarada como BLOQUEADA na matriz.
    bloqueada = matriz.by_status(matriz.STATUS_BLOCKED)[0].surface
    provider, nome = bloqueada.split("/")
    pasta = tmp_path / provider
    pasta.mkdir()
    (pasta / f"{nome}.schema.json").write_text(
        json.dumps(
            {
                "surface": bloqueada,
                "provider": provider,
                "reference": {"title": "t", "url": "https://learn.microsoft.com/x", "consulted_at": "2026-10-14"},
                "columns": [
                    {
                        "name": "Coluna",
                        "type": "string",
                        "required": False,
                        "source_url": "https://learn.microsoft.com/x",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    problemas = report.staleness(tmp_path)

    assert any(bloqueada in item for item in problemas), problemas


def test_golden_gaps_denuncia_superficie_gerada_sem_teste(tmp_path: Path) -> None:
    pasta_testes = tmp_path / "tests"
    pasta_testes.mkdir()
    (pasta_testes / "test_algo.py").write_text("# nenhuma spec citada aqui\n", encoding="utf-8")

    problemas = report.golden_gaps(tests_dir=pasta_testes)

    assert problemas, "uma superficie gerada sem teste tem de ser denunciada"


def test_golden_gaps_denuncia_teste_que_cita_sem_confrontar(tmp_path: Path) -> None:
    """Citar a spec nao e conferir o artefato.

    Um teste que so carrega a especificacao e afirma contagens passaria como
    cobertura sem nunca comparar o arquivo entregue com o contrato -- que e
    exatamente o que o projeto promete.
    """
    pasta_testes = tmp_path / "tests"
    pasta_testes.mkdir()
    implementada = matrix.by_status(matrix.STATUS_IMPLEMENTED)[0]
    spec = f"{implementada.surface.split('/')[-1]}.schema.json"
    (pasta_testes / "test_cita_sem_conferir.py").write_text(
        f'"""Cita {spec} mas nao chama nada que leia o artefato."""\nvalor = 1\n',
        encoding="utf-8",
    )

    problemas = report.golden_gaps(tests_dir=pasta_testes)

    assert any("nunca confronta o artefato" in item for item in problemas), problemas


def test_golden_gaps_aceita_teste_que_confronta(tmp_path: Path) -> None:
    pasta_testes = tmp_path / "tests"
    pasta_testes.mkdir()
    implementada = matrix.by_status(matrix.STATUS_IMPLEMENTED)[0]
    spec = f"{implementada.surface.split('/')[-1]}.schema.json"
    (pasta_testes / "test_confere.py").write_text(
        f'"""Le {spec} e confronta o artefato."""\nresultado = check_artifact(spec, caminho)\n',
        encoding="utf-8",
    )

    problemas = report.golden_gaps(tests_dir=pasta_testes)

    # Nao deve acusar ESTA superficie; outras continuarao ausentes, o que e esperado.
    assert not any(implementada.surface in item and "nunca confronta" in item for item in problemas)


# --- veredito de prontidao ---------------------------------------------------


def _audit(surface: str, **troca: object) -> SurfaceAudit:
    base: dict[str, object] = {
        "surface": surface,
        "renderer": "r",
        "artifacts": 1,
        "records": 10,
        "invented": (),
        "per_set": (),
        "populated": 5,
        "documented": 5,
        "required_empty": (),
        "error": None,
    }
    base.update(troca)
    return SurfaceAudit(**base)  # type: ignore[arg-type]


def test_prontidao_aceita_superficie_limpa() -> None:
    assert readiness((_audit("aws/x"),)) == ()


def test_prontidao_recusa_render_com_erro() -> None:
    problemas = readiness((_audit("aws/x", error="NameError: nope", records=0),))

    assert any("render falhou" in item for item in problemas)


def test_prontidao_recusa_superficie_sem_registro() -> None:
    """Formato fiel e vazio nao e dado -- foi o buraco que a rede escondeu."""
    problemas = readiness((_audit("gcp/x", records=0),))

    assert any("nenhum registro" in item for item in problemas)


def test_prontidao_recusa_coluna_inventada() -> None:
    problemas = readiness((_audit("azure/x", invented=("campo_inventado",)),))

    assert any("fora de qualquer spec" in item for item in problemas)


def test_prontidao_nao_usa_taxa_de_preenchimento_como_criterio() -> None:
    """Preencher pouco nao impede: depende do que o modelo tem fonte para afirmar."""
    assert readiness((_audit("gcp/x", populated=1),)) == ()


def test_prontidao_recusa_superficie_que_so_entrega_artefato_alheio() -> None:
    """Superficie que divide renderer passa no criterio de registro lendo a IRMA.

    Foi o caso do manifesto do cost export da Azure: o renderer escreve so o
    FOCUS, e a superficie do manifesto contava como 'com registro' por ler o CSV
    da irma. Zero nomes proprios presentes denuncia.
    """
    problemas = readiness((_audit("azure/x", per_set=(("<unico>", 0, 41),)),))

    assert any("nenhum artefato carrega campo proprio" in item for item in problemas)


def test_prontidao_aceita_quando_ao_menos_um_conjunto_tem_campo() -> None:
    """Conjunto vazio e legitimo: a spec cobre recursos que o export nao popula."""
    limpo = _audit("azure/y", per_set=(("Resources", 1, 14), ("SecurityResources/alerts", 0, 6)))

    assert readiness((limpo,)) == ()


def test_prontidao_nao_exige_coluna_obrigatoria_preenchida() -> None:
    """No FOCUS, 'required' e sobre a COLUNA existir; o valor pode ser nulo.

    Exigir valor tornaria o veredito impossivel de satisfazer honestamente -- mas a
    contagem aparece no relatorio como evidencia, porque ausencia em massa ou tem
    fonte faltando ou tem motivo a declarar.
    """
    com_vazias = _audit("azure/z", required_empty=("ChargeClass", "SkuId"))

    assert readiness((com_vazias,)) == ()


# --- contrato das specs dentro do aceitador ----------------------------------


def test_spec_problemas_esta_vazio_para_as_specs_reais() -> None:
    """O aceitador herda a checagem de contrato: contrato limpo hoje."""
    from tools.synthetic_clouds.fidelity.__main__ import _spec_problems
    from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT

    assert _spec_problems(DEFAULT_SPECS_ROOT) == []


def test_spec_problemas_denuncia_spec_malformada(tmp_path: Path) -> None:
    from tools.synthetic_clouds.fidelity.__main__ import _spec_problems

    raiz = tmp_path / "specs"
    (raiz / "aws").mkdir(parents=True)
    (raiz / "aws" / "quebrada.schema.json").write_text('{"surface": "aws/x"}', encoding="utf-8")

    problemas = _spec_problems(raiz)

    assert problemas, "uma spec sem o contrato minimo tem de ser denunciada"


def test_spec_problemas_nao_quebra_com_pasta_vazia(tmp_path: Path) -> None:
    from tools.synthetic_clouds.fidelity.__main__ import _spec_problems

    assert _spec_problems(tmp_path / "inexistente") == []
