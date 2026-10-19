"""Shared, seed-independent catalog constants for generation.

These are fixed vocabularies (regions, services, SKUs, pricing) so the generator
is deterministic and does not fabricate provider schemas it cannot verify. Money
is ``Decimal`` 6-dp throughout (FOCUS numeric(18,6)).
"""

from __future__ import annotations

from decimal import Decimal

from tools.synthetic_clouds.model.network import (
    DECISION_ALLOWED,
    DECISION_DENIED,
    DIRECTION_EGRESS,
    DIRECTION_INGRESS,
)
from tools.synthetic_clouds.model.storage import (
    S3_ALL_USERS_URI,
    S3_AUTHENTICATED_USERS_URI,
    S3_LOG_DELIVERY_URI,
)

SIX_DP = Decimal("0.000001")

# FOCUS canonical provider names (FR-G1b; DISCOVERY sec. 6.1).
PROVIDER_AZURE = "Microsoft Azure"
PROVIDER_GCP = "Google Cloud"
# AWS's FOCUS ServiceProviderName. This is the value the FOCUS 1.2 + AWS x_*
# Data Export carries, NOT the "aws" provider key used by the operational rows
# (see PROVIDER_KEY_* below) and NOT the lowercase ProviderLiteral in
# focus.py (modulo do consumidor).
PROVIDER_AWS = "Amazon Web Services"

# ChargeCategory domain (FR-G1a; parser._VALID_CATEGORIES, verified).
VALID_CATEGORIES = ("Usage", "Purchase", "Tax", "Credit", "Adjustment")

# Azure regions (id, display name).
AZURE_REGIONS = (
    ("eastus", "East US"),
    ("westeurope", "West Europe"),
    ("brazilsouth", "Brazil South"),
)
# GCP regions.
GCP_REGIONS = (
    ("us-central1", "us-central1"),
    ("europe-west1", "europe-west1"),
    ("southamerica-east1", "southamerica-east1"),
)
# AWS regions. Asia/ASCII display names only: the emitted FOCUS CSV must stay
# byte-stable, and a non-ASCII RegionName would change the encoding surface for
# no fidelity gain.
AWS_REGIONS = (
    ("us-east-1", "US East (N. Virginia)"),
    ("us-west-2", "US West (Oregon)"),
    ("sa-east-1", "South America (Sao Paulo)"),
)

#: Tipos de recurso que o estate modela como OBJETO DE REDE, e nao como linha de catalogo.
#:
#: O ``NetworkSecurityGroup`` existe no estado (com as suas regras) porque o consumidor do
#: lado do FinOps percorre as regras de cada NSG -- mas ele NAO entra em
#: ``AZURE_SERVICES``: uma linha de catalogo carrega consumo, fatura, inventario, achado,
#: metrica e IaC, e um NSG nao tem preco nem metrica neste modelo. Declarar o tipo aqui
#: nomeia a entidade sem inventar fatura para ela. (O ``public_ip`` e o caso oposto: aparece
#: no catalogo porque a Azure de fato o cobra.)
NETWORK_FABRIC_RESOURCE_TYPES = ("network_security_group",)

#: Como a postura declara o ESTADO DE SAUDE de uma verificacao. O vocabulario e do
#: SIMULADOR: o renderer publica so ``Healthy``/``Unhealthy``/``NotApplicable``, que sao os
#: literais que a pagina publica.
SAUDE_ALTERNADA = "alternating"
SAUDE_NAO_APLICAVEL = "not-applicable"

#: As POSTURAS das verificacoes de seguranca do Defender for Cloud aplicadas a cada
#: segmento Azure, na forma POSICIONAL: ``(postura, saude, severidade)``.
#:
#: * ``saude == SAUDE_ALTERNADA`` -- a verificacao avalia o recurso, entao o estado depende
#:   do INDICE DO ESCOPO: ``Unhealthy`` no escopo de indice par e ``Healthy`` no de indice
#:   impar. Alternar por indice (e nao sortear) e o que garante que os DOIS lados do filtro do
#:   consumidor apareçam no MESMO estado -- a mesma razao que faz
#:   :data:`GCP_FIREWALL_RULES_BY_PROJECT` alternar por projeto: com um perfil so, todo
#:   escopo ficaria do mesmo lado e o veredito seria unico.
#: * ``saude == SAUDE_NAO_APLICAVEL`` -- a verificacao nao se aplica ao recurso avaliado, e
#:   o estado e ``NotApplicable`` sempre. E o caso da verificacao de endpoint protection que
#:   o exemplo oficial da pagina nomeia ("Install endpoint protection solution on virtual
#:   machine scale sets"): ela avalia Conjuntos de VMs, e o recurso avaliado aqui e a VNet.
#:
#: A chave ``postura`` e vocabulario DO SIMULADOR e nunca chega ao artefato.
#:
#: O ramo ``NotApplicable`` e o que mostra que ``NotApplicable`` NAO e o ramo descartado: o
#: consumidor so descarta ``status.code == "Healthy"``, entao um assessment nao aplicavel
#: vira achado do mesmo jeito. E o ramo ``Healthy`` -- este sim -- e o unico que exercita o
#: descarte.
#:
#: A severidade so vem no ramo ``Unhealthy``: nao ha severidade de achado para projetar em
#: um assessment saudavel ou nao aplicavel, e preencher seria inventar.
AZURE_DEFENDER_ASSESSMENT_POSTURES = (
    ("network-exposure", SAUDE_ALTERNADA, "Medium"),
    ("endpoint-protection", SAUDE_NAO_APLICAVEL, ""),
)

# A compact service catalog per provider. Each entry:
#   (resource_type, service_name, service_category, sku_id, unit, list_unit_price)
AZURE_SERVICES = (
    ("virtual_machine", "Virtual Machines", "Compute", "azure-vm-d2s-v5", "Hours", Decimal("0.096000")),
    ("managed_disk", "Managed Disks", "Storage", "azure-disk-p10", "Hours", Decimal("0.021000")),
    ("public_ip", "Virtual Network", "Networking", "azure-pubip-std", "Hours", Decimal("0.004000")),
    ("sql_database", "SQL Database", "Databases", "azure-sql-gp-2", "Hours", Decimal("0.520000")),
    ("storage_account", "Storage Accounts", "Storage", "azure-blob-hot", "GB-Month", Decimal("0.018400")),
    ("log_analytics", "Log Analytics", "Management", "azure-la-ingest", "GB", Decimal("2.300000")),
    ("openai", "Azure OpenAI", "AI + Machine Learning", "azure-openai-gpt4", "1K-Tokens", Decimal("0.030000")),
    ("aks_cluster", "Azure Kubernetes Service", "Compute", "azure-aks-node-d4s", "Hours", Decimal("0.192000")),
    # Added for the FR-21 reverse gaps (design sec. 23): Azure App Service is a service
    # ``service_discovery.py (modulo do consumidor)`` monitors and no catalog entry modelled.
    ("app_service", "Azure App Service", "Compute", "azure-app-plan-b1", "Hours", Decimal("0.075000")),
)
GCP_SERVICES = (
    ("compute_instance", "Compute Engine", "Compute", "gcp-ce-e2-standard-2", "Hours", Decimal("0.067000")),
    ("persistent_disk", "Compute Engine", "Storage", "gcp-pd-ssd", "Hours", Decimal("0.017000")),
    ("external_ip", "Compute Engine", "Networking", "gcp-static-ip", "Hours", Decimal("0.004000")),
    ("cloud_sql", "Cloud SQL", "Databases", "gcp-sql-db-n1-2", "Hours", Decimal("0.098000")),
    ("gcs_bucket", "Cloud Storage", "Storage", "gcp-gcs-standard", "GB-Month", Decimal("0.020000")),
    ("bigquery", "BigQuery", "Analytics", "gcp-bq-ondemand", "TB-Scanned", Decimal("5.000000")),
    ("egress", "Compute Engine", "Networking", "gcp-egress-inet", "GB", Decimal("0.120000")),
    ("gke_cluster", "Kubernetes Engine", "Compute", "gcp-gke-node-e2-std4", "Hours", Decimal("0.134000")),
    # Added for the FR-21 reverse gaps (design sec. 23). ``cloud_function`` closes the
    # inventory token ``FUNCTIONS`` — ``resources.py (modulo do consumidor):32`` collects Cloud
    # Functions and the catalog did not emit it, so the endpoint returned nothing.
    # ``cloud_run_service`` closes the service-discovery token ``gcp_cloud_run``.
    ("cloud_function", "Cloud Functions", "Compute", "gcp-cf-gb-second", "GB-Seconds", Decimal("0.0000025000")),
    ("cloud_run_service", "Cloud Run", "Compute", "gcp-run-vcpu-second", "vCPU-Seconds", Decimal("0.0000240000")),
)
#: As regras de um NSG Azure, na forma POSICIONAL: (nome, prioridade, direcao, acesso,
#: protocolo, prefixo de origem, prefixo de destino, faixa de porta de origem, faixa de porta
#: de destino). Posicional e nao dicionario de proposito -- ver ``_security_rules`` em
#: ``estate_builder``: um dicionario nao diz ao verificador de tipos qual campo cada posicao
#: alimenta, e um nome trocado so apareceria em execucao.
#:
#: Constante e nao sorteio, por duas razoes:
#:
#: 1. **A regra e uma politica, nao um dado.** Nao existe "regra aleatoria": o que existe e
#:    uma postura. Sortear ``Allow``/``Deny`` faria a existencia do achado depender do seed, e
#:    um estado limpo deixaria de ser um resultado possivel.
#: 2. **Os dois casos tem de existir no MESMO NSG.** O scanner filtra
#:    ``direction == "Inbound" and access == "Allow"``; sem uma regra ``Deny`` o teste nao
#:    consegue provar que ele distingue as duas -- um artefato so com ``Allow`` passaria mesmo
#:    se o filtro estivesse invertido.
#:
#: 3. **O estado precisa produzir um ACHADO, alem de uma postura.** (Incremento 7, medido.) A
#:    postura anterior -- ``AllowVnetInboundTls`` na 443 e ``DenyInternetInboundRdp`` -- era
#:    coerente, mas a pagina do consumidor (``_CRITICAL_PORTS``: 22, 3389, 5432, 3306, 1433,
#:    27017, 6379) NAO inclui a 443. Rodando a logica REAL de
#:    ``AzureSecurityScanner._list_open_nsgs`` sobre os artefatos entregues, o estado dava
#:    **0 achados** em 6/6 NSGs. Um NSG que expoe uma porta de qualquer origem mas nunca e
#:    sinalizado nao treina o check. Por isso existe ``AllowInternetInboundSsh``: a exposicao
#:    que o consumidor classifica como CRITICAL, e ela usa o SERVICE TAG ``Internet`` -- uma das
#:    tres origens abertas que o consumidor aceita (``*``, ``0.0.0.0/0``, ``Internet``) --
#:    exercitando um ramo do filtro que nem a CIDR nem o asterisco cobrem.
#:
#: Prioridades 100, 200 e 300 (unicas na colecao, como a documentacao exige; menor = maior
#: prioridade, entao o ``Allow`` critico e avaliado antes -- que e o que torna a exposicao real).
#: ``protocol`` e o literal publicado ``Tcp``. Os prefixos e a porta de origem usam ``'*'``,
#: que a propria pagina documenta para esses campos; usar um CIDR exigiria afirmar a faixa da
#: VNet, que o modelo nao carrega, e um prefixo que nao contivesse as NICs da mesma VNet seria
#: uma afirmacao falsa sobre a rede. O prefixo de ORIGEM da regra critica e o service tag
#: ``Internet``, que a propria pagina publica como valor valido.
NSG_SECURITY_RULES = (
    (
        "AllowInternetInboundSsh",
        100,
        DIRECTION_INGRESS,
        DECISION_ALLOWED,
        "Tcp",
        "Internet",
        "*",
        "*",
        "22",
    ),
    (
        "AllowVnetInboundTls",
        200,
        DIRECTION_INGRESS,
        DECISION_ALLOWED,
        "Tcp",
        "*",
        "*",
        "*",
        "443",
    ),
    (
        "DenyInternetInboundRdp",
        300,
        DIRECTION_INGRESS,
        DECISION_DENIED,
        "Tcp",
        "*",
        "*",
        "*",
        "3389",
    ),
)

