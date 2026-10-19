# ec2-describe-security-groups

## 0. Qual superfície foi especificada, e por quê

**Especificamos a resposta da ação `DescribeSecurityGroups` da API Reference do Amazon EC2 — e, dentro dela, o objeto `SecurityGroup` e os cinco tipos de que uma regra é feita (`IpPermission`, `IpRange`, `Ipv6Range`, `PrefixListId`, `UserIdGroupPair`), mais `Tag`.**

Justificação, com evidência documental:

1. **Esta é a única superfície da AWS que publica a regra SUBCLASSO DE GRUPO DE SEGURANÇA.** Cada regra de entrada e de saída, com protocolo, faixa de portas e origem. As páginas de tipo enumeram cada membro com `Type` e `Required`. É essa documentação que permite preencher a coluna **Fonte** de cada linha com uma URL concreta.
   Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html

2. **A alternativa (`AWS::EC2::SecurityGroup` como configuration item do AWS Config) NÃO tem schema publicado.** A página *Supported Resource Types for AWS Config* lista o tipo e documenta apenas os seus **relacionamentos**, remetendo para o CloudFormation para as propriedades.
   Fonte: https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html

3. **E é exatamente a superfície de que as três regras gerenciadas de rede do AWS Config precisam.** `restricted-ssh`, `restricted-common-ports` e `vpc-default-security-group-closed` têm, todas, *Resource Types:* `AWS::EC2::SecurityGroup`, e as três leem regras de entrada — as duas primeiras — ou a ausência delas no grupo padrão — a terceira. Sem esta superfície, as três respondem `INSUFFICIENT_DATA` por falta do fato, e não por dúvida sobre a regra.

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | Amazon EC2 — ação `DescribeSecurityGroups`; objeto de resposta `SecurityGroup` |
| Documento oficial (ação) | *DescribeSecurityGroups* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| Documento oficial (objeto SecurityGroup) | *SecurityGroup* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| Documento oficial (objeto IpPermission) | *IpPermission* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| Documento oficial (objeto IpRange) | *IpRange* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpRange.html |
| Documento oficial (objeto Ipv6Range) | *Ipv6Range* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Ipv6Range.html |
| Documento oficial (objeto PrefixListId) | *PrefixListId* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_PrefixListId.html |
| Documento oficial (objeto UserIdGroupPair) | *UserIdGroupPair* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| Documento oficial (objeto Tag) | *Tag* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Tag.html |
| Documento oficial (semântica da regra) | *Security group rules* — https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html |
| Documento oficial (encoding da resposta) | *Query requests for Amazon EC2* — https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Documento oficial (o que é a API Reference) | *Welcome* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Welcome.html |
| Data de consulta | 2026-10-16 |
| Versão/schema de referência | EC2 API version **`2016-11-15`**. O namespace XML é `http://ec2.amazonaws.com/doc/2016-11-15/` |

## 2. Mecanismo e entrega

### 2.1 Isto NÃO é um export para um artefacto durável

`DescribeSecurityGroups` **não é um mecanismo de export** no sentido de "dado entregue a S3 ou equivalente". É uma API de leitura síncrona, paginada, que devolve o resultado na própria resposta HTTP. A AWS **não documenta** um export dela para S3 na API Reference de EC2.

Existe uma superfície **irmã e distinta**, `DescribeSecurityGroupRules`, que devolve cada regra como um objeto próprio (com `securityGroupRuleId`, `isEgress`, e a resolução da origem). O estado canônico **não a modela**, e ela não é emitida aqui: um security group e suas regras são a mesma unidade nesta especificação, e dividir o grupo das regras seria escolher a granularidade errada. Registado como follow-up, não como omissão silenciosa.

### 2.2 Encoding da resposta — o mesmo limite de `ec2-describe-instances`

O EC2 API Reference documenta **XML**, não JSON:

> *"This is the _Amazon EC2 API Reference_. It provides descriptions, API request parameters, and the **XML response** for each of the Amazon EC2 Query API actions."*
> — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Welcome.html

