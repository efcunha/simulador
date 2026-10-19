"""Golden tests for ``aws/config-describe-compliance-by-config-rule``.

The point of this module is to confront the DELIVERED artifact with
``specs/aws/config-describe-compliance-by-config-rule.schema.json`` -- names, values and the
empty contract -- and to hold the two judgement calls this surface makes, which are the ones
that would be easy to get quietly wrong:

1. **the rule names are real.** Every ``ConfigRuleName`` is an AWS Config *managed* rule, read
   out of the official list and checked against it, because a synthetic ``synth-*`` name would
   make the surface useless for checking a posture screen;
2. **a verdict is only asserted when the estate carries the fact.** All fourteen rules are now
   evaluated from the estate, so the tests below RECOUNT every verdict here from the model's own
   state, independently of the renderer, so the test cannot rubber-stamp it.

WHAT CHANGED IN THE INCREMENT 4.3
---------------------------------
The last three rules became answerable, closing every model gap in this catalog:
``cloudtrail-enabled``, ``securityhub-enabled`` and ``vpc-flow-logs-enabled``. They were
``INSUFFICIENT_DATA`` in every scope for a MODEL reason -- the estate carried no CloudTrail
trail, no Security Hub enrolment and no per-VPC flow-log configuration -- which is the one kind
of gap this surface is supposed to close rather than report.

They close the residue with a granularity the previous increments never used, because it is the
granularity the AWS publishes rather than the one that is convenient here:

* ``cloudtrail-enabled`` and ``securityhub-enabled`` read the ACCOUNT. Both pages carry trigger
  ``Periodic`` and NO "Resource Types", so they answer in all nine scopes with the same verdict
  per account -- the account-level half the identity rules opened in the Increment 4;
* ``vpc-flow-logs-enabled`` reads a RESOURCE (``Resource Types: AWS::EC2::VPC``), and it is the
  only rule in this catalog that turns ONE violating resource out of several into a
  NON_COMPLIANT rule -- which is what "for at least one Amazon VPC" means.

So the evaluated set still splits in two -- rules that read a resource, and rules that read the
account -- and :func:`test_as_regras_avaliadas_sao_as_unicas_sem_lacuna_e_ou_leem_recurso_ou_leem_conta`
asserts the two halves separately instead of pretending they are one.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import AwsSecurityGroup
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.model.storage import S3_ALL_USERS_URI, S3_AUTHENTICATED_USERS_URI
from tools.synthetic_clouds.render import _config_evaluators as evaluators_mod
from tools.synthetic_clouds.render import config_compliance_by_rule as mod
from tools.synthetic_clouds.render.base import RenderError, registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC_FILE = "config-describe-compliance-by-config-rule.schema.json"
_SPEC_PATH = _REPO_ROOT / "specs" / "aws" / _SPEC_FILE

# The four domains the catalog must cover, and the rules that witness each one. Written out
# here so that dropping a domain -- or renaming a rule away from its domain -- fails the test
# instead of silently shrinking the surface.
_DOMAINS: dict[str, frozenset[str]] = {
    "s3-public-exposure": frozenset(
        {
            "s3-bucket-public-read-prohibited",
            "s3-bucket-public-write-prohibited",
            "s3-bucket-level-public-access-prohibited",
        }
    ),
    "network": frozenset({"restricted-ssh", "restricted-common-ports", "vpc-default-security-group-closed"}),
    "identity": frozenset({"root-account-mfa-enabled", "iam-password-policy", "access-keys-rotated"}),
    "audit-guardrails": frozenset({"cloudtrail-enabled", "securityhub-enabled"}),
}

# The nine rules the estate can answer FROM A RESOURCE, and the ``Resource.resource_type`` each
# one reads. The three S3 ones joined this list in the Increment 3, with the bucket POSTURE the
# renderer reads -- ACL, bucket policy and Block Public Access -- instead of the group's rules --
# and ``vpc-flow-logs-enabled`` joined it in the Increment 4.3 with the per-VPC flow-log
# configuration. It is the only member whose verdict turns on ONE sibling out of several.
_EVALUATED: dict[str, str] = {
    "s3-bucket-tagged": "s3_bucket",
    "lambda-function-tagged": "lambda_function",
    "restricted-ssh": "security_group",
    "restricted-common-ports": "security_group",
    "vpc-default-security-group-closed": "security_group",
    "vpc-flow-logs-enabled": "vpc",
    "s3-bucket-public-read-prohibited": "s3_bucket",
    "s3-bucket-public-write-prohibited": "s3_bucket",
    "s3-bucket-level-public-access-prohibited": "s3_bucket",
}

#: The three rules the estate can answer FROM THE ACCOUNT, not from a resource. They joined
#: the evaluated set in the Increment 4, when the estate gained each account's root MFA,
#: password policy, IAM users and access keys. IAM is global, so ``resource_type`` stays
#: ``None`` for all three -- and that ``None`` is now a second way of being evaluated, which
#: is why they are listed apart from :data:`_EVALUATED` instead of folded into it.
_IDENTITY_RULES: frozenset[str] = frozenset(
    {
        "root-account-mfa-enabled",
        "iam-password-policy",
        "access-keys-rotated",
    }
)

#: The other two ACCOUNT-level rules, added by the Increment 4.3. They are listed apart from
#: :data:`_IDENTITY_RULES` for a reason that is not cosmetic: they read a DIFFERENT posture
#: (``estate.aws_audit_postures``, not ``aws_identity_postures``). A renderer that answered a
#: CloudTrail verdict out of an IAM posture would produce a plausible-looking answer here --
#: both are per-account booleans -- and it is precisely that swap this separation makes
#: visible.
_AUDIT_RULES: frozenset[str] = frozenset({"cloudtrail-enabled", "securityhub-enabled"})

#: Every rule that reads the ACCOUNT rather than a resource. Their pages carry trigger
#: ``Periodic`` and NO "Resource Types", which is the published reason and the only reason.
_ACCOUNT_SCOPED: frozenset[str] = _IDENTITY_RULES | _AUDIT_RULES

#: Every rule the surface answers from the estate: the resource-scoped ones and the
#: account-scoped ones. As of the Increment 4.3 this is the WHOLE catalog, and the gap every
#: other rule used to carry is exactly its complement.
_ANSWERED: frozenset[str] = frozenset(_EVALUATED) | _ACCOUNT_SCOPED

#: The three S3 exposure rules, answered from ``estate.aws_bucket_postures``.
_S3_RULES = frozenset(
    {
        "s3-bucket-public-read-prohibited",
        "s3-bucket-public-write-prohibited",
        "s3-bucket-level-public-access-prohibited",
    }
)

#: The rules answered from the security groups' RULES rather than from tags.
_NETWORK_RULES: frozenset[str] = frozenset(
    {"restricted-ssh", "restricted-common-ports", "vpc-default-security-group-closed"}
)

_VERDICTS = {"COMPLIANT", "NON_COMPLIANT", "INSUFFICIENT_DATA"}


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    """The base small estate (seed 123): the resources every rule reads."""
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_spec(_SPEC_PATH)


@pytest.fixture(scope="module")
def tree(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    written = mod.ConfigComplianceByRuleRenderer().render(estate, tmp_path_factory.mktemp("compliance"))
    assert written
    return written[0].parent


def _load(tree: Path, name: str) -> Any:
    return json.loads((tree / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def items(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "compliance-by-config-rule.json"))


@pytest.fixture(scope="module")
def responses(tree: Path) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", _load(tree, "describe-compliance-by-config-rule-response.json"))


# -- the renderer is wired ----------------------------------------------------


def test_o_renderer_esta_registrado() -> None:
    assert mod.RENDER_DIR in registered_names()
    assert mod.ConfigComplianceByRuleRenderer.name == "config_compliance_by_rule"


def test_a_spec_cita_a_acao_e_a_data_da_consulta(spec: Any) -> None:
    assert spec.surface == mod.SURFACE == "aws/config-describe-compliance-by-config-rule"
    assert spec.provider == "aws"
    assert spec.reference["url"].endswith("API_DescribeComplianceByConfigRule.html")
    assert spec.reference["consulted_at"] == "2026-10-16"


def test_a_spec_tem_os_cinco_conjuntos_documentados(spec: Any) -> None:
    assert [s.name for s in spec.sets] == [
        "describe-compliance-by-config-rule-response",
        "compliance-by-config-rule",
        "compliance",
        "compliance-contributor-count",
        "request-parameters",
    ]
    # 2 + 2 + 2 + 2 + 3; ``NextToken`` appears twice by design (response AND request side).
    assert len(spec.names) == 11


def test_a_entrega_e_json_e_read_api(spec: Any) -> None:
    assert spec.delivery["kind"] == "read_api"
    # The AWS Config API Reference publishes the response as JSON, so here the delivered
    # encoding IS the documented one -- there is no divergence to declare, unlike the EC2
    # DescribeInstances surface whose Reference publishes XML only.
    assert spec.delivery["format"] == "json"


# -- THE GOLDEN PART: artifact fields against the spec ------------------------


@pytest.mark.parametrize(
    ("file_name", "scope"),
    [
        ("describe-compliance-by-config-rule-response.json", mod.RESPONSE_SCOPE),
        ("compliance-by-config-rule.json", mod.ITEM_SCOPE),
        ("compliance.json", mod.COMPLIANCE_SCOPE),
        ("compliance-contributor-count.json", mod.CONTRIBUTOR_SCOPE),
        ("request-parameters.json", mod.REQUEST_SCOPE),
    ],
)
def test_cada_artefato_carrega_exatamente_os_campos_do_seu_conjunto(
    spec: Any, tree: Path, file_name: str, scope: str
) -> None:
    """The artifact, not the renderer's intent, has to match the specification."""
    findings = check_artifact(spec, tree / file_name, scope=scope)
    assert is_faithful(findings), [f"{f.kind}: {f.detail}" for f in findings]


