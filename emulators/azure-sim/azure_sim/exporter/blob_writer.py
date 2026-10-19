"""Blob writer into Azurite with manifest-last commit (design §4.7).

Uploads a run's parts to a staging prefix and writes ``manifest.json`` LAST, so
Phase 4 ingestion treats a window folder without a manifest as not-yet-complete
(never a partial commit). Transient 5xx responses are retried with bounded
backoff; any other failure is fatal and surfaces to the runner, which fails
closed before reporting success.

The ``azure-storage-blob`` SDK is imported lazily so this module (and the runner
that imports it) stays importable in environments where the SDK is absent — the
runner's unit tests inject a fake writer and never touch the real client. The
real client is constructed only inside :class:`AzuriteBlobWriter.__init__`.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from azure_sim.exporter.focus_export import LaidOutPart
from azure_sim.exporter.layout import manifest_blob_name, part_blob_name

# Azurite dev storage account connection string TEMPLATE. ``devstoreaccount1``
# and the account key below are the emulator's PUBLISHED default identity
# (documented by Microsoft, identical in every Azurite install) — not a secret,
# and never a real Azure credential. Overridable per call through the
# ``connection_string`` argument for any non-emulator deployment.
#
# AccountKey is mandatory: Azurite authenticates with SharedKey, so a connection
# string without it produces an unsigned request and the emulator answers
# ``AuthorizationFailure`` ("Server failed to authenticate the request").
_AZURITE_DEV_CONNECTION = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint={endpoint};"
)

_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 0.2


class BlobWriter(Protocol):
    """Minimal writer contract the runner depends on (fakeable in tests)."""

    def write_run(
        self, *, container: str, run_prefix: str, parts: list[LaidOutPart], manifest: dict[str, Any]
    ) -> None:
        """Upload parts then the manifest LAST for one run."""
        ...


@dataclass(slots=True)
class WriteResult:
    """Record of what a run wrote (useful for tests and logging)."""

    container: str
    run_prefix: str
    part_names: list[str]
    manifest_name: str


def _is_transient(status_code: int | None) -> bool:
    """Return True for retryable transient server errors (5xx)."""
    return status_code is not None and 500 <= status_code < 600


class AzuriteBlobWriter:
    """Concrete ``BlobWriter`` backed by ``azure-storage-blob`` against Azurite."""

    def __init__(self, *, endpoint: str, connection_string: str | None = None) -> None:
        from azure.storage.blob import BlobServiceClient  # lazy import (SDK optional)

        conn = connection_string or _AZURITE_DEV_CONNECTION.format(endpoint=endpoint)
        self._service = BlobServiceClient.from_connection_string(conn)

    def _ensure_container(self, container: str) -> None:
        from azure.core.exceptions import ResourceExistsError  # lazy import

        try:
            self._service.create_container(container)
        except ResourceExistsError:
            pass  # idempotent create (§4.7)

    def _upload_with_retry(self, container: str, blob_name: str, data: bytes) -> None:
        from azure.core.exceptions import HttpResponseError  # lazy import

        client = self._service.get_blob_client(container=container, blob=blob_name)
        attempt = 0
        while True:
            try:
                client.upload_blob(data, overwrite=True)
                return
            except HttpResponseError as exc:
                attempt += 1
                if attempt > _MAX_RETRIES or not _is_transient(getattr(exc, "status_code", None)):
                    raise
                time.sleep(_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))

    def write_run(
        self, *, container: str, run_prefix: str, parts: list[LaidOutPart], manifest: dict[str, Any]
    ) -> None:
        """Create the container idempotently, upload parts, then the manifest LAST."""
        self._ensure_container(container)
        for part in parts:
            self._upload_with_retry(container, part_blob_name(run_prefix, part.file_name), part.data)
        manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._upload_with_retry(container, manifest_blob_name(run_prefix), manifest_bytes)
