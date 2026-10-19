# Azure Virtual network flow logs (VNet flow logs)

## 1. Identificação

- **Nome oficial da superfície de export**: *Virtual network flow logs* — Azure Network Watcher.
- **Documento oficial principal**: "Virtual network flow logs" —
  <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview> — consultado em **2026-10-14** (página atualizada em 2026-06-25).
- **Documentos de apoio consultados em 2026-10-14**:
  - "Create, change, enable, disable, or delete virtual network flow logs" — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage> (atualizada 2026-01-22)
  - "Traffic analytics schema and data aggregation" (aba *Virtual network flow logs*) — <https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet> (atualizada 2025-08-20)
- **Versão/schema de referência**:
  - Registo de flow log: **`flowLogVersion` = 4** (valor do exemplo oficial).
  - Esquema do destino Log Analytics (traffic analytics): **`FASchemaVersion` = 3** — "Schema version. Doesn't reflect virtual network flow log version."

## 2. Mecanismo e entrega

### 2.1 O mecanismo existe e tem DOIS caminhos de entrega documentados

**(a) Entrega direta para Storage (é isto que é "virtual network flow logs" propriamente dito):**

> "Flow data from virtual network flow logs is sent to Azure Storage. From there, you can access the data and export it to any visualization tool, security information and event management (SIEM) solution, or intrusion detection system (IDS)."
> — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview>

**(b) Entrega para Log Analytics através de *traffic analytics* (opcional, configurável no mesmo recurso de flow log):**

O portal permite, no separador **Analytics** do recurso de flow log, ativar *traffic analytics* apontando para um Log Analytics workspace, com intervalo de processamento de **Every 1 hour** ou **Every 10 mins** (predefinição: 1 hora).
— <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage>

> **Precisão importante de fidelidade:** a documentação oficial **não** afirma que os registos de VNet flow logs sejam escritos diretamente numa tabela do Log Analytics com o mesmo schema do blob. O que é documentado é que o *traffic analytics* **lê os blobs do Storage**, agrega e "decora" os fluxos e só então ingere o resultado em Azure Monitor logs, na tabela `NTANetAnalytics`. Portanto há **dois schemas distintos** com semânticas distintas, documentados em §3.1/§3.2 (blob) e §3.3 (Log Analytics agregado).

### 2.2 Formato do ficheiro

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Formato | JSON ("Logs are written in the JavaScript Object Notation (JSON) format.") | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| Ficheiro | `PT1H.json` | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage |
| Compressão | **não documentada** | — |
| Encoding | **não documentado** | — |
| Delimitador | JSON; `flowTuples` é "a comma-separated format" | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| Cabeçalho | Não aplicável (JSON) | — |
| Cadência | "Logs are collected at one-minute intervals through the Azure platform." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| Ingestão | "Virtual network flow logs are ingested into a block blob at one-minute intervals by appending blocks. While ingestion is in progress, don't perform operations that modify the blob's block structure, such as editing, overwriting, or deleting the blob content." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage |

### 2.3 Caminho do blob e particionamento (template exato)

Template oficial, transcrito literalmente:

```
https://{storageAccountName}.blob.core.windows.net/insights-logs-flowlogflowevent/flowLogResourceID=/{subscriptionID}_NETWORKWATCHERRG/NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS/y={year}/m={month}/d={day}/h={hour}/m=00/macAddress={macAddress}/PT1H.json
```

Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage> (secção "Download a flow log")

- **Contentor**: `insights-logs-flowlogflowevent`
- **Prefixo de partição**: `flowLogResourceID=/` seguido de `{subscriptionID}_NETWORKWATCHERRG/{NetworkWatcherName}/{FlowLogName}/` — no template oficial o segmento aparece como `NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS` (nome do recurso `FlowLog`).
- **Particionamento temporal**: `y={year}/m={month}/d={day}/h={hour}/m=00/` — o componente de minuto é **literalmente `m=00`** (fixo).
- **Partição por MAC**: `macAddress={macAddress}/`
- **Ficheiro**: `PT1H.json`