#: Nomes das regras que o consumidor do FinOps DEVE encontrar ao varrer um NSG deste
#: estado. Nomear a expectativa aqui (e nao no teste) permite que o teste e o relatorio de
#: proveniencia citem a mesma fonte.
#:
#: A primeira e a exposicao CRITICAL (Internet -> 22): sem ela o consumidor nao produz achado
#: nenhum. A segunda e a Allow NAO-critica (443): existe para provar que o filtro distingue
#: porta critica de porta comum -- se ela tambem gerasse achado, o teste nao diria nada sobre a
#: classificacao de severidade. A terceira e a Deny, para provar que o filtro distingue Allow de
#: Deny mesmo com a MESMA origem aberta e uma porta critica (3389).
NSG_EXPECTED_INBOUND_ALLOW_CRITICAL = "AllowInternetInboundSsh"
NSG_EXPECTED_INBOUND_ALLOW = "AllowVnetInboundTls"
NSG_EXPECTED_INBOUND_DENY = "DenyInternetInboundRdp"

#: Provedor cujo NSG este estado modela na FORMA DA AZURE. A AWS tem grupo de seguranca com
#: formato de regra PROPRIO, especificado em ``aws/ec2-describe-security-groups`` e modelado em
#: :data:`AWS_SG_POSTURES` abaixo; o GCP nao modela grupo nenhum. Emitir o formato da Azure para
#: qualquer um deles seria inventar contrato.
NSG_MODELED_PROVIDER = "azure"

# ---------------------------------------------------------------------------
# AWS: a postura declarada dos security groups (ec2.describe_security_groups)
# ---------------------------------------------------------------------------
#
# Constante e nao sorteio, pelas mesmas duas razoes que valem para o NSG da Azure, e com uma
# terceira que aqui e o ponto inteiro desta superficie:
#
# 1. **A regra e uma politica, nao um dado.** Nao existe "regra aleatoria": o que existe e uma
#    postura. Sortear permitir/negar faria a existencia do achado depender do seed.
# 2. **Os casos precisam existir lado a lado.** Um estado so exposto daria ``NON_COMPLIANT``
#    para todas as regras de rede sem provar que o consumidor distingue exposicao de
#    restricao -- o mesmo cuidado que a postura do NSG documenta.
# 3. **O estado precisa responder as regras de Config que dependem delas.** Este e o Incremento
#    2: ``restricted-ssh``, ``restricted-common-ports`` e ``vpc-default-security-group-closed``
#    respondiam ``INSUFFICIENT_DATA`` no Config por nao terem regra para ler. Um estado com uma
#    postura so-exposta as deixaria igualmente sem informacao -- so trocaria "nenhum dado" por
#    "um dado so".
#
# A FORMA e posicional: ``(direcao, protocolo, from_port, to_port, origem_ipv4, descricao)``.
# Posicional e nao dicionario pelo mesmo motivo do NSG -- um dicionario nao diz ao verificador
# de tipos qual campo cada posicao alimenta.
#
# Cada tupla e uma regra de ALLOW. A AWS nao publica regra de negacao ("You can specify allow
# rules, but not deny rules",
# https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html): o bloqueio e a
# AUSENCIA da regra. Por isso nao ha ``decision`` aqui, ao contrario do NSG.
#
# Os dois CIDR tem origem declarada:
#
# * ``0.0.0.0/0`` -- "todos os enderecos IPv4", a origem que as tres regras gerenciadas de rede
#   nomeiam como a exposicao (``0.0.0.0/0`` e ``::/0`` aparecem literalmente nas tres paginas);
# * ``203.0.113.0/24`` -- o PRIMEIRO exemplo de faixa IPv4 da propria documentacao da AWS
#   ("A range of IPv4 addresses, in CIDR block notation. For example, ``203.0.113.0/24``",
#   https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html). E um prefixo
#   de documentacao (RFC 5737), que por desenho nao colide com host nenhum.
AWS_SG_RULES = {
    # Sem ingress E sem egress: a postura que a regra ``vpc-default-security-group-closed``
    # trata como COMPLIANT. O guia diz que um SG recem-criado nasce com UMA regra de egress
    # que libera tudo, entao este perfil e o estado DEPOIS de remover essa regra -- que e
    # exatamente a remediacao que a regra gerenciada pede.
    "fechado": (),
    # SSH liberado para qualquer origem: ``restricted-ssh`` le e diz NON_COMPLIANT.
    "ssh-aberto": (
        (DIRECTION_INGRESS, "tcp", 22, 22, "0.0.0.0/0", "AllowSshFromAnywhere"),
    ),
    # SSH liberado so de uma faixa restrita, e HTTPS publico. ``restricted-ssh`` le a origem
    # e ve que ela NAO e ``0.0.0.0/0``: COMPLIANT. E 443 nao esta entre as portas bloqueadas
    # padrao de ``restricted-common-ports``, entao essa regra tambem diz COMPLIANT.
    "restrito": (
        (DIRECTION_INGRESS, "tcp", 22, 22, "203.0.113.0/24", "AllowSshFromDocsRange"),
        (DIRECTION_INGRESS, "tcp", 443, 443, "0.0.0.0/0", "AllowHttpsFromAnywhere"),
    ),
    # RDP liberado para qualquer origem. 3389 e uma das PORTA BLOQUEADAS PADRAO de
    # ``restricted-common-ports`` (blockedPort3), entao essa regra diz NON_COMPLIANT -- e
    # ``restricted-ssh`` continua COMPLIANT, porque nao ha regra de 22.
    "rdp-aberto": (
        (DIRECTION_INGRESS, "tcp", 3389, 3389, "0.0.0.0/0", "AllowRdpFromAnywhere"),
    ),
}

#: A regra de egress que a AWS coloca em TODO grupo recem-criado, na forma exata que a amostra
#: oficial da acao publica: ``ipProtocol`` ``-1``, ``cidrIp`` ``0.0.0.0/0``, e NENHUM
#: ``fromPort``/``toPort``. As portas sao ``None`` aqui porque a documentacao diz que nao se
#: aplicam nesse caso -- zero seria um valor que a API nao devolve.
AWS_SG_DEFAULT_EGRESS = (DIRECTION_EGRESS, "-1", None, None, "0.0.0.0/0", "AllowAllOutbound")

#: Os perfis que NAO tem regra nenhuma. Um SG so chega a lista vazia quando a regra de egress
#: padrao foi removida de proposito.
AWS_SG_CLOSED_PROFILE = "fechado"

#: Os perfis aplicados, por posicao, aos grupos de uma conta. A posicao 0 de cada conta e o
#: grupo PADRAO da VPC (ver ``_aws_security_groups``); as demais quatro percorrem a rotacao da
#: conta, escolhida pela MESMA paridade que :data:`AWS_SG_DEFAULT_PROFILE_BY_ACCOUNT`.
#:
#: Sao duas rotacoes, e nao uma so, por um motivo que a auditoria mediu: com cinco grupos por
#: conta e uma rotacao unica de quatro perfis, TODA conta recebe um grupo exposto, e a regra
#: ``restricted-ssh`` -- que e COMPLIANT so quando *nenhum* grupo do escopo expoe a porta -- fica
#: NON_COMPLIANT em todos os escopos. Isso nao ensinaria nada: um consumidor com a porta
#: invertida, ou um check que ignorasse o CIDR de origem, receberia exatamente a mesma resposta.
#:
#: A conta PAR recebe a rotacao restrita (e o grupo padrao fechado): e o escopo que a regra
#: gerenciada classifica como COMPLIANT. A conta IMPAR recebe a rotacao exposta. Assim os dois
#: lados das tres regras existem no mesmo estado, e a diferenca entre eles e a postura.
AWS_SG_ROTATIONS = (
    # Conta par: so origem restrita ou grupo fechado.
    ("restrito", AWS_SG_CLOSED_PROFILE, "restrito", AWS_SG_CLOSED_PROFILE),
    # Conta impar: SSH e RDP abertos para qualquer origem.
    ("ssh-aberto", "restrito", "rdp-aberto", AWS_SG_CLOSED_PROFILE),
)

