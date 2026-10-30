# Mapa de impacto — Fase S4b3-B (a entrega diária publica no export que o consumidor lê)

**Data:** 2026-10-30 · **Revisão-base:** `dd1c3403` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `tools/synthetic_clouds/deliver/**` (código e doc do pacote),
`tools/synthetic_clouds/tests/test_deliver_namespace.py` (teste de regressão), `docs/**`,
`README.md`, `README.en.md`, `deploy/synthetic-clouds/README.md` ·
**Fora do escopo:** `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`, `specs/**`,
`docs/NAO-COMPROVADOS*` (gerado) e o código do `C:\Projetos\cloudpilot-deploy` — na CloudPilot
houve **apenas ingestão/verificação** com a conta de homologação, sem uma linha de código
alterada.

**Por que esta fase existe.** A S4b3-A fechou o lado do **produtor** (a árvore FOCUS/S3 servida
pelo `aws-sim`, re-renderizada no perfil `medium`) e deixou escrito, como dívida: *"A entrega
diária (FR-22) ainda publica no bucket `cloudpilot-focus12-daily-full` com o export
`cloudpilot-focus12-daily-full` — namespace que o consumidor não lê"*. Esta fase fecha o lado do
**mecanismo de entrega**: o dia gerado precisa chegar ao consumidor, todo dia, no namespace que
ele lê. Sem isso, o que roda no Windows toda noite produz objetos que ninguém consome.

## 1. O que muda

| | Antes (S4b3-A) | Depois (S4b3-B) |
|---|---|---|
| **Bucket da entrega AWS** | `cloudpilot-focus12-daily-full` | **`synthetic-focus12-daily-full`** (`DEFAULT_AWS_BUCKET`) |
| **Segmento de export da entrega** | `cloudpilot-focus12-daily-full` | **`synthetic-focus12-daily-full`** (`DEFAULT_AWS_EXPORT_NAME`) |
| **Nome do export do renderer** | `synthetic-focus12-daily-full` | **inalterado** — o renderer não foi renomeado |
| **Bucket que o consumidor lê** | `synthetic-focus12-daily-full` | **inalterado** (`cur_config.s3_bucket`) |
| **Export que o consumidor lê** | `synthetic-focus12-daily-full` | **inalterado** (`cur_config.export_name`) |
| **Objetos no bucket do consumidor** | 6 (só a árvore do `aws-sim`, 2026-01 → 2026-04) | **7** — a árvore do `aws-sim` + a entrega do dia `2026-10-26` (2026-10) |
| **Conta AWS no `/costs/unified`** | `cost: null`, `data_state: "unavailable"`, `provider_status.aws: "unavailable"` | **`cost: 54143.54`, `data_state: "available"`, `provider_status.aws: "available"`** |
| **`data_source` da resposta** | ausente (caminho quente) | **`focus_cost_records`** (caminho frio, logo após a ingestão) |
| **`source_by_provider.aws`** | ausente | **`"AWS Cost and Usage Report"`** |
| **Teste de regressão do namespace** | inexistente | **`tools/synthetic_clouds/tests/test_deliver_namespace.py`** (3 testes) — o default da entrega é o nome que o renderer emite, nos três caminhos por onde ele sai (a constante, a assinatura de `deliver_day` e o CLI) |

A edição é de **três arquivos do pacote de entrega** (`+48 −9`) mais **um teste de regressão**
(47 linhas, novo): nada no renderer, nada no compose, nada no `.env` da instalação, nada no
CloudPilot.

## 2. Causa raiz — medida, não suposta

### 2.1 O namespace da entrega é decidido em três lugares, e só um estava certo

