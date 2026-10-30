# Mapa de impacto — Fase S4b1-D (identificador nativo do cluster: EKS, AKS, GKE)

**Data:** 2026-10-28 · **Escopo:** `emulators/aws-sim`, `emulators/azure-sim`,
`emulators/gcp-sim` · **Fora do escopo:** CloudPilot (C-IDENT), fixture do k8s-sim
(S4b1-E), billing/compose, `specs/**`, `emulators/k8s-sim/**`.

**Revisão S4b1-D-C (2026-10-28):** a superfície EKS passa a ser **escopada pela conta**
e a lista passa a publicar o **mesmo nome** que o documento publica. As seções §1, §2,
§5, §7 e §8 foram atualizadas; o resto do mapa permanece válido.

**Revisão S4b1-E (2026-10-29):** o `k8s-sim` passa a aceitar o **id nativo** do cluster como
alias no filtro, e o fixture versionado passa a carregá-lo por cluster (`a64b8414`). As seções
§3, §6, §7 e §8 foram atualizadas e há um addendum no fim do mapa; o resto do mapa permanece
válido.

## 1. O que muda

Cada descoberta passa a publicar o **identificador nativo** do cluster, e o `name`
passa a ser o nome real da cloud:

| Provider | Antes | Depois |
|---|---|---|
| **EKS** | `cluster.name` = `cluster-<17 hex>` (id derivado do uuid); `cluster.arn` = `arn:aws:eks:<região>:<conta>:cluster/cluster-<17 hex>` | `cluster.name` = o nome do estate (`Resource.resource_name`); `cluster.arn` = `arn:aws:eks:<região>:<conta>:cluster/<nome>` |
| **AKS** | `id` = ARM ID completo; `name` = nome do estate | **sem mudança de payload** — o `id` já era o ARM ID completo; a fase adiciona o teste de contrato que prova isso |
| **GKE** | `name`, `endpoint`, `location`, `masterAuth.clusterCaCertificate` | acrescente **`selfLink`** = `projects/<projeto>/locations/<local>/clusters/<nome>`; os outros quatro ficam como estavam |

**Revisão S4b1-D-C — EKS, a lista e o escopo:**

| Antes (S4b1-D) | Depois (S4b1-D-C) |
|---|---|
| `GET /clusters` → `cluster-<17 hex>` (o handle do simulador) | `GET /clusters` → o **nome do estate**, o mesmo que o documento publica |
| a lista respondia com os clusters das **3 contas** | a lista responde com os clusters da **conta da credencial** |
| um nome repetido entre contas resolvia para **um** cluster (o primeiro) | um nome repetido resolve para **um cluster por conta** — o da conta que assinou o pedido |
| o handle era a única forma de alcançar um cluster específico | o handle continua **aceito como alias**, dentro da conta; o nome é o que se publica |

Nenhum campo inventado: o ARN do EKS e o `selfLink` do GKE são construídos **só**
com campos que o estate carrega (região, conta/projeto, nome). Nenhum membro que o
estate não modela foi acrescentado.

## 2. As rotas afetadas

| # | Rota | Handler | Projeção |
|---|---|---|---|
| 1 | `GET /clusters` (EKS) | `aws_sim/api/eks.py:68` (`list_clusters`) | `aws_sim/projections/eks.py:124` (`clusters`) |
| 2 | `GET /clusters/{name}` (EKS) | `aws_sim/api/eks.py:75` (`describe_cluster`) | `aws_sim/projections/eks.py:134` (`find_cluster`) → `:193` (`cluster_document`) |
| 3 | `GET /clusters/{name}/node-groups` | `aws_sim/api/eks.py:85` (`list_nodegroups`) | `aws_sim/projections/eks.py:153` (`node_groups`) |
| 4 | `GET /clusters/{name}/addons` | `aws_sim/api/eks.py:95` (`list_addons`) | `aws_sim/projections/eks.py:161` (`addons`) |
| 5 | `GET /projects/{project}/locations/{location}/clusters` (GKE) | `gcp_sim/routers/container.py:36` | `gcp_sim/projections/container.py:173` (`clusters`) → `:153` (`cluster`) |
| 6 | `GET /subscriptions/{id}/providers/Microsoft.ContainerService/managedClusters` (AKS) | `azure_sim/api/containerservice.py:114` | `azure_sim/projections/containerservice.py:130` (`project_managed_clusters`) → `arm.py:193` (`arm_row`) |
| 7 | `GET /subscriptions/{id}/resources?$filter=resourceType eq 'Microsoft.ContainerService/managedClusters'` | `azure_sim/api/containerservice.py:134` | a mesma `project_managed_clusters` |

As rotas 6 e 7 chamam a **mesma** projeção, então o `id` do mesmo cluster é o mesmo
nas duas.

**As quatro rotas do EKS passaram a receber a conta** (`aws_sim/api/eks.py:55`,
`_account`), e as três projeções que resolvem um cluster (`clusters`, `find_cluster`,
`node_groups`, `addons`) passaram a recebê-la também.

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

