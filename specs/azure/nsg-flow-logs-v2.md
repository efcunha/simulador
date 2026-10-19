# Azure NSG flow logs — versão 2 escrita numa conta de armazenamento

## 1. Identificação

- **Nome oficial da superfície de export**: *Network security group (NSG) flow logs* — Azure Network Watcher.
- **Documento oficial principal**: "Flow logging for network security groups" (*NSG Flow Logs Overview*) —
  <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview> — consultado em **2026-10-14** (página atualizada em 2026-02-10).
- **Documento de apoio consultado em 2026-10-14**: "Create, change, disable, or delete NSG flow logs" — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-manage>
- **Versão/schema de referência**: **Version 2** do schema de evento (`"Version": 2`). A versão 1 é legada e não inclui estado de fluxo nem contadores.
- **Aviso de retirada (documentado)**: "Network security group (NSG) flow logs retire on September 30, 2027. Because the feature is retiring, it no longer supports new NSG flow logs creation. Migrate to virtual network flow logs… Azure doesn't delete existing NSG flow log records from Azure Storage, and they continue to follow their configured retention policies." — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

## 2. Mecanismo e entrega

### 2.1 O mecanismo existe e o destino é Storage

> "NSG flow logs are written to storage accounts. You can export, process, analyze, and visualize NSG flow logs by using tools like Network Watcher traffic analytics, Splunk, Grafana, and Stealthwatch."
> — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

**Destino documentado:** Azure Storage (conta de armazenamento, blob). O documento afirma: "Flow data is sent to Azure Storage from where you can access it and export it to any visualization tool, security information and event management (SIEM) solution, or intrusion detection system (IDS) of your choice."

### 2.2 Formato do ficheiro

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Formato | JSON ("Logs are written in JSON format") | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| Ficheiro | `PT1H.json` (um por hora, por MAC) | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| Compressão | **não documentada** para o ficheiro em si | — |
| Encoding | **não documentado** | — |
| Delimitador | O ficheiro é JSON; os valores dentro de `flowTuples` são CSV ("Values in the `flowTuples` property are a comma-separated list.") | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| Cabeçalho | Não aplicável (JSON) | — |
| Cadência | "Logs are collected at 1-minute intervals through the Azure platform." e "Logs are written in JSON format and show outbound and inbound flows per network security group rule." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| Ingestão em bloco | O blob é escrito **anexando blocos**. (Afirmado na página das VNet flow logs, que partilha o mecanismo de blob; aplica-se ao mesmo serviço de flow logs.) | https://learn.microsoft.com/en-us/azure/network-watcher/vnet-flow-logs-manage |

### 2.3 Caminho do blob e particionamento (template exato)

Template oficial, transcrito literalmente:

```
https://{storageAccountName}.blob.core.windows.net/insights-logs-networksecuritygroupflowevent/resourceId=/SUBSCRIPTIONS/{subscriptionID}/RESOURCEGROUPS/{resourceGroupName}/PROVIDERS/MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/{nsgName}/y={year}/m={month}/d={day}/h={hour}/m=00/macAddress={macAddress}/PT1H.json
```

Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview> (secção "Read and export flow logs")

- **Contentor**: `insights-logs-networksecuritygroupflowevent`
- **Prefixo de partição**: `resourceId=/SUBSCRIPTIONS/{subscriptionID}/RESOURCEGROUPS/{resourceGroupName}/PROVIDERS/MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/{nsgName}/`
- **Particionamento temporal**: `y={year}/m={month}/d={day}/h={hour}/m=00/` — o componente de minuto é **literalmente `m=00`** (fixo), porque o ficheiro é horário.
- **Partição por MAC**: `macAddress={macAddress}/`
- **Ficheiro**: `PT1H.json`

### 2.4 Manifesto e metadados

Nenhum manifesto é documentado. O ficheiro `PT1H.json` contém diretamente o array `records`. **Não gerar manifesto.**

### 2.5 Retenção

