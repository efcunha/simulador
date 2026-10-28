# Contrato OpenCost do `k8s-sim` (Fase S4a)

> Idioma: **Português**. Sem gêmea `.en.md`: a allowlist da Fase S4a permite **apenas** este
> arquivo em `docs/`. A gêmea em inglês fica como pendência (§9).

Levantamento executado em **2026-10-28**, por leitura somente-leitura das fontes oficiais do
OpenCost. Este documento existe para que a forma do payload não dependa da memória de ninguém:
cada linha traz **a URL da fonte** e **o trecho que a sustenta**.

**O que este documento é:** o contrato HTTP do serviço mínimo `k8s-sim` — o caminho
`/allocation/compute`, o envelope, os campos de cada allocation e o comportamento dos
parâmetros.

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

### 1.1 Onde as fontes oficiais discordam entre si

Registrado porque o desacordo é real e muda o que se pode afirmar:

- **`status` no `AllocationResponse`.** O Swagger (F2) publica `status: string` no envelope. O
  código (F6) **não emite `status`**: emite `code`, `data`, `meta`, `message` e `warning`. A
  **fonte de máquina prevalece** e o `k8s-sim` emite o envelope do código (F6). O `status` do
  Swagger está **desatualizado** — registrado como `unverified` no §7.
- **`accumulate` em `/allocation`.** O Swagger (F2) o publica como **boolean**; o handler (F5)
  aceita **as duas** coisas: o `resolveAccumulateFromQuery` (`:84`) trata `all` como opção e
  qualquer valor truthy (`true`/`1`) como `AccumulateOptionAll`, e o `ParseAccumulate` aceita
  `day`/`week`/`month`. A página da API (F1) só documenta `accumulate` nas APIs de cloud cost.
- **`includeIdle` em `/allocation`.** A página da API (F1) documenta; o Swagger (F2) **não**.
- **O caminho.** F1 e F2 documentam `/allocation`; F3, F4 e F5 usam `/allocation/compute`. São
  o mesmo serviço — `/allocation` é a rota que **agrega** o resultado e `/allocation/compute` é a
  que **calcula**. O `k8s-sim` serve `/allocation/compute`, que é o caminho que o provider
  `opencost` do CloudPilot chama.

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

---

## 3. Parâmetros

| Parâmetro | O que a fonte oficial publica | O que esta fase faz |
|---|---|---|
| `window` | **Obrigatório** (F1, F2, F5). Aceita palavras (`today`, `lastweek`), durações (`30m`, `7d`), pares RFC 3339 (`2021-01-02T15:04:05Z,2021-02-02T15:04:05Z`) e timestamps Unix (`1578002645,1580681045`). Erro de parse → **400** (F5:341). | **Implementado, estreitado.** Só lê `YYYY-MM-DD,YYYY-MM-DD`, com **as duas pontas inclusivas**: `2026-10-01,2026-10-02` devolve **2** sets, um por dia. Ausente, malformado, data inexistente ou fim antes do início → **400** com o envelope de erro. As outras grafias oficiais **não** são lidas: recusadas, nunca adivinhadas. |
| `aggregate` | Aceita `cluster`, `node`, `namespace`, `controllerKind`, `controller`, `service`, `pod`, `container`, `label:LABEL_NAME`, `annotation:name`, listas separadas por vírgula, e `all` (F1, F5:32 `ParseAggregationProperties`). Valor inválido → 400 (F5:355). | **Implementado, estreitado.** Só serve `namespace`. Ausente ⇒ `namespace`. **Qualquer outro valor → 400**, nomeando o valor suportado. A recusa é deliberada: responder a `aggregate=cluster` com a visão de namespace é um downgrade silencioso, e o simulador não mente sobre o que respondeu. |
| `includeIdle` | Boolean, default `false` (F1; F5:360 `qp.GetBool("includeIdle", false)`). Controla a alocação `__idle__` do cluster. | **Aceito e ignorado.** O estate sintético não modela recurso ocioso — não há idle para incluir — então o payload **não muda** com o parâmetro. Isso é dito no payload: o que ele afirma sobre idle é verdade nos dois casos. |
| `accumulate` | Boolean no Swagger (F2): *"If true, sums the entire window into a single result set."*. No handler (F5:363, `:84`): aceita `true`/`1` (⇒ `all`), `all`, `day`, `week`, `month`, e `accumulateBy` com `quarter`/`none`. | **Recusado com 400.** Esta fase acumula **sempre por dia**. Honrar `accumulate=true` significaria devolver **um** set para a janela inteira em vez de **um por dia** — outra forma com o mesmo nome. A recusa diz *"esta fase não serve isso"*; o silêncio diria *"aqui está a resposta, mas não é a que você pediu"*. **Gap declarado para a S4b** (§9). |

