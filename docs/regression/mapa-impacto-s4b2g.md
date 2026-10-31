# Mapa de impacto — Fase S4b2-G (a API do Kubernetes no `k8s-sim`: as três rotas que o consumidor chama)

**Data:** 2026-10-31 · **Revisão-base:** `a66b7a8e` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `emulators/k8s-sim/**` (código, fixture, testes, `pyproject.toml`),
`docs/k8s-sim-opencost-contract.md`, `docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/ESTADO.md`,
`docs/ESTADO.en.md`, `docs/regression/mapa-impacto-s4b2g.md` ·
**Fora do escopo:** `deploy/synthetic-clouds/tls-front/nginx.conf` (o front), os outros emuladores,
`compose.*.yaml`, `scripts/**`, `specs/**`, `tools/**`, `AGENTS.md`, `docs/NAO-COMPROVADOS*`
(gerado) e `C:\Projetos\cloudpilot-deploy/**` (leitura somente-leitura, para medir a superfície).

**Por que esta fase existe.** O contrato do `k8s-sim` (§9) nomeava "API server do Kubernetes" como
pendência **sem dizer qual**: o §9 é uma lista de itens que a fase anterior não implementou, não uma
especificação. A S4b2 fecha o TLS e o caminho de rede; o que sobrava era um plano inteiro — API
server, Prometheus, Kubecost, UI e migration — sem superfície definida. Esta fase fecha **uma
fatia**: o subconjunto da API do Kubernetes que o **consumidor real** chama.

**O desenho veio da leitura do consumidor, não de imaginação.** As rotas não foram escolhidas por
analogia com um API server real: foram lidas no código do CloudPilot (somente-leitura) e
**medidas** no checkpoint da fase. O `nginx.conf` do front está fora da allowlist, o que também
**forçou** o desenho: as rotas novas moram no **mesmo** nome HTTPS que já existia, dentro do
encaminhamento `location /` que o front já fazia.

## 1. O que muda

| | Antes (S4b2-E) | Depois (S4b2-G) |
|---|---|---|
| **Planos do `k8s-sim`** | um: o contrato OpenCost | **dois**: o contrato OpenCost (inalterado) e a API do Kubernetes |
| **Rotas** | `/healthz`, `/clusterInfo`, `/allocation/compute` | **+ `/api/v1/namespaces`, `/api/v1/pods`, `/api/v1/namespaces/{ns}/pods`** |
| **Auth** | nenhuma (o contrato OpenCost nunca pediu) | o plano novo pede **`Authorization: Bearer <token>`**; o plano OpenCost **continua sem pedir** |
| **Envelope** | `code`/`data` (OpenCost) | o plano novo usa as **formas oficiais** (`NamespaceList`, `PodList`, `Status`) |
| **Conteúdo publicado** | a allocation `payments/api` do estate | **+ a namespace `payments`, o workload `api` e o pod `api`** — o mesmo namespace e o mesmo workload, com `requests` = `cpu: "2"`, `memory: "4Gi"` |
| **URL** | `https://opencost.synthetic-clouds.test` | **inalterada** — as rotas novas respondem no mesmo nome |
| **Rede, TLS, compose, front** | — | **inalterados**: nenhum arquivo de `deploy/**` foi tocado |
| **Contrato OpenCost** | — | **inalterado**: mesmos status, mesmos corpos, mesmos números |

## 2. O checkpoint: a superfície foi medida, não escolhida

O pedido da fase exigia propor a superfície antes de editar. As três rotas saíram da leitura do
código do consumidor (2026-10-31, `C:\Projetos\cloudpilot-deploy`, **somente-leitura**):

| Rota | Quem chama | O que lê | Onde |
|---|---|---|---|
| `/api/v1/namespaces` | `ConnectionTester` (o teste que roda **antes** de salvar um kubeconfig) e os providers `gcp`/`azure` | `items[].metadata.name`; o `ConnectionTester` **falha** com lista vazia | `services/k8s_finops/connection_tester.py`, `providers/gcp.py:125`, `providers/azure.py:182` |
| `/api/v1/pods` | o provider `aws`, pelo client **oficial** `kubernetes` (`CoreV1Api.list_pod_for_all_namespaces`) | `items[]`: `metadata.namespace`, `metadata.ownerReferences[]`, `spec.containers[].resources` | `providers/aws.py:350` e `:380` |
| `/api/v1/namespaces/{ns}/pods` | os providers `gcp`/`azure`, uma vez por namespace | idem | `providers/gcp.py:136`, `providers/azure.py:193` |

