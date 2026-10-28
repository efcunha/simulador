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
| F9 | OpenCost — resolução do `accumulate` | `pkg/costmodel/aggregation.go:84-96` (`resolveAccumulateFromQuery`), `:124-140` (`resolveDefaultStepFromAccumulate`), `:135-136` (`case AccumulateOptionAll: return window.Duration()`) | Resolve o parâmetro em três passos: `all` (sem distinção de caixa) ⇒ `AccumulateOptionAll`; `ParseAccumulate` para as opções nomeadas; e, para o resto, a leitura booleana. Com `all`, o **passo** passa a ser a duração da janela (`:135-136`), o que produz **um** set para a janela toda. O handler **nunca** recusa um valor de `accumulate`. |
| F10 | OpenCost — as opções de acumulação | `core/pkg/opencost/query.go:47-79` (`AccumulateOption`, `ParseAccumulate`) | As opções são `all`, `hour`, `day`, `week`, `month`, `quarter` e `none` (vazio). `ParseAccumulate` normaliza para minúsculas e lê `quarter`, `month`, `week`, `day`, `hour` e `true`; o resto é `none`. |
| F11 | OpenCost — a leitura booleana | `core/pkg/util/mapper/mapper.go:411-419` (`GetBool`) | `GetBool` usa `strconv.ParseBool`: aceita `1`, `t`, `T`, `TRUE`, `true`, `True` como verdadeiro (e `0`, `f`, `F`, `FALSE`, `false`, `False` como falso); o que não parseia devolve o valor padrão (`false`). É essa leitura que faz `accumulate=1` significar "a janela toda". |
| F12 | OpenCost — como a acumulação soma | `core/pkg/opencost/allocation.go:1422-1456` (`Allocation.add`), `:1109-1140` (`CPUCores`, `RAMBytes`, `PVBytes`), `:3178-3214` (`AllocationSet.Accumulate`), `:3330-3340` (`accumulateByAll`) | A soma junta os campos **cumulativos** (`cpuCoreHours`, `ramByteHours`, `networkTransferBytes` e todos os custos). `cpuCores`, `ramBytes` e `pvBytes` **não** são somados: são derivados (horas somadas ÷ minutos somados ÷ 60), então um uso diário constante mantém as mesmas figuras. `AllocationSet.Accumulate` produz **um** set com o início e o fim do intervalo inteiro, e `accumulateByAll` devolve um único set. |
| F13 | OpenCost — o agrupamento de calendário | `core/pkg/opencost/allocation.go:3393-3502` (`accumulateByMonth`, `accumulateByQuarter`, `accumulateByWeek`), `pkg/costmodel/aggregation.go:171-186` (`resolveQueryWindowForAccumulate`) | O agrupamento de calendário fecha o bucket no fim do mês, do trimestre e **no sábado** (a semana começa no domingo). Para servir essas opções, o handler **expande a janela consultada** para as bordas do bucket, de modo que a resposta passa a incluir dias que o chamador não pediu. |

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
| `accumulate` | Boolean no Swagger (F2): *"If true, sums the entire window into a single result set."*. No handler (F5:363, F9): aceita `true`/`1` (⇒ `all`), `all`, `day`, `week`, `month`, `quarter`, `hour`, e `accumulateBy` com `quarter`/`none`. | **Implementado, no padrão do handler.** A resolução é a de F9/F10/F11: `all` (qualquer caixa) e qualquer valor booleano verdadeiro (`true`, `1`, `t`, `TRUE`, `True`) ⇒ **uma** janela com os custos do período somados; `day` ⇒ uma janela por dia; `false`/`0`/ausente ⇒ uma janela por dia; `week`/`month`/`quarter`/`hour` ⇒ uma janela por dia (§3.2). **Nenhum valor de `accumulate` é recusado** — o handler oficial também não recusa. |

### 3.1 Parâmetro não servido: `step`

