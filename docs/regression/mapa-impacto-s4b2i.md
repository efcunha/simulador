# Mapa de impacto — Fase S4b2-I (a Model API do Kubecost no `k8s-sim`: a rota que o provider `kubecost` lê)

**Data:** 2026-10-31 · **Revisão-base:** `b221d0cc` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `emulators/k8s-sim/**` (código, fixtures, testes, `pyproject.toml`),
`docs/k8s-sim-opencost-contract.md`, `docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/ESTADO.md`,
`docs/ESTADO.en.md`, `docs/regression/mapa-impacto-s4b2i.md` ·
**Fora do escopo:** `deploy/synthetic-clouds/tls-front/nginx.conf` (o front), os outros emuladores,
`compose.*.yaml`, `scripts/**`, `specs/**`, `tools/**`, `AGENTS.md`, `docs/NAO-COMPROVADOS*`
(gerado) e `C:\Projetos\cloudpilot-deploy/**` (leitura somente-leitura para medir a superfície;
**exceção autorizada** pelo usuário para a verificação e a configuração do consumidor).

**Por que esta fase existe.** O contrato do `k8s-sim` (§9) nomeava "Kubecost" como pendência
**sem dizer qual**: o §9 é a lista do que a fase anterior não implementou, não uma especificação. A
S4b2-H fechou a fatia do Prometheus; sobrou o plano inteiro do Kubecost, sem superfície definida.
Esta fase fecha **uma fatia**: a rota da Model API do Kubecost que o **consumidor real** lê.

**O desenho veio de duas leituras, não de imaginação.** A superfície foi levantada no **código do
CloudPilot** (somente-leitura) e **medida** no checkpoint da fase — rodando o provider real contra
o serviço. E o **corpo da resposta** veio da **spec publicada da Model API do Kubecost**, não de
analogia com o OpenCost: os dois contratos publicam campos diferentes, e a diferença importa
(§2.3). O `nginx.conf` do front está fora da allowlist, o que também **forçou** o desenho: a rota
nova mora no **mesmo** nome HTTPS que já existia, dentro do encaminhamento `location /` que o front
já fazia.

## 1. O que muda

| | Antes (S4b2-H) | Depois (S4b2-I) |
|---|---|---|
| **Planos do `k8s-sim`** | três: o contrato OpenCost, a API do Kubernetes e o Prometheus | **quatro**: os três (inalterados) e a Model API do Kubecost |
| **Rotas** | `/healthz`, `/clusterInfo`, `/allocation/compute`, `/api/v1/namespaces`, `/api/v1/pods`, `/api/v1/namespaces/{ns}/pods`, `/api/v1/query` | **+ `/model/allocation`** |
| **Auth** | o plano da API pede `Authorization: Bearer <token>`; os planos OpenCost e Prometheus não | o plano novo **não exige** token (a spec da Model API não declara `securitySchemes`) e **aceita** o que o consumidor envia |
| **Envelope** | `code`/`data` (OpenCost); `NamespaceList`/`PodList`/`Status` (Kubernetes); `status`/`data` (Prometheus) | o plano novo usa o envelope publicado da Model API: `code` + `data`, com `data` sendo a **lista de sets** — o mesmo envelope do plano OpenCost |
| **O que o plano publica** | o uso do namespace, os objetos do cluster e os custos do plano OpenCost | os **mesmos custos** do estate, com os **nomes de campo do Kubecost** (`ramCost`, e não `memCost`) e as **quatro médias** que só a Model API publica |
| **Passo** | o plano OpenCost fixa o passo em `1d` | o plano novo segue o padrão publicado: **sem `step`, a resposta é um set para a janela inteira** |
| **Fuso** | o carimbo da avaliação (plano Prometheus) e nenhum outro | nenhum relógio novo |

## 2. O checkpoint: a superfície foi medida, não escolhida

O primeiro passo da fase foi responder uma pergunta com o código do consumidor, não com analogia:
**o consumidor lê o Kubecost? Em que endpoint, com que formato e que auth? — e por workspace?**

### 2.1 O que o consumidor tem

