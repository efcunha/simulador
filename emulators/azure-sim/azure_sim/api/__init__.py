"""Real-shaped Azure control-plane HTTP API (design §5).

A single FastAPI app (``app.py``) mounts every router on its official base path
with ``api-version`` handling, official response envelopes, and ``nextLink`` /
``$skipToken`` / ``NextPageLink`` paging. All data is projected from the SAME
gated ``CanonicalEstate`` the exporter uses (``azure_sim.projections``), so the
API serves native inputs only — never a FinOps-computed output.
"""
