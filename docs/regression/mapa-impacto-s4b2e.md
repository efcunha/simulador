# Mapa de impacto — Fase S4b2-E (o `k8s-sim` por HTTPS: nome próprio, SAN e URL do consumidor)

**Data:** 2026-10-30 · **Revisão-base:** `397bd96b` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `deploy/synthetic-clouds/compose.tls-front.yaml`, `deploy/synthetic-clouds/tls-front/nginx.conf`,
`deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`, `deploy/synthetic-clouds/.env` (config local),
`docs/**`, `README.md`, `README.en.md` ·
**Fora do escopo:** `emulators/**` (código, fixture, testes), `deploy/synthetic-clouds/compose.k8s.yaml`,
`deploy/synthetic-clouds/compose.yaml`, `compose.gcp.yaml`, `compose.aws.yaml`, `scripts/**`, `specs/**`,
`tools/**`, `AGENTS.md`, `docs/NAO-COMPROVADOS*` (gerado) e `C:\Projetos\cloudpilot-deploy/**`.

**Por que esta fase existe.** A S4b2-C fechou o **caminho de rede** até o `k8s-sim`: ele passou a
ser anexado à bridge do CloudPilot com o alias `k8s-sim`, e o backend o alcançava em
`http://k8s-sim:8089` — **HTTP puro, sem certificado e sem nome de nuvem**. Todo o resto da stack
fala TLS com o CloudPilot pelos hostnames reais; o plano Kubernetes era o único que não tinha
nome nem certificado. Esta fase fecha o **TLS** do plano Kubernetes.

**O contratempo, e por que ele não muda o desenho.** O plano Kubernetes **não tem hostname de
nuvem para imitar** — o OpenCost não é um serviço de nuvem, é um contrato. Não havia nome pronto
para publicar. Inventar um hostname real seria sequestrar o nome de alguém (o que a stack já
descobriu ser perigoso com `sts.*`); omitir o TLS deixaria o plano como a única superfície HTTP
pura. A saída foi o **checkpoint**: o hostname é **do front**, não da nuvem.

## 1. O que muda

| | Antes (S4b2-C) | Depois (S4b2-E) |
|---|---|---|
| **Nome do plano** | nenhum | **`opencost.synthetic-clouds.test`** — nome do front, em TLD reservada para testes (RFC 6761) |
| **URL do consumidor** | `http://k8s-sim:8089` | **`https://opencost.synthetic-clouds.test`** (porta 443, a do front) |
| **Transporte** | HTTP puro | **TLS**, folha do front, **mesma CA** de sempre (bundle do CloudPilot intocado) |
| **Alias na bridge** | `k8s-sim` (só do container) | `k8s-sim` **+ `opencost.synthetic-clouds.test`** (do front) |
| **Rota no front** | nenhuma | `upstream k8s_opencost { server k8s-sim:8089; }` + `server_name opencost.synthetic-clouds.test` |
| **SAN da folha** | 12 nomes | **13 nomes** (o novo entrou; folha reassinada pela mesma CA) |
| **Prova** | probe HTTP do backend | probe **HTTPS** (caminho do consumidor) **e** HTTP (upstream do front) |
| **Contrato HTTP** | `/allocation/compute`, `/clusterInfo`, `/healthz` | **inalterado** |

**Nada disso muda o contrato HTTP.** O `k8s-sim` continua servindo exatamente o que o
`docs/k8s-sim-opencost-contract.md` descreve. Nenhum arquivo de `emulators/**` foi tocado, e o
`compose.k8s.yaml` não foi alterado.

## 2. O checkpoint: o nome é do front, não da nuvem

A fase exigia um checkpoint **antes** de editar qualquer arquivo: propor hostname, URL e o valor
do provider OpenCost. Três nomes foram propostos ao operador, todos com a mesma URL e o mesmo
valor de provider (`https://<hostname>`, porta 443 implícita):

