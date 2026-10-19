"""AWS S3 ``GetBucketAcl`` renderer -- a ACL EFETIVA de cada bucket.

Projects the canonical estate's bucket postures into the **13 documented fields** of
``specs/aws/s3-get-bucket-acl.schema.json`` -- os 2 elementos de topo de
``AccessControlPolicy``, os 2 de ``Owner``, os 2 de ``Grant``, os 5 de ``Grantee`` e os 2
parametros documentados da requisicao.

THE ONE THING THIS RENDERER GETS RIGHT THAT A NAIVE ONE DOES NOT
----------------------------------------------------------------
The response is the **effective** ACL, not the stored one, and the documentation says so in
those words: "Calls to GetBucketAcl and GetObjectAcl always return the effective permissions
in place for the specified bucket or object. For example, suppose that a bucket has an ACL
that grants public access, but the bucket also has the IgnorePublicAcls setting enabled. In
this case, GetBucketAcl returns an ACL that reflects the access permissions that Amazon S3 is
enforcing, rather than the actual ACL that is associated with the bucket."

So this renderer publishes ``AwsBucketPosture.effective_grants()``. On a bucket whose
``IgnorePublicAcls`` is on, the grants to ``AllUsers``/``AuthenticatedUsers`` are absent from
the response even though the estate stores them -- and that bucket reads as private to anyone
consuming this surface, which is what the S3 service would tell them.

WHY THIS SURFACE EXISTS: THE THREE PUBLIC-EXPOSURE RULES OF AWS CONFIG
---------------------------------------------------------------------
The estate already carried fifteen ``s3_bucket`` RESOURCES and not one ACL. Because of that,
``render/config_compliance_by_rule.py`` had to answer three real managed rules
``INSUFFICIENT_DATA``, and the ``s3-bucket-public-read-prohibited`` page names the ACL as one
of the three things the rule reads: "The rule checks the Block Public Access settings, the
bucket policy, and the bucket access control list (ACL)." That was a MODEL gap, not a doubt
about the rule, and closing it is the Increment 3.

WHAT STAYS EMPTY, AND WHY
-------------------------
``Grantee.DisplayName`` and ``Grantee.EmailAddress`` are null because no grant in the estate
concedes to a grantee that would use them: a group grant carries only ``URI`` and a canonical
user grant carries only ``ID``, which is exactly what the official Sample Response shows.
The whole ``request-parameters`` set is null because the estate models no captured request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.storage import AwsBucketGrant, AwsBucketPosture
from tools.synthetic_clouds.render import s3_posture as shared

SURFACE = "aws/s3-get-bucket-acl"
RENDER_DIR = "s3_get_bucket_acl"

RESPONSE_SCOPE = "get-bucket-acl-response"
OWNER_SCOPE = "owner"
GRANT_SCOPE = "grant"
GRANTEE_SCOPE = "grantee"
REQUEST_SCOPE = "request-parameters"

_KEY = "s3_get_bucket_acl"

_RESPONSE_COLUMNS = shared.names_of(_KEY, RESPONSE_SCOPE)
_OWNER_COLUMNS = shared.names_of(_KEY, OWNER_SCOPE)
_GRANT_COLUMNS = shared.names_of(_KEY, GRANT_SCOPE)
_GRANTEE_COLUMNS = shared.names_of(_KEY, GRANTEE_SCOPE)
_REQUEST_COLUMNS = shared.names_of(_KEY, REQUEST_SCOPE)

_RESPONSE_PROJECTED: frozenset[str] = frozenset({"Grants", "Owner"})
_OWNER_PROJECTED: frozenset[str] = frozenset({"ID"})
_GRANT_PROJECTED: frozenset[str] = frozenset({"Grantee", "Permission"})
_GRANTEE_PROJECTED: frozenset[str] = frozenset({"Type", "ID", "URI"})
_REQUEST_PROJECTED: frozenset[str] = frozenset()


def specification() -> SurfaceSpec:
    """Return the cited specification for ``aws/s3-get-bucket-acl``."""
    return shared.specification(_KEY)


def _grantee(grant: AwsBucketGrant) -> dict[str, Any]:
    """Return the documented 5-member ``Grantee`` of one grant.

    Only the members the grant actually uses carry a value. A group grant carries ``URI``
    and no ``ID``; a canonical user grant carries ``ID`` and no ``URI``. That is what the
    official Sample Response shows, and filling all five would invent the others.
    """
    record: dict[str, Any] = {
        "Type": grant.grantee_type,
        "DisplayName": grant.display_name,
        "EmailAddress": grant.email_address,
        "ID": grant.grantee_id,
        "URI": grant.uri,
    }
    shared.require_projection(_KEY, record, _GRANTEE_COLUMNS, _GRANTEE_PROJECTED, "Grantee")
    return record


def _grant(grant: AwsBucketGrant) -> dict[str, Any]:
    """Return the documented 2-member ``Grant`` of one ACL entry."""
    record: dict[str, Any] = {
        "Grantee": _grantee(grant),
        "Permission": grant.permission,
    }
    shared.require_projection(_KEY, record, _GRANT_COLUMNS, _GRANT_PROJECTED, "Grant")
    return record


def _owner(posture: AwsBucketPosture) -> dict[str, Any]:
    """Return the documented 2-member ``Owner`` of one bucket."""
    record: dict[str, Any] = {
        "DisplayName": posture.owner.display_name,
        "ID": posture.owner.id,
    }
    shared.require_projection(_KEY, record, _OWNER_COLUMNS, _OWNER_PROJECTED, "Owner")
    return record


def _grant_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """Sort a projected ``Grant`` deterministically by its published shape."""
    grantee = record["Grantee"]
    return (
        str(grantee["Type"]),
        str(grantee["URI"] or ""),
        str(grantee["ID"] or ""),
        str(record["Permission"]),
    )


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as an all-null SHAPE fixture."""
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    shared.require_projection(_KEY, document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "forma de request-parameters")
    return document


