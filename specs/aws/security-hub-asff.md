# security-hub-asff

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | AWS Security Hub CSPM — **AWS Security Finding Format (ASFF)**; e o mecanismo de export oficial `StartExportJobV2` → Amazon S3 |
| Documento oficial (visão geral do ASFF) | *AWS Security Finding Format (ASFF)* — https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings-format.html |
| Documento oficial (atributos de topo obrigatórios) | *Required top-level ASFF attributes* — https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| Documento oficial (atributos de topo opcionais) | *Optional top-level ASFF attributes* — https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| Documento oficial (objeto `Resources`) | *Resources ASFF object* — https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources.html |
| Documento oficial (atributos de `Resources`) | *Resource attributes in the ASFF* — https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| Documento oficial (schema canônico da API) | *AwsSecurityFinding* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html |
| Documento oficial (objeto `Resource` da API) | *Resource* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html |
| Documento oficial (mecanismo de export) | *StartExportJobV2* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |
| Documento oficial (configuração de saída) | *FindingsOutput* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html |
| Documento oficial (destino S3) | *S3ExportDestination* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.html |
| Documento oficial (polling do job) | *GetExportJobV2* — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.html |
| Documento oficial (retenção e caminho alternativo) | *Creating and updating findings in Security Hub CSPM* — https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html |
| Data de consulta | 2026-10-14 |
| Versão/schema de referência | ASFF `SchemaVersion` = **`2018-10-08`** (único valor publicado: *"In the current release, the AWS Security Finding Format schema version is `2018-10-08`."*) |

## 2. Mecanismo e entrega

### 2.1 O mecanismo de export para S3 EXISTE — mas não em ASFF

**Existe export oficial para S3.** A API `StartExportJobV2` é documentada literalmente como:

> *"Starts an ad hoc export job that writes Security Hub findings to an Amazon Simple Storage Service (Amazon S3) bucket that you own."*
> — https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html

**Porém, o formato de saída NÃO é ASFF.** `FindingsOutput.Format` aceita apenas:

| Valor | Descrição oficial |
|---|---|
| `CSV` | *"produces comma-separated rows that are suitable for spreadsheets and analysis tools"* |
| `OCSF_JSON` | *"produces newline-delimited JSON records in the Open Cybersecurity Schema Framework (OCSF) format used elsewhere in Security Hub"* |

Fonte: https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html

**Não existe nenhum valor de `Format` que produza ASFF.** O campo `SelectedFields` reforça isto: seus valores válidos são **caminhos de campo OCSF** (`finding_info.title`, `severity`, `cloud.account.uid`, …), não campos ASFF. Não existe campo ASFF sequer na lista de `SelectedFields`.

> **Achado principal:** para o projeto, isto significa que **ASFF e o export para S3 são dois formatos diferentes da mesma fonte**. Um simulador que gera "Security Hub → S3" e afirma produzir ASFF estaria a inventar um mecanismo. As duas superfícies devem ser tratadas separadamente: (a) o **formato** ASFF, que é o formato normativo das findings dentro do Security Hub; e (b) o **export** para S3, que emite CSV ou OCSF JSON.

### 2.2 Caminho alternativo documentado no User Guide

O User Guide apresenta um caminho diferente e mais antigo:

> *"For longer-term retention of findings, you can export findings to an S3 bucket. You can do this by using a custom action with an Amazon EventBridge rule."*
> — https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html

Este caminho liga ao tópico *Using EventBridge for automated response and remediation* (`./securityhub-cloudwatch-events.html`). **Este caminho é genérico de EventBridge**: a AWS não publica neste ponto um layout de objeto S3, um nome de arquivo ou um schema de saída. É um mecanismo encadeado pelo cliente, não um export nativo.

**Os dois caminhos coexistem e a documentação não os reconcilia.** Registamos ambos sem escolher (ver secção 5).

