# `azure/arm-network-security-group-rules` — regras de NSG (ARM)

Superfície que fechou a **G1** deste lado: o consumidor do FinOps percorre as **regras** de
cada NSG e filtra por `direction`/`access`
(`security.py (modulo do consumidor):107,109`), e o estado canônico não tinha
nenhuma regra. O emulador `azure-sim` respondia **lista vazia por desenho** para
`networkSecurityGroups`, com a justificativa registrada de que "the estate models no network
security group" — e a subscription era reportada como **limpa porque não havia o que varrer**.

Fonte: [Microsoft.Network networkSecurityGroups](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/networksecuritygroups)
(HTTP 200, consultado em 2026-10-14; última atualização da página: 2026-09-21). A página do
recurso filho ([networkSecurityGroups/securityRules](https://learn.microsoft.com/en-us/azure/templates/microsoft.network/networksecuritygroups/securityrules))
publica o **mesmo** `SecurityRulePropertiesFormat`.

## Por que o envelope é o do recurso PAI

A superfície entrega o corpo do **NSG** (`GET .../networkSecurityGroups/{nsg}`), com as regras em
`properties.securityRules[]`. Duas razões, ambas vindas do consumidor: é o `list` de
`networkSecurityGroups` que um scanner de postura chama, e é essa coleção que ele itera. O
arquivo do recurso filho traria a mesma `SecurityRulePropertiesFormat` em outro envelope — a
escolha é declarada, não acidental.

Não é um formato de export: é a **resposta de uma API**, como `arm-resource-representation`.

## Os 15 campos documentados de uma regra

Tabela `SecurityRulePropertiesFormat`, com o tipo que a página publica:

| Campo | Tipo / domínio | Obrigatório |
|---|---|---|
| `access` | `'Allow'` \| `'Deny'` | **sim** |
| `direction` | `'Inbound'` \| `'Outbound'` | **sim** |
| `priority` | int, 100–4096, único na coleção; menor = maior prioridade | **sim** |
| `protocol` | `'*'` \| `'Ah'` \| `'Esp'` \| `'Icmp'` \| `'Tcp'` \| `'Udp'` | **sim** |
| `description` | string, até 140 chars | não |
| `sourceAddressPrefix` | string (CIDR/IP; `'*'`, `'VirtualNetwork'`, `'AzureLoadBalancer'`, `'Internet'`) | não |
| `sourceAddressPrefixes` | string[] | não |
| `destinationAddressPrefix` | string (mesmos curingas) | não |
| `destinationAddressPrefixes` | string[] | não |
| `sourcePortRange` | string (0–65535, ou `'*'`) | não |
| `sourcePortRanges` | string[] | não |
| `destinationPortRange` | string (0–65535, ou `'*'`) | não |
| `destinationPortRanges` | string[] | não |
| `sourceApplicationSecurityGroups` | ApplicationSecurityGroup[] | não |
| `destinationApplicationSecurityGroups` | ApplicationSecurityGroup[] | não |

**O que o consumidor precisa** são estritamente `direction` e `access`. Os outros 13 entram
porque este projeto não emite nome não citado — e porque a evidência do achado se beneficia de
`priority`, `protocol` e dos prefixos.

**Nota de fidelidade:** a página publica `ApplicationSecurityGroup` com `id`, `location`,
`properties` e `tags`, mas a tabela `ApplicationSecurityGroupPropertiesFormat` vem **vazia** — o
provedor não declara o conteúdo. É o caso `name-only`: o nome entra no contrato, o valor sai
vazio em vez de inventado. Pelo mesmo motivo, `properties.flushConnection` (tipo publicado,
valor não) e `apiVersion` (não é campo do corpo) ficam registrados como não comprovados.

## O que o estado gera

`model/network.py` ganhou `NetworkSecurityGroup` (assinatura, resource group, nome, regras) e
`SecurityRule` (nome, prioridade, direção, acesso, protocolo, prefixos e faixas). O
`EstateBuilder` monta **um NSG por segmento Azure**, com a postura declarada em
`generate/constants.py::NSG_SECURITY_RULES`:

| Regra | Prioridade | Direção | Acesso | Protocolo | Porta de destino |
|---|---|---|---|---|---|
| `AllowVnetInboundTls` | 100 | Inbound | **Allow** | Tcp | 443 |
| `DenyInternetInboundRdp` | 200 | Inbound | **Deny** | Tcp | 3389 |

A regra é uma **política, não um sorteio**: os dois casos vivem no **mesmo** NSG para que o
teste consiga provar que o filtro do consumidor distingue um do outro — um artefato só com
`Allow` passaria mesmo se o filtro estivesse invertido. As prioridades são únicas e o `Allow` é
avaliado antes, que é o que torna a exposição real.

Os prefixos e a porta de origem usam `'*'`, que a própria página documenta para esses campos:
usar um CIDR exigiria afirmar a faixa da VNet, que o modelo não carrega, e um prefixo que não
contivesse as NICs da mesma VNet seria uma **afirmação falsa** sobre a rede.

## O que **não** é gerado, e por quê

| Item | Motivo |
|---|---|
| `properties.securityRules[].id` | A página publica o **tipo** (`Resource ID.` como string) e **não afirma a forma** do id de uma regra. Compor o caminho aninhado seria inventar a forma — o nome está em `unverified` e o campo **não é emitido**. |
| ASG com valor | Nenhuma regra deste estado aponta para uma Application Security Group; os membros publicados (`id`/`location`) saem vazios dentro da lista, e não com um id inventado. |
| Formas **plurais** dos prefixos/portas | A Azure publica o par singular e o plural; o modelo guarda o singular (uma regra usa uma das duas), então os plurais saem vazios. Preenchê-los duplicaria o valor singular. |
| Regras de plataforma (`AllowVnetInBound`, `DenyAllInBound`, …) | A Azure cria seis por padrão, e a página de template **não publica** os seus nomes nem as suas prioridades. Gerar os literais seria inventar vocabulário. |
| `apiVersion` e `properties.flushConnection` | Registrados como não comprovados; `apiVersion` não é campo do corpo. |

## Onde está cada peça

| Peça | Arquivo |
|---|---|
| Contrato (fonte da verdade) | `specs/azure/arm-network-security-group-rules.schema.json` |
| Modelo | `tools/synthetic_clouds/model/network.py` (`NetworkSecurityGroup`, `SecurityRule`) |
| Postura | `tools/synthetic_clouds/generate/constants.py` (`NSG_SECURITY_RULES`) |
| Geração | `tools/synthetic_clouds/generate/estate_builder.py` (`_segment`, `_security_rules`) |
| Renderer | `tools/synthetic_clouds/render/azure_nsg_rules.py` |
| Teste golden | `tools/synthetic_clouds/tests/test_azure_nsg_rules_fidelity.py` |
| Gate | `tools/synthetic_clouds/validate/integrity.py` (vocabulário, prioridade única, presença de `Inbound`/`Allow`) |

## O que ainda falta — e é do outro lado

O `azure-sim` continua com `def project_network_security_groups(...): return []`, com o
docstring que registra a premissa antiga ("the estate models no network security group"). A
projeção passa a ser escrevível agora: o estado **tem** o NSG com as regras
(`NetworkSegment.network_security_group`), e `projections/arm.py` já mapeia o tipo
`"network_security_group"`. O docstring deve ser **substituído, não apagado em silêncio** — ele
registra uma decisão correta para o estado de então, e a mudança de premissa é a informação.

Pela regra inviolável nº 1 deste repositório, essa escrita é do time do FinOps, a partir da
<doc-de-lacunas>.md.