**Nenhum schema JSON é publicado para esta ação.** O artefacto entregue é JSON, com os nomes de propriedade do mapeamento Query/SDK. É a mesma divergência declarada em `ec2-describe-instances`, e pelo mesmo motivo: o Reference do EC2 publica o nome do membro na forma XML/Query, e o JSON é derivado do mesmo contrato, não de outra fonte.

### 2.3 Exemplo oficial de resposta (XML)

A Sample Response da acção é XML. O exemplo **Example 4** é o que importa aqui, porque é o que documenta o **grupo padrão** de uma VPC:

```xml
<DescribeSecurityGroupsResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>59dbff89-35bd-4eac-99ed-be587EXAMPLE</requestId>
    <securityGroupInfo>
        <item>
            <groupDescription>default VPC security group</groupDescription>
            <groupName>default</groupName>
            <groupId>sg-a33cbfda</groupId>
            <ownerId>111122223333</ownerId>
            <vpcId>vpc-a33cbfda</vpcId>
            <ipPermissions>
                <item>
                    <ipProtocol>tcp</ipProtocol>
                    <fromPort>80</fromPort>
                    <toPort>80</toPort>
                    <groups/>
                    <ipRanges>
                        <item><cidrIp>0.0.0.0/0</cidrIp></item>
                    </ipRanges>
                    <ipv6Ranges/>
                </item>
            </ipPermissions>
            <ipPermissionsEgress>
                <item>
                    <ipProtocol>-1</ipProtocol>
                    <ipRanges>
                        <item><cidrIp>0.0.0.0/0</cidrIp></item>
                    </ipRanges>
                    <ipv6Ranges/>
                    <groups/>
                    <prefixListIds/>
                </item>
            </ipPermissionsEgress>
        </item>
    </securityGroupInfo>
</DescribeSecurityGroupsResponse>
```

Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html

Duas leituras deste exemplo que a leitura apressada perde:

1. **`<groupName>default</groupName>` + `<groupDescription>default VPC security group</groupDescription>`** é como o grupo **padrão** de uma VPC se identifica. É o grupo que `vpc-default-security-group-closed` avalia.
2. **A regra de egress padrão não tem `fromPort` nem `toPort`.** É a regra `<ipProtocol>-1</ipProtocol>` do guia *"When you first create a security group, it has an outbound rule that allows all outbound traffic from the resource"*. As portas estão ausentes, não a zero. Ver secção 5.

## 3. Campos

Nove conjuntos, **40 colunas**. Todos os membros das páginas de tipo são `Required: No`; o único marcado obrigatório aqui é `requestId`, presente em toda resposta de sucesso documentada — o mesmo tratamento dado em `ec2-describe-instances`.

### 3.1 Elementos de topo da resposta de `DescribeSecurityGroups`

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `nextToken` | string | não | O token a incluir numa outra requisição para obter a próxima página de itens. *"This value is `null` when there are no more items to return."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `requestId` | string | sim (na resposta) | O ID da requisição | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `securityGroupInfo` | array | não | Os security groups | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |

### 3.2 Objeto `SecurityGroup` — os nove membros

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `groupDescription` | string | não | Uma descrição do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `groupId` | string | não | O ID do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `groupName` | string | não | O nome do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `IpPermissions.N` | Array de `IpPermission` | não | As regras de **entrada** associadas ao security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `IpPermissionsEgress.N` | Array de `IpPermission` | não | As regras de **saída** associadas ao security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `ownerId` | string | não | O ID da conta AWS dona do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `securityGroupArn` | string | não | O ARN do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `TagSet.N` | Array de `Tag` | não | Quaisquer tags atribuídas ao security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |
| `vpcId` | string | não | O ID da VPC do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_SecurityGroup.html |

