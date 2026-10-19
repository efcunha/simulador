# config-describe-compliance-by-config-rule

Superfície `aws/config-describe-compliance-by-config-rule` — a resposta de
`config:DescribeComplianceByConfigRule`.

Esta spec é uma das **duas** superfícies de AWS Config, e elas não são a mesma coisa:

| Superfície | Granularidade | Pergunta que responde |
|---|---|---|
| `aws/aws-config-snapshot-s3` | uma linha por **recurso** (configuration item) | "como este recurso está configurado?" |
| `aws/config-describe-compliance-by-config-rule` (esta) | uma linha por **regra** | "o que as regras decidiram?" |

Uma tela de postura quer a segunda. Misturar as duas entregaria um agregado onde se espera um fato
por recurso, e vice-versa.

## 0. Qual superfície foi especificada, e por quê

O FinOps varre a nuvem com 4 checks AWS próprios — S3 público, Security Groups, IAM sem MFA e
**AWS Config**. Medido no ambiente real em 2026-10-16 (30 contas AWS), o check de AWS Config responde
por **14.531 dos 14.889 findings abertos (97,6%)** do backlog. É o check que mais importa, e era o
único dos quatro que o simulador não produzia de forma alguma: existia a API de *snapshot*, que não
carrega estado de conformidade por regra.

Medido também no simulador: **0 de 4 checks** eram produzíveis antes desta superfície.

A escolha de `DescribeComplianceByConfigRule` como porta de entrada resolve a dúvida de volume sem
decidir nada: a resposta traz **um item por regra**, não por recurso, com o número de recursos
culpados em `Compliance.ComplianceContributorCount.CappedCount`. O agregado que a AWS publica tem
a ordem de grandeza das centenas de regras gerenciadas; a expansão para milhares de findings é
**do consumidor**.

## 1. Identificação

- **Ação**: `DescribeComplianceByConfigRule` — AWS Config
- **Documento oficial**:
  - `DescribeComplianceByConfigRule` — https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeComplianceByConfigRule.html
  - forma `ComplianceByConfigRule` — https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceByConfigRule.html
  - forma `Compliance` — https://docs.aws.amazon.com/config/latest/APIReference/API_Compliance.html
  - forma `ComplianceContributorCount` — https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceContributorCount.html
  - lista de regras gerenciadas — https://docs.aws.amazon.com/config/latest/developerguide/managed-rules-by-aws-config.html
  - `s3-bucket-tagged` — https://docs.aws.amazon.com/config/latest/developerguide/s3-bucket-tagged.html
  - `lambda-function-tagged` — https://docs.aws.amazon.com/config/latest/developerguide/lambda-function-tagged.html
- **Data de consulta**: 2026-10-16
- **Referência de versão**: não há. A AWS Config não publica versão de schema para esta resposta.

## 2. Mecanismo e entrega

### 2.1 Isto NÃO é um export para um artefato durável

`delivery.kind = read_api`. O AWS Config não publica nenhum artefato durável para esta ação, e a
seção `Request Parameters` da página documenta exatamente três parâmetros — `ComplianceTypes`,
`ConfigRuleNames` e `NextToken` — nenhum deles de entrega. Não existe `bucket`/`prefixo`/`chave`
onde esta resposta vá parar: ela vive na chamada.

### 2.2 Encoding da resposta

**A codificação entregue é a codificação documentada.** A seção `Response Syntax` da página da ação
publica JSON:

```json
{
   "ComplianceByConfigRules": [
      {
         "Compliance": {
            "ComplianceContributorCount": {
               "CapExceeded": boolean,
               "CappedCount": number
            },
            "ComplianceType": "string"
         },
         "ConfigRuleName": "string"
      }
   ],
   "NextToken": "string"
}
```

Vale registrar o contraste, porque ele muda a leitura: a superfície irmã
`aws/ec2-describe-instances` tem o mesmo `delivery.kind = read_api` e a mesma decisão de emitir
JSON, mas lá a API Reference publica a resposta em **XML** apenas, e a divergência entre o
documentado e o entregue precisa ser declarada na spec. Aqui não há divergência: `format = json`
porque é o que a AWS publica.

Uma diferença menor de grafia: a `Response Syntax` escreve `"CappedCount": number`, enquanto a
página do campo declara `Type: Integer`. Adotado o tipo **declarado pela página do campo**, que é a
fonte da verdade do conjunto `compliance-contributor-count`.

### 2.3 Escopo de um envelope

A resposta **não publica** conta nem região em nenhum campo. O agrupamento por `(conta, região)` que
o renderer faz é uma projeção do escopo do próprio estate — o AWS Config configura recorder e
regras por conta **e** por região — e não um campo documentado. Registrado em `unverified`.

### 2.4 Artefatos entregues

Cinco arquivos, um por conjunto documentado, mais o relatório irmão:

| Arquivo | Conjunto |
|---|---|
| `describe-compliance-by-config-rule-response.json` | `describe-compliance-by-config-rule-response` |
| `compliance-by-config-rule.json` | `compliance-by-config-rule` |
| `compliance.json` | `compliance` |
| `compliance-contributor-count.json` | `compliance-contributor-count` |
| `request-parameters.json` | `request-parameters` |
| `_provenance.json` | relatório irmão (nunca dentro do artefato) |

Um arquivo por conjunto é o que torna a conferência campo a campo possível: `columns_of` lê as
chaves de **topo** de um JSON, e achatados por conjunto cada arquivo carrega exatamente os membros
do seu próprio contrato.

## 3. Campos

### 3.1 Elementos de topo da resposta

| Campo | Tipo | Obrigatório | Restrição publicada |
|---|---|---|---|
| `ComplianceByConfigRules` | array de `ComplianceByConfigRule` | Não | — |
| `NextToken` | String | Não | token de paginação |

Fonte: https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeComplianceByConfigRule.html

### 3.2 Objeto `ComplianceByConfigRule`

| Campo | Tipo | Obrigatório | Restrição publicada |
|---|---|---|---|
| `Compliance` | objeto `Compliance` | Não | — |
| `ConfigRuleName` | String | Não | comprimento 1 a 64 |

Fonte: https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceByConfigRule.html

### 3.3 Objeto `Compliance`

| Campo | Tipo | Obrigatório | Restrição publicada |
|---|---|---|---|
| `ComplianceType` | String | Não | `COMPLIANT \| NON_COMPLIANT \| NOT_APPLICABLE \| INSUFFICIENT_DATA` — **ver 5.1** |
| `ComplianceContributorCount` | objeto `ComplianceContributorCount` | Não | — |

Fonte: https://docs.aws.amazon.com/config/latest/APIReference/API_Compliance.html

Semântica publicada na mesma página, que é o que o renderer aplica:

> A rule is compliant if all of the resources that the rule evaluates comply with it. A rule is
> noncompliant if any of these resources do not comply.

> AWS Config returns the INSUFFICIENT_DATA value when no evaluation results are available for the
> AWS Config rule.

### 3.4 Objeto `ComplianceContributorCount`

| Campo | Tipo | Obrigatório | Restrição publicada |
|---|---|---|---|
| `CapExceeded` | Boolean | Não | "se o máximo foi atingido" — **o máximo não é publicado** (ver 4.1) |
| `CappedCount` | Integer | Não | recursos que **causam** `NON_COMPLIANT` |

Fonte: https://docs.aws.amazon.com/config/latest/APIReference/API_ComplianceContributorCount.html

> The number of AWS resources or AWS Config rules that cause a result of `NON_COMPLIANT`, up to a
> maximum number.

Duas leituras que decorrem disso e que mudam o número emitido:

1. uma regra `COMPLIANT` carrega **`CappedCount = 0`** — nenhum recurso a fez não-compliance;
2. contar os recursos **avaliados** seria um número diferente, e um que a documentação não publica.

### 3.5 Parâmetros de requisição documentados

| Campo | Tipo | Obrigatório | Restrição publicada |
|---|---|---|---|
| `ComplianceTypes` | array de strings | Não | 0 a 3 itens; Valid Values com 4 valores |
| `ConfigRuleNames` | array de strings | Não | 0 a 25 itens; comprimento 1 a 128; Pattern `[A-Za-z0-9_-]+` |
| `NextToken` | String | Não | paginação |

Fonte: https://docs.aws.amazon.com/config/latest/APIReference/API_DescribeComplianceByConfigRule.html

`NextToken` aparece nos **dois** lados — lido na resposta, enviado na requisição. Por isso são dois
conjuntos, e não um nome repetido dentro de um só.

### 3.6 Os nomes de regra

`ConfigRuleName` carrega o nome de uma **regra gerenciada real** do AWS Config. Não é um campo livre
do qual o consumidor escolhe: é o identificador da regra cujo veredito vem ao lado.

O catálogo do renderer tem **14 regras**, todas conferidas uma a uma na lista oficial
(`managed-rules-by-aws-config.html`, 838 nomes, lida em 2026-10-16), cobrindo os quatro domínios:

| Domínio | Regras |
|---|---|
| Exposição pública de S3 | `s3-bucket-public-read-prohibited`, `s3-bucket-public-write-prohibited`, `s3-bucket-level-public-access-prohibited` |
| Rede | `restricted-ssh`, `restricted-common-ports`, `vpc-default-security-group-closed`, `vpc-flow-logs-enabled` |
| Identidade | `root-account-mfa-enabled`, `iam-password-policy`, `access-keys-rotated` |
| Auditoria e guardrails | `cloudtrail-enabled`, `securityhub-enabled` |
| Etiquetagem (avaliadas do estado) | `s3-bucket-tagged`, `lambda-function-tagged` |