class S3GetBucketAclRenderer:
    """Renders the EFFECTIVE ACL of every AWS bucket in the estate."""

    name = "s3_get_bucket_acl"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/s3_get_bucket_acl/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_scope, _ = shared.postures_by_scope(estate)
        postures, order = shared.per_bucket_order(estate)

        responses: list[dict[str, Any]] = []
        grants: list[dict[str, Any]] = []
        grantees: list[dict[str, Any]] = []
        ignored: list[str] = []

        # UMA resposta por bucket: ``GetBucketAcl`` devolve a ACL de UM bucket e o objeto
        # documentado nao tem nem array nem membro que nomeie o bucket. Juntar as ACLs de
        # varios buckets num envelope so seria um documento que a acao nunca produz.
        for posture in postures:
            scope_grants = [_grant(grant) for grant in posture.effective_grants()]
            response: dict[str, Any] = {"Grants": scope_grants, "Owner": _owner(posture)}
            shared.require_projection(_KEY, response, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")
            responses.append(response)
            for record in scope_grants:
                grants.append(record)
                grantees.append(record["Grantee"])
            if len(posture.effective_grants()) != len(posture.acl_grants):
                # O bucket tem grant publico ARMAZENADO que a resposta NAO publica. O nome do
                # bucket vai para a proveniencia porque e a unica evidencia neste artefacto de
                # que a ACL armazenada e a efetiva sao coisas diferentes.
                ignored.append(posture.bucket_name)

        grants.sort(key=_grant_sort_key)
        grantees.sort(key=lambda item: (str(item["Type"]), str(item["URI"] or ""), str(item["ID"] or "")))

        shared.write_json(target / "get-bucket-acl-response.json", responses, written)
        shared.write_json(target / "grant.json", grants, written)
        shared.write_json(target / "grantee.json", grantees, written)
        shared.write_json(target / "owner.json", [_owner(posture) for posture in postures], written)
        shared.write_json(target / "request-parameters.json", _request_parameters(), written, sort_keys=True)
        shared.write_provenance(target, self._provenance(estate, by_scope, ignored, order), written)
        return written

    def _provenance(
        self,
        estate: CanonicalEstate,
        by_scope: dict[tuple[str, str], list[AwsBucketPosture]],
        ignore_public_acls: list[str],
        order: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps."""
        spec = specification()
        stored = sum(len(posture.acl_grants) for posture in estate.aws_bucket_postures)
        effective = sum(len(posture.effective_grants()) for posture in estate.aws_bucket_postures)
        return shared.provenance_payload(
            surface=SURFACE,
            renderer=self.name,
            spec=spec,
            mechanism={
                "kind": "read_api",
                "format": "xml",
                "artifact_format": "json",
                "scope": "account_region",
                "response_wrapper": "AccessControlPolicy",
                "permission": spec.reference.get("permission"),
                "permission_note": spec.reference.get("permission_note"),
                "acl_published": "effective",
                "acl_published_note": (
                    "A resposta e a ACL EFETIVA, nao a armazenada. A pagina de Block Public "
                    "Access diz que GetBucketAcl 'always return the effective permissions in "
                    "place' e que, com IgnorePublicAcls ligado, devolve 'an ACL that reflects "
                    "the access permissions that Amazon S3 is enforcing, rather than the actual "
                    "ACL that is associated with the bucket'."
                ),
            },
            counts={
                "scopes": len(by_scope),
                "responses": len(estate.aws_bucket_postures),
                "grants_stored": stored,
                "grants_published": effective,
                "grants_suppressed_by_ignore_public_acls": stored - effective,
                "buckets_with_ignore_public_acls": len(ignore_public_acls),
            },
            derived={
                "response_order": (
                    "A resposta documentada nao tem array nem membro que nomeie o bucket, entao "
                    "ha UMA resposta por bucket e a ligacao se faz por POSICAO. A ordem e "
                    "(conta, regiao, nome do bucket) e esta escrita em response_order."
                ),
                "response_order_map": order,
                "effective ACL": (
                    f"Os grants para AllUsers/AuthenticatedUsers saem da resposta de "
                    f"{len(ignore_public_acls)} bucket(s) cujo IgnorePublicAcls esta ligado. "
                    "Os grants do grupo LogDelivery NAO sao suprimidos: a definicao de publico "
                    "da AWS nomeia apenas AllUsers e AuthenticatedUsers."
                ),
                "order": (
                    "Os grants sao ordenados por (Type, URI, ID, Permission). O Response Syntax "
                    "e XML e a pagina nao promete ordenacao: a ordem aqui e determinismo do "
                    "gerador."
                ),
                "owner.ID": (
                    "DERIVADO do id da conta, o mesmo valor que s3_list_buckets publica no "
                    "Owner da conta e que GetBucketAcl publica por bucket -- um dono so."
                ),
            },
            gaps={
                "Grantee.DisplayName": (
                    "NULO POR MODELO. O estate nao concede a um granted que use nome de "
                    "exibicao; a resposta de exemplo oficial tambem nao traz esse membro."
                ),
                "Grantee.EmailAddress": (
                    "NULO POR MODELO. O estate nao concede por email. Nenhum grant tem "
                    "Type=AmazonCustomerByEmail."
                ),
                "Owner.DisplayName": "NULO POR MODELO. O estate nao modela nome de exibicao de conta.",
                "request-parameters": (
                    "VAZIO POR MODELO. Os dois nomes pertencem ao lado da REQUISICAO e o estado "
                    "nao modela nenhuma requisicao capturada."
                ),
            },
            rules_read={
                "s3-bucket-public-read-prohibited": (
                    "Le a ACL quando 'the Block Public Access setting does not restrict public "
                    "bucket ACLs'. Um grant para AllUsers/AuthenticatedUsers com READ, READ_ACP "
                    "ou FULL_CONTROL concede leitura publica."
                ),
                "s3-bucket-public-write-prohibited": (
                    "Le a ACL pela mesma condicao. Um grant para os mesmos grupos com WRITE, "
                    "WRITE_ACP ou FULL_CONTROL concede escrita publica."
                ),
            },
        )