"NSG flow logs have a retention feature that allows deleting the logs automatically up to a year after their creation." e "Retention is available only if you use general-purpose v2 storage accounts." — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

## 3. Campos

### 3.1 Envelope do registo (objeto dentro de `records[]`)

Fonte de toda esta secção: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview> (secção "Log format" e exemplos "Version 2").

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| records | array (de registo) | true | — | — | — | Array de registos de flow log; é a raiz do ficheiro `PT1H.json` | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].time | string | true | — | ISO 8601 UTC, com parte fracionária de 7 dígitos e sufixo `Z`, ex.: `2018-11-13T12:00:35.3899262Z` | — | "Time in UTC when the event was logged." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].systemId | string (GUID) | true | — | — | — | "System ID of the network security group." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].category | string | true | — | — | `NetworkSecurityGroupFlowEvent` | "Category of the event. The category is always `NetworkSecurityGroupFlowEvent`." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].resourceId | string | true | — | — | — | "Resource ID of the network security group." (no exemplo, em maiúsculas: `/SUBSCRIPTIONS/…/RESOURCEGROUPS/…/PROVIDERS/MICROSOFT.NETWORK/NETWORKSECURITYGROUPS/…`) | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].operationName | string | true | — | — | `NetworkSecurityGroupFlowEvents` | "Always `NetworkSecurityGroupFlowEvents`." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties | object | true | — | — | — | "Collection of properties of the flow" | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.Version | integer | true | — | — | `1` ou `2` (a versão 2 emite `2`) | "Version number of the flow log's event schema." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.flows | array | true | — | — | — | "Collection of flows. This property has multiple entries for different rules." | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.flows[].rule | string | true | — | — | — | "Rule for which the flows are listed." (ex.: `DefaultRule_DenyAllInBound`, `UserRule_default-allow-rdp`, `DefaultRule_AllowInternetOutBound`) | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.flows[].flows | array | true | — | — | — | "Collection of flows." (nível por MAC) | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.flows[].flows[].mac | string (hex, 12 dígitos, sem separadores) | true | — | — | — | "MAC address of the NIC for the VM where the flow was collected." (ex.: `000D3AF87856`) | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |
| records[].properties.flows[].flows[].flowTuples | array de string (CSV) | true | — | — | — | "String that contains multiple properties for the flow tuple in a comma-separated format" | https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview |

### 3.2 `flowTuples` — as posições do CSV (ordem obrigatória)

A documentação define a **ordem** das posições. Fonte de todas as linhas: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview> (secção "Log format" — lista de `flowTuples`).

| # | Posição | Tipo | Obrigatório | Unidade | Formato | Valores permitidos | Descrição |
|---|---|---|---|---|---|---|---|
| 1 | Time stamp | integer | true | segundos (UNIX epoch) | epoch | — | "Time stamp of when the flow occurred in UNIX epoch format." |
| 2 | Source IP | string (IPv4/IPv6) | true | — | — | — | "Source IP address." |
| 3 | Destination IP | string (IPv4/IPv6) | true | — | — | — | "Destination IP address." |
| 4 | Source port | integer | true | — | — | — | "Source port." |
| 5 | Destination port | integer | true | — | — | — | "Destination port." |
| 6 | Protocol | string | true | — | — | `T` (TCP), `U` (UDP) | "Protocol of the flow. Valid values are `T` for TCP and `U` for UDP." |
| 7 | Traffic flow | string | true | — | — | `I` (inbound), `O` (outbound) | "Direction of the traffic flow." |
| 8 | Traffic decision | string | true | — | — | `A` (allowed), `D` (denied) | "Whether traffic was allowed or denied." |
| 9 | Flow State — **Version 2 only** | string | true (em v2) | — | — | `B` (Begin), `C` (Continuing), `E` (End) | "State of the flow." |
| 10 | Packets sent — **Version 2 only** | integer (ou vazio) | false | pacotes | — | — | "Total number of TCP packets sent from source to destination since the last update." |
| 11 | Bytes sent — **Version 2 only** | integer (ou vazio) | false | bytes | — | — | "Total number of TCP packet bytes sent from source to destination since the last update. Packet bytes include the packet header and payload." |
| 12 | Packets received — **Version 2 only** | integer (ou vazio) | false | pacotes | — | — | "Total number of TCP packets sent from destination to source since the last update." |
| 13 | Bytes received — **Version 2 only** | integer (ou vazio) | false | bytes | — | — | "Total number of TCP packet bytes sent from destination to source since the last update. Packet bytes include packet header and payload." |

