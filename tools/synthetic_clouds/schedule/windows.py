"""Windows Task Scheduler registration: making the tick actually happen.

The daily cadence existed and nothing fired it, which is the whole reason this module
exists. The operating system owns the timing -- not a long-running Python process --
because a daemon that must stay alive across reboots and logoffs is precisely the thing
that fails quietly and produces the symptom this work started from.

Two triggers are registered, and both earn their place:

* **daily at the configured time** -- the normal path;
* **at logon** -- the catch-up path. Combined with ``StartWhenAvailable`` (which makes
  the scheduler run a missed task as soon as the machine is back), a laptop that was
  off at 06:30 still generates its day.

Neither trigger needs to be exact, because :func:`tools.synthetic_clouds.schedule.runner.tick`
is idempotent: firing twice does nothing the second time, and firing late generates
exactly the days that are missing. That is what lets the schedule be simple.

Timing is written in the MACHINE's local time, because that is what the scheduler
reads. The configured zone decides *which day* a run belongs to; the conversion below
only decides what the clock in the task definition says. The two are reconciled by the
runner, not by hoping it is the same timezone.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from tools.synthetic_clouds.schedule.config import ScheduleConfig, guard_within_package

TASK_NAME_DEFAULT = "simulador-nuvem-daily"
DESCRIPTION = "Gera o dia sintetico de AWS/GCP/Azure do simulador-nuvem (idempotente)."

#: Namespace of the Task Scheduler schema. Element names are part of the contract; the
#: scheduler's own text report is LOCALIZED, and filtering it for English labels printed
#: nothing useful on a Portuguese Windows.
_TASK_NAMESPACE = "http://schemas.microsoft.com/windows/2004/02/mit/task"

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

#: Absolute path to the scheduler binary. Built from ``%SystemRoot%`` rather than
#: relying on ``PATH``: a task that resolves an interpreter or an executable by name
#: can start resolving a different one after an unrelated install.
_SCHTASKS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "schtasks.exe"


class WindowsTaskError(Exception):
    """Raised when the scheduled task cannot be built, registered or removed."""


@dataclass(frozen=True, slots=True)
class RegistrationPlan:
    """Everything a registration will do, inspectable before it does it."""

    task_name: str
    xml: str
    xml_path: Path
    wrapper_path: Path
    wrapper_text: str
    start_boundary: str
    machine_local_time: str
    zone_time: str
    zone_name: str
    user_id: str

    @property
    def commands(self) -> tuple[tuple[str, ...], ...]:
        """The exact command lines, in order. Printed for ``--dry-run``."""
        return (
            (str(_SCHTASKS), "/Create", "/TN", self.task_name, "/XML", str(self.xml_path), "/F"),
            (str(_SCHTASKS), "/Query", "/TN", self.task_name),
        )


def wrapper_path() -> Path:
    """Path of the generated ``.cmd`` the scheduled action invokes."""
    return _PACKAGE_ROOT / "schedule" / "run-daily.cmd"


def render_wrapper(*, python_exe: Path, repo_root: Path, task_log: Path, config_path: Path) -> str:
    """Return the ``.cmd`` text: set the import root, run one tick, log everything.

    ``PYTHONPATH`` and ``cd`` are both set. The package self-imports as
    ``tools.synthetic_clouds`` and ``tools/`` has no ``__init__.py``, so the import
    only resolves from the repository root -- a task with a different working
    directory would fail at import time, which is the least helpful way to fail.
    """
    return (
        "@echo off\r\n"
        "rem Gerado por `python -m tools.synthetic_clouds.schedule install`. Nao editar a mao:\r\n"
        "rem o proximo install sobrescreve. A logica esta em schedule/runner.py.\r\n"
        "setlocal\r\n"
        f'set "PYTHONPATH={repo_root}"\r\n'
        f'cd /d "{repo_root}"\r\n'
        f'"{python_exe}" -m tools.synthetic_clouds.schedule tick --config "{config_path}"'
        f' >> "{task_log}" 2>&1\r\n'
        "exit /b %ERRORLEVEL%\r\n"
    )


def current_user_id() -> str:
    """Return the current account as ``DOMAIN\\user``, the form the scheduler resolves.

    The logon trigger NEEDS this. A ``<LogonTrigger>`` with no ``<UserId>`` is a
    machine-wide trigger -- it would fire when *anyone* logs on -- and registering one
    is an administrative operation. That is exactly how the first version of this file
    failed: ``schtasks /Create`` answered "Acesso negado" and the cause looked like a
    missing privilege, when the XML was asking for a machine-wide trigger. Scoping the
    trigger to the account that owns the job makes the registration an ordinary
    per-user one.
    """
    domain = os.environ.get("USERDOMAIN")
    user = os.environ.get("USERNAME")
    if domain and user:
        return f"{domain}\\{user}"
    raise WindowsTaskError("cannot determine the current user: USERDOMAIN/USERNAME are unset")


def task_xml(
    *,
    command: str,
    arguments: str,
    start_boundary: str,
    user_id: str,
    description: str = DESCRIPTION,
) -> str:
    """Return the Task Scheduler XML: one daily trigger plus one logon catch-up.

    ``StartWhenAvailable`` is the setting that makes a missed run recoverable; without
    it a machine that was off at the configured hour simply loses that day until the
    next logon trigger.

    ``user_id`` is required rather than optional on purpose: leaving it out produces XML
    that only an administrator can register, and the failure ("access denied") points at
    privileges instead of at the trigger. Making the parameter mandatory means the
    machine-wide variant cannot be built by accident.
    """
    account = escape(user_id)
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\r\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\r\n'
        "  <RegistrationInfo>\r\n"
        f"    <Description>{escape(description)}</Description>\r\n"
        "  </RegistrationInfo>\r\n"
        "  <Triggers>\r\n"
        "    <CalendarTrigger>\r\n"
        f"      <StartBoundary>{start_boundary}</StartBoundary>\r\n"
        "      <Enabled>true</Enabled>\r\n"
        "      <ScheduleByDay>\r\n"
        "        <DaysInterval>1</DaysInterval>\r\n"
        "      </ScheduleByDay>\r\n"
        "    </CalendarTrigger>\r\n"
        "    <LogonTrigger>\r\n"
        "      <Enabled>true</Enabled>\r\n"
        f"      <UserId>{account}</UserId>\r\n"
        "    </LogonTrigger>\r\n"
        "  </Triggers>\r\n"
        "  <Principals>\r\n"
        '    <Principal id="Author">\r\n'
        f"      <UserId>{account}</UserId>\r\n"
        "      <LogonType>InteractiveToken</LogonType>\r\n"
        "      <RunLevel>LeastPrivilege</RunLevel>\r\n"
        "    </Principal>\r\n"
        "  </Principals>\r\n"
        "  <Settings>\r\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\r\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\r\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\r\n"
        "    <AllowHardTerminate>true</AllowHardTerminate>\r\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\r\n"
        "    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\r\n"
        "    <ExecutionTimeLimit>PT4H</ExecutionTimeLimit>\r\n"
        "    <Enabled>true</Enabled>\r\n"
        "  </Settings>\r\n"
        '  <Actions Context="Author">\r\n'
        "    <Exec>\r\n"
        f"      <Command>{escape(command)}</Command>\r\n"
        f"      <Arguments>{escape(arguments)}</Arguments>\r\n"
        "    </Exec>\r\n"
        "  </Actions>\r\n"
        "</Task>\r\n"
    )


def _machine_local_start_boundary(config: ScheduleConfig, now: datetime) -> tuple[str, str]:
    """Return ``(start_boundary, machine_local_HH:MM)`` for the next configured time.

    The configured time is interpreted in the CONFIGURED zone and then converted to the
    machine's own zone, because the scheduler only understands machine-local clock
    time. Converting an aware instant (rather than copying the hour across) is what
    keeps this honest when the two zones differ.
    """
    zone = config.zone()
    local_now = now.astimezone(zone)
    candidate = local_now.replace(hour=config.time.hour, minute=config.time.minute, second=0, microsecond=0)
    if candidate <= local_now:
        candidate = candidate + timedelta(days=1)
    machine_local = candidate.astimezone()
    return machine_local.strftime("%Y-%m-%dT%H:%M:%S"), machine_local.strftime("%H:%M")


def build_plan(
    config: ScheduleConfig,
    *,
    now: datetime,
    python_exe: Path,
    repo_root: Path,
    config_path: Path,
    task_name: str = TASK_NAME_DEFAULT,
    user_id: str | None = None,
) -> RegistrationPlan:
    """Assemble the wrapper text, the task XML and the paths, touching nothing."""
    state_dir = _PACKAGE_ROOT / "out" / "daily" / "_state"
    task_log = state_dir / "task.log"
    wrapper = wrapper_path()
    start_boundary, machine_local = _machine_local_start_boundary(config, now)
    user_id = user_id or current_user_id()
    arguments = f'/c "{wrapper}"'
    return RegistrationPlan(
        task_name=task_name,
        xml=task_xml(command="cmd.exe", arguments=arguments, start_boundary=start_boundary, user_id=user_id),
        xml_path=guard_within_package(_PACKAGE_ROOT / "schedule" / f"{task_name}.xml"),
        wrapper_path=wrapper,
        wrapper_text=render_wrapper(
            python_exe=python_exe,
            repo_root=repo_root,
            task_log=task_log,
            config_path=config_path,
        ),
        start_boundary=start_boundary,
        machine_local_time=machine_local,
        zone_time=config.time_text,
        zone_name=config.time_zone,
        user_id=user_id,
    )


def run_command(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run one scheduler command and return its result without raising on failure.

    ``check=False`` is deliberate: the caller decides what a non-zero exit means, and
    ``register`` must be able to report the scheduler's own message verbatim rather than
    a traceback.
    """
    return subprocess.run(  # noqa: S603 - fixed absolute binary, argument list, shell=False
        list(arguments),
        capture_output=True,
        text=True,
        check=False,
    )