### 2.4 Manifesto e metadados

**Nenhum manifesto é documentado.** Não gerar manifesto.

### 2.5 Diferenças face a NSG flow logs (documentadas)

Fonte de toda esta secção: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview>

| Aspeto | Afirmação oficial |
|---|---|
| Âmbito | "you can enable logging at virtual networks. Traffic through all supported workloads within a virtual network is recorded." |
| Simplificação | "Virtual network flow logs also avoid the need to enable multiple-level flow logging, such as in network security group flow logs." |
| Regras avaliadas | "Virtual network flow logs support identification of traffic that Azure Virtual Network Manager security admin rules allow or deny." (NSG flow logs não suportam Virtual Network Manager.) |
| Encriptação | "Virtual network flow logs also support evaluating the encryption status of your network traffic in scenarios where you're using virtual network encryption." (NSG flow logs não suportam.) |
| Protocolo | Nas VNet flow logs o protocolo é "expressed in IANA assigned values" (numérico); nas NSG flow logs é `T`/`U`. |
| Estado de fluxo | VNet flow logs acrescentam `D` (Deny) aos estados `B`/`C`/`E`. |
| Envelope do registo | VNet flow logs usam `flowLogVersion`, `flowLogGUID`, `macAddress`, `flowLogResourceID`, `targetResourceID`, `flowRecords.flows[].aclID`, `flowGroups[].rule`; NSG flow logs usam `systemId`, `properties.Version`, `properties.flows[].rule`, `flows[].mac`. |
| Tabela de destino em Log Analytics | "NTANetAnalytics in virtual network flow logs replaces AzureNetworkAnalytics_CL used in network security group flow logs." |
| Duplicação | "We recommend disabling network security group flow logs before enabling virtual network flow logs on the same underlying workloads to avoid duplicate traffic recording and additional costs." |
| Ordem de precedência de ativação | "If you configure virtual network flow logs at the NIC, subnet, and virtual network levels, the enablement preference follows this order: NIC > subnet > virtual network." |

### 2.6 Tabela de suporte por âmbito (documentada)

| Scope | Network security group flow logs | Virtual network flow logs |
|---|---|---|
| Bytes and packets in stateless flows | Not supported | Supported |
| Identification of virtual network encryption | Not supported | Supported |
| Azure API management | Not supported | Supported |
| Azure Application Gateway | Not supported | Supported |
| Azure Virtual Network Manager | Not supported | Supported |
| ExpressRoute gateway | Not supported | Supported |
| ExpressRoute FastPath | Not supported | Not supported |
| Virtual machine scale sets | Supported | Supported |
| VPN gateway | Not supported | Supported |

Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview>

### 2.7 Storage — requisitos

- **Location**: "The storage account must be in the same region as the virtual network."
- **Subscription**: mesma subscrição ou subscrição associada ao mesmo tenant Microsoft Entra.
- **Performance tier**: "The storage account must be standard. Premium storage accounts aren't supported."
- **Retention policy rules**: "Currently, a storage account supports 100 rules, and each rule can accommodate 10 blob prefixes."
- **Redundância**: "All Azure Storage redundancy configurations are supported, including locally redundant storage (LRS), zone-redundant storage (ZRS), geo-redundant storage (GRS), and geo-zone-redundant storage (GZRS)." — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage>

## 3. Campos

### 3.1 Envelope do registo no blob (`PT1H.json`)

