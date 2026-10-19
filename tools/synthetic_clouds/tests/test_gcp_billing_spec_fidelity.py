"""Golden fidelity: the GCP FinOps artifacts carry EXACTLY the documented columns.

The specification is the source of truth (``specs/README.md``) and its normative reader
is ``fidelity.spec.load_spec``. These tests RENDER the artifacts to a temporary
directory and compare the DELIVERED FILES with that specification -- never an in-memory
column list, which would only prove that two copies of the same mistake agree.

Level under test -- the DOTTED SPEC PATH
----------------------------------------
The specs spell a nested field as a path (``project.labels.key``, ``credits.amount``,
``resource.name``), so the compared unit is the dotted path: ``project`` AND
``project.labels.key`` are both columns. The top-level count is smaller than the path
count (26 x 71 on the standard table), so the top-level view is asserted separately --
the two levels are different claims and this file keeps them apart.

Which artifact proves which claim
---------------------------------
* The schema claim is proved on ``02_tables.sql`` (the DDL the provisioner submits),
  parsed back into dotted paths. The pricing surface has NO row file -- the estate models
  no per-SKU tiered price catalog -- so its DDL is the only artifact that exists, and
  ``09_rows_resource.json`` / ``08_rows_standard.json`` are checked in addition for the
  two usage tables. ``columns_of()`` (the fidelity core's real-artifact reader) supplies
  the JSON row fields.
* STRUCTURAL CONTAINERS: ``invoice``, ``service``, ``sku``, ``location`` and ``usage``
  are documented only through their SUBFIELDS (the spec has no row for the record
  itself), and BigQuery cannot declare ``service.id`` without declaring the record that
  hosts it. The declared-but-undocumented set is asserted to be EXACTLY that minimal
  prefix closure, so a synthesized container can never smuggle an undocumented column in.
* ``evidence: null-empty`` columns belong to the format but may not carry a value. The
  three billing surfaces have none today; the guard runs anyway so it becomes live the
  day one appears.
* VALUES are audited too: a column the state CAN fill must be filled from the modelled
  source (hierarchy, instance profile, SKU catalogue, the line's own costs), every value
  of a column with ``allowed_values`` must be one of them, and the columns with NO source
  must be named in ``model_gaps`` inside the delivered ``_provenance.json`` -- checked in
  both directions, so the registry cannot go stale in silence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity.artifacts import columns_of, is_empty_value
from tools.synthetic_clouds.fidelity.checker import (
    KIND_INVENTED,
    KIND_MISSING,
    check,
    is_faithful,
)
from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render.gcp_bigquery import GcpBigQueryRenderer
from tools.synthetic_clouds.render.gcp_bigquery_topology import (
    PROVENANCE_FILENAME,
    GcpBigQueryTopologyRenderer,
    SpecField,
    field_paths,
    fields_for,
)
from tools.synthetic_clouds.scenarios.emit import apply_all

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_DIR = _REPO_ROOT / "specs" / "gcp"

_SURFACES = ("standard", "detailed", "pricing")
_SPEC_FILE = {
    "standard": "billing-export-standard.schema.json",
    "detailed": "billing-export-detailed.schema.json",
    "pricing": "billing-export-pricing.schema.json",
}
#: Which DDL table each surface is delivered as (the billing account id is dynamic).
_TABLE_SUFFIX = {
    "standard": re.compile(r"\.gcp_billing_export_v1_[A-Za-z0-9_]+$"),
    "detailed": re.compile(r"\.gcp_billing_export_resource_v1_[A-Za-z0-9_]+$"),
    "pricing": re.compile(r"\.cloud_pricing_export$"),
}
_ROW_FILE = {
    "standard": "08_rows_standard.json",
    "detailed": "09_rows_resource.json",
    "pricing": "12_rows_pricing.json",
}


def _row_file(surface: str) -> str:
    """O artefato de LINHAS da superfície entregue por ``render()``."""
    return _ROW_FILE[surface]


_PRICING_ROW_FILE = _ROW_FILE["pricing"]

#: The golden counts of the cited documentation (standard/detailed/pricing). A spec edit
#: that changes them is exactly the event this file exists to surface.
_EXPECTED_COLUMNS = {"standard": 71, "detailed": 77, "pricing": 37}
#: Top-level names of the same surfaces (26/28/18): the specs spell nested fields as
#: paths, so the top-level count is SMALLER than the column count. Both are asserted, as
#: separate claims: a renderer can get every top-level name right and every subfield wrong.
_EXPECTED_TOP_LEVEL = {"standard": 26, "detailed": 28, "pricing": 18}
#: Columns exclusive of the detailed export (the detailed spec is a superset).
_DETAILED_ONLY = {
    "resource",
    "resource.name",
    "resource.global_name",
    "subscription",
    "subscription.instance_id",
    "consumption_model.applied_subscription_instance_id",
}
#: Tables ``02_tables.sql`` provisions that NO ``specs/*.schema.json`` covers: the invoice
#: pair is an invoice-side contract, and the CUD/FOCUS tables have no spec yet. Listed so
#: an un-audited table can never be added in silence.
_UNSPECIFIED_TABLES = (".invoice", ".invoice_line_item", ".cud_subscriptions_export")

_BQ_SCALAR_TYPES = {
    "String": "STRING",
    "Timestamp": "TIMESTAMP",
    "Float": "FLOAT64",
    "Numeric": "NUMERIC",
    "Boolean": "BOOL",
    "Date": "DATE",
}


# -- fixtures -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return apply_all(build_estate(seed=123, profile="small", currency="USD"))


@pytest.fixture(scope="module")
def topology_dir(tmp_path_factory: pytest.TempPathFactory, estate: CanonicalEstate) -> Path:
    """The DELIVERED Phase-3 artifact directory (written by the renderer's own ``render``)."""
    out = tmp_path_factory.mktemp("fidelity_topology")
    GcpBigQueryTopologyRenderer().render(estate, out)
    return out / "gcp_bigquery_topology"


@pytest.fixture(scope="module")
def probe_dir(tmp_path_factory: pytest.TempPathFactory, estate: CanonicalEstate) -> Path:
    """The DELIVERED Phase-1 probe artifact directory (``rows.json`` + ``ddl.sql``)."""
    out = tmp_path_factory.mktemp("fidelity_probe")
    GcpBigQueryRenderer().render(estate, out)
    return out / "gcp_bigquery"


def _spec(surface: str) -> SurfaceSpec:
    return load_spec(_SPEC_DIR / _SPEC_FILE[surface])


# -- artifact parsing (the artifact, not the code that wrote it) ---------------------

_CREATE_TABLE_RE = re.compile(r"CREATE TABLE `([^`]+)` \(\n(.*?)\n\);", re.S)
_INSERT_RE = re.compile(r"INSERT INTO `[^`]+` \(([^)]*)\) VALUES")
_FIELD_RE = re.compile(r"^`?([A-Za-z_][A-Za-z0-9_]*)`?\s+(.+)$", re.S)


def _table_blocks(ddl_text: str) -> dict[str, str]:
    """Map ``project.dataset.table`` -> its DDL column block, from the delivered file."""
    return {match.group(1): match.group(2) for match in _CREATE_TABLE_RE.finditer(ddl_text)}


def _split_type_fields(body: str) -> list[str]:
    """Split a DDL column list on the commas at nesting depth 0 (``<...>`` nests)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in body:
        if char == "<":
            depth += 1
        elif char == ">":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _flatten_types(body: str, prefix: str = "") -> dict[str, str]:
    """Expand a DDL column list into ``{dotted path: declared type}``.

    A record is a path of its own (``project``) and so is each of its subfields
    (``project.labels.key``): that is the level the spec lists.
    """
    mapping: dict[str, str] = {}
    for chunk in _split_type_fields(body):
        match = _FIELD_RE.match(chunk)
        assert match is not None, f"unparsable DDL column: {chunk!r}"
        name, type_text = match.group(1), match.group(2).strip()
        path = f"{prefix}{name}"
        mapping[path] = type_text
        inner = type_text
        if inner.startswith("ARRAY<") and inner.endswith(">"):
            inner = inner[len("ARRAY<") : -1]
        if inner.startswith("STRUCT<") and inner.endswith(">"):
            mapping.update(_flatten_types(inner[len("STRUCT<") : -1], f"{path}."))
    return mapping


def _block_for(topology_dir: Path, surface: str) -> str:
    """The DDL column block of ``surface``'s table, read from the delivered script."""
    blocks = _table_blocks((topology_dir / "02_tables.sql").read_text(encoding="utf-8"))
    matches = [fqtn for fqtn in blocks if _TABLE_SUFFIX[surface].search(fqtn)]
    assert len(matches) == 1, f"{surface}: expected exactly one table, got {matches}"
    return blocks[matches[0]]


def _declared_types(topology_dir: Path, surface: str) -> dict[str, str]:
    return _flatten_types(_block_for(topology_dir, surface))


def _audited_paths(declared: dict[str, str], spec: SurfaceSpec) -> list[str]:
    """Declared paths minus the structural containers -- i.e. what the spec must judge.

    São exatamente as colunas que a documentação afirma. Os contêineres estruturais são
    conferidos à parte (conjunto = fecho de prefixos mínimo), porque a spec documenta os
    subcampos e não uma linha para o record que o BigQuery obriga a declarar.
    """
    containers = _prefix_closure(spec)
    return [path for path in declared if path not in containers]


def _spec_children(spec: SurfaceSpec, name: str) -> list[str]:
    return [other for other in spec.names if other.startswith(f"{name}.")]


def _walk_fields(fields: tuple[SpecField, ...]) -> list[SpecField]:
    """Every node of the renderer's spec tree (records and leaves, all depths)."""
    nodes: list[SpecField] = []
    for field in fields:
        nodes.append(field)
        nodes.extend(_walk_fields(field.children))
    return nodes


def _prefix_closure(spec: SurfaceSpec) -> set[str]:
    """Caminhos que a spec NÃO documenta mas que hospedam um caminho documentado.

    É a única coisa que pode existir no DDL além das colunas documentadas: um record que
    o BigQuery obriga a declarar para poder declarar os subcampos documentados.
    """
    documented = spec.emittable_names
    closure: set[str] = set()
    for path in documented:
        segments = path.split(".")
        for cut in range(1, len(segments)):
            prefix = ".".join(segments[:cut])
            if prefix not in documented:
                closure.add(prefix)
    return closure


def _nested_paths(value: Any, prefix: str = "") -> set[str]:
    """Todo caminho pontuado presente num valor JSON (objetos aninhados e listas)."""
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}{key}"
            paths.add(path)
            paths |= _nested_paths(item, f"{path}.")
    elif isinstance(value, list):
        for item in value:
            paths |= _nested_paths(item, prefix)
    return paths