def write_plan_files(plan: RegistrationPlan) -> tuple[Path, Path]:
    """Write the wrapper and the task XML inside the package; return both paths.

    The XML is UTF-16 with a BOM because that is what ``schtasks /XML`` expects to read,
    and the declaration inside it says so.

    ``newline=""`` is load-bearing, not tidiness. Both payloads already carry explicit
    CRLF, and ``Path.write_text`` translates ``\\n`` to ``\\r\\n`` by default -- which
    turned every line ending into CR CR LF (8 in the wrapper, 40 in the XML). ``cmd.exe``
    happened to tolerate it, which is exactly what makes it dangerous: the file works
    until some tool reads the trailing CR as part of the value.
    """
    plan.wrapper_path.write_text(plan.wrapper_text, encoding="utf-8", newline="")
    plan.xml_path.write_text(plan.xml, encoding="utf-16", newline="")
    return plan.wrapper_path, plan.xml_path


def register(plan: RegistrationPlan) -> subprocess.CompletedProcess[str]:
    """Write the plan's files and register the task with the scheduler.

    Whether to do this at all is the caller's decision: ``--dry-run`` is handled in the
    CLI, so this function has exactly one job and no silent mode.
    """
    write_plan_files(plan)
    create = run_command(plan.commands[0])
    if create.returncode != 0:
        raise WindowsTaskError(
            f"schtasks /Create failed ({create.returncode}): {create.stdout.strip()}{create.stderr.strip()}"
        )
    return create


