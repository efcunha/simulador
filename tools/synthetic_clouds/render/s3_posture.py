"""OShared plumbing das QUATRO superficies de postura de bucket do Incremento 3.

As superficies ``s3-list-buckets``, ``s3-get-bucket-acl``, ``s3-get-bucket-policy`` e
``s3-get-public-access-block`` leem a MESMA colecao -- :class:`Estate.aws_bucket_postures` --
e por isso compartilham o carregamento de spec, o guarda de projecao, a escrita e a
proveniencia. O que NAO e compartilhado fica no modulo de cada superficie: o que cada uma
projeta, como ordena e o que declara como derivado.

Este modulo NAO e um renderer: ele nao define classe alguma, entao a varredura de
``render/base.py`` o ignora. Ele existe pelo mesmo motivo de ``render/markers.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.model.storage import AwsBucketPosture
from tools.synthetic_clouds.render.base import RenderError

#: As quatro superficies do Incremento 3, pelo nome do arquivo de spec de cada uma.
SPEC_FILES = {
    "s3_list_buckets": "s3-list-buckets.schema.json",
    "s3_get_bucket_acl": "s3-get-bucket-acl.schema.json",
    "s3_get_bucket_policy": "s3-get-bucket-policy.schema.json",
    "s3_get_public_access_block": "s3-get-public-access-block.schema.json",
}

_SPECS_ROOT = Path(__file__).resolve().parents[3] / "specs" / "aws"

_specs: dict[str, SurfaceSpec] = {}


def specification(key: str) -> SurfaceSpec:
    """Load (once) the cited specification of one Increment 3 surface."""
    spec = _specs.get(key)
    if spec is None:
        spec = load_spec(_SPECS_ROOT / SPEC_FILES[key])
        _specs[key] = spec
    return spec


def names_of(key: str, scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    A column the documentation describes without contracting it must never reach an
    artifact, and a documented column must never be dropped: both are hard errors.
    """
    columns = specification(key).columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"{key}: o conjunto {scope!r} da especificacao marcou colunas documentadas como "
            f"fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


def names_of_uncontracted(key: str, scope: str) -> tuple[str, ...]:
    """Return a set's column names for a set that is EXPLICITLY not contractual.

    The inverse guard of :func:`names_of`, and it exists because that one is not enough.

    ``names_of`` refuses a set with any column outside the schema -- which is right for the
    four contracted sets and wrong for a set that is ADMITTED to be uncontractual, like
    ``regional-access-block-configuration``. Passing such a set through ``names_of`` would
    force two bad options: drop the columns (and emit an empty artifact that proves nothing),
    or mark them verified (and turn "nobody checked this against a page" into a claim that
    somebody did).

    So the rule is symmetric, and both sides fail closed:

    * a set that claims to be CONTRACTUAL must be entirely verified (:func:`names_of`);
    * a set that claims to be NON-CONTRACTUAL must be entirely unverified (here).

    A set with a mix is refused, because a mix is the thing that actually hides: half-verified
    shapes read as fully verified ones.
    """
    columns = specification(key).columns_for(scope)
    comprovadas = tuple(column.name for column in columns if column.belongs_to_schema)
    if comprovadas:
        raise RenderError(
            f"{key}: o conjunto {scope!r} foi declarado NAO contratual, mas carrega colunas "
            f"marcadas como comprovadas: {list(comprovadas)}. Um conjunto nao comprovado nao "
            f"pode ter partes comprovadas -- a mistura e o que esconde."
        )
    return tuple(column.name for column in columns)


