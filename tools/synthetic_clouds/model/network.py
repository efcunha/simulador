"""Rede canonica: segmento, interface e fluxo (design sec. 4.7, estendido).

Existe porque os quatro renderers de flow log estavam fieis ao FORMATO e vazios
de DADO: o modelo nao tinha de onde tirar um fluxo. A especificacao do que faltava
esta em ``docs/MODELO-REDE.md``, derivada das quatro specs oficiais.

A ordem importa e e deliberada: **primeiro o inventario de rede, depois o fluxo**.
Sem interface e segmento, o ``log_resource_id`` de um fluxo seria dado orfao -- e
o gate do projeto (P2) recusa orfaos --, os segmentos de caminho documentados do
blob da Azure nao teriam valor, e nao existiria MAC, que a Azure exige em cada
grupo de fluxo.

Divergencias entre nuvens que este modelo NAO uniformiza (e por que):

* **protocolo** -- guardamos o numero IANA. O NSG da Azure escreve ``T``/``U`` e
  as outras escrevem o numero; cada renderer converte para a forma da sua nuvem.
* **granularidade do tempo** -- ``window_start``/``window_end`` sao instantes UTC.
  A Azure NSG publica segundos e o VNet milissegundos; quem escolhe o formato de
  saida e o renderer, a partir da spec.
* **estado do fluxo** -- ``flow_state`` e opcional: so NSG e VNet carregam
  (``B``/``C``/``E``, e o VNet acrescenta ``D``).
* **quem observou** -- ``reported_by`` e opcional e carrega o ``reporter`` do GCP
  (``SRC``/``DEST``). A AWS expressa a via reversa como uma linha propria, e a
  Azure como contadores reversos no mesmo registro; o modelo guarda as duas
  leituras possiveis em vez de escolher uma.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

#: Direcoes canonicas. Cada renderer traduz para o vocabulario da sua nuvem
#: (AWS ``ingress``/``egress``, Azure ``I``/``O``, GCP ``ingress``/``egress``).
DIRECTION_INGRESS = "ingress"
DIRECTION_EGRESS = "egress"
DIRECTIONS = (DIRECTION_INGRESS, DIRECTION_EGRESS)

#: Decisoes canonicas. AWS ``ACCEPT``/``REJECT``, Azure ``A``/``D``,
#: GCP ``ALLOWED``/``DENIED``.
DECISION_ALLOWED = "allowed"
DECISION_DENIED = "denied"
DECISIONS = (DECISION_ALLOWED, DECISION_DENIED)

#: Estados de fluxo documentados. ``D`` existe apenas no VNet.
FLOW_STATES = ("B", "C", "D", "E")

#: Literais de ``protocol`` que o ``SecurityRulePropertiesFormat`` da Azure publica. E uma
#: lista FECHADA: a pagina enumera exatamente estes seis valores, e um protocolo fora dela
#: seria vocabulario inventado.
SECURITY_RULE_PROTOCOLS = ("*", "Ah", "Esp", "Icmp", "Tcp", "Udp")

#: Faixa de ``priority`` que a Azure publica (100..4096, unica na colecao; menor = maior
#: prioridade). O modelo carrega a faixa porque um valor fora dela nao e uma regra valida.
SECURITY_RULE_PRIORITY_RANGE = (100, 4096)


@dataclass(slots=True, frozen=True)
class SecurityRule:
    """Uma regra de NSG, na forma que a Azure publica (``SecurityRulePropertiesFormat``).

    Existe porque o consumidor do lado do FinOps percorre as REGRAS de cada NSG e filtra
    por ``direction``/``access`` -- e o estado nao tinha nenhuma: o ``azure-sim`` respondia
    lista vazia "por desenho" para ``networkSecurityGroups``, com a justificativa registrada
    de que "the estate models no network security group".

    ``direction`` e ``access`` carregam o vocabulario CANONICO deste modelo
    (``DIRECTIONS``/``DECISIONS``, o mesmo de :class:`NetworkFlow`), e nao os literais
    ``Inbound``/``Allow`` da Azure: guardar a grafia de nuvem num modelo que existe para as
    tres seria duplicar o que o renderer ja faz. A conversao para os literais publicados e do
    renderer, a partir da spec.

    ``protocol`` e a EXCECAO deliberada, e a razao esta na evidencia: a Azure publica um
    dominio de STRINGS (``'*'``, ``'Ah'``, ``'Esp'``, ``'Icmp'``, ``'Tcp'``, ``'Udp'``) e nao
    numeros IANA -- ao contrario do flow log, onde o modelo guarda o numero e o renderer
    escreve ``T``/``U``. Guardar 6 e derivar "Tcp" exigiria uma tabela de conversao que a
    documentacao nao publica para os cinco casos (o que e "Ah"?), entao o modelo guarda o
    literal publicado e recusa qualquer outro (``SECURITY_RULE_PROTOCOLS``).

    Os campos de prefixo e de porta sao ``str``, e nao ``int``: a Azure publica
    ``sourcePortRange`` como string (``"*"`` ou ``"0-65535"``) e aceita curingas e service
    tags em ``addressPrefix``. Converter para inteiro perderia o dominio publicado.
    """

    name: str
    priority: int  # 100..4096, unico na colecao
    direction: str  # DIRECTIONS (canonico)
    access: str  # DECISIONS (canonico)
    protocol: str  # SECURITY_RULE_PROTOCOLS (literal da Azure)
    source_address_prefix: str
    destination_address_prefix: str
    source_port_range: str
    destination_port_range: str
    description: str | None = None


@dataclass(slots=True, frozen=True)
class NetworkSecurityGroup:
    """O NSG de um segmento: a assinatura e o resource group onde ele vive, mais as regras.

    O id ARM **nao e guardado**: ele e composto por :meth:`arm_id` a partir do resource group,
    que e o unico segmento que a Azure publica em minusculas/maiusculas mistas. Guardar as
    duas coisas (id e resource group) criaria duas grafias do mesmo id, que e exatamente o
    defeito que :meth:`~tools.synthetic_clouds.model.network.NetworkSegment` ja evita ao
    carregar o id VERBATIM para o flow log.

    ``rules`` e uma tupla ORDENADA por prioridade -- a documentacao exige prioridade unica na
    colecao e define que o menor numero tem a maior prioridade, entao a ordem e uma afirmacao
    do provedor, nao uma conveniencia de iteracao.
    """

    subscription_id: str  # GUID da assinatura, como o ARM id exige
    resource_group: str
    name: str
    rules: tuple[SecurityRule, ...]

    def arm_id(self) -> str:
        """O id ARM do NSG, no caminho que a pagina de template publica."""
        return (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.Network/networkSecurityGroups/{self.name}"
        )


@dataclass(slots=True, frozen=True)
class NetworkSegment:
    """Uma VPC/VNet com a sua sub-rede, dentro de um escopo (FK, sem orfaos)."""

    segment_uuid: str
    scope_id: str  # conta AWS | assinatura Azure | projeto GCP (FK)
    provider: str  # aws | azure | gcp (lowercase)
    region_id: str
    segment_id: str  # id nativo: vpc-... | ARM id da VNet | projects/../networks/..
    subnet_id: str
    name: str
    resource_group: str | None  # so Azure; o caminho do blob exige o segmento
    network_security_group_id: str | None  # id nativo da NSG/SG, quando houver
    network_security_group_uuid: str | None  # GUID da NSG: e ele que a Azure
    # publica em ``systemId``, NAO a assinatura. Projetar o scope_id ali poria um
    # id de assinatura num campo documentado como GUID de recurso.
    network_security_group: NetworkSecurityGroup | None = None  # so Azure, por ora:
    # e o NSG com as REGRAS. A AWS e o GCP tem grupo de seguranca, mas o formato de regra
    # de cada um e outro e nenhum deles foi especificado ainda -- deixar o campo ``None``
    # ali e a resposta correta, e nao um placeholder. O id acima continua sendo a
    # identidade que o flow log publica; este campo carrega o CONTEUDO da regra.


@dataclass(slots=True, frozen=True)
class NetworkInterface:
    """Uma interface (ENI/NIC) pertencente a UM recurso do estate (FK, sem orfaos).

    ``mac_address`` nao e enfeite: a Azure exige o MAC em cada grupo de fluxo, e
    ele vira a particao ``macAddress=`` do caminho do blob.
    """

    interface_uuid: str
    resource_uuid: str  # FK -> ResourceIdentity.uuid
    segment_uuid: str  # FK -> NetworkSegment.segment_uuid
    interface_id: str
    mac_address: str
    private_ip: str
    region_id: str


@dataclass(slots=True, frozen=True)
class NetworkFlow:
    """Um registro de fluxo numa janela, no nivel que as quatro nuvens documentam.

    ``src_interface_uuid`` e ``dst_interface_uuid`` podem ser ``None`` quando a
    ponta esta FORA do estate (internet), o que e comum em fluxo de entrada. O
    gate exige que ao menos uma das pontas esteja ligada a uma interface -- um
    fluxo sem nenhuma ponta conhecida nao teria de onde sair.
    """

    flow_id: str
    segment_uuid: str  # FK -> NetworkSegment.segment_uuid
    src_interface_uuid: str | None
    dst_interface_uuid: str | None
    window_start: datetime  # UTC
    window_end: datetime  # UTC
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol_number: int  # IANA: 6 TCP, 17 UDP, 1 ICMP
    direction: str  # DIRECTIONS
    decision: str  # DECISIONS
    packets: int
    bytes: int
    log_resource_id: str  # id do recurso que produz o log (interface ou segmento)
    account_id: str  # conta | assinatura | projeto
    flow_state: str | None = None  # B|C|D|E -- so Azure
    encryption: str | None = None  # so VNet e ``encryption-status`` da AWS
    reported_by: str | None = None  # reporter do GCP: SRC | DEST
    packets_reverse: int | None = None  # contadores reversos: Azure NSG/VNet
    bytes_reverse: int | None = None


# ---------------------------------------------------------------------------
# AWS: security group na forma que ``ec2.describe_security_groups`` publica
# ---------------------------------------------------------------------------
#
# Estas estruturas NAO reusam :class:`SecurityRule` / :class:`NetworkSecurityGroup`, e a
# razao e de DOMINIO, nao de estilo. A regra da AWS e outro objeto, publicado pela API
# ``ec2``, e forca-lo na forma da Azure fabricaria membros que a AWS nao publica e
# apagaria membros que ela publica:
#
# 1. **Nao existe regra ``denied`` na AWS.** O guia de VPC e explicito -- "You can
#    specify allow rules, but not deny rules"
#    (https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html).
#    O bloqueio e a AUSENCIA de regra. Como :data:`DECISIONS` existe para o fluxo
#    (onde ``REJECT`` e ``DENIED`` sao eventos observados), seria enganoso reusar esse
#    vocabulario aqui: nao ha evento de negacao para observar.
# 2. **Nao existe prioridade.** A Azure publica ``priority`` 100..4096 com o menor
#    numero vencendo; a API da AWS nao tem membro de ordem nem de precedencia -- todas
#    as regras de um grupo sao igualmente aplicadas. Guardar `priority` aqui seria um
#    campo que a fonte nao publica.
# 3. **O protocolo e um dominio DIFERENTE.** ``IpPermission.ipProtocol`` e String e a
#    documentacao diz aceitar um nome (``tcp``/``udp``/``icmp``/``icmpv6``) OU um numero
#    de protocolo, OU ``-1`` para "todos os protocolos" -- enquanto
#    :data:`SECURITY_RULE_PROTOCOLS` e a lista FECHADA de seis literais da Azure.
# 4. **A fonte e uma lista, nao dois campos.** ``IpPermission`` tem UM conjunto de
#    destinos possiveis (``IpRanges`` OU ``Ipv6Ranges`` OU ``Groups`` OU
#    ``PrefixListIds``, e a propria pagina diz que CIDR e security group sao mutuamente
#    exclusivos) e UM par ``fromPort``/``toPort``. A Azure tem prefixo de origem E de
#    destino, e faixa de porta de origem E de destino, quatro campos.
# 5. **As portas sao condicionais.** ``fromPort``/``toPort`` sao ``Required: No`` e, para
#    ``icmp``/``icmpv6``, nao sao portas: sao o TIPO e o CODIGO ICMP. Para ``-1`` eles
#    simplesmente nao existem -- a amostra oficial da acao traz a regra de egress padrao
#    sem nenhum dos dois.

#: Nomes de protocolo que a pagina de ``IpPermission`` exemplifica. Nao e lista fechada:
#: a mesma pagina diz que o campo tambem aceita um NUMERO de protocolo. O vocabulario
#: publicado e por isso nome-ou-numero, e ``-1`` significa "todos os protocolos".
AWS_IP_PROTOCOLS = ("tcp", "udp", "icmp", "icmpv6")

#: O valor que a documentacao chama de "todos os protocolos". A amostra oficial da acao
#: mostra a regra de egress padrao de um SG recem-criado exatamente assim -- ``-1`` sem
#: ``fromPort``/``toPort``.
AWS_IP_PROTOCOL_ALL = "-1"

#: O nome do grupo PADRAO de uma VPC. Sai da amostra oficial de ``DescribeSecurityGroups``,
#: cujo grupo padrao traz ``<groupName>default</groupName>`` e
#: ``<groupDescription>default VPC security group</groupDescription>``. E o que permite
#: identificar o grupo que a regra gerenciada ``vpc-default-security-group-closed``
#: avalia.
AWS_DEFAULT_SECURITY_GROUP_NAME = "default"

#: A descricao que a amostra oficial associa ao grupo padrao.
AWS_DEFAULT_SECURITY_GROUP_DESCRIPTION = "default VPC security group"


@dataclass(slots=True, frozen=True)
class AwsIpRange:
    """Um membro de ``IpPermission.IpRanges``: uma faixa IPv4 (``IpRange`` da API)."""

    cidr_ip: str
    description: str | None = None


@dataclass(slots=True, frozen=True)
class AwsIpv6Range:
    """Um membro de ``IpPermission.Ipv6Ranges``: uma faixa IPv6 (``Ipv6Range`` da API)."""

    cidr_ipv6: str
    description: str | None = None


@dataclass(slots=True, frozen=True)
class AwsPrefixListId:
    """Um membro de ``IpPermission.PrefixListIds`` (``PrefixListId`` da API)."""

    prefix_list_id: str
    description: str | None = None


@dataclass(slots=True, frozen=True)
class AwsUserIdGroupPair:
    """Um membro de ``IpPermission.Groups`` (``UserIdGroupPair`` da API).

    Os membros sao os que a pagina publica, e todos sao ``None`` quando o estado nao os
    carrega -- a unica excecao e ``group_id``, que identifica o par. ``peering_status``
    e ``vpc_peering_connection_id`` so tem valor num par que resolve um par via peering.
    """

    group_id: str
    group_name: str | None = None
    user_id: str | None = None
    vpc_id: str | None = None
    peering_status: str | None = None
    vpc_peering_connection_id: str | None = None
    description: str | None = None


@dataclass(slots=True, frozen=True)
class AwsIpPermission:
    """Uma regra de ingress ou egress, na forma de ``IpPermission``.

    ``ip_protocol`` guarda o valor PUBLICADO: um nome de :data:`AWS_IP_PROTOCOLS`, um
    numero de protocolo, ou :data:`AWS_IP_PROTOCOL_ALL`. Nao ha conversao para o
    ``protocol_number`` do fluxo, porque a fonte aceita os dois e escolher um seria
    perder o dominio.

    ``from_port``/``to_port`` sao ``None`` -- e nao zero -- quando a regra nao os publica:
    e o caso de ``-1``, e o caso em que a documentacao diz que nao se aplica. Guardar zero
    ali seria um valor que a API nao devolve.
    """

    ip_protocol: str
    from_port: int | None
    to_port: int | None
    ip_ranges: tuple[AwsIpRange, ...] = ()
    ipv6_ranges: tuple[AwsIpv6Range, ...] = ()
    group_pairs: tuple[AwsUserIdGroupPair, ...] = ()
    prefix_list_ids: tuple[AwsPrefixListId, ...] = ()


@dataclass(slots=True, frozen=True)
class AwsSecurityGroup:
    """Um security group da AWS, com as REGRAS que a acao publica.

    Differe de :class:`NetworkSecurityGroup` (Azure) em ate dois pontos que importam:
    ``resource_uuid`` amarra o grupo ao recurso ``security_group`` do estate -- a FK que o
    gate exige para nao haver orfao -- e ``owner_id`` guarda o DONO da conta, que
    ``UserIdGroupPair.userId`` tambem publica.

    ``ingress`` e ``egress`` sao as duas listas que ``SecurityGroup`` traz separadas
    (``IpPermissions`` e ``IpPermissionsEgress``), e nao um campo ``direction``: a AWS
    nao tem um membro ``direction`` na regra, porque a direcao ja e o nome da lista.
    Guardar a direcao em cada regra seria duplicar o que o nome da propriedade afirma.
    """

    resource_uuid: str  # FK -> ResourceIdentity.uuid (recurso ``security_group``)
    group_id: str
    group_name: str
    group_description: str
    owner_id: str
    vpc_id: str
    ingress: tuple[AwsIpPermission, ...] = ()
    egress: tuple[AwsIpPermission, ...] = ()

    @property
    def is_default(self) -> bool:
        """Se este e o grupo PADRAO da sua VPC.

        A regra gerenciada ``vpc-default-security-group-closed`` avalia "the default
        security group of any Amazon Virtual Private Cloud", e a amostra oficial identifica
        esse grupo por ``groupName = "default"``. A regra tambem diz que ela e
        NON_COMPLIANT quando o grupo padrao tem "one or more inbound or outbound traffic
        rules" -- e nao existe regra de negacao na AWS, logo o veredito se le nas DUAS
        listas.
        """
        return self.group_name == AWS_DEFAULT_SECURITY_GROUP_NAME


# ---------------------------------------------------------------------------
# GCP: regra de firewall na forma que ``compute.firewalls.list`` publica
# ---------------------------------------------------------------------------
#
# Estas estruturas NAO reusam :class:`SecurityRule` (Azure) nem :class:`AwsIpPermission`, e a
# razao e de DOMINIO, nao de estilo. A regra de firewall da GCP e outro objeto, publicado pela
# API ``compute``, e forca-lo em qualquer das outras formas fabricaria membros que a GCP nao
# publica e apagaria membros que ela publica:
#
# 1. **A decisao sao DUAS LISTAS, nao um campo.** A GCP publica ``allowed[]`` e ``denied[]``
#    lado a lado no mesmo recurso. O security group da AWS e so de PERMISSAO ("You can specify
#    allow rules, but not deny rules") e a Azure tem UMA regra com ``access``
#    (``allowed``/``denied``). Reusar qualquer um dos dois traria uma decisao para a regra
#    individual -- que a GCP nao tem -- e apagaria a simetria das duas listas.
# 2. **A direcao e um MEMBRO, e nao o nome da lista.** Na AWS a direcao e o nome da propriedade
#    que contem a regra (``IpPermissions``/``IpPermissionsEgress``) e nao ha membro nenhum; a
#    Azure publica ``direction`` por regra. A GCP publica ``direction`` tambem, com INGRESS ou
#    EGRESS, e fecha que "For EGRESS traffic, you cannot specify the sourceTags fields".
# 3. **As portas sao uma LISTA DE STRINGS que aceita faixa.** ``ports`` e ``["22"]`` ou
#    ``["12345-12349"]``, nao o par ``fromPort``/``toPort`` da AWS nem a string unica da
#    Azure. Nao ha par de portas para guardar, entao guardar numeros seria escolher uma
#    sintaxe que a GCP nao usa.
# 4. **O protocolo tem nome OU numero.** ``IPProtocol`` aceita um nome conhecido
#    (``tcp``/``udp``/``icmp``/``esp``/``ah``/``ipip``/``sctp``) OU o numero do protocolo, e
#    ``all`` e o valor que a API devolve na regra pre-populada ``default-allow-internal`` --
#    enquanto :data:`SECURITY_RULE_PROTOCOLS` e a lista FECHADA de seis literais da Azure.
# 5. **Origem e destino sao dois membros de faixa.** ``sourceRanges`` (entrada) e
#    ``destinationRanges`` (saida), ambos CIDR e ambos IPv4/IPv6, ao contrario da Azure que
#    tem prefixo de origem E de destino na MESMA regra.
# 6. **O alvo tem tres containers com exclusividade declarada.** ``targetTags``,
#    ``targetServiceAccounts`` e ``sourceTags``; a propria pagina fecha que
#    ``targetServiceAccounts`` "cannot be used at the same time as targetTags or sourceTags".

#: Os nomes de protocolo que a pagina de ``Firewall`` lista como "well known protocol strings".
#: NAO e lista fechada: a mesma pagina diz que o campo tambem aceita o NUMERO do protocolo, e o
#: valor ``all`` -- que a API devolve na regra pre-populada ``default-allow-internal`` -- nao
#: esta nessa prosa, o que a spec desta superficie registra em 'unverified'.
GCP_FIREWALL_PROTOCOLS = ("tcp", "udp", "icmp", "esp", "ah", "ipip", "sctp")

#: O valor que a API de fato devolve para a regra que libera TODO o trafego. A saida oficial de
#: ``gcloud compute firewall-rules list`` de um projeto recem-criado traz
#: ``default-allow-internal ... all``, e o guia de VPC firewall diz que a regra vale para
#: "all traffic on any protocol and any destination port" quando protocolo e portas sao
#: omitidos. Guardar este valor separado dos nomes acima e o que impede um verificador de tratar
#: a prosa da pagina como lista fechada.
GCP_FIREWALL_PROTOCOL_ALL = "all"

#: Os dois valores de ``direction`` que a pagina publica, e o default declarado ("The default
#: is ``INGRESS``"). A regra da GCP e sempre de UMA direcao: "A single rule cannot apply to both
#: ingress and egress traffic."
GCP_FIREWALL_INGRESS = "INGRESS"
GCP_FIREWALL_EGRESS = "EGRESS"
GCP_FIREWALL_DIRECTIONS = (GCP_FIREWALL_INGRESS, GCP_FIREWALL_EGRESS)

#: A faixa de ``priority`` que a pagina publica: inteiro de 0 a 65535, menor numero com maior
#: precedencia, e no empate a acao ``deny`` prevalece sobre ``allow``.
GCP_FIREWALL_PRIORITY_RANGE = (0, 65535)

#: A prioridade que a pagina declara como default, e a das quatro regras pre-populadas da rede
#: default (a "second lowest priority", depois das duas regras implicitas de 65535).
GCP_FIREWALL_DEFAULT_PRIORITY = 1000
GCP_FIREWALL_PREPOPULATED_PRIORITY = 65534

#: A enumeracao que a pagina de ``FirewallLogConfig.metadata`` publica.
GCP_FIREWALL_LOG_METADATA = ("EXCLUDE_ALL_METADATA", "INCLUDE_ALL_METADATA")

#: O valor que a pagina descreve como "include metadata for firewall logs". Nomeado a parte para
#: que um chamador nao dependa da POSICAO dentro da enumeracao.
GCP_FIREWALL_LOG_INCLUDE_ALL = "INCLUDE_ALL_METADATA"

#: O tipo de recurso que a coluna ``kind`` do recurso publica: "Always compute#firewall for
#: firewall rules".
GCP_FIREWALL_KIND = "compute#firewall"

#: O tipo de recurso que a coluna ``kind`` do ENVELOPE publica: "Always compute#firewallList for
#: lists of firewalls".
GCP_FIREWALL_LIST_KIND = "compute#firewallList"

#: A faixa que o guia de VPC firewall da para a rede default: "Permits incoming connections to VM
#: instances from other instances within the same VPC network", a origem de
#: ``default-allow-internal``.
GCP_FIREWALL_INTERNAL_RANGE = "10.128.0.0/9"

#: "todos os enderecos IPv4", a origem que a tabela de regras pre-populadas traz literalmente em
#: ``default-allow-ssh``, ``default-allow-rdp`` e ``default-allow-icmp``.
GCP_FIREWALL_ANY_RANGE = "0.0.0.0/0"

#: Um prefixo de documentacao (RFC 5737), o mesmo que a postura dos security groups da AWS usa,
#: para uma origem restrita que nao implica host real.
GCP_FIREWALL_DOCS_RANGE = "203.0.113.0/24"


@dataclass(slots=True, frozen=True)
class GcpFirewallEntry:
    """Uma tupla protocolo/porta de uma regra de firewall da GCP.

    E a MESMA forma em ``allowed[]`` e em ``denied[]``: a GCP nao publica um tipo nomeado
    diferente para os dois (no documento de discovery os dois sao um objeto inline), entao o
    modelo tem um tipo so e a distincao fica na lista que o contem.

    ``ports`` e a forma PUBLICADA -- uma lista de strings, cada uma um inteiro ou uma faixa
    (``["22"]``, ``["80","443"]``, ``["12345-12349"]``) -- e fica VAZIA quando a regra vale
    para qualquer porta, que e o que a pagina declara: "If not specified, this rule applies to
    connections through any port." Vazio aqui significa "qualquer porta"; a string ``"0-65535"``
    seria outra grafia do mesmo efeito, e o modelo nao escolhe uma delas.
    """

    ip_protocol: str
    ports: tuple[str, ...] = ()

    @property
    def allows_any_port(self) -> bool:
        """Se a tupla nao restringe porta -- o caso que a pagina diz valer "any port"."""
        return not self.ports


@dataclass(slots=True, frozen=True)
class GcpFirewallRule:
    """Uma regra de firewall da GCP, na forma que ``compute.firewalls.list`` publica.

    Differe de :class:`NetworkSecurityGroup` (Azure) e de :class:`AwsSecurityGroup` (AWS) no
    que a secao de dominio acima detalha: aqui a decisao sao DUAS listas, a direcao e membro, e
    as portas sao strings com faixa.

    ``segment_uuid`` amarra a regra a rede que ela protege -- a FK que o gate exige para nao
    haver orfao -- e ``scope_id`` e o PROJETO, que e o escopo da resposta: a lista e
    ``projects/<projeto>/global/firewalls``, global e sem regiao. A regra de firewall e global
    na GCP; a regiao so existe no par rede/sub-rede.

    ``network_url`` e o ``segment_id`` do segmento, VERBATIM: ao contrario do ``vpcId`` do
    security group da AWS, que e uma derivacao declarada a partir do segmento, aqui nao ha
    derivacao -- ``Firewall.network`` publica a URL da rede e o segmento ja carrega essa URL.
    """

    segment_uuid: str  # FK -> NetworkSegment.segment_uuid
    scope_id: str  # projeto GCP (FK); e o escopo da resposta da lista
    rule_name: str
    network_url: str
    direction: str  # INGRESS | EGRESS
    priority: int
    description: str = ""
    disabled: bool = False
    source_ranges: tuple[str, ...] = ()
    destination_ranges: tuple[str, ...] = ()
    target_tags: tuple[str, ...] = ()
    source_tags: tuple[str, ...] = ()
    target_service_accounts: tuple[str, ...] = ()
    source_service_accounts: tuple[str, ...] = ()
    allowed: tuple[GcpFirewallEntry, ...] = ()
    denied: tuple[GcpFirewallEntry, ...] = ()
    log_enabled: bool = False
    log_metadata: str | None = None

    @property
    def is_prepopulated(self) -> bool:
        """Se esta e uma das quatro regras que a rede DEFAULT nasce com.

        A tabela "Pre-populated rules in the default network" do guia de VPC firewall declara os
        quatro nomes, a direcao ingress, a prioridade 65534, a origem e os pares protocolo:porta
        de cada um. Uma rede que nao seja a default nao tem nenhuma delas.
        """
        return self.rule_name.startswith("default-allow-")

    @property
    def exposes_to_anywhere(self) -> bool:
        """Se a regra e de ENTRADA, esta habilitada e vem de qualquer endereco IPv4.

        E a conjuncao que o consumidor de seguranca avalia antes de olhar protocolo e porta, e
        cada metade dela e um membro documentado: ``direction`` INGRESS, ``disabled`` falso e
        ``0.0.0.0/0`` entre as origens.
        """
        return (
            self.direction == GCP_FIREWALL_INGRESS
            and not self.disabled
            and GCP_FIREWALL_ANY_RANGE in self.source_ranges
        )
