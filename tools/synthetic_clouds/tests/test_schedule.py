"""Agendador diário: configuração, ledger, plano de backfill, tick e registro no Windows.

As asserções que sustentam o resto são as de **idempotência e backfill**. Um job
agendado dispara duas vezes no mesmo dia (o gatilho diário e o do logon), a máquina
fica desligada na hora marcada, e nada disso pode gerar o dia duas vezes nem deixar um
buraco silencioso. O que se prova aqui é que o ledger decide isso, e não a sorte.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from tools.synthetic_clouds.schedule import __main__ as schedule_cli
from tools.synthetic_clouds.schedule import windows
from tools.synthetic_clouds.schedule.config import (
    ConfigError,
    ScheduleConfig,
    guard_within_package,
    load_config,
    save_config,
)
from tools.synthetic_clouds.schedule.runner import (
    DayGenerator,
    TickError,
    TickResult,
    plan_backfill,
    plan_prune,
    prune_days,
    target_day_for,
    tick,
)
from tools.synthetic_clouds.schedule.state import (
    RunState,
    StateError,
    load_state,
    save_state,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _REPO_ROOT / "tools" / "synthetic_clouds"

#: O CLI e o `save_config` aplicam a fronteira de escrita (NFR-4), então os testes que
#: passam pelo CLI precisam de caminhos DENTRO do pacote, não de `tmp_path`. O PID no
#: caminho evita que duas execuções da suíte em paralelo se apaguem mutuamente — o
#: mesmo motivo já documentado em `test_daily_cadence.py`.
_SCRATCH = _PACKAGE_ROOT / "out" / "pytest-schedule" / f"pid-{os.getpid()}"

_ZONE = "America/Sao_Paulo"
_NOW = datetime(2026, 10, 14, 6, 30, tzinfo=ZoneInfo(_ZONE))


def _config(**overrides: object) -> ScheduleConfig:
    document: dict[str, object] = {
        "time": "06:30",
        "time_zone": _ZONE,
        "seed": 123,
        "profile": "small",
    }
    document.update(overrides)
    return ScheduleConfig.from_document(document)


def _tick(
    config: ScheduleConfig,
    scratch: Path,
    *,
    now: datetime = _NOW,
    generate: DayGenerator | None = None,
    force: bool = False,
    only_day: date | None = None,
) -> TickResult:
    """Um tick apontado para o scratch do teste, com gerador injetado."""
    return tick(
        config,
        now=now,
        state_path=scratch / "state.json",
        out_root=scratch / "out",
        log_path=scratch / "runs.log",
        force=force,
        generate=generate,
        only_day=only_day,
    )


@pytest.fixture
def scratch(request: pytest.FixtureRequest) -> Iterator[Path]:
    """Um diretório de trabalho dentro do pacote, removido ao final."""
    path = _SCRATCH / request.node.name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


class TestConfig:
    def test_round_trips_through_document(self) -> None:
        config = _config()
        assert ScheduleConfig.from_document(config.to_document()) == config

    def test_time_text_is_zero_padded(self) -> None:
        assert _config(time="07:05").time_text == "07:05"

    @pytest.mark.parametrize("bad", ["6:30", "24:00", "06:60", "0630", "06:3", "06:30:00", ""])
    def test_bad_time_is_refused(self, bad: str) -> None:
        with pytest.raises(ConfigError):
            _config(time=bad)

    def test_unknown_key_is_refused_not_ignored(self) -> None:
        # "hour" ao lado de "time" é o caso que motiva a recusa: ignorar em silêncio
        # faria o job rodar na hora padrão enquanto o arquivo afirma outra.
        document = _config().to_document()
        document["hour"] = "07:00"
        with pytest.raises(ConfigError, match="unknown key"):
            ScheduleConfig.from_document(document)

    def test_missing_required_key_is_refused(self) -> None:
        document = _config().to_document()
        del document["seed"]
        with pytest.raises(ConfigError, match="missing required"):
            ScheduleConfig.from_document(document)

    def test_unresolvable_timezone_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="IANA"):
            _config(time_zone="America/Sao_Paulo_typo")

    def test_bool_is_not_accepted_as_seed(self) -> None:
        with pytest.raises(ConfigError, match="integer"):
            _config(seed=True)

    def test_negative_lag_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="lag_days"):
            _config(lag_days=-1)

    def test_replace_revalidates(self) -> None:
        config = _config()
        with pytest.raises(ConfigError):
            config.replace(time="nonsense")
        assert config.replace(time="08:00").time_text == "08:00"

    def test_unknown_renderer_is_refused(self) -> None:
        config = _config(renderers=["focus_aws"])
        # `cur2_aws` existe no projeto, mas não nesta seleção: é exatamente esse o
        # caso que a validação tem de pegar (nome válido em geral, inválido aqui).
        with pytest.raises(ConfigError, match="unknown renderer"):
            config.validate_renderers(["cur2_aws"])
        config.validate_renderers(["focus_aws", "cur2_aws"])

    def test_empty_renderer_list_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="non-empty"):
            _config(renderers=[]).validate_renderers(["focus_aws"])

    def test_null_renderers_means_all(self) -> None:
        _config(renderers=None).validate_renderers([])

    def test_retention_round_trips(self) -> None:
        assert _config(retention_days=7).retention_days == 7
        assert _config(retention_days=None).retention_days is None

    def test_retention_zero_is_refused(self) -> None:
        with pytest.raises(ConfigError, match="retention_days"):
            _config(retention_days=0)


class TestConfigPersistence:
    def test_save_then_load(self, scratch: Path) -> None:
        target = scratch / "config.json"
        written = save_config(_config(time="05:45"), target)
        assert load_config(written).time_text == "05:45"

    def test_missing_file_says_how_to_fix(self, scratch: Path) -> None:
        with pytest.raises(ConfigError, match="config init"):
            load_config(scratch / "absent.json")

    def test_malformed_json_is_refused(self, scratch: Path) -> None:
        target = scratch / "config.json"
        target.write_text("{not json", encoding="utf-8")
        with pytest.raises(ConfigError, match="not valid JSON"):
            load_config(target)

    def test_write_outside_the_package_is_refused(self, tmp_path: Path) -> None:
        # NFR-4: a fronteira vale para a configuração, não só para os artefatos.
        with pytest.raises(ConfigError, match="NFR-4"):
            save_config(_config(), tmp_path / "config.json")

    def test_guard_accepts_the_package_itself(self) -> None:
        assert guard_within_package(_PACKAGE_ROOT) == _PACKAGE_ROOT.resolve()


class TestState:
    def test_missing_ledger_is_empty(self, scratch: Path) -> None:
        state = load_state(scratch / "state.json")
        assert state.completed_days() == ()
        assert state.last_run is None

    def test_round_trips(self, scratch: Path) -> None:
        target = scratch / "state.json"
        state = RunState().with_day(date(2026, 10, 13), artifacts=7, at="2026-10-14T06:30:00-03:00")
        save_state(state, target)
        loaded = load_state(target)
        assert loaded.is_complete(date(2026, 10, 13))
        assert loaded.days["2026-10-13"].artifacts == 7

    def test_completed_days_are_sorted_oldest_first(self, scratch: Path) -> None:
        target = scratch / "state.json"
        state = RunState()
        for day in (date(2026, 10, 13), date(2026, 10, 11), date(2026, 10, 12)):
            state = state.with_day(day, artifacts=1, at="now")
        save_state(state, target)
        assert load_state(target).completed_days() == (
            date(2026, 10, 11),
            date(2026, 10, 12),
            date(2026, 10, 13),
        )

    def test_malformed_ledger_is_refused(self, scratch: Path) -> None:
        target = scratch / "state.json"
        target.write_text("{oops", encoding="utf-8")
        with pytest.raises(StateError, match="not valid JSON"):
            load_state(target)

    def test_wrong_version_is_refused(self, scratch: Path) -> None:
        target = scratch / "state.json"
        target.write_text(json.dumps({"version": 99, "days": {}}), encoding="utf-8")
        with pytest.raises(StateError, match="unsupported ledger version"):
            load_state(target)

    def test_days_key_must_be_an_iso_date(self, scratch: Path) -> None:
        target = scratch / "state.json"
        payload = {"version": 1, "days": {"ontem": {"status": "complete", "artifacts": 1, "completed_at": "x"}}}
        target.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(StateError, match="not an ISO date"):
            load_state(target)

    def test_a_ledger_without_the_pruned_field_still_loads(self, scratch: Path) -> None:
        # `pruned` é aditivo dentro de last_run: um ledger gravado antes da retenção
        # existir tem de continuar legível, senão o histórico vira refém do upgrade.
        target = scratch / "state.json"
        payload = {
            "version": 1,
            "days": {"2026-10-13": {"status": "complete", "artifacts": 5, "completed_at": "x"}},
            "last_run": {"at": "x", "target_day": "2026-10-13", "status": "ok", "generated": [], "errors": []},
        }
        target.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_state(target)
        assert loaded.last_run is not None
        assert loaded.last_run.pruned == ()

    def test_without_days_removes_only_the_named_days(self) -> None:
        state = RunState()
        for day in (date(2026, 10, 11), date(2026, 10, 12)):
            state = state.with_day(day, artifacts=1, at="x")
        trimmed = state.without_days((date(2026, 10, 11),))
        assert trimmed.completed_days() == (date(2026, 10, 12),)


class TestPlanBackfill:
    _TARGET = date(2026, 10, 13)

    def test_first_run_generates_only_the_target(self) -> None:
        plan = plan_backfill(self._TARGET, (), max_days=31)
        assert plan.days == (self._TARGET,)
        assert plan.truncated == 0

    def test_up_to_date_generates_nothing(self) -> None:
        plan = plan_backfill(self._TARGET, (self._TARGET,), max_days=31)
        assert plan.days == ()

    def test_clock_moving_backwards_generates_nothing(self) -> None:
        plan = plan_backfill(self._TARGET, (date(2026, 10, 20),), max_days=31)
        assert plan.days == ()

    def test_gap_is_filled_in_order(self) -> None:
        plan = plan_backfill(self._TARGET, (date(2026, 10, 10),), max_days=31)
        assert plan.days == (date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))

    def test_cap_keeps_the_newest_and_reports_the_rest(self) -> None:
        plan = plan_backfill(self._TARGET, (date(2026, 10, 10),), max_days=2)
        assert plan.days == (date(2026, 10, 12), date(2026, 10, 13))
        assert plan.truncated == 1

    def test_force_regenerates_the_newest_day(self) -> None:
        plan = plan_backfill(self._TARGET, (self._TARGET,), max_days=31, force=True)
        assert plan.days == (self._TARGET,)

    def test_only_day_overrides_the_calendar(self) -> None:
        explicit = date(2026, 9, 1)
        plan = plan_backfill(self._TARGET, (date(2026, 10, 13),), max_days=31, only=explicit)
        assert plan.days == (explicit,)
        assert plan.target_day == explicit

    def test_only_day_already_done_needs_force(self) -> None:
        explicit = date(2026, 9, 1)
        done = (self._TARGET, explicit)
        assert plan_backfill(self._TARGET, done, max_days=31, only=explicit).days == ()
        assert plan_backfill(self._TARGET, done, max_days=31, only=explicit, force=True).days == (explicit,)

    def test_cap_must_be_positive(self) -> None:
        with pytest.raises(TickError, match="max_days"):
            plan_backfill(self._TARGET, (), max_days=0)


class TestTargetDay:
    def test_lag_applies_in_the_configured_zone(self) -> None:
        config = _config(lag_days=1)
        # 02:00 UTC do dia 14 ainda é dia 13 em São Paulo (UTC-3): o dia alvo tem de
        # seguir o fuso configurado, não o da máquina nem UTC.
        now = datetime(2026, 10, 14, 2, 0, tzinfo=ZoneInfo("UTC"))
        assert target_day_for(config, now) == date(2026, 10, 12)

    def test_zero_lag_targets_the_local_day(self) -> None:
        config = _config(lag_days=0)
        assert target_day_for(config, _NOW) == date(2026, 10, 14)

    def test_default_lag_is_one_day(self) -> None:
        assert _config().lag_days == 1
        assert target_day_for(_config(), _NOW) == date(2026, 10, 13)


class TestTick:
    def test_first_tick_generates_the_target_and_records_it(self, scratch: Path) -> None:
        calls: list[date] = []

        def generate(day: date) -> int:
            calls.append(day)
            return 3

        result = _tick(_config(), scratch, generate=generate)
        assert calls == [date(2026, 10, 13)]
        assert result.status == "ok"
        assert result.artifacts == 3
        assert load_state(scratch / "state.json").is_complete(date(2026, 10, 13))

    def test_second_tick_the_same_day_generates_nothing(self, scratch: Path) -> None:
        calls: list[date] = []

        def generate(day: date) -> int:
            calls.append(day)
            return 1

        _tick(_config(), scratch, generate=generate)
        second = _tick(_config(), scratch, generate=generate)
        assert calls == [date(2026, 10, 13)]
        assert second.status == "up-to-date"
        assert second.generated == ()

    def test_backfill_generates_every_missing_day(self, scratch: Path) -> None:
        state = RunState().with_day(date(2026, 10, 10), artifacts=1, at="earlier")
        save_state(state, scratch / "state.json")
        calls: list[date] = []

        def generate(day: date) -> int:
            calls.append(day)
            return 2

        result = _tick(_config(), scratch, generate=generate)
        assert calls == [date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13)]
        assert result.artifacts == 6
        assert len(load_state(scratch / "state.json").completed_days()) == 4

    def test_backfill_respects_the_cap_and_says_so(self, scratch: Path) -> None:
        state = RunState().with_day(date(2026, 10, 10), artifacts=1, at="earlier")
        save_state(state, scratch / "state.json")
        result = _tick(_config(backfill_max_days=2), scratch, generate=lambda day: 1)
        assert result.generated == (date(2026, 10, 12), date(2026, 10, 13))
        assert result.truncated == 1

    def test_a_failing_day_is_recorded_and_stops_the_batch(self, scratch: Path) -> None:
        # Um dia que falha não pode apagar o registro dos que já deram certo.
        state = RunState().with_day(date(2026, 10, 10), artifacts=1, at="earlier")
        save_state(state, scratch / "state.json")

        def generate(day: date) -> int:
            if day == date(2026, 10, 12):
                raise RuntimeError("disco cheio")
            return 1

        result = _tick(_config(), scratch, generate=generate)
        assert result.status == "failed"
        assert result.generated == (date(2026, 10, 11),)
        assert "disco cheio" in result.errors[0]
        ledger = load_state(scratch / "state.json")
        assert ledger.is_complete(date(2026, 10, 11))
        assert not ledger.is_complete(date(2026, 10, 12))
        assert ledger.last_run is not None and ledger.last_run.status == "failed"

    def test_disabled_schedule_does_nothing(self, scratch: Path) -> None:
        result = _tick(_config(enabled=False), scratch, generate=lambda day: 1)
        assert result.status == "disabled"
        assert not (scratch / "state.json").exists()

    def test_run_log_gets_one_line_per_tick(self, scratch: Path) -> None:
        _tick(_config(), scratch, generate=lambda day: 1)
        _tick(_config(), scratch, generate=lambda day: 1)
        lines = (scratch / "runs.log").read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["status"] == "ok"
        assert json.loads(lines[1])["status"] == "up-to-date"

    def test_force_regenerates_the_target(self, scratch: Path) -> None:
        calls: list[date] = []

        def record(day: date) -> int:
            calls.append(day)
            return 1

        _tick(_config(), scratch, generate=record)
        _tick(_config(), scratch, generate=record, force=True)
        assert calls == [date(2026, 10, 13), date(2026, 10, 13)]

    def test_only_day_generates_an_out_of_order_day(self, scratch: Path) -> None:
        _tick(_config(), scratch, generate=lambda day: 1)
        result = _tick(_config(), scratch, generate=lambda day: 1, only_day=date(2026, 9, 1))
        assert result.generated == (date(2026, 9, 1),)
        assert load_state(scratch / "state.json").is_complete(date(2026, 9, 1))


class TestPlanPrune:
    _TARGET = date(2026, 10, 13)

    def test_none_keeps_everything(self) -> None:
        done = (date(2026, 1, 1), self._TARGET)
        assert plan_prune(self._TARGET, done, retention_days=None) == ()

    def test_window_ends_at_the_target(self) -> None:
        done = tuple(date(2026, 10, day) for day in range(1, 14))
        # retencao 3 -> mantem 11, 12, 13; poda 1..10
        pruned = plan_prune(self._TARGET, done, retention_days=3)
        assert pruned == tuple(date(2026, 10, day) for day in range(1, 11))

    def test_window_of_one_keeps_only_the_target(self) -> None:
        done = (date(2026, 10, 12), self._TARGET)
        assert plan_prune(self._TARGET, done, retention_days=1) == (date(2026, 10, 12),)

    def test_a_run_that_is_behind_does_not_prune_what_it_just_kept(self) -> None:
        # Alvo 13, retencao 3 -> nada antes de 11 e podado, mesmo que o ledger tenha
        # dias bem antigos que o backfill acabou de gerar.
        done = (date(2026, 10, 11), date(2026, 10, 12), self._TARGET)
        assert plan_prune(self._TARGET, done, retention_days=3) == ()

    def test_zero_is_refused(self) -> None:
        with pytest.raises(TickError, match="retention_days"):
            plan_prune(self._TARGET, (), retention_days=0)


class TestPruneDays:
    def test_deletes_the_day_directory(self, scratch: Path) -> None:
        day = date(2026, 10, 1)
        (scratch / day.isoformat() / "123-small-USD").mkdir(parents=True)
        deleted, errors = prune_days(scratch, (day,))
        assert deleted == (day,)
        assert errors == ()
        assert not (scratch / day.isoformat()).exists()

    def test_a_missing_directory_counts_as_deleted(self, scratch: Path) -> None:
        day = date(2026, 10, 1)
        deleted, errors = prune_days(scratch, (day,))
        assert deleted == (day,)
        assert errors == ()

    def test_a_locked_directory_is_reported_and_not_claimed(self, scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import shutil as shutil_module

        day = date(2026, 10, 1)
        (scratch / day.isoformat()).mkdir(parents=True)

        def boom(path: str | Path) -> None:
            raise OSError("em uso")

        monkeypatch.setattr(shutil_module, "rmtree", boom)
        deleted, errors = prune_days(scratch, (day,))
        assert deleted == ()
        assert "em uso" in errors[0]


class TestTickRetention:
    def _seed_ledger(self, scratch: Path, days: tuple[date, ...]) -> None:
        state = RunState()
        for day in days:
            state = state.with_day(day, artifacts=1, at="earlier")
            (scratch / "out" / day.isoformat()).mkdir(parents=True, exist_ok=True)
        save_state(state, scratch / "state.json")

    def test_prunes_and_drops_the_days_from_the_ledger(self, scratch: Path) -> None:
        days = (date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))
        self._seed_ledger(scratch, days)
        result = _tick(_config(retention_days=1), scratch, generate=lambda day: 1)

        assert result.status == "up-to-date"
        assert result.pruned == (date(2026, 10, 11), date(2026, 10, 12))
        assert not (scratch / "out" / "2026-10-11").exists()
        ledger = load_state(scratch / "state.json")
        assert ledger.completed_days() == (date(2026, 10, 13),)
        # O ledger não pode afirmar que existe um dia cujo artefato foi apagado.
        assert not ledger.is_complete(date(2026, 10, 11))

    def test_pruning_does_not_resurrect_the_day_later(self, scratch: Path) -> None:
        days = (date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))
        self._seed_ledger(scratch, days)
        _tick(_config(retention_days=1), scratch, generate=lambda day: 1)

        # O proximo dia e gerado; o podado continua podado.
        generated: list[date] = []

        def record(day: date) -> int:
            generated.append(day)
            return 1

        _tick(
            _config(retention_days=1),
            scratch,
            now=datetime(2026, 10, 15, 6, 30, tzinfo=ZoneInfo(_ZONE)),
            generate=record,
        )
        assert generated == [date(2026, 10, 14)]
        assert not (scratch / "out" / "2026-10-11").exists()

    def test_without_retention_nothing_is_deleted(self, scratch: Path) -> None:
        days = (date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))
        self._seed_ledger(scratch, days)
        result = _tick(_config(), scratch, generate=lambda day: 1)
        assert result.pruned == ()
        assert (scratch / "out" / "2026-10-11").exists()

    def test_prune_failure_does_not_fail_the_generation(self, scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import shutil as shutil_module

        days = (date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))
        self._seed_ledger(scratch, days)

        def boom(path: str | Path) -> None:
            raise OSError("em uso")

        monkeypatch.setattr(shutil_module, "rmtree", boom)
        result = _tick(_config(retention_days=1), scratch, generate=lambda day: 1)
        # A coleta falhou, mas os dados do dia estão íntegros: o status não pode dizer
        # que a geração falhou.
        assert result.status == "up-to-date"
        assert result.pruned == ()
        assert "em uso" in result.errors[0]
        assert load_state(scratch / "state.json").is_complete(date(2026, 10, 11))


class TestWindowsRegistration:
    def test_wrapper_sets_pythonpath_and_logs(self, scratch: Path) -> None:
        text = windows.render_wrapper(
            python_exe=Path(r"C:\venv\python.exe"),
            repo_root=Path(r"<raiz-do-repo>"),
            task_log=scratch / "task.log",
            config_path=Path(r"D:\cfg\config.json"),
        )
        assert 'set "PYTHONPATH=<raiz-do-repo>"' in text
        assert 'cd /d "<raiz-do-repo>"' in text
        assert "tools.synthetic_clouds.schedule tick" in text
        assert "2>&1" in text

    def test_xml_has_a_daily_trigger_a_logon_trigger_and_catch_up(self) -> None:
        xml = windows.task_xml(
            command="cmd.exe",
            arguments="/c wrapper.cmd",
            start_boundary="2026-10-15T06:30:00",
            user_id="DESKTOP-X\\tester",
        )
        assert "<CalendarTrigger>" in xml
        assert "<DaysInterval>1</DaysInterval>" in xml
        assert "<LogonTrigger>" in xml
        assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
        assert "2026-10-15T06:30:00" in xml

    def test_the_logon_trigger_is_scoped_to_the_account(self) -> None:
        """Sem `<UserId>`, o gatilho de logon vale para a MÁQUINA e exige administrador.

        Foi o defeito real: o registro respondia "Acesso negado" e parecia falta de
        privilégio, quando o XML é que pedia um gatilho de abrangência total. Este teste
        existe para que a variante de máquina inteira não volte por descuido.
        """
        xml = windows.task_xml(
            command="cmd.exe",
            arguments="/c wrapper.cmd",
            start_boundary="2026-10-15T06:30:00",
            user_id="DESKTOP-X\\tester",
        )
        logon = xml.split("<LogonTrigger>")[1].split("</LogonTrigger>")[0]
        assert "<UserId>DESKTOP-X\\tester</UserId>" in logon
        # E o principal também, para a tarefa rodar na conta que a possui.
        assert xml.count("<UserId>DESKTOP-X\\tester</UserId>") == 2

    def test_user_id_is_a_required_parameter(self) -> None:
        # Tornar o parâmetro obrigatório é o que impede construir o XML de máquina
        # inteira por omissão.
        import inspect

        signature = inspect.signature(windows.task_xml)
        assert signature.parameters["user_id"].default is inspect.Parameter.empty

    def test_current_user_id_prefers_domain_and_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("USERDOMAIN", "DESKTOP-X")
        monkeypatch.setenv("USERNAME", "tester")
        assert windows.current_user_id() == "DESKTOP-X\\tester"

    def test_current_user_id_refuses_to_guess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("USERDOMAIN", raising=False)
        monkeypatch.delenv("USERNAME", raising=False)
        with pytest.raises(windows.WindowsTaskError, match="USERDOMAIN"):
            windows.current_user_id()

    def test_plan_uses_machine_local_time_when_zones_agree(self, scratch: Path) -> None:
        config = _config()
        plan = windows.build_plan(
            config,
            now=_NOW,
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=scratch / "config.json",
            user_id="DESKTOP-X\\tester",
        )
        # Se a máquina já está no fuso configurado, as duas leituras coincidem.
        if _NOW.astimezone().utcoffset() == _NOW.astimezone(config.zone()).utcoffset():
            assert plan.machine_local_time == plan.zone_time
        assert plan.commands[0][1:3] == ("/Create", "/TN")

    def test_plan_boundary_rolls_to_tomorrow_when_the_hour_has_passed(self, scratch: Path) -> None:
        # 06:30 já passou às 12:00: o primeiro disparo tem de ser amanhã, não hoje.
        config = _config(time="06:30")
        plan = windows.build_plan(
            config,
            now=datetime(2026, 10, 14, 12, 0, tzinfo=ZoneInfo(_ZONE)),
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=scratch / "config.json",
            user_id="DESKTOP-X\\tester",
        )
        assert plan.start_boundary.startswith("2026-10-15T06:30")

    def test_register_dry_run_is_not_a_parameter_anymore(self) -> None:
        # A decisão de dry-run mora no CLI; `register` tem um trabalho só.
        assert "dry_run" not in windows.register.__code__.co_varnames

    def test_written_files_have_no_doubled_carriage_return(self, scratch: Path) -> None:
        """CRLF explícito + tradução automática do `write_text` = CR CR LF.

        Aconteceu de verdade: 8 ocorrências no `.cmd` e 40 no XML. O `cmd.exe` tolerou,
        que é justamente o que torna o defeito perigoso — funciona até alguém ler o CR
        como parte do valor.
        """
        config = _config()
        plan = windows.build_plan(
            config,
            now=_NOW,
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=scratch / "config.json",
            task_name="teste-bytes",
            user_id="DESKTOP-X\\tester",
        )
        wrapper, xml = windows.write_plan_files(plan)
        try:
            wrapper_bytes = wrapper.read_bytes()
            assert b"\r\r\n" not in wrapper_bytes
            assert b"\r\n" in wrapper_bytes
            xml_bytes = xml.read_bytes()
            assert "\r\r\n".encode("utf-16-le") not in xml_bytes
        finally:
            wrapper.unlink(missing_ok=True)
            xml.unlink(missing_ok=True)

    def test_the_plan_writes_the_wrapper_next_to_its_own_configuration(self, scratch: Path) -> None:
        """O wrapper pertence à configuração que o originou, não ao pacote.

        Foi o defeito real da S4b3-C: o plano derivava o caminho do wrapper da
        localização do PACOTE, e não da configuração. A suíte escrevia então o
        `run-daily.cmd` de produção e, na limpeza, apagava o arquivo — a tarefa
        agendada voltava a falhar sem nenhum rastro no `task.log`. Um teste não pode
        apagar o que a tarefa de produção executa.
        """
        config_path = scratch / "config.json"
        plan = windows.build_plan(
            _config(),
            now=_NOW,
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=config_path,
            task_name="teste-dono-da-config",
            user_id="DESKTOP-X\\tester",
        )
        # O diretório do wrapper é o da configuração; e o do XML, o mesmo.
        assert plan.wrapper_path.parent == scratch.resolve()
        assert plan.xml_path.parent == scratch.resolve()
        assert plan.wrapper_path.name == "run-daily.cmd"
        # E o caminho NÃO é o do pacote, que é onde a instalação de produção mora.
        assert plan.wrapper_path != windows.wrapper_path()

    def test_the_suite_does_not_touch_the_production_wrapper(self, scratch: Path) -> None:
        """A suíte escreve e limpa no scratch: o wrapper de produção fica como está.

        A segunda metade do defeito acima: o `test_written_files_have_no_doubled_carriage_return`
        apaga no `finally` o arquivo que acabou de escrever. Se esse arquivo for o
        de produção, a limpeza apaga a tarefa. Aqui o arquivo de produção é medido
        ANTES e comparado DEPOIS — e restaurado se alguma vez for tocado, para que
        uma rodada vermelha não destrua a tarefa real.
        """
        production = _PACKAGE_ROOT / "schedule" / "run-daily.cmd"
        existed = production.exists()
        before = production.read_bytes() if existed else b""
        before_mtime = production.stat().st_mtime_ns if existed else 0
        before_atime = production.stat().st_atime_ns if existed else 0
        try:
            plan = windows.build_plan(
                _config(),
                now=_NOW,
                python_exe=Path("python.exe"),
                repo_root=_REPO_ROOT,
                config_path=scratch / "config.json",
                task_name="teste-bytes",
                user_id="DESKTOP-X\\tester",
            )
            wrapper, xml = windows.write_plan_files(plan)
            try:
                # O conteúdo é o do scratch, e é lá que o teste vai limpar.
                assert wrapper == scratch.resolve() / "run-daily.cmd"
                assert b"\r\r\n" not in wrapper.read_bytes()
            finally:
                wrapper.unlink(missing_ok=True)
                xml.unlink(missing_ok=True)

            # O arquivo de produção está exatamente como estava: mesmo
            # estado, mesmos bytes, mesmo timestamp.
            assert production.exists() == existed
            if existed:
                assert production.read_bytes() == before
                assert production.stat().st_mtime_ns == before_mtime
        finally:
            # Restaura o que uma rodada com o defeito teria destruído: a tarefa
            # de produção não pertence ao teste.
            if existed:
                if not production.exists():
                    production.write_bytes(before)
                elif production.read_bytes() != before:
                    production.write_bytes(before)
                os.utime(production, ns=(before_atime, before_mtime))

    def test_a_denied_registration_names_the_real_usual_cause(self, scratch: Path) -> None:
        """A mensagem tem de apontar a causa, não um palpite.

        A primeira versão desta função culpava a falta de token de administrador, e
        estava ERRADA: a recusa vinha do XML, que pedia um gatilho de logon de
        abrangência total. Culpar o privilégio mandaria o operador caçar um problema que
        ele não tem.
        """
        config = _config()
        plan = windows.build_plan(
            config,
            now=_NOW,
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=scratch / "config.json",
            task_name="teste-negado",
            user_id="DESKTOP-X\\tester",
        )
        message = schedule_cli._register_failure_message(plan, "ERRO: Acesso negado.")
        assert "ABRANGENCIA TOTAL" in message
        assert plan.user_id in message
        assert "/Create" in message
        # E o erro cru do Windows nunca é escondido.
        assert "Acesso negado" in message

    def test_an_unrelated_registration_failure_is_not_dressed_up(self, scratch: Path) -> None:
        config = _config()
        plan = windows.build_plan(
            config,
            now=_NOW,
            python_exe=Path("python.exe"),
            repo_root=_REPO_ROOT,
            config_path=scratch / "config.json",
            user_id="DESKTOP-X\\tester",
        )
        message = schedule_cli._register_failure_message(plan, "XML malformado")
        assert message == "schtasks /Create failed: XML malformado"

    def test_describe_task_reads_the_schema_not_the_localized_report(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O relatório do Agendador é traduzido; o XML não.

        Em Windows em português, o `status` filtrava por rótulos em inglês e imprimia só
        "Status: Pronto" duas vezes. O XML tem nomes de elemento que não se traduzem.
        """
        xml = windows.task_xml(
            command="cmd.exe",
            arguments="/c wrapper.cmd",
            start_boundary="2026-10-15T06:30:00",
            user_id="DESKTOP-X\\tester",
        )

        def fake_run(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=list(arguments), returncode=0, stdout=xml, stderr="")

        monkeypatch.setattr(windows, "run_command", fake_run)
        view = windows.describe_task("qualquer")
        assert view is not None
        assert view.start_boundary == "2026-10-15T06:30:00"
        assert view.days_interval == "1"
        assert view.logon_user == "DESKTOP-X\\tester"
        assert view.start_when_available is True
        assert view.enabled is True
        assert view.command == "cmd.exe"

    def test_describe_task_returns_none_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def fake_run(arguments: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=list(arguments), returncode=1, stdout="", stderr="nao existe")

        monkeypatch.setattr(windows, "run_command", fake_run)
        assert windows.describe_task("ausente") is None


