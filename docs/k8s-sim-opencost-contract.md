# Contrato OpenCost do `k8s-sim` (Fases S4a, S4b1, S4b1-C, S4b1-E, S4b2-C, S4b2-E e S4b3-F)

> Idioma: **Português**. Sem gêmea `.en.md`: a allowlist permite **apenas** este arquivo em
> `docs/`. A gêmea em inglês fica como pendência (§9).

Levantamento executado em **2026-10-28**, por leitura somente-leitura das fontes oficiais do
OpenCost. Este documento existe para que a forma do payload não dependa da memória de ninguém:
cada linha traz **a URL da fonte** e **o trecho que a sustenta**.

**O que este documento é:** o contrato HTTP do serviço mínimo `k8s-sim` — o caminho
`/allocation/compute`, o envelope, os campos de cada allocation e o comportamento dos
parâmetros. Desde a **S4b1** ele cobre também os **clusters do estate** (o catálogo em
`k8s_sim/fixtures/clusters.json`), o parâmetro `filter`, o parâmetro `step` e a rota
`/clusterInfo`. Desde a **S4b1-C** a **identidade publicada do cluster é o `cluster_name`** — o
nome que a descoberta devolve no campo `name` — e o `cluster_id` do **fixture** (o `uuid` do
estate) é apenas auxiliar e alias (§6.1). Desde a **S4b1-E** o `filter` aceita um **terceiro
alias**: o **id nativo** que a descoberta publica (ARN do EKS, ARM id do AKS, `selfLink` do GKE) —
que é o id que o consumidor pós-C-IDENT manda — e o **nome continua sendo o valor publicado**
(§3.3, §6.1). **Atenção ao homônimo:** o `cluster_id` do `DiscoveryResult` do consumidor é o
**id nativo** (ARN/ARM id/`selfLink`), não o do fixture — a distinção está no §1.2.

**Atualizado em 2026-10-29** (revisão `9533b901`, branch `feat/p76-security-posture-gcp-azure`).
Duas coisas mudaram depois do levantamento, e as duas são datadas:

1. **O produtor do nome do EKS.** Até 2026-10-28 o `aws-sim` publicava o EKS pelo id derivado;
   desde `9533b901` publica o **nome do estate**, escopado pela conta da credencial (§6.1). Com
   isso a descoberta devolve o mesmo nome que o fixture do `k8s-sim` carrega, também no EKS.
2. **O consumidor** (F14) passou a mandar o **id nativo** no `filter`, e não o nome: o CloudPilot
   implementou o C-IDENT depois da leitura de F14 (§1.2).

**Fechado em 2026-10-29 pela S4b1-E:** o item 2 deixou de ser uma pendência. O fixture carrega
agora o **id nativo** de cada cluster (§6.1) e o `filter` o aceita como alias (§3.3), de modo que
o `k8s-sim` **serve** o consumidor pós-C-IDENT: o pedido sai 200 com `data` não vazio em
`/allocation/compute` e 200 em `/clusterInfo`. O que o simulador **publica** não mudou: continua
sendo o **nome**, que é o que o consumidor lê como display name (`opencost.py:209`).

**Atualizado em 2026-10-30 pela S4b2-C** (revisão-base `9ccbc71c`): o contrato HTTP **não
mudou** — o que fechou foi o **caminho de rede** até ele. O `k8s-sim` passou a ser anexado à
bridge do CloudPilot com o alias `k8s-sim`, e a URL **`http://k8s-sim:8089`** (§2.1) passou a
resolver **de dentro do backend do CloudPilot**. O §9 ("sem Dockerfile, compose, rede, URL") foi
corrigido: o que ainda falta é **TLS**, API server do Kubernetes, Prometheus, Kubecost, UI e
migration — o restante da S4b2. Detalhe no
[mapa de impacto](regression/mapa-impacto-s4b2c.md).

**Retificado em 2026-10-31 pela S4b3-F:** o bloco acima descreve o estado **naquela** data
(2026-10-30, S4b2-C) e é preservado como registro datado. O **TLS fechou na S4b2-E** — bloco
seguinte —: a URL que o **consumidor** usa é **`https://opencost.synthetic-clouds.test`**, e
`http://k8s-sim:8089` é o **upstream** do front na bridge (§2.1), não a rota do consumidor.

**Atualizado em 2026-10-30 pela S4b2-E**: o **TLS também fechou**. O contrato HTTP continua
igual — o que mudou é que agora ele chega ao consumidor por **HTTPS**, num nome do front
(**`opencost.synthetic-clouds.test`**, §2.1), com o certificado na folha do front e a mesma CA
de sempre. O provider `opencost` do CloudPilot foi apontado para essa URL na conta de
homologação e a leitura de custo responde por ela (5 linhas para `TEMP-aks_cluster-0025`, tanto
pelo nome quanto pelo id nativo). A pendência de TLS saiu do §9; o que continua aberto é o
restante da S4b2 (API server do Kubernetes, Prometheus, Kubecost, UI e migration) e um defeito
**pré-existente do CloudPilot** que impede o botão "Verificar Conexão" da UI de funcionar com
qualquer endpoint — detalhado no
[mapa de impacto](regression/mapa-impacto-s4b2e.md).

Os números do §6.1 e os testes do §10 foram reconferidos nesta data contra o código e o fixture;
F1–F14 permanecem como foram lidas em 2026-10-28.

**O que este documento NÃO é:** uma reconciliação de billing. **Os valores desta fase são
SINTÉTICOS.** O `k8s-sim` não lê billing, não lê preço de nuvem e não lê o cluster AKS real; a
tabela de preços do §6 é uma taxa inventada, declarada no código, para que a aritmética do custo
possa ser conferida à mão. Reconciliar esses números com uma linha de billing é trabalho da
**S4b**, e nada aqui afirma que eles reconciliam.

---

## 1. Fontes consultadas (URL + data + o que cada uma devolveu)

Todas lidas em **2026-10-28**. O código-fonte foi lido na branch `develop` do repositório
`opencost/opencost`, no commit **`e7b30fb7e40052d286aae7b4ca5b2fcb6dc3ab4f`** (último push do
repositório na data da leitura), por `gh api` — a fonte de máquina, lida localmente.

