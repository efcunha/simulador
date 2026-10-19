# Postura de segurança no simulador — o domínio, o contrato e a ordem

> Idioma: **Português** | [English](POSTURA-SEGURANCA.en.md)

**Decisão de 2026-10-16: o simulador passa a representar postura de segurança, nas três nuvens.**

Por quê, com evidência: o FinOps varre a nuvem com 4 checks AWS próprios — **S3 público**,
**Security Groups**, **IAM sem MFA** e **AWS Config** — mais 2 GCP (SCC e firewall) e 2 Azure
(NSG e Defender). Medido no ambiente real em 2026-10-16 (30 contas AWS):

| Check | Findings abertos | % do backlog |
|---|---|---|
| AWS Config | 14.531 | **97,6%** |
| Network / Security Groups | 191 | 1,3% |
| S3 Storage | 165 | 1,1% |
| IAM / Identity | 2 | 0,01% |
| SCC e Firewall (GCP) | 0 | 0% |

E medido no **simulador**: **nenhum** dos quatro é produzível hoje. Não há superfície de bucket com
postura, nem de Security Group da AWS, nem de IAM; e `aws-config-snapshot-s3` é a API de
*snapshot*, não a de conformidade.

## Marco — o domínio de postura **fechado** (2026-10-19)

**Os 8 checks que os três `SecurityScanner` do FinOps rodam têm, cada um, a superfície do
simulador que os produz** — medido contra o consumidor real, não inferido. A série que fechou o
domínio vai de `9848e1e` H-01 a `0f7e174` H-09: **15 commits** — **9 de entrega** (feat),
**5 de limpeza** (docs) e **1 de correção** (fix). A contagem foi feita na época por
`git rev-list --count 9848e1e^..0f7e174`; hoje o comando não roda, porque os commits
foram perdidos no achatamento do histórico. A lista completa, com o que cada um
entregou, está em PROVENANCIA-HISTORICO.md §3.1.

| Provedor | Check do consumidor | Superfície do simulador | Commit |
|---|---|---|---|
| AWS | Config by-rule | `aws/config-describe-compliance-by-config-rule` | `9848e1e` H-01 |
| AWS | Security Groups | `aws/ec2-describe-security-groups` | `5169404` H-02 |
| AWS | S3 público | `aws/s3-list-buckets`, `aws/s3-get-bucket-acl`, `aws/s3-get-bucket-policy`, `aws/s3-get-public-access-block` | `c65faeb` H-03 |
| AWS | IAM sem MFA | `aws/iam-get-credential-report` | `d38b325` H-04 |
| AWS | resíduo de Config (3 regras de auditoria) | *(sem superfície nova — a mesma do Config by-rule)* | `a80bc1f` H-05 |
| GCP | SCC findings | `gcp/scc-findings`, `gcp/scc-sources` | `69b721d` H-06 |
| GCP | Firewall | `gcp/compute-firewalls` | `dead1b0` H-07 |
| Azure | NSG rules | `azure/arm-network-security-group-rules` | `85951d9` H-08 |
| Azure | Defender/Assessments | `azure/security-assessments-list` | `0f7e174` H-09 |

As seis limpezas da série, que não construíram superfície e por isso não entram na tabela:
`df272f4` H-10, `186237f` H-11, `c091409` H-12, `ed1f1d5` H-13, `927eb93` H-14 (docs) e `7974f46` H-15 (fix).

**Conformidade de Config medida** — rodando o renderer (`config_compliance_by_rule`, seed 123,
perfil `small`), 14 regras × 9 escopos = **126** itens:

```
COMPLIANT 45   NON_COMPLIANT 27   INSUFFICIENT_DATA 54   NOT_APPLICABLE 0
```

Os 54 `INSUFFICIENT_DATA` têm **uma** causa só — a ausência de recurso do tipo no escopo (o
colapso `NOT_APPLICABLE` que a API reporta como `INSUFFICIENT_DATA`) — e **zero** regra sem
fonte. A decomposição está em *Resíduo nomeado*, abaixo.

**Estado do repositório no marco:** `--matrix` → `gerado=45 falta=0 bloqueado=1 total=46`
(a bloqueada é `azure/cost-management-export-cost-details`, uma superfície de **custo** — não
entra no domínio de postura); `--ready` → `PRONTO: 45 superficies`, **0 coluna inventada** em
qualquer provedor; suíte → **1095 passed / 20 skipped**.