def test_a_proveniencia_registra_as_lacunas_que_os_itens_nao_conseguem(tree: Path) -> None:
    """The reasons live beside the data -- never inside it.

    An ingestor of ``compliance-by-config-rule.json`` must not see a key no cloud documents, so
    the ``CapExceeded`` ceiling and the three request-side empties are reported in
    ``_provenance.json``.

    Since the Increment 4.3 this catalog has NO per-rule model gap at all: every entry in
    ``model_gaps`` is now a ``field`` entry, and the ``rule``-keyed list is empty. The reason is
    that a rule-level gap asserted as empty is the only assertion that would catch a future
    rule being added without a fact to read -- a new gap would silently be indistinguishable
    from "this surface never had one".
    """
    report = _load(tree, mod.PROVENANCE_PATH)
    assert report["kind"] == "provenance"
    assert report["surface"] == mod.SURFACE
    assert report["spec"] == f"specs/aws/{_SPEC_FILE}"
    gaps = {entry["rule"] for entry in report["model_gaps"] if "rule" in entry}
    assert gaps == set(mod.catalog_names()) - _ANSWERED
    assert gaps == set(), f"o catalogo voltou a ter regra sem lacuna nomeada: {sorted(gaps)}"
    assert all(entry["reason"].strip() for entry in report["model_gaps"])
    # And the counter-report agrees with the artifact: no rule is listed as unevaluable.
    assert report["counts"]["unevaluable_rules"] == []
    assert set(report["counts"]["evaluated_rules"]) == set(mod.catalog_names())


# -- the catalog is REAL managed rules ---------------------------------------


def test_o_catalogo_tem_pelo_menos_doze_regras_reais() -> None:
    names = mod.catalog_names()
    assert len(names) >= 12
    assert len(set(names)) == len(names)
    # Every name matches the documented ``ConfigRuleNames`` request pattern [A-Za-z0-9_-]+ and
    # fits the 1..64 window the ConfigRuleName field publishes.
    for name in names:
        assert 1 <= len(name) <= 64
        assert name.replace("-", "").replace("_", "").isalnum()


def test_o_catalogo_cobre_os_quatro_dominios() -> None:
    names = set(mod.catalog_names())
    for domain, expected in _DOMAINS.items():
        assert expected <= names, f"dominio {domain} perdeu regra: {sorted(expected - names)}"