_MISSING = object()


def _resolve(row: dict[str, Any], path: str) -> Any:
    """Resolve a dotted path inside one row; ``_MISSING`` when the field is absent."""
    current: Any = row
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return _MISSING
        current = current[segment]
    return current


def _split_balanced(text: str) -> list[str]:
    """Split a VALUES tuple body on depth-0 commas (parens, brackets, `<...>`, quotes)."""
    parts: list[str] = []
    depth = 0
    in_string = False
    current: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            current.append(char)
            if char == "\\":
                current.append(text[index + 1])
                index += 2
                continue
            if char == "'":
                in_string = False
        elif char == "'":
            in_string = True
            current.append(char)
        elif char in "([{<":
            depth += 1
            current.append(char)
        elif char in ")]}>":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _first_values_tuple(insert_sql: str) -> str:
    """Return the text of the first ``(...)`` VALUES tuple of an INSERT script."""
    body = insert_sql.split("VALUES", 1)[1]
    start = body.index("(")
    depth = 0
    in_string = False
    index = start
    while index < len(body):
        char = body[index]
        if in_string:
            if char == "\\":
                index += 2
                continue
            if char == "'":
                in_string = False
        elif char == "'":
            in_string = True
        elif char in "([{<":
            depth += 1
        elif char in ")]}>":
            depth -= 1
            if depth == 0:
                return body[start : index + 1]
        index += 1
    raise AssertionError("unterminated VALUES tuple")


