"""CLI: ``python -m tools.synthetic_clouds.schedule <comando>``.

Comandos, e o que cada um responde:

* ``init``      — cria a configuração padrão (06:30 no fuso da máquina, seed 123, small).
* ``show``      — a configuração efetiva, já validada.
* ``set``       — muda um ou mais campos, revalidando o resultado inteiro.
* ``tick``      — gera os dias devidos. **É isto que a tarefa agendada executa.**
* ``status``    — configuração, o que já foi gerado, e o que o Windows tem registrado.
* ``install``   — gera o wrapper e registra a tarefa no Agendador do Windows.
* ``uninstall`` — remove a tarefa.

O horário configurado é interpretado no fuso de ``time_zone``; a tarefa do Windows é
escrita no horário local da máquina, porque é só isso que o Agendador entende. Quem
reconcilia os dois é a idempotência do ``tick``, não uma coincidência de fuso.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from tools.synthetic_clouds.schedule import windows
from tools.synthetic_clouds.schedule.config import (
    CONFIG_PATH,
    ConfigError,
    ScheduleConfig,
    guard_within_package,
    load_config,
    save_config,
)
from tools.synthetic_clouds.schedule.runner import (
    DEFAULT_LOG_NAME,
    TickError,
    plan_target_day,
    tick,
)
from tools.synthetic_clouds.schedule.state import STATE_PATH, StateError, load_state

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _REPO_ROOT / "tools" / "synthetic_clouds"


class CliError(Exception):
    """Raised for fatal CLI errors, surfaced as a non-zero exit."""


def _format_offset(offset: timedelta | None) -> str:
    """Render a UTC offset as ``+HH:MM``/``-HH:MM``.

    ``str(timedelta)`` prints a negative offset as ``-1 day, 21:00:00``, which is
    correct and unreadable. An operator comparing two zones needs to see ``-03:00``.
    """
    if offset is None:
        return "?"
    total = int(offset.total_seconds())
    sign = "-" if total < 0 else "+"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{total % 3600 // 60:02d}"


def _flag_text(value: bool | None) -> str:
    """Render a tri-state flag without turning "unknown" into "yes"."""
    if value is None:
        return "nao informado pelo Windows"
    return "sim" if value else "NAO"


def _parse_now(raw: str | None, config: ScheduleConfig) -> datetime:
    """Parse ``--now``; a naive value is read in the configured zone.

    Refusing to guess would be better than a wrong guess, but a bare ``2026-10-14T06:30``
    is unambiguous *as the operator's own configured time*, and that is the zone the
    schedule is written in. An aware value is honoured as given.
    """
    if raw is None:
        return datetime.now(tz=config.zone())
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CliError(f"--now expects an ISO instant, got {raw!r}") from exc
    if moment.tzinfo is None:
        return moment.replace(tzinfo=config.zone())
    return moment


def _load(args: argparse.Namespace, *, validate_renderers: bool = False) -> ScheduleConfig:
    """Load and validate the schedule.

    The renderer check is opt-in because discovering renderers imports pandas, pyarrow
    and every renderer module: ``show`` and ``status`` must stay cheap enough to run
    from a shell prompt, while ``set`` and ``tick`` genuinely need to know that the
    names exist.
    """
    config = load_config(args.config)
    if validate_renderers:
        from tools.synthetic_clouds.render.base import registered_names

        config.validate_renderers(registered_names())
    return config


def _cmd_init(args: argparse.Namespace) -> int:
    target = CONFIG_PATH if args.config is None else args.config
    if target.exists():
        raise CliError(f"{target} already exists; use `set` to change it or delete it on purpose")
    config = ScheduleConfig.default()
    written = save_config(config, target)
    print(f"ok: wrote {written}")
    print(f"    time={config.time_text} time_zone={config.time_zone}")
    offset = datetime.now().astimezone().utcoffset()
    if config.time_zone == "UTC" and offset is not None and offset != timedelta(0):
        # Standard library cannot map a Windows zone id ("E. South America Standard
        # Time") to an IANA name, so the fallback is UTC. Saying so loudly matters:
        # 06:30 UTC is 03:30 in Sao Paulo, and a silent default would look like it
        # worked while generating on the wrong day boundary.
        print(
            f"    ATENCAO: nao consegui detectar o fuso IANA da maquina (offset local {_format_offset(offset)});\n"
            f"    gravei UTC. Rode `set --time-zone <IANA>` (ex.: America/Sao_Paulo) antes de instalar."
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    config = _load(args)
    for key, value in config.to_document().items():
        print(f"{key:20} {value}")
    return 0


def _cmd_set(args: argparse.Namespace) -> int:
    config = _load(args, validate_renderers=True)
    changes: dict[str, object] = {}
    if args.time is not None:
        changes["time"] = args.time
    if args.time_zone is not None:
        changes["time_zone"] = args.time_zone
    if args.seed is not None:
        changes["seed"] = args.seed
    if args.profile is not None:
        changes["profile"] = args.profile
    if args.currency is not None:
        changes["currency"] = args.currency
    if args.lag_days is not None:
        changes["lag_days"] = args.lag_days
    if args.backfill_max_days is not None:
        changes["backfill_max_days"] = args.backfill_max_days
    if args.retention_days is not None:
        raw = args.retention_days.strip().lower()
        if raw in {"none", "all", "0"}:
            changes["retention_days"] = None
        else:
            try:
                changes["retention_days"] = int(raw)
            except ValueError as exc:
                raise CliError(f"--retention-days expects an integer or 'none', got {args.retention_days!r}") from exc
    if args.renderers is not None:
        changes["renderers"] = None if args.renderers.strip().lower() == "all" else [
            token.strip() for token in args.renderers.split(",") if token.strip()
        ]
    if args.enable:
        changes["enabled"] = True
    if args.disable:
        changes["enabled"] = False
    if not changes:
        raise CliError("nothing to change; pass at least one option (see --help)")

    updated = config.replace(**changes)
    from tools.synthetic_clouds.render.base import registered_names

    updated.validate_renderers(registered_names())
    written = save_config(updated, args.config)
    print(f"ok: wrote {written}")
    for key, value in updated.to_document().items():
        print(f"{key:20} {value}")
    return 0


def _cmd_tick(args: argparse.Namespace) -> int:
    config = _load(args, validate_renderers=True)
    now = _parse_now(args.now, config)
    only: date | None = date.fromisoformat(args.date) if args.date else None
    # Imported here, not at module level: `daily.emit` reaches the renderer registry,
    # which imports pandas, pyarrow and every renderer module. `show` and `status` must
    # not pay that cost.
    from tools.synthetic_clouds.daily.emit import DEFAULT_OUT

    # NFR-4: the guard is at the CLI boundary, the same place `daily/__main__.py` puts
    # it. `tick` itself stays a function that writes where it is told, so tests can
    # drive it against a temp directory.
    state_path = guard_within_package(STATE_PATH if args.state is None else args.state)
    out_root = guard_within_package(args.out if args.out is not None else DEFAULT_OUT)
    log_path = state_path.parent / DEFAULT_LOG_NAME

    result = tick(
        config,
        now=now,
        state_path=state_path,
        out_root=out_root,
        log_path=log_path,
        force=args.force,
        only_day=only,
    )

    if result.status == "disabled":
        print("escala desabilitada (enabled=false): nada gerado")
        return 0
    print(f"alvo: {result.target_day.isoformat()}  fuso: {config.time_zone}  lag: {config.lag_days}d")
    if result.generated:
        print(f"gerados: {', '.join(day.isoformat() for day in result.generated)}  artefatos: {result.artifacts}")
    else:
        print("nada a gerar: o ledger ja cobre o alvo")
    if result.pruned:
        print(f"podados: {len(result.pruned)} dia(s) fora da retencao ({result.pruned[0].isoformat()}..{result.pruned[-1].isoformat()})")
    if result.truncated:
        print(f"atencao: {result.truncated} dia(s) anterior(es) ao limite de backfill ficaram de fora")
    for error in result.errors:
        print(f"erro: {error}", file=sys.stderr)

    delivery_failed = False
    if args.deliver and result.generated:
        from tools.synthetic_clouds.deliver import deliver_day

        for day in result.generated:
            delivery = deliver_day(day, daily_root=DEFAULT_OUT)
            print(
                f"entrega {day.isoformat()}: aws={delivery.aws_objects} objetos, "
                f"gcp={delivery.gcp_rows} linhas, azure={delivery.azure_days} dias"
            )
            for error in delivery.errors:
                print(f"erro de entrega: {error}", file=sys.stderr)
                delivery_failed = True
    return 0 if result.ok and not delivery_failed else 1


def _cmd_status(args: argparse.Namespace) -> int:
    config = _load(args)
    now = _parse_now(args.now, config)
    state_path = STATE_PATH if args.state is None else args.state
    state = load_state(state_path)

    print("== configuracao ==")
    for key, value in config.to_document().items():
        print(f"{key:20} {value}")
    print(f"{'config':20} {CONFIG_PATH if args.config is None else args.config}")

    print("\n== ledger ==")
    print(f"{'state':20} {state_path}")
    completed = state.completed_days()
    if completed:
        newest = completed[-1]
        print(f"{'dias gerados':20} {len(completed)}")
        print(f"{'primeiro':20} {completed[0].isoformat()}")
        print(f"{'ultimo':20} {newest.isoformat()}")
    else:
        print(f"{'dias gerados':20} 0")
    target = plan_target_day(config, now)
    print(f"{'alvo agora':20} {target.isoformat()}")
    if state.last_run is not None:
        print(f"{'ultima execucao':20} {state.last_run.at} ({state.last_run.status})")
        if state.last_run.errors:
            for error in state.last_run.errors:
                print(f"{'':20} erro: {error}")

    print("\n== tarefa do windows ==")
    task = windows.describe_task(args.task_name)
    if task is None:
        print(f"  nao registrada ({args.task_name})")
    else:
        print(f"  registrada:   {args.task_name}")
        daily = task.start_boundary or "?"
        print(f"  diario:       {daily}  (cada {task.days_interval or '?'} dia(s))")
        print(f"  no logon de:  {task.logon_user or '?'}")
        print(f"  atraso perdido: StartWhenAvailable={task.start_when_available}")
        # `None` aqui e "o Windows nao escreveu o campo", que nao e o mesmo que
        # "desligada": dizer "sim" seria afirmar o que nao foi lido.
        print(f"  habilitada:   {_flag_text(task.enabled)}")
        print(f"  comando:      {task.command} {task.arguments}")
    return 0


def _cmd_install(args: argparse.Namespace) -> int:
    config = _load(args)
    now = _parse_now(args.now, config)
    plan = windows.build_plan(
        config,
        now=now,
        python_exe=Path(sys.executable),
        repo_root=_REPO_ROOT,
        config_path=CONFIG_PATH if args.config is None else args.config,
        task_name=args.task_name,
    )
    print(f"tarefa: {plan.task_name}")
    print(f"conta:  {plan.user_id}")
    print(f"horario configurado: {plan.zone_time} ({plan.zone_name})")
    print(f"horario da tarefa:   {plan.machine_local_time} (hora local da maquina)")
    print(f"primeiro disparo:    {plan.start_boundary}")
    print(f"wrapper:             {plan.wrapper_path}")
    print(f"xml:                 {plan.xml_path}")
    for command in plan.commands:
        print("  " + " ".join(f'"{part}"' if " " in part else part for part in command))
    zone_offset = now.astimezone(config.zone()).utcoffset()
    machine_offset = now.astimezone().utcoffset()
    if zone_offset != machine_offset:
        print(
            f"\naviso: o fuso configurado ({config.time_zone}, offset {_format_offset(zone_offset)}) difere do\n"
            f"fuso da maquina (offset {_format_offset(machine_offset)}). O Agendador so entende hora local,\n"
            f"entao a tarefa foi escrita em {plan.machine_local_time}; quem garante o dia certo e a\n"
            f"idempotencia do tick."
        )
    if args.dry_run:
        print("\n--dry-run: nada foi escrito nem registrado.")
        return 0
    try:
        windows.register(plan)
    except windows.WindowsTaskError as exc:
        raise CliError(_register_failure_message(plan, str(exc))) from exc
    print(f"\nok: tarefa {plan.task_name} registrada (disparo diario + no logon, com StartWhenAvailable)")
    return 0


def _register_failure_message(plan: windows.RegistrationPlan, message: str) -> str:
    """Explain a failed registration in terms of the cause, not of a guess.

    The first version of this function blamed a missing administrator token, and that
    was WRONG: the denial came from the XML, which asked for a machine-wide logon
    trigger (``<LogonTrigger>`` with no ``<UserId>``). A minimal task registers fine
    without elevation on this machine. So the hint names the machine-wide trigger as the
    usual cause of a denial and keeps the raw message visible, instead of sending the
    operator after a privilege they may not need.
    """
    create = " ".join(f'"{part}"' if " " in part else part for part in plan.commands[0])
    lowered = message.lower()
    if "acesso negado" in lowered or "access is denied" in lowered:
        return (
            "o Agendador recusou o registro.\n\n"
            f"Mensagem do Windows: {message}\n\n"
            "Causa mais comum: XML com gatilho de ABRANGENCIA TOTAL (por exemplo um\n"
            "<LogonTrigger> sem <UserId>), que exige administrador. Aqui o gatilho esta\n"
            f"limitado a conta {plan.user_id}, entao o registro deveria ser de usuario comum.\n\n"
            "Se persistir, rode voce mesmo num PowerShell COMO ADMINISTRADOR:\n\n"
            f"  {create}\n\n"
            "O wrapper e o XML ja foram gravados:\n"
            f"  {plan.wrapper_path}\n  {plan.xml_path}"
        )
    return f"schtasks /Create failed: {message}"


def _cmd_uninstall(args: argparse.Namespace) -> int:
    if args.dry_run:
        print(f"--dry-run: removeria a tarefa {args.task_name}")
        return 0
    result = windows.unregister(args.task_name)
    if result.returncode != 0:
        message = f"{result.stdout.strip()}{result.stderr.strip()}"
        # schtasks reports a missing task as ERROR: The system cannot find the file
        # specified. Removing something already absent is the desired end state, so it
        # is reported as such instead of as a failure.
        if "cannot find" in message.lower() or "nao" in message.lower() or "não" in message.lower():
            print(f"nada a remover: {args.task_name} nao esta registrada")
            return 0
        raise CliError(f"schtasks /Delete failed ({result.returncode}): {message}")
    print(f"ok: tarefa {args.task_name} removida")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=None, help=f"caminho da configuracao (padrao: {CONFIG_PATH})")
    parser.add_argument("--now", default=None, help="instante ISO para a decisao de qual dia gerar (teste/replay)")


def _add_state_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--state", type=Path, default=None, help=f"caminho do ledger (padrao: {STATE_PATH})")
    parser.add_argument("--out", type=Path, default=None, help="diretorio raiz da saida diaria")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with every subcommand."""
    parser = argparse.ArgumentParser(
        prog="python -m tools.synthetic_clouds.schedule",
        description="Geracao diaria automatica dos dados de AWS, GCP e Azure.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="cria a configuracao padrao")
    _add_common(init)
    init.set_defaults(handler=_cmd_init)

    show = subparsers.add_parser("show", help="mostra a configuracao efetiva")
    _add_common(show)
    show.set_defaults(handler=_cmd_show)

    setter = subparsers.add_parser("set", help="altera a configuracao")
    _add_common(setter)
    setter.add_argument("--time", help="horario HH:MM no fuso de --time-zone")
    setter.add_argument("--time-zone", dest="time_zone", help="nome IANA, ex.: America/Sao_Paulo")
    setter.add_argument("--seed", type=int)
    setter.add_argument("--profile", choices=("small", "medium", "large"))
    setter.add_argument("--currency", choices=("USD", "BRL"))
    setter.add_argument("--lag-days", dest="lag_days", type=int, help="dias de atraso do export (FR-B2: 1)")
    setter.add_argument("--backfill-max-days", dest="backfill_max_days", type=int)
    setter.add_argument("--retention-days", dest="retention_days", help="dias mantidos, ou 'none' para guardar tudo")
    setter.add_argument("--renderers", help="lista separada por virgula, ou 'all'")
    setter.add_argument("--enable", action="store_true", help="liga a geracao diaria")
    setter.add_argument("--disable", action="store_true", help="desliga a geracao diaria")
    setter.set_defaults(handler=_cmd_set)

    tick_parser = subparsers.add_parser("tick", help="gera os dias devidos (usado pela tarefa agendada)")
    _add_common(tick_parser)
    _add_state_paths(tick_parser)
    tick_parser.add_argument("--force", action="store_true", help="regera o dia alvo mesmo que ja conste no ledger")
    tick_parser.add_argument("--date", help="gera exatamente este dia (YYYY-MM-DD)")
    tick_parser.add_argument(
        "--deliver",
        action="store_true",
        help="apos gerar, entrega cada dia aos emuladores (S3/BigQuery/azure-sim)",
    )
    tick_parser.set_defaults(handler=_cmd_tick)

    status = subparsers.add_parser("status", help="configuracao, ledger e tarefa do Windows")
    _add_common(status)
    _add_state_paths(status)
    status.add_argument("--task-name", dest="task_name", default=windows.TASK_NAME_DEFAULT)
    status.set_defaults(handler=_cmd_status)

    install = subparsers.add_parser("install", help="registra a tarefa no Agendador do Windows")
    _add_common(install)
    install.add_argument("--task-name", dest="task_name", default=windows.TASK_NAME_DEFAULT)
    install.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem registrar")
    install.set_defaults(handler=_cmd_install)

    uninstall = subparsers.add_parser("uninstall", help="remove a tarefa do Agendador")
    uninstall.add_argument("--task-name", dest="task_name", default=windows.TASK_NAME_DEFAULT)
    uninstall.add_argument("--dry-run", action="store_true")
    uninstall.set_defaults(handler=_cmd_uninstall)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the requested subcommand; return a process exit code."""
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        code: int = args.handler(args)
    except (CliError, ConfigError, StateError, TickError, windows.WindowsTaskError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code


__all__ = ["CliError", "build_parser", "main"]


if __name__ == "__main__":
    sys.exit(main())