| # | Fonte | URL / caminho | O que devolveu |
|---|---|---|---|
| F1 | OpenCost — página oficial da API | <https://opencost.io/docs/integrations/api/> | HTTP 200. Documenta a Allocation API no caminho **`/allocation`**, com os parâmetros `window` (obrigatório), `aggregate`, `step`, `resolution`, `includeIdle`, `shareIdle` e `idleByNode`. Documenta `accumulate` nas APIs `/cloudCost` e `/customCost/*` como *string* (`all`/`hour`/`day`/`week`/`month`/`quarter`, default `day`). Aponta o OpenAPI da API (`docs/swagger.json`). |
| F2 | OpenCost — OpenAPI/Swagger oficial | <https://github.com/opencost/opencost/blob/develop/docs/swagger.json> | HTTP 200, 28.779 bytes. Caminhos: `/allocation`, `/assets`, `/cloudCost`, `/inferenceCost/total`, `/inferenceCost/timeseries`. Para `/allocation`: `window` (obrigatório), `aggregate`, `step` e **`accumulate` (boolean — *"If true, sums the entire window into a single result set."*)**. Esquemas: `AllocationResponse` = `{code: integer, status: string, data: [object]}`; `Allocation` = {`name`, `cpuCost`, `cpuCoreUsageAverage`, `ramCost`, `ramByteUsageAverage`, `pvCost`, `networkCost`, `sharedCost`, `externalCost`, `totalCost`, `minutes`, `window`{`start`,`end`}, `properties`: map\<string,string\>}. |
| F3 | OpenCost — página de instalação | <https://opencost.io/docs/installation/install/> | HTTP 200. Publica a URL de verificação do servidor: *"To verify that the server is running, access `http://localhost:9003/allocation/compute?window=60m`"*. É a **única fonte documental oficial que nomeia o caminho `/allocation/compute`**. |
| F4 | OpenCost — registro das rotas | `pkg/costmodel/router.go:615` | `router.GET("/allocation/compute", a.ComputeAllocationHandler)` — a rota existe e é registrada por esse nome. |
| F5 | OpenCost — handler da rota | `pkg/costmodel/aggregation.go:332` (`ComputeAllocationHandler`) | Lê `window` (`:339`), `aggregate` (`:352`), `includeIdle` (`:360`), `accumulate` (`:363`), `accumulateBy`, `step`, `idleByNode`, `shareIdle`, `sharelb`, `filter`. Recusa com **400**: `window` inválido (`:341`), `aggregate` inválido (`:355`), `accumulateBy` inválido, `step` inválido. Responde `WriteData(w, asr, nil)` (`:410`). |
| F6 | OpenCost — envelope HTTP | `core/pkg/protocol/http.go:87` (`HTTPResponse`), `:153` (`WriteData`), `:243` (`WriteError`) | `HTTPResponse{Code int "code"; Data interface{} "data"; Meta "meta,omitempty"; Message "message,omitempty"; Warning "warning,omitempty"}`. `WriteData` → HTTP 200 + `{"code":200,"data":…}`. `WriteError` → HTTP 400 + `{"code":400,"message":"…"}`. |
| F7 | OpenCost — o allocation no wire | `core/pkg/opencost/allocation_json.go:13` (`AllocationJSON`), `:197` (`AllocationSet.MarshalJSON`), `:205` (`AllocationSetRange.MarshalJSON`) | A lista completa dos campos publicados, com os nomes JSON exatos (`name`, `properties`, `window`, `start`, `end`, `minutes`, `cpuCost`, `ramCost`, `pvCost`, `networkCost`, `sharedCost`, `externalCost`, `gpuCost`, `loadBalancerCost`, `totalCost`, …). `AllocationSet.MarshalJSON` faz `json.Marshal(as.Allocations)` — **o set é um mapa chave→allocation**; `AllocationSetRange.MarshalJSON` — **o `data` é um array de sets**. |
| F8 | OpenCost — propriedades e regra da chave | `core/pkg/opencost/allocationprops.go:178` (`cluster`), `:181` (`controller`), `:183` (`namespace`), `:361` (`GenerateKey`), `:551` (`strings.Join(names, "/")`) | As tags JSON das propriedades de allocation. E a regra da chave: `GenerateKey` monta a chave com os valores das propriedades agregadas, unidos por **`"/"`**. |
| F9 | OpenCost — resolução do `accumulate` | `pkg/costmodel/aggregation.go:84-96` (`resolveAccumulateFromQuery`), `:124-140` (`resolveDefaultStepFromAccumulate`), `:135-136` (`case AccumulateOptionAll: return window.Duration()`) | Resolve o parâmetro em três passos: `all` (sem distinção de caixa) ⇒ `AccumulateOptionAll`; `ParseAccumulate` para as opções nomeadas; e, para o resto, a leitura booleana. Com `all`, o **passo** passa a ser a duração da janela (`:135-136`), o que produz **um** set para a janela toda. O handler **nunca** recusa um valor de `accumulate`. |
| F10 | OpenCost — as opções de acumulação | `core/pkg/opencost/query.go:47-79` (`AccumulateOption`, `ParseAccumulate`) | As opções são `all`, `hour`, `day`, `week`, `month`, `quarter` e `none` (vazio). `ParseAccumulate` normaliza para minúsculas e lê `quarter`, `month`, `week`, `day`, `hour` e `true`; o resto é `none`. |
| F11 | OpenCost — a leitura booleana | `core/pkg/util/mapper/mapper.go:411-419` (`GetBool`) | `GetBool` usa `strconv.ParseBool`: aceita `1`, `t`, `T`, `TRUE`, `true`, `True` como verdadeiro (e `0`, `f`, `F`, `FALSE`, `false`, `False` como falso); o que não parseia devolve o valor padrão (`false`). É essa leitura que faz `accumulate=1` significar "a janela toda". |
| F12 | OpenCost — como a acumulação soma | `core/pkg/opencost/allocation.go:1422-1456` (`Allocation.add`), `:1109-1140` (`CPUCores`, `RAMBytes`, `PVBytes`), `:3178-3214` (`AllocationSet.Accumulate`), `:3330-3340` (`accumulateByAll`) | A soma junta os campos **cumulativos** (`cpuCoreHours`, `ramByteHours`, `networkTransferBytes` e todos os custos). `cpuCores`, `ramBytes` e `pvBytes` **não** são somados: são derivados (horas somadas ÷ minutos somados ÷ 60), então um uso diário constante mantém as mesmas figuras. `AllocationSet.Accumulate` produz **um** set com o início e o fim do intervalo inteiro, e `accumulateByAll` devolve um único set. |
| F13 | OpenCost — o agrupamento de calendário | `core/pkg/opencost/allocation.go:3393-3502` (`accumulateByMonth`, `accumulateByQuarter`, `accumulateByWeek`), `pkg/costmodel/aggregation.go:171-186` (`resolveQueryWindowForAccumulate`) | O agrupamento de calendário fecha o bucket no fim do mês, do trimestre e **no sábado** (a semana começa no domingo). Para servir essas opções, o handler **expande a janela consultada** para as bordas do bucket, de modo que a resposta passa a incluir dias que o chamador não pediu. |
| F14 | **O consumidor** — provider `opencost` do CloudPilot | `backend/app/services/k8s_finops/providers/opencost.py` (leitura somente-leitura em `C:\Projetos\cloudpilot-deploy`, 2026-10-28) | O que o consumidor **realmente envia**: `get_cluster_costs` (`:313-319`) → `aggregate=namespace,controller`, `step=1d`, `accumulate=false`, `filter=cluster:"<nome>"`; `get_namespace_costs` (`:330-335`) → `aggregate=namespace`, `filter=cluster:"<nome>"+namespace:"<ns>"`; `get_workload_costs` (`:350-356`) → `aggregate=controller`, `filter=cluster:"<nome>"+namespace:"<ns>"+controller:"<w>"`; `get_cluster_health` (`:464-467`) → `GET /clusterInfo` com `filter=cluster:"<nome>"`; `test_connection` (`:544-559`) → `GET /healthz` e, só se falhar, `/allocation/compute?window=1d&aggregate=cluster`. É a **fonte de verdade da S4b1**: o que esta fase implementa é o que o consumidor envia. O valor que o consumidor escreve em `cluster:"…"` é o **nome** que a descoberta devolve (`cluster_discovery.py`; o `ConfigTab.tsx:359-376` grava o mesmo nome em `config.clusters`), e o provider o lê de volta em `properties.cluster` (`opencost.py:209`). **Ver §1.2:** em 2026-10-29 o mesmo consumidor passou a escrever ali o **id nativo** — o que a S4b1-E passou a aceitar. |

> **F14 não é fonte oficial do OpenCost** — é o **consumidor**. Ela fica registrada à parte
> de propósito: o que o OpenCost publica é uma coisa (F1–F13); o que o CloudPilot envia é outra,
> e é a segunda que define o escopo desta fase.

### 1.1 Onde as fontes oficiais discordam entre si

Registrado porque o desacordo é real e muda o que se pode afirmar:

- **`status` no `AllocationResponse`.** O Swagger (F2) publica `status: string` no envelope. O
  código (F6) **não emite `status`**: emite `code`, `data`, `meta`, `message` e `warning`. A
  **fonte de máquina prevalece** e o `k8s-sim` emite o envelope do código (F6). O `status` do
  Swagger está **desatualizado** — registrado como `unverified` no §7.
- **`accumulate` em `/allocation`.** O Swagger (F2) o publica como **boolean**; o handler (F5,
  F9, F10, F11) aceita **as duas** coisas: o `resolveAccumulateFromQuery` (F9) trata `all`
  como opção e qualquer valor truthy (`true`/`1`) como `AccumulateOptionAll`, e o
  `ParseAccumulate` (F10) aceita `quarter`/`month`/`week`/`day`/`hour`/`true`. A página da
  API (F1) só documenta `accumulate` nas APIs de cloud cost.
- **`includeIdle` em `/allocation`.** A página da API (F1) documenta; o Swagger (F2) **não**.
- **O caminho.** F1 e F2 documentam `/allocation`; F3, F4 e F5 usam `/allocation/compute`. São
  o mesmo serviço — `/allocation` é a rota que **agrega** o resultado e `/allocation/compute` é a
  que **calcula**. O `k8s-sim` serve `/allocation/compute`, que é o caminho que o provider
  `opencost` do CloudPilot chama.

### 1.2 O consumidor mudou depois deste levantamento (2026-10-29)

A F14 foi lida em **2026-10-28** e registra o que o provider `opencost` enviava **naquele dia**:
`filter=cluster:"<nome que a descoberta devolve>"`. Depois disso o CloudPilot implementou o
**C-IDENT** (repositório `C:\Projetos\cloudpilot-deploy`): o commit `dbd66cca` (2026-10-28) e os fechamentos
`7e52f377`, `30b4e70c` e `385e9759` (2026-10-29). Verificado no código do consumidor em
2026-10-29 (HEAD `b60bde8e`):