def _insert_columns(insert_sql: str) -> list[str]:
    match = _INSERT_RE.search(insert_sql)
    assert match is not None, "no INSERT statement found"
    return [name.strip().strip("`") for name in match.group(1).split(",")]


# -- the specs themselves -----------------------------------------------------------


def test_the_three_gcp_billing_specs_have_the_documented_size() -> None:
    for surface, expected in _EXPECTED_COLUMNS.items():
        spec = _spec(surface)
        assert len(spec.columns) == expected, surface
        assert len(spec.names) == expected, surface
        # Toda coluna documentada PERTENCE ao formato (emittable). As três superfícies de
        # billing não têm nenhuma coluna `null-empty`: toda coluna documentada pode
        # receber valor, e é isso que autoriza o DDL a declarar e as linhas a preencher.
        assert spec.emittable_count == expected, surface
        assert spec.generatable_count == expected, surface
        assert spec.null_empty_names == frozenset(), surface
        assert spec.non_emittable_names == frozenset(), surface
        assert spec.unverified == (), surface


def test_detailed_spec_is_the_standard_spec_plus_six_fields() -> None:
    standard = _spec("standard")
    detailed = _spec("detailed")
    assert set(detailed.emittable_names) - set(standard.emittable_names) == _DETAILED_ONLY
    assert set(standard.emittable_names) <= set(detailed.emittable_names)


# -- the schema claim: exact set of documented dotted paths -------------------------


@pytest.mark.parametrize("surface", _SURFACES)
def test_table_columns_are_exactly_the_documented_paths(topology_dir: Path, surface: str) -> None:
    """The delivered DDL declares the documented paths -- no more, no fewer."""
    spec = _spec(surface)
    declared = _declared_types(topology_dir, surface)
    documented = _audited_paths(declared, spec)

    assert declared, f"{surface}: no columns parsed from 02_tables.sql"
    assert set(documented) == set(spec.emittable_names), (
        f"{surface}: DDL/documentation mismatch; "
        f"missing={sorted(set(spec.emittable_names) - set(documented))} "
        f"invented={sorted(set(documented) - set(spec.emittable_names))}"
    )
    assert len(documented) == len(spec.columns) == _EXPECTED_COLUMNS[surface]
    # Nenhum campo não-comprovado: nada do que a spec proíbe (sem contrato, ou registrado
    # como não comprovado) pode aparecer no artefato.
    assert not (set(documented) & spec.forbidden_names), sorted(set(documented) & spec.forbidden_names)

    findings = check(spec, documented)
    assert is_faithful(findings), "\n".join(str(finding) for finding in findings)


@pytest.mark.parametrize("surface", _SURFACES)
def test_top_level_columns_are_the_first_segments_of_the_documented_paths(
    topology_dir: Path, surface: str
) -> None:
    """The top-level view is a DIFFERENT claim from the dotted-path view, and both hold.

    ``26`` top-level names carry the ``71`` documented columns of the standard table: the
    DDL could name every top-level record correctly and still be missing half the
    documentation, which is why the nested level above is the primary comparison.
    """
    spec = _spec(surface)
    declared = _declared_types(topology_dir, surface)
    top_level = {path for path in declared if "." not in path}
    expected = {name.split(".", 1)[0] for name in spec.names}

    assert top_level == expected
    assert len(top_level) == _EXPECTED_TOP_LEVEL[surface]
    assert len(top_level) < len(spec.names)  # the two levels are not the same claim


@pytest.mark.parametrize("surface", _SURFACES)
def test_declared_but_undocumented_columns_are_only_structural_containers(
    topology_dir: Path, surface: str
) -> None:
    """A record the spec documents only through subfields is the only extra allowed.

    The expectation comes from the spec's own path set (its minimal prefix closure), not
    from a literal list of container names, so a spec edit moves both sides at once.
    """
    spec = _spec(surface)
    declared = _declared_types(topology_dir, surface)
    structural = {path for path in declared if path not in spec.emittable_names}
    closure = _prefix_closure(spec)

    assert structural == closure, (
        f"{surface}: only the minimal prefix closure may be synthesized; "
        f"extra={sorted(structural - closure)} unused={sorted(closure - structural)}"
    )
    # Each structural container is a synthesized record in the renderer's own tree: it
    # hosts documented subfields and is never `documented=True`.
    tree = {field.name: field for field in _walk_fields(fields_for(surface))}
    for name in sorted(structural):
        field = tree[name]
        assert field.documented is False, name
        assert field.children, name
    # Every node the spec DOES document stays documented (no silent synthesis).
    for field in _walk_fields(fields_for(surface)):
        if field.name in spec.emittable_names:
            assert field.documented is True, field.name


