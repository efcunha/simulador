"""Which types the estate meters, and that each series is keyed to its own resource.

Two properties, both load-bearing:

1. The AWS types the CloudWatch shim can answer about (``ec2_instance``,
   ``rds_instance``) actually carry a series. Before this, every series belonged to an
   Azure or GCP resource, so ``emulators/aws-sim`` answered every CloudWatch call
   well-formed but empty and FinOps AWS observability and rightsizing screens read
   nothing.

2. A series is a pure function of ``(seed, resource, metric)`` — drawn from
   ``stream_rng(seed, "metric/<resource uuid>")`` — and not of how many other metered
   resources happen to exist. That is what stops one provider's types from perturbing
   another's when the metered set grows, which is exactly the change that added AWS here.

A third property is asserted here too: the samples are **percentages** (0..100), the unit
every consumer declares for these metrics, and they spread across both sides of
``RightsizingAnalyzer(cpu_threshold_pct=20.0)`` and all three of ``_classify_severity``'s
bands. See ``generate/estate_builder._CPU_UTILIZATION_BANDS``.

A fourth: ``ec2_instance`` carries a second series, ``memory_utilization``, and no other
type does. It is there because FinOps rightsizing provider refuses a window whose
memory lookup came back empty (``cloudwatch_metrics_provider.get_utilization``), so memory
is the precondition of every CPU verdict — and the only AWS type that consumer asks memory
for is the EC2 instance (``rightsizing_detector._inventory_to_specs`` reads
``inventory["EC2"]``). See ``generate/estate_builder._MEMORY_METERED_RESOURCE_TYPES``.

A fifth: the cadence is **HOURLY** — 24 points per day, on the hour, UTC — and the intra-day
shape is a daily cycle whose peak factor is exactly 1.0. Both halves are the consumer's,
not the estate's: the rightsizing provider asks CloudWatch with ``Period=3600`` and prices
the window in hours (``expected_samples = (end - start) // 3600``), so a series holding one
point per day scores 1/24 = 4.17% coverage and is refused before the analyzer ever sees it.
See ``generate/estate_builder._METRIC_HOURS_PER_DAY``.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from tools.synthetic_clouds.determinism import stream_rng
from tools.synthetic_clouds.generate.estate_builder import (
    _CPU_UTILIZATION,
    _MEMORY_METERED_RESOURCE_TYPES,
    _MEMORY_UTILIZATION,
    _METRIC_HOURS_PER_DAY,
    _METRIC_INTRADAY_SHAPE,
    _cpu_utilization_band,
    _memory_utilization_band,
    build_estate,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.metrics import MetricPoint
from tools.synthetic_clouds.model.resource import Resource

_SEED = 123
_PROFILE = "small"


def _index(estate: CanonicalEstate) -> dict[str, Resource]:
    return {resource.identity.uuid: resource for resource in estate.resources}


def _types_with_series(estate: CanonicalEstate) -> set[str]:
    index = _index(estate)
    return {index[series.resource_uuid].resource_type for series in estate.metrics}


def test_aws_types_that_the_cloudwatch_shim_can_name_are_metered() -> None:
    """``ec2_instance`` and ``rds_instance``: the pair both AWS consumers agree on.

    ``aws_sim.projections.cloudwatch._NAMESPACE`` can express these two and no other AWS
    type, and FinOps ``aws_ec2``/``aws_rds`` templates plus the rightsizing CPU
    query ask for exactly them. Before AWS was metered this set was empty and the
    CloudWatch endpoint answered ``Metrics: []`` for every request.
    """
    metered = _types_with_series(build_estate(_SEED, _PROFILE, "USD"))
    assert {"ec2_instance", "rds_instance"} <= metered


def test_every_series_belongs_to_a_metered_resource() -> None:
    """One CPU series per metered resource, one memory series per memory-metered one.

    Also pins the metered set, so metering a type the CloudWatch shim cannot name
    (``lambda_function``, ``s3_bucket``, …) has to be a deliberate edit here rather than
    a silent widening that leaves a projection guessing a namespace.
    """
    estate = build_estate(_SEED, _PROFILE, "USD")
    index = _index(estate)

    assert {series.metric_name for series in estate.metrics} == {_CPU_UTILIZATION, _MEMORY_UTILIZATION}
    assert _types_with_series(estate) == {
        "virtual_machine",
        "sql_database",
        "compute_instance",
        "cloud_sql",
        "ec2_instance",
        "rds_instance",
    }

    metered = [r for r in estate.resources if r.resource_type in _types_with_series(estate)]
    cpu_series = [s for s in estate.metrics if s.metric_name == _CPU_UTILIZATION]
    memory_series = [s for s in estate.metrics if s.metric_name == _MEMORY_UTILIZATION]
    # Every metered resource carries CPU; only the memory-metered types carry memory, and
    # every one of those carries exactly one memory series.
    assert {s.resource_uuid for s in cpu_series} == {r.identity.uuid for r in metered}
    assert len(cpu_series) == len(metered)
    assert {index[s.resource_uuid].resource_type for s in memory_series} == set(_MEMORY_METERED_RESOURCE_TYPES)
    assert len(memory_series) == len(
        [r for r in metered if r.resource_type in _MEMORY_METERED_RESOURCE_TYPES],
    )
    assert len(estate.metrics) == len(metered) + len(memory_series)
    # Every series resolves to a real resource: no orphan (F2 in validate/integrity.py).
    assert all(series.resource_uuid in index for series in estate.metrics)


def test_types_no_consumer_can_name_carry_no_series() -> None:
    """The absence half: a type with no series is why its endpoint answers empty."""
    estate = build_estate(_SEED, _PROFILE, "USD")
    index = _index(estate)
    unmetered_aws = {"s3_bucket", "lambda_function", "application_lb", "ecs_cluster", "dynamodb_table"}

    assert unmetered_aws <= {r.resource_type for r in estate.resources}
    assert not (unmetered_aws & {index[s.resource_uuid].resource_type for s in estate.metrics})


def _expected_points(
    resource_uuid: str,
    metric_name: str,
    timestamps: tuple[datetime, ...],
) -> tuple[MetricPoint, ...]:
    """Rebuild one series' points from the per-resource stream alone.

    Deliberately the same steps ``_build_metrics`` takes — the workload band this
    resource's stream picks, then one draw per point of the window, each scaled by its
    hour's factor from ``_METRIC_INTRADAY_SHAPE`` — so a series that came from anywhere
    else could not match. The CPU band and its samples are consumed first, for every
    resource, because that is the order ``_build_metrics`` draws in: a memory series is
    the SECOND pair of draws on the same stream.
    """
    rng = stream_rng(_SEED, f"metric/{resource_uuid}")
    low, high = _cpu_utilization_band(rng)
    cpu_points = tuple(
        MetricPoint(ts=ts, value=round(rng.uniform(low, high) * _METRIC_INTRADAY_SHAPE[ts.hour], 4))
        for ts in timestamps
    )
    if metric_name == _CPU_UTILIZATION:
        return cpu_points
    memory_low, memory_high = _memory_utilization_band(rng)
    return tuple(
        MetricPoint(
            ts=ts,
            value=round(rng.uniform(memory_low, memory_high) * _METRIC_INTRADAY_SHAPE[ts.hour], 4),
        )
        for ts in timestamps
    )


def _expected_band(
    resource_uuid: str,
    metric_name: str,
    points_per_series: int,
) -> tuple[float, float]:
    """The workload band ``_build_metrics`` drew for this series, in its own draw order.

    The stream is walked the way the builder walks it — the CPU band, the CPU's sample
    draws, and only then (for a memory series) the memory band — so a memory series
    cannot be handed the CPU band by mistake.
    """
    rng = stream_rng(_SEED, f"metric/{resource_uuid}")
    cpu_low, cpu_high = _cpu_utilization_band(rng)
    if metric_name == _CPU_UTILIZATION:
        return cpu_low, cpu_high
    for _ in range(points_per_series):
        _ = rng.uniform(cpu_low, cpu_high)
    return _memory_utilization_band(rng)


def test_series_values_come_from_the_per_resource_stream() -> None:
    """The keying assertion: rebuild each series from ``metric/<uuid>`` alone.

    If the draws were positional (one stream shared in visit order) this reconstruction
    could not match, because it has no idea which other resources were metered — which is
    exactly the coupling the per-resource key removes.
    """
    estate = build_estate(_SEED, _PROFILE, "USD")
    assert estate.metrics
    assert {series.metric_name for series in estate.metrics} == {_CPU_UTILIZATION, _MEMORY_UTILIZATION}

    for series in estate.metrics:
        timestamps = tuple(point.ts for point in series.points)
        assert series.points == _expected_points(series.resource_uuid, series.metric_name, timestamps)


def test_two_resources_of_one_type_do_not_share_a_value() -> None:
    """A shared per-type stream would give every instance the same series; this one does not."""
    estate = build_estate(_SEED, _PROFILE, "USD")
    index = _index(estate)
    ec2 = [s for s in estate.metrics if index[s.resource_uuid].resource_type == "ec2_instance"]

    assert len(ec2) > 1
    assert len({s.points for s in ec2}) == len(ec2)


def test_points_land_on_every_hour_of_the_window() -> None:
    """The sample cadence is every hour of every day: 24 points per day, on the hour, UTC.

    Hourly rather than daily because that is the grain the AWS consumer reads at:
    ``cloudwatch_metrics_provider`` asks CloudWatch with ``Period=3600``, prices the
    window in hours (``expected_samples = (end - start) // 3600``) and refuses anything
    under ``MIN_COVERAGE_PERCENT``. A one-point-per-day series can only ever
    score 1/24 = 4.17%, so the estate has to answer in the consumer's own grain.
    """
    estate = build_estate(_SEED, _PROFILE, "USD")
    expected_days = (estate.sim_now - estate.sim_start).days + 1

    for series in estate.metrics:
        assert len(series.points) == expected_days * _METRIC_HOURS_PER_DAY
        assert [point.ts.date() for point in series.points] == [
            date.fromordinal(estate.sim_start.toordinal() + offset)
            for offset in range(expected_days)
            for _hour in range(_METRIC_HOURS_PER_DAY)
        ]
        assert [point.ts.hour for point in series.points] == list(range(_METRIC_HOURS_PER_DAY)) * expected_days
        # Stamped at the hour it measures, with no minute or second offset, so an
        # hourly bucket on the shim's side holds exactly one sample.
        assert all(
            point.ts == datetime.combine(point.ts.date(), time(point.ts.hour), tzinfo=UTC)
            for point in series.points
        )
        assert all(0.0 < point.value <= 100.0 for point in series.points)


def test_the_daily_cycle_shapes_the_day_without_lifting_a_peak_out_of_its_band() -> None:
    """The intra-day shape, and the two properties the detector depends on.

    ``RightsizingAnalyzer`` judges a resource on the window's PEAK — ``avg_cpu_pct`` is
    fed the CloudWatch ``p95`` and ``_fetch_metrics`` keeps the ``max()`` — so the shape
    is what the verdict is read from, and both of its ends matter:

    * the peak factor is 1.0, which is what keeps a series' maximum at the top of the
      resource's workload band instead of above it. A factor over 1.0 would lift every
      band over the thresholds ``_CPU_UTILIZATION_BANDS`` was placed against and hand
      the whole estate one verdict;
    * the cycle is a real curve, not a flat day: 24 identical values would make the
      intra-day structure a fiction the moment anything read it hour by hour.
    """
    estate = build_estate(_SEED, _PROFILE, "USD")

    assert len(_METRIC_INTRADAY_SHAPE) == _METRIC_HOURS_PER_DAY
    assert max(_METRIC_INTRADAY_SHAPE) == 1.0, "a peak factor above 1.0 leaves the band"
    assert min(_METRIC_INTRADAY_SHAPE) > 0.0, "a running instance never drops to zero"
    assert len(set(_METRIC_INTRADAY_SHAPE)) > 1, "a flat day is not a cycle"
    # A realistic swing — the trough carries just over half of the peak's load — so the
    # hour a sample is taken in genuinely shapes the day.
    assert max(_METRIC_INTRADAY_SHAPE) / min(_METRIC_INTRADAY_SHAPE) > 1.5

    for series in estate.metrics:
        low, high = _expected_band(series.resource_uuid, series.metric_name, len(series.points))
        values = [point.value for point in series.points]
        peak = max(values)
        # The number the detector reads is the top of the resource's band, never above it.
        assert low <= peak <= high
        # And it comes from the top half of that band: the peak hour of the window draws
        # afresh every day, so the window's maximum sits near `high`.
        assert peak > (low + high) / 2
        # The day is not 24 identical values.
        assert len(set(values[: _METRIC_HOURS_PER_DAY])) > 1


def test_a_resource_keeps_its_series_across_a_rebuild() -> None:
    """Determinism: same seed, same series — values included, not just uuids."""
    first = build_estate(_SEED, _PROFILE, "USD")
    second = build_estate(_SEED, _PROFILE, "USD")

    assert first.metrics == second.metrics


def test_the_daily_and_the_one_shot_surfaces_agree() -> None:
    """The same window built two ways yields the same series.

    ``build_estate`` with an explicit window is what the daily cadence calls, and the
    per-resource key is what makes its series a function of the window rather than of what
    was generated before it.
    """
    one_shot = build_estate(_SEED, _PROFILE, "USD")
    same_window = build_estate(
        _SEED,
        _PROFILE,
        "USD",
        sim_start=one_shot.sim_start,
        window_days=(one_shot.sim_now - one_shot.sim_start).days + 1,
    )

    assert same_window.metrics == one_shot.metrics


def test_metering_one_type_does_not_move_another_types_values() -> None:
    """The regression this keying exists to prevent.

    Recompute one Azure series and one GCP series from their own named streams, and a
    third series from an AWS resource's own stream: all three match. Under the positional
    stream the AWS draws (consumed last) would have left the Azure/GCP ones intact by luck
    of visit order only — the reverse order would have re-rolled them, which is what adding
    a provider's types mid-catalog would have done.
    """
    estate = build_estate(_SEED, _PROFILE, "USD")
    index = _index(estate)
    wanted = {"virtual_machine": "azure", "compute_instance": "gcp", "ec2_instance": "aws"}
    checked: set[str] = set()

    for series in estate.metrics:
        resource = index[series.resource_uuid]
        if wanted.get(resource.resource_type) != resource.identity.provider:
            continue
        timestamps = tuple(point.ts for point in series.points)
        assert series.points == _expected_points(series.resource_uuid, series.metric_name, timestamps)
        checked.add(resource.resource_type)

    assert checked == set(wanted)


def _severity(peak_pct: float) -> str:
    """The band ``RightsizingAnalyzer._classify_severity`` would name for a flagged peak."""
    if peak_pct <= 8.0:
        return "HIGH"
    if peak_pct <= 14.0:
        return "MEDIUM"
    return "LOW"


def test_cpu_utilization_samples_are_percentages_on_both_sides_of_the_detector_threshold() -> None:
    """The unit, asserted on the values themselves rather than on a consumer's copy.

    Every consumer declares this metric ``Percent`` and forwards the sample verbatim
    (``aws_sim/projections/cloudwatch.py`` under FinOps ``"Unit": "Percent"`` query,
    ``azure_sim/projections/metrics.py`` as Monitor's ``average`` beside a
    ``"Percent"`` definition). The estate used to emit a FRACTION
    (``uniform(0.02, 0.9)``) under those declarations, so every metered resource read as
    under 1% CPU — a whole estate the rightsizing analyzer at its
    ``cpu_threshold_pct=20.0`` classifies HIGH/idle, which is what this pins shut.

    The analyzer reads the window's PEAK sample (``avg_cpu_pct`` is fed the CloudWatch
    p95 and ``_fetch_metrics`` keeps the ``max()``), so the thresholds are checked against
    per-series maxima: 20.0 is the flag cutoff and 8 / 14 are ``_classify_severity``'s
    ceilings (``analyzer.py (modulo do consumidor)``).
    """
    estate = build_estate(_SEED, _PROFILE, "USD")
    samples = [point.value for series in estate.metrics for point in series.points]
    peaks = [max(point.value for point in series.points) for series in estate.metrics]
    flagged = [peak for peak in peaks if peak < 20.0]

    assert samples, "the estate meters resources, so there are samples to check"
    assert all(0.0 < value <= 100.0 for value in samples), "a Percentage, not a fraction"
    # No fraction-scale estate could produce a sample above 1%: this is the bug, pinned.
    assert max(samples) > 1.0
    # Both halves exist, and neither is the whole estate: idle resources for the detector
    # to find, plus ordinary production it must refuse to flag.
    assert flagged
    assert len(flagged) < len(peaks)
    # Every severity band the analyzer can name is reachable from this mixture. Shrinking
    # ``_CPU_UTILIZATION_BANDS`` so a band empties has to be a deliberate edit here.
    assert {_severity(peak) for peak in flagged} == {"HIGH", "MEDIUM", "LOW"}
