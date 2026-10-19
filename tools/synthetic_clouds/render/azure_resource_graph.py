"""Azure Resource Graph — the response of a ``resources`` query projected on ``microsoft.compute/virtualmachines``.

Surface: ``specs/azure/azure-resource-graph-virtual-machines.schema.json`` — 148 columns in
12 named sets; only ``Resources/microsoft.compute/virtualmachines`` (33 columns, 32
emittable/generatable) has a published shape, and that is the scope this renderer serves.
Every other set (``Resources``, the ten ``SecurityResources/*`` sets) is ``example-only``:
the columns are named in the official page but no type is asserted, so they are described
and NOT generatable. Emitting any of them is a finding, not a wider scope.

WHAT THIS SURFACE IS (and what it is NOT)
-----------------------------------------
``delivery.kind`` is ``query-api``: ``POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2024-04-01``,
``result_formats: ["Table", "ObjectArray"]``, and the spec's own note records that Resource
Graph "is a QUERY service, not a push export. There is no documented delivery to Azure
Storage, Log Analytics or Event Hub." The artifact is therefore the response of the query —
NOT a file in a bucket, and NOT a table in a workspace.

``ObjectArray`` is the delivered result format (a bare JSON array of rows) because it is the
one whose SHAPE is documented by the spec: an envelope (``count``/``totalRecords``/
``skipToken``/``resultTruncated``) is a field of no set, so emitting one would be an
invented field. The ``Table`` format is not emitted for the same reason: its ``columns`` and
``rows`` members are documented nowhere in this surface's sets.

WHAT THE QUERY RESPONSE CAN AND CANNOT CARRY
--------------------------------------------
* Only ``properties.*`` of a VM is documented (the ``Resources`` set that would carry
  ``id``/``name``/``type``/``location``/``resourceGroup``/``subscriptionId``/``tenantId``/
  ``tags`` is ``example-only``). A faithful row therefore has EXACTLY one top-level member,
  ``properties``, and no row identity beyond it.
* ``properties.vmId`` is the ONE identity-shaped column inside that shape, and it is what
  keeps the row joinable to the estate: it is filled with the resource's own
  ``ResourceIdentity.uuid``. ``TODO-verificar``: that is a DERIVED id in the documented
  shape (a GUID the platform assigns), NOT the GUID Azure assigned — the same discipline
  ``model/identity.py`` records for ``aws_resource_id``/``capacity_reservation_id``.
* The estate models no provisioning state and no OS/disk/image detail, so
  ``properties.provisioningState`` and ``properties.storageProfile.*`` (except the shape
  itself) are emitted empty. The model's off-standard resource names (FR-D3) are deliberately
  NOT reused as ``properties.osProfile.computerName``: a computer name has a charset/length
  contract that ``virtual_machine-0007 (do not delete)`` breaks.
* ``properties.networkProfile.networkInterfaces[].id`` and ``[].resourceGroup`` DID acquire a
  source when the network model bound each ``NetworkInterface`` to the resource it belongs to:
  the row names the VM's NIC and its resource group. The member paths exist for every row (ONE
  element, empty where the estate has nothing): without the element the documented member paths
  would vanish from the response, and an absent documented field is a different defect from an
  empty one. A resource a SCENARIO added after the network inventory was built has no NIC, and
  its two members stay empty -- counted in ``_provenance.json``.

The query response is accompanied by the sibling ``_provenance.json`` (the mechanism, the 32
emitted paths, the counts and the model gaps); the artifact itself carries only documented
fields.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.network import NetworkInterface, NetworkSegment
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.azure_arm_instances import (
    PROVENANCE_FILE,
    documented_document,
    documented_projection,
    emittable_columns,
    leaf_filled_fields,
    not_generated,
    provenance,
    structural_containers,
    virtual_machines,
    write_json,
)
from tools.synthetic_clouds.render.base import RenderError

#: O caminho da especificação normativa DENTRO de ``specs/`` (a proveniência cita este texto).
_SPEC_FILE = "azure/azure-resource-graph-virtual-machines.schema.json"

#: A especificação normativa desta superfície (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

#: O conjunto desta superfície que tem forma publicada -- e o escopo obrigatório de
#: ``check_artifact`` (a superfície tem 12 conjuntos nomeados).
VM_SCOPE = "Resources/microsoft.compute/virtualmachines"


@cache
def _spec() -> SurfaceSpec:
    """A spec normativa desta superfície, carregada uma vez; falha FECHADO se não servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _values(resource: Resource, interface: NetworkInterface | None, segment: NetworkSegment | None) -> dict[str, Any]:
    """O que o modelo canônico sustenta para esta linha de VM -- e só isso.

    ``properties.networkProfile.networkInterfaces[].id``/``.resourceGroup`` ganharam origem
    quando o modelo de rede ligou cada interface a um recurso: a linha passa a nomear a NIC da
    VM e o resource group dela, em vez de deixar os dois membros vazios.
    """
    values: dict[str, Any] = {
        "properties.hardwareProfile.vmSize": resource.sku_id,
        # TODO-verificar: id derivado NA FORMA documentada (GUID), não o GUID que a Azure
        # atribuiu -- a mesma disciplina de ``identity.aws_resource_id``.
        "properties.vmId": resource.identity.uuid,
    }
    if interface is not None:
        values["properties.networkProfile.networkInterfaces[].id"] = interface.interface_id
        if segment is not None and segment.resource_group:
            values["properties.networkProfile.networkInterfaces[].resourceGroup"] = segment.resource_group
    return values