@pytest.mark.parametrize("surface", _SURFACES)
def test_required_documented_columns_are_declared(topology_dir: Path, surface: str) -> None:
    spec = _spec(surface)
    declared = set(_declared_types(topology_dir, surface))
    for name in spec.required_names:
        assert name in declared, f"{surface}: required column {name!r} missing from the DDL"


@pytest.mark.parametrize("surface", _SURFACES)
def test_declared_types_follow_the_documented_type(topology_dir: Path, surface: str) -> None:
    """A documented type maps to exactly one DDL type -- the mapping is not optional."""
    spec = _spec(surface)
    declared = _declared_types(topology_dir, surface)
    for column in spec.columns:
        declared_type = declared[column.name]
        children = _spec_children(spec, column.name)
        if children:
            # Um record: o DDL declara STRUCT<...>; se o campo é repetido (tipo "List of
            # structs"/"Array of Strings" na spec, ou um dos records repetidos fixados),
            # o DDL o envolve em ARRAY<...>.
            if column.type in {"List of structs", "Array of Strings"} or declared_type.startswith("ARRAY<"):
                assert declared_type.startswith("ARRAY<STRUCT<"), f"{surface}:{column.name}"
            else:
                assert declared_type.startswith("STRUCT<"), f"{surface}:{column.name}"
        elif column.type in _BQ_SCALAR_TYPES:
            assert declared_type == _BQ_SCALAR_TYPES[column.type], f"{surface}:{column.name}"
        elif column.type == "Array of Strings":
            assert declared_type == "ARRAY<STRING>", f"{surface}:{column.name}"
        else:
            # Um record que a spec lista SEM subcampos: o BigQuery não declara STRUCT<>
            # e nenhum subcampo pode ser inventado, então ele fica como folha opaca.
            assert declared_type != "STRUCT<>", f"{surface}:{column.name}"
            assert declared_type in {"STRING", "ARRAY<STRING>"}, f"{surface}:{column.name}"


@pytest.mark.parametrize("surface", _SURFACES)
def test_opaque_records_are_exactly_the_fieldless_records_the_spec_cannot_enumerate(
    topology_dir: Path, surface: str
) -> None:
    """The leaf rendering of a fieldless record is pinned to the spec's own gaps."""
    spec = _spec(surface)
    fieldless = {
        column.name
        for column in spec.columns
        if column.type in {"Struct", "List of structs"} and not _spec_children(spec, column.name)
    }
    tree_opaque = {field.name for field in _walk_fields(fields_for(surface)) if field.is_opaque_record}
    assert tree_opaque == fieldless, surface

    declared = _declared_types(topology_dir, surface)
    for name in sorted(fieldless):
        assert declared[name] in {"STRING", "ARRAY<STRING>"}, f"{surface}:{name}"
        # A lacuna está registrada como TÓPICO da própria spec (subcampos não enumerados),
        # que é a razão de o campo existir sem estrutura inventada.
        assert any(
            name in topic.name or name in (topic.reason or "") for topic in spec.unverified_topics
        ), f"{surface}:{name} is not recorded as a spec gap"


def test_pinned_repeated_records_are_documented_records_with_subfields(topology_dir: Path) -> None:
    """The repeated-record set is pinned (the spec's `type` cannot express REPEATED)."""
    from tools.synthetic_clouds.render.gcp_bigquery_topology import _REPEATED_RECORDS

    for surface in ("standard", "detailed"):
        spec = _spec(surface)
        declared = _declared_types(topology_dir, surface)
        undocumented = _REPEATED_RECORDS - set(spec.names)
        assert not undocumented, f"{surface}: pinned repeated records not in the spec: {undocumented}"
        for name in sorted(_REPEATED_RECORDS):
            column = next(column for column in spec.columns if column.name == name)
            assert column.type in {"Struct", "List of structs"}, f"{surface}:{name}"
            assert _spec_children(spec, name), f"{surface}:{name} has no documented subfields"
            assert declared[name].startswith("ARRAY<STRUCT<"), f"{surface}:{name}"


# -- the row artifacts: real files read with the fidelity core ----------------------


@pytest.mark.parametrize("surface", ["standard", "detailed"])
def test_row_artifacts_carry_exactly_the_documented_fields(
    topology_dir: Path, surface: str
) -> None:
    spec = _spec(surface)
    row_file = topology_dir / _ROW_FILE[surface]
    rows = json.loads(row_file.read_text(encoding="utf-8"))
    assert rows, f"{surface}: no rows emitted"

    # ``columns_of`` reads the REAL file: the top-level fields it carries.
    top_level = set(columns_of(row_file))
    expected_top = {name.split(".", 1)[0] for name in spec.names}
    assert top_level == expected_top, (
        f"{surface}: top-level fields differ; missing={sorted(expected_top - top_level)} "
        f"extra={sorted(top_level - expected_top)}"
    )

    declared = set(_declared_types(topology_dir, surface))
    for row in rows:
        paths = _nested_paths(row)
        assert paths <= declared, (
            f"{surface}: a row carries a field the DDL does not declare: "
            f"{sorted(paths - declared)}"
        )
        assert not [key for key in paths if key.startswith("_")], f"{surface}: internal key leaked"
        for name in spec.required_names:
            assert _resolve(row, name) is not _MISSING, (
                f"{surface}: required field {name!r} missing from a row"
            )
        # Nenhum caminho emitido pode estar fora do que a spec autoriza a EXISTIR.
        assert paths <= set(spec.emittable_names) | _prefix_closure(spec)
        assert not (paths & spec.forbidden_names), sorted(paths & spec.forbidden_names)