Fonte de toda esta secção: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview> (secção "Log format" e "Sample log record").

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| records | array | true | — | — | — | Raiz do ficheiro `PT1H.json`; array de registos | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].time | string | true | — | ISO 8601 UTC com sufixo `Z`, ex.: `2022-09-14T09:00:52.5625085Z` | — | "Time in UTC when the event was logged." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowLogVersion | integer | true | — | — | `4` (valor do exemplo oficial) | "Version of the flow log." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowLogGUID | string (GUID) | true | — | — | — | "Resource GUID of the `FlowLog` resource." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].macAddress | string | true | — | — | — | "MAC address of the network interface where the event was captured." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].category | string | true | — | — | `FlowLogFlowEvent` | "Category of the event. The category is always `FlowLogFlowEvent`." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowLogResourceID | string | true | — | — | — | "Resource ID of the `FlowLog` resource." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].targetResourceID | string | true | — | — | — | "Resource ID of the target resource that's associated with the `FlowLog` resource." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].operationName | string | true | — | — | `FlowLogFlowEvent` | "Always `FlowLogFlowEvent`." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords | object | true | — | — | — | "Collection of flow records." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords.flows | array | true | — | — | — | "Collection of flows. This property has multiple entries for access control lists (ACLs)" | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords.flows[].aclID | string (GUID) | true | — | — | — ; valor especial `unspecified` | "Identifier of the resource that's evaluating traffic, either a network security group or Virtual Network Manager. For traffic that's denied because of encryption, this value is `unspecified`." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords.flows[].flowGroups | array | true | — | — | — | "Collection of flow records at a rule level" | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords.flows[].flowGroups[].rule | string | true | — | — | `unspecified` para tráfego negado por encriptação | "Name of the rule that allowed or denied the traffic. For traffic that's denied because of encryption, this value is `unspecified`." | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |
| records[].flowRecords.flows[].flowGroups[].flowTuples | array de string (CSV) | true | — | — | — | "String that contains multiple properties for the flow tuple in a comma-separated format" | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview |

### 3.2 `flowTuples` — posições do CSV (VNet flow logs)

Fonte de todas as linhas: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview> (secção "Log format").

| # | Posição | Tipo | Obrigatório | Unidade | Formato | Valores permitidos | Descrição |
|---|---|---|---|---|---|---|---|
| 1 | Time Stamp | integer | true | milissegundos desde a epoch UNIX | epoch | — | "Time stamp of when the flow occurred, in UNIX epoch format." (exemplos com 13 dígitos: `1663146003599`) |
| 2 | Source IP | string | true | — | — | — | "Source IP address." |
| 3 | Destination IP | string | true | — | — | — | "Destination IP address." |
| 4 | Source port | integer | true | — | — | — | "Source port." |
| 5 | Destination port | integer | true | — | — | — | "Destination port." |
| 6 | Protocol | integer | true | — | — | "IANA assigned values" (exemplos: `6` = TCP) | "Layer 4 protocol of the flow, expressed in IANA assigned values." |
| 7 | Flow direction | string | true | — | — | `I` (inbound), `O` (outbound) | "Direction of the traffic flow." |
| 8 | Flow state | string | true | — | — | `B` (Begin), `C` (Continuing), `E` (End), `D` (Deny) | "State of the flow." |
| 9 | Flow encryption | string | true | — | — | `X`, `NX`, `NX_HW_NOT_SUPPORTED`, `NX_SW_NOT_READY`, `NX_NOT_ACCEPTED`, `NX_NOT_SUPPORTED`, `NX_LOCAL_DST`, `NX_FALLBACK` | "Encryption state of the flow." |
| 10 | Packets sent | integer | false | pacotes | — | — | "Total number of packets sent from the source to the destination since the last update." |
| 11 | Bytes sent | integer | false | bytes | — | — | "Total number of packet bytes sent from the source to the destination since the last update. Packet bytes include the packet header and payload." |
| 12 | Packets received | integer | false | pacotes | — | — | "Total number of packets sent from the destination to the source since the last update." |
| 13 | Bytes received | integer | false | bytes | — | — | "Total number of packet bytes sent from the destination to the source since the last update. Packet bytes include the packet header and payload." |

**Total de posições documentadas: 13.**

**Valores documentados de `Flow encryption`** (tabela oficial na mesma página):