| Opção | Nome | Por que |
|---|---|---|
| **A (aprovada)** | `opencost.synthetic-clouds.test` | o contrato OpenCost, nomeado; `.test` é a TLD reservada para testes (RFC 6761) — **não resolve na internet pública** |
| B | `opencost.synthetic-clouds.internal` | mesma semântica, TLD privada (RFC 8375) |
| C | `k8s-sim.synthetic-clouds.test` | hostname 1:1 com o alias do container |

**A aprovada.** O sufixo `.test` é o ponto: um nome que **não pode vazar** para a internet
pública. É a mesma disciplina que tirou `sts.*` da bridge (§ STS em
`docs/INTEGRACAO-CLOUDPILOT-TLS.md`): sequestrar um nome real quebra qualquer conta real que
compartilhe a rede com o simulador.

**O que o nome NÃO é:** não é o hostname de nenhum serviço real, e o plano continua **sem**
hostname de nuvem para imitar. `.test` é declarado em TLD reservada justamente para não
resolver na internet — o oposto de sequestrar.

## 3. Rede, alias e URL — o mapa

| Peça | Valor | Onde está |
|---|---|---|
| Container | `synthetic-clouds-k8s-sim-1` | `compose.k8s.yaml` (fora da allowlist, **não** editado) |
| Rede do CloudPilot | `cloudpilot-deploy_cloudpilot_net` | criada pela stack do CloudPilot |
| Alias do container | `k8s-sim` | criado pelo `ensure-cloudpilot.ps1` (`Ensure-NetworkAliases`) |
| **Alias do front** | **`opencost.synthetic-clouds.test`** | `compose.tls-front.yaml` (`networks.cloudpilot_net.aliases`) |
| **Nome no SAN** | **`opencost.synthetic-clouds.test`** | `$FrontAliases` do `ensure-cloudpilot.ps1` → folha reassinada |
| **URL do consumidor** | **`https://opencost.synthetic-clouds.test`** | `provider_endpoint` do `opencost` no CloudPilot (workspace `[SYNTH] synthetic-homologation`) |
| Upstream do front | `http://k8s-sim:8089` | `nginx.conf` (`upstream k8s_opencost`) |
| URL no host (operador) | `http://localhost:8089/healthz` | só para o operador; a porta do host é `${K8S_SIM_PORT:-8089}` |

**O alias `k8s-sim` continua existindo** — e é por isso que ele não pode ser removido: ele é o
**upstream** do front. O nginx resolve os upstreams no *startup*; se `k8s-sim` não existisse
quando o front sobe, o front não subiria.

## 4. O mecanismo

Quatro peças, todas em arquivos versionados:

1. **`compose.tls-front.yaml`** — o alias novo entra na lista `aliases` do serviço `tls-front`
   na `cloudpilot_net`. O serviço `k8s-sim` **não** é tocado (continua servindo 8089 por HTTP).
2. **`tls-front/nginx.conf`** — um `upstream k8s_opencost { server k8s-sim:8089; }` e um
   `server` novo, com `listen 443 ssl` e `server_name opencost.synthetic-clouds.test`, que
   encaminha para esse upstream. Um `server` por hostname, como os outros — o nginx resolve o
   nome do emulador no startup, pela DNS de containers.
3. **`integration/ensure-cloudpilot.ps1`** — o nome entra em `$FrontAliases`, que é a lista que
   `Ensure-FrontCertificate` usa para **reassinar a folha** quando um alias roteado não está no
   SAN. É a mesma mecânica dos sete hostnames `.googleapis.com`: *rota e certificado são um
   contrato só*.
4. **O `ensure` também passa a medir as duas pontas**: `Test-K8sSimFromBackend` agora prova o
   caminho **HTTPS** (o do consumidor) e o caminho **HTTP** (o upstream do front), em
   `/healthz` e `/clusterInfo`.

