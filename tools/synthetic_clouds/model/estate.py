"""The ``CanonicalEstate`` root aggregate (design sec. 4.1).

The single source of truth; renderers are pure projections of it. All entities are
frozen dataclasses; money is ``Decimal`` at 6 fractional digits (FOCUS
``numeric(18,6)``, FR-G1c).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from tools.synthetic_clouds.model.audit import AwsAuditPosture, AwsVpcFlowLog
from tools.synthetic_clouds.model.billing import (
    BillingLine,
    ContractedPrice,
    DailyConsumption,
    ListPrice,
)
from tools.synthetic_clouds.model.commitments import Commitment, Credit, Tax
from tools.synthetic_clouds.model.compute import InstanceProfile
from tools.synthetic_clouds.model.hierarchy import AwsOrg, AzureMgmtGroup, BillingAccount, GcpOrg
from tools.synthetic_clouds.model.iac import IacStateSnapshot, InventoryAsset
from tools.synthetic_clouds.model.iam import AwsIdentityPosture
from tools.synthetic_clouds.model.invoice import Invoice
from tools.synthetic_clouds.model.metrics import MetricSeries
from tools.synthetic_clouds.model.native import (
    AzureDefenderAssessment,
    NativeFinding,
    NativeRecommendation,
)
from tools.synthetic_clouds.model.network import (
    AwsSecurityGroup,
    GcpFirewallRule,
    NetworkFlow,
    NetworkInterface,
    NetworkSegment,
)
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.model.storage import AwsBucketPosture


@dataclass(slots=True, frozen=True)
class CanonicalEstate:
    """The validated, correlated multi-cloud estate (frozen root aggregate)."""

    seed: int
    profile: str  # small | medium | large
    currency: str  # USD | BRL
    currency_conversion_rate: Decimal | None  # set only when currency == BRL
    sim_start: date
    sim_now: date  # SIM_NOW at end of generation window
    billing_accounts: tuple[BillingAccount, ...]
    azure_mgmt_groups: tuple[AzureMgmtGroup, ...]
    gcp_orgs: tuple[GcpOrg, ...]
    aws_orgs: tuple[AwsOrg, ...]
    resources: tuple[Resource, ...]
    consumption: tuple[DailyConsumption, ...]
    billing_lines: tuple[BillingLine, ...]
    list_prices: tuple[ListPrice, ...]
    contracted_prices: tuple[ContractedPrice, ...]
    commitments: tuple[Commitment, ...]
    credits: tuple[Credit, ...]
    taxes: tuple[Tax, ...]
    invoices: tuple[Invoice, ...]
    inventory: tuple[InventoryAsset, ...]
    findings: tuple[NativeFinding, ...]
    recommendations: tuple[NativeRecommendation, ...]
    metrics: tuple[MetricSeries, ...]
    iac_snapshots: tuple[IacStateSnapshot, ...]
    scenario_ids: tuple[str, ...]  # C01..C18 that were applied
    # Rede entra por ultimo e com default: a ordem inventario -> fluxo e a mesma
    # do ``docs/MODELO-REDE.md``, e um fluxo sem interface/segmento seria orfao.
    network_segments: tuple[NetworkSegment, ...] = ()
    network_interfaces: tuple[NetworkInterface, ...] = ()
    network_flows: tuple[NetworkFlow, ...] = ()
    # O perfil de instancia pendura na interface: o IP privado dele e o MESMO da
    # NIC do recurso, e o gate confere isso.
    instance_profiles: tuple[InstanceProfile, ...] = ()
    # As REGRAS dos security groups da AWS. Entra por ultimo e com default: os SGs da
    # Azure ja vivem em ``NetworkSegment.network_security_group`` e a GCP nao modela
    # grupo nenhum, entao esta colecao so existe para a AWS -- e e a unica forma de a
    # AWS ficar com o CONTEUDO da regra, que antes era uma lacuna nomeada nas regras de
    # Config do AWS.
    aws_security_groups: tuple[AwsSecurityGroup, ...] = ()
    # A POSTURA dos buckets S3: ACL, bucket policy e public access block. E o Incremento 3
    # pela mesma razao do campo acima -- o recurso ``s3_bucket`` ja existia e era
    # inventariado e faturado, mas nada no estate carregava a postura que
    # ``GetBucketAcl`` / ``GetBucketPolicy`` / ``GetPublicAccessBlock`` publicam, e as
    # tres regras de Config sobre exposicao publica respondiam INSUFFICIENT_DATA por
    # lacuna de modelo nomeada. Fica numa colecao propria (e nao como coluna em
    # ``Resource``) porque nenhum elemento do S3 pertence ao conjunto FOCUS 1.2.
    aws_bucket_postures: tuple[AwsBucketPosture, ...] = ()
    # A postura de IDENTIDADE de cada conta AWS: MFA do root, politica de senha, usuarios
    # e chaves de acesso. E o Incremento 4 pela mesma razao dos dois campos acima -- as
    # tres regras de Config de identidade respondiam INSUFFICIENT_DATA por lacuna de
    # modelo nomeada. A diferenca estrutural: a chave aqui e a CONTA
    # (``AwsAccount.account_id``), nao um recurso, porque IAM e global e nao tem regiao --
    # e por isso que o veredito das tres regras se repete em cada escopo regional da conta,
    # em vez de diferir. Ver ``model/iam.py``.
    aws_identity_postures: tuple[AwsIdentityPosture, ...] = ()
    # A postura de AUDITORIA de cada conta AWS: as trilhas CloudTrail e a inscricao do Security
    # Hub. E o Incremento 4.3 pela razao dos tres campos acima -- as duas regras de
    # auditoria/guardrails respondiam INSUFFICIENT_DATA por lacuna de modelo nomeada. A chave e
    # a CONTA, como em ``aws_identity_postures``, e nao um recurso: as duas paginas publicam
    # trigger ``Periodic`` e NENHUM "Resource Types", entao o alvo da regra e a conta.
    aws_audit_postures: tuple[AwsAuditPosture, ...] = ()
    # A configuracao de flow logs de cada VPC. Unico campo do estate chaveado pelo recurso
    # ``vpc`` e nao pela conta: a pagina de ``vpc-flow-logs-enabled`` publica
    # ``Resource Types: AWS::EC2::VPC``, entao o veredito e POR VPC. Ver ``model/audit.py``
    # para por que isso nao mora em ``NetworkSegment``.
    aws_vpc_flow_logs: tuple[AwsVpcFlowLog, ...] = ()
    # As regras de firewall da GCP que ``compute.firewalls.list`` publica. Chaveada pelo
    # PROJETO, e nao por recurso e nem por (conta, regiao): o caminho da acao e
    # ``projects/<projeto>/global/firewalls``, ou seja, a resposta e global e por projeto --
    # a regiao so existe no par rede/sub-rede. A regra liga a rede por ``segment_uuid`` (FK)
    # porque ``Firewall.network`` publica a URL da rede e o segmento ja a carrega verbatim.
    gcp_firewall_rules: tuple[GcpFirewallRule, ...] = ()
    # As VERIFICACOES DE SAUDE do Defender for Cloud sobre os segmentos Azure. Entra por
    # ultimo e com default pela razao do Incremento 8: o consumidor do FinOps le
    # ``assessments.list`` e filtra ``status.code == "Healthy"``, e o estado so tinha
    # achados -- que nao conseguem representar o ramo DESCARTADO do filtro. A chave e o
    # SEGMENTO (FK para ``NetworkSegment.segment_uuid``) porque e o unico objeto Azure do
    # estado que carrega um id ARM verdadeiro, que e o que ``properties.resourceDetails.id``
    # e o ``id`` do assessment publicam. Ver ``model/native.py::AzureDefenderAssessment``.
    azure_defender_assessments: tuple[AzureDefenderAssessment, ...] = ()

    def resource_uuids(self) -> frozenset[str]:
        """Return the set of all resource identity UUIDs in the estate (P2 base set)."""
        return frozenset(r.identity.uuid for r in self.resources)