#: O perfil do grupo PADRAO por paridade de indice de conta, alinhado com a rotacao acima. Grupo
#: fechado (COMPLIANT para ``vpc-default-security-group-closed``) na conta par, grupo com regra
#: (NON_COMPLIANT) na conta impar.
AWS_SG_DEFAULT_PROFILE_BY_ACCOUNT = (AWS_SG_CLOSED_PROFILE, "ssh-aberto")

# ── Postura das regras de firewall da GCP (Incremento 6) ─────────────────────
# A MESMA disciplina dos security groups acima: perfil DECLARADO, nunca sorteado, e os DOIS
# LADOS da mesma verificacao no mesmo estado. Nada aqui e escolha do gerador -- cada regra sai
# de uma fonte publicada:
#
# * as quatro regras pre-populadas (nome, direcao, prioridade 65534, origem e o par
#   protocolo:porta) vem da tabela "Pre-populated rules in the default network" do guia de VPC
#   firewall (https://docs.cloud.google.com/firewall/docs/firewalls) e da saida oficial de
#   ``gcloud compute firewall-rules list`` de um projeto recem-criado;
# * o valor ``all`` vem dessa MESMA saida, que mostra ``default-allow-internal`` com a coluna
#   ALLOW igual a ``all``;
# * a origem restrita ``203.0.113.0/24`` e um prefixo de documentacao (RFC 5737), o mesmo que a
#   postura dos security groups da AWS usa, para nao implicar host real.
#:
#: Uma tupla protocolo/porta de uma regra: ``(IPProtocol, ports)``. ``ports`` vazio e a forma de
#: "qualquer porta", que e o que a pagina declara ("If not specified, this rule applies to
#: connections through any port"); a faixa entra como a STRING que a GCP publica
#: (``"12345-12349"``), nunca como um par de numeros.
GcpFirewallEntrySpec = tuple[str, tuple[str, ...]]

#: Uma regra de firewall por tupla, na ordem POSICIONAL em que o construtor consome:
#: ``(name, direction, priority, source_ranges, allowed, denied, disabled, log_enabled, descricao)``.
#: Posicional e nao dicionario pelo mesmo motivo de ``NSG_SECURITY_RULES``: um ``dict`` nao diz ao
#: verificador de tipos QUAL campo cada posicao alimenta, entao um nome trocado so apareceria em
#: tempo de execucao.
#:
#: ``source_ranges`` sao as faixas de ENTRADA (``Firewall.sourceRanges``); a saida recebe o
#: destino, que a pagina separa em ``destinationRanges`` -- a mesma regra nao preenche os dois.
GcpFirewallRuleSpec = tuple[
    str,  # name
    str,  # direction: INGRESS | EGRESS
    int,  # priority
    tuple[str, ...],  # source_ranges
    tuple[GcpFirewallEntrySpec, ...],  # allowed
    tuple[GcpFirewallEntrySpec, ...],  # denied
    bool,  # disabled
    bool,  # log_enabled
    str,  # description
]

# As quatro regras com que a rede DEFAULT nasce, na ordem da tabela "Pre-populated rules in the
# default network". As tres ultimas trazem a origem ``0.0.0.0/0`` da tabela; a primeira traz
# ``10.128.0.0/9``.
#
# ``default-allow-internal`` recebe o valor ``all`` e nao os tres pares protocolo:porta que a
# tabela escreve: a saida oficial de ``gcloud compute firewall-rules list`` mostra a coluna ALLOW
# dessa regra como ``all``, e o CLI so colapsa assim o que a API guarda como uma unica tupla. A
# divergencia entre a tabela e a saida esta registrada em 'unverified' da spec -- nenhuma das
# duas fontes foi descartada, e a do CLI e a que le a API.
GCP_FIREWALL_PREPOPULATED: tuple[GcpFirewallRuleSpec, ...] = (
    (
        "default-allow-internal",
        "INGRESS",
        65534,
        ("10.128.0.0/9",),
        (("all", ()),),
        (),
        False,
        False,
        "Permits incoming connections to VM instances from other instances within the same VPC network.",
    ),
    (
        "default-allow-ssh",
        "INGRESS",
        65534,
        ("0.0.0.0/0",),
        (("tcp", ("22",)),),
        (),
        False,
        False,
        "Lets you connect to instances with tools such as ssh, scp, or sftp.",
    ),
    (
        "default-allow-rdp",
        "INGRESS",
        65534,
        ("0.0.0.0/0",),
        (("tcp", ("3389",)),),
        (),
        False,
        False,
        "Lets you connect to instances using the Microsoft Remote Desktop Protocol (RDP).",
    ),
    (
        "default-allow-icmp",
        "INGRESS",
        65534,
        ("0.0.0.0/0",),
        (("icmp", ()),),
        (),
        False,
        False,
        "Lets you use tools such as ping.",
    ),
)

# O perfil EXPOSTO: as regras de um projeto cuja postura o consumidor de seguranca classifica como
# exposicao. Cada linha existe para exercitar um ramo DISTINTO da verificacao.
GCP_FIREWALL_EXPOSED: tuple[GcpFirewallRuleSpec, ...] = (
    # ``all`` sem porta: a regra que libera TODO o trafego de 0.0.0.0/0. E o ramo do protocolo
    # que vale todos.
    (
        "allow-all-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("all", ()),),
        (),
        False,
        True,
        "allow-all-from-anywhere",
    ),
    # Protocolo tcp SEM portas: a pagina diz que a regra passa a valer "through any port", e o
    # consumidor le a ausencia de portas como trafego irrestrito. E o ramo das portas.
    (
        "allow-tcp-any-port-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("tcp", ()),),
        (),
        False,
        True,
        "allow-tcp-any-port-from-anywhere",
    ),
    # Protocolo udp SEM portas: o consumidor filtra por ``("tcp", "udp", "all")``, entao udp e um
    # ramo do filtro e tambem um caminho para o achado de trafego irrestrito. Sem esta regra o
    # vocabulario do consumidor teria um termo sem fixture.
    (
        "allow-udp-any-port-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("udp", ()),),
        (),
        False,
        True,
        "allow-udp-any-port-from-anywhere",
    ),
    # 5432 e uma das portas que o consumidor classifica como CRITICAL.
    (
        "allow-postgres-from-anywhere",
        "INGRESS",
        900,
        ("0.0.0.0/0",),
        (("tcp", ("5432",)),),
        (),
        False,
        True,
        "allow-postgres-from-anywhere",
    ),
    # 6379 esta na lista de portas do consumidor mas FORA do subconjunto que ele classifica como
    # CRITICAL: e o ramo que produz severidade menor, e sem ele o estado so ensinaria o critico.
    (
        "allow-redis-from-anywhere",
        "INGRESS",
        900,
        ("0.0.0.0/0",),
        (("tcp", ("6379",)),),
        (),
        False,
        True,
        "allow-redis-from-anywhere",
    ),
    # A MESMA exposicao do SSH, mas DESABILITADA: a pagina diz que uma regra desabilitada nao e
    # aplicada. E o ramo do ``disabled``.
    (
        "allow-ssh-from-anywhere-disabled",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("tcp", ("22",)),),
        (),
        True,
        True,
        "allow-ssh-from-anywhere-disabled",
    ),
    # EGRESS com origem 0.0.0.0/0: tem a origem aberta, mas a direcao impede a avaliacao. E o
    # ramo da direcao.
    (
        "egress-allow-all",
        "EGRESS",
        1000,
        ("0.0.0.0/0",),
        (("all", ()),),
        (),
        False,
        True,
        "egress-allow-all",
    ),
    # Uma regra que so NEGA: a GCP tem ``denied[]`` e o estado nao pode nao exercita-lo. Sem
    # ``allowed[]`` nao ha permissao a avaliar.
    (
        "deny-all-ingress",
        "INGRESS",
        65535,
        ("0.0.0.0/0",),
        (),
        (("all", ()),),
        False,
        True,
        "deny-all-ingress",
    ),
)

# O perfil RESTRITO: as MESMAS formas de regra com origens que NAO sao 0.0.0.0/0, mais a
# exposicao que nao casa com porta nenhuma. Um consumidor com a origem invertida, ou que
# tratasse 443 como porta critica, receberia dos dois perfis a mesma resposta.
GCP_FIREWALL_RESTRICTED: tuple[GcpFirewallRuleSpec, ...] = (
    # SSH liberado so da faixa de documentacao: a origem NAO e 0.0.0.0/0.
    (
        "allow-ssh-from-docs-range",
        "INGRESS",
        900,
        ("203.0.113.0/24",),
        (("tcp", ("22",)),),
        (),
        False,
        True,
        "allow-ssh-from-docs-range",
    ),
    # Mesma forma, outro par protocolo:porta, mesma origem restrita -- exercita que a checagem e
    # do PAR e nao so do protocolo.
    (
        "allow-postgres-from-office-range",
        "INGRESS",
        900,
        ("203.0.113.0/24",),
        (("tcp", ("5432",)),),
        (),
        False,
        True,
        "allow-postgres-from-office-range",
    ),
    # O mesmo udp do perfil exposto, com a origem restrita: prova que o silencio vem da origem e nao
    # do protocolo.
    (
        "allow-dns-from-docs-range",
        "INGRESS",
        900,
        ("203.0.113.0/24",),
        (("udp", ("53",)),),
        (),
        False,
        True,
        "allow-dns-from-docs-range",
    ),
    # Origem aberta com uma porta que nao e critica: o consumidor nao tem o que reportar.
    (
        "allow-https-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("tcp", ("443",)),),
        (),
        False,
        True,
        "allow-https-from-anywhere",
    ),
    # Origem aberta com protocolo fora do vocabulario que o consumidor filtra: e o ramo do filtro
    # de protocolo.
    (
        "allow-icmp-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("icmp", ()),),
        (),
        False,
        True,
        "allow-icmp-from-anywhere",
    ),
    # Origem aberta com portas que NAO contem nenhuma porta critica: a mesma exposicao de origem
    # sem achado. E o que separa "origem aberta" de "porta em risco".
    (
        "allow-web-from-anywhere",
        "INGRESS",
        1000,
        ("0.0.0.0/0",),
        (("tcp", ("80", "8080")),),
        (),
        False,
        True,
        "allow-web-from-anywhere",
    ),
)

