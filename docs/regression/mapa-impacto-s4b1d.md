# Mapa de impacto — Fase S4b1-D (identificador nativo do cluster: EKS, AKS, GKE)

**Data:** 2026-10-28 · **Escopo:** `emulators/aws-sim`, `emulators/azure-sim`,
`emulators/gcp-sim` · **Fora do escopo:** CloudPilot (C-IDENT), fixture do k8s-sim
(S4b1-E), billing/compose, `specs/**`, `emulators/k8s-sim/**`.

## 1. O que muda

Cada descoberta passa a publicar o **identificador nativo** do cluster, e o `name`
passa a ser o nome real da cloud:

| Provider | Antes | Depois |
|---|---|---|
| **EKS** | `cluster.name` = `cluster-<17 hex>` (id derivado do uuid); `cluster.arn` = `arn:aws:eks:<região>:<conta>:cluster/cluster-<17 hex>` | `cluster.name` = o nome do estate (`Resource.resource_name`); `cluster.arn` = `arn:aws:eks:<região>:<conta>:cluster/<nome>` |
| **AKS** | `id` = ARM ID completo; `name` = nome do estate | **sem mudança de payload** — o `id` já era o ARM ID completo; a fase adiciona o teste de contrato que prova isso |
| **GKE** | `name`, `endpoint`, `location`, `masterAuth.clusterCaCertificate` | acrescente **`selfLink`** = `projects/<projeto>/locations/<local>/clusters/<nome>`; os outros quatro ficam como estavam |

Nenhum campo inventado: o ARN do EKS e o `selfLink` do GKE são construídos **só**
com campos que o estate carrega (região, conta/projeto, nome). Nenhum membro que o
estate não modela foi acrescentado.

## 2. As rotas afetadas

| # | Rota | Handler | Projeção |
|---|---|---|---|
| 1 | `GET /clusters` (EKS) | `aws_sim/api/eks.py:47` (`list_clusters`) | `aws_sim/projections/eks.py:101` (`clusters`) |
| 2 | `GET /clusters/{name}` (EKS) | `aws_sim/api/eks.py:53` (`describe_cluster`) | `aws_sim/projections/eks.py:173` (`cluster_document`) |
| 3 | `GET /clusters/{name}/node-groups` | `aws_sim/api/eks.py:63` (`list_nodegroups`) | `aws_sim/projections/eks.py:133` (`node_groups`) |
| 4 | `GET /clusters/{name}/addons` | `aws_sim/api/eks.py:72` (`list_addons`) | `aws_sim/projections/eks.py:141` (`addons`) |
| 5 | `GET /projects/{project}/locations/{location}/clusters` (GKE) | `gcp_sim/routers/container.py:36` | `gcp_sim/projections/container.py:173` (`clusters`) → `:153` (`cluster`) |
| 6 | `GET /subscriptions/{id}/providers/Microsoft.ContainerService/managedClusters` (AKS) | `azure_sim/api/containerservice.py:114` | `azure_sim/projections/containerservice.py:130` (`project_managed_clusters`) → `arm.py:193` (`arm_row`) |
| 7 | `GET /subscriptions/{id}/resources?$filter=resourceType eq 'Microsoft.ContainerService/managedClusters'` | `azure_sim/api/containerservice.py:134` | a mesma `project_managed_clusters` |

As rotas 6 e 7 chamam a **mesma** projeção, então o `id` do mesmo cluster é o mesmo
nas duas.

## 3. Quem consome hoje (leitura, nenhuma mudança no CloudPilot)

| Consumidor | Local | O que lê hoje | Lê o identificador nativo? |
|---|---|---|---|
| Descoberta AWS | `backend/app/services/k8s_finops/cluster_discovery.py:124-140` | `eks:ListClusters` → `eks:DescribeCluster` → `DiscoveryResult(name=cluster_info.get("name", name), status, version, region, provider)` | **não** — o `arn` não entra no `DiscoveryResult` (C-IDENT) |
| Descoberta GCP | `cluster_discovery.py:181-217` + `providers/gcp.py:531-552` | `_list_gke_clusters` devolve só `name`, `endpoint`, `ca_data`, `location` | **não** — o `selfLink` não é lido (C-IDENT) |
| Descoberta Azure | `cluster_discovery.py:241-270` + `providers/azure.py:653` | a linha ARM; `DiscoveryResult(name=cluster.name, ...)` | **não** — o `id` ARM não é lido (C-IDENT) |
| Saúde do cluster (AWS) | `providers/aws.py:1301` | `cluster.get("arn", "")` — **o único leitor de ARN que existe hoje** | sim, e é o único |
| Consulta por nome (GCP) | `providers/gcp.py:254,354,379,500` | casa o cluster por `cluster["name"]` | não |

