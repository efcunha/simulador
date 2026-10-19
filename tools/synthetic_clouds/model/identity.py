"""Stable resource identity (P2) and the factory that mints it.

One ``ResourceIdentity`` per logical resource, derived deterministically from
``(seed, logical_path)`` via UUIDv5. The same ``uuid`` threads unchanged through
every record that references the resource (resource, consumption, billing,
inventory, finding, recommendation, metric, IaC) — the physical realization of P2.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from tools.synthetic_clouds.determinism import identity_for


@dataclass(slots=True, frozen=True)
class ResourceIdentity:
    """A stable, deterministic resource identity (P2)."""

    uuid: str  # UUIDv5(run_namespace(seed), logical_path) — the stable id
    logical_path: str  # e.g. "azure/sub-01/rg-prod/vm/web-01"
    provider: str  # "azure" | "gcp" (lowercase, matches operational rows)


@dataclass(slots=True, frozen=True)
class IdentityFactory:
    """Mints ``ResourceIdentity`` values for a fixed run seed.

    ``for_path`` is the single entry point; it guarantees a UUIDv5 identity and
    records the logical path so collisions are detectable (the estate builder
    asserts logical-path uniqueness).
    """

    seed: int

    def for_path(self, logical_path: str, provider: str) -> ResourceIdentity:
        """Return the ``ResourceIdentity`` for ``logical_path`` under ``provider``."""
        return ResourceIdentity(
            uuid=identity_for(self.seed, logical_path),
            logical_path=logical_path,
            provider=provider,
        )

    def uuid_for(self, logical_path: str) -> str:
        """Return just the UUIDv5 string for ``logical_path`` (for non-resource ids)."""
        return identity_for(self.seed, logical_path)


def azure_subscription_guid(seed: int, scope_id: str) -> str:
    """Deterministic Azure subscription GUID for a generator scope label.

    A FOCUS ``SubAccountId`` for Azure is the subscription GUID — the Azure
    promoter validates that 8-4-4-4-12 shape — while the generator's scope label is
    a friendly id like ``sub-02``. Minting the GUID here, next to the rest of the
    identity logic, keeps ONE source of truth: the Azure renderer stamps it into
    ``SubAccountId`` and the seed-side callers reuse the very same function.
    """
    return identity_for(seed, f"azure-subscription:{scope_id}")


def capacity_reservation_id(seed: int, resource_uuid: str) -> str:
    """Deterministic AWS capacity-reservation id for a generator resource.

    A capacity reservation is identified by its own provider-assigned id, which the
    FOCUS ``CapacityReservationId`` column carries, so the estate has to mint one
    rather than reuse the resource's ``ResourceIdentity.uuid`` (a UUIDv5, visibly not
    an AWS id). Minting it here, beside ``aws_account_id``, keeps the provider-shaped
    id minters in one place.

    The shape is ``cr-`` followed by 17 lowercase hex characters, which is the
    documented form of an AWS capacity-reservation id. It is derived from the resource
    the reservation targets, so the same ``(seed, resource)`` always yields the same
    id whatever window is generated.

    ``TODO-verificar``: this is a DERIVED id **in** the documented shape, NOT an
    official AWS identifier. AWS generated the real one; its exact entropy and
    checksum, if any, are not verifiable offline and are not reproduced here.
    """
    digest = hashlib.sha256(f"{seed}:capacity-reservation:{resource_uuid}".encode()).hexdigest()
    return f"cr-{digest[:17]}"


def gcp_sku_id(seed: int, sku_id: str) -> str:
    """Deterministic GCP SKU id, na forma que a documentacao publica.

    As TRES tabelas de billing do GCP usam ``sku.id`` para o identificador do SKU
    do recurso -- nas duas de uso ele e obrigatorio ("ID do recurso usado pelo
    servico; mapeia para precos de lista") e na de preco e a CHAVE DE JUNCAO
    ("Identificador unico do SKU de recurso usado pelo servico"), com exemplo
    ``2E27-4F75-95CD``.

    Emitir a CATEGORIA de servico (``Compute``, ``Storage``) ali funde SKUs
    distintos numa unica linha de preco: ``gcp-ce-e2-standard-2`` e
    ``gcp-ce-n2-standard-4`` virariam ambos ``Compute``. Este canho da a cada SKU do
    catalogo um id proprio, na forma publicada, para a juncao documentada fechar.

    ``TODO-verificar``: id DERIVADO **na** forma documentada, NAO um identificador
    oficial do Google -- a entropia real nao e verificavel offline e nao e
    reproduzida aqui. O que importa para a fidelidade e a FORMA e a unicidade, que
    sao afirmaveis.
    """
    digest = hashlib.sha256(f"{seed}:gcp-sku:{sku_id}".encode()).hexdigest().upper()
    return "-".join(digest[i : i + 4] for i in range(0, 16, 4))


#: AWS ``resource_type`` -> the prefix AWS's own id for that type carries. Closed over the
#: types AWS exposes as an OBJECT, so a missing key is a code change upstream rather than a
#: runtime condition — except ``data_transfer``, which the estate models as a cost line
#: rather than a live resource (``aws_sim.arns`` gives it no ARN for the same reason): a type
#: with no object has no id, and minting one would claim an object exists.
#:
#: The first six are the documented forms of the ids EC2 hands out (``i-``, ``vol-``,
#: ``vpc-``, ``sg-``, ``nat-``, ``eipalloc-``); the rest are NAME-shaped in AWS (an RDS
#: identifier, a Lambda function name, a bucket name) and get the same prefix+hex derivation
#: so that the id stays a valid member of the character class AWS documents for each (see
#: :func:`aws_resource_id`).
AWS_ID_PREFIXES: dict[str, str] = {
    "ec2_instance": "i-",
    "ebs_volume": "vol-",
    "vpc": "vpc-",
    "security_group": "sg-",
    "nat_gateway": "nat-",
    "elastic_ip": "eipalloc-",
    "rds_instance": "db-",
    "dynamodb_table": "table-",
    "lambda_function": "fn-",
    "eks_cluster": "cluster-",
    "ecs_cluster": "cluster-",
    "application_lb": "lb-",
    "s3_bucket": "bucket-",
    "cloudwatch_logs": "log-",
}


def aws_resource_id(resource_type: str, resource_uuid: str) -> str:
    """Deterministic AWS id for a generator resource, in its ``resource_type``'s shape.

    **Why a derived id at all.** An AWS id answers "which resource is this inside one
    account", and the canonical estate reuses ``Resource.resource_name`` across scopes
    (``generate/estate_builder.py`` restarts its per-scope counter for every account, so
    ``ec2_instance-0018`` exists in three of them). An AWS ``InstanceId`` is scope-free, so
    a projection that answers the name answers the SAME value for every resource that shares
    it — and every consumer that keys telemetry by that value (the CloudWatch shim's
    ``InstanceId`` / ``DBInstanceIdentifier`` dimension, and the rightsizing path that fills
    the dimension from the id ``DescribeInstances`` reported) then resolves several resources
    to one series. That is the correlation bug this mint exists to remove.

    The id is derived from the resource's own ``ResourceIdentity.uuid``, so it is unique per
    resource by construction, deterministic for a ``(seed, logical_path)``, and stable across
    a rebuild and across the daily and one-shot surfaces. It is computed with ``hashlib`` and
    never ``hash()``, which is salted per process and banned in this package (AC-6).

    ``TODO-verificar``: this is a DERIVED id **in** the documented shape, NOT an official AWS
    identifier. AWS generated the real one, and its entropy is not reproducible offline. Same
    discipline as :func:`capacity_reservation_id` and :func:`aws_account_id`.
    """
    prefix = AWS_ID_PREFIXES[resource_type]
    digest = hashlib.sha256(f"{resource_type}:{resource_uuid}".encode()).hexdigest()
    # 17 lowercase hex characters is the tail length of the EC2 family's ids (``i-`` plus 17
    # of them); the name-shaped types in the table above accept the same characters in the
    # same length, and the ``resource_type`` in the digest keeps two types apart even where
    # they share a prefix (``eks_cluster`` and ``ecs_cluster``).
    return f"{prefix}{digest[:17]}"


def aws_account_id(seed: int, scope_id: str) -> str:
    """Deterministic 12-digit AWS account id for a generator scope label.

    A FOCUS ``SubAccountId`` for AWS is the 12-digit account id, while the
    generator's scope label is a friendly id like ``acct-02``. Minting it here
    beside ``azure_subscription_guid`` keeps ONE source of truth: the AWS
    renderer stamps it into ``SubAccountId`` and the seed-side callers reuse the
    very same function.

    The leading ``9`` band is deliberate — it is obviously synthetic and cannot
    be mistaken for a real account id during a local run. Derived via
    ``hashlib.sha256`` for the same reason ``stream_rng`` is: ``hash()`` is
    salted per process and is banned in this package (AC-6).
    """
    digest = hashlib.sha256(f"{seed}:aws-account:{scope_id}".encode()).digest()
    return f"9{int.from_bytes(digest[:8], 'big') % 10**11:011d}"
