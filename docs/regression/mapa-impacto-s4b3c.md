# Mapa de impacto — Fase S4b3-C (a entrega diária roda sozinha: tarefa registrada e ledger em dia)

**Data:** 2026-10-31 · **Revisão-base:** `2e26dd13` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `tools/synthetic_clouds/schedule/windows.py` (correção), `docs/AGENDAMENTO.md`,
`docs/ESTADO.md`, `docs/ESTADO.en.md`, `README.md`, `README.en.md`, este mapa.
**Fora do escopo:** `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`, `specs/**`,
`docs/NAO-COMPROVADOS*` (gerado), `docs/AGENDAMENTO.en.md` (fora da allowlist — ver §8),
`tools/synthetic_clouds/tests/**` (fora da allowlist — ver §3.3) e o código do
`C:\Projetos\cloudpilot-deploy` — na CloudPilot houve **apenas ingestão/verificação** com a conta
de homologação, sem uma linha de código alterada.

**Por que esta fase existe.** A S4b3-B fechou o **namespace** da entrega (o dia chega ao bucket que o
consumidor lê) e deixou escrito, como dívida, que **ninguém disparava a entrega**. O Agendador do
Windows tinha a tarefa `simulador-nuvem-daily` registrada apontando para `D:\Simulador\...` — um
caminho de uma instalação que não existe nesta máquina — e o ledger estava parado em `2026-10-26`
com o alvo em `2026-10-30`. Esta fase fecha o circuito: **registra a tarefa no caminho atual,
recupera o atraso do ledger, e prova que o dia gerado chega ao consumidor** — e descobre, no
caminho, **duas armadilhas** que quebram justamente isso.

## 1. O que muda

| | Antes (leitura de 2026-10-29/30) | Depois (leitura de 2026-10-31) |
|---|---|---|
| **Tarefa do Windows** | registrada, mas com o wrapper em `D:\Simulador\...` (caminho morto) | **registrada com o caminho atual** — `cmd.exe /c "C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd"` |
| **Último resultado da tarefa** | `1` | **`0`** — disparada por `schtasks /run` às 13:06:47, com a linha no `task.log` |
| **Ledger** | 11 dias (`2026-10-16` → `2026-10-26`), alvo `2026-10-29` | **16 dias** (`2026-10-16` → `2026-10-31`), alvo `2026-10-31`, última execução `ok` |
| **Dia `2026-10-27`** | diretório **parcial** (render interrompido em `azure_arm_instances`, sem `aws_focus`) e **fora do ledger** | **completo e no ledger** — 45 superfícies renderizadas, `aws_focus` presente, igual ao `2026-10-31` |
| **Objetos no bucket do consumidor** | 1 (só a entrega de `2026-10-26`) | **5** — as entregas de `2026-10-27` … `2026-10-31` |
| **`/costs/unified` — conta AWS** | `HOMOLOGATION AWS [sim] · 54.143,54` | **`HOMOLOGATION AWS [sim] · 65.575,88`** (`data_source: focus_cost_records`) |
| **`cur_last_execution_id`** | `20261027T000000Z-eac552f3` | **`20261101T000000Z-eac552f3`** (a entrega de `2026-10-31`) |
| **Dono do `run-daily.cmd` gerado** | o **pacote** (`_PACKAGE_ROOT / "schedule"`) — quem instalou, apaga | **a configuração** (`config_path.parent`) — quem instala escreve, e um teste não apaga o wrapper instalado |
| **Código do repositório** | — | **uma correção** em `tools/synthetic_clouds/schedule/windows.py` (§3.3) |

O número que importa: **o dia passa a andar sozinho**. Antes, o ledger só crescia quando alguém
rodava `tick` na mão; agora há um gatilho diário às 12:00 e outro no logon — e a suíte de testes
deixa de ser capaz de desligar o job.

## 2. A tarefa registrada no caminho atual

O mecanismo oficial é `python -m tools.synthetic_clouds.schedule install`
(`tools/synthetic_clouds/schedule/__main__.py:284` → `schedule/windows.py:276`), e ele **reescreve
os dois artefatos** (`run-daily.cmd` e `simulador-nuvem-daily.xml`) e chama o `schtasks /Create
/TN simulador-nuvem-daily /XML ... /F`. Nada foi escrito à mão.

