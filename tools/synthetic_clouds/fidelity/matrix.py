"""Matriz de cobertura: liga cada superficie especificada ao que a produz.

A especificacao diz o que o simulador PODE gerar. Esta matriz diz o que ele de
fato gera hoje -- e, quando nao gera, por que. Sem ela, "o simulador cobre a
AWS" e uma impressao; com ela, e uma lista conferivel, e o que falta vira
trabalho nomeado em vez de esquecimento.

Tres estados, e a distincao entre os dois ultimos importa:

``implemented``
    Existe renderer registrado que produz o artefato.
``pending``
    A documentacao sustenta a geracao e o renderer ainda nao existe.
``blocked``
    A documentacao NAO sustenta a geracao (sem tipo publicado, sem colunas
    normativas). Nao e atraso: e uma recusa deliberada a inventar. So sai deste
    estado se aparecer evidencia oficial nova.
"""

from __future__ import annotations

from dataclasses import dataclass

STATUS_IMPLEMENTED = "implemented"
STATUS_PENDING = "pending"
STATUS_BLOCKED = "blocked"
_STATUSES = frozenset({STATUS_IMPLEMENTED, STATUS_PENDING, STATUS_BLOCKED})

# Uma superficie "gerada" pode estar num de dois patamares, e confundi-los faz o
# projeto se declarar completo entregando casca vazia:
#   records     -- o artefato carrega REGISTROS com dado.
#   format-only -- o artefato e o FORMATO documentado, com todo valor vazio.
# `format-only` nao e desonesto quando o modelo canonico nao tem aquele dado: e a
# resposta correta. Mas nao satisfaz "gera os dados necessarios", e por isso tem
# de aparecer contado.
DATA_RECORDS = "records"
DATA_FORMAT_ONLY = "format-only"
_DATA_KINDS = frozenset({DATA_RECORDS, DATA_FORMAT_ONLY})


@dataclass(frozen=True, slots=True)
class SurfaceCoverage:
    """O estado de uma superficie especificada."""

    surface: str
    status: str
    renderer: str | None
    note: str
    data: str = DATA_RECORDS


