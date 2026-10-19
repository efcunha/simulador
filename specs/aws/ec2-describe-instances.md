# ec2-describe-instances

## 0. Qual superfície foi especificada, e por quê

**Especificamos a resposta da ação `DescribeInstances` da API Reference do Amazon EC2 — e, dentro dela, o objeto `Instance`.**

Justificação, com evidência documental:

1. **A API Reference publica uma lista campo-a-campo exaustiva do objeto `Instance`.** A página *Instance* enumera cada membro com `Type`, `Required` e `Valid Values`. É essa a documentação que permite preencher a coluna **Fonte** de cada linha com uma URL concreta.
   Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html

2. **A alternativa (`AWS::EC2::Instance` como configuration item do AWS Config) NÃO tem schema publicado.** A página *Supported Resource Types for AWS Config* lista `AWS::EC2::Instance` e documenta apenas os seus **relacionamentos** (*contains* EC2 network interface; *is associated with* EC2 security group; *is attached to* Amazon EBS volume e EC2 Elastic IP (EIP); *is contained in* EC2 Dedicated host, Route table, Subnet, Virtual private cloud (VPC)). Para os campos, a própria página redireciona explicitamente:
   > *"For more detailed information about a resource type, see its reference information (such as syntax, properties and return values) in the [AWS resource and property types reference] in the AWS CloudFormation User Guide."*
   Fonte: https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html

   Ou seja: **o AWS Config não publica um schema de propriedades por tipo de recurso.** O que publica é um ponteiro para a documentação do CloudFormation, que usa a sua própria grafia de propriedades (PascalCase, `AWS::EC2::Instance`), não a grafia do configuration item do Config. Escolher o CI do Config significaria inventar nomes de campo do objeto `configuration` — exatamente a falha que este trabalho tem de evitar.

3. **Consequência para o simulador, e a divergência que isto implica:** a forma do objeto `configuration` do CI `AWS::EC2::Instance` no S3 **não está documentada pelo AWS Config campo a campo**. O exemplo oficial de snapshot do AWS Config mostra um CI `AWS::EC2::Instance` (ver `aws-config-snapshot-s3.md`, secção 5), mas o Config afirma que esse objeto é *"Information returned through a call to the Describe or List API of the resource"* — ou seja, são os campos de `DescribeInstances`. Por isso esta spec é a base correta para ambos, e está registada como divergência na secção 5.

## 1. Identificação

| Item | Valor |
|---|---|
| Nome oficial da superfície | Amazon EC2 — ação `DescribeInstances`; objeto de resposta `Instance` (dentro de `Reservation`) |
| Documento oficial (ação) | *DescribeInstances* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| Documento oficial (objeto Instance) | *Instance* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| Documento oficial (objeto Reservation) | *Reservation* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |
| Documento oficial (encoding da resposta) | *Query requests for Amazon EC2* — https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Documento oficial (o que é a API Reference) | *Welcome* — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Welcome.html |
| Documento oficial (relacionamentos do resource type) | *Supported Resource Types for AWS Config* — https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html |
| Data de consulta | 2026-10-14 |
| Versão/schema de referência | EC2 API version **`2016-11-15`**. Verificado: *"For the Amazon EC2 API, the version is 2016-11-15."* (https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html). O namespace XML é `http://ec2.amazonaws.com/doc/2016-11-15/` |

## 2. Mecanismo e entrega

### 2.1 Isto NÃO é um export para um artefacto durável

**Achado importante, e diferente das outras três superfícies.** `DescribeInstances` **não é um mecanismo de export** no sentido de "dado entregue a S3 ou equivalente". É uma API de leitura síncrona, paginada, que devolve o resultado na própria resposta HTTP. A AWS **não documenta** um export de `DescribeInstances` para S3 na API Reference de EC2.

O que existe, e que é o único caminho documentado para materializar isto num artefacto durável, é **encadeado pelo cliente**:

