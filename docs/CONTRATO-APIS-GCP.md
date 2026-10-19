# Contrato oficial das APIs GCP que o `gcp_rest_fixtures` emula (G11)

> Idioma: **Português** | [English](CONTRATO-APIS-GCP.en.md)

> **Este documento chama-se CONTRATO-APIS-GCP.md e trata das APIs do Google Cloud.** O contrato do
> **OCSF da AWS** (levantado para o item E5) está em seção própria no fim do arquivo, com a
> indicação de que pertence a outro provedor — o nome do arquivo não acompanhou o segundo uso.

Levantamento executado em **2026-10-14**, por leitura somente-leitura. Existe para que a auditoria
das famílias não tenha de ser refeita: cada linha traz a **URL da fonte** e o **trecho** que a
sustenta. O renderer em questão (`render/gcp_rest_fixtures.py`, 590 linhas, 13 fixtures) declara em
comentário que os envelopes são *"best-effort official-shaped"* com `TODO-verificar #7` em quase
todo campo — este documento substitui a memória pela fonte.

## As seis famílias, e o estado de cada uma

| # | Família | Método | Fixtures | Spec escrita | Confere? |
|---|---|---|---|---|---|
| 1 | Cloud Asset Inventory | `searchAllResources` | `cai_search_all_resources.json` | **sim** (`gcp/asset-search-all-resources`) | auditoria em dois níveis; `resourceUuid` fora do artefato novo |
| 1b | Cloud Asset Inventory | `searchAllIamPolicies` | `cai_search_all_iam_policies.json` | não | envelope e campos conferem; `resourceUuid` a mais |
| 1c | Cloud Asset Inventory | `analyzeIamPolicy` | `cai_analyze_iam_policy.json` | não | corpo mínimo, não auditado |
| 2 | Security Command Center | `sources.list` | `scc_sources.json` | não | campos conferem |
| 2b | Security Command Center | `findings.list` | `scc_findings.json` | não | envelope confere; `resourceUuid` a mais, e `resourceName` sintético |
| 3 | Recommender | `recommendations.list` | `recommender_recommendations.json` | não | envelope confere; `resourceUuid` a mais; `projects/-` no corpo |
| 3b | Recommender | `insights.list` | `recommender_insights.json` | não | idem |
| 4 | Cloud Billing Catalog | `services.list` | `catalog_services.json` | não | **nenhum campo desconhecido** |
| 4b | Cloud Billing Catalog | `services.skus.list` | `catalog_skus.json` | não | **nenhum campo desconhecido** |
| 5 | Cloud Monitoring | `timeSeries.list` | `monitoring_time_series.json` | não | campos conferem; 2 labels não oficiais |
| 5b | Cloud Monitoring | `metricDescriptors.list` | `monitoring_metric_descriptors.json` | não | campos conferem |
| 5c | Cloud Monitoring | `alertPolicies.list` | `monitoring_alert_policies.json` | não | campos conferem; junção em `userLabels` |
| 6 | Cloud Billing Budgets | `budgets.list` | `budgets.json` | não | **nenhum campo desconhecido** |

**Nenhum erro de envelope foi encontrado:** todos os dez nomes de campo de lista que o renderer usa
(`results`, `listFindingsResults`, `recommendations`, `insights`, `services`, `skus`, `timeSeries`,
`metricDescriptors`, `alertPolicies`, `budgets`, `sources`) estão **corretos** nos documentos
oficiais. O problema do renderer não é a forma do envelope — é o campo de junção que ele acrescenta.

## Fontes (URL + HTTP + revisão)

| Chave | URL | HTTP | Revisão |
|---|---|---|---|
| CAI | `https://www.googleapis.com/discovery/v1/apis/cloudasset/v1/rest` | 200 | `20261010` |
| SCC | `https://www.googleapis.com/discovery/v1/apis/securitycenter/v1/rest` | 200 | `20261009` |
| REC | `https://www.googleapis.com/discovery/v1/apis/recommender/v1/rest` | 200 | `20261004` |
| CAT | `https://www.googleapis.com/discovery/v1/apis/cloudbilling/v1/rest` | 200 | `20261002` |
| MON | `https://www.googleapis.com/discovery/v1/apis/monitoring/v3/rest` | 200 | `20260924` |
| BUD | **`https://www.googleapis.com/discovery/v1/apis/billingbudgets/v1/rest`** | **404** | — |
| BUD-API | `https://billingbudgets.googleapis.com/$discovery/rest?version=v1` | 200 | `20261011` |
| CAI proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/asset/v1/assets.proto` | 200 | — |
| SCC proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/securitycenter/v1/finding.proto` | 200 | — |
| REC proto | `https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/recommender/v1/recommendation.proto` | 200 | — |
| NAMES | `https://docs.cloud.google.com/asset-inventory/docs/asset-names` | 200 | — |
| MONRES | `https://cloud.google.com/monitoring/api/resources` | 200 | — |
| AIP159 | `https://google.aip.dev/159` | 200 | — |
| PROTOJSON | `https://protobuf.dev/programming-guides/json/` | 200 | — |
| PROTO3 | `https://protobuf.dev/programming-guides/proto3/` | 200 | — |
| PYJSON | `https://googleapis.dev/python/protobuf/latest/google/protobuf/json_format.html` | 200 | — |