### 2.3 Parâmetros de entrega do export nativo

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Destino | *"The destination that Security Hub writes the export to. You must specify exactly one destination type. Currently, the only supported type is Amazon S3."* | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportDestination.html |
| `BucketArn` | ARN do bucket. *"You must own the bucket"*. Obrigatório | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.html |
| `KmsKeyArn` | ARN completo da chave KMS simétrica `ENCRYPT_DECRYPT`, single-Region, mesma conta e mesma Region do job, partição `aws`/`aws-cn`/`aws-us-gov`. Chaves multi-Region (`mrk-`) são rejeitadas; key IDs e aliases são rejeitados. Obrigatório | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.html |
| `ObjectPrefix` | Prefixo opcional de chave, até 512 caracteres. *"Use a prefix to organize exports within the bucket."* **Não é publicado nenhum template de caminho além deste prefixo** | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.html |
| Service principal | `exportv2.securityhub.amazonaws.com` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |
| Concorrência | *"Security Hub allows only one export job in the `RUNNING` state per account at a time."* Exceder devolve `ServiceQuotaExceededException` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |
| Status possíveis | `RUNNING` \| `SUCCEEDED` \| `FAILED` \| `CANCELLED` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.html |
| `DataType` | `FINDINGS` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.html |
| `FailureCode` | `ACCESS_DENIED` \| `RESOURCE_NOT_FOUND` \| `INTERNAL_ERROR` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.html |
| `SelectedFields` (só CSV) | 1 a 50 campos, **obrigatório** para `CSV`, **não suportado** para `OCSF_JSON`. Para CSV, *"The field paths that you specify become the columns of the output, in the order that you provide them."* | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html |
| `Filters` | Filtros OCSF, mesma estrutura de `GetFindingsV2`. Omitir = exporta todas as findings acessíveis ao chamador | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html |
| `Scopes` | Até 10 entradas em `Scopes.AwsOrganizations`; combina com lógica OR. Só o delegated administrator pode usar | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |
| `ClientToken` | Idempotência. Comprimento 1–63, pattern `^[\x21-\x7E]{1,64}$` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |
| `ExportJobId` | Comprimento 1–64, pattern `^[a-z0-9]+$` | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html |

**O export é assíncrono**: `StartExportJobV2` devolve apenas `ExportJobId`; é preciso `GetExportJobV2` para fazer polling e `ListExportJobsV2` para listar.

### 2.4 Retenção nativa (motivo do export)

| Estado da finding | Retenção | Fonte |
|---|---|---|
| `RecordState` = `ACTIVE` | 90 dias | https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html |
| `RecordState` = `ARCHIVED` | 30 dias | https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html |

Expiração de control findings baseia-se em `UpdatedAt`; para os demais tipos, compara `ProcessedAt` e `UpdatedAt` e usa o mais recente. Fonte: https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html

### 2.5 Layout S3, formato de arquivo e manifesto

| Propriedade | Estado | Fonte |
|---|---|---|
| Template de caminho/objeto | **NÃO DOCUMENTADO.** A única afirmação publicada é que `ObjectPrefix` é *"an optional key prefix that Security Hub prepends to the Amazon S3 object keys of the export output"*. Nenhum segmento de conta, região, data ou job ID é publicado | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.html |
| Nome do objeto | **NÃO DOCUMENTADO** | — |
| Compressão | **NÃO DOCUMENTADA** | — |
| Encoding | **NÃO DOCUMENTADO** | — |
| Delimitador do CSV | **NÃO DOCUMENTADO** (a doc diz *"comma-separated rows"*) | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html |
| Cabeçalho do CSV | **NÃO DOCUMENTADO** | — |
| Quebra de registo no OCSF_JSON | **NÃO DOCUMENTADO explicitamente** (a doc diz *"newline-delimited JSON records"*) | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html |
| Manifesto | **NÃO DOCUMENTADO** — nenhuma página consultada descreve manifesto | — |
| Particionamento | **NÃO DOCUMENTADO** | — |

## 3. Campos

### 3.1 Campos de topo do ASFF

O ASFF é um JSON derivado de JSON Schema. A lista de campos abaixo é a enumeração canônica do schema da API `AwsSecurityFinding` (fonte: https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html), com a descrição semântica confirmada nas páginas do User Guide. `Obrigatório = sim` significa exigido em **todos** os findings; `Required: Yes` na API Reference.