| Caminho | Documentado? | Natureza |
|---|---|---|
| `DescribeInstances` → resposta HTTP | Sim | API de leitura. Sem entrega a artefacto |
| `DescribeInstances` → AWS Config CI → S3 | Parcialmente | O Config grava CIs de `AWS::EC2::Instance` (ver `aws-config-snapshot-s3.md`) e o objeto `configuration` corresponde grosso modo à resposta de `DescribeInstances`. **Mas o mapeamento campo-a-campo não é publicado pelo AWS Config** |
| `DescribeInstances` → S3 direto | **Não** | Não documentado |

Um simulador que queira "EC2 instances em S3" tem, portanto, de **escolher explicitamente** entre (a) emitir a resposta `DescribeInstances` como artefacto JSON/XML próprio, ou (b) emitir um CI `AWS::EC2::Instance` dentro do snapshot do AWS Config. Esta spec fornece os campos para ambos os casos, porque são os mesmos campos. Documentamos o mecanismo como **API de leitura**, não como export — ver secção 4.

### 2.2 Encoding da resposta — o ponto mais delicado desta superfície

Esta é a razão pela qual a superfície é perigosa para um simulador. A API Reference de EC2 documenta **XML**, não JSON:

> *"This is the _Amazon EC2 API Reference_. It provides descriptions, API request parameters, and the **XML response** for each of the Amazon EC2 Query API actions."*
> — https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Welcome.html

> *"In response to a Query request, the service returns an **XML data structure** that conforms to an XML schema defined for Amazon EC2."*
> — https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html

Consequências documentadas:

| Propriedade | Valor documentado | Fonte |
|---|---|---|
| Forma canônica documentada | XML | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Ação e versão | Query API, `Action=DescribeInstances`, versão `2016-11-15` | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Envelope de containers | *"Examples of containers include `groupSet` for security groups and `keySet` for key pairs… Item elements are children of containers"* | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Elemento de item | `<item>` | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html (Sample Response) |
| `requestId` | *"Every successful response includes a request ID in a `requestId` element, and every unsuccessful response includes a request ID in a `RequestID` element."* | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Ordem dos elementos | *"The order of the elements in the response, including those within nested structures, might vary. Applications should not assume that the elements appear in a particular order."* | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Indentação / new lines | *"As of July 31 2025, the XML data structures in the responses will no longer include new lines and indentations."* | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Paginação | `MaxResults`, `NextToken` (entrada), `nextToken` (saída). Continuar até `nextToken` ser nulo | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Combinação inválida | *"If you call a describe API action with both a list of IDs and `MaxResults`, the request fails with the error `InvalidParameterCombination`."* | https://docs.aws.amazon.com/ec2/latest/devguide/Query-Requests.html |
| Recomendação | *"We strongly recommend using only paginated requests. Unpaginated requests are susceptible to throttling and timeouts."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| Consistência | *"The Amazon EC2 API follows an eventual consistency model."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| Instâncias terminadas | *"Recently terminated instances might appear in the returned results. This interval is usually less than one hour."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |

**Nenhum schema JSON é publicado para esta ação.** A API Reference não publica um exemplo JSON de `DescribeInstances`, nem nomes de propriedade JSON. Um simulador que emita JSON **está a emitir um formato específico de um SDK ou do protocolo `ec2` JSON mais recente, que esta documentação não cobre** — ver secção 4 e secção 5.

### 2.3 Exemplo oficial de resposta (XML)

O único Sample Response oficial de `DescribeInstances` é XML. Fragmento literal:

```xml
<DescribeInstancesResponse xmlns="http://ec2.amazonaws.com/doc/2016-11-15/">
    <requestId>8f7724cf-496f-496e-8fe3-example</requestId>
    <reservationSet>
        <item>
            <reservationId>r-1234567890abcdef0</reservationId>
            <ownerId>123456789012</ownerId>
            <groupSet/>
            <instancesSet>
                <item>
                    <instanceId>i-1234567890abcdef0</instanceId>
                    <imageId>ami-bff32ccc</imageId>
                    <instanceState><code>16</code><name>running</name></instanceState>
                    ...
```

Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html

**Nota de fidelidade:** este exemplo oficial emite `<blockDeviceMapping>` (sem `Set`), enquanto a página do objeto `Instance` documenta o membro como `BlockDeviceMapping.N` e o exemplo do AWS Config usa `blockDeviceMappings`. Três grafias para o mesmo campo em três documentos oficiais. Registado na secção 5.

