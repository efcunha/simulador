# Agendamento da geração diária

> Idioma: **Português** | [English](AGENDAMENTO.en.md)
>
> Última atualização: **2026-10-29** (revisão `9533b901`, branch
> `feat/p76-security-posture-gcp-azure`).

Documento operacional. Responde **como configurar o horário**, **o que acontece quando
a máquina fica desligada** e **o que ainda não está resolvido** — sem repetir o que já
está em [`ESTADO.md`](ESTADO.md).

Nos blocos de comando abaixo:

```powershell
cd <raiz-do-repo>
$py = '.\.venv\Scripts\python.exe'
```

`python -m tools.synthetic_clouds…` acha o pacote pelo próprio diretório de trabalho:
**não é preciso `PYTHONPATH`** para nada deste documento. (O wrapper da tarefa o define
porque o Agendador pode iniciar o processo em outro diretório — ver
[O que a tarefa do Windows faz](#o-que-a-tarefa-do-windows-faz).)

## O problema que este documento resolve

O simulador tinha a **capacidade** de gerar dia a dia desde a FR-22: janela *month-to-date*,
determinística por `(seed, profile, currency, dia)`, e um CLI
(`python -m tools.synthetic_clouds.daily --day YYYY-MM-DD`). O que **não existia** era
qualquer coisa que o disparasse (situação medida em 2026-10-14, quando o agendador foi
escrito):

* nenhuma tarefa no Agendador do Windows (situação medida em 2026-10-14: nenhuma tarefa
  relacionada no sistema);
* nenhum agendador no código — nem cron, nem APScheduler;
* e a prova de que nunca rodou de verdade: `out/daily/` não existia. A única coisa sob
  `out/` eram sobras da suíte (`out/pytest-daily/pid-*`).

O CLI diário exige uma data explícita (`--day`, ou `--from`/`--to`) e recusa sem ela. Ou
seja: motor existia, ignição não. Este trabalho é a ignição.

## Como funciona

```
config.json  ──►  tick  ──►  run_days(dia)  ──►  out/daily/<dia>/...
   (hora,          │                                  ▲
    fuso, seed)     └──►  state.json  (ledger)  ───────┘
                          registra o dia concluído
```

Quatro módulos em `tools/synthetic_clouds/schedule/`:

| Módulo | Responsabilidade |
|---|---|
| `config.py` | **quando** rodar e **com o quê**. Falha fechada: configuração que não se entende é recusada na leitura. |
| `state.py` | o ledger do que já foi gerado. É o que dá idempotência. |
| `runner.py` | o `tick`. **Único lugar do projeto que consulta o relógio de parede.** |
| `windows.py` | o registro no Agendador, para o disparo ser do sistema operacional. |

`daily/` continua sem ler relógio nenhum — é isso que torna um dia reproduzível. Quem
pergunta "que horas são" é o `runner`, e ele converte a resposta numa **data explícita**
antes de entregar ao gerador.

## Dois níveis de configuração: o padrão de fábrica e esta instalação

Confundir os dois é o erro que faz um operador "corrigir" o código quando queria mudar a
instalação — ou aceitar um default achando que é a escolha deste repositório.

* **Padrão de fábrica** é o que `config.py` usa quando não há configuração: o que um
  `schedule init` num checkout limpo escreve. Vale como referência e como piso de
  validação, não como o estado desta máquina.
* **Configuração desta instalação** é `tools/synthetic_clouds/schedule/config.json`,
  **versionado** neste repositório. É ele que a tarefa agendada lê.

Leitura de 2026-10-29 (`schedule show`):

```text
enabled              True
time                 12:00
time_zone            America/Sao_Paulo
lag_days             0
backfill_max_days    31
retention_days       30
seed                 123
profile              medium
currency             USD
renderers            None
```

A tabela de campos, com as duas colunas, está em
[Campos da configuração](#campos-da-configuração).

### O alvo: por que o padrão é ontem e por que esta instalação gera hoje

`lag_days` **não é folga**. `clock.py` (FR-B2) documenta que uma cobrança do dia `D` só é
exportada em `D+1` às `00:00 UTC`; por isso o **padrão de fábrica** de `config.py` é
`lag_days = 1` e o alvo de um tick é ontem. Gerar hoje, no modelo do FR-B2, seria pedir um
dia cuja exportação ainda não existe.

**Esta instalação roda com `lag_days = 0` desde 2026-10-26** (commit `1f674563`). O motivo
está na mensagem do commit:

* o dashboard de demonstração precisa fechar em **"hoje"** — com lag 1, no dia 27 o alvo é
  26 e o próprio 27 só nasce no 28;
* o simulador gera **dias completos e determinísticos** e a entrega aos emuladores é
  imediata, então não existe export parcial a esperar;
* o atraso deixou de ser buraco de qualquer forma desde o backfill por watermark do lado do
  consumidor (`AZURE_FOCUS_INGEST_MAX_BACKFILL_DAYS`): se a máquina ficar dias parada, o
  leitor volta até o último dia armazenado.

Ou seja: o FR-B2 continua verdadeiro como **regra do dado que se emula**, mas ele não
obriga o simulador a entregar ontem. Para voltar ao comportamento do FR-B2:

```powershell
& $py -m tools.synthetic_clouds.schedule set --lag-days 1
```

O parâmetro existe para ser explícito — a diferença entre o padrão e a instalação é uma
decisão registrada, não um ajuste silencioso.

### Idempotência: por que disparar duas vezes é inofensivo

A tarefa tem **dois gatilhos** — o diário no horário configurado e um **no logon** — mais
`StartWhenAvailable`, que faz o Agendador rodar a tarefa perdida assim que a máquina
volta. Nenhum deles precisa ser exato, porque o `tick` consulta o ledger antes de gerar:

| Situação | O que acontece |
|---|---|
| Dispara de novo no mesmo dia | `up-to-date`, nada é gerado |
| Máquina desligada por N dias | gera exatamente os dias que faltam, em ordem |
| Desligada por mais que `backfill_max_days` (padrão 31) | gera os **N mais recentes** e **avisa** quantos ficaram de fora |
| Ledger vazio (primeira execução) | gera **um dia** — o alvo (hoje, com `lag_days=0`; ontem, com o padrão) |
| Relógio andou para trás (NTP, troca de fuso) | nada é gerado; `--force` é a única porta |
| Um dia falha | os dias já concluídos **ficam registrados**; o erro vai para o log e o exit code é 1 |

A primeira execução gerar um dia só é deliberado: ledger vazio significa "nada foi
gerado", não "falta um mês". Gerar histórico é ato explícito, e o CLI diário já faz isso
com `--from/--to`.

### Retenção: por que ela existe e o que ela não faz

Medição **histórica, não o estado atual** (2026-10-13/14, seed 123, USD, **19 superfícies**
— antes da expansão para as 49 superfícies atuais): um dia do perfil `small` com todas as
superfícies então existentes eram **2.736 arquivos / 61,3 MB**, em 12,3 s. Sem retenção
isso é ~1,8 GB por mês enchendo o disco em silêncio — o modo de falha clássico de um job
desatendido. O número de hoje é maior (mais superfícies); a decisão de retenção não mudou
por causa disso.

**A instalação deste repositório roda em perfil `medium` desde 2026-10-14** (decisão em
[DECISOES-PENDENTES.md](DECISOES-PENDENTES.md#e3--volume-e-retenção-com-o-horário-novo))
e com `retention_days = 30`. Medido no mesmo dia (2026-10-13, seed 123, USD, 19
superfícies): **12.006 arquivos / 281,3 MB**, 3.330 recursos, 49,4 s de build+render. O
perfil não muda a janela gerada (que é *month-to-date*, derivada do dia), e sim a
**densidade de recursos**: 370 por escopo contra 79. Consequência prática: o teto da
retenção é ~4,6× o do perfil `small`.

`retention_days = N` mantém os **N dias mais recentes terminando no dia alvo** e apaga os
mais antigos. A poda roda em **todo** tick, inclusive nos que não têm nada a gerar: uma
máquina sempre em dia nunca podaria se a poda só acontecesse junto com uma geração.

O ponto delicado é o ledger. Um dia apagado é **removido do ledger**, não mantido como
"completo": `is_complete` não pode responder "sim" para um dia cujo artefato não existe —
seria a mesma mentira em sentido contrário. E o dia não volta:

* o backfill só preenche o buraco **depois** do dia mais recente conhecido, então um dia
  antigo podado nunca é regenerado;
* se a poda falhar (arquivo em uso), o dia **fica no ledger** e o erro é relatado — o
  status da execução continua sendo o da geração, porque falha de limpeza não é falha de
  dado.

```powershell
& $py -m tools.synthetic_clouds.schedule set --retention-days 30   # manter 30 dias (estado atual)
& $py -m tools.synthetic_clouds.schedule set --retention-days none # voltar a guardar tudo
```

### Fuso horário: o configurado e o da máquina

São duas coisas diferentes, e confundi-las é o erro clássico:

* `time_zone` decide **a qual dia** uma execução pertence (o dia vira no fuso configurado);
* o Agendador do Windows só entende **hora local da máquina**, então é nessa hora que a
  tarefa é escrita.

O `install` mostra as duas leituras e **avisa** quando os offsets divergem. Se
divergirem, quem garante o dia certo é a idempotência do `tick`, não uma coincidência de
fuso.

Nesta instalação o fuso configurado é `America/Sao_Paulo`, que coincide com o fuso da
máquina — nesse caso as duas leituras coincidem e o aviso de offset divergente não
dispara.

> Na primeira execução de `init`, o fuso gravado é o **da máquina**; quando o identificador
> do Windows (*E. South America Standard Time*) não converte para um nome IANA, o projeto
> **recusa adivinhar** e cai em **UTC com um aviso explícito** — 06:30 UTC seriam 03:30 em
> São Paulo, e um padrão silencioso pareceria ter funcionado.

## Comandos

```powershell
# 1. configuração. Neste checkout o config.json JÁ EXISTE e é versionado, e o `init`
#    recusa sobrescrever ("already exists; use `set` ..."). A reprodução da config atual
#    desta instalação é o `set` abaixo. Num checkout sem config.json, rode `init` antes.
& $py -m tools.synthetic_clouds.schedule set `
    --profile medium --time-zone America/Sao_Paulo --time 12:00 `
    --lag-days 0 --retention-days 30
& $py -m tools.synthetic_clouds.schedule show

# 2. ver o que vai ser registrado, sem registrar nada
& $py -m tools.synthetic_clouds.schedule install --dry-run

# 3. registrar a tarefa (não precisa de administrador — ver nota abaixo)
& $py -m tools.synthetic_clouds.schedule install

# 4. conferir
& $py -m tools.synthetic_clouds.schedule status
```

> **O passo 3 NÃO precisa de administrador** — e a primeira versão deste documento
> dizia que precisava, o que estava errado. O registro como usuário comum funciona: foi
> assim que a tarefa deste projeto entrou no ar em 2026-10-15.
>
> A confusão nasceu de um defeito real no XML. Um `<LogonTrigger>` **sem** `<UserId>` é
> um gatilho de **abrangência total** — dispararia quando *qualquer* conta entrasse — e
> registrar isso é operação administrativa. O `schtasks` respondia "Acesso negado" e o
> sintoma apontava para privilégio, quando o problema era o XML pedir demais. Limitar o
> gatilho à conta (`<UserId>` no `LogonTrigger` e no `Principal`) torna o registro uma
> operação comum de usuário. Hoje `task_xml` **exige** o `user_id`: a variante de
> máquina inteira não pode mais ser construída por omissão.
>
> Se um registro for negado, a mensagem nomeia essa causa em vez de mandar você caçar
> um privilégio que talvez não falte.

`tick` é o que a tarefa executa. Rodá-lo à mão é a forma de testar sem esperar o horário:

```powershell
# gera o dia devido agora (hoje, com lag_days=0 nesta instalação; ontem no padrão de fábrica)
& $py -m tools.synthetic_clouds.schedule tick

# gera um dia específico, fora de ordem
& $py -m tools.synthetic_clouds.schedule tick --date 2026-03-18

# refaz o dia alvo mesmo que já conste no ledger
& $py -m tools.synthetic_clouds.schedule tick --force

# remover a tarefa
& $py -m tools.synthetic_clouds.schedule uninstall
```

### Campos da configuração

`config.py` define o padrão de fábrica; `config.json` (versionado) traz a escolha desta
instalação. As duas colunas são medidas, não estimadas.

| Campo | Padrão de fábrica (`config.py`) | Nesta instalação (`config.json`) | O que faz |
|---|---|---|---|
| `time` | `06:30` | `12:00` | horário **no fuso de `time_zone`** |
| `time_zone` | fuso da máquina; `UTC` **com aviso** quando não resolve | `America/Sao_Paulo` | nome IANA, ex.: `America/Sao_Paulo` |
| `seed` | `123` | `123` | semente do gerador |
| `profile` | `small` | `medium` | `small` / `medium` / `large`. A densidade do `medium` é ~4,6× a do `small` em volume. |
| `currency` | `USD` | `USD` | `USD` / `BRL` |
| `lag_days` | `1` (FR-B2) | `0` (desde 2026-10-26, `1f674563`) | atraso do export; ver [O alvo](#o-alvo-por-que-o-padrão-é-ontem-e-por-que-esta-instalação-gera-hoje) |
| `backfill_max_days` | `31` | `31` | teto de dias recuperados numa execução |
| `retention_days` | `null` (guarda tudo) | `30` | quantos dias manter; os mais antigos são apagados |
| `renderers` | `null` (todas) | `null` (todas) | lista de superfícies, ou `null` para todas |
| `enabled` | `true` | `true` | desliga a geração sem remover a tarefa |

Uma chave desconhecida é **recusada**, não ignorada: `"hour": "07:00"` ao lado de `time`
faria o job rodar na hora padrão enquanto o arquivo afirma outra coisa.

## Onde ficam os arquivos

Tudo sob `tools/synthetic_clouds/` — a fronteira de escrita do projeto (NFR-4). O `tick`
do CLI recusa caminho fora dela, e `save_config` também.

| Caminho | O que é |
|---|---|
| `schedule/config.json` | a configuração — **versionada**; hoje: perfil `medium`, 12:00 `America/Sao_Paulo`, lag 0, retenção 30 |
| `schedule/run-daily.cmd` | o wrapper que a tarefa executa (gerado por `install`; git-ignored; não editar à mão) |
| `schedule/<tarefa>.xml` | a definição da tarefa em XML (gerada; git-ignored) |
| `out/daily/<YYYY-MM-DD>/<seed>-<profile>-<currency>/{canonical,render}/` | os artefatos do dia |
| `out/daily/_state/state.json` | o ledger |
| `out/daily/_state/runs.log` | uma linha JSON por `tick` |
| `out/daily/_state/task.log` | stdout/stderr do processo disparado pelo Windows |

`state.json` e os logs carregam instantes de relógio, e isso é deliberado: são registros
**operacionais**, não artefatos. Nada escrito neles chega a um Parquet ou a um JSON de
export — os artefatos continuam byte-determinísticos (há teste que prova: regerar o mesmo
dia com `--force` reproduz os mesmos hashes).

## Estado desta instalação (leitura de 2026-10-29)

`schedule status` é a forma barata de responder "o que está acontecendo". Nesta leitura:

| Item | Leitura |
|---|---|
| configuração | `medium`, 12:00 `America/Sao_Paulo`, `lag_days=0`, retenção 30 (ver acima) |
| ledger | **11 dias** gerados, de `2026-10-16` a `2026-10-26`; último registro `2026-10-26T19:42:27.502954-03:00` (`up-to-date`) |
| alvo agora | `2026-10-29` |
| tarefa do Windows | **não registrada** (`simulador-nuvem-daily` não aparece para o `schtasks`) |

A consequência é direta: o ledger está 3 dias atrás do alvo (faltam 27, 28 e 29) e um
`tick` agora geraria exatamente esses três. O XML gerado em `schedule/simulador-nuvem-daily.xml`
(leitura: `StartBoundary 2026-10-27T12:00:00`, dois gatilhos, conta do usuário) existe,
mas o wrapper `schedule/run-daily.cmd` que ele referencia não está na árvore — **rodar
`install` de novo reescreve os dois arquivos e registra a tarefa**. Até isso acontecer,
nada dispara sozinho; o backfill só acontece quando alguém roda o `tick`.

## Entrega aos emuladores (`--deliver`)

O `tick` da tarefa roda com `--deliver` (é o que `render_wrapper` escreve no
`run-daily.cmd`): depois de gerar o dia, ele entrega o dia aos emuladores que o CloudPilot
lê pelos **conectores de produção** (S3/CUR, BigQuery billing export e Cost Management).
Sem essa etapa o dia existe só em disco.

| Alvo | O que faz | Endpoint padrão |
|---|---|---|
| `aws` | sobe o FOCUS 1.2 para o S3 em `<prefix>/<export_name>/data/billing_period=YYYY-MM/<execution>/...` | `http://localhost:9090` |
| `gcp` | apaga as linhas do dia e insere as do render (`insertAll`) nas tabelas de billing | `http://localhost:9050` |
| `azure` | estende a janela do estate do `azure-sim` até o dia **ou até o dia UTC atual, o que for maior** (`POST /admin/estate/refresh`) | `http://localhost:8080` |

**O namespace do alvo `aws` é o nome que o renderer emite.** O bucket e o segmento de export
publicados são `synthetic-focus12-daily-full` — o mesmo que o `render/focus_aws.py` fixa em
`EXPORT_NAME` e o mesmo que o leitor de CUR do CloudPilot tem configurado
(`cur_config.s3_bucket` / `cur_config.export_name`). A entrega **não** usa um nome próprio: um
export publicado num nome que o consumidor não lê **não é uma entrega parcial, é uma entrega
silenciosa** — os objetos sobem, a ingestão reporta `status: ok` e o dia não chega a lugar
nenhum. Foi exatamente o que a S4b3-B mediu e corrigiu (o default da entrega era
`cloudpilot-focus12-daily-full`, o nome do renderer **anterior** ao *standalone publish*).

```powershell
# entregar um dia já gerado (sem gerar de novo)
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23

# um alvo só
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23 --targets aws,gcp
```

A entrega é **idempotente por dia**: o GCP apaga o dia antes de inserir (então um
`tick --force` não duplica linhas), o AWS sobrescreve as mesmas chaves e o Azure recria a
mesma janela determinística. Endpoints, bucket e nome do export podem ser trocados por
variáveis `DELIVERY_TARGETS` (alvos padrão), `DELIVERY_AWS_ENDPOINT`,
`DELIVERY_AWS_BUCKET`, `DELIVERY_AWS_PREFIX`, `DELIVERY_AWS_EXPORT_NAME`,
`DELIVERY_GCP_ENDPOINT`, `DELIVERY_GCP_PROJECT`, `DELIVERY_GCP_DATASET`,
`DELIVERY_AZURE_ENDPOINT`.

**Duas entradas, duas leituras de namespace.** O CLI (`deliver`) lê essas variáveis; a tarefa do
Windows (`tick --deliver`) **não** — `schedule/__main__.py` chama `deliver_day()` sem argumento
de namespace, então valem os defaults do código (`deliver/core.py`: `DEFAULT_AWS_BUCKET` /
`DEFAULT_AWS_EXPORT_NAME`). Trocar `DELIVERY_AWS_BUCKET` no ambiente afeta **só** o CLI.

Falha de entrega **não desfaz** o dia no ledger (o dado foi gerado e registrado), mas
o `tick` sai com código 1 e o erro vai para o `task.log` — a tarefa aparece como
falha em vez de silenciar uma entrega que não aconteceu.

## O que a tarefa do Windows faz

| Item | Valor |
|---|---|
| nome | `simulador-nuvem-daily` (`--task-name` troca) |
| conta | a que registrou (`DOMAIN\user`), com `InteractiveToken` e privilégio mínimo |
| gatilhos | diário no horário configurado **+** no logon **daquela conta** |
| atraso perdido | `StartWhenAvailable=true` |
| instâncias simultâneas | `IgnoreNew` (dois `tick` concorrentes não se atropelam) |
| limite de execução | 4 h |
| energia | roda em bateria e não para ao mudar para bateria |

Na execução real de 2026-10-15, com a tarefa registrada, a leitura do Agendador mostrou
`Hora da próxima execução: 15/10/2026 06:30:00`, `Último resultado: 0`, e o gatilho
diário **disparou sozinho** num teste com horário antecipado (`runs.log` registrou o
instante exato). **Aquilo é histórico**: desde então o horário mudou para 12:00 (para
casar com a janela de entrega) e, na leitura de 2026-10-29, a tarefa **não está
registrada** nesta árvore — ver [Estado desta instalação](#estado-desta-instalação-leitura-de-2026-10-29).

## Limites conhecidos — o que este trabalho NÃO resolve

Vale ser explícito, para o documento não prometer mais do que entrega:

1. **A entrega aos emuladores existe; a ingestão do lado do FinOps continua pendente.**
   A tarefa roda com `--deliver` e publica o dia no S3 (endpoint `localhost:9090`, o
   `s3mock` desta pilha), no BigQuery e no Cost Management (ver
   [Entrega aos emuladores](#entrega-aos-emuladores---deliver)).
   Os emuladores são a **ponta do simulador**, não o consumidor: como o FinOps ingere cada
   domínio está em [`INGESTAO-D3-SEGURANCA.md`](INGESTAO-D3-SEGURANCA.md) (domínio D3) e
   o estado geral em [`ESTADO.md`](ESTADO.md); a ponte que escrevia no banco do produto
   (`seed/`) foi deliberadamente deixada de fora. Fazer a ingestão é a frente **C**.
2. **Cobertura: 49 superfícies especificadas, 47 geradas e 2 bloqueadas pela
   documentação** (leitura de 2026-10-29, `fidelity --matrix` →
   `gerado=47 falta=0 bloqueado=2 total=49`). As bloqueadas são
   `azure/cost-management-export-cost-details` (a Microsoft publica nomes sem tipos) e
   `gcp/container-clusters` (é **resposta de API** servida ao vivo pelo `gcp-sim`, não
   arquivo de export — não há renderer que produza artefato conferível contra a spec, e
   sem renderer dizer "implemented" seria mentira). O agendador gera o que existe; ele
   **não cria superfície nova**.
3. **Serviços sem artefato próprio: essa é a frente B.** EKS e AKS não têm superfície de
   export — são **APIs servidas ao vivo** pelos emuladores (`aws-sim` para EKS/EC2/S3/…,
   `azure-sim` para ARM/ContainerService/…). GKE tem a superfície
   `gcp/container-clusters`, mas ela está **bloqueada** justamente por ser resposta de API
   (`container.googleapis.com`, servida pelo `gcp-sim`), não export. Boa parte dos demais
   serviços de GCP e Azure idem: aparecem na descoberta e na linha de custo, não como
   arquivo de export.
4. **Uma tarefa agendada só roda com o usuário logado** (ou com a máquina ligada, no caso
   do gatilho de logon). Um servidor desligado não gera — e é por isso que o backfill
   existe.
5. **A retenção é opt-in no código, e esta instalação optou por 30 dias.**
   `retention_days` começa em `null` (guarda tudo). As medições de volume acima são
   **históricas** (2026-10-13/14, 19 superfícies): hoje há mais superfícies, então o
   número por dia é maior. A conta de ~17 GB para `medium` com 30 dias foi feita sobre
   aquela medição e continua sendo a referência da decisão. A decisão de 2026-10-14 foi
   **manter os 30 dias por ora, com revisão marcada** para quando a ocupação acumulada se
   aproximar do livre. Leitura de 2026-10-29: **`D:` tem ~30,0 GB livres**
   (32.264.364.032 bytes) — o teto estimado cabe. `large` está fora de questão neste
   disco (~4× o `medium`). O risco é declarado, não silencioso.

## Verificação

```powershell
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
```

A suíte do agendador cobre: configuração inválida (hora, fuso, chave desconhecida, seed
booleano), a fronteira de escrita, o ledger (versão, JSON corrompido, chave que não é
data), o plano de backfill (primeira execução, em dia, buraco, teto, relógio para trás,
dia explícito), o `tick` com gerador injetado (idempotência, backfill, falha no meio,
desabilitado, log), o registro no Windows (wrapper, XML, conversão de horário, virada
para o dia seguinte) e o CLI ponta a ponta **com renderização real** — incluindo o teste
que prova que um `--force` reproduz os mesmos bytes.
