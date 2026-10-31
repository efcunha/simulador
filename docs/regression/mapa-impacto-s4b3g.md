# Mapa de impacto — Fase S4b3-G (o plano Kubernetes no ar de ponta a ponta)

**Data:** 2026-10-31
**Branch do simulador:** `feat/p76-security-posture-gcp-azure`
**Branch do consumidor:** `C:\Projetos\cloudpilot-deploy` → `main`
**Escopo (simulador):** `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`,
`docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/ESTADO.md`, `docs/ESTADO.en.md`,
`docs/regression/mapa-impacto-s4b3g.md`.
**Escopo (consumidor):** `backend/app/services/k8s_finops/providers/opencost.py` e
`kubecost.py` (autorizados **se necessário** — não foi preciso: §4.3), o `main` do CloudPilot
(merge do fix `8378af04`) e a **config do workspace de homologação**, escrita pela API oficial
(§2.2).
**Fora do escopo:** `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`,
`deploy/synthetic-clouds/tls-front/**` (o `nginx.conf`), `specs/**`, `tools/**`, `scripts/**`,
`AGENTS.md`, `docs/NAO-COMPROVADOS*` e o resto do código do CloudPilot.

---

## 1. O que muda

Três coisas, cada uma fechando uma pendência **nomeada** por uma fase anterior:

| Pendência | Quem nomeou | Como fecha |
|---|---|---|
| o `ensure-cloudpilot.ps1` reanexa o alias `k8s-sim` mas **não** recarrega o nginx: o front precisa do reload depois de qualquer recriação do `k8s-sim` | S4b2-G, `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | o script passa a **recarregar o nginx** (`nginx -s reload`, no container vivo) e a **medir os quatro planos** pelo nome HTTPS, sem recriar o front |
| o `clusters: []` da config de homologação: o sync não itera cluster nenhum, e `/finops/kubernetes/overview` responde `no_data` ("First sync has not completed yet") | S4b2-E e S4b2-H | a config é gravada pela **API oficial** (`PUT /config`) com os **103 `native_id`** das três contas do workspace, e o sync materializa **3.193 snapshots** |
| o botão "Verificar Conexão" morre num `TypeError`: a factory passa `db=` a providers que não o aceitam (`opencost.py:47`, `kubecost.py:44`) | S4b2-E, S4b2-F, S4b2-G | o fix `8378af04` entra no `main` do CloudPilot (merge `126970e5`) e `POST /config/test-connection` responde **200** |

---

## 2. As três pendências, e a medição de cada uma

### 2.1 O alias e o IP do upstream — a causa raiz do 502

**O `nginx.conf` do front não tem `resolver`** (medido: `grep -rn 'resolver' /etc/nginx/` → **0
ocorrências**), e o upstream é um **nome**:

```
/etc/nginx/conf.d/default.conf:45:    server k8s-sim:8089;
```

Logo, o endereço do upstream é resolvido **uma vez**, na carga da configuração, e o worker
mantém aquele endereço. Um container do `k8s-sim` **recriado** não volta para o mesmo endereço —
e o `compose.k8s.yaml` declara o alias `k8s-sim` na rede **dos simuladores**
(`synthetic-clouds_synthclouds_net`), **não** na bridge do CloudPilot: quem anexa o container à
bridge `cloudpilot-deploy_cloudpilot_net` é o `ensure-cloudpilot.ps1`.

O sintoma medido, **antes** da correção (de dentro do `cloudpilot_backend`, pelo nome HTTPS):

```
PLANES:{"opencost":{"status":null,"error":"TimeoutError('The read operation timed out')"},
        "kubernetes":{"status":null,"error":"<HTTPError 502: 'Bad Gateway'>"},
        "prometheus":{"status":null,"error":"<HTTPError 502: 'Bad Gateway'>"},
        "kubecost":{"status":null,"error":"<HTTPError 502: 'Bad Gateway'>"}}
```

e o log do próprio front, que **nomeia a causa**:

```
[error] connect() failed (113: Host is unreachable) while connecting to upstream,
        client: 10.89.0.5, server: opencost.synthetic-clouds.test,
        request: "GET /api/v1/namespaces HTTP/1.1",
        upstream: "http://10.89.0.24:8089/api/v1/namespaces"