O caminho de **custo** K8s não lê nenhum dos três identificadores: ele consome o
`endpoint` (e o `name`, no filtro `cluster:"<nome>"` do k8s-sim). O que muda nesta
fase é o que o produtor **entrega**, não o que o consumidor lê.

## 4. O contrato do valor

| Propriedade | EKS | GKE |
|---|---|---|
| Forma | `arn:aws:eks:<região>:<conta>:cluster/<nome>` | `projects/<projeto>/locations/<local>/clusters/<nome>` |
| Origem | `arns.arn_for_type` (a forma vive na tabela de ARNs do pacote; o que preenche o segmento de nome é o `resource_name`) | os três segmentos são campos do estate: `project_id`, `region_id`, `resource_name` |
| Determinismo | mesmo cluster ⇒ mesmo ARN, em qualquer chamada | idem |
| Unicidade | **75/75** ARNs distintos no estate canônico (seed 123, `medium`) | **111/111** `selfLink` distintos (o projeto entra no caminho) |
| Nome | `Resource.resource_name` — inalterado em relação ao resto do estate | `Resource.resource_name` — inalterado |

O `selfLink` do GKE é a **forma canônica do caminho** que o Kubernetes Engine usa
para nomear um cluster. Todo segmento dele é um campo do estate; nada é inventado.

## 5. A decisão do EKS: a lista mantém o handle, e por quê

`ListClusters` continua respondendo com o id derivado (`cluster-<17 hex>`), e o
`name` novo vive no **documento** do cluster. Isso é deliberado, e é a única parte
desta fase que se afasta da leitura literal do enunciado.

**O porquê, medido.** O estate canônico (seed 123, `medium`) tem **75 clusters EKS
em 3 contas, com 40 nomes distintos** — o mesmo conjunto de nomes se repete nas três
contas (`generate/estate_builder.py:292` reinicia o contador por escopo). A
superfície EKS do simulador serve **todas** as contas do estate em um endpoint; o
serviço real resolve um nome **dentro da conta das credenciais**.

Se a lista passasse a publicar os nomes, a descoberta do consumidor (que percorre a
lista e descreve cada entrada, `cluster_discovery.py:128-130`) receberia **40 dos 75
clusters**: os outros 35 nunca seriam descritos e **o ARN deles nunca seria
publicado** — e o C-IDENT, que vai chavear o mapa pela ARN, não teria como
recuperá-los. Com o handle na lista, cada cluster é descrito e publica a sua ARN
(75/75), e o `name` que a descoberta entrega ao CloudPilot é o nome real, que é o
que o `filter=cluster:"<nome>"` do k8s-sim exige.

O mesmo raciocínio já vale para o GKE e o AKS, onde a superfície **é**
scope-scoped: a rota do GKE lista por projeto (`providers/gcp.py:539`) e a do AKS
por subscription — lá o nome identifica o cluster dentro do escopo e o `selfLink`/
`id` identifica o cluster no mundo.

## 6. O que **não** muda

- O estate (`generate/estate_builder.py`) — nenhum campo novo, nenhum tipo novo.
- O gerador de nomes (`model/identity.py`) — o id derivado continua sendo o que é.
- O nome do node group (`<id>-ng`) e o `roleArn` (`arn:aws:iam::<conta>:role/<id>-cluster-role`):
  nenhum dos dois é um nome que o estate possa carregar (`eks_cluster-0021 (do not delete)`
  não é nome IAM nem nome de node group), e normalizá-los seria inventar um nome.
- As demais propriedades do cluster EKS (`status`, `version`, `endpoint`, `tags`,
  `identity`, `resourcesVpcConfig`, `accessConfig`, `createdAt`).
