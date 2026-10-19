"""Native findings and recommendations (design sec. 4.7).

Both are bound to an existing ``ResourceIdentity.uuid`` — the P2 no-orphan
guarantee the gate enforces (FR-E4, AC-7).

Severity casing (Finding 7): ``NativeFinding.severity`` is intentionally UPPERCASE
(``CRITICAL|HIGH|MEDIUM|LOW``) per the security-findings convention, because a
finding is a cloud INPUT. Drift results use lowercase severity, but drift results
are a FinOps-COMPUTED output (P1) and are never emitted here. Do not "fix" the
native UPPERCASE casing to match drift's lowercase.

Native findings carry native ``status="open"`` only; FinOps owns
resolved/suppressed transitions.

``NativeFinding.raised_on`` is the day the finding appeared, and it exists for FR-22:
the daily cadence needs a per-day alert stream, and without a date a finding can only
be "present" or "absent" for the whole run. It is drawn from a stream keyed by the
**resource**, not by position, so the same resource raises the same finding on the
same day no matter which window is being generated. A finding dated later than the
window's ``sim_now`` is not emitted yet — alerts accumulate across the month instead
of all existing from day one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(slots=True, frozen=True)
class NativeFinding:
    """A Defender/SCC-style native finding bound to a resource identity."""

    finding_id: str  # deterministic
    resource_uuid: str  # FK -> ResourceIdentity.uuid
    provider: str  # azure | gcp | aws (lowercase)
    category: str  # NETWORK/IAM/CONFIG-style native category
    severity: str  # UPPERCASE CRITICAL|HIGH|MEDIUM|LOW (input convention)
    status: str  # "open" (native state; FinOps owns resolution)
    raised_on: date  # the day the finding appeared (FR-22 alert axis)
    source: str  # "synthetic" (NFR-3)
    evidence_json: dict[str, Any]  # evidence_json.synthetic = true (NFR-3)

    # Campos NEUTROS acrescentados em 2026-10-14, porque `Title`, `Description` e
    # `Types` sao OBRIGATORIOS no ASFF e saiam vazios. Sao neutros de proposito --
    # nao carregam o schema de uma nuvem so: o renderer de cada nuvem mapeia
    # (o ASFF escreve `Title`; o SCC, `description`; o Defender, o nome do
    # controle). Os defaults mantem as construcoes existentes validas.
    title: str = ""
    description: str = ""
    #: Forma documentada ``namespace/category/classifier``, com o namespace vindo
    #: da lista fechada que o ASFF publica. Os outros dois segmentos sao a
    #: classificacao do provedor, e por isso sao nossos.
    types: tuple[str, ...] = ()

    #: NAO existe `severity_normalized` como CAMPO DO MODELO, e a razao mudou em 2026-10-15.
    #: Antes ela era "as faixas nao estao na documentacao consultada" -- e isso ja nao e verdade:
    #: ``API_Severity.html`` publica a tabela (INFORMATIONAL-0, LOW-1, MEDIUM-40, HIGH-70,
    #: CRITICAL-90) e o renderer ASFF ja a aplica em ``Severity.Normalized``. O campo continua
    #: fora do MODELO porque um numero derivado de tabela nao e um fato que o estado carrega --
    #: ele pertence ao renderer, que e quem cita a fonte. Os campos `confidence` e
    #: `criticality` abaixo sao o contraexemplo: sao fatos do estado, e por isso vivem aqui.
    #:
    #: Tambem NAO existem `verification_state` nem `workflow_status`: os dois sao
    #: enums do ASFF sem equivalente nas outras nuvens, e carregar o schema de uma
    #: nuvem como se fosse o canonico e o que este modelo evita.

    #: Quem produziu a finding. Sao fatos genericos de procedencia, com os limites
    #: que a documentacao publica (generator 1-512, nome e empresa 1-128).
    generator_id: str = ""
    product_name: str = ""
    company_name: str = ""
    #: Quando o problema foi observado pela primeira vez. ``raised_on`` e o DIA
    #: (o eixo de alerta do FR-22); este e o instante dentro do dia.
    first_observed_at: datetime | None = None
    #: Escalas 0-100 que a documentacao define. ``None`` onde a nuvem nao tem o
    #: conceito -- o renderer deixa a coluna vazia em vez de inventar um numero.
    confidence: int | None = None
    criticality: int | None = None


@dataclass(slots=True, frozen=True)
class NativeRecommendation:
    """An Advisor/Recommender-style native recommendation bound to a resource."""

    recommendation_id: str
    resource_uuid: str  # FK -> ResourceIdentity.uuid
    provider: str
    kind: str  # advisor/recommender-style native type
    recommendation_model: str  # "synthetic.seed.v1" (NFR-3)
    detail_json: dict[str, Any]


#: Os TRES literais que ``AssessmentStatusCode`` publica para ``properties.status.code``
#: ("Assessments - List", Microsoft.Security, api-version 2021-06-01). Sao o vocabulario
#: NATIVO do provedor em caixa publicavel -- e nao o `status="open"` do NativeFinding,
#: que e o estado de um ACHADO e nao o estado de SAUDE de uma verificacao.
ASSESSMENT_HEALTH_HEALTHY = "Healthy"
ASSESSMENT_HEALTH_UNHEALTHY = "Unhealthy"
ASSESSMENT_HEALTH_NOT_APPLICABLE = "NotApplicable"
ASSESSMENT_HEALTH_CODES = (
    ASSESSMENT_HEALTH_HEALTHY,
    ASSESSMENT_HEALTH_UNHEALTHY,
    ASSESSMENT_HEALTH_NOT_APPLICABLE,
)

#: Os literais que ``SecurityAssessmentMetadataProperties.severity`` publica
#: (``Low``/``Medium``/``High``). ``NativeFinding.severity`` e o vocabulario NATIVO do
#: ESTADO em maiusculas (``CRITICAL|HIGH|MEDIUM|LOW``); a ponte entre os dois e uma
#: normalizacao de CASCA feita pelo renderer, que e quem cita a fonte.
ASSESSMENT_SEVERITIES = ("Low", "Medium", "High")


@dataclass(slots=True, frozen=True)
class AzureDefenderAssessment:
    """Uma verificacao de seguranca do Defender sobre um recurso, com o ESTADO DE SAUDE dela.

    POR QUE ISTO NAO E DERIVADO DE ``NativeFinding``
    -------------------------------------------------
    O consumidor do FinOps filtra assessments por ``status.code == "Healthy"`` e joga
    fora o resto. Um ``NativeFinding`` -- por definicao um PROBLEMA -- nao consegue
    representar o ramo descartado: um assessment ``Healthy`` nao tem finding, e um
    assessment ``NotApplicable`` nao tem finding por SER o assessment que nao se aplica ao
    tipo de recurso. Sem esta estrutura, nao existe assessment ``Healthy`` e o filtro do
    consumidor nunca descarta nada sobre o artefato -- um check que nunca ve o outro lado
    nao treina nada (a mesma razao que obrigou o Incremento 7 a posturar 443/3389 em vez de
    deixar o NSG sem abertura).

    A DERIVACAO A PARTIR DOS ACHADOS FOI IMPLEMENTADA, MEDIDA E DESCARTADA. Ligar o estado a
    um ``NativeFinding`` de categoria REDE no mesmo escopo e a leitura mais obvious, e ela
    produziu, no perfil ``small``/seed 123, ``Counter({'Unhealthy': 6, 'NotApplicable': 6})`` --
    nenhum ``Healthy``. O que decide o estado hoje e a POSTURA DECLARADA
    (:data:`~tools.synthetic_clouds.generate.constants.AZURE_DEFENDER_ASSESSMENT_POSTURES`),
    alternada pelo indice do segmento dentro da assinatura; ver
    ``generate/estate_builder.py::_azure_defender_assessments`` para as duas versao medidas.
    A severidade tambem vem da postura, e nao de ``NativeFinding.severity``: o dominio
    publicado (``Low|Medium|High``) nao tem faixa ``CRITICAL``, e projetar uma seria inventar
    um literal.

    A ADICAO e opt-in e nao migra nada: a colecao vive com default vazio em
    :class:`~tools.synthetic_clouds.model.estate.CanonicalEstate`, ``Resource`` e
    ``NetworkSegment`` nao mudam, e nenhuma construcao existente foi alterada.

    ``segment_uuid`` e FK para ``NetworkSegment.segment_uuid`` e nao para
    ``ResourceIdentity.uuid`` porque o assessment ancoreia um recurso que o estado ja
    carrega com um id ARM verdadeiro (``NetworkSegment.segment_id``, o mesmo que a
    ``azure_vnet_flow_logs`` entrega). Ancorar num ``Resource`` exigiria compor um id ARM
    de recurso de computacao, e o estado canonico NAO modela resource group -- um id
    inventado seria pior do que a lacuna visivel.
    """

    segment_uuid: str  # FK -> NetworkSegment.segment_uuid (Azure)
    #: O NOME do recurso assessment -- um GUID deterministico, na forma que o exemplo
    #: oficial publica (``name``: "21300918-b2e3-0346-785f-c77ff57d243b"). Ele e a
    #: ULTIMA segmento do ``id`` do assessment, entao sai do MESMO campo que o renderer
    #: compoe o caminho: duas grafias do mesmo id e o defeito que este repo evita.
    assessment_id: str
    #: Chave da POSTURA no simulador (``generate/constants.py``). NAO e publicada: nao
    #: existe em nenhuma pagina oficial, e por isso nunca chega ao artefato. E o que
    #: decide o par (health, severity) de forma declarativa e repetivel.
    posture: str
    #: Um de :data:`ASSESSMENT_HEALTH_CODES` -- literal documentado.
    health: str
    #: Um de :data:`ASSESSMENT_SEVERITIES`, ou ``""`` quando a postura nao declara
    #: severidade. Vazio e diferente de ``"Low"``: nao ha severidade para publicar.
    severity: str = ""
    #: Instantes publicados em ``properties.status``: a primeira avaliacao e a mudanca de
    #: estado. Ambos sao deterministicos (stream por segmento), nunca ``now()``.
    first_evaluated_at: datetime | None = None
    status_changed_at: datetime | None = None