| O quê | Onde | O que a leitura diz |
|---|---|---|
| O provider | `backend/app/services/k8s_finops/providers/kubecost.py` | o CloudPilot **publica** um `KubecostEnterpriseProvider`, registrado na factory sob `kubecost_enterprise` (`factory.py:118-132`) e **oferecido na UI** — medido: `GET /api/v1/finops/kubernetes/config/providers` devolve `aws`, `azure`, `gcp`, **`kubecost_enterprise`**, `opencost` |
| Os pedidos | `kubecost.py:305-323`, `:326-343`, `:404-424` | `GET {endpoint}/model/allocation` com `window`, `aggregate` (`namespace` ou `controller`), `filterClusters`, `filterNamespaces`, `filterControllers` e `accumulate=false` |
| Os outros dois pedidos | `kubecost.py:378-402`, `:544-559`, `:364-376` | `GET {endpoint}/model/clusterInfo` (com e sem `filterClusters`) e `GET {endpoint}/savings/requestSizing` |
| O envelope que o parser lê | `kubecost.py:176-197` | `raw_data["data"]` → `period_data.items()` → o allocation: **lista de sets**, cada set um mapa chave→allocation |
| Os campos que o parser lê | `kubecost.py:195-219` | `properties.cluster/namespace/controller`, `start`, `cpuCost`, **`memCost`**, `pvCost`, `networkCost`, `totalCost`, `ramByteRequestAverage`, `ramByteUsageAverage`, `cpuCoreRequestAverage`, `cpuCoreUsageAverage` |
| O auth | `kubecost.py:49-95` | `Authorization: Bearer <token>`; sem token o provider **não envia** nada |

### 2.2 A medição ao vivo (o checkpoint)

O provider real foi **instanciado dentro do container `cloudpilot_backend`**, contra a config
salva da conta de homologação (`provider_endpoint = https://opencost.synthetic-clouds.test`, token
presente), e os pedidos que ele emissiu foram lidos no **log de acesso** do `k8s-sim`. **Antes da
fase, os cinco respondiam 404**:

```
INFO: 10.89.0.20:41626 - "GET /model/allocation?window=2026-10-01%2C2026-10-01&aggregate=namespace&filterClusters=%2Fsubscriptions%2F…&accumulate=false HTTP/1.1" 404 Not Found
INFO: 10.89.0.20:41640 - "GET /model/allocation?window=…&aggregate=controller&filterClusters=…&filterNamespaces=payments&accumulate=false HTTP/1.1" 404 Not Found
INFO: 10.89.0.20:41646 - "GET /model/clusterInfo?filterClusters=… HTTP/1.1" 404 Not Found
INFO: 10.89.0.20:41658 - "GET /savings/requestSizing?filterClusters=… HTTP/1.1" 404 Not Found
INFO: 10.89.0.20:41674 - "GET /model/clusterInfo HTTP/1.1" 404 Not Found
```

**Por workspace.** Os três `k8s_finops_configs` do banco local são `opencost`, `opencost` e `aws`;
**nenhum** workspace está com `provider_type = kubecost_enterprise`, e a tabela
`k8s_opencost_bridge` — a ponte de FinOps que poderia carregar `tool_type = kubecost` — tem
**0 linhas**. A conta de homologação está em `opencost` (o provider que o OpenCost já serve).

**O veredito: o consumidor exige a superfície.** Ele **tem** o provider, o **expõe na UI** e
**emite** os pedidos — o `BLOCKED` previsto pela fase ("consumidor não consome Kubecost") não se
aplica. O que a fase implementou é a **interseção** entre o que o consumidor pede e o que a
fonte do Kubecost publica (§2.3).

### 2.3 A fonte: a spec publicada da Model API

A spec oficial **não** se deixou ler pelo caminho óbvio. As quatro URLs tentadas, com o que cada
uma devolveu em 2026-10-31:

| URL | O que devolveu |
|---|---|
| `https://docs.kubecost.com/apis/monitoring-apis/api-allocation` | **403 Forbidden** (a borda IBM bloqueia o acesso automatizado, com e sem *user-agent* de browser) |
| `https://api.docs.kubecost.com/` | **DNS**: o host não resolve |
| `https://raw.githubusercontent.com/api-evangelist/kubecost/refs/heads/main/openapi/kubecost-model-api-openapi.yml` | **404** (o espelho tem só `README.md`) |
| `https://web.archive.org/web/2024id_/https://api.docs.kubecost.com/` | **429** (duas vezes) |

