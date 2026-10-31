# Mapa de impacto — Fase S4b2-H (o Prometheus no `k8s-sim`: a query que o consumidor lê a telemetria)

**Data:** 2026-10-31 · **Revisão-base:** `a6ae2074` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `emulators/k8s-sim/**` (código, testes), `docs/k8s-sim-opencost-contract.md`,
`docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/ESTADO.md`, `docs/ESTADO.en.md`,
`docs/regression/mapa-impacto-s4b2h.md` ·
**Fora do escopo:** `deploy/synthetic-clouds/tls-front/nginx.conf` (o front), os outros emuladores,
`compose.*.yaml`, `scripts/**`, `specs/**`, `tools/**`, `AGENTS.md`, `docs/NAO-COMPROVADOS*`
(gerado) e `C:\Projetos\cloudpilot-deploy/**` (leitura somente-leitura para medir a superfície;
**exceção autorizada** pelo usuário para a verificação e a configuração do consumidor).

**Por que esta fase existe.** O contrato do `k8s-sim` (§9) nomeava "Prometheus" como pendência
**sem dizer qual**: o §9 é a lista do que a fase anterior não implementou, não uma especificação. A
S4b2-G fechou a fatia da API do Kubernetes; sobrou o plano inteiro do Prometheus, sem superfície
definida. Esta fase fecha **uma fatia**: a query que o **consumidor real** chama para obter a
telemetria de CPU e memória por namespace.

**O desenho veio da leitura do consumidor, não de imaginação.** A superfície não foi escolhida por
analogia com um Prometheus real: foi levantada no **código do CloudPilot** (somente-leitura) e
**medida** no checkpoint da fase. O `nginx.conf` do front está fora da allowlist, o que também
**forçou** o desenho: a rota nova mora no **mesmo** nome HTTPS que já existia, dentro do
encaminhamento `location /` que o front já fazia.

## 1. O que muda

| | Antes (S4b2-G) | Depois (S4b2-H) |
|---|---|---|
| **Planos do `k8s-sim`** | dois: o contrato OpenCost e a API do Kubernetes | **três**: os dois (inalterados) e o Prometheus |
| **Rotas** | `/healthz`, `/clusterInfo`, `/allocation/compute`, `/api/v1/namespaces`, `/api/v1/pods`, `/api/v1/namespaces/{ns}/pods` | **+ `/api/v1/query`** |
| **Auth** | o plano da API pede `Authorization: Bearer <token>`; o plano OpenCost não | o plano novo **não** pede token — o cliente do consumidor não carrega credencial (`opencost.py:112-132`) |
| **Envelope** | `code`/`data` (OpenCost); `NamespaceList`/`PodList`/`Status` (Kubernetes) | o plano novo usa o **envelope do Prometheus**: `status` + `data{resultType,result}`, e `status`/`errorType`/`error` no erro (**400**) |
| **O que o plano publica** | a namespace, o workload e os `requests` do pod | o **uso** da namespace: **2000 millicores** e **4294967296 bytes** — os mesmos 2 núcleos e 4 GiB dos outros dois planos |
| **Fuso** | nenhum relógio é lido | o **carimbo da avaliação** é o relógio da parede (como num Prometheus); o **valor** é constante |

## 2. O checkpoint: a superfície foi medida, não escolhida

O primeiro passo da fase foi responder uma pergunta com o código do consumidor, não com analogia:
**o consumidor lê o Prometheus? Em que endpoint, com que formato, que labels e que auth?**

A resposta (todas as medidas em `C:\Projetos\cloudpilot-deploy`, somente-leitura, em 2026-10-31):

| O quê | Onde | O que a leitura diz |
|---|---|---|
| De onde vem a URL | `opencost.py:56-57` | `config.prometheus_endpoint` **ou** `settings.K8S_PROMETHEUS_URL` (`config.py:619`). O modelo `K8sFinOpsConfig` **não tem** a coluna `prometheus_endpoint`, então o endpoint chega pela **variável de ambiente**. |
| O pedido | `opencost.py:112-132` | `GET {endpoint}/api/v1/query?query=…`, **sem nenhum header de autenticação**. |
| O que a resposta precisa ter | `opencost.py:134-148` | `status == "success"` e `data.result[]`, cada entrada com `metric.namespace` e `value` (lista de dois; o segundo elemento é o número, decimal finito e não-negativo). |
| As queries | `opencost.py:155-170` | `sum by (namespace) (rate(container_cpu_usage_seconds_total{cluster="<id>",container!="",image!=""}[5m])) * 1000` e `sum by (namespace) (container_memory_working_set_bytes{cluster="<id>",container!="",image!=""})`, com o **id nativo** no seletor. |
| Para que serve | `k8s_finops_sync.py:466-508` | vira `cpu_usage_current_millicores` / `memory_usage_current_bytes` do snapshot, com `collection_method = "opencost_prometheus"`. |
| O que fecha sem ela | `opencost.py:375-457` | `get_recommendations` **falha fechado**: sem telemetria, a lista de recomendações é **vazia**. |