**A folha é reassinada, a CA não é tocada.** `Ensure-FrontCertificate` reexecuta o gerador com
a mesma CA e a folha nova sai com 13 SANs. O bundle do CloudPilot
(`C:\Projetos\cloudpilot-deploy\.local\tls\ca-bundle.pem`) **não muda** — nenhuma credencial
foi salva em arquivo do repo, e nenhum segredo aparece neste mapa.

**O front foi recriado, e só ele.** O nginx lê o certificado no *início do processo*, então
folha nova sem recriar o container não muda nada. O mecanismo oficial é
`podman compose -f deploy/synthetic-clouds/compose.tls-front.yaml up -d`, que recriou **apenas**
o `synthetic-clouds-tls-front` (os outros containers mantiveram o ID).

## 5. O teste da fase

### 5.1 A folha, antes e depois

```
--- before: SANs of the current leaf ---
SAN: bigquery.googleapis.com
... (12 nomes)
SAN: s3.amazonaws.com

--- Ensure-FrontCertificate ---
2026-10-30 18:36:55 [WARN] front leaf re-signed (missing SANs: opencost.synthetic-clouds.test); the tls-front must be recreated to pick it up
returned: True

--- after: SANs of the leaf ---
... (os mesmos 12)
SAN: opencost.synthetic-clouds.test
TOTAL: 13
HAS_K8S: True
```

### 5.2 O front, recriado pelo mecanismo oficial

```
$ podman inspect synthetic-clouds-tls-front --format '{{.Id}} {{.Created}}'
846747b76f524d91d8009aa7e154753500bf9e2fbcc57f45093dc0b35fddd120 2026-10-30 13:16:11 UTC

$ podman compose -f deploy/synthetic-clouds/compose.tls-front.yaml up -d
>>>> Container synthetic-clouds-tls-front Recreate
>>>> Container synthetic-clouds-tls-front Recreated
>>>> Container synthetic-clouds-tls-front Started
exit=0

$ podman inspect synthetic-clouds-tls-front --format '{{.Id}} {{.State.Status}} health={{.State.Health.Status}}'
9a313a73ab7f82b0778c742797635d6a9b870fe8774ff4656cfc47e662785ab5 running health=healthy
```

Os aliases publicados na bridge depois da recriação:

```
synthetic-clouds-tls-front
tls-front
bigquery.googleapis.com
oauth2.googleapis.com
cloudresourcemanager.googleapis.com
compute.googleapis.com
config.googleapis.com
container.googleapis.com
securitycenter.googleapis.com
opencost.synthetic-clouds.test      <-- o novo
9a313a73ab7f
```

### 5.3 A prova de dentro do backend do CloudPilot

```
$ podman exec cloudpilot_backend python -c "import ssl,urllib.request; c=ssl.create_default_context(); r=urllib.request.urlopen('https://opencost.synthetic-clouds.test/healthz', timeout=5, context=c); print(r.status, r.read().decode())"
200 {"status":"ok","synthetic":true}

$ podman exec cloudpilot_backend python -c "import ssl,urllib.request; c=ssl.create_default_context(); r=urllib.request.urlopen('https://opencost.synthetic-clouds.test/clusterInfo?filter=cluster%3A%22TEMP-aks_cluster-0025%22', timeout=5, context=c); print(r.status, r.read().decode())"
200 {"code":200,"data":{"version":"synthetic"}}
```

O contexto TLS padrão do container confia na CA local por `SSL_CERT_FILE=/certs/ca-bundle.pem`
— a validação **não** foi desligada em lugar nenhum.

### 5.3.1 O probe do `ensure`, rodado isolado

O `Test-K8sSimFromBackend` foi reescrito para medir as duas pontas. Rodado **isolado** (a
função e os helpers extraídos do script, sem executar o `ensure` inteiro — que mexeria na
janela do estate e em containers fora do escopo desta fase):