def test_as_regras_avaliadas_sao_as_unicas_sem_lacuna_e_ou_leem_recurso_ou_leem_conta() -> None:
    """A rule is answered iff it carries no gap -- and it must read SOMETHING.

    This was one equality at the Increment 2 (``com_recurso == sem_lacuna == _EVALUATED``),
    because every evaluated rule read a ``Resource``. The identity rules broke it on purpose in
    the Increment 4, and the audit rules broke it the same way in the Increment 4.3 -- IAM, and
    then CloudTrail and Security Hub, are configured per account, so those five read the ACCOUNT
    and their ``resource_type`` is ``None``.

    So the invariant is restated rather than relaxed: no gap means the rule is evaluated, and an
    evaluated rule reads either a resource type OR the account. A rule with no gap that reads
    NEITHER would be a rule this surface claims to answer while answering nothing, and that is
    exactly what the two halves of the assertion below refuse.

    The account half is now checked against the RENDERER'S OWN dispatch table rather than a
    hand-written list, so a rule declared account-level without a matching evaluator fails here
    instead of at the first scope.
    """
    com_recurso = {rule.name for rule in mod.CATALOG if rule.resource_type is not None}
    sem_lacuna = {rule.name for rule in mod.CATALOG if not rule.gap}
    assert com_recurso == set(_EVALUATED)
    assert sem_lacuna == _ANSWERED

    por_conta = {rule.name for rule in mod.CATALOG if rule.semantics in mod._ACCOUNT_SEMANTICS}
    assert por_conta == _ACCOUNT_SCOPED
    # As duas metades sao disjuntas e juntas cobrem tudo que e avaliado: uma regra por conta
    # nao pode declarar um resource_type, senao voltaria a ser lida duas vezes.
    assert not (por_conta & com_recurso)
    assert por_conta | com_recurso == sem_lacuna

    # Todo avaliador registrado no modulo de semantica tem uma regra correspondente no
    # catalogo, e vice-versa para o subconjunto que o modulo cobre: as cinco regras POR CONTA
    # mais ``vpc-flow-logs-enabled``. As outras oito regras de recurso sao avaliadas inline no
    # renderer (``_violacoes_rede``, ``_violacoes_s3`` e a contagem de tags) e por isso nao
    # aparecem aqui -- e essa assimetria e o que impede uma regra de recurso de ser respondida
    # por um avaliador que le conta.
    registrados = (
        set(evaluators_mod.IAM_RULE_EVALUATORS)
        | set(evaluators_mod.ACCOUNT_AUDIT_RULE_EVALUATORS)
        | set(evaluators_mod.VPC_FLOW_LOG_RULE_EVALUATORS)
    )
    assert registrados == _ACCOUNT_SCOPED | {"vpc-flow-logs-enabled"}
    assert registrados <= set(mod.catalog_names())
    assert not (set(evaluators_mod.ACCOUNT_AUDIT_RULE_EVALUATORS) & com_recurso)

    for rule in mod.CATALOG:
        if rule.gap:
            assert rule.gap.strip(), f"{rule.name} sem motivo de lacuna"
            assert rule.source_url.startswith("https://docs.aws.amazon.com/config/")
        else:
            assert rule.semantics.strip(), f"{rule.name} avaliada sem semantica declarada"
            assert rule.source_url.endswith(f"/{rule.name}.html"), (
                f"{rule.name} avaliada cita a pagina errada: {rule.source_url}"
            )


def test_toda_regra_do_artefato_sai_do_catalogo(items: list[dict[str, Any]]) -> None:
    assert {item["ConfigRuleName"] for item in items} == set(mod.catalog_names())


# -- the verdicts, and what they are NOT allowed to say -----------------------


def test_nenhum_veredito_fora_do_enum_documentado(items: list[dict[str, Any]]) -> None:
    for item in items:
        assert item["Compliance"]["ComplianceType"] in _VERDICTS


def test_not_applicable_nunca_e_emitido(items: list[dict[str, Any]]) -> None:
    """``NOT_APPLICABLE`` is in the field's enum but is NOT supported by the type.

    The ``Compliance`` page lists it under Valid Values and then says, in the same page, that
    "AWS Config does not support the NOT_APPLICABLE value for the Compliance data type".
    Reading only the enum would invite exactly this value; the API reports the
    all-NOT_APPLICABLE case as INSUFFICIENT_DATA instead.
    """
    assert not [item for item in items if item["Compliance"]["ComplianceType"] == "NOT_APPLICABLE"]
    assert mod.NOT_APPLICABLE_EMITTED is False


def _esperado(candidates: list[Resource]) -> tuple[str, int]:
    """The verdict the PUBLISHED rule text implies, computed without the renderer.

    The tagged rules are NON_COMPLIANT iff the resource has no countable tag; a rule with no
    resource to evaluate has no result; and ``ComplianceContributorCount`` counts the resources
    that CAUSE the NON_COMPLIANT result -- so a COMPLIANT rule carries 0.
    """
    if not candidates:
        return ("INSUFFICIENT_DATA", 0)
    violando = [
        r for r in candidates if not any(not key.lower().startswith(mod.RESERVED_TAG_PREFIX) for key, _ in r.tags)
    ]
    return ("NON_COMPLIANT", len(violando)) if violando else ("COMPLIANT", 0)


def _porta_aberta(rule: Any, porta: int) -> bool:
    """True when an ingress rule admits TCP ``porta`` -- recounted here, not borrowed.

    Deliberately a SECOND implementation: the renderer's ``_permite_porta`` is the thing under
    test, so reusing it would make this an assertion that the renderer agrees with itself. An
    all-protocol rule (``-1``) admits every port, per the ``IpPermission`` page.
    """
    if rule.ip_protocol == "-1":
        return True
    if rule.ip_protocol != "tcp":
        return False
    return (rule.from_port is None or porta >= rule.from_port) and (
        rule.to_port is None or porta <= rule.to_port
    )


def _esperado_rede(regra: str, groups: list[AwsSecurityGroup]) -> tuple[str, int]:
    """The verdict of one network rule, recomputed from each managed rule's own page.

    * ``restricted-ssh`` -- COMPLIANT iff the incoming SSH sources are "restricted (CIDR other
      than 0.0.0.0/0 or ::/0)";
    * ``restricted-common-ports`` -- COMPLIANT iff a blocked port (the page's own defaults, since
      this renderer passes no parameters) is not open to the whole internet through an inbound
      TCP rule;
    * ``vpc-default-security-group-closed`` -- NON_COMPLIANT iff the DEFAULT group has one or
      more inbound OR outbound rules, and only the default group is evaluated at all.

    A scope holding no security group at all has not evaluated anything, which the API reports
    as ``INSUFFICIENT_DATA`` -- and a COMPLIANT verdict there would mean "everything it looked at
    complied" about a set that is empty.
    """
    if not groups:
        return ("INSUFFICIENT_DATA", 0)
    if regra == "vpc-default-security-group-closed":
        padroes = [g for g in groups if g.group_name == "default"]
        if not padroes:
            return ("INSUFFICIENT_DATA", 0)
        abertos = [g for g in padroes if g.ingress or g.egress]
        return ("NON_COMPLIANT", len(abertos)) if abertos else ("COMPLIANT", 0)

    portas = (22,) if regra == "restricted-ssh" else (20, 21, 3389, 3306, 4333)
    violando: list[AwsSecurityGroup] = []
    for group in groups:
        for ingress in group.ingress:
            cobre = any(_porta_aberta(ingress, porta) for porta in portas)
            origem_irrestrita = any(
                entry.cidr_ip in ("0.0.0.0/0", "::/0") for entry in ingress.ip_ranges
            )
            if cobre and origem_irrestrita:
                violando.append(group)
                break
    return ("NON_COMPLIANT", len(violando)) if violando else ("COMPLIANT", 0)