| Valor | Significado (tradução fiel) |
|---|---|
| `X` | Connection is encrypted. Encryption is configured, and the platform encrypted the connection. |
| `NX` | Connection is unencrypted. Logged when encryption isn't configured, or when an encrypted VM communicates with an endpoint that lacks encryption (such as an internet endpoint). |
| `NX_HW_NOT_SUPPORTED` | Hardware is unsupported. Encryption is configured, but the VM is running on a host that doesn't support encryption. |
| `NX_SW_NOT_READY` | Software isn't ready. Encryption is configured, but the software component (GFT) in the host networking stack isn't ready; the packet is dropped. |
| `NX_NOT_ACCEPTED` | Drop due to no encryption. Encryption is configured on both source and destination endpoints with a drop on unencrypted policies; if traffic encryption fails, the packet is dropped. |
| `NX_NOT_SUPPORTED` | Discovery is unsupported; the packet is dropped. |
| `NX_LOCAL_DST` | Destination is on the same host; the connection isn't encrypted by design. |
| `NX_FALLBACK` | Fall back to no encryption. Encryption is configured with the **Allow unencrypted** policy on both endpoints; the connection is allowed but isn't encrypted. |

"Traffic in your virtual networks is unencrypted (`NX`) by default." — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview>

**Regras de plataforma (`Platform Rules`)**: a documentação explica que, em flow logs, "a platform rule represents network traffic that is processed by the Azure platform itself rather than by user-configured rules, such as Network Security Groups (NSGs) or Azure Virtual Network Manager rules" e que, nesses casos, "the flow log may associate it with a platform rule instead of a user-defined rule". Não é documentado um valor literal específico para o nome da regra de plataforma. — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview>

### 3.3 Destino Log Analytics — tabela `NTANetAnalytics` (traffic analytics, `FASchemaVersion` 3)

Fonte de todas as linhas: <https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet> (secção "Traffic analytics schema", aba *Virtual network flow logs*).

