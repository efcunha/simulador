"""FR-22 daily cadence: calendar, per-day determinism, the three axes, the CLI.

The load-bearing assertions are the determinism ones. "Day N alone equals day N
inside a range" is the property that makes a daily surface usable at all — without
it, the artifact a run produces depends on what was generated before it, and a
re-run cannot be trusted to reproduce a reported alert.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from tools.synthetic_clouds.daily import DailyWindow, build_day, days_in_range, run_days
from tools.synthetic_clouds.daily import __main__ as daily_cli
from tools.synthetic_clouds.daily.emit import emit_day
from tools.synthetic_clouds.generate.estate_builder import CANONICAL_EPOCH
from tools.synthetic_clouds.model.estate import CanonicalEstate

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE_ROOT = _REPO_ROOT / "tools" / "synthetic_clouds"

_DAY = date(2026, 3, 18)
_PROFILE = "small"
_SEED = 123
_CHEAP_RENDERER = "focus_aws"  # one renderer keeps the emission tests fast

#: The CLI enforces the NFR-4 write boundary, so its tests need an output path inside
#: the package rather than pytest's tmp_path. ``out/`` is gitignored.
#:
#: O PID no caminho nao e enfeite: sem ele, duas execucoes da suite ao mesmo tempo
#: (o normal quando varios agentes trabalham em paralelo) compartilham o diretorio,
#: e uma apaga o que a outra esta escrevendo. O sintoma e um FileNotFoundError
#: intermitente que parece defeito do gerador e nao e.
_CLI_OUT_ROOT = _PACKAGE_ROOT / "out" / "pytest-daily" / f"pid-{os.getpid()}"


def _digest(directory: Path) -> dict[str, str]:
    """Map every file under ``directory`` to its content hash, keyed by relative path."""
    return {
        path.relative_to(directory).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


@pytest.fixture(scope="module")
def day_estate() -> CanonicalEstate:
    return build_day(_SEED, _PROFILE, "USD", _DAY)


@pytest.fixture
def emissions(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path / "daily"


@pytest.fixture
def cli_out(request: pytest.FixtureRequest) -> Iterator[Path]:
    """A per-test output directory the CLI accepts, removed afterwards."""
    path = _CLI_OUT_ROOT / request.node.name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


class TestCalendar:
    def test_window_is_month_to_date(self) -> None:
        window = DailyWindow(_DAY)
        assert window.start == date(2026, 3, 1)
        assert window.days == 18  # noqa: PLR2004 - the 18th of March

    def test_first_of_month_is_a_single_day(self) -> None:
        window = DailyWindow(date(2026, 3, 1))
        assert window.start == window.day
        assert window.days == 1

    def test_month_start_is_derived_from_the_day_alone(self) -> None:
        """No prior day has to have been generated for day N to be reproducible."""
        for day in (date(2026, 2, 1), date(2026, 2, 28), date(2026, 12, 31)):
            assert DailyWindow(day).start == day.replace(day=1)

    def test_days_in_range_is_inclusive_and_ordered(self) -> None:
        assert days_in_range(date(2026, 3, 1), date(2026, 3, 3)) == (
            date(2026, 3, 1),
            date(2026, 3, 2),
            date(2026, 3, 3),
        )
        assert days_in_range(date(2026, 3, 1), date(2026, 3, 1)) == (date(2026, 3, 1),)

    def test_days_in_range_rejects_a_reversed_range(self) -> None:
        with pytest.raises(ValueError, match="precedes"):
            days_in_range(date(2026, 3, 3), date(2026, 3, 1))

    def test_canonical_epoch_is_still_the_default_window(self) -> None:
        """FR-22 must not have moved the one-shot window."""
        assert CANONICAL_EPOCH == date(2026, 1, 1)


class TestValuesAxis:
    def test_billing_covers_exactly_the_month_to_date_window(self, day_estate: CanonicalEstate) -> None:
        days = {line.charge_period_start.date() for line in day_estate.billing_lines}
        assert min(days) == date(2026, 3, 1)
        assert max(days) == _DAY
        assert len(days) == 18  # noqa: PLR2004 - one row per day per resource

    def test_consumption_carries_the_same_days(self, day_estate: CanonicalEstate) -> None:
        assert {row.usage_date for row in day_estate.consumption} == set(days_in_range(date(2026, 3, 1), _DAY))

    def test_all_three_providers_have_values(self, day_estate: CanonicalEstate) -> None:
        providers = {line.service_provider_name for line in day_estate.billing_lines}
        assert len(providers) == 3  # noqa: PLR2004 - Azure + GCP + AWS, FR-20.1


class TestAlertsAxis:
    def test_every_finding_has_arrived_by_the_emitted_day(self, day_estate: CanonicalEstate) -> None:
        assert day_estate.findings
        for finding in day_estate.findings:
            assert date(2026, 3, 1) <= finding.raised_on <= _DAY

    def test_alerts_accumulate_across_the_month(self) -> None:
        """A later day sees a superset — alerts arrive, they do not appear all at once."""
        early = build_day(_SEED, _PROFILE, "USD", date(2026, 3, 5))
        late = build_day(_SEED, _PROFILE, "USD", date(2026, 3, 25))

        def raised(estate: CanonicalEstate) -> set[date]:
            return {finding.raised_on for finding in estate.findings}

        assert raised(early) <= raised(late)
        assert len(early.findings) < len(late.findings)

    def test_alerts_span_all_three_providers(self, day_estate: CanonicalEstate) -> None:
        assert {finding.provider for finding in day_estate.findings} == {"azure", "gcp", "aws"}

    def test_findings_carry_their_markers(self, day_estate: CanonicalEstate) -> None:
        for finding in day_estate.findings:
            assert finding.source == "synthetic"
            assert finding.evidence_json.get("synthetic") is True
            assert finding.status == "open"


class TestInfrastructureAxis:
    def test_resources_and_inventory_are_present(self, day_estate: CanonicalEstate) -> None:
        assert day_estate.resources
        assert len(day_estate.inventory) == len(day_estate.resources)

    def test_infrastructure_spans_all_three_providers(self, day_estate: CanonicalEstate) -> None:
        assert {resource.identity.provider for resource in day_estate.resources} == {"azure", "gcp", "aws"}

    def test_infrastructure_is_stable_across_days(self) -> None:
        """Churn does not exist yet (design sec. 21.2), so the set must at least be stable.

        Pinned as a test so that introducing create/delete churn is a deliberate change
        that updates this assertion, rather than a silent behaviour shift.
        """
        first = build_day(_SEED, _PROFILE, "USD", date(2026, 3, 2))
        last = build_day(_SEED, _PROFILE, "USD", date(2026, 3, 25))
        assert {r.identity.uuid for r in first.resources} == {r.identity.uuid for r in last.resources}


class TestDayAddressability:
    def test_build_day_is_deterministic(self) -> None:
        first = build_day(_SEED, _PROFILE, "USD", _DAY)
        second = build_day(_SEED, _PROFILE, "USD", _DAY)
        assert first.billing_lines == second.billing_lines
        assert first.findings == second.findings
        assert first.resources == second.resources

    def test_day_alone_equals_day_inside_a_range(self, emissions: Path) -> None:
        """AC-22's core property: what a day emits cannot depend on what preceded it."""
        alone = emissions / "alone"
        emit_day(build_day(_SEED, _PROFILE, "USD", _DAY), alone, _DAY, (_CHEAP_RENDERER,))

        ranged = emissions / "ranged"
        run_days(
            _SEED,
            _PROFILE,
            "USD",
            days_in_range(date(2026, 3, 16), date(2026, 3, 18)),
            ranged,
            (_CHEAP_RENDERER,),
        )

        assert _digest(alone / _DAY.isoformat()) == _digest(ranged / _DAY.isoformat())

    def test_range_in_two_halves_equals_the_whole_range(self, emissions: Path) -> None:
        whole = emissions / "whole"
        run_days(
            _SEED,
            _PROFILE,
            "USD",
            days_in_range(date(2026, 3, 16), date(2026, 3, 18)),
            whole,
            (_CHEAP_RENDERER,),
        )

        # Same three days, generated in descending order: the tree must not care.
        halves = emissions / "halves"
        run_days(
            _SEED,
            _PROFILE,
            "USD",
            tuple(reversed(days_in_range(date(2026, 3, 16), date(2026, 3, 18)))),
            halves,
            (_CHEAP_RENDERER,),
        )

        assert _digest(whole) == _digest(halves)

    def test_no_scenarios_are_applied_to_a_daily_build(self, day_estate: CanonicalEstate) -> None:
        """Scenario windows are relative to sim_start and would drift day to day."""
        assert day_estate.scenario_ids == ()

    def test_re_running_one_day_rewrites_only_that_day(self, emissions: Path) -> None:
        run_days(
            _SEED,
            _PROFILE,
            "USD",
            days_in_range(date(2026, 3, 16), date(2026, 3, 18)),
            emissions,
            (_CHEAP_RENDERER,),
        )
        before = _digest(emissions / date(2026, 3, 16).isoformat())
        emit_day(build_day(_SEED, _PROFILE, "USD", _DAY), emissions, _DAY, (_CHEAP_RENDERER,))
        assert _digest(emissions / date(2026, 3, 16).isoformat()) == before


