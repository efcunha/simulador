# Mapa de impacto — Fase S3 (`properties.fqdn` do AKS)

**Data:** 2026-10-28 · **Reconferido em 2026-10-29 (revisão `9533b901`; consumidor HEAD
`b60bde8e`):** as linhas citadas do `azure-sim` continuam válidas e as do consumidor foram
atualizadas — ele evoluiu com o **C-IDENT** (commits `dbd66cca` de 2026-10-28 e `7e52f377`,
`30b4e70c`, `385e9759` de 2026-10-29), que passou a keyear o cluster pelo id nativo (o ARM id do
AKS). O `properties.fqdn` continua sendo o endpoint que a descoberta lê e o `get_cluster_health`
publica.
**Escopo:** `emulators/azure-sim` · **Fora do escopo:** CloudPilot, custo OpenCost/Kubecost (S4).

## 1. O que muda

**Um campo, um lugar:** `properties.fqdn` passa a ser publicado nas linhas de
`Microsoft.ContainerService/managedClusters` servidas pelo `azure-sim`.

Nada mais muda no payload: `properties` continua tendo exatamente
`provisioningState` e `fqdn`. O campo é **derivado** na projeção (não é campo do
estate, não é coluna de spec, não muda o gerador).

## 2. As duas rotas afetadas

As duas chamam a **mesma** função de projeção (`project_managed_clusters`), então
uma única linha de código altera as duas — e é por isso que o `fqdn` do mesmo
cluster é **o mesmo** nas duas:

| # | Rota (ARM) | Handler | Projeção |
|---|---|---|---|
| 1 | `GET /subscriptions/{subscriptionId}/resources?$filter=resourceType eq 'Microsoft.ContainerService/managedClusters'` | `azure_sim/api/containerservice.py:134` (`subscription_resources`) | `azure_sim/projections/containerservice.py:130` (`project_managed_clusters`) |
| 2 | `GET /subscriptions/{subscriptionId}/providers/Microsoft.ContainerService/managedClusters` | `azure_sim/api/containerservice.py:114` (`managed_clusters`) | `azure_sim/projections/containerservice.py:130` (`project_managed_clusters`) |

**A rota 1 é a que a descoberta do CloudPilot realmente lê** (a lista ARM de
recursos filtrada por tipo). A rota 2 é a lista tipada do serviço.

A derivação do valor está em `azure_sim/projections/containerservice.py:99`
(`cluster_fqdn`).

## 3. Quem lê `properties.fqdn` no CloudPilot

Leitura **somente** — nenhuma alteração no CloudPilot é feita nesta fase (a
correção C-AKS já está aprovada).

| Consumidor | Local | O que faz com o campo |
|---|---|---|
| `_list_aks_clusters` | `backend/app/services/k8s_finops/providers/azure.py:670` | Lê `properties.fqdn` da linha ARM via `_arm_property(properties, "fqdn")` (`:697`) e guarda em `_AksCluster.fqdn` (`:704`, campo declarado em `:111`). `properties` chega como `dict` puro (o SDK tipa `GenericResource.properties` como `object`), então a leitura é **por nome**, não por atributo. O laço é a rota 1 (`resources.list`, `:688`). |
| `get_cluster_health` | `backend/app/services/k8s_finops/providers/azure.py:415` | Devolve `"endpoint": cluster_spec.fqdn` (`:431`). É o contrato de endpoint que o `discovery` publica. Desde o C-IDENT recebe o **id nativo** (`cluster_id`) e resolve conta/nome por `_resolve_account_for_cluster` (`:515`). |
| `_fetch_aks_credential` | `backend/app/services/k8s_finops/providers/azure.py:715` | Lê `certificate-authority-data` do kubeconfig (`:799`); quando falta, confere o `cluster.fqdn` do listing ARM (`:806`) e falha com `ProviderDataError` (`:807`/`:808-811`) — o FQDN **não** substitui a CA no handshake. |

O caminho de **custo** K8s não lê o FQDN diretamente: ele é servido pela mesma
descoberta (`_list_aks_clusters`), e é o `endpoint` publicado que a superfície de
custo consome — por isso o campo vazio chegava ao consumidor como
"cluster sem endpoint".

## 4. O contrato do valor

| Propriedade | Regra | Por quê |
|---|---|---|
| Forma | `<cluster>-<hash>.<region>.azmk8s.io` | Host puro: **sem** `http://`, **sem** `https://`, **sem** porta. |
| `cluster` | Label DNS: minúsculo, todo caractere fora de `[a-z0-9]` virando `-`, sem hífen nas pontas, ≤ 63 caracteres | O nome do recurso no estate não é um label DNS: há `aks_cluster-0043_FINAL_v2` (underscore e maiúsculas) e `aks_cluster-0187 (do not delete)` (espaços e parênteses). |
| `hash` | `sha256("<identity.uuid>:<resource_name>:<region_id>")` (10 hex), determinístico | O `uuid` da identidade é único no estate inteiro, então o hash desambigua clusters de nomes iguais em subscriptions diferentes. |
| `region` | O `region_id` do recurso, normalizado como label | Fica no host porque o AKS publica o FQDN por região. |
| Determinismo | Mesmo cluster ⇒ mesmo FQDN, em qualquer chamada, em qualquer rebuild | O estate é determinístico em `(seed, profile)`; o FQDN não pode depender de ordem nem de processo. |
| Unicidade | FQDN distinto por cluster | Verificado em 2026-10-29 nos 41 clusters AKS de `sub-01` (41 FQDNs distintos, com a função `cluster_fqdn` do próprio `azure-sim`). No estate inteiro decorre do `uuid` da identidade, que não se repete (123 recursos AKS, 123 `uuid` distintos). |

`hashlib.sha256` e nunca `hash()`: `hash()` é salted por processo e está banido
neste pacote (AC-6) — mesma regra que `model/identity.py` segue.

## 5. O que **não** muda

- O estate (`generate/estate_builder.py`) — nenhum campo novo, nenhum tipo novo.
- Nenhuma outra propriedade de `managedCluster` (`agentPoolProfiles`,
  `dnsPrefix`, `privateFqdn` e `privateClusterFqdn` continuam **ausentes**, não vazios).
- `specs/**` e `tools/synthetic_clouds/fidelity/**` — nenhuma spec nova, matriz
  intocada (gap registrado no HANDOFF).
- GKE / EKS — o `fqdn` de outras nuvens não é tocado.
- Custo OpenCost/Kubecost, namespaces, pods, alocação (S4).

## 6. Riscos residuais

1. **O FQDN não é dialável.** É sintético: não existe servidor Kubernetes por
   trás, e o host não resolve. Ele serve o **contrato** (o campo existe, é
   estável e é único), não a rede.
2. **Sem API server Kubernetes.** Publicar o FQDN não cria um plano de dados;
   o handshake TLS contra o AKS continua fora de alcance.
3. **Sem spec dedicada de AKS.** O campo é oficial
   (`Microsoft.ContainerService/managedClusters.properties.fqdn` — a referência de modelo
   do Azure SDK publica `fqdn` como *"The FQDN of the master pool"*, Microsoft Learn,
   consultado em 2026-10-28,
   https://learn.microsoft.com/en-us/python/api/azure-mgmt-containerservice/azure.mgmt.containerservice.models.managedclusterproperties?view=azure-python),
   mas não há surface de spec que o declare — gap para uma fase própria.
4. **Custo OpenCost/Kubecost é S4.** Esta fase entrega o endpoint; o consumo
   dele pelo caminho de custo é da fase seguinte.
