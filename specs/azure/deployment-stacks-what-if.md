# `deployment-stacks-what-if` — Deployment Stacks what-if results

## 1. Identificação

- **Superfície:** `Microsoft.Resources/deploymentStacksWhatIfResults` — resultado do
  **what-if** de uma Deployment Stack.
- **Documentos oficiais e datas de consulta (2026-10-27):**

| Documento | URL | Consultado em |
|---|---|---|
| REST: Deployment Stacks What If Results At Resource Group — Create Or Update (`DeploymentStacksWhatIfResult`, `WhatIfChange`, `WhatIfResourceChange`, `WhatIfPropertyChange`) | <https://learn.microsoft.com/en-us/rest/api/resources/deployment-stacks-what-if-results-at-resource-group/create-or-update?view=rest-resources-2025-07-01> | 2026-10-27 |
| Preview deployment stack changes with what-if | <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks-what-if> | 2026-10-27 |
| Create and deploy Azure deployment stacks (managed/unmanaged, detach, denySettings) | <https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks> | 2026-10-27 |

- **api-version:** `2025-07-01`.
- **Host:** `management.azure.com`.

## 2. Mecanismo

`what-if` compara o template/Bicep com o estado atual e devolve um recurso
`Microsoft.Resources/deploymentStacksWhatIfResults`, com as mudanças por recurso e por
propriedade. O resultado é um **plano**, não um registro de drift persistido: `modify`,
`delete` e `detach` são mudanças previstas.

- `detach` = o recurso existe na Azure e deixou de ser gerenciado pela stack; é o vocabulário
  oficial para o que a CloudPilot chama de `unmanaged`.
- `delete` = existe no estado, não na nuvem; corresponde a `missing`.
- `modify` = existe nos dois e as propriedades mudam; é o diff por atributo.
- `noChange` e `unsupported` não são drift.

## 3. Envelope e item

```json
{
  "id": "/subscriptions/SUB/resourceGroups/RG/providers/Microsoft.Resources/deploymentStacksWhatIfResults/NAME",
  "type": "Microsoft.Resources/deploymentStacksWhatIfResults",
  "name": "NAME",
  "location": "eastus",
  "properties": {
    "changes": {
      "resourceChanges": [
        {
          "id": "/subscriptions/SUB/resourceGroups/RG/providers/Microsoft.Compute/virtualMachines/vm-web",
          "type": "Microsoft.Compute/virtualMachines",
          "changeType": "modify",
          "changeCertainty": "definite",
          "managementStatusChange": { "before": "managed", "after": "managed" },
          "resourceConfigurationChanges": {
            "before": { "tags": { "env": "prod" }, "properties": { "hardwareProfile": { "vmSize": "Standard_D2s_v5" } } },
            "after":  { "tags": {}, "properties": { "hardwareProfile": { "vmSize": "Standard_D2s_v5" } } },
            "delta": [
              { "path": "tags.env", "before": "prod", "after": null, "changeType": "delete", "children": [] }
            ]
          }
        }
      ]
    }
  }
}
```

| Campo | Valores/documento |
|---|---|
| `resourceChanges[].changeType` | `create`, `delete`, `detach`, `modify`, `noChange`, `unsupported` |
| `resourceChanges[].changeCertainty` | `definite`, `potential` |
| `resourceChanges[].managementStatusChange.before/after` | `managed`, `unmanaged`, `unknown` |
| `resourceChanges[].resourceConfigurationChanges.before/after` | configuração atual/desejada |
| `delta[].path` | caminho ARM (ex.: `properties.hardwareProfile.vmSize`, `tags.env`) |
| `delta[].before/after` | valores atual/desejado |
| `delta[].changeType` | `array`, `create`, `delete`, `modify`, `noEffect` |
| `delta[].children[]` | mudanças aninhadas |

**Direção:** `before` é o estado atual; `after` é o desejado. É a semântica do what-if, e ela
está fixada no contrato do provedor (diferente do GCP, onde a direção ainda é `unverified`).

## 4. O que o simulador projeta

O simulador emite o input C11 (tags declaradas no snapshot vs. tags do inventário +
`managed_by_iac`) e projeta:

- `modify` com `delta[].path = tags.<chave>` para uma tag removida do estado desejado;
- `detach` para `managed_by_iac = false`, com
  `managementStatusChange {before: managed, after: unmanaged}`;
- `before`/`after` com `location`, `tags` e `properties.hardwareProfile.vmSize` (quando o
  `InstanceProfile` tem `instance_type`).

O caminho é `model/drift.py::project_drift_views`; o mesmo documento é servido por
`emulators/azure-sim/azure_sim/api/deployment_stacks.py`.

## 5. Não comprovado

| Item | Motivo |
|---|---|
| `deploymentScopeChange`, `denySettingsChange` | o contrato publica os dois, mas o estado do simulador não modela mudança de escopo nem deny settings; não são emitidos em vez de receber placeholder |
| conjunto completo de propriedades do resultado (`parameters`, `template`, `templateLink`, `validationLevel`, `diagnostics`, `retentionInterval`, `provisioningState`, ...) | o simulador modela apenas as mudanças de recurso desta fase; omitir é intencional |
| tipo de elemento de `resourceConfigurationChanges.delta` | a página publica o membro e descreve `DeploymentStacksWhatIfPropertyChange`, mas não imprime um link de tipo explícito para `delta`; o container não é afirmado |

## 6. Fidelidade

- Spec de máquina: `specs/azure/deployment-stacks-what-if.schema.json`.
- Golden test: `tools/synthetic_clouds/tests/test_drift_views_fidelity.py`.
- Teste do emulador: `emulators/azure-sim/azure_sim/tests/test_deployment_stacks.py`.
