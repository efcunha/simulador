# `azure/security-assessments-list` — assessments de segurança do Defender (ARM)

Superfície que fecha a **lacuna de assessments** do lado do simulador: o consumidor do FinOps
lê `security.assessments.list(scope="/subscriptions/{id}")` e filtra por
`properties.status.code` (`security.py (modulo do consumidor)`,
`AzureSecurityScanner._list_defender_findings`), e **não existia nenhuma superfície** que
publicasse essa forma. O `azure-sim` devolvia lista vazia, e o renderer de continuous export
entrega as tabelas `SecurityAlert`/`SecurityRecommendation` — que são **outro objeto**.

Fonte: [Assessments - List](https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/assessments/list?view=rest-defenderforcloud-composite-stable)
(HTTP 200, `api-version=2021-06-01`, consultado em 2026-10-18). A visão
[`latest`](https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/assessments/list?view=rest-defenderforcloud-composite-latest)
publica a **mesma** api-version e as mesmas tabelas de Definitions — foi conferida para não
haver membro publicado só em uma das visões.

## O que é e o que não é

Não é um export: é o **corpo de resposta de um GET do plano de controle ARM**, como
`azure/arm-resource-representation`. A página publica o endpoint e o envelope
`SecurityAssessmentList` e nada mais — não há caminho de blob, particionamento, compactação
nem manifesto. O arquivo entregue é um envelope por **escopo de assinatura**, no caminho que
a própria URI endereça.

O `scope` documentado aceita assinatura **ou** grupo de gerenciamento. Só a assinatura é
entregue: é o que o consumidor consulta, e o estado canônico não modela grupo de gerenciamento
da Azure.

## Por que dois conjuntos

`assessment` (34 colunas) é o `SecurityAssessmentResponse` com os objetos que ele publica;
`assessmentList` (2) é o envelope. São contratos disjuntos: um `value` dentro de cada assessment
seria inventar um campo que o recurso não tem — o mesmo tratamento que o envelope
`NetworkSecurityGroupListResult` recebe em `azure/arm-network-security-group-rules`.

## Os três campos que decidem o descarte

`properties.status.code` é uma `AssessmentStatusCode` de domínio **fechado**:

| Valor | O que a página diz |
|---|---|
| `Healthy` | The resource is healthy |
| `Unhealthy` | The resource has a security issue that needs to be addressed |
| `NotApplicable` | Assessment for this resource did not happen |

O consumidor descarta **apenas** `Healthy`. Logo `NotApplicable` **vira achado** — a página o
descreve como *"assessment for this resource did not happen"*, uma verificação que nem rodou, e
mesmo assim entra na fila de achados DEFENDER. O único código que exercita o descarte é
`Healthy`, e é por isso que o estado entrega os três.

## A severidade mora em `properties.metadata.severity`

Não existe `properties.severity` nesta resposta. A severidade é publicada em
`properties.metadata.severity` (`SecurityAssessmentMetadataProperties`), com domínio fechado
`Low | Medium | High`. É o único lugar da resposta onde ela é publicada, e é onde o renderer
escreve.

### Divergência SDK-vs-wire, medida

O consumidor lê `assessment.properties.severity`. Medido em 2026-10-18 contra o SDK que ele usa
(`azure-mgmt-security` 7.0.0, travado em `consumidor/requirements.lock`):

- `SecurityCenter(cred, sub).assessments` resolve para a **api 2021-06-01** (medido, não
  inferido: o cliente multiapi declara `DEFAULT_API_VERSION = 2024-04-01`, e `_get_api_version("assessments")`
  cai no único ramo compatível, `v2021_06_01`);
- o modelo devolvido é `SecurityAssessmentResponse`, que **achata `properties.*`** em atributos
  de topo: `display_name` ← `properties.displayName`, `status` ← `properties.status`,
  `metadata` ← `properties.metadata`;
- esse modelo **não tem atributo `properties`** — `assessment.properties.severity` levanta
  `AttributeError: 'SecurityAssessmentResponse' object has no attribute 'properties'`, que o
  `except Exception` externo engole, e o check inteiro devolve `[]` registrando
  `azure_defender_scan_failed`.

Consequências, todas **do lado do FinOps** (aqui nada é corrigido):

1. o fallback `"MEDIUM"` é **código morto** — `assessment.properties` é avaliado *antes* do
   `getattr`, então nunca chega a ser chamado;
2. mesmo corrigindo o caminho para `.metadata.severity`, o valor `"High"` precisaria de caixa
   alta como o `severity` que o achado usa (`severity = severity.upper()`).

O caminho correto por SDK é `assessment.metadata.severity`. Ver
`docs/INGESTAO-D3-SEGURANCA.md`.

## `metadata` — o que fica vazio e por quê

O domínio de `categories`, `threats`, `implementationEffort` e `userImpact` está publicado
(tabelas de enumeração), mas a página **não afirma a qual valor cada avaliação pertence**, e o
estado canônico não modela o catálogo de avaliações do Defender. Escolher um valor seria
inventar a associação, então todos saem vazios. `policyDefinitionId` sai vazio pelo mesmo
motivo: uma avaliação embutida do Defender não tem definição de política ARM para apontar, e
nenhuma página consultada exemplifica o valor.

`displayName` e `description` (nos dois níveis) saem vazios pelo mesmo motivo — o texto é do
catálogo do Defender, que o estado não tem.

## `resourceDetails` e a âncora do assessment

`properties.resourceDetails` é uma união de três variantes e o estado produz só a `Azure`
(`source: "Azure"`, literal que o próprio tipo declara). As duas `OnPremise` descrevem máquinas
híbridas sob um agente do Log Analytics, que este repositório não modela. A âncora é o
`NetworkSegment`, que é o **único objeto Azure do estado com um id ARM verdadeiro**
(`segment_id`, o mesmo que a `azure_vnet_flow_logs` entrega) — por isso `resourceDetails.id` e o
`id` do assessment saem de um id real, e não de um composto com um resource group inventado.

## A forma do `id`

Quem fixa a forma é o **exemplo de resposta**, não a prosa:

```
<id-do-recurso-avaliado>/providers/Microsoft.Security/assessments/<guid>
```

com `name` = o mesmo guid e `type` = `Microsoft.Security/assessments`. O renderer compõe o `id`
a partir do `segment_id` e do `assessment_id` do modelo — duas grafias do mesmo id não existem.

## 10 lacunas registradas

Todas em `unverified`, nenhuma delas é campo: o valor de `status.cause` (só há um exemplo,
`OffByPolicy`, e exemplo de payload não fixa vocabulário), os membros de `additionalData`, o
template de `azurePortalUri`, `policyDefinitionId`, as categorias/ameanças/esforço/impacto, os
três campos de parceiro, os dois `secret` de escrita, as variantes `OnPremise`, a página de
`nextLink` e o escopo por grupo de gerenciamento. Detalhes e motivos no `.schema.json`.