**Notas de citação que custaram para descobrir:**

* `https://www.googleapis.com/discovery/v1/apis/billingbudgets/v1/rest` **não existe** (404); a
  família 6 só é citável por `https://billingbudgets.googleapis.com/$discovery/rest?version=v1`.
* `https://cloud.google.com/asset-inventory/docs/resource-name-format` **redireciona**
  (cross-origin) para `https://docs.cloud.google.com/asset-inventory/docs/asset-names`.
* As páginas do `docs.cloud.google.com` **não servem para os métodos de lista**: a navegação
  consome o orçamento do fetch antes das tabelas de campos. O caminho que funciona é o *discovery
  document* (111 KB a 478 KB) e o `.proto` — ambos em máquina.

## O achado principal: `resourceUuid`

**`resourceUuid` ocorre ZERO vezes nos seis documentos oficiais completos.** Ele não é campo de
`ResourceSearchResult`, `IamPolicySearchResult`, `Finding`, `Recommendation`, `Insight` nem
`AlertPolicy`. É uma chave de junção entre planos que o renderer **inventou** — o próprio código a
chama de *"synthetic cross-plane join key (P2)"*.

| # | Endpoint | Onde | Emitido em |
|---|---|---|---|
| 1 | CAI `searchAllResources` | topo do resultado | `gcp_rest_fixtures.py:119` |
| 2 | CAI `searchAllIamPolicies` | topo do resultado | `:140` |
| 3 | SCC `findings.list` | topo do finding | `:206` |
| 4 | Recommender `recommendations.list` | topo | `:243` |
| 5 | Recommender `insights.list` | topo | `:270` |
| 6 | Monitoring `alertPolicies.list` | **já migrado** para `userLabels.resource_uuid` | `:529` |

### O risco, medido com a documentação oficial

O código do próprio renderer registra, para a família 6, o efeito que o motivou a migrar o campo:

> *"this body is parsed into the CLIENT's own AlertPolicy proto, which declares no top-level
> resourceUuid and rejects the whole response when one is present (measured: ParseDict fails with
> 'has no field named resourceUuid')"*

A documentação oficial confirma a regra e **delimita o risco**:

* **JSON → proto rejeita por padrão.** `google.protobuf.json_format.ParseDict(js_dict, message,
  ignore_unknown_fields=False, …)` — *"ignore_unknown_fields – If True, do not raise errors for
  unknown fields"*; e a guia ProtoJSON: *"The Protobuf JSON parser should reject unknown fields by
  default but may provide an option to ignore unknown fields in parsing"* e *"Any key validity
  checking should still occur (disallowing unknown fields)"*.
* **gRPC binário NÃO rejeita.** O payload gRPC é protobuf binário, e o proto3 *"preserve[s] unknown
  fields and include[s] them during parsing and in the serialized output"*. Ou seja: o mesmo corpo
  que quebra via `ParseDict` **passa em silêncio** pelo transporte gRPC — e o campo desconhecido
  ainda se perde se o cliente reserializar para JSON (*"Serialize a proto to JSON"* está na lista
  do que descarta campos desconhecidos).

**Consequência prática, e é o que muda a decisão:** o campo é sempre **não documentado** (isso basta
para a fidelidade), mas o efeito **depende do transporte**. Como o consumidor usa os dois caminhos
(`client.py (modulo do consumidor)` constrói clientes gRPC; os fixtures são JSON), a remoção é correta por
fidelidade e *potencialmente* necessária por função — não é uma falha garantida em produção. Isso
está dito assim em `specs/gcp/asset-search-all-resources.schema.json` e no relatório de proveniência
do renderer novo, para não trocar uma imprecisão por outra.

## Campos com valor sintético dentro de campo real (→ `unverified`, não remoção)

