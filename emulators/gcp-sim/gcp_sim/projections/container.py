"""The GKE (Kubernetes Engine) cluster projection: the estate's ``gke_cluster`` rows.

``Cluster`` is the resource the Kubernetes Engine API returns for one cluster, and the
estate already carries one row per cluster (``generate/constants.py`` names the type
``gke_cluster``, with the GKE node SKU it bills). This module turns that row into the
published members of a ``Cluster`` and nothing else.

**The five members, and why there are five.** The REST reference publishes 87 members
on ``Cluster``; the estate answers for five of them:

* ``name`` -- the cluster's name (``Resource.resource_name``).
* ``selfLink`` -- the cluster's full resource path
  (``projects/<project>/locations/<location>/clusters/<name>``), the canonical shape
  of the path the Kubernetes Engine names a cluster by. Every segment of it is a
  field the estate carries (the project that owns the cluster, the region it sits
  in and its own name), so the path is PUBLISHED, not invented.
* ``endpoint`` -- where the cluster's master endpoint lives.
* ``location`` -- the zone or region the cluster resides in (``Resource.region_id``).
* ``masterAuth.clusterCaCertificate`` -- the public certificate that roots the
  cluster's trust, base64-encoded.

**The path is what identifies a cluster; the name alone does not.** The estate reuses
a name across projects, so ``gke_cluster-0017`` names three clusters of three
projects; the path carries the project and the location, which is what makes it the
unique key the CloudPilot needs (C-IDENT).

Every other published member is registered as unproven in
``specs/gcp/container-clusters.schema.json`` with the reason that the estate does not
model it (``currentMasterVersion``, ``nodePools``, ``network``, ...). A member the
estate cannot answer for is not emitted with a plausible-looking value: it is absent,
and the spec says so.

**The endpoint is derived, and the derivation is the point.** The reference describes
``endpoint`` as "The IP address of this cluster's master endpoint"; the estate models no
IP address, and a fabricated one would be a number the estate never asserted. So the
simulator publishes the HTTPS URL the reference itself shows the endpoint being used
at (``https://username:password@endpoint/``), with the host name derived from the
resource's own uuid: the value is then stable across calls, unique per cluster, and
names the cluster it belongs to. The divergence from the published "IP address"
wording is declared in the spec (``container-clusters.md`` sec. 5).

**The CA certificate is a real certificate, and it is deterministic.** Ed25519 is used
because its signature is deterministic by construction (RFC 8032): a certificate signed
with ECDSA or RSA carries a random nonce and would differ byte for byte between two
runs, and the contract asks for a per-cluster deterministic value. The private key is
derived from the resource uuid and never leaves the process -- the reference publishes
the certificate as the *public* root of the cluster's trust, and the key is not part of
the contract. The validity window is a fixed range, so the certificate does not depend
on the clock either.

``cryptography`` is not a declared dependency of this service: it arrives with
``google-cloud-monitoring`` -> ``google-auth``, which requires it unconditionally, and
the image installs the former.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
from functools import lru_cache
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import NameOID
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from gcp_sim import scope

#: The estate's resource type for a Kubernetes Engine cluster.
CLUSTER = "gke_cluster"

#: The location that matches every zone and every region. Published on the list method:
#: "Location "-" matches all zones and all regions".
ALL_LOCATIONS = "-"

#: The host the cluster endpoint is published under.
ENDPOINT_HOST = "container.googleapis.com"

#: The certificate's validity window: a fixed range, so the certificate does not depend
#: on the clock (a restart must not change a published value).
NOT_BEFORE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
NOT_AFTER = dt.datetime(2036, 1, 1, tzinfo=dt.UTC)

#: The organization the simulated cluster CA belongs to.
CA_ORGANIZATION = "synthetic-clouds"


def _endpoint(resource: Resource) -> str:
    """The cluster's master endpoint: an HTTPS URL derived from the resource's uuid.

    Derived, not read: the estate carries no address for the cluster. The uuid makes
    the value unique per cluster and stable across calls, and the host is the one the
    Kubernetes Engine API is served under.
    """
    return f"https://{resource.identity.uuid}.{ENDPOINT_HOST}"


@lru_cache(maxsize=512)
def _ca_certificate_pem(resource_uuid: str) -> str:
    """The PEM of the cluster's CA certificate: deterministic, and keyless.

    The private key is derived from the uuid, used to sign the certificate and dropped:
    what the API publishes is the public certificate, and a published key would be a
    secret the provider never published. Ed25519 keeps the signature deterministic, so
    the same cluster carries the same certificate in every process and every restart.
    """
    seed = hashlib.sha256(f"{resource_uuid}:gke-cluster-ca".encode()).digest()
    key = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
    name = x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, CA_ORGANIZATION),
            x509.NameAttribute(NameOID.COMMON_NAME, f"gke-cluster-ca-{resource_uuid}"),
        ]
    )
    serial = int.from_bytes(hashlib.sha256(f"{resource_uuid}:serial".encode()).digest()[:16], "big")
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(NOT_BEFORE)
        .not_valid_after(NOT_AFTER)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, None)
    )
    return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")


def _ca_certificate(resource: Resource) -> str:
    """The base64-encoded CA certificate, as the reference publishes it."""
    return base64.b64encode(_ca_certificate_pem(resource.identity.uuid).encode("ascii")).decode("ascii")


def cluster(resource: Resource, project_id: str) -> dict[str, Any]:
    """One ``Cluster`` for an estate cluster: the members the estate answers for.

    ``selfLink`` is the cluster's full path, built from the three fields the estate
    carries about it -- the project that owns it, the region it sits in and its own
    name. It is the identifier that survives a hop between two GCP calls, and the
    one a caller needs when the name alone is ambiguous (the estate reuses a name
    across projects).
    """
    return {
        "name": resource.resource_name,
        "selfLink": (
            f"projects/{project_id}/locations/{resource.region_id}/clusters/{resource.resource_name}"
        ),
        "endpoint": _endpoint(resource),
        "location": resource.region_id,
        "masterAuth": {"clusterCaCertificate": _ca_certificate(resource)},
    }


def clusters(estate: CanonicalEstate, project_id: str, location: str) -> tuple[dict[str, Any], ...]:
    """This project's clusters of one location, ordered by name.

    ``ALL_LOCATIONS`` ("-") matches every location, which is what the list method
    publishes. A project or a location the estate does not carry selects nothing: the
    emulator answers about what it owns instead of inventing a row for something it
    does not (the same rule the sibling routers take).
    """
    rows = scope.resources_of_type(estate, CLUSTER, project_id=project_id)
    if location != ALL_LOCATIONS:
        rows = tuple(row for row in rows if row.region_id == location)
    return tuple(cluster(row, project_id) for row in rows)