**O veredito: o consumidor exige a superfície.** Sem ela, o caminho de rightsizing do consumidor
fecha — e é isso que a fase entrega.

**O que a leitura também descartou.** Duas superfícies foram **declaradas fora** porque a medição
mostrou que o consumidor **não** as exige:

- **A Metrics API** (`apis/metrics.k8s.io/v1beta1/pods`) — é um contrato **diferente** (métricas do
  Kubernetes, não Prometheus). O provider `opencost`, que é o que aponta para este plano, tira a
  telemetria do **Prometheus**; a Metrics API é lida pelos providers **EKS** e **Azure**, pelo
  kubeconfig, e a ausência dela é tratada com elegância (404 → `metrics_error` →
  `collection_method = "k8s_api_requests_only"`). O mapa da S4b2-G dizia que a Metrics API "vai com
  o Prometheus"; a medição mostra que **não vai** — e a allowlist desta fase nem inclui a API do
  Kubernetes.
- **As métricas do Karpenter** — o consumidor tem um segundo cliente Prometheus
  (`karpenter_metrics.py`) que lê `karpenter_nodes_created_total`,
  `karpenter_nodes_terminated_total` e o quantil de startup de pods. O estate **não modela
  Karpenter** (não tem nós, nem node claims, nem provisionamento). Publicar essas métricas seria
  inventar um fato sobre um estate que não existe; elas respondem **vetor vazio**, que é a
  resposta honesta.

## 3. O que a fase **não** faz (e está declarado no contrato)

- **Não é um motor de PromQL.** Só as **duas** queries do consumidor são lidas; qualquer outra
  query responde **200 com vetor vazio** — como um Prometheus responde uma query que não seleciona
  série nenhuma.
- **Não serve `/api/v1/query_range`** — o consumidor não a chama.
- **Não publica métricas de Karpenter**, nem `__name__` (a agregação `sum by (namespace)` o
  descarta), nem séries por nó, por container ou por pod.
- **Não pede token** e **não muda** o contrato OpenCost nem o contrato da API do Kubernetes.

## 4. O mecanismo

- **Projeção nova** `emulators/k8s-sim/k8s_sim/projections/prometheus.py` — a **terceira** projeção
  do mesmo estate. O uso vem do plano da API do Kubernetes (`CPU_CORES`, `MEMORY_BYTES`), e a
  projeção do Kubernetes passou a **derivar** as strings de quantity (`"2"`, `"4Gi"`) dos números, o
  que deixa a coerência dos três planos **estrutural**, e não uma coincidência mantida à mão.
- **Rota** `GET /api/v1/query` em `app.py`, ao lado dos outros dois planos, com o mesmo envelope
  HTTP do Prometheus.
- **Seletor lido** com um scanner de matchers (o valor pode conter vírgula, aspas escapadas e
  barras) — o consumidor escapa `\` e `"` no id do cluster (`opencost.py:155`), e o id nativo do
  EKS/ACS é justamente o tipo de valor que não pode ser partido naïvely.
- **Alias do cluster**: o seletor aceita os **três** aliases (nome, `cluster_id` do estate,
  `native_id`) e a resposta carrega o **nome** — a mesma regra dos outros dois planos (§6.1).
- **O relógio**: o único do serviço, e só para carimbar a avaliação. O `time` (timestamp Unix ou
  RFC 3339) é lido; um `time` ilegível é recusado com 400, como o Prometheus HTTP API recusa.

## 5. O teste da fase

### 5.1 O baseline, antes de qualquer mudança

- Suíte: `pytest emulators\k8s-sim\k8s_sim\tests -q -p no:cacheprovider` → **122 passed** em
  14,9 s.
- Container: `synthetic-clouds-k8s-sim-1` no ar, `localhost/k8s-sim:latest`, "Up 28 minutes".
- Probes de dentro do `cloudpilot_backend`, pelo nome HTTPS:
  - `/healthz` → **200** `{"status":"ok","synthetic":true}`
  - `/api/v1/namespaces` **sem token** → **401** (o plano da API pede token)
  - `/api/v1/query?query=up` → **404** (a superfície ainda não existia)

### 5.2 A suíte, depois

- **138 passed** em 13,1 s — os **122** da S4b2-G mais **16** novos, em
  `emulators/k8s-sim/k8s_sim/tests/test_prometheus.py`.