@pytest.mark.parametrize("surface", ["standard", "detailed"])
def test_null_empty_columns_would_be_delivered_empty(topology_dir: Path, surface: str) -> None:
    """``evidence: null-empty`` columns belong to the format and must carry no value.

    Vacuously true on the three billing surfaces (the spec declares none), and deliberately
    written so that it becomes a live failure the moment one appears.
    """
    spec = _spec(surface)
    rows = json.loads((topology_dir / _ROW_FILE[surface]).read_text(encoding="utf-8"))
    for name in sorted(spec.null_empty_names):
        for row in rows:
            value = _resolve(row, name)
            assert value is not _MISSING, f"{surface}: {name} pertence ao formato mas sumiu"
            assert value in ("", None, [], {}), f"{surface}: {name} tem valor: {value!r}"


# -- column list and VALUES cannot drift apart --------------------------------------


@pytest.mark.parametrize(
    ("surface", "script"),
    [
        ("standard", "03_insert_standard.sql"),
        ("detailed", "04_insert_resource.sql"),
        ("pricing", "05_insert_pricing.sql"),
    ],
)
def test_insert_columns_match_the_ddl_top_level_order(topology_dir: Path, surface: str, script: str) -> None:
    """The INSERT column list is the DDL's top-level columns, in the DDL's order."""
    ddl_columns = [path for path in _declared_types(topology_dir, surface) if "." not in path]
    insert_sql = (topology_dir / script).read_text(encoding="utf-8")
    assert _insert_columns(insert_sql) == ddl_columns

    # E a tupla de VALUES tem exatamente aquela quantidade de expressões de topo: uma
    # lista de colunas desalinhada dos valores grava a coluna errada sem erro de SQL.
    first_row = _first_values_tuple(insert_sql)
    assert len(_split_balanced(first_row[1:-1])) == len(ddl_columns)


def test_only_the_documented_tables_are_audited_and_the_rest_is_named(topology_dir: Path) -> None:
    """Every provisioned table is either spec-audited or explicitly out of scope."""
    blocks = _table_blocks((topology_dir / "02_tables.sql").read_text(encoding="utf-8"))
    audited = {surface for surface in _SURFACES if any(_TABLE_SUFFIX[surface].search(fqtn) for fqtn in blocks)}
    assert audited == set(_SURFACES)

    unspecified = [
        fqtn
        for fqtn in blocks
        if not any(_TABLE_SUFFIX[surface].search(fqtn) for surface in _SURFACES)
    ]
    assert unspecified, "expected the invoice/CUD/FOCUS tables to be present"
    for fqtn in unspecified:
        assert any(fqtn.endswith(suffix) for suffix in _UNSPECIFIED_TABLES) or ".gcp_billing_export_focus_" in fqtn, (
            f"{fqtn} has no spec and is not declared out of scope"
        )


def test_topology_directory_keeps_metadata_out_of_the_export_tree(topology_dir: Path) -> None:
    """Metadata lives in a ``_``-prefixed sibling report, never inside the export tree.

    The auditor unions the top-level keys of every non-``_`` file in a surface's directory
    against the spec, so a ``manifest.json`` sitting next to the rows was -- correctly --
    reported as 8 invented columns (``schema_specs``, ``todo_verificar``, ``tables`` …).
    This pins the convention and the filename, so the report cannot drift back inside.
    """
    specs = [_spec(surface) for surface in _SURFACES]
    allowed = set().union(*(set(spec.names) for spec in specs))
    structural = set().union(*(_prefix_closure(spec) for spec in specs))

    assert not (topology_dir / "manifest.json").exists()
    assert PROVENANCE_FILENAME.startswith("_")
    assert (topology_dir / PROVENANCE_FILENAME).is_file()

    for path in sorted(topology_dir.glob("*")):
        if not path.is_file() or path.name.startswith("_") or path.suffix not in {".json", ".jsonl"}:
            continue
        emitted = set(columns_of(path))
        assert emitted <= allowed | structural, (path.name, sorted(emitted - allowed - structural))


def test_pricing_rows_close_the_documented_join(topology_dir: Path, estate: CanonicalEstate) -> None:
    """``sku.id`` é a CHAVE da junção documentada: uso -> preço, nas duas tabelas de uso.

    A spec de pricing declara ``sku.id`` como chave de junção ("Identificador único do SKU
    de recurso usado pelo serviço", ex. ``2E27-4F75-95CD``) e o canho é o MESMO nas três
    tabelas. Sem este teste, a próxima mudança reabre o buraco em silêncio -- foi assim que
    a categoria de serviço (``Compute``) fundiu SKUs distintos numa linha de preço.

    Linha sem SKU (a de imposto, que não tem recurso) não tem ``sku.id`` e não junta
    ninguém: o que se compara é o conjunto NÃO VAZIO das tabelas de uso.
    """
    from tools.synthetic_clouds.model.identity import gcp_sku_id

    usage = {
        row["sku"]["id"]
        for row in json.loads((topology_dir / "08_rows_standard.json").read_text(encoding="utf-8"))
    } | {
        row["sku"]["id"]
        for row in json.loads((topology_dir / "09_rows_resource.json").read_text(encoding="utf-8"))
    }
    usage.discard("")
    pricing_rows = json.loads((topology_dir / _PRICING_ROW_FILE).read_text(encoding="utf-8"))
    pricing = {row["sku"]["id"] for row in pricing_rows}

    assert usage, "no usage row carries a sku.id"
    assert "" not in pricing, "a pricing row without sku.id cannot be joined by anyone"
    assert usage <= pricing, f"sku.id fora da tabela de preço: {sorted(usage - pricing)}"
    # Aqui a modelagem permite IGUALDADE: o catálogo cobre todo SKU que os recursos usam.
    assert usage == pricing, f"preço sem uso: {sorted(pricing - usage)}"

    # E o valor é o canho do SKU do recurso, não a categoria de serviço.
    expected = {
        gcp_sku_id(estate.seed, resource.sku_id)
        for resource in estate.resources
        if resource.identity.provider == "gcp" and resource.sku_id
    }
    assert usage == expected
    assert not (usage & {"Compute", "Storage", "Networking", "Databases", "Analytics"})