### 3.3 Objeto `IpPermission` — os sete membros

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `fromPort` | Integer | não | Para TCP/UDP: o início da faixa de portas. Para ICMP/ICMPv6: o **tipo** ICMP, ou `-1` para todos os tipos | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `Groups.N` | Array de `UserIdGroupPair` | não | Os pares security group e ID de conta AWS | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `ipProtocol` | String | não | O nome do protocolo IP (`tcp`, `udp`, `icmp`, `icmpv6`) **ou o número** dele. `-1` = todos os protocolos | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `IpRanges.N` | Array de `IpRange` | não | As faixas de endereço IPv4 | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `Ipv6Ranges.N` | Array de `Ipv6Range` | não | As faixas de endereço IPv6 | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `PrefixListIds.N` | Array de `PrefixListId` | não | Os IDs de prefix list | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |
| `toPort` | Integer | não | Para TCP/UDP: o fim da faixa de portas. Para ICMP/ICMPv6: o **código** ICMP, ou `-1` para todos os códigos | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpPermission.html |

### 3.4 Objetos `IpRange`, `Ipv6Range` e `PrefixListId`

| Conjunto | Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|---|
| `ip-range` | `cidrIp` | string | não | A faixa IPv4. `/32` para um endereço único. **Canonicalizada pela AWS** | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpRange.html |
| `ip-range` | `description` | string | não | Descrição da regra que referencia esta faixa. Até 255 caracteres | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_IpRange.html |
| `ipv6-range` | `cidrIpv6` | string | não | A faixa IPv6. `/128` para um endereço único | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Ipv6Range.html |
| `ipv6-range` | `description` | string | não | Descrição da regra que referencia esta faixa. Até 255 caracteres | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Ipv6Range.html |
| `prefix-list-id` | `prefixListId` | string | não | O ID do prefixo | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_PrefixListId.html |
| `prefix-list-id` | `description` | string | não | Descrição da regra que referencia esta prefix list. Até 255 caracteres | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_PrefixListId.html |

### 3.5 Objeto `UserIdGroupPair` — os sete membros documentados

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `description` | string | não | Descrição do security group de origem ou de destino | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `groupId` | string | não | O ID do security group | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `groupName` | string | não | O nome do security group de destino | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `peeringStatus` | string | não | `pending` = peering pendente de aprovação; `active` = conexão ativa | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `userId` | string | não | O ID da conta AWS de destino do security group de origem | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `vpcId` | string | não | O ID da VPC de destino | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |
| `vpcPeeringConnectionId` | string | não | O ID da conexão de peering de VPC | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_UserIdGroupPair.html |

### 3.6 Objeto `Tag` — os dois membros

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `key` | string | não | A chave da tag. Até 127 caracteres Unicode. **Não pode começar com `aws:`** | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Tag.html |
| `value` | string | não | O valor da tag. Até 256 caracteres Unicode | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Tag.html |

### 3.7 Parâmetros de requisição documentados

| Campo | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `DryRun` | Boolean | não | Verifica as permissões sem executar a alteração | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `Filter.N` | Array de `Filter` | não | Os filtros. Os membros de `Filter` **não** são modelados: nenhum filtro foi capturado | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `GroupId.N` | Array de strings | não | Os IDs dos security groups | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `GroupName.N` | Array de strings | não | Os nomes dos security groups | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `MaxResults` | Integer | não | O máximo de resultados numa chamada | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |
| `NextToken` | string | não | O identificador da requisição anterior | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeSecurityGroups.html |

## 4. Campos não comprovados

| Item | Motivo |
|---|---|
| `securityGroupRuleId` | A Sample Response oficial traz `<securityGroupRuleId>sgr-abcdefghi01234560</securityGroupRuleId>` dentro de `<groups>`, mas a página de `UserIdGroupPair` publica sete membros e esse **não** é um deles. Exemplo ≠ contrato de tipo: o nome fica **proibido** no artefacto (`forbidden_names`). |
| Nomes de propriedade JSON | Só o XML é documentado; nenhuma lista de propriedades JSON nem exemplo JSON é publicado. Mesmo limite de `ec2-describe-instances`. |
| Enumeração fechada de `ipProtocol` | A página exemplifica `tcp`/`udp`/`icmp`/`icmpv6`, aceita um **número** de protocolo e `-1`, mas não publica lista fechada. O domínio é **nome-ou-número-ou-`-1`**; um conjunto fechado seria afirmação que a documentação não faz. |
| Vínculo VPC ↔ security group do estate | A API publica `vpcId`, mas o modelo canónico não carrega a relação: os recursos `vpc` e `security_group` do estate vivem em regiões diferentes e nenhum par (conta, região) tem os dois. Ver secção 5. |