def is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for False).

    ``False`` is a REAL value here: three of the four ``PublicAccessBlock`` members are
    legitimately false on a configured bucket, so treating ``False`` as empty would erase
    the posture a Config rule reads.
    """
    return value is None or value == "" or value == {} or value == []


def require_projection(
    key: str,
    record: dict[str, Any],
    columns: tuple[str, ...],
    projected: frozenset[str],
    where: str,
) -> None:
    """Fail closed when a document is not exactly the set's members, or fills a gap.

    Two failures: a divergent member set (a documented member dropped, or a key no
    documentation defines) and a non-null value outside the model-backed ``projected``
    names. The second is the fabrication rule of this package expressed in code.
    """
    fields = set(record)
    expected = set(columns)
    if fields != expected:
        raise RenderError(
            f"{key}: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    null_empty = specification(key).null_empty_names
    filled = sorted(name for name in null_empty & fields if not is_empty(record[name]))
    if filled:
        raise RenderError(f"{key}: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not is_empty(record[name]) and name not in projected)
    if invented:
        raise RenderError(
            f"{key}: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def write_text(path: Path, text: str, written: list[Path]) -> None:
    """Write one artifact as UTF-8 and record it exactly once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)


def write_json(path: Path, payload: Any, written: list[Path], sort_keys: bool = False) -> None:
    """Write one JSON artifact, newline-terminated, so a rebuild is byte-identical."""
    write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=sort_keys) + "\n", written)


def postures_by_scope(
    estate: CanonicalEstate,
) -> tuple[dict[tuple[str, str], list[AwsBucketPosture]], dict[str, Resource]]:
    """Group the estate's AWS bucket postures by (account, region), deterministically.

    One group per (account, region) because that is the scope of a per-bucket S3 read: a
    bucket belongs to one account in one region, so one account's buckets in three regions
    are three answers, not one. This is the same granularity ``render/ec2_security_groups.py``
    uses for the same reason.

    The resource index comes back with it because the posture is keyed by
    ``resource_uuid`` and a posture with no resource behind it would let a renderer name a
    bucket the estate does not have.
    """
    by_uuid = {resource.identity.uuid: resource for resource in estate.resources}
    grouped: dict[tuple[str, str], list[AwsBucketPosture]] = {}
    for posture in estate.aws_bucket_postures:
        resource = by_uuid.get(posture.resource_uuid)
        if resource is None:
            raise RenderError(
                f"bucket {posture.bucket_name!r} tem postura apontando para "
                f"{posture.resource_uuid!r}, que nao e recurso do estate (FK orfa)"
            )
        if resource.identity.provider != PROVIDER_KEY_AWS:
            raise RenderError(
                f"bucket {posture.bucket_name!r} pertence a um recurso "
                f"{resource.identity.provider!r}, que nao e AWS"
            )
        if resource.resource_type != "s3_bucket":
            raise RenderError(
                f"postura do bucket {posture.bucket_name!r} aponta para um recurso do tipo "
                f"{resource.resource_type!r}, que nao e s3_bucket"
            )
        grouped.setdefault((posture.account_id, resource.region_id), []).append(posture)
    return (
        {
            scope: sorted(items, key=lambda item: item.bucket_name)
            for scope, items in sorted(grouped.items())
        },
        by_uuid,
    )


def postures_by_account(estate: CanonicalEstate) -> dict[str, list[AwsBucketPosture]]:
    """Group the estate's bucket postures by ACCOUNT, deterministically.

    ``ListBuckets`` is the one Increment 3 surface whose scope is the account and not the
    (account, region): the action "returns a list of all buckets owned by the authenticated
    sender of the request", and the region of each bucket travels inside the ``Bucket``
    object. Emitting one artifact per (account, region) would count the same bucket set
    once per region.
    """
    grouped: dict[str, list[AwsBucketPosture]] = {}
    for posture in estate.aws_bucket_postures:
        grouped.setdefault(posture.account_id, []).append(posture)
    return {
        account: sorted(items, key=lambda item: item.bucket_name)
        for account, items in sorted(grouped.items())
    }