#: As regras de cada projeto, por paridade do indice do projeto na lista ordenada. Sao DUAS
#: listas e nao um perfil so, pelo mesmo motivo medido nos security groups da AWS: com um perfil
#: unico TODOS os projetos ficariam expostos e o veredito do consumidor seria unico no estado
#: inteiro -- um consumidor com a origem ou a porta invertida receberia a mesma resposta. Com
#: dois, um projeto responde COMPLIANT e outro NON_COMPLIANT no mesmo estado.
#:
#: As regras PRE-POPULADAS entram nos DOIS lados, e nao e uma assimetria: elas nao sao decisao de
#: postura, sao o ESTADO DE UM PROJETO RECEM-CRIADO que a tabela da documentacao descreve. E
#: delas que vem o achado de SSH/RDP no perfil restrito tambem -- que e o comportamento real de um
#: projeto na rede default.
GCP_FIREWALL_RULES_BY_PROJECT = (
    GCP_FIREWALL_PREPOPULATED + GCP_FIREWALL_RESTRICTED,
    GCP_FIREWALL_PREPOPULATED + GCP_FIREWALL_EXPOSED,
)

#: O indice, entre as redes do projeto ordenadas por ``segment_id``, da rede que recebe as regras
#: PRE-POPULADAS. A tabela da documentacao diz que elas existem na rede ``default``; o modelo nao
#: tem uma rede ``default`` -- ele da uma rede por (projeto, regiao), como se fosse a VPC da AWS.
#: A primeira rede do projeto e portanto a que as recebe, e essa escolha esta declarada como
#: derivacao na proveniencia do renderer.
GCP_FIREWALL_DEFAULT_NETWORK_SLOT = 0

# ── Postura dos buckets S3 (Incremento 3) ────────────────────────────────────
# A MESMA disciplina dos security groups acima: perfil DECLARADO, nunca sorteado, e os
# dois lados de cada regra no mesmo estado. Os grants vem da tabela de canned ACLs da AWS
# (``acl-overview.md``, "Amazon S3 supports a set of predefined grants, known as canned
# ACLs"), que e onde a propria AWS diz quem recebe o que -- nada aqui e escolha do
# gerador.
#
#: Um grant de canned ACL: ``(permission, grantee type, group URI or None)``. O URI e None
#: quando o grant vai para o usuario canonico do proprio bucket.
S3GrantSpec = tuple[str, str, "str | None"]
#: Um statement de TEMPLATE de policy: ``(sid, effect, actions, principals, resources)``.
S3StatementSpec = tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]
#: Um TEMPLATE de bucket policy: ``(id, version, statements)``. ``None`` no perfil significa
#: "o bucket nao tem bucket policy", o estado que a API sinaliza com ``NoSuchBucketPolicy``.
S3PolicySpec = tuple[str, str, tuple[S3StatementSpec, ...]]
#: Os quatro booleanos do Block Public Access, na ordem da resposta da API:
#: ``(BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy, RestrictPublicBuckets)``.
S3PabSpec = tuple[bool, bool, bool, bool]
#: Um PERFIL de postura: ACL armazenada, template de bucket policy, configuracao de block.
S3ProfileSpec = tuple[tuple[S3GrantSpec, ...], "S3PolicySpec | None", S3PabSpec]

# Cada grant e ``(permission, grantee_type, uri)``: o ``uri`` e None quando o grant vai
# para o usuario canonico do proprio bucket, e preenchido quando vai para um grupo
# predefinido.
S3_GRANT_OWNER_FULL_CONTROL = ("FULL_CONTROL", "CanonicalUser", None)
S3_GRANT_ALL_USERS_READ = ("READ", "Group", S3_ALL_USERS_URI)
S3_GRANT_ALL_USERS_WRITE = ("WRITE", "Group", S3_ALL_USERS_URI)
S3_GRANT_AUTHENTICATED_USERS_READ = ("READ", "Group", S3_AUTHENTICATED_USERS_URI)
S3_GRANT_LOG_DELIVERY_WRITE = ("WRITE", "Group", S3_LOG_DELIVERY_URI)
S3_GRANT_LOG_DELIVERY_READ_ACP = ("READ_ACP", "Group", S3_LOG_DELIVERY_URI)

# Os quatro booleanos do PublicAccessBlock, na ordem da resposta da API.
S3_PAB_ALL_ON = (True, True, True, True)
S3_PAB_ALL_OFF = (False, False, False, False)
#: "block public bucket policies" ligado, ACLs livres de block e ``IgnorePublicAcls``
#: ligado. E o perfil que exercita a diferenca entre a ACL armazenada e a EFETIVA que a
#: pagina de Block Public Access documenta.
S3_PAB_POLICY_BLOCKED_ACL_IGNORED = (False, True, True, False)
#: So o ``BlockPublicPolicy`` ligado, com a policy JÁ ARMAZENADA e publica. E o perfil que
#: exercita o curto-circuito da regra: a primeira metade da clausula publicada e um "ou" cujo
#: primeiro termo e o block, entao com o block ligado a metade passa SEM que a policy seja
#: consultada -- mesmo sendo publica. Um renderizador que so perguntasse "a policy e publica?"
#: reprovaria este bucket onde a AWS aprovada.
S3_PAB_POLICY_BLOCKED_ONLY = (False, False, True, False)

# O documento de bucket policy: ``(policy_id, version, statements)`` e cada statement e
# ``(sid, effect, actions, principals, resources)``. ``None`` no ``policy_id`` de um
# perfil significa "o bucket nao tem bucket policy", que e o estado que a API sinaliza
# com ``NoSuchBucketPolicy``.
_S3_PRIVATE_ACTIONS = ("s3:GetObject", "s3:ListBucket")
_S3_PRIVATE_RESOURCES = ("arn:aws:s3:::BUCKET/*", "arn:aws:s3:::BUCKET")

S3_POLICY_PRIVATE = (
    "svc-leitura",
    "2012-10-17",
    (
        (
            "SomenteLeituraDoServico",
            "Allow",
            _S3_PRIVATE_ACTIONS,
            ("arn:aws:iam::956104725713:root",),
            _S3_PRIVATE_RESOURCES,
        ),
    ),
)

S3_POLICY_PUBLIC_READ = (
    "leitura-publica",
    "2012-10-17",
    (("PermitirGetParaTodos", "Allow", ("s3:GetObject",), ("*",), ("arn:aws:s3:::BUCKET/*",)),),
)

S3_POLICY_PUBLIC_WRITE = (
    "escrita-publica",
    "2012-10-17",
    (("PermitirPutParaTodos", "Allow", ("s3:PutObject",), ("*",), ("arn:aws:s3:::BUCKET/*",)),),
)

#: O perfil -> ``(grants da ACL armazenada, bucket policy, public access block)``.
#: Os grants sao as canned ACLs que a AWS documenta: ``private`` da ``FULL_CONTROL``
#: so ao owner; ``public-read`` acrescenta ``READ`` ao grupo AllUsers; ``public-read-write``
#: acrescenta ``READ`` e ``WRITE``; ``authenticated-read`` da ``READ`` ao grupo
#: AuthenticatedUsers; ``log-delivery-write`` da ``WRITE`` e ``READ_ACP`` ao LogDelivery.
#: O grupo LogDelivery NAO e um dos dois grupos que a AWS chama de public, entao o bucket
#: que o recebe nao fica publico -- e a ACL ``log-delivery-write`` e a propria evidencia
#: de que essa leitura e a certa.
S3_BUCKET_PROFILES: dict[str, S3ProfileSpec] = {
    "privado-bloqueado": ((S3_GRANT_OWNER_FULL_CONTROL,), None, S3_PAB_ALL_ON),
    "privado-aberto": ((S3_GRANT_OWNER_FULL_CONTROL,), None, S3_PAB_ALL_OFF),
    "politica-privada": ((S3_GRANT_OWNER_FULL_CONTROL,), S3_POLICY_PRIVATE, S3_PAB_ALL_OFF),
    "log-delivery": ((S3_GRANT_OWNER_FULL_CONTROL, S3_GRANT_LOG_DELIVERY_WRITE, S3_GRANT_LOG_DELIVERY_READ_ACP), None, S3_PAB_ALL_OFF),
    "public-read-ignorado": ((S3_GRANT_OWNER_FULL_CONTROL, S3_GRANT_ALL_USERS_READ), None, S3_PAB_POLICY_BLOCKED_ACL_IGNORED),
    "public-read": ((S3_GRANT_OWNER_FULL_CONTROL, S3_GRANT_ALL_USERS_READ), None, S3_PAB_ALL_OFF),
    "public-read-write": ((S3_GRANT_OWNER_FULL_CONTROL, S3_GRANT_ALL_USERS_READ, S3_GRANT_ALL_USERS_WRITE), None, S3_PAB_ALL_OFF),
    "authenticated-read": ((S3_GRANT_OWNER_FULL_CONTROL, S3_GRANT_AUTHENTICATED_USERS_READ), None, S3_PAB_ALL_OFF),
    "politica-publica-leitura": ((S3_GRANT_OWNER_FULL_CONTROL,), S3_POLICY_PUBLIC_READ, S3_PAB_ALL_OFF),
    "politica-publica-escrita": ((S3_GRANT_OWNER_FULL_CONTROL,), S3_POLICY_PUBLIC_WRITE, S3_PAB_ALL_OFF),
    "politica-publica-bloqueada": ((S3_GRANT_OWNER_FULL_CONTROL,), S3_POLICY_PUBLIC_READ, S3_PAB_POLICY_BLOCKED_ONLY),
}