- `ruff check emulators\k8s-sim --config emulators\k8s-sim\pyproject.toml` → **All checks passed!**
- `mypy --config-file pyproject.toml -p k8s_sim` → **Success: no issues found in 11 source files**.

**Provado em vermelho-verde.** Um único número foi mutado (o multiplicador da query de CPU,
`× 1000` → `× 100`) e a suíte foi reexecutada: **3 testes falharam** — o da query de CPU, o da
forma que o consumidor lê e o de coerência entre os três planos. Restaurado o número, a suíte
voltou a **138 passed**. Os testes mordem.

### 5.3 O deploy: só o `k8s-sim`

`podman compose -f compose.k8s.yaml up -d --build k8s-sim`, em `deploy/synthetic-clouds/`:

- imagem reconstruída: `77c7aa0a5a38` → `localhost/k8s-sim:latest`
- container **recriado**: `synthetic-clouds-k8s-sim-1` — "Up 3 minutes (healthy)" no `podman ps`
  final, contra "Up 5 hours" de **todos** os outros containers (front TLS, os três planos de nuvem
  e os containers do CloudPilot). **Nenhum outro plano foi tocado** e o front **não** foi recriado.
- **A dívida operacional da S4b2-G voltou a aparecer e foi resolvida do mesmo jeito:** a recriação
  perdeu o alias `k8s-sim` na bridge do CloudPilot (`podman network connect --alias k8s-sim
  cloudpilot-deploy_cloudpilot_net synthetic-clouds-k8s-sim-1`) e o nginx do front continuava
  apontando para o **IP antigo** do upstream (o front não tem `resolver`: o nome é resolvido uma
  vez, na carga da configuração) — a correção foi `podman exec synthetic-clouds-tls-front nginx -s
  reload`, **sem recriar o front**, que manteve PID, uptime e aliases.

### 5.4 As rotas novas, de dentro do `cloudpilot_backend`

Sonda por HTTPS (`https://opencost.synthetic-clouds.test`), de dentro do container do backend:

```
PROMETHEUS cpu (id nativo) -> 200
{"status":"success","data":{"resultType":"vector","result":[{"metric":{"namespace":"payments","cluster":"TEMP-aks_cluster-0025"},"value":[1793477962.329657,"2000"]}]}}

PROMETHEUS memory (id nativo) -> 200
{"status":"success","data":{"resultType":"vector","result":[{"metric":{"namespace":"payments","cluster":"TEMP-aks_cluster-0025"},"value":[1793477962.336396,"4294967296"]}]}}

PROMETHEUS por nome -> 200      (mesma série, o nome como alias)
PROMETHEUS cluster desconhecido -> 200   {"status":"success","data":{"resultType":"vector","result":[]}}
PROMETHEUS query sem serie -> 200        {"status":"success","data":{"resultType":"vector","result":[]}}
PROMETHEUS sem query -> 400
{"status":"error","errorType":"bad_data","error":"invalid parameter \"query\": 1:1: parse error: no expression found in input"}
```

### 5.5 A não-regressão dos outros dois planos

Na mesma sondagem, do mesmo container:

```
OPENCOST healthz -> 200          {"status":"ok","synthetic":true}
OPENCOST allocation/compute -> 200   {"code":200,"data":[{"payments":{… "cpuCores":2.0,"ramBytes":4294967296.0, … "totalCost":3.88}}]}
OPENCOST clusterInfo -> 200      {"code":200,"data":{"version":"synthetic"}}
K8S namespaces (sem token) -> 401   (o Status oficial)
K8S namespaces (com token) -> 200   NamespaceList [payments]
K8S pods (com token) -> 200          PodList, requests cpu "2" / memory "4Gi"
```

Os números do allocation são os **mesmos** da S4b2-E: 2 núcleos, 4 GiB, **3.88 USD**.

### 5.6 O consumidor, na conta de homologação

O **provider real** do CloudPilot (`app.services.k8s_finops.providers.opencost.OpenCostProvider`),
rodando **dentro do container do backend**, contra a **config salva** da conta de homologação
(`5d5a8ec7-9911-4d19-a958-b6c27737fbe6`, `provider_type = opencost`,
`provider_endpoint = https://opencost.synthetic-clouds.test`):