def test_usage_rows_carry_the_minted_sku_id_not_the_service_category(
    topology_dir: Path, estate: CanonicalEstate
) -> None:
    """Cada linha de uso traz o canho do SKU do SEU recurso (não a categoria de serviço)."""
    import tools.synthetic_clouds.render.gcp_bigquery_topology as mod
    from tools.synthetic_clouds.model.identity import gcp_sku_id

    resources = {resource.identity.uuid: resource for resource in estate.resources}
    rows = json.loads((topology_dir / "08_rows_standard.json").read_text(encoding="utf-8"))
    lines = mod._gcp_lines(estate)

    assert len(rows) >= len(lines)
    for line, row in zip(lines, rows, strict=False):
        resource = resources.get(line.resource_uuid or "")
        assert resource is not None
        assert row["sku"]["id"] == gcp_sku_id(estate.seed, resource.sku_id or "")
        assert row["sku"]["id"] != line.service_category


def test_sku_description_is_never_the_service_category(topology_dir: Path) -> None:
    """A categoria não é descrição de SKU: a coluna fica AUSENTE, não preenchida com ela.

    A doc pede a descrição do TIPO DE RECURSO (ex.: ``Standard Storage US``). O estado
    modela o token do SKU (identificador), o nome do serviço e a categoria -- nenhum é essa
    descrição. Repetir a categoria ali era a fonte errada, e ela está nomeada em
    ``model_gaps`` com o motivo.
    """
    from tools.synthetic_clouds.render.gcp_bigquery_topology import model_gaps

    categories = {"Compute", "Storage", "Networking", "Databases", "Analytics"}
    for surface, row_file in (("standard", "08_rows_standard.json"), ("detailed", "09_rows_resource.json")):
        rows = json.loads((topology_dir / row_file).read_text(encoding="utf-8"))
        for row in rows:
            assert row["sku"].get("description", "") == ""
            assert row["sku"].get("description", "") not in categories
        assert "sku.description" in model_gaps(surface)


def test_numbers_without_a_source_are_null_not_zero(topology_dir: Path) -> None:
    """Ausência numérica é ``NULL``, não ``0.0``: zero é preço "de graça" para o consumidor.

    O núcleo de fidelidade trata zero como valor legítimo (``is_empty_value``), então o
    placeholder antigo (``0.0``) fazia uma coluna sem fonte PARECER preenchida -- e um
    consumidor que soma preços lia zero. Onde zero/um é o valor real (faixa única começa em
    0; preço por 1 unidade) ele É projetado, e isso é asserido à parte.
    """
    rows = json.loads((topology_dir / "08_rows_standard.json").read_text(encoding="utf-8"))
    priced = [row for row in rows if row["price"]["list_price"]]
    assert priced, "nenhuma linha com preço de catálogo"
    for row in priced:
        # valores reais: o preço de tabela/contrato do SKU e a faixa única
        assert row["price"]["list_price"] > 0
        assert row["price"]["tier_start_amount"] == 0.0  # zero REAL (faixa única)
        assert row["price"]["pricing_unit_quantity"] == 1.0  # um REAL (preço por 1 unidade)
    # Ausência de verdade: a linha de imposto não tem uso medido nem preço de SKU.
    tax_rows = [row for row in rows if row["cost_type"] == "tax"]
    assert tax_rows
    for row in tax_rows:
        assert row["usage"]["amount"] is None
        assert row["usage"]["amount_in_pricing_units"] is None
        assert row["price"]["list_price"] is None
        assert row["cost_at_effective_price_default"] is None


def test_pricing_rows_carry_the_modelled_price(topology_dir: Path, estate: CanonicalEstate) -> None:
    """O preço do catálogo chega ao artefato pela faixa documentada, com a conversão."""
    import tools.synthetic_clouds.render.gcp_bigquery_topology as mod
    from tools.synthetic_clouds.model.identity import gcp_sku_id

    rows = json.loads((topology_dir / _PRICING_ROW_FILE).read_text(encoding="utf-8"))
    sources = mod._value_sources(estate)
    assert rows
    for row in rows:
        assert row["billing_account_id"]
        assert row["business_entity_name"] == "GCP"
        assert row["pricing_as_of_time"] and row["export_time"]
        assert row["account_currency_code"] == estate.currency
        assert row["currency_conversion_rate"] == "1.0"  # doc: 1.0 quando a moeda é USD
        assert row["aggregation_info"]["aggregation_level"] == "UNKNOWN_AGGREGATION_LEVEL"
        assert row["aggregation_info"]["aggregation_interval"] == "UNKNOWN_AGGREGATION_INTERVAL"
        tiers = row["tiered_rates"]
        assert len(tiers) == 1, "catálogo do estado é faixa única"
        tier = tiers[0]
        assert tier["start_usage_amount"] == 0.0
        assert tier["pricing_unit_quantity"] == 1.0
        assert tier["usd_amount"] == pytest.approx(tier["account_currency_amount"])  # taxa 1.0
        # e o valor é o preço do catálogo do SKU correspondente
        sku_id = next(sku for sku in sources.service_by_sku if gcp_sku_id(estate.seed, sku) == row["sku"]["id"])
        assert tier["usd_amount"] == pytest.approx(float(sources.list_price_by_sku[sku_id]), abs=1e-6)
        assert row["pricing_unit"] == sources.sku_unit_by_sku[sku_id]
        assert row["service"]["id"] == sources.service_by_sku[sku_id]