- `DiscoveryResult.cluster_id` é o **identificador nativo** do cluster — o ARN do EKS, o ARM id do
  AKS, o `selfLink` do GKE — e o nome continua sendo o rótulo
  (`backend/app/schemas/k8s_finops.py:439-460`; a descoberta preenche em
  `cluster_discovery.py:276`, `:356` e `:411`).
- `config.clusters` e `cluster_account_map` passaram a ser **keyed por esse id**
  (`cluster_discovery.py:131-137`; a UI grava a chave canônica em
  `frontend/src/pages/finops/kubernetes/tabs/ConfigTab.tsx:329` e `:450`).
- o provider `opencost` envia `filter=cluster:"<cluster_id>"`, onde `cluster_id` é esse id, nas
  três leituras de custo — `get_cluster_costs` (`:318`), `get_namespace_costs` (`:334`) e
  `get_workload_costs` (`:355`) — e lê o nome de volta de `properties.cluster` (`:209`).

**Consequência para este contrato.** O `k8s-sim` resolve o `cluster` do `filter` por **três
aliases** — o **nome**, o **uuid do estate** e o **id nativo** (ARN/ARM id/`selfLink`) — e
**publica o nome** (§3.3). Uma configuração salva **antes** do C-IDENT (keyed by name) continua
funcionando; uma configuração **nova** (keyed pelo id nativo) também: desde a **S4b1-E** o
fixture carrega o id nativo de cada cluster (§6.1) e o `filter` o aceita, de modo que o pedido
responde **200 com `data` não vazio** em `/allocation/compute` e **200** em `/clusterInfo`.

> **Dois `cluster_id` diferentes — não confundir.** No fixture do `k8s-sim` (e nos §§6.1, 7 e 9),
> `cluster_id` é o **`uuid` do estate**. No `DiscoveryResult` do consumidor (e no §1.2), `cluster_id`
> é o **id nativo**. São o mesmo nome de campo para duas coisas distintas; este documento usa a
> primeira acepção fora do §1.2 e diz qual é qual quando as duas aparecem juntas. O id nativo
> entra no fixture com o nome **`native_id`** — para que nenhum leitor confunda os dois
> `cluster_id`.

---

## 2. O endpoint

```
GET /allocation/compute
```

Fonte: F3 (documental), F4 (rota registrada), F5 (handler).

Resposta de sucesso: **HTTP 200**, corpo JSON no envelope do §4.

Erro: **HTTP 400**, corpo JSON no envelope de erro do §4. Não existe outra forma de erro: nem
422, nem 500 no caminho exercitado. Os parâmetros chegam como *strings* crus justamente para
isso — o FastAPI responderia 422 a um booleano malformado, e este contrato tem uma forma de
erro só.

Rota extra: `GET /healthz` → `{"status":"ok","synthetic":true}`, como nos outros emuladores do
simulador.

Rota extra (S4b1): `GET /clusterInfo` → descreve **um** cluster, o que o `filter` nomear:

```
GET /clusterInfo?filter=cluster:"<nome>"
```

Sucesso — HTTP 200, `{"code":200,"data":{"version":"synthetic"}}`. O cluster tem de ser um dos
309 do estate (§6.1): um `filter` ausente → **400**; um cluster que o estate não tem → **400**;
um `filter` que esta fase não lê → **400**. O `cluster_id` do estate e o **id nativo** (ARN do
EKS, ARM id do AKS, `selfLink` do GKE) são aceitos como **alias** do nome, como em
`/allocation/compute` (§3.3). O corpo é **fixo**: nenhum `nodeCount`, nenhum
`podCount`, nenhuma utilização — o estate não modela esses fatos, e publicá-los seria afirmar
alguma coisa sobre um dado que o simulador não tem. (O consumidor lê `version` e usa
`nodeCount`/`podCount` com **default 0** — `opencost.py:487-490` — então a ausência é lida
como ausência, não como erro.)

### 2.1 A URL de deploy (S4b2-C, 2026-10-30; URL HTTPS na S4b2-E)

O contrato HTTP acima é o que o `k8s-sim` serve; **onde** ele atende é uma questão de
deployment, e ela está fechada desde a S4b2-C — e passou a ser **HTTPS** na S4b2-E:

| Contexto | URL | Quem a usa |
|---|---|---|
| **Do backend do CloudPilot** | **`https://opencost.synthetic-clouds.test`** | o provider `opencost` — TLS na frente, certificado do front |
| Do front, para o upstream | `http://k8s-sim:8089` | o `nginx` do front (`upstream k8s_opencost`) e o probe em HTTP |
| Do host, para o operador | `http://localhost:8089/healthz` | o resumo do `cold-start.ps1` e a conferência manual |

**O host `k8s-sim` é um alias de rede**, criado pelo
`deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1` na bridge
`cloudpilot-deploy_cloudpilot_net`. Não é o nome do container
(`synthetic-clouds-k8s-sim-1`) nem `localhost`: do backend, só o **alias** resolve. Sem ele
o pedido falha com `URLError: <urlopen error [Errno -2] Name or service not known>` — é o
sintoma medido **antes** da fase (ver o
[mapa de impacto](regression/mapa-impacto-s4b2c.md) §4).

A porta **8089** é a do container, fixa em `compose.k8s.yaml` (`K8S_SIM_PORT: "8089"`) e
exposta pelo `Containerfile`. No host ela é `${K8S_SIM_PORT:-8089}`, declarada em
`deploy/synthetic-clouds/.env.example`.

**Desde a S4b2-E o consumidor passa pelo front TLS.** O plano Kubernetes não tem hostname de
nuvem real para imitar, então o front o serve sob um nome próprio,
**`opencost.synthetic-clouds.test`** (decidido no checkpoint da fase; `.test` é a TLD
reservada para testes, RFC 6761, e **não resolve na internet pública**). O nome é publicado
como alias na bridge, entra na folha do front como SAN (reassinada pela mesma CA — o bundle
do CloudPilot não muda) e é encaminhado ao upstream `k8s-sim:8089`. O alias `k8s-sim`
continua existindo: é o **upstream** do front e o que o probe do `ensure-cloudpilot.ps1`
mede em HTTP para provar que ele continua de pé.

Detalhe da decisão e da medição: [mapa de impacto](regression/mapa-impacto-s4b2e.md).

---

## 3. Parâmetros

| Parâmetro | O que a fonte oficial publica | O que esta fase faz |
|---|---|---|
| `window` | **Obrigatório** (F1, F2, F5). Aceita palavras (`today`, `lastweek`), durações (`30m`, `7d`), pares RFC 3339 (`2021-01-02T15:04:05Z,2021-02-02T15:04:05Z`) e timestamps Unix (`1578002645,1580681045`). Erro de parse → **400** (F5:341). | **Implementado, estreitado.** Só lê `YYYY-MM-DD,YYYY-MM-DD`, com **as duas pontas inclusivas**: `2026-10-01,2026-10-02` devolve **2** sets, um por dia. Ausente, malformado, data inexistente ou fim antes do início → **400** com o envelope de erro. As outras grafias oficiais **não** são lidas: recusadas, nunca adivinhadas. |
| `aggregate` | Aceita `cluster`, `node`, `namespace`, `controllerKind`, `controller`, `service`, `pod`, `container`, `label:LABEL_NAME`, `annotation:name`, listas separadas por vírgula, e `all` (F1, F5:32 `ParseAggregationProperties`). Valor inválido → 400 (F5:355). | **Implementado, estreitado.** Serve exatamente quatro: `namespace`, `namespace,controller`, `controller` e `cluster` — as quatro que o consumidor envia (F14). Ausente ⇒ `namespace`. **Qualquer outro valor → 400**, nomeando os suportados. A recusa é deliberada: responder a `aggregate=node` com a visão de namespace é um downgrade silencioso, e o simulador não mente sobre o que respondeu. |
| `filter` | F5 lista `filter` entre os parâmetros lidos pelo handler. O OpenCost aplica o filtro às propriedades da allocation. | **Implementado, estreitado.** A gramática é a que o consumidor envia (F14): termos `chave:"valor"` unidos por `+`. Só `cluster`, `namespace` e `controller` são lidos. `cluster` seleciona o cluster (§6.1) — pelo **nome**, que é a identidade do contrato, com o `cluster_id` do estate aceito como **alias**; `namespace` e `controller` restringem ao workload sintético. Cluster que o estate não tem → **200 com `data: []`**. Filtro malformado ou com chave que esta fase não lê → **400** (§3.3). |
| `step` | F1, F2, F5: define a duração de cada set; por default é igual à janela. `step` inválido → **400** (F5). | **Implementado, estreitado.** Só `1d` (e a ausência). O consumidor envia `step=1d` (F14). Outro valor → **400** (§3.1). |
| `includeIdle` | Boolean, default `false` (F1; F5:360 `qp.GetBool("includeIdle", false)`). Controla a alocação `__idle__` do cluster. | **Aceito e ignorado.** O estate sintético não modela recurso ocioso — não há idle para incluir — então o payload **não muda** com o parâmetro. Isso é dito no payload: o que ele afirma sobre idle é verdade nos dois casos. |
| `accumulate` | Boolean no Swagger (F2): *"If true, sums the entire window into a single result set."*. No handler (F5:363, F9): aceita `true`/`1` (⇒ `all`), `all`, `day`, `week`, `month`, `quarter`, `hour`, e `accumulateBy` com `quarter`/`none`. | **Implementado, no padrão do handler.** A resolução é a de F9/F10/F11: `all` (qualquer caixa) e qualquer valor booleano verdadeiro (`true`, `1`, `t`, `TRUE`, `True`) ⇒ **uma** janela com os custos do período somados; `day` ⇒ uma janela por dia; `false`/`0`/ausente ⇒ uma janela por dia; `week`/`month`/`quarter`/`hour` ⇒ uma janela por dia (§3.2). **Nenhum valor de `accumulate` é recusado** — o handler oficial também não recusa. |