SURFACES: tuple[SurfaceCoverage, ...] = (
    # --- AWS -----------------------------------------------------------------
    SurfaceCoverage(
        "aws/bcm-data-exports-focus12",
        STATUS_IMPLEMENTED,
        "focus_aws",
        "FOCUS 1.2 com as 3 colunas AWS. O Parquet entregue tem exatamente as 60 colunas da spec.",
    ),
    SurfaceCoverage(
        "aws/bcm-data-exports-cur2",
        STATUS_IMPLEMENTED,
        "cur2_aws",
        "Export nativo da AWS (CUR 2.0) com as 131 colunas documentadas.",
    ),
    SurfaceCoverage(
        "aws/vpc-flow-logs-s3",
        STATUS_IMPLEMENTED,
        "vpc_flow_logs",
        "54/54 campos e fluxos derivados das VPCs do estate, no layout S3 documentado.",
    ),
    SurfaceCoverage(
        "aws/aws-config-snapshot-s3",
        STATUS_IMPLEMENTED,
        "aws_config_snapshot",
        "Os 4 conjuntos conferidos (envelope, item, relacao, notificacao SNS). Entrega JSON gzipado.",
    ),
    SurfaceCoverage(
        "aws/security-hub-asff",
        STATUS_IMPLEMENTED,
        "security_hub",
        "ASFF completo (46 + 12 + 38). A AWS nao exporta ASFF para S3: o formato de export e CSV "
        "ou OCSF_JSON, e isso esta registrado na spec.",
    ),
    SurfaceCoverage(
        "aws/security-hub-ocsf-export",
        STATUS_IMPLEMENTED,
        "security_hub_ocsf_export",
        "O artefato que a AWS EXPORTA (StartExportJobV2 -> FindingsOutput.Format = OCSF_JSON), em "
        "JSON por linha. Mesma origem do ASFF, formato diferente: a resposta da API e o export sao "
        "duas superficies. Os caminhos vem da lista de campos que a AWS publica; a CLASSE OCSF do "
        "envelope e o metadata.version NAO sao emitidos, porque nenhuma fonte da AWS os afirma.",
    ),
    SurfaceCoverage(
        "aws/ec2-describe-instances",
        STATUS_IMPLEMENTED,
        "ec2_instances",
        "Resposta da API (3 + 5 + 61 + 6 campos). Nao ha export duravel documentado.",
    ),
    SurfaceCoverage(
        "aws/ec2-describe-security-groups",
        STATUS_IMPLEMENTED,
        "ec2_security_groups",
        "Resposta da API (3 + 9 + 7 + 2 + 2 + 2 + 7 + 2 + 6 campos), 9 conjuntos. Existe "
        "porque o consumidor de postura varre as REGRAS e o estado nao tinha nenhuma: os 15 "
        "recursos security_group existiam, sem uma unica regra de entrada para ler. E a "
        "superficie de que as tres regras gerenciadas de REDE do AWS Config dependem "
        "(restricted-ssh, restricted-common-ports, vpc-default-security-group-closed), que "
        "ate aqui respondiam INSUFFICIENT_DATA por falta do fato e nao por duvida sobre a "
        "regra. A regra da AWS e ALLOW-ONLY -- 'You can specify allow rules, but not deny "
        "rules' -- e nao tem prioridade, entao o modelo usa um tipo PROPRIO e nao reusa a "
        "SecurityRule da Azure. vpcId e a pendencia declarada: o estate nao liga SG a VPC "
        "(os dois recursos vivem em regioes diferentes), e o valor vem do segmento de rede do "
        "mesmo (conta, regiao).",
    ),
    SurfaceCoverage(
        "aws/config-describe-compliance-by-config-rule",
        STATUS_IMPLEMENTED,
        "config_compliance_by_rule",
        "Resposta da API (2 + 2 + 2 + 2 + 3 campos), um item POR REGRA gerenciada e nao por "
        "recurso: e a superficie que um painel de postura consome quando quer veredito de "
        "regra. Os 14 ConfigRuleName sao regras gerenciadas REAIS, conferidas na lista oficial "
        "(838 nomes); o aws-sim do produto usa nomes sinteticos synth-*, que servem de stub e "
        "nao servem para conferir postura real. Das 14, SEIS sao avaliadas do estado (duas de "
        "tag, s3-bucket-tagged e lambda-function-tagged, TRES DE REDE desde o Incremento 2: "
        "restricted-ssh, restricted-common-ports e vpc-default-security-group-closed, que antes "
        "respon INSUFFICIENT_DATA porque o estate tinha os 15 recursos security_group e nenhuma "
        "regra, e TRES DE S3 desde o Incremento 3: s3-bucket-public-read-prohibited, "
        "s3-bucket-public-write-prohibited e s3-bucket-level-public-access-prohibited, que antes "
        "respon INSUFFICIENT_DATA porque o estate tinha os 15 recursos s3_bucket e nem ACL, nem "
        "bucket policy, nem Block Public Access) e OITO ficam INSUFFICIENT_DATA com a lacuna do "
        "modelo registrada -- nao ha entidade de IAM, trilhas CloudTrail nem inscricao do "
        "Security Hub. "
        "NOT_APPLICABLE nunca e emitido: a propria pagina Compliance diz que o tipo nao o suporta.",
    ),
    SurfaceCoverage(
        "aws/s3-list-buckets",
        STATUS_IMPLEMENTED,
        "s3_list_buckets",
        "Resposta da API (4 + 4 + 2 + 4 campos), 4 conjuntos. E a unica do Incremento 3 com escopo "
        "de CONTA, porque a acao lista 'all buckets owned by the authenticated sender' e a regiao "
        "de cada bucket viaja dentro do objeto Bucket. BucketArn sai nulo por CONTRATO: a pagina do "
        "tipo diz que ele so e suportado para directory buckets. Incremento 3.",
    ),
    SurfaceCoverage(
        "aws/s3-get-bucket-acl",
        STATUS_IMPLEMENTED,
        "s3_get_bucket_acl",
        "Resposta da API (2 + 2 + 2 + 5 + 2 campos), 5 conjuntos. Publica a ACL EFETIVA e nao a "
        "armazenada: com IgnorePublicAcls ligado a pagina manda devolver 'an ACL that reflects "
        "the access permissions that Amazon S3 is enforcing', entao os grants para AllUsers e "
        "AuthenticatedUsers saem da resposta aunque o estado os guarde. Incremento 3.",
    ),
    SurfaceCoverage(
        "aws/s3-get-bucket-policy",
        STATUS_IMPLEMENTED,
        "s3_get_bucket_policy",
        "Resposta da API (1 + 3 + 5 + 2 campos), 4 conjuntos. Unica das quatro em que a resposta "
        "e documentada em JSON de verdade. Os membros do documento vem da Sample Response da "
        "mesma pagina -- a lista de Response Elements publica so Policy -- e Condition nao "
        "aparece nesse exemplo, logo nao entra. Incremento 3.",
    ),
    SurfaceCoverage(
        "aws/s3-get-public-access-block",
        STATUS_IMPLEMENTED,
        "s3_get_public_access_block",
        "Resposta da API (4 + 2 campos), 2 conjuntos. Os quatro interruptores nunca sao nulos: um "
        "bucket sem configuracao tem os quatro desligados, que e a leitura que as regras fazem. "
        "BlockPublicPolicy e BlockPublicAcls sao o curto-circuito das duas regras "
        "s3-bucket-public-*-prohibited. Incremento 3.",
    ),
    SurfaceCoverage(
        "aws/iam-get-account-password-policy",
        STATUS_IMPLEMENTED,
        "iam_get_account_password_policy",
        "Resposta da API (10 campos), 1 conjunto. Escopo CONTA, nao (conta, regiao): a acao nao leva "
        "parametro nenhum e PasswordPolicy nao tem membro que nomeie a conta, entao a resposta e "
        "identica em relacao a conta e a atribuicao fica no _provenance. ExpirePasswords e DERIVADO "
        "de MaxPasswordAge pela propria pagina do tipo, e por isso e propriedade no modelo e nao um "
        "campo independente. Incremento 4.",
    ),
    # --- GCP -----------------------------------------------------------------
    SurfaceCoverage(
        "gcp/billing-export-standard",
        STATUS_IMPLEMENTED,
        "gcp_bigquery_topology",
        "Tabela gcp_billing_export_v1_<ID>.",
    ),
    SurfaceCoverage(
        "gcp/billing-export-detailed",
        STATUS_IMPLEMENTED,
        "gcp_bigquery_topology",
        "Tabela gcp_billing_export_resource_v1_<ID>.",
    ),
    SurfaceCoverage(
        "gcp/billing-export-pricing",
        STATUS_IMPLEMENTED,
        "gcp_bigquery_topology",
        "Tabela cloud_pricing_export.",
    ),
    SurfaceCoverage(
        "gcp/security-command-center-findings-bigquery",
        STATUS_IMPLEMENTED,
        "gcp_scc_findings",
        "67 registros. As 6 colunas sem tipo publicado nao sao geradas -- num alvo tipado isso "
        "exigiria inventar o tipo.",
    ),
    SurfaceCoverage(
        "gcp/vpc-flow-logs-bigquery",
        STATUS_IMPLEMENTED,
        "gcp_flow_logs",
        "O artefato e o FORMATO documentado com todo valor vazio, e o manifesto registra "
        "records=0. Os 181 campos conferem, mas NAO HA FLUXO: o modelo canonico nao tem tipo de "
        "registro de fluxo (ver docs/MODELO-REDE.md).",
        DATA_FORMAT_ONLY,
    ),
    SurfaceCoverage(
        "gcp/cloud-asset-inventory-compute-instance",
        STATUS_IMPLEMENTED,
        "gcp_asset_inventory",
        "126 registros; 9 dos 10 conjuntos completos (o ausente em asset_message e o obsoleto).",
    ),
    SurfaceCoverage(
        "gcp/compute-instances-rest",
        STATUS_IMPLEMENTED,
        "gcp_compute_instances",
        "48/48 campos, representacao REST do recurso.",
    ),
    SurfaceCoverage(
        "gcp/asset-search-all-resources",
        STATUS_IMPLEMENTED,
        "gcp_cai_search_all_resources",
        "Contrato do proto oficial (ResourceSearchResult) conferido em dois niveis: o envelope "
        "(results/nextPageToken) e o item. A chave de juncao sintetica resourceUuid, que o proto "
        "nao declara, NAO e emitida aqui -- o proto do consumidor recusa resposta com campo de "
        "topo desconhecido.",
    ),
    # --- G11: as respostas de API que o gcp_rest_fixtures entregava sem contrato --------------
    # Onze superficies, uma por endpoint. O renderer antigo continua no ar (o emulador o consome)
    # e estas sao a forma CONFORME ao contrato publicado, com a diferenca agora medivel.
    SurfaceCoverage(
        "gcp/asset-search-all-iam-policies",
        STATUS_IMPLEMENTED,
        "gcp_asset_search_all_iam_policies",
        "Envelope e bindings do proto oficial; a chave de juncao resourceUuid nao e emitida.",
    ),
    SurfaceCoverage(
        "gcp/scc-sources",
        STATUS_IMPLEMENTED,
        "gcp_scc_sources",
        "Source com name/displayName/description -- os tres campos que o renderer antigo ja usava.",
    ),
    SurfaceCoverage(
        "gcp/scc-findings",
        STATUS_IMPLEMENTED,
        "gcp_api_scc_findings",
        "Finding no formato do proto, com o resourceName resolvido do estado (o antigo embrulhava "
        "um UUID cru num host). As chaves de sourceProperties nao tem enumeracao oficial e estao "
        "registradas como tema.",
    ),
    SurfaceCoverage(
        "gcp/compute-firewalls",
        STATUS_IMPLEMENTED,
        "compute_firewalls",
        "Envelope FirewallList por PROJETO (o caminho e projects/<p>/global/firewalls: global, sem "
        "regiao) e o recurso Firewall com as DUAS listas de decisao -- allowed[] e denied[], e nao "
        "um campo como o NSG da Azure. O nome oficial do protocolo e IPProtocol. 'id', 'selfLink' e "
        "'creationTimestamp' sao output-only do servidor e 'params' e input-only: os quatro vao "
        "vazios, declarados na proveniencia.",
    ),
    SurfaceCoverage(
        "gcp/recommender-recommendations",
        STATUS_IMPLEMENTED,
        "gcp_recommender_recommendations",
        "Nome canonico com o projeto real: o antigo emitia 'projects/-/...', que e curinga de "
        "REQUISICAO (AIP-159) e nao pode aparecer no corpo da resposta.",
    ),
    SurfaceCoverage(
        "gcp/recommender-insights",
        STATUS_IMPLEMENTED,
        "gcp_recommender_insights",
        "Idem: nome canonico, sem o curinga de requisicao.",
    ),
    SurfaceCoverage(
        "gcp/catalog-services",
        STATUS_IMPLEMENTED,
        "gcp_catalog_services",
        "Nenhum campo desconhecido: o renderer antigo ja usava name/serviceId/displayName. O id "
        "derivado do estado esta registrado como nao comprovado.",
    ),
    SurfaceCoverage(
        "gcp/catalog-skus",
        STATUS_IMPLEMENTED,
        "gcp_catalog_skus",
        "Idem para o SKU, incluindo a categoria aninhada.",
    ),
    SurfaceCoverage(
        "gcp/monitoring-time-series",
        STATUS_IMPLEMENTED,
        "gcp_monitoring_time_series",
        "Os labels sao os DECLARADOS para o tipo monitorado (gce_instance/cloudsql_database); o "
        "resourcePath e o resourceUuid que o antigo punha ali nao sao labels do tipo.",
    ),
    SurfaceCoverage(
        "gcp/monitoring-metric-descriptors",
        STATUS_IMPLEMENTED,
        "gcp_monitoring_metric_descriptors",
        "Um descritor por tipo de metrica que o estado realmente reporta, e nada mais.",
    ),
    SurfaceCoverage(
        "gcp/monitoring-alert-policies",
        STATUS_IMPLEMENTED,
        "gcp_monitoring_alert_policies",
        "Politica derivada das series, com condicao de AUSENCIA (o estado nao carrega limiar de "
        "operador). Nenhuma juncao sintetica -- nem no topo, nem em userLabels.",
    ),
    SurfaceCoverage(
        "gcp/billing-budgets",
        STATUS_IMPLEMENTED,
        "gcp_billing_budgets",
        "Formato do nome e da quantia conferem; o contrato nao impoe formato ao budgetId, entao um "
        "UUID e aceitavel.",
    ),
    SurfaceCoverage(
        "gcp/observability-partial",
        STATUS_IMPLEMENTED,
        "gcp_observability_partial",
        "A MESMA leitura de series pedida num escopo de projeto INTEIRO (projects/-) e respondida em "
        "PARTE: um projeto de tres, com o inventario do que sobrou de fora em missing.json. O pedido "
        "e anonimo -- o escopo viaja em DADOS (curinga de projeto, filtro, janela) e nao em "
        "credencial, entao o conjunto request-parameters nao tem accessToken, apiKey nem "
        "Authorization. Nenhum dos dois artefatos irmaos entra no corpo: o contrato nao declara um "
        "campo de itens ausentes. Incremento 4.",
    ),
    SurfaceCoverage(
        "gcp/infrastructure-manager-resource-drift",
        STATUS_IMPLEMENTED,
        "drift_views",
        "ResourceDrift/PropertyDrift do Infrastructure Manager. O gerador emite o INPUT (tags "
        "declaradas no snapshot vs. inventario), e a projecao traduz para o contrato oficial. "
        "Tambem e servido em config.googleapis.com pelo gcp-sim.",
    ),
    SurfaceCoverage(
        "gcp/container-clusters",
        STATUS_BLOCKED,
        None,
        "ListClustersResponse do Kubernetes Engine v1 (projects.locations.clusters.list): o envelope "
        "(clusters[]/missingZones[]) e 4 dos 87 membros publicados de Cluster. BLOQUEADA por "
        "falta de artefato duravel, e nao pela documentacao: a documentacao sustenta a FORMA "
        "(esta e a unica razao pela qual as 4 colunas sao nao geraveis na spec), mas a superficie "
        "e uma RESPOSTA de API servida ao vivo pelo gcp-sim em container.googleapis.com "
        "(emulators/gcp-sim/gcp_sim/routers/container.py) e nao um arquivo de export -- nao ha "
        "renderer que produza um artefato conferivel contra a spec, e sem renderer 'implemented' "
        "seria mentira. A forma publicada e a citacao oficial estao em specs/gcp/container-clusters.md.",
    ),
    SurfaceCoverage(
        "aws/iam-get-credential-report",
        STATUS_IMPLEMENTED,
        "iam_get_credential_report",
        "Resposta da API, 3 conjuntos: as 23 colunas do CSV, o parametro do pedido (report_format) e "
        "os 3 elementos do envelope. O unico contrato CSV do repositorio, e as diferencas nao sao "
        "cosmeticas: booleanos em TRUE/FALSE maiusculo, cabecalho obrigatorio na ordem documentada, e "
        "N/A / not_supported / no_information como ESTADOS com significado proprio -- traduzi-los "
        "para null apagaria 'este usuario nao tem senha'. A linha da conta root vem primeiro e e a "
        "unica que carrega 'not_supported'; o LITERAL do nome dela nao foi verificado nas duas paginas "
        "consultadas e vai marcado como nao comprovado no _provenance. Incremento 4.",
    ),
    # --- Azure ---------------------------------------------------------------
    SurfaceCoverage(
        "azure/cost-management-export-focus12",
        STATUS_IMPLEMENTED,
        "focus_azure",
        "FocusCost 1.2-preview: 104 colunas emitidas = exatamente as emittable da spec; as 6 "
        "declaradas sempre vazias saem vazias.",
    ),
    SurfaceCoverage(
        "azure/cost-management-export-manifest",
        STATUS_IMPLEMENTED,
        "focus_azure",
        "export_run.json com exatamente os 12 campos contratados pela API REST; os 29 do exemplo "
        "oficial sao recusados por inteiro.",
    ),
    SurfaceCoverage(
        "azure/cost-management-export-cost-details",
        STATUS_BLOCKED,
        None,
        "A Microsoft publica nomes, sem tipos, e nenhum dos 132 nomes aparece nos cinco "
        "contratos ao mesmo tempo. Gerar exigiria inventar tipo e escolher contrato.",
    ),
    SurfaceCoverage(
        "azure/azure-resource-graph-virtual-machines",
        STATUS_IMPLEMENTED,
        "azure_resource_graph",
        "56 registros; 32 dos 33 caminhos properties.* das VMs. Os conjuntos "
        "securityresources ficam de fora porque sao example-only. Resource Graph e consulta, "
        "nao export.",
    ),
    SurfaceCoverage(
        "azure/nsg-flow-logs-v2",
        STATUS_IMPLEMENTED,
        "azure_nsg_flow_logs",
        "13 membros JSON do registo (a amostra oficial fixa a forma). As 26 posicoes do fluxo "
        "vivem dentro de uma string, logo nao tem tipo JSON.",
    ),
    SurfaceCoverage(
        "azure/vnet-flow-logs",
        STATUS_IMPLEMENTED,
        "azure_vnet_flow_logs",
        "12 registros, mas apenas 7 das 127 colunas sao geraveis: os 120 campos de blob sao "
        "example-only. Esparso por falta de contrato publicado, nao por omissao.",
    ),
    SurfaceCoverage(
        "azure/defender-for-cloud-continuous-export",
        STATUS_IMPLEMENTED,
        "azure_defender",
        "107 registros nas tres estruturas com schema publicado. As 21 de attackpaths nao tem "
        "tipo nem exemplo de payload. Azure Storage nao e destino documentado.",
    ),
    SurfaceCoverage(
        "azure/arm-resource-representation",
        STATUS_IMPLEMENTED,
        "azure_arm_instances",
        "56 registros; 301 das 327 colunas. E a resposta da API, nao um arquivo de export.",
    ),
    SurfaceCoverage(
        "azure/arm-network-security-group-rules",
        STATUS_IMPLEMENTED,
        "azure_nsg_rules",
        "As 23 colunas do envelope do NSG e de SecurityRulePropertiesFormat. Existe porque o "
        "consumidor varre as REGRAS (direction/access) e o estado nao tinha nenhuma: o "
        "azure-sim respondia lista vazia por desenho. Cada NSG entrega as duas posturas "
        "(Inbound/Allow e Deny) para que um filtro invertido nao passe.",
    ),
    SurfaceCoverage(
        "azure/security-assessments-list",
        STATUS_IMPLEMENTED,
        "azure_defender_assessments",
        "36 colunas em 2 conjuntos (assessment/assessmentList); um envelope SecurityAssessmentList "
        "por assinatura. Existe porque o consumidor varre assessments.list e filtra por "
        "status.code, e nao havia superficie nenhuma com essa forma. O estado entrega os TRES "
        "literais: so 'Healthy' e descartado, e 'NotApplicable' vira achado do mesmo jeito.",
    ),
    SurfaceCoverage(
        "azure/deployment-stacks-what-if",
        STATUS_IMPLEMENTED,
        "drift_views",
        "DeploymentStacksWhatIfResult com resourceChanges modify/detach e delta por propriedade. "
        "O what-if e um PLANO (before=atual, after=desejado), nao um drift nativo persistido; "
        "tambem e servido em management.azure.com pelo azure-sim.",
    ),
)

_BY_SURFACE = {coverage.surface: coverage for coverage in SURFACES}


def coverage_for(surface: str) -> SurfaceCoverage | None:
    """Estado declarado de uma superficie, ou ``None`` se nao declarada."""
    return _BY_SURFACE.get(surface)


def declared_surfaces() -> tuple[str, ...]:
    """Identificadores das superficies declaradas nesta matriz."""
    return tuple(coverage.surface for coverage in SURFACES)


def by_status(status: str) -> tuple[SurfaceCoverage, ...]:
    """Superficies num estado (``implemented``, ``pending`` ou ``blocked``)."""
    if status not in _STATUSES:
        raise ValueError(f"status desconhecido: {status!r}")
    return tuple(coverage for coverage in SURFACES if coverage.status == status)


def summary() -> dict[str, int]:
    """Contagem por estado, para relatorio."""
    return {status: len(by_status(status)) for status in sorted(_STATUSES)}
