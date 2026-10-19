"""As superficies AWS de seguranca, rede e instancias: fidelidade provada por artefato.

Quatro superficies, quatro renderers, e a mesma regra em todas: o que e conferido e o
ARQUIVO QUE FOI ESCRITO, lido por ``fidelity.artifacts.columns_of``/``populated_of`` e
comparado com a especificacao citada por ``fidelity.checker.check_artifact`` -- nunca a
lista de colunas que o renderer tem em memoria. Uma coluna fora da spec, uma coluna
obrigatoria ausente e um valor inventado numa coluna sem fonte no modelo reprovam aqui.

O ``scope`` e obrigatorio nas tres superficies com mais de um conjunto nomeado (AWS
Config: 4; Security Hub: 3; EC2: 4) e ausente na unica plana (VPC Flow Logs), que e
exatamente o que ``checker._resolve_columns`` exige.

O que cada superficie prova, e como:

* **``vpc_flow_logs``** -- o objeto Parquet carrega as 54 colunas documentadas e o objeto
  de texto carrega os mesmos valores na MESMA ordem, com o marcador ``-`` documentado nas
  posicoes ausentes. O formato texto nao tem cabecalho (a documentacao nao menciona
  nenhum), entao os NOMES das colunas nao existem no arquivo de texto: o contrato de nome
  e conferido no Parquet da mesma janela, e o texto e conferido posicionalmente contra a
  ordem documentada. Os campos preenchidos sao RECONSTRUIDOS aqui a partir dos FLUXOS do
  modelo (``estate.network_flows``) e comparados como MULTICONJUNTO com as linhas do
  artefato: o teste exige REGISTRO, nao so o conjunto de colunas -- uma superficie "fiel e
  vazia" reprova.
* **``aws_config_snapshot``** -- o objeto entregue (``.json.gz``, caminho e nome
  documentados), o payload da notificacao SNS, a extracao VERBATIM dos configuration items
  e a fixture de forma do conjunto ``relationship`` (que o modelo nao alimenta: o teste
  exige que ela siga vazia e que as ``relationships`` entregues sejam arrays vazios).
* **``security_hub``** -- os 46 atributos de topo, os 12 de ``Resources[]`` e os 38
  caminhos aninhados; ``resources.json`` e ``nested.json`` sao RECONSTRUIDOS aqui a partir
  de ``findings.json``, com um caminhador escrito neste arquivo, para provar que sao
  projecoes do documento e nao uma segunda geracao.
* **``ec2_instances``** -- os 61 membros do objeto ``Instance``, os 5 de ``Reservation``,
  os 3 do envelope e os 6 parametros de requisicao; os fixtures sao JSON por decisao
  registrada (a API publica XML, e o nucleo de fidelidade le Parquet/CSV/JSON).

O estado e construido uma vez por modulo: cada build leva ~15 s e os renderers sao puros.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import check_artifact, is_faithful, load_spec
from tools.synthetic_clouds.fidelity.artifacts import columns_of, populated_of
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.estate_builder import (
    FLOW_WINDOW_MINUTES,
    FLOW_WINDOWS,
    build_estate,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import AWS_ID_PREFIXES, aws_resource_id
from tools.synthetic_clouds.model.network import NetworkFlow, NetworkInterface, NetworkSegment
from tools.synthetic_clouds.render import aws_config_snapshot, ec2_instances, security_hub, vpc_flow_logs
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.markers import unmarked_name

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPECS = _REPO_ROOT / "specs" / "aws"

_VPC_SPEC = _SPECS / "vpc-flow-logs-s3.schema.json"
_CONFIG_SPEC = _SPECS / "aws-config-snapshot-s3.schema.json"
_HUB_SPEC = _SPECS / "security-hub-asff.schema.json"
_EC2_SPEC = _SPECS / "ec2-describe-instances.schema.json"

# The ASFF `Severity.Label` enum and the `Normalized` value AWS publishes for each label, both
# read from `API_Severity.html` on 2026-10-15. Copied here so the test confronts the artifact
# against the documented table rather than against the renderer, which would repeat its own
# error. `Normalized` is what Security Hub itself writes when a provider sends only `Label`.
_ASFF_SEVERITY_LABEL = {"INFORMATIONAL", "LOW", "MEDIUM", "HIGH", "CRITICAL"}
_ASFF_SEVERITY_NORMALIZED = {"INFORMATIONAL": 0, "LOW": 1, "MEDIUM": 40, "HIGH": 70, "CRITICAL": 90}

# The five keys the renderer carries in the ASFF's free-form ``UserDefinedFields``. Four of them
# are the NOT NULL columns the consumer needs and the ASFF message cannot model; the fifth is
# the native category, which travels under the consumer's name. The set is exact on purpose: a
# free-form map would accept anything, and that is where an invented value would slip in.
_ASFF_INGEST_FIELDS = {"category", "evidence", "exposure", "impact", "fingerprint"}

# The documented file-name templates, as regular expressions. `fl-` + 17 hex is the
# documented flow-log id shape this package derives (see the renderer's docstring).
_VPC_NAME_RE = re.compile(
    r"^(?P<account>\d{12})_vpcflowlogs_(?P<region>[a-z0-9-]+)_(?P<flow_log>fl-[0-9a-f]{17})_"
    r"(?P<stamp>\d{8}T\d{4})Z_(?P<digest>[0-9a-f]{8})(?P<ext>\.log\.gz|\.parquet)$"
)
_VPC_PATH_RE = re.compile(
    r"^vpc-flow-logs/AWSLogs/(?P<account>\d{12})/vpcflowlogs/(?P<region>[a-z0-9-]+)/"
    r"(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/"
)
_CONFIG_NAME_RE = re.compile(
    r"^(?P<account>\d{12})_Config_(?P<region>[a-z0-9-]+)_ConfigSnapshot_"
    r"(?P<stamp>\d{8}T\d{6})Z_(?P<snapshot>[0-9a-f-]{36})\.json\.gz$"
)
_CONFIG_PATH_RE = re.compile(
    r"^AWSLogs/(?P<account>\d{12})/Config/(?P<region>[a-z0-9-]+)/"
    r"(?P<year>\d{4})/(?P<month>\d{1,2})/(?P<day>\d{1,2})/ConfigSnapshot/"
)


# ── the estate and the rendered trees ────────────────────────────────────────


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The base small estate (seed 123): the resources and findings every surface projects."""
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def vpc_tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    written = vpc_flow_logs.VpcFlowLogsRenderer().render(estate, tmp_path_factory.mktemp("vpc"))
    assert written
    return written


@pytest.fixture(scope="module")
def config_tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    written = aws_config_snapshot.AwsConfigSnapshotRenderer().render(estate, tmp_path_factory.mktemp("config"))
    assert written
    return written


@pytest.fixture(scope="module")
def hub_tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    written = security_hub.SecurityHubAsffRenderer().render(estate, tmp_path_factory.mktemp("hub"))
    assert written
    return written


@pytest.fixture(scope="module")
def ec2_tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    written = ec2_instances.Ec2InstancesRenderer().render(estate, tmp_path_factory.mktemp("ec2"))
    assert written
    return written


def _emittable(spec: Any, scope: str) -> set[str]:
    """Os nomes que o conjunto ``scope`` autoriza a EXISTIR no artefato."""
    return {column.name for column in spec.columns_for(scope) if column.belongs_to_schema}


def _assert_faithful(spec: Any, path: Path, scope: str | None = None) -> tuple[str, ...]:
    """Confere nomes E valores do arquivo real; devolve os nomes observados."""
    findings = check_artifact(spec, path, scope=scope)
    assert is_faithful(findings), f"{path}: " + " | ".join(str(finding) for finding in findings)
    observed = columns_of(path)
    assert observed, f"{path}: nenhum campo lido"
    allowed = _emittable(spec, scope) if scope else set(spec.emittable_names)
    assert set(observed) <= allowed, f"{path}: campo emitido fora do conjunto documentado"
    return observed


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_gz(path: Path) -> Any:
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def _aws_resources(estate: CanonicalEstate, resource_type: str | None = None) -> list[Any]:
    return sorted(
        (
            resource
            for resource in estate.resources
            if resource.identity.provider == const.PROVIDER_KEY_AWS
            and (resource_type is None or resource.resource_type == resource_type)
        ),
        key=lambda resource: resource.identity.logical_path,
    )


def _aws_network(
    estate: CanonicalEstate,
) -> tuple[dict[str, NetworkSegment], list[NetworkInterface], list[NetworkFlow]]:
    """O recorte AWS do modelo de rede: segmentos, interfaces e fluxos."""
    segments = {s.segment_uuid: s for s in estate.network_segments if s.provider == const.PROVIDER_KEY_AWS}
    interfaces = [i for i in estate.network_interfaces if i.segment_uuid in segments]
    flows = [f for f in estate.network_flows if f.segment_uuid in segments]
    return segments, interfaces, flows


