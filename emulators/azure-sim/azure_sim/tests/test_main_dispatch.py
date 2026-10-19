"""`python -m azure_sim` dispatch tests (FEAT-002 step 9).

``export`` with a faked blob writer runs a full slice and exits 0; unknown
subcommand / bad enum exits non-zero (fail-closed before any write).
"""

from __future__ import annotations

import azure_sim.exporter.blob_writer as blob_writer_module
from azure_sim.__main__ import main


class _FakeWriter:
    """A blob writer that records runs instead of touching Azurite."""

    instances: list[_FakeWriter] = []

    def __init__(self, *, endpoint: str, connection_string: str | None = None) -> None:
        self.endpoint = endpoint
        self.calls: list[str] = []
        _FakeWriter.instances.append(self)

    def write_run(self, *, container, run_prefix, parts, manifest) -> None:
        self.calls.append(run_prefix)


def test_export_runs_slice_and_exits_zero(monkeypatch) -> None:
    _FakeWriter.instances = []
    monkeypatch.setattr(blob_writer_module, "AzuriteBlobWriter", _FakeWriter)
    # Monthly schedule writes a single run; csv keeps it a single format.
    code = main(["export", "--schedule", "monthly", "--format", "csv"])
    assert code == 0
    assert _FakeWriter.instances, "the export never constructed a writer"
    assert _FakeWriter.instances[0].calls, "the export never wrote a run"


def test_export_bad_enum_exits_nonzero(monkeypatch) -> None:
    monkeypatch.setattr(blob_writer_module, "AzuriteBlobWriter", _FakeWriter)
    # Invalid PROFILE => ConfigError => fail-closed, non-zero, no write.
    code = main(["export", "--profile", "gigantic"])
    assert code == 1


def test_unknown_subcommand_exits_nonzero() -> None:
    try:
        main(["frobnicate"])
    except SystemExit as exc:
        # argparse errors exit with code 2 for a bad subcommand.
        assert exc.code != 0
        return
    raise AssertionError("expected a non-zero SystemExit for an unknown subcommand")