**Esta é a forma AGREGADA e DECORADA, não o registo bruto do blob.** Ver §2.1(b).

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| TableName | string | true | — | — | `NTANetAnalytics` | Table for traffic analytics data. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SubType | string | true | — | — | `FlowLog` | Subtype for the flow logs. Use only FlowLog; other values are for internal use. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FASchemaVersion | integer | true | — | — | `3` | Schema version. Doesn't reflect virtual network flow log version. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| TimeProcessed | datetime | true | — | UTC | — | Time at which the traffic analytics processed the raw flow logs from the storage account. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowIntervalStartTime | datetime | true | — | UTC | — | Starting time of the flow log processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowIntervalEndTime | datetime | true | — | UTC | — | Ending time of the flow log processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowStartTime | datetime | true | — | UTC | — | First occurrence of the flow (which gets aggregated) in the processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowEndTime | datetime | true | — | UTC | — | Last occurrence of the flow (which gets aggregated) in the processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowType | string | true | — | — | `IntraVNet`, `InterVNet`, `S2S`, `P2S`, `AzurePublic`, `ExternalPublic`, `MaliciousFlow`, `Unknown Private`, `Unknown` | Categorização do fluxo segundo os IPs envolvidos. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcIp | string | true | — | — | — | Source IP address. Blank in AzurePublic and ExternalPublic flows. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestIp | string | true | — | — | — | Destination IP address. Blank in AzurePublic and ExternalPublic flows. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| TargetResourceId | string | true | — | — | — | The ID of the resource at which flow logging and traffic analytics is enabled (ResourceGroupName/ResourceName). | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| TargetResourceType | string | true | — | — | `VirtualNetwork`, `Subnet`, `NetworkInterface` | Type of resource at which flow logging and traffic analytics is enabled. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowLogResourceId | string | true | — | — | — | The resource ID of the flow log (ResourceGroupName/NetworkWatcherName/FlowLogName). | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestPort | integer | true | — | — | — | Port at which traffic is incoming. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| L4Protocol | string | true | — | — | `T` (TCP), `U` (UDP) | Transport Protocol. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| L7Protocol | string | true | — | — | — | Protocol Name. Derived from destination port. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowDirection | string | true | — | — | `I` (Inbound), `O` (Outbound) | Direction of the flow: in or out of the target resource per flow log. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowStatus | string | true | — | — | `A` (Allowed), `D` (Denied) | Status of flow: allowed or denied by target resource per flow log. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| AclGroup | string | true | — | — | — | `<SubscriptionID>/<resourcegroup_Name>/<NSG_Name>` — Network security group associated with the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| AclRule | string | true | — | — | — | NSG_Rule_Name — Network security group rule that allowed or denied the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| MACAddress | string | true | — | — | — | MAC address of the NIC at which the flow was captured. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcSubscription | string | true | — | — | — | Subscription ID of virtual network / network interface / virtual machine that the source IP in the flow belongs to. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestSubscription | string | true | — | — | — | Subscription ID of virtual network / network interface / virtual machine that the destination IP in the flow belongs to. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcRegion | string | true | — | — | — | Azure region of virtual network / network interface / virtual machine that the source IP in the flow belongs to. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestRegion | string | true | — | — | — | Azure region of virtual network that the destination IP in the flow belongs to. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcNic | string | true | — | — | — | `<resourcegroup_Name>/<NetworkInterfaceName>` — NIC associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestNic | string | true | — | — | — | `<resourcegroup_Name>/<NetworkInterfaceName>` — NIC associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcVm | string | true | — | — | — | `<resourcegroup_Name>/<VirtualMachineName>` — Virtual machine associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestVm | string | true | — | — | — | `<resourcegroup_Name>/<VirtualMachineName>` — Virtual machine associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcSubnet | string | true | — | — | — | `<ResourceGroup_Name>/<VirtualNetwork_Name>/<SubnetName>` — Subnet associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestSubnet | string | true | — | — | — | `<ResourceGroup_Name>/<VirtualNetwork_Name>/<SubnetName>` — Subnet associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcApplicationGateway | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<ApplicationGatewayName>` — Application gateway associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestApplicationGateway | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<ApplicationGatewayName>` — Application gateway associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcExpressRouteCircuit | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<ExpressRouteCircuitName>` — ExpressRoute circuit ID, when flow is sent from site via ExpressRoute. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestExpressRouteCircuit | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<ExpressRouteCircuitName>` — ExpressRoute circuit ID, when flow is received from cloud by ExpressRoute. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ExpressRouteCircuitPeeringType | string | true | — | — | `AzurePrivatePeering`, `AzurePublicPeering`, `MicrosoftPeering` | ExpressRoute peering type involved in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcLoadBalancer | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<LoadBalancerName>` — Load balancer associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestLoadBalancer | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<LoadBalancerName>` — Load balancer associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcLocalNetworkGateway | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<LocalNetworkGatewayName>` — Local network gateway associated with the source IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestLocalNetworkGateway | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<LocalNetworkGatewayName>` — Local network gateway associated with the destination IP in the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ConnectionType | string | true | — | — | `VNetPeering`, `VpnGateway`, `ExpressRoute` | The connection type. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ConnectionName | string | true | — | — | — | `<SubscriptionID>/<ResourceGroupName>/<ConnectionName>`; for flow type P2S formatted as `<GatewayName>_<VPNClientIP>` | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ConnectingVNets | string | true | — | — | — | Space separated list of virtual network names. In hub and spoke topology, hub virtual networks are populated here. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| Country | string | true | — | — | ISO 3166-1 alpha-2 | Two-letter country code. Populated for flow type ExternalPublic. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| AzureRegion | string | true | — | — | — | Azure region locations. Populated for flow type AzurePublic. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| AllowedInFlows | integer | true | flows | — | — | Count of inbound flows that were allowed. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DeniedInFlows | integer | true | flows | — | — | Count of inbound flows that were denied. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| AllowedOutFlows | integer | true | flows | — | — | Count of outbound flows that were allowed. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DeniedOutFlows | integer | true | flows | — | — | Count of outbound flows that were denied. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PacketsDestToSrc | integer | true | packets | — | — | Represents packets sent from the destination to the source of the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PacketsSrcToDest | integer | true | packets | — | — | Represents packets sent from the source to the destination of the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| BytesDestToSrc | integer | true | bytes | — | — | Represents bytes sent from the destination to the source of the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| BytesSrcToDest | integer | true | bytes | — | — | Represents bytes sent from the source to the destination of the flow. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| CompletedFlows | integer | true | flows | — | — | Total number of flows completed (populated with non-zero value when a flow gets a completed event). | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SrcPublicIps | string | true | — | — | — | `<SOURCE_PUBLIC_IP>\|<FLOW_STARTED_COUNT>\|<FLOW_ENDED_COUNT>\|<OUTBOUND_PACKETS>\|<INBOUND_PACKETS>\|<OUTBOUND_BYTES>\|<INBOUND_BYTES>`; entries separated by bars. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DestPublicIps | string | true | — | — | — | `<DESTINATION_PUBLIC_IP>\|<FLOW_STARTED_COUNT>\|<FLOW_ENDED_COUNT>\|<OUTBOUND_PACKETS>\|<INBOUND_PACKETS>\|<OUTBOUND_BYTES>\|<INBOUND_BYTES>`; entries separated by bars. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowEncryption | string | true | — | — | `Encrypted`, `Unencrypted`, `Unsupported hardware`, `Software not ready`, `Drop due to no encryption`, `Discovery not supported`, `Destination on same host`, `Fall back to no encryption.` | Encryption level of flows. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PrivateEndpointResourceId | string | true | — | — | — | `<ResourceGroup/privateEndpointResource>` — Resource ID of the private endpoint resource. Populated when traffic is flowing to or from a private endpoint resource. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PrivateLinkResourceId | string | true | — | — | — | `<ResourceGroup/ResourceType/privateLinkResource>` — Resource ID of the private link service. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PrivateLinkResourceName | string | true | — | — | — | Resource name of the private link service. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| IsFlowCapturedAtUDRHop | boolean | true | — | — | `True`, `False` | If the flow was captured at a UDR hop, the value is True. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |

> **Nota de tipo:** a coluna "Format" da tabela oficial é descritiva (por exemplo "Date and time in UTC", "Subscription ID"). A coluna **Tipo** acima traduz essa descrição para um tipo de dados; onde a documentação não indica o tipo, foi usado `string` por ser o formato textual descrito. Os campos `AllowedInFlows`/`DeniedInFlows`/`AllowedOutFlows`/`DeniedOutFlows`/`CompletedFlows` têm "Format" **vazio** no documento oficial e a descrição diz "Count of…" — o tipo `integer` é uma **classificação nossa, não uma afirmação oficial**. Ver §4.

### 3.4 Destino Log Analytics — tabela `NTAIpDetails` (dados de IP público)

Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet>

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| TableName | string | true | — | — | `NTAIpDetails` | Table that contains traffic analytics IP details data. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| SubType | string | true | — | — | `FlowLog` | Subtype for the flow logs. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FaSchemaVersion | integer | true | — | — | `3` | Schema version. Doesn't reflect virtual network flow log version. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowIntervalStartTime | datetime | true | — | UTC | — | Start time of the flow log processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowIntervalEndTime | datetime | true | — | UTC | — | End time of the flow log processing interval. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| FlowType | string | true | — | — | `AzurePublic`, `ExternalPublic`, `MaliciousFlow` | See Notes for definitions. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| IP | string | true | — | — | — | Public IP whose information is provided in the record. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| PublicIPDetails | string | true | — | — | — | For AzurePublic IP: Azure Service owning the IP or `Microsoft Virtual Public IP` for 168.63.129.16. For ExternalPublic/Malicious IP: WhoIS information of the IP. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ThreatType | string | false | — | — | `Botnet`, `C2`, `CryptoMining`, `DarkNet`, `DDoS`, `MaliciousUrl`, `Malware`, `Phishing`, `Proxy`, `PUA`, `WatchList` | Threat posed by malicious IP. For Malicious IPs only. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| DNSDomain | string | false | — | — | — | For Malicious IPs only. Domain name associated with this IP. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| ThreatDescription | string | false | — | — | — | For Malicious IPs only. Description of the threat posed by the malicious IP. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| Location | string | true | — | — | ISO 3166-1 alpha-2 (external/malicious) | For Azure Public IP: Azure region of the resource to which the IP belongs or Global for 168.63.129.16. For External Public IP and Malicious IP: two-letter country code. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| Url | string | false | — | — | — | For Malicious IPs only. URL corresponding to the malicious IP. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |
| Port | integer | false | — | — | — | For Malicious IPs only. Port corresponding to the malicious IP. | https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet |

## 4. Campos não comprovados

### 4.0 Nota sobre `sets` e `evidence` no `.schema.json` (contrato atualizado)

O `.schema.json` está organizado em `sets`, um por estrutura documentada. Isto é **obrigatório** aqui, não cosmético: esta superfície tem **três esquemas distintos** (§3.1/§3.2 blob, §3.3 `NTANetAnalytics`, §3.4 `NTAIpDetails`) e os nomes `TableName`, `SubType`, `FlowType`, `FlowIntervalStartTime` e `FlowIntervalEndTime` aparecem em **mais do que uma** dessas estruturas com significados diferentes. Achatar num único conjunto destruiria essa distinção.

| set | estrutura | `evidence` nas colunas | Gerável? |
|---|---|---|---|
| `blob` | registo bruto de `records[]` | `example-only` | não — sem tipo e a trava impede `format-observed` |
| `blob-envelope` | envelope do registo no blob | `example-only` | não — sem tipo e a trava impede `format-observed` |
| `flowTuples-position` | as 13 posições do CSV `flowTuples` | `example-only` | não — sem tipo e a trava impede `format-observed` |
| `NTANetAnalytics` | tabela agregada do traffic analytics | `declared` | **5 de 62** — só as que têm tipo afirmado |
| `NTAIpDetails` | tabela de enriquecimento de IP | `declared` | **2 de 14** — só as que têm tipo afirmado |

**Veredito de gerabilidade: 7 de 127 colunas são geráveis** (inalterado pela introdução de `type_source`).

**Justificação (uma frase):** as 7 geráveis são exatamente as colunas cujo **tipo a própria documentação enuncia em prosa normativa** — "Date and time in UTC" em `TimeProcessed`, `FlowIntervalStartTime`, `FlowIntervalEndTime`, `FlowStartTime` e `FlowEndTime` (set `NTANetAnalytics`) e `FlowIntervalStartTime`/`FlowIntervalEndTime` (set `NTAIpDetails`) — enquanto as restantes têm a coluna "Format" da tabela oficial preenchida com **prosa descritiva** ("Subscription ID", "MAC Address") ou **em branco** (os contadores de fluxos), pelo que o tipo foi classificado por nós e a coluna fica com `type: null` + `type_note` e não é gerável.

**Porque os 120 campos de `example-only` não podem usar `type_source: "format-observed"`:** a trava do contrato recusa derivar a forma de um exemplo para um campo que não esteja declarado (`evidence: "declared"`). Nos sets `blob`, `blob-envelope` e `flowTuples-position` as 120 colunas estão qualificadas como `example-only` — o `.schema.json` regista que a coluna consta da tabela de schema oficial, mas que o único tipo disponível é a classificação do autor e não uma afirmação da Microsoft — logo `format-observed` fica barrado e nenhuma destas 120 colunas muda. Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-overview> (§"Log format") e <https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet> (§"Traffic analytics schema").

> **Nota:** os tipos `integer`/`string` que constam das tabelas de §3.1–§3.4 deste documento continuam a ser a nossa leitura dos dados; o `.schema.json` só os marca como geráveis onde a documentação os enuncia, e usa `type_note` para explicar a ausência nos demais.

