# Mapa de impacto — Fase S4b3-A (a árvore FOCUS/S3 do `aws-sim` no perfil `medium`)

**Data:** 2026-10-30 · **Revisão-base:** `d9235fa2` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `scripts/synthetic-clouds/aws-up.ps1`, `deploy/synthetic-clouds/.env` (local, git-ignored),
`deploy/synthetic-clouds/README.md`, `docs/**`, `README.md`, `README.en.md` ·
**Fora do escopo:** `emulators/**` (código, fixture, testes), `deploy/synthetic-clouds/compose.*.yaml`,
`specs/**`, `tools/**`, `AGENTS.md`, `docs/NAO-COMPROVADOS*` (gerado) e o código do
`C:\Projetos\cloudpilot-deploy`.

**Por que esta fase existe.** A S4b2-D deixou o `aws-sim` no perfil `medium` e registrou, como
dívida aberta, que **a árvore FOCUS/S3 servida pelo emulador ainda tinha sido renderizada no
perfil `small`** — o uploader (`scripts/synthetic-clouds/aws-up.ps1`) estava fora da allowlist
daquela fase. O resultado era um plano AWS servindo **dois volumes diferentes**: as superfícies
de API (Cost Explorer, EC2, Organizations) respondiam o estate `medium`, e o export de
faturamento que o CloudPilot ingere respondia o estate `small`. Esta fase re-renderiza a
árvore no perfil `medium`, publica-a e fecha o circuito até o `/costs/unified`.

## 1. O que muda

| | Antes (S4b2-D) | Depois (S4b3-A) |
|---|---|---|
| **Perfil da árvore FOCUS/S3** | `small` (`_provenance.json`: `"profile": "small"`, `"seed": 123`) | **`medium`** (`"profile": "medium"`, `"seed": 123`) |
| **Volume da árvore no volume** | **28 objetos / 6.812.651 B** — 12 parquet + 12 `Manifest.json` do export **legado** (`cloudpilot-focus12-daily-full`, 2026-01→2026-10), 3 parquet do render `small` (`synthetic-focus12-daily-full`) e o `_provenance.json` | **6 objetos / 14.011.803 B** — 5 parquet de `focus12-full/synthetic-focus12-daily-full/` + o `_provenance.json` |
| **Linhas de faturamento na árvore** | **77.451** (65.242 no export legado + 12.209 no render `small`) | **130.236** (perfil `medium`, janela do perfil) |
| **Proveniência** | `{"bytes": 1360468, "objects": 3, "records": 12209}` — o render `small` | `{"bytes": 14007710, "objects": 5, "records": 130236}` — o render `medium` |
| **Recursos AWS** | **237** no estate `small` | **1.110** no estate `medium`, dos quais **966** com linha de faturamento — os **966** `ResourceId` da árvore |
| **Quem decide o perfil** | o **ambiente de processo** do shell (default `small` do script) | o **`.env` da instalação** (`deploy/synthetic-clouds/.env`), com o ambiente de processo ainda sobrepondo-o |
| **Árvore no volume** | mesclada com a anterior (`podman cp` **somava** as árvores) | **substituída** (remove e copia) — nunca duas árvores no mesmo volume |
| **Rebuild de imagem** | `up -d --build` (rebuild de `aws-sim` + `s3mock`) | **não**: os containers em execução são reutilizados; `-Build` é opt-in |
| **Nome do export lido pelo consumidor** | `cloudpilot-focus12-daily-full` (nome **legado**) | **`synthetic-focus12-daily-full`** (o nome que o renderer emite) |
| **CUR ingerido pelo CloudPilot** | 0 linhas (a promoção era *fail-closed*) | **58.926 linhas / US$ 166.204,47** |

## 2. Causa raiz — medida, não suposta

Três causas independentes, todas verificadas neste host.

### 2.1 O uploader lia o namespace no lugar errado

`compose.aws.yaml` lê `${AWS_SIM_SEED:-123}` e `${AWS_SIM_PROFILE:-small}` — a interpolação do
compose usa o **`.env` do diretório do compose** (`deploy/synthetic-clouds/.env`), onde a
instalação fixa `AWS_SIM_PROFILE=medium`. Mas o **gerador roda no host**, e o script resolvia o
namespace só do **ambiente de processo**, com default `small`:

```powershell
$AwsProfile = if ($env:AWS_SIM_PROFILE) { $env:AWS_SIM_PROFILE } else { "small" }
```