```
--- Test-K8sSimFromBackend ---
2026-10-30 18:46:52 [INFO] k8s-sim https/healthz = 200 from cloudpilot_backend (https://opencost.synthetic-clouds.test)
2026-10-30 18:46:52 [INFO] k8s-sim https/clusterInfo = 200 from cloudpilot_backend (https://opencost.synthetic-clouds.test)
2026-10-30 18:46:52 [INFO] k8s-sim http/healthz = 200 from cloudpilot_backend (http://k8s-sim:8089)
2026-10-30 18:46:52 [INFO] k8s-sim http/clusterInfo = 200 from cloudpilot_backend (http://k8s-sim:8089)
problems: 0
```

**Nota de extração (vale para quem for mexer no script).** Uma função do `ensure` **não** pode
ser extraída com `(?ms)^function\s+NOME\s*\{.*?^\}`: o here-string de Python dentro do probe tem
um literal de dicionário que fecha com `}` **na coluna 0**, e o regex corta a função pela
metade ("The string is missing the terminator: '@"). A extração correta é por **bloco**
(`[regex]::Split($text, '(?m)^(?=function\s+)')`), e é assim que este probe foi rodado.

### 5.4 O provider real do CloudPilot, com a config salva

O provider `opencost` do CloudPilot (a mesma classe, `httpx`, com a URL lida do banco),
instanciado com a config da conta de homologação:

```
PROVIDER:{"workspace_id": "e757043f-2325-506b-b3eb-e61f8d07147d", "provider_type": "opencost",
"endpoint_saved": "https://opencost.synthetic-clouds.test", "success": true, "latency_ms": 29,
"provider_version": null, "error_message": null}
```

E a leitura de custo (o outro item do passo 5 da fase), pelo **nome** e pelo **id nativo** —
o alias do C-IDENT continua resolvendo pelo caminho novo:

```
COSTS:{"endpoint_saved": "https://opencost.synthetic-clouds.test", "reads": {
 "name":     {"rows": 5, "first": {"cluster_id": "TEMP-aks_cluster-0025", "cluster_name": "TEMP-aks_cluster-0025",
                                    "namespace": "payments", "workload": "api", "total_cost_usd": "3.88", "date": "2026-10-01"}},
 "native_id":{"rows": 5, "first": {"cluster_id": "/subscriptions/0aa7d1ea-…/managedClusters/TEMP-aks_cluster-0025",
                                    "cluster_name": "TEMP-aks_cluster-0025", "namespace": "payments", "workload": "api",
                                    "total_cost_usd": "3.88", "date": "2026-10-01"}}}}
```

### 5.5 Os outros planos, intactos

```
$ podman exec synthetic-clouds-tls-front nginx -t
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful

$ podman exec cloudpilot_backend python -c "import httpx; print(httpx.get('https://compute.googleapis.com/', timeout=10).status_code)"
404
$ podman exec cloudpilot_backend python -c "import httpx; print(httpx.get('https://bigquery.googleapis.com/bigquery/v2/projects', timeout=10).status_code)"
200
$ podman exec cloudpilot_backend python -c "import httpx; print(httpx.get('https://management.azure.com/subscriptions', timeout=10).status_code)"
404
```

O 404 de `compute` e `management.azure.com` é a resposta **dos próprios emuladores** (o gcp-sim e
o azure-sim não têm rota para esses caminhos) — o que prova que o TLS e o encaminhamento do front
continuam funcionando para os outros planos. O aviso `listen ... http2 is deprecated` vem do
bloco do SCC (linha 196), **pré-existente**, e não desta fase.

## 6. O "Verificar Conexão" da UI: defeito **pré-existente** do CloudPilot

O botão "Verificar Conexão" da aba Config **não** chega ao provider. O log do backend:

```
2026-10-30T21:38:43.553423Z [error] unhandled_middleware_exception
  error="OpenCostProvider.__init__() got an unexpected keyword argument 'db'"
  method=POST path=/api/v1/finops/kubernetes/config/test-connection
```

**Causa raiz medida (no repo do CloudPilot, que esta fase não pode tocar):**