### 3.1 Parâmetro não servido: `step`

`step` (F1, F2, F5) define a duração de cada set e, no OpenCost, **por default é igual à janela**
— o que devolve **um** set para a janela toda. Esta fase entrega **um set por dia**, ou seja,
equivale a `step=1d`. O parâmetro não é lido: a fase fixa o passo em um dia. Registrado aqui
porque é a razão de `window=2026-10-01,2026-10-02` devolver dois sets em vez de um.

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
pela chave do workload:

```json
{
  "code": 200,
  "data": [
    {
      "payments/api": {
        "name": "payments/api",
        "properties": {
          "cluster": "aks-synthetic-01",
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
| `name` | F7 (`AllocationJSON.Name`) | A chave do allocation: `payments/api`. |
| `properties.cluster` / `.namespace` / `.controller` | F8 (`AllocationProperties`, tags JSON em `:178`, `:181`, `:183`) | O cluster sintético, o namespace e o workload. |
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

O `k8s-sim` modela **um** cluster, **um** namespace e **um** workload:

| | |
|---|---|
| cluster | `aks-synthetic-01` |
| namespace | `payments` |
| controller | `api` |
| chave do allocation set | `payments/api` |

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

---

## 7. A chave do allocation set

A regra oficial (F8) é: `GenerateKey` (`allocationprops.go:361`) monta a chave com os valores das
propriedades agregadas e os une com **`"/"`** (`:551`). O que entra na chave depende da
agregação pedida:

| Agregação pedida | Chave no OpenCost oficial |
|---|---|
| `aggregate=namespace` | `payments` (só o namespace) |
| `aggregate=namespace,controller` | `payments/api` — o `controllerKind` só entra como prefixo (`deployment:api`) quando a allocation **tem** `controllerKind` |
| `aggregate` ausente | `cluster/node/namespace/pod/container` (F5:34, o default do `ParseAggregationProperties`) |

**Desvio D2 (o único desvio de conteúdo da fase).** A fase pede `aggregate=namespace` e exige a
chave **`payments/api`**. No OpenCost oficial, `aggregate=namespace` produz **`payments`**. A
fase entrega a chave **do workload** (`namespace/controller`), que é a forma de chave que o
OpenCost produz para a agregação `namespace,controller` quando a allocation não tem
`controllerKind` — e o `k8s-sim` não publica `controllerKind` (F8 lista-o, e a fase não o
modela), de modo que `payments/api` **é** uma chave legítima do contrato oficial.

Por que a fase prefere a chave do workload: o consumer (o provider `opencost` do CloudPilot) lê
`data` como lista de janelas e indexa a **custo por workload**, não por namespace agregado. A
chave é a identidade do custo, e nesta fase o custo é de um workload.

Este desvio é **deliberado, visível e fixado por teste** — não é um accidento de implementação.
Uma fase futura que queira a chave de namespace pura deve trocar `WORKLOAD_KEY` e o teste que a
fixa; o formato da chave (junção por `"/"`) continua sendo o do OpenCost.

---

## 8. `unverified` — o que a fonte não publica

Registro honesto do que **não** pôde ser lido na fonte, e portanto **não** foi inventado:

| Item | Situação |
|---|---|
| `status` no envelope (`AllocationResponse`) | Publicado pelo Swagger (F2), **não emitido** pelo código (F6). Divergência entre as duas fontes oficiais; o código prevalece. Não é emitido pelo `k8s-sim`. |
| `includeIdle` no Swagger de `/allocation` | A página da API publica (F1), o Swagger não (F2). O `k8s-sim` segue o comportamento do handler (F5:360), não o do Swagger. |
| `accumulate` como boolean **em `/allocation`** | O Swagger publica boolean (F2); o handler aceita as duas grafias (F5:84). O `k8s-sim` recusa o parâmetro (§3), então não precisa resolver a ambiguidade. |
| Semântica de `window` quando o fim é igual ao início | Nenhuma das fontes publica o comportamento de um intervalo de um único dia com bordas inclusivas. Esta fase devolve **1** set para `X,X` (implementação própria, por consequência da regra inclusiva do §3). |
| Nomes de campo de `properties` além de `cluster`/`namespace`/`controller` | F8 publica `node`, `container`, `controllerKind`, `pod`, `services`, `providerID`, `labels`, `annotations`, `namespaceLabels`, `namespaceAnnotations`. Esta fase publica **só os três** que a fase exige; os demais não são preenchidos. |
| Formato exato da mensagem de erro do `window` | O OpenCost escreve `Invalid 'window' parameter: %s` com o erro do parser Go (F5:341). O texto do parser **não** é reimplementado: a mensagem do `k8s-sim` é própria e o formato (`Invalid 'window' parameter: …`) é o oficial. |

---

## 9. Fora de escopo desta fase (e o que fica pendente)

Nada abaixo foi implementado, e nada abaixo é um bug desta fase:

- **Sem billing, sem reconciliação.** Os números são sintéticos (§6). S4b.
- **Um cluster só.** `aks-synthetic-01`, um namespace, um workload. Multi-cluster é S4b.
- **Sem `step`, sem `accumulate`, sem `includeIdle` efetivo** (§3). `accumulate` recusado com 400.
- **Sem agregações além de `namespace`** (§3).
- **Sem** `Dockerfile`, `compose.k8s.yaml`, rede, TLS, URL do cluster, API server do Kubernetes,
  Prometheus, Kubecost, UI ou migration.
- **Sem spec de máquina** em `specs/` e **sem entrada na matriz de fidelidade** — S4b.
- **Sem** wiring no provider do CloudPilot, **sem** rodar sync, **sem** validar tela. O CloudPilot
  não foi tocado.
- **Sem gêmea `.en.md`** deste documento: a allowlist da fase permite só este arquivo em `docs/`.
  Pendência para quando a allowlist abrir.
- **`accumulate=true` quebra um consumer que o mande.** Um provider que envie
  `accumulate=true` recebe 400 nesta fase. É um gap declarado, não um acidente: ou a S4b implementa
  a acumulação, ou o consumer para de pedi-la.

---

## 10. Onde o contrato é testado

`emulators/k8s-sim/k8s_sim/tests/test_allocation.py`, via `fastapi.testclient.TestClient`:

| O que o teste fixa |
|---|
| `/healthz` → 200 com o corpo dos emuladores irmãos |
| envelope `code`/`data`; `data` é lista |
| uma entrada por dia na janela `2026-10-01,2026-10-02` (2 janelas) |
| cada janela é um dict com a chave `payments/api` |
| `properties.cluster` / `.namespace` / `.controller` |
| os cinco campos de custo presentes |
| `totalCost == cpuCost + ramCost + pvCost + networkCost`, no bit |
| custos finitos e não negativos |
| duas chamadas iguais devolvem o mesmo payload |
| `window` inválido, ausente, invertido ou com data inexistente → 400 |
| `aggregate` fora de `namespace` → 400 |
| `accumulate` presente → 400 |
| `includeIdle` não muda o payload |