```

O `10.89.0.24` era o endereço do container **anterior**. A correção é o par
`podman network connect --alias k8s-sim …` + `nginx -s reload`, **sem** recriar o front.

**O que a fase muda:** o `nginx -s reload` deixa de ser um passo manual e passa a ser parte do
`ensure-cloudpilot.ps1` (`Sync-FrontUpstream`), seguido de uma **medição** dos quatro planos
(`Test-K8sSimPlanes`) que roda de dentro do `cloudpilot_backend`.

### 2.2 O `clusters: []` — a configuração do workspace de homologação

**Baseline medido** (antes da escrita):

```
GET /api/v1/finops/kubernetes/config      -> 200  provider_type=opencost
                                                 provider_endpoint=https://opencost.synthetic-clouds.test
                                                 has_token=true  clusters=[]  cluster_account_map={}
                                                 last_sync_at=null  sync_status=idle
GET /api/v1/finops/kubernetes/overview     -> 200  {"status":"no_data",
                                                 "meta":{"reason":"First sync has not completed yet"}}
GET /api/v1/finops/kubernetes/sync/status  -> 200  clusters=[]  overall_status=idle
```

**A descoberta oficial não é o caminho.** `GET /config/discover-clusters` responde 200, mas
**todas as cinco contas do workspace falham**: `AWS Account 1` e `AWS Account 2` com
`InvalidClientTokenId` do STS, `[SYNTH] AWS acct-01` com `404 NoSuchBucket` (S3),
`[SYNTH] GCP contoso-prod-01` com 404 de `container.googleapis.com` e
`[SYNTH] AZURE container-export-01` com `cannot import name 'ResourceManagementClient' from
'azure.mgmt.resource'`. A descoberta conversa com as APIs nativas de cada nuvem, e é isso que o
simulador não expõe nesse caminho.

**O caminho que funciona é o da configuração, pela API oficial.** O `PUT /config` com os
**`native_id`** (ARN do EKS, id ARM do AKS, `selfLink` do GKE) evita a descoberta: o
`_canonicalize_cluster_selection` do CloudPilot só chama o discovery quando a seleção **não**
"parece identificador canônico", e o `native_id` é exatamente isso. As três formas foram
medidas contra o `k8s-sim`, pelo nome HTTPS:

```
PROBE arn:aws:eks:us-east-1:911368690069:cluster/TEMP-eks_cluster-0141                -> 200
PROBE /subscriptions/61a34ffc-…/managedClusters/TEMP-aks_cluster-0106                -> 200
PROBE projects/contoso-prod-01/locations/europe-west1/clusters/TEMP-gke_cluster-0037  -> 200
```

Os três respondem o **mesmo** envelope OpenCost (`code` + `data`), a mesma entrada
(`payments/api`), o mesmo custo (`totalCost=3.88`) e o `properties.cluster` com o **nome**
(`TEMP-eks_cluster-0141`, `TEMP-aks_cluster-0106`, `TEMP-gke_cluster-0037`) — o id nativo é a
chave da requisição, o nome é o que o contrato publica.

**A escrita (registrada, como o enunciado exige).** `PUT /api/v1/finops/kubernetes/config`
com `provider_type=opencost`, `provider_endpoint=https://opencost.synthetic-clouds.test`,
`sync_interval_hours=24`, `clusters` = **103 `native_id`** e `cluster_account_map` = **103
entradas** (o mesmo `native_id` → UUID da conta). O `kubecost_token` **não** foi enviado: a
`update_config` só re-criptografa o token quando o campo vem, e omiti-lo **preserva** o token
existente — o `has_token` continua `true` depois da escrita.

As 103 entradas são as três contas `[SYNTH]` do workspace `e757043f-2325-506b-b3eb-e61f8d07147d`
("[SYNTH] Synthetic Workspace synthetic-homologation"):

