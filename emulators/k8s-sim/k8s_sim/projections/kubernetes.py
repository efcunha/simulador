"""The Kubernetes objects the k8s-sim publishes on its API plane.

This is the second projection of the SAME synthetic estate: :mod:`k8s_sim.projections.allocation`
describes what the estate **costs** (the OpenCost allocation contract) and this module describes
what it **contains** (the objects a Kubernetes API server would list).

Both describe one estate, so their constants agree by construction: the namespace here is the
``NAMESPACE`` of the allocation projection and the workload is its ``CONTROLLER``. That is not
coincidence. The CloudPilot consumer builds a namespace's cost out of the **pods** of that
namespace (``_namespace_usage_from_pods`` in the GCP/Azure providers), so a simulator whose two
planes disagreed would publish two different truths about the same cluster.

What the estate models, and what it does not:

* **One namespace** (``payments``), **one workload** (``api``) and **one pod** (``api``).
* **The pod's requests ARE the estate's usage**: two CPU cores and four gibibytes -- the same
  figures the OpenCost allocation costs (``_CPU_CORES`` and ``_RAM_GIB`` in the allocation
  projection). The consumer sums the requests of the pods of a namespace to obtain that
  namespace's usage, so publishing anything else here would make the two planes tell different
  stories about the same cluster.
* **No limits.** The estate models no limit distinct from the request, and a limit is a promise
  the simulator cannot keep.
* **No status, no image, no resourceVersion.** The estate models the **identity** of the
  objects (their names) and the **usage** they declare; it does not model a lifecycle, a
  registry or a revision. A plausible value for any of those would assert a fact the simulator
  does not have -- the same rule the OpenCost contract follows when it refuses to publish a
  ``nodeCount`` the estate does not model. The one exception is the ``uid`` of the owner
  reference: the official model **requires** that field, so the estate has to publish
  something, and it publishes a declared placeholder rather than a minted UUID.

The wire shapes are the official ones -- ``kind``, ``apiVersion``, ``metadata`` and ``items`` --
because the CloudPilot consumer reads them with the official ``kubernetes`` client
(``CoreV1Api.list_pod_for_all_namespaces``, ``kubernetes`` 37.x), which deserializes the answer
into ``V1PodList``. Two fields of that model are **required** and are therefore always present:
``items`` on a list and ``name`` on a container.
"""

from __future__ import annotations

from typing import Any

#: The namespace the synthetic workload lives in. It is the same namespace the
#: allocation projection costs, and the test suite pins the two together.
NAMESPACE = "payments"

#: The workload inside the namespace -- the OpenCost projection's ``CONTROLLER``.
WORKLOAD = "api"

#: The pod's name. The estate models one workload served by one pod.
POD = "api"

#: The container's name. ``V1Container.name`` is a required field of the official
#: model: a container without it cannot be deserialized by the official client.
CONTAINER = "api"

#: The UID of the workload that owns the pod. The official model **requires** it --
#: ``V1OwnerReference.uid`` is a required field in the ``kubernetes`` 37.x models, and
#: the official client raises while deserializing a reference without it. The estate
#: models no object identity, so this is a declared, deterministic placeholder: it
#: says what it is instead of wearing a minted UUID it did not earn.
UID = "synthetic-deployment-api"

#: The CPU the pod requests, in cores: two cores, the same usage the allocation
#: projection costs. It is the numeric form of the estate's usage, and the Prometheus
#: projection reads it to answer the consumer's CPU query.
CPU_CORES = 2

#: The memory the pod requests, in bytes: four gibibytes, the same usage the
#: allocation projection costs. Like :data:`CPU_CORES`, it is the numeric form of the
#: estate's usage, read by the Prometheus projection.
MEMORY_BYTES = 4 * 1024**3

#: The CPU the pod requests, in Kubernetes' whole-core form: two cores. It is the
#: same number as :data:`CPU_CORES`, written the way the Kubernetes API writes a
#: quantity.
CPU_REQUEST = str(CPU_CORES)

#: The memory the pod requests: four gibibytes. It is the same number as
#: :data:`MEMORY_BYTES`, written the way the Kubernetes API writes a quantity.
MEMORY_REQUEST = f"{MEMORY_BYTES // 1024**3}Gi"


def has_namespace(namespace: str) -> bool:
    """Whether the estate has the namespace.

    A namespace the estate does not have does not exist: the request that names
    it is answered with a 404, the way an API server answers a resource that is
    not there.
    """
    return namespace == NAMESPACE


def namespace_list() -> dict[str, Any]:
    """The ``NamespaceList`` the API plane publishes.

    The payload carries the namespace's **name** -- the identity the estate
    models and the only field the consumer reads (``ConnectionTester`` counts
    the items; the GCP and Azure providers read ``metadata.name``).
    """
    return {
        "kind": "NamespaceList",
        "apiVersion": "v1",
        "metadata": {},
        "items": [_namespace(NAMESPACE)],
    }


def pod_list() -> dict[str, Any]:
    """The ``PodList`` the API plane publishes, across every namespace.

    The consumer reads the pod's namespace, its owner and the requests of its
    containers; the payload publishes exactly those.
    """
    return {
        "kind": "PodList",
        "apiVersion": "v1",
        "metadata": {},
        "items": [_pod()],
    }


def _namespace(name: str) -> dict[str, Any]:
    """One namespace of the estate.

    Only the name is published: the estate models the namespace's existence and
    its name, not its finalizers, not its phase and not its revision.
    """
    return {
        "kind": "Namespace",
        "apiVersion": "v1",
        "metadata": {"name": name},
    }


def _pod() -> dict[str, Any]:
    """The one pod of the estate.

    The pod is owned by the workload ``api``: the owner is published as a
    ``Deployment``, so the consumer reads the workload's name as ``api`` -- the
    controller the allocation projection costs. The estate does not model the
    ReplicaSet layer a real cluster puts between a Deployment and its pods, and
    publishing a hash-suffixed name would put a name in the payload that the
    OpenCost contract does not know.
    """
    return {
        "kind": "Pod",
        "apiVersion": "v1",
        "metadata": {
            "name": POD,
            "namespace": NAMESPACE,
            "ownerReferences": [
                {
                    "apiVersion": "apps/v1",
                    "kind": "Deployment",
                    "name": WORKLOAD,
                    "uid": UID,
                    "controller": True,
                }
            ],
        },
        "spec": {
            "containers": [
                {
                    "name": CONTAINER,
                    "resources": {"requests": {"cpu": CPU_REQUEST, "memory": MEMORY_REQUEST}},
                }
            ]
        },
    }
