# D3 — Ingestão de segurança: do simulador para a tabela `findings`

**Status em 2026-10-16: reescrito. A versão anterior partia de uma premissa errada.**

---

## Achados para o time do consumidor

**Seção canônica dos 3 achados de produto** que a medição das superfícies de postura expôs. Os
outros documentos deste repositório **apontam** para cá; o detalhe de cada achado continua escrito
onde nasceu e **não é duplicado** abaixo.

Os caminhos do consumidor são relativos a `<arvore-do-consumidor>`.

| # | Achado | Consumidor (file:line) | Sintoma | Correção de uma linha | Onde o detalhe está |
|---|---|---|---|---|---|
| 1 | Nome de regra com hífen a mais | `aws/security.py:721` (fn `_config_rule_severity`, def em `:701`) | `high_patterns` traz `cloud-trail-enabled`; o nome real é `cloudtrail-enabled`. O padrão casa com **0 dos 838** nomes gerenciados, então a regra real cai no `return "MEDIUM"` (`:746`) em vez do `HIGH` pretendido. | `cloud-trail-enabled` → `cloudtrail-enabled` | [§Incremento 4.3, neste doc](#o-defeito-do-consumidor-que-a-medição-tornou-visível) · <doc-de-cobertura>.md §G2 |
| 2 | Regras implícitas da VPC não são listáveis | `gcp/security.py:114` (fn `_list_open_firewalls`) | A GCP documenta que toda rede VPC tem **duas** regras implícitas — `ingress-deny-all` e `egress-allow-all`, prioridade 65535. Elas **não são recursos** e `firewalls.list` **não as devolve**: o scanner varre a lista e nunca vê a regra que protege a rede. | — **achado estrutural da API**, não defeito de uma linha: não existe correção de uma linha | <doc-de-cobertura>.md §2 · [NAO-COMPROVADOS.md, `gcp/compute-firewalls`](NAO-COMPROVADOS.md#gcpcompute-firewalls--6-itemns) (tema `as duas regras implícitas de toda rede VPC`) |
| 3 | Severidade do Defender lida de um caminho que não existe | `azure/security.py:153` (fn `_list_defender_findings`, def em `:142`) | `assessment.properties.severity` levanta `AttributeError`: o modelo `SecurityAssessmentResponse` (api 2021-06-01) **achata** `properties.*` em atributos de topo e **não tem** atributo `properties`. O `except Exception` externo engole, `_list_defender_findings` devolve `[]` e o check loga `azure_defender_scan_failed` (`:171`). O fallback `"MEDIUM"` é **código morto** — `assessment.properties` é avaliado *antes* do `getattr`. | `assessment.properties.severity` → `assessment.metadata.severity` | [§Incremento 8, neste doc](#incremento-8--o-check-de-assessments-da-azure-ganhou-a-superfície-que-ele-lia-2026-10-18) · <doc-de-cobertura>.md §Incremento 8 |

**Nenhum dos três foi corrigido aqui.** O FinOps é read-only nesta tarefa (regra inviolável nº 1
de [ESTADO.md](ESTADO.md)): os três são **para o time de lá**, registrados, medidos e não
corrigidos. O achado 2 é o único que **não** tem correção de uma linha — a GCP não expõe as regras
implícitas em `firewalls.list`, e nenhum simulador os entregaria sem inventar um recurso que a
documentação não publica.

---

## 1. A correção que reescreve esta spec

A primeira redação deste documento mapeava o **ASFF** (`AwsSecurityFinding`) para a tabela
`findings`. Isso partia da suposição de que o FinOps **consome o export do Security Hub**. A
leitura do código e a navegação na aplicação desmentem isso.

**O FinOps varre a nuvem com scanners próprios.** `scan_security.py (modulo do consumidor)` chama
`AWSSecurityScanner(client).run_full_scan(...)` por conta, e o resultado vira linha em `findings`.
Não existe nenhum leitor de ASFF, de OCSF, de CSV, nem de Security Hub no produto — a varredura foi
confirmada por busca no código e pela tela de Segurança, que descreve os checks um a um.

E há uma consequência mais séria: **o simulador não produz nenhum dos quatro checks.** Detalhado
na §4. Esta spec deixou de ser "uma ponte" e passou a ser "modelar um domínio novo".

| | a versão anterior dizia | o que é verdade |
|---|---|---|
| origem | export ASFF do Security Hub | os 4 checks próprios do produto |
| acerto | "construção do zero" | mantém-se, mas por outro motivo — e agora com a causa nomeada |
| estratégia | mapear campos existentes | modelar os primitivos que os checks leem |

---

## 2. Os 4 checks, e o que cada um lê da AWS

Fonte: `security.py (modulo do consumidor)`, 746 linhas.

| # | Check | API da AWS | Fingerprint (`scan_security.py`) |
|---|---|---|---|
| 1 | **S3 público** | `s3.list_buckets`, `get_bucket_acl`, `get_bucket_policy`, `get_public_access_block`, `get_bucket_location` | `s3.anonymous_policy` |
| 2 | **Security Groups** | `ec2.describe_regions`, `ec2.describe_security_groups` (paginator por região) | `ec2.security_group.open_all` / `ec2.security_group.open_port.<N>` |
| 3 | **IAM sem MFA** | `iam.get_credential_report` (com fallback por usuário) | `iam.user.mfa_required` |
| 4 | **AWS Config** | `config.describe_compliance_by_config_rule(ComplianceTypes=["NON_COMPLIANT"])` | `config.<rule_name>` |

No GCP, o produto tem dois checks próprios — **Security Command Center** e **Firewall Rules** — que
na tela de 2026-10-16 apareciam ambos como `0 ✓ limpo`.

## 3. O que a tabela `findings` exige

19 colunas, `UNIQUE(workspace_id, fingerprint)`, nove `NOT NULL` sem default.
`SecurityFindingAdapter.from_dict(row) → Finding(**row)` exige que **as chaves do dict sejam
exatamente os nomes das colunas ORM**.

O que a tela mostra por finding — e portanto o que precisa existir: **severidade**, **CVSS**,
**idade/SLA** ("2d 13h restantes"; Crítico 24h · High 72h · Medium 7d · Low 30d), **origem**
(`CONFIG`), **região** (`us-east-1`), **recurso** (`AIDA3M3X…`, `ALBAccessLogsMonitor`).

O vocabulário já bate, e isso foi medido: `_SEVERITY_TO_RISK` do adapter usa
`CRITICAL | HIGH | MEDIUM | LOW | INFORMATIONAL`, **exatamente** o `Valid Values` do
`Severity.Label` do ASFF, e normaliza com `.upper()`; `_category_to_complexity` cai em `MODERATE`.
O contrato foi feito para tolerar a entrada.

## 4. O que o simulador tem hoje — medido, não estimado

> **Atualizado em 2026-10-16.** Este texto já foi atualizado três vezes no mesmo dia: pela entrega de
> `aws/config-describe-compliance-by-config-rule` (Incremento 1), pela de
> `aws/ec2-describe-security-groups` (Incremento 2) e pelas quatro de bucket do **Incremento 3**
> (`s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`, `s3-get-public-access-block`).
> O veredicto passou de **0 de 4** para **1**, depois **2**, e agora **3 de 4** checks produzíveis.

| Check | Antes | Agora | Por quê |
|---|---|---|---|
| 1. S3 público | **NÃO** | **SIM** | o Incremento 3 entregou as quatro superfícies do bucket: ACL (`GetBucketAcl`, com `Grant`/`Grantee` e `Permission`), bucket policy (`GetBucketPolicy`), Block Public Access (`GetPublicAccessBlock`, os quatro booleanos) e a listagem por conta (`ListBuckets`). O que faltava — "quem pode ler ou escrever este bucket" — passou a ser fato do modelo |
| 2. Security Groups | **NÃO** | **SIM** | o Incremento 2 entregou `aws/ec2-describe-security-groups`: `SecurityGroup` com `IpPermissions`/`IpPermissionsEgress`, cada regra com `ipProtocol`, `fromPort`/`toPort` e a origem. É a mesma forma que o check da Azure já lia em `azure/arm-network-security-group-rules` |
| 3. IAM sem MFA | **NÃO** | **NÃO** | não há superfície de IAM; `NativeFinding.category` chega a `IAM` como rótulo, mas nada atrás dele. `root-account-mfa-enabled`, `iam-password-policy` e `access-keys-rotated` ficam `INSUFFICIENT_DATA` pelo mesmo motivo |
| 4. AWS Config | **PARCIAL** | **SIM** | era só `aws/aws-config-snapshot-s3`, que é a API de *snapshot*. Passou a existir `aws/config-describe-compliance-by-config-rule`, que é a resposta de conformidade **por regra** |

E há um fato estrutural que explica o resto: **o simulador tem findings no modelo e nenhuma
superfície que os entregue.** `NativeFinding` existe e é consumido pelo renderer ASFF, mas as 13
superfícies AWS do repositório são `aws-config-snapshot-s3`,
`config-describe-compliance-by-config-rule`, `bcm-data-exports-cur2`,
`bcm-data-exports-focus12`, `ec2-describe-instances`, `ec2-describe-security-groups`,
`s3-list-buckets`, `s3-get-bucket-acl`, `s3-get-bucket-policy`, `s3-get-public-access-block`,
`security-hub-asff`, `security-hub-ocsf-export` e `vpc-flow-logs-s3` — a entrega do Incremento 1
deu estado de conformidade por regra, a do Incremento 2 deu a postura de rede, a do Incremento 3 deu
a postura de bucket, mas ainda **não** é um fluxo de findings de segurança com recurso avaliado.

**Veredicto: 3 de 4 checks são produzíveis** (eram 0). A superfície errada continua sendo
`aws/security-hub-asff`: ela entrega findings no formato do Security Hub, e o produto não lê
Security Hub.

### O que o Incremento 3 acrescenta à ponte, e o que ele não resolve

O check de S3 público lê hoje as **regras de conformidade** do AWS Config, e é por isso que o
Incremento 3 não o torna "parcialmente bom": com a ACL, a policy e o block modelados, as **três**
regras gerenciadas de exposição (`s3-bucket-public-read-prohibited`,
`s3-bucket-public-write-prohibited`, `s3-bucket-level-public-access-prohibited`) saem de
`INSUFFICIENT_DATA` e passam a responder `COMPLIANT` **e** `NON_COMPLIANT` no mesmo estado.

O que a superfície entrega a um escritor de findings:

- **`resource_id` / `resource_type` / `region`** — pela junção por posição descrita na
  `_provenance.json` de cada artefato (`response_order`, com a tripla conta/região/bucket);
- **`description` / `evidence`** — os `Grant` com `Permission` e o `URI` do grupo, e os
  `Statement` da policy com `Effect`, `Action` e `Principal`;
- **`exposure`** — os quatro booleanos do `PublicAccessBlockConfiguration`, que são a postura
  efetiva do bucket e não um rótulo derivado.

Duas limitações continuam, e são do **modelo**, não do contrato:

- **a data de criação do bucket é derivada.** `s3_bucket` não é medido — não há linha de consumo
  de onde a data viesse — então a `CreationDate` sai de um hash do próprio recurso, num intervalo
  fixo. Está na proveniência como derivação;
- **o public access block de nível de CONTA não é modelado.** A página do `GetPublicAccessBlock` é
  explícita: a operação devolve *"the bucket-level configuration only"*, e na avaliação o S3 usa a
  combinação mais restritiva entre o block do bucket e o da conta. O check que quiser o efeito de
  nível de conta continua sem fonte, e a limitação está declarada na proveniência do artefato.

### O que o Incremento 2 acrescenta à ponte, e o que ele não resolve

A superfície `aws/ec2-describe-security-groups` dá ao check de Security Groups exatamente o que
ele filtra: `direction` (a lista `IpPermissions` **ou** `IpPermissionsEgress`) e a origem da
regra. Duas limitações continuam e são do **modelo**, não do contrato:

- **a VPC de cada grupo é uma derivação.** O estate não liga security group a VPC — os recursos
  `vpc` e `security_group` vivem em regiões diferentes — e o `vpcId` emitido vem do segmento de
  rede do mesmo (conta, região). Está marcado `TODO-verificar` na proveniência;
- **`securityGroupArn` vai `null`**, porque o ARN precisa da partição e o modelo não a carrega.

E há uma consequência direta do lado do AWS Config: com as regras agora modeladas,
`restricted-ssh`, `restricted-common-ports` e `vpc-default-security-group-closed` saíram de
`INSUFFICIENT_DATA` e passaram a responder com o texto da página de cada regra. Medido no estate
pequeno (seed 123): cada uma dá **2 escopos `COMPLIANT` e 1 `NON_COMPLIANT`**, e 6
`INSUFFICIENT_DATA` — os escopos sem nenhum security group, que é o caso "nada avaliado".

**O que a nova superfície já entrega de útil**, e que responde direto ao check de AWS Config:
14 regras gerenciadas **reais** (conferidas na lista oficial), com veredito por regra e o número de
recursos culpados. No estate `small`, seed 123, são 126 itens: 2 `COMPLIANT`, 4 `NON_COMPLIANT` e
120 `INSUFFICIENT_DATA` — os 120 são as regras cujo fato o modelo não carrega, cada uma com o motivo
registrado. Os vereditos reais vêm de `s3-bucket-tagged` e `lambda-function-tagged`, cujas páginas de
regra enunciam a condição sem parameterização.

**O que ainda falta para os outros três**, e a ordem de custo:

1. **Bucket S3 com postura** — ACL (`PublicRead`/`PublicReadWrite`), policy (acesso anônimo),
   public-access-block ligado/desligado, região.
2. **Security Group da AWS com ingress** — portas, origem (`0.0.0.0/0` ou não), VPC/grupo pai.
3. **Usuário IAM com MFA** — nome, MFA ligado/desligado, último uso.
4. **Regra AWS Config com estado** — nome da regra, `NON_COMPLIANT`, recurso avaliado, id da regra.

Cada um com a mesma disciplina de hoje: o nome do campo vem da documentação da AWS, o valor vem do
estado, e o que a fonte não publica fica declarado. **Nada disso é leitura de evidência — é
modelagem, e é decisão de produto**: o simulador passa a representar postura de segurança, não só
custo.

## 6. O que já está entregue e onde isso vale

O `commit b3dd315` H-18 fez o simulador carregar `category`, `evidence`, `exposure`, `impact` e
`fingerprint` no `UserDefinedFields` do ASFF, para que o consumidor não fabricasse dado que o
produtor tem. **Isso continua válido** se a ponte passar pelo ASFF — e passa a ser o *molde* do que
a nova superfície de findings deve carregar: as mesmas cinco chaves, os mesmos nomes, a impressão
ainda recalculável a partir do documento.

O resto continua igual: 13 diretas · 1 derivação de cardinalidade · 1 de vocabulário · 2 chaves
estrangeiras (`workspace_id`, `cloud_account_id`) · **0 ausentes**.

## 7. Sequência

O D3 **não depende** do trio `D6 → D2 → D5` e pode correr em paralelo. Mas a §5 é pré-requisito de
tudo: sem um check que produza finding, não há o que ingerir. O caminho mais curto é:

1. **Check 4 (AWS Config) primeiro.** É o de maior volume real (14.531 de 14.889 findings na conta
   de produção) e o mais simples de modelar: nome da regra, estado, recurso avaliado.
2. **Check 2 (Security Groups)** em seguida — o segundo maior (191) e o que mais alimenta o
   `ec2.security_group.open_port.*`.
3. **Checks 1 e 3** por último: 165 e 2 findings, e o de IAM é o mais pobre em sinal.

Nada aqui toca a regra nº 1: a escrita é no FinOps, e quem executa é o time de lá. O que este
lado entrega é o contrato e a evidência.
## Incremento 4 — o check de IAM ganhou a superfície que ele lia (2026-10-18)

Este documento descreve o **lado do contrato**, não a escrita: a escrita é no FinOps, e quem
executa é o time de lá. O que mudou aqui é que o check de IAM deixou de esperar por uma
superfície que não existia.

### O que era

O check de IAM era o mais pobre em sinal — e a causa não era o check. Era que o lado do contrato
oferecia a **política de senha da conta** (que é um requisito de configuração) e nenhuma
superfície com **as identidades**. O consumidor faz o cruzamento de MFA por usuário; sem o
credential report, ele não tinha o que cruzar.

### O que passou a existir

| Superfície | O que entrega | Quem lê |
|---|---|---|
| `aws/iam-get-credential-report` | 23 colunas CSV: identidades, senha, MFA, idade das chaves, e a linha da conta root | o cruzamento de MFA por usuário |
| `aws/iam-get-account-password-policy` | os 10 membros de `PasswordPolicy`, com `ExpirePasswords` derivado | `iam-password-policy` |
| `gcp/observability-partial` | a mesma leitura pedida num escopo de projeto inteiro, respondida em parte, com `missing.json` | "e se a leitura fosse só de um subconjunto?" |

### Três decisões de contrato que valem para o check

1. **`ExpirePasswords` é derivado, não independente.** A página do tipo define o membro por meio
   de `MaxPasswordAge`. Traduzir os dois como fatos separados admitiria `ExpirePasswords: true`
   ao lado de um `MaxPasswordAge` ausente — um estado que a AWS nunca devolve;
2. **o literal `N/A` é um estado.** No credential report, `N/A` significa que o objeto **não
   existe** (usuário sem senha, chave inexistente), `not_supported` aparece **só** na linha da
   raiz, e `no_information` é um terceiro valor ("a senha nunca abriu um site da AWS"). Se o
   check traduzir qualquer um deles para `null`, ele perde a diferença entre "este usuário não
   tem senha" e "esta coluna veio vazia";
3. **o boolean do CSV é `TRUE`/`FALSE`, em maiúsculo.** Todos os outros artefatos do repositório
   são JSON e grafam `true`/`false`. Um check que compare com `true` lê a conta inteira como
   `false` — e inverte o achado em silêncio, sem erro nenhum.

### O que este lado não faz

Nada aqui escreve no FinOps, e nada aqui decide quando o check passa a ler. A política de
ingestão da §4 continua sendo a decisão do time de lá; o que este lado entrega é a superfície
fiel e a evidência de por que ela é fiel.

## Incremento 4.3 — o resíduo de Config fecha, e nenhuma superfície nova (2026-10-18)

Este incremento fecha as **três** últimas regras de Config que respondiam `INSUFFICIENT_DATA` em
todos os escopos. O headline para o lado do contrato é negativo, e é o resultado importante:
**nenhuma superfície nova foi criada**.

### Por que nenhuma superfície nova

A pergunta que a §4 deste documento responde primeiro — "o check do produto lê isto por uma chamada
própria?" — foi conferida no consumidor, em leitura:
`security.py (modulo do consumidor)`.

O arquivo **não** contém `DescribeTrails`, `GetEnabledStandards` nem `DescribeVpcFlowLogs`. O que
ele contém é `_config_rule_severity(rule_name)`, que classifica a severidade por **substring** do
`ConfigRuleName` que vem no payload de `DescribeComplianceByConfigRule`.

Conclusão: **o payload de conformidade do Config já é o canal pelo qual o produto lê as três
regras.** Entregar `cloudtrail:DescribeTrails` ou `securityhub:DescribeHub` aqui seria uma
superfície que ninguém consome. O `fidelity/matrix.py` não ganhou linha, e `--matrix` segue em
`gerado=43 falta=0` — o mesmo número de antes.

### O que o check ganha, em contrato

As três regras passam a trazer veredito real. O que o check precisa saber para não ler errado:

| Regra | O que o veredito significa | O que **não** significa |
|---|---|---|
| `cloudtrail-enabled` | a conta tem ao menos uma trilha | não é o número de trilhas, nem o bucket, nem o log group — o renderer não passa os três parâmetros opcionais |
| `securityhub-enabled` | o Security Hub está inscrito na conta | não diz nada sobre findings, standards ou agregadores — não são modelados |
| `vpc-flow-logs-enabled` | **por VPC**: alguma VPC do escopo está sem flow log | `CappedCount` é a **contagem de VPCs sem log**, não de VPCs avaliadas |

O terceiro é o que mais importa para o consumidor: é a única regra do catálogo que é
`NON_COMPLIANT` por **uma** VPC entre várias. Um check que tratasse o `ComplianceType` da regra
como "o escopo inteiro é não conforme" perderia a contagem, que está em `CappedCount`.

### Os três `INSUFFICIENT_DATA` que continuam, e por que não são bug

`vpc-flow-logs-enabled` ainda devolve `INSUFFICIENT_DATA` em **6 dos 9 escopos**, e isso não é
lacuna de modelo: o estate põe os 15 recursos `vpc` em uma região só por conta, então 6 escopos
não têm VPC nenhuma. A API reporta o colapso `NOT_APPLICABLE` como `INSUFFICIENT_DATA`.

O check **não** deve tratar esse valor como "não sabemos" quando há VPC no escopo, nem como
"tudo certo". No escopo que tem VPC, uma VPC sem flow log é `NON_COMPLIANT` com `CappedCount`
≥ 1 — e é assim que o achado se distingue de um escopo que simplesmente não tinha o que avaliar.

### O defeito do consumidor que a medição tornou visível

`_config_rule_severity` tem `cloud-trail-enabled` (com hífen) em `high_patterns`. O nome real é
`cloudtrail-enabled`, **sem** hífen — a página avisa que *"the rule identifier
(CLOUD_TRAIL_ENABLED) and rule name (cloudtrail-enabled) are different"*. O padrão casa com
**zero** nomes do catálogo, então a regra real cai no `return "MEDIUM"` do fim da função em vez
do `HIGH` pretendido. Já documentado no `<doc-de-cobertura>.md` (G2) com base em 838 nomes,
quando nenhuma das três existia aqui; este incremento dá a **primeira ocorrência real**.

**Não corrigido aqui** — o FinOps é read-only nesta tarefa, e a correção é do lado de lá.

→ Este é o **achado nº 1** da [seção canônica dos achados](#achados-para-o-time-do-consumidor).

## Incremento 7 — o check de NSG da Azure ganhou o campo de que a remediação depende (2026-10-18)

### O que era

O check `_list_open_nsgs` (`security.py (modulo do consumidor):103`) já
tinha uma superfície do simulador — `azure/arm-network-security-group-rules` — mas a auditoria de
fidelidade encontrou que ela **não entregava o `nsg.id`**, que é o campo de que duas linhas do
achado dependem:

```python
resource_id=nsg.id or nsg.name,                                    # security.py:121
... f"--resource-group {nsg.id.split('/')[4] if nsg.id else ''}"   # security.py:125
```

Sem o campo: o `resource_id` caía no **nome** do NSG (um id que não é clicável em nenhum lugar), e o
`remediation_command` — que é o que o operador copia para o terminal — saía com `--resource-group`
**vazio**. Medido: `nsg.id` ausente em **6/6** NSGs entregues.

### O que mudou no contrato

A coluna `id` entrou no conjunto `networkSecurityGroup` da spec, e o renderer passou a emiti-la a
partir de `NetworkSecurityGroup.arm_id()` — o **mesmo** método que já compunha o caminho do arquivo,
o que torna divergência entre "id do recurso" e "caminho do blob" estruturalmente impossível.

O `properties.securityRules[].id`, que estava em `unverified`, saiu de lá: a página REST publica o
objeto `Security Rule` com `id | string | Resource ID.` e o exemplo do GET fixa a forma
`<id-do-NSG>/securityRules/<nome>`. A leitura anterior era verdadeira para a página de *template* e
falsa para a fonte que o consumidor realmente chama.

### O achado que muda a ponte: o check nunca disparava

Rodando a lógica **real** do consumidor (filtro completo + `_parse_ports` + `_CRITICAL_PORTS`) sobre
os artefatos, a postura anterior produzia **0 achados em 6/6 NSGs**. A 443 não está no dicionário de
portas críticas do consumidor, e a 3389 — que está — era uma `Deny`, descartada antes de a porta ser
lida. O estado expunha uma porta de qualquer origem e a assinatura saía limpa.

Entrou `AllowInternetInboundSsh` (`Internet` → `22`), e a medição passou a **6 achados**. Isso importa
para a ponte porque é o caso em que um estado internamente coerente produz **silenciosamente** a
assinatura que o scan quer evitar: nenhum teste que confira só o par `direction`/`access` — que era o
que existia — enxergaria a diferença.

### O que este lado não faz

A projeção no `azure-sim` (`projections/network.py`, que ainda devolve `[]` por desenho) é escrita do
time do FinOps — regra inviolável nº 1. O que muda é que ela passa a ter, do lado do estado, um
artefato fiel **e** que produz achado, com `resource_id` e `remediation_command` corretamente formados.
## Incremento 8 — o check de assessments da Azure ganhou a superfície que ele lia (2026-10-18)

**Achado para o time do FinOps, e ele é de severidade, não de estilo:** o
`AzureSecurityScanner` **não produz achado nenhum** hoje, e não por falta de dado no simulador.

Lendo `security.assessments.list(scope="/subscriptions/{id}")`, ele descarta o que tem
`properties.status.code == "Healthy"` e, para o resto, monta o achado. A linha que lê a
severidade é `getattr(assessment.properties, "severity", "MEDIUM") if assessment.properties else "MEDIUM"`.

Medido em 2026-10-18 contra o SDK que o próprio FinOps usa (`azure-mgmt-security` 7.0.0,
travado em `consumidor/requirements.lock`):

| Fato | Medido como |
|---|---|
| api-version resolvida por `SecurityCenter(cred, sub).assessments` | **2021-06-01** — o cliente multiapi declara `DEFAULT_API_VERSION = 2024-04-01`, e `_get_api_version("assessments")` cai no único ramo compatível |
| modelo devolvido | `SecurityAssessmentResponse`, que **achata** `properties.*` em atributos de topo |
| `assessment.properties` | **não existe** → `AttributeError: 'SecurityAssessmentResponse' object has no attribute 'properties'` |
| efeito | o `except Exception` externo engole, `_list_defender_findings` devolve `[]` e o check registra `azure_defender_scan_failed` |
| o fallback `"MEDIUM"` | **código morto** — `assessment.properties` é avaliado *antes* do `getattr` |

Correções que cabem do lado de lá:

1. `assessment.metadata.severity` no lugar de `assessment.properties.severity` — é onde o
   SDK publica, e é também onde a documentação publica (a severidade **não** é
   `properties.severity`: é `properties.metadata.severity`, no objeto
   `SecurityAssessmentMetadataProperties`).
2. Considerar caixa: o literal é `High`/`Medium`/`Low` e o achado usa
   `severity = severity.upper()`, então sem o `.upper()` o valor chega como `High` e sai
   `HIGH` — que é o que o schema do FinOps espera. Verificar o que já está feito.
3. O `[]` silencioso é o ponto mais caro: o worker degrada com honestidade
   (`defender_assessments` entra em `failed_checks` e a cobertura não carimba 100%), então a
   falha não passa como "tudo limpo" — mas também não aparece como erro de verdade.

→ Este é o **achado nº 3** da [seção canônica dos achados](#achados-para-o-time-do-consumidor).

**Segunda observação, também medida:** `NotApplicable` **não** é o ramo descartado. O filtro é
`if not status or status.code == "Healthy"`, e a página descreve `NotApplicable` como
*"Assessment for this resource did not happen"* — uma verificação que nem rodou entra na fila de
achados DEFINDER. Se a intenção era "só o que tem problema vira achado", a condição precisa
também tratar `NotApplicable`.

## O que este lado passou a entregar

Superfície nova `azure/security-assessments-list` (**36 colunas**, 2 conjuntos, api 2021-06-01),
o estado ganha `AzureDefenderAssessment` (coleção opt-in, default vazio) e o teste golden
confere, sobre os **bytes entregues**, que o consumidor produz achado **e** descarta — os dois
lados, porque um check que nunca vê o ramo que ele tem de decidir não treina nada.

O que **não** muda: a projeção no `azure-sim` é escrita do time do FinOps. O que muda é
que ela passa a ter, do lado do estado, um artefato fiel ao contrato — inclusive com o
`resourceDetails.id` e o `id` do assessment formados a partir de um id ARM verdadeiro.