A spec veio do **artefato**: `https://artifacts.apis.io/kubecost/openapi/kubecost-model-api-openapi.yml`
— 39.957 bytes, OpenAPI 3.2.0, `info.title: Kubecost Model API`, montada a partir das **seis**
definições que o Kubecost publica (`kubecost-allocation-openapi.yml`, `…-assets-…`,
`…-budget-…`, `…-cloud-cost-…`, `…-forecast-…`, `…-savings-…`).

O que ela decide:

- **quinze** rotas. O `k8s-sim` serve **uma** — `/model/allocation` —: a única que o consumidor lê
  **e** que a fonte publica. As outras catorze (`/model/assets`, `/model/budget`,
  `/model/cloudCost`, `/model/forecast/allocation`, `/model/savings/*`) **não** são lidas por nada
  no consumidor.
- **`/model/clusterInfo` não está entre as quinze.** O motor do produto (`cost-model`,
  `pkg/costmodel/router.go`) registra `/clusterInfo` — **sem** o prefixo `/model/`. E
  `/savings/requestSizing` também não é uma rota da Model API: ela publica
  `/model/savings/requestSizingV2`, outro prefixo e outra versão. As duas rotas que o consumidor
  pede e que a fonte **não** publica **não foram servidas**.
- O schema `Allocation` publica `ramCost` e **não** publica `memCost` nem `minutes`; publica as
  **quatro médias** e o `totalCost`.
- `step` ausente = **a janela inteira** (um set, custos somados) — o padrão publicado.
- A spec **não declara `securitySchemes`** → o plano não exige token.

## 3. O que a fase **não** faz (e está declarado no contrato)

- **Não serve `/model/clusterInfo`** nem `/savings/requestSizing` — a fonte não os publica.
- **Não publica `memCost`** — o campo que o consumidor lê e que o Kubecost não publica. O
  simulador publica `ramCost`, que é o campo da fonte; publicar os dois seria inventar um.
- **Não serve CSV** (`format=csv` → 400): servir CSV seria um segundo contrato para manter
  coerente com o primeiro.
- **Não lê os parâmetros que a fonte publica e o estate não honra** — `filterControllerKinds`,
  `filterLabels`, `filterAnnotations`, `filterServices`, `shareIdle`, `splitIdle`, `idleByNode`:
  recusados com **400**, nunca ignorados.
- **Não lê listas** de filtro (a spec as publica separadas por vírgula): esta fase lê **um**
  cluster, uma namespace e um controller por pedido.
- **Não publica GPU, custo compartilhado, custo externo, balanceador, ajustes nem eficiências** —
  o estate não tem figura para eles (a mesma regra do plano OpenCost).
- **Não exige token** e **não muda** os contratos OpenCost, da API do Kubernetes nem do Prometheus.

## 4. O mecanismo

- **Projeção nova** `emulators/k8s-sim/k8s_sim/projections/kubecost.py` — a **quarta** projeção do
  mesmo estate. Ela **reaproveita** a aritmética e a janela da projeção do allocation (as mesmas
  figuras, o mesmo rate card) e monta o allocation **na forma da Model API**: os custos com os
  nomes do Kubecost e as **quatro médias** (a requisição **é** o uso, como o plano Prometheus já
  afirmava). O plano OpenCost **não foi tocado**.
- **Rota** `GET /model/allocation` em `app.py`, ao lado dos outros três planos.
- **Alias do cluster**: o filtro aceita os **três** aliases (nome, `cluster_id` do estate,
  `native_id`) e a resposta carrega o **nome** — a mesma regra dos outros planos (§6.1 do
  contrato).
- **Erro**: o envelope `code` + `message` com o status HTTP no `code` — o mesmo do plano
  OpenCost (a spec declara o status `400`, não o corpo).

## 5. O teste da fase

### 5.1 O baseline, antes de qualquer mudança

- Suíte: `pytest emulators\k8s-sim\k8s_sim\tests -q -p no:cacheprovider` → **138 passed** em
  16,95 s.
- `ruff check emulators\k8s-sim --config emulators\k8s-sim\pyproject.toml` → **All checks passed!**
- `mypy --config-file pyproject.toml -p k8s_sim` (de `emulators/k8s-sim`) → **Success: no issues
  found in 11 source files**.