def _network_lookups(
    estate: CanonicalEstate,
) -> tuple[dict[str, NetworkSegment], dict[str, NetworkInterface], dict[str, Any]]:
    """Os referentes que um fluxo nomeia por FK: segmento, interface e recurso."""
    segments = {s.segment_uuid: s for s in estate.network_segments}
    interfaces_by_id = {i.interface_id: i for i in estate.network_interfaces}
    resources = {r.identity.uuid: r for r in estate.resources}
    return segments, interfaces_by_id, resources


#: Os campos do registro que carregam VALOR de um fluxo do modelo, na ordem em que o teste
#: os reconstroi. ``version`` e o ``log-status`` ficam de fora: um e derivado do formato, o
#: outro e o literal documentado de um intervalo com trafego.
_VPC_FLOW_FIELDS: tuple[str, ...] = (
    "account-id",
    "interface-id",
    "srcaddr",
    "dstaddr",
    "srcport",
    "dstport",
    "protocol",
    "packets",
    "bytes",
    "start",
    "end",
    "action",
    "vpc-id",
    "subnet-id",
    "region",
    "instance-id",
    "flow-direction",
)


def _expected_flow_values(
    flow: NetworkFlow,
    segments: dict[str, NetworkSegment],
    interfaces_by_id: dict[str, NetworkInterface],
    resources: dict[str, Any],
) -> tuple[Any, ...]:
    """Reconstroi AQUI, a partir do modelo, o valor de cada campo projetado de ``flow``.

    Nada e lido do renderer: a interface que registrou o trafego vem de
    ``log_resource_id``, a regiao da interface, o ``instance-id`` do dono dela quando ele e
    uma instancia EC2, e a acao do dominio documentado.
    """
    segment = segments[flow.segment_uuid]
    interface = interfaces_by_id.get(flow.log_resource_id)
    region = interface.region_id if interface is not None else segment.region_id
    instance_id = None
    if interface is not None:
        owner = resources[interface.resource_uuid]
        if owner.resource_type == "ec2_instance":
            instance_id = aws_resource_id(owner.resource_type, owner.identity.uuid)
    action = {"allowed": "ACCEPT", "denied": "REJECT"}[flow.decision]
    return (
        flow.account_id,
        flow.log_resource_id,
        flow.src_ip,
        flow.dst_ip,
        flow.src_port,
        flow.dst_port,
        flow.protocol_number,
        flow.packets,
        flow.bytes,
        int(flow.window_start.timestamp()),
        int(flow.window_end.timestamp()),
        action,
        segment.segment_id,
        segment.subnet_id,
        region,
        instance_id,
        flow.direction,
    )


def _row_values(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row[name] for name in _VPC_FLOW_FIELDS)


# ═══════════════════════════════════════════════════════════════════════════════
# VPC Flow Logs -- a superficie plana (54 campos, sem conjuntos nomeados)
# ═══════════════════════════════════════════════════════════════════════════════


def test_vpc_spec_declares_the_54_published_fields() -> None:
    spec = load_spec(_VPC_SPEC)
    assert spec.surface == vpc_flow_logs.SURFACE == "aws/vpc-flow-logs-s3"
    assert len(spec.columns) == 54, f"spec declares {len(spec.columns)} fields, expected 54"
    assert spec.emittable_count == 54, "every published field belongs to the record"
    assert not spec.set_names, "this surface has a single anonymous set; scope= is not used"
    assert spec.delivery["absent_value_marker"] == "-"


def test_vpc_column_list_is_derived_from_the_spec() -> None:
    """``_COLUMNS`` IS the spec's emittable set, in the documentation's order."""
    spec = load_spec(_VPC_SPEC)
    assert vpc_flow_logs._COLUMNS == spec.names, "the emitted order is the documentation's order"
    assert set(vpc_flow_logs._COLUMNS) == spec.emittable_names
    assert len(set(vpc_flow_logs._COLUMNS)) == 54
    assert set(vpc_flow_logs._COLUMNS) & spec.forbidden_names == set()


def test_vpc_parquet_artifact_carries_exactly_the_documented_fields(vpc_tree: list[Path]) -> None:
    """O schema do Parquet ENTREGUE e o conjunto de campos da especificacao.

    Em TODOS os objetos: nenhum campo fora da spec, nenhuma coluna obrigatoria ausente
    (``check_artifact`` confere nomes e valores). O conjunto EXATO das 54 colunas e conferido
    numa amostra deterministica, porque o produtor do registro e UM caminho de codigo e a
    derivacao de ``_COLUMNS`` a partir da spec e asserida em separado.
    """
    spec = load_spec(_VPC_SPEC)
    parts = [path for path in vpc_tree if path.suffix == ".parquet"]
    assert parts, "expected Parquet objects"
    for part in parts:
        findings = check_artifact(spec, part)
        assert is_faithful(findings), f"{part}: " + " | ".join(str(finding) for finding in findings)
    for part in parts[::97]:
        observed = columns_of(part)
        assert set(observed) == spec.emittable_names, f"{part.name}: conjunto de campos divergente"
        assert len(observed) == 54, f"{part.name} carries {len(observed)} fields"


def test_vpc_text_artifact_carries_the_same_records_in_the_documented_order(vpc_tree: list[Path]) -> None:
    """O objeto de TEXTO entrega os mesmos valores, na ordem documentada, com ``-`` no ausente.

    O formato texto nao tem cabecalho (a documentacao nao menciona nenhum), entao os nomes
    dos campos nao existem no arquivo: o que se prova aqui e a POSICAO -- 54 tokens por
    registro, na ordem da spec -- e, numa amostra deterministica, o VALOR de cada posicao
    contra o objeto Parquet da MESMA janela de agregacao.
    """
    import pyarrow.parquet as pq

    spec = load_spec(_VPC_SPEC)
    texts = [path for path in vpc_tree if path.suffix == ".gz"]
    assert texts, "expected text objects"
    assert len(texts) == len([path for path in vpc_tree if path.suffix == ".parquet"])
    for index, text in enumerate(texts):
        parquet = text.with_name(text.name[: -len(".log.gz")] + ".parquet")
        assert parquet.exists(), f"{text.name} has no Parquet twin"
        lines = gzip.decompress(text.read_bytes()).decode("utf-8").splitlines()
        assert lines, f"{text.name}: um objeto da entrega nao pode vir vazio"
        assert len(lines) == pq.read_metadata(parquet).num_rows, f"{text.name}: linhas != registros"
        tokens = [line.split(" ") for line in lines]
        assert all(len(row) == 54 for row in tokens), f"{text.name}: um registro sem 54 campos"
        assert any(token != vpc_flow_logs.ABSENT_MARKER for row in tokens for token in row), (
            f"{text.name}: registro so com ausencia"
        )
        if index % 12:
            continue
        rows = pq.read_table(parquet).to_pylist()
        for row_tokens, row in zip(tokens, rows, strict=True):
            for position, name in enumerate(spec.names):
                value = row[name]
                expected = vpc_flow_logs.ABSENT_MARKER if value is None else str(value)
                assert row_tokens[position] == expected, f"{text.name}: campo {name} na posicao {position}"


def test_vpc_path_and_file_name_match_the_documented_templates(vpc_tree: list[Path]) -> None:
    for path in vpc_tree:
        relative = path.as_posix().split(f"{vpc_flow_logs.RENDER_DIR}/", 1)[1]
        path_match = _VPC_PATH_RE.match(relative)
        assert path_match, f"caminho fora do template documentado: {relative}"
        name_match = _VPC_NAME_RE.match(path.name)
        assert name_match, f"nome fora do template documentado: {path.name}"
        assert name_match.group("account") == path_match.group("account")
        assert name_match.group("region") == path_match.group("region")
        window = datetime.strptime(name_match.group("stamp"), "%Y%m%dT%H%M").replace(tzinfo=UTC)
        assert (str(window.year), f"{window.month:02d}", f"{window.day:02d}") == (
            path_match.group("year"),
            path_match.group("month"),
            path_match.group("day"),
        ), f"{relative}: a data do caminho nao e a da janela do nome"


