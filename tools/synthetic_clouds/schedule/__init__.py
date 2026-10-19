"""Scheduled daily generation: the clock, the config, the ledger and the Windows task.

O gerador diário existia e nada o disparava — esta é a peça que faltava. Quatro
módulos, cada um com uma responsabilidade:

* :mod:`config`  — **quando** rodar e **com o quê** (hora, fuso, seed, profile, moeda,
  superfícies). Falha fechada: configuração que não se entende é recusada na leitura.
* :mod:`state`   — o livro-caixa do que já foi gerado. É o que dá idempotência.
* :mod:`runner`  — o ``tick``: decide qual dia é devido, gera, registra. É o único
  lugar do projeto que consulta o relógio de parede.
* :mod:`windows` — o registro no Agendador de Tarefas, para o disparo ser do sistema
  operacional e não de um processo que precisa ficar vivo.

O horário configurado é interpretado no fuso de ``time_zone``; a tarefa do Windows é
escrita no horário local da máquina, porque é só isso que o Agendador entende. Quem
reconcilia os dois é a idempotência do ``tick``: disparar duas vezes não gera duas
vezes, e disparar atrasado gera exatamente os dias que faltam.
"""

from __future__ import annotations

from tools.synthetic_clouds.schedule.config import (
    CONFIG_PATH,
    ConfigError,
    ScheduleConfig,
    load_config,
    save_config,
)
from tools.synthetic_clouds.schedule.runner import (
    DEFAULT_LOG_NAME,
    TickError,
    TickPlan,
    TickResult,
    plan_backfill,
    target_day_for,
    tick,
)
from tools.synthetic_clouds.schedule.state import (
    STATE_PATH,
    RunState,
    StateError,
    load_state,
    save_state,
)

__all__ = [
    "CONFIG_PATH",
    "DEFAULT_LOG_NAME",
    "STATE_PATH",
    "ConfigError",
    "RunState",
    "ScheduleConfig",
    "StateError",
    "TickError",
    "TickPlan",
    "TickResult",
    "load_config",
    "load_state",
    "plan_backfill",
    "save_config",
    "save_state",
    "target_day_for",
    "tick",
]