| Família | Campo | Problema | Evidência |
|---|---|---|---|
| CAI | `name` | serviço sempre `cloudresourcemanager.googleapis.com` e path `projects/<p>/<type>/<name>`, sem `zones/{zone}`/`locations/{loc}` | NAMES publica o formato **por tipo**: `//compute.googleapis.com/projects/PROJECT_ID/zones/ZONE/instances/INSTANCE`, `//cloudsql.googleapis.com/projects/PROJECT_ID/instances/INSTANCE`, `//container.googleapis.com/projects/PROJECT_ID/locations/LOCATION/clusters/CLUSTER`, `//storage.googleapis.com/BUCKET` |
| CAI | `assetType` | `<tipo_interno>.googleapis.com/Resource` | o proto exemplifica `compute.googleapis.com/Disk`; NAMES publica `compute.googleapis.com/Instance` |
| SCC | `resourceName` | `//cloudasset.googleapis.com/<uuid>` — UUID puro onde se espera path | o campo admite string de cliente, mas [NAMES] exige `//<serviço>/<path>` |
| SCC | `sourceProperties.Explanation` / `.Recommendation` | chaves livres; **não encontrei** enumeração oficial | o contrato só diz que as chaves são geridas pela fonte |
| SCC | `name`/`parent` source number | int64 sintético na **forma** correta | o próprio código admite |
| REC | `name` | `projects/-/…` no **corpo da resposta** | AIP-159: *"The resource name in the response must use the canonical name of the resource, with actual parent collection identifiers (instead of - )"* |
| MON | `resource.labels.resourcePath`, `resource.labels.resourceUuid` | não são labels **declarados** para `gce_instance` (project_id/instance_id/zone) nem `cloudsql_database` (project_id/database_id/region) | MONRES publica o conjunto fechado por tipo |
| MON | `userLabels.resource_uuid` | chave schema-válida, **não canônica** | o contrato declara o mapa e as regras de chave, não essa chave |
| MON | `metric.type` | valor **não verificável** nas fontes buscadas | `metrics_gcp` é renderizado por JS (0 ocorrências das strings no HTML); declarar `unverified`, **não** inexistente |
| CAT | `serviceId`/`skuId`/`name` | formato `services/{id}` correto; id derivado do nome do serviço | a doc exemplifica `6F81-5844-456A` / `D041-B8A1-6E0B` |
| BUD | `name` | formato correto; o contrato **não impõe** formato ao `budgetId`, então UUID é aceitável | — |

## O que **não** foi verificado (dito, não omitido)

1. Nenhuma enumeração oficial das chaves `Explanation`/`Recommendation` de `sourceProperties`.
2. Nenhuma frase oficial que diga literalmente que gRPC não falha com campo desconhecido — a
   conclusão acima é a **combinação** de duas afirmações oficiais (payload binário + preservação de
   campo desconhecido), não uma frase única.
3. Nenhuma verificação oficial dos valores de `metric.type`.
4. Nenhuma verificação oficial dos ids `google.compute.instance.MachineTypeRecommender` e
   `...MachineTypeInsight` (o catálogo de recommenders não foi consultado).

---

# Contrato OCSF do Security Hub (AWS) — levantado para o item E5

**Este bloco é de outro provedor.** Fica aqui porque o item E5 nasceu da mesma sessão, e o nome do
arquivo não acompanhou o segundo uso — está dito no topo para que ninguém procure OCSF num
documento chamado "APIS-GCP".

## O achado que reorienta o E5

O E5 foi escrito como *"reespecificar `aws/security-hub-asff` para `CSV`/`OCSF_JSON`"*. Ao ler a
spec atual, ela **já documenta** o achado:

> *"ASFF is NOT an available export format. SelectedFields accepts OCSF field paths only, so ASFF
> and the S3 export are two different formats of the same source."*

E a fonte primária confirma, na própria página da operação de export:

> *"Specify the destination bucket and AWS KMS key in the `Destination` parameter, and the output
> format (`CSV` or `OCSF_JSON`)"* — [StartExportJobV2](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.html), HTTP 200 em 2026-10-14

**Consequência:** a superfície `aws/security-hub-asff` **não está errada** — ela descreve os
encontros no formato que a API do Security Hub devolve (`AwsSecurityFinding`, 96 colunas, 0 não
comprovadas). O que o D3(c) pede não é reescrevê-la: é **acrescentar a superfície do formato que a
AWS exporta**, que não existe. São duas superfícies do mesmo dado, e a atual é a outra metade.

## A cadeia de herança do OCSF (para o formato do export)