def test_vpc_artifact_has_records_and_every_one_is_a_model_flow(
    vpc_tree: list[Path], estate: CanonicalEstate
) -> None:
    """O artefato tem REGISTROS, e cada registro e um fluxo do modelo (multiconjunto).

    Esta e a prova que a superficie nao pode contornar: sem ela, um renderer que emitisse o
    conjunto de colunas com tudo nulo passaria em todas as outras checagens -- foi assim que
    a versao "fiel e vazia" sobreviveu. A comparacao e um MULTICONJUNTO dos campos de valor,
    reconstruidos aqui a partir dos fluxos do modelo, entao nem uma linha a mais nem um
    campo trocado passam.
    """
    import pyarrow.parquet as pq

    segments, interfaces, flows = _aws_network(estate)
    assert segments and flows, "o estate precisa modelar segmentos e fluxos AWS"
    expected_lookups = _network_lookups(estate)
    rows = [
        row
        for part in (path for path in vpc_tree if path.suffix == ".parquet")
        for row in pq.read_table(part).to_pylist()
    ]
    assert rows, "o artefato nao tem nenhum registro"
    assert len(rows) == len(flows), f"{len(rows)} registros para {len(flows)} fluxos modelados"
    assert Counter(_row_values(row) for row in rows) == Counter(
        _expected_flow_values(flow, *expected_lookups) for flow in flows
    )
    # E o valor veio mesmo do modelo: nenhuma dessas colunas pode ser ausencia disfarcada.
    assert any(row["srcaddr"] != "0.0.0.0" for row in rows)
    assert any(row["packets"] > 0 for row in rows)
    assert any(row["bytes"] > 0 for row in rows)
    assert {row["action"] for row in rows} <= {"ACCEPT", "REJECT"}
    assert {row["action"] for row in rows} == {"ACCEPT", "REJECT"}, "as duas decisoes existem no estate"
    assert {row["flow-direction"] for row in rows} <= {"ingress", "egress"}
    assert {row["protocol"] for row in rows} <= {6, 17, 1}
    assert {row["log-status"] for row in rows} == {"OK"}
    assert {row["version"] for row in rows} == {11}
    assert all(row["interface-id"].startswith("eni-") for row in rows)
    assert all(row["vpc-id"].startswith("vpc-") and row["subnet-id"].startswith("subnet-") for row in rows)
    assert all(row["end"] - row["start"] == FLOW_WINDOW_MINUTES * 60 for row in rows)


def test_vpc_populated_columns_are_exactly_the_model_projections(vpc_tree: list[Path]) -> None:
    """As colunas preenchidas sao exatamente as que tem fonte no modelo -- nem uma a mais."""
    always = {
        "version",
        "account-id",
        "interface-id",
        "srcaddr",
        "dstaddr",
        "srcport",
        "dstport",
        "protocol",
        "packets",
        "bytes",
        "start",
        "end",
        "action",
        "log-status",
        "vpc-id",
        "subnet-id",
        "region",
        "flow-direction",
    }
    optional = {"instance-id"}
    union: set[str] = set()
    with_instance = 0
    without_instance = 0
    # A amostra cobre um objeto por flow log (as 12 janelas de um mesmo flow log repetem o
    # mesmo produtor de registro); o conjunto COMPLETO de valores e provado no multiconjunto.
    for part in list(path for path in vpc_tree if path.suffix == ".parquet")[::11]:
        populated = set(populated_of(part))
        assert populated - (always | optional) == set(), f"{part.name}: coluna preenchida sem fonte"
        assert always <= populated, f"{part.name}: campos do modelo ausentes"
        union |= populated
        if "instance-id" in populated:
            with_instance += 1
        else:
            without_instance += 1
    assert union == always | optional, f"colunas preenchidas: {sorted(union)}"
    assert len(always) == 18
    # ``instance-id`` so existe para interface de instancia EC2: as duas metades do estate
    # (instancia e ENI gerenciado por servico) precisam aparecer.
    assert with_instance and without_instance


def test_vpc_delivery_has_one_object_per_flow_log_and_window(
    vpc_tree: list[Path], estate: CanonicalEstate
) -> None:
    """Um objeto de texto e um Parquet por (flow log, janela de agregacao) do modelo."""
    _, _, flows = _aws_network(estate)
    log_resources = {flow.log_resource_id for flow in flows}
    assert log_resources, "o estate precisa modelar fluxos AWS"
    expected_ids = {log: vpc_flow_logs._flow_log_id(estate.seed, log) for log in log_resources}
    expected_pairs = {
        (expected_ids[flow.log_resource_id], flow.window_start.strftime("%Y%m%dT%H%M")) for flow in flows
    }
    seen: dict[tuple[str, str], set[str]] = {}
    for path in vpc_tree:
        match = _VPC_NAME_RE.match(path.name)
        assert match
        seen.setdefault((match.group("flow_log"), match.group("stamp")), set()).add(match.group("ext"))
    assert set(seen) == expected_pairs, "os objetos nao cobrem exatamente os fluxos do modelo"
    assert all(extensions == {".log.gz", ".parquet"} for extensions in seen.values())
    assert len(vpc_tree) == 2 * len(expected_pairs)
    # Toda interface que registrou fluxo tem o seu flow log, e so essas.
    assert {match.group("flow_log") for match in map(_VPC_NAME_RE.match, (p.name for p in vpc_tree)) if match} == set(
        expected_ids.values()
    )
    windows = {window for _log, window in expected_pairs}
    assert len(windows) == FLOW_WINDOWS == 12, "as janelas do artefato sao as do modelo"


def test_vpc_windows_are_the_models_own(estate: CanonicalEstate) -> None:
    """A janela do artefato e a do fluxo: 5 minutos, terminando no fim do dia simulado."""
    _, _, flows = _aws_network(estate)
    assert flows
    assert all((flow.window_end - flow.window_start) == timedelta(minutes=FLOW_WINDOW_MINUTES) for flow in flows)
    starts = sorted({flow.window_start for flow in flows})
    assert len(starts) == FLOW_WINDOWS
    boundary = datetime.combine(estate.sim_now + timedelta(days=1), time(0, 0), tzinfo=UTC)
    assert starts[-1] + timedelta(minutes=FLOW_WINDOW_MINUTES) == boundary
    assert starts[0] == boundary - timedelta(minutes=FLOW_WINDOW_MINUTES * FLOW_WINDOWS)


def test_vpc_version_is_the_highest_version_among_the_specified_fields() -> None:
    """A regra documentada do campo ``version``, conferida contra a propria spec.

    *"If you use a custom format, the version is the highest version among the specified
    fields."* O formato emitido inclui os campos introduzidos na v11 (as tags e os
    ``next-hop-*``), entao a maior versao publicada entre os campos especificados e 11.
    """
    spec = load_spec(_VPC_SPEC)
    assert spec.delivery["default_format_field_order"].split() == list(spec.names[:14]), (
        "as 14 primeiras colunas da spec sao o formato padrao, na ordem documentada"
    )
    assert {"instance-tag", "next-hop-interface-type"} <= set(vpc_flow_logs._COLUMNS)
    assert vpc_flow_logs._FORMAT_VERSION == 11


def test_vpc_guard_refuses_a_value_without_a_model_source(estate: CanonicalEstate) -> None:
    """A trava de fabricacao: preencher uma lacuna e erro, nao um default."""
    _, _, flows = _aws_network(estate)
    assert flows
    network = vpc_flow_logs._AwsNetwork(estate)
    record = vpc_flow_logs._record(flows[0], network)
    vpc_flow_logs._require_columns(record)
    vpc_flow_logs._require_columns(vpc_flow_logs._record(flows[-1], network))
    for gap in ("tcp-flags", "type", "az-id", "interface-tag", "next-hop-vpc-id"):
        with pytest.raises(RenderError, match="lacuna, nao valor"):
            vpc_flow_logs._require_columns(dict(record, **{gap: "valor-inventado"}))