def per_bucket_order(
    estate: CanonicalEstate,
) -> tuple[list[AwsBucketPosture], list[dict[str, Any]]]:
    """Return every bucket posture in the ONE order all three per-bucket surfaces use.

    ``GetBucketAcl``, ``GetBucketPolicy`` and ``GetPublicAccessBlock`` are all PER-BUCKET
    calls whose documented response is a single object -- there is no array and no member
    that names the bucket. So each of those artifacts emits one response per bucket, in this
    order, and a consumer joins a response to its bucket by position.

    Attribution by position rather than by an invented ``bucketName`` member is deliberate:
    the documentation publishes no such member on the response, and adding one would be a
    contract this package does not have. The mapping is written explicitly into each
    artifact's provenance under ``response_order``, so the join is discoverable from the
    artifact itself and not only from the code that produced it.

    The order is ``(account, region, bucket name)`` -- account first because that is the
    outermost scope the estate has, name last because that is what makes it total.
    """
    postures = sorted(
        estate.aws_bucket_postures,
        key=lambda posture: (posture.account_id, posture.region_id, posture.bucket_name),
    )
    return (
        postures,
        [
            {"index": index, "account": posture.account_id, "region": posture.region_id, "bucket": posture.bucket_name}
            for index, posture in enumerate(postures)
        ],
    )


def provenance_payload(
    surface: str,
    renderer: str,
    spec: SurfaceSpec,
    mechanism: dict[str, Any],
    counts: dict[str, Any],
    derived: dict[str, Any],
    gaps: dict[str, str],
    rules_read: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Assemble the sibling provenance document shared by the four Increment 3 surfaces.

    The shape is the repository's: ``kind``, ``surface``, ``spec``, ``mechanism``, ``counts``,
    ``columns``, ``model_gaps``, ``not_generated``, ``derivations`` -- the same keys
    ``fidelity/audit_renderers.py`` names when it explains why an ``_``-prefixed report is
    excluded from the exported artifacts. ``rules_read`` is the Increment 3 addition: which
    managed rule consumes each of these facts, so a reader of the report does not have to
    re-derive it.

    The reasons live HERE and not in the artifact: an ingestor of the fixture must not see
    a key no cloud documents. This file is what says which values are derivations and which
    are declared gaps.
    """
    # ``spec.path`` is ``<repo>/specs/aws/<file>``, so parents[2] is the repo root -- NOT
    # parents[3], which is the depth that reaches the root from ``fidelity/spec.py`` itself.
    if spec.path is None:  # pragma: no cover - load_spec sempre anexa o caminho
        raise RenderError(f"{surface}: a especificacao foi carregada sem caminho de origem")
    spec_relative = spec.path.relative_to(spec.path.parents[2]).as_posix()
    # O mapa de ordem sai como CHAVE DE TOPO, e nao como uma derivacao: ele nao explica um
    # valor, ele diz qual resposta do artefato e de qual bucket. Um consumidor precisa poder
    # ler isso sem varrer as razoes.
    response_order = derived.pop("response_order_map", [])
    return {
        "kind": "provenance",
        "surface": surface,
        "spec": spec_relative,
        "renderer": renderer,
        "mechanism": {
            **mechanism,
            "reference": spec.reference.get("url"),
            "consulted_at": spec.reference.get("consulted_at"),
        },
        "counts": counts,
        "columns": {
            column_set.name: [column.name for column in column_set.columns] for column_set in spec.sets
        },
        "response_order": response_order,
        "model_gaps": [{"field": field, "reason": reason} for field, reason in gaps.items()],
        "not_generated": [
            {"column": name, "reason": "coluna documentada que nao pertence ao formato desta superficie"}
            for name in sorted(spec.non_emittable_names)
        ],
        "derivations": [
            {"field": field, "reason": reason} for field, reason in derived.items()
        ],
        "rules_read": rules_read or {},
    }


def write_provenance(target: Path, payload: dict[str, Any], written: list[Path]) -> None:
    """Write the provenance document beside the data, never inside it."""
    write_json(target / "_provenance.json", payload, written)