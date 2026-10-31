# Mapa de impacto — Fase S4b3-D (o fecho: a regressão do wrapper fica escrita, o doc EN fica verdadeiro, e a conta `[SYNTH] AWS acct-01` passa a ler a entrega que o consumidor publica)

**Data:** 2026-10-31 · **Revisão-base:** `adbede44` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `tools/synthetic_clouds/tests/test_schedule.py` (teste de regressão),
`docs/AGENDAMENTO.en.md` (correção), `docs/ESTADO.md`, `docs/ESTADO.en.md`, `README.md`,
`README.en.md`, este mapa.
**Fora do escopo:** `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`, `specs/**`,
`docs/NAO-COMPROVADOS*` (gerado), `docs/AGENDAMENTO.md` (fora da allowlist — ver §7),
`tools/synthetic_clouds/schedule/windows.py` (fora da allowlist — a correção da S4b3-C **não**
foi tocada aqui, só protegida) e o código do `C:\Projetos\cloudpilot-deploy` — na CloudPilot
houve **apenas ingestão/verificação** com a conta de homologação, sem uma linha de código
alterada.

**Por que esta fase existe.** A S4b3-C corrigiu o dono do `run-daily.cmd` gerado e **deixou
escrito, como dívida**, que o teste de regressão que fixa aquele comportamento morava em
`tools/synthetic_clouds/tests/test_schedule.py`, fora da allowlist daquela fase. Um fix sem
teste é um fix que pode voltar. Esta fase escreve o teste (e prova que ele falha sem o fix),
corrige o `docs/AGENDAMENTO.en.md` — que ainda afirmava que a tarefa do Windows **não** estava
registrada — e, no lado do consumidor, alinha a conta `[SYNTH] AWS acct-01` ao nome de export
que o simulador realmente publica, para que a leitura de custo do workspace padrão não fique
congelada.

## 1. O que muda

| | Antes (leitura de 2026-10-29/30) | Depois (leitura de 2026-10-31) |
|---|---|---|
| **Teste de regressão do wrapper** | **inexistente** — a correção da S4b3-C era verificável só por medição | **dois testes** na suíte do agendador, com prova vermelho-verde (§2) |
| **Suíte do agendador** | 92 passed | **94 passed** (92 + 2), sem regressão |
| **`run-daily.cmd` de produção depois da suíte** | podia ser **apagado** pela limpeza do teste | **byte-idêntico** (mesmo `sha256`, mesmo `LastWriteTime`) — verificado |
| **`docs/AGENDAMENTO.en.md`** | "11 days", ledger até `2026-10-26`, "the task **is not registered**" | **16 dias** (`2026-10-16` → `2026-10-31`), **tarefa registrada**, disparo próprio em `2026-10-31 13:06:47` |
| **`export_name` da conta `f4b259ca`** | `cloudpilot-focus12-daily-full` (export que o renderizador **não publica mais**) | **`synthetic-focus12-daily-full`** — o export que o consumidor lê (§4) |
| **`cur_last_execution_id` da conta `f4b259ca`** | `20261010T000000Z-eac552f3` | **`20261101T000000Z-eac552f3`** — a mesma entrega da conta de homologação |
| **Custo de outubro no workspace `e757043f`** | `8.333,66` | **`65.575,88`** (29.946 linhas promovidas) |
| **Custo da conta de homologação (ws `9ff4da5f`)** | `65.575,88` | **`65.575,88`** — **inalterado**, como deve ser (§5) |

O número que importa: **a entrega diária tem dono, a suíte não pode mais desligar o job, e o
consumidor lê as duas contas para o mesmo export.**

## 2. O teste de regressão (a dívida da S4b3-C, fechada)

### 2.1 O que os testes afirmam

Dois testes novos em `tools/synthetic_clouds/tests/test_schedule.py`, na classe
`TestWindowsRegistration`:

| Teste | O que fixa |
|---|---|
| `test_the_plan_writes_the_wrapper_next_to_its_own_configuration` | um plano com `config_path` num diretório temporário **gera o wrapper ali** — `plan.wrapper_path.parent == scratch.resolve()` — e **não** no caminho do pacote |
| `test_the_suite_does_not_touch_the_production_wrapper` | depois de `write_plan_files` **e da limpeza**, o `schedule/run-daily.cmd` de produção está **exatamente como estava**: mesmos bytes, mesmo `st_mtime_ns`, mesmo estado (presente ou ausente) |

O segundo teste **restaura** o arquivo se uma execução o tocar, em vez de apenas reprovar:
uma rodada vermelha não pode destruir a tarefa real. A restauração acontece no `finally`,
**depois** da asserção — o defeito continua reprovando o teste, e o artefato volta ao lugar.

### 2.2 A prova vermelho-verde

Reverter o fix da S4b3-C (uma linha, em `windows.py`) e rodar:

```
$ .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py \
    -v -k "next_to_its_own_configuration or does_not_touch_the_production_wrapper"
```

**Com o fix revertido** (`target_dir = _PACKAGE_ROOT / "schedule"`):

```
FAILED tools/synthetic_clouds/tests/test_schedule.py::TestWindowsRegistration::test_the_plan_writes_the_wrapper_next_to_its_own_configuration
FAILED tools/synthetic_clouds/tests/test_schedule.py::TestWindowsRegistration::test_the_suite_does_not_touch_the_production_wrapper
2 failed, 92 deselected, 1 warning in 0.24s      <- exit 1
```

A asserção que reprova, naverbatim:

```
E  AssertionError: assert WindowsPath('C:/Projetos/Simulador/tools/synthetic_clouds/schedule/run-daily.cmd')
E              == WindowsPath('.../out/pytest-schedule/pid-23892/test_the_suite_does_not_touch_the_production_wrapper/run-daily.cmd')
```

**Com o fix restaurado** (`git checkout -- tools/synthetic_clouds/schedule/windows.py`):

```
2 passed, 92 deselected, 1 warning in 0.10s
```

E a suíte inteira:

```
$ .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
94 passed, 1 warning in 14.50s
```

### 2.3 O wrapper de produção sobreviveu à rodada vermelha

Este é o ponto que a S4b3-C mediu à mão e que agora é automático. **A assinatura do arquivo
antes e depois de tudo:**

```
wrapper ANTES  : mtime=2026-10-31T13:06:47.0627020-03:00  sha256=D7C22E20EEA8D14F8585A8631782F13084D94F452E29264ECCE9DBC9473D8F51
wrapper DEPOIS : mtime=2026-10-31T13:06:47.0627020-03:00  sha256=D7C22E20EEA8D14F8585A8631782F13084D94F452E29264ECCE9DBC9473D8F51
```

O mesmo vale depois da **rodada vermelha** (com o fix revertido): o teste falhou — como deve
falhar — e o `finally` devolveu o arquivo com o mesmo `sha256` e o mesmo `mtime`.

> O `run-daily.cmd` e o `simulador-nuvem-daily.xml` são artefatos **gerados** e **não
> rastreados** no git. Por isso o backup antes da prova vermelha foi para `$env:TEMP`, e não
> para o repositório.

### 2.4 Lint e tipos

| Ferramenta | Antes | Depois |
|---|---|---|
| `ruff check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml` | 4 erros | **4 erros** (os mesmos: `deliver/core.py` `S310`/`S608` e `test_gcp_topology_render.py` `N802` ×2) — **nenhum novo** |
| `mypy -p tools.synthetic_clouds --config-file tools\synthetic_clouds\pyproject.toml` | 10 erros | **10 erros** — os mesmos 10, **nenhum em `test_schedule.py`** |

A primeira passada do mypy acusou **3** `union-attr` no teste novo (`st_mtime_ns` de um
`stat_result | None`). Foram corrigidos no próprio teste,ootro `stat()` para os dois
timestamps, e o mypy voltou ao baseline de 10.

## 3. `docs/AGENDAMENTO.en.md` corrigido

O documento em inglês ainda afirmava coisas que a leitura de 2026-10-31 desmente:

| Afirmação antiga | Leitura real (2026-10-31) |
|---|---|
| "**11 days** generated, from `2026-10-16` to `2026-10-26`" | **16 dias**, de `2026-10-16` a `2026-10-31` |
| "target now: `2026-10-29`" | alvo `2026-10-31` |
| "Windows task — **not registered**" | **registrada**: próxima execução `2026-11-01T12:00:00`, disparo no logon, `StartWhenAvailable=true` |
| "the ledger is 3 days behind the target" | ledger **em dia** (`up-to-date` em `2026-10-31T13:06:48.390274-03:00`) |
| "in the 2026-10-29 reading, the task **is not registered**" | a tarefa **disparou sozinha** em `2026-10-31 13:06:47`, com `Último resultado: 0` |

A seção "State of this installation" passou a citar a **leitura real** (`schedule status`), e
ganhou uma subseção nova, *"The wrapper belongs to its configuration"*, que explica por que o
wrapper é escrito ao lado da configuração que o possui — e por que um teste não pode apagar o
que a tarefa de produção executa.

**O `docs/AGENDAMENTO.md` (PT) continua desatualizado** — ele está **fora da allowlist**
desta fase. Ver §7.

## 4. A conta `[SYNTH] AWS acct-01` alinhada ao export

### 4.1 O que estava errado

Duas contas AWS com o **mesmo** `external_account_id` (`911368690069`) e o **mesmo** bucket:

| Conta | Workspace | `export_name` | `cur_last_execution_id` |
|---|---|---|---|
| `HOMOLOGATION AWS [sim]` (`e6bc24c7`) | `9ff4da5f` (Homologation) | `synthetic-focus12-daily-full` | `20261101T000000Z-eac552f3` |
| `[SYNTH] AWS acct-01` (`f4b259ca`) | `e757043f` (default da conta de homologação) | **`cloudpilot-focus12-daily-full`** | `20261010T000000Z-eac552f3` |

O renderizador publica em `synthetic-focus12-daily-full` — o export **antigo** da conta
`[SYNTH]` é o nome que ninguém publica mais. As chaves **existem** as duas no `s3mock`
(o export antigo tem entregas de `2026-01` a `2026-10`, o novo tem `2026-01` e
`2026-10-27` … `2026-11-01`), mas só o novo corresponde ao que o simulador gera hoje.

### 4.2 A correção, pelo mecanismo oficial

Nada foi escrito direto no banco. O caminho é o da API:

```
PUT /api/v1/cur-ingestion/accounts/f4b259ca-3a0d-49bb-ade9-bf75101317c8/config
  -> 200 {"status":"success","data":{"config":{... "export_name":"synthetic-focus12-daily-full" ...}},
          "meta":{"sync_queued":true,"task_id":"b5ccf7d5-369e-44e8-b316-59818d34b731"}}

POST /api/v1/cur-ingestion/accounts/f4b259ca-3a0d-49bb-ade9-bf75101317c8/ingest
  -> 200 {"status":"success","data":{"status":"ok","workspace_id":"e757043f-2325-506b-b3eb-e61f8d07147d",
       "periods_ingested":["2026-10-01"],"files_read":1,"rows_scanned":39,
       "invoice_records_upserted":3,"total_billed_cost":65575.879831,"currency":"USD", ...}}
```

Autenticação: **conta de homologação** (`homologation@cloudpilot.io`), com o
`X-Workspace-ID` **ausente** — o escopo veio do workspace **default** da conta
(`e757043f`), que é onde a conta `f4b259ca` mora. Nenhuma senha foi gravada em arquivo do
repositório nem neste documento.

A promoção das linhas de custo veio da task que o próprio `PUT` enfileirou
(`app.tasks.cur_ingestion_sync.sync_cur_for_account[b5ccf7d5-…]`, 7,28 s):

```
cur_cost_promoted_resource  cloud_account_id=f4b259ca-… rows_promoted=29946 total_billed_cost=65575.879831
cur_ingestion_account_done  cloud_account_id=f4b259ca-… cost_rows=29946 invoice_rows=3 status=ok workspace_id=e757043f-…
```

Estado final da conta:

```
name                | cur_last_execution_id       | cur_last_ingested_at
HOMOLOGATION AWS [sim] | 20261101T000000Z-eac552f3 | 2026-10-31 15:53:30.768839+00
[SYNTH] AWS acct-01    | 20261101T000000Z-eac552f3 | 2026-10-31 17:05:38.782847+00
```

As duas contas leem **a mesma entrega**. No ledger (`focus_cost_records`), a janela de
outubro de 2026 é idêntica nas duas:

```
HOMOLOGATION AWS [sim] | 9ff4da5f | 29946 linhas | 65575.88 | de 2026-10-01 a 2026-10-01
[SYNTH] AWS acct-01    | e757043f | 29946 linhas | 65575.88 | de 2026-10-01 a 2026-10-01
```

## 5. Os dois números do `/costs/unified` — e por que são diferentes

O endpoint é `POST /api/v1/costs/unified` (a janela default é o mês corrente: `2026-10-01` a
`2026-10-31`).

**Workspace `e757043f` (sem header — o default da conta):**

```
total_cost=646370.57   is_stale=False   data_state=partial   metadata.source=cur
   - [SYNTH] AWS acct-01          (f4b259ca)  aws    65575.88   data_state=available
   - [SYNTH] GCP contoso-prod-01  (a77c3a50)  gcp    83865.74   data_state=available
   - [SYNTH] AZURE container-export-01 (212dc724) azure 496928.95 data_state=available
   - AWS Account 1 / AWS Account 2            cost=null          data_state=no_data_for_account
```

**Workspace `9ff4da5f` (com `X-Workspace-ID`):**

```
total_cost=282678.76   is_stale=False   data_state=partial   metadata.source=cur
   - HOMOLOGATION AWS [sim]       (e6bc24c7)  aws    65575.88   data_state=available
   - HOMOLOGATION GCP [sim]       (a666626a)  gcp    83865.74   data_state=available
   - HOMOLOGATION GCP [conta real] (2f008b9a) gcp    73863.63   data_state=available
   - HOMOLOGATION AZURE [conta real] (2e5ca016) azure 59373.50 data_state=available
   - HOMOLOGATION AZURE [sim]     (6e6f4967)  azure  cost=null  data_state=unavailable
```