#: Os perfis aplicados, por posicao, aos buckets de cada conta. A conta PAR recebe a
#: rotacao restrita e a conta IMPAR a exposta -- a mesma divisao de
#: :data:`AWS_SG_ROTATIONS`, e pelo mesmo motivo: com uma rotacao so, os dois lados das
#: tres regras nao existiriam no mesmo estado.
#:
#: Dois criterios governam a ordem, e os dois vem da mesma constatacao: o veredito de uma
#: regra e por ESCOPO, e basta UM bucket em violacao para o escopo inteiro virar
#: NON_COMPLIANT. Logo a restrita nao pode conter nenhum perfil que reprove a regra de nivel,
#: e a exposta precisa conter os dois perfis que existem so para provar discriminacoes --
#: ``public-read-ignorado`` (ACL armazenada publica com ``IgnorePublicAcls`` ligado: a
#: resposta do ``GetBucketAcl`` nao a publica) e ``politica-publica-bloqueada`` (policy publica
#: com ``BlockPublicPolicy`` ligado: o curto-circuito da regra, que e o erro mais provavel ao
#: implementa-la).
#:
#: Os dois estao nos cinco primeiros slots de proposito: o perfil ``small`` da o estate cinco
#: buckets por conta, e um slot so de ordem deixaria um deles -- e a discriminacao que ele
#: existe para provar -- fora de qualquer estado que a suite construa.
#:
#: A exposta reprova as DUAS regras ``*-prohibited`` e a regra de nivel; a restrita aprova as
#: tres. E assim que os dois lados das tres existem no mesmo estado.
S3_BUCKET_ROTATIONS = (
    (
        "privado-bloqueado",
        "privado-aberto",
        "politica-privada",
        "public-read-ignorado",
        "log-delivery",
    ),
    (
        "public-read",
        "public-read-write",
        "authenticated-read",
        "politica-publica-escrita",
        "politica-publica-bloqueada",
        "politica-publica-leitura",
    ),
)

#: O ARN de um bucket aparece dentro dos TEMPLATES de policy acima, como
#: ``arn:aws:s3:::BUCKET/*`` -- sem regiao e sem conta, porque o nome do bucket e global. Nao ha
#: um template separado: o unico lugar onde o ARN aparece num bucket policy e o ``Resource``,
#: e um prefixo solto seria uma segunda fonte da mesma verdade.

# ── Postura de IDENTIDADE (Incremento 4) ─────────────────────────────────────
# A MESMA disciplina dos security groups e dos buckets: perfil DECLARADO, nunca sorteado,
# e os DOIS lados de cada uma das tres regras no mesmo estado. Os valores sao os que a AWS
# publica -- nenhum deles e escolha do gerador.
#
#: A politica de senha da conta -> os oito membros que ``iam:GetAccountPasswordPolicy``
#: publica. A ordem do Documento e a ordem da resposta da API.
#: ``(min, simbolos, numeros, maiusculas, minusculas, pode_mudar, expira_duras, max_dias)``
#: com ``max_dias`` em ``None`` para a senha que nunca expira.
IamPolicySpec = tuple[int, bool, bool, bool, bool, bool, bool, "int | None"]

#: Os perfis de senha. ``forte`` e ``fraca`` sao os que a rotacao usa, porque sao os extremos
#: de um intervalo real de politica -- e sao eles que produzem os dois lados do veredito.
#:
#: ``media`` NAO e usado pela rotacao e existe aqui de proposito: ele cumpre comprimento,
#: simbolos, numeros e maiusculas, e so nao exige MINUSCULA. Com so ``forte`` e ``fraca`` no
#: estate, um renderizador que lesse apenas o comprimento da senha reprovaria ``fraca`` (que
#: tem 8) e aprovaria ``forte`` (que tem 14) -- passaria por acidente. Como o estate tem
#: tres contas e cada regra precisa reprovar numa conta DIFERENTE, nao ha vaga para um
#: terceiro perfil no estado, entao ``media`` e exercitado pelo teste de fidelidade, que o
#: monta como entrada. Um valor declarado e nunca lido seria lixo; este e lido, e por quem
#: pode provar que a regra le o requisito e nao so o numero.
AWS_IAM_PASSWORD_POLICIES: dict[str, IamPolicySpec] = {
    # A politica que a propria AWS recomenda: 14 caracteres, os quatro requisitos,
    # troca permitida, expiracao em 90 dias e 24 senhas de historico.
    "forte": (14, True, True, True, True, True, True, 90),
    # Cumpre comprimento, simbolos, numeros e maiusculas -- e nao exige minuscula.
    "media": (14, True, True, True, False, True, True, 90),
    # A politica que a AWS aplica quando a conta nao tem nenhuma: 8 caracteres, sem
    # requisito nenhum, senha que nunca expira. E o perfil que reprova a regra por cinco
    # motivos ao mesmo tempo.
    "fraca": (8, False, False, False, False, True, False, None),
}

#: O perfil de CHAVES de um usuario: quantas chaves, e o estado de cada uma. As duas datas
#: sao EM DIAS a partir do ``sim_now`` do estate, e nao datas soltas, para que a regra
#: ``access-keys-rotated`` seja um teste de idade de verdade e nao uma comparacao de string.
#: ``(status, idade_em_dias, ultimo_uso_em_dias)``, e ``None`` no ultimo uso significa "nunca
#: usada" -- estado legitimo, e NAO a mesma coisa de uma chave recem-criada.
#:
#: Os perfis existem pelo mesmo motivo de ``public-read-ignorado`` no Incremento 3:
#: ``inativa-antiga`` tem uma chave de 410 dias que e INATIVA ao lado de uma de 30 dias, e a
#: regra so reprova chave ATIVA. Um renderizador que reprovasse por idade sem olhar o
#: ``status`` reprovaria as DUAS contas que tem esse perfil, e um que so olhasse o ``status``
#: aprovaria a conta da chave de 410 dias. So a comparacao dos dois separa os erros.
AWS_IAM_KEY_PROFILES: dict[str, tuple[tuple[str, int, int | None], ...]] = {
    # Duas chaves ativas dentro da janela de rotacao, uma delas usada recentemente.
    "rotacionadas": (("Active", 12, 3), ("Active", 40, 21)),
    # A unica fonte de NON_COMPLIANT de ``access-keys-rotated``: uma chave ativa de 410 dias,
    # bem além da janela de 90, e usada 22 dias atras -- ou seja, uma chave que ainda
    # FUNCIONA. E o caso que a regra existe para pegar.
    "antigas": (("Active", 410, 388),),
    # Mesma idade, status oposto, mais uma chave ativa dentro da janela.
    "inativa-antiga": (("Inactive", 410, None), ("Active", 30, 9)),
    # Ativa, dentro da janela, e NUNCA usada. Separa "idade" de "uso": prova que o
    # ``None`` de ``last_used_date`` e tratado como ausencia de uso e nao como data invalida.
    "ativa-jovem-nunca-usada": (("Active", 45, None),),
}

#: Os parametros com que as REGRAS GERENCIADAS sao executadas. Cada regra gerenciada le um
#: parametro por requisito, e ``-1`` significa "nao avaliar este requisito"; sem parametro a
#: AWS usa o padrao documentado. Declarar o parametro AQUI, e nao dentro do renderer, e o
#: que torna o veredito reproduzivel -- um teste de fidelidade que reconta o veredito com
#: outros numeros reconta OUTRA regra, e falha.
AWS_IAM_RULE_PARAMETERS: dict[str, dict[str, int]] = {
    # ``iam-password-policy`` avalia a minima exigida e cada um dos quatro requisitos.
    "iam-password-policy": {
        "minimumPasswordLength": 14,
        "requireSymbols": 1,
        "requireNumbers": 1,
        "requireUppercaseCharacters": 1,
        "requireLowercaseCharacters": 1,
    },
    # ``access-keys-rotated`` avalia a idade MAXIMA de uma chave ATIVA, em dias.
    "access-keys-rotated": {"maxAccessKeysAge": 90},
}

#: A rotacao por indice de conta: ``(root, senha, chaves-do-usuario-de-servico)``.
#:
#: O estate tem EXATAMENTE tres contas AWS em qualquer perfil
#: (``_SCOPES_PER_PROVIDER = 3``), e a rotacao tem tres entradas porque cada uma das tres
#: regras precisa REPROVAR em uma conta e cada reprovacao precisa cair numa conta DIFERENTE.
#: E o que torna os tres vereditos distinguiveis: se duas regras reprovassem na mesma conta,
#: um renderizador que as trocasse de lugar receberia a mesma resposta e passaria.
#:
#:    conta 0 -> so a SENHA reprova
#:    conta 1 -> so as CHAVES reprovam
#:    conta 2 -> so o ROOT reprova
#:
#: Cada eixo aparece tambem COMPLIANT nas outras duas contas, entao os dois lados das tres
#: regras existem no mesmo estado -- a mesma disciplina de :data:`AWS_SG_ROTATIONS` e
#: :data:`S3_BUCKET_ROTATIONS`.
AWS_IAM_ROTATIONS: tuple[tuple[str, str, str], ...] = (
    ("mfa-ativo", "fraca", "rotacionadas"),
    ("mfa-ativo", "forte", "antigas"),
    ("mfa-inativo", "forte", "rotacionadas"),
)