### 2.1 O que a leitura de 2026-10-29 acertou e o que ela não viu

O `docs/AGENDAMENTO.md` afirmava, na leitura de 2026-10-29, que a tarefa **não estava registrada**
(`schtasks` vazio). A leitura real de 2026-10-31 mostra outra coisa:

```
schtasks /query /tn simulador-nuvem-daily /v /fo LIST
  Tarefa a ser executada: cmd.exe /c "D:\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd"
  Status:                          Habilitada
  Última Resultado:                1
  Última execução Time:            31/10/2026 12:10:53
  Próxima execução Time:           01/11/2026 12:00:00
```

A tarefa **existia**, com dois gatilhos (diário às 12:00 + no logon) e `StartWhenAvailable`, mas
apontava para **`D:\Simulador`** — a árvore de uma instalação anterior, num drive que não existe
nesta máquina (`Test-Path D:\Simulador` → `False`). Por isso o último resultado era `1`: o
wrapper nem existia para ser executado.

A causa é a **mecânica**, não um bug do agendador: `install` resolve o caminho a partir da
localização do pacote, então uma árvore **movida** fica com um wrapper obsoleto até alguém rodar
`install` de novo. Nada no repositório detecta isso — e não deveria: registrar é uma operação de
instalação, não de código.

### 2.2 O `install` (saída real)

```
$ .\.venv\Scripts\python.exe -m tools.synthetic_clouds.schedule install
tarefa: simulador-nuvem-daily
conta:  DESKTOP-38HP3S9\ECUNHA
horario configurado: 12:00 (America/Sao_Paulo)
horario da tarefa:   12:00 (hora local da maquina)
primeiro disparo:    2026-11-01T12:00:00
wrapper:             C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd
xml:                 C:\Projetos\Simulador\tools\synthetic_clouds\schedule\simulador-nuvem-daily.xml
  C:\WINDOWS\System32\schtasks.exe /Create /TN simulador-nuvem-daily /XML C:\Projetos\Simulador\tools\synthetic_clouds\schedule\simulador-nuvem-daily.xml /F
  C:\WINDOWS\System32\schtasks.exe /Query /TN simulador-nuvem-daily

ok: tarefa simulador-nuvem-daily registrada (disparo diario + no logon, com StartWhenAvailable)
```

O `wrapper` gerado (gitignored, `schedule/run-daily.cmd` está fora do versionamento):

```cmd
@echo off
rem Gerado por `python -m tools.synthetic_clouds.schedule install`. Nao editar a mao:
rem o proximo install sobrescreve. A logica esta em schedule/runner.py.
setlocal
set "PYTHONPATH=C:\Projetos\Simulador"
cd /d "C:\Projetos\Simulador"
"C:\Projetos\Simulador\.venv\Scripts\python.exe" -m tools.synthetic_clouds.schedule tick --config "C:\Projetos\Simulador\tools\synthetic_clouds\schedule\config.json" --deliver >> "C:\Projetos\Simulador\tools\synthetic_clouds\out\daily\_state\task.log" 2>&1
exit /b %ERRORLEVEL%
```

### 2.3 A tarefa **dispara sozinha** (prova de execução real)

O wrapper foi restaurado (§3.3) e a tarefa disparada pelo próprio Agendador:

```
$ schtasks /run /tn simulador-nuvem-daily
ÊXITO: tentativa de executar a tarefa agendada "simulador-nuvem-daily".

$ schtasks /query /tn simulador-nuvem-daily /v /fo LIST
  Horário da última execução:                31/10/2026 13:06:47
  Último resultado:                          0
```

E o `task.log` recebeu a linha do `tick` — a prova de que o wrapper **rodou** (não só que o
Agendador aceitou o disparo):

```
alvo: 2026-10-31  fuso: America/Sao_Paulo  lag: 0d
nada a gerar: o ledger ja cobre o alvo
```

## 3. Duas armadilhas no caminho — ambas medidas

### 3.1 O podman não subia: socket Unix obsoleto

**Sintoma.** `podman ps` falhava com `unable to connect to Podman socket: failed to connect: dial
tcp 127.0.0.1:61926: … recusou ativamente`. A VM HyperV estava `Running`, mas nada escutava na
61926.

**Diagnóstico (medido, não suposto).**

