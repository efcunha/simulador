"""Golden tests for the four Increment 3 surfaces: ``aws/s3-list-buckets``,
``aws/s3-get-bucket-acl``, ``aws/s3-get-bucket-policy`` and ``aws/s3-get-public-access-block``.

The point of this module is to confront the DELIVERED artifacts with their specs -- names,
values and the empty contract -- and to hold the judgement calls these surfaces invite
getting quietly wrong:

1. **the ACL published is the EFFECTIVE one, not the stored one.** The Block Public Access
   page says ``GetBucketAcl`` "always return the effective permissions in place" and that with
   ``IgnorePublicAcls`` on it returns "an ACL that reflects the access permissions that Amazon
   S3 is enforcing, rather than the actual ACL". A renderer that published ``acl_grants``
   would look right on 73 of 75 buckets and be wrong on the two that matter;
2. **"public" is a property of the RECIPIENT, not of the permission name.** AWS names two
   groups -- ``AllUsers`` and ``AuthenticatedUsers``. The ``LogDelivery`` group is not one of
   them, so a bucket carrying the documented ``log-delivery-write`` canned ACL is NOT public,
   and the test proves it by finding it and checking;
3. **the Block Public Access setting is a SHORT-CIRCUIT, not a fourth opinion.** The rule is a
   conjunction of two disjunctions whose first term is the block, so a bucket whose
   ``BlockPublicPolicy`` is on is COMPLIANT while still carrying a wildcard policy;
4. **the three S3 rules answer in BOTH directions in the SAME state**, which is what makes the
   Increment 3 useful rather than merely present;
5. **one of the four responses is really JSON and three are really XML** -- and the one is
   ``get-bucket-policy``, which is the one a reader would guess wrong.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.storage import (
    S3_ALL_USERS_URI,
    S3_AUTHENTICATED_USERS_URI,
    S3_LOG_DELIVERY_URI,
    AwsBucketPosture,
)
from tools.synthetic_clouds.render import s3_get_bucket_acl as acl_mod
from tools.synthetic_clouds.render import s3_get_bucket_policy as policy_mod
from tools.synthetic_clouds.render import s3_get_public_access_block as pab_mod
from tools.synthetic_clouds.render import s3_list_buckets as list_mod
from tools.synthetic_clouds.render import s3_posture as shared
from tools.synthetic_clouds.render.base import registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: surface -> (module, spec file, expected format, {(artifact file, scope)})
_SURFACES: tuple[tuple[Any, str, str, tuple[tuple[str, str], ...], int], ...] = (
    (
        list_mod,
        "s3-list-buckets.schema.json",
        "xml",
        (
            ("list-buckets-response.json", list_mod.RESPONSE_SCOPE),
            ("bucket.json", list_mod.BUCKET_SCOPE),
            ("owner.json", list_mod.OWNER_SCOPE),
            ("request-parameters.json", list_mod.REQUEST_SCOPE),
        ),
        14,
    ),
    (
        acl_mod,
        "s3-get-bucket-acl.schema.json",
        "xml",
        (
            ("get-bucket-acl-response.json", acl_mod.RESPONSE_SCOPE),
            ("grant.json", acl_mod.GRANT_SCOPE),
            ("grantee.json", acl_mod.GRANTEE_SCOPE),
            ("owner.json", acl_mod.OWNER_SCOPE),
            ("request-parameters.json", acl_mod.REQUEST_SCOPE),
        ),
        13,
    ),
    (
        policy_mod,
        "s3-get-bucket-policy.schema.json",
        "json",
        (
            ("get-bucket-policy-response.json", policy_mod.RESPONSE_SCOPE),
            ("bucket-policy-document.json", policy_mod.DOCUMENT_SCOPE),
            ("policy-statement.json", policy_mod.STATEMENT_SCOPE),
            ("request-parameters.json", policy_mod.REQUEST_SCOPE),
        ),
        11,
    ),
    (
        pab_mod,
        "s3-get-public-access-block.schema.json",
        "xml",
        (
            ("get-public-access-block-response.json", pab_mod.RESPONSE_SCOPE),
            ("request-parameters.json", pab_mod.REQUEST_SCOPE),
        ),
        # 4 contratuais + 2 parametros + 8 do conjunto IRMAO nao comprovado (o objeto e os cinco
        # membros DELE, cada um com caminho). As oito ultimas entram na contagem porque a spec
        # as declara e o artefacto as emite -- mas elas NAO passam pela auditoria de conjunto,
        # que recusaria coluna fora do formato. Ver ``test_o_bloco_regional_e_irmao_e_nao_comprovado``.
        14,
    ),
)

_RENDERERS = (list_mod, acl_mod, policy_mod, pab_mod)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The base small estate (seed 123): the buckets and the posture every rule reads."""
    return build_estate(seed=123, profile="small", currency="USD")