- Container: `synthetic-clouds-k8s-sim-1` no ar, `localhost/k8s-sim:latest`, "Up 34 minutes".
- Planos servidos: `/healthz`, `/clusterInfo`, `/allocation/compute`, `/api/v1/namespaces`,
  `/api/v1/pods`, `/api/v1/namespaces/{ns}/pods`, `/api/v1/query`.

### 5.2 A suíte, depois

- **164 passed** em 17,81 s — os **138** da S4b2-H mais **26** novos, em
  `emulators/k8s-sim/k8s_sim/tests/test_kubecost.py`.
- `ruff check emulators\k8s-sim --config emulators\k8s-sim\pyproject.toml` → **All checks passed!**
- `mypy --config-file pyproject.toml -p k8s_sim` → **Success: no issues found in 13 source files**.

**Provado em vermelho-verde, duas vezes.** Um único número foi mutado de cada vez, e a suíte foi
reexecutada:

1. `cpuCoreUsageAverage` recebeu `× 2` → **2 testes falharam** (o das médias e o de coerência com
   o plano Prometheus): **162 passed, 2 failed**. Restaurado → **164 passed**.
2. O passo padrão da Model API (de "a janela inteira" para o `accumulate` da requisição) →
   **1 teste falhou** (o do passo padrão): **163 passed, 1 failed**. Restaurado → **164 passed**.

### 5.3 O deploy: só o `k8s-sim`

```
$ podman compose -f compose.k8s.yaml up -d --build k8s-sim
--> 3ca4a396f51c
Successfully tagged localhost/k8s-sim:latest
 Container synthetic-clouds-k8s-sim-1 Recreate
 Container synthetic-clouds-k8s-sim-1 Recreated
 Container synthetic-clouds-k8s-sim-1 Started
```

A recriação perdeu o alias na bridge do CloudPilot e o IP do upstream no nginx (o `nginx.conf`
não tem `resolver` — dívida medida na S4b2-G). Corrigido do mesmo jeito, **sem recriar o front**:

```
$ podman network connect --alias k8s-sim cloudpilot-deploy_cloudpilot_net synthetic-clouds-k8s-sim-1
$ podman exec synthetic-clouds-tls-front nginx -s reload
2026/10/31 21:14:23 [notice] 743#743: signal process started

$ podman inspect synthetic-clouds-tls-front --format 'pid={{.State.Pid}} started={{.State.StartedAt}}'
pid=4329 started=2026-10-31 15:26:38.81766917 +0000 UTC      <-- o MESMO PID de antes
```

### 5.4 A rota nova, de dentro do `cloudpilot_backend`

Pelo **nome HTTPS** (`https://opencost.synthetic-clouds.test`), de dentro do container do backend:

```
[200] k8s-sim  kubecost  /model/allocation (aggregate=namespace)
        {"code":200,"data":[{"payments":{"name":"payments","properties":{"cluster":"TEMP-aks_cluster-0025","namespace":"payments","controller":"api"},"window":{"start":"2026-10-01T00:00:00Z","end":"2026-10-02T00:00:00Z"},"start"...
[200] k8s-sim  kubecost  /model/allocation (aggregate=controller)
        {"code":200,"data":[{"api":{"name":"api","properties":{"cluster":"TEMP-aks_cluster-0025","namespace":"payments","controller":"api"},"window":{"start":"2026-10-01T00:00:00Z","end":"2026-10-02T00:00:00Z"},"start"...
[200] k8s-sim  kubecost  /model/allocation (com Authorization)
        {"code":200,"data":[{"payments":{"name":"payments","properties":{"cluster":"TEMP-aks_cluster-0025",…
[404] k8s-sim  LACUNA    /model/clusterInfo (nao publicado pela Model API)
        {"detail":"Not Found"}
[404] k8s-sim  LACUNA    /savings/requestSizing (fora de escopo)
        {"detail":"Not Found"}
```

### 5.5 A não-regressão dos outros três planos

