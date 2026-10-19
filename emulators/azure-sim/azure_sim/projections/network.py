"""Azure Network resource plane: ``networkSecurityGroups`` — of which this estate has none.

``network_security_groups.list_all`` is consumed by a security scan:
``security.py (modulo do consumidor):107`` walks each group's
``security_rules`` looking for inbound ``Allow`` rules from ``*`` or ``0.0.0.0/0`` on a
critical port, and reports a CRITICAL finding per match. The answer here is therefore an
**empty list**, and that is the point of this module rather than an omission.

The canonical estate carries no network-security-group resource at all: the nine Azure
``resource_type`` values are defined at ``generate/constants.py:49`` and include no NSG
(``public_ip`` is the only networking entry, and a public IP is not a rule set). Both
directions of invention are wrong, and each is worth naming:

* a group with a permissive rule would hand FinOps a CRITICAL finding about a posture
  nothing in the estate records — a security report about fabricated configuration;
* a group with an empty rule list would report the subscription as scanned-and-clean,
  which is the same falsehood with the sign flipped, and ``security.py:59`` explains why
  that is worse than a failure: a subscription whose scan returns nothing must stay
  distinguishable from a subscription that was actually observed.

Absence is the answer, so the read returns no rows and the scan finds nothing to report.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate


def project_network_security_groups(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Always empty: the estate models no network security group (see module docstring)."""
    return []