**A descoberta AWS é por conta, e é por isso que o escopo do simulador casa com ela.**
`cluster_discovery.py:116` roda uma vez por `CloudAccount`, e o cliente de cada conta
assina com a credencial **dessa** conta (`get_aws_client_for_account`). Com a lista
escopada, cada descoberta devolve exatamente os clusters da sua conta — e o
`DiscoveryResult` recebe o nome real, que é o que o `filter=cluster:"<nome>"` do
k8s-sim exige.

**Atualização de 2026-10-29 — fechado em `a64b8414` (S4b1-E):** o `k8s-sim` deixou de resolver
o filtro só pelo **nome**: passa a aceitar também o **id nativo** (ARN do EKS, id ARM do AKS,
`selfLink` do GKE) e o **uuid do estate** (`cluster_id`), como aliases do nome — em
`/allocation/compute` e em `/clusterInfo`. O parágrafo acima descreve o consumo como era na
S4b1-D; o que mudou foi o lado do **simulador**, não o do consumidor.

**Medido em 2026-10-28, no ambiente local:** nenhum hostname AWS é apontado para o
aws-sim (`deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1:73` — a lista
`$FrontAliases` só traz hostnames do GCP; o alias do STS foi removido em `e461f572`), e
só a conta `[SYNTH] AWS acct-01` tem override de endpoint, para o **STS**
(`cur_config.endpoint_overrides.sts`). **O tráfego de EKS do CloudPilot não chega ao
aws-sim neste ambiente** — ele vai para a AWS real. A mudança desta fase, portanto,
não altera o runtime do CloudPilot local; ela muda o **contrato** da superfície do
simulador, que é o que o `cluster_discovery` consumirá quando o endpoint for apontado
para o simulador.

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

## 5. A decisão do EKS (revisão S4b1-D-C): a lista publica o nome, escopada pela conta

`ListClusters` responde com o **nome do estate** — o mesmo que o `DescribeCluster`
publica — e a resposta é **escopada pela conta da credencial**.

**O escopo vem da credencial, e de nenhum outro lugar.** A conta é decodificada da
credencial SigV4 do pedido (`projections/sts.py`: `parse_access_key` +
`account_from_access_key`), que é **a regra única de conta-por-credencial do pacote** —
a mesma que o `sts.GetCallerIdentity`, o relatório de credenciais do IAM e as
credenciais do SSO já seguem. Nenhum header novo foi inventado: a conta é a conta com
que o chamador assinou. Um pedido sem credencial decodificável cai na **primeira conta
do estate** (`covered_account`), o mesmo fallback do STS e do IAM — determinístico e
sempre uma conta do próprio estate.

**Por que o escopo é o que torna a lista um espaço de endereçamento sem perdas.** O
estate canônico (seed 123, `medium`) tem **75 clusters EKS em 3 contas, com 41 nomes
distintos** — o mesmo conjunto de nomes se repete nas três contas
(`generate/estate_builder.py:292` reinicia o contador por escopo). **Dentro de uma
conta os nomes são únicos** (medido: 25 clusters, 25 nomes distintos em cada uma das 3
contas) — porque o gerador nomeia cada recurso uma vez por escopo. Então, dentro da
conta das credenciais, um nome endereça **exatamente um** cluster, e a ARN (que carrega
a conta e a região além do nome) o identifica no mundo. A descoberta do consumidor
percorre a lista e descreve cada entrada: com os nomes publicados e a lista escopada,
**cada cluster é descrito e cada cluster publica a sua ARN** — 75/75, sem duplicação.

O mesmo raciocínio já vale para o GKE e o AKS, onde a superfície **é** scope-scoped: a
rota do GKE lista por projeto (`providers/gcp.py:539`) e a do AKS por subscription —
lá o nome identifica o cluster dentro do escopo e o `selfLink`/`id` identifica o
cluster no mundo. O EKS agora faz o mesmo.

**O handle derivado continua existindo, e continua sendo apenas um alias.** Ele não é
publicado como nome (a regra do `cluster_id` do k8s-sim e do alias de label de
subscription do Azure): `find_cluster` o aceita ao lado do nome do estate, **dentro
da conta**, porque um nome resolve dentro da conta. Quem guardou o handle continua
resolvendo; quem guardou o nome também.

**O que não acompanha o nome.** O nome do node group (`<id>-ng`) e o nome da role IAM
(`<id>-cluster-role`) continuam no id derivado: nenhum dos dois é um nome que o estate
possa carregar (`eks_cluster-0021 (do not delete)` não é nome IAM nem nome de node
group), e normalizá-los seria inventar um nome.

## 6. O que **não** muda

- O estate (`generate/estate_builder.py`) — nenhum campo novo, nenhum tipo novo.
- O gerador de nomes (`model/identity.py`) — o id derivado continua sendo o que é.
- O nome do node group (`<id>-ng`) e o `roleArn`
  (`arn:aws:iam::<conta>:role/<id>-cluster-role`): normalizá-los seria inventar um nome.
- As demais propriedades do cluster EKS (`status`, `version`, `endpoint`, `tags`,
  `identity`, `resourcesVpcConfig`, `accessConfig`, `createdAt`).