```
[200] k8s-sim  opencost  /allocation/compute
        {"code":200,"data":[{"payments/api":{"name":"payments/api","properties":{"cluster":"TEMP-aks_cluster-0025",…
[200] k8s-sim  opencost  /clusterInfo
        {"code":200,"data":{"version":"synthetic"}}
[200] k8s-sim  k8s-api   /api/v1/namespaces
        {"kind":"NamespaceList","apiVersion":"v1","metadata":{},"items":[{"kind":"Namespace","apiVersion":"v1","metadata":{"name":"payments"}}]}
[200] k8s-sim  k8s-api   /api/v1/pods
        {"kind":"PodList","apiVersion":"v1","metadata":{},"items":[{"kind":"Pod","apiVersion":"v1","metadata":{"name":"api","namespace":"payments",…
[200] k8s-sim  k8s-api   /api/v1/namespaces/payments/pods
        {"kind":"PodList","apiVersion":"v1","metadata":{},"items":[{"kind":"Pod","apiVersion":"v1","metadata":{"name":"api","namespace":"payments",…
[200] k8s-sim  prometheus/api/v1/query
        {"status":"success","data":{"resultType":"vector","result":[{"metric":{"namespace":"payments","cluster":"TEMP-aks_cluster-0025"},"value":[1793481290.0146353,"2000"]}]}}
[200] k8s-sim  healthz   /healthz
        {"status":"ok","synthetic":true}
```

### 5.6 O consumidor, de verdade

O **provider real** (`KubecostEnterpriseProvider`), rodando dentro do container do backend, contra
a **config salva da conta de homologação** e o **id nativo real** do estate:

```
get_cluster_costs OK -> [ClusterCostData(cluster_name='TEMP-aks_cluster-0025', namespace='payments', workload='api',
  date=datetime.date(2026, 10, 1), cpu_cost_usd=Decimal('1.92'), memory_cost_usd=Decimal('0'),
  storage_cost_usd=Decimal('0.384'), network_cost_usd=Decimal('1.0'), total_cost_usd=Decimal('3.88'),
  cpu_requests=Decimal('2.0'), memory_requests_gb=Decimal('4.0'), cpu_usage_avg=Decimal('2.0'),
  memory_usage_avg_gb=Decimal('4.0'), metadata={'cluster': 'TEMP-aks_cluster-0025', 'namespace': 'payments', 'controller': 'api'})]

get_namespace_costs OK -> [ClusterCostData(... mesmo conteúdo ...)]

get_cluster_health OK -> {'cluster_id': '…', 'status': 'unknown', 'message': 'Cluster health endpoint not available'}
get_recommendations FAIL -> ProviderDataError: Kubecost API returned HTTP 404: {"detail":"Not Found"}
test_connection FAIL -> ProviderDataError: Kubecost API returned HTTP 404: {"detail":"Not Found"}
```

O `memory_cost_usd=0` **não** é defeito do simulador: é a lacuna `memCost` (§6.1) — o consumidor lê
um campo que o Kubecost não publica.

### 5.7 A conta de homologação

Login na conta `homologation@cloudpilot.io` (a senha veio do MCP Memory e **não** foi gravada em
nenhum arquivo deste repositório nem neste documento):

```
[200] LOGIN
[200] ME
        {"id":"9f0bba98-…","email":"homologation@cloudpilot.io","name":"CloudPilot - Homologation","is_active":true,"default_workspace_id":"e757043f-…"}
[200] CONFIG
{
  "status": "ok",
  "data": {
    "provider_type": "opencost",
    "provider_endpoint": "https://opencost.synthetic-clouds.test",
    "has_token": "<presente>",
    "sync_interval_hours": 24,
    "clusters": [],
    "cluster_account_map": {},
    "last_sync_at": null,
    "sync_status": "idle"
  }
}
[200] CONFIG_PROVIDERS
{"provider_type": "aws", …}
{"provider_type": "azure", …}
{"provider_type": "gcp", …}
{"provider_type": "kubecost_enterprise", …}
{"provider_type": "opencost", …}
[200] OVERVIEW
{
  "status": "no_data"
}
```

**O que mudou no consumidor: nada.** A configuração continua `provider_type = opencost` (é o
provider que o plano OpenCost já serve, e é o que segue sem regressão), `clusters: []` e
`sync_status: idle`. O `/overview` responde `no_data` porque o **sync nunca rodou** — a config
não tem cluster para iterar (pendência da S4b2-E, fora do escopo desta fase).

## 6. Débitos e lacunas declaradas

### 6.1 Do lado do **consumidor** (o CloudPilot — fora da allowlist desta fase)