| Onde | Valor | Quem consome |
|---|---|---|
| `deploy/synthetic-clouds/compose.aws.yaml:83` — `AWS_SIM_BUCKET` | `synthetic-focus12-daily-full` | o `aws-sim` e o `s3mock` |
| `cur_config.s3_bucket` / `cur_config.export_name` (conta de homologação) | `synthetic-focus12-daily-full` | o leitor de CUR do CloudPilot |
| `tools/synthetic_clouds/deliver/core.py` — defaults de `deliver_day` | **`cloudpilot-focus12-daily-full`** | **ninguém** |

O `render/focus_aws.py` emite `EXPORT_NAME = "synthetic-focus12-daily-full"` — o mesmo nome que
o bucket e que o consumidor já usavam. A entrega era a **única** peça do circuito fora do
namespace, e por isso a entrega não era consumida: o dia era gerado, o objeto subia para o S3, a
ingestão reportava `status: ok`, e o `/costs/unified` continuava sem AWS.

### 2.2 Por que o `.env` da instalação não resolvia

`deploy/synthetic-clouds/.env` é o arquivo que o **compose** interpola. O **gerador e a entrega
rodam no host**, e o wrapper que a tarefa do Windows executa
(`tools/synthetic_clouds/schedule/windows.py:86-104`) escreve um `.cmd` que faz exatamente duas
coisas antes do `tick`:

```cmd
set "PYTHONPATH={repo_root}"
cd /d "{repo_root}"
"{python_exe}" -m tools.synthetic_clouds.schedule tick --config "{config_path}" --deliver >> "{task_log}" 2>&1
```

Não há leitura do `.env` ali. E o `.env` também não teria ajudado: ele fixa `SEED`, `PROFILE`,
`AWS_SIM_SEED`, `AWS_SIM_PROFILE`, `WINDOW_DAYS`, `CURRENCY`, `API_PORT`, `API_PAGE_SIZE` — não
tem nenhuma variável `DELIVERY_*`. **O namespace da entrega nunca foi configurável por arquivo
nesta instalação**: ele vinha do código.

### 2.3 O caminho do agendado não passa pelo CLI — e por isso o default é o que manda

Há **dois** caminhos de entrega, e eles não leem as mesmas coisas:

- **CLI** (`python -m tools.synthetic_clouds.deliver --day <dia>`): lê `DELIVERY_AWS_BUCKET` /
  `DELIVERY_AWS_EXPORT_NAME` do ambiente, com default **no código**.
- **Tarefa do Windows** (`tick --deliver`): `schedule/__main__.py:227` chama
  `deliver_day(day, daily_root=DEFAULT_OUT)` — **sem argumento de namespace**, então valem os
  defaults de `deliver/core.py`.

Corrigir só o CLI deixaria a tarefa do Windows publicando no namespace morto. Por isso os dois
defaults foram corrigidos, e a constante passou a ser a **fonte única** (`DEFAULT_AWS_BUCKET` /
`DEFAULT_AWS_EXPORT_NAME` em `deliver/core.py`, importada pelo CLI e re-exportada pelo pacote).

### 2.4 Por que o defeito era silencioso

`deliver_aws` faz `PUT` das chaves e **não valida nada**: um `PUT` bem-sucedido num bucket que
ninguém lê produz exatamente o mesmo log (`ok: true`, `aws_objects: 1`) que um `PUT` no bucket
certo. Não há, em nenhum ponto do caminho, uma checagem de que o namespace publicado é o que o
consumidor está configurado para ler. Essa checagem continua **fora** desta fase (ver §5).

## 3. A correção