| Campo | Estado | Motivo |
|---|---|---|
| Compressão do blob `PT1H.json` | UNVERIFIED | Não documentada. |
| Encoding do blob | UNVERIFIED | Não documentado. |
| Tipos de dados declarados para as colunas de `NTANetAnalytics` | UNVERIFIED | O documento oficial apresenta a coluna "Format" como texto descritivo (ex.: "Date and time in UTC", "Subscription ID") e deixa-a **em branco** para `AllowedInFlows`, `DeniedInFlows`, `AllowedOutFlows`, `DeniedOutFlows`, `CompletedFlows`. O tipo `integer` atribuído na tabela acima é classificação do autor da spec. |
| Tipos de dados declarados para as colunas de `NTAIpDetails` | UNVERIFIED | Idem: "Format" descritivo. |
| Valor literal do nome de uma *platform rule* | UNVERIFIED | A documentação descreve o conceito de platform rule mas não publica o literal que aparece em `flowGroups[].rule` nesse caso. |
| Valores permitidos de `flowLogVersion` | UNVERIFIED | O único valor observado na documentação é `4` no exemplo oficial; a documentação não publica uma enumeração dos valores válidos. |
| Manifesto / ficheiro de metadados | UNVERIFIED | Não documentado. |
| Esquema de colunas de `NTANetAnalytics` segundo a referência do Azure Monitor | UNVERIFIED | A página oficial de traffic analytics remete para `/azure-monitor/reference/tables/ntanetanalytics`, mas o documento consultado **não** transcreve os tipos dessa referência; não foi usada nenhuma lista de colunas não lida. |
| Prefixo exato `NETWORKWATCHER_{Region}_...` vs. nome do recurso FlowLog | UNVERIFIED | O template oficial usa `NETWORKWATCHER_{Region}_{ResourceName}-{ResourceGroupName}-FLOWLOGS` dentro do segmento de partição; a documentação não afirma como isso é derivado quando o nome do FlowLog é personalizado. |

## 5. Divergências conhecidas

1. **A barra dupla em `flowLogResourceID=/`.** O template oficial apresenta literalmente `insights-logs-flowlogflowevent/flowLogResourceID=/{subscriptionID}_NETWORKWATCHERRG/...` — com `/` imediatamente a seguir ao `=`. Transcrito como está; não normalizado.
2. **Unidades do campo de tempo do tuple.** Nas NSG flow logs o timestamp é em **segundos** epoch (10 dígitos nos exemplos); nas VNet flow logs os exemplos oficiais mostram **13 dígitos** (`1663146003599`). O texto de ambas as páginas diz "UNIX epoch format". A diferença de granularidade é observável nos exemplos oficiais e não é explicitamente comentada pela documentação — registada como divergência.
3. **Protocolo numérico vs. literal.** VNet flow logs usam valores IANA atribuídos (numérico); NSG flow logs usam `T`/`U`. Não converter entre formatos sem regra explícita.
4. **`FASchemaVersion` ≠ `flowLogVersion`.** A documentação afirma explicitamente: "Schema version. Doesn't reflect virtual network flow log version." São dois números independentes (3 vs 4 nos exemplos). Não confundir.
5. **Agregação do traffic analytics altera a cardinalidade.** "Flows that have the same `Source IP`, `Destination IP`, `Destination port`, `NSG name`, `NSG rule`, `Flow Direction`, and `Transport layer protocol (TCP or UDP)` are clubbed into a single flow by traffic analytics (Note: source port is excluded for aggregation)." e "the flows indicated in the Azure portal are total flows seen, but in Azure Monitor logs, user sees only the single, reduced record. To see all the flows, use the `blob_id` field". — <https://learn.microsoft.com/en-us/azure/network-watcher/traffic-analytics-schema?tabs=vnet>. O campo `blob_id` é referido no texto mas **não consta** da tabela de schema — ver §4 (não listado como campo por falta de linha de schema).
6. **Sufixos `_s`/`_d`.** "Some field names are appended with `_s` or `_d`, which don't signify source and destination but indicate the data types string and decimal respectively." Esses sufixos não aparecem na tabela de schema (que usa nomes sem sufixo, ex.: `SrcIp`) mas aparecem no texto das notas (`VMIP_s`, `PublicIPs_s`, `SrcIP_s`, `SrcIP_s`, `FlowIntervalStartTime_t`). Divergência entre a tabela de schema e o texto — não normalizar por inferência.
7. **Retenção**: as regras de retenção em Storage estão limitadas a 100 regras por conta e 10 prefixos de blob por regra; `0` significa retenção indefinida. — <https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage>
