"""Pure projections: canonical estate -> Azure wire dicts (design §5).

Every function here is a PURE projection over a frozen, gated ``CanonicalEstate``,
deterministic for a fixed seed. The projections emit ONLY native Azure inputs
(billing/inventory/findings/recommendations/prices/metrics) and NEVER a
FinOps-computed output (opportunities, drift results, budget forecasts, tag
scores, compliance verdicts). The HTTP routers in ``azure_sim.api`` serve these
dicts verbatim through the shared paging helper.
"""