### 3.1 O `step`: só o dia

`step` (F1, F2, F5) define a duração de cada set e, no OpenCost, **por default é igual à janela**
— o que devolve **um** set para a janela toda. Esta fase entrega **um set por dia** — ou seja,
equivale a `step=1d` —, exceto quando o `accumulate` pede a janela inteira (§3.2).

**Desde a S4b1 o parâmetro é lido.** O consumidor envia `step=1d` (F14), e essa é a única
grafia servida: `step=1d` e `step` ausente dão o mesmo passo de um dia; **qualquer outra
grafia → 400**, com o envelope de erro (`Invalid 'step' parameter: this phase supports only
'1d'.`). O passo de um dia é também o que o OpenCost usaria com `step=1d`, então aqui a
fase coincide com ele — não é um estreitamento silencioso.

`step=1h` e os buckets de calendário (`week`, `month`, `quarter`) ficam para a **S4b4**.

### 3.2 O que esta fase distingue de `accumulate`: a janela inteira, e o dia

A fase distingue **duas** formas de acumulação, e só duas:

| Forma | Como se pede | O que volta |
|---|---|---|
| **A janela inteira** | `accumulate=true` (e `all`, `1`, `t`, `TRUE`, `True`) | **uma** janela, com `window`, `start`, `end` e `minutes` cobrindo o período pedido, e os custos somados |
| **O dia** | `accumulate=day`, `false`, `0`, ausente, e qualquer outra grafia | **uma** janela por dia, o passo que a fase já fixava |

A forma "janela inteira" é a que o Swagger (F2) descreve — *"If true, sums the entire window
into a single result set"* — e é a que o handler produz: com `AccumulateOptionAll` o passo
passa a ser a duração da janela (F9, `:135-136`) e os sets são fundidos em um só (F12).

O que a soma **não** faz é somar os campos de capacidade: `cpuCores`, `ramBytes` e `pvBytes`
são derivados das horas somadas divididas pelos minutos somados (F12), de modo que um uso
diário constante **mantém as mesmas figuras** na janela acumulada. Só os campos cumulativos
(`cpuCoreHours`, `ramByteHours`, `pvByteHours`, `networkTransferBytes` e os cinco custos) escalam
com o número de dias.

**As opções de calendário (`week`, `month`, `quarter`) e a opção `hour` não são distinguidas.**
Servi-las como o OpenCost serviria exigiria **expandir a janela consultada** para as bordas do
bucket de calendário (F13, `resolveQueryWindowForAccumulate`), de modo que a resposta passaria a
incluir dias que o chamador **não pediu** — e a opção `hour` exigiria ainda uma distribuição do
uso dentro do dia, que o estate sintético não modela (ele tem **um** número por dia). Devolver um
set por dia usando o nome de um pedido de bucket de semana seria responder com outra forma;
inventar uso fora da janela seria inventar dado. A fase aceita essas grafias e devolve um set por
dia, e **isso está declarado** aqui, no contrato e no código — não é um silêncio. **Gap declarado
para a S4b** (§9).

### 3.3 O `filter`: o que esta fase lê, e o que ela recusa

A gramática é a que o consumidor escreve (F14): termos `chave:"valor"` unidos por `+`.

```
filter=cluster:"<nome>"
filter=cluster:"<nome>"+namespace:"<ns>"
filter=cluster:"<nome>"+namespace:"<ns>"+controller:"<w>"
```

| Termo | O que faz |
|---|---|
| `cluster` | **Seleciona o cluster.** O valor tem de ser um dos 309 do estate (§6.1), escrito por qualquer um dos **três aliases** aceitos: o **nome**, o `cluster_id` do estate (o `uuid`) ou o **id nativo** (ARN do EKS, ARM id do AKS, `selfLink` do GKE). Cluster que o estate não tem → **200 com `data: []`** — o pedido não selecionou nada e nada é inventado para preenchê-lo. |
| `namespace` | Restringe ao namespace do workload sintético. `namespace:"payments"` casa; qualquer outro valor não casa → **`data: []`**. |
| `controller` | Restringe ao workload sintético. `controller:"api"` casa; qualquer outro valor → **`data: []`**. |

**A identidade PUBLICADA do cluster é o NOME.** `properties.cluster` carrega o nome e
`aggregate=cluster` usa o nome como chave (§6.1, §7) — independentemente de qual alias o pedido
trouxe.

**O `filter` aceita TRÊS aliases, e publica um só.** O valor do termo `cluster` pode ser:

| Alias | O que é | Quem o manda |
|---|---|---|
| **nome** | o `resource_name` do estate — `aks_cluster-0133`, `TEMP-gke_cluster-0037`, `eks_cluster-0291` | o consumidor de 2026-10-28 (F14) e o `DiscoveryResult.name` |
| **`cluster_id`** | o `uuid` canônico do estate (o campo `cluster_id` do fixture) | rastreabilidade; aceito desde a S4b1-C |
| **id nativo** | o id que a descoberta publica: ARN do EKS, ARM id do AKS, `selfLink` do GKE (o campo `native_id` do fixture) | o consumidor pós-C-IDENT (§1.2) |

Os três são **aceitos, nunca publicados**: a resposta carrega sempre o **nome**, mesmo quando o
pedido entrou por um alias. Um pedido respondido pelo id nativo é, byte a byte, indistinguível de
um respondido pelo nome: o simulador não publica duas identidades para o mesmo cluster, e publica
a que o consumidor lê como display name (`opencost.py:209`).

**O id nativo é o único alias que separa homônimos.** Um nome é único dentro de um scope, não no
estate (§6.1): os 309 clusters carregam 160 nomes distintos, e o mesmo nome aparece em contas
diferentes. O id nativo é **único no estate** (309 ids para 309 clusters), então é ele — e só ele
— que diz *qual* dos dois clusters o pedido quer. O serviço resolve o id nativo para o **cluster
concreto**; como o payload publica o nome e o workload é o mesmo em todo cluster (§6), os dois
homônimos produzem payloads idênticos — o que muda é *qual* cluster o pedido selecionou.

> **Corrigido em 2026-10-29 (§1.2).** Até a S4b1-E o `k8s-sim` resolvia o `cluster` do `filter` pelo
> **nome** e pelo **uuid do estate** — não pelo ARN/ARM id/`selfLink`, de modo que um pedido do
> consumidor pós-C-IDENT não selecionava nenhum cluster e a resposta era **200 com `data: []`**. A
> **S4b1-E** fechou isso: o fixture carrega o id nativo (§6.1) e o `filter` o aceita.

**Um `filter` sem `cluster`** não seleciona cluster nenhum: o serviço responde pelo cluster
sintético padrão (§6.1). Um `filter` **malformado** (termo sem aspas, aspas não fechadas,
valor vazio, chave repetida) ou com uma **chave que esta fase não lê** (`pod`, `node`,
`label:…`, `service`, …) → **400**.

**Os nomes com espaço** (`aks_cluster-0160 (do not delete)`) são servidos: o valor do termo é
lido até a aspa de fechamento, e o nome viaja intacto pela query string até o `filter` (§6.1).
**Os ids nativos também viajam intactos**: nenhum deles contém `"` nem `+` — os dois caracteres
que a gramática usa como separadores (§6.1). Eles **contêm** `:` e `/`, que a gramática aceita
como parte do valor.

