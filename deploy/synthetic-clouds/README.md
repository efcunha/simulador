# synthetic-clouds — stack local dos emuladores (Azure, GCP e AWS)

> Última atualização: **2026-10-29** (revisão `9533b901`).

Quatro arquivos compose, um por lado da pilha, em `deploy/synthetic-clouds/`:

| Compose | Serviços | Portas no host | Volumes | Sobe com |
|---|---|---|---|---|
| `compose.yaml` | `azurite` + `azure-sim` | `10000` (blob; `${AZURITE_BLOB_PORT}`) · `8080` (API; `${API_PORT}`) — o `azure-sim` também escuta **443 TLS** dentro da rede | `azurite-data` | `scripts/synthetic-clouds/up.ps1` (plano Azure) |
| `compose.gcp.yaml` | `bigquery-emulator` + `gcp-sim` + `gcp-bq-provision` (one-shot) | `9050`/`9060` (BigQuery REST/gRPC; `${GCP_BQ_REST_PORT}`/`${GCP_BQ_GRPC_PORT}`) · `8085` (gcp-sim REST) · `8087` (monitoring gRPC) | `gcp_provision`, `gcp_sim_fixtures` | `scripts/synthetic-clouds/gcp-up.ps1` |
| `compose.aws.yaml` | `s3mock` + `aws-sim` | `9090` (S3; `${S3_PORT}`) · `8086` (aws-sim; `${AWS_SIM_PORT}`) | `aws_sim_render` | `scripts/synthetic-clouds/aws-up.ps1` |
| `compose.tls-front.yaml` | `tls-front` (nginx 1.27-alpine) | **nenhuma publicada** — escuta 443 (TLS) e 80 (healthz) dentro da rede do CloudPilot | — (monta `../../emulators/azure-sim/tls` em `/certs:ro`) | `integration/ensure-cloudpilot.ps1` / `integration/cold-start.ps1` |