**O que o checkpoint aprovou** (decisão do usuário, 2026-10-31): superfície **mínima** (as três
rotas, sem `/version`, sem `apis/apps/v1`, sem Metrics API), **Bearer obrigatório** com qualquer
token não-vazio aceito (o simulador não modela identidade nem RBAC), e conteúdo **coerente**: uma
namespace `payments` e um pod `api` com os mesmos `requests` que o contrato OpenCost precifica.

**O que a leitura do consumidor acrescenta, e o checkpoint não previa.** O consumer constrói o
custo de uma namespace **somando os `requests` dos pods** dela
(`_namespace_usage_from_pods`, `providers/gcp.py:591+`). Publicar requests diferentes dos que o
contrato OpenCost precifica faria o simulador dizer duas verdades sobre o mesmo cluster — por isso
o pod declara `cpu: "2"` e `memory: "4Gi"`, que são exatamente os 2 núcleos e os 4 GiB por dia da
§6 do contrato. Um teste fixa essa coerência entre os dois planos.

## 3. O que a fase **não** faz (e está declarado no contrato)

- **Não é um API server**: é o subconjunto que o consumidor chama. Sem `/version`, `/api`, `/apis`,
  sem `apis/apps/v1/.../{workload}` (labels, best-effort no consumidor), sem
  `apis/metrics.k8s.io/v1beta1/pods` (Metrics API; Prometheus é o S4b2-H), sem `nodes`, sem RBAC.
- **Não publica o que o estate não modela**: sem `limits` (o estate não modela um limite distinto do
  pedido), sem `status` do pod, sem `image`, sem `resourceVersion`, sem `uid` nos metadados.
- **Não toca no contrato OpenCost**: as rotas antigas continuam sem token, com o mesmo envelope e os
  mesmos números.
- **Não toca no CloudPilot**: `C:\Projetos\cloudpilot-deploy` não recebeu uma linha de código.
- **Não toca no front**: `nginx.conf` está fora da allowlist, e as rotas novas não exigiram mudá-lo.

## 4. O mecanismo

| Arquivo | O que faz |
|---|---|
| `emulators/k8s-sim/k8s_sim/projections/kubernetes.py` | **novo** — a segunda projeção do estate: a namespace, o workload e o pod, com as formas oficiais |
| `emulators/k8s-sim/k8s_sim/app.py` | as três rotas, o `Status` oficial e o `Bearer` obrigatório |
| `emulators/k8s-sim/k8s_sim/tests/test_kubernetes_api.py` | **novo** — 31 testes do contrato novo |
| `docs/k8s-sim-opencost-contract.md` | §2.2 (o plano novo), §9 (pendência fechada), §10.1 (os testes) |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | as URLs novas no mesmo nome + o que não sobrevive a um `up -d --build k8s-sim` |

**Nenhum** arquivo de `deploy/**` foi tocado: a porta é a mesma (`8089`), o nome é o mesmo, o
caminho é o mesmo.

## 5. O teste da fase

### 5.1 O baseline, antes de qualquer mudança

```
$ pytest emulators\k8s-sim\k8s_sim\tests -q -p no:cacheprovider
91 passed, 1 warning in 12.73s

$ podman exec cloudpilot_backend python -c "... urlopen('https://opencost.synthetic-clouds.test/...') ..."
/healthz 200 {"status":"ok","synthetic":true}
/clusterInfo?filter=cluster:"TEMP-aks_cluster-0025" 200 {"code":200,"data":{"version":"synthetic"}}
/allocation/compute?window=2026-10-01,2026-10-02&... 200 {"code":200,"data":[{"payments":{...
```

Os três endpoints OpenCost respondiam 200 **de dentro do `cloudpilot_backend`**, pelo nome HTTPS, com
o TLS validado contra a CA local.

### 5.2 A suíte, depois