A recusa é deliberada, e é a mesma doutrina da recusa de `aggregate` (§3): **responder a um
pedido filtrado por `pod` com um payload não filtrado seria mentir sobre o que foi
servido.** A alternativa — ignorar o termo desconhecido — faria o consumidor receber custos de
um pod que ele pediu para excluir. O simulador prefere recusar.

A linguagem de filtro do OpenCost é muito mais larga (rótulos, anotações, `node`, `pod`,
`container`, …). Esta fase lê as **três** chaves que o consumidor envia e recusa o resto.

---

## 4. O envelope

Fonte: F6 (`core/pkg/protocol/http.go`).

**Sucesso — HTTP 200:**

```json
{ "code": 200, "data": [ … ] }
```

**Erro — HTTP 400:**

```json
{ "code": 400, "message": "Invalid 'window' parameter: …" }
```

`meta` e `warning` são omitidos quando vazios, como `omitempty` faz no Go. O `code` é o status
HTTP, exatamente como `WriteData` e `WriteError` o escrevem.

> **Desvio D1.** O OpenCost escreve o erro de `window` em **texto puro** (`http.Error`, F5:341) e o
> erro de `aggregate` no envelope JSON (`proto.WriteError`, F5:355). O `k8s-sim` usa o **envelope
> JSON nos dois**: um contrato com uma forma de erro só é mais fácil de consumir do que um com
> duas, e a forma JSON é a do `WriteError` oficial.

---

## 5. O allocation

`data` é uma **lista de allocation sets**, um por dia da janela (F7: `AllocationSetRange` é um
array; cada set é um **mapa** chave→allocation, F7:197). Cada set tem **uma** entrada, indexada
pela chave da agregação — `payments` para `aggregate=namespace`, `payments/api` para
`aggregate=namespace,controller` (§7). O exemplo abaixo é o pedido do consumidor (F14):
`aggregate=namespace,controller&filter=cluster:"aks_cluster-0133"&step=1d&accumulate=false`:

```json
{
  "code": 200,
  "data": [
    {
      "payments/api": {
        "name": "payments/api",
        "properties": {
          "cluster": "aks_cluster-0133",
          "namespace": "payments",
          "controller": "api"
        },
        "window": { "start": "2026-10-01T00:00:00Z", "end": "2026-10-02T00:00:00Z" },
        "start": "2026-10-01T00:00:00Z",
        "end": "2026-10-02T00:00:00Z",
        "minutes": 1440.0,
        "cpuCores": 2.0,
        "cpuCoreHours": 48.0,
        "ramBytes": 4294967296.0,
        "ramByteHours": 103079215104.0,
        "pvBytes": 21474836480.0,
        "pvByteHours": 515396075520.0,
        "networkTransferBytes": 53687091200.0,
        "cpuCost": 1.92,
        "ramCost": 0.576,
        "pvCost": 0.384,
        "networkCost": 1.0,
        "totalCost": 3.88
      }
    }
  ]
}
```

### 5.1 Os campos, e de onde vem cada nome

| Campo | Origem do nome | Onde esta fase o preenche |
|---|---|---|
| `name` | F7 (`AllocationJSON.Name`) | A chave do allocation: `payments`, `payments/api`, `api` ou o **nome** do cluster, conforme a agregação (§7). |
| `properties.cluster` / `.namespace` / `.controller` | F8 (`AllocationProperties`, tags JSON em `:178`, `:181`, `:183`) | O **nome** do cluster **selecionado** pelo `filter`, o namespace e o workload sintéticos. |
| `window.start` / `window.end` | F2 (`Window`), F7 | As bordas do set, em RFC 3339 UTC. |
| `start` / `end` | F7 (`AllocationJSON.Start`/`End`) | As mesmas bordas, no nível do allocation. O OpenCost os formata com `time.RFC3339` em UTC. |
| `minutes` | F2, F7 | Duração do set em minutos: `1440.0` para um dia. |
| `cpuCores`, `cpuCoreHours` | F7 | Base de cálculo do custo de CPU. |
| `ramBytes`, `ramByteHours` | F7 | Base de cálculo do custo de RAM. |
| `pvBytes`, `pvByteHours` | F7 | Base de cálculo do custo de PV. |
| `networkTransferBytes` | F7 | Base de cálculo do custo de rede. |
| `cpuCost`, `ramCost`, `pvCost`, `networkCost`, `totalCost` | F2, F7 | Os cinco campos de custo que a fase exige. |

### 5.2 Campos do OpenCost que esta fase **não** emite

O `AllocationJSON` oficial publica mais de cinquenta campos. O `k8s-sim` emite **apenas** os
listados em §5.1. Os omitidos são, em suma: `gpuCost`, `sharedCost`, `externalCost`,
`loadBalancerCost`, todos os `*CostAdjustment` / `*CostIdle`, todos os `*Average` de recurso, os
`*Bytes`/`*Hours` de PV e rede, `pvs`, `lbAllocations`, `rawAllocationOnly`,
`proportionalAssetResourceCosts`, `sharedCostBreakdown` e `gpuAllocation`.

**A omissão é o registro, não o zero.** Um campo omitido não é um campo zerado: `k8s-sim` não
modela GPU, load balancer, custo compartilhado nem custo externo, então **não há** um valor para
esses campos — publicá-los como `0.0` seria afirmar um fato sobre um recurso que este estate não
tem. A consequência prática é que a fórmula oficial do total continua valendo sobre o que é
publicado: `TotalCost()` (F7) é a soma de `cpuCost + ramCost + pvCost + networkCost` mais os
componentes omitidos, e os omitidos são zero por ausência.

### 5.3 A identidade do total

O OpenCost define `TotalCost()` como a soma dos componentes **mais** os ajustes, o idle, o custo
compartilhado, o externo, o GPU e o load balancer. Como esta fase não emite nenhum deles, a
identidade que sobra — e que o teste da fase fixa — é:

```
totalCost == cpuCost + ramCost + pvCost + networkCost
```

A igualdade vale **no bit**, não só no centavo: o total é somado **sobre os floats que vão para o
wire**, na ordem em que o contrato nomeia os componentes.

---

## 6. O estate sintético e a aritmética

O `k8s-sim` modela **um** namespace e **um** workload — os mesmos em **todos** os clusters do
estate:

| | |
|---|---|
| namespace | `payments` |
| controller | `api` |
| chave do allocation set | conforme a agregação (§7) |

O uso e a taxa são **sintéticos**, declarados em `k8s_sim/projections/allocation.py` para que a
conta possa ser refeita à mão:

| Recurso | Quantidade por dia | Preço unitário sintético | Custo |
|---|---|---|---|
| CPU | 2,0 cores → 48,0 core·h | 0,04 / core·h | `cpuCost` = **1,92** |
| RAM | 4 GiB → 103.079.215.104 byte·h | 0,006 / GiB·h | `ramCost` = **0,576** |
| PV | 20 GiB → 515.396.075.520 byte·h | 0,0008 / GiB·h | `pvCost` = **0,384** |
| Rede (egress) | 50 GiB | 0,02 / GiB | `networkCost` = **1,00** |
| | | | `totalCost` = **3,88** |

O uso é **constante por dia**: o estate cobra uma diária fixa, sem modelo de uso. O payload é
uma **função pura da janela** — nenhum relógio é lido, nenhum banco é aberto, nenhuma lista de
preços é buscada. É isso que faz duas chamadas iguais devolverem bytes iguais.

**Estes preços não são preços do Azure.** Não há nenhuma relação com Azure Retail Prices, com o
ledger do CloudPilot ou com qualquer linha de billing: são números redondos escolhidos para a
aritmética ser conferível. Reconciliação é S4b.

### 6.1 Os clusters do estate: o fixture `clusters.json`

**O fixture é DADO, derivado do estate.** Ele mora em
`emulators/k8s-sim/k8s_sim/fixtures/clusters.json` e é gerado por
`emulators/k8s-sim/scripts/export_clusters.py`, a partir do `resources.parquet` canônico do
perfil **`123-medium-USD`** (seed 123, profile `medium`), filtrando os três tipos de recurso de
cluster Kubernetes: `eks_cluster`, `gke_cluster` e `aks_cluster`.

| | |
|---|---|
| clusters | **309** |
| EKS (AWS) | **75** |
| GKE (GCP) | **111** |
| AKS (Azure) | **123** |
| campos por registro | `cluster_id`, `cluster_name`, `native_id`, `provider`, `region_id` |
| nomes distintos | **160** (o estate reusa o nome entre scopes) |
| ids nativos distintos | **309** (o id nativo é único no estate) |