- Os outros quatro membros do cluster GKE (`name`, `endpoint`, `location`, `masterAuth`).
- `specs/**` e `tools/synthetic_clouds/fidelity/**` — intocados (gap no §8).
- `emulators/k8s-sim/**` — intocado (o fixture é S4b1-E).
- O CloudPilot (`d:\cloudpilot-deploy`) — **nenhum arquivo alterado**.

## 7. Riscos residuais

1. **A superfície EKS é account-agnostic.** Um nome que o estate reusa entre contas
   resolve para **um** cluster (o primeiro que o carrega) — os outros não são
   endereçáveis pelo nome. O ARN de cada cluster continua único, e o handle
   endereça cada um exatamente; fechar a lacuna é tornar a superfície escopada por
   conta, o que toca `api/eks.py` (fora da allowlist desta fase).
2. **O ARN do EKS diverge do ARN do mesmo cluster em outras superfícies do próprio
   simulador.** O Resource Groups Tagging API e o AWS Config publicam
   `arns.resource_arn(...)`, que usa o id derivado; o `DescribeCluster` publica
   agora o ARN oficial, com o nome. O valor oficial está certo no `DescribeCluster`
   e errado nos outros dois — alinhar exige mexer em `aws_sim/arns.py` /
   `aws_sim/ids.py`, fora da allowlist. **Nenhum consumidor de hoje cruza os dois**
   (o único leitor de ARN é `providers/aws.py:1301`, que lê o do `DescribeCluster`).
3. **`specs/gcp/container-clusters.schema.json` ficou desatualizado:** o `selfLink`
   está registrado lá como `unverified` ("o estate não forja uma URL definida pelo
   servidor"). O valor publicado agora é o caminho canônico, montado só com campos do
   estate — mas o spec (e o `docs/NAO-COMPROVADOS.md`, que dele deriva) não podem ser
   regerados nesta fase (`specs/**` fora da allowlist).
4. **O mapa de contas do CloudPilot ainda é chaveado por nome.** Publicar o nome real
   faz os nomes repetidos colidirem no `cluster_account_map` (75 clusters, 40 nomes
   no EKS): o mapa perde entradas até o C-IDENT chavear pela ARN. É o motivo de
   existir o C-IDENT — e o motivo de a lista do EKS não ter virado os nomes.
5. **Os nomes do estate são publicados verbatim, e alguns não são válidos na AWS.**
   O gerador produz ruído de propósito (`TEMP-eks_cluster-0006`,
   `eks_cluster-0021 (do not delete)`, `prodeks_cluster-0021COPY`), e o ARN do EKS
   e o `id` ARM do AKS carregam esse nome como é — um ARN real não aceitaria
   espaço nem parêntese. Normalizar seria inventar um nome (e quebraria o
   contrato "o ARN termina com o nome publicado"), então o ruído fica visível.
   O `id` ARM do AKS já carrega o nome verbatim desde antes desta fase.
6. **Custo OpenCost/Kubecost é S4.** Esta fase entrega os identificadores; o consumo
   deles pelo caminho de custo é da fase seguinte.

## 8. Gaps para fases seguintes

| Gap | Fase sugerida |
|---|---|
| C-IDENT no CloudPilot: `DiscoveryResult` (e o `cluster_account_map`) passam a chavear pelo identificador nativo | S4b1-C (CloudPilot) |
| Fixture do k8s-sim com o identificador nativo por cluster e filtro por ID | S4b1-E |
| Superfície EKS escopada por conta (o nome resolve dentro da conta das credenciais) | S4b1-E ou posterior |
| Alinhar o ARN do EKS no Tagging API e no AWS Config com o ARN oficial | S4b1-E ou posterior |
| O docstring da rota `eks:ListClusters` (`aws_sim/api/eks.py:49`) ainda diz "the cluster names this account owns" — a lista responde com o handle (ver §5) | S4b1-E ou posterior (o arquivo está fora da allowlist desta fase) |
| Regerar `specs/gcp/container-clusters.schema.json` (o `selfLink` deixa de ser `unverified`) e `docs/NAO-COMPROVADOS.md` | fase de spec |