Um `.\scripts\synthetic-clouds\aws-up.ps1` sem `export` ambiente renderizava **`small`** — medido
no artefato da última execução: `tools/synthetic_clouds/out/aws-plane/123-small-USD` (mtime
2026-10-29 20:21). O `.env` que a instalação documenta nunca chegava ao gerador.

### 2.2 O consumidor lia um nome de export que o renderer não emite

O renderer nomeia o export **no código**: `tools/synthetic_clouds/render/focus_aws.py` →
`EXPORT_NAME = "synthetic-focus12-daily-full"`. O uploader publica a árvore **verbatim** (a
pasta `focus12-full/<export>/` vai para o bucket com o mesmo nome de pasta), então o bucket
`AWS_SIM_BUCKET` passa a conter `focus12-full/synthetic-focus12-daily-full/...`.

A conta de homologação, porém, estava configurada com `export_name =
cloudpilot-focus12-daily-full` — o nome do **renderer anterior** ao *standalone publish* (o que
escrevia `Manifest.json` no export, e que por isso tem um prefixo `cloudpilot-`). O leitor de
CUR busca `f"{s3_prefix}/{export_name}/"`, então media, no bucket do consumidor:

```
BUCKETS: ['synthetic-focus12-daily-full']
--- synthetic-focus12-daily-full: KeyCount=6 n=6
=== READER PREFIX focus12-full/cloudpilot-focus12-daily-full/ ===
KeyCount= 0
```

O prefixo configurado **não existia** no bucket. A árvore legada (com `Manifest.json`) que
ainda estava no volume era o que sustentava a ingestão de 2026-10-28 — e ela é do perfil
`small`.

### 2.3 A promoção do CUR é *fail-closed* sem id de conta de 12 dígitos