O plano GCP também sobe o **plano gRPC do SCC** na porta **8088**, dentro do processo do
`gcp-sim` (`GCP_SIM_SCC_GRPC_PORT`, padrão 8088). Ela **não é publicada no host**: quem a
consome é o front TLS, pela rede compartilhada (ver
[`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](../../docs/INTEGRACAO-CLOUDPILOT-TLS.md#hostnames-e-destinos)).

O `k8s-sim` **não está no compose** e não tem Containerfile: é um app FastAPI/uvicorn
separado (ver [k8s-sim](#k8s-sim-fora-do-compose)).

> **Podman, não Docker.** Os compose usam o schema que `podman compose` aceita. Os comandos
> abaixo assumem `podman compose`; troque por `podman-compose` se for o que a máquina tem.

## Pré-requisitos

- Podman com a máquina rodando (`podman machine start`) e `podman compose`.
- PowerShell 7 (`pwsh`) para os scripts de `scripts/synthetic-clouds/` e `integration/`.
- O venv do repositório ativo: `gcp-up.ps1` e `aws-up.ps1` chamam **`python` puro** para
  gerar o estado na máquina. Sem o venv ativo, o `python` do PATH é outro (medido nesta
  máquina: `C:\Python314\python.exe`), sem as dependências do gerador. Ative antes:

  ```powershell
  cd <raiz-do-repo>
  & .\.venv\Scripts\Activate.ps1
  ```

- O front TLS depende da rede do CloudPilot (`cloudpilot-deploy_cloudpilot_net`), criada
  pela stack do CloudPilot; nenhum dos três planos a cria.

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
- **AWS** (`aws-up.ps1`): gera o FOCUS 1.2, sobe `s3mock` + `aws-sim`, espera o `GET /` do
  S3 (ListBuckets) responder, copia a árvore renderizada para o volume `aws_sim_render` e
  roda `python -m aws_sim.upload` **dentro** do `aws-sim` para publicar no `s3mock`.

Para um único plano, chame o sub-script direto (`.\scripts\synthetic-clouds\gcp-up.ps1`).
Cada um aceita `-DryRun`.

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
os emuladores à rede do CloudPilot. O `cold-start.ps1` encadeia máquina → stack CloudPilot →
planos → integração, tolera a corrida de "already running" entre o GUI do Podman, a tarefa
agendada e o CLI, e termina mostrando endpoints e containers. Detalhes, flags e log em
[`integration/README.md`](integration/README.md).

## k8s-sim (fora do compose)

`emulators/k8s-sim/` serve o contrato **OpenCost** (`/allocation/compute`, `/clusterInfo`,
`/healthz`). Não tem `Containerfile` nem serviço de compose: é um app FastAPI/uvicorn com
`pyproject.toml` próprio e fixture versionada (`k8s_sim/fixtures/clusters.json`). O contrato
HTTP e os parâmetros estão em
[`docs/k8s-sim-opencost-contract.md`](../../docs/k8s-sim-opencost-contract.md). Rode a partir
do diretório do pacote, com um ambiente que tenha `fastapi`/`uvicorn` (o venv do gerador
**não** tem `uvicorn`):

```powershell
cd emulators\k8s-sim
python -m uvicorn k8s_sim.app:app      # a porta é escolha de quem sobe; o contrato não fixa uma
```

## Configuração (`.env`)

O `.env` deste diretório é **local e git-ignored**; o template é `.env.example` (todas as
variáveis são opcionais e os defaults produzem uma pilha `small` funcional).

```powershell
Copy-Item deploy\synthetic-clouds\.env.example deploy\synthetic-clouds\.env   # opcional
```

Três blocos no template:

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

O bloco **"Phase-4 override contract"** do `.env.example` (`AZURE_MANAGEMENT_ENDPOINT`,
`AZURE_AUTHORITY_HOST`, `AZURE_BLOB_ENDPOINT`) está **documentado, não implementado por
estes composes**: `azure-sim` só lê `AZURE_BLOB_ENDPOINT` (lado escritor); os outros dois não
são consumidos por nenhum serviço desta pilha. Não existe, hoje, código de override de
endpoint no simulador — quem aponta o FinOps para o simulador é a configuração de rede/TLS
descrita em `docs/INTEGRACAO-CLOUDPILOT-TLS.md`.

Nesta instalação o `.env` local (git-ignored, leitura de 2026-10-29) fixa
`SEED=123`, `PROFILE=medium`, `WINDOW_DAYS=297`, `API_PORT=8080`, `API_PAGE_SIZE=20000`.
`SEED=123` e `PROFILE=medium` são os mesmos valores que a config do agendador usa — ver
[`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md).

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
- **`s3mock` é o alvo do upload, não o que o FinOps lê.** Como o `boto3` não tem override por
  serviço, o cliente S3 do consumidor cai no `aws-sim`, que serve a superfície S3 REST a
  partir da mesma árvore (`AWS_SIM_S3_STORE_DIR=/render/aws_focus`); o `s3mock` prova que o
  upload funciona contra uma implementação S3 real. MinIO não é obtenível (os `podman pull`
  oficiais falham — medido), e é por isso que o mock é `adobe/s3mock`.
- **Azurite com `--skipApiVersionCheck`.** A imagem fixa do Azurite recusa o `x-ms-version`
  mais novo do SDK de blob do `azure-sim`; o flag é a exceção documentada pelo próprio
  Azurite e só vale para este ambiente local.
- **Nomes de container.** O `integration/ensure-cloudpilot.ps1` procura os containers do
  projeto compose padrão (`synthetic-clouds-azure-sim-1`, `synthetic-clouds-gcp-sim-1`,
  `synthetic-clouds-aws-sim-1`, `synthetic-clouds-bigquery-emulator-1`,
  `synthetic-clouds-s3mock-1`, `synthetic-clouds-tls-front`). Mudar `SYNTHCLOUDS_PROJECT`
  no `up.ps1` tira os containers desses nomes e a integração passa a não encontrá-los.

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
