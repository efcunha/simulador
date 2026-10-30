# Automação da integração CloudPilot ↔ simulador

> Última atualização: **2026-10-29** (revisão `9533b901`).

Esta pasta contém os scripts que reaplicam, de forma idempotente, o que **não**
sobrevive a restart/recriação de container.

| Arquivo | Papel |
|---|---|
| `cold-start.ps1` | **começo frio em um comando**: sobe a máquina podman (limpando proxy órfão), a stack CloudPilot+CIP, os planos de nuvem sintética e a integração; tolera `already running`; no fim mostra endpoints e containers (`exit 0` ok, `1` problemas, `2` a máquina não subiu) |
| `ensure-cloudpilot.ps1` | garante podman machine, containers dos emuladores, aliases DNS na rede do CloudPilot, CA confiável nos containers, folha do front (reassina com a mesma CA se o SAN estiver atrás dos aliases), janela do estate até o dia UTC atual e (com `-Smoke`) “Verificar Conexão” + `/costs/unified` (`exit 0` ok, `1` problemas, `2` podman indisponível) |
| `register-ensure-task.ps1` | registra a tarefa `CloudPilot-Simulator-Ensure` (logon + repetição a cada 30 min) via XML **por usuário**; `-RunNow` executa uma vez após registrar |
| `run-ensure.cmd` | wrapper que a tarefa agendada executa |
| `README.md` | este arquivo |

## Começo frio (após `podman machine stop` ou reboot do Windows)

`podman machine stop` derruba **todos** os containers, e **nenhum volta sozinho** quando a
máquina sobe — nem os que têm `restart=unless-stopped` (a política só vale enquanto o
serviço vive). Use o cold start:

```powershell
.\deploy\synthetic-clouds\integration\cold-start.ps1
```

A ordem interna é obrigatória: máquina → stack CloudPilot → simuladores → integração.
Os simuladores precisam da bridge `cloudpilot-deploy_cloudpilot_net` (criada pela stack
CloudPilot), e a integração é o passo que **anexa** os emuladores a ela — sem ele o
`tls-front` entra em crash-loop com `host not found in upstream "bigquery-emulator:9050"`.

Opções: `-SkipSimulators`, `-SkipIntegration`, `-SkipMachine`.

> **Três-controladores.** Neste host a máquina podman é disputada pelo GUI do Podman
> Desktop, pela tarefa agendada `CloudPilot-Simulator-Ensure` e pelo CLI. Quando dois
> iniciam ao mesmo tempo, o perdedor falha com
> `unable to start "podman-machine-default": already running` (exit 125) — **inofensivo**
> (a máquina está no ar), mas o GUI mostra um diálogo de erro vermelho. O `cold-start.ps1`
> tolera esse erro; o GUI não.

## Uso manual

```powershell
# reaplicar tudo (idempotente; não recria containers saudáveis)
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1

# incluir a verificação autenticada das 3 contas + unified
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1 -Smoke

# forçar a reconstrução do estate (custa ~1-2 min de CPU)
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1 -ForceRefresh

# não tocar na janela do estate (só aliases/CA/folha)
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1 -SkipEstate

# só problemas no console (o arquivo de log recebe tudo)
.\deploy\synthetic-clouds\integration\ensure-cloudpilot.ps1 -Quiet
```

| Script | Flag | Efeito |
|---|---|---|
| `ensure-cloudpilot.ps1` | `-Smoke` | roda "Verificar Conexão" das 3 contas e `/costs/unified` (minta um JWT curto dentro do backend; nada é lido/escrito em disco) |
| | `-ForceRefresh` | reconstrói o estate mesmo com a janela em dia |
| | `-SkipEstate` | não mexe na janela do estate |
| | `-Quiet` | console só com problemas; linhas `INFO` (inclusive o “summary OK”) vão só para o log |
| | `-LogPath` | caminho do log (padrão `%LOCALAPPDATA%\synthetic-clouds\integration.log`) |
| `cold-start.ps1` | `-SkipSimulators` | sobe só a stack CloudPilot (sem os planos Azure/GCP/AWS) |
| | `-SkipIntegration` | não roda o `ensure-cloudpilot.ps1` no fim |
| | `-SkipMachine` | assume a máquina podman já no ar |
| `register-ensure-task.ps1` | `-TaskName` | nome da tarefa (padrão `CloudPilot-Simulator-Ensure`) |
| | `-EveryMinutes` | intervalo da repetição (padrão 30; mínimo 5, máximo 1440) |
| | `-RunNow` | executa a tarefa uma vez logo após registrar |