def unregister(task_name: str = TASK_NAME_DEFAULT) -> subprocess.CompletedProcess[str]:
    """Remove the task. The caller decides how to read a non-zero exit.

    "Task not found" is a non-zero exit, and it is not a failure to remove a task that
    is already absent -- but that judgement belongs to the CLI, next to the message it
    prints, rather than hidden here.
    """
    return run_command((str(_SCHTASKS), "/Delete", "/TN", task_name, "/F"))


def query(task_name: str = TASK_NAME_DEFAULT) -> subprocess.CompletedProcess[str]:
    """Ask the scheduler about the task, so `status` can report what Windows believes."""
    return run_command((str(_SCHTASKS), "/Query", "/TN", task_name, "/FO", "LIST", "/V"))


@dataclass(frozen=True, slots=True)
class TaskView:
    """The few facts about a registered task that matter, read from its XML.

    The XML is queried instead of the ``/FO LIST`` report because that report is
    LOCALIZED: ``status`` was filtering for English labels and printing nothing but a
    bare "Status: Pronto" twice on a Portuguese Windows. Element names are part of the
    task schema and do not translate.
    """

    start_boundary: str | None
    days_interval: str | None
    logon_user: str | None
    start_when_available: bool | None
    enabled: bool | None
    command: str | None
    arguments: str | None


def describe_task(task_name: str = TASK_NAME_DEFAULT) -> TaskView | None:
    """Return what the scheduler has for ``task_name``, or ``None`` if it is not there."""
    result = run_command((str(_SCHTASKS), "/Query", "/TN", task_name, "/XML"))
    if result.returncode != 0:
        return None
    try:
        # noqa: S314 - the input is the local scheduler's own output for a task this
        # tool registered, not untrusted network data. `defusedxml` would add a
        # dependency to parse a document produced three lines up.
        root = ElementTree.fromstring(result.stdout)  # noqa: S314
    except ElementTree.ParseError:
        return None
    ns = {"t": _TASK_NAMESPACE}

    def _text(path: str) -> str | None:
        found = root.find(path, ns)
        return None if found is None or found.text is None else found.text.strip()

    def _flag(path: str) -> bool | None:
        raw = _text(path)
        if raw is None:
            return None
        return raw.lower() == "true"

    return TaskView(
        start_boundary=_text(".//t:CalendarTrigger/t:StartBoundary"),
        days_interval=_text(".//t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval"),
        logon_user=_text(".//t:LogonTrigger/t:UserId"),
        start_when_available=_flag(".//t:Settings/t:StartWhenAvailable"),
        enabled=_flag(".//t:Settings/t:Enabled"),
        command=_text(".//t:Actions/t:Exec/t:Command"),
        arguments=_text(".//t:Actions/t:Exec/t:Arguments"),
    )


__all__ = [
    "DESCRIPTION",
    "TASK_NAME_DEFAULT",
    "RegistrationPlan",
    "TaskView",
    "WindowsTaskError",
    "build_plan",
    "current_user_id",
    "describe_task",
    "query",
    "register",
    "render_wrapper",
    "run_command",
    "task_xml",
    "unregister",
    "wrapper_path",
    "write_plan_files",
]