class TestCli:
    def _run(self, argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
        code = schedule_cli.main(argv)
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    def test_init_then_show_then_set(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        code, out = self._run(["init", "--config", str(config_path)], capsys)
        assert code == 0, out

        code, out = self._run(
            ["set", "--config", str(config_path), "--time", "07:15", "--time-zone", _ZONE, "--seed", "7"],
            capsys,
        )
        assert code == 0, out
        assert load_config(config_path).time_text == "07:15"

        code, out = self._run(["show", "--config", str(config_path)], capsys)
        assert code == 0
        assert "07:15" in out

    def test_init_refuses_to_overwrite(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(["init", "--config", str(config_path)], capsys)
        assert code == 1
        assert "already exists" in out

    def test_set_without_changes_is_refused(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(["set", "--config", str(config_path)], capsys)
        assert code == 1
        assert "nothing to change" in out

    def test_set_refuses_an_unknown_renderer(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(["set", "--config", str(config_path), "--renderers", "nao_existe"], capsys)
        assert code == 1
        assert "unknown renderer" in out

    def test_install_dry_run_touches_nothing(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(
            ["install", "--config", str(config_path), "--dry-run", "--task-name", "teste-nao-registrar"],
            capsys,
        )
        assert code == 0
        assert "--dry-run" in out
        assert "/Create" in out
        assert windows.query("teste-nao-registrar").returncode != 0

    def test_status_reports_config_and_ledger(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(
            ["status", "--config", str(config_path), "--state", str(scratch / "state.json"), "--task-name", "teste"],
            capsys,
        )
        assert code == 0
        assert "dias gerados" in out
        assert "nao registrada" in out

    def test_tick_outside_the_package_is_refused(self, scratch: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        self._run(["init", "--config", str(config_path)], capsys)
        code, out = self._run(
            ["tick", "--config", str(config_path), "--state", str(tmp_path / "state.json")],
            capsys,
        )
        assert code == 1
        assert "NFR-4" in out


class TestCliRealRender:
    """A cadeia inteira: config → ledger → renderer de verdade → artefato no disco.

    Um renderer barato (`focus_aws`) e um dia só: o que se prova aqui não é a
    fidelidade do artefato -- isso é assunto dos testes golden -- e sim que o
    agendador chega até ele.
    """

    def test_tick_writes_a_real_day(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        config_path = scratch / "config.json"
        out_root = scratch / "daily"
        state_path = scratch / "state.json"
        code = schedule_cli.main(["init", "--config", str(config_path)])
        assert code == 0
        code = schedule_cli.main(["set", "--config", str(config_path), "--renderers", "focus_aws", "--seed", "123"])
        assert code == 0
        capsys.readouterr()

        code = schedule_cli.main(
            [
                "tick",
                "--config",
                str(config_path),
                "--state",
                str(state_path),
                "--out",
                str(out_root),
                "--now",
                "2026-10-14T06:30:00-03:00",
            ]
        )
        out = capsys.readouterr().out
        assert code == 0, out
        assert "2026-10-13" in out

        ledger = load_state(state_path)
        assert ledger.is_complete(date(2026, 10, 13))
        assert ledger.days["2026-10-13"].artifacts > 0
        assert (out_root / "2026-10-13").is_dir()

        # Segundo tick no mesmo dia: idempotente, e não reescreve nada.
        code = schedule_cli.main(
            [
                "tick",
                "--config",
                str(config_path),
                "--state",
                str(state_path),
                "--out",
                str(out_root),
                "--now",
                "2026-10-14T18:00:00-03:00",
            ]
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "nada a gerar" in out
        assert len(load_state(state_path).completed_days()) == 1

    def test_forced_rerun_is_byte_identical(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Regerar o mesmo dia tem de reproduzir os mesmos bytes.

        É a propriedade que faz o backfill ser seguro: um dia gerado tarde não pode
        diferir de um dia gerado na hora.
        """
        from hashlib import sha256

        config_path = scratch / "config.json"
        out_root = scratch / "daily"
        state_path = scratch / "state.json"
        schedule_cli.main(["init", "--config", str(config_path)])
        schedule_cli.main(["set", "--config", str(config_path), "--renderers", "focus_aws"])
        capsys.readouterr()
        argv = [
            "tick",
            "--config",
            str(config_path),
            "--state",
            str(state_path),
            "--out",
            str(out_root),
            "--now",
            "2026-10-14T06:30:00-03:00",
        ]
        assert schedule_cli.main(argv) == 0
        capsys.readouterr()
        day_dir = out_root / "2026-10-13"
        first = {path.relative_to(day_dir).as_posix(): sha256(path.read_bytes()).hexdigest() for path in day_dir.rglob("*") if path.is_file()}
        assert schedule_cli.main([*argv, "--force"]) == 0
        capsys.readouterr()
        second = {path.relative_to(day_dir).as_posix(): sha256(path.read_bytes()).hexdigest() for path in day_dir.rglob("*") if path.is_file()}
        assert first == second

    def test_backfill_after_downtime_generates_the_gap(self, scratch: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Máquina desligada por três dias: o tick seguinte fecha o buraco."""
        config_path = scratch / "config.json"
        out_root = scratch / "daily"
        state_path = scratch / "state.json"
        schedule_cli.main(["init", "--config", str(config_path)])
        schedule_cli.main(["set", "--config", str(config_path), "--renderers", "focus_aws"])
        capsys.readouterr()

        def tick_at(moment: str) -> int:
            return schedule_cli.main(
                [
                    "tick",
                    "--config",
                    str(config_path),
                    "--state",
                    str(state_path),
                    "--out",
                    str(out_root),
                    "--now",
                    moment,
                ]
            )

        assert tick_at("2026-10-10T06:30:00-03:00") == 0
        capsys.readouterr()
        assert tick_at("2026-10-14T06:30:00-03:00") == 0
        capsys.readouterr()

        done = load_state(state_path).completed_days()
        assert done == (date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 12), date(2026, 10, 13))
        for day in done:
            assert (out_root / day.isoformat()).is_dir()


def test_scratch_root_is_inside_the_package() -> None:
    """Guarda-corpo do próprio teste: `tmp_path` não serve para os casos de CLI."""
    assert _PACKAGE_ROOT in _SCRATCH.parents


def test_default_config_time_is_early_and_lagged_by_one_day() -> None:
    config = ScheduleConfig.default()
    assert config.lag_days == 1
    assert config.enabled is True
    assert config.backfill_max_days == 31
    assert config.time_text == "06:30"
    # A distância entre o horário e o alvo é o que FR-B2 exige; nada aqui pode
    # silenciosamente virar "gere o dia de hoje".
    assert target_day_for(config, _NOW) == _NOW.date() - timedelta(days=config.lag_days)
