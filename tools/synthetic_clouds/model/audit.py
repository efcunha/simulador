"""Os fatos de AUDITORIA e GUARDRAILS de uma conta AWS -- a chave que as tres regras
residuais do Config leem.

As tres regras que sobraram depois do Incremento 4 -- ``cloudtrail-enabled``,
``securityhub-enabled`` e ``vpc-flow-logs-enabled`` -- respondiam ``INSUFFICIENT_DATA`` por
lacuna de MODELO nomeada, e nao por duvida sobre a regra. E o Incremento 4.3 pela mesma razao
dos tres anteriores: o recurso ja era inventariado e faturado, mas nada no estate carregava o
CONTEUDO que a regra leria.

A GRANULARIDADE E DIFERENTE NOS DOIS LADOS, e a diferenca vem da documentacao das paginas das
regras, nao de uma escolha demodelagem:

* ``cloudtrail-enabled`` e ``securityhub-enabled`` sao de NIVEL DE CONTA. As duas paginas
  publicam **Trigger type: Periodic** e **nenhum "Resource Types"** -- o alvo e a conta, e nao
  um recurso. Por isso moram em :class:`AwsAuditPosture`, chaveada por
  ``AwsAccount.account_id``, e o veredito se repete em cada escopo regional da conta, como o das
  regras de IAM do Incremento 4.
* ``vpc-flow-logs-enabled`` e **POR VPC**. A pagina publica ``Resource Types: AWS::EC2::VPC``, e
  o veredito de uma VPC e o de uma VPC. Por isso ela fica em :class:`AwsVpcFlowLog`, keyed pelo
  recurso ``vpc`` do proprio estate -- o mesmo join de ``AwsBucketPosture`` e
  ``AwsSecurityGroup`` (Incrementos 3 e 2).

POR QUE ``vpc-flow-logs-enabled`` NAO VIVE EM ``NetworkSegment``
-------------------------------------------------------------
``NetworkSegment`` e a estrutura de REDE multi-provedor (``provider`` em ``aws|azure|gcp``), e os
15 ``NetworkSegment`` de AWS nao sao os 15 recursos ``vpc`` do inventory -- moram em outra regiao.
Estender a estrutura compartilhada com um campo so da AWS seria colocar semantica de um
provedor dentro de um registro que os quatro leem, e o filtro por ``provider`` passaria a
depender de um campo que so um preenche. Por isso a postura fica em colecao propria e o join e
pelo recurso ``vpc`` -- identico ao dos Incrementos 2 e 3.

E por que nao reaproveitar ``NetworkFlow``, que ja existe: o renderer
``render/vpc_flow_logs.py`` projeta ``NetworkFlow`` em REGISTROS DE ENTREGA de flow log, e o
docstring dele proprio diz que "the estate carries no flow-log resource" e que na AWS o recurso
que produz o log e a ENI (``eni-...``), nao a VPC. "Havia trafego entregue numa ENI" e "esta VPC
tem flow log habilitado" sao fatos diferentes, de granularidades diferentes, e derivar o segundo
do primeiro seria responder a uma pergunta que ninguem fez.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AwsCloudTrail:
    """Uma trilha CloudTrail da conta -- o que ``cloudtrail-enabled`` le.

    A regra nao le a trilha: ela le **se existe trilha na conta**. Por isso a postura e uma
    TUPLA de trilhas e nao um booleano -- um booleano ``cloudtrail_enabled`` no modelo traria a
    resposta da regra gravada no proprio fato, e o veredito deixaria de ser o resultado de
    consultar o estado para virar a leitura de um campo. Com a tupla, "pelo menos uma" e uma
    consulta de verdade sobre entidades de verdade.

    Os tres membros ``s3_bucket_name`` / ``cloud_watch_logs_group_arn`` / ``sns_topic_arn`` sao
    os tres parametros OPCIONAIS da propria regra, e ficam no modelo mesmo com o renderer nao
    passando nenhum: e o que torna a reducao declarada em
    :func:`~tools.synthetic_clouds.render._config_evaluators.evaluate_cloudtrail_enabled`
    verificavel -- uma avaliacao parametrizada tem os tres valores no estado em vez de ter que
    inventa-los.

    ``is_multi_region_trail`` e o que a documentacao chama de trilha "multi-regiao": uma trilha
    dessas grava o trafego de varias regioes numa unica conta de destino, e e o estado que o
    operador liga quando quer a cobertura de auditoria da conta inteira.
    """

    trail_name: str
    trail_arn: str  # arn:aws:cloudtrail:<region>:<account-id>:trail/<name>
    home_region: str
    is_multi_region_trail: bool
    s3_bucket_name: str | None = None
    cloud_watch_logs_group_arn: str | None = None
    sns_topic_arn: str | None = None


@dataclass(slots=True, frozen=True)
class AwsSecurityHubEnrollment:
    """A inscricao do Security Hub na conta -- o que ``securityhub-enabled`` le.

    ``enabled`` e o booleano da propria regra: "The rule is NON_COMPLIANT if AWS Security Hub is
    not enabled." E ``hub_arn`` e o identificador que a conta recebe quando a inscricao existe --
    ``None`` quando ela nao existe, e nao uma string vazia, para que "nao inscrito" e "inscrito
    sem ARN" nao sejam o mesmo estado.

    Os finding aggregator e os PADRAO (CIS, PCI DSS...) **nao** sao modelados, e a razao e o
    proprio criterio deste pacote: a regra le um booleano de inscricao, e um campo que nenhum
    consumidor daqui projeta seria fidelidade de vitrine.
    """

    enabled: bool
    hub_arn: str | None  # arn:aws:securityhub:<region>:<account-id>:hub/default


@dataclass(slots=True, frozen=True)
class AwsAuditPosture:
    """A postura de AUDITORIA de UMA conta -- a chave que as duas regras de conta leem.

    Uma instancia por conta do estate. ``cloudtrail`` pode ser vazia: uma conta sem nenhuma
    trilha e um estado legitimo, e nesse caso ``cloudtrail-enabled`` responde ``NON_COMPLIANT``
    nomeando a conta -- e nao ``INSUFFICIENT_DATA``, que diria que o estate nao sabe, quando ele
    sabe.

    O veredito se repete nas tres regioes da conta, e nao por esquecimento: as duas paginas
    publicam trigger ``Periodic`` e nenhum ``Resource Types``, entao nao ha regiao que a regra
    avalie -- e um veredito que variasse por regiao seria um fato que a AWS nao tem.
    """

    account_id: str  # FK -> AwsAccount.account_id
    cloudtrail: tuple[AwsCloudTrail, ...]
    security_hub: AwsSecurityHubEnrollment


@dataclass(slots=True, frozen=True)
class AwsVpcFlowLog:
    """A configuracao de flow logs de UMA VPC -- o que ``vpc-flow-logs-enabled`` le.

    A chave e o recurso ``vpc`` (``Resource.identity.uuid``), porque a pagina da regra publica
    ``Resource Types: AWS::EC2::VPC`` e o veredito de Config e por recurso avaliado: a regra e
    NON_COMPLIANT quando "flow logs are not enabled for at least one Amazon VPC".

    ``flow_log_ids`` vazio e o estado NAO CONFORME, e nao um estado desconhecido: e o que o
    estate afirma quando a VPC nao tem trilha nenhuma. E por isso que a lista e o campo lido em
    vez de um ``enabled: bool`` -- a regra conta as VPCs que reprovam, e um booleano por VPC
    daria a mesma resposta sem dizer QUAL VPC.

    ``traffic_types`` sao os tipos de trafego que a trilha coleta, no vocabulario da propria
    API (``ALL`` / ``ACCEPT`` / ``REJECT``). A regra aceita um parametro OPCIONAL
    ``trafficType``, e o renderer nao o passa -- entao a regra reduz a condicao incondicional da
    pagina ("flow logs are found and enabled"), sem filtro por tipo. Os valores ficam no modelo
    porque sao publicados, e sao o que torna a reducao declarada inspecionavel.

    A granularidade e por VPC e nao por conta: uma VPC com log e uma VPC sem log na MESMA conta
    sao o par que prova que a regra le a VPC, e nao a conta.
    """

    resource_uuid: str  # FK -> ResourceIdentity.uuid (recurso ``vpc``)
    vpc_id: str  # id nativo vpc-...
    account_id: str
    region_id: str
    flow_log_ids: tuple[str, ...] = ()  # vazio = a VPC nao tem flow log
    traffic_types: tuple[str, ...] = ()  # ALL | ACCEPT | REJECT