Isso é uma decisão, não um detalhe. O lado do produto (`<raiz-do-consumidor>/emulators/aws-sim`) usa nomes
sintéticos `synth-required-tags` / `synth-iac-managed`. Nomes sintéticos servem de stub e **não**
serviriam para conferir uma tela de postura real contra um catálogo verdadeiro.

O parâmetro `requiredKeyTags`, que as duas regras etiquetadas aceitam, **não pertence a esta
superfície**: ele é parâmetro da regra, não campo da resposta.

## 4. Campos não comprovados

### 4.1 O teto que `CappedCount` trunca e que `CapExceeded` compara

`CapExceeded` é documentado como *"Indicates whether the maximum count is reached"*, mas a página
**nunca publica esse máximo** — diz apenas *"up to a maximum number"*. Sem o teto, a comparação não
é reproduzível a partir da documentação.

Consequência: `CapExceeded` vai **`null`** em todos os 126 itens, com o motivo no relatório irmão.
`CappedCount` continua real, porque é uma contagem do modelo. Escrever `false` afirmaria que nenhum
teto foi atingido — o que é uma afirmação sobre um número que a documentação não publica.

### 4.2 Ausência de exemplo oficial de payload

A página da ação publica `Response Syntax`, mas nenhum exemplo preenchido. A estrutura dos artefatos
vem da `Response Syntax` e da seção `Request Parameters`, não de um exemplo.

### 4.3 Escopo `(conta, região)` não é campo documentado

Ver 2.3.

### 4.4 As doze regras que o modelo não alcança

Isto não é um campo não comprovado, é a lacuna do modelo de cada regra, e vai para
`_provenance.json`. Resumo:

| Regra | O que o estate não carrega |
|---|---|
| `s3-bucket-public-read-prohibited`, `...-write-`, `...-level-public-access-` | ACL de bucket e public-access-block |
| `restricted-ssh`, `restricted-common-ports` | **as REGRAS do security group da AWS** |
| `vpc-default-security-group-closed` | associação do SG padrão e suas regras |
| `vpc-flow-logs-enabled` | VPC existe; o fato avaliado (flow logs) não |
| `root-account-mfa-enabled`, `iam-password-policy`, `access-keys-rotated` | **nenhuma entidade de IAM no modelo** |
| `cloudtrail-enabled` | CloudTrail não é um tipo de recurso do estate |
| `securityhub-enabled` | o estate não modela inscrição de serviço |

`restricted-ssh` merece registro porque é a armadilha mais fácil de cair: o estate **tem** 15
recursos `security_group`, mas `model/network.py` popula `NetworkSegment.network_security_group`
**só para a Azure** e deixa `None` na AWS. O recurso existe; a regra, não tem o que ler.

## 5. Divergências conhecidas

### 5.1 `NOT_APPLICABLE` está no enum e não é suportado pelo tipo

A linha de Valid Values do campo `ComplianceType` lista quatro valores:

```
COMPLIANT | NON_COMPLIANT | NOT_APPLICABLE | INSUFFICIENT_DATA
```

E a **mesma página**, no parágrafo que descreve o tipo, afirma:

> For the `Compliance` data type, AWS Config supports only `COMPLIANT`, `NON_COMPLIANT`, and
> `INSUFFICIENT_DATA` values. AWS Config does not support the `NOT_APPLICABLE` value for the
> `Compliance` data type.

Os dois lados ficam registrados; **a escolha é do renderer e está declarada**: `NOT_APPLICABLE` nunca
é emitido, e isso é uma constante no código (`NOT_APPLICABLE_EMITTED = False`), não só prosa.

A página da ação fecha o ciclo: uma regra cuja Lambda devolveu `NOT_APPLICABLE` em **todas** as
avaliações é reportada como `INSUFFICIENT_DATA`.

E há uma assimetria real que torna a confusão fácil: o **filtro de requisição** `ComplianceTypes`
**aceita** `NOT_APPLICABLE`. Só a resposta é que não.

### 5.2 Um escopo sem recurso não pode virar `COMPLIANT`

O estate coloca cada tipo de recurso AWS em **uma única região** por conta (buckets em `us-west-2`,
Lambda em `sa-east-1`, security groups em `us-east-1`). Com nove escopos `(conta, região)`, a
maioria não tem bucket nenhum.

Três respostas possíveis, e só uma é defensável:

- `COMPLIANT` — **errado**: uma regra sem recurso não avaliou tudo;
- `NOT_APPLICABLE` — **indisponível**: ver 5.1;
- `INSUFFICIENT_DATA` — **o terceiro caso documentado**, e o que o renderer emite.

### 5.3 O nome da regra e o tipo do recurso

A página de cada regra publica um campo `Resource Types:` com o tipo no formato CloudFormation
(`AWS::S3::Bucket`). O renderer **não** afirma esse tipo para as doze regras que não avalia, porque
não leu a página de cada uma delas e não tem uso para um tipo que não consegue ler. Só as duas
regras efetivamente avaliadas declaram o `resource_type` que consomem do modelo.