- Os outros quatro membros do cluster GKE (`name`, `endpoint`, `location`, `masterAuth`).
- `specs/**` e `tools/synthetic_clouds/fidelity/**` — intocados (gap no §8).
- `emulators/k8s-sim/**` — intocado por esta fase (o fixture é S4b1-E). **Atualização de
  2026-10-29:** a S4b1-E tocou o `k8s-sim` em `a64b8414` (fixture com `native_id` e filtro
  por id nativo); o escopo histórico da S4b1-D acima não muda.
- O CloudPilot (`C:\Projetos\cloudpilot-deploy`) — **nenhum arquivo alterado**.
- GKE e AKS — intocados.

## 7. Riscos residuais

1. ~~**A superfície EKS é account-agnostic.**~~ **FECHADO em S4b1-D-C.** A superfície
   é escopada pela conta da credencial; um nome repetido entre contas resolve para um
   cluster por conta, e o handle continua aceito como alias dentro da conta.
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
4. **O mapa de contas do CloudPilot ainda é chaveado por nome.** O
   `cluster_account_map` é `{cluster_name: account_uuid}`
   (`cur_cluster_cost.py:172`, `cost_tracker.py:88`). Com a lista escopada, a
   **colisão entre contas desaparece** (a descoberta de cada conta devolve só os
   clusters dela, e dentro da conta os nomes são únicos), mas o mapa continua
   **name-keyed** — é o que o C-IDENT tem de corrigir, chaveando pelo identificador
   nativo (a ARN). **O lado do simulador desse residual está fechado desde 2026-10-29
   (S4b1-E, `a64b8414`):** o `k8s-sim` aceita o id nativo como alias no filtro, então um
   `filter=cluster:"<id nativo>"` volta a selecionar o cluster. O item acima descreve o
   lado do **consumidor**, e não muda aqui.
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
| Alinhar o ARN do EKS no Tagging API e no AWS Config com o ARN oficial | posterior (não entregue pela S4b1-E) |
| Regerar `specs/gcp/container-clusters.schema.json` (o `selfLink` deixa de ser `unverified`) e `docs/NAO-COMPROVADOS.md` | fase de spec |

**Fechados em S4b1-E (2026-10-29):**

| Gap | Como foi fechado |
|---|---|
| O `k8s-sim` aceitar o id nativo do cluster como alias | `resolve_cluster_name` aceita **três aliases** da mesma identidade — o **nome**, o **uuid do estate** (`cluster_id`) e o **id nativo** (ARN do EKS, id ARM do AKS, `selfLink` do GKE) — **aceitos e nunca publicados**, porque a resposta carrega o nome (`emulators/k8s-sim/k8s_sim/projections/allocation.py`) |
| Fixture do k8s-sim com o identificador nativo por cluster e filtro por ID (o mesmo item, do lado do dado) | o fixture versionado `emulators/k8s-sim/k8s_sim/fixtures/clusters.json` carrega `native_id` por cluster — **309 clusters** (75 EKS, 111 GKE, 123 AKS) — e é gerado por `emulators/k8s-sim/scripts/export_clusters.py`; `/clusterInfo` aceita os mesmos aliases |

**Fechados em S4b1-D-C:**

| Gap | Como foi fechado |
|---|---|
| Superfície EKS escopada por conta (o nome resolve dentro da conta das credenciais) | a conta é decodificada da credencial SigV4 (`projections/sts.py`) e todas as quatro rotas a recebem (`aws_sim/api/eks.py:55`) |
| A lista publicava o handle (`cluster-<17 hex>`) em vez do nome | `clusters()` publica `Resource.resource_name` — o mesmo do documento |
| O docstring da rota `eks:ListClusters` (`aws_sim/api/eks.py:68`) dizia "the cluster names this account owns" sem que a conta fosse levada em conta | a frase agora é verdadeira: a rota é escopada pela conta |

## Addendum — S4b1-E (2026-10-29)

Medido no commit `a64b8414` (2026-10-29 20:13:42), com a suíte do `k8s-sim` rodada localmente:
**91 passed** — 78 anteriores ao commit + 13 novos. O fixture versionado
`emulators/k8s-sim/k8s_sim/fixtures/clusters.json` carrega `native_id` por cluster —
**309 clusters** (75 EKS, 111 GKE, 123 AKS) — e o filtro de `/allocation/compute` e de
`/clusterInfo` aceita **três aliases** da identidade do cluster: o **nome** (o que o contrato
publica), o **uuid do estate** (`cluster_id`) e o **id nativo** que a descoberta publica (ARN do
EKS, id ARM do AKS, `selfLink` do GKE). Os 309 ids nativos são distintos entre si (309 ids para
309 clusters) e disjuntos dos outros identificadores; os 309 clusters carregam 160 nomes
distintos, e é o id nativo que separa os homônimos de contas diferentes. Fonte: o handoff da
fase S4b1-E (`a64b8414`), conferido contra o fixture, a projeção e a suíte do `k8s-sim`.