```
config: 5d5a8ec7-9911-4d19-a958-b6c27737fbe6 opencost https://opencost.synthetic-clouds.test
clusters na config: []
prometheus endpoint: https://opencost.synthetic-clouds.test
telemetry: {'payments': NamespaceTelemetry(namespace='payments', cpu_usage_millicores=2000, memory_usage_bytes=4294967296)}
namespace=payments cpu_usage_millicores=2000 memory_usage_bytes=4294967296
custo: ClusterCostData(cluster_id='/subscriptions/…/managedClusters/TEMP-aks_cluster-0025', cluster_name='TEMP-aks_cluster-0025',
                        namespace='payments', workload='api', date=2026-10-01, cpu_cost_usd=1.92, memory_cost_usd=0.576,
                        storage_cost_usd=0.384, network_cost_usd=1.0, total_cost_usd=3.88, …)
```

Ou seja: **o consumidor leu a telemetria da superfície nova** (os mesmos 2.000 millicores e
4.294.967.296 bytes que o allocation precifica) **e o contrato OpenCost não regrediu** (3.88 USD,
`payments/api`, 2026-10-01).

### 5.7 A configuração do consumidor (o que mudou)

- **`C:\Projetos\cloudpilot-deploy\backend\.env.local`** (arquivo **não rastreado**, `.gitignore:96`)
  ganhou uma chave:

  ```
  K8S_PROMETHEUS_URL=https://opencost.synthetic-clouds.test
  ```

  É a **URL base** — o provider **acrescenta** `/api/v1/query` a ela.
- **Nenhum código do CloudPilot foi tocado**, e **os containers do CloudPilot não foram
  recriados**: a variável entra em vigor na próxima recriação
  (`pwsh -File C:\Projetos\cloudpilot-deploy\scripts\compose-local.ps1 -Action up`), porque o
  `settings` é lido na importação do processo. A medição do §5.6 rodou com a **mesma** chave
  injetada no processo (`podman exec -e K8S_PROMETHEUS_URL=…`), sem depender do restart.

## 6. Débitos e lacunas declaradas

- **`clusters: []` na config da homologação.** A tarefa de sync itera `config.clusters`
  (`k8s_finops_sync.py:434-451`), e na conta de homologação essa lista está **vazia** — então o
  **sync agendado não chama o Prometheus hoje**, mesmo com a variável configurada. Preencher a
  lista (pela descoberta de clusters) é o que falta para o fluxo inteiro rodar; a pendência
  "rodar sync" da S4b2-E continua aberta.
- **O `/savings/requestSizing` do OpenCost não é servido.** O `get_recommendations` do provider
  (`opencost.py:375-457`) chama esse endpoint do OpenCost, que o `k8s-sim` **não** implementa — o
  rightsizing completo continua fora de alcance do simulador, mesmo com a telemetria disponível.
  É uma fatia própria, do contrato OpenCost, não do plano Prometheus.
- **A Metrics API não é servida** (§2) — e a S4b2-G a tinha declarado como "vai com o Prometheus".
- **O botão "Verificar Conexão" continua quebrado** — defeito **pré-existente** do CloudPilot
  (a factory passa `db=` a um provider que não o aceita; `opencost.py:47`), fora da allowlist.
- **A gêmea em inglês do contrato** (`docs/k8s-sim-opencost-contract.en.md`) continua **sem
  existir** (pendência da S4b1) — a allowlist desta fase permite **apenas** o arquivo PT.
- **A dívida operacional continua**: o `ensure-cloudpilot.ps1` reanexa o alias quando falta, mas
  **não** recarrega o nginx; quem recria o `k8s-sim` tem de rodar o `nginx -s reload` do front
  (o §5.3 mediu de novo).

## 7. Documentos afetados

| Documento | O que mudou |
|---|---|
| `docs/k8s-sim-opencost-contract.md` | **§2.3** nova (o plano Prometheus: a medição do consumidor, o que é servido, o que é publicado, o que **não** é servido, o wiring); §2.2.6 e §9 com o Prometheus fechado e a Metrics API declarada fora; §10.2 nova (os 16 testes); §10 com a contagem 138; cabeçalho e título datados |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | a linha do hostname `opencost.synthetic-clouds.test` na tabela de destinos; a seção de configuração de conta com o `K8S_PROMETHEUS_URL` (o que é, por que, e quando entra em vigor) |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | a linha da fase e a seção datada |
| `docs/regression/mapa-impacto-s4b2h.md` | este documento |

## 8. O que esta fase **não** faz

- Não toca o `nginx.conf` do front, os outros emuladores, `compose.*.yaml`, `scripts/**`,
  `specs/**`, `tools/**`, `AGENTS.md` nem `docs/NAO-COMPROVADOS*`.
- Não escreve no repositório do CloudPilot nem recria os containers dele.
- Não roda o sync do CloudPilot, não grava snapshot e não valida tela.
- Não implementa a Metrics API, o `/savings/requestSizing`, nem um motor de PromQL.