`step` (F1, F2, F5) define a duração de cada set e, no OpenCost, **por default é igual à janela**
— o que devolve **um** set para a janela toda. Esta fase entrega **um set por dia** — ou seja,
equivale a `step=1d` —, exceto quando o `accumulate` pede a janela inteira (§3.2). O parâmetro não
é lido: a fase fixa o passo em um dia. Registrado aqui porque é a razão de
`window=2026-10-01,2026-10-02` devolver dois sets em vez de um.

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
pela chave da agregação — `payments`, para `aggregate=namespace` (§7):

```json
{
  "code": 200,
  "data": [
    {
      "payments": {
        "name": "payments",
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
| `name` | F7 (`AllocationJSON.Name`) | A chave do allocation: `payments`. |
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
| chave do allocation set | `payments` |

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

| Agregação pedida | Chave no OpenCost oficial |
|---|---|
| `aggregate=namespace` | `payments` (só o namespace) |
| `aggregate=namespace,controller` | `payments/api` — o `controllerKind` só entra como prefixo (`deployment:api`) quando a allocation **tem** `controllerKind` |
| `aggregate` ausente | `cluster/node/namespace/pod/container` (F5:34, o default do `ParseAggregationProperties`) |

**O `k8s-sim` serve `aggregate=namespace`, e portanto serve a chave `payments`.** O mapa do
allocation set é `{"payments": {...}}` e o `name` da allocation é `payments` — o `name` é a
chave sob a qual a allocation é arquivada, não o nome do workload.

O `controller` continua publicado em `properties.controller` (`api`), porque é uma propriedade
real da allocation sintética — apenas não é parte da chave dessa agregação.

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

---

## 9. Fora de escopo desta fase (e o que fica pendente)

Nada abaixo foi implementado, e nada abaixo é um bug desta fase:

- **Sem billing, sem reconciliação.** Os números são sintéticos (§6). S4b.
- **Um cluster só.** `aks-synthetic-01`, um namespace, um workload. Multi-cluster é S4b.
- **Sem `step`** e **sem `includeIdle` efetivo** (§3, §3.1). `includeIdle` é aceito e ignorado;
  `accumulate` **é** servido, nas duas formas da §3.2.
- **Sem agregações além de `namespace`** (§3).
- **Sem** `Dockerfile`, `compose.k8s.yaml`, rede, TLS, URL do cluster, API server do Kubernetes,
  Prometheus, Kubecost, UI ou migration.
- **Sem spec de máquina** em `specs/` e **sem entrada na matriz de fidelidade** — S4b.
- **Sem** wiring no provider do CloudPilot, **sem** rodar sync, **sem** validar tela. O CloudPilot
  não foi tocado.
- **Sem gêmea `.en.md`** deste documento: a allowlist da fase permite só este arquivo em `docs/`.
  Pendência para quando a allowlist abrir.
- **`accumulate=week`/`month`/`quarter`/`hour` não são distintos** (§3.2): a fase devolve um set
  por dia para essas grafias, onde o OpenCost agruparia por calendário. Declarado no contrato;
  S4b.

---

## 10. Onde o contrato é testado

`emulators/k8s-sim/k8s_sim/tests/test_allocation.py`, via `fastapi.testclient.TestClient`:

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
| `aggregate` fora de `namespace` → 400 |
| `accumulate=true` → 200 com **uma** janela cobrindo o período e os custos somados |
| as grafias que o oficial lê como janela inteira (`true`, `1`, `t`, `T`, `TRUE`, `True`, `all`, `ALL`) → uma janela |
| a janela acumulada tem `window`, `start`, `end` e `minutes` do período inteiro |
| os custos acumulados são a soma dos dias; `cpuCores`/`ramBytes`/`pvBytes` são a média, não a soma |
| a identidade do total sobrevive à acumulação, no bit |
| `accumulate=false` / `0` / `day` → os sets diários, como sem o parâmetro |
| `includeIdle` não muda o payload |
