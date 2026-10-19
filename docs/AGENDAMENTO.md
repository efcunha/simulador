# Agendamento da geração diária

> Idioma: **Português** | [English](AGENDAMENTO.en.md)

Documento operacional. Responde **como configurar o horário**, **o que acontece quando
a máquina fica desligada** e **o que ainda não está resolvido** — sem repetir o que já
está em [`ESTADO.md`](ESTADO.md).

## O problema que este documento resolve

O simulador tinha a **capacidade** de gerar dia a dia desde a FR-22: janela *month-to-date*,
determinística por `(seed, profile, currency, dia)`, e um CLI
(`python -m tools.synthetic_clouds.daily --day YYYY-MM-DD`). O que **não existia** era
qualquer coisa que o disparasse:

* nenhuma tarefa no Agendador do Windows (191 tarefas no sistema, nenhuma relacionada);
* nenhum agendador no código — nem cron, nem APScheduler;
* e a prova de que nunca rodou de verdade: `out/daily/` não existia. A única coisa sob
  `out/` eram sobras da suíte (`out/pytest-daily/pid-*`).

O CLI diário exige uma data explícita e recusa sem ela. Ou seja: motor existia, ignição
não. Este trabalho é a ignição.

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

### Por que o alvo é ontem, não hoje

`lag_days` (padrão **1**) não é folga: `clock.py` (FR-B2) documenta que uma cobrança do
dia `D` só é exportada em `D+1` às `00:00 UTC`. O dia mais recente cuja exportação está
completa na data de hoje é, portanto, **ontem**. Gerar hoje seria pedir um dia cuja
exportação ainda não existe.

O parâmetro existe para ser explícito, não para ser ajustado sem motivo.

### Idempotência: por que disparar duas vezes é inofensivo

A tarefa tem **dois gatilhos** — o diário no horário configurado e um **no logon** — mais
`StartWhenAvailable`, que faz o Agendador rodar a tarefa perdida assim que a máquina
volta. Nenhum deles precisa ser exato, porque o `tick` consulta o ledger antes de gerar:

| Situação | O que acontece |
|---|---|
| Dispara de novo no mesmo dia | `up-to-date`, nada é gerado |
| Máquina desligada por N dias | gera exatamente os dias que faltam, em ordem |
| Desligada por mais que `backfill_max_days` (padrão 31) | gera os **N mais recentes** e **avisa** quantos ficaram de fora |
| Ledger vazio (primeira execução) | gera **um dia** — o alvo. Não despeja um mês de histórico |
| Relógio andou para trás (NTP, troca de fuso) | nada é gerado; `--force` é a única porta |
| Um dia falha | os dias já concluídos **ficam registrados**; o erro vai para o log e o exit code é 1 |

A primeira execução gerar um dia só é deliberado: ledger vazio significa "nada foi
gerado", não "falta um mês". Gerar histórico é ato explícito, e o CLI diário já faz isso
com `--from/--to`.

### Retenção: por que ela existe e o que ela não faz

Medido: um dia do perfil `small` com todas as superfícies são **2.736 arquivos / 61,3 MB**.
Sem retenção isso é ~1,8 GB por mês enchendo o disco em silêncio — o modo de falha
clássico de um job desatendido.