**Por que 646.370,57 e 282.678,76?** Porque os dois workspaces **não têm as mesmas contas**.
A conta AWS é a mesma nos dois e vale **65.575,88** nos dois — é a mesma entrega do mesmo
export, promovida em workspaces diferentes:

- `e757043f`: `496.928,95` (Azure) + `83.865,74` (GCP) + `65.575,88` (AWS) = **`646.370,57`**
- `9ff4da5f`: `83.865,74` + `73.863,63` + `65.575,88` + `59.373,50` = **`282.678,75`** (o
  endpoint reporta `282.678,76` — arredondamento do total)

E o **custo da conta de homologação não se moveu**: `65.575,88` antes e depois da ingestão da
`[SYNTH]`, exatamente como deve ser — a ingestão é escopada por `workspace_id` +
`cloud_account_id` (`promotion.py:458`), então a conta da outra workspace não foi tocada.

**Duas formas do mesmo dado.** A **primeira** leitura logo depois da ingestão voltou pelo
caminho frio do SWR: `is_stale=True`, `warming=False` e `data_source: focus_cost_records`
(o fallback P74 lê `focus_cost_records` direto). Depois que o warm assentou, a mesma rota
devolveu `is_stale=False` com `metadata.source=cur`. **As duas formas apontam para a mesma
fonte** — o ledger CUR (`focus_cost_records`) — e o número de AWS é o mesmo nas duas. As três
leituras espaçadas de 30 s deram valores idênticos.

## 6. O que a fase entregou, em uma linha

**O wrapper gerado tem dono, a suíte não pode mais desligar o job, o documento em inglês
diz a verdade, e as duas contas AWS do consumidor leem o mesmo export — com o workspace
padrão mostrando custo de outubro em vez de um número congelado.**

## 7. Lacunas declaradas (o que esta fase **não** resolve)

1. **`docs/AGENDAMENTO.md` (a versão em português) continua desatualizado.** Ele ainda diz
   "11 dias", ledger até `2026-10-26` e tarefa não registrada. O arquivo está **fora da
   allowlist** desta fase (`docs/AGENDAMENTO.en.md` é que estava dentro), então o texto não
   foi corrigido aqui. **A dívida que a S4b3-C deixou em cima do próprio gemelo agora está no
   outro idioma** — é a próxima fase que fecha.
2. **A árvore FOCUS de `2026-01` → `2026-04` do `aws-sim` não está no bucket.** O `s3mock` é
   em memória; repô-la é outra fase, como na S4b3-C.
3. **A tabela CUD do BigQuery diverge do esperado** (esperado 3, veio 9) — fora do escopo
   desta fase, como na S4b3-C.
4. **A resposta de promoção do CloudPilot segue fora de escopo** — e é bom registrá-lo: no
   `ingest` manual o bloco `ingestion.cost_rows_promoted` veio `0` com
   `cost_promotion_status: "skipped"`, **enquanto** o bloco irmão `promotion` do mesmo retorno
   dizia `status: ok, rows_promoted: 29946`. A promoção **ocorreu** (confirmado no log do
   celery e no banco); o que não se fecha aqui é **por que** o primeiro bloco reporta `skipped`.
5. **`HOMOLOGATION AZURE [sim]` está `unavailable`** no workspace `9ff4da5f`, com
   `multicloud_cost_failed` no log: `cannot import name 'ResourceManagementClient' from
   'azure.mgmt.resource'`. É defeito **pré-existente** do CloudPilot, fora da allowlist
   (nenhuma linha do `C:\Projetos\cloudpilot-deploy` foi alterada).
6. **`AWS Account 1` e `AWS Account 2`** no workspace `e757043f` respondem
   `no_data_for_account` — contas sem dado de custo, pré-existente, não tocadas.

## 8. Verificação

```powershell
# suíte do agendador
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
# -> 94 passed, 1 warning in 14.50s

# lint e tipos (a forma oficial, com --config)
& .\.venv\Scripts\python.exe -m ruff check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml
# -> Found 4 errors  (os 4 pré-existentes)
& .\.venv\Scripts\python.exe -m mypy -p tools.synthetic_clouds --config-file tools\synthetic_clouds\pyproject.toml
# -> Found 10 errors in 8 files (checked 8214 source files)  (os 10 pré-existentes)

# estado do agendador
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.schedule status
# -> ledger: 16 dias, 2026-10-16 .. 2026-10-31, ultima execucao 2026-10-31T13:06:48 (up-to-date)
# -> tarefa: registrada, diario 2026-11-01T12:00:00

# integridade do wrapper de produção
Get-FileHash tools\synthetic_clouds\schedule\run-daily.cmd -Algorithm SHA256
# -> D7C22E20EEA8D14F8585A8631782F13084D94F452E29264ECCE9DBC9473D8F51 (inalterado)
```
