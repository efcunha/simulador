"""ARM resource representation (instances) — the body of a ``GET`` on ``Microsoft.Compute/virtualMachines``.

Surface: ``specs/azure/arm-resource-representation.schema.json`` — 327 columns in ONE
anonymous set (``spec.set_names == ()``, so ``check_artifact`` needs no ``scope``), 301 of
them emittable/generatable.

WHAT THIS SURFACE IS (and what it is NOT)
-----------------------------------------
The spec's ``delivery`` block is explicit: ``kind: "arm-rest-api"``, endpoint
``GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/{vmName}?api-version=2026-04-01``,
``responses.200 -> VirtualMachine``. This is NOT an export: it is the JSON body of a
control-plane REST response. Its own ``delivery.note`` says so — "This is an ARM
control-plane REST response, not a push export. No blob path, partitioning, compression
or manifest is documented because none exists for this surface." There is therefore no
container, no blob path and no manifest to lay out; the artifact is ONE JSON document per
virtual machine, written at the path the documented endpoint itself addresses
(``subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/{vmName}.json``).

THE DOCUMENTED SHAPE IS DERIVED FROM THE SPEC
---------------------------------------------
The response body is built from the spec's own field paths (:func:`documented_document`),
so the delivered JSON carries EXACTLY the documented properties — the 301 emittable
columns, no more — and every property the canonical estate cannot source is emitted EMPTY
(``null`` for a scalar, ``{}``/``[]`` for a collection the spec does not enumerate,
``[element]`` for a collection whose element members the spec DOES enumerate, so that a
documented ``[]``-member path never disappears from the artifact). No value is ever
invented: the model is the only source of values (see ``_values``).

A documented-but-UNDOCUMENTED-CONTAINER path (a prefix the spec does not list as a column
of its own, e.g. ``properties.networkProfile.networkInterfaces[].properties``) is
synthesized as a structural container, exactly as ``render/gcp_bigquery_topology.py`` does
for the BigQuery records. The fidelity test asserts that the document's extra paths are
EXACTLY that minimal prefix closure AND that the delivered field projection carries the
spec's paths and no container besides -- a synthesized container never becomes a column of
the artifact.

THE MODEL GAPS (reported, not papered over)
-------------------------------------------
* ``id``, ``type``, ``tags``, ``properties.vmId``, ``properties.provisioningState``,
  ``properties.timeCreated``, ``identity.principalId``/``tenantId``, ``resources`` and the
  extension ``resources[].properties.*`` are ``evidence: example-only`` in the spec: the
  documentation shows them in a payload but establishes no schema for them. They must NOT
  be emitted, so the ARM response this renderer delivers carries no ARM resource id, no
  ``tags`` (even though the canonical ``Resource`` HAS tags), no provisioning state and no
  ``vmId``. The only identity the response has is the path it was delivered at.
* The canonical estate carries no resource group, no ARM resource id, no OS/disk/image
  detail, no identity/plan/host/placement: every such property is emitted empty. The
  partition segment the model cannot source carries the documentation's OWN template token
  (``{resourceGroupName}``), never a minted name.
* ``properties.networkProfile.networkInterfaces[].id`` DID acquire a source: the network
  model binds each ``NetworkInterface`` to the resource it belongs to
  (``NetworkInterface.resource_uuid``), so the response names the NIC the VM actually uses.
  The NIC ARM id is projected verbatim -- including the subscription token its own id
  carries, so the response never names one subscription and its path another.

This surface also writes the sibling ``_provenance.json`` (the mechanism, the counts, the 26
columns the spec refuses and the model gaps). It is a SEPARATE file on purpose: a field of a
cloud's own payload and a FinOps-side report are different things, and an ingester of the
response must never see ``surface``/``spec``/``model_gaps`` in it.

WHERE THE SHARED HELPERS LIVE
-----------------------------
``emittable_columns``, ``documented_document``, ``flatten_document`` and ``write_json`` are
generic over any ``SurfaceSpec``; the four sibling Azure renderers of this slice import them
from here because this module is the surface whose whole artifact IS a nested documented
document. A dedicated ``render/azure_document.py`` would be the tidier home, but that file
is outside the ownership of this slice — the extraction is the maintainer's call.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    Column,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.identity import azure_subscription_guid
from tools.synthetic_clouds.model.network import NetworkInterface
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.base import RenderError

#: O caminho da especificação normativa DENTRO de ``specs/`` (a proveniência cita este texto).
_SPEC_FILE = "azure/arm-resource-representation.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

_AZURE = "azure"

#: O token que o PRÓPRIO template da especificação usa para o que ele não resolve
#: (``resourceGroups/{resourceGroupName}``). O estado canônico não modela resource group,
#: e inventar um nome seria pior do que deixar a lacuna visível no caminho entregue.
_RESOURCE_GROUP_SEGMENT = "{resourceGroupName}"


# -- helpers compartilhados pelos renderers Azure deste slice --------------------------


def emittable_columns(spec: SurfaceSpec, scope: str | None = None) -> tuple[Column, ...]:
    """Colunas que PERTENCEM ao formato no ``scope`` (inclui as ``null-empty``).

    É a barreira do contrato: uma coluna que não passe em ``belongs_to_schema`` não entra
    no artefato -- nem vazia. ``scope=None`` vale para uma superfície de conjunto único
    (ou anônimo, como esta).
    """
    columns = spec.columns if scope is None else spec.columns_for(scope)
    return tuple(column for column in columns if column.belongs_to_schema)


def _emitted_name(prefix: str) -> str:
    """A forma que o caminho assume no documento: ``a.b[]`` é a chave ``a.b`` da lista."""
    return prefix[:-2] if prefix.endswith("[]") else prefix


def container_paths(columns: Sequence[Column]) -> frozenset[str]:
    """Caminhos documentados que HOSPEDAM outro caminho documentado (contêineres)."""
    names = {column.name for column in columns}
    parents: set[str] = set()
    for column in columns:
        segments = column.name.split(".")
        for cut in range(1, len(segments)):
            emitted = _emitted_name(".".join(segments[:cut]))
            if emitted in names:
                parents.add(emitted)
    return frozenset(parents)


def structural_containers(spec: SurfaceSpec, scope: str | None = None) -> frozenset[str]:
    """Os contêineres ESTRUTURAIS do documento: prefixos que a spec não lista como coluna.

    Existem no documento porque hospedam um caminho documentado (``properties``,
    ``...networkInterfaces[].properties``) e NUNCA viram coluna da projeção entregue. É este
    conjunto que o relatório conta: uma resposta ARM completa tem 301 campos documentados e
    quatro contêineres que a spec não nomeia.
    """
    documented = {column.name for column in emittable_columns(spec, scope)}
    closure: set[str] = set()
    for path in documented:
        segments = path.split(".")
        for cut in range(1, len(segments)):
            emitted = _emitted_name(".".join(segments[:cut]))
            if emitted not in documented:
                closure.add(emitted)
    return frozenset(closure)


def leaf_filled_fields(columns: Sequence[Column], row: Mapping[str, Any]) -> int:
    """Quantos campos FOLHA da projeção carregam valor -- o número que o relatório publica.

    Um contêiner documentado (``properties``, ``properties.hardwareProfile``) tem como valor a
    subárvore que hospeda, então contá-lo como "preenchido" inflaria o relatório: o dado de um
    contêiner está nos filhos. Aqui só os campos que não hospedam outro caminho entram.
    """
    containers = container_paths(columns)
    return sum(
        1
        for column in columns
        if column.name not in containers and not is_blank(row.get(column.name))
    )


def is_blank(value: Any) -> bool:
    """Ausência de valor, na mesma definição que o núcleo de fidelidade usa."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"", "{}", "[]", "null", "none", "nan"}
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _blank(column: Column) -> Any:
    """O valor VAZIO do tipo documentado — nunca um valor plausível.

    Escalar sai ``null`` (em JSON, ausência de valor); uma coleção sem membros enumerados
    sai vazia (``[]``/``{}``); uma coleção COM membros enumerados é montada pelo
    construtor, para que os caminhos documentados das suas posições não sumam.
    """
    kind = (column.type or "").lower()
    if kind == "array":
        return []
    if kind in {"object", "dynamic"}:
        return {}
    return None