def _vpc_resource_stub() -> Any:
    """Um recurso VPC minimo, so para exercitar as travas de projecao dos outros modulos."""
    from tools.synthetic_clouds.model.identity import ResourceIdentity
    from tools.synthetic_clouds.model.resource import Resource

    return Resource(
        identity=ResourceIdentity(uuid="0" * 36, logical_path="aws/9/vpc/0000", provider="aws"),
        parent_scope_id="969191373337",
        service_name="Amazon Virtual Private Cloud",
        service_category="Networking",
        resource_type="vpc",
        resource_name="vpc-0000",
        region_id="us-east-1",
        region_name="US East (N. Virginia)",
        tags=(),
        sku_id="aws-vpc-unbilled",
        capacity_reservation=None,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AWS Config snapshot -- 4 conjuntos, um objeto entregue + notificacao + fixtures
# ═══════════════════════════════════════════════════════════════════════════════


def _config_objects(config_tree: list[Path]) -> list[Path]:
    return [path for path in config_tree if path.suffix == ".gz"]


def _config_extraction(config_tree: list[Path], scope: str) -> Path:
    """A extracao VERBATIM de um conjunto, sob ``extracted/<scope>.json``."""
    return next(
        path
        for path in config_tree
        if path.parent.name == aws_config_snapshot.EXTRACTION_DIR and path.name == f"{scope}.json"
    )


def test_config_spec_declares_the_36_fields_in_four_sets() -> None:
    spec = load_spec(_CONFIG_SPEC)
    assert spec.surface == aws_config_snapshot.SURFACE == "aws/aws-config-snapshot-s3"
    assert spec.set_names == (
        "configuration-file-envelope",
        "configuration-item",
        "relationship",
        "sns-delivery-notification",
    )
    assert len(spec.columns) == 36
    assert spec.emittable_count == 36


def test_config_column_lists_are_derived_from_the_spec() -> None:
    spec = load_spec(_CONFIG_SPEC)
    for scope, emitted in (
        (aws_config_snapshot.ENVELOPE_SCOPE, aws_config_snapshot._ENVELOPE_COLUMNS),
        (aws_config_snapshot.ITEM_SCOPE, aws_config_snapshot._ITEM_COLUMNS),
        (aws_config_snapshot.RELATIONSHIP_SCOPE, aws_config_snapshot._RELATIONSHIP_COLUMNS),
        (aws_config_snapshot.NOTIFICATION_SCOPE, aws_config_snapshot._NOTIFICATION_COLUMNS),
    ):
        assert emitted == tuple(column.name for column in spec.columns_for(scope))
        assert set(emitted) <= spec.emittable_names


def test_config_snapshot_object_carries_the_documented_envelope(config_tree: list[Path]) -> None:
    """O envelope entregue -- conferido na extracao VERBATIM do objeto gzipped.

    O nucleo de fidelidade le um JSON como texto (``artifacts._json_columns``), entao o
    ``.json.gz`` ENTREGUE nao pode ser lido por ele. A extracao existe para isso, e este
    teste prova que ela E o objeto entregue -- nao uma segunda renderizacao: a igualdade
    documento a documento e afirmada abaixo.
    """
    spec = load_spec(_CONFIG_SPEC)
    scope = aws_config_snapshot.ENVELOPE_SCOPE
    objects = _config_objects(config_tree)
    assert objects, "expected delivered snapshot objects"
    extraction = next(
        path
        for path in config_tree
        if path.parent.name == aws_config_snapshot.EXTRACTION_DIR and path.name == f"{scope}.json"
    )
    observed = _assert_faithful(spec, extraction, scope)
    assert set(observed) == _emittable(spec, scope)
    envelopes = _json(extraction)
    assert envelopes == [_json_gz(path) for path in objects], "a extracao precisa SER o objeto entregue"
    for document in envelopes:
        assert document["fileVersion"] == "1.0"
        assert document["configurationItems"], "a snapshot describes the recorded resources"
        assert set(document) == _emittable(spec, scope)


def test_config_snapshot_path_matches_the_official_example_layout(config_tree: list[Path]) -> None:
    """Caminho e nome documentados, com ``month``/``day`` SEM zero a esquerda (exemplo oficial)."""
    for path in _config_objects(config_tree):
        relative = path.as_posix().split(f"{aws_config_snapshot.RENDER_DIR}/", 1)[1]
        path_match = _CONFIG_PATH_RE.match(relative)
        assert path_match, f"caminho fora do template documentado: {relative}"
        name_match = _CONFIG_NAME_RE.match(path.name)
        assert name_match, f"nome fora do template documentado: {path.name}"
        assert name_match.group("account") == path_match.group("account")
        assert name_match.group("region") == path_match.group("region")
        assert path_match.group("year") == name_match.group("stamp")[:4]
        assert int(path_match.group("month")) == int(name_match.group("stamp")[4:6])
        assert int(path_match.group("day")) == int(name_match.group("stamp")[6:8])
        assert path_match.group("month") == str(int(path_match.group("month"))), "month sem zero a esquerda"
        assert path_match.group("day") == str(int(path_match.group("day"))), "day sem zero a esquerda"


def test_config_items_are_one_per_recordable_resource_and_verbatim(
    config_tree: list[Path], estate: CanonicalEstate
) -> None:
    """A extracao e uma copia dos itens ENTREGUES, e cada item vem de um recurso do modelo."""
    spec = load_spec(_CONFIG_SPEC)
    scope = aws_config_snapshot.ITEM_SCOPE
    extraction = _config_extraction(config_tree, scope)
    observed = _assert_faithful(spec, extraction, scope)
    assert set(observed) == _emittable(spec, scope)
    items = _json(extraction)

    delivered: list[dict[str, Any]] = []
    for path in _config_objects(config_tree):
        delivered.extend(_json_gz(path)["configurationItems"])
    assert items == delivered, "a extracao precisa ser o que foi ENTREGUE, nao uma segunda renderizacao"

    recordable = [resource for resource in _aws_resources(estate) if resource.resource_type in AWS_ID_PREFIXES]
    excluded = [resource for resource in _aws_resources(estate) if resource.resource_type not in AWS_ID_PREFIXES]
    # O estate modela tipos que NAO sao objetos (o `data_transfer` e uma linha de custo, sem
    # id em `model/identity.py`): eles nao podem virar configuration item.
    assert excluded, "the AWS estate models at least one type with no object id"
    assert {resource.resource_type for resource in excluded} == {"data_transfer"}
    assert len(items) == len(recordable), "um configuration item por recurso registravel"
    assert {item["resourceId"] for item in items} == {
        aws_resource_id(resource.resource_type, resource.identity.uuid) for resource in recordable
    }
    by_id = {item["resourceId"]: item for item in items}
    documented_by_token = {"ec2_instance": "AWS::EC2::Instance", "ebs_volume": "AWS::EC2::Volume"}
    for resource in recordable:
        expected_id = aws_resource_id(resource.resource_type, resource.identity.uuid)
        item = by_id[expected_id]
        assert item["configurationItemVersion"] == "1.0"
        assert item["resourceName"] == resource.resource_name
        assert item["accountId"] == resource.parent_scope_id
        assert item["awsRegion"] == resource.region_id
        assert item["tags"] == dict(resource.tags)
        assert item["resourceType"] == documented_by_token.get(resource.resource_type, "")
        assert item["configurationItemStatus"] == "OK"
        # Documentado como vazio desde a versao 1.3 do configuration item: a CHAVE existe e
        # nao carrega valor. Preencher isso seria tao infiel quanto omitir a chave.
        assert item["configurationItemMD5Hash"] == ""
        assert item["relatedEvents"] == []
        assert item["configuration"] == {} and item["supplementaryConfiguration"] == {}
    assert items


def test_config_item_gaps_stay_empty(config_tree: list[Path]) -> None:
    """As lacunas reais (ARN, relacoes, tempos) entregues VAZIAS, e o tipo so onde ha catalogo.

    ``resourceType`` so tem valor para os tipos que a pagina do AWS Config EXEMPLIFICA
    (``aws/config-snapshot-s3.md``): ``AWS::EC2::Instance`` e ``AWS::EC2::Volume``. Qualquer
    outro token sai vazio, porque a propria spec declara a lista de tipos dinamica e deduzir
    ``AWS::Servico::Recurso`` seria inventar vocabulario. O teste falha se um nome deduzido
    aparecer.
    """
    items = _json(_config_extraction(config_tree, aws_config_snapshot.ITEM_SCOPE))
    documented_by_token = {"ec2_instance": "AWS::EC2::Instance", "ebs_volume": "AWS::EC2::Volume"}
    seen_types: set[str] = set()
    for item in items:
        assert item["arn"] == ""
        assert item["relationships"] == []
        assert item["configurationItemCaptureTime"] == ""
        assert item["configurationItemDeliveryTime"] == ""
        assert item["configurationStateID"] == "" and item["configurationStateId"] == ""
        assert item["resourceCreationTime"] == ""
        assert item["recordingFrequency"] == ""
        assert item["resourceType"] in {"", *documented_by_token.values()}
        if item["resourceType"]:
            seen_types.add(item["resourceType"])
    # As duas metades existem no estate: o tipo documentado e o tipo sem nome publicado.
    assert seen_types == set(documented_by_token.values())
    assert any(item["resourceType"] == "" for item in items)


def test_config_notifications_carry_the_documented_message(
    config_tree: list[Path], estate: CanonicalEstate
) -> None:
    spec = load_spec(_CONFIG_SPEC)
    scope = aws_config_snapshot.NOTIFICATION_SCOPE
    notifications = [path for path in config_tree if path.parent.name == aws_config_snapshot.NOTIFICATION_DIR]
    assert notifications, "expected delivery notifications"
    assert len(notifications) == len(_config_objects(config_tree))
    for path in notifications:
        observed = _assert_faithful(spec, path, scope)
        assert set(observed) == _emittable(spec, scope)
        message = _json(path)
        assert message["messageType"] == "ConfigurationSnapshotDeliveryCompleted"
        assert message["recordVersion"] == "1.1"
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", message["notificationCreationTime"])
        # A chave aponta para um objeto que EXISTE na arvore entregue.
        key = message["s3ObjectKey"]
        target = next((path for path in _config_objects(config_tree) if path.as_posix().endswith(key)), None)
        assert target is not None, f"a notificacao aponta para um objeto inexistente: {key}"
        name_match = _CONFIG_NAME_RE.match(target.name)
        assert name_match
        assert message["configSnapshotId"] == name_match.group("snapshot")
        assert message["s3Bucket"] == aws_config_snapshot.bucket_name(
            name_match.group("account"), name_match.group("region")
        )


def test_config_relationship_set_is_a_shape_with_no_invented_value(config_tree: list[Path]) -> None:
    """O conjunto ``relationship`` nao tem instancia entregue: a fixture de forma prova a lacuna.

    O modelo canonico nao modela relacionamento entre recursos, entao as ``relationships``
    entregues sao arrays vazios. A fixture carrega os SEIS nomes documentados com o valor
    vazio de cada tipo, e o teste exige que continue assim -- dotacao inventada reprova.
    """
    spec = load_spec(_CONFIG_SPEC)
    scope = aws_config_snapshot.RELATIONSHIP_SCOPE
    shape = next(path for path in config_tree if path.parent.name == aws_config_snapshot.SHAPE_DIR)
    observed = _assert_faithful(spec, shape, scope)
    assert set(observed) == _emittable(spec, scope)
    document = _json(shape)
    assert all(value in ("", [], {}) for value in document.values()), "a fixture de forma nao pode ter valor"
    for path in _config_objects(config_tree):
        for item in _json_gz(path)["configurationItems"]:
            assert item["relationships"] == []


def test_config_versions_and_literals_come_from_the_specification() -> None:
    """Os literais emitidos sao os que a propria spec publica em ``allowed_values``.

    Lidos do JSON CRU da spec, porque ``fidelity.spec.Column`` nao expoe
    ``allowed_values``: o contrato conferido aqui e o da especificacao citada.
    """
    raw = json.loads(_CONFIG_SPEC.read_text(encoding="utf-8"))
    sets = {column_set["name"]: column_set["columns"] for column_set in raw["sets"]}

    def allowed(scope: str, name: str) -> str:
        return next(
            (column.get("allowed_values") or "") for column in sets[scope] if column["name"] == name
        )

    assert aws_config_snapshot.FILE_VERSION in allowed(aws_config_snapshot.ENVELOPE_SCOPE, "fileVersion")
    assert aws_config_snapshot.CONFIGURATION_ITEM_VERSION in allowed(
        aws_config_snapshot.ITEM_SCOPE, "configurationItemVersion"
    )
    assert aws_config_snapshot.RECORD_VERSION in allowed(aws_config_snapshot.NOTIFICATION_SCOPE, "recordVersion")
    assert aws_config_snapshot.MESSAGE_TYPE in allowed(aws_config_snapshot.NOTIFICATION_SCOPE, "messageType")


def test_config_guard_refuses_a_filled_gap() -> None:
    item = aws_config_snapshot._configuration_item(_vpc_resource_stub())
    with pytest.raises(RenderError, match="lacuna, nao valor"):
        aws_config_snapshot._require_projection(
            dict(item, arn="arn:aws:ec2:us-east-1:969191373337:instance/i-0123456789abcdef0"),
            aws_config_snapshot._ITEM_COLUMNS,
            aws_config_snapshot._ITEM_PROJECTED,
            "teste",
        )


def test_config_series_has_no_manifest_or_invented_object(config_tree: list[Path]) -> None:
    """Nenhum manifesto: a spec registra a ausencia como achado, e nao se inventa um."""
    spec = load_spec(_CONFIG_SPEC)
    assert "manifest" in spec.delivery and not spec.delivery["manifest"]
    for path in _config_objects(config_tree):
        assert "Manifest" not in path.name


# ═══════════════════════════════════════════════════════════════════════════════
# Security Hub ASFF -- 3 conjuntos, fixtures ASFF (a AWS nao exporta ASFF para S3)
# ═══════════════════════════════════════════════════════════════════════════════


def _hub_files(hub_tree: list[Path]) -> dict[str, Path]:
    return {path.name: path for path in hub_tree}


def test_hub_spec_declares_the_96_fields_in_three_sets() -> None:
    spec = load_spec(_HUB_SPEC)
    assert spec.surface == security_hub.SURFACE == "aws/security-hub-asff"
    assert spec.set_names == ("asff-top-level", "asff-resources", "asff-nested")
    assert len(spec.columns) == 96
    assert spec.emittable_count == 96


def test_hub_findings_artifact_carries_the_46_top_level_attributes(hub_tree: list[Path]) -> None:
    spec = load_spec(_HUB_SPEC)
    scope = security_hub.TOP_LEVEL_SCOPE
    path = _hub_files(hub_tree)["findings.json"]
    observed = _assert_faithful(spec, path, scope)
    assert set(observed) == _emittable(spec, scope)
    findings = _json(path)
    assert findings, "the AWS estate must carry findings"
    for document in findings:
        assert set(document) == _emittable(spec, scope), "todo finding tem o mesmo conjunto de atributos"


def test_hub_resources_artifact_carries_the_12_documented_members(hub_tree: list[Path]) -> None:
    spec = load_spec(_HUB_SPEC)
    scope = security_hub.RESOURCES_SCOPE
    path = _hub_files(hub_tree)["resources.json"]
    observed = _assert_faithful(spec, path, scope)
    assert set(observed) == _emittable(spec, scope)
    items = _json(path)
    assert items
    for item in items:
        assert set(item) == _emittable(spec, scope)


def test_hub_nested_artifact_carries_the_38_documented_paths(hub_tree: list[Path]) -> None:
    spec = load_spec(_HUB_SPEC)
    scope = security_hub.NESTED_SCOPE
    path = _hub_files(hub_tree)["nested.json"]
    observed = _assert_faithful(spec, path, scope)
    assert set(observed) == _emittable(spec, scope)
    documents = _json(path)
    assert documents
    for document in documents:
        assert set(document) == _emittable(spec, scope)


def test_hub_resources_and_nested_are_rebuilt_here_from_the_findings(hub_tree: list[Path]) -> None:
    """As duas views sao RECONSTRUIDAS aqui, com um caminhador escrito neste arquivo.

    Se o renderer tivesse inventado um valor em qualquer view, a reconstrucao a partir de
    ``findings.json`` divergiria -- o teste nao pode concordar com a implementacao.
    """
    files = _hub_files(hub_tree)
    findings = _json(files["findings.json"])
    resources = _json(files["resources.json"])
    nested = _json(files["nested.json"])

    assert resources == [item for document in findings for item in document["Resources"]]

    def walk(document: dict[str, Any], path: str) -> Any:
        current: Any = document
        for segment in path.split("."):
            if current is None:
                return None
            if segment == "Resources[]":
                items = current.get("Resources") if isinstance(current, dict) else None
                current = items[0] if items else None
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(segment)
        return current

    spec = load_spec(_HUB_SPEC)
    rebuilt = [
        {column.name: walk(document, column.name) for column in spec.columns_for(security_hub.NESTED_SCOPE)}
        for document in findings
    ]
    assert nested == rebuilt
    assert len(nested) == len(findings) == len(resources)


def test_hub_findings_project_the_model(estate: CanonicalEstate, hub_tree: list[Path]) -> None:
    findings = _json(_hub_files(hub_tree)["findings.json"])
    model_findings = sorted(
        (finding for finding in estate.findings if finding.provider == const.PROVIDER_KEY_AWS),
        key=lambda finding: finding.finding_id,
    )
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    profiles = {profile.resource_uuid: profile for profile in estate.instance_profiles}
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
    accounts = {account.account_id: unmarked_name(account.name) for org in estate.aws_orgs for account in org.accounts}
    assert len(findings) == len(model_findings)
    assert model_findings
    for document, finding in zip(findings, model_findings, strict=True):
        resource = resources[finding.resource_uuid]
        assert document["Id"] == finding.finding_id
        assert document["AwsAccountId"] == resource.parent_scope_id
        assert document["AwsAccountName"] == accounts[resource.parent_scope_id]
        assert document["Region"] == resource.region_id
        assert document["Severity"]["Label"] == finding.severity
        assert document["Severity"]["Original"] == finding.severity
        # `Normalized` e o numero que a AWS publica para o rotulo (API_Severity.html, 2026-10-15):
        # nao e um inteiro escolhido dentro da faixa 0-100, e o preenchimento automatico que o
        # proprio Security Hub faz quando recebe so o `Label`.
        assert document["Severity"]["Normalized"] == _ASFF_SEVERITY_NORMALIZED[finding.severity]
        assert document["RecordState"] == "ACTIVE"
        assert document["SchemaVersion"] == "2018-10-08"
        day = datetime.combine(finding.raised_on, time(0, 0), tzinfo=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert document["CreatedAt"] == day and document["UpdatedAt"] == day
        # Os nove atributos de topo que o modelo passou a carregar: texto, procedencia,
        # escala e o instante da primeira observacao.
        assert document["Title"] == (finding.title or None)
        assert document["Description"] == (finding.description or None)
        assert document["GeneratorId"] == (finding.generator_id or None)
        assert document["ProductName"] == (finding.product_name or None)
        assert document["CompanyName"] == (finding.company_name or None)
        assert document["Types"] == (list(finding.types) or None)
        assert finding.first_observed_at is not None, "o modelo precisa datar a primeira observacao"
        assert document["FirstObservedAt"] == finding.first_observed_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert document["Confidence"] == finding.confidence
        assert document["Criticality"] == finding.criticality
        assert 0 <= document["Confidence"] <= 100 and 0 <= document["Criticality"] <= 100
        # O provedor e este proprio estado: as escalas e os tipos vao tambem para o bloco
        # do provedor que o ASFF guarda ao lado dos normalizados.
        assert document["FindingProviderFields"]["Confidence"] == finding.confidence
        assert document["FindingProviderFields"]["Criticality"] == finding.criticality
        assert document["FindingProviderFields"]["Types"] == (list(finding.types) or None)
        # Os quatro atributos obrigatorios (fora ProductArn, sem fonte) estao preenchidos.
        for required in ("Title", "Description", "GeneratorId", "Id", "SchemaVersion", "Types"):
            assert document[required] is not None, required
        assert document["ProductArn"] is None, "o ARN exige ids de produto que o modelo nao tem"
        # ProductFields e o mapa de evidencia do proprio finding, com a regra documentada de
        # map<string,string> (booleano vira "true"/"false"; o resto vira JSON compacto).
        expected_fields: dict[str, str] = {}
        for key, value in sorted(finding.evidence_json.items()):
            if isinstance(value, bool):
                expected_fields[key] = "true" if value else "false"
            elif isinstance(value, str):
                expected_fields[key] = value
            else:
                expected_fields[key] = json.dumps(value, sort_keys=True, separators=(",", ":"))
        assert document["ProductFields"] == expected_fields
        assert document["ProductFields"], "a evidencia do finding nao pode ser um mapa vazio"
        item = document["Resources"][0]
        assert item["Id"] == (
            aws_resource_id(resource.resource_type, resource.identity.uuid)
            if resource.resource_type in AWS_ID_PREFIXES
            else None
        )
        assert item["Provider"] == "AWS" and item["Partition"] == "aws"
        assert item["Region"] == resource.region_id
        assert item["Tags"] == dict(resource.tags)
        # O tipo vem do catalogo: os dois exemplos documentados e o escape ``Other``.
        expected_type = {"ec2_instance": "AwsEc2Instance", "s3_bucket": "AwsS3Bucket"}.get(
            resource.resource_type, "Other"
        )
        assert item["Type"] == expected_type
        # O bloco de detalhes da instancia EC2: os sete membros com fonte no modelo.
        profile = profiles.get(resource.identity.uuid)
        if resource.resource_type != "ec2_instance" or profile is None:
            assert item["Details"] is None, "so o AwsEc2Instance tem membros enumerados na spec"
        else:
            details = item["Details"]["AwsEc2Instance"]
            assert details["ImageId"] == profile.image_id
            assert details["Type"] == profile.instance_type
            assert details["LaunchedAt"] == profile.launch_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            addresses = [profile.private_ip] + ([profile.public_ip] if profile.public_ip else [])
            assert details["IpV4Addresses"] == addresses
            interface_uuid, segment_uuid = profile.interface_uuid, profile.segment_uuid
            assert interface_uuid is not None and segment_uuid is not None
            interface = interfaces[interface_uuid]
            assert details["NetworkInterfaces"] == [{"NetworkInterfaceId": interface.interface_id}]
            segment = segments[segment_uuid]
            assert details["SubnetId"] == segment.subnet_id and details["VpcId"] == segment.segment_id


def test_hub_ec2_details_keep_the_unmodelled_members_empty(hub_tree: list[Path]) -> None:
    """Os oito membros que o modelo nao tem continuam VAZIOS -- preencher reprova.

    A pagina do ASFF publica o bloco inteiro; o modelo sustenta sete membros. Os outros
    (perfil IAM, key pair, IPv6, opcoes de metadados e seus quatro subcampos, tipo de
    virtualizacao) precisam seguir nulos, e o teste existe para que um valor plausivel
    neles reprove.
    """
    documents = _json(_hub_files(hub_tree)["findings.json"])
    observed = 0
    for document in documents:
        details = document["Resources"][0]["Details"]
        if details is None:
            continue
        observed += 1
        block = details["AwsEc2Instance"]
        assert block["IamInstanceProfileArn"] is None
        assert block["KeyName"] is None
        assert block["IpV6Addresses"] is None
        assert block["VirtualizationType"] is None
        assert block["MetadataOptions"] is None
    assert observed, "o estate precisa ter findings de instancia EC2"


def test_hub_does_not_claim_an_export_mechanism_it_does_not_have(hub_tree: list[Path]) -> None:
    """ASFF nao e um formato de export: nenhuma fixture finge um layout de objeto S3."""
    spec = load_spec(_HUB_SPEC)
    assert spec.delivery["kind"] == "s3"
    assert spec.delivery["format"] == "|".join(security_hub.DOCUMENTED_EXPORT_FORMATS)
    assert "ASFF is NOT an available export format" in spec.delivery["format_note"]
    for path in hub_tree:
        assert "AWSLogs" not in path.as_posix(), "nenhum caminho de S3 pode ser inventado"
        assert "Manifest" not in path.name
    assert {path.name for path in hub_tree} == {"findings.json", "resources.json", "nested.json"}


def test_a_severidade_sai_do_enum_publicado_e_nao_da_faixa(hub_tree: list[Path]) -> None:
    """``Severity.Label`` e ``Severity.Normalized`` sao o enum e a tabela que a AWS publica.

    Duas coisas sao conferidas, e as duas dependem da leitura da pagina do objeto ``Severity``
    (``API_Severity.html``, 2026-10-15):

    1. Todo rotulo emitido esta no enum **formal** ``INFORMATIONAL | LOW | MEDIUM | HIGH |
       CRITICAL``. Ate a leitura dessa pagina, o contrato so tinha "guidance, not a formal
       enum" -- e a pagina do objeto e que traz o ``Valid Values``.
    2. ``Normalized`` e o valor **exato** que a AWS publica para cada rotulo, nao um inteiro
       qualquer dentro da faixa 0-100. A faixa estava documentada desde sempre; a tabela de
       preenchimento automatico e que nao estava, e e ela que torna o valor verificavel.
    """
    documentos = _json(_hub_files(hub_tree)["findings.json"])
    assert documentos, "nenhum achado ASFF conferido"
    pares = {(documento["Severity"]["Label"], documento["Severity"]["Normalized"]) for documento in documentos}
    rotulos = {rotulo for rotulo, _ in pares}
    assert rotulos <= _ASFF_SEVERITY_LABEL, f"rotulo fora do enum publicado: {sorted(rotulos)}"
    for rotulo, normalizado in pares:
        assert normalizado == _ASFF_SEVERITY_NORMALIZED[rotulo], (
            f"Normalized fora da tabela da AWS: {rotulo}={normalizado}"
        )


def test_os_campos_de_consumo_vem_no_user_defined_fields(hub_tree: list[Path]) -> None:
    """O produtor carrega os quatro fatos que o ASFF nao tem membro, em UserDefinedFields.

    O consumidor exige ``evidence``, ``exposure``, ``impact`` e ``fingerprint`` como NOT NULL, e a
    ``AwsSecurityFinding`` nao tem membro para nenhum deles. Em vez de deixar o consumidor
    inventar, o produtor os carrega no mapa livre que a propria AWS publica para isso. Este teste
    existe para que o mapa nunca vire um campo vazio outra vez, e para travar TRES coisas:

    1. as cinco chaves existem e nao ha nenhuma a mais -- um mapa livre aceita qualquer coisa, e
       "aceita qualquer coisa" e exatamente onde um dado inventado entraria sem ninguem notar;
    2. a impressao e RE-CALCULAVEL a partir do proprio documento (regra unica, abaixo), o que
       significa que qualquer consumidor pode verifica-la em vez de confiar;
    3. os tetos publicados (chave ate 128, valor ate 1024) sao respeitados.
    """
    documentos = _json(_hub_files(hub_tree)["findings.json"])
    assert documentos, "nenhum achado ASFF conferido"

    chaves = {chave for documento in documentos for chave in documento["UserDefinedFields"]}
    assert chaves == set(_ASFF_INGEST_FIELDS), f"chaves inesperadas ou ausentes: {sorted(chaves)}"

    for documento in documentos:
        campos = documento["UserDefinedFields"]
        for chave, valor in campos.items():
            assert len(chave) <= 128, f"chave acima do teto publicado: {chave!r}"
            assert len(valor) <= 1024, f"valor acima do teto publicado em {chave!r}"
        # Regra unica: a impressao e o sha256 do que o DOCUMENTO mostra. O id do recurso vem de
        # `exposure.resource` -- que e `Resources[0].Id`, ou o uuid do modelo no tipo que nao tem
        # id de objeto (`data_transfer`), e por isso o expoe em vez de esconder.
        esperado = hashlib.sha256(
            "|".join(
                (
                    json.loads(campos["exposure"])["resource"],
                    "/".join(documento["Types"] or []),
                    documento["Severity"]["Label"],
                )
            ).encode()
        ).hexdigest()
        assert campos["fingerprint"] == esperado, (
            f"impressao nao recalculavel a partir do documento: {documento['Id']}"
        )
        # `evidence` e o `evidence_json` do modelo -- o mesmo conteudo que `ProductFields` leva,
        # com os booleanos convertidos em string porque um valor de mapa ASFF e string.
        evidencia = json.loads(campos["evidence"])
        assert set(evidencia) == set(documento["ProductFields"] or {}), (
            f"evidence nao corresponde ao evidence_json que ProductFields leva: {documento['Id']}"
        )
        assert campos["category"], f"categoria nativa vazia em {documento['Id']}"


# ═══════════════════════════════════════════════════════════════════════════════
# EC2 DescribeInstances -- 4 conjuntos, fixtures JSON (a API publica XML)
# ═══════════════════════════════════════════════════════════════════════════════


def _ec2_files(ec2_tree: list[Path]) -> dict[str, Path]:
    return {path.name: path for path in ec2_tree}


def test_ec2_spec_declares_the_75_fields_in_four_sets() -> None:
    spec = load_spec(_EC2_SPEC)
    assert spec.surface == ec2_instances.SURFACE == "aws/ec2-describe-instances"
    assert spec.set_names == (
        "describe-instances-response",
        "reservation",
        "instance",
        "request-parameters",
    )
    assert len(spec.columns) == 75
    assert spec.emittable_count == 75
    assert spec.delivery["kind"] == "read_api"
    assert spec.delivery["format"] == "xml"


def test_ec2_instance_fixture_carries_the_61_documented_members(ec2_tree: list[Path]) -> None:
    spec = load_spec(_EC2_SPEC)
    scope = ec2_instances.INSTANCE_SCOPE
    path = _ec2_files(ec2_tree)["instance.json"]
    observed = _assert_faithful(spec, path, scope)
    assert set(observed) == _emittable(spec, scope)
    instances = _json(path)
    assert instances, "the AWS estate must model EC2 instances"
    for instance in instances:
        assert set(instance) == _emittable(spec, scope)


def test_ec2_reservation_response_and_request_fixtures(ec2_tree: list[Path]) -> None:
    spec = load_spec(_EC2_SPEC)
    files = _ec2_files(ec2_tree)
    for name, scope in (
        ("reservation.json", ec2_instances.RESERVATION_SCOPE),
        ("describe-instances-response.json", ec2_instances.RESPONSE_SCOPE),
    ):
        observed = _assert_faithful(spec, files[name], scope)
        assert set(observed) == _emittable(spec, scope)
        for document in _json(files[name]):
            assert set(document) == _emittable(spec, scope)

    scope = ec2_instances.REQUEST_SCOPE
    observed = _assert_faithful(spec, files["request-parameters.json"], scope)
    assert set(observed) == _emittable(spec, scope)
    # A lacuna: o modelo nao carrega requisicao capturada, entao os seis nomes sao emitidos
    # com valor nulo em vez de um default plausivel.
    assert all(value is None for value in _json(files["request-parameters.json"]).values())


def test_ec2_instances_project_the_model(estate: CanonicalEstate, ec2_tree: list[Path]) -> None:
    spec = load_spec(_EC2_SPEC)
    instances = _json(_ec2_files(ec2_tree)["instance.json"])
    model_instances = _aws_resources(estate, "ec2_instance")
    profiles = {profile.resource_uuid: profile for profile in estate.instance_profiles}
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    interfaces = {interface.interface_uuid: interface for interface in estate.network_interfaces}
    assert model_instances
    assert len(instances) == len(model_instances)
    scope = ec2_instances.INSTANCE_SCOPE
    populated = {
        column.name
        for column in spec.columns_for(scope)
        if any(not _empty(instance[column.name]) for instance in instances)
    }
    assert populated == {
        "instanceId",
        "capacityReservationId",
        "imageId",
        "instanceType",
        "launchTime",
        "privateIpAddress",
        "ipAddress",
        "instanceState",
        "placement",
        "subnetId",
        "vpcId",
        "NetworkInterfaceSet.N",
        "TagSet.N",
    }
    by_id = {instance["instanceId"]: instance for instance in instances}
    for resource in model_instances:
        expected_id = aws_resource_id("ec2_instance", resource.identity.uuid)
        instance = by_id[expected_id]
        profile = profiles[resource.identity.uuid]
        interface_uuid, segment_uuid = profile.interface_uuid, profile.segment_uuid
        assert interface_uuid is not None and segment_uuid is not None
        segment = segments[segment_uuid]
        interface = interfaces[interface_uuid]
        assert instance["imageId"] == profile.image_id
        assert instance["instanceType"] == profile.instance_type
        assert instance["launchTime"] == profile.launch_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        assert instance["privateIpAddress"] == profile.private_ip
        assert instance["ipAddress"] == profile.public_ip
        assert instance["instanceState"] == {
            "code": 16 if profile.state == "running" else 80,
            "name": profile.state,
        }
        assert instance["placement"] == {"availabilityZone": profile.zone}
        assert instance["subnetId"] == segment.subnet_id and instance["vpcId"] == segment.segment_id
        assert instance["NetworkInterfaceSet.N"] == [
            {
                "networkInterfaceId": interface.interface_id,
                "macAddress": interface.mac_address,
                "privateIpAddress": interface.private_ip,
                "subnetId": segment.subnet_id,
                "vpcId": segment.segment_id,
            }
        ]
        # Os membros aninhados usam a grafia de RESPOSTA da API (``key``/``value``), nao a de
        # requisicao: a pagina do objeto Tag publica as duas.
        assert instance["TagSet.N"] == [{"key": key, "value": value} for key, value in resource.tags]
        reservation = resource.capacity_reservation
        assert instance["capacityReservationId"] == (None if reservation is None else reservation.reservation_id)
    # Os dois estados canonicos aparecem, e ambos os codigos documentados sao exercitados.
    assert {instance["instanceState"]["name"] for instance in instances} == {"running", "stopped"}
    assert {instance["instanceState"]["code"] for instance in instances} == {16, 80}


def test_ec2_instance_gaps_stay_empty(ec2_tree: list[Path]) -> None:
    """Os membros sem fonte no modelo continuam nulos -- preencher com plausibilidade reprova."""
    instances = _json(_ec2_files(ec2_tree)["instance.json"])
    assert instances
    for instance in instances:
        for column in (
            "amiLaunchIndex",
            "architecture",
            "BlockDeviceMapping.N",
            "bootMode",
            "cpuOptions",
            "dnsName",
            "ebsOptimized",
            "enaSupport",
            "GroupSet.N",
            "hypervisor",
            "iamInstanceProfile",
            "instanceLifecycle",
            "ipv6Address",
            "keyName",
            "metadataOptions",
            "monitoring",
            "platform",
            "privateDnsName",
            "ProductCodes.N",
            "rootDeviceName",
            "rootDeviceType",
            "sourceDestCheck",
            "stateReason",
            "usageOperation",
            "virtualizationType",
        ):
            assert instance[column] is None, column


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == {} or value == []


def test_ec2_response_reservation_and_instances_agree(ec2_tree: list[Path]) -> None:
    files = _ec2_files(ec2_tree)
    responses = _json(files["describe-instances-response.json"])
    reservations = _json(files["reservation.json"])
    instances = _json(files["instance.json"])
    assert len(responses) == len(reservations) > 0
    assert [reservation for response in responses for reservation in response["reservationSet"]] == reservations
    assert [instance for reservation in reservations for instance in reservation["InstancesSet.N"]] == instances
    for reservation in reservations:
        assert reservation["ownerId"] is not None
        # "Not supported." e o que a pagina do objeto Reservation publica para este membro.
        assert reservation["GroupSet.N"] == []
        assert reservation["reservationId"] is None and reservation["requesterId"] is None
    for response in responses:
        assert response["nextToken"] is None, 'a pagina carrega todo o inventario: "null quando nao ha mais itens"'
        # O identificador da CHAMADA e cunhado (UUIDv5), ao contrario dos parametros da
        # requisicao, que sao fatos sobre uma chamada que ninguem capturou.
        assert re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", response["requestId"]
        )


def test_ec2_fixture_encoding_decision_is_recorded() -> None:
    """O formato publicado e XML; os fixtures sao JSON, e a decisao e explicita e testada."""
    spec = load_spec(_EC2_SPEC)
    assert ec2_instances.PUBLISHED_ENCODING == spec.delivery["format"] == "xml"
    assert ec2_instances.FIXTURE_ENCODING == "json"
    assert "XML" in spec.delivery["format_note"]


def test_ec2_guard_refuses_a_filled_gap(estate: CanonicalEstate) -> None:
    instance = ec2_instances._instance(_vpc_resource_stub(), ec2_instances._Ec2Model(estate))
    with pytest.raises(RenderError, match="lacuna, nao valor"):
        ec2_instances._require_projection(
            dict(instance, imageId="ami-0123456789abcdef0", architecture="x86_64"),
            ec2_instances._INSTANCE_COLUMNS,
            ec2_instances._INSTANCE_PROJECTED,
            "teste",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Transversal: determinismo, fronteira de escrita e o contrato da spec
# ═══════════════════════════════════════════════════════════════════════════════


def _renderers() -> tuple[tuple[Any, str], ...]:
    return (
        (vpc_flow_logs.VpcFlowLogsRenderer(), vpc_flow_logs.RENDER_DIR),
        (aws_config_snapshot.AwsConfigSnapshotRenderer(), aws_config_snapshot.RENDER_DIR),
        (security_hub.SecurityHubAsffRenderer(), security_hub.RENDER_DIR),
        (ec2_instances.Ec2InstancesRenderer(), ec2_instances.RENDER_DIR),
    )


def _relative(path: Path, render_dir: str) -> Path:
    """O caminho de um objeto relativo ao diretorio do renderer.

    A ULTIMA ocorrencia do nome: o diretorio de destino de um teste pode se chamar como o
    renderer (``tmp_path / renderer.name``), e cortar na primeira deixaria o segundo no
    caminho relativo.
    """
    parts = path.parts
    index = len(parts) - 1 - parts[::-1].index(render_dir)
    return Path(*parts[index + 1 :])


def test_every_renderer_writes_under_its_own_directory_and_is_deterministic(
    estate: CanonicalEstate,
    tmp_path: Path,
    vpc_tree: list[Path],
    config_tree: list[Path],
    hub_tree: list[Path],
    ec2_tree: list[Path],
) -> None:
    """Fronteira de escrita (NFR-4) e estabilidade byte a byte, numa segunda renderizacao.

    O mesmo seed sobre o mesmo estado tem de produzir os MESMOS objetos e os MESMOS bytes.
    Uma renderizacao por renderer aqui (a primeira foi a fixture), comparada objeto a objeto
    com a arvore ja conferida acima.
    """
    fixtures = (vpc_tree, config_tree, hub_tree, ec2_tree)
    for (renderer, render_dir), fixture in zip(_renderers(), fixtures, strict=True):
        assert renderer.name == render_dir, "o diretorio segue a convencao do nome do renderer"
        written = renderer.render(estate, tmp_path / renderer.name)
        assert written
        expected = {_relative(path, render_dir): path for path in fixture}
        observed = {_relative(path, render_dir): path for path in written}
        assert set(observed) == set(expected), f"{renderer.name}: o conjunto de objetos mudou"
        for relative, path in observed.items():
            assert path.exists()
            assert render_dir in path.parts, f"{path} escaped the render dir"
            assert path.read_bytes() == expected[relative].read_bytes(), f"{relative} is not byte-stable"


def test_specs_still_declare_every_column_as_emittable() -> None:
    """Se uma coluna deixar de pertencer ao formato, o renderer precisa falhar -- nao encurtar."""
    for spec_path in (_VPC_SPEC, _CONFIG_SPEC, _HUB_SPEC, _EC2_SPEC):
        spec = load_spec(spec_path)
        refused = [column.name for column in spec.columns if not column.belongs_to_schema]
        assert refused == [], f"{spec.surface}: colunas documentadas fora do formato: {refused}"


def test_empty_and_filled_are_two_different_things() -> None:
    """A regra que o teste de registros protege: um campo VAZIO nao e o mesmo que um campo
    preenchido com ausencia.

    ``_empty`` (o predicado deste arquivo) trata ``None``/``""``/``{}``/``[]`` como vazio e
    ZERO como valor -- e e por isso que ``packets = 0`` contaria como preenchido. O golden
    acima exige ``packets > 0`` em algum registro, entao uma coluna que voltasse a ser
    apenas ausencia (todos os registros nulos) reprovaria.
    """
    assert _empty(None) and _empty("") and _empty({}) and _empty([])
    assert not _empty(0) and not _empty("0") and not _empty(6)


# ═══════════════════════════════════════════════════════════════════════════════
# Invariante: nenhuma coluna OBRIGATORIA sai vazia sem declaracao
# ═══════════════════════════════════════════════════════════════════════════════


def _scope_artifacts(surface: str, tree: list[Path]) -> dict[str | None, list[Path]]:
    """Os artefatos de cada conjunto nomeado de uma superficie (``None`` = conjunto plano).

    Cada conjunto e conferido no arquivo que o carrega: o Parquet no caso plano do flow log,
    as extracoes e a fixture de forma no AWS Config, os tres JSON do ASFF e os quatro do EC2.
    """
    if surface == vpc_flow_logs.SURFACE:
        return {None: [path for path in tree if path.suffix == ".parquet"]}
    if surface == aws_config_snapshot.SURFACE:
        return {
            aws_config_snapshot.ENVELOPE_SCOPE: [
                _config_extraction(tree, aws_config_snapshot.ENVELOPE_SCOPE)
            ],
            aws_config_snapshot.ITEM_SCOPE: [_config_extraction(tree, aws_config_snapshot.ITEM_SCOPE)],
            aws_config_snapshot.RELATIONSHIP_SCOPE: [
                path for path in tree if path.parent.name == aws_config_snapshot.SHAPE_DIR
            ],
            aws_config_snapshot.NOTIFICATION_SCOPE: [
                path for path in tree if path.parent.name == aws_config_snapshot.NOTIFICATION_DIR
            ],
        }
    if surface == security_hub.SURFACE:
        files = _hub_files(tree)
        return {
            security_hub.TOP_LEVEL_SCOPE: [files["findings.json"]],
            security_hub.RESOURCES_SCOPE: [files["resources.json"]],
            security_hub.NESTED_SCOPE: [files["nested.json"]],
        }
    files = _ec2_files(tree)
    return {
        ec2_instances.RESPONSE_SCOPE: [files["describe-instances-response.json"]],
        ec2_instances.RESERVATION_SCOPE: [files["reservation.json"]],
        ec2_instances.INSTANCE_SCOPE: [files["instance.json"]],
        ec2_instances.REQUEST_SCOPE: [files["request-parameters.json"]],
    }


def test_no_required_column_ships_empty_without_a_declared_reason(
    vpc_tree: list[Path],
    config_tree: list[Path],
    hub_tree: list[Path],
    ec2_tree: list[Path],
) -> None:
    """Toda coluna ``required`` da spec tem valor em algum registro -- ou uma lacuna declarada.

    O buraco que este teste fecha: contar so "colunas emitidas" deixa passar a coluna
    OBRIGATORIA que ninguem preenche e ninguem declara (foi assim que dois ``requestId``
    ficaram vazios). A declaracao vive no modulo, em ``REQUIRED_EMPTY_GAPS``, e a conferencia
    e EXATA nos dois sentidos: uma coluna obrigatoria vazia tem de estar declarada, e um nome
    declarado nao pode ter valor em lugar nenhum.
    """
    cases = (
        (vpc_flow_logs.SURFACE, _VPC_SPEC, vpc_tree, vpc_flow_logs),
        (aws_config_snapshot.SURFACE, _CONFIG_SPEC, config_tree, aws_config_snapshot),
        (security_hub.SURFACE, _HUB_SPEC, hub_tree, security_hub),
        (ec2_instances.SURFACE, _EC2_SPEC, ec2_tree, ec2_instances),
    )
    for surface, spec_path, tree, module in cases:
        spec = load_spec(spec_path)
        artifacts = _scope_artifacts(surface, tree)
        assert set(artifacts) == set(spec.set_names or (None,)), f"{surface}: conjuntos nao cobertos"
        empty_required: set[str] = set()
        for scope, paths in artifacts.items():
            columns = spec.columns_for(scope) if scope else spec.columns
            required = {column.name for column in columns if column.required}
            populated: set[str] = set()
            for path in paths:
                populated |= set(populated_of(path))
            missing = required - populated
            assert missing <= set(module.REQUIRED_EMPTY_GAPS), (
                f"{surface}/{scope}: coluna obrigatoria sem valor e sem declaracao: {sorted(missing)}"
            )
            empty_required |= missing
        declared = module.REQUIRED_EMPTY_GAPS
        assert set(declared) == empty_required, (
            f"{surface}: declaracao de lacunas desatualizada -- declaradas={sorted(declared)} "
            f"vazias={sorted(empty_required)}"
        )
        for name, reason in declared.items():
            assert len(reason.strip()) >= 40, f"{surface}: lacuna {name} sem justificativa"


def test_request_ids_are_minted_in_the_documented_shape(
    estate: CanonicalEstate, config_tree: list[Path], ec2_tree: list[Path]
) -> None:
    """Os dois ``requestId`` cunhados: UUID na forma, deterministas e distintos por chamada.

    A pagina do ``InstanceState`` nao ajuda aqui -- a forma vem dos exemplos oficiais das
    duas superficies: o sample do ``DescribeInstances`` escreve
    ``8f7724cf-496f-496e-8fe3-example`` e o ``s3ObjectKey`` do Config carrega o
    ``configSnapshotId`` como UUID. O id e DERIVADO (``TODO-verificar``), nao emitido pela
    AWS, e o teste prova que ele e funcao de (seed, chamada) e nao um valor solto.
    """
    uuid_form = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
    envelopes = _json(_config_extraction(config_tree, aws_config_snapshot.ENVELOPE_SCOPE))
    responses = _json(_ec2_files(ec2_tree)["describe-instances-response.json"])
    assert envelopes and responses
    for document in envelopes:
        assert uuid_form.match(document["requestId"]), document["requestId"]
    for response in responses:
        assert uuid_form.match(response["requestId"]), response["requestId"]
    assert len({document["requestId"] for document in envelopes}) == len(envelopes)
    assert len({response["requestId"] for response in responses}) == len(responses)
    # Determinstico: o mesmo estado cunha os mesmos ids.
    for account_id, region, _resources in aws_config_snapshot._pairs(estate):
        moment = aws_config_snapshot.snapshot_moment(estate.sim_now)
        assert aws_config_snapshot.request_id(estate, account_id, region, moment) in {
            document["requestId"] for document in envelopes
        }
    for account_id, region, _resources in ec2_instances._calls(estate):
        assert ec2_instances.request_id(estate, account_id, region) in {
            response["requestId"] for response in responses
        }