def test_a_null_empty_column_is_declared_but_never_filled() -> None:
    """``evidence: null-empty``: pertence ao formato (DDL) e nunca recebe valor.

    As três superfícies de billing não têm nenhuma coluna assim hoje, então o contrato é
    provado no mecanismo do renderer: a coluna aparece no DDL, a linha a emite como
    ``None`` (NULL no SQL) e projetar um valor nela levanta em vez de gravar.
    """
    from tools.synthetic_clouds.render.base import RenderError
    from tools.synthetic_clouds.render.gcp_bigquery_topology import SpecField, build_row, ddl_columns, row_values

    field = SpecField(name="never_filled", type="String", children=(), repeated=False, documented=True, null_empty=True)
    assert ddl_columns((field,)).strip() == "never_filled STRING"  # pertence ao formato
    assert build_row((field,), {}) == {"never_filled": None}
    assert row_values({"never_filled": None}, (field,)) == "(NULL)"
    with pytest.raises(RenderError, match="null-empty"):
        build_row((field,), {"never_filled": "invented"})


# -- the provenance report carries the audited counts --------------------------------


def test_provenance_report_schema_counts_match_the_specs(topology_dir: Path) -> None:
    manifest = json.loads((topology_dir / PROVENANCE_FILENAME).read_text(encoding="utf-8"))
    for surface in _SURFACES:
        entry = manifest["schema_specs"][surface]
        spec = _spec(surface)
        assert entry["columns"] == len(spec.columns), surface
        assert entry["top_level"] == len({name.split(".", 1)[0] for name in spec.names}), surface
        assert (_REPO_ROOT / entry["spec"]).is_file(), entry["spec"]


# -- the Phase-1 probe renderer declares the same schema ----------------------------


def test_probe_ddl_and_rows_are_the_standard_surface(probe_dir: Path) -> None:
    spec = _spec("standard")
    blocks = _table_blocks((probe_dir / "ddl.sql").read_text(encoding="utf-8"))
    assert len(blocks) == 1, blocks.keys()
    declared = _flatten_types(next(iter(blocks.values())))
    documented = _audited_paths(declared, spec)
    assert set(documented) == set(spec.emittable_names)
    assert {path for path in declared if path not in spec.emittable_names} == _prefix_closure(spec)
    assert is_faithful(check(spec, documented))

    top_level = set(columns_of(probe_dir / "rows.json"))
    assert top_level == {name.split(".", 1)[0] for name in spec.names}


# -- falsification: the comparison must be able to fail -----------------------------


def test_a_fabricated_column_is_denounced(topology_dir: Path) -> None:
    """Anti-vacuity: a column the documentation does not define cannot pass the audit."""
    spec = _spec("standard")
    mutated = _block_for(topology_dir, "standard") + ",\n  net_cost FLOAT64"
    declared = _flatten_types(mutated)
    documented = _audited_paths(declared, spec)

    assert set(documented) != set(spec.emittable_names)  # the exact-set assertion bites
    findings = check(spec, documented)
    assert any(finding.kind == KIND_INVENTED and finding.column == "net_cost" for finding in findings), findings


def test_a_missing_required_column_is_denounced(topology_dir: Path) -> None:
    """Anti-vacuity: dropping a documented required column cannot pass the audit."""
    spec = _spec("standard")
    body = _block_for(topology_dir, "standard")
    without_cost = "\n".join(line for line in body.splitlines() if not line.strip().startswith("cost "))
    declared = _flatten_types(without_cost)
    documented = _audited_paths(declared, spec)

    assert set(documented) != set(spec.emittable_names)
    findings = check(spec, documented)
    assert any(finding.kind == KIND_MISSING and finding.column == "cost" for finding in findings), findings


def test_an_undeclared_but_documented_column_is_denounced(topology_dir: Path) -> None:
    """Anti-vacuity: an optional documented column missing from the DDL is still caught.

    ``check`` only flags REQUIRED absences, so the exact-set assertion is what carries the
    optional ones -- this test proves that comparison is not vacuous.
    """
    spec = _spec("standard")
    body = _block_for(topology_dir, "standard")
    without_tags = "\n".join(line for line in body.splitlines() if not line.strip().startswith("tags "))
    declared = _flatten_types(without_tags)
    documented = _audited_paths(declared, spec)

    assert "tags" in spec.emittable_names  # documented, and NOT required
    assert "tags" not in documented
    assert set(documented) != set(spec.emittable_names)


def test_the_renderers_derive_their_columns_from_the_spec_not_from_a_literal() -> None:
    """The column set is the spec's: changing the spec changes what the DDL declares.

    Proof by construction -- the renderer's tree carries exactly the spec's documented
    paths plus the structural prefix closure, with no hand-written block left to drift.
    """
    for surface in _SURFACES:
        spec = _spec(surface)
        documented = set(field_paths(fields_for(surface))) - _prefix_closure(spec)
        assert documented == set(spec.emittable_names), surface


# -- values: filled from the modelled source, or declared as a gap ------------------


