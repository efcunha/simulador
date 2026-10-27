# `container-clusters` — Kubernetes Engine `clusters`

## 1. Identificação

- **Superfície:** `Kubernetes Engine` → `locations` → `clusters`
  (`projects.locations.clusters.list`).
- **Documentos oficiais e datas de consulta (2026-10-27):**

| Documento | URL | Consultado em |
|---|---|---|
| Method: `projects.locations.clusters.list` (path, query, envelope da resposta) | <https://docs.cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations.clusters/list> | 2026-10-27 |
| REST Resource: `projects.locations.clusters` (`Cluster`, `MasterAuth`) | <https://docs.cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations.clusters> | 2026-10-27 |
| REST Resource: `ListClustersResponse` (`clusters[]`, `missingZones[]`) | <https://docs.cloud.google.com/kubernetes-engine/docs/reference/rest/v1/ListClustersResponse> | 2026-10-27 |

- **Fonte de máquina:** <https://container.googleapis.com/$discovery/rest?version=v1> — a
  mesma API v1 cuja tabela de propriedades a página de `Cluster` renderiza. As duas
  trazem os mesmos nomes para **86 dos 87** membros de `Cluster` (o discovery acrescenta
  `parentProductConfig`, que a página renderizada, de 2026-04-15, ainda não traz). O
  endpoint de discovery **não** é `source_url` de nenhuma coluna: a citação de cada
  coluna é a página de documentação, legível por uma pessoa.
- **Versão:** Kubernetes Engine API **v1**, host `container.googleapis.com`.

## 2. Mecanismo

1. `GET https://container.googleapis.com/v1/{parent=projects/*/locations/*}/clusters`
   lista os clusters de um projeto em uma zona ou região.
2. O `parent` é obrigatório, no formato `projects/*/locations/*`. `Location "-"`
   corresponde a todas as zonas e todas as regiões.
3. A requisição **não tem corpo**, e o método **não publica parâmetro de paginação**.
4. A resposta é um `ListClustersResponse`: o array `clusters` e o array `missingZones`.

Os parâmetros de query `projectId` e `zone` são **deprecados** na própria página e
foram substituídos pelo `parent`; por isso a rota aceita apenas a forma do `parent`.

Isso **não é um export de arquivo**: é uma resposta de API do plano de controle. Não há
blob, partição, compressão ou manifesto documentado.

## 3. Envelope e item

Resposta do `list`:

```json
{
  "clusters": [ { "object (Cluster)" } ],
  "missingZones": [ "string" ]
}
```

`Cluster` (os membros que o simulador publica):

```json
{
  "name": "string",
  "endpoint": "string",
  "location": "string",
  "masterAuth": { "clusterCaCertificate": "string" }
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `clusters` | array | lista de clusters do projeto na zona indicada, ou em todas |
| `missingZones` | array | zonas cuja listagem pode estar incompleta |
| `name` | string | nome do cluster |
| `endpoint` | string | endpoint master do cluster |
| `location` | string | zona ou região onde o cluster reside |
| `masterAuth.clusterCaCertificate` | string | certificado público, em base64, que é a raiz de confiança do cluster |

## 4. O que o simulador projeta

O caminho é `emulators/gcp-sim/gcp_sim/projections/container.py` (a projeção) e
`emulators/gcp-sim/gcp_sim/routers/container.py` (a rota). A rota servida é
`GET /container/v1/projects/{project}/locations/{location}/clusters`.

- `name` = `Resource.resource_name`; `location` = `Resource.region_id` (o estate
  registra uma **região**, e o `location` publicado aceita zona ou região).
- `endpoint` = `https://<uuid>.container.googleapis.com`, derivado do uuid do próprio
  recurso: estável entre chamadas e único por cluster.
- `masterAuth.clusterCaCertificate` = um certificado X.509 real (Ed25519), em PEM,
  codificado em base64 como a documentação publica. A chave privada é derivada do uuid,
  usada para assinar e descartada: **nunca** é publicada. A assinatura Ed25519 é
  determinística por construção (RFC 8032), então o mesmo cluster carrega o **mesmo**
  certificado em qualquer processo e qualquer restart; a janela de validade é fixa, para
  que o relógio também não mude o valor.
