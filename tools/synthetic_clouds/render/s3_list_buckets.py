"""AWS S3 ``ListBuckets`` renderer -- a lista de buckets de uma CONTA.

Projects the canonical estate's bucket postures into the **14 documented fields** of
``specs/aws/s3-list-buckets.schema.json`` -- os 4 elementos de topo de
``ListAllMyBucketsResult``, os 4 membros de ``Bucket``, os 2 de ``Owner`` e os 4 parametros
documentados da requisicao.

WHY THIS SURFACE IS ACCOUNT-SCOPED
----------------------------------
The other three Increment 3 surfaces are per bucket. This one is not, and the difference is
documented: the action "returns a list of all buckets owned by the authenticated sender of
the request", and the bucket's own region travels INSIDE the ``Bucket`` object
(``BucketRegion``). So one artifact per account, and never one per (account, region) --
which would count the same bucket set once per region.

WHAT STAYS EMPTY, AND WHY
-------------------------
``BucketArn`` is null. The ``Bucket`` page restricts it outright: "This parameter is only
supported for S3 directory buckets." The estate has general purpose buckets, for which the
action publishes no ARN, and inventing one would assert a fact the documentation withholds.
``ContinuationToken`` and ``Prefix`` are null because the estate's accounts fit in a single
page and no prefix filter was applied -- a pagination fact, not a refusal to model one.
The whole ``request-parameters`` set is null because the estate models no captured request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.storage import AwsBucketPosture
from tools.synthetic_clouds.render import s3_posture as shared

SURFACE = "aws/s3-list-buckets"
RENDER_DIR = "s3_list_buckets"

RESPONSE_SCOPE = "list-buckets-response"
BUCKET_SCOPE = "bucket"
OWNER_SCOPE = "owner"
REQUEST_SCOPE = "request-parameters"

_KEY = "s3_list_buckets"

_RESPONSE_COLUMNS = shared.names_of(_KEY, RESPONSE_SCOPE)
_BUCKET_COLUMNS = shared.names_of(_KEY, BUCKET_SCOPE)
_OWNER_COLUMNS = shared.names_of(_KEY, OWNER_SCOPE)
_REQUEST_COLUMNS = shared.names_of(_KEY, REQUEST_SCOPE)

#: The model facts each set may project. A non-null value anywhere else is a value the
#: canonical model does not carry, and ``require_projection`` fails closed on it.
_RESPONSE_PROJECTED: frozenset[str] = frozenset({"Buckets", "Owner"})
_BUCKET_PROJECTED: frozenset[str] = frozenset({"BucketRegion", "CreationDate", "Name"})
_OWNER_PROJECTED: frozenset[str] = frozenset({"ID"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()


def specification() -> SurfaceSpec:
    """Return the cited specification for ``aws/s3-list-buckets``."""
    return shared.specification(_KEY)


def _owner(posture: AwsBucketPosture) -> dict[str, Any]:
    """Return the documented 2-member ``Owner`` of one bucket's account."""
    record: dict[str, Any] = {
        "DisplayName": posture.owner.display_name,
        "ID": posture.owner.id,
    }
    shared.require_projection(_KEY, record, _OWNER_COLUMNS, _OWNER_PROJECTED, "Owner")
    return record


