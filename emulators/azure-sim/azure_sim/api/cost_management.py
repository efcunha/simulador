"""Cost Management routers: Query, Exports, Budgets, Price Sheet, Reservations (design §5.1).

Every response is projected from the shared gated estate (native inputs only) and
list endpoints page via ``nextLink`` through ``api.paging``. The Query endpoint
returns the ``{properties:{columns,rows}, nextLink}`` envelope matching DISCOVERY
§2.3's ActualCost shape. ``Exports .../run`` executes a real export run into
Azurite via the FEAT-001 runner (an injected writer in tests).

TODO-verificar §11.6/§11.7: the exact ``api-version`` strings, the Query column
metadata, and the Budgets/Price Sheet/Reservations envelope keys are NOT offline-
verifiable; they default to the latest known shape and are flagged.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Request

from azure_sim.api.common import (
    CODE_INVALID_REQUEST,
    CODE_NOT_FOUND,
    AzureApiError,
    get_estate,
    get_settings,
    require_api_version,
)
from azure_sim.api.paging import page_rows_and_link
from azure_sim.exporter.blob_writer import AzuriteBlobWriter, BlobWriter
from azure_sim.exporter.runner import run_export
from azure_sim.projections.cost_query import project_cost_query
from azure_sim.projections.prices import project_price_sheet

router = APIRouter()

# Official api-version strings per Cost Management API. ``2025-03-01`` is the
# default the Track2 SDK in this stack sends (azure-mgmt-costmanagement 5.0.0
# pins it in ``CostManagementClientConfiguration``); the older GA versions stay
# accepted because a real deployment can call them.
# TODO-verificar §11.6/§11.7: the exact api-version strings.
_QUERY_API_VERSIONS: frozenset[str] = frozenset(
    {"2022-10-01", "2023-11-01", "2024-08-01", "2025-03-01"}
)
_EXPORTS_API_VERSIONS: frozenset[str] = frozenset({"2023-07-01-preview", "2023-08-01"})
_BUDGETS_API_VERSIONS: frozenset[str] = frozenset({"2023-11-01", "2024-08-01"})
_PRICESHEET_API_VERSIONS: frozenset[str] = frozenset({"2023-11-01", "2024-08-01"})
_RESERVATIONS_API_VERSIONS: frozenset[str] = frozenset({"2023-03-01", "2024-08-01"})

# Cost Management continuation uses the $skipToken field name (§5.2).
_TOKEN_FIELD = "$skipToken"  # noqa: S105 - a paging field name, not a credential


async def _json_body(request: Request) -> dict[str, Any]:
    """Return the parsed JSON body or raise a 400 Azure envelope on malformed input."""
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError) as exc:
        raise AzureApiError(
            400, code=CODE_INVALID_REQUEST, message="Request body is not valid JSON."
        ) from exc
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise AzureApiError(
            400, code=CODE_INVALID_REQUEST, message="Request body must be a JSON object."
        )
    return body


def _granularity(body: dict[str, Any]) -> str:
    """Extract the Query granularity (daily|monthly) from the request body (§5.4)."""
    dataset = body.get("dataset")
    raw: Any = body.get("granularity") or "daily"
    if isinstance(dataset, dict) and isinstance(dataset.get("granularity"), str):
        raw = dataset["granularity"]
    normalized = str(raw).lower()
    if normalized in {"daily", "day"}:
        return "daily"
    if normalized in {"monthly", "month"}:
        return "monthly"
    raise AzureApiError(
        400,
        code=CODE_INVALID_REQUEST,
        message=f"Unsupported granularity {raw!r}; expected daily or monthly.",
    )


def _dataset(body: dict[str, Any]) -> dict[str, Any]:
    dataset = body.get("dataset")
    return dataset if isinstance(dataset, dict) else {}


def _aggregations(body: dict[str, Any]) -> dict[str, str]:
    """Return ``{alias: measure}`` from ``dataset.aggregation`` in request order.

    The Query API names the result column after the caller's alias (CloudPilot
    asks for ``CostInBillingCurrency``) and aggregates the measure under it. A
    body without an aggregation keeps the historical single-column shape.
    """
    raw = _dataset(body).get("aggregation")
    if not isinstance(raw, dict) or not raw:
        return {"PreTaxCost": "Cost"}
    aggregations: dict[str, str] = {}
    for alias, spec in raw.items():
        name = spec.get("name") if isinstance(spec, dict) else None
        aggregations[str(alias)] = str(name or "Cost")
    return aggregations


def _grouping(body: dict[str, Any]) -> list[str] | None:
    """Return the requested dimension names, in request order.

    ``type`` is honoured: only ``Dimension`` entries become columns (a
    ``TagKey`` grouping is not a dimension this estate can project). ``None``
    means "no grouping in the body", so the projection keeps its default set.
    """
    raw = _dataset(body).get("grouping")
    if not isinstance(raw, list):
        return None
    dimensions: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("type", "Dimension")).lower() not in {"dimension", ""}:
            continue
        name = entry.get("name")
        if not name or not isinstance(name, str):
            continue
        if name not in dimensions:
            dimensions.append(name)
    return dimensions or None


def _iso_day(value: Any) -> date | None:
    """Parse an ISO-8601 day (``YYYY-MM-DD`` or a full timestamp) or return None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _time_window(body: dict[str, Any]) -> tuple[date | None, date | None]:
    """Return the ``(from, to)`` requested by the Query body, when it has one.

    The real Cost Management Query API honours ``timePeriod``: a ``CUSTOM``
    query returns only the rows inside the requested window. The projection
    here is built from the whole estate, so without this cut the simulator
    answered every query with the same first page — a caller asking for
    October received January, and the mismatch was invisible until the
    promoted dates were inspected.
    """
    raw = body.get("timePeriod")
    if not isinstance(raw, dict):
        return None, None
    return _iso_day(raw.get("from")), _iso_day(raw.get("to"))