## 3. Campos

### 3.1 Elementos de topo da resposta de `DescribeInstances`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `requestId` | string | sim (na resposta) | — | — | — | O ID da requisição | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `reservationSet` | array de objetos `Reservation` | não | — | — | — | Informação sobre as reservas | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `nextToken` | string | não | — | — | — | O token a incluir numa outra requisição para obter a próxima página de itens. *"This value is `null` when there are no more items to return."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |

### 3.2 Objeto `Reservation`

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `reservationId` | string | não | — | — | — | O ID da reserva | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |
| `ownerId` | string | não | — | — | — | O ID da conta AWS dona da reserva | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |
| `requesterId` | string | não | — | — | — | O ID do requisitante que lançou as instâncias em seu nome (ex.: AWS Management Console ou Auto Scaling) | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |
| `GroupSet.N` | array de objetos `GroupIdentifier` | não | — | — | — | **Não suportado.** *"Not supported."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |
| `InstancesSet.N` | array de objetos `Instance` | não | — | — | — | As instâncias | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html |

### 3.3 Objeto `Instance` — inventário completo

Todos os membros publicados na página oficial do objeto `Instance`, com o `Type`, o `Required` e os `Valid Values` exatamente como publicados. Data de consulta de todas as linhas: **2026-10-14**. Fonte de todas as linhas: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html (o URL é repetido em `schema.json`).

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `amiLaunchIndex` | Integer | não | — | — | — | O índice de lançamento da AMI, que pode ser usado para encontrar esta instância no grupo de lançamento | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `architecture` | String | não | — | — | `i386` \| `x86_64` \| `arm64` \| `x86_64_mac` \| `arm64_mac` | A arquitetura da imagem | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `BlockDeviceMapping.N` | Array de objetos `InstanceBlockDeviceMapping` | não | — | — | — | Quaisquer entradas de mapeamento de dispositivos de bloco para a instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `bootMode` | String | não | — | — | `legacy-bios` \| `uefi` \| `uefi-preferred` | O modo de boot especificado pela AMI. Se o valor for `uefi-preferred`, a AMI suporta UEFI e Legacy BIOS | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `capacityBlockId` | String | não | — | — | — | O ID do Capacity Block. Para instâncias P5 refere-se a um grupo de instâncias; para Trn2u, a um EC2 UltraServer | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `capacityReservationId` | String | não | — | — | — | O ID da Capacity Reservation | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `capacityReservationSpecification` | objeto `CapacityReservationSpecificationResponse` | não | — | — | — | Informação sobre a opção de direcionamento da Capacity Reservation | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `clientToken` | String | não | — | — | — | O token de idempotência fornecido no lançamento da instância, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `cpuOptions` | objeto `CpuOptions` | não | — | — | — | As opções de CPU para a instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `currentInstanceBootMode` | String | não | — | — | `legacy-bios` \| `uefi` | O modo de boot usado para iniciar a instância no lançamento ou arranque | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `dnsName` | String | não | — | — | — | O nome DNS público atribuído à instância. Não disponível até a instância entrar no estado `running`; só disponível se os DNS hostnames estiverem habilitados na VPC | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ebsOptimized` | Boolean | não | — | — | — | Indica se a instância está otimizada para I/O do Amazon EBS | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ElasticGpuAssociationSet.N` | Array de objetos `ElasticGpuAssociation` | não | — | — | — | **Deprecated.** *"Amazon Elastic Graphics reached end of life on January 8, 2024."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ElasticInferenceAcceleratorAssociationSet.N` | Array de objetos `ElasticInferenceAcceleratorAssociation` | não | — | — | — | **Deprecated.** *"Amazon Elastic Inference is no longer available."* | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `enaSupport` | Boolean | não | — | — | — | Especifica se o enhanced networking com ENA está habilitado | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `enclaveOptions` | objeto `EnclaveOptions` | não | — | — | — | Indica se a instância está habilitada para AWS Nitro Enclaves | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `GroupSet.N` | Array de objetos `GroupIdentifier` | não | — | — | — | Os security groups da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `hibernationOptions` | objeto `HibernationOptions` | não | — | — | — | Indica se a instância está habilitada para hibernação | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `hypervisor` | String | não | — | — | `ovm` \| `xen` | O tipo de hypervisor da instância. O valor `xen` é usado tanto para Xen quanto para Nitro | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `iamInstanceProfile` | objeto `IamInstanceProfile` | não | — | — | — | O perfil de instância IAM associado à instância, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `imageId` | String | não | — | — | — | O ID da AMI usada para lançar a instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `instanceId` | String | não | — | — | — | O ID da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `instanceLifecycle` | String | não | — | — | `spot` \| `scheduled` \| `capacity-block` \| `interruptible-capacity-reservation` | Indica se é uma Spot Instance ou uma Scheduled Instance | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `instanceState` | objeto `InstanceState` | não | — | — | — | O estado atual da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `instanceType` | String | não | — | — | Lista muito extensa de tipos (ex.: `t2.micro`, `m5.large`, `c7g.metal`, `p5.48xlarge`) | O tipo da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ipAddress` | String | não | — | — | — | O endereço IPv4 público, ou o Carrier IP atribuído à instância, se aplicável. Carrier IP só se aplica a instâncias lançadas numa subnet associada a uma Wavelength Zone | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ipv6Address` | String | não | — | — | — | O endereço IPv6 atribuído à instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `kernelId` | String | não | — | — | — | O kernel associado a esta instância, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `keyName` | String | não | — | — | — | O nome do key pair, se a instância foi lançada com um key pair associado | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `launchTime` | Timestamp | não | — | ISO 8601 UTC, ex.: `2018-05-08T16:46:19.000Z` | — | O horário em que a instância foi lançada pela última vez. Para o primeiro lançamento, ver o attachment time da interface de rede primária | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `LicenseSet.N` | Array de objetos `LicenseConfiguration` | não | — | — | — | As configurações de licença da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `maintenanceOptions` | objeto `InstanceMaintenanceOptions` | não | — | — | — | Informação sobre as opções de recuperação e manutenção da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `metadataOptions` | objeto `InstanceMetadataOptionsResponse` | não | — | — | — | As opções de metadados da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `monitoring` | objeto `Monitoring` | não | — | — | — | O monitoramento da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `NetworkInterfaceSet.N` | Array de objetos `InstanceNetworkInterface` | não | — | — | — | As interfaces de rede da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `networkPerformanceOptions` | objeto `InstanceNetworkPerformanceOptions` | não | — | — | — | Contém configurações para as opções de desempenho de rede da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `operator` | objeto `OperatorResponse` | não | — | — | — | O provedor de serviço que gerencia a instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `outpostArn` | String | não | — | — | — | O ARN do Outpost | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `placement` | objeto `Placement` | não | — | — | — | O local onde a instância foi lançada, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `platform` | String | não | — | — | `windows` | A plataforma. O valor é `windows` para instâncias Windows; caso contrário é vazio | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `platformDetails` | String | não | — | — | — | O valor de detalhes da plataforma da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `privateDnsName` | String | não | — | — | — | **[IPv4 apenas]** O nome de host DNS privado atribuído à instância. Só pode ser usado dentro da rede do Amazon EC2; não disponível até a instância entrar no estado `running` | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `privateDnsNameOptions` | objeto `PrivateDnsNameOptionsResponse` | não | — | — | — | As opções para o hostname da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `privateIpAddress` | String | não | — | — | — | O endereço IPv4 privado atribuído à instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ProductCodes.N` | Array de objetos `ProductCode` | não | — | — | — | Os product codes anexados a esta instância, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `ramdiskId` | String | não | — | — | — | O RAM disk associado a esta instância, se aplicável | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `reason` | String | não | — | — | — | O motivo da transição de estado mais recente. Pode ser uma string vazia | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `rootDeviceName` | String | não | — | — | — | O nome do dispositivo do volume do dispositivo raiz (ex.: `/dev/sda1`) | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `rootDeviceType` | String | não | — | — | `ebs` \| `instance-store` | O tipo de dispositivo raiz usado pela AMI | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `SecondaryInterfaceSet.N` | Array de objetos `InstanceSecondaryInterface` | não | — | — | — | As interfaces secundárias da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `sourceDestCheck` | Boolean | não | — | — | — | Indica se a verificação de origem/destino está habilitada | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `spotInstanceRequestId` | String | não | — | — | — | Se a requisição é uma requisição de Spot Instance, o ID da requisição | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `sriovNetSupport` | String | não | — | — | — | Especifica se o enhanced networking com a interface Intel 82599 Virtual Function está habilitado | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `stateReason` | objeto `StateReason` | não | — | — | — | O motivo da transição de estado mais recente | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `subnetId` | String | não | — | — | — | O ID da subnet na qual a instância está a correr | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `TagSet.N` | Array de objetos `Tag` | não | — | — | — | Quaisquer tags atribuídas à instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `tpmSupport` | String | não | — | — | `v2.0` | Se a instância está configurada para suporte NitroTPM, o valor é `v2.0` | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `usageOperation` | String | não | — | — | — | O valor de operação de uso da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `usageOperationUpdateTime` | Timestamp | não | — | ISO 8601 UTC, ex.: `2022-09-15T17:15:20.000Z` | — | O horário em que a operação de uso foi atualizada pela última vez | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `virtualizationType` | String | não | — | — | `hvm` \| `paravirtual` | O tipo de virtualização da instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |
| `vpcId` | String | não | — | — | — | O ID da VPC na qual a instância está a correr | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html |