Saída do `ensure-cloudpilot.ps1`: `0` = tudo OK; `1` = há problema (lista no fim e no log);
`2` = podman indisponível. O log fica em
`%LOCALAPPDATA%\synthetic-clouds\integration.log` por padrão.

## Agendamento

**Na leitura de 2026-10-29 a tarefa não está registrada nesta máquina** (`schtasks /Query
/TN CloudPilot-Simulator-Ensure` responde "O sistema não pode encontrar o caminho
especificado"). Registre (ou re-registre) com:

```powershell
.\deploy\synthetic-clouds\integration\register-ensure-task.ps1 -RunNow
Get-ScheduledTaskInfo -TaskName CloudPilot-Simulator-Ensure
```

O XML usa `LogonTrigger` com `<UserId>DOMAIN\user</UserId>`, `RunLevel=LeastPrivilege`,
`MultipleInstancesPolicy=IgnoreNew`, `StartWhenAvailable=true` e
`ExecutionTimeLimit=PT45M`. **É o escopo por usuário que dispensa elevação**: um logon
trigger sem `UserId` é machine-wide e responde “Acesso negado” — o mesmo motivo documentado
em `tools/synthetic_clouds/schedule/windows.py`. Se o `schtasks` recusar mesmo assim, a
mensagem do script sugere rodar de um shell elevado ou usar o fallback de pasta de
Inicialização; **este repositório não implementa esse fallback** (é decisão de deployment
com privilégio).

O gatilho é “ao logon” com `<Repetition><Interval>PT30M</Interval></Repetition>`
(indefinido enquanto o usuário estiver logado). `-RunNow` executa uma vez logo
após registrar.

Para remover: `schtasks /Delete /TN CloudPilot-Simulator-Ensure /F`.

> O `run-ensure.cmd` é um arquivo **versionado** que chama o `ensure-cloudpilot.ps1` por
> caminho absoluto desta árvore (`C:\Projetos\Simulador\...`) e passa `-Quiet`. Mover o repositório
> exige editar esse caminho no wrapper e re-registrar a tarefa (o `schtasks /Create /XML`
> aponta para o wrapper).

## O que ele **não** faz

- Não edita código, credenciais nem banco.
- Não recria containers do CloudPilot. Se detectar que falta a CA em algum
  (`REQUESTS_CA_BUNDLE`/`/certs`), ele falha e indica recriar com
  `docker-compose.local.yml`:
  `pwsh -File C:\Projetos\cloudpilot-deploy\scripts\compose-local.ps1 -Action up`
- Não rotaciona a CA. Se `gen_dev_tls.py` for reexecutado, o bundle
  `C:\Projetos\cloudpilot-deploy\.local\tls\ca-bundle.pem` precisa ser refeito e os
  containers do CloudPilot recriados.
- Não sobe a stack GCP inteira: o `bigquery-emulator` foi anexado manualmente à
  rede do CloudPilot e um `compose up` o recria sem esse vínculo. Ele garante o
  alias quando o container existe; se o container sumir, falha e aponta para a
  documentação (`docs/INTEGRACAO-CLOUDPILOT-TLS.md`).
- Não sobe os planos GCP/AWS: se `gcp-sim`, `aws-sim`, `s3mock` ou `bigquery-emulator` não
  existirem, ele reporta como problema (rode `scripts/synthetic-clouds/up.ps1`). Só o
  `azure-sim` e o `tls-front` ele recria a partir dos composes quando o container sumiu — e
  o front só depois que os aliases dos upstreams existem.

## Limite do gatilho “ao logon”

Se a máquina reiniciar sem ninguém logar, a tarefa não roda até o próximo logon
(ou o próximo disparo já agendado). Para o cenário “servidor sempre ligado sem
sessão”, registre a mesma tarefa com um gatilho de inicialização em uma conta
que tenha acesso à podman machine do usuário — isso é uma decisão de deployment
com privilégio, fora do que este script tenta fazer sozinho.