**Total de posições documentadas: 13.** Em fluxos com estado `B` (Begin), as posições 10–13 aparecem **vazias** — o exemplo oficial é literalmente `"1542110402,192.0.2.190,10.5.16.4,28746,443,U,I,D,B,,,,"` (quatro campos vazios à direita). Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

**Semântica dos contadores (documentada):** "For continuation (`C`) and end (`E`) flow states, byte and packet counts are aggregate counts from the time of the previous flow's tuple record." Exemplo oficial de cálculo: para `1708978215,203.0.113.105,10.0.0.5,35370,443,T,I,A,B,,,,` / `…C,1021,588096,8005,4610880` / `…E,52,29952,47,27072`, o total de pacotes é 1021+52+8005+47 = 9125 e o total de bytes é 588096+29952+4610880+27072 = 5256000. Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

### 3.3 Configuração do recurso (não é o registo)

- **Localização**: "The storage account must be in the same region as the network security group." — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>
- **Subscrição**: "The storage account must be in the same subscription of the network security group or in a subscription associated with the same Microsoft Entra tenant of the network security group's subscription."
- **Nível de desempenho**: "The storage account must be standard. Premium storage accounts aren't supported."
- **Registo de recurso necessário**: o fornecedor `Microsoft.Insights` tem de estar registado — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>

## 4. Campos não comprovados

### 4.0 Nota sobre `sets` e `evidence` no `.schema.json` (contrato atualizado)

O `.schema.json` está organizado em dois `sets`, porque as secções §3.1 e §3.2 descrevem camadas diferentes do mesmo ficheiro:

| set | estrutura | `evidence` | Gerável? |
|---|---|---|---|
| `record` (26) | campos de `records[]` (§3.1) | `declared` | **13 de 26** — os 13 membros JSON; as 13 posições do CSV `flowTuples` ficam de fora |
| `flowTuples-position` (13) | as 13 posições do CSV `flowTuples` (§3.2) | `declared` | **não** — o payload entrega-as dentro de uma string |

**Veredito de gerabilidade: 13 das 39 colunas são geráveis** (os 13 membros JSON do registo); as 26 colunas de posição do CSV `flowTuples` continuam **não-geráveis**.

**Justificação (uma frase):** os campos são `declared` porque a secção "Log format" da página oficial **descreve normativamente o formato do registo** — enumera cada propriedade por nome e afirma o que cada uma significa ("`time`: Time in UTC when the event was logged.", "`category`: Category of the event. The category is always `NetworkSecurityGroupFlowEvent`.", "`rule`: Rule for which the flows are listed.") e define a **ordem obrigatória** das 13 posições do `flowTuples` a partir de `flowTuples` ("String that contains multiple properties for the flow tuple in a comma-separated format") — e, para os **13 membros JSON**, a amostra oficial "Version 2" fixa a representação de cada um (`"time": "2018-11-13T12:00:35.3899262Z"` ⇒ string; `"Version": 2` ⇒ número inteiro; `"properties": { … }` ⇒ objeto; `"flows": [ … ]` e `"flowTuples": [ … ]` ⇒ array), o que sob o contrato atual autoriza `type_source: "format-observed"` com o trecho citado em `type_note`. As **posições do CSV** não recebem tipo: o payload oficial entrega-as **dentro de uma string** (`"flowTuples": [ "1542110402,192.0.2.190,10.5.16.4,28746,443,U,I,D,B,,,," ]`), pelo que nenhum exemplo fixa um **tipo JSON** para a posição — e nos contadores 10–13 o próprio exemplo mostra campo vazio no estado `B`.