| Peça | Onde | O que é |
|---|---|---|
| A factory passa `db` para todo provider | `backend/app/services/k8s_finops/providers/factory.py:132` — `provider_cls(config, db=db)` | o ponto que quebra |
| `azure.py:285` e `gcp.py:242` | `def __init__(self, config: Any, db: AsyncSession | None = None)` | **aceitam** `db` → funcionam |
| `opencost.py:47` | `def __init__(self, config: Any)` | **não aceita** `db` → `TypeError` |
| `kubecost.py:44` | `def __init__(self, config: object)` | **não aceita** `db` → mesmo defeito |
| O serviço chama a factory | `backend/app/services/k8s_finops/service.py:1789` (`test_connection`) e `:1002` (leitura de custo) | todo caminho que usa a factory |

**Não é regressão desta fase — é reproduzível com qualquer endpoint.** Prova: o mesmo
`TypeError` foi registrado duas vezes, com **URLs diferentes**:

```
2026-10-30T21:38:43.553423Z  endpoint = https://opencost.synthetic-clouds.test
2026-10-30T21:40:35.641517Z  endpoint = http://k8s-sim:8089   (o valor antigo, de propósito)
```

O endpoint antigo foi restaurado para essa medição e depois **devolvido** ao valor aprovado
(confirmado no banco, §7).

**O código dentro do container é o do repo.** `opencost.py` do container e o do repo são
idênticos, linha a linha (normalizando fim de linha): `IGUAIS=True`. Não é imagem velha.

**A correção é do lado do CloudPilot** (uma linha por provider, espelhando `azure.py`/`gcp.py`):

```python
def __init__(self, config: Any, db: AsyncSession | None = None) -> None:
```

**Por que a fase não a fez:** `C:\Projetos\cloudpilot-deploy\**` está **fora da allowlist**.
A exceção da fase cobre *configurar/verificar* o provider OpenCost — não alterar o código do
CloudPilot. E a correção exigiria **reconstruir e recriar os containers do CloudPilot**, o que
a fase proíbe ("apenas o front reiniciado").

**O que a fase entrega no lugar disso:** a prova de que a URL funciona, feita com o **provider
real** (§5.4) — o mesmo código, a mesma config do banco, a mesma rede e o mesmo TLS. O que
falta é só o botão da UI, que morre **antes** de falar com a rede.

## 7. O estado final no CloudPilot

Config do provider OpenCost na conta de homologação (workspace `[SYNTH] Synthetic Workspace
synthetic-homologation`, `e757043f-2325-506b-b3eb-e61f8d07147d`):

```
$ podman exec cloudpilot_postgres psql -U cloudpilot -d cloudpilot -c "select …"
 workspace_id                          | provider_type |           provider_endpoint            | has_token | is_active
---------------------------------------+---------------+------------------------------------+-----------+-----------
 e757043f-2325-506b-b3eb-e61f8d07147d | opencost      | https://opencost.synthetic-clouds.test | f         | t
```

Resposta da API no save (o que a UI gravou):

```json
{"status":"ok","data":{"provider_type":"opencost","provider_endpoint":"https://opencost.synthetic-clouds.test",
 "has_token":false,"sync_interval_hours":24,"clusters":[],"cluster_account_map":{},"last_sync_at":null,"sync_status":"idle"}}
```

`has_token: false` — o token ficou vazio de propósito (o autofill do navegador colocaria a senha
do login no campo; ela foi apagada explicitamente antes de salvar).

## 8. Documentos afetados