```diff
--- a/tools/synthetic_clouds/deliver/core.py
+++ b/tools/synthetic_clouds/deliver/core.py
@@ -45,6 +49,15 @@ _BULK_BATCH = 500
 _RESOURCE_TABLE = "gcp_billing_export_resource_v1_ba_gcp_1"
 _STANDARD_TABLE = "gcp_billing_export_v1_ba_gcp_1"

+#: Namespace the CloudPilot CUR reader is configured with: the bucket it lists
+#: and the export segment it expects under the prefix. It is the name the
+#: renderer itself emits (``render/focus_aws.py``), NOT a delivery-only alias.
+#: A delivery that publishes under a different name writes into a namespace no
+#: reader looks at: the objects land in S3, the ingestion reports success, and
+#: the day never reaches the consumer. Measured in S4b3-B.
+DEFAULT_AWS_BUCKET = "synthetic-focus12-daily-full"
+DEFAULT_AWS_EXPORT_NAME = "synthetic-focus12-daily-full"
+

 @dataclass(slots=True)
 class DeliveryResult:
@@ -225,9 +241,9 @@ def deliver_day(
     daily_root: Path,
     targets: Iterable[str] = ("aws", "gcp", "azure"),
     aws_endpoint: str = "http://localhost:9090",
-    aws_bucket: str = "cloudpilot-focus12-daily-full",
+    aws_bucket: str = DEFAULT_AWS_BUCKET,
     aws_prefix: str = "focus12-full",
-    aws_export_name: str = "cloudpilot-focus12-daily-full",
+    aws_export_name: str = DEFAULT_AWS_EXPORT_NAME,
     gcp_endpoint: str = "http://localhost:9050",
```

```diff
--- a/tools/synthetic_clouds/deliver/__main__.py
+++ b/tools/synthetic_clouds/deliver/__main__.py
@@ -61,10 +65,10 @@ def main(argv: list[str] | None = None) -> int:
         targets=targets,
         aws_endpoint=os.environ.get("DELIVERY_AWS_ENDPOINT", "http://localhost:9090"),
-        aws_bucket=os.environ.get("DELIVERY_AWS_BUCKET", "cloudpilot-focus12-daily-full"),
+        aws_bucket=os.environ.get("DELIVERY_AWS_BUCKET", DEFAULT_AWS_BUCKET),
         aws_prefix=os.environ.get("DELIVERY_AWS_PREFIX", "focus12-full"),
         aws_export_name=os.environ.get(
-            "DELIVERY_AWS_EXPORT_NAME", "cloudpilot-focus12-daily-full"
+            "DELIVERY_AWS_EXPORT_NAME", DEFAULT_AWS_EXPORT_NAME
         ),
```

`deliver/__init__.py` re-exporta as duas constantes. O literal deixou de existir em três
arquivos; hoje ele está em **um** lugar, e o nome vem do renderer.

O CLI ganhou um helper `_aws_settings()` que concentra a resolução do namespace
(ambiente → default), para que o fallback seja testável sem subir um servidor S3. E o teste de
regressão fecha o invariante:

```python
def test_delivery_default_namespace_is_the_name_the_renderer_emits() -> None:
    """The renderer's own name is the only namespace that can be published and read."""
    assert deliver_core.DEFAULT_AWS_BUCKET == focus_aws.EXPORT_NAME
    assert deliver_core.DEFAULT_AWS_EXPORT_NAME == focus_aws.EXPORT_NAME
```

## 4. Medições

### 4.1 A entrega

Dia gerado escolhido: **`2026-10-26`** — o mais recente **completo** do ledger
(`out/daily/_state/state.json`: `status: complete`, 12.119 artefatos). O diretório `2026-10-27`
existe mas está **parcial** (só `aws_config_snapshot` e `azure_arm_instances`, sem `aws_focus`),
entregá-lo não teria nada a publicar.

```powershell
> & .\.venv\Scripts\python.exe -m tools.synthetic_clouds.deliver --day 2026-10-26 --targets aws
{"aws_objects": 1, "azure_days": null, "day": "2026-10-26", "errors": [], "gcp_rows": 0, "ok": true}
EXIT=0
```

**Caminho do agendado** — a chamada exata que `schedule/__main__.py:227` faz (sem namespace, com
os três alvos):

```python
> deliver_day(date.fromisoformat('2026-10-26'), daily_root=DEFAULT_OUT)
DeliveryResult(day='2026-10-26', aws_objects=1, gcp_rows=2268, azure_days=303, errors=[])
EXIT=0
```

