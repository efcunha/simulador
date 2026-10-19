"""Referential-integrity checks (P2 no-orphans, resource scoping).

F2 (design-review must-fix): the no-orphan check inspects ONLY non-None
``resource_uuid`` values. A ``BillingLine`` with ``resource_uuid is None`` is the
sanctioned FR-D5 null-resource line (or a C05 commitment Purchase line) and is
exempt — never treated as an orphan, never silently coerced to a sentinel. Every
OTHER record type (findings/recommendations/metrics/IaC/consumption) requires a
non-None ``resource_uuid`` in the resource identity set.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.compute import STATES
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import ASSESSMENT_HEALTH_CODES, ASSESSMENT_SEVERITIES
from tools.synthetic_clouds.model.network import (
    DECISION_ALLOWED,
    DECISIONS,
    DIRECTION_INGRESS,
    DIRECTIONS,
    SECURITY_RULE_PRIORITY_RANGE,
    SECURITY_RULE_PROTOCOLS,
)


class IntegrityError(Exception):
    """Raised when a referential-integrity invariant is violated (fatal)."""


def _valid_scope_ids(estate: CanonicalEstate) -> frozenset[str]:
    azure = {s.subscription_id for mg in estate.azure_mgmt_groups for s in mg.subscriptions}
    gcp = {p.project_id for org in estate.gcp_orgs for f in org.folders for p in f.projects}
    aws = {a.account_id for org in estate.aws_orgs for a in org.accounts}
    return frozenset(azure | gcp | aws)


def check_no_orphans(estate: CanonicalEstate) -> None:
    """Assert every non-None resource_uuid references an existing resource (AC-7).

    Also asserts (F2) that findings/recommendations/metrics/IaC/consumption carry
    NO ``None`` resource_uuid, and that billing lines with ``resource_uuid is None``
    are only the sanctioned billing-only lines (FR-D5 null line + C05 commitment
    Purchase lines, which have no backing resource by design).
    """
    ids = estate.resource_uuids()

    # Consumption: non-None and in the identity set.
    for row in estate.consumption:
        if row.resource_uuid not in ids:
            raise IntegrityError(f"orphan consumption row -> {row.resource_uuid!r} (usage_date={row.usage_date})")

    # Findings / recommendations / metrics: non-None and in the set.
    for finding in estate.findings:
        if finding.resource_uuid not in ids:
            raise IntegrityError(f"orphan finding {finding.finding_id} -> {finding.resource_uuid!r}")
    for rec in estate.recommendations:
        if rec.resource_uuid not in ids:
            raise IntegrityError(f"orphan recommendation {rec.recommendation_id} -> {rec.resource_uuid!r}")
    for series in estate.metrics:
        if series.resource_uuid not in ids:
            raise IntegrityError(f"orphan metric series {series.metric_name} -> {series.resource_uuid!r}")

    # IaC resource states: non-None and in the set.
    for snapshot in estate.iac_snapshots:
        for state in snapshot.resource_states:
            if state.resource_uuid not in ids:
                raise IntegrityError(f"orphan IaC state in {snapshot.snapshot_id} -> {state.resource_uuid!r}")

    # Inventory: non-None and in the set.
    for asset in estate.inventory:
        if asset.resource_uuid not in ids:
            raise IntegrityError(f"orphan inventory asset -> {asset.resource_uuid!r}")

    # Billing: non-None resource_uuid must be in the set; None is a sanctioned
    # billing-only line (FR-D5 / C05). The gate does NOT coerce None.
    for line in estate.billing_lines:
        if line.resource_uuid is not None and line.resource_uuid not in ids:
            raise IntegrityError(f"orphan billing line {line.line_id} -> {line.resource_uuid!r}")

    _check_network_integrity(estate, ids)
    _check_instance_integrity(estate, ids)


def _check_instance_integrity(estate: CanonicalEstate, ids: frozenset[str]) -> None:
    """Instancia: pendura no recurso E na interface, com o MESMO IP privado.

    A coerencia de IP e o ponto: uma instancia cujo IP privado difere do IP da
    sua propria NIC e um estado impossivel, e o simulador nao deve poder produzi-lo
    sem que o gate acuse.
    """
    interface_por_uuid = {interface.interface_uuid: interface for interface in estate.network_interfaces}
    segment_uuids = {segment.segment_uuid for segment in estate.network_segments}

    for perfil in estate.instance_profiles:
        if perfil.resource_uuid not in ids:
            raise IntegrityError(f"orphan instance profile -> {perfil.resource_uuid!r}")
        if perfil.state not in STATES:
            raise IntegrityError(
                f"instance profile {perfil.native_id} com estado fora do canonico: {perfil.state!r}"
            )
        if not (estate.sim_start <= perfil.launch_time.date() <= estate.sim_now):
            raise IntegrityError(
                f"instance profile {perfil.native_id} lancado fora da janela: {perfil.launch_time.isoformat()}"
            )
        if perfil.segment_uuid is not None and perfil.segment_uuid not in segment_uuids:
            raise IntegrityError(
                f"instance profile {perfil.native_id} -> segmento inexistente {perfil.segment_uuid!r}"
            )
        if perfil.interface_uuid is None:
            continue
        interface = interface_por_uuid.get(perfil.interface_uuid)
        if interface is None:
            raise IntegrityError(
                f"instance profile {perfil.native_id} -> interface orfa {perfil.interface_uuid!r}"
            )
        if interface.private_ip != perfil.private_ip:
            raise IntegrityError(
                f"instance profile {perfil.native_id} com IP privado {perfil.private_ip!r} "
                f"diferente do IP da sua propria interface ({interface.private_ip!r})"
            )
        if interface.resource_uuid != perfil.resource_uuid:
            raise IntegrityError(
                f"instance profile {perfil.native_id} aponta interface de outro recurso "
                f"({interface.resource_uuid!r})"
            )


def _check_network_integrity(estate: CanonicalEstate, ids: frozenset[str]) -> None:
    """Rede: segmento no escopo, interface no recurso, fluxo ligado a interface.

    A ordem importa e e a mesma do documento de rede: o fluxo depende do
    inventario. Um fluxo sem nenhuma ponta conhecida nao teria de onde sair, e um
    ``log_resource_id`` vazio tornaria o registro inutil para o renderer.
    """
    scope_ids = _valid_scope_ids(estate)
    segment_uuids = {segment.segment_uuid for segment in estate.network_segments}

    for segment in estate.network_segments:
        if segment.scope_id not in scope_ids:
            raise IntegrityError(
                f"network segment {segment.segment_uuid} -> scope inexistente {segment.scope_id!r}"
            )

    interface_uuids: set[str] = set()
    for interface in estate.network_interfaces:
        if interface.resource_uuid not in ids:
            raise IntegrityError(
                f"orphan network interface {interface.interface_uuid} -> {interface.resource_uuid!r}"
            )
        if interface.segment_uuid not in segment_uuids:
            raise IntegrityError(
                f"network interface {interface.interface_uuid} -> segment inexistente "
                f"{interface.segment_uuid!r}"
            )
        interface_uuids.add(interface.interface_uuid)

    for flow in estate.network_flows:
        if flow.segment_uuid not in segment_uuids:
            raise IntegrityError(f"network flow {flow.flow_id} -> segment inexistente {flow.segment_uuid!r}")
        for ponta, uuid in (("origem", flow.src_interface_uuid), ("destino", flow.dst_interface_uuid)):
            if uuid is not None and uuid not in interface_uuids:
                raise IntegrityError(f"network flow {flow.flow_id} -> {ponta} orfa {uuid!r}")
        if flow.src_interface_uuid is None and flow.dst_interface_uuid is None:
            raise IntegrityError(f"network flow {flow.flow_id} sem nenhuma ponta no estate")
        if not flow.log_resource_id:
            raise IntegrityError(f"network flow {flow.flow_id} sem log_resource_id")
        if flow.packets < 0 or flow.bytes < 0:
            raise IntegrityError(f"network flow {flow.flow_id} com contador negativo")
        if flow.decision not in DECISIONS or flow.direction not in DIRECTIONS:
            raise IntegrityError(
                f"network flow {flow.flow_id} fora do vocabulario canonico: "
                f"{flow.direction!r}/{flow.decision!r}"
            )

    for segment in estate.network_segments:
        nsg = segment.network_security_group
        if nsg is None:
            continue
        if not nsg.rules:
            raise IntegrityError(f"network security group {nsg.name} sem nenhuma regra")
        prioridades: list[int] = []
        for rule in nsg.rules:
            if rule.direction not in DIRECTIONS or rule.access not in DECISIONS:
                raise IntegrityError(
                    f"security rule {rule.name} fora do vocabulario canonico: "
                    f"{rule.direction!r}/{rule.access!r}"
                )
            if rule.protocol not in SECURITY_RULE_PROTOCOLS:
                raise IntegrityError(
                    f"security rule {rule.name} com protocolo fora do dominio publicado: {rule.protocol!r}"
                )
            minimo, maximo = SECURITY_RULE_PRIORITY_RANGE
            if not minimo <= rule.priority <= maximo:
                raise IntegrityError(
                    f"security rule {rule.name} com prioridade fora de [{minimo}, {maximo}]: {rule.priority}"
                )
            prioridades.append(rule.priority)
        if len(set(prioridades)) != len(prioridades):
            # A documentacao exige prioridade UNICA na colecao: duas regras com o mesmo
            # numero deixariam a ordem de avaliacao indefinida, que e o oposto do que uma
            # politica de firewall afirma.
            raise IntegrityError(f"network security group {nsg.name} com prioridade repetida: {sorted(prioridades)}")
        if not any(
            rule.direction == DIRECTION_INGRESS and rule.access == DECISION_ALLOWED for rule in nsg.rules
        ):
            # O consumidor varre as regras Inbound/Allow. Um NSG sem nenhuma delas nao e um
            # estado limpo: e um estado em que ele nao teria o que procurar.
            raise IntegrityError(
                f"network security group {nsg.name} sem regra Inbound/Allow: o consumidor nao teria o que ler"
            )

    # A verificacao de saude do Defender ancora um SEGMENTO (e nao um Resource): o
    # assessment publica o id ARM do recurso avaliado, e o segmento ja o carrega. Um
    # assessment sem segmento nao teria de onde sair o id que ele publica.
    for assessment in estate.azure_defender_assessments:
        if assessment.segment_uuid not in segment_uuids:
            raise IntegrityError(
                f"orphan azure defender assessment {assessment.assessment_id} -> segmento inexistente "
                f"{assessment.segment_uuid!r}"
            )
        if assessment.health not in ASSESSMENT_HEALTH_CODES:
            raise IntegrityError(
                f"azure defender assessment {assessment.assessment_id} fora do vocabulario publicado: "
                f"{assessment.health!r}"
            )
        if assessment.severity and assessment.severity not in ASSESSMENT_SEVERITIES:
            raise IntegrityError(
                f"azure defender assessment {assessment.assessment_id} com severidade fora do dominio "
                f"publicado: {assessment.severity!r}"
            )


def check_resource_scoping(estate: CanonicalEstate) -> None:
    """Assert every resource belongs to a valid subscription/project/account (AC-8, FR-E3)."""
    valid = _valid_scope_ids(estate)
    for resource in estate.resources:
        if resource.parent_scope_id not in valid:
            raise IntegrityError(
                f"resource {resource.identity.uuid} has invalid parent_scope_id {resource.parent_scope_id!r}"
            )