def _in_window(row: object, start: date | None, end: date | None, date_index: int) -> bool:
    """Whether a projected row's UsageDate falls in ``[start, end)``."""
    if start is None and end is None:
        return True
    if not isinstance(row, list) or len(row) <= date_index:
        return False
    day = _iso_day(row[date_index])
    if day is None:
        return False
    if start is not None and day < start:
        return False
    return not (end is not None and day >= end)


# Name of the query parameter carrying the original body inside a ``nextLink``.
# The real service keeps that state server-side; the simulator encodes it in the
# link so a plain ``GET`` of ``nextLink`` can rebuild the exact same page without
# state shared between requests (the API may run with more than one worker).
_CONTINUATION_BODY_PARAM = "$query"


def _continuation_url(request: Request, body: dict[str, Any]) -> str:
    """Return the request URL carrying ``body`` for GET-based continuation."""
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    token = base64.urlsafe_b64encode(raw).decode("ascii")
    parts = urlsplit(str(request.url))
    query = parse_qs(parts.query, keep_blank_values=True)
    query[_CONTINUATION_BODY_PARAM] = [token]
    flat = urlencode(query, doseq=True)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, flat, parts.fragment))


def _continuation_body(request: Request) -> dict[str, Any]:
    """Decode the ``$query`` parameter of a ``nextLink`` GET (400 on garbage)."""
    token = request.query_params.get(_CONTINUATION_BODY_PARAM)
    if not token:
        return {}
    try:
        # The link carries the token unpadded (URL-friendly); restore the
        # padding ``urlsafe_b64decode`` requires.
        padded = token + "=" * (-len(token) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        body = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        raise AzureApiError(
            400, code=CODE_INVALID_REQUEST, message="Malformed continuation link."
        ) from exc
    return body if isinstance(body, dict) else {}


def _query_response(request: Request, body: dict[str, Any]) -> dict[str, Any]:
    """Project one Query page; shared by the POST and the continuation GET."""
    granularity = _granularity(body)
    aggregations = _aggregations(body)
    dimensions = _grouping(body)
    estate = get_estate(request)
    settings = get_settings(request)
    projected = project_cost_query(
        estate,
        granularity=granularity,
        aggregations=aggregations,
        dimensions=dimensions,
    )
    start, end = _time_window(body)
    date_index = len(aggregations)  # UsageDate follows the aggregation columns
    rows: list[object] = [
        row for row in projected["rows"] if _in_window(row, start, end, date_index)
    ]
    # A continuation GET already carries ``$query`` in its own URL; adding it
    # again would grow the link on every page.
    base_url = (
        str(request.url)
        if _CONTINUATION_BODY_PARAM in request.query_params
        else _continuation_url(request, body)
    )
    page_rows, next_link = page_rows_and_link(
        rows, page_size=settings.api_page_size, request_url=base_url, token_field=_TOKEN_FIELD
    )
    return {
        "properties": {"columns": projected["columns"], "rows": page_rows},
        "nextLink": next_link,
    }


@router.post("/providers/Microsoft.CostManagement/query")
@router.post("/{scope:path}/providers/Microsoft.CostManagement/query")
async def cost_query(request: Request, scope: str = "") -> dict[str, Any]:
    """Return the ``{properties:{columns,rows}, nextLink}`` ActualCost envelope (§5.1)."""
    require_api_version(request, _QUERY_API_VERSIONS)
    body = await _json_body(request)
    return _query_response(request, body)


@router.get("/providers/Microsoft.CostManagement/query")
@router.get("/{scope:path}/providers/Microsoft.CostManagement/query")
async def cost_query_continuation(request: Request, scope: str = "") -> dict[str, Any]:
    """Serve the page a ``nextLink`` points at (the real API continues with GET).

    The link is a full URL into this same route; the original query body travels
    in ``$query`` and the row offset in ``$skipToken`` (``api.paging``).
    """
    require_api_version(request, _QUERY_API_VERSIONS)
    return _query_response(request, _continuation_body(request))


# --- Exports CRUD + execute --------------------------------------------------


def _exports_store(request: Request) -> dict[str, dict[str, Any]]:
    """Return the in-memory export-definition store (native definitions only)."""
    store: dict[str, dict[str, Any]] | None = getattr(request.app.state, "exports", None)
    if store is None:
        store = {}
        request.app.state.exports = store
    return store


@router.get("/{scope:path}/providers/Microsoft.CostManagement/exports")
async def list_exports(request: Request, scope: str = "") -> dict[str, Any]:
    """List native export definitions (``value[]`` envelope)."""
    require_api_version(request, _EXPORTS_API_VERSIONS)
    store = _exports_store(request)
    return {"value": [dict(value) for _, value in sorted(store.items())]}


@router.get("/{scope:path}/providers/Microsoft.CostManagement/exports/{export_name}")
async def get_export(request: Request, export_name: str, scope: str = "") -> dict[str, Any]:
    """Get one native export definition or a 404 Azure envelope."""
    require_api_version(request, _EXPORTS_API_VERSIONS)
    store = _exports_store(request)
    if export_name not in store:
        raise AzureApiError(404, code=CODE_NOT_FOUND, message=f"Export {export_name!r} not found.")
    return dict(store[export_name])


@router.put("/{scope:path}/providers/Microsoft.CostManagement/exports/{export_name}")
async def put_export(request: Request, export_name: str, scope: str = "") -> dict[str, Any]:
    """Create/replace a native export definition (native config only).

    The stored definition is ``name`` + ``properties`` only: a ``synthetic`` key is
    not a field any ``Microsoft.CostManagement/exports`` payload defines, and the
    provenance a reader needs lives in the estate the rows project from (the
    ``[SYNTH] `` account names ``api/token.py`` and the manifest markers cover),
    not in a key invented per response.
    """
    require_api_version(request, _EXPORTS_API_VERSIONS)
    body = await _json_body(request)
    definition = {"name": export_name, "properties": body.get("properties", {})}
    _exports_store(request)[export_name] = definition
    return dict(definition)


def _export_writer(request: Request, settings: Any) -> BlobWriter:
    """Return the injected test writer if present, else a real Azurite writer."""
    injected: BlobWriter | None = getattr(request.app.state, "export_writer", None)
    if injected is not None:
        return injected
    return AzuriteBlobWriter(endpoint=settings.azure_blob_endpoint)


@router.post("/{scope:path}/providers/Microsoft.CostManagement/exports/{export_name}/run")
async def run_export_endpoint(request: Request, export_name: str, scope: str = "") -> dict[str, Any]:
    """Execute an export run into Azurite via the FEAT-001 runner (§5.1).

    ``status``/``runPrefixes`` are the whole payload: the run's own result, with no
    invented ``synthetic`` key (see ``put_export``).
    """
    require_api_version(request, _EXPORTS_API_VERSIONS)
    estate = get_estate(request)
    settings = get_settings(request)
    prefixes = run_export(estate, settings, _export_writer(request, settings))
    return {"status": "Completed", "runPrefixes": prefixes}


# --- Budgets (native definitions only) ---------------------------------------


def _budgets_store(request: Request) -> dict[str, dict[str, Any]]:
    """Return the in-memory budget-definition store (native definitions only)."""
    store: dict[str, dict[str, Any]] | None = getattr(request.app.state, "budgets", None)
    if store is None:
        store = {}
        request.app.state.budgets = store
    return store


@router.get("/{scope:path}/providers/Microsoft.Consumption/budgets/{budget_name}")
async def get_budget(request: Request, budget_name: str, scope: str = "") -> dict[str, Any]:
    """Get a native budget definition or a 404 Azure envelope."""
    require_api_version(request, _BUDGETS_API_VERSIONS)
    store = _budgets_store(request)
    if budget_name not in store:
        raise AzureApiError(404, code=CODE_NOT_FOUND, message=f"Budget {budget_name!r} not found.")
    return dict(store[budget_name])


@router.put("/{scope:path}/providers/Microsoft.Consumption/budgets/{budget_name}")
async def put_budget(request: Request, budget_name: str, scope: str = "") -> dict[str, Any]:
    """Create/replace a native budget DEFINITION (thresholds/notifications only).

    This is a native budget definition — NOT a FinOps budget evaluation or
    forecast (P1). FinOps computes any over/under verdict from these inputs.
    No invented ``synthetic`` key: see ``put_export``.
    """
    require_api_version(request, _BUDGETS_API_VERSIONS)
    body = await _json_body(request)
    definition = {"name": budget_name, "properties": body.get("properties", {})}
    _budgets_store(request)[budget_name] = definition
    return dict(definition)


# --- Price Sheet --------------------------------------------------------------


@router.post("/{scope:path}/providers/Microsoft.CostManagement/pricesheet")
async def price_sheet(request: Request, scope: str = "") -> dict[str, Any]:
    """Return the native Price Sheet rows from contracted prices (§5.1)."""
    require_api_version(request, _PRICESHEET_API_VERSIONS)
    estate = get_estate(request)
    settings = get_settings(request)
    rows: list[object] = list(project_price_sheet(estate))
    page_rows, next_link = page_rows_and_link(
        rows, page_size=settings.api_page_size, request_url=str(request.url), token_field=_TOKEN_FIELD
    )
    return {"properties": {"pricesheets": page_rows}, "nextLink": next_link}


# --- Reservations summaries/details -------------------------------------------


def _reservation_rows(estate: Any) -> list[dict[str, Any]]:
    """Project commitments into reservation summary rows (Used/Unused, C05/C16)."""
    rows: list[dict[str, Any]] = []
    for commitment in estate.commitments:
        rows.append(
            {
                "reservationId": commitment.identity.uuid,
                "kind": commitment.kind,
                "scopeId": commitment.scope_id,
                # Native CommitmentDiscountStatus (Used|Unused) — a native input.
                "usageStatus": commitment.status,
                "committedAmount": float(commitment.committed_amount),
            }
        )
    return sorted(rows, key=lambda row: str(row["reservationId"]))


@router.get("/providers/Microsoft.Capacity/reservations")
async def list_reservations(request: Request) -> dict[str, Any]:
    """Return reservation summaries from estate commitments (native Used/Unused)."""
    require_api_version(request, _RESERVATIONS_API_VERSIONS)
    estate = get_estate(request)
    settings = get_settings(request)
    rows: list[object] = list(_reservation_rows(estate))
    page_rows, next_link = page_rows_and_link(
        rows, page_size=settings.api_page_size, request_url=str(request.url), token_field=_TOKEN_FIELD
    )
    return {"value": page_rows, "nextLink": next_link}
