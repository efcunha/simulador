"""Golden fidelity: o export OCSF do Security Hub confere com o contrato que a AWS publica.

Superfície ``aws/security-hub-ocsf-export`` — criada pelo item **E5**, e a criação *é* o achado:
o ``aws/security-hub-asff`` **não** estava errado (descreve a resposta da API ``AwsSecurityFinding``);
o que faltava era o artefato que a AWS **exporta**. A página do ``FindingsOutput`` fixa a forma:

    "``OCSF_JSON`` produces newline-delimited JSON records in the Open Cybersecurity Schema
    Framework (OCSF) format used elsewhere in Security Hub."

O QUE ESTE FICHEIRO PROVA
-------------------------
1. **A forma do arquivo é JSON por linha** — e não um array. O teste lê linha a linha; se o
   artefato virasse um array, o conjunto de chaves de topo mudaria e a conferência acusaria.
2. **Os caminhos são os que a AWS publica.** A expectativa vem da spec, e a spec cita a lista de
   ``SelectedFields`` do ``FindingsOutput`` — nunca uma forma deduzida do repositório normativo do
   OCSF, que diverge (o OCSF tem ``resource`` singular, depreciado; a AWS publica ``resources``).
3. **O que a AWS não afirma NÃO está no artefato.** ``class_uid``/``category_uid``/``type_uid``
   (a classe OCSF do envelope) e ``metadata.version`` não são emitidos, e o teste exige que não
   sejam — emitir qualquer um seria construir o contrato por analogia com o ``compliance_finding``.
4. **A âncora.** Cada registro conferido é o arquivo entregue, lido do disco.

O ``aws/security-hub-asff`` **não** é tocado: ele é a outra metade do mesmo dado, e continua
descrevendo a resposta da API.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import matrix, report
from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.fidelity.checker import KIND_INVENTED, check, check_values
from tools.synthetic_clouds.fidelity.spec import DEFAULT_SPECS_ROOT, SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.security_hub_ocsf import SecurityHubOcsfExportRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

_SURFACE = "aws/security-hub-ocsf-export"
_SCOPE = "ocsf-finding"
_ARTIFACT = "security_hub_ocsf_findings.jsonl"

#: O nome do arquivo da spec, citado LITERALMENTE: a cobertura golden do projeto exige que um
#: teste cite o arquivo, e não o caminho montado em tempo de execução.
_SPEC_FILE = "security-hub-ocsf-export.schema.json"

#: O enum de ``severity_id`` LIDO no repositorio normativo do OCSF (``dictionary.json``, tag
#: ``1.6.0``; reconferido na ``1.9.0``, onde e identico): 0 Unknown, 1 Informational, 2 Low,
#: 3 Medium, 4 High, 5 Critical, 6 Fatal, 99 Other. Copiado aqui para que o teste confronte o
#: artefato contra a enum -- e nao contra o proprio renderer, que repetiria o mesmo erro.
_SEVERITY_ID = {"Low": 2, "Medium": 3, "High": 4, "Critical": 5}


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def delivered(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    renderer = SecurityHubOcsfExportRenderer()
    out = tmp_path_factory.mktemp("ocsf")
    renderer.render(estate, out)
    return out / renderer.name


def _spec() -> SurfaceSpec:
    return load_spec(DEFAULT_SPECS_ROOT / "aws" / _SPEC_FILE)


def _records(path: Path) -> list[dict[str, Any]]:
    """Os registros do artefato, LINHA A LINHA — é a forma que a AWS publica para o formato."""
    return [json.loads(linha) for linha in path.read_text(encoding="utf-8").splitlines() if linha.strip()]


def _flatten(registro: Any, prefix: str, fields: dict[str, Any]) -> None:
    """Achata o registro em caminhos ``a.b.c``, escrevendo cada no dicionario ``fields``.

    Uma lista escreve o **contêiner** com o marcador ``[]`` e desce dentro do ITEM — é o que
    separa ``resources[]`` de ``resources[].name``. O marcador existe porque é ele que distingue
    um item de array de um objeto comum na hora de casar o achatamento com os caminhos que a AWS
    publica (``resources.name``, sem marcador); o teste normaliza o ``[]`` dos dois lados.
    """
    if isinstance(registro, dict):
        for chave, valor in registro.items():
            nome = f"{prefix}{chave}"
            fields[nome] = valor
            _flatten(valor, f"{nome}.", fields)
    elif isinstance(registro, list):
        nome = f"{prefix.rstrip('.')}[]"
        fields[nome] = registro
        for item in registro:
            _flatten(item, f"{nome}.", fields)
    elif prefix:
        fields[prefix.rstrip(".")] = registro


def test_a_superficie_esta_na_matriz_e_as_invariantes_valem(delivered: Path) -> None:
    coverage = matrix.coverage_for(_SURFACE)
    assert coverage is not None
    assert coverage.renderer == "security_hub_ocsf_export"
    assert report.staleness() == ()
    assert report.golden_gaps() == ()


def test_o_artefato_e_json_por_linha_e_nao_um_array(delivered: Path) -> None:
    """A forma publicada: 'newline-delimited JSON records'. Um array seria outro formato."""
    texto = (delivered / _ARTIFACT).read_text(encoding="utf-8")
    assert not texto.lstrip().startswith("[")
    assert texto.endswith("\n"), "cada registro e uma linha terminada por newline"
    registros = _records(delivered / _ARTIFACT)
    assert registros, "sem registro nao ha o que conferir"
    assert all(isinstance(registro, dict) for registro in registros)
    # Cada linha e UM objeto: a contagem de linhas e a contagem de registros.
    assert len(registros) == len([linha for linha in texto.splitlines() if linha.strip()])


def test_os_caminhos_de_topo_conferem_com_o_contrato(delivered: Path) -> None:
    """O `columns_of` de JSONL le as chaves de TOPO: elas tem de ser as colunas de continente."""
    spec = _spec()
    alvo = delivered / _ARTIFACT
    esperado = {c.name for c in spec.columns_for(_SCOPE) if c.belongs_to_schema and "." not in c.name and "[]" not in c.name}
    assert set(columns_of(alvo)) == esperado
    assert check(spec, columns_of(alvo), scope=_SCOPE) == ()
    assert check_values(spec, populated_of(alvo), scope=_SCOPE) == ()


def test_os_caminhos_aninhados_conferem_com_o_contrato(delivered: Path) -> None:
    """Os caminhos emitidos e os declarados coincidem, com a notação de lista normalizada.

    O achatamento produz DUAS populações de nome, e as duas são legítimas: os contêineres que a
    spec declara (``cloud``, ``metadata.product`` — eles **são** colunas) e as folhas que ela
    enumera. A conferência é por igualdade nas duas.

    **A normalização do ``[]`` é deliberada, e a diferença é de notação, não de dado.** A AWS
    publica ``resources.name`` (sem marcador de lista) na sua lista de campos; o achatamento de um
    item de array escreve ``resources[].name``. Normalizar aqui mantém a spec como a AWS a
    publica — reescrever os caminhos da spec para acomodar o achatamento faria o texto do contrato
    deixar de ser citável — e ao mesmo tempo exige que o CONJUNTO DE CAMPOS seja exatamente o
    declarado, que é o que a fidelidade mede.
    """
    spec = _spec()
    declarados = {c.name for c in spec.columns_for(_SCOPE) if c.belongs_to_schema}
    encontrados: set[str] = set()
    for registro in _records(delivered / _ARTIFACT):
        campos: dict[str, Any] = {}
        _flatten(registro, "", campos)
        encontrados |= {nome.replace("[]", "") for nome in campos}
    normalizados = {nome.replace("[]", "") for nome in declarados}
    assert encontrados <= normalizados, f"emitido fora do contrato: {sorted(encontrados - normalizados)}"
    assert normalizados <= encontrados, f"declarado e nao emitido: {sorted(normalizados - encontrados)}"


def test_o_que_a_aws_nao_afirma_nao_e_emitido(delivered: Path) -> None:
    """A classe OCSF e o `metadata.version` ficam FORA: nenhuma fonte da AWS os afirma.

    Emitir a classe seria a analogia com o ``compliance_finding`` (oid 3) do repositório normativo
    do OCSF — e a lista de campos da AWS a recusa, porque mistura campos de vulnerabilidade,
    malware e databucket. Este teste é a guarda contra "resolver" a lacuna por semelhança.
    """
    spec = _spec()
    assert any("class_uid" in item for item in spec.unverified)
    assert "metadata.version" in spec.unverified
    for registro in _records(delivered / _ARTIFACT):
        assert "class_uid" not in registro
        assert "category_uid" not in registro
        assert "type_uid" not in registro
        assert "version" not in registro.get("metadata", {})


def test_os_valores_vem_do_modelo(delivered: Path, estate: CanonicalEstate) -> None:
    """Os valores são do estado, e não plausíveis: uid, título, conta, provedor e região."""
    registros = _records(delivered / _ARTIFACT)
    por_id = {f.finding_id: f for f in estate.findings if f.provider == "aws"}
    for registro in registros:
        finding = por_id[registro["finding_info"]["uid"]]
        assert registro["metadata"]["uid"] == finding.finding_id
        assert registro["metadata"]["product"]["name"] == finding.product_name
        assert registro["finding_info"]["title"] == finding.title
        assert registro["finding_info"]["types"] == list(finding.types)
        assert registro["severity_id"] == _SEVERITY_ID[registro["severity"]]
        assert registro["cloud"]["provider"] == "AWS"


def test_o_status_e_o_mesmo_mapeamento_do_asff(delivered: Path) -> None:
    """O par (rotulo, identificador) do OCSF sai do MESMO literal nativo que o ASFF mapeia."""
    pares = {(registro["status"], registro["status_id"]) for registro in _records(delivered / _ARTIFACT)}
    assert pares <= {("New", 1), ("In Progress", 2), ("Resolved", 4)}
    assert pares, "nenhum status mapeado"


def test_a_severidade_sai_do_enum_do_ocsf_e_nao_do_literal_nativo(delivered: Path) -> None:
    """O par ``(severity, severity_id)`` vem do enum lido no OCSF -- e da legenda, nao do nativo.

    Duas coisas sao conferidas aqui, e as duas sao consequencias do enum:

    1. O **valor** do inteiro: ``Low``=2, ``Medium``=3, ``High``=4, ``Critical``=5, exatamente
       como o ``dictionary.json`` do OCSF declara (tag 1.6.0, reconferido na 1.9.0).
    2. A **forma** do rotulo: o mesmo arquivo define ``severity`` como *"normalized to the caption
       of the ``severity_id`` value"*. O estado carrega o literal NATIVO em maiusculas
       (``model/native.py``), entao um rotulo em maiusculas seria o valor da fonte -- nao o valor
       que o OCSF define. E o par ``status``/``status_id`` deste renderer ja saia assim.
    """
    pares = {(registro["severity"], registro["severity_id"]) for registro in _records(delivered / _ARTIFACT)}
    assert pares <= set(_SEVERITY_ID.items())
    assert pares, "nenhuma severidade mapeada"
    assert not any(rotulo.isupper() for rotulo, _ in pares), (
        f"o rotulo saiu com a caixa do literal nativo, e nao com a legenda do enum: {sorted(pares)}"
    )


def test_a_severidade_nao_e_mais_lacuna() -> None:
    """``severity_id`` saiu de ``unverified`` porque o enum foi lido -- nao por deducao."""
    spec = _spec()
    assert "severity_id" not in spec.unverified
    assert "severity_id" in {c.name for c in spec.columns_for(_SCOPE)}


def test_o_auditor_denuncia_coluna_inventada(delivered: Path, tmp_path: Path) -> None:
    spec = _spec()
    alvo = tmp_path / "inventada.jsonl"
    alvo.write_text(json.dumps({"class_uid": 2003}) + "\n", encoding="utf-8")

    findings = check(spec, columns_of(alvo), scope=_SCOPE)
    assert any(f.kind == KIND_INVENTED and f.column == "class_uid" for f in findings)


def test_renderizar_duas_vezes_da_os_mesmos_bytes(estate: CanonicalEstate, tmp_path: Path) -> None:
    renderer = SecurityHubOcsfExportRenderer()
    a, b = tmp_path / "a", tmp_path / "b"
    renderer.render(estate, a)
    renderer.render(estate, b)
    relativos = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    assert relativos == sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    for relativo in relativos:
        assert (a / relativo).read_bytes() == (b / relativo).read_bytes()


def test_a_proveniencia_nomeia_as_lacunas(delivered: Path, estate: CanonicalEstate) -> None:
    """O relatório irmão conta os registros e diz o que NÃO foi possível afirmar."""
    relatorio = json.loads((delivered / "_provenance.json").read_text(encoding="utf-8"))
    assert relatorio["counts"]["records"] == len(_records(delivered / _ARTIFACT))
    assert relatorio["spec"].endswith(_SPEC_FILE)
    itens = " ".join(gap["item"] for gap in relatorio["model_gaps"])
    assert "class_uid" in itens
    assert "metadata.version" in itens