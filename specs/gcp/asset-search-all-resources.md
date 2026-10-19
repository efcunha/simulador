# `gcp/asset-search-all-resources` — Cloud Asset Inventory `searchAllResources`

Primeira superfície fechada da **G11**. O renderer `gcp_rest_fixtures` entrega este corpo desde a
Phase 3 como *"best-effort official-shaped"* — o próprio docstring dele registra `TODO-verificar #7`
no envelope e nos campos. Esta superfície substitui a memória pela fonte: o **`.proto` oficial** que
gera a documentação, campo a campo.

## Fontes, e por que estas

| Fonte | O que ela fixa | Como foi obtida |
|---|---|---|
| [`google/cloud/asset/v1/assets.proto`](https://raw.githubusercontent.com/googleapis/googleapis/master/google/cloud/asset/v1/assets.proto) | os campos das **mensagens** (`ResourceSearchResult`) | HTTP 200 em 2026-10-14 |
| [`cloudasset.googleapis.com/$discovery/rest?version=v1`](https://cloudasset.googleapis.com/$discovery/rest?version=v1) | o **método** e o **envelope** (`searchAllResources` → `SearchAllResourcesResponse`) | HTTP 200 em 2026-10-14 |

O `.proto` é a fonte que **gera** a página de referência REST, e o documento de descoberta é o
contrato que o Google publica em máquina. As páginas do `docs.cloud.google.com` foram tentadas
primeiro e **não servem para este método por fetch**: a navegação consome o orçamento da extração
antes das tabelas de campos.

## O contrato, em dois níveis

O artefato é o **corpo da resposta**, então a auditoria tem dois níveis — e conferir um contra a
união do outro acusaria ausência de tudo o que pertence ao outro:

**Envelope** (`SearchAllResourcesResponse`, escopo `response`):

| Campo | Tipo | Evidência |
|---|---|---|
| `results` | `ResourceSearchResult[]` | o discovery document declara `searchAllResources` com `response: SearchAllResourcesResponse`; o array é o campo `results` |
| `nextPageToken` | string | `next_page_token` no proto da resposta |

**Item** (`ResourceSearchResult`, escopo `resourceSearchResult`) — 6 campos, com o nome JSON em
`lowerCamelCase` como o proto3 o define:

| Campo (JSON) | Campo (proto) | Tipo |
|---|---|---|
| `name` | `name` | string |
| `assetType` | `asset_type` | string |
| `project` | `project` | string |
| `displayName` | `display_name` | string |
| `location` | `location` | string |
| `labels` | `labels` | `map<string, string>` |

**Escopo declarado, não silencioso.** O proto documenta ~30 campos em `ResourceSearchResult`
(`folders`, `organization`, `description`, `networkTags`, `kmsKeys`, `createTime`, `updateTime`,
`state`, `additionalAttributes`, `parentFullResourceName`, `versionedResources`,
`attachedResources`, `relationships`, `tagKeys`, `tagValues`, `tagValueIds`, `tags`,
`effectiveTags`, `enrichments`, `parentAssetType`, `sccSecurityMarks`). Nenhum deles é emitido
pelo artefato, e todos ficam **fora** deste contrato em vez de virarem coluna obrigatória vazia.
Ampliar o escopo é uma decisão, não um efeito colateral.

**Mapa é uma coluna.** `labels` é `map<string, string>`; a spec o nomeia como **uma** coluna de
tipo objeto, e a projeção **não abre** as suas chaves. O precedente é o `tags` do
`azure-resource-graph-virtual-machines`: quem precisa das chaves as declara com `{key}`. Abrir o
mapa na projeção produziria `labels.app`, `labels.env`… e o auditor acusaria de inventado cada
campo do mapa, porque a spec não enumera as **chaves**.

## O que **não** é emitido, e por quê

| Item | Motivo |
|---|---|
| **`resourceUuid`** | O artefato do `gcp_rest_fixtures` emite essa chave em cada resultado, como junção entre planos sintéticos. **O proto não a declara.** Em proto3, campo desconhecido não está no contrato — e o próprio código do renderer registra o efeito medido, para a família de alert policies: *"ParseDict fails with has no field named resourceUuid"*. O consumidor lê essas APIs por **gRPC** com o proto gerado, então o campo não é apenas não documentado: é um campo que pode fazer o cliente recusar a resposta inteira. Aqui a forma conforme é entregue, e a diferença entre os dois artefatos passa a ser **medível** em vez de suposta. |
| `assetType` com a forma exata | O **tipo** é publicado e o valor é emitido; a **forma** do valor não está comprovada (`<resource_type>.googleapis.com` contra o exemplo `compute.googleapis.com/Disk`). Está registrado em `unverified` — o valor entra, a dúvida fica dita. |

## Onde está cada peça

| Peça | Arquivo |
|---|---|
| Contrato | `specs/gcp/asset-search-all-resources.schema.json` |
| Projeção (compartilhada pelas famílias da G11) | `tools/synthetic_clouds/render/gcp_api_projection.py` |
| Renderer | `tools/synthetic_clouds/render/gcp_cai_search_all_resources.py` |
| Teste golden | `tools/synthetic_clouds/tests/test_gcp_cai_fidelity.py` |

## O que isto **não** resolve — e é a decisão aberta

O `gcp_rest_fixtures` **não foi tocado**: ele alimenta o emulador e tem testes que o fixam.
Aposentá-lo, ou fazê-lo emitir a forma conforme, é decisão de produto registrada em
[DECISOES-PENDENTES.md](../../docs/DECISOES-PENDENTES.md) (item **E2**), não efeito colateral desta
auditoria. As outras **5 famílias** (SCC, Recommender, Billing Catalog, Cloud Monitoring,
Budgets) seguem o mesmo método, uma por vez, e ainda não foram fechadas.