**Total: 61 membros do objeto `Instance`** (dos quais **2 deprecated**: `ElasticGpuAssociationSet.N` e `ElasticInferenceAcceleratorAssociationSet.N`).

Mais: **3** elementos de topo da resposta + **5** membros de `Reservation` = **69 campos** nesta spec.

### 3.4 Parâmetros de requisição documentados

| Parâmetro | Tipo | Obrigatório | Descrição | Fonte |
|---|---|---|---|---|
| `DryRun` | Boolean | não | Verifica permissões sem fazer a requisição | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `Filter.N` | Array de objetos `Filter` | não | Os filtros. A página publica uma lista extensa de nomes de filtro documentados | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `IncludeManagedResources` | Boolean | não | Se `true`, a saída inclui recursos geridos por serviços AWS, mesmo que a visibilidade esteja definida como oculta | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `InstanceId.N` | Array de strings | não | Os IDs das instâncias. Default: descreve todas as instâncias | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `MaxResults` | Integer | não | O número máximo de itens a devolver. Não pode ser especificado em conjunto com o parâmetro de IDs de instância | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |
| `NextToken` | String | não | O token devolvido por uma requisição paginada anterior | https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html |

## 4. Campos não comprovados

| Item | Status | Motivo |
|---|---|---|
| Schema/nomes de propriedade JSON da resposta de `DescribeInstances` | **UNVERIFIED** | A documentação oficial publica **apenas XML** para esta ação. Não existe exemplo JSON nem lista de nomes JSON na API Reference. Qualquer JSON emitido seria a representação de um SDK específico, não um formato documentado pela AWS |
| Grafia exata dos wrappers de container no XML | **UNVERIFIED como regra geral** | A API Reference usa `BlockDeviceMapping.N`, `GroupSet.N`, `NetworkInterfaceSet.N`, `TagSet.N`, `ProductCodes.N`, `LicenseSet.N`, `SecondaryInterfaceSet.N`, `ElasticGpuAssociationSet.N`, `ElasticInferenceAcceleratorAssociationSet.N`; o Sample Response oficial usa `<blockDeviceMapping>`, `<groupSet>`, `<networkInterfaceSet>`, `<tagSet>`, `<productCodes>`, `<blockDeviceMappings>` (no exemplo do AWS Config). Não existe regra publicada de conversão para o nome do elemento XML |
| Formato do `az-id` | **UNVERIFIED** | O filtro `availability-zone-id` existe, mas o padrão do identificador não é publicado |
| `Valid Values` de `platformDetails` | **UNVERIFIED nesta spec** | A página do objeto `Instance` não publica a lista; a lista existe na página do filtro `platform-details` de `DescribeInstances`, que é uma lista de **filtros**, não de valores de retorno. Não transportamos a lista de filtros para valores de campo |
| Schema do objeto `configuration` do CI `AWS::EC2::Instance` | **UNVERIFIED** | O AWS Config não publica schemas de propriedades por tipo de recurso; redireciona para o CloudFormation. Ver secção 0 |
| Mapeamento campo-a-campo entre `Instance` e o `configuration` do CI | **UNVERIFIED** | O AWS Config afirma apenas que o `configuration` é *"Information returned through a call to the Describe or List API"* |
| Mecanismo de export de `DescribeInstances` para um artefacto durável | **UNVERIFIED (evidência negativa)** | Não documentado. `DescribeInstances` é uma API de leitura |
| `publicDnsName` / `publicIpAddress` como nomes de retorno | **UNVERIFIED** | A página do objeto `Instance` usa `dnsName` e `ipAddress`. O exemplo de CI `AWS::EC2::Instance` do AWS Config usa `publicDnsName` e `publicIpAddress`. Nenhum documento publica `publicDnsName`/`publicIpAddress` como membros do objeto `Instance` |