| Medida | Resultado |
|---|---|
| `podman machine list` | `podman-machine-default · hyperv · Currently running` |
| `podman machine start` | `Error: unable to start "podman-machine-default": already running` |
| `podman --log-level=debug machine start` | `machine did not transition into running state: ssh error: machine is not listening on ssh port` |
| log do `gvproxy` (`%LOCALAPPDATA%\Temp\podman\gvproxy.log`) | `level=error msg="accept tcp 127.0.0.1:61926: use of closed network connection"` |
| `podman machine inspect` | `UserModeNetworking: true` (o forward SSH é feito pelo `gvproxy`, não pela VM) |

**ROOT CAUSE.** Um socket Unix obsoleto no `%LOCALAPPDATA%\Temp\podman\`. O
`podman-machine-default-api.sock` tinha data de **2026-10-30 10:13** — anterior a esta sessão. Com
`UserModeNetworking`, o `gvproxy` precisa fazer `bind` nesse caminho para abrir o forward da API; o
`bind` falhou com *"Normalmente é permitida apenas uma utilização de cada endereço de soquete"*, o
`gvproxy` morreu antes de criar o forward SSH da 61926, e o `podman machine start` passou a
esperar por um socket que jamais abriria. A mensagem `use of closed network connection` no log do
`gvproxy` é a **consequência**, não a causa.

**Correção:** remover o socket obsoleto (e o `gvproxy.pid`/`gvproxy.log` do mesmo diretório, que são
artefatos de runtime) e rodar `podman machine start` de novo:

```
$ podman machine stop   -> Machine "podman-machine-default" stopped successfully
$ podman machine start  -> Machine "podman-machine-default" started successfully
                           API forwarding listening on: npipe:////./pipe/docker_engine
```

### 3.2 O que a queda da VM levou junto (e o que foi restaurado)

A VM estava de pé, mas **todos os containers estavam parados há ~15 h** (`Exited (0) 15 hours ago`,
de antes desta sessão — a queda do plano não foi causada aqui). O store do `s3mock` é **em memória**
e o `bigquery-emulator` roda **DuckDB em memória** (`podman inspect … --format "{{json .Mounts}}"`
→ `[]`), então os dois perderam o estado:

| Estado | Depois da queda | O que foi feito | Rebuilt? |
|---|---|---|---|
| containers (25, dos dois planos + CloudPilot) | parados | `podman start` nos containers **existentes** (sem recreate) | **não** |
| aliases de rede (`s3mock`, `aws-sim` na bridge do CloudPilot) | — | preservados no config do container; conferido de dentro do backend: `s3mock -> 10.89.0.15`, `aws-sim -> 10.89.0.18` | **não** |
| store do `s3mock` (bucket) | `KeyCount=0` | repovoado pela própria entrega (§4) | — |
| tabelas do `bigquery-emulator` | `datasets: []` | provisionador one-shot com a **imagem existente** (`--no-deps`, **sem** `--build`), copiando a topologia renderizada de 2026-10-29 para o volume | **não** |

A restauração do BigQuery **não** passou pelo `gcp-up.ps1`: ele roda
`podman compose up -d --build --force-recreate bigquery-emulator gcp-sim`, ou seja, *rebuild* e
*recreate* — **fora do escopo desta fase**. O caminho usado foi o mesmo provisionador, com a
imagem que já existia em disco.

```
$ podman compose -p synthetic-clouds -f compose.gcp.yaml up --no-deps gcp-bq-provision
gcp-bq-provision-1  | ok: 08_rows_standard.json (14110 rows streamed into synthetic.all_billing_data.gcp_billing_export_v1_ba_gcp_1)
gcp-bq-provision-1  | ok: 09_rows_resource.json (14110 rows streamed into synthetic.all_billing_data.gcp_billing_export_resource_v1_ba_gcp_1)
gcp-bq-provision-1  | ok: 12_rows_pricing.json (10 rows streamed into synthetic.all_billing_data.cloud_pricing_export)
gcp-bq-provision-1  | error: row-count mismatch for cud (synthetic.all_billing_data.cud_subscriptions_export): expected 3, got 9
gcp-bq-provision-1 exited with code 1
```

As **duas tabelas que a entrega diária usa** foram criadas e populadas (14.110 linhas cada). A
saída `1` é de um **check de contagem da tabela de CUD** (discount de uso comprometido) —
inconsistência **pré-existente** do render de 2026-10-29 (`expected 3, got 9`), numa superfície que
a entrega diária não toca. Ver §8.

### 3.3 A suíte de testes apagava o wrapper instalado

**A segunda armadilha, e a mais silenciosa.** Depois do `install` das 12:21, a tarefa foi disparada
às **13:02:33** e o Agendador respondeu **`Último resultado: 1`** — sem nenhuma linha nova no
`task.log`. O wrapper não existia mais:

```
$ Test-Path C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd
False
```

**ROOT CAUSE.** `tools/synthetic_clouds/schedule/windows.py` derivava o caminho do wrapper da
**localização do pacote** (`_PACKAGE_ROOT / "schedule" / "run-daily.cmd"`), e não da configuração
à qual ele pertence. O teste `test_written_files_have_no_doubled_carriage_return`
(`tools/synthetic_clouds/tests/test_schedule.py:647-673`) escreve os artefatos do plano **nesse
caminho de produção** e no `finally` os apaga:

```python
wrapper, xml = windows.write_plan_files(plan)
try:
    ...