Data de consulta de todas as linhas: **2026-10-14**.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `AwsAccountId` | string | sim | — | — | 12 dígitos (Length Constraints: 12) | O ID da conta AWS à qual a finding se aplica | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `CreatedAt` | string | sim | — | ISO 8601 UTC com milissegundos, ex.: `2017-03-22T13:22:13.933Z` | — | Indica quando o problema/evento de segurança foi criado | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Description` | string | sim | — | — | comprimento 1–1024 | Descrição da finding. Pode ser boilerplate ou específica da instância | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `GeneratorId` | string | sim | — | — | comprimento 1–512 | O identificador do componente específico da solução que gerou a finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Id` | string | sim | — | — | comprimento 1–512 | O identificador específico do produto para a finding. Para control findings, é o ARN da finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `ProductArn` | string | sim | — | — | comprimento 12–2048; formato `arn:partition:securityhub:region:account-id:product/company-id/product-id` | ARN gerado pelo Security Hub que identifica unicamente o produto gerador | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Resources` | array de objetos `Resource` | sim | — | — | mínimo 1, máximo 32 itens | Conjunto de tipos de dados de recursos que descrevem os recursos referidos pela finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `SchemaVersion` | string | sim | — | — | `2018-10-08` | A versão de schema para a qual a finding está formatada | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Severity` | objeto `Severity` | sim | — | — | — | Define a importância de uma finding. Objeto de topo **e** aninhado sob `FindingProviderFields`. Só deve ser atualizado com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Title` | string | sim | — | — | comprimento 1–256 | O título da finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Types` | array de strings | sim | — | — | `namespace/category/classifier`. Namespaces: `Software and Configuration Checks` \| `TTPs` \| `Effects` \| `Unusual Behaviors` \| `Sensitive Data Identifications`. Máximo 50 itens | Um ou mais tipos de finding que classificam a finding. Só deve ser atualizado com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `UpdatedAt` | string | sim | — | ISO 8601 UTC com milissegundos, ex.: `2017-04-22T13:22:13.933Z` | — | Indica quando o provedor atualizou pela última vez o registo da finding. Não pode ser atualizado com `BatchUpdateFindings`, apenas `BatchImportFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `Action` | objeto `Action` | não | — | — | — | Detalhes sobre uma ação que afeta ou foi tomada sobre um recurso | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `AwsAccountName` | string | não | — | — | comprimento 1–50 | O nome da conta AWS à qual a finding se aplica | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `CompanyName` | string | não | — | — | comprimento 1–128 | O nome da empresa do produto que gerou a finding. Preenchido automaticamente pelo Security Hub | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Compliance` | objeto `Compliance` | não | — | — | — | Detalhes sobre uma control finding: standards aplicáveis e status da verificação | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Confidence` | integer | não | escala 0–100 | — | 0–100 | A probabilidade de a finding identificar corretamente o comportamento ou problema | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Criticality` | integer | não | escala 0–100 | — | 0–100, apenas inteiros | O nível de importância atribuído aos recursos associados à finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Detection` | objeto `Detection` | não | — | — | — | Detalhes sobre uma attack sequence finding do Amazon GuardDuty Extended Threat Detection | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `FindingProviderFields` | objeto `FindingProviderFields` | não | — | — | — | Contém `Confidence`, `Criticality`, `RelatedFindings`, `Severity`, `Types` aninhados. Finding providers não podem atualizar com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `FirstObservedAt` | string | não | — | ISO 8601 UTC com milissegundos, ex.: `2017-03-22T13:22:13.933Z` | — | Indica quando o problema/evento foi observado pela primeira vez | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `GeneratorDetails` | objeto `GeneratorDetails` | não | — | — | — | Metadados para o detector do Amazon CodeGuru associado a uma finding (funções Lambda) | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html |
| `LastObservedAt` | string | não | — | ISO 8601 UTC com milissegundos, ex.: `2017-03-23T13:22:13.933Z` | — | Indica quando o problema/evento foi observado mais recentemente | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Malware` | array de objetos `Malware` | não | — | — | máximo 5 itens | Uma lista de malware relacionada com a finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Network` | objeto `Network` | não | — | — | — | Informação relacionada com rede sobre uma finding. **RETIRADO**: *"This object is retired. To provide this data, you can either map the data to a resource in `Resources`, or use the `Action` object."* | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `NetworkPath` | array de objetos `NetworkPathComponent` | não | — | — | — | Informação sobre um caminho de rede relacionado com uma finding. Cada entrada é um componente do caminho | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Note` | objeto `Note` | não | — | — | — | Uma nota definida pelo usuário adicionada a uma finding. Só pode ser atualizada com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `PatchSummary` | objeto `PatchSummary` | não | — | — | — | Resumo do status de conformidade de patch de uma instância contra um standard selecionado | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Process` | objeto `ProcessDetails` | não | — | — | — | Detalhes relacionados com processo sobre uma finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `ProcessedAt` | string | não | — | ISO 8601 UTC com milissegundos, ex.: `2023-03-23T13:22:13.933Z` | — | Indica quando o Security Hub recebeu a finding e começou a processá-la | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `ProductFields` | mapa string→string | não | — | — | máximo 50 pares; chave até 128 caracteres, valor até 2048 caracteres. Prefixo `aws/` reservado para AWS | Detalhes específicos da solução que não fazem parte do ASFF definido | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `ProductName` | string | não | — | — | comprimento 1–128 | O nome do produto que gerou a finding. Preenchido automaticamente pelo Security Hub | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `RecordState` | string | não | — | — | `ACTIVE` \| `ARCHIVED` | O estado de registo de uma finding. Só atualizável com `BatchImportFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Region` | string | não | — | — | comprimento 1–16 | A Region AWS a partir da qual a finding foi gerada. Preenchido automaticamente pelo Security Hub | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `RelatedFindings` | array de objetos `RelatedFinding` | não | — | — | mínimo 1, máximo 10 itens | Lista de findings relacionadas com a finding atual | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Remediation` | objeto `Remediation` | não | — | — | — | Informação sobre passos de remediação recomendados | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `RiskAssessment` | objeto | não | — | — | — | Avaliação de risco com `Posture` (`FindingTotal`, `Indicators[].Type`, `Indicators[].Findings[]`) | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Sample` | boolean | não | — | — | `true` \| `false` | Especifica se a finding é uma sample finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `SourceUrl` | string | não | — | — | — | URL que liga a uma página sobre a finding no produto gerador | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `ThreatIntelIndicators` | array de objetos `ThreatIntelIndicator` | não | — | — | mínimo 1, máximo 5 itens | Detalhes de threat intelligence relacionados com uma finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Threats` | array de objetos `Threat` | não | — | — | mínimo 1, máximo 32 itens | Detalhes sobre a ameaça detectada e os caminhos de arquivo afetados | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `UserDefinedFields` | mapa string→string | não | — | — | máximo 50 pares; chave até 128 caracteres, valor até 1024 caracteres | Pares nome-valor customizados. Só atualizável com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `VerificationState` | string | não | — | — | `UNKNOWN` \| `TRUE_POSITIVE` \| `FALSE_POSITIVE` \| `BENIGN_POSITIVE` | A veracidade de uma finding. Um provider pode dar valor inicial mas não atualizar depois | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Vulnerabilities` | array de objetos `Vulnerability` | não | — | — | — | Lista de vulnerabilidades associadas à finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Workflow` | objeto `Workflow` | não | — | — | — | Informação sobre o status da investigação de uma finding. Só atualizável com `BatchUpdateFindings` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `WorkflowState` | string | não | — | — | `NEW` \| `ASSIGNED` \| `IN_PROGRESS` \| `DEFERRED` \| `RESOLVED` | **RETIRADO.** *"This object is retired and has been replaced by the `Status` field of the `Workflow` object."* | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |

Total: **46 campos de topo** (12 obrigatórios + 34 opcionais).

> **Divergência de contagem:** o schema canônico `AwsSecurityFinding` da API Reference lista **44** membros — não inclui `RiskAssessment`, que existe apenas na página do User Guide. Registado na secção 5.

### 3.2 Campos do objeto `Resources[]`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `Id` | string | sim | — | — | pattern `.*\S.*` | O identificador canônico do tipo de recurso. Para recursos identificados por ARN, é o ARN | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html |
| `Type` | string | sim | — | — | comprimento 1–256. `AwsEc2Instance`, `AwsS3Bucket`, … ou `Other` | O tipo do recurso para o qual os detalhes são fornecidos | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html |
| `ApplicationArn` | string | não | — | — | pattern `.*\S.*` | O ARN da aplicação envolvida na finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `ApplicationName` | string | não | — | — | — | O nome da aplicação envolvida na finding | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `DataClassification` | objeto `DataClassificationDetails` | não | — | — | — | Informação sobre dados sensíveis detectados no recurso | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `Details` | objeto `ResourceDetails` | não | — | — | — | Informação adicional sobre um recurso, usando o objeto apropriado ao `Type`. *"if the finding size exceeds the maximum of 240 KB, then the `Details` object is removed from the finding"* | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `Owner` | objeto `ResourceOwner` | não | — | — | — | Informação sobre a conta e a organização donas do recurso | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html |
| `Partition` | string | não | — | — | `aws` \| `aws-cn` \| `aws-us-gov` \| `aws-us-iso` \| `aws-us-iso-b` \| `AzureCloud` | A partição na qual o recurso está localizado | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `Provider` | string | não | — | — | `AWS` \| `Azure` | O provedor de nuvem ao qual o recurso pertence | https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html |
| `Region` | string | não | — | — | comprimento 1–16 | O código da Region AWS onde o recurso está localizado | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `ResourceRole` | string | não | — | — | — | Identifica o papel do recurso na finding: alvo da atividade ou ator que a executou | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |
| `Tags` | mapa string→string | não | — | — | chaves/valores com pattern `.*\S.*` | Informação de chave e valor de tags do recurso. Só incluir para recursos que tenham tags associadas | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |

Total: **12 campos de `Resources[]`**.

### 3.3 Objetos aninhados conhecidos (não exaustivo)

Os campos abaixo têm nomes publicados nos exemplos oficiais. **Não** foram enumerados exaustivamente por subobjeto nesta spec — ver secção 4.

| Caminho | Campos publicados no exemplo oficial | Fonte |
|---|---|---|
| `Severity` | `Label`, `Normalized`, `Original` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html |
| `FindingProviderFields` | `Confidence`, `Criticality`, `RelatedFindings`, `Severity`, `Types` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Compliance` | `AssociatedStandards`, `RelatedRequirements`, `SecurityControlId`, `SecurityControlParameters`, `Status`, `StatusReasons` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Note` | `Text`, `UpdatedBy`, `UpdatedAt` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Workflow` | `Status` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Remediation` | `Recommendation.Text`, `Recommendation.Url` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `RelatedFindings[]` | `ProductArn`, `Id` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html |
| `Resources[].Details.AwsEc2Instance` | `IamInstanceProfileArn`, `ImageId`, `IpV4Addresses`, `IpV6Addresses`, `KeyName`, `LaunchedAt`, `MetadataOptions`, `NetworkInterfaces`, `SubnetId`, `Type`, `VirtualizationType`, `VpcId` | https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html |

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Template de caminho/chave de objeto S3 do export nativo | **UNVERIFIED** | A AWS só publica que `ObjectPrefix` é prependado às chaves. Nenhum segmento de conta, região, data, job ID ou nome de ficheiro é documentado |
| Nome/estrutura do arquivo de export | **UNVERIFIED** | Não documentado |
| Compressão e encoding do export | **UNVERIFIED** | Não documentados |
| Cabeçalho e delimitador exatos do CSV | **UNVERIFIED** | A doc diz apenas *"comma-separated rows"* |
| Manifesto de export | **UNVERIFIED (evidência negativa)** | Nenhuma página consultada descreve manifesto |
| Corpo exaustivo de 33 subobjetos ASFF (`Action`, `Detection`, `Malware`, `Process`, `PatchSummary`, `Threats`, `Vulnerabilities`, `NetworkPath`, `ThreatIntelIndicators`, `RiskAssessment`, `DataClassification`, …) | **UNVERIFIED nesta spec** | A página `securityhub-findings-format.html` publica o outline completo do JSON mas a resposta foi truncada na recolha. Os nomes de topo estão verificados; os subcampos profundos **não** foram enumerados um a um e por isso **não entram** no `schema.json`. Devem ser objeto de uma iteração dedicada por subobjeto |
| `Severity.Label` valores permitidos | **UNVERIFIED como enum formal** | A doc dá orientação (*"`INFORMATIONAL`… `LOW`… `MEDIUM`… `HIGH` or `CRITICAL`"*) mas remete ao objeto `Severity` da API Reference, que não foi lido nesta iteração |
| Mapeamento ASFF → colunas CSV do export | **UNVERIFIED** | `SelectedFields` só aceita caminhos OCSF. Não existe mapeamento ASFF↔CSV publicado |
| Schema OCSF JSON emitido pelo export | **UNVERIFIED** | A doc refere *"the Open Cybersecurity Schema Framework (OCSF) format"* e lista caminhos de campo, mas não publica o schema OCSF completo nem a versão OCSF usada |
| Layout S3 do caminho EventBridge + custom action | **UNVERIFIED** | O User Guide descreve o mecanismo mas não publica layout, nome de arquivo ou schema de saída |