```
$ pytest emulators\k8s-sim\k8s_sim\tests -q -p no:cacheprovider
122 passed, 1 warning in 12.80s          # 91 + 31

$ ruff check emulators\k8s-sim --config emulators\k8s-sim\pyproject.toml
All checks passed!

$ mypy --config-file emulators\k8s-sim\pyproject.toml -p k8s_sim
Success: no issues found in 9 source files
```

### 5.3 O deploy: só o `k8s-sim`

```
$ podman compose -f deploy\synthetic-clouds\compose.k8s.yaml up -d --build k8s-sim
Successfully built 8234a51bc44e
Container synthetic-clouds-k8s-sim-1  Recreated
Container synthetic-clouds-k8s-sim-1  Started
EXIT=0
```

### 5.4 O contratempo do 502, e a causa raiz

A primeira chamada depois do recreate devolveu **502 Bad Gateway** em **todas** as rotas do nome —
inclusive nas que já funcionavam. Não era o serviço novo, e não era o token: eram **duas** coisas
que a recriação do container quebra.

**A primeira: o alias.** A bridge do CloudPilot (`cloudpilot-deploy_cloudpilot_net`) **não** está
no `compose.k8s.yaml`; quem anexa o container a ela com o alias `k8s-sim` é o
`ensure-cloudpilot.ps1`. Recriar o container desfaz a anexação.

**A segunda: o IP.** O `nginx.conf` **não tem `resolver`** (`nginx.conf:44-46`): o nome do upstream
é resolvido **uma vez**, na carga da configuração. O front continuava apontando para o IP antigo
(`10.89.0.19`), enquanto o container novo já estava em `10.89.0.21` — e o DNS do front, consultado
de novo, devolvia o IP novo. O front estava falando com um container que não existia mais.

A correção, **sem recriar o front** (o `nginx.conf` e o container do front estão fora da
allowlist, e recriar o front derrubaria todos os planos):

```powershell
podman network connect --alias k8s-sim cloudpilot-deploy_cloudpilot_net synthetic-clouds-k8s-sim-1
podman exec synthetic-clouds-tls-front nginx -s reload     # re-lê a config e resolve o upstream de novo
```

O `nginx -s reload` mantém o container do front **intacto** (mesmo PID, mesmo uptime, mesmos
aliases). O aviso `listen ... http2 is deprecated` que aparece no reload vem do bloco do SCC
(linha 196 do `nginx.conf`), é **pré-existente** e não é desta fase.

### 5.5 As rotas novas, de dentro do backend

```
PROBE|K8S namespaces (com token)|{"status": 200, "body": "{\"kind\":\"NamespaceList\",\"apiVersion\":\"v1\",\"metadata\":{},\"items\":[{\"kind\":\"Namespace\",\"apiVersion\":\"v1\",\"metadata\":{\"name\":\"payments\"}}]}"}
PROBE|K8S pods (com token)|{"status": 200, "body": "{\"kind\":\"PodList\",..."}
PROBE|K8S pods da namespace|{"status": 200, "body": "{\"kind\":\"PodList\",..."}
PROBE|K8S namespaces (sem token)|{"status": 401, "body": "{\"kind\":\"Status\",...\"reason\":\"Unauthorized\",\"code\":401}"}
PROBE|K8S namespace inexistente|{"status": 404, "body": "{\"kind\":\"Status\",...\"reason\":\"NotFound\",\"code\":404}"}
PROBE|OpenCost healthz|{"status": 200, ...}
PROBE|OpenCost clusterInfo|{"status": 200, ...}
PROBE|OpenCost allocation/compute|{"status": 200, ...}
```

### 5.6 O client **oficial** `kubernetes`, e o `ConnectionTester` real

O `kubernetes` **37.0.1** está instalado no container do backend. O mesmo client que o provider
`aws` usa, contra o `k8s-sim` no ar:

```
K8SCLIENT|pods_type=V1PodList count=1
K8SCLIENT|pod=payments/api owner=Deployment/api uid=synthetic-deployment-api requests={"cpu": "2", "memory": "4Gi"}
K8SCLIENT|namespaces=["payments"]
CONNTESTER|{"success": true, "namespace_count": 1, "error_type": null, "error_message": null, "latency_ms": 184}
```