#: O MFA da conta ROOT por valor do eixo. A conta root e o que a regra
#: ``root-account-mfa-enabled`` le, e por isso tem vocabulario proprio: ela NAO concorda
#: com o MFA do usuario de servico em nenhuma das tres contas, que e o que impede o erro de
#: trocar "o root tem MFA" por "um usuario tem MFA".
AWS_IAM_ROOT_MFA_ACTIVE = "mfa-ativo"
AWS_IAM_ROOT_MFA_INACTIVE = "mfa-inativo"

#: O nome do usuario de SERVICO, que e o unico membro da conta cujas chaves mudam com a
#: rotacao. Os outros usuarios da conta sao fixos (ver :data:`AWS_IAM_FIXED_USERS`) e por
#: isso nunca alteram um veredito.
AWS_IAM_SERVICE_USER_NAME = "contoso-servico"

#: O usuario de servico e de API: nao tem senha e nao tem console. E o unico membro da conta
#: que pode reprovar a regra de chaves, e ele existe justamente por NAO ter tela -- a regra
#: ``access-keys-rotated`` e sobre credencial de API, e nao sobre console.
AWS_IAM_SERVICE_USER_HAS_PASSWORD = False

#: Os OUTROS usuarios, presentes em TODAS as contas e iguais em todas elas. Eles existem
#: por tres motivos, e nenhum deles e enfeite:
#:
#: 1. ``contoso-plataforma`` -- console com MFA e chaves dentro da janela: o membro que a
#:    regra de chaves APROVA mesmo na conta que ela reprova, sem o qual ``users`` nunca
#:    teria quem aprova;
#: 2. ``contoso-integracao`` -- console com MFA e o perfil ``inativa-antiga``: obriga a
#:    regra a olhar o ``status`` da chave, e nao so a idade;
#: 3. ``contoso-batch`` -- so de API: obriga o consumidor a tratar um usuario sem senha
#:    como um usuario que NAO entra no achado "console sem MFA".
#:
#: Os tres tem ``mfa_active`` compativel com "tem console", porque uma conta em que NINGUEM
#: no console tem MFA e um estado real -- e e um estado que o estate precisa ter, senao o
#: cruzamento que a ferramenta de postura faz (senha E sem MFA) nao teria o que achar e o
#: ``mfa_active`` da coluna nao teria o valor que importa. Quem garante isso e
#: :data:`AWS_IAM_ROOT_MFA_INACTIVE_ACCOUNT_USERS`, consultado pelo eixo do root.
AWS_IAM_FIXED_USERS: tuple[tuple[str, str, bool, bool, str], ...] = (
    # (user_name, path, tem_senha, mfa_ativo, perfil de chaves)
    ("contoso-plataforma", "/", True, True, "rotacionadas"),
    ("contoso-integracao", "/", True, True, "inativa-antiga"),
    ("contoso-batch", "/servico/", False, True, "ativa-jovem-nunca-usada"),
)

#: Os usuarios que so existem na conta cujo ROOT esta sem MFA.
#:
#: E o unico lugar do estado em que um humano de console fica sem MFA, e ele existe por um
#: motivo que nao e enfeite: sem ele, a coluna ``mfa_active`` valeria ``TRUE`` em todas as
#: linhas de usuario de todas as contas, e o cruzamento que o FinOps faz -- console com
#: senha e sem MFA -- nao encontraria NADA. Uma superficie que existe para achar uma coisa e
#: um estado em que a coisa nao existe nao prova nada sobre ela mesma.
#:
#: Coura o perfil do eixo do root, e nao uma data: a conta cujo root nao tem MFA e a mesma
#: conta em que ninguem ligou o MFA, entao e a MESMA escolha de operador aparecendo nos dois
#: lugares. E por isso que o perfil ``contoso-operacoes`` aparece aqui e nao na rotacao.
AWS_IAM_ROOT_MFA_INACTIVE_ACCOUNT_USERS: tuple[tuple[str, str, bool, bool, str], ...] = (
    # (user_name, path, tem_senha, mfa_ativo, perfil de chaves)
    ("contoso-operacoes", "/", True, False, "rotacionadas"),
)

# -- Incremento 4.3: auditoria e guardrails ------------------------------------
# As DUAS regras de conta (``cloudtrail-enabled`` e ``securityhub-enabled``) e a regra por VPC
# (``vpc-flow-logs-enabled``) eram as ultimas do catalogo do Config a responder
# INSUFFICIENT_DATA em TODO escopo. As tresorcaes de modelo estao nomeadas uma a uma no
# renderer; aqui mora so a POSTURA que as fecha.
#
# O vocabulario e separado por eixo pelo mesmo motivo de :data:`AWS_IAM_ROTATIONS`: se as duas
# regras de conta reprovassem na mesma conta, um renderizador que as trocasse de lugar receberia
# a mesma resposta e passaria. Aqui cada eixo reprova numa conta DIFERENTE.

#: O vocabulario do eixo CloudTrail. ``ausente`` nao e um estado degenerado: e a conta que nao
#: tem trilha nenhuma, que e exatamente o estado que ``cloudtrail-enabled`` reprova ("The rule is
#: NON_COMPLIANT if a trail is not enabled").
AWS_AUDIT_CLOUDTRAIL_ENABLED = "cloudtrail-ativa"
AWS_AUDIT_CLOUDTRAIL_ABSENT = "cloudtrail-ausente"

#: O vocabulario do eixo Security Hub, pelo mesmo motivo -- e pelos mesmos dois estados.
AWS_AUDIT_SECURITYHUB_ENABLED = "securityhub-ativo"
AWS_AUDIT_SECURITYHUB_ABSENT = "securityhub-ausente"

#: A rotacao de auditoria por indice de conta: ``(cloudtrail, securityhub)``.
#:
#: O estate tem EXATAMENTE tres contas AWS em qualquer perfil
#: (``_SCOPES_PER_PROVIDER = 3``), e a rotacao tem tres entradas pelo mesmo motivo da de IAM.
#:
#:    conta 0 -> CloudTrail ativo E Security Hub ativo (as duas regras aprovam)
#:    conta 1 -> CloudTrail ativo E Security Hub AUSENTE (so o Hub reprova)
#:    conta 2 -> CloudTrail AUSENTE E Security Hub ativo (so o CloudTrail reprova)
#:
#: Cada eixo aparece COMPLIANT em duas contas e NON_COMPLIANT numa, entao os dois lados das
#: duas regras existem no mesmo estado -- e cada reprovacao cai numa conta diferente.
AWS_AUDIT_ROTATIONS: tuple[tuple[str, str], ...] = (
    (AWS_AUDIT_CLOUDTRAIL_ENABLED, AWS_AUDIT_SECURITYHUB_ENABLED),
    (AWS_AUDIT_CLOUDTRAIL_ENABLED, AWS_AUDIT_SECURITYHUB_ABSENT),
    (AWS_AUDIT_CLOUDTRAIL_ABSENT, AWS_AUDIT_SECURITYHUB_ENABLED),
)

#: As trilhas de cada perfil -> ``(sufixo-do-nome, multi-regiao, s3, cloudwatch-logs, sns)``.
#:
#: Os tres ultimos booleanos sao exatamente os tres parametros OPCIONAIS da regra
#: (``s3BucketName``, ``cloudWatchLogsLogGroupArn`` e ``snsTopicArn``). Eles ficam no perfil
#: porque a pagina da regra os publica, e e o que torna a reducao declarada inspecionavel: o
#: renderer nao passa NENHUM dos tres, e ainda assim o estado carrega o que eles filtrariam.
#:
#: A trilha ``regional`` vai so para o S3 porque e o destino minimo que o proprio servico exige
#: de qualquer trilha -- as tres bandeiras independentes descreveriam um estado que a AWS nao
#: produz.
AWS_CLOUDTRAIL_TRAILS: dict[str, tuple[tuple[str, bool, bool, bool, bool], ...]] = {
    AWS_AUDIT_CLOUDTRAIL_ENABLED: (
        ("organizacional", True, True, True, True),
        ("regional", False, True, False, False),
    ),
    AWS_AUDIT_CLOUDTRAIL_ABSENT: (),
}

#: A inscricao do Security Hub por perfil. O valor e o booleano da regra ("NON_COMPLIANT if AWS
#: Security Hub is not enabled"); o ARN da conta sai dele no builder, como os demais
#: identificadores desta tabela.
AWS_SECURITYHUB_ENABLED: dict[str, bool] = {
    AWS_AUDIT_SECURITYHUB_ENABLED: True,
    AWS_AUDIT_SECURITYHUB_ABSENT: False,
}

#: O vocabulario da regra POR VPC, por escopo (conta, regiao). Cada valor da tupla e o perfil das
#: VPCs desse escopo, na ordem em que os recursos ``vpc`` aparecem.
AWS_VPC_FLOW_LOG_ALL_LOGGED = "vpc-todas-com-log"
AWS_VPC_FLOW_LOG_NONE_LOGGED = "vpc-nenhuma-com-log"
AWS_VPC_FLOW_LOG_MIXED = "vpc-misturado"

#: A rotacao de flow log por escopo. Sao TRES perfis e nao dois porque o terceiro estado e o que
#: prova a GRANULARIDADE: o escopo misturado tem VPC com log ao lado de VPC sem log na MESMA
#: conta, entao a regra responde NON_COMPLIANT por causa de uma VPC especifica -- um renderizador
#: que lesse a conta em vez da VPC receberia a mesma resposta e passaria.
AWS_VPC_FLOW_LOG_ROTATIONS: tuple[str, ...] = (
    AWS_VPC_FLOW_LOG_ALL_LOGGED,
    AWS_VPC_FLOW_LOG_NONE_LOGGED,
    AWS_VPC_FLOW_LOG_MIXED,
)

