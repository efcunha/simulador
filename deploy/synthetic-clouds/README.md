# synthetic-clouds — stack local dos emuladores (Azure, GCP, AWS e Kubernetes)

> Última atualização: **2026-10-31** (revisão `6765522b`).

Cinco arquivos compose, um por lado da pilha, em `deploy/synthetic-clouds/`:

| Compose | Serviços | Portas no host | Volumes | Sobe com |
|---|---|---|---|---|
| `compose.yaml` | `azurite` + `azure-sim` | `10000` (blob; `${AZURITE_BLOB_PORT}`) · `8080` (API; `${API_PORT}`) — o `azure-sim` também escuta **443 TLS** dentro da rede | `azurite-data` | `scripts/synthetic-clouds/up.ps1` (plano Azure) |
| `compose.gcp.yaml` | `bigquery-emulator` + `gcp-sim` + `gcp-bq-provision` (one-shot) | `9050`/`9060` (BigQuery REST/gRPC; `${GCP_BQ_REST_PORT}`/`${GCP_BQ_GRPC_PORT}`) · `8085` (gcp-sim REST) · `8087` (monitoring gRPC) | `gcp_provision`, `gcp_sim_fixtures` | `scripts/synthetic-clouds/gcp-up.ps1` |
| `compose.aws.yaml` | `s3mock` + `aws-sim` | `9090` (S3; `${S3_PORT}`) · `8086` (aws-sim; `${AWS_SIM_PORT}`) | `aws_sim_render` | `scripts/synthetic-clouds/aws-up.ps1` |
| `compose.k8s.yaml` | `k8s-sim` (OpenCost) | `8089` (`${K8S_SIM_PORT}`) | — (o fixture do estate vai na imagem) | `integration/ensure-cloudpilot.ps1` (plano Kubernetes) |
| `compose.tls-front.yaml` | `tls-front` (nginx 1.27-alpine) | **nenhuma publicada** — escuta 443 (TLS) e 80 (healthz) dentro da rede do CloudPilot | — (monta `../../emulators/azure-sim/tls` em `/certs:ro`) | `integration/ensure-cloudpilot.ps1` / `integration/cold-start.ps1` |

