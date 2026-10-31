"""FR-22 delivery namespace: the delivery must publish where the reader reads.

The failure this guards against is *silent*. ``deliver_aws`` PUTs the keys and
counts them; a PUT into a bucket nobody reads produces the same ``ok: true`` and
the same ``aws_objects: 1`` as a PUT into the right bucket. The day is
generated, the object goes up, the ingestion reports success -- and the consumer
never sees it. In S4b3-B the delivery published under
``cloudpilot-focus12-daily-full`` while the CloudPilot CUR reader was configured
for ``synthetic-focus12-daily-full``: the object was there and the cost was not.

The invariant is therefore about *names*, not about bytes: the bucket and the
export segment the delivery defaults to are the ones the renderer emits.
"""

from __future__ import annotations

import inspect
import os
from unittest import mock

from tools.synthetic_clouds.deliver import __main__ as deliver_cli
from tools.synthetic_clouds.deliver import core as deliver_core
from tools.synthetic_clouds.render import focus_aws


def test_delivery_default_namespace_is_the_name_the_renderer_emits() -> None:
    """The renderer's own name is the only namespace that can be published and read."""
    assert deliver_core.DEFAULT_AWS_BUCKET == focus_aws.EXPORT_NAME
    assert deliver_core.DEFAULT_AWS_EXPORT_NAME == focus_aws.EXPORT_NAME


def test_deliver_day_defaults_carry_the_namespace() -> None:
    """The scheduled task calls ``deliver_day()`` with no namespace, so the defaults are it."""
    params = inspect.signature(deliver_core.deliver_day).parameters
    assert params["aws_bucket"].default == focus_aws.EXPORT_NAME
    assert params["aws_export_name"].default == focus_aws.EXPORT_NAME


def test_cli_env_defaults_carry_the_namespace() -> None:
    """The CLI may override the namespace, but its fallback is not the dead name."""
    with mock.patch.dict(os.environ, {}, clear=True):
        assert deliver_cli._aws_settings() == {
            "aws_endpoint": "http://localhost:9090",
            "aws_bucket": focus_aws.EXPORT_NAME,
            "aws_prefix": "focus12-full",
            "aws_export_name": focus_aws.EXPORT_NAME,
        }