#: Os perfis -> ``tem-flow-log por VPC do escopo``. O estate peca as VPCs por modulo, entao o
#: tamanho da tupla nao depende do perfil de estate.
AWS_VPC_FLOW_LOG_PROFILES: dict[str, tuple[bool, ...]] = {
    AWS_VPC_FLOW_LOG_ALL_LOGGED: (True, True, True, True, True),
    AWS_VPC_FLOW_LOG_NONE_LOGGED: (False, False, False, False, False),
    AWS_VPC_FLOW_LOG_MIXED: (True, False, True, False, True),
}

#: O ``TrafficType`` que a trilha coleta, no vocabulario da API (``describe_flow_logs``): o
#: parametro OPCIONAL ``trafficType`` da regra nao e passado, entao a regra reduz a condicao
#: incondicional da pagina ("flow logs are found and enabled"), sem filtro por tipo. Os valores
#: ficam no estado porque sao publicados -- e sao o que torna essa reducao inspecionavel.
AWS_VPC_FLOW_LOG_TRAFFIC_TYPES: tuple[str, ...] = ("ALL", "ACCEPT", "REJECT")

#: Os parametros OPCIONAIS que cada uma das tres regras publica, pelo NOME que a pagina usa.
#:
#: Aqui so os NOMES, nunca valores, e a ausencia de valor e o que significa a REDUCAO: o renderer
#: nao passa nenhum parametro, entao cada regra reduz a condicao que a propria pagina enuncia sem
#: filtro. Registrar os nomes torna essa reducao verificavel -- da para ler que ``s3BucketName``
#: existe, que o renderer nao o passa, e que por isso a regra nao filtra por bucket.
#:
#: ``securityhub-enabled`` tem lista vazia porque a pagina publica "Parameters: None": nao ha
#: nenhuma reducao a declarar, a condicao ja e incondicional.
#:
#: Fontes:
#: * ``cloudtrail-enabled`` -- https://docs.aws.amazon.com/config/latest/developerguide/cloudtrail-enabled.html
#: * ``securityhub-enabled`` -- https://docs.aws.amazon.com/config/latest/developerguide/securityhub-enabled.html
#: * ``vpc-flow-logs-enabled`` -- https://docs.aws.amazon.com/config/latest/developerguide/vpc-flow-logs-enabled.html
AWS_AUDIT_RULE_PARAMETERS: dict[str, tuple[str, ...]] = {
    "cloudtrail-enabled": ("cloudWatchLogsLogGroupArn", "s3BucketName", "snsTopicArn"),
    "securityhub-enabled": (),
    "vpc-flow-logs-enabled": ("trafficType",),
}

#: O bloco por REGIAO -> ``(BlockPublicAcls, IgnorePublicAcls, BlockPublicPolicy,
#: RestrictPublicBuckets)``, ou ``None`` quando a conta nao definiu um. O ``RegionPrefix``
#: NAO vem daqui: ele sai da REGIAO DO PROPRIO BUCKET, em ``_aws_regional_access_block`` --
#: um prefixo declarado aqui seria um literal, e um literal nao diz a qual regiao se aplica.
type S3RegionalAccessSpec = tuple[bool, bool, bool, bool]

#: A rotacao do bloco por REGIAO, por SLOT dentro do perfil de bucket.
#:
#: A sequencia alterna ``None`` (nao configurado) e dois perfis realmente distintos, e a
#: alternancia e o que importa: um bloco por regiao so diz algo quando convive com a ausencia
#: dele, do mesmo jeito que um bucket com ACL so diz algo quando existe um bucket sem ACL.
S3_REGIONAL_ACCESS_BLOCK_ROTATION: tuple[S3RegionalAccessSpec | None, ...] = (
    None,
    (True, False, True, True),
    None,
    (False, False, False, True),
)

# AWS services, same 6-tuple shape. These are the entries that become RESOURCES
# (each carries consumption, inventory, findings, metrics, IaC). Billing-only
# constructs stay out on purpose: AWS Marketplace and AWS Support line items
# (scenario A10) are no-resource FOCUS rows, and the gate asserts exactly ONE
# ``None``-resource billing line exists (FR-D5), so they cannot be a catalog
# entry here — they belong to the scenario emitter.
#
# ``data_transfer`` carries the cross-AZ SKU scenario A09 needs; ``eks_cluster``
# gives ``validate.quality.check_k8s_coherence`` an AWS cluster service to
# recognise (its ``cluster_services`` tuple).
AWS_SERVICES = (
    ("ec2_instance", "Amazon Elastic Compute Cloud", "Compute", "aws-ec2-m5-large", "Hours", Decimal("0.096000")),
    ("ebs_volume", "Amazon Elastic Block Store", "Storage", "aws-ebs-gp3", "GB-Month", Decimal("0.080000")),
    ("nat_gateway", "Amazon Virtual Private Cloud", "Networking", "aws-natgw-hour", "Hours", Decimal("0.045000")),
    ("rds_instance", "Amazon Relational Database Service", "Databases", "aws-rds-db-m5-lg", "Hours", Decimal("0.340000")),
    ("s3_bucket", "Amazon Simple Storage Service", "Storage", "aws-s3-standard", "GB-Month", Decimal("0.023000")),
    ("data_transfer", "Amazon Virtual Private Cloud", "Networking", "aws-dt-cross-az", "GB", Decimal("0.010000")),
    ("eks_cluster", "Amazon Elastic Kubernetes Service", "Compute", "aws-eks-node-m5lg", "Hours", Decimal("0.192000")),
    ("cloudwatch_logs", "Amazon CloudWatch", "Management", "aws-cw-logs-ingest", "GB", Decimal("0.500000")),
    # ── Added to close the FR-21 reverse gaps (design sec. 23) ──────────────────
    # These five are resource types FinOps AWS inventory already collects
    # (``resources.py (modulo do consumidor):35``) and the catalog never emitted, so the
    # endpoints that read them (LAMBDA, EIP, ALB, VPC, SG) returned nothing against
    # the synthetic estate.
    #
    # ``vpc`` and ``security_group`` carry a **zero** price on purpose: AWS charges
    # nothing for a VPC or a security group, and inventing a rate so the row looks
    # billable would be exactly the fabrication NFR-3 forbids. A zero price means "this
    # resource exists and is inventoried but is not billed", and the builder emits no
    # billing line for it — see ``estate_builder._build_consumption_and_billing``.
    ("lambda_function", "AWS Lambda", "Compute", "aws-lambda-gb-second", "GB-Seconds", Decimal("0.0000166667")),
    ("elastic_ip", "Amazon Virtual Private Cloud", "Networking", "aws-eip-hour", "Hours", Decimal("0.005000")),
    ("application_lb", "Elastic Load Balancing", "Networking", "aws-alb-hour", "Hours", Decimal("0.022500")),
    ("vpc", "Amazon Virtual Private Cloud", "Networking", "aws-vpc-unbilled", "Hours", Decimal("0.000000")),
    ("security_group", "Amazon Virtual Private Cloud", "Networking", "aws-sg-unbilled", "Hours", Decimal("0.000000")),
    # Added for the FR-21 reverse gaps (design sec. 23): two services
    # ``service_discovery.py (modulo do consumidor)`` monitors and no catalog entry modelled.
    ("dynamodb_table", "Amazon DynamoDB", "Databases", "aws-ddb-wcu", "Write-Capacity-Units", Decimal("0.0006500000")),
    ("ecs_cluster", "Amazon Elastic Container Service", "Compute", "aws-fargate-vcpu-hour", "Hours", Decimal("0.040480")),
)

# ── provider dispatch ────────────────────────────────────────────────────────
#
# The generator keys providers two ways and both matter:
#   * the OPERATIONAL key ("azure" | "gcp" | "aws") on ResourceIdentity,
#     BillingAccount and the scope descriptors;
#   * the FOCUS ServiceProviderName stamped on BillingLine.
#
# Every selection site used to be a strict binary ternary
# (``AZURE_* if provider == "azure" else GCP_*``), which silently assigns any
# third provider to GCP. These tables replace the ternaries with one lookup, so
# adding a provider is a data change rather than a hunt for ternaries.
PROVIDER_KEY_AZURE = "azure"
PROVIDER_KEY_GCP = "gcp"
PROVIDER_KEY_AWS = "aws"

PROVIDER_KEYS = (PROVIDER_KEY_AZURE, PROVIDER_KEY_GCP, PROVIDER_KEY_AWS)

# Operational provider key -> FOCUS ServiceProviderName.
FOCUS_PROVIDER_NAME = {
    PROVIDER_KEY_AZURE: PROVIDER_AZURE,
    PROVIDER_KEY_GCP: PROVIDER_GCP,
    PROVIDER_KEY_AWS: PROVIDER_AWS,
}

PROVIDER_REGIONS = {
    PROVIDER_KEY_AZURE: AZURE_REGIONS,
    PROVIDER_KEY_GCP: GCP_REGIONS,
    PROVIDER_KEY_AWS: AWS_REGIONS,
}

PROVIDER_SERVICES = {
    PROVIDER_KEY_AZURE: AZURE_SERVICES,
    PROVIDER_KEY_GCP: GCP_SERVICES,
    PROVIDER_KEY_AWS: AWS_SERVICES,
}