**A identidade PUBLICADA do cluster é o `cluster_name`** — a coluna `resource_name` do estate, que é
o que a descoberta do CloudPilot devolve no campo `name`. O `cluster_id` — o `uuid` canônico do
estate — é **auxiliar**: fica no fixture para rastreabilidade e é aceito como **alias** do nome no
`filter`, mas nunca é publicado (§3.3).

**O `native_id` é o id que a descoberta publica**, e é aceito como **alias** pelo mesmo motivo: é
o valor que o consumidor pós-C-IDENT manda no `filter` (§1.2). Ele entra no fixture com esse nome
— e não como `cluster_id` — porque `cluster_id` já significa outra coisa no `DiscoveryResult` do
consumidor (§1.2).

**O `native_id` é derivado das PRÓPRIAS projeções das descobertas, não reimpresso.** O exportador
é ferramenta de desenvolvimento, então pode importar os pacotes dos emuladores e pergunta a cada
descoberta o id que ela publica:

| Provider | Descoberta | Função | Forma do id |
|---|---|---|---|
| EKS (AWS) | `DescribeCluster` | `aws_sim.projections.eks.cluster_arn` | `arn:aws:eks:<region>:<account>:cluster/<nome>` |
| GKE (GCP) | listagem de clusters | `gcp_sim.projections.container.cluster(...)["selfLink"]` | `projects/<projeto>/locations/<região>/clusters/<nome>` |
| AKS (Azure) | `managedClusters.list` | `azure_sim.projections.arm.resource_id_for` | `/subscriptions/<guid>/resourceGroups/<rg>/providers/Microsoft.ContainerService/managedClusters/<nome>` |

Reimplementar os três formatos no exportador seria o caminho para um id que **divergiria** das
descobertas — e um id divergente é um id que o consumidor não tem. A regra do exportador é, então:
**perguntar à descoberta**.

O GUID da subscription do AKS **não é inventado**: o ARM id carrega o GUID que
`azure_subscription_guid(seed, scope)` minta, e o `seed` é lido do `meta.json` do próprio snapshot
do estate (o sidecar que o serializador escreve ao lado do parquet), não assumido. Um GUID mintado
de outro seed nomearia uma subscription que não existe — e o id estaria errado de um jeito que
ninguém veria.

> **Medido em 2026-10-29:** os 309 `native_id` do fixture são **byte a byte** iguais aos ids que as
> descobertas publicam sobre os **mesmos** clusters do estate reconstruído (`build_estate(seed=123,
> profile="medium", currency="USD")` + `apply_all`), comparados um a um por `uuid`: 309/309 iguais.
> São **309 valores distintos**, e nenhum deles colide com um nome ou com um `uuid` do estate.

**O nome não é único no estate, e isso é medido, não suposto.** Os 309 clusters carregam **160**
nomes distintos: o gerador reusa um nome entre scopes (o mesmo `aks_cluster-0133` aparece em
`sub-01`, `sub-02` e `sub-03`, com três `uuid` diferentes). Medido em 2026-10-28 e reconferido em
2026-10-29 sobre o snapshot `2026-10-27` do `resources.parquet` canônico:
`unique (nome, scope) == 309`, `unique (nome, região) == 160`, nenhum nome atravessa dois
provedores ou duas regiões, e os 309 `uuid` são distintos. Por isso o catálogo guarda **todos os
309 clusters** — um registro por cluster do estate — e o nome identifica o cluster **dentro do
seu scope**. Nenhum nome é inventado: os 160 são os que o estate publica.

**Os nomes são ruidosos, e o ruído é contrato.** O gerador escreve `TEMP-gke_cluster-0037`,
`aks_cluster-0160 (do not delete)`, `*_FINAL_v2`, `*COPY` — **15** nomes distintos carregam
espaço (17 registros, porque dois deles se repetem entre scopes). O simulador carrega o nome
**verbatim**: é esse o valor que o consumidor tem em mãos, e um nome "corrigido" seria um cluster
que o consumidor não reconhece. Nenhum nome do estate contém `"`, `+` ou `/` — os três caracteres
que a gramática do `filter` usa como separadores (§3.3). **O mesmo vale para o `native_id`**:
nenhum dos 309 contém `"` nem `+`, de modo que o id nativo atravessa o `filter` sem precisar de
escape. Eles **contêm** `:` e `/` (o ARN, o ARM id e o `selfLink` têm os dois), e a gramática os
aceita como parte do valor — nenhuma mudança de parsing foi necessária.

**Homônimos entre scopes: o nome não basta, o id nativo basta.** Quando dois registros do fixture
compartilham o nome, o `filter` com **nome** seleciona o **primeiro na ordem do fixture** (por
nome, depois por id) — determinístico, e o payload é indistinguível entre os dois homônimos porque
o workload é o mesmo em todo cluster (§6). O `filter` com **id nativo** seleciona o cluster
**concreto**: o id nativo carrega o scope (a conta no ARN, a subscription no ARM id, o projeto no
`selfLink`), então ele diz qual dos dois o pedido quer. No EKS isso é medido: os **75** clusters
carregam **40** nomes distintos — 25 por conta, únicos dentro da conta — e o `9533b901` é
justamente o que fez a descoberta passar a devolver esses nomes um a um, escopada pela conta.

**O serviço não importa o gerador.** O `k8s-sim` lê o arquivo; `tools.synthetic_clouds` não é
dependência de runtime do pacote (o `pyproject.toml` do `k8s-sim` declara apenas `fastapi` e
`uvicorn`). O exportador é ferramenta de desenvolvimento e usa `pyarrow`, que por isso não
entra nas dependências do serviço. O mesmo vale para os **projeções dos emuladores**: o
exportador os importa (é ele que deriva o `native_id` perguntando a cada descoberta), e para isso
acrescenta as raízes de `emulators/aws-sim`, `emulators/gcp-sim` e `emulators/azure-sim` ao
`sys.path` — o serviço em runtime não faz isso e não precisa.

**Quando regenerar.** Sempre que o estate mudar. O fixture é ordenado por `cluster_name` (com o
`cluster_id` desempatando) e **não carimba horário**, então regerar a partir de um estate
inalterado reproduz o arquivo byte a byte: um diff no fixture significa que o estate mudou.

```powershell
.\.venv\Scripts\python.exe emulators\k8s-sim\scripts\export_clusters.py
```

> **Medido em 2026-10-28, reconferido em 2026-10-29:** as tuplas
> `(uuid, resource_name, provider, region_id)` dos 309 clusters são **idênticas** em todos os
> snapshots `123-medium-USD` do estate (os diários de 2026-10-16 a 2026-10-27 e o snapshot
> `gcp-plane`). A escolha do snapshot lido não muda o fixture; o exportador, rodado nesta data
> com `--out` para um arquivo temporário, reproduziu o fixture **byte a byte**.
>
> **Idempotência medida em 2026-10-29 (S4b1-E):** duas execuções do exportador contra o mesmo
> estate produziram arquivos com o **mesmo SHA-256**
> (`579fddcd20ad4885688ff21cb23a58af583e1e2c5127433a9231e0f4df3c8419`), e esse hash é o do fixture
> **commitado** — ou seja, o fixture versionado é exatamente o que o exportador produz a partir do
> estate. O teste `test_the_fixture_is_idempotent` fixa essa propriedade (ele é pulado quando o
> checkout não tem o parquet do estate, que não é versionado).

> **As três descobertas publicam o `resource_name` do estate (verificado em 2026-10-29).** O
> `azure-sim` e o `gcp-sim` já publicavam o nome; desde `9533b901` o `aws-sim` também publica o
> EKS pelo **nome do estate** (`Resource.resource_name`), com a superfície **escopada pela conta
> da credencial** — o mesmo nome que o `k8s-sim` carrega no fixture. O id derivado
> (`cluster-<17 hex>`) deixou de ser publicado como nome e continua **aceito como alias** dentro
> da conta (`emulators/aws-sim/aws_sim/projections/eks.py:124-150`).
>
> **Cuidado com a leitura (ver §1.2).** "A descoberta devolve o `resource_name`" é verdade sobre o
> **campo `name`** do `DiscoveryResult`; o campo **`cluster_id`** é o id nativo, e é **ele** que o
> consumidor pós-C-IDENT manda no `filter`. Desde a **S4b1-E** o id nativo **também** está no
> fixture do `k8s-sim` — no campo `native_id` — e é aceito no `filter` (§3.3). A lacuna que o §1.2
> descrevia está fechada.