def _spec_json(surface: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((_SPEC_DIR / _SPEC_FILE[surface]).read_text(encoding="utf-8"))
    return payload


def _allowed_values(surface: str) -> dict[str, tuple[str, ...]]:
    """``allowed_values`` declarados pela spec, por caminho (a fonte da verdade)."""
    return {
        column["name"]: tuple(str(value) for value in column["allowed_values"])
        for column in _spec_json(surface)["columns"]
        if column.get("allowed_values")
    }


def _values_at(row: dict[str, Any], path: str) -> list[Any]:
    """Todos os valores do caminho dentro de UMA linha (atravessa listas de structs)."""
    current: list[Any] = [row]
    for segment in path.split("."):
        following: list[Any] = []
        for node in current:
            if isinstance(node, dict) and segment in node:
                following.append(node[segment])
            elif isinstance(node, list):
                following.extend(item[segment] for item in node if isinstance(item, dict) and segment in item)
        current = following
    return current


@pytest.mark.parametrize("surface", _SURFACES)
def test_model_gaps_are_exactly_the_columns_with_no_value(topology_dir: Path, surface: str) -> None:
    """The gap registry is checked in BOTH directions, so it cannot go stale.

    A column absent from the artifact but absent from ``model_gaps`` too would be a silent
    hole; a column listed as a gap but actually filled would be a false excuse.
    """
    from tools.synthetic_clouds.render.gcp_bigquery_topology import model_gaps

    spec = _spec(surface)
    rows = json.loads((topology_dir / _row_file(surface)).read_text(encoding="utf-8"))
    empty = {
        name
        for name in spec.names
        if not any(not is_empty_value(value) for row in rows for value in _values_at(row, name))
    }
    gaps = model_gaps(surface)

    assert set(gaps) == empty, (
        f"{surface}: empty-but-undeclared={sorted(empty - set(gaps))} "
        f"declared-but-filled={sorted(set(gaps) - empty)}"
    )
    assert all(reason.strip() for reason in gaps.values()), "every gap needs a reason"

    report = json.loads((topology_dir / PROVENANCE_FILENAME).read_text(encoding="utf-8"))
    assert set(report["model_gaps"][surface]) == set(gaps)
    assert report["model_gaps_note"]


@pytest.mark.parametrize("surface", _SURFACES)
def test_values_stay_inside_the_documented_allowed_values(topology_dir: Path, surface: str) -> None:
    """Every emitted value of an enumerated column is one of the documented literals."""
    rows = json.loads((topology_dir / _row_file(surface)).read_text(encoding="utf-8"))
    checked = 0
    for path, allowed in _allowed_values(surface).items():
        for row in rows:
            for value in _values_at(row, path):
                if is_empty_value(value):
                    continue
                assert isinstance(value, str) and value in allowed, (
                    f"{surface}:{path} emitiu {value!r}, fora de {allowed}"
                )
                checked += 1
    assert checked, f"{surface}: nenhum valor enumerado emitido -- teste vazio"


def test_optional_columns_are_filled_from_the_modelled_sources(
    topology_dir: Path, estate: CanonicalEstate
) -> None:
    """A coluna com fonte no modelo é preenchida a partir dela, não deixada em placeholder.

    Cada asserção liga a coluna a uma fonte NOMEADA: a hierarquia GCP
    (``project.ancestry_numbers``), o perfil de instância (``location.zone``,
    ``system_labels``/machine_spec), o catálogo de preços do SKU do recurso (``price.*``)
    e os custos contratado/lista da própria linha (``cost_at_*``).
    """
    import tools.synthetic_clouds.render.gcp_bigquery_topology as mod

    rows = json.loads((topology_dir / "08_rows_standard.json").read_text(encoding="utf-8"))
    lines = mod._gcp_lines(estate)
    std_rows = rows[: len(lines)]
    resources = {resource.identity.uuid: resource for resource in estate.resources}
    profiles = {p.resource_uuid: p for p in estate.instance_profiles if p.provider == "gcp"}
    list_prices = {price.sku_id: price.unit_price for price in estate.list_prices}
    contracted = {price.sku_id: price.unit_price for price in estate.contracted_prices}
    ancestry = {
        project.project_id: f"/{org.org_id.rpartition('/')[2]}/{folder.folder_id.rpartition('/')[2]}/"
        for org in estate.gcp_orgs
        for folder in org.folders
        for project in folder.projects
    }

    assert len(std_rows) == len(lines)
    for line, row in zip(lines, std_rows, strict=True):
        assert row["project"]["ancestry_numbers"] == ancestry[line.sub_account_id]

        profile = profiles.get(line.resource_uuid or "")
        zone = ""
        if profile is not None and profile.zone and line.region_id:
            if profile.zone.startswith(f"{line.region_id}-"):
                zone = profile.zone
        assert row["location"]["zone"] == zone
        assert row["location"]["location"] == (zone or line.region_id)
        assert row["location"]["region"] == line.region_id  # M1 (consumidor de produção)

        if profile is not None and profile.instance_type:
            assert row["system_labels"] == [
                {"key": "compute.googleapis.com/machine_spec", "value": profile.instance_type}
            ]
        else:
            assert row["system_labels"] == []

        resource = resources.get(line.resource_uuid or "")
        sku_id = resource.sku_id if resource is not None else None
        if sku_id in list_prices:
            assert row["price"]["list_price"] == pytest.approx(float(list_prices[sku_id]), abs=1e-6)
            assert row["price"]["list_price_consumption_model"] == pytest.approx(
                float(list_prices[sku_id]), abs=1e-6
            )
        if sku_id in contracted:
            assert row["price"]["effective_price_default"] == pytest.approx(
                float(contracted[sku_id]), abs=1e-6
            )
            assert row["price"]["effective_price"] == pytest.approx(float(contracted[sku_id]), abs=1e-6)

        assert row["cost_at_effective_price_default"] == pytest.approx(float(line.contracted_cost), abs=1e-6)
        assert row["cost_at_list_consumption_model"] == pytest.approx(float(line.list_cost), abs=1e-6)

    # As fontes são reais, não um caminho morto: existe linha zonal, linha com machine_spec
    # e o catálogo cobre todo SKU referenciado.
    assert any(row["location"]["zone"] for row in std_rows)
    assert any(row["system_labels"] for row in std_rows)
    assert all(row["price"]["list_price"] for row in std_rows)
    assert all(row["price"]["effective_price_default"] for row in std_rows)