O `ConnectionTester` do CloudPilot — o código que decide se um kubeconfig conecta — respondeu
`success: true`, **1 namespace**.

### 5.7 O consumidor, na conta de homologação

Login com `homologation@cloudpilot.io` e o **endpoint real** do CloudPilot (o teste de kubeconfig
que a UI chama antes de salvar):

```
LOGIN|status=200
ME|status=200 email=homologation@cloudpilot.io
KUBECONFIG_TEST|status=200
KUBECONFIG_TEST|body={"success": true, "namespace_count": 1, "server_url": "https://opencost.synthetic-clouds.test", "error_type": null, "error_message": null, "latency_ms": 21}
```

O kubeconfig do teste apontava para `https://opencost.synthetic-clouds.test` e trazia um token de
portão. A senha da conta veio do MCP Memory e **não** foi gravada em nenhum arquivo deste repositório
nem neste documento.

### 5.8 A não-regressão do contrato OpenCost, pelo **provider real**

O provider `opencost` do CloudPilot, instanciado com a config **salva** da conta de homologação
(workspace `e757043f-2325-506b-b3eb-e61f8d07147d`), lendo o custo pelo nome e pelo id nativo:

```
PROVIDER:{"workspace_id": "e757043f-2325-506b-b3eb-e61f8d07147d", "provider_type": "opencost",
          "endpoint_saved": "https://opencost.synthetic-clouds.test", "success": true, "latency_ms": 32, "error_message": null}
COSTS:{"read": "name",      "rows": 2, "first": {"cluster_id": "TEMP-aks_cluster-0025", "cluster_name": "TEMP-aks_cluster-0025",
                                                 "namespace": "payments", "workload": "api", "total_cost_usd": "3.88", "date": "2026-10-01"}}
COSTS:{"read": "native_id", "rows": 2, "first": {"cluster_id": "/subscriptions/0aa7d1ea-…/managedClusters/TEMP-aks_cluster-0025",
                                                 "cluster_name": "TEMP-aks_cluster-0025", "namespace": "payments", "workload": "api",
                                                 "total_cost_usd": "3.88", "date": "2026-10-01"}}
```

Os mesmos números que a S4b2-E mediu (`payments/api`, 3.88 USD, 2026-10-01), pelo nome e pelo id
nativo. O endpoint `/api/v1/finops/kubernetes/clusters` da conta de homologação responde
`{"status":"no_data","meta":{"reason":"First sync has not completed yet"}}` — estado **pré-existente**
do CloudPilot (nenhum snapshot foi gravado; é a pendência "rodar sync" que a S4b2-E já tinha
declarado), e não uma consequência desta fase.

### 5.9 Os outros planos, intactos

```
$ podman exec synthetic-clouds-tls-front nginx -t
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful

$ podman exec cloudpilot_backend python -c "import httpx; ..."
compute.googleapis.com 404
bigquery.googleapis.com 200

$ podman ps --format '{{.Names}}\t{{.Status}}'
synthetic-clouds-azure-sim-1   Up 4 hours (healthy)
synthetic-clouds-gcp-sim-1     Up 4 hours (healthy)
synthetic-clouds-aws-sim-1     Up 4 hours (healthy)
synthetic-clouds-tls-front      Up 4 hours (healthy)
cloudpilot_backend              Up 4 hours (healthy)
synthetic-clouds-k8s-sim-1     Up 3 minutes (healthy)   <-- o único recriado
```

## 6. O defeito que só o client oficial enxergou

A primeira versão do plano publicava a `ownerReference` **sem `uid`** — o estate não modela
identidade de objeto, e a omissão parecia correta pela regra do repo. O client oficial **a
recusou**:

```
pydantic_core._pydantic_core.ValidationError: 1 validation error for V1OwnerReference
uid
  Input should be a valid string [type=string_type, input_value=None, input_type=NoneType]
```

O `uid` da referência é **campo obrigatório** do modelo `V1OwnerReference` no `kubernetes` 37.x.
Medido no container do backend, campo a campo (`model_fields` com `is_required()`):