## 5. Divergências conhecidas

1. **XML é o único formato documentado, mas o objeto é documentado em notação de SDK.** A API Reference afirma *"the XML response for each of the Amazon EC2 Query API actions"*, e o único Sample Response é XML. No entanto, os membros do objeto `Instance` são publicados em notação de SDK (`imageId`, `amiLaunchIndex`, `instanceId` — camelCase com inicial minúscula), que **não é** a notação dos elementos XML do exemplo (`<instanceId>`, `<amiLaunchIndex>` coincidem por acaso para estes, mas `<reservationSet>` vs. membro `InstancesSet.N`, e `<blockDeviceMapping>` vs. membro `BlockDeviceMapping.N`, divergem). Registamos as três notações sem escolher. Fontes: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/Welcome.html e https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html

2. **`blockDeviceMapping` vs. `BlockDeviceMapping.N` vs. `blockDeviceMappings`.** Três documentos oficiais, três grafias: o Sample Response de `DescribeInstances` usa `<blockDeviceMapping>`; a página do objeto `Instance` documenta `BlockDeviceMapping.N`; o exemplo de CI `AWS::EC2::Instance` do AWS Config usa `"blockDeviceMappings"`. Fontes: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html, https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html e https://docs.aws.amazon.com/config/latest/developerguide/example-s3-snapshot.html