| Conta | UUID | Clusters no `native_id` | Chave |
|---|---|---|---|
| `[SYNTH] AWS acct-01` (`911368690069`) | `f4b259ca-3a0d-49bb-ade9-bf75101317c8` | 25 | ARN do EKS |
| `[SYNTH] AZURE container-export-01` (`61a34ffc-…`) | `212dc724-eb8f-4ab4-b108-0321076cbb12` | 41 | id ARM do AKS |
| `[SYNTH] GCP contoso-prod-01` | `a77c3a50-d925-4a4e-9ae8-b15b9c8cdf5b` | 37 | `selfLink` do GKE |

**O sync, e o que ele materializou.** `POST /api/v1/finops/kubernetes/sync` → 200; a tarefa
`k8s_finops_sync_workspace` (fila `k8s_costs`, worker `celery_worker_k8s`) faz o *gap-fill* de
30 dias e grava por data:

```
select count(*), min(date), max(date) from k8s_cost_snapshots
  where workspace_id='e757043f-…';      ->  3193 | 2026-10-01 | 2026-10-31
select status, count(*) from …            ->  success | 103
```

**3.193 = 103 clusters × 31 dias**, e **103/103 clusters** com status `success`.

**O overview deixou de ser `no_data`:**

```
GET /api/v1/finops/kubernetes/overview -> 200
{"status":"ok","data":{"total_cost":"12388.8400","cost_trend":null,"cluster_count":103,
 "namespace_count":1,
 "top_cost_drivers":[{"name":"payments","cluster":"gke_cluster-0367","cost":"12388.8400",
                       "percentage_of_total":100.0}],
 "active_alerts_count":0,"budget_utilization_percentage":null,"staleness_warning":null},
 "meta":{"requested_start_date":"2026-10-01","requested_end_date":"2026-10-31",
         "covered_days":31,"expected_days":31,"coverage_percent":100.0,
         "min_data_date":"2026-10-01","max_data_date":"2026-10-31",
         "last_successful_sync_at":"2026-10-31T22:28:31.807103Z","is_stale":false,
         "data_source":"k8s_cost_snapshots","attribution_method":"resource_tag",
         "value_type":"measured","confidence":"high","decision_eligible":true}}
```

O `total_cost` é a soma de 103 clusters de **3,88 USD/dia** (o mesmo `payments/api` que o
contrato precifica desde a S4b2-E) × 31 dias: `103 × 3,88 × 31 = 12.388,84`. A cobertura é de
**31/31 dias (100 %)** e `is_stale` é `false`.

### 2.3 O botão "Verificar Conexão" — o defeito do `db`

A factory do CloudPilot instancia o provider **sempre** com `db=`:

```python
# backend/app/services/k8s_finops/providers/factory.py
provider_cls(config, db=db)
```

e nem `OpenCostProvider.__init__` nem `KubecostEnterpriseProvider.__init__` declaravam `db` —
o que faz **todo** endpoint que passa pela factory levantar
`TypeError: OpenCostProvider.__init__() got an unexpected keyword argument 'db'`.

**O que a fase encontrou, medido (e que muda o enunciado da fase):** o botão **já** respondia
200 **no container em execução**, porque a imagem do backend carrega o fix
(`org.opencontainers.image.revision=8378af04…`) — mas o **`main` do repositório não**. Os dois
códigos foram comparados por hash:

| Arquivo | `main` (host) | container em execução |
|---|---|---|
| `opencost.py` | `3ea1048402d3693a8b556ec3fece247d` | `3ea1048402d3693a8b556ec3fece247d` |
| `kubecost.py` | `110227261d93cafceb945117c64e8683` | `110227261d93cafceb945117c64e8683` |

*(as duas colunas só ficaram iguais **depois** do merge; antes, o `main` tinha
`dca2b98593b063ec95553c2f454959a0` para o `opencost.py`.)*