**O cluster padrão.** Um pedido **sem** `cluster` no `filter` é servido pelo cluster sintético
`aks-synthetic-01` — o da fase anterior, que **não** é um cluster do estate e **não** está no
fixture. Ele sobrevive porque é o que o contrato da S4a já publicava, e porque um `filter` sem
`cluster` não seleciona cluster nenhum. `filter=cluster:"aks-synthetic-01"` **não seleciona
nada**: a rota do allocation responde 200 com `data: []` (§3.3) e o `/clusterInfo` recusa com
400 (§2) — esse nome não está no catálogo.

**O workload é o mesmo em todos os clusters.** O fixture traz a **identidade** do cluster (o
nome, o provider e a região), não o seu workload: o estate sintético carrega `payments/api` em
todos eles. Por isso o custo é o mesmo em qualquer cluster — e isso é declarado, não descoberto.

---

## 7. A chave do allocation set

A regra oficial (F8) é: `GenerateKey` (`allocationprops.go:361`) monta a chave com os valores das
propriedades agregadas e os une com **`"/"`** (`:551`). A chave carrega **só as propriedades que
a agregação pediu** — e é isso que decide o formato dela.

Lendo o `switch` de `GenerateKey` (F8, `:374-404`):

| Propriedade agregada | O que entra na chave |
|---|---|
| `cluster` | `p.Cluster` |
| `node` | `p.Node` |
| `namespace` | `p.Namespace` |
| `controller` | `p.Controller`, prefixado pelo `ControllerKind` quando a allocation o tem (`deployment:api`) |
| `pod`, `container`, `service`, `label:`, `annotation:` | o valor correspondente |

O `controller` entra na chave **quando a agregação o pede**, e não porque a allocation o tem.
Com `aggregate=namespace`, o `switch` só encontra `p.Namespace`: o `controller` fica em
`properties`, como uma propriedade da allocation, e **não** na chave.

| Agregação pedida | Chave no OpenCost oficial | Chave do `k8s-sim` |
|---|---|---|
| `aggregate=namespace` | `payments` (só o namespace) | `payments` |
| `aggregate=namespace,controller` | `payments/api` — o `controllerKind` só entra como prefixo (`deployment:api`) quando a allocation **tem** `controllerKind` | `payments/api` (a allocation sintética **não** tem `controllerKind`) |
| `aggregate=controller` | `api` | `api` |
| `aggregate=cluster` | o id do cluster | o **nome** do cluster selecionado |
| `aggregate` ausente | `cluster/node/namespace/pod/container` (F5:34, o default do `ParseAggregationProperties`) | `namespace` (§3) |

**O `k8s-sim` serve as quatro agregações que o consumidor envia (F14), e a chave segue a regra
oficial em todas elas.** O mapa do allocation set é `{"<chave>": {...}}` e o `name` da
allocation é a chave sob a qual ela é arquivada — o `name` é a chave, não o nome do workload.

O `controller` continua publicado em `properties.controller` (`api`), porque é uma propriedade
real da allocation sintética — apenas não é parte da chave dessa agregação. O `cluster`
selecionado continua publicado em `properties.cluster` em todas as agregações, pela mesma
razão: as propriedades descrevem a allocation, e a agregação decide **a chave**.

---

## 8. `unverified` — o que a fonte não publica

Registro honesto do que **não** pôde ser lido na fonte, e portanto **não** foi inventado:

| Item | Situação |
|---|---|
| `status` no envelope (`AllocationResponse`) | Publicado pelo Swagger (F2), **não emitido** pelo código (F6). Divergência entre as duas fontes oficiais; o código prevalece. Não é emitido pelo `k8s-sim`. |
| `includeIdle` no Swagger de `/allocation` | A página da API publica (F1), o Swagger não (F2). O `k8s-sim` segue o comportamento do handler (F5:360), não o do Swagger. |
| `accumulate` como boolean **em `/allocation`** | O Swagger publica boolean (F2); o handler aceita as duas grafias (F5:84, F9, F10, F11). O `k8s-sim` resolve pelo caminho do handler (§3) e serve as duas formas, de modo que a ambiguidade do Swagger não o afeta. |
| `accumulate=week`/`month`/`quarter`/`hour` | O OpenCost agrupa por calendário e **expande a janela consultada** para as bordas do bucket (F13), de modo que a resposta inclui dias que o chamador não pediu; `hour` exige ainda uma distribuição intra-dia que o estate não modela. O `k8s-sim` **não distingue** essas opções: devolve um set por dia (§3.2). Declarado, não silencioso. |
| Semântica de `window` quando o fim é igual ao início | Nenhuma das fontes publica o comportamento de um intervalo de um único dia com bordas inclusivas. Esta fase devolve **1** set para `X,X` (implementação própria, por consequência da regra inclusiva do §3). |
| Nomes de campo de `properties` além de `cluster`/`namespace`/`controller` | F8 publica `node`, `container`, `controllerKind`, `pod`, `services`, `providerID`, `labels`, `annotations`, `namespaceLabels`, `namespaceAnnotations`. Esta fase publica **só os três** que a fase exige; os demais não são preenchidos. |
| Formato exato da mensagem de erro do `window` | O OpenCost escreve `Invalid 'window' parameter: %s` com o erro do parser Go (F5:341). O texto do parser **não** é reimplementado: a mensagem do `k8s-sim` é própria e o formato (`Invalid 'window' parameter: …`) é o oficial. |
| `step` diferente de `1d` | F1, F2, F5 publicam o parâmetro e o 400 do `step` inválido (F5), mas não publicam a **gramática** do que o OpenCost aceita. Esta fase serve `1d` e a ausência; o resto é 400 (§3.1). Declarado, não silencioso. |
| A linguagem de `filter` além de `cluster`, `namespace` e `controller` | F5 lista `filter` entre os parâmetros lidos, mas o **critério** com que o OpenCost casa um termo de filtro **não** foi lido nesta execução. A fase lê as três chaves que o consumidor envia e recusa as demais com 400 (§3.3). |
| O corpo de `/clusterInfo` | As fontes F1–F13 **não** publicam o corpo dessa rota. A forma `{"code":200,"data":{"version":"synthetic"}}` é a que o consumidor lê (F14 — ele usa `data.version`, e `data.nodeCount`/`data.podCount` com default 0) e a que esta fase prescreve. Nenhum `nodeCount`/`podCount` é publicado: o estate não os modela, e publicá-los seria afirmar um fato que o simulador não tem. |
| `window` na forma `1d` (o fallback do teste de conexão) | O consumidor, no `test_connection`, tenta `/healthz` **primeiro** (F14, `opencost.py:544`) e é por ele que a conexão é confirmada — o `k8s-sim` responde 200 em `/healthz`. O *fallback* (`window=1d&aggregate=cluster`, `opencost.py:556-559`) **não** é servido: uma janela de duração sem âncora exigiria ler o relógio, e o `k8s-sim` não lê relógio (§6). `aggregate=cluster` **é** servido, com a janela no formato desta fase. |

---

## 9. Fora de escopo desta fase (e o que fica pendente)

Nada abaixo foi implementado, e nada abaixo é um bug desta fase:

- **Sem billing, sem reconciliação.** Os números são sintéticos (§6). **S4b3**.
- **Sem workload por cluster.** O fixture traz a **identidade** do cluster (§6.1), não o seu
  workload: `payments/api` é o mesmo em todos os 309. O uso e a taxa são os da §6, em todo
  cluster.
- **Sem `clusterId` em `properties`.** O `AllocationProperties` oficial (F8) publica `cluster`,
  `controller`, `namespace`, `node`, `container`, `controllerKind`, `pod`, `services`,
  `providerID`, `labels`, `annotations` — e **nenhum** campo de id do cluster. A identidade que o
  contrato publica é o **nome**; o `cluster_id` do estate fica no fixture como auxiliar e como
  alias do filtro (§6.1, §3.3), e o `native_id` também — nenhum dos dois é publicado. Publicar um
  `clusterId` seria inventar um campo que a fonte não publica.
- **Sem `includeIdle` efetivo** (§3). `includeIdle` é aceito e ignorado; `accumulate` **é**
  servido, nas duas formas da §3.2; `step=1d` **é** servido (§3.1).
- **Sem `step` ≠ `1d`** (`1h`, `24h`, buckets de calendário) → **400**. **S4b4**.
- **Sem `accumulate=week`/`month`/`quarter`/`hour` distintos** (§3.2): a fase devolve um set por
  dia para essas grafias, onde o OpenCost agruparia por calendário. Declarado no contrato.
  **S4b4**.