def documented_document(columns: Sequence[Column], values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Monta o documento aninhado cujos CAMINHOS são exatamente as colunas documentadas.

    ``values`` mapeia caminho -> valor SÓ para o que o modelo canônico sustenta; todo o
    resto sai vazio (:func:`_blank`). A ordem de inserção é a ordem da documentação, o que
    mantém o artefato determinístico e legível.
    """
    supplied = dict(values or {})
    parents = container_paths(columns)
    document: dict[str, Any] = {}
    for column in columns:
        _ensure(document, column.name.split("."))
    for column in columns:
        if column.name in parents:
            # Um contêiner documentado vale pela ESTRUTURA que hospeda; o valor vazio do
            # seu tipo não pode substituí-la.
            continue
        _assign(document, column.name.split("."), supplied.get(column.name, _blank(column)))
    return document


def _ensure(node: dict[str, Any], segments: Sequence[str]) -> None:
    head, rest = segments[0], segments[1:]
    if head.endswith("[]"):
        key = head[:-2]
        items = node.get(key)
        if items is None:
            items = []
            node[key] = items
        if not isinstance(items, list):  # pragma: no cover - spec contraditória
            raise RenderError(f"{key!r}: membro documentado e lista documentada ao mesmo tempo")
        if not items:
            items.append({})
        item = items[0]
        if not rest:
            return
        if not isinstance(item, dict):  # pragma: no cover - defensivo
            raise RenderError(f"{key!r}: elemento de lista não é objeto")
        _ensure(item, rest)
        return
    if not rest:
        if head.endswith("[]"):  # pragma: no cover - defensivo
            raise RenderError(f"{head!r}: campo documentado termina em '[]'")
        node.setdefault(head, None)
        return
    child = node.get(head)
    if child is None:
        child = {}
        node[head] = child
    if not isinstance(child, dict):  # pragma: no cover - spec contraditória
        raise RenderError(f"{head!r}: membro documentado e objeto documentado ao mesmo tempo")
    _ensure(child, rest)


def _assign(node: Any, segments: Sequence[str], value: Any) -> None:
    head, rest = segments[0], segments[1:]
    if not rest:
        node[head] = value
        return
    if head.endswith("[]"):
        _assign(node[head[:-2]][0], rest, value)
        return
    _assign(node[head], rest, value)


def flatten_document(payload: Any) -> list[dict[str, Any]]:
    """Achata o documento entregue: um dicionário por registo, chave = caminho pontuado.

    Convenção (a mesma do leitor independente do teste): uma chave de objeto vira um caminho;
    uma lista não acrescenta caminho próprio, e cada elemento continua o caminho do pai com
    ``[]``. Um caminho guarda o valor que aquele caminho tem no documento -- inclusive um
    contêiner, que guarda a sua subárvore.

    O conjunto de chaves que este achatamento produz inclui os CONTÊINERES ESTRUTURAIS (o
    caminho que hospeda um caminho documentado sem ser ele próprio uma coluna da spec). Quem
    precisa do conjunto de campos que a spec enumera usa :func:`documented_projection`.
    """
    rows = payload if isinstance(payload, list) else [payload]
    flat: list[dict[str, Any]] = []
    for row in rows:
        fields: dict[str, Any] = {}
        _walk(row, "", fields)
        flat.append(fields)
    return flat


def documented_projection(payload: Any, columns: Sequence[Column]) -> list[dict[str, Any]]:
    """A projeção do documento REAL com EXATAMENTE os campos que a spec enumera.

    O núcleo de fidelidade lê o conjunto de campos de um arquivo (``columns_of``), e um
    documento da nuvem é aninhado. Esta projeção é o que aterra o documento no nível que a
    especificação nomeia (``properties.storageProfile.osDisk.caching``), e ela é calculada a
    partir dos BYTES entregues, nunca de uma segunda cópia em memória.

    Um contêiner que a spec NÃO lista (``...networkInterfaces[].properties``) existe no
    documento porque é ele que hospeda os caminhos documentados -- mas ele não é um campo da
    especificação, e publicá-lo como coluna INVENTARIA um nome que a documentação não define.
    Por isso o achatamento completo (:func:`flatten_document`) serve para auditar a ESTRUTURA
    do documento, e só os caminhos enumerados entram nesta projeção.
    """
    allowed = {column.name for column in columns}
    return [
        {name: value for name, value in row.items() if name in allowed}
        for row in flatten_document(payload)
    ]


def _walk(node: Any, prefix: str, fields: dict[str, Any]) -> None:
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        path = f"{prefix}{key}"
        fields[path] = value
        if isinstance(value, list):
            for item in value:
                _walk(item, f"{path}[].", fields)
        else:
            _walk(value, f"{path}.", fields)


def write_json(path: Path, payload: Any) -> Path:
    """Escreve ``payload`` como JSON determinístico (indent=2, UTF-8, fim de linha final)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


#: O arquivo IRMÃO que carrega o relatório de proveniência (nunca dentro do artefato).
PROVENANCE_FILE = "_provenance.json"


def arm_id_token(arm_id: str, key: str) -> str | None:
    """O token que segue ``key`` num ARM resource id (``subscriptions``/``resourceGroups``)."""
    segments = [segment for segment in arm_id.split("/") if segment]
    lowered = [segment.lower() for segment in segments]
    wanted = key.lower()
    if wanted not in lowered:
        return None
    index = lowered.index(wanted)
    return segments[index + 1] if index + 1 < len(segments) else None


def arm_resource_name(arm_id: str) -> str:
    """O último segmento de um ARM resource id -- o NOME do recurso que ele endereça."""
    return arm_id.rstrip("/").rsplit("/", 1)[-1]


def mac_wire(mac: str) -> str:
    """O MAC na forma que a documentação da Azure exemplifica: 12 dígitos hex, sem separadores.

    ``model/network.py`` guarda o MAC na forma canônica com ``:``; a Azure publica
    ``000D3AF87856`` (maiúsculas, sem separador) tanto na partição ``macAddress=`` quanto em
    ``flows[].mac``. A conversão é de FORMATO -- o valor é o mesmo --, como a do número IANA
    para o literal de protocolo.
    """
    return mac.replace(":", "").replace("-", "").upper()


def provenance(
    spec: SurfaceSpec,
    *,
    spec_file: str,
    artifacts: Sequence[str],
    mechanism: Mapping[str, Any],
    columns: Mapping[str, Any],
    counts: Mapping[str, Any],
    model_gaps: Sequence[Mapping[str, Any]],
    not_generated: Sequence[Mapping[str, Any]] = (),
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """O relatório IRMÃO do artefato: a spec, o mecanismo, as contagens e as lacunas.

    Fica num arquivo à parte, sempre: um ingestor do artefato não pode ver uma chave que
    nuvem nenhuma documenta (``surface``/``spec``/``model_gaps``...), e a proveniência é o
    entregável que diz o que NÃO foi gerado e por quê. As cinco superfícies deste slice
    compartilham este formato, para que os relatórios sejam comparáveis entre si.
    """
    report: dict[str, Any] = {
        "kind": "provenance",
        "surface": spec.surface,
        "spec": f"specs/{spec_file}",
        "artifacts": list(artifacts),
        "mechanism": dict(mechanism),
        "columns": dict(columns),
        "counts": dict(counts),
        "not_generated": [dict(entry) for entry in not_generated],
        "model_gaps": [dict(entry) for entry in model_gaps],
    }
    if extra:
        report.update(extra)
    return report


def not_generated(spec: SurfaceSpec, scope: str | None = None) -> list[dict[str, Any]]:
    """As colunas que o escopo descreve e o CONTRATO não autoriza a gerar, com o motivo.

    É o conteúdo mais importante do relatório: uma coluna aqui está descrita e fora do
    artefato de propósito, e o motivo distingue "a documentação não publica tipo" de "a
    documentação só mostra um exemplo".
    """
    entries: list[dict[str, Any]] = []
    for column in spec.columns if scope is None else spec.columns_for(scope):
        if column.is_generatable:
            continue
        if column.belongs_to_schema:
            reason = f"evidence={column.evidence!r}: pertence ao formato e nunca recebe valor"
        elif not column.type:
            reason = f"sem tipo publicado (evidence={column.evidence!r}): a spec descreve o campo e nao afirma a forma"
        elif (column.evidence or "").lower() not in {"declared", "null-empty", ""}:
            reason = f"evidence={column.evidence!r}: documentado por exemplo, nao por contrato"
        else:
            reason = "sem status verificado ou sem source_url: nao ha evidencia para gerar"
        entries.append(
            {"column": column.name, "type": column.type, "evidence": column.evidence, "reason": reason}
        )
    return entries


# -- esta superfície -------------------------------------------------------------------


@cache
def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada uma vez; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def virtual_machines(estate: CanonicalEstate) -> list[Resource]:
    """As VMs Azure do estado, em ordem determinística (scope, nome)."""
    return sorted(
        (
            resource
            for resource in estate.resources
            if resource.identity.provider == _AZURE and resource.resource_type == "virtual_machine"
        ),
        key=lambda resource: (resource.parent_scope_id, resource.resource_name),
    )


def _values(resource: Resource, interface: NetworkInterface | None) -> dict[str, Any]:
    """O que o modelo canônico sustenta para esta VM — e só isso.

    ``name``/``location``/``properties.hardwareProfile.vmSize`` são os campos cujo valor o
    ``Resource`` carrega (``resource_name``, ``region_id``, ``sku_id``), e
    ``properties.networkProfile.networkInterfaces[].id`` passou a ter origem quando o modelo
    de rede ligou cada interface a um recurso (``NetworkInterface.resource_uuid``): a resposta
    passa a nomear a NIC que a VM usa, em vez de deixar a lista vazia. Todo o resto da
    representação ARM — id, tags, perfil de SO, discos, identidade, plano — não tem origem no
    modelo e sai vazio.
    """
    values: dict[str, Any] = {
        "name": resource.resource_name,
        "location": resource.region_id,
        "properties.hardwareProfile.vmSize": resource.sku_id,
    }
    if interface is not None:
        values["properties.networkProfile.networkInterfaces[].id"] = interface.interface_id
    return values


def instance_document(resource: Resource, interface: NetworkInterface | None = None) -> dict[str, Any]:
    """O corpo da resposta ``VirtualMachine`` para ``resource``: a forma documentada, valores do modelo."""
    return documented_document(emittable_columns(_spec()), _values(resource, interface))


def _model_gaps() -> list[dict[str, Any]]:
    """As lacunas que mantêm campos vazios nesta resposta -- o entregável do relatório."""
    return [
        {
            "item": "ARM resource id e resource group do recurso",
            "reason": (
                "o Resource canonico nao carrega o ARM id nem o resource group; ``id`` e ``type`` "
                "sao example-only na spec, entao a unica identidade da resposta e o caminho do GET"
            ),
        },
        {
            "item": "tags",
            "reason": (
                "o Resource TEM tags, mas a spec descreve ``tags`` por exemplo (example-only): "
                "emiti-lo seria campo sem contrato"
            ),
        },
        {
            "item": "properties.vmId / properties.provisioningState / properties.timeCreated",
            "reason": "example-only na spec: o payload os mostra e nao estabelece schema para eles",
        },
        {
            "item": "perfil de SO, discos e imagem",
            "reason": "o modelo nao tem adminUsername, computerName, osType, tamanho de disco nem imagem",
        },
        {
            "item": "identidade, plano, host, placement e profiles de seguranca",
            "reason": "nenhuma entidade do estado os modela; a FORMA sai com todos os membros vazios",
        },
        {
            "item": "properties.capacityReservation.capacityReservationGroup.id",
            "reason": (
                "o modelo tem CapacityReservation, mas so para tipos AWS-elegiveis; nenhuma VM "
                "Azure carrega uma, e o id do GROUP nao existe em campo nenhum"
            ),
        },
        {
            "item": "forma do token de assinatura nos ARM ids",
            "reason": (
                "os ARM ids do modelo de rede embutem o rotulo de escopo (``sub-01``), enquanto as "
                "superficies de fatura usam o GUID de ``azure_subscription_guid``; o renderer NAO "
                "reescreve id nenhum -- a divergencia fica registrada aqui"
            ),
        },
        {
            "item": "NIC de recurso acrescentado por CENARIO",
            "reason": (
                "o inventario de rede e construido dentro do build do estado, antes da emissao dos "
                "cenarios: um recurso que um cenario acrescenta depois (o C18, por exemplo) nao tem "
                "NetworkInterface, e a lista ``networkInterfaces`` sai vazia para ele em vez de "
                "receber um id inventado"
            ),
        },
    ]


class AzureArmInstancesRenderer:
    """Entrega uma resposta ARM ``GET .../virtualMachines/{vmName}`` por VM Azure do estado."""

    name = "azure_arm_instances"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve um JSON por VM sob ``out_dir/azure_arm_instances/subscriptions/...``."""
        target = out_dir / self.name
        columns = emittable_columns(_spec())
        interfaces = {interface.resource_uuid: interface for interface in estate.network_interfaces}
        written: list[Path] = []
        filled: Counter[int] = Counter()
        for resource in virtual_machines(estate):
            subscription = azure_subscription_guid(estate.seed, resource.parent_scope_id)
            document = (
                target
                / "subscriptions"
                / subscription
                / "resourceGroups"
                / _RESOURCE_GROUP_SEGMENT
                / "providers"
                / "Microsoft.Compute"
                / "virtualMachines"
                / f"{resource.resource_name}.json"
            )
            write_json(document, instance_document(resource, interfaces.get(resource.identity.uuid)))
            # A projeção é derivada dos BYTES entregues (lidos de volta do disco) e carrega os
            # 301 campos que a spec enumera -- nenhum contêiner intermediário a mais.
            projection = target / "field_projection" / f"{subscription}__{resource.resource_name}.json"
            rows = documented_projection(json.loads(document.read_text(encoding="utf-8")), columns)
            write_json(projection, rows)
            filled[leaf_filled_fields(columns, rows[0])] += 1
            written.extend((document, projection))
        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=["subscriptions/**/virtualMachines/*.json", "field_projection/*.json", PROVENANCE_FILE],
                mechanism={
                    "kind": "arm-rest-api",
                    "endpoint": (
                        "GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/"
                        "{resourceGroupName}/providers/Microsoft.Compute/virtualMachines/{vmName}"
                        "?api-version=2026-04-01"
                    ),
                    "responses": {"200": "VirtualMachine", "other": "CloudError"},
                    "api_version": "2026-04-01",
                    "blob_path": None,
                    "partitioning": None,
                    "compression": None,
                    "manifest": None,
                    "note": (
                        "corpo de resposta de um GET do plano de controle ARM, nao um export: a propria "
                        "spec registra que nenhum caminho de blob, particionamento, compressao ou manifesto "
                        "existe para esta superficie"
                    ),
                    "layout": "um arquivo por VM, no caminho que o endpoint do GET endereca",
                    "resource_group_segment": _RESOURCE_GROUP_SEGMENT,
                    "resource_group_segment_note": (
                        "o estado nao carrega resource group; o segmento carrega o token do PROPRIO template "
                        "da documentacao em vez de um nome inventado"
                    ),
                },
                columns={
                    "documented": len(_spec().columns),
                    "emittable": len(columns),
                    "generated": len(columns),
                    "with_value": max(filled, default=0),
                    "empty": len(columns) - max(filled, default=0),
                    "with_value_note": (
                        "campos FOLHA que carregam valor numa resposta tipica; um conteiner documentado "
                        "(``properties.hardwareProfile``) hospeda os filhos e nao conta como valor. "
                        "``fields_with_value_per_document`` mostra a distribuicao: um documento com um "
                        "campo a menos e um recurso acrescentado por cenario, que nao tem NIC no inventario"
                    ),
                    "fields_with_value_per_document": {
                        str(count): documents for count, documents in sorted(filled.items())
                    },
                },
                counts={
                    "documents": len(virtual_machines(estate)),
                    "virtual_machines": len(virtual_machines(estate)),
                    "structural_containers": len(structural_containers(_spec())),
                },
                not_generated=not_generated(_spec()),
                model_gaps=_model_gaps(),
                extra={
                    "naming": {
                        "level": "caminho pontuado da spec (a spec aninha propriedades)",
                        "projection": (
                            "field_projection/<assinatura>__<vm>.json carrega EXATAMENTE os caminhos que a spec "
                            "enumera: um conteiner que a spec nao lista nao vira coluna do artefato"
                        ),
                    }
                },
            ),
        )
        written.append(target / PROVENANCE_FILE)
        return written
