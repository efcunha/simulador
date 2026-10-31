# `infrastructure-manager-resource-drift` — Infrastructure Manager `resourceDrifts`

## 1. Identificação

- **Superfície:** `Infrastructure Manager` → `previews` → `resourceDrifts`
  (`projects.locations.previews.resourceDrifts.list` / `get`).
- **Documentos oficiais e datas de consulta (2026-10-27):**

| Documento | URL | Consultado em |
|---|---|---|
| REST Resource: `projects.locations.previews.resourceDrifts` (`ResourceDrift`, `ResourceDriftTerraformInfo`, `PropertyDrift`) | <https://docs.cloud.google.com/infrastructure-manager/docs/reference/rest/v1/projects.locations.previews.resourceDrifts> | 2026-10-27 |
| Method: `resourceDrifts.list` (path, query, response envelope) | <https://docs.cloud.google.com/infrastructure-manager/docs/reference/rest/v1/projects.locations.previews.resourceDrifts/list> | 2026-10-27 |
| Export and view preview results (preview must be SUCCEEDED/STALE; `resource-drifts list`) | <https://docs.cloud.google.com/infrastructure-manager/docs/export-view-preview-results> | 2026-10-27 |

- **Versão:** Infrastructure Manager API **v1**, host `config.googleapis.com`.

## 2. Mecanismo

1. O operador cria um **preview** de uma configuração Terraform.
2. O preview precisa estar `SUCCEEDED` ou `STALE` para ser exportado/consultado.
3. `GET https://config.googleapis.com/v1/{parent=projects/*/locations/*/previews/*}/resourceDrifts`
   devolve `ResourceDrift[]`.
4. `GET .../resourceDrifts/{resource_drift}` devolve um item.

Isso **não é um export de arquivo**: é uma resposta de API do plano de controle. Não há blob,
partição, compressão ou manifesto documentado.

## 3. Envelope e item

Resposta do `list`:

```json
{
  "resourceDrifts": [ { "object (ResourceDrift)" } ],
  "nextPageToken": "string",
  "unreachable": [ "string" ]
}
```

`ResourceDrift`:

```json
{
  "name": "projects/PROJECT/locations/LOCATION/previews/PREVIEW/resourceDrifts/RESOURCE_DRIFT",
  "terraformInfo": {
    "address": "google_compute_instance.web",
    "type": "google_compute_instance",
    "resourceName": "web",
    "provider": "registry.terraform.io/hashicorp/google"
  },
  "propertyDrifts": [
    {
      "path": "machine_type",
      "beforeSensitivePaths": [],
      "before": "e2-medium",
      "afterSensitivePaths": [],
      "after": "e2-standard-2"
    }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `name` | string | identificador do `ResourceDrift` |
| `terraformInfo.address` | string | endereço do recurso no state |
| `terraformInfo.type` | string | tipo Terraform (`google_compute_instance`) |
| `terraformInfo.resourceName` | string | nome lógico do recurso no Terraform |
| `terraformInfo.provider` | string | provider Terraform |
| `propertyDrifts[].path` | string | caminho da propriedade (path do Terraform/state) |
| `propertyDrifts[].before` | value | representação antes das ações |
| `propertyDrifts[].after` | value | representação depois das ações |
| `propertyDrifts[].beforeSensitivePaths[]` | string[] | paths sensíveis dentro de `before` |
| `propertyDrifts[].afterSensitivePaths[]` | string[] | paths sensíveis dentro de `after` |

## 4. O que o simulador projeta

O simulador **não** inventa o drift: ele emite o input C11 (tags declaradas no snapshot de IaC
vs. tags do inventário) e projeta o resultado no contrato acima. O caminho é
`model/drift.py::project_drift_views`; o mesmo documento é servido por
`emulators/gcp-sim/gcp_sim/routers/infra_manager.py`.

- `terraformInfo.address` = `google_compute_instance.<rótulo>`; o rótulo é derivado do nome do
  recurso (caracteres inválidos viram `_`), nunca um literal fixo.
- `propertyDrifts[].path` = `labels.<chave>`; `before` = valor atual, `after` = declarado
  (`null` quando a tag foi removida do estado desejado).
- `name` usa `location` = região do recurso e `preview` = `synthetic-drift` (nome escolhido
  pelo simulador; não é um nome do provedor).

## 5. Não comprovado

| Item | Motivo |
|---|---|
| forma concreta de `before`/`after` por tipo Terraform | a referência publica `value (Value format)`, sem schema por tipo; o simulador só emite valores que o próprio estado sustenta |
| semântica de `before`/`after` em relação ao estado desejado | a página diz "before/after the actions" sem fixar qual lado é o desejado; a direção deve ser medida num preview real antes de virar contrato de consumidor |
| paridade `machine_type`/API Compute | `path` é um caminho Terraform, não o campo `machineType` da Compute API; os dois vocabulários não podem ser normalizados um no outro |

## 6. Fidelidade

- Spec de máquina: `specs/gcp/infrastructure-manager-resource-drift.schema.json`.
- Golden test: `tools/synthetic_clouds/tests/test_drift_views_fidelity.py`.
- Teste do emulador: `emulators/gcp-sim/tests/test_infra_manager.py`.