Os dois caminhos publicam no namespace corrigido. O segundo exercita também os alvos `gcp` e
`azure` da entrega oficial: **2.268 linhas** inseridas no BigQuery emulado e o estate do
`azure-sim` estendido até **303 dias**.

### 4.2 O efeito no S3

Antes: **6 chaves**, 1 bucket. Depois: **7 chaves**, 1 bucket.

```
=== BUCKETS no s3mock ===
synthetic-focus12-daily-full

=== CHAVES no bucket do consumidor (synthetic-focus12-daily-full) ===
KeyCount=7
_provenance.json  (4093 bytes, 2026-10-30T19:15:31.822Z)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-01/20260113T000000Z-80f388ff/synthetic-focus12-daily-full-00001.snappy.parquet  (1291518 bytes)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-01/20260201T000000Z-80f388ff/synthetic-focus12-daily-full-00001.snappy.parquet  (3273234 bytes)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-02/20260301T000000Z-238acda6/synthetic-focus12-daily-full-00001.snappy.parquet  (2972539 bytes)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-03/20260401T000000Z-0d644f6f/synthetic-focus12-daily-full-00001.snappy.parquet  (3284866 bytes)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-04/20260501T000000Z-6b092ea7/synthetic-focus12-daily-full-00001.snappy.parquet  (3185553 bytes)
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261027T000000Z-eac552f3/synthetic-focus12-daily-full-00001.snappy.parquet  (2734569 bytes, 2026-10-30T19:58:40.454Z)
```

Duas leituras que importam:

- **O bucket `cloudpilot-focus12-daily-full` não existe.** A entrega antiga criaria um bucket
  próprio; hoje há **um** bucket, o que o consumidor lê.
- A chave nova tem **2.734.569 B**, exatamente o tamanho do parquet de origem
  (`out/daily/2026-10-26/123-medium-USD/render/aws_focus/focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261027T000000Z-eac552f3/synthetic-focus12-daily-full-00001.snappy.parquet`).

### 4.3 A ingestão no CloudPilot

Mecanismo oficial (`POST /api/v1/cur-ingestion/accounts/{id}/ingest`, conta
`HOMOLOGATION AWS [sim]` = `e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc`, workspace
`9ff4da5f-d8d1-4ba1-8a10-8ac67604f201`):

```json
{
  "status": "ok",
  "data": {
    "cloud_account_id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc",
    "workspace_id": "9ff4da5f-d8d1-4ba1-8a10-8ac67604f201",
    "status": "ok",
    "periods_ingested": ["2026-04-01", "2026-10-01"],
    "files_read": 2,
    "rows_scanned": 78,
    "invoice_records_upserted": 6,
    "total_billed_cost": 140108.435868,
    "currency": "USD",
    "cost_rows_promoted": 0,
    "cost_promotion_status": "skipped",
    "cost_total_billed": null,
    "source": null,
    "is_stale": false
  }
}
```

**`cost_promotion_status: "skipped"` mente.** O campo da resposta é o comportamento *fail-closed*
conhecido (a promoção só ocorre com `external_account_id` de 12 dígitos — esta conta tem
`911368690069`), e **não** reflete o que aconteceu. O log do backend diz o que aconteceu:

```
cur_cost_promoted_resource  cloud_account_id=e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc
                             method=POST  path=/api/v1/cur-ingestion/accounts/e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc/ingest
                             request_id=c2a6bb06-173d-41c6-a883-6786bd493709
                             rows_promoted=54096  total_billed_cost=140108.435868
```

**54.096 linhas promovidas** para `focus_cost_records`.