def _bucket(posture: AwsBucketPosture) -> dict[str, Any]:
    """Return the documented 4-member ``Bucket`` of one bucket.

    ``BucketArn`` goes out null: the ``Bucket`` page supports it for directory buckets
    only, and every bucket in this estate is a general purpose one.
    """
    record: dict[str, Any] = {
        "BucketArn": None,
        "BucketRegion": posture.region_id,
        "CreationDate": posture.creation_date,
        "Name": posture.bucket_name,
    }
    shared.require_projection(_KEY, record, _BUCKET_COLUMNS, _BUCKET_PROJECTED, "Bucket")
    return record


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as an all-null SHAPE fixture.

    These four names belong to the REQUEST side of the action; the estate models no
    captured request, so every value is null. The document exists so the request
    vocabulary is present and distinguishable from an omission.
    """
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    shared.require_projection(_KEY, document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "forma de request-parameters")
    return document


class S3ListBucketsRenderer:
    """Renders the canonical estate's AWS buckets, one artifact per ACCOUNT."""

    name = "s3_list_buckets"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/s3_list_buckets/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_account = shared.postures_by_account(estate)

        responses: list[dict[str, Any]] = []
        buckets: list[dict[str, Any]] = []
        owners: list[dict[str, Any]] = []

        for _account_id, scope_postures in by_account.items():
            # O owner e o MESMO para todos os buckets da conta -- e o que a acao publica, que
            # traz um unico Owner no topo. Guardar um por resposta (e nao um por bucket) evita
            # que o consumidor encontre N donos para a mesma conta.
            owner = _owner(scope_postures[0])
            scope_records = [_bucket(posture) for posture in scope_postures]
            buckets.extend(scope_records)
            owners.append(owner)
            response: dict[str, Any] = {
                "Buckets": scope_records,
                "ContinuationToken": None,
                "Owner": owner,
                "Prefix": None,
            }
            shared.require_projection(_KEY, response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")
            responses.append(response)

        shared.write_json(target / "list-buckets-response.json", responses, written)
        shared.write_json(target / "bucket.json", buckets, written)
        shared.write_json(target / "owner.json", owners, written)
        shared.write_json(target / "request-parameters.json", _request_parameters(), written, sort_keys=True)
        shared.write_provenance(target, self._provenance(estate, by_account), written)
        return written

    def _provenance(
        self, estate: CanonicalEstate, by_account: dict[str, list[AwsBucketPosture]]
    ) -> dict[str, Any]:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps."""
        spec = specification()
        return shared.provenance_payload(
            surface=SURFACE,
            renderer=self.name,
            spec=spec,
            mechanism={
                "kind": "read_api",
                "format": "xml",
                "artifact_format": "json",
                "scope": "account",
                "scope_note": (
                    "A acao lista os buckets do remetente da requisicao e a regiao de cada bucket "
                    "vem DENTRO do objeto Bucket (BucketRegion). O escopo e a conta, e nao "
                    "(conta, regiao): um artefacto por regiao contaria o mesmo conjunto de "
                    "buckets uma vez por regiao."
                ),
                "permission": spec.reference.get("permission"),
                "permission_note": spec.reference.get("permission_note"),
            },
            counts={
                "accounts": len(by_account),
                "responses": len(by_account),
                "buckets": sum(len(items) for items in by_account.values()),
                "owners": len(by_account),
            },
            derived={
                "CreationDate": (
                    "DERIVADA. Um bucket nao e medido -- s3_bucket esta entre os tipos que o "
                    "estate nao fatura -- entao nao ha linha de consumo de onde a data viesse. "
                    "A data e derivada do resource_uuid num intervalo fixo e anterior a janela "
                    "de simulacao, para ser estavel entre execucoes. Nao e um timestamp emitido "
                    "pela AWS."
                ),
                "owner.ID": (
                    "DERIVADO. O ID canonico do dono e derivado do id da conta, para que o "
                    "owner desta resposta e o owner que GetBucketAcl publica para o mesmo "
                    "bucket sejam o mesmo valor. A resposta de exemplo da acao mostra o "
                    "formato de ID de conta AWS (AIDACKCEVSQ6C2EXAMPLE); o estado usa um hex "
                    "de 64 caracteres, que e o formato que a resposta de exemplo do "
                    "GetBucketAcl mostra."
                ),
                "order": (
                    "Os buckets sao ordenados por nome. Nenhuma das respostas de exemplo da "
                    "pagina esta em ordem alfabetica e a pagina nao declara ordenacao: a "
                    "ordem aqui e determinismo do gerador, nao uma afirmacao sobre o servico."
                ),
            },
            gaps={
                "BucketArn": (
                    "NULO POR CONTRATO. A pagina do tipo Bucket diz 'This parameter is only "
                    "supported for S3 directory buckets.' Todo bucket do estado e de uso geral, "
                    "portanto a acao nao publica ARN para ele. Preencher seria inventar."
                ),
                "ContinuationToken": (
                    "NULO POR PAGINACAO. A conta inteira cabe em uma pagina (25 buckets, bem "
                    "abaixo da cota padrao de 10.000 que a pagina cita como limite de "
                    "listagem sem paginacao)."
                ),
                "Prefix": "NULO POR REQUISICAO. Nenhuma listagem foi filtrada por prefixo.",
                "Owner.DisplayName": (
                    "NULO POR MODELO. O estate nao modela um nome de exibicao de conta; a "
                    "resposta de exemplo da propria acao tambem traz so <ID>."
                ),
                "request-parameters": (
                    "VAZIO POR MODELO. Os quatro nomes pertencem ao lado da REQUISICAO e o "
                    "estado nao modela nenhuma requisicao capturada. A forma existe; o valor "
                    "nao."
                ),
            },
            rules_read={
                "s3-bucket-level-public-access-prohibited": (
                    "Esta regra e de NIVEL DE BUCKET e nao de conta, entao a listagem de conta "
                    "nao a responde. Ela le os fatos de GetPublicAccessBlock, GetBucketPolicy "
                    "e GetBucketAcl -- as outras tres superficies deste Incremento 3."
                )
            },
        )