finally:
    wrapper.unlink(missing_ok=True)
    xml.unlink(missing_ok=True)
```

Ou seja: **rodar a suíte do agendador apagava o `run-daily.cmd` instalado** e a tarefa agendada
voltava a falhar com `1` — sem uma linha no `task.log`, porque o wrapper nem existia para
executar. Foi o que aconteceu aqui: o `install` das 12:21, a suíte rodada logo depois (92 passed),
e a tarefa às 13:02:33 sem wrapper.

**A correção** (`tools/synthetic_clouds/schedule/windows.py`): o wrapper e o XML passam a ser
derivados do **diretório da configuração** (`config_path.parent`), não do pacote:

```python
target_dir = config_path.resolve().parent
wrapper = guard_within_package(wrapper_path(target_dir))
...
xml_path=guard_within_package(target_dir / f"{task_name}.xml"),
```

A configuração instalada está em `schedule/`, então **o caminho de produção é idêntico ao de
antes** (`install` continua imprimindo `C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd`);
uma configuração em outro lugar — a de um teste — escreve **lá**, dentro do pacote (o `_SCRATCH` do
teste é `tools/synthetic_clouds/out/pytest-schedule/pid-<pid>`, então a fronteira NFR-4 continua
satisfeita) e **não pode mais apagar o que a tarefa de produção executa**.

**Medido:**

```
$ pytest tools\synthetic_clouds\tests\test_schedule.py -q
92 passed, 1 warning in 15.04s

wrapper ANTES da suite : Length 532, LastWriteTime 31/10/2026 13:04:29
wrapper DEPOIS da suite: Length 532, LastWriteTime 31/10/2026 13:04:29   <- sobreviveu
xml DEPOIS da suite   : True
```

**Em aberto:** o **teste de regressão** que fixa esse comportamento mora em
`tools/synthetic_clouds/tests/test_schedule.py`, que **não está na allowlist** desta fase — então
não foi adicionado aqui. A correção é verificável por medição (acima), mas a rede de proteção
automática fica para a fase que mexer nos testes.

## 4. O backfill pelo mecanismo oficial

Um único comando — o mesmo que a tarefa do Windows executa:

```
$ .\.venv\Scripts\python.exe -m tools.synthetic_clouds.schedule tick --deliver
alvo: 2026-10-31  fuso: America/Sao_Paulo  lag: 0d
gerados: 2026-10-27, 2026-10-28, 2026-10-29, 2026-10-30, 2026-10-31  artefatos: 60620
entrega 2026-10-27: aws=1 objetos, gcp=2260 linhas, azure=304 dias
entrega 2026-10-28: aws=1 objetos, gcp=2260 linhas, azure=304 dias
entrega 2026-10-29: aws=1 objetos, gcp=2256 linhas, azure=304 dias
entrega 2026-10-30: aws=1 objetos, gcp=2272 linhas, azure=304 dias
entrega 2026-10-31: aws=1 objetos, gcp=2282 linhas, azure=304 dias
EXIT=0   (duração: 830,5 s)
```

Sem erro em nenhum alvo. O `ledger` depois:

```
$ .\.venv\Scripts\python.exe -m tools.synthetic_clouds.schedule status
== ledger ==
dias gerados         16
primeiro             2026-10-16
ultimo               2026-10-31
alvo agora           2026-10-31
ultima execucao      2026-10-31T12:37:15.480065-03:00 (ok)