**A configuração do consumidor não foi tocada.** A conta `HOMOLOGATION AWS [sim]` está como a
S4b3-A a deixou — `s3_bucket: synthetic-focus12-daily-full`, `s3_prefix: focus12-full`,
`export_name: synthetic-focus12-daily-full`, `endpoint_url: http://s3mock:9090`,
`enabled: true`, `external_account_id: 911368690069`. O que mudou são só os campos de
livro-razão da ingestão:

```
cur_last_ingested_at   = 2026-10-30 20:00:02.111018+00
cur_last_execution_id  = 20261027T000000Z-eac552f3
```

`cur_last_execution_id` é agora **a execução da entrega diária** — a prova direta de que o
consumidor leu o objeto que a entrega publicou (e não um objeto antigo da árvore do
`aws-sim`, cujas execuções são `20260113T…`, `20260201T…`, `20260301T…`, `20260401T…` e
`20260501T…`).

### 4.4 O `/costs/unified`

**Antes** (baseline, antes de qualquer escrita; janela padrão 2026-10-01 → 2026-10-30):

```json
{
  "total_cost": 59373.5,
  "data_state": "partial",
  "by_provider": [{"provider": "azure", "cost": 59373.5, "pct": 100.0, "data_state": "available"},
                  {"provider": "gcp",   "cost": 0.0,    "pct": 0.0,   "data_state": "available"}],
  "by_account": [{"id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc", "name": "HOMOLOGATION AWS [sim]",
                  "provider": "aws", "cost": null, "data_state": "unavailable"}],
  "accounts_with_data": 3,
  "metadata": {"source": "cur",
               "source_by_provider": {"azure": "Azure Cost Management export"},
               "provider_status": {"aws": "unavailable", "azure": "available", "gcp": "available"}}
}
```

**Depois** — a chamada logo após a ingestão (cache invalidado pela própria ingestão) responde
pelo caminho de `focus_cost_records`:

```json
{
  "total_cost": 113517.05,
  "by_account": [
    {"id": "2e5ca016-81bb-4a0a-b440-27cb2d89587f", "name": "HOMOLOGATION AZURE [conta real]",
     "provider": "azure", "cost": 59373.5},
    {"id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc", "name": "HOMOLOGATION AWS [sim]",
     "provider": "aws", "cost": 54143.54}
  ],
  "metric_requested": "net_amortized",
  "metric_applied": "net_amortized",
  "data_source": "focus_cost_records"
}
```

E a chamada seguinte (payload re-calculado, cache quente) mostra a AWS **disponível** no caminho
normal:

```json
{
  "total_cost": 113517.05,
  "data_state": "partial",
  "by_provider": [{"provider": "azure", "cost": 59373.5, "pct": 52.3, "data_state": "available"},
                  {"provider": "aws",   "cost": 54143.54, "pct": 47.7, "data_state": "available"},
                  {"provider": "gcp",   "cost": 0.0,    "pct": 0.0,   "data_state": "available"}],
  "by_account": [{"id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc", "name": "HOMOLOGATION AWS [sim]",
                  "provider": "aws", "cost": 54143.54, "data_state": "available"}],
  "accounts_with_data": 4,
  "metadata": {"source": "cur",
               "source_by_provider": {"azure": "Azure Cost Management export",
                                      "aws": "AWS Cost and Usage Report"},
               "provider_status": {"aws": "available", "azure": "available", "gcp": "available"}}
}
```

(O `gcp: 0.0` e o `total_cost: 113517.05` desta leitura são os de **antes** de os dados do alvo
`gcp` da entrega aparecerem para o conector — ver §4.5.)

### 4.5 O efeito colateral dos alvos `gcp` e `azure` — e por que o total do workspace se move

O §4.1 rodou a entrega oficial com **os três alvos** (é a chamada do caminho do agendado, que não
filtra alvo). Isso **escreveu** fora do S3:

| Alvo | Efeito medido |
|---|---|
| `gcp` | **2.268 linhas** inseridas no BigQuery emulado (1.134 na tabela padrão + 1.134 na de recurso), dia `2026-10-26`; o emulador soma `cost = 14627.533293999992` e `cost_at_effective_price_default = 14627.574` para esse dia |
| `azure` | janela do estate do `azure-sim` estendida até **303 dias** (`POST /admin/estate/refresh`) |

A consequência no consumidor é **visível e precisa ser dita**: a conta `HOMOLOGATION GCP [sim]`
do workspace de homologação saiu de `0.0` para **14.613,94** (o valor do conector difere em
~13,59 do total do emulador pelo filtro/janela do próprio conector), e o `total_cost` do
workspace saiu de **113.517,05** para **128.130,99** — **não** por causa da mudança do AWS, que
ficou em **54.143,54** nas duas medições. O `data_source: "focus_cost_records"` continua
valendo:

```
total_cost = 128130.99
data_source = focus_cost_records
HOMOLOGATION AZURE [conta real]: 59373.5
HOMOLOGATION AWS [sim]:           54143.54
HOMOLOGATION GCP [sim]:           14613.94
```

Nada foi revertido: a escrita é o **comportamento correto** da entrega diária (é o que o
`tick --deliver` faz), e a conta de homologação é o destino declarado para validação que escreve.
O que se registra aqui é o **estado** em que o workspace de homologação ficou.

### 4.6 O volume é o do artefato entregue — conferido nos três lugares

| Onde | Valor |
|---|---|
| `EffectiveCost` do parquet entregue (25.634 linhas) | **54.143,544220** |
| `focus_cost_records`, período 2026-10 (25.116 linhas promovidas) | **54.143,54** |
| `/costs/unified` → `HOMOLOGATION AWS [sim]` | **54.143,54** |

Os três concordam. E a decomposição por período mostra que o valor do `/costs/unified` vem
**inteiramente** da entrega diária (a janela é outubro; os períodos do `aws-sim` são março e
abril):

```
periodo | linhas |  billed  | effective |     de     |   ate
--------+--------+----------+-----------+------------+------------
2026-03 |  29946 | 80239.58 |  80239.58 | 2026-03-01 | 2026-03-31
2026-04 |  28980 | 85964.89 |  85964.89 | 2026-04-01 | 2026-04-30
2026-10 |  25116 | 54143.54 |  54143.54 | 2026-10-01 | 2026-10-26
```