- **Sem a linguagem de filtro do OpenCost** além de `cluster`, `namespace` e `controller**
  (§3.3): as demais chaves são recusadas com 400, não servidas.
- **Sem `Dockerfile`, `compose.k8s.yaml`, rede, TLS, URL do cluster, API server do Kubernetes,
  Prometheus, Kubecost, UI ou migration**. **S4b2**.
  **Atualizado em 2026-10-30 (S4b2-C):** a primeira metade dessa frase foi **fechada** — o
  `Containerfile` e o `compose.k8s.yaml` chegaram na S4b2-A/B, e a S4b2-C integratei o
  `k8s-sim` à rede do CloudPilot com o alias `k8s-sim` e a URL **`http://k8s-sim:8089`**
  (§2.1 e o [mapa de impacto](regression/mapa-impacto-s4b2c.md)).
  **Atualizado em 2026-10-30 (S4b2-E):** o **TLS também está fechado**. O plano é servido pelo
  front TLS sob o nome próprio **`opencost.synthetic-clouds.test`** (porta 443), com SAN na
  folha do front assinada pela mesma CA; a URL do consumidor passou a ser
  **`https://opencost.synthetic-clouds.test`** (§2.1 e o
  [mapa de impacto](regression/mapa-impacto-s4b2e.md)). Continuam **abertos**, e são o restante
  da S4b2: API server do Kubernetes, Prometheus, Kubecost, UI e migration.
- **Sem spec de máquina** em `specs/` e **sem entrada na matriz de fidelidade**.
- **Sem** wiring no provider do CloudPilot, **sem** rodar sync, **sem** validar tela. O CloudPilot
  não foi tocado **por esta fase**; ele evoluiu depois por conta própria (C-IDENT, §1.2).
  **Atualizado em 2026-10-30 (S4b2-E):** o **wiring existe** — na conta de homologação, o
  provider `opencost` do CloudPilot aponta para `https://opencost.synthetic-clouds.test` e a
  leitura de custo foi validada por ele (5 linhas, nome e id nativo). Continuam **abertos**:
  **rodar sync** (nenhum snapshot foi gravado nesta fase) e **validar tela** — o botão
  "Verificar Conexão" não chega ao provider por um defeito **pré-existente do CloudPilot**
  (a factory passa `db=` a um provider que não o aceita; ver o
  [mapa de impacto](regression/mapa-impacto-s4b2e.md) §6).
- **Sem gêmea `.en.md`** deste documento — verificado em 2026-10-29: `docs/k8s-sim-opencost-contract.en.md`
  não existe. A allowlist da fase S4b1 permitia só este arquivo em `docs/`; a gêmea fica como
  pendência declarada.

**Fechado depois do levantamento.** O nome do EKS no `aws-sim` deixou de ser pendência: desde
`9533b901` o `aws-sim` publica o nome do estate, escopado pela conta da credencial (§6.1), e o
nome que a descoberta devolve é o que o fixture do `k8s-sim` carrega — sem tradução. O valor que
o consumidor manda no `filter`, porém, mudou com o C-IDENT (§1.2) — **e a S4b1-E fechou essa
parte**: o fixture carrega o **id nativo** de cada cluster (§6.1) e o `filter` o aceita como
alias (§3.3), de modo que o `k8s-sim` serve o consumidor pós-C-IDENT. O resto da lista acima
continua valendo; em particular o billing (S4b3), `step≠1d` e os buckets de calendário (S4b4) e
a gêmea `.en.md`.

---

## 10. Onde o contrato é testado

`emulators/k8s-sim/k8s_sim/tests/test_allocation.py`, via `fastapi.testclient.TestClient`.
Medido em **2026-10-29** (após a S4b1-E): `pytest emulators\k8s-sim\k8s_sim\tests -q -p no:cacheprovider` →
**91 passed** em 11,2 s (1 aviso de depreciação do `TestClient` com `httpx`) — os 78 testes da
S4b1-C mais **13** da S4b1-E.

| O que o teste fixa |
|---|
| `/healthz` → 200 com o corpo dos emuladores irmãos |
| envelope `code`/`data`; `data` é lista |
| uma entrada por dia na janela `2026-10-01,2026-10-02` (2 janelas) |
| cada janela é um dict com a chave `payments` |
| o `name` da allocation é a chave sob a qual ela é arquivada |
| `properties.cluster` / `.namespace` / `.controller` |
| os cinco campos de custo presentes |
| `totalCost == cpuCost + ramCost + pvCost + networkCost`, no bit |
| custos finitos e não negativos |
| duas chamadas iguais devolvem o mesmo payload |
| `window` inválido, ausente, invertido ou com data inexistente → 400 |
| `aggregate` fora das quatro suportadas → 400 |
| `accumulate=true` → 200 com **uma** janela cobrindo o período e os custos somados |
| as grafias que o oficial lê como janela inteira (`true`, `1`, `t`, `T`, `TRUE`, `True`, `all`, `ALL`) → uma janela |
| a janela acumulada tem `window`, `start`, `end` e `minutes` do período inteiro |
| os custos acumulados são a soma dos dias; `cpuCores`/`ramBytes`/`pvBytes` são a média, não a soma |
| a identidade do total sobrevive à acumulação, no bit |
| `accumulate=false` / `0` / `day` → os sets diários, como sem o parâmetro |
| `includeIdle` não muda o payload |
| **o fixture tem 309 clusters — 75 EKS, 111 GKE, 123 AKS — ordenados por nome e sem repetição de id** |
| **todo registro do fixture traz `cluster_id`, `cluster_name`, `native_id`, `provider` e `region_id`** |
| **os 309 clusters carregam 160 nomes distintos — o estate reusa o nome entre scopes** |
| **o fixture traz o nome que a descoberta devolve, com o provedor certo (`aks_cluster-0133`/azure, `TEMP-gke_cluster-0037`/gcp, `eks_cluster-0291`/aws)** |
| **o `native_id` de cada cluster tem a forma que a descoberta daquele provedor publica (`arn:aws:eks:` / `projects/` / `/subscriptions/`)** |
| **os 309 `native_id` são distintos e não colidem com nenhum nome nem com nenhum `uuid` do estate** |
| `aggregate=namespace,controller` + `filter=cluster:"<nome>"` + `step=1d` → chave `payments/api`, com `properties.namespace` e `properties.controller` |
| `aggregate=namespace` + `filter=cluster:"<nome>"` → chave `payments` |
| `aggregate=controller` + `filter=cluster:"<nome>"+namespace:"payments"+controller:"api"` → chave `api` |
| `aggregate=cluster` + `filter=cluster:"<nome>"` → chave `<nome>` |
| o `filter` nomeia o cluster que o payload carrega em `properties.cluster` |
| **`filter=cluster:"<nome>"` para um AKS, um GKE e um EKS → 200, `properties.cluster` = o nome, chave `payments/api`** |
| **`aggregate=cluster` devolve o NOME como chave, não o `uuid`** |
| **o `cluster_id` do estate é aceito como alias — e a resposta carrega o NOME, não o id** |
| **`aggregate=cluster` pelo alias também chaveia pelo nome** |
| **o `native_id` (ARN do EKS, ARM id do AKS, `selfLink` do GKE) seleciona o cluster em `/allocation/compute` → 200 com `data` não vazio, e `properties.cluster` = o NOME** |
| **o `native_id` seleciona o cluster em `/clusterInfo` → 200 com a mesma resposta** |
| **`aggregate=cluster` pelo `native_id` também chaveia pelo nome** |
| **dois clusters que compartilham o nome são clusters diferentes: cada `native_id` resolve para o seu próprio registro** |
| **um nome que o estate não tem → 200 com `data: []`** |
| **um nome com espaço no meio (`aks_cluster-0160 (do not delete)`) viaja intacto pelo `filter`** |
| um cluster que o estate não tem → **200 com `data: []`** |
| duas chamadas iguais **com** `filter` devolvem o mesmo payload |
| `step=1d` é aceito; `1h`, `24h`, `2d`, `1w`, `month` → 400 |
| `accumulate=true`/`false` continuam valendo **com** `filter` |
| `filter` malformado ou com chave que a fase não lê → 400 |
| `/clusterInfo?filter=cluster:"<nome>"` → 200 com `data == {"version": "synthetic"}` |
| `/clusterInfo?filter=cluster:"<cluster_id>"` (alias) → 200 com a mesma resposta |
| `/clusterInfo` sem `filter`, ou com cluster que o estate não tem → 400 |
| **o fixture é idempotente: duas execuções do exportador contra o mesmo estate produzem o mesmo arquivo, byte a byte — e esse arquivo é o fixture commitado** (teste pulado quando o checkout não tem o parquet do estate, que não é versionado) |