| Documento | O que mudou |
|---|---|
| `deploy/synthetic-clouds/compose.tls-front.yaml` | o alias `opencost.synthetic-clouds.test` na `cloudpilot_net` |
| `deploy/synthetic-clouds/tls-front/nginx.conf` | `upstream k8s_opencost` + o `server` do nome novo |
| `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1` | `$FrontAliases`, `$K8sSimUrl`/`$K8sSimAliasUrl`, e o probe em duas pontas |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | a seção do plano Kubernetes, a tabela de hostnames (dez), o SAN e a ordem de subida |
| `docs/k8s-sim-opencost-contract.md` | §2.1 (a URL agora é HTTPS), §9 (TLS sai da pendência) e o cabeçalho |
| `README.md` / `README.en.md` | como o CloudPilot alcança o `k8s-sim`, o débito da frente e o parágrafo do emulador |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | linha da entrega e a seção da S4b2-E (commit separado) |
| `docs/regression/mapa-impacto-s4b2e.md` | este mapa |

## 9. Débitos e lacunas declaradas

- **O botão "Verificar Conexão" da UI continua quebrado** — defeito **pré-existente** do
  CloudPilot (§6). Enquanto ele não for corrigido lá, o caminho da UI não fecha; o caminho do
  provider, sim (§5.4).
- **O mesmo defeito atinge o provider `kubecost`** (`kubecost.py:44` não aceita `db`).
- **Nenhum sync foi rodado.** A leitura foi provada no nível do provider; não há snapshot de
  custo novo no workspace de homologação.
- **`deploy/synthetic-clouds/README.md` ficou com texto obsoleto** — ele ainda diz que o backend
  alcança o `k8s-sim` em `http://k8s-sim:8089` (HTTP puro) e que *"o TLS para o plano Kubernetes
  é o restante da S4b2"*, e a tabela de URL do plano Kubernetes ainda traz o endereço antigo.
  O arquivo está **fora da allowlist** desta fase (que lista `compose.tls-front.yaml`,
  `tls-front/nginx.conf`, `integration/ensure-cloudpilot.ps1`, `.env`, `docs/**`, `README.md` e
  `README.en.md`) — por isso o texto **não** foi corrigido aqui, e fica como **débito nomeado**.
  O texto correto é o da §3 deste mapa.
- **`deploy/synthetic-clouds/.env.example` ficou com o `K8S_SIM_URL` antigo** — ele ainda
  documenta e comenta `K8S_SIM_URL=http://k8s-sim:8089`, com a justificativa do alias de rede.
  Também está **fora da allowlist**: a correção seria trocá-lo por
  `K8S_SIM_URL=https://opencost.synthetic-clouds.test`, com a nota de que o alias `k8s-sim`
  continua sendo o upstream do front. **A `.env` local desta instalação** (`K8S_SIM_PORT=8089`)
  não precisa de mudança: a URL do consumidor é configuração do **CloudPilot**, não do compose.
- **`docs/DECISOES-PENDENTES.md` (e a gêmea `.en.md`)** ainda descrevem o plano Kubernetes sem
  TLS. O arquivo está **fora da allowlist** desta fase — débitos nomeado.
- **`AGENTS.md` ainda descreve o `k8s-sim` como "sem `Containerfile`"** e o `k8s-sim` como
  alcançado por HTTP puro. Falso desde a S4b2-B/S4b2-E, e `AGENTS.md` está explicitamente
  proibido de edição nesta fase.
- **A folha TLS é local e git-ignored.** O repositório guarda o *contrato* (o nome, a rota, o
  SAN via `$FrontAliases`), não a folha. Uma instalação nova reassina a folha pelo
  `ensure-cloudpilot.ps1` — que é exatamente o que esta fase automatizou.

## 10. O que esta fase **não** faz

- Não toca `emulators/**`: nem o código, nem o fixture, nem os testes do `k8s-sim`.
- Não edita `compose.k8s.yaml` (entregue pela S4b2-B) nem os outros composes.
- Não reconstrói imagem de emulador nenhum; o `k8s-sim` nem foi reiniciado.
- Não toca o código do CloudPilot — nem recria container dele. **Só o front do simulador foi
  recriado.**
- Não roda a suíte canônica (`pytest tools\synthetic_clouds\tests`): a fase não toca código de
  produção do gerador nem dos emuladores.
- Não sequestra hostname de nuvem real algum.