(25.634 linhas no parquet → 25.116 promovidas, e a diferença **não** é custo zerado: nenhuma
linha do artefato tem `BilledCost` zero ou negativo. A promoção roda em grão de recurso
(`CUR_RESOURCE_LEVEL_ENABLED=True`) e faz upsert na chave natural
`(SubAccountId, ResourceId, ChargePeriodStart)` — que no artefato tem exatamente **25.116**
grupos distintos. As 518 linhas a mais dividem a chave com outra e são **agregadas**, não
descartadas: somando por grupo sai o mesmo **54.143,544220**. Um `REPLACE` linha a linha
teria dado **52.993,088293** — 1.150 menor. A conta de homologação é **uma** para as **três**
contas do estate — o `external_account_id` declarado (`911368690069`) é o da conta payer, e é o
que faz a promoção ser *fail-closed* quando ausente.

## 5. O que continua aberto

- **O nome do export está em dois lugares independentes** — o default do `deliver/` e o
  `cur_config.export_name` do CloudPilot — e nada os amarra. A correção alinhou os dois; ela
  **não** impede a divergência de voltar. Um guard que compare o namespace publicado com o
  configurado no consumidor seria a correção estrutural, e ela é do lado do CloudPilot (fora
  da allowlist desta fase).
- **A entrega AWS não valida o que publica.** `deliver_aws` faz `PUT` e conta objetos; não
  confere se o bucket existe para o leitor nem se o nome bate. O lado **deste** repositório
  está coberto por um teste de regressão (`tests/test_deliver_namespace.py`: o default da
  entrega é o nome que o renderer emite) — mas o guard que impediria a divergência de
  **voltar** é do lado do CloudPilot, que compara o namespace publicado com o configurado no
  consumidor, e está fora da allowlist.
- **A tarefa do Windows não está registrada** (`simulador-nuvem-daily` não aparece no
  `schtasks`; ver `docs/AGENDAMENTO.md`). A entrega está pronta, mas **nada a dispara** — o
  backfill continua dependendo de alguém rodar o `tick`.
- **O ledger está atrás do alvo**: 11 dias completos (2026-10-16 → 2026-10-26) e um diretório
  parcial (2026-10-27) contra o alvo 2026-10-30.
- **A árvore do `aws-sim` cobre a janela do perfil** (2026-01 → 2026-04), não "até hoje"; a
  entrega diária é que cobre o dia corrente.
- **O consumidor ingere os 2 períodos mais novos** (`CUR_INGEST_LOOKBACK_PERIODS`) — com a
  entrega diária, o par ingerido passa a ser `{2026-04, 2026-10}`.
- **`CUR_INGEST_WORKSPACE_IDS=32428cd8-…`** no backend: a ingestão automática (Celery) só roda
  para o workspace *CloudPilot* do admin. A ingestão da conta de homologação foi disparada
  pelo endpoint oficial, à mão.
- **O store do `s3mock` é em memória**: recriar o container esvazia o bucket e o
  `aws-up.ps1` precisa rodar de novo.
- **A conta `[SYNTH] AWS acct-01`** (workspace `[SYNTH] Synthetic Workspace
  synthetic-homologation`) continua com `export_name = cloudpilot-focus12-daily-full` — o nome
  **morto**. Ela não faz mais parte desta fase (o alvo é a conta `HOMOLOGATION AWS [sim]`), mas
  é a mesma dívida, em outra conta: se alguém rodar a entrega para o namespace antigo, é essa
  conta que volta a receber.
- **Uma reingestão matou o worker do backend do CloudPilot — uma vez, e de forma não
  determinística.** Na segunda execução da ingestão do mesmo dia, o worker do uvicorn morreu no
  meio da promoção (`INFO: Child process [34] died`, sem traceback). Não foi OOM do container
  (`OOMKilled=false`, `RestartCount=0`, sem limite de memória) e o uvicorn reergueu o worker
  sozinho (`Started server process [1110]`). **O estado ficou íntegro**: `focus_cost_records` com
  as mesmas 84.042 linhas / US$ 220.348,01, `cur_last_ingest_error` vazio, `cur_last_ingested_at`
  no valor da execução bem-sucedida. A terceira execução passou (exit 0, 25,8 s,
  `rows_promoted=54096` de novo), então **não** é determinístico. É fragilidade do lado do
  CloudPilot, fora da allowlist desta fase — e **não** é efeito da mudança daqui: o repositório
  do CloudPilot não foi tocado, e o que a entrega faz é publicar um objeto no S3.

## 6. Reproduzir

```powershell
# 1. entrega do dia gerado, no namespace que o consumidor lê
> & .\.venv\Scripts\python.exe -m tools.synthetic_clouds.deliver --day 2026-10-26 --targets aws
{"aws_objects": 1, "azure_days": null, "day": "2026-10-26", "errors": [], "gcp_rows": 0, "ok": true}

# 2. o que apareceu no bucket do consumidor
> (Invoke-WebRequest "http://localhost:9090/synthetic-focus12-daily-full?list-type=2").Content

# 3. ingestão oficial no CloudPilot (conta de homologação)
> POST /api/v1/cur-ingestion/accounts/e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc/ingest
# 4. a resposta do consumidor
> POST /api/v1/costs/unified
```

O passo 3 devolve `cost_promotion_status: "skipped"` **mesmo tendo promovido**; o número vero
está no log do backend (`cur_cost_promoted_resource`, `rows_promoted=`).