Fonte: o repositório normativo do OCSF, arquivo por arquivo, HTTP 200 em 2026-10-14.

| Peça | Arquivo | O que fixa |
|---|---|---|
| Classe | [`events/findings/compliance_finding.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/events/findings/compliance_finding.json) | `uid: 3`, `name: compliance_finding`, `extends: finding`; torna `compliance` **required** e acrescenta `evidences`, `remediation`, `resource`†, `resources` |
| Base | [`events/findings/finding.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/events/findings/finding.json) | `extends: base_event`; torna `finding_info` **required**; declara `activity_id` (1 Create, 2 Update, 3 Close), `status_id` (1 New … 6 Deleted), `confidence_id`, `resources`, `vendor_attributes`, `time`, `start_time`, `end_time`; aplica o profile `incident` |
| Objeto | [`objects/finding_info.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/finding_info.json) | `uid` **required**; `title` recommended; `desc`, `types`, `analytic`, `created_time`, `src_url`, `tags`, `attacks`, `product`… |
| Objeto | [`objects/compliance.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/compliance.json) | `status_id`: **1 Pass, 2 Warning, 3 Fail**; `control`, `standards`, `requirements`, `checks`, `status`, `status_code`, `desc` |
| Objeto | [`objects/metadata.json`](https://raw.githubusercontent.com/ocsf/ocsf-schema/main/objects/metadata.json) | `product` **required**, `version` **required** ("the version of the OCSF schema"); `log_name`, `reporter`, `source`, `tenant_uid` recommended |

† `resource` está `@deprecated` desde 1.3.0 com `superseded_by: ["resources"]` — o renderer deve
usar `resources`, e o `resource` singular **não** deve ser emitido.

**O `version` é obrigatório e tem de ser uma versão LANÇADA.** O `main` do repositório traz
`{"version": "1.10.0-dev"}` — um pré-lançamento, que não serve para um campo obrigatório de um
artefato. A última lançada, verificada na API de releases do repositório, é **`1.9.0`**
(`tag_name: "1.9.0"`, `prerelease: false`, publicada em 2026-08-03). A mesma checagem de versão
vale para `metadata.product.version` — que é a versão do **produtor**, não a do OCSF.

## O que o estado do simulador sustenta projetar

Lido de `render/security_hub.py:552-621` (o mapeamento ASFF, que já projeta os mesmos fatos):

| OCSF | Origem no estado |
|---|---|
| `finding_info.uid` | `NativeFinding.finding_id` |
| `finding_info.title` / `.desc` | `title` / `description` |
| `finding_info.types` | `finding.types` |
| `finding_info.created_time` | `raised_on` (como o ASFF usa em `CreatedAt`) |
| `severity_id` | `severity` — **RESOLVIDO em 2026-10-15**: o enum do OCSF foi lido no `dictionary.json` (tags 1.6.0 e 1.9.0, idênticos) e o literal nativo é normalizado para a legenda (`LOW` → `"Low"`, **2**) |
| `resources[].uid` / `.name` / `.region` | `Resource` do achado: ARN/uuid, `resource_name`, `region_id` |
| `metadata.product.name` / `.vendor_name` | `finding.product_name` / `company_name` |
| `metadata.version` | **constante `1.9.0`**, e não um valor do estado |
| `metadata.log_name` | o nome do arquivo do export, que a superfície fixa |
| `status_id` | `finding.status` — o ASFF já faz o mapa (`_RECORD_STATE: open -> ACTIVE`) |
| `compliance.status_id` / `.control` / `.standards` | **NÃO modelado** — o ASFF também emite `Compliance: None`, com a justificativa registrada de que o modelo não carrega framework nem controle |

## O que **não** foi levantado (dito, não omitido)

1. **A lista completa de atributos de `base_event`** (onde vivem `metadata`, `severity_id`, `time`,
   `class_uid`, `category_uid`, `type_uid`) — não foi lida nesta execução. *(Parecia esse arquivo,
   mas `base_event.json` **não existe** em nenhuma tag: os atributos base vivem no
   `dictionary.json` da raiz, de 258 KB. Foi aí que a enum de `severity_id` foi encontrada.)*
2. **A classe que o export do Security Hub realmente emite.** O candidato natural é
   `compliance_finding` (uid 3), mas **nenhuma página consultada afirma qual classe a AWS usa**.
   Escrever a spec contra `compliance_finding` sem essa confirmação é uma **suposição**, e a spec
   teria de a registrar como não comprovada. *(Reconssultado em 2026-10-15 — ver "O residual
  procurado de novo".) O que apareceu foi `class_name` como caminho publicado do export, e nenhum
  identificador numérico.*
3. **A forma exata do arquivo de export**: se é JSON por linha (`.jsonl`), um array, ou um arquivo
   por página, e qual o `ObjectPrefix`/particionamento. A spec atual já registra que o
   `path_template` **não é documentado** (só o `ObjectPrefix`, até 512 chars).
4. **O mapeamento `severity` -> `severity_id`** do OCSF: a enum não foi lida. *(Cumprido em
   2026-10-15 — ver "A lacuna que a busca fechou" abaixo.)*

**Onde isso deixa o E5:** **FECHADO em 2026-10-14** — a superfície `aws/security-hub-ocsf-export`
foi escrita, e as duas peças que faltavam foram **resolvidas ou declaradas**, cada uma pelo seu
lado:

* **A forma do arquivo: RESOLVIDA.** A página do `FindingsOutput` publica que `OCSF_JSON`
  *"produces newline-delimited JSON records"* — JSON por linha, e não um array. Essa é a forma do
  artefato entregue.
* **A classe OCSF: DECLARADA COMO LACUNA.** A lista de campos que a AWS publica **recusa** a
  analogia com o `compliance_finding`: ela mistura campos de `vulnerabilities`, `malware`,
  `databucket` e `evidences`, o que indica que o export não usa uma classe só como envelope. Os
  identificadores `class_uid`/`category_uid`/`type_uid` ficam **fora** do artefato e em `unverified`
  na spec — e o teste golden exige que não sejam emitidos.
* **O `metadata.version`: DECLARADO COMO LACUNA**, pela mesma razão: a última revisão LANÇADA do
  OCSF é `1.9.0`, e a AWS não afirma qual revisão o seu export usa. *(Reconssultado em 2026-10-15:
  a AWS passou a ter **uma** frase sobre versão — *"Security Hub currently supports findings in
  OCSF schema version 1.6"* — e ela **não** resolve. Ver abaixo.)*
* **O particionamento: DECLARADO COMO LACUNA** — a AWS publica apenas o `ObjectPrefix`.

## A fonte que fechou o item: `FindingsOutput`

| URL | HTTP | O que ela fixa |
|---|---|---|
| [`API_FindingsOutput.html`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html) | 200 | **`Format`: `CSV \| OCSF_JSON`**; *"`OCSF_JSON` produces newline-delimited JSON records in the Open Cybersecurity Schema Framework (OCSF) format"*; **`SelectedFields` não é suportado em `OCSF_JSON`** (o formato inclui o achado inteiro, e enviá-lo devolve `ValidationException`); e a lista de ~120 caminhos OCSF com os nomes de campo que a AWS publica |
| [`API_ExportOutput.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportOutput.md) | 200 | A união tem **um** membro: `Findings`, do tipo `FindingsOutput` |
| [`API_StartExportJobV2.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.md) | 200 | *"the output format (`CSV` or `OCSF_JSON`)"*; entrega em S3 (`exportv2.securityhub.amazonaws.com`); o bucket policy de exemplo confirma que a AWS escreve **objetos**, com suporte a multipart upload |

**A lista de `SelectedFields` foi usada como CATÁLOGO DE CAMPOS, não como seleção.** Ela é a única
fonte da AWS que publica os **nomes de caminho** do formato OCSF do export (`metadata.uid`,
`cloud.account.uid`, `finding_info.title`, `compliance.status`, `resources.name`…), e é por isso
que as colunas da spec são esses caminhos — e **não** formas deduzidas do repositório normativo do
OCSF, que divergem: o OCSF tem `resource` **singular** (`@deprecated` desde 1.3.0, com
`superseded_by: ["resources"]`), enquanto a AWS publica `resources`.

**Uma diferença de notação que ficou registrada no teste:** a AWS publica `resources.name`, e o
achatamento de um item de array escreve `resources[].name`. O teste normaliza o `[]` e compara o
**conjunto de campos**, mantendo a spec com a grafia citável da AWS em vez de reescrevê-la para
acomodar o achatamento.

## O residual procurado de novo (2026-10-15)

Escopo desta rodada: `class_uid`/`category_uid`/`type_uid` e `metadata.version`. O residual já
estava declarado desde 2026-10-14; esta rodada é a **procura** que fecha a declaração, e não a
primeira busca. Todas as páginas foram buscadas em 2026-10-15.

| URL | HTTP | O que ela devolveu sobre as duas perguntas |
|---|---|---|
| [`securityhub-v2-findings-export.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-findings-export.html) | 200 | A página **real** da operação de export. Diz que *"JSON (OCSF) exports always contain the complete finding, so there is no column selection"*. Não menciona classe nem versão. *O slug antigo `securityhub-findings-export.html` redireciona para o índice — foi por isso que ele parecia ausente na primeira rodada.* |
| [`securityhub-ocsf.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-ocsf.html) | 200 | A **única** frase da AWS sobre versão em toda a documentação: *"Security Hub currently supports findings in OCSF schema version 1.6."* |
| [`securityhub-v2-automation-rules.md`](https://docs.aws.amazon.com/securityhub/latest/userguide/securityhub-v2-automation-rules.md) | 200 | Tabela dos campos OCSF aceitos em critérios de regra (os mesmos que o `Filters` do `GetFindingsV2` aceita). Publica `class_name`; **não** publica `class_uid`, `category_uid`, `type_uid` nem `metadata.version`. |
| [`API_FindingsOutput.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.md) | 200 | Lista **íntegra** dos caminhos válidos de `SelectedFields` — **119** caminhos. O `.md` devolve a lista inteira; o `.html` trunca no meio. Inclui `class_name`, `metadata.uid`, `metadata.product.*`, `severity_id`, `status_id`; **não** inclui nenhum dos três identificadores nem `metadata.version`. |
| [`API_OcsfFindingFilters.md`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_OcsfFindingFilters.md) | 200 | Publica só `CompositeFilters` e `CompositeOperator`; os campos entram por `FieldName` dentro de cada filtro, sem catálogo fechado. |
| [`API_GetFindingsV2.html`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetFindingsV2.html) | 200 | Mesmo formato OCSF na resposta, com paginação por `NextToken`. Sem exemplo de registro, sem versão. |
| [`ocsf-aws-extension.html`](https://docs.aws.amazon.com/securityhub/latest/userguide/ocsf-aws-extension.html) | 200 | Página da extensão OCSF da AWS (o "next" da página de OCSF). Não trata do export do Security Hub e não fixa classe nem versão. |

**O que isso decide.** Apareceram duas pistas, e nenhuma das duas é um valor:

* **`class_name`** é o único caminho de classe que a AWS publica — e publica o **nome do campo**,
  sem o identificador numérico que o OCSF define ao lado dele, e sem a lista de valores que o
  `class_name` pode assumir. Uma coluna precisa das duas metades: o nome vem da AWS, o valor não
  vem de lugar nenhum. Emitir exigiria inventar um valor de exemplo; escolher `compliance_finding`
  (uid 3) seria escolher a classe por analogia — que é o que a lista de campos já recusou ao
  mostrar `vulnerabilities.*`/`malware.*`/`databucket.*`/`evidences.*` no mesmo catálogo.
* **A frase da `1.6`** é sobre a revisão de schema que o serviço **suporta** para os achados em
  geral, não sobre o valor do campo no arquivo exportado — e a lista de campos do export nem
  publica `metadata.version`. Emitir `1.6` seria pegar o nome do campo no repositório normativo e
  o valor numa frase lateral: duas inferências sobre um campo que a AWS não documenta para esta
  superfície. Escolher `1.9.0` pelo mesmo caminho seria idêntico em espírito, e errado pela mesma
  razão. O campo continua declarado.

**Um sinal de terceiros — registrado, e explicitamente não normativo.** Um artigo do time da
Cyber Security Cloud, em japonês, publicado em 2026-05-25 e atualizado em 2026-05-28
([`zenn.dev/cscloud_blog`](https://zenn.dev/cscloud_blog/articles/securityhub-v2-overview)),
relata que uma chamada real ao `GetFindingsV2` devolveu `metadata.version: "1.8.0"` enquanto a
documentação anuncia 1.6, e lista **quatro** classes em uso no serviço (Compliance Finding 2003,
Detection Finding 2004, Vulnerability Finding 2002, Data Security Finding 2006). Nada disso entra
na spec — a regra do projeto é fonte oficial do provedor, e um blog não é fonte. Fica registrado
porque decide o mesmo ponto por outro lado: um valor que a própria documentação contradiz
publicamente não é um valor seguro para um artefato, e a existência de **quatro** classes (não uma)
confirma que o envelope do export não é uma classe só.

**Onde isso deixa o E5:** a superfície continua **fechada**, com o residual **declarado** — agora
com um motivo que é positivo, e não só ausência: a AWS publica o nome do campo da classe e não
o identificador, e publica uma versão de schema suportada que não é a revisão do arquivo. Os dois
itens seguem em `unverified` na spec, o `model_gaps` do relatório de proveniência repete os
mesmos motivos, e o teste golden continua exigindo que nada disso seja emitido. O registro dos
não comprovados estava em **299** nessa data — nenhuma lacuna foi fechada por dedução.

## A lacuna que a busca fechou: `severity_id` (2026-10-15)

O `severity_id` era a quinta entrada de `unverified` desta superfície, com um motivo honesto e
incompleto: *"a tabela literal->inteiro do OCSF não foi lida nesta execução"*. É uma lacuna que
esperava **leitura**, não decisão.

**Onde a enum realmente está.** O `spec` procurava `base_event.json` — e esse arquivo **não existe**
em nenhuma tag do repositório. Os atributos base vivem no [`dictionary.json`](https://github.com/ocsf/ocsf-schema/blob/1.6.0/dictionary.json),
na raiz, com **258 KB** na 1.6.0. Foi ele que devolveu a tabela:

| `severity_id` | legenda | | `severity_id` | legenda |
|---|---|---|---|---|
| 0 | Unknown | | 4 | **High** |
| 1 | Informational | | 5 | **Critical** |
| 2 | **Low** | | 6 | Fatal |
| 3 | **Medium** | | 99 | Other |

**Por que o número é confiável apesar de a revisão do schema continuar desconhecida.** A mesma
enum foi lida na tag `1.9.0` e é **idêntica** — mesmos valores, mesmas legendas, mesmas
descrições. Um valor que não muda entre 1.6 e 1.9 não depende de resolver a lacuna de
`metadata.version`, que segue declarada. Sem essa conferência, emitir `severity_id` seria
pendurar um artefato em cima de outra lacuna aberta.

**A busca também corrigiu o `severity`.** O dicionário define o campo de texto como *"normalized to
the caption of the `severity_id` value"* — ou seja, a **legenda** (`"High"`), não o literal. O
artefato emitia o literal **nativo em maiúsculas** (`"HIGH"`), que é o vocabulário de entrada do
modelo (`model/native.py`), não o valor que o OCSF define. O par saía inconsistente com a fonte que
o justificava, e o próprio renderer já fazia o certo no caso vizinho: `status` sai como `"New"`,
não como o `"open"` nativo. Agora `severity`/`severity_id` seguem o mesmo caminho, com uma
normalização de caixa declarada — a mesma técnica que `render/azure_defender.py` usa em
`AlertSeverity`, e pela mesma razão.

Resultado: a superfície passa a **27 colunas**, e o registro de não comprovados cai de **299 para
296** (AWS: 117 → **114**) — as primeiras lacunas fechadas por **evidência**, não por dedução.

## A leva seguinte: o `Severity.Label` do ASFF, e a tabela que ninguém tinha lido (2026-10-15)

O registro de não comprovados foi tratado como fila, e a triagem mostrou que os itens da AWS **não**
são da mesma espécie do `severity_id`: quase todos dizem *"a fonte não publica"*. Mas dois deles
eramandersos de leitura — o motivo registrava que a página **não había sido lida**:

| Item | Motivo antigo | O que a leitura entregou |
|---|---|---|
| `Severity.Label formal enum` | *"prose guidance only; the Severity API object page was not read in this iteration"* | `API_Severity.html` publica **`Valid Values: INFORMATIONAL \| LOW \| MEDIUM \| HIGH \| CRITICAL`**, cada um com o seu significado |
| `exhaustive bodies of the remaining ASFF subobjects` | *"JSON outline page response truncated"* | O limite era a **ferramenta de leitura**, não a fonte: a página é o outline **completo** (a própria AWS escreve *"complete outline"*) e tem versão `.md` |

E a mesma leitura resolveu o item que estava **declarado impossível** no modelo. O `Severity.Normalized`
saía `null` com o motivo *"as faixas 0-100 não estão na documentação consultada"*. A faixa estava; o
que faltava era a **tabela**, e ela está na mesma página:

> *"If you provide `Label` and don't provide `Normalized`, then `Normalized` is set automatically as
> follows: `INFORMATIONAL`–0, `LOW`–1, `MEDIUM`–40, `HIGH`–70, `CRITICAL`–90"*

O campo agora sai preenchido com **o número que a AWS publica**, não com um inteiro escolhido dentro
da faixa. E saiu assim por um motivo que vale registrar: `Normalized` é **deprecated quanto à
entrada** (*"instead of providing Normalized, provide Label"*), mas continua no schema e é preenchido
pelo Security Hub — e esta superfície descreve a **resposta** da API, não o que o finding provider
submete. Emitir `null` seria afirmar que o serviço devolve o campo vazio, o que é falso.

Um item **não** fechou, e a tentativa virou evidência a favor da recusa: o padrão do identificador de
Availability Zone continua sem fonte. A página do objeto `Placement` descreve `AvailabilityZone` como
`Type: String`, sem pattern — enquanto o **mesmo** objeto publica `Valid Values` para `Tenancy`
(`default | dedicated | host`). Quando a AWS tem um domínio fechado, publica; aqui ela não tem, e a
ausência é do tipo de dado, não da leitura.

## A leva do mecanismo de export (2026-10-15): seis lacunas, nenhuma fechada — e todas mais fortes

O item 5 da fila foi aplicado à superfície `aws/security-hub-asff`, cujos residuais são sobre a
**mecânica de export** (e não sobre o formato ASFF). A fonte certa não era a página do outline do
JSON, era a API do export. Todas lidas em 2026-10-15:

| URL | HTTP | O que fixa |
|---|---|---|
| [`API_Operations`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_Operations.html) | 200 | O inventário de ações: `StartExportJobV2`, `GetExportJobV2`, `CancelExportJobV2`, `ListExportJobsV2` — e o fato de `API_ExportJob` **não existir** |
| [`API_StartExportJobV2`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_StartExportJobV2.md) | 200 | `Destination`, `OutputConfiguration`, `Scopes`, `ClientToken`; `ExportJobId` com pattern `^[a-z0-9]+$`; exemplos de política com multipart upload |
| [`API_GetExportJobV2`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_GetExportJobV2.md) | 200 | A resposta **completa** do job — e a lista completa dos seus membros |
| [`API_ExportOutput`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportOutput.md) | 200 | Union: o único membro é `Findings`, do tipo `FindingsOutput` |
| [`API_ExportDestination`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_ExportDestination.md) | 200 | Union: o único membro é `S3` |
| [`API_FindingsOutput`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.md) | 200 | `Format` (`CSV | OCSF_JSON`), `Filters`, `SelectedFields` (1–50 caminhos OCSF) |
| [`API_S3ExportDestination`](https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_S3ExportDestination.md) | 200 | `BucketArn`, `KmsKeyArn` (simétrica, single-Region, ARN completo), `ObjectPrefix` (≤512, *prependido*) |

**Nenhum dos seis residuais fechou.** O que mudou foi a natureza da evidência: deixou de ser *"não
achei"* e passou a ser *"a página que descreveria isso existe, foi lida, e o membro não está lá"*.

- **`export manifest`** — `GetExportJobV2` devolve, no total, onze membros (`DataType`,
  `Destination`, `EndedAt`, `ExportJobId`, `FailureCode`, `FailureMessage`, `Name`,
  `OutputConfiguration`, `Scopes`, `StartedAt`, `Status`) e **nenhum é de manifest**. É evidência
  estrutural, não ausência de busca.
- **`ASFF to CSV column mapping`** — aqui a fonte **mudou de opinião**: a regra estava publicada e
  ninguém tinha lido. Para `CSV`, `SelectedFields` é **obrigatório**, as colunas **são** os field
  paths e saem **na ordem fornecida** (1 a 50). O console publica ainda os **nomes das nove colunas
  padrão** e um exemplo explícito — `Finding account` vem de `cloud.account.uid`. O residual foi
  **reduzido** ao que ainda falta: o path das outras oito. E a tentação ali é real, porque `Severity`,
  `Status` e `Created at` têm path obvio no contrato do OCSF — por isso continuam fora.
- **`CSV header line, quoting rules and line terminator`** — renomeado, porque metade da pergunta
  original tem resposta: o delimitador é "comma-separated rows" e o conjunto/ordem das colunas estão
  publicados. O que falta é a linha de cabeçalho em si, as regras de aspas e o terminador.
- **`export compression and encoding`** — separado o que é documentado: a **criptografia** é
  obrigatória e detalhada (SSE-KMS, chave simétrica `ENCRYPT_DECRYPT`, single-Region, ARN completo,
  mesma conta e Região). Compressão e encoding continuam sem fonte.
- **`S3 object key template`** — o `ObjectPrefix` é *prependido às chaves de objeto*, com no máximo
  512 caracteres e opcional. O template do resto da chave continua fora.

Uma correção de leitura que essa leva produziu: `delivery.format` da spec já valia `CSV|OCSF_JSON` e
o renderer já afirmava *"ASFF is NOT an available export format"*. Bastou a leitura da API para
confirmar que estava certo — **nada precisou mudar lá**, o que é o resultado que mais gosta de ver.