| Modelo | Campos obrigatórios |
|---|---|
| `V1OwnerReference` | `apiVersion`, `kind`, `name`, **`uid`** |
| `V1Container` | **`name`** |
| `V1PodSpec` | **`containers`** |
| `V1PodList` | **`items`** |
| `V1NamespaceList` | **`items`** |
| `V1ObjectMeta`, `V1Namespace`, `V1ResourceRequirements`, `V1ListMeta` | nenhum |

O `uid` é o único que o "publicar só o que o estate modela" apaga, e é o único que o modelo
**exige**. A correção publica um **placeholder declarado e determinístico**
(`synthetic-deployment-api`), que diz o que é em vez de vestir um UUID que não ganhou — e os
testes fixam a lista inteira de campos obrigatórios como literal, para que o próximo campo
obrigatório que o modelo pedir não passe despercebido.

**Por que isso importa para a fase.** Um teste que só conferisse o JSON "parece certo" teria
aceitado o payload. O que o reprovou foi **o cliente real do consumidor**, no ar. A lição é a
mesma das outras fases do repo: a fidelidade se mede contra o consumidor, não contra a
plausibilidade do payload.

## 7. Débitos e lacunas declaradas

1. **Não é um API server**: as rotas de descoberta, as labels do workload, a Metrics API, os
   `nodes` e o RBAC não são servidos (§3). Declarado no contrato, §2.2.6.
2. **O plano descreve UM cluster sintético**, não os 309 do estate: o `k8s-sim` serve uma
   namespace e um workload — o mesmo par `payments/api` que o contrato OpenCost precifica. O
   `filter` por cluster do contrato OpenCost não tem contrapartida aqui: a API server é por
   cluster, e este plano é de um cluster só.
3. **O `ownerReference` aponta para um `Deployment` que o plano não serve como recurso**: as
   labels do workload (`apis/apps/v1`) estão fora da superfície. O consumidor as lê em
   `get_workload_labels` e trata a falta como `{}` — best-effort, sem quebra.
4. **O Prometheus é o S4b2-H**, e a Metrics API (`apis/metrics.k8s.io/v1beta1/pods`) vai com ele.
5. **O botão "Verificar Conexão" da UI continua quebrado** — defeito **pré-existente** do
   CloudPilot (a factory passa `db=` a um provider que não o aceita), detalhado no
   [mapa da S4b2-E](mapa-impacto-s4b2e.md) §6. **Esta fase não o tocou** e **não pode**: o
   CloudPilot está fora da allowlist.
6. **O `ensure-cloudpilot.ps1` reanexa o alias, mas não recarrega o nginx**: depois de qualquer
   recriação do `k8s-sim`, o front precisa do `nginx -s reload`. Está documentado no
   `INTEGRACAO-CLOUDPILOT-TLS.md`, e é a dívida operacional que a fase deixa.
7. **A gêmea em inglês do contrato** (`docs/k8s-sim-opencost-contract.en.md`) continua **sem
   existir** — pendência herdada da S4b1, declarada no contrato (§9).

## 8. Documentos afetados

| Documento | O que mudou |
|---|---|
| `docs/k8s-sim-opencost-contract.md` | §2.2 (o plano novo, com a superfície medida e o `uid` exigido pelo modelo), §2.2.6 (o que não é servido), §9 (a pendência "API server do Kubernetes" fechada, com data), §10 e §10.1 (os 31 testes novos e a contagem) |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | as URLs da API do Kubernetes no mesmo nome HTTPS + a seção do que não sobrevive a um `up -d --build k8s-sim` |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | a linha da fase |
| `docs/regression/mapa-impacto-s4b2g.md` | este documento |

## 9. O que esta fase **não** faz

- **Não** implementa o Prometheus, o Kubecost, a UI do plano Kubernetes nem a migration — são o
  resto da S4b2.
- **Não** toca no `nginx.conf`, no `compose.k8s.yaml` nem em qualquer outro plano.
- **Não** toca no CloudPilot (leitura somente-leitura, para medir a superfície).
- **Não** roda o sync do CloudPilot nem grava snapshot: essa pendência é da S4b2-E e continua
  aberta.
- **Não** fecha o botão "Verificar Conexão" da UI, que morre num defeito do CloudPilot.