## 5. Divergências conhecidas

1. **ASFF não é o formato do export para S3.** O export nativo (`StartExportJobV2`) emite **CSV** ou **OCSF_JSON**; nenhum valor de `Format` produz ASFF. O formato ASFF (`SchemaVersion` `2018-10-08`) é o formato normativo das findings dentro do Security Hub e o formato aceito por `BatchImportFindings`. Fontes: https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html e https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html

2. **Dois mecanismos de export coexistem sem reconciliação.** O User Guide afirma que para retenção de longo prazo *"you can export findings to an S3 bucket… by using a custom action with an Amazon EventBridge rule"*, enquanto a API Reference documenta um export nativo para S3. A documentação não diz qual substitui o outro nem se o texto do User Guide está desatualizado. Registamos ambos. Fontes: https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-findings.html e https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html

3. **`RiskAssessment` existe no User Guide mas não no schema `AwsSecurityFinding` da API Reference.** A página *Optional top-level ASFF attributes* documenta `RiskAssessment` com exemplos; a enumeração canônica da API não o lista. Contagem: 46 campos de topo pelo User Guide, 45 membros pelo schema da API. Fontes: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html e https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html

4. **`Partition` tem valores diferentes entre a API e o User Guide.** O User Guide lista três partições (`aws`, `aws-cn`, `aws-us-gov`); o schema `Resource` da API lista seis (`aws`, `aws-cn`, `aws-us-gov`, `aws-us-iso`, `aws-us-iso-b`, `AzureCloud`). Fontes: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html e https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Resource.html

5. **`ResourceRole` tem capitalização inconsistente nos exemplos oficiais.** O User Guide mostra `"ResourceRole": "target"` (minúsculas) e o exemplo de `Resources` na página de atributos obrigatórios mostra `"ResourceRole": "Target"` (maiúscula). Registamos ambos sem normalizar. Fontes: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html e https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html

6. **`Network` e `WorkflowState` estão retirados mas continuam nos schemas.** A doc marca ambos explicitamente como retired. O simulador deve gerar as chaves apenas se modelar dados históricos, e nunca como campos correntes. Fonte: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html

7. **`ProductFields` tem limites contraditórios entre fontes.** A API afirma *"Can contain up to 50 key-value pairs. For each key-value pair, the key can contain up to 128 characters, and the value can contain up to 2048 characters."* A mesma frase aparece no User Guide. Contudo o User Guide lista `aws/securityhub/CompanyName` como chave usada para filtragem por API enquanto a consola usa `CompanyName` — e afirma explicitamente *"Security Hub CSPM does not synchronize those two attributes."* Registamos a assimetria. Fontes: https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html e https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html

8. **`Tags` em `Resources[]` é populado via operação de outra API.** O User Guide afirma que o Security Hub chama `GetResources` da AWS Resource Groups Tagging API através da service-linked role para obter as tags. Não é um campo que o finding provider possa simplesmente escrever. Fonte: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-resources-attributes.html

9. **`Severity` é obrigatório num documento e opcional no outro.** A página *Required top-level ASFF attributes* afirma *"The following top-level attributes … are required for all findings"* e inclui `Severity`. O schema da API `AwsSecurityFinding` marca `Severity` como `Required: No` (apenas `AwsAccountId`, `CreatedAt`, `Description`, `GeneratorId`, `Id`, `ProductArn`, `Resources`, `SchemaVersion`, `Title` e `UpdatedAt` são `Required: Yes`). Registamos os dois. Fontes: https://docs.aws.amazon.com/securityhub/latest/userguide/asff-required-attributes.html e https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html

10. **`GeneratorDetails` e `AwsAccountName` só existem na API Reference, e `RiskAssessment` só existe no User Guide.** Três campos documentados num documento e ausentes no outro. Nenhum foi removido desta spec; todos estão marcados com a sua fonte individual. Fontes: https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_AwsSecurityFinding.html e https://docs.aws.amazon.com/securityhub/latest/userguide/asff-top-level-attributes.html