3. **`instanceLifecycle` tem valores diferentes entre a API e o filtro.** A página do objeto `Instance` publica `spot | scheduled | capacity-block | interruptible-capacity-reservation`. O filtro `instance-lifecycle` de `DescribeInstances` publica apenas `spot | scheduled | capacity-block`. O campo de retorno tem um valor a mais que o filtro. Fontes: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html e https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_DescribeInstances.html

4. **`GroupSet.N` existe em `Instance` e em `Reservation`, com significados diferentes.** Em `Reservation`, *"Not supported."* Em `Instance`, *"The security groups for the instance."* O mesmo nome de membro, em dois níveis, com suporte diferente. Fontes: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Reservation.html e https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html

5. **`instanceType` publica uma lista de `Valid Values` que a própria AWS mantém incompleta.** A lista termina em `r8i.metal-96xl` e `r8i-flex.16xlarge`, mas omite tipos existentes. É uma lista em movimento; o simulador não deve tratar a lista como fechada. Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html

6. **`elasticGpuAssociationSet` e `elasticInferenceAcceleratorAssociationSet` estão deprecated mas continuam no schema.** Amazon Elastic Graphics terminou a 8 de janeiro de 2024; Amazon Elastic Inference já não está disponível. Os membros permanecem documentados. Fonte: https://docs.aws.amazon.com/AWSEC2/latest/APIReference/API_Instance.html

7. **O AWS Config não publica o schema do CI que corresponderia a esta superfície.** Para `AWS::EC2::Instance`, a página de tipos de recurso do Config publica apenas relacionamentos e redireciona para o CloudFormation. Portanto: **existe documentação dos campos da API EC2, mas não existe documentação dos campos do configuration item do EC2 no AWS Config.** Esta é a razão pela qual esta spec documenta a API. Fonte: https://docs.aws.amazon.com/config/latest/developerguide/resource-config-reference.html
