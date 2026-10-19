"""O diagnostico RETROSPECTIVO de uma regra de Config: "o que esta tela mostraria hoje?".

Por que isto e um instrumento e nao um relatorio
------------------------------------------------
Um ``INSUFFICIENT_DATA`` na tela de postura e um sintoma com pelo menos TRES causas
diferentes, e elas pedem acoes opostas:

1. **a regra e avaliavel com o estado atual** -- o veredito existe, o renderer nao o consultou,
   e a correcao e no renderer;
2. **a regra tem carga mas falta o dado** -- o modelo nao carrega o fato que a regra le, e a
   correcao e no modelo, nao no renderer;
3. **falha de configuracao** -- a regra nao esta habilitada no Config da conta, ou nao pode
   ser executada, e a correcao e na conta, e nenhuma correcao de codigo resolve.

Um painel que so diz "INSUFFICIENT_DATA" obriga quem olha a escolher entre as tres no escuro.
Por isso este modulo nomeia as tres, para cada regra, e diz QUAL delas e o caso -- e o faz
chamando o MESMO avaliador que o renderer de Config chama, de
:mod:`tools.synthetic_clouds.render._config_evaluators`.

POR QUE O AVALIADOR COMPARTILHADO E O QUE TORNA ISSO CONFIAVEL
-------------------------------------------------------------
Se o diagnostico reimplementasse a semantica da regra, ele poderia dizer COMPLIANT onde a
tela diz NON_COMPLIANT, e o instrumento de confianca do incremento passaria a ser a coisa
menos confiavel do projeto. Por isso :data:`IAM_RULE_EVALUATORS` e a UNICA implementacao: o
renderer a chama para escrever o artefato, e este modulo a chama para descrever o que a tela
mostraria. Divergencia entre os dois e impossivel por construcao, nao por disciplina.

O QUE "AVALIAVEL" SIGNIFICA AQUI
--------------------------------
Uma regra e avaliavel quando o estado carrega o fato que ela le. Para as tres de identidade,
isso e :class:`AwsIdentityPosture` da conta -- e nao a existencia de um recurso do tipo
certo: IAM e global, entao nao ha recurso algum que "esteja na regiao". Uma conta sem
postura e uma conta que o modelo nao descreve, e o diagnostico diz isso pelo nome em vez de
contar um veredito que nao tem como produzir.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render._config_evaluators import (
    COMPLIANT,
    IAM_RULE_EVALUATORS,
    NON_COMPLIANT,
    RuleVerdict,
)

#: As tres causas, nomeadas. O texto e o que o painel mostra ao usuario final, entao e
#: deliberadamente concreto: "falta o dado" sem dizer QUAL dado nao ajuda ninguem.
CAUSA_AVALIAVEL: Final = "avaliavel"
CAUSA_CARGA_SEM_DADO: Final = "carga-sem-dado"
CAUSA_FALHA_DE_CONFIGURACAO: Final = "falha-de-configuracao"

#: O que o Config faz quando a regra esta habilitada mas nao ha fato: ``INSUFFICIENT_DATA``.
#: A propria pagina da Compliance usa esse valor para "a regra nao avaliou nada", e e o que
#: distingue o caso 2 dos outros dois.
INSUFFICIENT_DATA: Final = "INSUFFICIENT_DATA"


@dataclass(slots=True, frozen=True)
class RuleDiagnosis:
    """O que a tela mostraria hoje, e de qual das tres causas o ``INSUFFICIENT_DATA`` vem."""

    rule_name: str
    scope: str  # "CONTA" -- as regras de IAM nao tem escopo regional
    current_compliance_type: str  # o que o artefato carrega AGORA
    prospective_compliance_type: str  # o que a tela mostraria se a regra fosse avaliada
    cause: str  # uma das tres causas acima
    reason: str  # porque e esta causa, e nao outra
    contributors: tuple[str, ...]
    per_account: tuple[tuple[str, str, tuple[str, ...]], ...]  # (conta, veredito, reprovados)

    @property
    def would_change(self) -> bool:
        """Whether the two aggregations disagree -- i.e. whether the screen would change.

        Both sides aggregate PER RULE over the scopes, with the same worst-wins rule:
        ``current`` reduces the rendered artifact in :func:`_compliance_types_por_regra`, and
        ``prospective`` reduces the evaluator's per-account verdicts in
        :func:`diagnose_identity_rule`. They are the same question, so a disagreement is
        real -- renderer and evaluator reading the same state differently -- and agreement
        means the screen already shows what the rules say.

        This only holds because both sides reduce the same way. When ``current`` was pinned to
        the FIRST scope, the flag compared one account against the fleet and reported ``True``
        on the seed-123 estate for ``access-keys-rotated`` and ``root-account-mfa-enabled``,
        each of which fails on one account of three, not the first.
        """
        return self.current_compliance_type != self.prospective_compliance_type


def diagnose_identity_rule(
    estate: CanonicalEstate, rule_name: str, current_compliance_type: str
) -> RuleDiagnosis:
    """Diagnose one identity rule against the CURRENT state.

    ``current_compliance_type`` is what the delivered artifact carries -- the caller reads it
    from the rendered ``config-describe-compliance-by-config-rule`` document rather than
    recomputing it, so that "what the screen shows today" is measured and not assumed.
    """
    evaluator = IAM_RULE_EVALUATORS[rule_name]
    postures = sorted(estate.aws_identity_postures, key=lambda posture: posture.account_id)
    sim_now = estate.sim_now

    if not postures:
        return RuleDiagnosis(
            rule_name=rule_name,
            scope="CONTA",
            current_compliance_type=current_compliance_type,
            prospective_compliance_type=INSUFFICIENT_DATA,
            cause=CAUSA_CARGA_SEM_DADO,
            reason=(
                "o estate nao carrega postura de identidade de NENHUMA conta: faltam os fatos de "
                "IAM (MFA do root, politica de senha, usuarios e chaves) no modelo canonico. A "
                "correcao e no MODELO -- nenhuma correcao de renderer resolve uma regra que nao "
                "tem o que ler"
            ),
            contributors=(),
            per_account=(),
        )

    por_conta: list[tuple[str, str, tuple[str, ...]]] = []
    for postura in postures:
        veredito: RuleVerdict = evaluator(postura, sim_now)
        por_conta.append((postura.account_id, veredito.compliance_type, veredito.contributors))

    # O veredito da CONTA e o do escopo: IAM e global, e as tres regras leem um fato sem
    # regiao. Uma regra por conta que devolvesse um veredito so por regiao estaria inventando
    # uma dimensao que o AWS nao tem, entao o diagnostico worka no veredito da conta e diz
    # isso no texto -- e nao multiplica por regiao para inflar a contagem.
    em_conflito = {veredito for _conta, veredito, _reprovados in por_conta}
    prospectivo = NON_COMPLIANT if NON_COMPLIANT in em_conflito else COMPLIANT
    reprovados = tuple(
        f"{conta}: {', '.join(reprovacao)}"
        for conta, _veredito, reprovacao in por_conta
        if reprovacao
    )

    if current_compliance_type != INSUFFICIENT_DATA:
        cause = CAUSA_AVALIAVEL
        reason = (
            "a regra ja responde: o veredito do artefato NAO e INSUFFICIENT_DATA, entao nao ha "
            "lacuna a diagnosticar aqui. Este caso existe para o diagnostico poder dizer "
            "'nada a fazer' em vez de calar sobre uma regra que ja funciona"
        )
    else:
        cause = CAUSA_AVALIAVEL
        reason = (
            "a regra E avaliavel com o estado atual: estate.aws_identity_postures carrega o MFA "
            "do root, a politica de senha, os usuarios e as chaves de cada conta, e o avaliador "
            "produz um veredito para todas elas. O INSUFFICIENT_DATA do artefato NAO vem de "
            "falta de dado nem de falha de configuracao -- vem de o renderer nao ter combinado "
            "com o avaliador. A correcao e no RENDERER, e e uma linha"
        )

    return RuleDiagnosis(
        rule_name=rule_name,
        scope="CONTA",
        current_compliance_type=current_compliance_type,
        prospective_compliance_type=prospectivo,
        cause=cause,
        reason=reason,
        contributors=reprovados,
        per_account=tuple(por_conta),
    )


def diagnose_iam(estate: CanonicalEstate) -> tuple[RuleDiagnosis, ...]:
    """Diagnose the three identity rules, measuring what the screen shows today.

    The measurement is what makes this retrospective rather than predictive: the current
    ``ComplianceType`` is READ FROM THE RENDERED ARTIFACT, so a diagnosis that says "the screen
    would change" can be wrong in exactly the way a bug would be, and the measurement is the
    only thing that would catch it.

    The artifact is rendered into a temp directory that is removed before returning -- this
    function reports, it does not deliver, and handing a caller a directory it has to remember
    to delete would be a second thing to forget.
    """
    from tools.synthetic_clouds.render import config_compliance_by_rule as config

    with tempfile.TemporaryDirectory(prefix="review-state-iam-") as pasta:
        config.ConfigComplianceByRuleRenderer().render(estate, Path(pasta))
        respostas = _compliance_types_por_regra(Path(pasta) / config.RENDER_DIR)

    diagnosticos: list[RuleDiagnosis] = []
    for rule_name in sorted(IAM_RULE_EVALUATORS):
        diagnosticos.append(
            diagnose_identity_rule(estate, rule_name, respostas.get(rule_name, INSUFFICIENT_DATA))
        )
    return tuple(diagnosticos)


def _compliance_types_por_regra(base: Path) -> dict[str, str]:
    """Read each rule's ``ComplianceType`` out of the rendered response document.

    One entry per rule, not one per scope: the three identity rules answer per ACCOUNT and
    repeat that verdict in each of the account's regions, so a per-scope tally would multiply
    one fact by three and make the number look like more evidence than it is.

    O documento fala POR ESCOPO (``(conta, regiao)``) e a tela de postura fala POR REGRA, entao
    ler o artefato como a tela ve significa reduzir os escopos -- e a reducao tem de ser a MESMA
    que :func:`diagnose_identity_rule` usa para o ``prospective``: **pior caso vence**.
    ``NON_COMPLIANT`` se algum escopo for ``NON_COMPLIANT``; senao ``COMPLIANT`` se algum for
    ``COMPLIANT``; senao ``INSUFFICIENT_DATA``, porque uma regra cujos escopos nao produziram
    nada para agregar nao avaliou nada.

    Prender o PRIMEIRO escopo (``setdefault``) respondia uma pergunta diferente: IAM e global,
    entao o primeiro escopo da ordem ``(conta, regiao)`` do renderer e so a primeira CONTA, e
    fixar o veredito dela fazia :meth:`RuleDiagnosis.would_change` comparar uma conta com a
    frota. Medido em ``build_estate(seed=123, profile="small", currency="USD")``, isso reportava
    ``access-keys-rotated`` e ``root-account-mfa-enabled`` como prestes a mudar quando renderer e
    avaliador ja concordavam conta por conta -- cada uma reprova em exatamente uma conta das tres,
    e nao na primeira.

    Mesma reducao, mesma entrada, mesma resposta dos dois lados: e por isso que ``would_change``
    passa a valer ``False`` quando os dois concordam, que e o unico caso em que ele diz algo.
    """
    documento = json.loads((base / "describe-compliance-by-config-rule-response.json").read_text("utf-8"))
    por_regra: dict[str, set[str]] = {}
    for envelope in documento:
        for item in envelope["ComplianceByConfigRules"]:
            por_regra.setdefault(item["ConfigRuleName"], set()).add(item["Compliance"]["ComplianceType"])
    return {
        regra: (
            NON_COMPLIANT
            if NON_COMPLIANT in vereditos
            else COMPLIANT if COMPLIANT in vereditos else INSUFFICIENT_DATA
        )
        for regra, vereditos in por_regra.items()
    }


def describe(diagnosticos: tuple[RuleDiagnosis, ...]) -> str:
    """Render the diagnoses as the text a person reads, in pt-BR like the rest of the tool."""
    linhas: list[str] = []
    for diagnostico in diagnosticos:
        linhas.append(f"\n=== {diagnostico.rule_name} (escopo {diagnostico.scope}) ===")
        linhas.append(
            f"  hoje na tela .... {diagnostico.current_compliance_type}"
        )
        linhas.append(
            f"  se fosse avaliada  {diagnostico.prospective_compliance_type}"
        )
        linhas.append(f"  causa .............. {diagnostico.cause}")
        linhas.append(f"  porque ............ {diagnostico.reason}")
        if diagnostico.contributors:
            linhas.append("  o que reprova:")
            for item in diagnostico.contributors:
                linhas.append(f"    - {item}")
    return "\n".join(linhas)


__all__ = [
    "CAUSA_AVALIAVEL",
    "CAUSA_CARGA_SEM_DADO",
    "CAUSA_FALHA_DE_CONFIGURACAO",
    "RuleDiagnosis",
    "describe",
    "diagnose_iam",
    "diagnose_identity_rule",
]