== tarefa do windows ==
  registrada:   simulador-nuvem-daily
  diario:       2026-11-01T12:00:00  (cada 1 dia(s))
  no logon de:  DESKTOP-38HP3S9\ECUNHA
  atraso perdido: StartWhenAvailable=True
  comando:      cmd.exe /c "C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd"
```

### 4.1 O alvo é `2026-10-31`, não `2026-10-30`

A fase foi escrita em 2026-10-30; a execução é de **2026-10-31**. Com `lag_days=0` (decisão de
2026-10-26, `1f674563`), o alvo **é o dia corrente**: o `tick` gerou até `2026-10-31` e o
`target_day` no ledger é `2026-10-31`. Gerar até o dia corrente é o comportamento documentado —
parar em `2026-10-30` seria truncar o backfill arbitrariamente.

### 4.2 O dia `2026-10-27` parcial foi **regenerado por inteiro**

A fase condicionava a entrega do `2026-10-27` a ele deixar de ser parcial. A leitura de 2026-10-31
do diretório mostrava `render/` interrompido em `azure_arm_instances`, **sem** `aws_focus`, e o
dia **fora do ledger** (interrompido no meio). O `tick` reescreveu o dia inteiro:

| | Antes | Depois |
|---|---|---|
| diretórios de render | 2 (`aws_config_snapshot`, `azure_arm_instances`) | **45** (idêntico ao `2026-10-31`) |
| `aws_focus` | ausente | **presente** (1 parquet, 30.542 linhas) |
| no ledger | não | **sim** |

O gerador não apaga o diretório antes de escrever, mas reescreve **todas** as superfícies
registradas (45 renderers registrados = 45 diretórios de render), então o resultado é completo.

### 4.3 O que foi para o bucket do consumidor

```
$ GET http://localhost:9090/synthetic-focus12-daily-full?list-type=2
KeyCount=5
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261028T000000Z-eac552f3/…parquet
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261029T000000Z-eac552f3/…parquet
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261030T000000Z-eac552f3/…parquet
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261031T000000Z-eac552f3/…parquet
focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261101T000000Z-eac552f3/…parquet
```

O `execution_id` é o dia **seguinte** ao do render (o export do dia `D` é publicado com o carimbo
`D+1`); é a mesma convenção da entrega da S4b3-B (`2026-10-26` → `20261027T000000Z-eac552f3`).

## 5. A ingestão oficial e o `/costs/unified`

Conta de homologação: `HOMOLOGATION AWS [sim]` (`e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc`,
`external_account_id=911368690069`), no workspace **CloudPilot - Homologation's Workspace**
(`9ff4da5f-d8d1-4ba1-8a10-8ac67604f201`) — **não** o workspace padrão do usuário, que é
`[SYNTH] Synthetic Workspace synthetic-homologation`. O `cur_config` da conta:

```json
{
  "enabled": true,
  "s3_bucket": "synthetic-focus12-daily-full",
  "s3_prefix": "focus12-full",
  "export_name": "synthetic-focus12-daily-full",
  "export_format": "focus",
  "region": "us-east-1",
  "endpoint_url": "http://s3mock:9090",
  "s3_force_path_style": true,
  "endpoint_overrides": { "sts": "http://aws-sim:8086", "gcp_base_url": null, "gcp_bigquery_endpoint": null, "azure_authority": null, "azure_base_url": null }
}
```

### 5.1 Ingestão (`POST /api/v1/cur-ingestion/accounts/{id}/ingest`)

```json
{
  "status": "ok",
  "data": {
    "cloud_account_id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc",
    "workspace_id": "9ff4da5f-d8d1-4ba1-8a10-8ac67604f201",
    "status": "ok",
    "billing_account_id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc",
    "periods_ingested": ["2026-10-01"],
    "files_read": 1,
    "rows_scanned": 39,
    "invoice_records_upserted": 3,
    "total_billed_cost": 65575.879831,
    "currency": "USD",
    "cost_rows_promoted": 0,
    "cost_promotion_status": "skipped",
    "cost_total_billed": null,
    "is_stale": false,
    "started_at": "2026-10-31T15:52:55.294071Z",
    "finished_at": "2026-10-31T15:53:33.350072Z"
  }
}
```

**`cost_rows_promoted: 0` e `cost_promotion_status: "skipped"` mentem.** No CloudPilot, esses dois
campos são **defaults do schema** (`app/schemas/cur_ingestion.py:224-226`) e **nunca são
atribuídos** em nenhum ponto do código (`grep` por `cost_promotion_status\s*=` e
`cost_rows_promoted\s*=` em `backend/app` → **zero ocorrências** de atribuição). O resultado real da
promoção está **só no log**:

```
podman logs cloudpilot_backend | Select-String cur_cost_promoted_resource
  cur_cost_promoted_resource  cloud_account_id=e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc
                              rows_promoted=29946  total_billed_cost=65575.879831