def query_rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """As linhas da resposta ``ObjectArray``: uma por VM Azure, na forma documentada."""
    columns = emittable_columns(_spec(), VM_SCOPE)
    interfaces = {interface.resource_uuid: interface for interface in estate.network_interfaces}
    segments = {segment.segment_uuid: segment for segment in estate.network_segments}
    rows: list[dict[str, Any]] = []
    for resource in virtual_machines(estate):
        interface = interfaces.get(resource.identity.uuid)
        segment = segments.get(interface.segment_uuid) if interface is not None else None
        rows.append(documented_document(columns, _values(resource, interface, segment)))
    return rows


class AzureResourceGraphRenderer:
    """Entrega a resposta (``ObjectArray``) de uma query ``resources`` sobre as VMs Azure do estado."""

    name = "azure_resource_graph"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve a resposta da query, a projeção dela e o relatório sob ``out_dir/azure_resource_graph``."""
        target = out_dir / self.name
        columns = emittable_columns(_spec(), VM_SCOPE)
        response = target / "virtualmachines_objectarray.json"
        write_json(response, query_rows(estate))
        # A projeção é derivada dos BYTES entregues (lidos de volta do disco) e carrega os 32
        # caminhos que a spec enumera -- o contêiner ``properties`` que a hospeda não é uma
        # coluna da especificação e não é publicado como tal.
        projection = target / "field_projection" / "virtualmachines.json"
        rows = documented_projection(json.loads(response.read_text(encoding="utf-8")), columns)
        write_json(projection, rows)
        write_json(
            target / PROVENANCE_FILE,
            provenance(
                _spec(),
                spec_file=_SPEC_FILE,
                artifacts=["virtualmachines_objectarray.json", "field_projection/virtualmachines.json", PROVENANCE_FILE],
                mechanism={
                    "kind": "query-api",
                    "endpoint": "POST https://management.azure.com/providers/Microsoft.ResourceGraph/resources?api-version=2024-04-01",
                    "result_format": "ObjectArray",
                    "result_formats_documented": ["Table", "ObjectArray"],
                    "objectarray_note": (
                        "o resultado entregue e o formato ``ObjectArray`` (um array de linhas); um envelope "
                        "(``count``/``totalRecords``/``skipToken``/``resultTruncated``) e campo de conjunto nenhum "
                        "desta superficie, entao emiti-lo seria campo inventado"
                    ),
                    "table_format_note": (
                        "o formato ``Table`` nao e entregue: ``columns``/``rows`` nao sao membros que a spec "
                        "documente em conjunto nenhum"
                    ),
                    "storage_delivery": None,
                    "storage_delivery_note": (
                        "Resource Graph e um servico de CONSULTA: nao ha entrega documentada para Storage, "
                        "Log Analytics ou Event Hub, e nao se inventa uma"
                    ),
                    "path_template": None,
                    "partitioning": None,
                    "compression": None,
                    "manifest": None,
                    "limits": {"default_records_per_query": 1000, "max_first_or_top": 1000, "csv_export_max_records": 55000},
                },
                columns={
                    "documented": len(_spec().columns),
                    "emittable": len(columns),
                    "generated": len(columns),
                    "set": VM_SCOPE,
                    "sets_total": len(_spec().set_names),
                    "sets_without_published_shape": {
                        scope: len(_spec().columns_for(scope))
                        for scope in _spec().set_names
                        if scope != VM_SCOPE
                    },
                },
                counts={
                    "rows": len(rows),
                    "virtual_machines": len(virtual_machines(estate)),
                    "fields_with_value": leaf_filled_fields(columns, rows[0]) if rows else 0,
                    "fields_with_value_note": (
                        "campos FOLHA que carregam valor na primeira linha; um conteiner documentado "
                        "(``properties.hardwareProfile``) hospeda os filhos e nao conta como valor"
                    ),
                    "rows_without_a_nic": len(
                        [
                            resource
                            for resource in virtual_machines(estate)
                            if resource.identity.uuid not in {item.resource_uuid for item in estate.network_interfaces}
                        ]
                    ),
                    "structural_containers": len(structural_containers(_spec(), VM_SCOPE)),
                },
                not_generated=not_generated(_spec(), VM_SCOPE),
                model_gaps=[
                    {
                        "item": "colunas de identidade da linha (``id``/``name``/``type``/``location``/``resourceGroup``/``subscriptionId``/``tenantId``/``tags``)",
                        "reason": (
                            "o conjunto ``Resources`` que as carrega e example-only: nenhum tipo publicado, entao "
                            "nenhuma delas entra no artefato. A identidade sobrevive em ``properties.vmId``"
                        ),
                    },
                    {
                        "item": "estado de provisionamento e disco/OS/imagem da VM",
                        "reason": "o Resource nao carrega estado, tamanho de disco, osType nem imagem; as colunas saem vazias",
                    },
                    {
                        "item": "ARM resource id do recurso",
                        "reason": "o modelo nao tem o ARM id do recurso (a NIC tem o dela); ``properties.vmId`` e o id derivado",
                    },
                    {
                        "item": "propriedades de instance view (``properties.extended.instanceView.powerState.code``)",
                        "reason": "declarada na spec sem tipo publicado: descrita e nao-geravel, fora do artefato",
                    },
                    {
                        "item": "NIC de recurso acrescentado por CENARIO",
                        "reason": (
                            "o inventario de rede e construido antes da emissao dos cenarios: um recurso que um "
                            "cenario acrescenta depois nao tem NetworkInterface, e os dois membros "
                            "``networkInterfaces[].id``/``.resourceGroup`` saem vazios para ele"
                        ),
                    },
                ],
                extra={
                    "naming": {
                        "level": "caminho pontuado da spec (a tabela ``Resources`` aninha ``properties.*``)",
                        "projection": (
                            "field_projection/virtualmachines.json carrega EXATAMENTE os 32 caminhos que a spec "
                            "enumera; o conteiner ``properties`` existe no documento e nao vira coluna"
                        ),
                    }
                },
            ),
        )
        written = [response, projection, target / PROVENANCE_FILE]
        return written