def _esperado_identidade(rule_name: str, posture: Any, sim_now: Any) -> tuple[str, int]:
    """Recount an identity verdict from the model's own facts, independently of the renderer.

    A second implementation on purpose, like :func:`_esperado_s3` beside it. It re-derives
    each managed rule's own published condition from ``AwsIdentityPosture`` rather than
    calling ``_config_evaluators``, so a renderer that swapped two rules, inverted a
    requirement or ignored ``status``/``status``-vs-age fails here even if the evaluator and
    the artifact agree with each other.
    """
    if rule_name == "root-account-mfa-enabled":
        # The rule reads the ROOT account, not any IAM user. The estate has accounts where the
        # two disagree, so a renderer reading ``user.mfa_active`` here would be caught.
        return ("COMPLIANT", 0) if posture.root_mfa.mfa_active else ("NON_COMPLIANT", 1)
    if rule_name == "iam-password-policy":
        politica = posture.password_policy
        params = const.AWS_IAM_RULE_PARAMETERS["iam-password-policy"]
        falhas = 0 if politica.minimum_password_length >= params["minimumPasswordLength"] else 1
        falhas += sum(
            1
            for nome, observado in (
                ("requireSymbols", politica.require_symbols),
                ("requireNumbers", politica.require_numbers),
                ("requireUppercaseCharacters", politica.require_uppercase),
                ("requireLowercaseCharacters", politica.require_lowercase),
            )
            if params[nome] >= 0 and not observado
        )
        return ("NON_COMPLIANT", falhas) if falhas else ("COMPLIANT", 0)
    # ``access-keys-rotated``: ACTIVE keys older than the window. An INACTIVE key of any age
    # must not count, and ``last_used_date`` must not be consulted.
    janela = const.AWS_IAM_RULE_PARAMETERS["access-keys-rotated"]["maxAccessKeysAge"]
    vencidas = [
        chave
        for usuario in posture.users
        for chave in usuario.access_keys
        if chave.status == "Active"
        and (sim_now - date.fromisoformat(chave.create_date)).days > janela
    ]
    return ("NON_COMPLIANT", len(vencidas)) if vencidas else ("COMPLIANT", 0)


def _esperado_auditoria(rule_name: str, posture: Any) -> tuple[str, int]:
    """Recount an AUDIT verdict from the model's own facts, independently of the renderer.

    A second implementation on purpose, like :func:`_esperado_identidade` and :func:`_esperado_s3`
    beside it -- it reads ``AwsAuditPosture`` directly and never calls ``_config_evaluators``.

    * ``cloudtrail-enabled`` -- COMPLIANT iff the account has at least one trail. The page's
      three optional parameters (``s3BucketName``, ``cloudWatchLogsLogGroupArn``,
      ``snsTopicArn``) are NOT passed by this renderer, so the rule reduces to that existence
      test; a recount that filtered by bucket would be a different rule, not a second reading of
      this one.
    * ``securityhub-enabled`` -- COMPLIANT iff the Security Hub is enabled. "Parameters: None",
      so there is no reduction to model at all.

    Both count the ACCOUNT as the single contributor of a NON_COMPLIANT result, because the
    thing that failed IS the account.
    """
    if rule_name == "cloudtrail-enabled":
        return ("COMPLIANT", 0) if posture.cloudtrail else ("NON_COMPLIANT", 1)
    if rule_name == "securityhub-enabled":
        return ("COMPLIANT", 0) if posture.security_hub.enabled else ("NON_COMPLIANT", 1)
    raise AssertionError(f"regra de auditoria desconhecida: {rule_name}")


def _esperado_vpc_flow_logs(logs: list[Any]) -> tuple[str, int]:
    """Recount ``vpc-flow-logs-enabled`` over one scope's VPCs, independently.

    The page says the rule is NON_COMPLIANT "if flow logs are not enabled for at least one
    Amazon VPC", and names ``AWS::EC2::VPC`` as the resource type -- so the aggregate is "every
    VPC in the scope has one", and the contributor count is how many do NOT.

    The two states this deliberately does NOT collapse:

    * a scope with NO VPC has evaluated nothing, and the API reports that as
      ``INSUFFICIENT_DATA`` -- not as a COMPLIANT scope that looked at nothing;
    * a VPC whose ``flow_log_ids`` is EMPTY is NON_COMPLIANT, not unmeasurable. The empty list
      is the estate asserting "this VPC has no flow log", and reading it as a gap would hide a
      real violation behind an "I don't know".
    """
    if not logs:
        return ("INSUFFICIENT_DATA", 0)
    sem_log = [log for log in logs if not log.flow_log_ids]
    return ("NON_COMPLIANT", len(sem_log)) if sem_log else ("COMPLIANT", 0)