```

A promoção foi de grão **resource** (`cur_cost_parse_aggregated_resources`, `aggregated_rows=29946`
sobre `source_rows=30542`). Isso é **dívida do CloudPilot**, fora da allowlist desta fase: o
veredito da promoção deveria ser copiado para a resposta.

### 5.2 `/costs/unified` (duas chamadas, cache)

```json
{
  "total_cost": 139563.32,
  "by_account": [
    { "id": "e6bc24c7-9db6-4fe2-a9ba-ec32b973eacc", "name": "HOMOLOGATION AWS [sim]", "provider": "aws", "cost": 65575.88 },
    { "id": "2e5ca016-81bb-4a0a-b440-27cb2d89587f", "name": "HOMOLOGATION AZURE [conta real]", "provider": "azure", "cost": 59373.5 },
    { "id": "a666626a-6f78-4029-bba6-ed6ee262740b", "name": "HOMOLOGATION GCP [sim]", "provider": "gcp", "cost": 14613.94 }
  ],
  "data_source": "focus_cost_records",
  "is_stale": true,
  "metric_requested": "net_amortized",
  "metric_applied": "net_amortized"
}
```

`data_source: focus_cost_records` — a conta AWS **não** está mais no `cost: null` da S4b3-B.
`is_stale: true` é o **caminho frio** do endpoint (`costs.py:524`): o payload vem do ledger do
CUR em vez de uma consulta ao Cost Explorer. **Não** é cache velho — o valor confere com o ledger e
com o parquet (§5.3).

### 5.3 O volume confere nos três lugares

| Onde | Valor |
|---|---|
| parquet entregue (`2026-10-31`, `EffectiveCost` somado sobre 30.542 linhas) | **65.575,879831** |
| ledger `focus_cost_records` (conta `e6bc24c7…`, período `2026-10-01`, 29.946 linhas, `ChargePeriodStart` de `2026-10-01` a `2026-10-31`) | **65.575,88** |
| `/costs/unified` → `HOMOLOGATION AWS [sim]` | **65.575,88** |

E o porquê de o valor ter **subido** de 54.143,54 (S4b3-B) para 65.575,88: o export do dia é um
**snapshot month-to-date**. O parquet do dia `2026-10-31` cobre `ChargePeriodStart` de
`2026-10-01` a `2026-10-31` (o do dia `2026-10-26` cobria até `2026-10-26`), e o leitor de CUR lê o
**execution mais recente** (`files_read: 1`). O crescimento é o mês,andando — não uma soma de
snapshots.

## 6. O que o leitor de CUR leu (e o que ele não leu)

O leitor escolhe **um** arquivo: o `execution_id` mais recente do período
(`20261101T000000Z-eac552f3`, o do dia `2026-10-31`). As 5 chaves do bucket coexistem, mas só a
última é lida — que é o comportamento correto para export cumulativo (ler os cinco e somar
contaria o mês cinco vezes).

**Consequência declarada:** o bucket do `s3mock` contém **só as entregas de outubro**. A árvore
FOCUS/S3 do `aws-sim` (2026-01 → 2026-04), que a S4b3-A publicou no mesmo bucket, **não está lá**:
o store do `s3mock` é em memória e o container foi reiniciado (§3.2). Publicá-la de novo exigiria
`aws-up.ps1` — que re-renderiza a árvore e **replaces** o volume, ou seja, "restart dos planos",
**fora do escopo** desta fase.

Isso **não** altera a medição da janela corrente:

- o ledger ainda tem os períodos `2026-03` (80.239,58) e `2026-04` (85.964,89) da ingestão da
  S4b3-A, porque o `focus_cost_records` é persistente (Postgres com volume) e a promoção usa
  semântica de `REPLACE` **por período**;
- a janela de outubro (a que o `/costs/unified` mostra) depende só do export de outubro, que está
  no bucket.

## 7. O que a fase entregou, em uma linha

**A tarefa `simulador-nuvem-daily` está registrada no caminho atual, dispara sozinha (resultado
`0`, com a linha no `task.log`), e a suíte de testes deixou de ser capaz de apagá-la.** O ledger
está em dia com o alvo (16 dias, `2026-10-16` → `2026-10-31`) e o dia gerado chega ao consumidor
(US$ 65.575,88 em `focus_cost_records`, conferido nos três lugares).

## 8. Lacunas declaradas (o que esta fase **não** resolve)

1. **`docs/AGENDAMENTO.en.md` ficou desatualizado** — o gêmeo inglês do documento de
   agendamento continua afirmar que a tarefa não está registrada e que o ledger está em
   `2026-10-26`. Ele **não está na allowlist** desta fase (que traz `docs/AGENDAMENTO.md`), então
   o texto não foi corrigido aqui. É dívida de uma linha editorial, não de comportamento.
2. **O teste de regressão da §3.3 não foi escrito** — ele mora em
   `tools/synthetic_clouds/tests/test_schedule.py`, fora da allowlist. A correção em `windows.py`
   é verificável por medição (§3.3), mas a rede de proteção automática fica para a fase que mexer
   nos testes.
3. **A tabela de CUD não fecha a contagem** — o provisionador do BigQuery falha no check
   `cud_subscriptions_export` (`expected 3, got 9`) com o render de 2026-10-29. Superfície
   **pré-existente**, que a entrega diária não toca; as duas tabelas de billing foram criadas e
   populadas. O conserto é da fase do GCP.
4. **A resposta da ingestão não reporta a promoção** (`cost_rows_promoted`, `cost_promotion_status`
   e `cost_total_billed` são defaults do schema, nunca atribuídos). O veredito real só existe no
   log (`cur_cost_promoted_resource`). Correção do lado do CloudPilot, fora da allowlist.
5. **A árvore do `aws-sim` não voltou ao bucket** (§6) — deliberate, "restart dos planos" está
   fora do escopo; a reposição é `aws-up.ps1`.
6. **A máquina que roda a tarefa tem que estar ligada e com a conta logada** — limite conhecido já
   documentado no `AGENDAMENTO.md` (item 4 da seção de limites).

## 9. Verificação

```powershell
$ .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
92 passed, 1 warning in 15.04s
```

```powershell
$ .\.venv\Scripts\python.exe -m tools.synthetic_clouds.schedule status
$ schtasks /query /tn simulador-nuvem-daily /v /fo LIST
$ podman ps --format "table {{.Names}}\t{{.Status}}"
```

`podman ps` no fim da fase — 25 containers, todos `Up`, os planos e o CloudPilot com
`healthy`:

```
NAMES                                  STATUS
cip-api                                Up (healthy)
synthetic-clouds-azurite-1             Up (healthy)
synthetic-clouds-azure-sim-1           Up (healthy)
synthetic-clouds-s3mock-1              Up
synthetic-clouds-bigquery-emulator-1   Up (healthy)
synthetic-clouds-gcp-sim-1             Up (healthy)
synthetic-clouds-k8s-sim-1             Up (healthy)
synthetic-clouds-aws-sim-1             Up (healthy)
synthetic-clouds-tls-front             Up (healthy)
cloudpilot_postgres                    Up (healthy)
cloudpilot_redis                       Up (healthy)
cloudpilot_opa                         Up
cloudpilot_openobserve                 Up (healthy)
cloudpilot_otel_collector              Up
cloudpilot_infisical                   Up (healthy)
cloudpilot_frontend                    Up
cloudpilot_backend                     Up (healthy)
cloudpilot_celery_worker               Up (healthy)
cloudpilot-deploy-celery_worker_k8s-1  Up (healthy)
cloudpilot_celery_beat                 Up (healthy)
cloudpilot_celery_worker_drift         Up (healthy)
```