- `missingZones` é publicado **vazio**: o campo diz "a listagem pode estar faltando
  essas zonas", e o estate não modela nenhuma zona que o emulador deixou de responder.
- Um projeto ou uma localização que o estate não carrega **seleciona nada** (array
  vazio), em vez de 404 — a mesma regra dos routers irmãos.

### 4.1 Divergência declarada: o `endpoint` não é um endereço IP

A tabela de campos publica `endpoint` como *"Output only. The IP address of this
cluster's master endpoint"*. O estate **não** carrega endereço para um cluster, e um IP
inventado seria um número que o estate nunca afirmou. O simulador publica a **URL
HTTPS** que a mesma frase da documentação mostra o endpoint sendo usado
(`https://username:password@endpoint/`), com o host derivado do uuid do recurso.

A divergência é **declarada**, não silenciosa: está nesta seção, na nota da spec
(`notes`) e na lacuna "the endpoint as an IP address (the published wording of the
member)". Um consumidor que exija um IP precisa saber que o simulador não publica um.

## 5. Não comprovado

| Item | Motivo |
|---|---|
| `currentMasterVersion`, `currentNodeVersion` | o estate não modela versão de Kubernetes: o `sku_id` nomeia o SKU de **node** que ele cobra, que não é a versão do master nem a do node |
| `nodePools`, `nodeConfig`, `nodePoolDefaults`, `initialNodeCount`, `currentNodeCount` | o estate carrega uma linha por cluster, e nenhum pool dentro dele |
| `network`, `subnetwork`, `networkConfig`, `ipAllocationPolicy`, `clusterIpv4Cidr`, `servicesIpv4Cidr` | o estate não modela plano de endereçamento nem VPC de um cluster |
| `status`, `statusMessage` | o estate é uma linha de base de custo, não uma máquina de estado do plano de controle |
| `createTime`, `expireTime`, `id`, `selfLink` | o estate afirma nenhum instante de criação e não carrega o id nem a URL que o provedor define |
| `zone` | o estate registra uma região e nada mais fino; `location` carrega a região. O próprio campo está deprecado em favor de `location` |
| `addonsConfig`, `privateClusterConfig`, `databaseEncryption`, `releaseChannel`, `loggingService`, `monitoringService`, `resourceLabels`, `labelFingerprint`, `workloadIdentityConfig`, `securityPostureConfig`, `notificationConfig`, `maintenancePolicy`, `autoscaling`, `verticalPodAutoscaling`, `autopilot` | o estate não modela nenhum deles |
| `masterAuth.clientKey` | é uma **chave privada**: o simulador deriva uma para assinar o certificado da CA e nunca a publica |
| `masterAuth.clientCertificate`, `masterAuth.clientCertificateConfig` | o estate não modela configuração de certificado de cliente |
| `masterAuth.username`, `masterAuth.password` | o estate não modela conta de autenticação básica; a própria página marca a autenticação básica como deprecada |
| os demais membros publicados de `Cluster` (74 nomes listados na spec) | o estate não modela nenhum deles; estão listados um a um na spec para que nenhum membro publicado desapareça da contabilidade |
| `endpoint` como endereço IP (a redação publicada do campo) | ver §4.1: a divergência é declarada, e a lacuna registra o que a documentação publica e o que o simulador entrega |
| as variantes zonal (`projects.zones.clusters.list`) e agregada (`projects.aggregated.clusters.list`) da mesma listagem | ambas existem na mesma versão da API e devolvem o mesmo `ListClustersResponse`; só a forma regional é servida. É limite de escopo desta superfície, não afirmação de que não existam |
| os parâmetros de query deprecados `projectId` e `zone` | a própria página os marca como substituídos pelo `parent` |
| a alcançabilidade do `endpoint` publicado | ele nomeia o endpoint master do cluster e é derivado do uuid; o emulador não hospeda nenhum API server do Kubernetes atrás dele |

## 6. Fidelidade

- Spec de máquina: `specs/gcp/container-clusters.schema.json`.
- Teste do emulador: `emulators/gcp-sim/tests/test_container.py`.
- Entrada na matriz: `tools/synthetic_clouds/fidelity/matrix.py` (`gcp/container-clusters`).
