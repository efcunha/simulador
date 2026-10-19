"""AWS S3 ``GetBucketPolicy`` renderer -- a bucket policy de cada bucket.

Projects the canonical estate's bucket postures into the **11 documented fields** of
``specs/aws/s3-get-bucket-policy.schema.json`` -- o elemento ``Policy``, os 3 membros de
documento, os 5 de statement e os 2 parametros documentados da requisicao.

THIS IS THE ONE INCREMENT-3 SURFACE WHOSE RESPONSE IS REALLY JSON
----------------------------------------------------------------
The other three are documented as XML. This one is not: the Response Syntax is literally
``{ Policy in JSON format }`` and the page states "The following data is returned in JSON
format by the service." So there is no XML-to-JSON divergence to declare here, and there is
also no JSON-schema divergence: the artifact IS the documented format.

WHERE THE DOCUMENT ENDS
-----------------------
The action's Response Elements list has exactly one item, ``Policy``. The members of the
document -- ``Version``, ``Id``, ``Statement``, and ``Sid``, ``Effect``, ``Principal``,
``Action``, ``Resource`` inside a statement -- come from the Sample Response on the same
page, not from a type page. ``Condition`` is a real member of the policy language and does
NOT appear in that example, so it is not emitted and not in the spec; the reason is recorded
in the spec's ``unverified`` so nobody widens the list believing the page publishes it.

A BUCKET WITH NO POLICY IS A LEGITIMATE STATE
--------------------------------------------
``Policy`` is not required, and a bucket with no policy is what the service reports as
``NoSuchBucketPolicy``. The estate has such buckets, and for them ``Policy`` goes out null
rather than as an invented empty document -- that is the reading of the published type.

WHY THIS SURFACE EXISTS: THE THREE PUBLIC-EXPOSURE RULES OF AWS CONFIG
----------------------------------------------------------------------
``s3-bucket-public-read-prohibited`` names the bucket policy as one of the three things the
rule reads. Without this surface the rule could not evaluate the policy half of its own
published condition, and the Increment 3 would have closed only the ACL and Block Public
Access halves.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.storage import AwsBucketPolicy, AwsBucketPosture, AwsPolicyStatement
from tools.synthetic_clouds.render import s3_posture as shared

SURFACE = "aws/s3-get-bucket-policy"
RENDER_DIR = "s3_get_bucket_policy"

RESPONSE_SCOPE = "get-bucket-policy-response"
DOCUMENT_SCOPE = "bucket-policy-document"
STATEMENT_SCOPE = "policy-statement"
REQUEST_SCOPE = "request-parameters"

_KEY = "s3_get_bucket_policy"

_RESPONSE_COLUMNS = shared.names_of(_KEY, RESPONSE_SCOPE)
_DOCUMENT_COLUMNS = shared.names_of(_KEY, DOCUMENT_SCOPE)
_STATEMENT_COLUMNS = shared.names_of(_KEY, STATEMENT_SCOPE)
_REQUEST_COLUMNS = shared.names_of(_KEY, REQUEST_SCOPE)

_RESPONSE_PROJECTED: frozenset[str] = frozenset({"Policy"})
_DOCUMENT_PROJECTED: frozenset[str] = frozenset({"Id", "Statement", "Version"})
_STATEMENT_PROJECTED: frozenset[str] = frozenset({"Action", "Effect", "Principal", "Resource", "Sid"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()


def specification() -> SurfaceSpec:
    """Return the cited specification for ``aws/s3-get-bucket-policy``."""
    return shared.specification(_KEY)


def _statement(statement: AwsPolicyStatement) -> dict[str, Any]:
    """Return the documented 5-member statement of one bucket policy.

    ``Action`` and ``Resource`` are always arrays. The Sample Response publishes one of each
    form -- ``"Action": ["s3:*"]`` and ``"Resource": "arn:aws:s3:::bucket/*"`` -- and the
    policy language accepts both; normalizing to a list keeps one shape in the artifact, and
    the normalization is declared in the spec's ``armadilhas``.

    ``Principal`` is flattened to a list of strings. The Sample Response nests the values
    under a type key (``{"AWS": [...]}``); the estate models only the values, and the spec
    records the omitted qualifier in ``unverified`` rather than inventing a shape for it.
    """
    record: dict[str, Any] = {
        "Action": list(statement.actions),
        "Effect": statement.effect,
        "Principal": list(statement.principals),
        "Resource": list(statement.resources),
        "Sid": statement.sid,
    }
    shared.require_projection(_KEY, record, _STATEMENT_COLUMNS, _STATEMENT_PROJECTED, "Statement")
    return record


def _document(policy: AwsBucketPolicy) -> dict[str, Any]:
    """Return the documented 3-member bucket policy document."""
    record: dict[str, Any] = {
        "Id": policy.policy_id,
        "Statement": [_statement(statement) for statement in policy.statements],
        "Version": policy.version,
    }
    shared.require_projection(_KEY, record, _DOCUMENT_COLUMNS, _DOCUMENT_PROJECTED, "documento de policy")
    return record


def _statement_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Sort a projected statement deterministically by its published shape."""
    return (
        str(record["Sid"] or ""),
        str(record["Effect"]),
        ",".join(str(item) for item in record["Action"]),
        ",".join(str(item) for item in record["Principal"]),
    )


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as an all-null SHAPE fixture."""
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    shared.require_projection(_KEY, document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "forma de request-parameters")
    return document


class S3GetBucketPolicyRenderer:
    """Renders the bucket policy of every AWS bucket in the estate."""

    name = "s3_get_bucket_policy"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/s3_get_bucket_policy/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_scope, _ = shared.postures_by_scope(estate)
        postures, order = shared.per_bucket_order(estate)

        responses: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        statements: list[dict[str, Any]] = []
        com_policy: list[str] = []

        # UMA resposta por bucket: ``GetBucketPolicy`` devolve a policy de UM bucket, e o
        # objeto documentado tem um membro so. Emitir uma lista de policies dentro de ``Policy``
        # transformaria o documento em algo que a acao nunca produz.
        for posture in postures:
            if posture.policy is None:
                # Sem policy e um estado legitimo: Policy nao e obrigatorio e a acao sinaliza a
                # ausencia com NoSuchBucketPolicy. Nao se inventa documento vazio.
                response: dict[str, Any] = {"Policy": None}
            else:
                document = _document(posture.policy)
                response = {"Policy": document}
                documents.append(document)
                statements.extend(document["Statement"])
                com_policy.append(posture.bucket_name)
            shared.require_projection(_KEY, response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")
            responses.append(response)

        statements.sort(key=_statement_sort_key)

        shared.write_json(target / "get-bucket-policy-response.json", responses, written)
        shared.write_json(target / "bucket-policy-document.json", documents, written)
        shared.write_json(target / "policy-statement.json", statements, written)
        shared.write_json(target / "request-parameters.json", _request_parameters(), written, sort_keys=True)
        shared.write_provenance(target, self._provenance(estate, by_scope, com_policy, order), written)
        return written

    def _provenance(
        self,
        estate: CanonicalEstate,
        by_scope: dict[tuple[str, str], list[AwsBucketPosture]],
        com_policy: list[str],
        order: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps."""
        spec = specification()
        sem_policy = len(estate.aws_bucket_postures) - len(com_policy)
        return shared.provenance_payload(
            surface=SURFACE,
            renderer=self.name,
            spec=spec,
            mechanism={
                "kind": "read_api",
                "format": "json",
                "artifact_format": "json",
                "scope": "account_region",
                "permission": spec.reference.get("permission"),
                "permission_note": spec.reference.get("permission_note"),
                "document_members_source": (
                    "A lista de Response Elements da acao publica UM item so, Policy. Os "
                    "membros de documento e de statement vem da Sample Response da MESMA "
                    "pagina. Condition, NotAction, NotPrincipal e NotResource nao aparecem "
                    "nessa resposta e por isso nao entram no artefacto."
                ),
            },
            counts={
                "scopes": len(by_scope),
                "responses": len(estate.aws_bucket_postures),
                "buckets_total": len(estate.aws_bucket_postures),
                "buckets_with_policy": len(com_policy),
                "buckets_without_policy": sem_policy,
                "documents": len(com_policy),
            },
            derived={
                "response_order": (
                    "O objeto documentado tem um membro so e nao nomeia o bucket, entao ha UMA "
                    "resposta por bucket e a ligacao se faz por POSICAO. A ordem e (conta, "
                    "regiao, nome do bucket) e esta escrita em response_order."
                ),
                "response_order_map": order,
                "Action/Resource normalization": (
                    "Sempre arrays. A resposta de exemplo traz 'Action' como lista e "
                    "'Resource' como escalar; a linguagem aceita as duas formas e o artefacto "
                    "usa uma so, com a conversao declarada."
                ),
                "Principal flattening": (
                    "O exemplo traz 'Principal': {'AWS': [...]} -- um objeto com chave de "
                    "TIPO. O artefacto achata em lista de strings e nao modela a chave: um "
                    "consumidor que precise do tipo do principal nao o encontra aqui."
                ),
                "Resource ARN": (
                    "O ARN do bucket e derivado do NOME do bucket, com o prefixo "
                    "arn:aws:s3:::. Um ARN de outro bucket seria uma policy que o S3 "
                    "rejeitaria."
                ),
            },
            gaps={
                "Policy (bucket sem policy)": (
                    f"{sem_policy} bucket(s) nao tem policy e por isso tem Policy nulo. E o "
                    "estado que a acao sinaliza com NoSuchBucketPolicy, e Policy nao e "
                    "obrigatorio na lista de Response Elements. Preencher um documento vazio "
                    "seria afirmar que o bucket tem uma policy que nao existe."
                ),
                "Statement.Sid": (
                    "Nulo nos statements que nao o declaram. O exemplo da pagina traz Sid, e o "
                    "estado usa-o, mas a linguagem nao o exige."
                ),
                "Condition": (
                    "AUSENTE DO CONTRATO. Condition existe na linguagem de policy mas nao "
                    "aparece na resposta de exemplo desta acao, entao nao entra no artefacto. "
                    "O motivo esta em unverified na spec."
                ),
                "request-parameters": (
                    "VAZIO POR MODELO. Os dois nomes pertencem ao lado da REQUISICAO e o estado "
                    "nao modela nenhuma requisicao capturada."
                ),
            },
            rules_read={
                "s3-bucket-public-read-prohibited": (
                    "Le a policy quando 'the Block Public Access setting does not restrict "
                    "public policies'. Um statement Allow que concede acao de leitura (s3:Get*, "
                    "s3:List*) a um principal curinga como '*' concede leitura publica."
                ),
                "s3-bucket-public-write-prohibited": (
                    "Mesma condicao, com acao de escrita (s3:Put*, s3:Delete*) a principal "
                    "curinga."
                ),
            },
        )