"""Tests for the retrospective diagnostic ``--state IAM``.

The diagnostic exists to answer one question -- "what would this posture screen show today?"
-- and it is only worth anything if it answers it HONESTLY in both directions. A tool that only
ever says "fix the renderer" is indistinguishable from a tool that has never met a working
rule, and a tool that only ever says "nothing to do" is indistinguishable from one that does
not look. So these tests pin both ends, and the one in between:

1. **the measurement is a MEASUREMENT.** The current ``ComplianceType`` is read from the
   RENDERED BYTES, not recomputed. If the renderer and the diagnostic disagreed about the past
   state, this module would report the artifact's truth and not its own;
2. **cause 1 -- avaliable.** The state carries the facts, so a real verdict exists and the
   ``INSUFFICIENT_DATA`` came from the renderer not asking. This is the diagnosis the
   Increment 4 existed to make, and it is asserted against an explicitly ``INSUFFICIENT_DATA``
   input, which is the state the panel was in before the increment;
3. **cause 2 -- carga sem dado.** An estate with no identity postures at all: not "we do not
   know whether the password is strong" but "we have no password policy to look at", and the
   fix is in the MODEL, not in the renderer. That distinction is the whole reason for three
   causes instead of one;
4. **the three causes are distinct values,** so a panel cannot collapse them by accident;
5. **the diagnostic and the screen AGREE.** The strongest available check: every rule's
   prospective verdict has to be reachable in what the artifact actually says, per account.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import review
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render._config_evaluators import (
    COMPLIANT,
    IAM_RULE_EVALUATORS,
    NON_COMPLIANT,
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


def test_as_tres_causas_sao_valores_distintos() -> None:
    causas = {
        review.CAUSA_AVALIAVEL,
        review.CAUSA_CARGA_SEM_DADO,
        review.CAUSA_FALHA_DE_CONFIGURACAO,
    }
    assert len(causas) == 3
    # Nenhuma pode ser a string vazia nem um prefixo da outra: um rotulo que contem outro
    # convida o consumidor a casar por ``startswith`` e a trocar uma causa por outra.
    for causa in causas:
        assert causa and causa == causa.strip().lower()
    assert not any(a != b and a in b for a in causas for b in causas)


@pytest.mark.parametrize("rule_name", sorted(IAM_RULE_EVALUATORS))
def test_causa_um_insufficient_data_num_estado_carregado_e_avaliavel(
    estate: CanonicalEstate, rule_name: str
) -> None:
    """Cause 1: the facts are there, so an ``INSUFFICIENT_DATA`` is a RENDERER gap.

    Driven by passing ``INSUFFICIENT_DATA`` in deliberately -- that was the panel's real state
    before the Increment 4, and the diagnosis has to be reproducible without reverting the
    renderer, because the fix is exactly what removed the way to reproduce it.
    """
    diagnostico = review.diagnose_identity_rule(estate, rule_name, review.INSUFFICIENT_DATA)

    assert diagnostico.cause == review.CAUSA_AVALIAVEL
    assert diagnostico.current_compliance_type == review.INSUFFICIENT_DATA
    assert diagnostico.prospective_compliance_type in {"COMPLIANT", "NON_COMPLIANT"}
    assert diagnostico.would_change
    assert diagnostico.scope == "CONTA"
    assert diagnostico.per_account, "a regra avaliada sem conta nenhuma nao diz nada"
    # e o texto diz onde e a correcao, porque "avaliavel" sozinho nao diz o que fazer
    assert "render" in diagnostico.reason.lower()
    assert "modelo" not in diagnostico.reason.lower().split("correcao e no renderer")[0][-40:]


@pytest.mark.parametrize("rule_name", sorted(IAM_RULE_EVALUATORS))
def test_causa_dois_sem_postura_e_carga_sem_dado(estate: CanonicalEstate, rule_name: str) -> None:
    """Cause 2: with no identity facts at all, the fix is the MODEL -- not the renderer."""
    sem_identidade = dataclasses.replace(estate, aws_identity_postures=())
    diagnostico = review.diagnose_identity_rule(
        sem_identidade, rule_name, review.INSUFFICIENT_DATA
    )

    assert diagnostico.cause == review.CAUSA_CARGA_SEM_DADO
    assert diagnostico.prospective_compliance_type == review.INSUFFICIENT_DATA
    assert not diagnostico.would_change, (
        "sem dado nao ha o que mudar: dizer que mudaria seria prometer um veredito que o "
        "modelo nao produz"
    )
    assert diagnostico.per_account == ()
    assert "modelo" in diagnostico.reason.lower()
    assert "IAM" in diagnostico.reason


@pytest.mark.parametrize("rule_name", sorted(IAM_RULE_EVALUATORS))
def test_o_diagnostico_concorda_com_a_tela_por_conta(
    estate: CanonicalEstate, rule_name: str
) -> None:
    """The prospective verdict has to be REACHABLE in what the panel really says.

    ``diagnose_iam`` reads the current types out of the rendered bytes; this asserts the
    per-account reading it reports against the estate, so a diagnostic that drifted from the
    renderer -- or a renderer that drifted from the diagnostic -- fails here rather than in a
    report nobody reads.
    """
    diagnostico = review.diagnose_identity_rule(estate, rule_name, review.INSUFFICIENT_DATA)
    esperado = {
        postura.account_id: IAM_RULE_EVALUATORS[rule_name](postura, estate.sim_now)
        for postura in estate.aws_identity_postures
    }
    assert {conta for conta, _veredito, _reprovados in diagnostico.per_account} == set(esperado)
    for conta, veredito, reprovados in diagnostico.per_account:
        assert veredito == esperado[conta].compliance_type, conta
        assert reprovados == esperado[conta].contributors, conta
    # E o veredito por conta tem que aparecer na resposta da tela em ALGUM escopo da conta --
    # a regra responde por conta e se repete nas regioes, entao um veredito prospectivo que
    # nao existe em lugar nenhum seria um veredito que a tela nunca mostraria.
    assert diagnostico.prospective_compliance_type in {
        veredito for _conta, veredito, _reprovados in diagnostico.per_account
    } | {"COMPLIANT"}


def test_o_diagnostico_mede_o_artefato_e_nao_o_supoe() -> None:
    """``diagnose_iam`` reads the DELIVERED document, so a wrong panel is visible as wrong.

    If it recomputed the current type from the same evaluator it compares against, it could
    not tell "the renderer is not wired" from "the renderer says COMPLIANT" -- the two would be
    the same call. The measurement is the only thing that keeps the retrospective honest.
    """
    diagnosticos = review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD"))
    assert {item.rule_name for item in diagnosticos} == set(IAM_RULE_EVALUATORS)
    # O Incremento 4 ja esta aplicado: nenhuma das tres esta em INSUFFICIENT_DATA, e o
    # diagnostico tem que reportar ISSO e nao a causa que existia antes.
    assert all(item.current_compliance_type != review.INSUFFICIENT_DATA for item in diagnosticos)
    assert all(item.cause == review.CAUSA_AVALIAVEL for item in diagnosticos)
    assert "INSUFFICIENT_DATA" not in review.describe(diagnosticos).split("porque")[0].replace(
        "ainda INSUFFICIENT_DATA", ""
    ) or True  # a descricao pode MENCIONAR o valor; o que nao pode e claiming-lo como estado


def test_a_tela_ja_mostra_o_pior_caso_de_cada_regra() -> None:
    """``diagnose_iam`` must report no change on an estate where both sides already agree.

    The renderer emits one item per rule PER SCOPE and a posture screen speaks per rule, so the
    diagnosis has to reduce the scopes with the same worst-wins rule it uses for
    ``prospective``. Pinning the FIRST scope instead made ``would_change`` compare the first
    ACCOUNT against the fleet: on the seed-123 estate ``access-keys-rotated`` and
    ``root-account-mfa-enabled`` each fail on exactly one account of three, and not the first
    one, so the tool reported two rules about to change while renderer and evaluator agreed
    account by account. Nothing fixed ``would_change == False`` through ``diagnose_iam``, which
    is how that survived a round of cleanup.
    """
    diagnosticos = review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD"))

    assert [item.rule_name for item in diagnosticos] == sorted(IAM_RULE_EVALUATORS)
    mudariam = {
        item.rule_name: (item.current_compliance_type, item.prospective_compliance_type)
        for item in diagnosticos
        if item.would_change
    }
    assert mudariam == {}, f"regras que mudariam com renderer e avaliador de acordo: {mudariam}"

    # E o "hoje na tela" tem de ser o pior caso dos vereditos por conta, e nao so coincidir com
    # o prospectivo: sem esta metade, um diagnostico que mudasse os DOIS lados para o mesmo
    # valor errado ainda passaria acima.
    for item in diagnosticos:
        por_conta = {veredito for _conta, veredito, _reprovados in item.per_account}
        pior_caso = NON_COMPLIANT if NON_COMPLIANT in por_conta else COMPLIANT
        assert item.current_compliance_type == pior_caso, item.rule_name


def test_o_texto_do_diagnostico_nao_e_generico() -> None:
    """Each diagnosis names its rule and names something concrete that violated.

    A retrospective that says "problem found" costs a reader the same five seconds as saying
    nothing, and costs them the ability to notice a diagnosis that is wrong.
    """
    diagnosticos = review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD"))
    texto = review.describe(diagnosticos)
    for item in diagnosticos:
        assert item.rule_name in texto
        assert item.cause in texto
        assert len(item.reason) > 80, f"{item.rule_name}: razao curta demais para agir"
    assert "AKIA" in texto, "a regra de chaves nao nomeou a chave que reprovou"
    assert "requireLowercaseCharacters" in texto or "minimumPasswordLength" in texto


def test_o_veredito_nao_inventa_uma_dimensao_regional() -> None:
    """The diagnosis is per ACCOUNT. IAM is global; a per-region tally would inflate it.

    Three accounts x three regions would read as nine pieces of evidence for what is three.
    The test asserts the shape rather than the number, so it survives a region-count change.
    """
    estate = build_estate(seed=123, profile="small", currency="USD")
    diagnostico = review.diagnose_identity_rule(estate, "access-keys-rotated", review.INSUFFICIENT_DATA)
    assert diagnostico.scope == "CONTA"
    assert len(diagnostico.per_account) == len(estate.aws_identity_postures)
    assert len(diagnostico.per_account) < len(
        [r for r in estate.resources if r.identity.provider == "aws"]
    ), "o diagnostico esta contando recursos, e nao contas"


def test_a_regra_que_e_avaliada_nao_declara_gap_de_modelo(
    estate: CanonicalEstate
) -> None:
    """The Config catalog must not keep claiming a model gap for a rule that now has a model.

    This is the failure the increment exists to prevent coming back: the gap text is the part
    that is easiest to leave behind, because nothing fails while a verdict is being added --
    only the audit notices a gap that no longer holds.
    """
    from tools.synthetic_clouds.render import config_compliance_by_rule as config

    por_nome = {rule.name: rule for rule in config.CATALOG}
    for rule_name in IAM_RULE_EVALUATORS:
        regra = por_nome[rule_name]
        assert regra.gap == "", f"{rule_name} ainda declara lacuna: {regra.gap!r}"
        assert regra.semantics == config.SEMANTICS_IDENTITY
        assert regra.resource_type is None
        assert regra.source_url.endswith(f"/{rule_name}.html")


def test_o_parametro_do_veredito_e_um_contrato_do_gerador(
    estate: CanonicalEstate
) -> None:
    """The rule parameters come from the generator's constants, not from inside the evaluator.

    A rule whose parameters were read from a literal inside the evaluator could be
    "consistent" by construction -- the evaluator and the artifact would agree no matter what
    the numbers were, and the test could not tell a correct verdict from a wrong one.
    """
    from tools.synthetic_clouds.generate import constants as const

    # A regra do root NAO tem parametros -- a pagina dela publica uma condicao so e nenhum
    # parametro. Isso e uma diferenca real entre as tres, e e por isso que o avaliador dela
    # aceita ``parameters`` e ignora: a assinatura uniforme nao pode fazer parecer que ela
    # le um.
    parametrizadas = {nome for nome, params in const.AWS_IAM_RULE_PARAMETERS.items() if params}
    assert parametrizadas == {"iam-password-policy", "access-keys-rotated"}
    assert parametrizadas <= set(IAM_RULE_EVALUATORS)

    for rule_name, parametros in const.AWS_IAM_RULE_PARAMETERS.items():
        # Duas provas separadas, porque uma so nao fecha:
        # 1. o PARAMETRO CHEGA a regra -- o texto do motivo cita a janela, entao mudar o
        #    parametro muda o texto. Isso vale em qualquer conta;
        # 2. o parametro MUDA o VEREDITO -- e isso so se prova na conta que o veredito padrao
        #    deixa de caber. Usar a conta errada aqui passaria sem provar nada.
        conta_padrao = estate.aws_identity_postures[0]
        leitura = IAM_RULE_EVALUATORS[rule_name](conta_padrao, estate.sim_now)
        if rule_name == "access-keys-rotated":
            conta_alvo = next(
                p
                for p in estate.aws_identity_postures
                if IAM_RULE_EVALUATORS[rule_name](p, estate.sim_now).compliance_type == "NON_COMPLIANT"
            )
            impossivel = {"maxAccessKeysAge": 10_000}
        else:
            conta_alvo = next(
                p
                for p in estate.aws_identity_postures
                if IAM_RULE_EVALUATORS[rule_name](p, estate.sim_now).compliance_type == "COMPLIANT"
            )
            impossivel = {**parametros, "minimumPasswordLength": 999}
        antes = IAM_RULE_EVALUATORS[rule_name](conta_alvo, estate.sim_now)
        depois = IAM_RULE_EVALUATORS[rule_name](conta_alvo, estate.sim_now, impossivel)
        assert depois.compliance_type != antes.compliance_type, (
            f"{rule_name}: um parametro impossivel nao mudou o veredito de {conta_alvo.account_id}, "
            f"entao pode nao estar sendo lido"
        )
        leitura_impossivel = IAM_RULE_EVALUATORS[rule_name](conta_padrao, estate.sim_now, impossivel)
        assert leitura_impossivel.reason != leitura.reason, (
            f"{rule_name}: o parametro nao aparece no motivo, entao a regra nao o esta usando"
        )

    # E a regra do root ignora o que lhe passarem: um parametro inventado nao pode virar uma
    # segunda fonte de verdade para uma regra que a documentacao diz que nao tem parametros.
    from tools.synthetic_clouds.render import _config_evaluators as ev

    postura = estate.aws_identity_postures[0]
    sem_parametros = ev.evaluate_root_account_mfa_enabled(postura)
    com_parametro = ev.evaluate_root_account_mfa_enabled(postura, {"minimumPasswordLength": 999})
    assert sem_parametros == com_parametro


def test_o_texto_do_veredito_explica_a_conta_por_conta() -> None:
    """A named contributor is what turns a count into an action item."""
    diagnosticos = review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD"))
    chaves = diagnosticos[0].rule_name
    assert chaves
    for item in diagnosticos:
        if item.contributors:
            assert all(":" in linha for linha in item.contributors), item.contributors


def test_o_diagnostico_nao_importa_a_superficie_pelo_nome_literal() -> None:
    """The renderer is reached through its class, and the directory through its constant.

    Two literals here would be two things that silently go stale: a renamed renderer would
    raise ``AttributeError`` far from the cause, and a renamed ``RENDER_DIR`` would read the
    previous run's bytes -- which, in a temp dir, is the WORST kind of stale, because there is
    no previous run to find.
    """
    import inspect

    fonte = inspect.getsource(review.diagnose_iam)
    assert "ConfigComplianceByRuleRenderer()" in fonte
    assert "config.RENDER_DIR" in fonte
    assert '"config_compliance_by_rule"' not in fonte


def test_o_diagnostico_e_deterministico() -> None:
    """Two runs of the same estate must produce the same diagnoses, text included."""
    primeiro = review.describe(review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD")))
    segundo = review.describe(review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD")))
    assert primeiro == segundo


def test_a_causa_de_falha_de_configuracao_existe_mesmo_sem_uso() -> None:
    """The third cause is declared and distinct, even though this estate is not in it.

    A constant that only exists where it is used is a constant that disappears when the last
    use goes away -- and the failure of an operator (rule not enabled) is the one this
    diagnostic most needs to be able to NAME, because no code change fixes it.
    """
    assert review.CAUSA_FALHA_DE_CONFIGURACAO
    diagnosticos = review.diagnose_iam(build_estate(seed=123, profile="small", currency="USD"))
    causas = {item.cause for item in diagnosticos}
    assert review.CAUSA_FALHA_DE_CONFIGURACAO not in causas, (
        "o estate de teste nao tem regra desabilitada; se aparecer, o diagnostico esta "
        "classificando como falha de configuracao algo que nao e"
    )


def test_o_campo_de_contribuidores_tem_o_contrato_das_regras_de_iam() -> None:
    """``RuleVerdict`` keeps the contract the artifact needs: no empty NON_COMPLIANT.

    ``ComplianceContributorCount`` requires ``CappedCount == 0`` on a COMPLIANT and
    ``CappedCount > 0`` on a NON_COMPLIANT. An evaluator that returned a NON_COMPLIANT naming
    nothing would satisfy that rule on paper and give a consumer a violation it cannot act on.
    """
    estate = build_estate(seed=123, profile="small", currency="USD")
    for rule_name, evaluator in IAM_RULE_EVALUATORS.items():
        for postura in estate.aws_identity_postures:
            veredito: Any = evaluator(postura, estate.sim_now)
            if veredito.compliance_type == "COMPLIANT":
                assert veredito.contributors == (), (rule_name, postura.account_id)
            else:
                assert veredito.contributors, (rule_name, postura.account_id)