def test_o_veredito_e_confirmado_pelas_tags_do_modelo(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """Recount the model's own state here, independently of the renderer.

    The fixture carries no account/region field -- the API does not publish one -- so each
    envelope is matched to its scope by POSITION, which is the order the renderer writes them
    in and the order ``_resources_by_scope`` returns.
    """
    scopes = mod._resources_by_scope(estate)
    grupos = {group.resource_uuid: group for group in estate.aws_security_groups}
    posturas = {p.resource_uuid: p for p in estate.aws_bucket_postures}
    identidades = {p.account_id: p for p in estate.aws_identity_postures}
    auditorias = {p.account_id: p for p in estate.aws_audit_postures}
    logs_por_vpc = {log.resource_uuid: log for log in estate.aws_vpc_flow_logs}
    assert len(responses) == len(scopes)
    for ((conta, regiao), recursos), envelope in zip(scopes.items(), responses, strict=True):
        por_regra = {item["ConfigRuleName"]: item["Compliance"] for item in envelope["ComplianceByConfigRules"]}
        assert set(por_regra) == set(mod.catalog_names())
        for rule_name in _IDENTITY_RULES:
            compliance = por_regra[rule_name]
            obtido = (
                compliance["ComplianceType"],
                compliance["ComplianceContributorCount"]["CappedCount"],
            )
            assert conta in identidades, (
                f"{conta}/{regiao} {rule_name}: a conta do escopo nao tem postura de identidade"
            )
            assert obtido == _esperado_identidade(rule_name, identidades[conta], estate.sim_now), (
                f"{conta}/{regiao} {rule_name}"
            )
        for rule_name in _AUDIT_RULES:
            compliance = por_regra[rule_name]
            obtido = (
                compliance["ComplianceType"],
                compliance["ComplianceContributorCount"]["CappedCount"],
            )
            assert conta in auditorias, (
                f"{conta}/{regiao} {rule_name}: a conta do escopo nao tem postura de auditoria"
            )
            assert obtido == _esperado_auditoria(rule_name, auditorias[conta]), (
                f"{conta}/{regiao} {rule_name}"
            )
        for rule_name, resource_type in _EVALUATED.items():
            compliance = por_regra[rule_name]
            obtido = (
                compliance["ComplianceType"],
                compliance["ComplianceContributorCount"]["CappedCount"],
            )
            candidatos = [r for r in recursos if r.resource_type == resource_type]
            if rule_name in _NETWORK_RULES:
                esperado = _esperado_rede(rule_name, [grupos[r.identity.uuid] for r in candidatos])
            elif rule_name in _S3_RULES:
                sem_postura = [r for r in candidatos if r.identity.uuid not in posturas]
                assert not sem_postura, (
                    f"{conta}/{regiao} {rule_name}: {len(sem_postura)} bucket(s) sem postura no estate; "
                    "a regra leria um recurso sem fato"
                )
                esperado = _esperado_s3(rule_name, [posturas[r.identity.uuid] for r in candidatos])
            elif rule_name == "vpc-flow-logs-enabled":
                sem_log = [r for r in candidatos if r.identity.uuid not in logs_por_vpc]
                assert not sem_log, (
                    f"{conta}/{regiao} {rule_name}: {len(sem_log)} VPC(s) sem configuracao de flow log; "
                    "a regra leria uma VPC sem fato"
                )
                esperado = _esperado_vpc_flow_logs([logs_por_vpc[r.identity.uuid] for r in candidatos])
            else:
                esperado = _esperado(candidatos)
            assert obtido == esperado, f"{conta}/{regiao} {rule_name}"


_PUBLIC_GRANTS = {S3_ALL_USERS_URI, S3_AUTHENTICATED_USERS_URI}
_LEITURA_ACL = {"READ", "READ_ACP", "FULL_CONTROL"}
_ESCRITA_ACL = {"WRITE", "WRITE_ACP", "FULL_CONTROL"}
_LEITURA_ACAO = ("s3:Get", "s3:List")
_ESCRITA_ACAO = ("s3:Put", "s3:Delete")


def _esperado_s3(rule_name: str, buckets: list[Any]) -> tuple[str, int]:
    """Recount the S3 verdict from the model's posture, independently of the renderer.

    Deliberately a second implementation: it reads ``effective_grants`` and re-derives the
    block short-circuit from the four booleans, so a renderer that dropped either term of the
    published condition fails this even though the two implementations agree today.
    """
    if not buckets:
        return ("INSUFFICIENT_DATA", 0)

    def acl_publica(permissao: set[str]) -> bool:
        return any(
            grant.uri in _PUBLIC_GRANTS and grant.permission in permissao
            for posture in buckets
            for grant in posture.effective_grants()
        )

    def policy_publica(prefixos: tuple[str, ...]) -> bool:
        return any(
            statement.effect == "Allow"
            and "*" in statement.principals
            and any(action in {"*", "s3:*"} or action.startswith(prefixos) for action in statement.actions)
            for posture in buckets
            if posture.policy is not None
            for statement in posture.policy.statements
        )

    if rule_name == "s3-bucket-level-public-access-prohibited":
        if acl_publica(_LEITURA_ACL) or acl_publica(_ESCRITA_ACL) or policy_publica(_LEITURA_ACAO) or policy_publica(
            _ESCRITA_ACAO
        ):
            return ("NON_COMPLIANT", len(buckets))
        return ("COMPLIANT", 0)

    leitura = rule_name == "s3-bucket-public-read-prohibited"
    permissao, prefixos = (_LEITURA_ACL, _LEITURA_ACAO) if leitura else (_ESCRITA_ACL, _ESCRITA_ACAO)
    violando = [
        posture
        for posture in buckets
        if (
            not posture.public_access_block.restricts_public_policies and policy_publica_em(posture, prefixos)
        )
        or (not posture.public_access_block.restricts_public_acls and acl_publica_em(posture, permissao))
    ]
    return ("NON_COMPLIANT", len(violando)) if violando else ("COMPLIANT", 0)


def policy_publica_em(posture: Any, prefixos: tuple[str, ...]) -> bool:
    """Whether ONE bucket's policy allows a matching action to a wildcard principal."""
    if posture.policy is None:
        return False
    return any(
        statement.effect == "Allow"
        and "*" in statement.principals
        and any(action in {"*", "s3:*"} or action.startswith(prefixos) for action in statement.actions)
        for statement in posture.policy.statements
    )


def acl_publica_em(posture: Any, permissao: set[str]) -> bool:
    """Whether ONE bucket's EFFECTIVE ACL grants ``permissao`` to a public group."""
    return any(grant.uri in _PUBLIC_GRANTS and grant.permission in permissao for grant in posture.effective_grants())


def test_as_regras_de_rede_respondem_em_ambos_os_sentidos(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """Each network rule must produce BOTH a compliant and a non-compliant scope.

    An estate that only exposed would answer NON_COMPLIANT everywhere and prove nothing: a
    consumer with the ports backwards, or a check that ignored the source CIDR entirely, would
    score exactly the same. ``restricted-ssh`` and ``restricted-common-ports`` do read different
    ports here -- 22 in one posture, 3389 in another -- so a renderer that evaluated one rule
    with the other's port list fails this estate too.
    """
    vereditos: dict[str, set[str]] = {name: set() for name in _NETWORK_RULES}
    for envelope in responses:
        for item in envelope["ComplianceByConfigRules"]:
            if item["ConfigRuleName"] in vereditos:
                vereditos[item["ConfigRuleName"]].add(item["Compliance"]["ComplianceType"])
    for name, vistos in vereditos.items():
        assert "NON_COMPLIANT" in vistos, f"{name} so produziu veredito favoravel"
        assert "COMPLIANT" in vistos, f"{name} so produziu veredito desfavoravel"


def test_as_regras_de_s3_respondem_em_ambos_os_sentidos(
    responses: list[dict[str, Any]],
) -> None:
    """Each S3 exposure rule must produce BOTH a compliant and a non-compliant scope.

    Same reasoning as the network rules: an estate that only exposed would answer
    NON_COMPLIANT everywhere and prove nothing, because a consumer that inverted the
    read/write test, or one that ignored the Block Public Access short-circuit entirely,
    would score exactly the same.
    """
    vereditos: dict[str, set[str]] = {name: set() for name in _S3_RULES}
    for envelope in responses:
        for item in envelope["ComplianceByConfigRules"]:
            if item["ConfigRuleName"] in vereditos:
                vereditos[item["ConfigRuleName"]].add(item["Compliance"]["ComplianceType"])
    for name, vistos in vereditos.items():
        assert "NON_COMPLIANT" in vistos, f"{name} so produziu veredito favoravel"
        assert "COMPLIANT" in vistos, f"{name} so produziu veredito desfavoravel"


def test_o_grupo_padrao_avaliado_e_o_unico_nomeado_default(
    estate: CanonicalEstate,
) -> None:
    """``vpc-default-security-group-closed`` must not read a group that is not the default one.

    The page scopes the rule to "the default security group of any Amazon Virtual Private Cloud",
    and the official Sample Response identifies that group by ``groupName = "default"``. Counting
    every security group here would make the rule answer about fifteen groups, of which at most
    one per VPC is the default.
    """
    padroes = [g for g in estate.aws_security_groups if g.group_name == "default"]
    assert padroes, "o estate nao produz nenhum grupo padrao: a regra nunca teria o que avaliar"
    # One per (account, region): a VPC has exactly one default group.
    assert len(padroes) == len({g.vpc_id for g in padroes})
    # And they are not all the same posture, or the rule could not be told apart from "any group".
    postures = {(bool(g.ingress), bool(g.egress)) for g in padroes}
    assert len(postures) > 1, "todos os grupos padrao tem a mesma postura"


def test_as_regras_de_auditoria_respondem_em_ambos_os_sentidos(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """Each audit rule must produce BOTH a compliant and a non-compliant account.

    Same reasoning as the network and S3 rules: an estate where every account fails would prove
    nothing, because a consumer that inverted the boolean -- or, worse, one that answered
    ``cloudtrail-enabled`` out of the Security Hub field, both being per-account booleans --
    would score exactly the same.

    The estate's rotation makes each rule fail on a DIFFERENT account, so the two NON_COMPLIANT
    scopes cannot be the same one: swapping the two evaluators here changes at least one verdict.
    """
    vereditos: dict[str, set[str]] = {name: set() for name in _AUDIT_RULES}
    for envelope in responses:
        for item in envelope["ComplianceByConfigRules"]:
            if item["ConfigRuleName"] in vereditos:
                vereditos[item["ConfigRuleName"]].add(item["Compliance"]["ComplianceType"])
    for name, vistos in vereditos.items():
        assert "NON_COMPLIANT" in vistos, f"{name} so produziu veredito favoravel"
        assert "COMPLIANT" in vistos, f"{name} so produziu veredito desfavoravel"

    # The two rules must not fail on the same account, or they would be indistinguishable.
    reprovam = {
        name: {p.account_id for p in estate.aws_audit_postures if not _aprovada(name, p)}
        for name in _AUDIT_RULES
    }
    assert reprovam["cloudtrail-enabled"] != reprovam["securityhub-enabled"]


def _aprovada(rule_name: str, posture: Any) -> bool:
    """Whether the audit posture satisfies ``rule_name`` -- a third, independent reading."""
    if rule_name == "cloudtrail-enabled":
        return bool(posture.cloudtrail)
    return bool(posture.security_hub.enabled)


def test_o_veredito_de_flow_log_e_por_vpc_e_nao_por_conta(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """The estate must contain a scope where logging is MIXED, and that scope must fail.

    This is the granularity test, and it is the one thing the other two audit rules cannot
    check. ``vpc-flow-logs-enabled`` publishes ``Resource Types: AWS::EC2::VPC`` and says the
    rule is NON_COMPLIANT "if flow logs are not enabled for at least one Amazon VPC" -- so a
    scope holding a VPC with flow logs NEXT TO a VPC without them is the discriminating state:
    a renderer reading the ACCOUNT, or taking the scope's verdict from any single VPC, would
    answer for that scope at random and this test would fail.
    """
    por_escopo: dict[tuple[str, str], list[bool]] = {}
    for log in estate.aws_vpc_flow_logs:
        por_escopo.setdefault((log.account_id, log.region_id), []).append(bool(log.flow_log_ids))
    misturados = [escopo for escopo, bandeiras in por_escopo.items() if len(set(bandeiras)) > 1]
    assert misturados, (
        "o estate nao produz nenhum escopo com VPCs mistas: a regra nunca e provada na granularidade "
        "por VPC, e um renderizador que lesse a conta passaria"
    )
    assert len(misturados) >= 1

    # And that scope answers NON_COMPLIANT, with a contributor count of the missing ones.
    escopos = mod._resources_by_scope(estate)
    responses_por_escopo = dict(zip(escopos.keys(), responses, strict=True))
    for escopo in misturados:
        envelope = responses_por_escopo[escopo]
        item = next(i for i in envelope["ComplianceByConfigRules"] if i["ConfigRuleName"] == "vpc-flow-logs-enabled")
        esperadas = [b for b in por_escopo[escopo] if not b]
        assert item["Compliance"]["ComplianceType"] == "NON_COMPLIANT", (
            f"{escopo}: VPCs mistas com {len(esperadas)} sem flow log, e a regra respondeu "
            f"{item['Compliance']['ComplianceType']}"
        )
        assert item["Compliance"]["ComplianceContributorCount"]["CappedCount"] == len(esperadas)


def test_uma_avaliacao_parametrizada_falha_em_vez_de_responder_em_silencio(
    estate: CanonicalEstate,
) -> None:
    """Passing an OPTIONAL rule parameter must raise, never answer the unfiltered condition.

    ``cloudtrail-enabled`` publishes three optional parameters and ``vpc-flow-logs-enabled`` one.
    This renderer passes none, so each reduces to the page's unconditional clause. The dangerous
    failure is not the reduction -- it is a caller that later passes a parameter and gets the
    UNFILTERED verdict back with no error: the artifact would then carry a confident answer to a
    question nobody asked, which is worse than the gap this increment closed.

    ``securityhub-enabled`` is the control: its page publishes "Parameters: None", so there is
    nothing to pass and nothing to guard.
    """
    postura = estate.aws_audit_postures[0]
    log = estate.aws_vpc_flow_logs[0]

    for _nome, avaliador, alvo, parametro in (
        (
            "cloudtrail-enabled",
            evaluators_mod.ACCOUNT_AUDIT_RULE_EVALUATORS["cloudtrail-enabled"],
            (postura, estate.sim_now),
            {"s3BucketName": "contoso-auditoria-123"},
        ),
        (
            "vpc-flow-logs-enabled",
            evaluators_mod.VPC_FLOW_LOG_RULE_EVALUATORS["vpc-flow-logs-enabled"],
            (log, estate.sim_now),
            {"trafficType": "REJECT"},
        ),
    ):
        with pytest.raises(NotImplementedError):
            avaliador(*alvo, parametro)

    # The parameter-free call is the one the renderer makes, and it answers.
    assert evaluators_mod.ACCOUNT_AUDIT_RULE_EVALUATORS["cloudtrail-enabled"](
        postura, estate.sim_now
    ).compliance_type in {"COMPLIANT", "NON_COMPLIANT"}
    assert evaluators_mod.ACCOUNT_AUDIT_RULE_EVALUATORS["securityhub-enabled"](
        postura, estate.sim_now
    ).compliance_type in {"COMPLIANT", "NON_COMPLIANT"}


def test_o_veredito_de_flow_log_responde_em_ambos_os_sentidos(
    responses: list[dict[str, Any]],
) -> None:
    """``vpc-flow-logs-enabled`` must answer COMPLIANT somewhere and NON_COMPLIANT somewhere.

    Same reasoning as every other two-sides assertion here. It is worth stating separately
    because the rule's aggregate is unusual: it is the one rule of the catalog that is
    NON_COMPLIANT because ONE sibling out of several is missing, so a renderer that evaluated
    only the FIRST VPC of each scope could produce a plausible surface -- it just could not
    produce both of these verdicts from the same estate.
    """
    vistos: set[str] = set()
    for envelope in responses:
        for item in envelope["ComplianceByConfigRules"]:
            if item["ConfigRuleName"] == "vpc-flow-logs-enabled":
                vistos.add(item["Compliance"]["ComplianceType"])
    assert "NON_COMPLIANT" in vistos, "vpc-flow-logs-enabled so produziu veredito favoravel"
    assert "COMPLIANT" in vistos, "vpc-flow-logs-enabled so produziu veredito desfavoravel"


def test_as_regras_de_auditoria_respondem_em_todos_os_nove_escopos(
    responses: list[dict[str, Any]],
) -> None:
    """The two account-level audit rules must never be ``INSUFFICIENT_DATA`` in any scope.

    They answer once per ACCOUNT and repeat in each of its regions, so ``INSUFFICIENT_DATA`` here
    could only mean one of two things -- a missing posture, or the ``NOT_APPLICABLE`` collapse --
    and both are wrong here: the rules publish no resource type at all, so the collapse does not
    apply to them, and a missing posture is a hole in the estate that the renderer refuses
    rather than answers around.
    """
    for envelope in responses:
        por_regra = {i["ConfigRuleName"]: i["Compliance"] for i in envelope["ComplianceByConfigRules"]}
        for name in _AUDIT_RULES:
            assert por_regra[name]["ComplianceType"] != "INSUFFICIENT_DATA", (
                f"{name} respondeu INSUFFICIENT_DATA num escopo que tem conta com postura de auditoria"
            )


def test_a_regra_de_flow_log_ainda_colapsa_nos_escopos_sem_vpc(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """A scope with no VPC at all is ``INSUFFICIENT_DATA``, and that is NOT a model gap.

    The remaining ``INSUFFICIENT_DATA`` items on this surface are this collapse, not a missing
    fact. The estate places each AWS resource type in a single region per account, so only three
    of the nine scopes hold a ``vpc`` at all. The reason string has to say so, because the same
    value means "no evaluation results" in the API and only this surface can tell the two apart.
    """
    escopos = mod._resources_by_scope(estate)
    com_vpc = {
        escopo
        for escopo, recursos in escopos.items()
        if any(r.resource_type == "vpc" for r in recursos)
    }
    assert com_vpc, "o estate nao produz nenhuma VPC: a regra nao teria o que avaliar"
    respostas = dict(zip(escopos.keys(), responses, strict=True))
    for escopo, envelope in respostas.items():
        item = next(i for i in envelope["ComplianceByConfigRules"] if i["ConfigRuleName"] == "vpc-flow-logs-enabled")
        if escopo in com_vpc:
            assert item["Compliance"]["ComplianceType"] != "INSUFFICIENT_DATA"
        else:
            assert item["Compliance"]["ComplianceType"] == "INSUFFICIENT_DATA", (
                f"{escopo} nao tem VPC, e a regra respondeu {item['Compliance']['ComplianceType']}"
            )
    # A VPC sem flow log NUNCA vira INSUFFICIENT_DATA: e o veredito oposto ao do colapso.
    for log in estate.aws_vpc_flow_logs:
        escopo = (log.account_id, log.region_id)
        envelope = respostas[escopo]
        item = next(i for i in envelope["ComplianceByConfigRules"] if i["ConfigRuleName"] == "vpc-flow-logs-enabled")
        if not log.flow_log_ids:
            assert item["Compliance"]["ComplianceType"] == "NON_COMPLIANT"


def test_as_duas_regras_avaliadas_produzem_algum_veredito_real(responses: list[dict[str, Any]]) -> None:
    """The surface must not degrade into N rows of INSUFFICIENT_DATA.

    Guarding the real verdicts keeps the two evaluated rules honest: if a future estate change
    emptied every tag, this would fail instead of quietly turning the whole surface into gaps.
    """
    reais = [
        item
        for envelope in responses
        for item in envelope["ComplianceByConfigRules"]
        if item["Compliance"]["ComplianceType"] in {"COMPLIANT", "NON_COMPLIANT"}
    ]
    assert reais, "nenhuma regra produziu veredito a partir do estado"
    assert {item["ConfigRuleName"] for item in reais} <= _ANSWERED
    assert any(item["Compliance"]["ComplianceType"] == "NON_COMPLIANT" for item in reais)


def test_cap_exceeded_e_nulo_e_a_proveniencia_explica_por_que(
    items: list[dict[str, Any]], tree: Path
) -> None:
    """``CapExceeded`` is null everywhere, and the report says which maximum is missing.

    ``ComplianceContributorCount`` publishes "up to a maximum number" without ever publishing
    that maximum, so the boolean "the maximum count is reached" is not reproducible.
    """
    for item in items:
        assert item["Compliance"]["ComplianceContributorCount"]["CapExceeded"] is None
    report = _load(tree, mod.PROVENANCE_PATH)
    lacunas = [e for e in report["model_gaps"] if e.get("field") == "ComplianceContributorCount.CapExceeded"]
    assert len(lacunas) == 1
    assert "maximo" in lacunas[0]["reason"].lower()


def test_um_recurso_sem_tag_conta_e_um_com_tag_nao(items: list[dict[str, Any]]) -> None:
    """No rule answers COMPLIANT while a violating resource exists, and vice versa.

    A COMPLIANT verdict always carries ``CappedCount == 0``; a NON_COMPLIANT verdict always
    carries a positive count. A zero on a NON_COMPLIANT rule would mean the rule found a
    violation and then failed to name the resource that caused it.
    """
    for item in items:
        compliance = item["Compliance"]
        count = compliance["ComplianceContributorCount"]["CappedCount"]
        assert isinstance(count, int) and count >= 0
        if compliance["ComplianceType"] == "COMPLIANT":
            assert count == 0
        if compliance["ComplianceType"] == "NON_COMPLIANT":
            assert count > 0


def test_um_escopo_sem_recurso_do_tipo_e_insufficient_data(
    estate: CanonicalEstate, responses: list[dict[str, Any]]
) -> None:
    """No applicable resource means no evaluation -- and NOT_APPLICABLE is not an option.

    The estate places each AWS resource type in a single region per account, so most scopes
    hold no bucket at all. Those scopes are INSUFFICIENT_DATA, never a fabricated COMPLIANT.

    The three identity rules are the exception this test has to name: they read the account,
    not a resource, so they produce a real verdict in EVERY scope -- including the scopes that
    hold no bucket, and there is nothing wrong with that, because the fact they read does not
    live in the scope.
    """
    scopes = mod._resources_by_scope(estate)
    assert len(responses) == len(scopes)
    for envelope in responses:
        for item in envelope["ComplianceByConfigRules"]:
            if item["ConfigRuleName"] in _ANSWERED:
                continue
            assert item["Compliance"]["ComplianceType"] == "INSUFFICIENT_DATA"
    # At least one scope genuinely lacks a resource type, so the empty-scope path is exercised.
    tipos = {r.resource_type for r in estate.resources if r.identity.provider == PROVIDER_KEY_AWS}
    assert len(tipos) > 1
    sem_bucket = [s for s, rs in scopes.items() if not any(r.resource_type == "s3_bucket" for r in rs)]
    assert sem_bucket, "o estate nao exercita mais o escopo sem recurso do tipo"


# -- the empty contract ------------------------------------------------------


def test_nenhuma_coluna_obrigatoria_foi_exigida(spec: Any) -> None:
    """Every field of this API is "Required: No", so the spec requires nothing.

    Requiring one would be a claim the documentation does not make, and ``readiness`` measures
    required columns separately.
    """
    assert spec.required_names == ()


def test_request_parameters_e_um_documento_de_forma(tree: Path) -> None:
    """The three request-side names are present and empty: no request was captured.

    ``ConfigRuleNames`` is deliberately NOT filled with this renderer's catalog -- the rules
    evaluated here are its own scope, not a call anybody made.
    """
    documento = _load(tree, "request-parameters.json")
    assert set(documento) == {"ComplianceTypes", "ConfigRuleNames", "NextToken"}
    assert all(value is None for value in documento.values())


def test_o_token_de_continuidade_e_nulo(tree: Path) -> None:
    """``NextToken`` is null in every envelope: each scope's rules fit in one page."""
    for envelope in _load(tree, "describe-compliance-by-config-rule-response.json"):
        assert envelope["NextToken"] is None


def test_countable_tags_exclui_o_prefixo_reservado() -> None:
    """Both rule pages say "The rule does not check for tags starting with 'aws:'"."""
    recurso = _resource_stub((("env", "prod"), ("aws:cloudformation:stack-name", "x")))
    assert mod.countable_tags(recurso) == (("env", "prod"),)
    assert mod.RESERVED_TAG_PREFIX == "aws:"


# -- determinism and fail-closed projection -----------------------------------


def test_o_render_e_deterministico(estate: CanonicalEstate, tmp_path: Path) -> None:
    primeiro = mod.ConfigComplianceByRuleRenderer().render(estate, tmp_path / "a")
    segundo = mod.ConfigComplianceByRuleRenderer().render(estate, tmp_path / "b")
    assert [p.name for p in primeiro] == [p.name for p in segundo]
    for a, b in zip(primeiro, segundo, strict=True):
        assert a.read_bytes() == b.read_bytes(), a.name


def test_a_prova_de_projecao_recusa_coluna_sem_fonte_no_modelo() -> None:
    """``_require_projection`` fails closed: a value with no model source is an error.

    ``CapExceeded`` is the real case. It belongs to the format and is projected by nobody --
    the ceiling it compares against is unpublished -- so filling it is rejected by the code
    path, not merely left undone by convention.
    """
    assert "CapExceeded" not in mod._CONTRIBUTOR_PROJECTED
    with pytest.raises(RenderError):
        mod._require_projection(
            {"CapExceeded": False, "CappedCount": 3},
            mod._CONTRIBUTOR_COLUMNS,
            mod._CONTRIBUTOR_PROJECTED,
            "ComplianceContributorCount",
        )
    # The documented value the renderer actually writes passes the same proof.
    mod._require_projection(
        {"CapExceeded": None, "CappedCount": 3},
        mod._CONTRIBUTOR_COLUMNS,
        mod._CONTRIBUTOR_PROJECTED,
        "ComplianceContributorCount",
    )


def test_a_prova_de_projecao_recusa_membro_faltante() -> None:
    """A documented member that never reaches the artifact is also a hard error."""
    with pytest.raises(RenderError):
        mod._require_projection(
            {"ConfigRuleName": "x"},
            mod._ITEM_COLUMNS,
            mod._ITEM_PROJECTED,
            "item",
        )


def _resource_stub(tags: tuple[tuple[str, str], ...]) -> Resource:
    from tools.synthetic_clouds.model.identity import ResourceIdentity

    return Resource(
        identity=ResourceIdentity(
            uuid="00000000-0000-0000-0000-000000000001",
            logical_path="aws/956104725713/us-west-2/s3_bucket/exemplo",
            provider=PROVIDER_KEY_AWS,
        ),
        parent_scope_id="956104725713",
        service_name="Amazon S3",
        service_category="Storage",
        resource_type="s3_bucket",
        resource_name="exemplo",
        region_id="us-west-2",
        region_name="US West (Oregon)",
        tags=tags,
        sku_id="sku-s3",
        capacity_reservation=None,
    )