**A instalação deste repositório roda em perfil `medium` desde 2026-10-14** (decisão em
[DECISOES-PENDENTES.md](DECISOES-PENDENTES.md#e3--volume-e-retenção-com-o-horário-novo)).
Medido no mesmo dia (`2026-10-13`, seed 123, USD, 19 superfícies): **12.006 arquivos /
281,3 MB**, 3.330 recursos, 49,4 s de build+render. O perfil não muda a janela gerada (que é
*month-to-date*, derivada do dia), e sim a **densidade de recursos**: 370 por escopo contra
79. Consequência prática: o teto da retenção é ~4,6× o do perfil `small`.

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
& $py -m tools.synthetic_clouds.schedule set --retention-days 30   # manter 30 dias
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

Se a máquina já estiver no fuso configurado, as duas leituras coincidem e não há o que
reconciliar.

> Na primeira execução de `init`, o fuso padrão é **UTC** com um aviso explícito. A
> biblioteca padrão do Python não converte o identificador do Windows
> (*E. South America Standard Time*) para um nome IANA, e o projeto **recusa adivinhar**:
> 06:30 UTC seriam 03:30 em São Paulo, e um padrão silencioso pareceria ter funcionado.

## Comandos

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'
$py = '.\.venv\Scripts\python.exe'

# 1. criar a configuração e acertar o fuso e o horário
& $py -m tools.synthetic_clouds.schedule init
& $py -m tools.synthetic_clouds.schedule set --time-zone America/Sao_Paulo --time 06:30
& $py -m tools.synthetic_clouds.schedule show

# 2. ver o que vai ser registrado, sem registrar nada
& $py -m tools.synthetic_clouds.schedule install --dry-run

# 3. registrar a tarefa  <-- este passo exige PowerShell COMO ADMINISTRADOR
& $py -m tools.synthetic_clouds.schedule install

# 4. conferir
& $py -m tools.synthetic_clouds.schedule status
```

> **O passo 3 NÃO precisa de administrador** — e a primeira versão deste documento
> dizia que precisava, o que estava errado. O registro como usuário comum funciona: foi
> assim que a tarefa deste projeto entrou no ar.
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
# gera o dia devido agora (ontem, se lag_days=1)
& $py -m tools.synthetic_clouds.schedule tick

# gera um dia específico, fora de ordem
& $py -m tools.synthetic_clouds.schedule tick --date 2026-03-18

# refaz o dia alvo mesmo que já conste no ledger
& $py -m tools.synthetic_clouds.schedule tick --force

# remover a tarefa
& $py -m tools.synthetic_clouds.schedule uninstall
```

### Campos da configuração

| Campo | Padrão | O que faz |
|---|---|---|
| `time` | `06:30` | horário **no fuso de `time_zone`** |
| `time_zone` | `UTC` (com aviso) | nome IANA, ex.: `America/Sao_Paulo` |
| `seed` | `123` | semente do gerador |
| `profile` | `small` | `small` / `medium` / `large`. **Aqui está `medium`** desde 2026-10-14 — 281,3 MB/dia contra 61,3 MB do `small`. |
| `currency` | `USD` | `USD` / `BRL` |
| `lag_days` | `1` | atraso do export (FR-B2) |
| `backfill_max_days` | `31` | teto de dias recuperados numa execução |
| `retention_days` | `null` (guarda tudo) | quantos dias manter; os mais antigos são apagados |
| `renderers` | `null` (todas) | lista de superfícies, ou `null` para todas |
| `enabled` | `true` | desliga a geração sem remover a tarefa |

Uma chave desconhecida é **recusada**, não ignorada: `"hour": "07:00"` ao lado de `time`
faria o job rodar na hora padrão enquanto o arquivo afirma outra coisa.

## Onde ficam os arquivos

Tudo sob `tools/synthetic_clouds/` — a fronteira de escrita do projeto (NFR-4). O `tick`
do CLI recusa caminho fora dela, e `save_config` também.

| Caminho | O que é |
|---|---|
| `schedule/config.json` | a configuração (hoje: perfil `medium`, 12:00 `America/Sao_Paulo`, retenção 30) |
| `schedule/run-daily.cmd` | o wrapper que a tarefa executa (gerado; não editar à mão) |
| `schedule/<tarefa>.xml` | a definição da tarefa em XML (gerado) |
| `out/daily/<YYYY-MM-DD>/<seed>-<profile>-<currency>/{canonical,render}/` | os artefatos do dia |
| `out/daily/_state/state.json` | o ledger |
| `out/daily/_state/runs.log` | uma linha JSON por `tick` |
| `out/daily/_state/task.log` | stdout/stderr do processo disparado pelo Windows |

`state.json` e os logs carregam instantes de relógio, e isso é deliberado: são registros
**operacionais**, não artefatos. Nada escrito neles chega a um Parquet ou a um JSON de
export — os artefatos continuam byte-determinísticos (há teste que prova: regerar o mesmo
dia com `--force` reproduz os mesmos hashes).

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

Verificado no registro real deste projeto: `Hora da próxima execução: 15/10/2026
06:30:00`, `Último resultado: 0`, e o gatilho diário **disparou sozinho** num teste com
horário antecipado (`runs.log` registrou o instante exato).

## Limites conhecidos — o que este trabalho NÃO resolve

Vale ser explícito, para o documento não prometer mais do que entrega:

1. **A entrega ao FinOps continua pendente.** Os artefatos nascem dentro de
   `tools/synthetic_clouds/out/daily/`. Nada é publicado em bucket, MinIO ou qualquer
   lugar que o FinOps leia: não há `boto3`, `minio` nem upload no pacote, e a ponte
   que escrevia no banco do produto (`seed/`) foi deliberadamente deixada de fora. Fazer
   a entrega é a frente **C** — e depende de fechar os pontos de ingestão do outro lado.
2. **10 das 21 superfícies não têm ponto de ingestão identificado** em
   `<doc-de-ingestao>.md`. Gerar todo dia não faz essas
   chegarem a lugar nenhum enquanto isso não for resolvido do lado do FinOps.
3. **Cobertura de serviços é a frente B.** O agendador gera as 20 superfícies que existem;
   ele não cria superfície nova. EKS/GKE/AKS e boa parte dos serviços de GCP e Azure
   continuam sem artefato próprio — aparecem só como linha de custo.
4. **Uma tarefa agendada só roda com o usuário logado** (ou com a máquina ligada, no caso
   do gatilho de logon). Um servidor desligado não gera — e é por isso que o backfill
   existe.
5. **A retenção é opt-in, e o padrão é guardar tudo.** `retention_days` começa em
   `null`. Medido: um dia do perfil `small` com todas as superfícies são **2.736
   arquivos / 61,3 MB** em **12,3 s**; um dia do perfil `medium` são **12.006 arquivos /
   281,3 MB** em **49,4 s**. A instalação feita aqui ficou com **30 dias** — mas esse
   número foi escolhido quando o perfil era `small`, e **`medium` com 30 dias pede ~17 GB**
   (janelas *month-to-date* de 13 a 31 dias, média ~24–26). Na leitura de 2026-10-14T17:54,
   **`D:` tem 26,67 GB livres** — o teto de ~17 GB cabe (na leitura da manhã eram 12,10 GB, e
   não cabia) —, e a decisão de 2026-10-14 foi **manter os 30 dias por ora, com revisão
   marcada** para quando a ocupação acumulada se aproximar do livre: o risco é declarado, não
   silencioso. `large` está fora de questão neste disco (~4× o `medium`).

## Verificação

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests\test_schedule.py -q
```

A suíte do agendador cobre: configuração inválida (hora, fuso, chave desconhecida, seed
booleano), a fronteira de escrita, o ledger (versão, JSON corrompido, chave que não é
data), o plano de backfill (primeira execução, em dia, buraco, teto, relógio para trás,
dia explícito), o `tick` com gerador injetado (idempotência, backfill, falha no meio,
desabilitado, log), o registro no Windows (wrapper, XML, conversão de horário, virada
para o dia seguinte) e o CLI ponta a ponta **com renderização real** — incluindo o teste
que prova que um `--force` reproduz os mesmos bytes.