# ── FOCUS descriptive catalog: ServiceSubcategory / ChargeDescription ─────────
#
# ``ServiceSubcategory`` and ``ChargeDescription`` describe the SERVICE a charge
# belongs to, so they are catalog data and live here, beside the tables that already
# describe each service (resource_type / service_name / category / sku / unit / price).
# The renderers only PROJECT them. A description assembled inside
# ``render/focus_aws.py`` would be a plausible-looking string no data source backs,
# which is the fabrication the field-fidelity rule forbids.
#
# Shape, keyed by operational provider key (the same key ``PROVIDER_SERVICES`` uses):
#
#   resource_type -> (ServiceSubcategory, ChargeDescription template)
#
# Every ``{...}`` field of a template is filled from the SAME row's own model values --
# the line's ``service_name`` and the resource's ``sku_id`` -- so not one character of
# the emitted string is new. A row whose service this table does not name emits an
# EMPTY column: absence is absence, never a guess (the billing-only constructs, for
# instance the AWS Marketplace and Support lines, are no catalog entry and stay empty).
#
# ``{resource_type}`` is deliberately NOT a field of any template. It holds the
# simulator's own snake_case token (``ec2_instance``), so a description using it would
# leak a FinOps modelling id into a provider-shaped string while telling the reader
# nothing new: ``sku_id`` already says which variant of the service is billed.
#
# Only ``aws`` is keyed. ``render/focus_azure.py`` and ``render/gcp_bigquery.py`` record
# why their two columns are not wired to this table.
#
# Provenance of each ServiceSubcategory literal, so a reviewer can check it against the
# provider's own published vocabulary:
#
#   * "Virtual Machines", "Managed Databases", "Object Storage", "Network Edge",
#     "Load Balancing", "Bandwidth" and "Functions" are verbatim the literals
#     FinOps OWN AWS FOCUS normalizer maps a CUR product family to --
#     ``aws_mapper.py (modulo do consumidor)::_FAMILY_TO_SUBCATEGORY`` (its
#     ``_service_subcategory`` also returns them by service name for Lambda, RDS,
#     DynamoDB and S3). Reusing them keeps the export and the ingestion path agreeing
#     about a service instead of each carrying its own idea of the same one.
#   * "Block Storage", "Containers", "Observability", "Network Infrastructure" and
#     "Network Security" have NO literal in that map, so they are UNVERIFIED against
#     AWS's published ServiceSubcategory values and are flagged TODO-verificar in
#     ``docs/synthetic-clouds/UNVERIFIED.md`` exactly the way ``focus_aws._SERVICE_CODE``
#     flags its entries: the column set is authoritative, these VALUES are illustrative.
#     "Observability" is the literal FinOps Azure normalizer already uses for a
#     monitoring service (``azure_mapper._METER_FAMILY_SUBCATEGORY``), kept identical so
#     the two providers do not invent two words for one idea.
FOCUS_SERVICE_DESCRIPTIONS: dict[str, dict[str, tuple[str, str]]] = {
    PROVIDER_KEY_AWS: {
        "ec2_instance": ("Virtual Machines", "{service_name} instance usage ({sku_id})"),
        "ebs_volume": ("Block Storage", "{service_name} volume storage ({sku_id})"),
        "nat_gateway": ("Network Edge", "{service_name} NAT gateway usage ({sku_id})"),
        "rds_instance": ("Managed Databases", "{service_name} database instance usage ({sku_id})"),
        "s3_bucket": ("Object Storage", "{service_name} storage usage ({sku_id})"),
        "data_transfer": ("Bandwidth", "{service_name} data transfer ({sku_id})"),
        "eks_cluster": ("Containers", "{service_name} cluster usage ({sku_id})"),
        "cloudwatch_logs": ("Observability", "{service_name} log ingestion ({sku_id})"),
        "lambda_function": ("Functions", "{service_name} function invocation ({sku_id})"),
        "elastic_ip": ("Network Edge", "{service_name} address usage ({sku_id})"),
        "application_lb": ("Load Balancing", "{service_name} load balancer usage ({sku_id})"),
        "vpc": ("Network Infrastructure", "{service_name} VPC usage ({sku_id})"),
        "security_group": ("Network Security", "{service_name} security group usage ({sku_id})"),
        "dynamodb_table": ("Managed Databases", "{service_name} table throughput ({sku_id})"),
        "ecs_cluster": ("Containers", "{service_name} cluster usage ({sku_id})"),
    },
}

# Commitment kind per provider. Azure Savings Plans and AWS Savings Plans are the
# same FOCUS-visible construct; GCP's analogue is a CUD. AWS ALSO sells reserved
# instances, but the base estate emits one commitment per scope — an
# unconditional RI on every AWS scope would make scenario A01's reserved-instance
# half indistinguishable from the baseline. A01's RI is therefore scenario-emitted.
COMMITMENT_KIND = {
    PROVIDER_KEY_AZURE: "savings_plan",
    PROVIDER_KEY_GCP: "cud",
    PROVIDER_KEY_AWS: "savings_plan",
}

# The metered unit a commitment of each ``Commitment.kind`` covers, and therefore the
# FOCUS ``CommitmentDiscountUnit`` it carries. This table does double duty on purpose:
#
#   * it is the unit of ``Commitment.quantity`` — the builder sums the quantities of the
#     lines the commitment covers, in this unit; and
#   * it is the eligibility rule for coverage — a line can only be covered when its own
#     ``pricing_unit`` IS this unit. That is what makes a Savings Plan / reservation /
#     CUD cover compute *hours* and leave ``GB-Month`` storage and ``GB`` transfer
#     uncovered, which is how the real discounts behave.
#
# The value is the catalog's own unit vocabulary ("Hours" in the ``*_SERVICES`` tables)
# rather than a second vocabulary invented at render time, so a covered row's
# ``CommitmentDiscountUnit`` agrees with its own ``ConsumedUnit``.
COMMITMENT_UNIT = {
    "savings_plan": "Hours",
    "reservation": "Hours",
    "cud": "Hours",
}

# Display label per commitment kind, used to name a commitment (FOCUS
# ``CommitmentDiscountName``). A commitment's name is free text the customer chooses in
# every provider, so the estate mints it from the scope the commitment applies to: the
# name is derived, identical on every row the commitment covers, and no renderer has to
# make one up.
COMMITMENT_LABEL = {
    "savings_plan": "Savings Plan",
    "reservation": "Reserved Instance",
    "cud": "Committed Use Discount",
}

# The share of a scope's commitment-ELIGIBLE resources a commitment covers. Real
# coverage of committable compute sits well under 100%: an estate carries covered and
# uncovered usage side by side, and a fully committed estate is no more faithful than an
# uncommitted one. Float because it is compared against ``random.Random.random()``.
COMMITMENT_COVERAGE = 0.65

# ── capacity reservations (FOCUS CapacityReservationId / CapacityReservationStatus) ──
#
# Provider key -> the resource types a capacity reservation can target. Keyed per
# provider for the same reason ``PROVIDER_SERVICES`` and ``FOCUS_SERVICE_DESCRIPTIONS``
# are: an eligibility rule is provider vocabulary, and a membership test without the
# provider key would silently apply one provider's product surface to the others.
#
# Only ``aws`` is keyed, and the eligible set is the catalog's ``ec2_instance``: an AWS
# capacity reservation is an EC2 construct. The catalog's other Compute-category types
# (``lambda_function``, ``eks_cluster``, ``ecs_cluster``) and ``rds_instance`` are NOT
# eligible — neither product reserves capacity that way, and listing them would model a
# reservation AWS does not sell. Azure (whose FOCUS schema carries both columns, see
# ``render/focus_azure.py``) has no key here for the parity reason that module's
# docstring records: nothing in this estate models an Azure-shaped reservation, so
# there is nothing to project. GCP's native BigQuery export has no such column at all.
CAPACITY_RESERVATION_TYPES: dict[str, tuple[str, ...]] = {
    PROVIDER_KEY_AWS: ("ec2_instance",),
}

# FOCUS 1.2 ``CapacityReservationStatus`` literal domain. Both values are the ones this
# package already emits for the sibling status column — ``CommitmentDiscountStatus``
# (``model/commitments.py``, ``model/billing.py``) — which is the allowed set a model
# literal may be checked against; no third literal is invented here.
CAPACITY_RESERVATION_STATUSES: tuple[str, str] = ("Used", "Unused")

# The share of the capacity-reservation-ELIGIBLE compute the estate reserves capacity
# on. Like ``COMMITMENT_COVERAGE``, deliberately partial: an estate where every
# instance sits in a reservation is as unfaithful as one with none, and the reserving
# and non-reserving halves together are what a reservation-coverage reader has to see.
CAPACITY_RESERVATION_COVERAGE = 0.3

# The share of those reservations whose capacity the instance actually consumes. An
# unused reservation is a modelled fact, not a renderer default: estates do keep
# reserved capacity standing idle, and the FOCUS column has a literal for it. Both
# literals stay reachable — see ``EstateBuilder._capacity_reservation``.
CAPACITY_RESERVATION_USED_SHARE = 0.8

# Contracted price discount factor relative to list (<= 1.0; FR-A3, FR-E flows).
CONTRACTED_DISCOUNT = Decimal("0.850000")

# Fixed BRL conversion rate for the BRL profile (seed-independent, informational).
BRL_CONVERSION_RATE = Decimal("5.400000")

# Standard tag keys applied to the ~85% tagged resources (FR-D2).
STANDARD_TAG_KEYS = ("env", "owner", "cost_center", "app")

# Weekday seasonality multipliers (Mon..Sun); weekends lighter (FR-D1).
WEEKDAY_SEASONALITY = (
    Decimal("1.05"),  # Mon
    Decimal("1.10"),  # Tue
    Decimal("1.08"),  # Wed
    Decimal("1.06"),  # Thu
    Decimal("1.00"),  # Fri
    Decimal("0.70"),  # Sat
    Decimal("0.65"),  # Sun
)

# Daily growth slope applied as (1 + GROWTH_PER_DAY * day_index) (FR-D1).
GROWTH_PER_DAY = Decimal("0.004")

# Profile windows and target FOCUS row bands (design sec. 6.1; OA-8 tolerance +/-10%).
PROFILE_WINDOW_DAYS = {"small": 45, "medium": 120, "large": 400}
PROFILE_TARGET_ROWS = {"small": 40_000, "medium": 500_000, "large": 2_000_000}
PROFILE_ROW_TOLERANCE = Decimal("0.10")

# K8s dominant-namespace share (C15 coherence; seed-derived majority band).
K8S_NAMESPACES = ("prod", "staging", "kube-system", "monitoring")
K8S_DOMINANT_SHARE = Decimal("0.65")