## 5. Divergências conhecidas

**1. A regra da AWS é ALLOW-ONLY, e o modelo não tem decisão.** O guia é explícito:

> *"You can specify allow rules, but not deny rules."*
> — https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html

O bloqueio é a **ausência** de regra. É por isso que `model/network.py` não reutiliza a `SecurityRule` da Azure para isto: aquela tem `access` (`allowed`/`denied`), e um SG da AWS **não tem** members de decisão para os quais apontar. O mesmo vale para o NSG da Azure, que também tem `priority` 100..4096 com o menor número a vencer — `IpPermission` não publica nada que ordene ou precedencie regras, e todas as regras de um grupo são igualmente aplicadas.

**2. `fromPort`/`toPort` são condicionais, e `-1` não os tem.** A página diz, do protocolo:

> *"Use `-1` to specify all protocols. When authorizing security group rules, specifying `-1` or a protocol number other than `tcp`, `udp`, `icmp`, or `icmpv6` allows traffic on all ports, regardless of any port range you specify."*

E a Sample Response confirma na prática: a regra de egress padrão do grupo vem `<ipProtocol>-1</ipProtocol>` **sem** `fromPort` nem `toPort`. No modelo, portas ausentes são `None` — nunca `0`, que seria um valor que a API não devolve.

**3. Para ICMP, as portas são tipo e código, não portas.**

> *"For ICMP, the ICMP type and code. For example, use type 8 for ICMP Echo Request or type 128 for ICMPv6 Echo Request."*
> — https://docs.aws.amazon.com/vpc/latest/userguide/security-group-rules.html

Os mesmos dois campos, com outro significado. É um motivo a mais para não os converter para um intervalo de portas canónico.

**4. A origem é uma LISTA, não um par de campos.** `IpPermission` tem um conjunto de origens possíveis — `IpRanges` **ou** `Ipv6Ranges` **ou** `Groups` **ou** `PrefixListIds` — e a página de `IpRange` fecha a exclusividade:

> *"You can either specify a CIDR block or a source security group, not both."*

O NSG da Azure tem prefixo de origem **e** de destino e faixa de porta de origem **e** de destino: quatro campos. Achatar a regra da AWS nesses quatro seria fabricar metade da estrutura.

**5. A direção é o NOME DA LISTA, não um membro.** Não existe `direction` em `IpPermission`. A direção é o que distingue `IpPermissions` de `IpPermissionsEgress`. Guardá-la dentro da regra seria duplicar o que o nome da propriedade já afirma.

**6. A AWS canoniza CIDR, e este estado já nasce canónico.**

> *"AWS canonicalizes IPv4 and IPv6 CIDRs. For example, if you specify `100.68.0.18/18`, AWS canonicalizes the CIDR block to `100.68.0.0/18`."*

Um cadastro posterior da forma não canónica é erro de duplicata na API. Todo CIDR gerado aqui já está na forma que a API devolveria.

**7. `vpcId` é uma derivação declarada, e esta é a pendência real desta superfície.** A API publica `vpcId` em `SecurityGroup`, e o estado escreve um valor lá. De onde vem:

- os recursos `vpc` do estate vivem todos em `sa-east-1`;
- os recursos `security_group` vivem todos em `us-east-1`;
- **nenhum par (conta, região) tem os dois**, e os ids `sg-…` dos recursos e dos segmentos não se cruzam em nenhum caso.

O que existe é o **segmento de rede**: um `NetworkSegment` por (conta, região), cujo `segment_id` já é o id nativo `vpc-…`. A associação é, portanto, a função do próprio agrupamento do modelo — uma VPC por conta e região — e não uma escolha sobre a semântica do provedor. Fica registado como `TODO-verificar` no renderer: a verificação pendente é a relação VPC↔SG de uma conta real, e ela só se resolve quando o modelo passar a carregar essa relação. Sem o segmento, a construção **falha** em vez de escrever um `vpcId` vazio — um grupo sem VPC faria `vpc-default-security-group-closed` responder sobre uma VPC que não existe.