class TestRealDailyDeliverySemantics:
    def test_the_execution_advances_day_over_day_within_one_billing_period(self, emissions: Path) -> None:
        """This is what makes daily ingestion accumulate instead of overwrite.

        Promotion is REPLACE-per-period and the S3 reader pins the newest execution,
        so every day must deliver the same period under a strictly later execution id.
        """
        run_days(
            _SEED,
            _PROFILE,
            "USD",
            days_in_range(date(2026, 3, 17), date(2026, 3, 18)),
            emissions,
            (_CHEAP_RENDERER,),
        )
        # One execution id per delivered day. It appears twice in the tree — once
        # under ``data/`` and once under ``metadata/`` — so the assertion is on the
        # distinct ids, not on the paths.
        executions = sorted(
            {path.name for path in emissions.rglob("billing_period=*/*") if path.is_dir() and "T" in path.name},
        )
        assert len(executions) == 2  # noqa: PLR2004 - one execution per delivered day
        assert executions[0] < executions[1]
        periods = {path.name for path in emissions.rglob("billing_period=*") if path.is_dir()}
        assert periods == {"billing_period=2026-03"}

    def test_meta_records_the_day_window(self, emissions: Path) -> None:
        emit_day(build_day(_SEED, _PROFILE, "USD", _DAY), emissions, _DAY, (_CHEAP_RENDERER,))
        meta = json.loads((emissions / _DAY.isoformat() / f"{_SEED}-{_PROFILE}-USD" / "canonical" / "meta.json").read_text())
        assert meta["sim_start"] == "2026-03-01"
        assert meta["sim_now"] == _DAY.isoformat()
        assert meta["scenario_ids"] == []