**O que a fase fez:** o fix `8378af04` ("accept db in OpenCost and Kubecost provider
constructors") entrou no `main` do CloudPilot por **merge** — commit `126970e5`, **3 arquivos**,
`git diff --check` exit 0:

```
 backend/app/services/k8s_finops/providers/kubecost.py  |  9 +-
 backend/app/services/k8s_finops/providers/opencost.py  |  7 +-
 .../k8s_finops/test_provider_factory_db.py             | 110 +++++++++++++
```

O `git diff main...fix/cp-fix-01-provider-db-factory` (três pontos) mostra **exatamente** esses
3 arquivos: o merge não traz nenhuma outra linha do branch.

**A prova do botão, depois do merge:**

```
POST /api/v1/finops/kubernetes/config/test-connection -> 200
{"status":"ok","data":{"success":true,"latency_ms":18,"provider_version":null,
                       "error_message":null}}
```

O `provider_type` da config é `opencost` e o provider instanciado pela factory é o
`OpenCostProvider` — o `opencost.py` do `main`, byte a byte igual ao do container.

---

## 3. O que foi corrigido, arquivo por arquivo

### 3.1 `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`

| Mudança | Por quê |
|---|---|
| `Ensure-NetworkAliases` **devolve `$true`/`$false`** (a anexação mudou?) | o chamador precisa saber se o upstream pode ter mudado de endereço |
| **nova** `Sync-FrontUpstream` → `podman exec <front> nginx -s reload` | o `nginx` **não tem `resolver`**: sem o reload, o front continua dialando o endereço morto. O reload acontece **no container vivo** (mesmo master, mesmos workers reciclados): o front **não** é recriado, e o endereço/certificado que ele serve não mudam |
| **nova** `Test-K8sSimPlanes` → os **quatro** planos (`/allocation/compute`, `/api/v1/namespaces`, `/api/v1/query`, `/model/allocation`) pelo nome HTTPS, medidos de dentro do `cloudpilot_backend` | a medição é o que diz se o front está encaminhando para o upstream **atual**; um front com endereço velho responde 502 |
| passos **2c** (reload) e **2d** (medição) no fluxo principal | o recarregamento e a prova ficam no caminho idempotente do script, não em passo manual |
| a descrição do script passa a citar o passo 2c | o `.DESCRIPTION` é a contrato do script |

**Idempotência (medida, duas passagens consecutive):**

```
1ª passagem:  connecting synthetic-clouds-k8s-sim-1 to cloudpilot-deploy_cloudpilot_net with aliases k8s-sim
               tls-front: nginx reloaded; upstreams resolved again
               k8s-sim plane opencost|kubernetes|prometheus|kubecost = 200 by HTTPS name
               summary: integration OK (0 problems)          -> exit 0
2ª passagem:  synthetic-clouds-k8s-sim-1 aliases OK on cloudpilot-deploy_cloudpilot_net
               tls-front: nginx reloaded; upstreams resolved again
               k8s-sim plane opencost|kubernetes|prometheus|kubecost = 200 by HTTPS name
               summary: integration OK (0 problems)          -> exit 0
```

A 2ª passagem **não reanexa** nada (o alias já está) e continua verde. O front **não** foi
recriado em nenhuma das duas: mesmo container (`9a313a73ab7f…`) e mesmo `StartedAt`
(`2026-10-31 15:26:38`). O `k8s-sim` novo (`7e3ca5bbf3d4…`) ficou em `10.89.0.25` na bridge —
**endereço diferente** do `10.89.0.24` que o nginx tinha em cache, o que prova que o reload
não era decorativo.

### 3.2 `docs/INTEGRACAO-CLOUDPILOT-TLS.md`

A seção "O que mais não sobrevive a um `up -d --build k8s-sim`" afirmava que o
`ensure-cloudpilot.ps1` reanexa o alias mas **não** recarrega o nginx. A afirmação ficou
**falsa** e foi corrigida, com a data do fechamento.

### 3.3 `docs/ESTADO.md` / `docs/ESTADO.en.md`

Linha na tabela "Entregas registradas" e seção própria da fase, nas duas línguas.

### 3.4 `deploy/synthetic-clouds/.env`

**Não tocado.** A configuração do plano Kubernetes vive no **consumidor** (a config do
workspace, gravada pela API), não no `.env` do simulador: o `.env` fixa o perfil/seed/janela do
estate, e nenhum deles muda nesta fase.

### 3.5 CloudPilot — `main`

Merge `126970e5`, **3 arquivos** (§2.3). Nenhuma outra linha do repositório do consumidor foi
tocada; o trabalho F0 do usuário, commitado em `feat/k8s-mgmt-f0-foundation` (`8d7a9d4b`), ficou
intacto.

---

## 4. Lacunas declaradas (o que esta fase **não** resolve)

### 4.1 A telemetria Prometheus não chega ao runtime — `K8S_PROMETHEUS_URL`

`backend/.env.local` **linha 272** tem `K8S_PROMETHEUS_URL=https://opencost.synthetic-clouds.test`
(mtime **2026-10-31 17:20:44**), mas os containers do CloudPilot foram criados **antes**
(`StartedAt` **2026-10-31 00:48 UTC**) e **não têm** a variável:

```
podman exec cloudpilot_backend env | grep -i K8S_PROMETHEUS   ->  (vazio)
podman exec cloudpilot_backend env | grep -i K8S_FINOPS        ->  K8S_FINOPS_CHARGEBACK_EXPORT_ENABLED=false
                                                                  K8S_FINOPS_DECISION_ACTIONS_ENABLED=false
                                                                  K8S_FINOPS_MIN_COVERAGE_PERCENT=50.0
                                                                  K8S_FINOPS_RIGHTSIZING_ACTIONS_ENABLED=false
```

Consequência medida nos snapshots: **`cpu_usage_current_millicores` é nulo em 3.193 linhas e
`collection_method` é nulo em 3.193 linhas**. O plano Prometheus do `k8s-sim` está publicado e
responde **200** (§2.1), mas o provider não o consulta, porque não há endpoint configurado no
processo. O sync **não** falhou por causa disso: `_query_prometheus` devolve vetor vazio quando
não há endpoint, e `_enrich_cost_data_telemetry` sai sem tocar as linhas.

**Fechar esta lacuna exige recriar os containers do CloudPilot** — fora do escopo desta fase,
e a recriação traria a imagem do `main` (que hoje já contém o merge) para um backend cujo
`main` também carrega o trabalho F0 do usuário, não commitado. Declarada, não deduzida.

### 4.2 A conta GCP e o projeto do estate

O `cluster_account_map` dos 37 clusters GKE foi atribuído à conta
`[SYNTH] GCP contoso-prod-01` pelo **nome** da conta e pelo **projeto que o `gcp-sim` serve**
(`contoso-prod-01`). A credencial da conta, **descriptografada**, carrega
`project_id: "synthetic"` e `client_email: synth-sa@contoso.example` — que **não** é
`contoso-prod-01`. Não existe, no CloudPilot, uma coluna que guarde o projeto do estate: o
`external_account_id` e o `subscription_id` estão **vazios** nessa conta (o `billing_table` é
`synthetic.all_billing_data.gcp_billing_export_resource_v1_ba_gcp_1`).

`ASSUMPTION:` o projeto `contoso-prod-01` é o da conta `[SYNTH] GCP contoso-prod-01`. O
`external_account_id` **não** é uma alternativa — está vazio também. O único lugar em que a
ligação aparece é o **nome** da conta.

### 4.3 O contrato de erro do botão — **não** precisou mudar

A allowlist autorizava `opencost.py`/`kubecost.py` "só contrato de erro do `test_connection`, se
necessário". **Não foi necessário:** o frontend já declara o contrato que o backend pratica.

| Camada | Contrato |
|---|---|
| frontend (`frontend/src/pages/finops/kubernetes/types.ts`) | `ConnectionTestResponse { success, latency_ms, provider_version, error_message }` — **exatamente** os quatro campos que o backend devolve |
| frontend (`hooks.ts`, `useK8sTestConnection`) | o erro é tipado `AxiosError<UnavailableResponse>` — ou seja, a UI **espera** a resposta de "indisponível" |
| backend (`opencost.py`, `test_connection`) | caminho feliz → `success=true`; timeout/`ConnectError` → `ProviderUnavailableError` |
| backend (`exception_handlers.py`) | `ProviderUnavailableError` → **503** com JSON estruturado (o `UnavailableResponse` que a UI tipa) |

O caminho do botão **não** exige `provider_type` no corpo da resposta, e o backend não o
devolve. Alterar o contrato seria inventar um campo que a UI não consome.

### 4.4 Continuam abertos, e não são desta fase

- **A descoberta oficial de clusters** (`GET /config/discover-clusters`) continua falhando contra
  as 5 contas do simulador (§2.2). O caminho usado foi a configuração pela API.
- **A UI do plano Kubernetes** e a **migration** — o resto da S4b2.
- **`/model/clusterInfo`** e **`/savings/requestSizing`** — 404, porque a spec da Model API do
  Kubecost **não as publica** (declarado na S4b2-I).
- **`memCost`** — o parser do consumidor lê um campo que o Kubecost não publica (declarado na
  S4b2-I).
- **A gêmea em inglês do contrato** (`docs/k8s-sim-opencost-contract.en.md`) continua **sem
  existir** (pendência da S4b1).
- **`scripts/synthetic-clouds/up.ps1`** não sobe o plano Kubernetes.

---

## 5. Verificação

### 5.1 O simulador

```powershell
# o script alterado é sintaticamente válido
$tokens=$null; $errors=$null
[System.Management.Automation.Language.Parser]::ParseFile(
  'C:\Projetos\Simulador\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1',
  [ref]$tokens, [ref]$errors) | Out-Null
# -> PARSE OK (tokens=3078)

# a recriação quebra; o script conserta, sem passo manual
podman compose -f compose.k8s.yaml up -d --force-recreate --no-deps --no-build k8s-sim
# -> Container synthetic-clouds-k8s-sim-1 Recreated / Started
#    (o novo container NAO entra na bridge do CloudPilot: o compose declara o
#     alias na rede dos simuladores, e a bridge é do consumidor)

.\ensure-cloudpilot.ps1
# -> connecting synthetic-clouds-k8s-sim-1 to cloudpilot-deploy_cloudpilot_net with aliases k8s-sim
#    tls-front: nginx reloaded; upstreams resolved again
#    k8s-sim plane opencost = 200 by HTTPS name
#    k8s-sim plane kubernetes = 200 by HTTPS name
#    k8s-sim plane prometheus = 200 by HTTPS name
#    k8s-sim plane kubecost = 200 by HTTPS name
#    summary: integration OK (0 problems)          -> exit 0
```

> O `--no-build` é deliberado: a imagem `localhost/k8s-sim:latest` já existe e **reconstruir o
> emulador está fora do escopo**. O que a prova exige é a **recriação do container**, e é ela
> que troca o endereço.

### 5.2 O consumidor

```powershell
cd C:\Projetos\cloudpilot-deploy
git worktree list
# -> C:/Projetos/cloudpilot-deploy  126970e5 [main]   (a branch main do consumidor)
git show --stat --oneline HEAD
# -> 126970e5 fix(k8s-finops): merge provider db constructor fix into main
#    backend/app/services/k8s_finops/providers/kubecost.py  |  9 +-
#    backend/app/services/k8s_finops/providers/opencost.py  |  7 +-
#    backend/tests/services/k8s_finops/test_provider_factory_db.py | 110 +++
git diff --check          # -> exit 0
git status --porcelain    # -> ?? docs/k8s-feature/   (pré-existente, não rastreado)

cd backend
.\.venv\Scripts\python.exe -m pytest tests/services/k8s_finops/test_provider_factory_db.py -q
# -> 24 passed in 28.27s
```

### 5.3 O estado final, medido

```
podman ps                                    # todos "Up"
k8s_finops_configs (e757043f)                -> opencost | https://opencost.synthetic-clouds.test | 103 clusters | 103 map | has_token=true
k8s_cost_snapshots (e757043f)                -> 3193 linhas | 2026-10-01..2026-10-31 | 103 clusters | 1 namespace
k8s_sync_status (e757043f)                  -> success | 103/103
GET /overview                                -> 200 | total_cost=12388.8400 | coverage=100% | is_stale=false
POST /config/test-connection                 -> 200 | success=true | latency_ms=18
```
