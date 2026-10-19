"""A SEMANTICA de veredito das regras gerenciadas do AWS Config que leem o estado do estate.

Este e o unico lugar do repositorio onde o significado de um veredito de Config mora. Duas
coisas o consomem, e as duas precisam chamar a MESMA funcao:

* ``render/config_compliance_by_rule.py``, que escreve o artefato que um painel de postura
  consome;
* ``fidelity/review.py --state IAM``, o diagnostico retrospectivo que pergunta "o que esta
  tela mostraria se esta regra fosse avaliada hoje".

Se houvesse uma implementacao em cada lado, o diagnostico poderia dizer COMPLIANT onde a
tela diz NON_COMPLIANT -- e o diagnostico, que e o instrumento de confianca do incremento,
passaria a ser a coisa menos confiavel do projeto. Por isso o modulo existe e por isso a
regra do ``docs/POSTURA-SEGURANCA.md`` de um avaliador por regra se cumpre AQUI.

O que um avaliador devolve
--------------------------
:class:`RuleVerdict` traz o veredito E os ``contributors``: os recursos que reprovaram. Nao e
enfeite -- o contrato de ``ComplianceContributorCount`` exige ``CappedCount == 0`` num
veredito COMPLIANT e ``CappedCount > 0`` num NON_COMPLIANT, entao um veredito que nao sabe
dizer QUE reprovou nao consegue satisfazer o contrato, e a regra passaria a carregar uma
contagem que nao conta nada.

Os parametros vem de :data:`const.AWS_IAM_RULE_PARAMETERS` e sao argumento, nao constante
global lida de dentro: a regra gerenciada e parametrizavel, e fixar os numeros dentro da
funcao tornaria impossivel avaliar a regra com os parametros que a AWS de fato publica.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Final

from tools.synthetic_clouds.generate import constants as const
from tools.synthetic_clouds.model.audit import AwsAuditPosture, AwsVpcFlowLog
from tools.synthetic_clouds.model.iam import AwsIdentityPosture

#: Os tres vereditos que a pagina Compliance publica. NOT_APPLICABLE NAO esta aqui porque a
#: propria pagina diz que o tipo nao o suporta -- e o renderer do Config tambem nao o emite.
COMPLIANT: Final = "COMPLIANT"
NON_COMPLIANT: Final = "NON_COMPLIANT"

#: Os nomes das tres regras de identidade, como o catalogo do Config as escreve. Vem do
#: catalogo e nao e redigitado aqui, para que um nome trocado no cataleto nao vire um nome
#: antigo gravado aqui.
RULE_ROOT_MFA: Final = "root-account-mfa-enabled"
#: Falso positivo do S105 ("possible hardcoded password"): o nome contem "password" e o VALOR e
#: o nome de uma regra gerenciada do catalogo do Config. Nao ha credencial nenhuma aqui -- e
#: copiar o nome do catalogo em vez de reescreve-lo e o que impede que o nome na spec e o nome
#: no avaliador se separem sem ninguem notar.
RULE_PASSWORD_POLICY: Final = "iam-password-policy"  # noqa: S105
RULE_ACCESS_KEYS_ROTATED: Final = "access-keys-rotated"

#: Os nomes dos requisitos que a regra ``iam-password-policy`` avalia, na ordem em que a
#: pagina da regra os lista. A ordem e a do documento e nao a de um conjunto, porque a razao
#: que a funcao devolve para uma conta nao conformidade e uma lista, nao um booleano.
PASSWORD_REQUIREMENTS: Final[tuple[str, ...]] = (
    "minimumPasswordLength",
    "requireSymbols",
    "requireNumbers",
    "requireUppercaseCharacters",
    "requireLowercaseCharacters",
)


@dataclass(slots=True, frozen=True)
class RuleVerdict:
    """O veredito de UMA regra sobre UMA conta, e o que o produziu.

    ``compliance_type`` e ``COMPLIANT`` ou ``NON_COMPLIANT`` -- nunca ``INSUFFICIENT_DATA``.
    A ausencia do terceiro valor aqui e deliberada: um avaliador so e chamado quando o
    estado carrega o fato que a regra le, e quem decide se o estado carrega o fato e o
    renderer, antes de chegar aqui.

    ``contributors`` nomeia o que reprovou. Num veredito COMPLIANT e vazio por construcao
    (e e o que satisfaz ``CappedCount == 0``); num NON_COMPLIANT, os contributors sao os
    recursos, as chaves ou -- na regra da senha -- os NOMES dos requisitos que a conta
    reprova, que e a unica forma de dizer *por que* uma politica de senha e fraca.
    """

    compliance_type: str
    contributors: tuple[str, ...]
    reason: str


def _verdict(compliance_type: str, contributors: tuple[str, ...], reason: str) -> RuleVerdict:
    """Guarda a invariante que o contrato de ``ComplianceContributorCount`` exige."""
    if compliance_type == COMPLIANT and contributors:
        raise ValueError(f"veredito COMPLIANT com {len(contributors)} contribuidor(es)")
    if compliance_type == NON_COMPLIANT and not contributors:
        raise ValueError("veredito NON_COMPLIANT sem contributors: a regra achou a violacao e nao disse qual")
    return RuleVerdict(compliance_type, contributors, reason)


def evaluate_root_account_mfa_enabled(
    posture: AwsIdentityPosture, parameters: dict[str, int] | None = None
) -> RuleVerdict:
    """A regra gerenciada ``root-account-mfa-enabled``.

    A pagina da regra publica uma so condicao: "Checks whether the AWS account root user has
    MFA enabled. The rule is NON_COMPLIANT if the AWS account root user does not have MFA
    enabled." Nao ha parametro, e por isso o ``parameters`` existe so para a assinatura
    uniforme -- e e ignorado.

    A regra fala da conta ROOT e nao de nenhum usuario. E por isso que ela le
    ``posture.root_mfa`` e nao ``user.mfa_active``: uma conta cujo root tem MFA e aprovada
    mesmo que um usuario de servico nao tenha, e vice-versa. O estate tem contas em que as
    duas coisas discordam justamente para que essa troca nao possa passar.
    """
    if posture.root_mfa.mfa_active:
        return _verdict(COMPLIANT, (), "a conta root tem MFA habilitado")
    return _verdict(
        NON_COMPLIANT,
        (posture.account_id,),
        "a conta root nao tem MFA habilitado: a conta root nao tem usuario gerenciavel, "
        "entao nao ha quem instale o MFA -- e exatamente por isso que a regra existe",
    )


def evaluate_iam_password_policy(
    posture: AwsIdentityPosture, parameters: dict[str, int] | None = None
) -> RuleVerdict:
    """A regra gerenciada ``iam-password-policy``.

    A pagina publica cinco parametros: ``minimumPasswordLength``, ``requireSymbols``,
    ``requireNumbers``, ``requireUppercaseCharacters`` e ``requireLowercaseCharacters``, todos
    inteiros, com ``-1`` significando "nao avaliar este requisito". E por isso que o
    requisito avaliado e traduzido por :meth:`AwsPasswordPolicy.exige` e nao por um ``and``
    de booleanos: um requisito que a regra nao avalia nunca reprova, mesmo que a politica
    da conta nao o exija.

    O comprimento e o unico dos cinco que NAO e um "exigir": ele e um piso, e
    ``minimumPasswordLength = 14`` reprova uma politica de 8. Os outros quatro sao interruptores
    e ``requireSymbols = 1`` reprova uma politica que nao exige simbolos.
    """
    params = parameters if parameters is not None else const.AWS_IAM_RULE_PARAMETERS[RULE_PASSWORD_POLICY]
    politica = posture.password_policy
    violacoes: list[str] = []
    exigido = params["minimumPasswordLength"]
    if exigido >= 0 and politica.minimum_password_length < exigido:
        violacoes.append("minimumPasswordLength")

    interruptores = (
        ("requireSymbols", politica.require_symbols),
        ("requireNumbers", politica.require_numbers),
        ("requireUppercaseCharacters", politica.require_uppercase),
        ("requireLowercaseCharacters", politica.require_lowercase),
    )
    for nome, observado in interruptores:
        if politica.exige(parametro=params[nome]) and not observado:
            violacoes.append(nome)

    if violacoes:
        return _verdict(
            NON_COMPLIANT,
            tuple(violacoes),
            "a politica de senha da conta nao atende "
            + ", ".join(violacoes)
            + f" (exigido: {', '.join(f'{n}={params[n]}' for n in violacoes)})",
        )
    return _verdict(
        COMPLIANT,
        (),
        f"a politica de senha da conta atende os {len(PASSWORD_REQUIREMENTS)} requisitos avaliados",
    )


def evaluate_access_keys_rotated(
    posture: AwsIdentityPosture,
    sim_now: date,
    parameters: dict[str, int] | None = None,
) -> RuleVerdict:
    """A regra gerenciada ``access-keys-rotated``.

    A pagina publica um parametro, ``maxAccessKeysAge``, em dias: a regra e NON_COMPLIANT
    quando alguma chave ATIVA foi criada ha mais que isso. Duas consequencias que a pagina
    deixa explicitas e que a funcao cumpre:

    * **So chave ATIVA.** Uma chave ``Inactive`` de 410 dias nao reprova nada -- foi
      desativada, e nao e uma credencial em uso. Reprovar por idade sem olhar o status
      acusaria uma conta que ja resolved o problema.
    * **A idade vem da CRIACAO, nao do ultimo uso.** Uma chave que nunca foi usada e uma
      chave recem-criada sao as duas jovens para a regra; ``last_used_date`` nao entra.

    ``sim_now`` e argumento em vez de lido do posture porque a idade e uma RELACAO com o
    presente do estate. Uma chave "de 410 dias" escrita como data fixa seria um veredito
    que muda quando ``sim_now`` passa, sem que nada no estado de identidade tenha mudado --
    e a regra de rotacao deixaria de ser uma propriedade do estado.
    """
    params = parameters if parameters is not None else const.AWS_IAM_RULE_PARAMETERS[RULE_ACCESS_KEYS_ROTATED]
    janela = params["maxAccessKeysAge"]
    vencidas: list[str] = []
    for usuario in posture.users:
        for chave in usuario.access_keys:
            if chave.status != "Active":
                continue
            idade = (sim_now - date.fromisoformat(chave.create_date)).days
            if idade > janela:
                vencidas.append(f"{chave.access_key_id} ({usuario.user_name}, {idade}d > {janela}d)")
    if vencidas:
        return _verdict(
            NON_COMPLIANT,
            tuple(vencidas),
            f"{len(vencidas)} chave(s) ativa(s) criada(s) ha mais de {janela} dias: " + "; ".join(vencidas),
        )
    return _verdict(COMPLIANT, (), f"nenhuma chave ativa com mais de {janela} dias de criacao")


#: A regra gerenciada -> o avaliador dela, sob uma ASSINATURA UNIFORME
#: ``(posture, sim_now, parameters=None)``.
#:
#: A uniformidade e o ponto: os tres avaliadores tem ORDENS DE ARGUMENTOS DIFERENTES
#: (``access-keys-rotated`` precisa do ``sim_now`` para medir idade; os outros dois nao), e um
#: registro cujas chaves sao funcoes com assinaturas diferentes obriga TODO chamador a saber
#: qual regra e qual ordem. Um diagnostico que erra a ordem nao falha com um erro de tipo --
#: ele devolve um veredito errado em silencio, que e o pior modo de falha para um instrumento
#: cuja unica razao de existir e dizer a verdade.
#:
#: O renderer NOMEIA por aqui em vez de comparar nomes em ``if``, e o diagnostico retrospectivo
#: itera por aqui: a lista de regras de IAM que a tela avalia e a lista que o diagnostico
#: avalia sao a MESMA tupla.
IAM_RULE_EVALUATORS: Final = {
    RULE_ROOT_MFA: lambda posture, sim_now, parameters=None: evaluate_root_account_mfa_enabled(
        posture, parameters
    ),
    RULE_PASSWORD_POLICY: lambda posture, sim_now, parameters=None: evaluate_iam_password_policy(
        posture, parameters
    ),
    RULE_ACCESS_KEYS_ROTATED: lambda posture, sim_now, parameters=None: evaluate_access_keys_rotated(
        posture, sim_now, parameters
    ),
}


# -- Incremento 4.3: auditoria e guardrails -------------------------------------
#
# Estas tres fecharam o residuo de Config. As DUAS primeiras sao de nivel de CONTA -- as paginas
# publicam trigger ``Periodic`` e NENHUM "Resource Types" -- e a terceira e POR VPC, com
# ``Resource Types: AWS::EC2::VPC``. A diferenca de granularidade e o que impede as duas metades
# de virarem um so avaliador: o mesmo estado (a conta) tem dois alvos, e o terceiro alvo e um
# recurso.

RULE_CLOUDTRAIL: Final = "cloudtrail-enabled"
RULE_SECURITYHUB: Final = "securityhub-enabled"
RULE_VPC_FLOW_LOGS: Final = "vpc-flow-logs-enabled"


def evaluate_cloudtrail_enabled(
    posture: AwsAuditPosture, parameters: Mapping[str, str] | None = None
) -> RuleVerdict:
    """A regra gerenciada ``cloudtrail-enabled``.

    A pagina publica a condicao curta -- "Checks if an AWS CloudTrail trail is enabled in your
    AWS account. The rule is NON_COMPLIANT if a trail is not enabled." -- e tres parametros
    OPCIONAIS: ``cloudWatchLogsLogGroupArn``, ``s3BucketName`` e ``snsTopicArn``. Este renderer
    nao passa NENHUM deles, entao a regra **reduz** a condicao incondicional da pagina: o que
    sobra e "existe trilha na conta". A reducao e declarada, e nao um esquecimento -- os nomes
    dos tres parametros ficam em :data:`const.AWS_AUDIT_RULE_PARAMETERS` justamente para que
    "nao foi passado" seja uma escolha visivel.

    A armadilha de nome que a propria pagina avisa: "For this rule, the rule identifier
    (CLOUD_TRAIL_ENABLED) and rule name (cloudtrail-enabled) are different." O IDENTIFICADOR tem
    hifen entre ``CLOUD`` e ``TRAIL`` e o NOME nao tem. Ler o identificador como nome -- o que o
    escritor de FinOps ja fez, e cujo padrão de severidade ainda carrega ``cloud-trail-enabled``
    -- produz uma regra que nao existe no catalogo.

    Uma conta sem nenhuma trilha e NON_COMPLIANT nomeando a CONTA como contributor. E nao
    INSUFFICIENT_DATA: "a conta nao tem trilha" e um fato que o estado carrega, nao uma
    ignorancia sobre a conta. O terceiro valor so apareceria se a postura inteira nao existisse, e
    esse caso e decidido pelo renderer, que falha fechado em vez de devolver lacuna.
    """
    if parameters:
        # Uma avaliacao PARAMETRIZADA exigiria casar a trilha com o bucket, o log group ou o topico
        # pedido. O renderer nao passa parametro, entao este ramo existe para tornar o contrato
        # explicito -- e nao para ser um caminho silenciosamente diferente.
        raise NotImplementedError(
            f"{RULE_CLOUDTRAIL} ainda nao e avaliada com parametro; a condicao publicada sem "
            "parametro e a unica implementada"
        )
    if posture.cloudtrail:
        return _verdict(
            COMPLIANT,
            (),
            f"a conta tem {len(posture.cloudtrail)} trilha(s) CloudTrail: "
            + ", ".join(trail.trail_name for trail in posture.cloudtrail),
        )
    return _verdict(
        NON_COMPLIANT,
        (posture.account_id,),
        "a conta nao tem nenhuma trilha CloudTrail: a regra e NON_COMPLIANT se uma trilha nao "
        "esta habilitada",
    )


def evaluate_securityhub_enabled(posture: AwsAuditPosture) -> RuleVerdict:
    """A regra gerenciada ``securityhub-enabled``.

    A condicao completa da pagina, sem reducao nenhuma: "Checks if AWS Security Hub is enabled
    for an AWS Account. The rule is NON_COMPLIANT if AWS Security Hub is not enabled." E a
    pagina publica "Parameters: None" -- nao ha parametro opcional para reduzir, o que torna
    esta a regra mais simples do residuo e a que menos armadilha tem.

    Ela e por CONTA e nao por recurso, e a pagina nao publica "Resource Types": e o Security Hub
    que se inscreve na conta, e nao um recurso que se inventaria. Por isso o veredito se repete
    nas tres regioes da conta, igual ao das regras de IAM.
    """
    if posture.security_hub.enabled:
        return _verdict(COMPLIANT, (), "o Security Hub esta habilitado na conta")
    return _verdict(
        NON_COMPLIANT,
        (posture.account_id,),
        "o Security Hub nao esta habilitado na conta: a regra e NON_COMPLIANT se o Security Hub "
        "nao esta habilitado",
    )


def evaluate_vpc_flow_logs_enabled(
    log: AwsVpcFlowLog, parameters: Mapping[str, str] | None = None
) -> RuleVerdict:
    """A regra gerenciada ``vpc-flow-logs-enabled``, sobre UMA VPC.

    A pagina publica ``Resource Types: AWS::EC2::VPC``, e por isso o alvo aqui e a VPC e nao a
    conta. A condicao e "Checks if Amazon Virtual Private Cloud (Amazon VPC) flow logs are found
    and enabled for all Amazon VPCs. The rule is NON_COMPLIANT if flow logs are not enabled for
    at least one Amazon VPC." -- e o agregado da pagina ("for all", "at least one") e o que a
    pagina do ``Compliance`` ja resolve: "A rule is noncompliant if any of these resources do
    not comply". Por isso o avaliador responde sobre UMA VPC, e quem agrega e o renderer.

    **A armadilha que esta regra tem e a ausencia do fato.** Uma VPC sem flow log e
    ``NON_COMPLIANT``, e nao ``INSUFFICIENT_DATA``: ``flow_log_ids`` vazio e o estado que
    afirma "esta VPC nao tem trilha nenhuma", e nao "o estate nao sabe". Tratar a lista vazia como
    lacuna trocaria um achado por uma duvida e entregaria ao consumidor uma tela que esconde a
    violacao. O terceiro valor so aparece -- e e o renderer que decide -- no escopo que nao tem
    NENHUMA VPC, porque ai nao ha o que avaliar.

    O parametro OPCIONAL ``trafficType`` nao e passado, entao a regra reduz a condicao
    incondicional da pagina e nao filtra por tipo de trafego. Os tipos que cada trilha coleta
    ficam no estado (:attr:`AwsVpcFlowLog.traffic_types`) porque sao publicados -- e sao o que
    torna essa reducao inspecionavel.
    """
    if parameters:
        raise NotImplementedError(
            f"{RULE_VPC_FLOW_LOGS} ainda nao e avaliada com parametro; a condicao publicada sem "
            "parametro e a unica implementada"
        )
    if log.flow_log_ids:
        return _verdict(
            COMPLIANT,
            (),
            f"a VPC {log.vpc_id} tem {len(log.flow_log_ids)} flow log(s) habilitado(s)",
        )
    return _verdict(
        NON_COMPLIANT,
        (log.vpc_id,),
        f"a VPC {log.vpc_id} nao tem flow log habilitado: a regra e NON_COMPLIANT quando o flow "
        "log nao esta habilitado para pelo menos uma VPC",
    )


#: As DUAS regras de CONTA, sob a mesma assinatura uniforme dos avaliadores de identidade. A
#: postura e a de auditoria da conta, e nao a de identidade: sao colecoes distintas porque os
#: fatos nao tem nada a ver -- MFA do root nao diz se existe trilha, e trilha nao diz se a senha
#: e forte.
#:
#: ``parameters`` e ADIADO, nunca ENGOLIDO. Descartar o argumento aqui faria a guarda
#: ``NotImplementedError`` de :func:`evaluate_cloudtrail_enabled` nunca disparar, e um chamador
#: que pedisse a regra com ``s3BucketName`` receberia a condicao nao filtrada sem nenhum erro --
#: o veredito de OUTRA regra, em silencio, que e o pior modo de falha possivel num instrumento
#: cuja razao de existir e dizer a verdade. A regra do Security Hub e a excecao que prova a
#: regra: a pagina publica "Parameters: None", entao nao ha o que adiar e a funcao nem aceita o
#: argumento.
ACCOUNT_AUDIT_RULE_EVALUATORS: Final = {
    RULE_CLOUDTRAIL: lambda posture, sim_now, parameters=None: evaluate_cloudtrail_enabled(
        posture, parameters
    ),
    RULE_SECURITYHUB: lambda posture, sim_now, parameters=None: evaluate_securityhub_enabled(posture),
}

#: A regra POR RECURSO de flow log, com a MESMA assinatura. Fica em registro proprio porque a
#: postura dela e por recurso e nao por conta; uma regra por conta nao pode declarar um
#: ``resource_type``, e uma regra por recurso nao pode ser avaliada com a conta. O
#: ``parameters`` e adiado pelo mesmo motivo do registro acima.
VPC_FLOW_LOG_RULE_EVALUATORS: Final = {
    RULE_VPC_FLOW_LOGS: lambda posture, sim_now, parameters=None: evaluate_vpc_flow_logs_enabled(
        posture, parameters
    ),
}
