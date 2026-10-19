"""The provider boundary for every runtime projection in gcp-sim (Phase 6).

gcp-sim consumes the **multi-cloud** canonical estate, so each surface must answer with
its own provider's rows. The renderer side already filters (``render/gcp_rest_fixtures.py:39``
builds every fixture from the estate's GCP resources only), but a runtime projection that
walks ``estate.resources`` without a filter answers a GCP screen with an Azure VM or an AWS
EC2 instance -- the owner's fidelity requirement inverted -- and that is the failure this
module exists to make impossible. Every Phase 6 projection reads its rows through here, so
the boundary is one place to check rather than one per router (the same discipline as
``emulators/azure-sim/azure_sim/projections/scope.py`` and ``emulators/aws-sim/aws_sim/scope.py``).

Where the provider lives on the model, and therefore where each filter is written:

* a resource carries ``ResourceIdentity.provider`` (the operational key, lowercase ``gcp``
  -- the key ``generate/constants.py`` dispatches on), so :func:`resources` and
  :func:`resources_of_type` filter on that field;
* the GCP hierarchy is the ``GcpOrg -> GcpFolder -> GcpProject`` tree, which is GCP by
  type. :func:`projects` is the only reader of ``estate.gcp_orgs`` in this package, so no
  projection can reach another provider's scoping through the hierarchy.

Scope selection is by ``parent_scope_id``, which on a GCP resource is the owning
``project_id`` (``model/resource.py``; the gate's ``check_resource_scoping`` enforces that
FK). A project this estate does not carry therefore selects **nothing**: the projections
answer with what the emulator owns instead of inventing a row for something it does not,
which is the position ``emulators/aws-sim/aws_sim/projections/elbv2.py`` already takes.
"""

from __future__ import annotations

from dataclasses import dataclass

from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.hierarchy import GcpProject
from tools.synthetic_clouds.model.resource import Resource

#: The operational provider key (``ResourceIdentity.provider``), lowercase.
PROVIDER = "gcp"


@dataclass(slots=True, frozen=True)
class ProjectScope:
    """One GCP project together with the folder that owns it.

    ``GcpProject`` carries no link back to its folder -- the nesting is the link -- so the
    walk that builds this pair is the only place the parent is known. ``projects.list``
    reports that parent, and a projection that re-derived it from the id would be guessing.
    """

    project: GcpProject
    folder_id: str


def resources(estate: CanonicalEstate) -> tuple[Resource, ...]:
    """This provider's resources, in estate order."""
    return tuple(r for r in estate.resources if r.identity.provider == PROVIDER)


def resources_of_type(
    estate: CanonicalEstate,
    resource_type: str,
    project_id: str | None = None,
) -> tuple[Resource, ...]:
    """This provider's resources of one ``resource_type``, ordered by name.

    ``project_id`` narrows the result to one project; ``None`` covers every GCP project
    the estate carries. Ordering is by ``resource_name`` so a page is stable across calls
    (the estate's own order is by uuid, which no wire shape sorts by).
    """
    return tuple(
        sorted(
            (
                r
                for r in resources(estate)
                if r.resource_type == resource_type and (project_id is None or r.parent_scope_id == project_id)
            ),
            key=lambda r: r.resource_name,
        ),
    )


def projects(estate: CanonicalEstate) -> tuple[ProjectScope, ...]:
    """Every GCP project of the org/folder tree, in estate order.

    The estate models one organization holding folders holding projects; flattening it
    here keeps the parent folder attached to each project instead of dropping it the way a
    plain project list would.
    """
    return tuple(
        ProjectScope(project=project, folder_id=folder.folder_id)
        for org in estate.gcp_orgs
        for folder in org.folders
        for project in folder.projects
    )
