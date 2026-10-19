"""Azure Compute resource plane: ``virtualMachines`` and ``disks`` (Phase 6).

``virtual_machines.list_all`` is consumed today: ``resources.py (modulo do consumidor):49`` reads ``vm.id``, ``vm.name`` and ``vm.location`` and, for the VM size,
``vm.hardware_profile.vm_size``. ``vmSize`` is therefore nested under
``properties.hardwareProfile`` — that is where ``VirtualMachine._attribute_map`` looks for
it, and a row that put it anywhere else would read as a VM with no size, not as an error.
The estate carries no NIC, no OS image, no admin login and no data disk
(``model/resource.py`` holds identity, scope, region, tags and a SKU), so none of those
are emitted: an empty ``networkProfile`` would assert a VM attached to nothing, which is a
claim about the VM rather than about the estate.

``disks`` has no consumer yet; it is served because ``managed_disk`` resources exist in the
estate (28 VMs to 27 disks in the small profile) and a subscription-scoped
``Microsoft.Compute/disks`` that 404'd would read as "this subscription has no disks".

Both rows are the resource's identity plus a **closed** map from the estate's ``sku_id``
to the ARM vocabulary it names (``azure-vm-d2s-v5`` -> ``Standard_D2s_v5``,
``azure-disk-p10`` -> ``P10``). Closed on purpose: an unmapped SKU is a generator change
upstream and must raise here rather than let a plausible-looking size reach a caller —
the rule ``aws_sim/projections/ec2.py:82`` applies to instance types. The disk capacity is
part of that same map because in Azure the SKU name IS the size band (P10 = 128 GiB in the
published Premium SSD catalogue), so it is read off the estate's own SKU rather than
invented.
"""

from __future__ import annotations

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.resource import Resource

from azure_sim.projections import arm, scope

#: The estate's ``resource_type`` values (``generate/constants.py:49``). The ARM types they
#: are served as live in ``projections/arm.py``, which is also where the id built from them
#: comes from — one table, so the row and the id cannot name two different types.
VIRTUAL_MACHINE = "virtual_machine"
MANAGED_DISK = "managed_disk"

#: ``sku_id`` -> ARM VM size. One entry per SKU the Azure catalogue carries today.
VM_SIZES: dict[str, str] = {
    "azure-vm-d2s-v5": "Standard_D2s_v5",
}

#: ``sku_id`` -> (ARM sku name, sku tier, capacity in GiB), the capacity being the one the
#: SKU name itself fixes in Azure's Premium SSD catalogue.
DISK_SKUS: dict[str, tuple[str, str, int]] = {
    "azure-disk-p10": ("Premium_LRS", "Premium", 128),
}


def project_virtual_machines(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``virtualMachines.list_all`` rows: this provider's VMs, ordered by name."""
    return [
        arm.arm_row(
            estate,
            resource,
            arm_type=arm.VIRTUAL_MACHINE_TYPE,
            properties={
                "hardwareProfile": {"vmSize": VM_SIZES[resource.sku_id]},
                "provisioningState": arm.PROVISIONING_SUCCEEDED,
            },
        )
        for resource in scope.of_type(estate, VIRTUAL_MACHINE)
    ]


def _disk_row(estate: CanonicalEstate, resource: Resource) -> dict[str, object]:
    """One ``disks`` row for an estate managed disk."""
    sku_name, tier, size_gb = DISK_SKUS[resource.sku_id]
    return arm.arm_row(
        estate,
        resource,
        arm_type=arm.DISK_TYPE,
        properties={
            "diskSizeGB": size_gb,
            "provisioningState": arm.PROVISIONING_SUCCEEDED,
        },
        top_level={"sku": {"name": sku_name, "tier": tier}},
    )


def project_disks(estate: CanonicalEstate) -> list[dict[str, object]]:
    """Return ``disks`` rows: this provider's managed disks, ordered by name."""
    return [_disk_row(estate, resource) for resource in scope.of_type(estate, MANAGED_DISK)]