def _render(module: Any, estate: CanonicalEstate, out_dir: Path) -> Path:
    """Render one surface into ``out_dir`` and return the directory the artifacts landed in."""
    renderer = next(
        value
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
    )
    written = renderer().render(estate, out_dir / module.RENDER_DIR)
    assert written
    return written[0].parent


@pytest.fixture(scope="module")
def trees(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    raiz = tmp_path_factory.mktemp("s3-posture")
    return {module.RENDER_DIR: _render(module, estate, raiz) for module in _RENDERERS}


def _load(tree: Path, name: str) -> Any:
    return json.loads((tree / name).read_text(encoding="utf-8"))


# -- the four renderers are wired ---------------------------------------------


@pytest.mark.parametrize("module", _RENDERERS, ids=lambda module: module.RENDER_DIR)
def test_o_renderer_esta_registrado(module: Any) -> None:
    assert module.RENDER_DIR in registered_names()
    classes = [
        value
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
    ]
    assert classes, f"{module.RENDER_DIR}: nenhuma classe de renderer definida no modulo"
    assert cast("Any", classes[0]).name == module.RENDER_DIR


def test_o_bloco_regional_e_irmao_e_nao_comprovado(
    estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """The regional block is a SIBLING, and it is admitted to be unverified.

    Three things have to hold at once, and each one fails differently:

    1. **it is not a member of the response.** ``RegionalAccessBlockConfiguration`` has zero
       occurrences on both consulted action pages, so a fifth member in the documented root
       type would be a column the set audit calls invented. The response keeps exactly four;
    2. **it is not audited as if it were contractual.** The set is marked ``unverified``
       throughout and its columns come through ``names_of_uncontracted``, whose guard is the
       INVERSE of ``names_of`` -- a set admitted to be non-contractual must be entirely
       unverified, because a half-verified shape reads as a fully verified one;
    3. **a bucket without one is omitted, not zeroed.** Emitting four ``false`` would claim the
       account set a regional block that blocks nothing, which is a different fact from never
       having set one -- the same distinction the bucket policy's ``None`` makes.
    """
    spec = load_spec(_REPO_ROOT / "specs" / "aws" / "s3-get-public-access-block.schema.json")
    destino = tmp_path_factory.mktemp("regional-block")
    pab_mod.S3GetPublicAccessBlockRenderer().render(estate, destino)
    base = destino / pab_mod.RENDER_DIR

    # (1) a resposta continua com os quatro membros, e nada mais
    resposta = json.loads((base / "get-public-access-block-response.json").read_text(encoding="utf-8"))
    assert resposta
    for registro in resposta:
        assert set(registro) == set(pab_mod._RESPONSE_COLUMNS)
        assert pab_mod._REGIONAL_CONFIG_COLUMN not in registro
        assert pab_mod._REGIONAL_BUCKET_COLUMN not in registro

    # (2) o conjunto irmao existe, NAO passa pela auditoria de conjunto, e diz por que
    colunas = spec.columns_for(pab_mod.REGIONAL_SCOPE)
    assert colunas, "o conjunto regional sumiu da spec"
    assert not any(column.belongs_to_schema for column in colunas), (
        "o conjunto regional tem coluna marcada como comprovada: e o estado que a guarda "
        "names_of_uncontracted recusa, porque meia verificacao se le como verificacao inteira"
    )

    # (3) so entram os buckets com o bloco configurado, e cada um nomeia o seu bucket
    regional = json.loads((base / "regional-access-block.json").read_text(encoding="utf-8"))
    com_bloco = {p.bucket_name for p in estate.aws_bucket_postures if p.regional_access_block is not None}
    assert regional, "nenhum bucket com bloco regional: o estado nao exercita o caminho"
    assert {entrada["Bucket"] for entrada in regional} == com_bloco
    assert len(regional) < len(estate.aws_bucket_postures), (
        "todo bucket tem o bloco configurado, e entao a ausencia some do artefato"
    )
    for entrada in regional:
        bloco = entrada[pab_mod._REGIONAL_CONFIG_COLUMN]
        assert set(bloco) == {
            coluna.split(".", 1)[1] for coluna in pab_mod._REGIONAL_CONFIG_COLUMNS
        }
        # O prefixo tem que alcancar o bucket: um bloco que nomeia outra regiao nao se aplica.
        assert bloco["RegionPrefix"] == bloco["Region"]
        postura = next(p for p in estate.aws_bucket_postures if p.bucket_name == entrada["Bucket"])
        regional = postura.regional_access_block
        assert regional is not None, entrada["Bucket"]
        assert bloco["Region"] == postura.region_id
        assert bloco["BlockPublicAcls"] == regional.block_public_acls

    # e o motivo da nao verificacao esta nos dois lugares onde um leitor vai procurar.
    # ``unverified`` no nome da propriedade so devolve NOME DE CAMPO; esta entrada e uma lacuna
    # de TOPICO (o bloco inteiro, nao uma coluna), entao ela vive em ``unverified_topics``. A
    # busca e pelo TEXTO das duas listas para o teste nao depender dessa distincao.
    registradas = [campo.name for campo in spec.unverified_fields]
    assert any("RegionalAccessBlockConfiguration" in nome for nome in registradas), (
        f"a spec nao declara a nao verificacao do bloco regional: {registradas}"
    )
    proveniencia = json.loads((base / "_provenance.json").read_text(encoding="utf-8"))
    lacunas = json.dumps(proveniencia, ensure_ascii=False)
    assert "RegionalAccessBlockConfiguration" in lacunas, (
        "o _provenance nao declara a nao verificacao do bloco regional"
    )


@pytest.mark.parametrize(("module", "spec_file", "fmt", "scopes", "count"), _SURFACES, ids=lambda v: str(v))
def test_a_spec_cita_a_acao_a_data_e_o_formato(
    module: Any, spec_file: str, fmt: str, scopes: Any, count: int
) -> None:
    spec = load_spec(_REPO_ROOT / "specs" / "aws" / spec_file)
    assert spec.surface == module.SURFACE
    assert spec.provider == "aws"
    assert spec.reference["url"].startswith("https://docs.aws.amazon.com/AmazonS3/latest/API/")
    assert spec.reference["consulted_at"] == "2026-10-16"
    assert spec.delivery["format"] == fmt
    assert spec.delivery["kind"] == "read_api"
    # A contagem de colunas que o docstring de cada renderer promete.
    assert len(spec.names) == count


def test_a_superficie_de_policy_e_a_unica_em_json() -> None:
    """Three of the four are XML; the one that is JSON is the one a reader guesses wrong.

    ``GetBucketPolicy`` returns "JSON format" by the page's own words, and it is the only
    Increment 3 surface with no XML-to-JSON divergence to declare.
    """
    formatos = {module.RENDER_DIR: load_spec(_REPO_ROOT / "specs" / "aws" / file).delivery["format"]
                for module, file, _f, _s, _c in _SURFACES}
    assert formatos == {
        "s3_list_buckets": "xml",
        "s3_get_bucket_acl": "xml",
        "s3_get_bucket_policy": "json",
        "s3_get_public_access_block": "xml",
    }


# -- THE GOLDEN PART: artifact fields against the spec ------------------------


@pytest.mark.parametrize(("module", "spec_file", "fmt", "scopes", "count"), _SURFACES, ids=lambda v: str(v))
def test_cada_artefato_carrega_exatamente_os_campos_do_seu_conjunto(
    module: Any, spec_file: str, fmt: str, scopes: tuple[tuple[str, str], ...], count: int, trees: dict[str, Path]
) -> None:
    """The artifact, not the renderer's intent, has to match the specification."""
    spec = load_spec(_REPO_ROOT / "specs" / "aws" / spec_file)
    tree = trees[module.RENDER_DIR]
    for file_name, scope in scopes:
        findings = check_artifact(spec, tree / file_name, scope=scope)
        assert is_faithful(findings), [
            f"{module.RENDER_DIR}/{file_name} [{scope}]: {f.kind}: {f.detail}" for f in findings
        ]


@pytest.mark.parametrize("module", _RENDERERS, ids=lambda module: module.RENDER_DIR)
def test_a_proveniencia_registra_as_lacunas_que_os_itens_nao_conseguem(
    module: Any, trees: dict[str, Path]
) -> None:
    """The reasons live beside the data -- never inside it.

    An ingestor of the artifact must not see a key no cloud documents, so the gaps and the
    derivations are reported in ``_provenance.json`` and nowhere else.
    """
    report = _load(trees[module.RENDER_DIR], "_provenance.json")
    assert report["kind"] == "provenance"
    assert report["surface"] == module.SURFACE
    assert report["spec"] == f"specs/aws/{shared.SPEC_FILES[module.RENDER_DIR]}"
    assert report["model_gaps"], f"{module.RENDER_DIR}: proveniencia sem nenhuma lacuna declarada"
    assert all(entry["reason"].strip() for entry in report["model_gaps"])
    assert all(entry["reason"].strip() for entry in report["derivations"])


# -- JUDGEMENT 1: the published ACL is the EFFECTIVE one ----------------------


def test_a_acl_publicada_e_a_efetiva_e_nao_a_armazenada(
    estate: CanonicalEstate, trees: dict[str, Path]
) -> None:
    """``IgnorePublicAcls`` must REMOVE public grants from the response, not keep them.

    The page says GetBucketAcl "always return the effective permissions in place" and, with
    IgnorePublicAcls on, returns "an ACL that reflects the access permissions that Amazon S3
    is enforcing, rather than the actual ACL". So the renderer must publish
    ``effective_grants()``. Reading ``acl_grants`` instead would be indistinguishable on every
    bucket whose block is off -- and that is the mistake this test exists to catch.
    """
    divergentes = [
        posture for posture in estate.aws_bucket_postures if len(posture.effective_grants()) != len(posture.acl_grants)
    ]
    assert divergentes, "o estate nao produz nenhum bucket com ACL armazenada != efetiva: nada seria provado"

    respostas = cast("list[dict[str, Any]]", _load(trees[acl_mod.RENDER_DIR], "get-bucket-acl-response.json"))
    posicoes = _response_order(trees[acl_mod.RENDER_DIR])
    assert len(respostas) == len(posicoes)

    for posture in divergentes:
        # O nome do bucket REPETE entre contas -- o gerador reinicia o contador por escopo --
        # entao a posicao tem de ser achada pela tripla (conta, regiao, bucket), nunca pelo
        # nome so. Um consumidor que casasse pelo nome leria a ACL da conta errada.
        indice = next(
            item["index"]
            for item in posicoes
            if (item["account"], item["region"], item["bucket"])
            == (posture.account_id, posture.region_id, posture.bucket_name)
        )
        publicados = respostas[indice]["Grants"]
        uris = {grant["Grantee"]["URI"] for grant in publicados}
        assert S3_ALL_USERS_URI not in uris, (
            f"{posture.bucket_name}: grant de AllUsers na resposta de um bucket com IgnorePublicAcls ligado"
        )
        assert S3_AUTHENTICATED_USERS_URI not in uris
        assert len(publicados) < len(posture.acl_grants)
        # E o grant ao owner continua: IgnorePublicAcls nao mexe no que NAO e publico.
        assert any(grant["Grantee"]["ID"] == posture.owner.id for grant in publicados)


def test_o_nome_do_bucket_repete_entre_contas_e_a_ordem_desambigua(
    estate: CanonicalEstate, trees: dict[str, Path]
) -> None:
    """The join must be by (account, region, bucket): the NAME ALONE IS NOT UNIQUE.

    ``estate_builder`` restarts its per-scope counter for every account, so ``s3_bucket-0004``
    exists in more than one account. An order map keyed by name would silently hand one
    account's ACL to another account's block -- so this pins the triple.
    """
    nomes = [posture.bucket_name for posture in estate.aws_bucket_postures]
    assert len(set(nomes)) < len(nomes), "o estate nao repete nomes de bucket: a ambiguidade nao seria exercitada"
    order = _response_order(trees[acl_mod.RENDER_DIR])
    assert len({item["bucket"] for item in order}) < len(order)
    assert len({(item["account"], item["region"], item["bucket"]) for item in order}) == len(order)


def test_ignore_public_acls_so_suprime_grants_publicos_e_nao_o_grupo_de_logs(
    estate: CanonicalEstate,
) -> None:
    """The suppression is by the TWO public groups, and ``LogDelivery`` survives.

    AWS defines public as grants to ``AllUsers`` or ``AuthenticatedUsers`` -- and nothing else.
    A suppression that filtered on "any group" would wrongly erase the documented
    ``log-delivery-write`` canned ACL, which grants WRITE and READ_ACP to the LogDelivery group
    and is explicitly not public.
    """
    com_logs = [
        posture
        for posture in estate.aws_bucket_postures
        if any(grant.uri == S3_LOG_DELIVERY_URI for grant in posture.acl_grants)
    ]
    assert com_logs, "o estate nao produz nenhum bucket com grant de LogDelivery"
    for posture in com_logs:
        if posture.public_access_block.ignore_public_acls:
            continue  # nenhum perfil combina LogDelivery com IgnorePublicAcls
        assert any(grant.uri == S3_LOG_DELIVERY_URI for grant in posture.effective_grants())


def test_a_proveniencia_conta_os_grants_suprimidos(trees: dict[str, Path]) -> None:
    report = _load(trees[acl_mod.RENDER_DIR], "_provenance.json")
    counts = report["counts"]
    assert counts["grants_stored"] > counts["grants_published"]
    assert counts["grants_suppressed_by_ignore_public_acls"] == (
        counts["grants_stored"] - counts["grants_published"]
    )
    assert counts["buckets_with_ignore_public_acls"] > 0


# -- JUDGEMENT 2: "public" is about the RECIPIENT ----------------------------


def test_publico_e_sobre_o_recebedor_e_nao_sobre_o_nome_da_permissao(
    estate: CanonicalEstate,
) -> None:
    """The estate must carry a public ACL and a NON-public group grant, or nothing is proven.

    A consumer that treated any group grant as public would flag the LogDelivery buckets; a
    consumer that treated only ``ALL_USERS`` as public would miss the ``authenticated-read``
    posture. Both fail here, which is what makes the pair meaningful.
    """
    def tem_grupo(posture: AwsBucketPosture, uri: str) -> bool:
        return any(grant.uri == uri for grant in posture.effective_grants())

    all_users = [p for p in estate.aws_bucket_postures if tem_grupo(p, S3_ALL_USERS_URI)]
    autenticados = [p for p in estate.aws_bucket_postures if tem_grupo(p, S3_AUTHENTICATED_USERS_URI)]
    logs = [p for p in estate.aws_bucket_postures if tem_grupo(p, S3_LOG_DELIVERY_URI)]
    assert all_users, "nenhum bucket expoe ao grupo AllUsers"
    assert autenticados, "nenhum bucket expoe ao grupo AuthenticatedUsers: a definicao nomeia os dois"
    assert logs, "nenhum bucket concede ao LogDelivery"


# -- JUDGEMENT 3: the response has no bucket name, so ORDER is the join -------


def test_a_ordem_das_respostas_e_a_mesma_nas_tres_superficies_por_bucket(
    trees: dict[str, Path], estate: CanonicalEstate
) -> None:
    """Three responses carry no member that names the bucket; the join is by POSITION.

    ``AccessControlPolicy``, ``PublicAccessBlockConfiguration`` and the ``Policy`` element all
    describe ONE bucket and none of them names it. Rather than invent a ``bucketName`` member,
    the three surfaces share one documented order -- (account, region, bucket) -- and each
    records the mapping in its provenance. If the three orders ever diverge, a consumer joining
    by position would silently read one bucket's ACL against another's block.
    """
    orders = {module.RENDER_DIR: _response_order(trees[module.RENDER_DIR]) for module in (acl_mod, pab_mod, policy_mod)}
    reference = orders[acl_mod.RENDER_DIR]
    assert reference, "proveniencia sem mapa de ordem"
    for render_dir, order in orders.items():
        assert order == reference, f"{render_dir}: ordem das respostas divergente das irmaas"

    esperados = sorted(
        ((p.account_id, p.region_id, p.bucket_name) for p in estate.aws_bucket_postures),
    )
    obtidos = [(item["account"], item["region"], item["bucket"]) for item in reference]
    assert obtidos == esperados
    assert len({item["index"] for item in reference}) == len(reference)


def test_o_mapa_de_ordem_bate_com_o_artefato(trees: dict[str, Path]) -> None:
    """The index in the provenance must address a real response, not drift from it."""
    tree = trees[acl_mod.RENDER_DIR]
    respostas = cast("list[dict[str, Any]]", _load(tree, "get-bucket-acl-response.json"))
    order = _response_order(tree)
    assert [item["index"] for item in order] == list(range(len(respostas)))


# -- JUDGEMENT 4: the two sides, in the SAME state ---------------------------


def test_o_estate_traz_postura_dos_dois_lados_das_tres_regras(
    estate: CanonicalEstate,
) -> None:
    """At least one bucket violates each rule AND at least one complies with it.

    Same argument as the Increment 2's network rules: a state that only exposed would prove
    nothing, because a consumer that inverted the read/write test would score identically.
    The three rules read three different facts, so the split has to exist in all three.
    """
    from tools.synthetic_clouds.render.config_compliance_by_rule import (  # noqa: PLC0415
        SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS,
        SEMANTICS_S3_PUBLIC_READ_PROHIBITED,
        SEMANTICS_S3_PUBLIC_WRITE_PROHIBITED,
        _violacoes_s3,
    )

    for semantics in (
        SEMANTICS_S3_PUBLIC_READ_PROHIBITED,
        SEMANTICS_S3_PUBLIC_WRITE_PROHIBITED,
        SEMANTICS_S3_BUCKET_LEVEL_PUBLIC_ACCESS,
    ):
        violando, razao = _violacoes_s3(semantics, list(estate.aws_bucket_postures))
        assert 0 < len(violando) < len(estate.aws_bucket_postures), (
            f"{semantics}: {len(violando)} de {len(estate.aws_bucket_postures)} buckets violam; "
            "sem os dois lados nao ha o que provar"
        )
        assert razao.strip()


def test_o_curto_circuito_do_block_publica_vence_a_policy_que_e_publica(
    estate: CanonicalEstate,
) -> None:
    """``BlockPublicPolicy`` on makes the rule pass EVEN WITH a wildcard policy.

    The rule's first clause is a disjunction whose first term is the block: "The Block Public
    Access setting restricts public policies OR the bucket policy does not allow public read
    access". A renderer that only asked "is the policy public?" would answer NON_COMPLIANT
    where AWS answers COMPLIANT -- the single most likely way to get this rule wrong.
    """
    from tools.synthetic_clouds.render.config_compliance_by_rule import (  # noqa: PLC0415
        SEMANTICS_S3_PUBLIC_READ_PROHIBITED,
        _policy_e_publico,
        _violacoes_s3,
    )

    publicas_com_block = [
        posture
        for posture in estate.aws_bucket_postures
        if _policy_e_publico(posture, ("s3:Get", "s3:List"))
    ]
    bloqueadas = [p for p in publicas_com_block if p.public_access_block.restricts_public_policies]
    assert bloqueadas, (
        "o estate nao produz nenhum bucket com policy publica E BlockPublicPolicy ligado: "
        "o curto-circuito da regra nunca seria exercitado"
    )
    violando = set(_violacoes_s3(SEMANTICS_S3_PUBLIC_READ_PROHIBITED, bloqueadas)[0])
    for posture in bloqueadas:
        assert posture.bucket_name not in violando, (
            f"{posture.bucket_name}: policy publica com BlockPublicPolicy ligado foi reprovada"
        )


# -- the model itself --------------------------------------------------------


def test_a_postura_vive_no_estate_e_nao_no_resource(estate: CanonicalEstate) -> None:
    """The posture is a collection keyed by the bucket, NOT a column on ``Resource``.

    ``Resource`` is the FOCUS 1.2 identity carrier and every billing consumer reads it column
    by column; adding a bucket ACL to it would put a field no FOCUS column defines inside the
    record that defines all of them.
    """
    campos_resource = set(CanonicalEstate.__dataclass_fields__)
    assert "aws_bucket_postures" in campos_resource
    campos = set(type(estate.resources[0]).__dataclass_fields__)
    for proibido in ("acl", "public_access_block", "bucket_policy", "grants"):
        assert not any(proibido in campo for campo in campos), (
            f"postura vazou para Resource: {[c for c in campos if proibido in c]}"
        )


def test_toda_postura_aponta_para_um_bucket_do_estate(estate: CanonicalEstate) -> None:
    """The join is closed: every posture has a bucket behind it, and vice versa."""
    uuids_bucket = {
        resource.identity.uuid
        for resource in estate.resources
        if resource.identity.provider == PROVIDER_KEY_AWS and resource.resource_type == "s3_bucket"
    }
    uuids_postura = {posture.resource_uuid for posture in estate.aws_bucket_postures}
    assert uuids_postura == uuids_bucket
    assert len(uuids_postura) == len(estate.aws_bucket_postures), "postura repetida para o mesmo bucket"


def test_a_listagem_e_por_conta_e_as_outras_tres_por_bucket(
    estate: CanonicalEstate, trees: dict[str, Path]
) -> None:
    """One artifact per ACCOUNT for ListBuckets, one response per BUCKET for the rest.

    ``ListBuckets`` lists every bucket the caller owns and each bucket's region travels inside
    the ``Bucket`` object -- so one response per (account, region) would count the same bucket
    set once per region. The other three are per-bucket calls by construction.
    """
    respostas = cast("list[dict[str, Any]]", _load(trees[list_mod.RENDER_DIR], "list-buckets-response.json"))
    contas = {posture.account_id for posture in estate.aws_bucket_postures}
    assert len(respostas) == len(contas)
    assert len(contas) > 1, "o estate nao tem mais de uma conta: o escopo de conta nao seria exercitado"

    for module in (acl_mod, pab_mod, policy_mod):
        arvore = trees[module.RENDER_DIR]
        respostas_por_bucket = {
            acl_mod: "get-bucket-acl-response.json",
            pab_mod: "get-public-access-block-response.json",
            policy_mod: "get-bucket-policy-response.json",
        }[module]
        registros = cast("list[dict[str, Any]]", _load(arvore, respostas_por_bucket))
        assert len(registros) == len(estate.aws_bucket_postures)


def test_bucket_arn_e_nulo_por_contrato_e_nao_por_gap(trees: dict[str, Path]) -> None:
    """The ``Bucket`` page supports the ARN for DIRECTORY buckets only.

    Every bucket in this estate is a general purpose one, so the column is emitted null and
    the reason says why. A non-null ARN would be an invented fact, not a derivation.
    """
    buckets = cast("list[dict[str, Any]]", _load(trees[list_mod.RENDER_DIR], "bucket.json"))
    assert buckets
    assert all(bucket["BucketArn"] is None for bucket in buckets)
    report = _load(trees[list_mod.RENDER_DIR], "_provenance.json")
    lacunas = {entry["field"]: entry["reason"] for entry in report["model_gaps"]}
    assert "BucketArn" in lacunas
    assert "directory bucket" in lacunas["BucketArn"].lower()


def test_um_bucket_sem_policy_publica_policy_nulo_e_nao_documento_vazio(
    estate: CanonicalEstate, trees: dict[str, Path]
) -> None:
    """No policy is a legitimate state: ``Policy`` is null, not an invented empty document.

    The action reports a bucket with no policy as ``NoSuchBucketPolicy``, and ``Policy`` is not
    a required element. Filling it with an empty ``Statement`` would assert the bucket HAS a
    policy that does not exist.
    """
    sem_policy = [p for p in estate.aws_bucket_postures if p.policy is None]
    assert sem_policy, "o estate nao produz nenhum bucket sem policy: o caminho nulo nunca seria exercitado"
    registros = cast("list[dict[str, Any]]", _load(trees[policy_mod.RENDER_DIR], "get-bucket-policy-response.json"))
    nulos = [registro for registro in registros if registro["Policy"] is None]
    assert len(nulos) == len(sem_policy)


# -- determinism -------------------------------------------------------------


def test_os_quatro_renderers_sao_byte_a_byte_deterministicos(
    estate: CanonicalEstate, trees: dict[str, Path], tmp_path: Path
) -> None:
    """A rebuild writes the same bytes, so the artifacts can be diffed against a baseline."""
    for module in _RENDERERS:
        outro = _render(module, estate, tmp_path)
        for arquivo in sorted((trees[module.RENDER_DIR]).glob("*.json")):
            if arquivo.name == "_provenance.json":
                continue  # the map carries no absolute path, but ordering is asserted elsewhere
            assert arquivo.read_bytes() == (outro / arquivo.name).read_bytes(), (
                f"{module.RENDER_DIR}/{arquivo.name}: rebuild nao reproduziu os bytes"
            )


def _response_order(tree: Path) -> list[dict[str, Any]]:
    """The explicit (account, region, bucket) -> index map a provenance writes."""
    return cast("list[dict[str, Any]]", _load(tree, "_provenance.json")["response_order"])