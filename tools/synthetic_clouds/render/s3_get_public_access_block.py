"""AWS S3 ``GetPublicAccessBlock`` renderer -- os quatro interruptores de cada bucket.

Projects the canonical estate's bucket postures into the **14 declared fields** of
``specs/aws/s3-get-public-access-block.schema.json`` -- the 4 members of
``PublicAccessBlockConfiguration``, the 2 documented request parameters, and the 8 of the
SIBLING, NON-CONTRACTUAL ``regional-access-block-configuration`` set (the
``RegionalAccessBlockConfiguration`` object plus its five members, each by path). The 14 are not
14 of the same kind: 6 are audited against the contract and 8 are declared unverified. See the
section on the regional block below for why they are counted together and audited apart.

WHY THIS SURFACE IS FIRST IN THE RULE, NOT LAST
-----------------------------------------------
The ``s3-bucket-public-read-prohibited`` page states its two conditions in this order: the
rule is compliant when "the Block Public Access setting restricts public policies OR the
bucket policy does not allow public read access" AND "the Block Public Access setting
restricts public ACLs OR the bucket ACL does not allow public read access". The block setting
is the SHORT-CIRCUIT: when it is on, the policy and the ACL are never read. So the two
surface siblings that answer the second half of each clause would be consulted on buckets
where the answer is already decided here -- and the estate needs both halves populated for
the rule to be able to say either.

THE FOUR MEMBERS ARE NOT INTERCHANGEABLE
----------------------------------------
``BlockPublicAcls`` stops a public ACL from being WRITTEN. ``IgnorePublicAcls`` makes the
service IGNORE public ACLs that already exist -- and that is what makes ``GetBucketAcl``
return the effective ACL instead of the stored one, which is the behaviour
``render/s3_get_bucket_acl.py`` implements. ``BlockPublicPolicy`` stops a public policy from
being written. ``RestrictPublicBuckets`` restricts ACCESS to a bucket that has a public
policy. Collapsing the four into one boolean would erase exactly the distinction the rule
reads, so the artifact carries all four for every bucket.

REGIONAL ACCESS BLOCK: DECLARED, NOT CONTRACTUAL
--------------------------------------------------
``RegionalAccessBlockConfiguration`` has ZERO occurrences on ``API_GetPublicAccessBlock.html``
AND on ``API_PutPublicAccessBlock.html`` (measured 2026-10-18), and the
``PublicAccessBlockConfiguration`` both pages document has four members, none of them regional.
The regional block exists in the API and the SDKs publish it, but the public reference pages
consulted here do not describe it.

So it does NOT go into the response. Adding a fifth member to the documented root type would
be a column the set audit would -- correctly -- call invented, and it would hide the very fact
that matters: nobody here has verified the shape against a page. It goes into a SIBLING set,
its own artifact, with its columns marked ``unverified`` in the spec, so that the distinction
between "the contract says so" and "the SDK says so" survives in the artifact instead of being
resolved silently in favour of the one that is convenient.

The ``RegionPrefix`` is the bucket's OWN region, not a declared literal: a block naming a prefix
the bucket is not in does not apply to it, and a consumer could not tell "not configured" from
"configured for somewhere else".

WHAT STAYS EMPTY, AND WHY
-------------------------
Nothing in the response set is ever null: all four members are ``Required: No`` booleans and a
bucket with no block configuration has all four off, which is the reading the rules make. A
bucket with no configuration is a bucket with four ``false``, not an absent record. The whole
``request-parameters`` set is null because the estate models no captured request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.storage import AwsBucketPosture
from tools.synthetic_clouds.render import s3_posture as shared
from tools.synthetic_clouds.render.base import RenderError

SURFACE = "aws/s3-get-public-access-block"
RENDER_DIR = "s3_get_public_access_block"

RESPONSE_SCOPE = "get-public-access-block-response"
REQUEST_SCOPE = "request-parameters"
#: O bloco por REGIAO, num conjunto IRMAO. Ele nao entra no corpo da resposta porque as duas
#: acoes publicadas nao documentam nenhum membro regional -- ver o docstring do modulo e a
#: entrada ``regional-access-block-configuration`` da spec, marcada nao comprovada.
REGIONAL_SCOPE = "regional-access-block-configuration"

_KEY = "s3_get_public_access_block"

_RESPONSE_COLUMNS = shared.names_of(_KEY, RESPONSE_SCOPE)
_REQUEST_COLUMNS = shared.names_of(_KEY, REQUEST_SCOPE)

_RESPONSE_PROJECTED: frozenset[str] = frozenset(
    {"BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"}
)
_REQUEST_PROJECTED: frozenset[str] = frozenset()
_REGIONAL_COLUMNS = shared.names_of_uncontracted(_KEY, REGIONAL_SCOPE)
#: Os membros DE DENTRO do ``RegionalAccessBlockConfiguration``, com caminho. A spec os declara
#: prefixados porque o objeto e um membro do artefato IRMAO e nao um conjunto plano -- e e essa
#: forma que o auditor consegue casar a chave do artefato com um nome da spec.
_REGIONAL_CONFIG_COLUMN = "RegionalAccessBlockConfiguration"
_REGIONAL_CONFIG_COLUMNS: tuple[str, ...] = tuple(
    column for column in _REGIONAL_COLUMNS if column.startswith(f"{_REGIONAL_CONFIG_COLUMN}.")
)
_REGIONAL_BUCKET_COLUMN = "Bucket"
_REGIONAL_PROJECTED: frozenset[str] = frozenset(
    {
        f"{_REGIONAL_CONFIG_COLUMN}.BlockPublicAcls",
        f"{_REGIONAL_CONFIG_COLUMN}.BlockPublicPolicy",
        f"{_REGIONAL_CONFIG_COLUMN}.IgnorePublicAcls",
        f"{_REGIONAL_CONFIG_COLUMN}.Region",
        f"{_REGIONAL_CONFIG_COLUMN}.RegionPrefix",
        f"{_REGIONAL_CONFIG_COLUMN}.RestrictPublicBuckets",
    }
)


def _regional_config(regional: Any) -> dict[str, Any]:
    """The six members of the regional block, keyed the way the spec spells them.

    The keys carry the ``RegionalAccessBlockConfiguration.`` prefix because that is how the
    spec declares them: they are members OF the object, not siblings of it. Spelling them flat
    here would be the same artifact under a different reading, and the audit -- which compares
    the artifact's keys with the spec's names -- would see a set no declared name matches.
    """
    record: dict[str, Any] = {
        f"{_REGIONAL_CONFIG_COLUMN}.Region": regional.region_id,
        f"{_REGIONAL_CONFIG_COLUMN}.RegionPrefix": regional.region_prefix,
        f"{_REGIONAL_CONFIG_COLUMN}.BlockPublicAcls": regional.block_public_acls,
        f"{_REGIONAL_CONFIG_COLUMN}.BlockPublicPolicy": regional.block_public_policy,
        f"{_REGIONAL_CONFIG_COLUMN}.IgnorePublicAcls": regional.ignore_public_acls,
        f"{_REGIONAL_CONFIG_COLUMN}.RestrictPublicBuckets": regional.restrict_public_buckets,
    }
    shared.require_projection(_KEY, record, _REGIONAL_CONFIG_COLUMNS, _REGIONAL_PROJECTED, "RegionalAccessBlockConfiguration")
    return record


def specification() -> SurfaceSpec:
    """Return the cited specification for ``aws/s3-get-public-access-block``."""
    return shared.specification(_KEY)


def _public_access_block(posture: AwsBucketPosture) -> dict[str, Any]:
    """Return the documented 4-member ``PublicAccessBlockConfiguration`` of one bucket."""
    block = posture.public_access_block
    record: dict[str, Any] = {
        "BlockPublicAcls": block.block_public_acls,
        "BlockPublicPolicy": block.block_public_policy,
        "IgnorePublicAcls": block.ignore_public_acls,
        "RestrictPublicBuckets": block.restrict_public_buckets,
    }
    shared.require_projection(_KEY, record, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "PublicAccessBlockConfiguration")
    return record


def _regional_access_block(posture: AwsBucketPosture) -> dict[str, Any] | None:
    """The bucket's regional block, or ``None`` when the account never configured one.

    A bucket with no regional block is a legitimate state and the artifact says so by OMITTING
    the entry, the way ``GetBucketPolicy`` omits the ``Policy`` element when there is no policy.
    Emitting four ``false`` here would be a different claim: it would say the account set a
    regional block that blocks nothing, which is not the same as not having set one.
    """
    regional = posture.regional_access_block
    if regional is None:
        return None
    return _regional_config(regional)


def _request_parameters() -> dict[str, Any]:
    """Return the documented request parameters as an all-null SHAPE fixture."""
    document: dict[str, Any] = dict.fromkeys(_REQUEST_COLUMNS)
    shared.require_projection(_KEY, document, _REQUEST_COLUMNS, _REQUEST_PROJECTED, "forma de request-parameters")
    return document


class S3GetPublicAccessBlockRenderer:
    """Renders the Block Public Access configuration of every AWS bucket in the estate."""

    name = "s3_get_public_access_block"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/s3_get_public_access_block/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []
        by_scope, _ = shared.postures_by_scope(estate)
        postures, order = shared.per_bucket_order(estate)

        responses: list[dict[str, Any]] = []
        for posture in postures:
            record = _public_access_block(posture)
            shared.require_projection(_KEY, record, _RESPONSE_COLUMNS, _RESPONSE_PROJECTED, "envelope de resposta")
            responses.append(record)

        shared.write_json(target / "get-public-access-block-response.json", responses, written)
        shared.write_json(target / "request-parameters.json", _request_parameters(), written, sort_keys=True)
        # O bloco por REGIAO e IRMAO do corpo, nunca um membro dele: as duas acoes publicadas
        # nao documentam nenhum membro regional. Um bucket sem o bloco configurado simplesmente
        # nao entra na lista.
        regional: list[dict[str, Any]] = []
        for posture in postures:
            registro = _regional_access_block(posture)
            if registro is None:
                continue
            entrada = {
                _REGIONAL_BUCKET_COLUMN: posture.bucket_name,
                _REGIONAL_CONFIG_COLUMN: {
                    chave.split(".", 1)[1]: valor for chave, valor in registro.items()
                },
            }
            # A entrada do artefato IRMAO e um par (bucket, configuracao), e por isso nao passa
            # pela guarda de conjunto: aquela compara um objeto plano com os nomes do conjunto.
            # O que se confere aqui e o que a guarda nao alcança -- que o bucket tem nome e que a
            # configuracao e o bloco, e nao outra coisa.
            if not entrada[_REGIONAL_BUCKET_COLUMN]:
                raise RenderError(
                    f"{RENDER_DIR}: regional-access-block.json tem uma entrada sem bucket; "
                    "a configuracao regional nao se liga a nada sem o bucket que ela alcanca"
                )
            regional.append(entrada)
        shared.write_json(target / "regional-access-block.json", regional, written)
        shared.write_provenance(target, self._provenance(estate, by_scope, responses, order, regional), written)
        return written

    def _provenance(
        self,
        estate: CanonicalEstate,
        by_scope: dict[tuple[str, str], list[AwsBucketPosture]],
        responses: list[dict[str, Any]],
        order: list[dict[str, str]],
        regional: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps."""
        spec = specification()
        total = len(responses)
        counts: dict[str, Any] = {
            "scopes": len(by_scope),
            "responses": total,
            "buckets_total": len(estate.aws_bucket_postures),
            "regional_blocks": len(regional),
            "buckets_without_regional_block": total - len(regional),
        }
        for member in _RESPONSE_COLUMNS:
            counts[f"true_{member}"] = sum(1 for record in responses if record[member] is True)
        return shared.provenance_payload(
            surface=SURFACE,
            renderer=self.name,
            spec=spec,
            mechanism={
                "kind": "read_api",
                "format": "xml",
                "artifact_format": "json",
                "scope": "account_region",
                "scope_note": (
                    "A propria pagina avisa que a operacao devolve SO a configuracao de nivel de "
                    "bucket: 'This operation returns the bucket-level configuration only.' A "
                    "regra s3-bucket-level-public-access-prohibited e de nivel de bucket, entao "
                    "esta e a superficie correta para ela; o block de nivel de CONTA e outro "
                    "fato, consultado pela s3control, e nao esta aqui."
                ),
                "permission": spec.reference.get("permission"),
                "boolean_representation": (
                    "A resposta de exemplo oficial escreve TRUE/FALSE, que e a grafia booleana "
                    "de XML. O artefacto e JSON e emite true/false, o booleano correspondente. "
                    "Um consumidor que compare com o exemplo oficial vai ver outra grafia."
                ),
            },
            counts=counts,
            derived={
                "response_order": (
                    "O elemento raiz e o proprio tipo e nao nomeia o bucket, entao ha UMA "
                    "resposta por bucket e a ligacao se faz por POSICAO. A ordem e (conta, "
                    "regiao, nome do bucket) e esta escrita em response_order."
                ),
                "response_order_map": order,
                "no configuration is four false": (
                    f"Os {total} buckets tem os quatro membros preenchidos. Um bucket que nunca "
                    "chamou PutPublicAccessBlock tem os quatro desligados, e a regra le esse "
                    "estado como 'o block nao restringe' -- e nao como 'nao ha dado'."
                ),
            },
            gaps={
                "account-level PublicAccessBlock": (
                    "AUSENTE DO CONTRATO DESTA SUPERFICIE. A pagina afirma que o S3 usa a "
                    "combinacao MAIS RESTRITIVA entre o block do bucket e o da conta. O estado "
                    "nao modela o de nivel de conta, entao o que esta aqui sao os quatro fatos "
                    "do bucket -- que e exatamente o que a pagina diz que esta operacao devolve."
                ),
                "request-parameters": (
                    "VAZIO POR MODELO. Os dois nomes pertencem ao lado da REQUISICAO e o estado "
                    "nao modela nenhuma requisicao capturada."
                ),
                "regional-access-block-configuration": (
                    "AUSENTE DO CONTRATO DAS DUAS ACOES PUBLICADAS, E DECLARADO POR ISSO. "
                    "Medido em 2026-10-18: 'RegionalAccessBlockConfiguration' tem ZERO ocorrencias "
                    "em API_GetPublicAccessBlock.html E em API_PutPublicAccessBlock.html, e o "
                    "PublicAccessBlockConfiguration que ambas documentam tem quatro membros, "
                    "nenhum regional. O bloco por regiao existe na API e os SDKs o publicam, mas a "
                    "referencia publica consultada nao o descreve. Por isso ele NAO e um quinto "
                    "membro da resposta -- seria uma coluna que o auditor de conjunto acusaria de "
                    "inventada -- e sim um conjunto IRMAO, com as colunas marcadas nao "
                    "comprovadas nesta spec. A distincao entre 'o contrato diz' e 'o SDK diz' "
                    "sobrevive no artefacto em vez de ser resolvida em silencio a favor do que e "
                    "mais comodo. Um bucket sem o bloco configurado simplesmente nao entra na "
                    "lista: emitir quatro false ali seria afirmar que a conta configurou um bloco "
                    "regional que nao bloqueia nada, que nao e o mesmo que nao ter configurado."
                ),
            },
            rules_read={
                "s3-bucket-public-read-prohibited": (
                    "'The Block Public Access setting restricts public policies' -- o membro "
                    "BlockPublicPolicy -- 'OR the bucket policy does not allow public read "
                    "access'; e 'restricts public ACLs' -- o membro BlockPublicAcls -- 'OR the "
                    "bucket ACL does not allow public read access'. Com o block ligado, a "
                    "segunda metade da clausula nem e consultada."
                ),
                "s3-bucket-public-write-prohibited": (
                    "As mesmas duas condicoes, com escrita no lugar de leitura."
                ),
                "s3-bucket-level-public-access-prohibited": (
                    "'The rule is NON_COMPLIANT if an S3 bucket is not listed in the "
                    "excludedPublicBuckets parameter and bucket level settings are public.' A "
                    "regra e de nivel de bucket, e o parametro excludedPublicBuckets e opcional "
                    "-- o estado nao passa parametro, entao a clausula se reduz a 'os settings "
                    "de nivel de bucket sao publicos'."
                ),
            },
        )