Fonte: <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview> — secção **"Log format"** (e a amostra "Version 2").

> **Nota de rigor:** os valores de tipo que aparecem nas tabelas de §3.1/§3.2 deste documento (ex.: `integer` para as posições 1/4/5, `string` para a posição 2) foram lidos das **amostras JSON oficiais**, não de uma tabela de tipos da Microsoft. No `.schema.json`, os 13 membros JSON carregam agora esse tipo com `type_source: "format-observed"` + `type_note` citando o trecho oficial; as 13 posições do CSV mantêm `type: null` + `type_note` explicando por que a forma não é fixada.

| Campo | Estado | Motivo |
|---|---|---|
| Campo de **compressão** do `PT1H.json` | UNVERIFIED | Nenhuma página oficial consultada afirma compressão (nem a sua ausência). Não assumir gzip. |
| Campo de **encoding** | UNVERIFIED | Nenhuma página oficial consultada afirma encoding. |
| `records[].properties.flows[].flows[].flowTuples` com contadores presentes em estado `B` | UNVERIFIED | A documentação afirma "Statistics aren't provided" para `B`; os exemplos mostram campos vazios. Não documenta um valor numérico nem um literal alternativo. |
| Sufixo/padrão exato de data/hora quando a parte fracionária não tem 7 dígitos | UNVERIFIED | Todos os exemplos oficiais mostram 7 dígitos. A documentação não afirma que sejam sempre 7. |
| Manifesto / ficheiro de metadados | UNVERIFIED | Nenhuma página oficial consultada documenta manifesto para NSG flow logs v2. |
| Nome de contentor alternativo ou prefixo `resourceId=` com maiúsculas/minúsculas canónico | UNVERIFIED | O template oficial mostra `resourceId=/SUBSCRIPTIONS/…` em maiúsculas, mas o `resourceId` do registo é apresentado como `/SUBSCRIPTIONS/…` nos exemplos v1 e `resourceId` minúsculo na lista de propriedades (`resourceid`). Divergência registada em §5, não resolvida por inferência. |
| Tamanho máximo do ficheiro `PT1H.json` / número máximo de registos | UNVERIFIED | Não documentado. |

## 5. Divergências conhecidas

1. **Caixa do nome do campo `resourceId`.** A lista de propriedades da secção "Log format" escreve `resourceid` (tudo minúsculo); **todos os exemplos JSON oficiais** escrevem `resourceId`. Ambas as grafias aparecem no **mesmo** documento oficial. Registado — não escolher por conta própria. A implementação deve aceitar `resourceId` (forma dos exemplos) e assinalar a divergência.
2. **Ficheiro de exemplo v1 malformado.** O exemplo "Version 1" do documento oficial contém um `records` aninhado dentro de `records` e chaves desequilibradas (o objeto externo tem `records` dentro de `records`). É um defeito da documentação, não uma variante de schema. Não replicar.
3. **Contadores em fluxos inbound não-default.** "network security group non-default security rules that affect inbound TCP flows are implemented in a stateless way. Flows affected by non-default inbound rules become non-terminating. Additionally, byte and packet counts aren't recorded for these flows. Because of those factors, the number of bytes and packets reported in NSG flow logs (and Network Watcher traffic analytics) could be different from actual numbers." — <https://learn.microsoft.com/en-us/azure/network-watcher/nsg-flow-logs-overview>
4. **Retenção limitada a um ano e apenas GPv2.** Documentado explicitamente. Ver §2.5.
5. **Retirada do mecanismo em 2027-09-30.** O mecanismo continua documentado mas já não permite criar novos NSG flow logs. Deve ser tratado como *legacy* no simulador.
