"""Golden fidelity: the GCP security / network / instance artifacts vs the cited specs.

The specification is the source of truth (``specs/README.md``), its normative reader is
``fidelity.spec.load_spec`` and its comparison engine is ``fidelity.checker``. These tests
RENDER each surface with the renderer's own ``render`` and compare the DELIVERED FILES with
the cited specification through ``check_artifact`` -- never an in-memory column list, which
would only prove that two copies of the same mistake agree.

Artifact and provenance are separate files
------------------------------------------
Every artifact emitted by these four surfaces carries ONLY documented fields, and every
surface also writes a sibling ``_provenance.json`` with the mechanism, the counts, the model
gaps and the provider's JSON spelling of a repeated field. The separation is asserted here,
not assumed: ``test_no_artifact_mixes_in_provenance`` fails if a provenance key ever appears
inside a record file, which is what an ingester would read as a cloud field.

The repeated-field notation
---------------------------
The specs spell a repeated field as ``nome[]`` (``ancestors[]``, ``networkInterfaces[]``),
which is how the provider's field table spells it; the provider's JSON serialization drops
the brackets. The artifacts keep the DOCUMENTED spelling -- the name under contract, and the
only one the fidelity core can compare -- and the bracket-free wire spelling is published in
``_provenance.json`` under ``naming.wire_names``. ``test_repeated_notation_is_injective``
proves the mapping cannot merge two documented names, and
``test_wire_naming_is_the_specs_own_repeated_fields`` proves it is derived from the spec.

What each surface proves here
-----------------------------
* ``security-command-center-findings-bigquery`` -- the target is a TYPED BigQuery table and
  six of its columns (``source_id``, ``finding_id``, ``event_time``, ``bulk_export_id``,
  ``finding``, ``resource``) have no published BigQuery type, so they are not generated.
  What is generated is the 68 documented ``finding.*`` paths of the ``Finding`` object. The
  check therefore reports EXACTLY the four columns that are required AND untyped
  (``source_id``, ``finding_id``, ``event_time``, ``finding``) as ``missing`` -- and this
  file asserts that set equals the spec's own ``required - emittable`` set. That is the
  honest answer of the surface, not a defect, so ``is_faithful`` is deliberately asserted
  FALSE there and the failing set is pinned to the specification's own gap.
* ``vpc-flow-logs-bigquery`` -- there is no direct export to BigQuery: the documented
  destination is Cloud Logging and the BigQuery path is a linked dataset with an
  unpublished column list. The artifact keeps the documented RECORD FORMAT (181 paths) and
  now projects the canonical network model into it: one record per GCP ``NetworkFlow``, with
  the values PROVED to come from the model (multiset comparison, not a smoke test) and a
  closed list of the paths that stay empty because the model does not carry them.
* ``cloud-asset-inventory-compute-instance`` -- ten named sets, so every check passes the
  correct ``scope``. ``relatedAssets`` (DEPRECATED, "The server will never generate
  responses with this field") must be absent from every artifact.
* ``compute-instances-rest`` -- the REST representation of the resource (48 fields), not a
  file.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of, populated_paths
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    KIND_UNVERIFIED,
    ScopeError,
    check_artifact,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.network import DECISION_DENIED, NetworkFlow
from tools.synthetic_clouds.render.gcp_asset_inventory import (
    ARTIFACT_BY_SCOPE as CAI_ARTIFACT_BY_SCOPE,
)
from tools.synthetic_clouds.render.gcp_asset_inventory import GcpAssetInventoryRenderer
from tools.synthetic_clouds.render.gcp_compute_instances import GcpComputeInstancesRenderer
from tools.synthetic_clouds.render.gcp_flow_logs import GcpFlowLogsRenderer
from tools.synthetic_clouds.render.gcp_scc_findings import GcpSccFindingsRenderer
from tools.synthetic_clouds.scenarios.emit import apply_all

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "specs" / "gcp"

#: Superficie -> arquivo de spec e contagem documentada de entradas de campo. Estas
#: contagens sao as da documentacao citada; uma edicao de spec que as mude e exatamente o
#: evento que este arquivo existe para mostrar.
_SPEC_FILE: dict[str, str] = {
    "scc": "security-command-center-findings-bigquery.schema.json",
    "flow": "vpc-flow-logs-bigquery.schema.json",
    "cai": "cloud-asset-inventory-compute-instance.schema.json",
    "instances": "compute-instances-rest.schema.json",
}
_EXPECTED_COLUMNS: dict[str, int] = {"scc": 74, "flow": 181, "cai": 90, "instances": 48}

#: O relatorio de proveniencia e IRMAO do artefato, nunca parte dele. Estas chaves sao o
#: vocabulario de proveniencia -- e deliberadamente NAO incluem palavras que tambem sao
#: nomes de campo documentados (``kind`` no Compute, ``asset_type`` no CAI), porque o que
#: se prova aqui e que um RELATORIO nao vaza para dentro de um REGISTRO; o conjunto exato de
#: campos do artefato e provado em ``test_artifact_carries_exactly_the_documented_fields``.
_PROVENANCE_FILE = "_provenance.json"
_PROVENANCE_KEYS = frozenset(
    {
        "artifact_field_names",
        "artifacts",
        "artifacts_by_scope",
        "mechanism",
        "model_gaps",
        "name_pattern_violations",
        "naming",
        "notes",
        "not_generated",
        "records_note",
        "row_keys",
        "spec",
        "spec_set_sizes",
        "surface",
    }
)

#: As tres colunas de clustering que a pagina de export SCC afirma, e as seis colunas da
#: tabela `findings` que ela publica SEM tipo.
_SCC_CLUSTERING = ("source_id", "finding_id", "event_time")
_SCC_TABLE_COLUMNS = ("source_id", "finding_id", "event_time", "bulk_export_id", "finding", "resource")

#: Os caminhos do ENVELOPE e do objeto ``Finding`` que a projecao do modelo PREENCHE. Lista
#: fechada: tudo o que a spec publica e nao esta aqui sai vazio, porque o modelo nao o carrega
#: OU porque o vocabulario e o de outra nuvem (title/types/confidence/criticality sao do ASFF).
_SCC_FILLED = frozenset(
    {
        "source_id",
        "finding_id",
        "event_time",
        "bulk_export_id",
        "finding.name",
        "finding.parent",
        "finding.resourceName",
        "finding.category",
        "finding.description",
        "finding.eventTime",
        "finding.createTime",
    }
)

#: As colunas de envelope da tabela ``findings`` que a pagina de export lista e cujo TIPO
#: BigQuery ela nao publica, mas que o artefato EMITE: ele e um registro, nao um DDL.
_SCC_ENVELOPE_EMITTED = ("source_id", "finding_id", "event_time", "bulk_export_id", "resource")

#: As colunas ``required`` da spec que o artefato NAO preenche, com o motivo declarado -- o
#: mesmo invariante que o auditor mede em ``obrig.vazias``. O teste falha se a spec ganhar
#: uma obrigatoria vazia que nao esteja aqui.
_SCC_REQUIRED_EMPTY_DECLARED = frozenset({"finding"})

#: O mesmo invariante para a superficie de rede, medida com ``populated_paths`` (o leitor do
#: nucleo): o container ``connection`` e os campos que o modelo de rede nao carrega.
_FLOW_REQUIRED_EMPTY_DECLARED = frozenset(
    {
        "connection",
        "round_trip_time",
        "rtt_msec",
        "drop_reason",
        "bytes_dropped",
        "packets_dropped",
        "throughput_inclusion",
    }
)

_CAI_SCOPES = tuple(sorted(CAI_ARTIFACT_BY_SCOPE))
_CAI_ASSET_TYPE = "compute.googleapis.com/Instance"

#: Os caminhos de ``instances.get`` que a projecao do perfil de instancia PREENCHE. Lista
#: fechada: tudo o que a spec publica e nao esta aqui sai vazio (ver os motivos na
#: proveniencia -- enderecos, disco raiz e imagem nao tem subcampo transcrito na spec).
_INSTANCES_FILLED = frozenset(
    {"kind", "id", "creationTimestamp", "name", "machineType", "status", "zone", "labels"}
)

#: Surface -> (arquivo do artefato, scope da spec). O escopo e obrigatorio em toda
#: superficie com mais de um conjunto nomeado; aqui ele e explicito por artefato.
_ARTIFACTS: tuple[tuple[str, str, str | None], ...] = (
    ("scc", "findings_rows.json", None),
    ("flow", "flow_log_records.json", None),
    ("instances", "instances.json", None),
    *tuple(("cai", CAI_ARTIFACT_BY_SCOPE[scope], scope) for scope in _CAI_SCOPES),
)


# -- fixtures -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


def _render(factory: Any, estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory, label: str) -> Path:
    """Roda o ``render`` do renderer e devolve o diretorio ENTREGUE."""
    out = tmp_path_factory.mktemp(label)
    factory().render(estate, out)
    return out / label


@pytest.fixture(scope="module")
def scc_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(GcpSccFindingsRenderer, estate, tmp_path_factory, "gcp_scc_findings")


@pytest.fixture(scope="module")
def flow_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(GcpFlowLogsRenderer, estate, tmp_path_factory, "gcp_flow_logs")


@pytest.fixture(scope="module")
def cai_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(GcpAssetInventoryRenderer, estate, tmp_path_factory, "gcp_asset_inventory")


@pytest.fixture(scope="module")
def instances_dir(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _render(GcpComputeInstancesRenderer, estate, tmp_path_factory, "gcp_compute_instances")


@pytest.fixture(scope="module")
def surface_dirs(
    scc_dir: Path, flow_dir: Path, cai_dir: Path, instances_dir: Path
) -> dict[str, Path]:
    return {
        "gcp_scc_findings": scc_dir,
        "gcp_flow_logs": flow_dir,
        "gcp_asset_inventory": cai_dir,
        "gcp_compute_instances": instances_dir,
    }


# -- helpers (artifact parsing, never the code that wrote it) ------------------------


def _spec(key: str) -> SurfaceSpec:
    return load_spec(_SPEC_DIR / _SPEC_FILE[key])


def _documented_spelling(names: Sequence[str]) -> tuple[str, ...]:
    """O nome que a spec da a um campo repetido e ``nome[]``; a chave JSON e ``nome``."""
    return tuple(name[:-2] if name.endswith("[]") else name for name in names)


def _emittable_names(spec: SurfaceSpec, scope: str | None = None) -> set[str]:
    columns = spec.columns if scope is None else spec.columns_for(scope)
    return {column.name for column in columns if column.belongs_to_schema}


def _artifact_path(dirs: Mapping[str, Path], key: str, filename: str) -> Path:
    return dirs[_SURFACE_DIR[key]] / filename


_SURFACE_DIR: dict[str, str] = {
    "scc": "gcp_scc_findings",
    "flow": "gcp_flow_logs",
    "cai": "gcp_asset_inventory",
    "instances": "gcp_compute_instances",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _records(path: Path) -> list[dict[str, Any]]:
    """Os registros de um artefato, seja um array JSON, um objeto JSON ou NDJSON."""
    if path.suffix.lower() in {".ndjson", ".jsonl"}:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    payload = _load_json(path)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    assert isinstance(payload, dict), f"{path}: JSON precisa ser objeto ou lista de objetos"
    return [payload]


def _mutate(tmp_path: Path, source: Path, extra: Mapping[str, Any]) -> Path:
    """Copia o artefato REAL acrescentando ``extra`` no primeiro registro (falsificacao)."""
    rows = _records(source)
    rows[0] = {**rows[0], **extra}
    target = tmp_path / "mutated.json"
    target.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return target


def _provenance(dirs: Mapping[str, Path], key: str) -> dict[str, Any]:
    """O relatorio de proveniencia da superficie (o arquivo IRMAO do artefato)."""
    payload = _load_json(_artifact_path(dirs, key, _PROVENANCE_FILE))
    assert isinstance(payload, dict), f"{key}: {_PROVENANCE_FILE} precisa ser um objeto JSON"
    return payload


# -- the specs themselves -----------------------------------------------------------


@pytest.mark.parametrize("key", sorted(_EXPECTED_COLUMNS))
def test_specs_have_the_size_the_documentation_declares(key: str) -> None:
    spec = _spec(key)
    assert len(spec.columns) == _EXPECTED_COLUMNS[key], key
    assert len(spec.names) == _EXPECTED_COLUMNS[key], key


@pytest.mark.parametrize("key", sorted(_EXPECTED_COLUMNS))
def test_repeated_notation_is_injective(key: str) -> None:
    """``nome[]`` -> ``nome`` nao pode fundir dois nomes DENTRO DE UM CONJUNTO.

    Entre conjuntos a repeticao e legitima (``ancestors`` no schema BigQuery RESOURCE e
    ``ancestors[]`` na mensagem REST sao contratos diferentes), entao a prova e por conjunto.
    """
    spec = _spec(key)
    scopes: tuple[str | None, ...] = spec.set_names or (None,)
    for scope in scopes:
        names = [column.name for column in (spec.columns if scope is None else spec.columns_for(scope))]
        assert len(set(_documented_spelling(names))) == len(set(names)), f"{key}/{scope}"


def test_scc_six_table_columns_are_exactly_the_untyped_ones() -> None:
    """As 6 colunas sem tipo publicado sao exatamente as que nao pertencem ao formato."""
    spec = _spec("scc")
    untyped = {column.name for column in spec.columns if not column.type}
    assert untyped == set(_SCC_TABLE_COLUMNS)
    assert untyped == set(spec.non_emittable_names)
    assert len(untyped) == 6
    # Quatro delas sao OBRIGATORIAS pela propria tabela de campos da pagina de export: e
    # essa interseccao que o artefato nao pode satisfazer sem inventar tipo.
    required_untyped = {column.name for column in spec.columns if column.required and not column.belongs_to_schema}
    assert required_untyped == {"source_id", "finding_id", "event_time", "finding"}
    assert len(spec.columns) - len(untyped) == spec.emittable_count == 68


def test_cai_publishes_ten_sets_and_the_only_deprecated_field_is_related_assets() -> None:
    spec = _spec("cai")
    assert len(spec.set_names) == 10
    assert set(spec.non_emittable_names) == {"relatedAssets"}
    assert {column.evidence for column in spec.columns if column.name == "relatedAssets"} == {"deprecated"}
    # Nenhum conjunto publicado pode ficar sem artefato em silencio, e dois conjuntos nao
    # podem dividir o mesmo arquivo (o artefato e a prova de UM contrato).
    assert set(_CAI_SCOPES) == set(spec.set_names)
    assert len(set(CAI_ARTIFACT_BY_SCOPE.values())) == len(_CAI_SCOPES)


def test_flow_logs_surface_has_no_unpublished_type() -> None:
    """A superficie de rede tem os 181 caminhos com tipo publicado (o RECORD e o que existe)."""
    spec = _spec("flow")
    assert spec.emittable_count == 181 == spec.generatable_count
    assert spec.non_emittable_names == frozenset()
    assert len({name.split(".", 1)[0] for name in spec.names}) == 35


# -- artifact vs provenance: two files, never one ------------------------------------


@pytest.mark.parametrize(("key", "filename", "scope"), _ARTIFACTS)
def test_artifact_carries_exactly_the_documented_fields(
    surface_dirs: Mapping[str, Path], key: str, filename: str, scope: str | None
) -> None:
    """A conferencia principal: o arquivo REAL contra a spec, no escopo do conjunto."""
    spec = _spec(key)
    path = _artifact_path(surface_dirs, key, filename)
    assert path.is_file(), f"{key}: artefato ausente: {filename}"
    observed = set(columns_of(path))
    # O SCC tambem emite as colunas de ENVELOPE da tabela (sem tipo publicado, mas exigidas
    # pela pagina de export); nas outras superficies o conjunto e o que pertence ao formato.
    esperado = _emittable_names(spec, scope) | (set(_SCC_ENVELOPE_EMITTED) if key == "scc" else set())
    assert observed == esperado, (
        f"{key}/{scope}: missing={sorted(esperado - observed)} extra={sorted(observed - esperado)}"
    )
    findings = check_artifact(spec, path, scope=scope)
    if key == "scc":
        # As duas divergencias DECLARADAS da superficie: as 5 colunas de envelope que a
        # documentacao exige e nao tipa, e o container `finding` representado pelos filhos.
        assert {finding.column for finding in findings} == set(_SCC_ENVELOPE_EMITTED) | set(
            _SCC_REQUIRED_EMPTY_DECLARED
        ), findings
    else:
        assert is_faithful(findings), f"{key}/{scope}: {findings}"


@pytest.mark.parametrize(("key", "filename", "scope"), _ARTIFACTS)
def test_no_artifact_mixes_in_provenance(
    surface_dirs: Mapping[str, Path], key: str, filename: str, scope: str | None
) -> None:
    """Principio: o que sai no artefato e o REGISTRO; o relatorio vive ao lado.

    Um ingester le o arquivo de registro; qualquer chave de proveniencia ali dentro seria um
    campo que nuvem nenhuma documenta. Aqui a interseccao tem de ser vazia, e o arquivo de
    proveniencia existe ao lado.
    """
    path = _artifact_path(surface_dirs, key, filename)
    for record in _records(path):
        assert not (set(record) & _PROVENANCE_KEYS), f"{key}: proveniencia dentro do artefato"
    provenance = _artifact_path(surface_dirs, key, _PROVENANCE_FILE)
    assert provenance.is_file(), f"{key}: sem arquivo de proveniencia"
    assert set(_load_json(provenance)) & _PROVENANCE_KEYS, "o relatorio nao tem conteudo de proveniencia"
    assert _load_json(provenance)["spec"] == f"specs/gcp/{_SPEC_FILE[key]}"


def test_every_emitted_file_is_either_an_artifact_or_the_provenance(surface_dirs: Mapping[str, Path]) -> None:
    """Nenhum arquivo inesperado no diretorio entregue: so artefato e relatorio."""
    expected = {
        "gcp_scc_findings": {"findings_rows.json"},
        "gcp_flow_logs": {"flow_log_records.json"},
        "gcp_compute_instances": {"instances.json"},
        "gcp_asset_inventory": set(CAI_ARTIFACT_BY_SCOPE.values()),
    }
    for label, directory in surface_dirs.items():
        assert {path.name for path in directory.iterdir()} == expected[label] | {_PROVENANCE_FILE}


@pytest.mark.parametrize("key", sorted(_EXPECTED_COLUMNS))
def test_wire_naming_is_the_specs_own_repeated_fields(surface_dirs: Mapping[str, Path], key: str) -> None:
    """O mapa para a grafia do provedor e derivado da spec, e nao pode fundir dois nomes."""
    spec = _spec(key)
    if key == "cai":
        return  # a superficie tem um mapa por conjunto; conferido abaixo
    provenance = _provenance(surface_dirs, key)
    names = [column.name for column in spec.columns if column.belongs_to_schema]
    expected = {name: name[:-2] for name in names if name.endswith("[]")}
    assert provenance["naming"]["wire_names"] == expected
    assert len(set(expected.values())) == len(expected)


def test_cai_wire_naming_is_per_set(surface_dirs: Mapping[str, Path]) -> None:
    spec = _spec("cai")
    provenance = _provenance(surface_dirs, "cai")
    expected = {
        name: name[:-2]
        for name in _emittable_names(spec, "asset_message")
        if name.endswith("[]")
    }
    assert provenance["naming"]["wire_names"] == expected == {
        "ancestors[]": "ancestors",
        "assetExceptions[]": "assetExceptions",
        "orgPolicy[]": "orgPolicy",
    }


# -- Security Command Center findings -------------------------------------------------


def test_scc_rows_carry_the_documented_paths_and_the_envelope(scc_dir: Path) -> None:
    """A linha traz os 68 caminhos de ``finding.*`` E o envelope da tabela documentada."""
    spec = _spec("scc")
    rows = _records(scc_dir / "findings_rows.json")
    assert rows, "no SCC rows emitted"
    observed = set(columns_of(scc_dir / "findings_rows.json"))
    assert observed == _emittable_names(spec) | set(_SCC_ENVELOPE_EMITTED)
    assert len(observed) == 68 + len(_SCC_ENVELOPE_EMITTED) == 73
    for row in rows:
        assert set(row) == observed
    # O container exigido nao e emitido como chave: ele e representado pelos filhos.
    assert "finding" not in observed


def test_scc_envelope_columns_carry_the_documented_values(scc_dir: Path) -> None:
    """As colunas de envelope que TEM fonte saem com valor; a que nao tem estrutura, vazia.

    ``source_id``, ``finding_id``, ``event_time`` e ``bulk_export_id`` tem fonte; ``resource``
    fica presente e VAZIO (nenhuma pagina publicou a estrutura do objeto Resource).
    """
    rows = _records(scc_dir / "findings_rows.json")
    assert rows
    for row in rows:
        # O id da fonte e o ultimo segmento do nome de fonte documentado, e o nome do achado
        # e composto com ele -- a consistencia e conferida entre os dois, nao contra um literal.
        parent = row["finding.parent"]
        assert parent.startswith("organizations/") and "/sources/" in parent
        assert row["source_id"] == parent.rsplit("/", 1)[-1]
        assert row["finding_id"] and row["finding_id"].isalnum() and len(row["finding_id"]) <= 32
        # A coluna de LINHA segue a forma do unico exemplo publicado para ela
        # (``2019-09-26 12:48:00.985000 UTC`` -- a spec registra que NAO e RFC 3339); o campo
        # do objeto Finding segue RFC 3339, a forma que a declaracao de tipo DELE enuncia.
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6} UTC", row["event_time"])
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", row["finding.eventTime"])
        assert row["bulk_export_id"]
        assert row["resource"] == {}
    # Um achado, um id: o nome, a coluna e a chave de linha usam o MESMO valor.
    nomes = {row["finding.name"].rsplit("/", 1)[-1] for row in rows}
    assert nomes == {row["finding_id"] for row in rows}


def test_scc_table_columns_and_the_required_empty_invariant(scc_dir: Path) -> None:
    """Toda coluna ``required`` da spec tem valor OU esta declarada -- o invariante do auditor.

    Medido com ``populated_paths``, o MESMO leitor que o ``--audit`` usa para contar
    ``obrig.vazias``: assim o numero que o teste prova e o numero que a auditoria imprime.
    """
    spec = _spec("scc")
    provenance = _load_json(scc_dir / _PROVENANCE_FILE)
    assert provenance["mechanism"]["ddl_emitted"] is False
    assert provenance["columns"] == {
        "documented": 74,
        "emitted": 73,
        "without_published_type": 6,
        "container_not_emitted": 1,
    }
    # As seis colunas sem tipo publicado da tabela `findings` estao todas explicadas.
    assert {entry["column"] for entry in provenance["table_columns"]} == set(_SCC_TABLE_COLUMNS)

    populated = set(populated_paths(scc_dir / "findings_rows.json", spec.names))
    vazias = {name for name in spec.required_names if name not in populated}
    assert vazias == _SCC_REQUIRED_EMPTY_DECLARED
    declared = provenance["required_empty_declared"]
    assert {entry["column"] for entry in declared} == _SCC_REQUIRED_EMPTY_DECLARED
    for entry in declared:
        assert "SEM MOTIVO" not in entry["reason"], f"{entry['column']}: obrigatoria vazia sem motivo"
    # O container nao emitido esta declarado e diz quem o representa.
    container = provenance["container_representation"]
    assert container["column"] == "finding"
    assert set(container["represents"]) == {name for name in populated if name.startswith("finding.")}
    assert container["represents"], "o container tem de apontar para os filhos que o representam"


def test_scc_check_artifact_reports_exactly_the_declared_divergences(scc_dir: Path) -> None:
    """O que o nucleo acusa e EXATAMENTE o que a superficie declara -- nem mais, nem menos.

    Depois do envelope, o check nao tem mais ``missing`` (as 4 obrigatorias estao emitidas ou
    representadas) e acusa as 5 colunas de envelope como ``unverified_emitted``: sao colunas
    que a pagina de export publica e cujo TIPO ela nao publica, e o nucleo exige tipo para
    gerar. As duas listas sao derivadas da spec, e o teste falha se aparecer qualquer outra.
    """
    spec = _spec("scc")
    findings = check_artifact(spec, scc_dir / "findings_rows.json")
    nao_comprovadas = {finding.column for finding in findings if finding.kind == KIND_UNVERIFIED}
    ausentes = {finding.column for finding in findings if finding.kind == KIND_MISSING}
    assert nao_comprovadas == set(_SCC_ENVELOPE_EMITTED)
    assert ausentes == _SCC_REQUIRED_EMPTY_DECLARED == {"finding"}
    assert {finding.kind for finding in findings} == {KIND_UNVERIFIED, KIND_MISSING}
    # A superficie continua NAO sendo "fiel" pela regra estrita do nucleo, e isso e o estado
    # declarado: emitir uma coluna que a documentacao exige e cujo tipo ela nao publica.
    assert not is_faithful(findings)
    # Nao e fidelidade plena -- e a lacuna declarada da propria especificacao, e o teste a
    # registra como tal em vez de mascara-la.
    assert not is_faithful(findings)


def test_scc_provenance_records_the_documented_row_identity(
    scc_dir: Path, estate: CanonicalEstate
) -> None:
    """As tres colunas de clustering nao viram coluna, mas a identidade de linha nao se perde."""
    provenance = _load_json(scc_dir / _PROVENANCE_FILE)
    assert tuple(provenance["mechanism"]["clustering"]) == _SCC_CLUSTERING
    rows = _records(scc_dir / "findings_rows.json")
    assert len(provenance["row_keys"]) == len(rows) == provenance["rows"]
    for entry in provenance["row_keys"]:
        assert set(entry) == {"source_id", "finding_id", "event_time", "resource_uuid"}
    names = {row["finding.name"].rsplit("/", 1)[-1] for row in rows}
    assert {entry["finding_id"] for entry in provenance["row_keys"]} == names
    # O instante da chave de clustering e o MESMO que alimenta ``event_time`` (a forma da
    # coluna de linha, que segue o exemplo publicado e nao e RFC 3339).
    modelo = {finding.finding_id.replace("-", ""): finding for finding in _gcp_findings(estate)}
    for entry in provenance["row_keys"]:
        assert entry["event_time"] == _event_time(modelo[entry["finding_id"]].first_observed_at)


def test_scc_text_and_instants_come_from_the_model(scc_dir: Path, estate: CanonicalEstate) -> None:
    """``description`` e os instantes: os campos que o modelo ganhou e o SCC documenta.

    O modelo carrega UM instante (``first_observed_at``) e o SCC publica dois
    (``eventTime``/``createTime``); os dois saem dele, e a coincidencia esta declarada em
    ``value_domains`` -- se o modelo separar deteccao de criacao, este teste muda com ele.
    """
    rows = _records(scc_dir / "findings_rows.json")
    findings = _gcp_findings(estate)
    assert findings and len(rows) == len(findings)
    projected = Counter(
        (row["finding.description"], row["finding.eventTime"], row["finding.createTime"]) for row in rows
    )
    expected = Counter(
        (finding.description, _instant(finding.first_observed_at), _instant(finding.first_observed_at))
        for finding in findings
    )
    assert projected == expected
    assert all(row["finding.description"] for row in rows), "descricao vazia: o modelo carrega uma"
    assert all(row["finding.eventTime"].endswith("Z") for row in rows)


def test_scc_resource_name_comes_from_the_profile_zone(scc_dir: Path, estate: CanonicalEstate) -> None:
    """``finding.resourceName``: a forma completa do recurso, com a zona do perfil.

    Achados cujo recurso nao e uma instancia Compute (GKE, Cloud SQL) nao tem forma citada
    nesta spec, entao ficam vazios: montar uma por analogia seria inventar identidade.
    """
    resources = {r.identity.uuid: r for r in estate.resources}
    profiles = {p.resource_uuid: p for p in estate.instance_profiles if p.provider == "gcp"}
    esperados = {
        # O id do achado na forma documentada (alfanumerico, <= 32) e a chave da comparacao.
        finding.finding_id.replace("-", ""): (
            f"//compute.googleapis.com/projects/{resources[finding.resource_uuid].parent_scope_id}"
            f"/zones/{profiles[finding.resource_uuid].zone}"
            f"/instances/{resources[finding.resource_uuid].resource_name}"
            if profiles.get(finding.resource_uuid) is not None
            and resources[finding.resource_uuid].resource_type == "compute_instance"
            else ""
        )
        for finding in _gcp_findings(estate)
    }
    rows = {
        row["finding_id"]: row["finding.resourceName"] for row in _records(scc_dir / "findings_rows.json")
    }
    assert rows == esperados
    preenchidos = [value for value in rows.values() if value]
    assert 0 < len(preenchidos) < len(rows), "nem todos os achados sao de instancias Compute"


def test_scc_fields_without_a_model_equivalent_stay_empty(scc_dir: Path) -> None:
    """O vocabulario do SCC nao e o do ASFF: sem equivalente no modelo, o campo sai VAZIO.

    ``title``, ``types``, ``confidence``, ``criticality``, ``product_name`` e
    ``company_name`` sao vocabulario do ASFF e nao tem campo no objeto ``Finding`` v1; as
    constantes de enum e ``sourceProperties`` a propria spec registra como nao comprovadas.
    """
    vazios = (
        "finding.state",
        "finding.severity",
        "finding.mute",
        "finding.findingClass",
        "finding.sourceProperties",
        "finding.moduleName",
        "finding.canonicalName",
        "finding.nextSteps",
        "finding.externalUri",
        "finding.externalSystems",
        "finding.securityMarks",
        "finding.mitreAttack",
        "finding.vulnerability",
        "finding.indicator",
        "finding.access",
    )
    for row in _records(scc_dir / "findings_rows.json"):
        for name in vazios:
            assert row[name] in ({}, "", None, []), (name, row[name])


def test_scc_populated_paths_are_reported_and_match_the_core(scc_dir: Path) -> None:
    """A superficie nao e "fiel e vazia": sete caminhos carregam valor, e a proveniencia os relata."""
    path = scc_dir / "findings_rows.json"
    populated = set(populated_of(path))
    assert populated == _SCC_FILLED
    provenance = _load_json(scc_dir / _PROVENANCE_FILE)
    assert set(provenance["populated_paths"]) == populated
    # O relatorio usa a ordem da DOCUMENTACAO; o arquivo entregue esta ordenado por chave.
    assert provenance["populated_paths"] == [name for name in _spec("scc").names if name in populated]
    assert provenance["populated_count"] == len(populated)
    assert provenance["value_domains"]["finding.createTime"]
    assert provenance["open_questions"], "a duvida de vocabulario fica registrada, nao decidida em silencio"


def test_scc_the_container_cannot_be_smuggled_in_as_an_empty_key(scc_dir: Path, tmp_path: Path) -> None:
    """Anti-vacuidade: emitir o container ``finding`` como chave e denunciado pelo nucleo.

    O container e representado pelos filhos; uma chave ``finding`` vazia nao passa como se
    fosse o container (o nucleo a acusa como coluna sem contrato suficiente), e e por isso
    que a representacao por filhos e uma DECISAO declarada, nao um atalho.
    """
    spec = _spec("scc")
    mutated = _mutate(tmp_path, scc_dir / "findings_rows.json", {"finding": {}})
    findings = check_artifact(spec, mutated)
    assert any(finding.kind == KIND_UNVERIFIED and finding.column == "finding" for finding in findings)


def test_scc_a_fabricated_field_is_denounced(scc_dir: Path, tmp_path: Path) -> None:
    spec = _spec("scc")
    mutated = _mutate(tmp_path, scc_dir / "findings_rows.json", {"finding.exploitability": "HIGH"})
    findings = check_artifact(spec, mutated)
    assert any(finding.kind == KIND_INVENTED and finding.column == "finding.exploitability" for finding in findings)


# -- VPC Flow Logs -------------------------------------------------------------------

#: Os caminhos documentados que a projecao do modelo de rede PREENCHE. E uma lista FECHADA
#: de proposito: tudo o que a spec publica e nao esta aqui tem de sair vazio, porque o modelo
#: nao o carrega (RTT, drop_reason, geografia, GKE, PSC, load balancing, zona, ...).
_FLOW_FILLED = frozenset(
    {
        "connection.src_ip",
        "connection.dest_ip",
        "connection.src_port",
        "connection.dest_port",
        "connection.protocol",
        "reporter",
        "connection_direction",
        "start_time",
        "end_time",
        "bytes_sent",
        "packets_sent",
        "disposition",
        "src_instance.project_id",
        "src_instance.region",
        "src_instance.vm_name",
        "dest_instance.project_id",
        "dest_instance.region",
        "dest_instance.vm_name",
        "src_vpc.project_id",
        "src_vpc.vpc_name",
        "src_vpc.subnetwork_name",
        "src_vpc.subnetwork_region",
        "dest_vpc.project_id",
        "dest_vpc.vpc_name",
        "dest_vpc.subnetwork_name",
        "dest_vpc.subnetwork_region",
    }
)


def _instant(moment: datetime | None) -> str:
    """O formato de data RFC 3339 que as tabelas de formato publicam (UTC, Z-normalizado).

    Escrito aqui, no teste, de forma independente do renderer: e a expectativa do formato
    documentado, nao uma copia da implementacao.
    """
    if moment is None:
        return ""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_time(moment: datetime | None) -> str:
    """A forma do UNICO exemplo publicado para a coluna de linha ``event_time``.

    ``2019-09-26 12:48:00.985000 UTC`` -- a spec registra (secao 5) que esse exemplo nao esta
    em RFC 3339, e e a unica evidencia que existe sobre a forma do valor dessa coluna.
    """
    if moment is None:
        return ""
    return f"{moment.astimezone(UTC).strftime('%Y-%m-%d %H:%M:%S.%f')} UTC"


def _gcp_flows(estate: CanonicalEstate) -> list[NetworkFlow]:
    """Os fluxos do estado cujo segmento e GCP (a populacao que a superficie projeta)."""
    gcp = {segment.segment_uuid for segment in estate.network_segments if segment.provider == "gcp"}
    return [flow for flow in estate.network_flows if flow.segment_uuid in gcp]


def _gcp_findings(estate: CanonicalEstate) -> list[NativeFinding]:
    """Os achados nativos GCP, em ordem estavel (a populacao que a superficie SCC projeta)."""
    return sorted(
        (finding for finding in estate.findings if finding.provider == "gcp"),
        key=lambda finding: finding.finding_id,
    )


def test_flow_log_artifact_carries_exactly_the_181_documented_paths(flow_dir: Path) -> None:
    spec = _spec("flow")
    observed = set(columns_of(flow_dir / "flow_log_records.json"))
    assert observed == _emittable_names(spec)
    assert len(observed) == 181
    findings = check_artifact(spec, flow_dir / "flow_log_records.json")
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)


def test_flow_logs_one_record_per_gcp_flow_with_the_models_values(
    flow_dir: Path, estate: CanonicalEstate
) -> None:
    """Um registro por fluxo GCP, e os VALORES sao os do modelo -- nao um formato vazio.

    A comparacao e de MULTICONJUNTO (``Counter``): se o artefato perdesse um fluxo, trocasse
    um valor ou inventasse um fluxo, as duas contagens deixariam de coincidir.
    """
    records = _records(flow_dir / "flow_log_records.json")
    flows = _gcp_flows(estate)
    assert flows, "o estado nao tem fluxo GCP: a superficie voltaria a ser fiel e vazia"
    assert len(records) == len(flows)

    projected = Counter(
        (
            record["connection.src_ip"],
            record["connection.dest_ip"],
            record["connection.src_port"],
            record["connection.dest_port"],
            record["connection.protocol"],
            record["bytes_sent"],
            record["packets_sent"],
            record["start_time"],
            record["end_time"],
        )
        for record in records
    )
    expected = Counter(
        (
            flow.src_ip,
            flow.dst_ip,
            flow.src_port,
            flow.dst_port,
            flow.protocol_number,
            flow.bytes,
            flow.packets,
            _instant(flow.window_start),
            _instant(flow.window_end),
        )
        for flow in flows
    )
    assert projected == expected


def test_flow_logs_published_literals_come_from_the_model(flow_dir: Path, estate: CanonicalEstate) -> None:
    """``reporter``, ``connection_direction`` e ``disposition``: os literais publicados.

    ``disposition`` e o unico que NAO mapeia um-a-um: a tabela de formato publica ``DROPPED``
    e diz que o campo so e populado em registro que captura pacote derrubado -- entao um
    fluxo permitido sai VAZIO, e ``ALLOWED``/``DENIED`` nao sao valores desta documentacao.
    """
    records = _records(flow_dir / "flow_log_records.json")
    flows = _gcp_flows(estate)
    assert Counter(record["reporter"] for record in records) == Counter(flow.reported_by for flow in flows)
    assert Counter(record["connection_direction"] for record in records) == Counter(
        {"ingress": "INGRESS", "egress": "EGRESS"}[flow.direction] for flow in flows
    )
    assert Counter(record["disposition"] for record in records) == Counter(
        "DROPPED" if flow.decision == DECISION_DENIED else "" for flow in flows
    )
    # A conversao nao e vazia em nenhum dos dois lados: ha fluxo permitido e fluxo derrubado.
    assert {flow.decision for flow in flows} == {"allowed", DECISION_DENIED}
    assert {"DROPPED", ""} == {record["disposition"] for record in records}


def test_flow_logs_endpoint_details_come_from_the_interface_and_its_segment(
    flow_dir: Path, estate: CanonicalEstate
) -> None:
    """``*_vpc`` / ``*_instance`` saem da interface do endereco, do segmento e do recurso."""
    interfaces = {interface.private_ip: interface for interface in estate.network_interfaces}
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    records = _records(flow_dir / "flow_log_records.json")
    seen_vm = 0
    for record in records:
        for prefix in ("src", "dest"):
            interface = interfaces.get(record[f"connection.{prefix}_ip"])
            if interface is None:
                # ponta fora do estado: a documentacao so popula os detalhes de quem esta
                # numa VPC, entao nada pode ter sido preenchido.
                for name in _FLOW_FILLED:
                    if name.startswith(f"{prefix}_"):
                        assert record[name] in ({}, "", None, []), (name, record[name])
                continue
            segment = segments[interface.segment_uuid]
            assert record[f"{prefix}_vpc.project_id"] == segment.scope_id
            assert record[f"{prefix}_vpc.vpc_name"] == segment.name
            assert record[f"{prefix}_vpc.subnetwork_name"] == segment.subnet_id.rpartition("/")[2]
            assert record[f"{prefix}_vpc.subnetwork_region"] == segment.region_id
            resource = resources[interface.resource_uuid]
            if resource.resource_type == "compute_instance":
                seen_vm += 1
                assert record[f"{prefix}_instance.project_id"] == resource.parent_scope_id
                assert record[f"{prefix}_instance.region"] == interface.region_id
                assert record[f"{prefix}_instance.vm_name"] == resource.resource_name
            else:
                # GKE/Cloud SQL tem interface, mas nao sao "the VM instance details".
                assert record[f"{prefix}_instance.vm_name"] == ""
                assert record[f"{prefix}_instance.project_id"] == ""
    assert seen_vm > 0, "nenhum fluxo GCP toca uma instancia Compute: a projecao nao seria provada"


def test_flow_logs_the_required_empty_invariant_is_declared(
    flow_dir: Path, estate: CanonicalEstate
) -> None:
    """Toda coluna ``required`` da spec de rede tem valor OU esta declarada com motivo.

    Medido com ``populated_paths`` -- o mesmo leitor que o ``--audit`` usa para
    ``obrig.vazias``: o container ``connection`` (representado pelos filhos achatados) e os
    campos que o modelo de rede nao carrega. Se um deles passar a ter valor, o teste acusa o
    relatorio desatualizado; se a spec ganhar uma obrigatoria nova sem fonte, ela aparece sem
    motivo declarado e o teste falha.
    """
    spec = _spec("flow")
    populated = set(populated_paths(flow_dir / "flow_log_records.json", spec.names))
    vazias = {name for name in spec.required_names if name not in populated}
    assert vazias == _FLOW_REQUIRED_EMPTY_DECLARED
    provenance = _load_json(flow_dir / _PROVENANCE_FILE)
    declared = provenance["required_empty_declared"]
    assert {entry["column"] for entry in declared} == vazias
    for entry in declared:
        assert "SEM MOTIVO" not in entry["reason"], f"{entry['column']}: obrigatoria vazia sem motivo"
    container = provenance["container_representation"]
    assert container["column"] == "connection"
    assert set(container["represents"]) == {name for name in populated if name.startswith("connection.")}
    assert len(_gcp_flows(estate)) > 0


def test_flow_logs_populate_exactly_the_projected_paths_and_report_them(
    flow_dir: Path, estate: CanonicalEstate
) -> None:
    """A superficie deixou de ser "fiel e vazia": 26 caminhos carregam valor, e sao esses.

    O conjunto e comparado com o que o PROPRIO nucleo mede no arquivo entregue
    (``populated_of``), e o relatorio de proveniencia tem de contar a mesma coisa -- o
    ``records: 0`` honesto de antes nao pode reaparecer em silencio.
    """
    path = flow_dir / "flow_log_records.json"
    populated = set(populated_of(path))
    assert populated == _FLOW_FILLED
    assert len(populated) == 26
    provenance = _load_json(flow_dir / _PROVENANCE_FILE)
    assert provenance["records"] == len(_gcp_flows(estate)) > 0
    # O relatorio lista os caminhos na ORDEM DA DOCUMENTACAO (a ordem da spec); o arquivo
    # entregue esta ordenado por chave. Mesmos nomes, dois eixos de ordem diferentes.
    assert set(provenance["populated_paths"]) == populated
    assert provenance["populated_paths"] == [name for name in _spec("flow").names if name in populated]
    assert provenance["populated_count"] == len(populated)
    assert provenance["record_format"]["emitted_paths"] == 181
    assert provenance["model_gaps"], "as lacunas que sobram continuam registradas"
    # Um campo que o modelo nao carrega continua vazio, e nao "plausivel".
    record = _records(path)[0]
    for name in ("drop_reason", "bytes_dropped", "packets_dropped", "throughput_inclusion", "rtt_msec"):
        assert record[name] in ("", None), (name, record[name])
    assert record["round_trip_time"] == {}


def test_flow_logs_report_the_model_divergence_they_cannot_fix(
    flow_dir: Path, estate: CanonicalEstate
) -> None:
    """O modelo NAO tem mais divergencia de regiao -- e o relatorio tem de concordar.

    Antes havia UMA sub-rede por segmento e interfaces de varias regioes, e o renderer
    relatava o numero de pontas em que as duas leituras discordavam. O modelo passou a
    ter segmento por (escopo, regiao), entao a divergencia medida e ZERO. O teste
    continua nos dois sentidos: exige que a contagem medida seja zero E que o
    relatorio nao afirme divergencia que o estado nao tem -- uma divergencia nova,
    se voltar, aparece aqui.
    """
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
    expected = 0
    for flow in _gcp_flows(estate):
        for interface_uuid in (flow.src_interface_uuid, flow.dst_interface_uuid):
            interface = interfaces.get(interface_uuid or "")
            if interface is None:
                continue
            if interface.region_id != segments[interface.segment_uuid].region_id:
                expected += 1

    assert expected == 0, "toda interface tem de estar na regiao do seu segmento"
    divergence = _load_json(flow_dir / _PROVENANCE_FILE)["model_divergences"]
    relatado = {entry["item"]: entry["count"] for entry in divergence}
    assert relatado.get("regiao da sub-rede vs regiao da interface", 0) == expected


def test_flow_logs_do_not_claim_a_bigquery_export(flow_dir: Path) -> None:
    """O destino documentado e o Cloud Logging; nenhum artefato afirma uma tabela BigQuery."""
    provenance = _load_json(flow_dir / _PROVENANCE_FILE)
    mechanism = provenance["mechanism"]
    assert mechanism["destination"] == "Cloud Logging"
    assert mechanism["direct_bigquery_export"] is False
    assert mechanism["file_format"] is None
    for path in flow_dir.iterdir():
        assert "bigquery" not in path.name.lower()


def test_flow_logs_a_fabricated_field_is_denounced(flow_dir: Path, tmp_path: Path) -> None:
    spec = _spec("flow")
    mutated = _mutate(tmp_path, flow_dir / "flow_log_records.json", {"src_vpc.vpc_id": "vpc-1"})
    findings = check_artifact(spec, mutated)
    assert any(finding.kind == KIND_INVENTED and finding.column == "src_vpc.vpc_id" for finding in findings)


# -- Cloud Asset Inventory: ExportAssets -------------------------------------------


def test_cai_every_set_is_projected(cai_dir: Path) -> None:
    spec = _spec("cai")
    total = 0
    for scope in _CAI_SCOPES:
        names = columns_of(cai_dir / CAI_ARTIFACT_BY_SCOPE[scope])
        assert set(names) == _emittable_names(spec, scope), scope
        total += len(names)
    # A soma e a contagem de COLUNAS da spec (o mesmo nome em conjuntos diferentes e uma
    # coluna de cada conjunto -- 'sets' existe exatamente para isso).
    assert total == spec.emittable_count == 89


def test_cai_assets_ndjson_is_one_documented_asset_per_line(cai_dir: Path) -> None:
    """O formato entregue ao Cloud Storage: NDJSON, um Asset por linha."""
    spec = _spec("cai")
    path = cai_dir / "assets.ndjson"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "no Asset lines emitted"
    expected = _emittable_names(spec, "asset_message")
    for line in lines:
        payload = json.loads(line)
        assert set(payload) == expected
        assert "relatedAssets" not in payload, "campo DEPRECATED nao pode ser emitido"
        assert "accessLevel" in payload, "o registro carrega o conjunto documentado inteiro"
    assets = [json.loads(line) for line in lines]
    assert {asset["assetType"] for asset in assets} == {_CAI_ASSET_TYPE}
    assert len(assets) == len(_records(cai_dir / "resource_schema_rows.json"))


def test_cai_resource_data_is_never_filled(cai_dir: Path, estate: CanonicalEstate) -> None:
    """``resource.data`` e UNVERIFIED na spec: fica vazio, mesmo o modelo tendo os campos.

    O perfil de instancia carrega a maquina, mas a spec afirma que a forma de
    ``resource.data`` para ``compute.googleapis.com/Instance`` nao e publicada e que a
    correspondencia com a representacao REST de Instances nao e afirmada em pagina nenhuma;
    projetar a forma REST ali seria afirmar exatamente essa correspondencia.
    """
    profiles = {p.resource_uuid: p for p in estate.instance_profiles if p.provider == "gcp"}
    resources = {r.identity.uuid: r for r in estate.resources}
    assets = _records(cai_dir / "assets.ndjson")
    assert assets
    for asset in assets:
        assert asset["resource"]["data"] == {}, "resource.data preenchido sem schema publicado"
        # A localizacao e a ZONA do perfil (a tabela publicada diz "zona/regiao").
        assert asset["resource"]["location"].count("-") == 2, asset["resource"]["location"]
        # O nome do asset usa a MESMA forma que a descricao do campo publica.
        assert asset["name"].startswith("//compute.googleapis.com/projects/")
        assert "/zones/" in asset["name"] and "/instances/" in asset["name"]

    # Todo asset tem nome, e ele e o do recurso que o perfil descreve (mesma forma).
    nomes = {asset["name"] for asset in assets}
    esperados = {
        f"//compute.googleapis.com/projects/{resources[p.resource_uuid].parent_scope_id}"
        f"/zones/{p.zone}/instances/{resources[p.resource_uuid].resource_name}"
        for p in profiles.values()
        if p.zone and resources[p.resource_uuid].resource_type == "compute_instance"
    }
    assert nomes == esperados

    # ``resource_schema.name`` corresponde a ``Asset.name`` (e a coluna ``resource.data``
    # continua vazia: ela e uma STRING com o JSON do recurso, cuja forma nao foi publicada).
    for row in _records(cai_dir / "resource_schema_rows.json"):
        assert row["resource.data"] == ""
        assert row["name"] in nomes
        assert row["resource.location"] in {p.zone for p in profiles.values()}


def test_cai_ancestors_come_from_the_estate_hierarchy(cai_dir: Path, estate: CanonicalEstate) -> None:
    """``ancestors`` e projetado da hierarquia real do estado, na forma publicada."""
    projects = {
        project.project_id: (folder.folder_id, org.org_id)
        for org in estate.gcp_orgs
        for folder in org.folders
        for project in folder.projects
    }
    assets = _records(cai_dir / "assets.ndjson")
    assert assets
    for asset in assets:
        ancestors = asset["ancestors[]"]
        assert ancestors, "ancestors vazio"
        project = ancestors[0].removeprefix("projects/")
        folder_id, org_id = projects[project]
        assert ancestors == [f"projects/{project}", folder_id, org_id]


def test_cai_export_request_and_destinations_are_the_documented_shapes(cai_dir: Path) -> None:
    spec = _spec("cai")
    request = _load_json(cai_dir / CAI_ARTIFACT_BY_SCOPE["export_request"])
    assert request["contentType"] == "RESOURCE"
    assert request["assetTypes[]"] == [_CAI_ASSET_TYPE]
    assert request["readTime"].endswith("Z")
    assert request["outputConfig"]["gcsDestination"]["uriPrefix"].startswith("gs://")
    gcs = _load_json(cai_dir / CAI_ARTIFACT_BY_SCOPE["gcs_destination"])
    assert gcs["uri"] == "" and gcs["uriPrefix"].startswith("gs://")
    bq = _load_json(cai_dir / CAI_ARTIFACT_BY_SCOPE["bigquery_destination"])
    assert bq["dataset"].startswith("projects/") and "/datasets/" in bq["dataset"]
    # O container fica no seu vazio e o subcampo documentado e irmao plano (o nivel que a
    # spec escreve); o valor publicado da enumeracao vive no caminho, nao no container.
    assert bq["partitionSpec"] == {}
    assert bq["partitionSpec.partitionKey"] == "READ_TIME"
    assert bq["separateTablesPerAssetType"] is True
    extra = _load_json(cai_dir / CAI_ARTIFACT_BY_SCOPE["partition_extra_column"])
    assert extra["readTime"] == request["readTime"] == extra["requestTime"]
    assert gcs["uriPrefix"] == request["outputConfig"]["gcsDestination"]["uriPrefix"]
    findings = check_artifact(
        spec, cai_dir / CAI_ARTIFACT_BY_SCOPE["bigquery_destination"], scope="bigquery_destination"
    )
    assert is_faithful(findings)


def test_cai_a_deprecated_field_cannot_be_emitted(cai_dir: Path, tmp_path: Path) -> None:
    """Anti-vacuidade: ``relatedAssets`` e DEPRECATED e nao pode aparecer no artefato."""
    spec = _spec("cai")
    lines = [line for line in (cai_dir / "assets.ndjson").read_text(encoding="utf-8").splitlines() if line.strip()]
    asset = {**json.loads(lines[0]), "relatedAssets": {}}
    target = tmp_path / "mutated.ndjson"
    target.write_text("\n".join([json.dumps(asset), *lines[1:]]) + "\n", encoding="utf-8")
    findings = check_artifact(spec, target, scope="asset_message")
    assert any(finding.kind == KIND_UNVERIFIED and finding.column == "relatedAssets" for finding in findings)


def test_cai_a_fabricated_column_is_denounced(cai_dir: Path, tmp_path: Path) -> None:
    spec = _spec("cai")
    mutated = _mutate(tmp_path, cai_dir / CAI_ARTIFACT_BY_SCOPE["resource_schema"], {"resource.iam_policy": {}})
    findings = check_artifact(spec, mutated, scope="resource_schema")
    assert any(finding.kind == KIND_INVENTED and finding.column == "resource.iam_policy" for finding in findings)


def test_cai_scope_is_required_because_the_surface_has_ten_sets(cai_dir: Path) -> None:
    """Conferir a superficie multiconjunto sem ``scope`` seria comparar contra a uniao."""
    spec = _spec("cai")
    with pytest.raises(ScopeError, match="scope"):
        check_artifact(spec, cai_dir / CAI_ARTIFACT_BY_SCOPE["resource_schema"])


# -- Compute Engine Instances (REST representation) ---------------------------------


def test_instances_records_are_the_documented_representation(instances_dir: Path, estate: CanonicalEstate) -> None:
    """O registro: 48 campos documentados, sem envelope ``InstanceList``."""
    spec = _spec("instances")
    records = _records(instances_dir / "instances.json")
    assert records, "no instances emitted"
    expected = _emittable_names(spec)
    for record in records:
        assert set(record) == expected
        assert record["kind"] == "compute#instance"
        assert record["name"]
        assert record["labels"] and all(isinstance(key, str) for key in record["labels"])
        assert record["networkInterfaces[]"] == [] and record["disks[]"] == []
    assert not (set(records[0]) & {"items", "nextPageToken", "warning"}), "InstanceList nao pertence a esta spec"
    names = {record["name"] for record in records}
    expected_names = {
        r.resource_name
        for r in estate.resources
        if r.identity.provider == "gcp" and r.resource_type == "compute_instance"
    }
    assert names == expected_names


def test_instances_model_gaps_are_reported(instances_dir: Path, estate: CanonicalEstate) -> None:
    """O que o modelo nao cobre -- e o que a SPEC nao transcreve -- e registrado."""
    provenance = _load_json(instances_dir / _PROVENANCE_FILE)
    assert provenance["mechanism"]["is_export"] is False
    assert provenance["columns"] == {
        "documented": 48,
        "emitted_per_instance": 48,
        "required": [],
        "not_generated": [],
    }
    gaps = {entry["item"] for entry in provenance["model_gaps"]}
    assert {"enderecos de rede da instancia", "disco raiz", "imagem"} <= gaps
    assert provenance["open_questions"], "a coincidencia de 'last start' fica como pergunta, nao como valor"
    records = _records(instances_dir / "instances.json")
    models = sorted(
        (r for r in estate.resources if r.identity.provider == "gcp" and r.resource_type == "compute_instance"),
        key=lambda r: r.identity.uuid,
    )
    assert len(records) == len(models) == provenance["instances"]
    profiles = {p.resource_uuid: p for p in estate.instance_profiles if p.provider == "gcp"}
    for record, resource in zip(records, models, strict=True):
        profile = profiles[resource.identity.uuid]
        assert record["name"] == resource.resource_name
        assert record["labels"] == dict(resource.tags)
        # O perfil de instancia e a fonte: id uint64, zona, tipo de maquina, estado e criacao.
        assert record["id"] == profile.native_id
        assert record["zone"] == f"zones/{profile.zone}"
        assert record["machineType"] == f"zones/{profile.zone}/machineTypes/{profile.instance_type}"
        assert record["status"] == {"running": "RUNNING", "stopped": "TERMINATED"}[profile.state]
        assert record["creationTimestamp"] == _instant(profile.launch_time)
        # O que a spec nao transcreve continua vazio, mesmo o perfil carregando o valor.
        assert record["networkInterfaces[]"] == [] and record["disks[]"] == []
        assert record["lastStartTimestamp"] == "" and record["selfLink"] == ""


def test_instances_populated_paths_are_reported_and_match_the_core(
    instances_dir: Path, estate: CanonicalEstate
) -> None:
    """De 3 para 8 caminhos preenchidos: a proveniencia relata o mesmo que o nucleo mede."""
    path = instances_dir / "instances.json"
    populated = set(populated_of(path))
    assert populated == _INSTANCES_FILLED
    assert {"kind", "name", "labels"} < populated, "o perfil de instancia passou a alimentar a superficie"
    provenance = _load_json(instances_dir / _PROVENANCE_FILE)
    assert set(provenance["populated_paths"]) == populated
    assert provenance["populated_paths"] == [name for name in _spec("instances").names if name in populated]
    assert provenance["populated_count"] == len(populated)
    esperado = sum(
        1 for r in estate.resources if r.identity.provider == "gcp" and r.resource_type == "compute_instance"
    )
    assert provenance["instances"] == esperado > 0


def test_instances_a_fabricated_field_is_denounced(instances_dir: Path, tmp_path: Path) -> None:
    spec = _spec("instances")
    mutated = _mutate(tmp_path, instances_dir / "instances.json", {"machineTypeFamily": "e2"})
    findings = check_artifact(spec, mutated)
    assert any(finding.kind == KIND_INVENTED and finding.column == "machineTypeFamily" for finding in findings)
    assert is_faithful(check_artifact(spec, instances_dir / "instances.json"))