1. **`memCost`.** `kubecost.py:216` lê `alloc.get("memCost", 0)`; o Kubecost publica `ramCost`
   (F15, F16 — `memCost` não existe no modelo do Kubecost: grep, zero ocorrências). O
   `memory_cost_usd` sai **0**; `cpuCost`, `pvCost`, `networkCost` e `totalCost` estão certos.
   **Não** se publica um `memCost` para maquiar o número: o campo publicado é o da fonte.
2. **`/model/clusterInfo`.** O provider `kubecost` o chama em `get_cluster_health` e em
   `test_connection`, e a Model API **não** o publica. O 404 é tratado pelo `get_cluster_health`
   (`status="unknown"`), mas o `test_connection` **levanta** `ProviderDataError` — ou seja, o botão
   "Verificar Conexão" de uma config `kubecost_enterprise` não funciona contra um Kubecost real
   também, e a correção é do lado do consumidor.
3. **`/savings/requestSizing`.** O provider `kubecost` o chama no `get_recommendations`; a Model API
   publica `/model/savings/requestSizingV2` (outra rota, outra versão). Fora de escopo também
   pelo lado do OpenCost.
4. **A divergência entre o `main` do CloudPilot e o container em execução.** O construtor do
   provider **no `main`** (`29f7e535`) é `def __init__(self, config: object)` — sem `db` —, e a
   factory chama `provider_cls(config, db=db)`: no `main`, a factory **quebraria** para os
   providers `opencost` e `kubecost_enterprise`. O fix existe e está na branch
   `fix/cp-fix-01-provider-db-factory` (`8378af04`, 2026-10-30), **que não é ancestral do `main`**
   (`git merge-base --is-ancestor 8378af04 HEAD` → exit 1). O container em execução **tem** o fix —
   medido: `factory(kubecost_enterprise) -> OK KubecostEnterpriseProvider`. O `§9` do contrato
   descreve o defeito como se ele valesse para o ambiente; ele vale para o **`main`**, e o
   ambiente roda a branch do fix. **Observação, não ação**: o repositório do CloudPilot está fora
   da allowlist desta fase.

### 6.2 Do lado do **simulador**

5. **O `/savings/requestSizing`** não é servido (já era fora de escopo pelo plano OpenCost).
6. **A Metrics API** continua **não servida**, com a razão já medida (o provider `opencost` — o
   que aponta para este plano — tira a telemetria do Prometheus).
7. **A gêmea em inglês** do contrato (`docs/k8s-sim-opencost-contract.en.md`) continua **sem
   existir** (pendência da S4b1).
8. **O `config.clusters` da homologação está vazio**, então o sync agendado não itera cluster
   nenhum e o `/overview` responde `no_data` (pendência da S4b2-E).

## 7. Documentos afetados

| Documento | O que mudou |
|---|---|
| `emulators/k8s-sim/k8s_sim/projections/kubecost.py` | **novo** — a quarta projeção: a forma da Model API, os filtros, a janela e o `step` |
| `emulators/k8s-sim/k8s_sim/app.py` | a rota `GET /model/allocation` e o cabeçalho do módulo (quatro planos, oito rotas) |
| `emulators/k8s-sim/k8s_sim/tests/test_kubecost.py` | **novo** — 26 testes |
| `docs/k8s-sim-opencost-contract.md` | §1.0 (fontes F15–F19), §2.4 (o plano Kubecost), §9 (lacunas), §10.3 (os testes), título |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | o nome HTTPS passa a falar também a Model API; a tabela de hostnames |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | a entrega da fase e a seção do fase |
| `docs/regression/mapa-impacto-s4b2i.md` | **novo** — este documento |

## 8. O que esta fase **não** faz

- **Não toca** o `nginx.conf` do front, nem os outros emuladores, nem os outros composes, nem
  `specs/**`, `tools/**`, `scripts/**`, `AGENTS.md` ou `docs/NAO-COMPROVADOS*`.
- **Não toca** o código do CloudPilot — a leitura foi somente-leitura e a verificação usou a conta
  de homologação, **sem** alterar a configuração.
- **Não serve** a UI do plano Kubernetes nem a migration (fases seguintes).
- **Não roda** o sync agendado (`clusters: []`) nem conserta o botão "Verificar Conexão".
- **Não serve** `/model/clusterInfo` nem `/savings/requestSizing` — a fonte do Kubecost não os
  publica.
- **Não faz push.**