O plano GCP também sobe o **plano gRPC do SCC** na porta **8088**, dentro do processo do
`gcp-sim` (`GCP_SIM_SCC_GRPC_PORT`, padrão 8088). Ela **não é publicada no host**: quem a
consome é o front TLS, pela rede compartilhada (ver
[`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](../../docs/INTEGRACAO-CLOUDPILOT-TLS.md#hostnames-e-destinos)).

O `k8s-sim` **entra no compose** (`compose.k8s.yaml`, entregue pela S4b2-B) e é **anexado à
rede do CloudPilot** pelo `integration/ensure-cloudpilot.ps1`, que cria o alias `k8s-sim`:
é assim que o **front TLS** o alcança, em `http://k8s-sim:8089`, e é pelo front que o backend
do CloudPilot chega ao contrato OpenCost, em **`https://opencost.synthetic-clouds.test`**
(desde a S4b2-E) (ver [k8s-sim](#plano-kubernetes--k8s-sim)).

> **Podman, não Docker.** Os compose usam o schema que `podman compose` aceita. Os comandos
> abaixo assumem `podman compose`; troque por `podman-compose` se for o que a máquina tem.

## Pré-requisitos

- Podman com a máquina rodando (`podman machine start`) e `podman compose`.
- PowerShell 7 (`pwsh`) para os scripts de `scripts/synthetic-clouds/` e `integration/`.
- O venv do repositório ativo: `gcp-up.ps1` chama **`python` puro** para gerar o estado na
  máquina. Sem o venv ativo, o `python` do PATH é outro (medido nesta máquina:
  `C:\Python314\python.exe`), sem as dependências do gerador. Ative antes:

  ```powershell
  cd <raiz-do-repo>
  & .\.venv\Scripts\Activate.ps1
  ```

  O `aws-up.ps1` (S4b3-A) **não depende** disso: ele usa `.venv\Scripts\python.exe` quando o
  venv existe e só cai no `python` do PATH como último recurso.

- O front TLS depende da rede do CloudPilot (`cloudpilot-deploy_cloudpilot_net`), criada
  pela stack do CloudPilot; nenhum dos quatro planos a cria. É a integração que anexa os
  emuladores a ela — inclusive o `k8s-sim`, com o alias `k8s-sim`.

## Quick start — os três planos

`scripts/synthetic-clouds/up.ps1` é o ponto de entrada único: ele sobe **Azure, depois GCP,
depois AWS**, reporta falha por plano e sai com código 1 se algum falhar (pilha parcialmente
no ar nunca é reportada como sucesso). `-DryRun` imprime o plano ordenado; `-Skip gcp,aws`
pula planos; `SYNTHCLOUDS_PROJECT` renomeia o projeto compose dos três (para uma pilha
paralela).

```powershell
# plano sem executar
pwsh -NoProfile -File .\scripts\synthetic-clouds\up.ps1 -DryRun

# subir os três (Azure -> GCP -> AWS)
pwsh -NoProfile -File .\scripts\synthetic-clouds\up.ps1

# só um plano mudou
pwsh -NoProfile -File .\scripts\synthetic-clouds\up.ps1 -Skip gcp,aws
```

O que cada plano faz além do `compose up`:

- **Azure**: `podman compose -f compose.yaml up -d`; para validar o schema sem subir nada:
  `podman compose -f compose.yaml config`.
- **GCP** (`gcp-up.ps1`): gera `gcp_bigquery_topology`/`gcp_rest_fixtures` na máquina, sobe
  emulador + `gcp-sim`, espera o emulador responder, copia os artefatos para os **volumes
  nomeados** com `podman cp` (nunca bind mount de `C:\Projetos\`), roda o `gcp-bq-provision`
  (DDL + `insertAll`) e reinicia o `gcp-sim` para carregar os fixtures.
- **AWS** (`aws-up.ps1`): gera o FOCUS 1.2 **no perfil que o `.env` da instalação declara**
  (`AWS_SIM_PROFILE`; o ambiente de processo ainda sobrescreve), sobe `s3mock` + `aws-sim`
  **sem rebuild** (os containers em execução são reutilizados; `-Build` é explícito), espera o
  `GET /` do S3 (ListBuckets) responder, **substitui** a árvore renderizada no volume
  `aws_sim_render` (remove e copia — nunca mescla) e roda `python -m aws_sim.upload` **dentro**
  do `aws-sim` para publicar no `s3mock`. No fim ele **confere** a árvore pela superfície S3 do
  próprio `aws-sim` e falha se a lista vier vazia.

Para um único plano, chame o sub-script direto (`.\scripts\synthetic-clouds\gcp-up.ps1`).
Cada um aceita `-DryRun`.

> **O plano Kubernetes não está no `up.ps1`.** Ele é autocontido (o fixture do estate vai na
> imagem) e sobe pelo `integration/ensure-cloudpilot.ps1`, que também é quem cria o alias
> `k8s-sim` na rede do CloudPilot — o `up.ps1` é dono dos três planos de nuvem. Ver
> [Plano Kubernetes](#plano-kubernetes--k8s-sim).

## TLS front (separado, na rede do CloudPilot)

O `compose.tls-front.yaml` **não** é iniciado pelo `up.ps1`: ele é external à rede
`cloudpilot-deploy_cloudpilot_net` e declara os sete aliases `*.googleapis.com` que o
CloudPilot resolve. O nginx resolve os upstreams **no startup** e sai com
`host not found in upstream` se eles não existirem — por isso o front só pode subir depois
que `gcp-sim`, `bigquery-emulator`, `aws-sim` e `s3mock` estiverem anexados à rede do
CloudPilot com seus aliases. Quem faz essa ordem é a integração:

```powershell
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1   # idempotente
# ou, para o ambiente inteiro após reboot / podman machine stop:
.\deploy\synthetic-clouds\integration\cold-start.ps1
```

Hostnames roteados, upstreams e a decisão de **não** publicar `sts.*` estão em
[`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](../../docs/INTEGRACAO-CLOUDPILOT-TLS.md).

## Integração e automação

`deploy/synthetic-clouds/integration/` reaplica o que não sobrevive a restart/recriação de
container (aliases DNS, CA confiável, folha do front, janela do estate) e é o que **anexa**
os emuladores à rede do CloudPilot — incluindo o `k8s-sim`, com o alias `k8s-sim`. É também
o que **cria** o container do plano Kubernetes, quando ele não existe (a partir de
`compose.k8s.yaml`, sem rebuild). O `cold-start.ps1` encadeia máquina → stack CloudPilot →
planos → integração, tolera a corrida de "already running" entre o GUI do Podman, a tarefa
agendada e o CLI, e termina mostrando endpoints e containers. Detalhes, flags e log em
[`integration/README.md`](integration/README.md).

## Plano Kubernetes — k8s-sim

`emulators/k8s-sim/` serve o contrato **OpenCost** (`/allocation/compute`, `/clusterInfo`,
`/healthz`). Desde a **S4b2-B** ele tem `Containerfile` e serviço de compose
(`compose.k8s.yaml`); desde a **S4b2-C** ele é **anexado à rede do CloudPilot** com o alias
`k8s-sim`; e desde a **S4b2-E** o **front TLS** o publica sob o nome próprio
`opencost.synthetic-clouds.test` (com o SAN na folha), de modo que o backend do CloudPilot o
alcança em **`https://opencost.synthetic-clouds.test`**. O alias `k8s-sim:8089` continua sendo
o **upstream** do front — não é a URL do consumidor.

O plano é **autocontido**: o fixture do estate (`k8s_sim/fixtures/clusters.json`) vai dentro
da imagem, então não há provisioning a fazer — só `compose up`. O contrato HTTP e os
parâmetros estão em
[`docs/k8s-sim-opencost-contract.md`](../../docs/k8s-sim-opencost-contract.md).

**Quem sobe.** O `scripts/synthetic-clouds/up.ps1` é dono dos **três planos de nuvem**
(Azure, GCP, AWS) e **não** sobe este. O `k8s-sim` é criado e anexado pelo
`integration/ensure-cloudpilot.ps1`, a partir de `compose.k8s.yaml` e **sem rebuild**
(`--no-deps --no-build` sobre a imagem `localhost/k8s-sim:latest`):

```powershell
# idempotente: cria o container se faltar, cria o alias se faltar, probe no -Smoke
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1 -Smoke -SkipEstate
```

Ou, direto no compose (só o container — **sem** o alias da bridge):

```powershell
cd deploy\synthetic-clouds
podman compose -f compose.k8s.yaml up -d --no-build
```

**A URL, e por que ela só funciona pelo alias:**

| Contexto | URL |
|---|---|
| do backend do CloudPilot | **`https://opencost.synthetic-clouds.test`** — nome próprio do front TLS, com o SAN na folha (desde a S4b2-E) |
| do front TLS para o plano | `http://k8s-sim:8089` — o host `k8s-sim` é o **alias de rede** na bridge `cloudpilot-deploy_cloudpilot_net`, e o `nginx.conf` o usa como `upstream` |
| do host, para o operador | `http://localhost:8089/healthz` (porta `${K8S_SIM_PORT:-8089}`) |

Sem o alias, o nome não resolve: o front não consegue resolver o *upstream* (o nginx resolve
os upstreams no *startup*, então nem sobe) e um pedido enviado direto para o alias falha com
`URLError: <urlopen error [Errno -2] Name or service not known>`.

**TLS desde a S4b2-E.** O plano Kubernetes **já tem** TLS: o `tls-front` serve o hostname
próprio `opencost.synthetic-clouds.test` (TLD reservada para testes, RFC 6761) e o alcança
por `http://k8s-sim:8089` **na rede**, sem TLS; o certificado, com o SAN do hostname, é
reemitido pela mesma CA local. O que **ainda não** existe é um hostname de **nuvem real**
para imitar — o OpenCost é um contrato, não um serviço de nuvem, e inventar um nome
sequestraria o nome de alguém (como o `sts.*`). Detalhe em
[`docs/regression/mapa-impacto-s4b2e.md`](../../docs/regression/mapa-impacto-s4b2e.md).

<details>
<summary>Rodar o serviço direto, sem container (modo desenvolvimento)</summary>

Com um ambiente que tenha `fastapi`/`uvicorn` (o venv do gerador **não** tem `uvicorn`):

```powershell
cd emulators\k8s-sim
python -m uvicorn k8s_sim.app:app      # a porta é escolha de quem sobe; o contrato não fixa uma
```

</details>

## Configuração (`.env`)

O `.env` deste diretório é **local e git-ignored**; o template é `.env.example` (todas as
variáveis são opcionais e os defaults produzem uma pilha `small` funcional).

```powershell
Copy-Item deploy\synthetic-clouds\.env.example deploy\synthetic-clouds\.env   # opcional
```

Quatro blocos no template:

- **Azure** — settings do `azure_sim/config.py` (`SEED`, `PROFILE`, `CURRENCY`,
  `AGREEMENT`, `EXPORTS`, `FORMAT`, `SCHEDULE`, `LATENCY_HOURS`, `MAX_ROWS_PER_PART`,
  `BLOB_CONTAINER`, `ROOT_DIRECTORY`, `API_PAGE_SIZE`) e portas do host (`API_PORT`,
  `AZURITE_BLOB_PORT`). O `AZURE_BLOB_ENDPOINT` é lido pelo **escritor** do `azure-sim`
  (é o endereço do Azurite dentro da rede). O compose também aceita `WINDOW_DAYS`, que
  **não** está no template — nesta instalação o `.env` local o define.
- **GCP** — `GCP_PROJECT`, portas (`GCP_BQ_REST_PORT`, `GCP_BQ_GRPC_PORT`,
  `GCP_SIM_PORT`, `GCP_SIM_GRPC_PORT`), `GCP_SEED`/`GCP_PROFILE` e os placeholders de
  billing (`GCP_BILLING_ACCOUNT_ID`, `GCP_BILLING_LOCATION`). O `gcp-up.ps1` usa
  `GCP_SEED=123`/`GCP_PROFILE=small` como defaults quando as variáveis não estão no
  ambiente.
- **AWS** — `S3_ACCESS_KEY`/`S3_SECRET_KEY` (inertes: o `s3mock` ignora credenciais),
  `S3_PORT`, `AWS_SIM_BUCKET`, `AWS_SIM_PORT`, `AWS_SIM_SEED`, `AWS_SIM_PROFILE`,
  `AWS_SIM_REGION`; `AWS_SIM_S3_STORE_DIR` documentado e comentado (comentado = a
  superfície S3 do `aws-sim` lista buckets sem objetos).
  **O plano AWS tem o seu próprio namespace:** `compose.aws.yaml` lê
  `SEED: "${AWS_SIM_SEED:-123}"` e `PROFILE: "${AWS_SIM_PROFILE:-small}"` — **não** os
  nomes genéricos `SEED`/`PROFILE` que os planos Azure/GCP leem. Com `AWS_SIM_PROFILE`
  ausente, o `aws-sim` cai no default `small` e serve um **estate diferente** do resto da
  pilha, com o mesmo seed (medido na S4b2-D: `small` = 237 recursos AWS / 37.922 linhas de
  faturamento; `medium` = 1.110 / 474.390). Os **ids de conta são os mesmos** nos dois
  perfis — eles derivam de `(seed, índice)`, não do perfil.
  **Desde a S4b3-A o `aws-up.ps1` lê o mesmo `.env`**: o namespace do plano AWS deixou de
  depender só do ambiente de processo, e a árvore FOCUS/S3 saiu de `small` para `medium`
  (medido: `_provenance.json` com `"profile": "medium"`, 130.236 linhas, 966 recursos com
  faturamento — ver [`docs/regression/mapa-impacto-s4b3a.md`](../../docs/regression/mapa-impacto-s4b3a.md)).
- **Kubernetes** — `K8S_SIM_PORT` (porta do host para o container 8089; a porta do
  container é fixa) e a URL `K8S_SIM_URL` documentada e comentada — a URL do **consumidor**
  é `https://opencost.synthetic-clouds.test` (front TLS, desde a S4b2-E); o alias
  `k8s-sim:8089` continua sendo o upstream do front. O plano é autocontido: não há seed,
  perfil nem provisioning.

O bloco **"Phase-4 override contract"** do `.env.example` (`AZURE_MANAGEMENT_ENDPOINT`,
`AZURE_AUTHORITY_HOST`, `AZURE_BLOB_ENDPOINT`) está **documentado, não implementado por
estes composes**: `azure-sim` só lê `AZURE_BLOB_ENDPOINT` (lado escritor); os outros dois não
são consumidos por nenhum serviço desta pilha. Não existe, hoje, código de override de
endpoint no simulador — quem aponta o FinOps para o simulador é a configuração de rede/TLS
descrita em `docs/INTEGRACAO-CLOUDPILOT-TLS.md`.

Nesta instalação o `.env` local (git-ignored, leitura de 2026-10-30) fixa
`SEED=123`, `PROFILE=medium`, `AWS_SIM_SEED=123`, `AWS_SIM_PROFILE=medium`,
`WINDOW_DAYS=297`, `API_PORT=8080`, `API_PAGE_SIZE=20000`.
`SEED=123` e `PROFILE=medium` são os mesmos valores que a config do agendador usa — ver
[`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md). O par `AWS_SIM_*` é o **mesmo seed e o
mesmo perfil** declarado pelo namespace do plano AWS: sem ele, o `aws-sim` sobe em `small`
(default do compose) enquanto o resto da pilha sobe em `medium`.

## Operação

- **Sem bind mount de `C:\Projetos\`.** A máquina Podman (Windows + hyperv) falha `statfs ... i/o
  error` em bind mount de drive. Todo estado é **volume nomeado**; artefatos entram por
  `podman cp` (nos scripts) ou por HTTP (upload do AWS, `podman cp` do GCP). O
  `azure-sim` já tem o gerador embutido na imagem e não precisa de mount para produzir
  estado/export.
- **Build context = raiz do worktree.** Os Containerfiles copiam só
  `tools/synthetic_clouds`, `specs` e `emulators/*`; `deploy/synthetic-clouds/Containerfile.dockerignore`
  corta caches e `out/` (`**/out` — o `out/` do gerador chegou a 5,67 GB/133.748 arquivos
  num build lento, medido em 2026-10-28).
- **`s3mock` é o alvo do upload, e é o que o consumidor de CUR lê.** O cliente S3 do CloudPilot
  usa o `endpoint_url` **por conta** (`cur_config.endpoint_url`), que nesta instalação aponta
  para `http://s3mock:9090` com *path style*; o bucket é o `AWS_SIM_BUCKET`
  (`synthetic-focus12-daily-full`) e o prefixo do export é `focus12-full/<export_name>/`. O
  `aws-sim` serve a **mesma árvore** pela superfície S3 REST a partir do volume
  (`AWS_SIM_S3_STORE_DIR=/render/aws_focus`), o que prova o conteúdo sem passar pelo mock.
  MinIO não é obtenível (os `podman pull` oficiais falham — medido), e é por isso que o mock
  é `adobe/s3mock`.
- **O store do `s3mock` é em memória.** Recriar o container esvazia o bucket (medido em
  2026-10-30: `KeyCount=0` logo depois de o container ser recriado), e o leitor de CUR passa a
  não encontrar nada. Publicar a árvore é parte do trabalho: `.\scripts\synthetic-clouds\aws-up.ps1`
  a republica.
- **O `export_name` que o consumidor lê é o que o renderer emite** —
  `synthetic-focus12-daily-full` (`tools/synthetic_clouds/render/focus_aws.py`). O nome
  `cloudpilot-focus12-daily-full` pertence ao renderer **anterior** ao *standalone publish* (o
  que escrevia `Manifest.json` no export); um consumidor configurado com ele não acha as
  chaves publicadas. Medido e corrigido na S4b3-A — ver
  [`docs/regression/mapa-impacto-s4b3a.md`](../../docs/regression/mapa-impacto-s4b3a.md) §2.2.
- **A entrega diária (FR-22) publica no mesmo namespace que o consumidor lê.** O bucket e o
  segmento de export da entrega são `synthetic-focus12-daily-full` — o nome que o renderer
  emite e o que o `cur_config` da conta de homologação tem. Antes da S4b3-B a entrega
  publicava em `cloudpilot-focus12-daily-full`: o dia era gerado, subia para o S3, a ingestão
  reportava `status: ok` e o `/costs/unified` continuava **sem AWS**. Medido e corrigido na
  S4b3-B — ver
  [`docs/regression/mapa-impacto-s4b3b.md`](../../docs/regression/mapa-impacto-s4b3b.md).
- **Azurite com `--skipApiVersionCheck`.** A imagem fixa do Azurite recusa o `x-ms-version`
  mais novo do SDK de blob do `azure-sim`; o flag é a exceção documentada pelo próprio
  Azurite e só vale para este ambiente local.
- **Nomes de container.** O `integration/ensure-cloudpilot.ps1` procura os containers do
  projeto compose padrão (`synthetic-clouds-azure-sim-1`, `synthetic-clouds-gcp-sim-1`,
  `synthetic-clouds-aws-sim-1`, `synthetic-clouds-bigquery-emulator-1`,
  `synthetic-clouds-s3mock-1`, `synthetic-clouds-k8s-sim-1`, `synthetic-clouds-tls-front`).
  Mudar `SYNTHCLOUDS_PROJECT` no `up.ps1` tira os containers desses nomes e a integração passa
  a não encontrá-los.

Validar, subir e derrubar um compose individual:

```powershell
podman compose -f deploy\synthetic-clouds\compose.yaml config
podman compose -f deploy\synthetic-clouds\compose.yaml up -d
podman compose -f deploy\synthetic-clouds\compose.yaml down          # mantém o volume
podman compose -f deploy\synthetic-clouds\compose.yaml down -v        # descarta o volume
```

Endpoints úteis depois de subir:

| Serviço | Endpoint |
|---|---|
| `azure-sim` | `http://localhost:8080/healthz` |
| `gcp-sim` | `http://localhost:8085/healthz` |
| `aws-sim` | `http://localhost:8086/healthz` |
| `bigquery-emulator` | `http://localhost:9050/healthz` |
| `s3mock` | `GET http://localhost:9090/` (ListBuckets; não há healthcheck no compose) |
| `tls-front` | sem porta publicada; só pela rede do CloudPilot |

Export avulso do `azure-sim` (uma execução para o Azurite, com `podman cp` opcional):

```powershell
pwsh -NoProfile -File .\scripts\synthetic-clouds\export_once.ps1 -WhatIf
pwsh -NoProfile -File .\scripts\synthetic-clouds\export_once.ps1
```
