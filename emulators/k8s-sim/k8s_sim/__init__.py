"""k8s-sim: the OpenCost allocation contract for one synthetic AKS cluster (Phase S4a).

Where ``aws-sim``, ``gcp-sim`` and ``azure-sim`` project a *canonical estate* onto a
cloud provider's own protocol, this package projects a **fixed synthetic workload** onto
the OpenCost allocation protocol. The wire shape is OpenCost's, the numbers are not
OpenCost's: they are synthetic and they do not reconcile billing.

The contract this package serves is documented in
``docs/k8s-sim-opencost-contract.md``, which cites the official OpenCost sources the
shape was read from and records every place where this phase narrows or deviates from
them.

Nothing here reads a clock, a database, a price list or the network: the payload is a
pure function of the requested window, which is what makes two identical calls return
identical bytes.
"""

from __future__ import annotations

from k8s_sim.app import create_app

__all__ = ["create_app"]