class TestCli:
    def test_day_writes_a_single_day(self, cli_out: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--day",
                _DAY.isoformat(),
                "--out",
                str(cli_out),
                "--emit",
                _CHEAP_RENDERER,
            ],
        )
        assert code == 0
        assert (cli_out / _DAY.isoformat()).is_dir()
        assert "1 day(s)" in capsys.readouterr().out

    def test_range_writes_every_day(self, cli_out: Path) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--from",
                "2026-03-16",
                "--to",
                "2026-03-18",
                "--out",
                str(cli_out),
                "--emit",
                _CHEAP_RENDERER,
            ],
        )
        assert code == 0
        assert sorted(p.name for p in cli_out.iterdir()) == ["2026-03-16", "2026-03-17", "2026-03-18"]

    def test_from_without_to_is_a_single_day(self, cli_out: Path) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--from",
                "2026-03-18",
                "--out",
                str(cli_out),
                "--emit",
                _CHEAP_RENDERER,
            ],
        )
        assert code == 0
        assert [p.name for p in cli_out.iterdir()] == ["2026-03-18"]

    def test_out_outside_the_package_is_refused(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--day",
                _DAY.isoformat(),
                "--out",
                str(tmp_path / "elsewhere"),
            ],
        )
        assert code == 1
        assert "write boundary" in capsys.readouterr().err

    def test_day_and_from_together_are_refused(self, cli_out: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--day",
                _DAY.isoformat(),
                "--from",
                "2026-03-01",
                "--out",
                str(cli_out),
            ],
        )
        assert code == 1
        assert "mutually exclusive" in capsys.readouterr().err

    def test_a_date_is_required(self, cli_out: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = daily_cli.main(["--seed", str(_SEED), "--profile", _PROFILE, "--out", str(cli_out)])
        assert code == 1
        assert "--day or --from is required" in capsys.readouterr().err

    def test_unknown_renderer_is_refused(self, cli_out: Path, capsys: pytest.CaptureFixture[str]) -> None:
        code = daily_cli.main(
            [
                "--seed",
                str(_SEED),
                "--profile",
                _PROFILE,
                "--day",
                _DAY.isoformat(),
                "--out",
                str(cli_out),
                "--emit",
                "nope",
            ],
        )
        assert code == 1
        assert "unknown renderer" in capsys.readouterr().err