`promotion.py` exige que a conta tenha `external_account_id` com **12 dígitos** ("CUR payer
account configuration must be a 12-digit AWS account ID"). A conta `HOMOLOGATION AWS [sim]`
estava **vazia** — e o erro é engolido pelo `except` da promoção, que devolve
`cost_promotion_status: "skipped"` e **zero linhas** promovidas. Isto é **pré-existente** e
independente da árvore: a ingestão de 2026-10-28 também não promoveu nada.

### 2.4 O `s3mock` não guarda nada entre recriações

O store do `s3mock` é **em memória**: o container foi recriado neste host e o bucket
`synthetic-focus12-daily-full` voltou **vazio** (`KeyCount=0`). Publicar a árvore é, portanto,
parte do que a fase precisa fazer — não um detalhe que se pode presumir.

## 3. O que o `aws-up.ps1` passou a fazer

O script é o **único** dono da publicação da árvore no plano AWS. Quatro correções, todas no
arquivo que a fase autorizou:

1. **O `.env` da instalação decide o namespace.** `Resolve-Setting` lê o **ambiente de
   processo primeiro** e o `deploy/synthetic-clouds/.env` **depois** — o arquivo que já fixa
   `AWS_SIM_PROFILE=medium` passa a valer sem `export`, e um `export` explícito ainda sobrescreve.
   Sem isso, o default `small` continua sendo um silêncio.
2. **O interpretador é o venv do repositório.** O `python` do `PATH` nesta máquina é
   `C:\Python314\python.exe`, sem as dependências do gerador; o script usa
   `.venv\Scripts\python.exe` quando ele existe.
3. **A árvore é substituída, não mesclada.** O leitor de CUR fixa a execução **mais nova por
   período de faturamento**; uma árvore mesclada deixaria períodos do perfil antigo ao lado dos
   novos — dois estates num só volume. O script remove `/render/aws_focus` (como `root`, porque
   o container roda como `awssim` e `/render` é do `root`) e copia a árvore nova.
4. **Sem rebuild de imagem por padrão.** `up -d --build` reconstruía `aws-sim` e `s3mock` a
   cada publicação; agora os containers em execução são reutilizados e `-Build` é explícito. O
   script avisa quando a **imagem em execução é mais antiga que os fontes** do emulador — que é
   o caso medido aqui (`imagem 2026-10-28 14:49Z` vs fonte mais recente `2026-10-28 22:27Z`),
   porque reconstruir a imagem é fase própria.

O script também **prova** o resultado: depois do `podman cp`, ele lista o bucket pela
superfície S3 do próprio `aws-sim` (o `store` do volume) e falha se a lista vier vazia.

## 4. Medições — a árvore `medium`

**No volume (`synthetic-clouds_aws_sim_render`, `AWS_SIM_S3_STORE_DIR=/render/aws_focus`):**

```
== PROVENANCE ==
  profile   : medium
  seed      : 123
  mechanism : {"prefix": "focus12-full", "export_name": "synthetic-focus12-daily-full", "format": "parquet", ...}
  totals    : {"bytes": 14007710, "objects": 5, "records": 130236}
== TOTALS ==
  total_rows           : 130236
  distinct_resource_ids: 966
```

| Período | Execução | Linhas | Bytes |
|---|---|---|---|
| 2026-01 | `20260113T000000Z-80f388ff` | 11.870 | 1.291.518 |
| 2026-01 | `20260201T000000Z-80f388ff` | 30.653 | 3.273.234 |
| 2026-02 | `20260301T000000Z-238acda6` | 27.599 | 2.972.539 |
| 2026-03 | `20260401T000000Z-0d644f6f` | 30.533 | 3.284.866 |
| 2026-04 | `20260501T000000Z-6b092ea7` | 29.581 | 3.185.553 |

A árvore inteira tem **6 objetos / 14.011.803 B** (os 5 parquet acima + o `_provenance.json` de
4.093 B); a proveniência conta os **5** arquivos de dados.

**No `s3mock` (o bucket que o consumidor lê), com as chaves que o leitor espera:**

```
--- synthetic-focus12-daily-full: KeyCount=6 n=6
    _provenance.json
    focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-01/20260113T000000Z-80f388ff/synthetic-focus12-daily-full-00001.snappy.parquet
    focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-01/20260201T000000Z-80f388ff/synthetic-focus12-daily-full-00001.snappy.parquet
    focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-02/20260301T000000Z-238acda6/synthetic-focus12-daily-full-00001.snappy.parquet
    focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-03/20260401T000000Z-0d644f6f/synthetic-focus12-daily-full-00001.snappy.parquet
    focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-04/20260501T000000Z-6b092ea7/synthetic-focus12-daily-full-00001.snappy.parquet
```

### 4.1 A correspondência com o perfil `medium`

O perfil é conferido contra o **estate canônico** — o mesmo que o pipeline do gerador constrói
(`apply_all(build_estate(seed, profile, currency))`, `tools/synthetic_clouds/cli.py:109`):

```
profile=medium window=120 (profile default) sim=2026-01-01..2026-04-30
  aws_resources_total       : 1110
  aws_resources_with_lines  : 966
  billing_lines_total       : 474390
  billing_lines_by_provider : {'Amazon Web Services': 118366, 'Google Cloud': 175865, 'Microsoft Azure': 180159}
  aws_billing_lines         : 118366
```

| Número da fase S4b2-D | Esperado `medium` | Medido | Onde |
|---|---|---|---|
| recursos AWS | **1.110** | **1.110** | estate canônico |
| linhas de faturamento | **474.390** | **474.390** | estate canônico (com cenários) |
| — | — | **966** | recursos AWS **com** linha de faturamento = os 966 `ResourceId` da árvore |

Os **966** `ResourceId` distintos da árvore publicada são exatamente os **966** recursos AWS que
têm linha de faturamento no estate: a árvore e o estate são o mesmo volume, medido pelos dois
lados.

## 5. O lado CloudPilot — o que mudou fora deste repositório

O repo do CloudPilot está **fora** da allowlist desta fase: nada lá foi editado. Duas mudanças
de **configuração** na conta de homologação (`HOMOLOGATION AWS [sim]`, workspace
`9ff4da5f-d8d1-4ba1-8a10-8ac67604f201`) foram necessárias para o consumidor ler a árvore nova:

| Mudança | Antes | Depois | Por quê |
|---|---|---|---|
| `cur_config.export_name` | `cloudpilot-focus12-daily-full` | `synthetic-focus12-daily-full` | o renderer emite este nome (§2.2); feito pelo endpoint oficial `PUT /api/v1/cur-ingestion/accounts/{id}/config` |
| `cloud_accounts.external_account_id` | *(vazio)* | `911368690069` | a promoção exige id AWS de 12 dígitos (§2.3). É a conta **payer** do estate (`ba-aws-1`), a mesma que o workspace sintético marca como `is_payer` |

O `s3_bucket` (`synthetic-focus12-daily-full`), o `s3_prefix` (`focus12-full`) e o
`endpoint_url` (`http://s3mock:9090`) **não** mudaram: o bucket que o consumidor lê já era o
bucket que o uploader publica.

### 5.1 A ingestão pelo mecanismo oficial

`POST /api/v1/cur-ingestion/accounts/e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc/ingest`:

```json
{ "status": "ok",
  "data": { "status": "ok", "periods_ingested": ["2026-03-01", "2026-04-01"],
            "files_read": 2, "rows_scanned": 78, "invoice_records_upserted": 6,
            "total_billed_cost": 166204.470549, "currency": "USD",
            "is_stale": false } }
```

E o log da promoção (o campo `cost_promotion_status` da resposta **não** reflete o resultado —
ele fica `"skipped"`; o log é a evidência):

```
cur_cost_promoted  grain=resource  rows_promoted=58926  total_billed_cost=166204.470549
```

No banco, o workspace de homologação passa a ter:

```
 cloud_account_id           | source | rows  | first_bp  | last_bp   | total_usd | sub_accounts | resources
 e6bc24c7-9db6-4fe2-a9ba-… | cur    | 58926 | 2026-03-01| 2026-04-01| 166204.47 |            3 |       966
 2e5ca016-81bb-4a0a-b440-… | azure  |  3332 | 2026-10-27| 2026-10-29|  59373.50 |            3 |      1111
```

### 5.2 O `/costs/unified` reflete o volume novo

`POST /api/v1/costs/unified` (conta de homologação, `X-Workspace-ID` do workspace):

| Janela | `total_cost` | `by_account` | `data_source` |
|---|---|---|---|
| antes (mês corrente) | 59.373,50 | só Azure | `focus_cost_records` |
| depois (2026-01-01 → 2026-04-30) | **166.204,47** | **aws · HOMOLOGATION AWS [sim] · 166.204,47** | `focus_cost_records` |

E no navegador (`http://localhost:5174/costs`, login `homologation@cloudpilot.io`, workspace
`CloudPilot - Homologation's Workspace`, intervalo *Year to Date*):

```
Custo Total            : US$ 225.578
Top conta              : HOMOLOGATION AWS [sim] — US$ 166.204,47 (73,7%)
Fonte                  : CUR/FOCUS
Amazon CloudWatch      : US$ 61.305,95
```

## 6. O que continua aberto

- **A entrega diária (FR-22) ainda não alimenta este consumidor.** `deliver_day` publica a
  árvore no bucket `cloudpilot-focus12-daily-full` com o export `cloudpilot-focus12-daily-full`;
  o consumidor lê `synthetic-focus12-daily-full` + `synthetic-focus12-daily-full`. Os dois
  namespaces divergem desde o *standalone publish*. `tools/**` está fora da allowlist — não foi
  corrigido aqui.
- **A árvore cobre a janela do perfil** (2026-01-01 → 2026-04-30, 120 dias), não "até hoje".
  A extensão diária é o papel da entrega diária — que, pelo item anterior, ainda não chega a
  este consumidor. A árvore anterior cobria 2026-01 → 2026-10 porque a entrega diária a
  empilhava.
- **O consumidor ingere os 2 períodos mais novos** (`CUR_INGEST_LOOKBACK_PERIODS`), ou seja 2 dos
  4 períodos da árvore. É política do consumidor, não da árvore.
- **A promoção tem granularidade `resource`** e a conta de homologação é **uma** conta para as
  **três** contas do estate; o total agregado é atribuído à conta payer, mas o escopo por
  `cost-dimensions` (que casa `sub_account_id` com `external_account_id`) deixa as outras duas
  contas AWS do estate sem conta própria.
- **O default `PROFILE: small` do `compose.aws.yaml` continua lá** — o compose está fora da
  allowlist. A proteção agora é dupla: o `.env` da instalação **e** o uploader, que lê o mesmo
  arquivo.
- **A imagem do `aws-sim` é mais antiga que os fontes do emulador** (`2026-10-28 14:49Z` vs
  `2026-10-28 22:27Z`). O script avisa; reconstruir é fase própria (`-Build`).
- **O store do `s3mock` é em memória**: recriar o container esvazia o bucket e obriga a rodar o
  uploader de novo.

## 7. Comandos de medição

```powershell
# a árvore servida pelo aws-sim (é o volume, pela superfície S3 do próprio emulador)
podman exec synthetic-clouds-aws-sim-1 cat /render/aws_focus/_provenance.json
podman exec synthetic-clouds-aws-sim-1 python -c "import os,json; ..."
# o que o leitor do CloudPilot vê
podman exec cloudpilot_backend python /tmp/s4b3a_list_s3.py
# o estate canônico do perfil
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix
```