Os 3 achados de produto que esta série de medições expôs estão reunidos num ponto único em
[INGESTAO-D3-SEGURANCA.md](INGESTAO-D3-SEGURANCA.md#achados-para-o-time-do-consumidor) — seção
canônica, à qual os demais documentos apontam.

O histórico dos incrementos, um a um, está abaixo e **não muda** com este marco.

## A regra que governa todas as superfícies daqui

O simulador emite **o que o provedor publica**, no formato do provedor. Quem mapeia para a tabela
`findings` do FinOps é o writer, do lado de lá. Isso mantém a regra do projeto intacta — o nome
do campo vem da documentação oficial, o valor vem do estado, e o que a fonte não publica fica
declarado.

E há uma consequência boa, medida na API do próprio AWS Config: **`describe_compliance_by_config_rule`
agrega por REGRA, não por recurso.** A resposta traz uma linha por regra, com o número de recursos
que não complym em `Compliance.ComplianceContributorCount.CappedCount`. Ou seja, a superfície
natural tem ~150 linhas (o número de regras gerenciadas da AWS), e a expansão para os milhares de
findings por recurso é **do consumidor**. Isso elimina a dúvida de volume sem precisar decidir
nada: o simulador produz o agregado que a AWS publica, e o backlog de 14.531 é o produto contando
os recursos.

## Incremento 1 — AWS Config, `describe_compliance_by_config_rule` — **ENTREGUE em 2026-10-16**

Superfície `aws/config-describe-compliance-by-config-rule`, renderer
`config_compliance_by_rule`, spec `specs/aws/config-describe-compliance-by-config-rule.schema.json`.
Contrato lido em 2026-10-16 nas quatro páginas do API Reference (a ação e as três formas que ela
devolve), mais a lista oficial de regras gerenciadas.

### Requisição

| Parâmetro | Tipo | Restrição publicada |
|---|---|---|
| `ComplianceTypes` | array de strings | 0 a 3 itens. **Valid Values: `COMPLIANT \| NON_COMPLIANT \| NOT_APPLICABLE \| INSUFFICIENT_DATA`** |
| `ConfigRuleNames` | array de strings | 0 a 25 itens; comprimento 1 a 128; **Pattern `[A-Za-z0-9_-]+`** |
| `NextToken` | string | paginação |

### Resposta

`ComplianceByConfigRules`: array de `ComplianceByConfigRule`

| Membro | Tipo | Restrição publicada |
|---|---|---|
| `Compliance.ComplianceType` | string | `COMPLIANT \| NON_COMPLIANT \| NOT_APPLICABLE \| INSUFFICIENT_DATA` |
| `Compliance.ComplianceContributorCount.CapExceeded` | boolean | "se o máximo foi atingido" — **o máximo não é publicado** |
| `Compliance.ComplianceContributorCount.CappedCount` | **Integer** | número de recursos que **causam** `NON_COMPLIANT` |
| `ConfigRuleName` | string | comprimento 1 a 64 |

A semântica está escrita na própria fonte: *"A rule is compliant if all of the resources that the
rule evaluated comply with it. A rule is noncompliant if any of these resources do not comply."*

`INSUFFICIENT_DATA` tem significado próprio, e a AWS explica os três casos — regra nunca
avaliada, Lambda sem `config:PutEvaluations`, ou todos os recursos `NOT_APPLICABLE`. **Esse valor não
é sinônimo de "não avaliado"**, e o simulador tem de reproduzir a distinção ou o consumidor vai ler
um estado que não existe.

### Duas armadilhas do contrato, que a leitura apressada erra

**1. `NOT_APPLICABLE` aparece no enum e não é suportado.** A linha de Valid Values acima lista os
quatro valores, mas a **mesma página** da forma `Compliance` diz, no parágrafo de descrição do tipo:
*"For the `Compliance` data type, AWS Config supports only `COMPLIANT`, `NON_COMPLIANT`, and
`INSUFFICIENT_DATA` values. AWS Config does not support the `NOT_APPLICABLE` value for the
`Compliance` data type."* E `DescribeComplianceByConfigRule` fecha o ciclo: uma regra cuja Lambda
devolveu `NOT_APPLICABLE` em todas as avaliações é reportada como `INSUFFICIENT_DATA`. Note a
assimetria real: o **filtro de requisição** `ComplianceTypes` aceita `NOT_APPLICABLE`, a
**resposta** não. O renderer nunca emite o valor, e isso é uma constante no código
(`NOT_APPLICABLE_EMITTED = False`), não só prosa.

**2. `CappedCount` conta os culpados, não os avaliados.** A página de `ComplianceContributorCount`
descreve o objeto como *"The number of AWS resources or AWS Config rules that cause a result of
`NON_COMPLIANT`"*. Logo uma regra `COMPLIANT` carrega `CappedCount = 0` — não o total de recursos
que ela avaliou. Contar os avaliados seria um número diferente, e um que a documentação não publica.

**3. `CapExceeded` não é reproduzível.** O booleano é documentado como *"Indicates whether the
maximum count is reached"*, mas a mesma página **nunca publica esse máximo** — só diz *"up to a
maximum number"*. Sem o teto, a comparação não sai da documentação, então o campo vai `null` com o
motivo registrado na proveniência. `CappedCount` continua real, porque é uma contagem do modelo.

### As regras são REAIS, e isso é o que diferencia a superfície

Cada `ConfigRuleName` emitido é uma **regra gerenciada real** do AWS Config, conferida uma a uma na
lista oficial (`managed-rules-by-aws-config.html`, 838 nomes, lida em 2026-10-16). Nada aqui é
inventado. Isso importa porque o lado do produto usa nomes sintéticos `synth-*`
(`emulators/aws-sim`), o que serve de stub e **não** serviria para conferir uma tela de postura real.

O catálogo cobre os quatro domínios — S3 público, rede, identidade, auditoria — com 14 regras.

**Zero regras sem fonte, e isso é um resultado, não uma falha.** As regras respondiam
`INSUFFICIENT_DATA` não porque o veredito fosse incerto, mas porque o estate não carregava o
**fato** que cada uma lê. E há quatro lacunas mais sutis que vale registrar aqui porque
**mudaram nos quatro últimos incrementos**:

- **Incremento 2** — o estate não carregava as REGRAS do security group da AWS: `model/network.py`
  populava `NetworkSegment.network_security_group` só para a Azure e deixava `None` na AWS. Existiam
  15 recursos `security_group`, mas nenhum tinha regra de entrada para ler.
- **Incremento 3** — o estate não carregava ACL, bucket policy nem public access block: existiam 15
  recursos `s3_bucket` inventariados e faturados, mas nada neles afirmava quem pode lê-los ou
  escrevê-los. Hoje a postura vive em `model/storage.py`, na coleção `aws_bucket_postures`.
- **Incremento 4** — o estate não tinha **nenhuma entidade de IAM**: sem MFA de raiz, sem política de
  senha, sem chaves de acesso. Hoje vive em `model/iam.py`, na coleção `aws_identity_postures`.
- **Incremento 4.3** — o estate não tinha trilha de CloudTrail, nem inscrição do Security Hub, nem
  configuração de flow log por VPC. Hoje vivem em `model/audit.py`, nas coleções
  `aws_audit_postures` (por conta) e `aws_vpc_flow_logs` (por VPC).

Eram doze; eram nove; eram seis; eram três; **são zero**.

**No Incremento 1, só duas eram avaliadas do estado de verdade**: `s3-bucket-tagged` e
`lambda-function-tagged`. (Hoje são catorze — o parágrafo abaixo descreve o ponto de partida, não
o estado atual.) As
páginas das duas regras dizem, na mesma frase, *"The rule is NON_COMPLIANT if there are no tags or
if the specified tag keys are not present. The rule does not check for tags starting with 'aws:'"* —
e `requiredKeyTags` é um parâmetro **opcional** da regra, que este renderer não passa. A condição
reduz, então, ao que a página afirma incondicionalmente: `NON_COMPLIANT` se o recurso não tem tag.
`Resource.tags` é exatamente esse fato. Medido **no Incremento 1**, estate pequeno, perfil `small`,
seed canônico 123:
126 itens (14 regras × 9 escopos de conta/região), sendo 2 `COMPLIANT`, 4 `NON_COMPLIANT` e 120
`INSUFFICIENT_DATA`. A divisão entre `COMPLIANT` e `NON_COMPLIANT` varia com a seed — é o
distribuidor de tags do estate mudando — mas os **120** `INSUFFICIENT_DATA` eram estáveis: 12
regras sem fonte × 9 escopos, mais os 6 escopos sem bucket e os 6 sem Lambda.

Um detalhe que o estate produziu e que valia a superfície: cada tipo de recurso AWS existe em
**uma única região** por conta (buckets em `us-west-2`, Lambda em `sa-east-1`, security groups em
`us-east-1`). Então a maioria dos escopos não tem bucket nenhum, e a resposta correta não é
`COMPLIANT` — uma regra sem recurso não avaliou tudo — nem `NOT_APPLICABLE`, que o tipo não suporta.
É `INSUFFICIENT_DATA`, que é o terceiro caso documentado.

## Incremento 2 — AWS Security Groups, `ec2.describe_security_groups` — **ENTREGUE em 2026-10-16**

Superfície `aws/ec2-describe-security-groups`, renderer `ec2_security_groups`, spec
`specs/aws/ec2-describe-security-groups.schema.json`. Contrato lido em 2026-10-16 nas oito páginas
do API Reference (a ação e as sete formas que ela devolve), mais a página de *Security group rules*,
que é onde está a semântica. Auditoria medida: **9 artefatos, 112 registros, 18 caminhos com valor,
0 colunas inventadas**.

### Resposta

`securityGroupInfo`: array de `SecurityGroup` — **9 conjuntos, 40 campos**.

| Conjunto | Campos | O que é |
|---|---|---|
| `describe-security-groups-response` | 3 | `nextToken`, `requestId`, `securityGroupInfo` |
| `security-group` | 9 | identidade, VPC dona, descrição, tags e as **duas** listas de regras |
| `ip-permission` | 7 | protocolo, faixa de portas e as quatro listas de origem |
| `ip-range` / `ipv6-range` / `prefix-list-id` | 2 cada | uma origem de cada tipo |
| `user-id-group-pair` | 7 | referência a outro grupo como origem |
| `tag` | 2 | `key`, `value` |
| `request-parameters` | 6 | `DryRun`, `Filter.N`, `GroupId.N`, `GroupName.N`, `MaxResults`, `NextToken` |

### Cinco armadilhas do contrato, que a leitura apressada erra

**1. A regra é allow-only, e não existe "deny".** O guia de VPC é literal: *"You can specify allow
rules, but not deny rules"*. O bloqueio é a **ausência** de regra. É por isso que o modelo grew
tipos próprios (`AwsSecurityGroup`, `AwsIpPermission`) em vez de reusar a `SecurityRule` da Azure —
aquela tem `access` (`allowed`/`denied`), e a AWS não tem membro de decisão para apontar. Também
não há **prioridade**: o NSG da Azure publica `priority` 100..4096 com o menor número vencendo;
`IpPermission` não publica nada que ordene regras.

**2. `ipProtocol` é nome-ou-número-ou-`-1`.** É um `String`, e a documentação aceita um nome
(`tcp`/`udp`/`icmp`/`icmpv6`), um número de protocolo, ou `-1`. Não é a lista fechada de seis
literais da Azure.

**3. `fromPort`/`toPort` são condicionais.** São `Required: No`. Para `-1` as portas não se aplicam
— e a amostra oficial traz a regra de egress padrão *sem nenhum dos dois*: ausência, não zero. Para
`icmp`/`icmpv6` os mesmos campos são **tipo e código ICMP**, não portas.

**4. A origem é uma lista, não um par.** `IpPermission` tem um conjunto de origens — `IpRanges`
**ou** `Ipv6Ranges` **ou** `Groups` **ou** `PrefixListIds` — e a página de `IpRange` fecha a
exclusividade: *"You can either specify a CIDR block or a source security group, not both."* O
NSG da Azure tem prefixo **e** porta, de origem **e** de destino: quatro campos. E a **direção é o
nome da lista** (`IpPermissions` / `IpPermissionsEgress`), não um membro da regra.

**5. A amostra oficial tem um membro que a página de tipo não documenta.** O `Example 4` traz
`<securityGroupRuleId>` dentro de `<groups>`, mas `UserIdGroupPair` publica sete membros e esse não
é um deles. Ele fica em `unverified` e portanto **proibido** no artefato: exemplo não é contrato de
tipo.

O mesmo `Example 4` é quem identifica o **grupo padrão** da VPC: `<groupName>default</groupName>` com
`<groupDescription>default VPC security group</groupDescription>`. É o grupo que
`vpc-default-security-group-closed` avalia.

### A retroalimentação: três regras de rede saem de `INSUFFICIENT_DATA`

As três regras gerenciadas de rede têm, todas, *Resource Types:* `AWS::EC2::SecurityGroup`, e as
três leem regras de entrada — as duas primeiras — ou a ausência delas no grupo padrão — a terceira.
Com as regras agora modeladas, cada uma aplica o texto da **sua própria página**:

| Regra | Condição publicada | Veredito |
|---|---|---|
| `restricted-ssh` | *"COMPLIANT if the IP addresses of the incoming SSH traffic … are restricted (CIDR other than 0.0.0.0/0 or ::/0)"* | `NON_COMPLIANT` se algum SG abre 22 para `0.0.0.0/0` |
| `restricted-common-ports` | COMPLIANT se a porta está bloqueada, ou aberta só por Inbound rules cuja origem não cobre `0.0.0.0/0` / `::/0` | `NON_COMPLIANT` se algum SG abre uma porta bloqueada para toda a internet |
| `vpc-default-security-group-closed` | *"NON_COMPLIANT if the default security group has one or more inbound or outbound traffic rules"* | `NON_COMPLIANT` se o grupo **padrão** tem ao menos uma regra |

Duas reduções que valem registrar, porque sem elas o veredito seria uma escolha local:

- `restricted-common-ports` tem parâmetros **opcionais** (`blockedPort1..5`). O renderer não passa
  nenhum, então a regra reduz aos **defaults da própria página**: 20, 21, 3389, 3306 e 4333. É a
  mesma redução que o Incremento 1 já fazia com `requiredKeyTags`.
- Uma regra de entrada com `ipProtocol` `-1` conta como quem abre a porta. A página de `IpPermission`
  diz que `-1` *"allows traffic on all ports, regardless of any port range you specify"*; ler `-1`
  como "não é TCP" deixaria passar uma regra que expõe SSH.

**Medido no estate pequeno, seed 123:** 126 itens, sendo **8 `COMPLIANT`, 7 `NON_COMPLIANT` e 111
`INSUFFICIENT_DATA`** (eram 2 / 4 / 120). Cada regra de rede dá **2 escopos `COMPLIANT` e 1
`NON_COMPLIANT`** — e os 6 `INSUFFICIENT_DATA` de cada uma são os escopos sem nenhum security
group, que é o caso "nada avaliado" e não o caso "tudo conforme".

Esse dois-lados não é decoração. **Foi uma falha real deste incremento**, medida pelo teste golden:
com cinco grupos por conta e uma rotação única de quatro perfis, *toda* conta recebia um grupo
exposto, e `restricted-ssh` — que só é `COMPLIANT` quando *nenhum* grupo do escopo expõe a porta —
ficava `NON_COMPLIANT` em todos os escopos. Isso não ensinaria nada: um consumidor com a porta
invertida, ou um check que ignorasse o CIDR de origem, receberia exatamente a mesma resposta. A
postura passou a ser **conta par endurecida, conta ímpar exposta**.

### O que ficou declarado, e não afirmação

`vpcId` é a pendência real desta superfície, e é um `TODO-verificar`. O estate **não** liga um
security group a uma VPC: os recursos `vpc` vivem todos em `sa-east-1` e os `security_group` todos
em `us-east-1`, e nenhum par (conta, região) tem os dois. O valor vem do **segmento** de rede do
mesmo (conta, região), cujo `segment_id` já é o id nativo `vpc-…` — ou seja, é a função do
agrupamento do próprio modelo, não uma escolha sobre a semântica do provedor. A construção **falha**
se um grupo não tiver segmento: um grupo sem VPC faria `vpc-default-security-group-closed` responder
sobre uma VPC que não existe.

`securityGroupArn` vai `null`: o ARN é `arn:<partition>:ec2:…` e o modelo não carrega a **partição**.
Escrever `arn:aws:` afirmaria um fato que o estate não tem — e a partição é exatamente o que difere
entre comercial, GovCloud e China.

## Incremento 3 — Bucket S3: `list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block` — **ENTREGUE em 2026-10-16**

Quatro superfícies, quatro renderers, quatro specs — mesmo desenho do Incremento 2, aplicado à
família do bucket. Contrato lido em 2026-10-16 nas páginas do S3 API Reference (`API_ListBuckets`,
`API_Bucket`, `API_Owner`, `API_GetBucketAcl`, `API_Grant`, `API_Grantee`, `API_GetBucketPolicy`,
`API_GetPublicAccessBlock`, `API_PublicAccessBlockConfiguration`), mais três do **User Guide** que
são onde está a semântica: `acl-overview.md` (canned ACLs e grupos predefinidos),
`access-control-block-public-access.md` (o que a AWS chama de "público") e as três páginas de regra
gerenciada do AWS Config. Auditoria medida (`fidelity --audit`, revisão 5169404): **40 superfícies,
0 com erro, 0 sem registro, 0 com coluna inventada** — as quatro do S3 entram nesse total com
19 artefatos e 0 coluna fora do contrato.

A postura vive em `model/storage.py`, numa coleção **`CanonicalEstate.aws_bucket_postures`** — e
**não** como coluna em `Resource`. `Resource` é o portador de identidade que a FOCUS 1.2 consome
coluna a coluna; nenhum elemento do S3 pertence àquele conjunto, e pôr uma ACL ali colocaria um
campo que nenhuma coluna FOCUS define dentro do registro que define todas elas.

### As quatro respostas, e o que cada uma publica

| Superfície | Conjuntos | Campos | Formato da resposta |
|---|---|---|---|
| `aws/s3-list-buckets` | 4 | **14** | XML |
| `aws/s3-get-bucket-acl` | 5 | **13** | XML |
| `aws/s3-get-bucket-policy` | 4 | **11** | **JSON** |
| `aws/s3-get-public-access-block` | 2 | **6** | XML |

O escopo **não** é o mesmo nas quatro, e essa é a primeira coisa a acertar: `ListBuckets` lista
*"all buckets owned by the authenticated sender"*, e a região de cada bucket viaja **dentro** do
objeto `Bucket` (`BucketRegion`). Logo ela é **por conta** — um artefato por (conta, região)
contaria o mesmo conjunto de buckets uma vez por região. As outras três são chamadas **por bucket**,
por construção.

### Cinco armadilhas do contrato, que a leitura apressada erra

**1. A ACL publicada é a EFETIVA, e não a armazenada.** A página de Block Public Access é literal:
*"Calls to GetBucketAcl and GetObjectAcl always return the effective permissions in place for the
specified bucket or object… suppose that a bucket has an ACL that grants public access, but the
bucket also has the IgnorePublicAcls setting enabled. In this case, GetBucketAcl returns an ACL that
reflects the access permissions that Amazon S3 is enforcing, rather than the actual ACL that is
associated with the bucket."* O estate guarda as **duas** ACLs e o renderer publica a efetiva.
Medido: **25 grants armazenados, 23 publicados, 2 suprimidos** em 2 buckets.

**2. "Público" é propriedade do RECEBEDOR, não do nome da permissão.** A definição da AWS é:
*"Amazon S3 considers a bucket or object ACL public if it grants any permissions to members of the
predefined AllUsers or AuthenticatedUsers groups."* Os dois grupos, e só eles. O grupo
`LogDelivery` — que a canned ACL `log-delivery-write` usa — **não** está na frase, então um bucket
que o recebe não fica público. E `FULL_CONTROL` para `AllUsers` conta como leitura **e** como
escrita, porque concede as duas.

**3. O Block Public Access é CURTO-CIRCUITO, e não uma quarta opinião.** A regra é uma conjunção de
duas disjunções cujo primeiro termo é o block. Com `BlockPublicPolicy` ligado, a metade passa **sem
que a policy seja consultada** — mesmo sendo pública. Um renderizador que só perguntasse "a policy é
pública?" reprovaria onde a AWS aprova. É o erro mais provável ao implementar esta regra, e é por
isso que existe um perfil só para exercitá-lo.

**4. Só `GetBucketPolicy` é JSON.** As outras três têm "The following data is returned in **XML**
format by the service". Tratar a quarta como XML por estar no mesmo capítulo seria errado. E o
membro `Type` do `Grantee` aparece no XML como `<xsi:type>`, que é a mesma coisa com o namespace do
schema instance — o nome do membro é `Type`.

**5. `Policy` é o único Response Element da página da policy — e não é onde os membros estão.** A
lista tem um item só. `Version`, `Id`, `Statement` e, dentro do statement, `Sid`, `Effect`,
`Principal`, `Action` e `Resource`, vêm da **Sample Response da mesma página**. `Condition` existe
na linguagem de policy e **não** aparece nesse exemplo, logo não entra no artefato; a razão está em
`unverified` para que ninguém amplie a lista achando que a página a publica.

### A retroalimentação: três regras de S3 saem de `INSUFFICIENT_DATA`

As três publicam *Resource Types:* `AWS::S3::Bucket`, e as duas primeiras leem **as mesmas três
coisas**: *"The rule checks the Block Public Access settings, the bucket policy, and the bucket
access control list (ACL)."*

| Regra | Condição publicada | Veredito |
|---|---|---|
| `s3-bucket-public-read-prohibited` | *"compliant when **both**: the Block Public Access setting restricts public policies **OR** the bucket policy does not allow public read access; **and** … restricts public ACLs **OR** the bucket ACL does not allow public read access"* | `NON_COMPLIANT` se algum bucket escapa ao block por policy **ou** por ACL |
| `s3-bucket-public-write-prohibited` | a mesma estrutura, com escrita | idem, na direção de escrita |
| `s3-bucket-level-public-access-prohibited` | *"NON_COMPLIANT if an S3 bucket is not listed in the `excludedPublicBuckets` parameter and bucket level settings are public"* | `NON_COMPLIANT` se algum bucket tem ACL ou policy pública |

Duas reduções declaradas, porque sem elas o veredito seria escolha local:

- `excludedPublicBuckets` é **opcional** e o renderer não passa parâmetro, então a exclusão é vazia
  e a condição reduz a "os settings de nível de bucket são públicos".
- O texto da regra de nível é **uma frase** e não detalha a avaliação. Aqui "público" é lido como a
  presença de ACL pública ou de policy com principal curinga — a mesma definição que a página de
  Block Public Access publica. Alimitação registrada em `unverified` na spec.

**Medido no estate pequeno, seed 123:** as três regras dão **2 escopos `COMPLIANT` e 1
`NON_COMPLIANT`** cada, e 6 `INSUFFICIENT_DATA` — que são os escopos sem nenhum bucket, o caso
"nada avaliado" e não "tudo conforme". O total dos 126 itens do renderer de conformidade foi de
**14 `COMPLIANT`, 10 `NON_COMPLIANT`, 102 `INSUFFICIENT_DATA`** (eram 8 / 7 / 111 — os mesmos 8 e 7
que o Incremento 2 mediu). A conta fecha: cada uma das três regras trocou **3 dos seus 9 escopos** de
`INSUFFICIENT_DATA` para um veredito — 2 para `COMPLIANT` e 1 para `NON_COMPLIANT` — o que são 9 itens
no total, e `111 − 9 = 102`. Os outros 6 escopos de cada regra nunca mudaram de estado: são os que
não têm bucket algum.

### O dois-lados de novo, e o modo como ele falhou aqui

Os perfis são **declarados**, nunca sorteados, e os grants vêm da tabela de **canned ACLs da AWS** —
que é onde a própria AWS diz quem recebe o quê em cada ACL predefinida. A conta par recebe a rotação
restrita, a ímpar a exposta.

O teste golden pegou uma falha real de distribuição: com cinco buckets por conta, o perfil que
exercita o curto-circuito do block estava no **sexto** slot da rotação restrita, e o perfil `small` só
produz cinco. Ou seja, a discriminação mais importante da regra **não existia em nenhum estado que a
suíte constrói** — passaria despercebida. A correção foi de ordem, não de código, e a lição é a
mesma do Incremento 2: a rotação é um mecanismo de prova, e um mecanismo de prova só prova o que
alcança.

Uma segunda consequência do mesmo mecanismo vale registrada: o veredito de uma regra é **por escopo**,
e basta **um** bucket em violação para o escopo inteiro virar `NON_COMPLIANT`. Por isso a rotação
restrita não pode conter nenhum perfil que reprove a regra de nível — se contivesse, não existiria
escopo conforme, e o lado bom da regra deixaria de existir no estado.

### O que ficou declarado, e não afirmação

`BucketArn` vai `null`, e é **por contrato**: a página do tipo `Bucket` diz *"This parameter is only
supported for S3 directory buckets"*, e todo bucket do estado é de uso geral. Emitir um ARN seria
afirmar um fato que a documentação retém.

`CreationDate` é **derivada**: um bucket não é medido — `s3_bucket` está entre os tipos que o estate
não fatura —, então não há linha de consumo de onde a data viesse.

A junção entre resposta e bucket é **por posição**, e isso é declarado, não acidental: as respostas de
`GetBucketAcl`, `GetPublicAccessBlock` e `GetBucketPolicy` descrevem **um** bucket e nenhuma delas
tem membro que o nomeie. Em vez de inventar um `bucketName`, as três superfícies compartilham uma
ordem documentada — (conta, região, bucket) — e cada artefato grava o mapa `response_order` na
proveniência. A tripla é necessária, e não o nome: `estate_builder` reinicia o contador por escopo,
então `s3_bucket-0004` existe em mais de uma conta.

## Incrementos seguintes, na ordem

| # | Família | Check | Onde está o contrato |
|---|---|---|---|
| ~~2~~ | **Security Group da AWS** | `ec2.describe_security_groups` + ingress | **entregue** |
| ~~3~~ | **Bucket S3** | `list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block` | **entregue** |
| ~~4~~ | **IAM sem MFA** | `iam.get_credential_report` | **entregue** |
| ~~5~~ | **GCP — SCC** | findings do Security Command Center | **entregue em 2026-10-18 (fidelidade)** |
| 6 | **GCP — firewall** | regras `0.0.0.0/0` em portas críticas | Network Security / VPC firewall |
| ~~7~~ | **Azure — NSG** | regras de NSG | **entregue em 2026-10-18 (fidelidade)** |
| 8 | **Azure — Defender** | posture de Defender for Cloud | Defender for Cloud |

O item 7 foi o mais barato de **medir** (a superfície já existia), não de **fechar**: a auditoria
achou o `nsg.id` ausente — do qual o comando de remediação do consumidor depende — e um estado que
o check nunca sinalizava. "A superfície já está pronta" é hipótese de partida, não veredito.

## O que muda na ponte (D3)

O writer do FinOps passa a ler estas superfícies em vez do export do Security Hub. Os campos que
ele precisa e que o simulador passa a trazer:

| Coluna do consumidor | De onde vem |
|---|---|
| `category` | `config` para Config, `network` para SG, `s3` para bucket, `iam` para MFA |
| `severity` | derivado do `ComplianceType` + regra — **regra a definir**, ver abaixo |
| `resource_id` / `resource_type` | do recurso avaliado pela regra |
| `region` | do recurso |
| `description` / `evidence` / `exposure` / `impact` | do molde do `b3dd315` H-18 (as cinco chaves em `UserDefinedFields`) |
| `fingerprint` | mesma regra do `b3dd315` H-18, recalculável a partir do documento |

**Uma decisão que fica sua:** a coluna `severity` é `NOT NULL` na tabela do consumidor, e o
`ComplianceType` do AWS Config é um estado de conformidade, **não** uma severidade. Mapear
`NON_COMPLIANT → HIGH` é um juízo de produto, não uma leitura de documentação. As saídas são:
(a) o simulador carrega a severidade por regra, vinda da documentação da própria regra gerenciada;
(b) o consumidor deriva de `ComplianceType` com uma tabela fixa, que é dele; ou (c) `severity`
deixa de ser `NOT NULL`. **Nenhuma delas é óbvia, e a escolha muda o que o simulador precisa
modelar.**

### A decisão acima já está respondida do lado do produto — e de um jeito que muda a pergunta

Conferido em 2026-10-16 em `security.py (modulo do consumidor):700-748`: o
produto **já tem** uma tabela de severidade por regra, `_config_rule_severity`. Ou seja, a saída
(b) já está implementada — com uma diferença que importa: a tabela é indexada pelo **nome da
regra**, não pelo `ComplianceType`. `ComplianceType` diz que a regra falhou; o nome diz *qual* regra
e *quão grave* ela é. Isso é melhor informação do que a que a API entrega sozinha, e é por isso que
a saída (a) — carregar severidade no simulador — fica descartada sem custo: a API **não publica**
severidade por regra, e o simulador que a inventasse violaria a regra de ouro desta fase.

E o consumo é literalmente o que esta superfície entrega. O check `_scan_config_failures` chama
`DescribeComplianceByConfigRule` filtrado por `ComplianceTypes=["NON_COMPLIANT"]` e depois
`GetComplianceDetailsByConfigRule` para os recursos de trás de cada regra. **A primeira chamada é
esta superfície**; a segunda é uma superfície diferente, que guarda o detalhe por recurso e que
continua fora do escopo.

### Desencontro de nomes de regra entre o produto e a AWS — medido, não suspected

`security.py:721-722` lista dois nomes de regra do AWS Config. Conferência um a um contra a lista
oficial (838 nomes, lida em 2026-10-16):

| Padrão no produto | Existe como nome real? | Efeito |
|---|---|---|
| `cloud-trail-enabled` | **NÃO** — o nome real é `cloudtrail-enabled`, sem hífen | o padrão casa com **0 dos 838** nomes, então a regra real cai no `return "MEDIUM"` do fim em vez do `HIGH` pretendido |
| `cloudtrail-s3-dataevents` | o nome real é `cloudtrail-s3-dataevents-enabled` | **benigno**: o padrão casa por prefixo com o nome real |

Ou seja: um defeito real, pequeno e datado. O nome oficial existe com outra grafia e a comparação
por substring nunca o alcança. É correção de uma linha no lado do produto e **não foi feita aqui** —
esta tarefa é somente leitura do FinOps. Registrado para o writer.

→ Este é o **achado nº 1** da [seção canônica dos achados](INGESTAO-D3-SEGURANCA.md#achados-para-o-time-do-consumidor).

## Regra de ouro desta fase

Nenhum valor inventado para fechar lacuna de segurança. Se a AWS publica o campo, ele entra com
URL e data; se não publica, fica em `unverified` e o renderer emite vazio — exatamente como
`class_uid` e `metadata.version` ficaram no OCSF. O ganho aqui é **cobertura de domínio**, que é
escopo; a fidelidade dos valores continua sendo evidência.

## Incremento 4 — IAM: três regras de Config que deixaram de responder `INSUFFICIENT_DATA` (2026-10-18)

### O problema, em uma frase

`--matrix` estava em **40 geradas de 41 declaradas** e `--ready` verde, e mesmo assim o painel de
postura de Config mostrava `INSUFFICIENT_DATA` em **102 das 126** respostas. Nenhuma das duas
medições via o problema: uma conta o número de artefatos que existem, e a outra o número de
artefatos fiéis. **Fidelidade de coluna não é dado presente.**

### A regra de ouro, aplicada de verdade

Este incremento é o primeiro em que a regra de ouro desta fase **muda de comprimento**: não é
mais "nenhum valor inventado para fechar lacuna". É **"nenhum valor inventado para deixar de
reportar uma lacuna"** — e a diferença aparece em `gcp/observability-partial` e em
`iam-get-credential-report`, onde duas lacunas de forma (o conjunto `missing.json`, o envelope de
colunas) **não** foram preenchidas com campo inventado, e sim com artefato irmão ou marcação
`unverified`.

O teste de uma lacuna é: *se eu não estivesse desse lado, o consumidor saberia a mesma coisa?*
Para o envelope do credential report, sim — ele lê o CSV decodificado; para o `missing`, sim — ele
lê `missing.json`. Nenhum dos dois precisou que inventássemos um campo dentro de um corpo que a
documentação fecha.

### As três regras, e a lacuna que as três tinham

| Regra | Veredito | Lê |
|---|---|---|
| `root-account-mfa-enabled` | 6 C / 3 NC | MFA da conta **root** |
| `iam-password-policy` | 6 C / 3 NC | a **política de senha da conta** |
| `access-keys-rotated` | 6 C / 3 NC | idade das chaves dos **usuários** |

As três respondiam `INSUFFICIENT_DATA` pela **mesma** lacuna nomeada: o estate não tinha
**nenhuma entidade de IAM**. Não "não sabemos se a senha é forte" — não tínhamos senha para
olhar. É a lacuna que os incrementos 2 e 3 fecharam para grupos de segurança e postura de bucket,
e que este fecha para identidade.

### O eixo é a CONTA, e isso muda a forma da regra

IAM é global. A senha, o MFA do root e as chaves não têm região. Então:

- a chave da postura é `AwsAccount.account_id`, **não** `Resource.identity.uuid`;
- a regra responde **por conta** e **se repete** nas três regiões da conta;
- `resource_type` continua `None` para as três — e `None` deixou de significar "não avaliada".

Um veredito diferente por região seria um fato que a AWS não tem.

### Por que cada regra reprova numa conta diferente

```
conta 0  ->  só a SENHA reprova          (política de 8 caracteres, sem requisito)
conta 1  ->  só as CHAVES reprovam       (uma chave ATIVA de 410 dias)
conta 2  ->  só o ROOT reprova           (conta root sem MFA)
```

Não é estética. Se duas regras reprovassem na mesma conta, um renderer que as trocasse de lugar
receberia a mesma resposta e **passaria**. Com uma violação por conta, trocar duas regras muda a
contagem — e é isso que `test_o_veredito_e_confirmado_pelas_tags_do_modelo` mede.

### Um avaliador, e por isso isso

`render/_config_evaluators.py` é a **única** implementação da semântica de veredito. O renderer de
Config chama para escrever o artefato; `fidelity/review.py --state IAM` chama para descrever o
que a tela mostraria. Divergência é **impossível por construção**.

`RuleVerdict` devolve o veredito **e os `contributors`**, e isso não é enfeite:
`ComplianceContributorCount` exige `CappedCount == 0` num `COMPLIANT` e `> 0` num
`NON_COMPLIANT`. Um avaliador que não sabe dizer **que** reprovou satisfaz o contrato no papel e
não dá ao consumidor nada acionável.

### O diagnóstico retrospectivo

Um `INSUFFICIENT_DATA` na tela tem **três** causas que pedem ações opostas:

1. **avaliável com o estado atual** → corrige-se no **renderer**;
2. **carga mas falta o dado** → corrige-se no **modelo**;
3. **falha de configuração** → corrige-se na **conta**; nenhum código resolve.

`--state IAM` mede o `ComplianceType` atual nos **bytes gravados** — é a medição que impede o
diagnóstico de dizer "não mudou" sobre uma tela que mudou.

### Os 4 checks de postura AWS estão fechados

Os quatro checks que o FinOps roda na AWS têm, cada um, a superfície que os produz:

| Check | Superfície | Incremento |
|---|---|---|
| AWS Config by-rule | `aws/config-describe-compliance-by-config-rule` | 1 |
| Security Groups | `aws/ec2-describe-security-groups` | 2 |
| S3 público | `aws/s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`, `s3-get-public-access-block` | 3 |
| IAM sem MFA | `aws/iam-get-credential-report` | 4 |

Conformidade medida (seed 123, perfil `small`, **126** registros em **9** escopos):

```
COMPLIANT 45   NON_COMPLIANT 27   INSUFFICIENT_DATA 54   NOT_APPLICABLE 0
```

Era `32 / 19 / 75` antes do Incremento 4.3 — as três últimas regras nomeadas em *Resíduo
nomeado*, abaixo, saíram de `INSUFFICIENT_DATA` em todos os escopos.

### Resíduo nomeado: três regras de auditoria — **FECHADO no Incremento 4.3 (2026-10-18)**

Das **14** regras do catálogo, **14** são avaliadas do estado. Não resta nenhuma regra que não
responda, e o `INSUFFICIENT_DATA` que sobrou tem **uma** causa só: a ausência de recurso do tipo
no escopo (o colapso `NOT_APPLICABLE` que a API reporta como `INSUFFICIENT_DATA`). A lacuna de
modelo nomeada **não existe mais** nesta superfície.

O que foi modelado, e por quê em dois formatos:

| Regra | Granularidade | Fato novo | Fonte do formato |
|---|---|---|---|
| `cloudtrail-enabled` | **por conta** | trilhas CloudTrail da conta | página publica trigger `Periodic` e **nenhum** *Resource Types* |
| `securityhub-enabled` | **por conta** | inscrição do Security Hub | idem — "Parameters: None" |
| `vpc-flow-logs-enabled` | **por VPC** | configuração de flow log da VPC | página publica *Resource Types:* `AWS::EC2::VPC` |

Os **54** `INSUFFICIENT_DATA` agora se decompõem assim, e a decomposição importa porque separa
duas coisas que já não devem ser confundidas:

- **48** são de 8 regras **avaliadas** que não têm recurso do tipo em 6 dos 9 escopos;
- **6** são da 9ª regra por recurso, `vpc-flow-logs-enabled`, nos 6 escopos sem VPC.

Ou seja: **27 → 0**. A queda total foi de 21 (75 → 54) e não de 27, porque a regra de VPC
comporta-se como qualquer outra regra por recurso — responde nos 3 escopos que têm VPC e
colapsa nos outros 6. Isso é o caso "nada avaliado", não lacuna.

Os três estados que antes podiam se parecer e agora são explicitamente distintos:

- escopo **sem VPC nenhuma** → `INSUFFICIENT_DATA` (nada foi avaliado);
- VPC com lista de flow logs **vazia** → `NON_COMPLIANT` (o estate afirma que ela não tem log);
- conta **sem trilha nenhuma** → `NON_COMPLIANT`, nomeando a conta como *contributor*.

Ler a lista vazia como ausência de conhecimento esconderia uma violação real atrás de um "não
sei" — que é exatamente o defeito que este incremento elimina.

`lambda-function-tagged` segue o mesmo padrão de antes: responde `NON_COMPLIANT` nos 3 escopos
onde há função Lambda e `INSUFFICIENT_DATA` nos outros 6, porque o estate põe funções em uma
região só por conta. Não é lacuna de modelo — é ausência de recurso no escopo.

### O que fica para o próximo

- ~~`cloudtrail-enabled`, `securityhub-enabled`, `vpc-flow-logs-enabled`~~: **fechado no
  Incremento 4.3**. O diagnóstico `--state` ainda os cobre só por identidade; a avaliação de
  auditoria e de flow log ainda não tem retrospectivo próprio;
- `lambda-function-tagged`: **não** é resíduo — é avaliada onde existe recurso, e a causa
  do resto é ausência de recurso no escopo, não lacuna de modelo;
- o Block Public Access **de nível de conta** — que a própria página do `GetPublicAccessBlock`
  descreve ("the most restrictive combination") — não é modelado; só o do bucket é.

## Incremento 5 — GCP SCC: fidelidade da superfície de findings (2026-10-18)

### Este incremento não constrói nada; ele mede

Os quatro incrementos anteriores construíram do zero uma superfície que faltava. O SCC é o
oposto: `gcp/scc-findings` e `gcp/scc-sources` **já existiam** e estavam `STATUS_IMPLEMENTED`.
O trabalho foi auditar esses campos, um a um, contra o que o FinOps de fato lê. E a
regra de ouro se aplica nos dois sentidos: se eu tivesse inventado uma divergência para
"entregar algo", teria cometido a mesma falha que a regra proíbe.

Duas divergências foram levantadas como hipótese. **Uma se confirmou, a outra não.**

### O contrato do consumidor, medido

Lido em `<arvore-de-origem>` (read-only, `security.py (modulo do consumidor)`),
`GCPSecurityScanner._list_scc_findings` chama `securitycenter_client().list_findings(...)` —
a API gRPC `securitycenter_v1`, **não** BigQuery — e projeta cinco campos do `finding`:

| Campo lido | Linha | Spec do simulador | Bate? |
|---|---|---|---|
| `f.severity.name` | `security.py:86` | `finding.severity` | sim |
| `f.resource_name` | `security.py:91` | `finding.resourceName` | sim |
| `f.category` | `security.py:92`, `:94` | `finding.category` | sim |
| `f.description` | `security.py:94` | **ausente** | **NÃO — fechado aqui** |
| `f.name` | `security.py:98` | `finding.name` | sim |

Correção ao enunciado do pedido: `f.state` **não** é lido do objeto. Ele aparece só dentro da
string de filtro (`security.py:80`), nunca como campo projetado. A spec declara `finding.state`
porque o filtro o nomeia e o renderer emite `ACTIVE` — e `ACTIVE` é o valor que o enum oficial
publica. Está correto como estava.

### Divergência 1 — `description`: CONFIRMADA e fechada

O consumidor monta a descrição do finding com `f.description or f.resource_name`. A coluna
não existia na spec e o renderer não emitia a chave: em proto3 o campo ausente chega como
string vazia, então **todo** finding da superfície cairia no fallback e o artefato nunca
exercitaria o campo que o consumidor projeta. Fiel ao formato, desleal ao contrato.

Comprovável por duas fontes oficiais de máquina:

- `finding.proto`: `string description = 37;` — *"Contains more details about the finding."*
- discovery v1 (`securitycenter.googleapis.com/$discovery/rest?version=v1`):
  `Finding.properties.description` = `{"type": "string"}`

Fechado em duas linhas: a coluna `listFindingsResults[].finding.description` na spec
(`status: verified`, com a página de docs no `source_url` e as fontes de máquina em
`reference_urls`), e a projeção no renderer. O valor é `NativeFinding.description` — o mesmo
fato que o renderer **irmão** da tabela do BigQuery já projetava em `finding.description`. Não
foi preciso inventar valor: o `estate_builder` já popula esse campo em toda finding
(`estate_builder.py:1817`), e a medição no artefato confirma **64 de 64** findings com texto
não-vazio. O mesmo `NativeFinding` que alimenta as duas superfícies é o que evita a divergência
entre elas.

### Divergência 2 — `parent` projeto × organização: NÃO é divergência

O consumidor pede `projects/{project_id}/sources/-`; o simulador emite
`organizations/{org}/sources/{n}`. Era a suspeita mais séria do pedido, e ela **não se
confirmou**: os dois níveis são publicados.

- `securitycenter_service.proto`, rpc `ListFindings`: três bindings — `organizations/*/sources/*`,
  `folders/*/sources/*` e `projects/*/sources/*`;
- discovery v1: `v1/projects/{projectsId}/sources/{sourcesId}/findings`, ao lado dos outros dois;
- `Finding.name` publica os três padrões, e o `resource_reference` de `Finding` declara
  `organizations`, `folders` **e** `projects`.

Emitir no nível da organização é uma instância válida do contrato, não um caso ausente, e a
forma da coluna não muda com o nível. Registrei a medição na spec (`notes`) para que a pergunta
não seja re-litigada a cada incremento. **Nenhuma modelagem foi alterada** — mudar o nível
emitido seria trocar uma escolha válida por outra sem ganho de fidelidade.

### Resíduo

- `sourceProperties.{Explanation,Recommendation}`: **permanece `unverified`**, e o motivo
  continua o mesmo — o proto diz que as chaves do mapa são geridas pela fonte e publica apenas
  a gramática do nome (1–255 caracteres, começando por letra). Não há enumeração oficial das
  chaves do Security Health Analytics.
- `listFindingsResults[].resourceUuid`: **permanece `unverified`** (plano best-effort legado).

Nenhuma das duas mudou, então `NAO-COMPROVADOS.md` não foi regerado.

### Estado no mapa

`gcp/scc-findings` fechou em **13 colunas na spec, 13 populadas, 0 ausentes, 0 inventadas**
(eram 12). O check GCP SCC em `<doc-de-cobertura>.md` sai de *inferido* para *medido*: a
superfície é fiel ao contrato do consumidor em todos os campos que o consumidor projeta.

## Incremento 7 — Azure NSG: fidelidade da superfície de regras (2026-10-18)

### Este incremento também não constrói uma superfície; ele a mede

`azure/arm-network-security-group-rules` já existia e estava pronta: 23 colunas em dois conjuntos
(`rule`, `networkSecurityGroup`), renderer, modelo, teste golden. O pedido eram quatro divergências
candidatas. **Duas se confirmaram, uma se refutou por ser Transporte, uma por já estar coberta** — e a
medição revelou um problema **maior que as quatro**, que nenhuma delas antecipava.

### O contrato do consumidor, medido

Lido em `<arvore-de-origem>` (read-only, `security.py (modulo do consumidor)`),
`AzureSecurityScanner._list_open_nsgs` (linha 103) chama `network.network_security_groups.list_all()`,
itera `nsg.security_rules or []` e filtra por direção, acesso, origem aberta e **porta crítica**:

| Campo lido | Linha | Spec do simulador | Bate? |
|---|---|---|---|
| `rule.direction` (filtra `Inbound`) | `security.py:109` | `...properties.direction` | sim |
| `rule.access` (filtra `Allow`) | `security.py:109` | `...properties.access` | sim |
| `rule.source_address_prefix` (filtra `*` / `0.0.0.0/0` / `Internet`) | `security.py:111` | `...properties.sourceAddressPrefix` | sim |
| `rule.destination_port_range` | `security.py:114` | `...properties.destinationPortRange` | sim |
| `rule.destination_port_ranges` (**plural**, lista) | `security.py:114` | `...properties.destinationPortRanges` | na spec, vazio no estado |
| `rule.name` | `security.py:124` | `...name` | sim |
| `nsg.name` | `security.py:124` | `name` | sim |
| `nsg.location` | `security.py:123` | `location` | sim |
| `nsg.security_rules` | `security.py:108` | `properties.securityRules` | sim |
| **`nsg.id`** | **`security.py:121`, `:125`** | **ausente** | **NÃO — fechado aqui** |

### Divergência 1 — envelope `list_all` × corpo por NSG: NÃO é divergência

O consumidor chama `list_all()`, cujo envelope REST é `{"value": [...], "nextLink": ...}`
(`NetworkSecurityGroupListResult`). A superfície emite **um corpo por NSG**, não o envelope de lista.

Isso é a **forma de entrega certa**, e a fonte a confirma: `NetworkSecurityGroupListResult` publica
exatamente `nextLink | string (uri)` e `value | Network Security Group []` — a paginação da coleção,
não um campo do recurso. O SDK desembrulha `value` antes de entregar cada NSG ao consumidor, e é por
isso que ele consegue ler `name`/`id`/`location`/`security_rules` de cada objeto iterado. Emitir um
`value` **dentro** de cada NSG seria inventar um membro que o recurso não tem — a mesma armadilha do
Incremento 5. Registrei a análise na spec (`notes`) para não ser re-litigada.

### Divergência 2 — `destinationPortRanges` (plural): já coberta pela spec

O consumidor lê `rule.destination_port_ranges` **além** do singular, e `_parse_ports` processa os
dois. A spec **tem** a coluna (`string[]`, `status: verified`) e a doc oficial confirma o membro.
Portanto **não há divergência de spec a fechar**. O que existe é uma lacuna de *cobertura de estado*:
o modelo guarda a forma singular, então o plural sai vazio e o ramo `if ranges:` de `_parse_ports`
nunca executa contra o artefato. Fechá-lo exigiria modelar a forma plural em `SecurityRule` — que é
mudança no `model/network.py`, compartilhado com os renderers de NSG flow logs. **Não foi feito**:
é ganho de cobertura, não de fidelidade, e o enunciado manda construir só o que a divergência
comprovada exigir.

### Divergência 3 — origem `Internet`: CONFIRMADA como ramo morto

O consumidor trata `Internet` como origem aberta (`security.py:111`), e a doc publica
`"Default tags such as 'VirtualNetwork', 'AzureLoadBalancer' and 'Internet' can also be used"` —
portanto a spec, que declara `sourceAddressPrefix` como `string`, já cobre o valor.

O problema não era a spec: era que **nenhuma regra do estado usava `Internet`**. As duas regras
usavam `*`, então o terceiro ramo do filtro nunca era executado contra o artefato. Fechado junto com
a divergência 4 (abaixo): a regra crítica nova usa `Internet` como origem.

### Divergência 4 — `nsg.id`: CONFIRMADA, e com efeito observável

A página de template não publica `id`. Mas a **página REST** publica: o objeto
`Network Security Group` traz a linha `id | string | Resource ID.`, e o exemplo de resposta do
`list_all` mostra o id completo de cada NSG.

O impacto não é cosmético. O consumidor faz:

```python
resource_id=nsg.id or nsg.name,                                    # security.py:121
... f"--resource-group {nsg.id.split('/')[4] if nsg.id else ''}"   # security.py:125
```

Sem o campo, `resource_id` caía no **nome** do NSG (um id que não é clicável em lugar nenhum) e o
comando de remediação saía com `--resource-group` **vazio** — ou seja, o comando que o operador copia
para o terminal não funcionava. Medido antes da mudança: **`nsg.id` ausente em 6/6 NSGs**.

Fechado com duas colunas e uma composição: `id` no conjunto `networkSecurityGroup`, e
`properties.securityRules[].id` — que estava em `unverified` **por um motivo que a doc REST refuta**,
pois ela publica o objeto `Security Rule` com a mesma linha `id | string | Resource ID.` e o exemplo
do GET fixa a forma como `<id-do-NSG>/securityRules/<nome>`. Os dois saem de
`NetworkSecurityGroup.arm_id()`, o mesmo método que já compunha o caminho do arquivo: **nenhuma
grafia do mesmo id pode divergir**.

### O achado que as quatro divergências não antecipavam: o check nunca disparava

Rodando a lógica **real** de `_list_open_nsgs` (filtro completo + `_parse_ports` + o dicionário de
`_CRITICAL_PORTS`) sobre os artefatos entregues, o resultado da postura anterior foi:

```
NSGs entregues: 6
regra Inbound/Allow+source aberto por NSG: 6
ACHADOS CRITICAL que o consumidor real produziria: 0
```

**Zero.** A postura era coerente — `AllowVnetInboundTls` na 443 e `DenyInternetInboundRdp` na 3389,
duasentro no mesmo NSG, a exposição real do `Allow` avaliada antes do `Deny`. Mas 443 **não está** no
`_CRITICAL_PORTS` do consumidor (22, 3389, 5432, 3306, 1433, 27017, 6379), e a única regra com porta
crítica era uma `Deny`, descartada pelo filtro de acesso **antes** de a porta ser lida.

Ou seja: o estado expunha uma porta de qualquer origem e o check de postura reportava **nada**. Um
check que nunca dispara sobre o artefato não treina o check, e o teste golden antigo não pegava
isso porque conferia só o par `direction`/`access` — que a postura antiga satisfazia.

Fechado com a regra `AllowInternetInboundSsh` (`Internet` → `22`, prioridade 100). Medido depois:

```
ACHADOS CRITICAL do consumidor real: 6          (era 0)
split('/')[4] (resource-group) = 'synthetic-rg-sub-03'
id da regra coerente com nsg.id + /securityRules/ + nome: True
```

### Resíduo

- Formas **plurais** de prefixos e portas: continuam vazias por escolha do modelo (ver Divergência 2).
  Fechá-las exige `model/network.py`, fora do que a divergência comprovada exigia.
- `defaultSecurityRules`: a Azure cria três regras de entrada e três de saída por padrão, e o
  exemplo REST **publica** os seis nomes e prioridades (`AllowVnetInBound` 65000,
  `AllowAzureLoadBalancerInBound` 65001, `DenyAllInBound` 65500, e os três de saída). Elas **não**
  entram no estado: as três de entrada são `Allow` com origem `VirtualNetwork`/`AzureLoadBalancer`
  (não abertas), e `DenyAllInBound` é `Deny` — portanto **nenhuma delas produziria achado** e incluí-las
  seria ruído sem ganho de fidelidade. Fica registrado aqui como observação, não como `unverified`.
- `NAO-COMPROVADOS.md` **foi** regerado: saiu um `unverified` (`properties.securityRules[].id`).

### Estado no mapa

`azure/arm-network-security-group-rules` fechou em **27 colunas na spec, 16 documentadas, 16
emitíveis** (eram 25 colunas em spec; `topo` 16). O check Azure NSG em
`<doc-de-cobertura>.md` sai de *inferido* para *medido*: a superfície entrega, campo a campo,
tudo o que `AzureSecurityScanner` projeta — incluindo o `nsg.id` de que o comando de remediação
depende — e o estado agora produz achado de fato.
## Incremento 8 — Azure assessments: o check de Defender ganhou a superfície que ele lia (2026-10-18)

O `AzureSecurityScanner` do FinOps lê `security.assessments.list(scope="/subscriptions/{id}")`
e filtra por `properties.status.code`. **Não havia nenhuma superfície** com essa forma: o
`azure-sim` devolvia lista vazia e o renderer de continuous export entrega
`SecurityAlert`/`SecurityRecommendation`, que são outro objeto. Entrou
`azure/security-assessments-list` — **36 colunas** em 2 conjuntos (`assessment` 34,
`assessmentList` 2), envelope `SecurityAssessmentList` por assinatura, na api `2021-06-01`.

Fonte: [Assessments - List](https://learn.microsoft.com/en-us/rest/api/defenderforcloud-composite/assessments/list?view=rest-defenderforcloud-composite-stable).

### O estado precisa de um fato novo, e ele é opt-in

`NativeFinding` **não dá conta**: ele é, por definição, um problema, e o filtro do consumidor
descarta justamente o ramo que não é problema. Um assessment `Healthy` não tem finding, e um
`NotApplicable` não tem finding **por ser** o assessment que não se aplica ao tipo de recurso.

Por isso entrou `AzureDefenderAssessment` (`model/native.py`), chaveado por
`segment_uuid` e não por resource: o segmento é o único objeto Azure do estado com um id ARM
verdadeiro, e é ele que `properties.resourceDetails.id` e o `id` do assessment publicam.
A coleção entra **com default vazio** em `CanonicalEstate` — `Resource` e `NetworkSegment`
não mudaram, nada foi migrado, e por isso não foi preciso checkpoint de aprovação.

### Duas versões que foram **medidas e descartadas**, não presumidas

| Versão | Resultado medido no perfil `small`/seed 123 | Por que caiu |
|---|---|---|
| Derivar o estado dos achados (`NativeFinding` de categoria `NETWORK` no mesmo escopo → `Unhealthy`) | `Counter({'Unhealthy': 6, 'NotApplicable': 6})` — **nenhum `Healthy`** | o consumidor descarta **só** `Healthy`; o artefato nunca exercitava o descarte |
| Alternar pelo índice do **escopo** | o consumidor descartava `[0, 0, 2]` — dois envelopes de três sem nenhum descarte | os segmentos se agrupam em **assinaturas**, não em índices de escopo |
| **Alternar pelo índice do segmento DENTRO DA ASSINATURA** | cada envelope carrega os dois lados | é a unidade que a resposta entrega |

A regra que vale: **um check que nunca vê o ramo que ele tem de decidir não treina nada.** É a
mesma que obrigou o Incremento 7 a posturar 443/3389 em vez de deixar o NSG sem abertura.

### `NotApplicable` **não** é o ramo descartado

O pedido que originou este incremento supunha que `Healthy` **e/ou** `NotApplicable` seriam
o ramo que não vira achado. **Não é o caso**, e é medido no texto do filtro
(`if not status or status.code == "Healthy": continue`): só `Healthy` é descartado.
`NotApplicable` vira achado DEFENDER do mesmo jeito que `Unhealthy` — e a página o descreve
como *"Assessment for this resource did not happen"*, ou seja, uma verificação que **nem rodou**
entra na fila de achados. O estado entrega os três literais justamente para mostrar isso.

### A severidade mora em `properties.metadata.severity`

`properties.severity` **não existe** nesta resposta. Medido contra o SDK que o consumidor usa
(`azure-mgmt-security` 7.0.0, travado no `requirements.lock`):

- `SecurityCenter(cred, sub).assessments` resolve para a **api 2021-06-01** — o cliente multiapi
  declara `DEFAULT_API_VERSION = 2024-04-01`, mas `_get_api_version("assessments")` cai no
  único ramo compatível;
- o modelo devolvido é `SecurityAssessmentResponse`, que **achata** `properties.*` em atributos
  de topo (`display_name`, `status`, `metadata`);
- esse modelo **não tem atributo `properties`**: `assessment.properties.severity` levanta
  `AttributeError`, o `except Exception` externo engole, e o check inteiro devolve `[]`
  registrando `azure_defender_scan_failed`.

O fallback `"MEDIUM"` é **código morto**: `assessment.properties` é avaliado *antes* do
`getattr`. Mesmo corrigido o caminho, `"High"` precisaria de caixa alta como o achado
(`severity = severity.upper()`). O caminho correto por SDK é `assessment.metadata.severity`.

**Não corrigido aqui** — o FinOps é read-only nesta tarefa (regra inviolável nº 1).

→ Este é o **achado nº 3** da [seção canônica dos achados](INGESTAO-D3-SEGURANCA.md#achados-para-o-time-do-consumidor).

### O que fica vazio, e por quê

O **catálogo de avaliações** do Defender não é modelado pelo estado: `displayName`,
`description` (nos dois níveis), `categories`, `threats`, `implementationEffort`,
`userImpact`, `policyDefinitionId` e `preview` saem vazios. Os domínios estão publicados,
mas a página **não afirma a qual valor cada avaliação pertence**.

`status.cause` também sai vazio, e este é o caso-limite: o exemplo de resposta traz
`"cause": "OffByPolicy"`, mas **exemplo de payload fixa a forma do campo, não o vocabulário**.

E o efeito é visível e nomeado: o consumidor usa `display_name` como **título** do achado, então
o título sai vazio. É uma lacuna real, não um detalhe cosmético.

### Estado no mapa

`--matrix`: **gerado=45 falta=0 bloqueado=1 total=46** (as geradas eram 44; o total era 45).
`--audit azure`: a superfície entrega 4 arquivos, 4 registros, **17 caminhos documentados com
valor**, **0 colunas inventadas**, **0 obrigatórias vazias**.
`--ready azure`: `PRONTO: 9 superficies`. Teste golden: **34 testes**.

