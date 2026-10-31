# Estado do simulador-nuvem

> Idioma: **Português** | [English](ESTADO.en.md)

Documento vivo. Registra o que existe, o que foi decidido e por quê, para que o
trabalho continue sem depender de contexto de conversa.

Última atualização: **2026-10-31** (revisão `77a6a03a`, branch `feat/p76-security-posture-gcp-azure`).

## Entregas registradas

| Commit | Fase | O que trouxe |
|---|---|---|
| `9848e1e` H-01…`0f7e174` H-09 | **Domínio de postura — FECHADO (2026-10-19)** | Os **8 checks** que os três `SecurityScanner` do FinOps rodam têm, cada um, a superfície do simulador que os produz, medida contra o consumidor real. Série de **15 commits** (9 feat, 5 docs, 1 fix), contados na época por `git rev-list --count 9848e1e^..0f7e174` (comando que hoje não roda — ver PROVENANCIA-HISTORICO.md §3.1). Commits-âncora: AWS `9848e1e` H-01 (Config by-rule), `5169404` H-02 (Security Groups), `c65faeb` H-03 (S3), `d38b325` H-04 (IAM), `a80bc1f` H-05 (resíduo de Config); GCP `69b721d` H-06 (SCC), `dead1b0` H-07 (Firewall); Azure `85951d9` H-08 (NSG), `0f7e174` H-09 (Defender). Evidência: 46 superfícies, suíte **1095 passed / 20 skipped**, `--matrix` `gerado=45 falta=0 bloqueado=1`. Detalhe do marco em [POSTURA-SEGURANCA.md](POSTURA-SEGURANCA.md#marco--o-domínio-de-postura-fechado-2026-10-19); débitos residuais em [A área de postura](#a-área-de-postura--completa-2026-10-19). |
| `d38b325` H-04 | IAM — incremento 4 | A identidade da conta AWS: três regras de Config saíram de `INSUFFICIENT_DATA` (medido: 14/10/102 → 32/19/75). O commit **trouxe também, FORA do plano de postura AWS, três superfícies de categoria C** — `gcp/observability-partial`, o bloco regional do S3 e o diagnóstico `fidelity/review.py --state IAM`. Elas estão nomeadas em [o bloco C](#as-três-superfícies-que-entraram-fora-do-plano-categoria-c) porque são dívida de **granularidade de commit**, não parte da fase IAM — o próximo incremento não deve classificá-las como IAM. |
| `a64b8414` | S4b1-E — o `k8s-sim` aceita o id nativo do cluster | O filtro do `k8s-sim` passa a aceitar **três aliases** da identidade do cluster — o **nome** (o que o contrato publica), o **uuid do estate** (`cluster_id`) e o **id nativo** que a descoberta publica (ARN do EKS, id ARM do AKS, `selfLink` do GKE). O fixture versionado `k8s_sim/fixtures/clusters.json` passa a carregar `native_id` por cluster (**309 clusters**: 75 EKS, 111 GKE, 123 AKS), gerado por `scripts/export_clusters.py`; `/allocation/compute` e `/clusterInfo` respondem o mesmo cluster pelos três. Medido: **91 passed** (78 anteriores + 13 novos). Detalhe em [regression/mapa-impacto-s4b1d.md](regression/mapa-impacto-s4b1d.md) e no [contrato do k8s-sim](k8s-sim-opencost-contract.md). |
| `7fcbb7ca` | S4b2-C — o `k8s-sim` na rede do CloudPilot (alias, URL e docs) | O `k8s-sim` vivia só na rede dos simuladores; o backend do CloudPilot não resolvia o nome e `http://k8s-sim:8089` falhava com `Name or service not known`. O `ensure-cloudpilot.ps1` passa a ser o dono do plano Kubernetes: **cria** o container a partir de `compose.k8s.yaml` quando falta (`--no-deps --no-build`, sem rebuild), **anexa** o `synthetic-clouds-k8s-sim-1` à bridge `cloudpilot-deploy_cloudpilot_net` com o alias **`k8s-sim`** e **probeia** `/healthz` e `/clusterInfo` de dentro do `cloudpilot_backend` no `-Smoke`. O `cold-start.ps1` mantém um dono só do vínculo e lista o plano no resumo final. Medido: **antes** `URLError [Errno -2]`; **depois** `/healthz` e `/clusterInfo?filter=cluster:"TEMP-aks_cluster-0025"` → **200** do backend, e o container aparece no `network inspect` da bridge. Detalhe em [regression/mapa-impacto-s4b2c.md](regression/mapa-impacto-s4b2c.md) e no [contrato do k8s-sim](k8s-sim-opencost-contract.md) (§2.1 e §9). |
| `41183517` | S4b2-D — o `aws-sim` no perfil `medium` e a checagem de conexão AWS | O plano AWS tem o **próprio namespace** de variáveis: `compose.aws.yaml` lê `AWS_SIM_SEED`/`AWS_SIM_PROFILE`, **não** os nomes genéricos `SEED`/`PROFILE` dos planos Azure/GCP — e, sem o par `AWS_SIM_*`, o `aws-sim` caía no default `small` e servia um estate **diferente** do resto da pilha. A causa raiz que a S4b2-C mediu estava **errada**: os ids de conta derivam de `(seed, índice)`, não do perfil (`small` e `medium` produzem os **mesmos** três ids), e o `InvalidClientTokenId` vinha do **AWS real** — a imagem do backend em execução era anterior ao override de endpoint por conta (`endpoint_overrides.py` ausente, `sts_endpoint_url` inexistente), então o `cur_config.endpoint_overrides.sts` guardado era inerte e o `botocore` resolvia `https://sts.us-east-1.amazonaws.com`. Medido: `aws-sim` recriado pelo compose oficial com `PROFILE=medium`/`SEED=123` healthy; imagem do backend do CloudPilot reconstruída do `HEAD` com `[PARITY] Code parity OK (742 .py files, host == 5 running container(s))`; credencial re-mintada na forma `ASIA<conta>SYNT` (a conta declarada `911368690069` volta, em vez da queda para a primeira conta do estate); `ensure-cloudpilot.ps1 -Smoke` → **exit 0**, `connection check aws = connected`, `summary: integration OK (0 problems)`. Detalhe em [regression/mapa-impacto-s4b2c.md](regression/mapa-impacto-s4b2c.md) §7 (revisão datada de 2026-10-30). |
| `21cc0eaa` | S4b3-A — a árvore FOCUS/S3 do `aws-sim` no perfil `medium` | O `aws-sim` servia **dois volumes**: as APIs no `medium` e o export de faturamento no `small` — o uploader (`scripts/synthetic-clouds/aws-up.ps1`) resolvia o namespace do plano AWS **só do ambiente de processo**, com default `small`, e o `.env` da instalação (que fixa `AWS_SIM_PROFILE=medium`) nunca chegava ao gerador. O uploader agora lê o `.env` (ambiente de processo primeiro), usa o venv do repositório, **substitui** a árvore no volume em vez de mesclá-la, **não reconstrói** imagem por padrão (`-Build` é explícito) e **confere** a árvore pela superfície S3 do próprio emulador. Do lado do consumidor foram necessárias duas correções de configuração para a ingestão: `cur_config.export_name` (`cloudpilot-focus12-daily-full` → `synthetic-focus12-daily-full`, o nome que o renderer emite) e `external_account_id` (vazio → `911368690069`, exigido pelo guard *fail-closed* da promoção). Medido: `aws-up.ps1` → **exit 0** sem rebuild nem recreate; árvore = 6 objetos / 14.011.803 B, `"profile": "medium"`, **130.236 linhas**, **966** `ResourceId` — os 966 recursos AWS com faturamento do estate `medium` (1.110 recursos / 474.390 linhas); ingestão oficial → `status: ok`, `rows_promoted=58926`, **US$ 166.204,47** no `/costs/unified` (`by_account: aws · HOMOLOGATION AWS [sim]`) e no browser (`/costs` YTD → US$ 225.578, a conta AWS com 73,7%). Detalhe em [regression/mapa-impacto-s4b3a.md](regression/mapa-impacto-s4b3a.md). |
| `a16aa7fb` | S4b3-B — a entrega diária publica no export que o consumidor lê | A entrega (FR-22) publicava em `cloudpilot-focus12-daily-full` — o nome do renderer **anterior** ao *standalone publish* —, enquanto o bucket (`AWS_SIM_BUCKET`) e o `cur_config` da conta de homologação usam `synthetic-focus12-daily-full`, o nome que o renderer emite: a entrega era a **única** peça do circuito fora do namespace, e a falha era **silenciosa** (`deliver_aws` faz `PUT` e conta objetos, sem validar nada — o mesmo `ok: true` para o bucket certo e para o bucket morto). O namespace virou fonte única (`DEFAULT_AWS_BUCKET` / `DEFAULT_AWS_EXPORT_NAME` em `deliver/core.py`), cobrindo os **dois** caminhos de entrega: o CLI (defaults das variáveis `DELIVERY_AWS_*`) e a tarefa do Windows (`schedule/__main__.py:227` chama `deliver_day()` **sem** namespace, logo usa os defaults do código) — o `.env` não resolvia e não resolveria, porque não tem nenhuma variável `DELIVERY_*`. Medido: entrega do dia `2026-10-26` → **exit 0** (`aws_objects: 1`), chave nova em `focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/...` (2.734.569 B = exatamente o parquet de origem) e **nenhum** bucket `cloudpilot-focus12-daily-full` criado; ingestão oficial → `rows_promoted=54096` e `cur_last_execution_id` = a execução da entrega; `/costs/unified` → `HOMOLOGATION AWS [sim] · 54.143,54` com `data_source: focus_cost_records` (antes: `cost: null`, `data_state: "unavailable"`), e o volume confere nos três lugares (parquet `EffectiveCost` 54.143,544220 = `focus_cost_records` do período 2026-10 = `/costs/unified`). Suíte: **1109 passed / 20 skipped**. Detalhe em [regression/mapa-impacto-s4b3b.md](regression/mapa-impacto-s4b3b.md). |
| `77a6a03a` | S4b3-C — a entrega diária roda sozinha: tarefa registrada e ledger em dia | A tarefa `simulador-nuvem-daily` **existia**, mas o wrapper apontava para `D:\Simulador\...` — uma instalação anterior num drive inexistente —, então o último resultado era `1` e nada disparava sozinho; a S4b3-B tinha escrito que ela "não está registrada", e a leitura real corrigiu a premissa. A causa é mecânica: `install` resolve o caminho a partir da localização do pacote, então **mover a instalação** deixa um wrapper obsoleto — o mecanismo oficial (`schedule install`) reescreve o `run-daily.cmd` e o XML e refaz o registro (**exit 0**, comando `cmd.exe /c "C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd"`, disparo diário 12:00 + no logon, `StartWhenAvailable`), e disparada por `schtasks /run` às 13:06:47 devolveu **`Último Resultado: 0`**, com a linha do `tick` no `task.log`. **A suíte de testes apagava o wrapper** (`test_written_files_have_no_doubled_carriage_return` escrevia no caminho de produção e o apagava no `finally`, porque `windows.py` derivava o caminho do *pacote*): a tarefa de 13:02:33 deu `1` sem linha no log — o wrapper não existia; **corrigido** em `tools/synthetic_clouds/schedule/windows.py` (wrapper e XML agora vêm de `config_path.parent`; caminho de produção idêntico; `92 passed` e o wrapper sobrevive à suíte). No caminho houve um **incidente de ambiente**: o `podman` não subia porque um socket Unix obsoleto (`%LOCALAPPDATA%\Temp\podman\podman-machine-default-api.sock`, de 2026-10-30) bloqueava o `bind` do `gvproxy`, que morria antes de abrir o forward SSH (`accept tcp 127.0.0.1:61926: use of closed network connection` era consequência, não causa); removido o socket, `podman machine start` → *"started successfully"*. A queda da VM tinha levou o estado em memória dos dois planos (containers parados há ~15 h, **antes** da fase), restaurado **sem rebuild e sem recreate**: `podman start` nos containers existentes e o provisionador do BigQuery com a imagem já em disco (`--no-deps`, sem `--build` — o `gcp-up.ps1` faria `--build --force-recreate`). O backfill, pelo mecanismo oficial e em um comando (`schedule tick --deliver`) → **exit 0** (830,5 s): `gerados: 2026-10-27 … 2026-10-31` (**60.620 artefatos**), cinco entregas sem erro (`aws=1 objetos`, `gcp=2260/2260/2256/2272/2282 linhas`, `azure=304 dias`); ledger de **11** para **16 dias** (`2026-10-16` → `2026-10-31`), `target_day: 2026-10-31`. O alvo é `2026-10-31` e não `2026-10-30` porque, com `lag_days=0`, o alvo **é o dia corrente**. O dia `2026-10-27` — que estava **parcial** (render interrompido, sem `aws_focus`, fora do ledger) — foi reescrito inteiro (**45** superfícies, igual ao `2026-10-31`), então a lacuna condicional **não** se materializou. No CloudPilot (conta `HOMOLOGATION AWS [sim]`, workspace *Homologation's Workspace* `9ff4da5f…`, **não** o workspace padrão do usuário): ingestão oficial → `status: ok`, `total_billed_cost: 65575.879831`, log de promoção **`rows_promoted=29946`** (a resposta diz `cost_promotion_status: "skipped"` — **o campo mente**: são defaults do schema nunca atribuídos); `/costs/unified` → **`HOMOLOGATION AWS [sim] · 65.575,88`** com `data_source: focus_cost_records` (antes `54.143,54`), e o volume confere nos três lugares (parquet `EffectiveCost` 65.575,879831 = ledger = `/costs/unified`); o export do dia é snapshot **month-to-date** e o leitor CUR lê o execution mais recente (`files_read: 1`), por isso o valor cresce com o mês. **Em aberto:** `docs/AGENDAMENTO.en.md` (fora da allowlist), a contagem da tabela de CUD do BigQuery (`expected 3, got 9`, pré-existente) e a árvore do `aws-sim` no bucket (store em memória; repopular é `aws-up.ps1`, "restart dos planos", fora do escopo). Detalhe em [regression/mapa-impacto-s4b3c.md](regression/mapa-impacto-s4b3c.md). |



| `1e5e1443` | S4b2-E — o `k8s-sim` por HTTPS: nome próprio, SAN e URL do consumidor | O plano Kubernetes era o único que falava **HTTP puro**: o backend do CloudPilot o alcançava por `http://k8s-sim:8089`, um alias de rede sem certificado e sem hostname de nuvem — e o OpenCost, sendo um contrato e não um serviço de nuvem, não tinha hostname real para imitar (inventar sequestraria o nome de alguém, como o `sts.*`). O **checkpoint** da fase aprovou o nome do **front**: `opencost.synthetic-clouds.test` (TLD reservada para testes, RFC 6761, que não resolve na internet pública). O nome entra como alias do `tls-front`, ganha `server` próprio com upstream `k8s-sim:8089` no `nginx.conf` e é **reassinado na folha** pela mesma CA (13 SANs; o bundle do CloudPilot intacto) — o alias `k8s-sim` continua, é o upstream do front. A URL do consumidor passou a `https://opencost.synthetic-clouds.test`: o provider `opencost` do CloudPilot (conta de homologação) aponta para ela e a leitura de custo devolve **5 linhas** para `TEMP-aks_cluster-0025`, pelo nome e pelo id nativo. Medido: front recriado pelo compose oficial (`health=healthy`, **só ele**), `/healthz` e `/clusterInfo?filter=cluster:"TEMP-aks_cluster-0025"` → **200** de dentro do `cloudpilot_backend` (TLS validado contra a CA local), o probe do `ensure` medindo as duas pontas (**4/4 = 200**, 0 problemas), `nginx -t` ok e os outros planos respondendo pelo front. **Em aberto:** o botão "Verificar Conexão" da UI, que morre num defeito **pré-existente do CloudPilot** (a factory passa `db=` a providers que não o aceitam: `opencost.py:47`, `kubecost.py:44`) — reproduzido também com a URL HTTP antiga, e a correção é do lado do CloudPilot, fora da allowlist. Detalhe em [regression/mapa-impacto-s4b2e.md](regression/mapa-impacto-s4b2e.md). |

## Princípio

O simulador gera dados de nuvem **fiéis ao formato de export oficial** de AWS,
GCP e Azure. A fidelidade não é presumida: cada campo tem URL da documentação
oficial e data de consulta, e a regra é *se a documentação não afirma, o
simulador não afirma*. Um campo marcado como não comprovado é um resultado
esperado, não uma pendência a preencher com um palpite.

## Isolamento

Este repositório é autônomo. Nada é criado ou alterado em `C:\Projetos\Simulador`,
em `<arvore-de-origem>` ou em qualquer banco/container do FinOps.

O container `cp-sim-fix` — criado à mão, sem definição declarativa — rodava com
`DATABASE_URL` apontando para `postgres:5432/<banco-do-consumidor>`, e o alias `postgres`
resolvia para o `postgres-do-consumidor` real (<ip-do-consumidor>) porque ambos estavam na
mesma rede. **Foi parado.** Era o vetor de escrita no banco real.

## Arquitetura da fidelidade

| Peça | Papel |
|---|---|
| `specs/<provider>/*.schema.json` | Contrato legível por máquina, derivado da documentação oficial. Fonte da verdade. |
| `specs/<provider>/*.md` | A mesma informação em prosa, com citações, divergências e lacunas. |
| `fidelity/spec.py` | Carrega e **recusa** spec sem evidência (falha fechada). |
| `fidelity/checker.py` | Compara o artefato emitido com a spec: nomes **e** valores. |
| `fidelity/artifacts.py` | Lê os campos e os valores REAIS de um arquivo gerado (Parquet/CSV/JSON). |
| `fidelity/sources.py` | Lista fechada de domínios oficiais — procedência é regra, não impressão. |
| `fidelity/matrix.py` | Liga cada superfície especificada ao renderer que a produz. |
| `fidelity/__main__.py` | Relatório de auditoria (`--matrix` mostra o que falta gerar). |
| `fidelity/review.py` | Diagnóstico **retrospectivo** por estado (`--state IAM`): o que a tela mostraria hoje, e de qual das três causas vem o `INSUFFICIENT_DATA`. |
| `render/_config_evaluators.py` | **A** semântica de veredito das regras gerenciadas que leem estado. Chamado pelo renderer de Config **e** pelo diagnóstico, para que os dois não possam divergir. |

### Duas decisões, não uma

Confundir "a coluna existe no arquivo" com "a coluna pode ser preenchida" custa
fidelidade nos dois sentidos:

| | **Pertence ao formato** (`belongs_to_schema`) | **Pode receber valor** (`is_generatable`) |
|---|---|---|
| Exigências | nome, tipo, `verified`, `source_url`, `evidence` ∈ {`declared`, `null-empty`} | as mesmas, com `evidence: declared` e `type_source` válido |
| Efeito | a coluna tem de existir no artefato | a coluna pode ser preenchida |

`null-empty` é o caso que obriga a separação: a documentação afirma que a coluna
**existe** e que **nunca tem valor**. Omiti-la é infiel ao formato; preenchê-la é
infiel ao contrato. O correto é emiti-la vazia. Já `example-only` **não** pertence
ao formato.

E o auditor confere **valores**, não só nomes: `check_values` acusa coluna
declarada sempre vazia que saiu preenchida — antes disso, escrever um valor
inventado numa dessas colunas passava em silêncio. `check_artifact` faz nome e
valor num passo, e é o que os testes golden chamam.

### Regras do contrato

- **`status`** é estritamente binário: `verified` ou `unverified`.
- **`evidence`** carrega a nuance: `declared`, `null-empty`, `example-only`,
  `name-only`, `deprecated`, `author-classification`.
- **`type_source`**: `documented` (o provedor publica o tipo) ou
  `format-observed` (o provedor não publica tabela de tipos, mas descreve o campo
  normativamente e o formato oficial fixa a representação). `format-observed`
  exige que o campo seja declarado — não se deriva a forma de um exemplo para um
  campo que só existe no exemplo.
- **`unverified`** aceita string ou objeto com `name`/`field`/`column` e `reason`.
  Entradas com `item`/`topic`/`gap` são **lacunas de tópico** (particionamento,
  clustering), não nomes de campo — não poluem a lista de proibidos.
- **`sets`** existe porque uma superfície pode ter vários esquemas, e eles podem
  ser **disjuntos**. Conferir um artefato de um contrato contra a união de todos
  acusaria ausência de tudo o que os outros declaram; por isso `check()` exige
  `scope=` quando há mais de um conjunto nomeado.
- **Ordem** só é contratual quando o provedor publica ordem fixa (ex.: CSV da
  Azure). Num Data Export da AWS a ordem vem do `SELECT` da definição do export.

## Cobertura atual

45 superfícies geradas de 46 declaradas (a bloqueada é a que a documentação não sustenta).
Os três comandos abaixo são a fonte viva disto:

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity            # specs validas?
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix   # o que falta gerar
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --golden   # o que falta provar
```

```
gerado=45  falta=0  bloqueado=1  total=46
specs: 46 superfícies, 2610 colunas, 1972 geráveis, 258 não comprovadas, 0 problemas
tipo derivado do formato oficial (type_source=format-observed): 45
```

> **Medido em 2026-10-19**, depois da série que fechou o domínio de postura
> (`9848e1e` H-01…`0f7e174` H-09, 15 commits). Antes dela a matriz contava **43 geradas de 44 declaradas**. As
> linhas `gerado` e `specs` são as que esta medição produziu; a linha de suíte está registrada em
> [A área de postura](#a-área-de-postura--completa-2026-10-19).

Toda superfície especificada tem renderer e teste golden que confronta o artefato
com a spec, exceto a bloqueada pela documentação.

| Estado | O que significa |
|---|---|
| **gerado** | Existe renderer que produz o artefato, com teste golden. |
| **falta** | A documentação sustenta a geração e o renderer ainda não existe. |
| **bloqueado** | A documentação não sustenta a geração. Não é atraso: é recusa deliberada a inventar. |

Uma superfície só conta como pronta quando as três coisas fecham: spec válida,
renderer que emite, e **teste golden que compara o artefato com a spec**. O
`--golden` denuncia superfície declarada como gerada que nenhum teste confronta —
fidelidade não verificada é fidelidade presumida.

O `--matrix` **detecta quando a própria matriz envelhece** — se uma superfície
marcada como bloqueada passa a ter colunas geráveis, ele avisa. Foi assim que
Resource Graph, NSG flow logs e ARM foram pegos depois de destravados por
`format-observed`. Ele também nomeia duas coisas que nenhum teste deveria
esconder:

* **`untyped_required`** — colunas obrigatórias cujo tipo o provedor não publica.
  São a causa de o auditor acusar `missing` num renderer **correto**: a coluna
  está sempre presente no arquivo real, mas num alvo tipado não pode ser escrita
  sem inventar o tipo. Hoje são 4 superfícies e 401 colunas (`cost-details` 272,
  `vnet` 107, `nsg` 18, `scc` 4). O residual é irredutível enquanto a
  documentação não publicar o tipo — e o lugar de nomeá-lo é aqui, não no
  contrato do gerador.
* **renderer sem superfície** — `gcp_bigquery` produz a tabela padrão em forma
  aninhada, ao lado de `gcp_bigquery_topology`; `gcp_rest_fixtures` é plano de
  API, não formato de export. Ambos são legítimos, mas têm de estar declarados.

Superfície ainda **bloqueada**:

| Superfície | Motivo |
|---|---|
| `azure/cost-management-export-cost-details` | O dataset clássico publica **nomes, sem tipos**, e nenhum dos 132 nomes aparece nos cinco contratos ao mesmo tempo. Gerar exigiria inventar tipo e escolher contrato. |

### Decisão limítrofe registrada

A coluna `tags` do ARM ficou **não gerável**. A referência de templates descreve-a
em prosa ("Dictionary of tag names and values") sem a palavra-chave de tipo que
usa nas outras linhas (`string[]`, `bool`, `int`). O critério do projeto exige que
o formato **fixe** a representação; prosa descritiva ficou do lado conservador. Se
o dono do produto aceitar a prosa como tipo publicado, é uma linha: `documented` +
`object`. Não foi forçado.

## A área de postura — **completa** (2026-10-19)

**Estado: completo.** Os **8 checks** que os três `SecurityScanner` do FinOps rodam — 4 na AWS
(Config by-rule, Security Groups, S3 público, IAM sem MFA), 2 no GCP (SCC findings, Firewall) e 2
na Azure (NSG rules, Defender/Assessments) — têm, cada um, a superfície do simulador que os
produz, **medida contra o consumidor real**. O marco e a tabela provedor × check × superfície ×
commit estão em [POSTURA-SEGURANCA.md](POSTURA-SEGURANCA.md#marco--o-domínio-de-postura-fechado-2026-10-19).

**Evidência:**

| Medida | Valor | Como medir |
|---|---|---|
| Superfícies declaradas | **46** | `--matrix` → `gerado=45 falta=0 bloqueado=1 total=46` |
| Superfícies prontas | **45** | `--ready` → `PRONTO: 45 superficies`, 0 coluna inventada em qualquer provedor |
| Conformidade de Config | **45 COMPLIANT / 27 NON_COMPLIANT / 54 INSUFFICIENT_DATA** | rodando o renderer `config_compliance_by_rule` (seed 123, perfil `small`): 14 regras × 9 escopos = 126 itens |
| Suíte | **1095 passed / 20 skipped** | `pytest tools\synthetic_clouds\tests -q` |

A única superfície bloqueada é `azure/cost-management-export-cost-details`, que é de **custo** —
não pertence ao domínio de postura.

**Débitos remanescentes nomeados.** "Completo" é o estado do *domínio* — os 8 checks têm
superfície. Não é a afirmação de que nada ficou por fazer, e os débitos abaixo são reais,
**limitados e nomeados**:

| Débito | Onde | Por que fica |
|---|---|---|
| `displayName` do Defender sai vazio | `azure/security-assessments-list` | O estado não tem qual verificação o Defender aplicou a uma VNet, e inventar um nome de avaliação seria afirmar sobre o provedor algo que nenhuma página consultada sustenta. **Efeito visível:** o consumidor usa `display_name` como **título** do achado, então o título sai vazio. |
| `status.cause` sai vazio | `azure/security-assessments-list` | Caso-limite: o exemplo de resposta traz `"cause": "OffByPolicy"`, mas **exemplo de payload fixa a forma do campo, não o vocabulário**. |
| 2 `unverified` no SCC | `gcp/scc-findings` | `sourceProperties.{Explanation,Recommendation}` (o proto diz que as chaves do mapa são geridas pela fonte e publica só a gramática do nome — não há enumeração oficial) e `listFindingsResults[].resourceUuid` (plano best-effort legado que nenhum dos seis contratos oficiais declara). |
| Plural de portas da Azure não exercitado | `azure/arm-network-security-group-rules` | `destinationPortRanges` (plural) sai vazio porque o modelo guarda a forma singular, então o ramo `if ranges:` de `_parse_ports` nunca executa contra o artefato. Fechá-lo exige modelar a forma plural em `SecurityRule`, compartilhado com os renderers de NSG flow logs — é ganho de cobertura de ramo, não de fidelidade. |
| `<root_account>` não comprovado | `aws/iam-get-credential-report` | Nem `API_GetCredentialReport.html` nem a página de colunas do IAM User Guide declaram o literal da coluna `user` na linha da conta root. A linha **é** emitida (sem ela `root-account-mfa-enabled` não teria linha onde ler o MFA da raiz) e o literal é `<root_account>`, com o motivo no `_provenance`. |

Nenhum desses débitos é uma lacuna de **superfície**: cada um está escrito no lugar que o produz e
none deles impede um check de rodar. `NAO-COMPROVADOS.md` **não** foi regerado nesta rodada — nada
de spec mudou.

## Mecanismos de export que NÃO existem

Refutações verificadas na documentação — o simulador não vai fingir que existem:

- **Security Hub → S3 em ASFF**: não existe. `FindingsOutput.Format` aceita apenas
  `CSV` ou `OCSF_JSON`. ASFF é o formato interno da finding, não um formato de export.
- **EC2 `DescribeInstances` → artefato durável**: não existe; é API paginada, e a
  referência publica só XML.
- **VPC Flow Logs (GCP) → BigQuery direto**: não existe. O destino é o Cloud
  Logging; o caminho BigQuery é dataset vinculado, que o Google descreve como
  consulta "sem exportar os dados".
- **Defender for Cloud → Azure Storage**: não é destino documentado (só Log
  Analytics, Event Hubs e Logic Apps), e não há schema publicado do payload além de
  `SecurityAlert` e `SecurityRecommendation`.
- **Manifesto de export da Microsoft**: sem schema formal; a definição oficial é um
  único exemplo.
- **`aka.ms/ASCAutomationSchemas`**: o ponteiro da própria página oficial
  redireciona para a raiz do GitHub — morto.

## Decisões tomadas

1. **Projeto independente**, nada dentro do FinOps.
2. **Tipos derivados do formato documentado são permitidos** (`format-observed`),
   com qualificador auditável e a trava de exigir campo declarado. Sem isso, a
   Azure ficaria sem rede e sem instâncias.
3. **Geradores dirigidos por spec**, FinOps primeiro, depois segurança, rede e
   instâncias.
4. **O pacote `coverage/` foi para `attic/product-coupled/`**: ele varre
   `<arvore-do-consumidor>` do FinOps, ou seja, é assunto da fase de ingestão.
5. **O teste da CUR da AWS passou a comparar com a spec citada**, não com o
   arquivo-âncora copiado do FinOps: antes o teste se comparava com uma cópia
   de si mesmo.
6. **As decisões abertas com o FinOps (D1–D8, E1–E3) foram aprovadas em 2026-10-14** e o
   registro respectivo ([DECISOES-PENDENTES.md](DECISOES-PENDENTES.md)) passou de proposta a
   decisão com destino de execução. O que depende daqui foi feito (D7 vigente, D8 implementado,
   E3 aplicado); o que depende de escrita no repositório do FinOps continua pendente, porque
   a regra nº 1 segue de pé.

## Verificação

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'

# auditoria das especificações (exit 1 se alguma estiver sem evidência)
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity

# lint e tipos (o ruff deve rodar DE DENTRO do pacote: o per-file-ignores e o
# isort dependem de a raiz do projeto ser o pacote)
cd tools\synthetic_clouds; & ..\..\.venv\Scripts\ruff.exe check .
cd <raiz-do-repo>
& .\.venv\Scripts\mypy.exe --config-file tools\synthetic_clouds\pyproject.toml tools\synthetic_clouds

# suíte
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests -q
```

Ferramentas de auditoria das specs em `specs/_tools/`:

| Ferramenta | O que responde |
|---|---|
| `check_urls.py` | Toda citação de evidência resolve de fato? Uma citação que dá 404 não é evidência. Depende de rede, então é ferramenta de manutenção — não entra na suíte. |
| `audit_sources.py` | De que domínio vem a evidência de cada coluna. |
| `show_urls.py` | URLs distintas de uma superfície, com contagem — uma spec inteira apontando para uma única URL genérica é sinal de alerta. |
| `list_columns.py` | Amostra de colunas de uma superfície filtradas por origem, para a verificação hostil. |

**Resultado de 2026-10-14: 74 URLs distintas de evidência, 74 resolvem (HTTP 200), 0 falhas.**

Duas verificações de procedência, refeitas depois das últimas edições de spec:

* **Domínio da evidência**: `audit_sources.py` percorre toda coluna de toda spec e
  confere o domínio da `source_url`. Resultado: **0 especificações com problema**,
  nenhuma coluna sem URL, nenhuma fora de domínio oficial (resultado por superfície
  no comando).
* **Tipo derivado do formato** (`type_source = format-observed`, a qualificação
  auditável que o projeto admite onde a documentação não declara o tipo): são **45
  colunas, todas no Azure e todas com evidência em `learn.microsoft.com`**. As 45
  têm `source_url` **e** o qualificador textual explícito — nenhuma entrou por
  dedução silenciosa.

### O veredito: `--ready`

```powershell
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready          # tudo
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready azure    # um provedor
```

Renderiza cada superfície declarada como gerada e aplica **cinco critérios
objetivos**. Nenhum deles é taxa de preenchimento: quanto uma superfície preenche
depende do que o modelo tem fonte para afirmar, e isso varia por superfície. O que
se exige é:

1. renderiza sem erro;
2. entrega ao menos um registro — formato sem dado não é dado;
3. entrega ao menos um artefato que carregue **algum nome próprio** — sem este
   critério, uma superfície que divide renderer com outra passa lendo o artefato da
   irmã (foi o caso do manifesto do cost export da Azure);
4. nenhuma coluna fora de spec alguma;
5. existe teste que **confronta** o artefato (`check_artifact`/`columns_of`) — não
   basta citar a spec.

O `--audit` (mesma renderização) mostra, por superfície, arquivos, registros,
**caminhos com valor** e colunas inventadas. A taxa de preenchimento é evidência
para decidir onde investir, não critério de aprovação.

**Toda medição termina se identificando (D8).** `--audit`, `--matrix`, `--golden`, `--ready` e a
auditoria de specs imprimem a última linha como

```
revisao=d44624c  branch=master  arvore=com alteracoes nao commitadas
```

Os números por superfície só valem para a revisão que os produziu, e um relatório sem ela não é
comparável com o próximo — foi assim que o registro de decisões passou a exigir a revisão junto
do ambiente. A detecção vive em `fidelity/revision.py` e tem três propriedades deliberadas: fora
de um repositório git a revisão vira `desconhecida` e a medição continua valendo (a auditoria
mede artefatos, não git); `arvore` distingue uma medição reproduzível de uma que nenhum commit
contém; e o campo nunca diz "limpa" sem ter olhado.

Duas colunas de preenchimento, e a diferença importa: **`caminhos`** conta os
caminhos que a spec enumera (`invoice.month`, `networkInterfaces[].id`) com valor
no artefato, e **`topo`** conta só os nomes no nível de topo. O artefato de billing
do GCP **aninha** os campos enquanto a spec enumera caminhos pontuados (50 dos 71
nomes têm ponto), então `topo` dizia 17 onde havia 43. `topo` continua no relatório
porque é a leitura certa para as superfícies que **achatam** a chave (`"finding.name"`
como chave literal, no SCC e no flow log do GCP) — olhar só uma das formas erra
para baixo na outra, e foi o que aconteceu ao implementar apenas o aninhamento: o
SCC caiu para zero caminhos como se não entregasse nada.

A terceira coluna, **`obrig.vazias`**, conta as colunas que a spec marca
`required` e que estão **sem valor em todas as linhas**. Ela não é critério de
aprovação, e a ressalva é da própria especificação: no FOCUS, `required` significa
que a **coluna** deve existir, e o valor pode ser nulo quando não se aplica
(`ChargeClass` só vale em linha de correção). Exigir valor tornaria o veredito
impossível de satisfazer honestamente. Mas ausência em massa ou tem fonte faltando
ou tem motivo a declarar — e ausência silenciosa foi como estas passaram:

| superfície | obrigatórias vazias | leitura |
|---|---|---|
| `aws/bcm-data-exports-focus12` | 0 de 19 | completo |
| `gcp/billing-export-standard` / `detailed` | 0 de 13 | completo |
| `azure/cost-management-export-focus12` | **61 de 104** | outlier; classificadas uma a uma pelo agente (preenchível / não aplicável / lacuna) |
| `aws/aws-config-snapshot-s3` e `ec2-describe-instances` | 1 cada (`requestId`) | identificador de requisição: cunhável, não identidade de recurso |
| `aws/security-hub-asff` | 1 (`ProductArn`) | lacuna declarada: o ARN exige ids de produto, e o modelo tem nomes |
| `aws/config-describe-compliance-by-config-rule` | 0 | nenhuma coluna é `required`: a API Reference marca **todos** os membros desta resposta como `Required: No` |
| `gcp/security-command-center` | 4 (`source_id`, `finding_id`, `event_time`, `finding`) | envelope do export ausente: o artefato achata os 68 campos internos e omite as 6 colunas de envelope |

Quando a superfície tem mais de um conjunto, parte da contagem pode ser
**posicional** e não ausência real: o artefato do NSG entrega `flowTuples` como uma
string de 13 campos separados por vírgula (a forma documentada do blob) enquanto a
spec modela as 13 posições como caminhos próprios. O relatório declara essa
ressalva em vez de apresentar o número como se fosse ausência.

**Resultado de 2026-10-14 (tarde):** AWS 6/6 e GCP 7/7 prontas; Azure 6/7, com o
manifesto do cost export pendente de decisão — o renderer entrega só o artefato da
superfície irmã (FOCUS), então ele ou passa a ter artefato próprio ou consta como
bloqueado, e não como gerado.


## O que falta para "gerar todos os dados"

Fidelidade de coluna não é o mesmo que dado presente. Uma superfície pode emitir
exatamente os campos documentados e ainda assim sair vazia, porque o **modelo
canônico** não carrega aquele dado. O estado de 2026-10-14, medido:

| Domínio | O que o modelo canônico oferece | Consequência |
|---|---|---|
| **FinOps** | `DailyConsumption`, `BillingLine`, `ListPrice`, `ContractedPrice`, `Commitment`, `Credit`, `Tax`, `Invoice`, e o preço de lista por SKU | FOCUS AWS com 59 caminhos preenchidos e **0 de 19 obrigatórias vazias**; GCP com 43/47/7; Azure FOCUS com 43 — e **61 obrigatórias vazias**, em tratamento |
| **Instâncias** | `Resource`, `InventoryAsset.config_json` e `InstanceProfile` | id nativo por nuvem (o mesmo `aws_resource_id` que as superfícies AWS usam), tipo derivado do SKU do catálogo, zona, estado, IP privado **igual ao da própria NIC**, imagem e lançamento |
| **Segurança** | `NativeFinding` com `title`, `description`, `types`, `generator_id`, procedência, `first_observed_at` e as escalas 0–100 | os campos obrigatórios do ASFF têm fonte; o que continua vazio é o que a documentação não publica (faixas de `Severity.Normalized`, `ProductArn` que exigiria ids de produto) ou o que a spec não transcreve |
| **Rede** | `NetworkSegment` (por escopo **e região**), `NetworkInterface` e `NetworkFlow` | 24 segmentos, 222 interfaces e 2.664 fluxos; **zero interfaces fora da região do próprio segmento**; as quatro superfícies de flow log entregam registros de verdade |

O que **não** está resolvido, e a diferença importa:

* **Barreiras de especificação, não de modelo.** No `gcp/compute-instances-rest`,
  os IPs privado e público só têm casa documentada em
  `networkInterfaces[].networkIP` e `accessConfigs[].natIP`, e a spec **não
  transcreveu** esses subcampos — escrevê-los poria um nome não citado dentro de uma
  coluna documentada. Preencher exige trabalho de **spec** (ler a página oficial e
  citar), não de renderer. Mesma natureza no VNet flow log, cujas 57+12 colunas de
  fluxo são `example-only`.
* **Contagem posicional.** Onde a spec modela as posições de um campo como
  caminhos próprios (as 13 posições do `flowTuples` do NSG) e o artefato entrega o
  campo como uma string, a contagem de obrigatórias vazias **superestima** — o
  relatório declara a ressalva.
* **A ingestão não é deste repositório.** O desenho está em
  <doc-de-ingestao>.md, escrito a partir de leitura
  somente-leitura: 11 das 21 superfícies têm ponto de ingestão identificado, 10 são
  `NÃO IDENTIFICADO` e **nenhuma superfície de rede tem destino em nenhum dos dois
  modelos de integração do FinOps** (emulação de API e ingestão de arquivo).
  Aplicar é do time do FinOps.

### Questões abertas herdadas do gerador original

O README do pacote carregava uma lista `TODO-verificar` escrita para o **outro**
projeto (a cópia dentro do FinOps) e que apontava para lá. A lista foi retirada
do README, e as três questões ficam aqui para não se perderem:

| item | estado |
|---|---|
| **OA-2** — algum leitor do FinOps filtra `source IN ('ce','cur')` e descartaria um valor `'synthetic'`? | **RESPONDIDA**: todos os leitores FOCUS de `<arvore-do-consumidor>` fixam `source = 'cur'`, e os promotores gravam `'cur'` de propósito; linhas sob qualquer outro valor ficam invisíveis. Evidência citada em <doc-de-ingestao>.md §4.5 |
| **OA-5** — o conjunto de campos aninhados do billing do GCP | **RESOLVIDA**: três specs extraídas das páginas oficiais (71/77/37 colunas, evidência em `docs.cloud.google.com`); o residual são os 8/9/10 nomes que cada spec lista em `unverified` |
| **OA-6** — os conjuntos de valores de `BillingPeriodStatus` / `InvoiceIssueStatus` do FOCUS | **ABERTA**: não está transcrita em spec nenhuma. Quando for, o lugar é a lista `unverified` da superfície correspondente, com o motivo |
| **Codificação de `Tags` em Parquet** | **ABERTA**: a codificação oficial não é documentada; a forma escolhida (string JSON de pares) se justifica pelo que o parser real aceita, e está declarada |

## G1 — NSG da Azure: a metade deste repositório (2026-10-14)

A lacuna **G1** tinha duas metades: o `azure-sim` respondia lista vazia para
`networkSecurityGroups` ("the estate models no network security group"), e este repositório
também não modelava NSG — só o **flow log**, que é registro de tráfego, não a **regra** que o
scanner avalia. A consequência era medida: o scanner Azure reportava a subscription como
**limpa porque não havia o que varrer**.

A metade daqui está feita, em sete peças, na ordem que a especificação fixava:

| # | Peça | Onde |
|---|---|---|
| 1 | Identidade da superfície | `azure/arm-network-security-group-rules` (nova) |
| 2 | Contrato citado | `specs/azure/arm-network-security-group-rules.{md,schema.json}` — **27 colunas** (25 antes do Incremento 7), todas geráveis, 5 itens em `unverified` |
| 3 | Modelo | `model/network.py`: `NetworkSecurityGroup`, `SecurityRule`, `SECURITY_RULE_PROTOCOLS`, `SECURITY_RULE_PRIORITY_RANGE` |
| 4 | Postura | `generate/constants.py`: `NSG_SECURITY_RULES` (posicional, **3 regras**), `NETWORK_FABRIC_RESOURCE_TYPES` |
| 5 | Geração | `generate/estate_builder.py`: um NSG por segmento Azure, com `Inbound/Allow` **e** `Deny` no mesmo NSG |
| 6 | Renderer + teste golden | `render/azure_nsg_rules.py`, `tests/test_azure_nsg_rules_fidelity.py` (22 testes) |
| 7 | Matriz + gate | `fidelity/matrix.py`, `validate/integrity.py` (vocabulário, prioridade única, presença de `Inbound/Allow`) |

Três decisões que valem registro, porque não são óbvias:

1. **O envelope é o do recurso PAI** (`GET .../networkSecurityGroups`), com as regras em
   `properties.securityRules[]`. O recurso filho publica a **mesma**
   `SecurityRulePropertiesFormat`, e a escolha veio do consumidor: é o `list` de
   `networkSecurityGroups` que um scanner chama, e é essa coleção que ele itera. O envelope de
   **lista** (`{"value": [...], "nextLink"}`) **não** é emitido: é paginação de coleção, não campo
   do recurso, e o SDK desembrulha `value` antes de entregar cada NSG.
2. **Os dois `id` são emitidos** (Incremento 7), e saem da mesma composição
   (`NetworkSecurityGroup.arm_id()`), então o id do envelope, o caminho do arquivo e o caminho
   aninhado da regra não podem divergir. Isto **corrige** a decisão anterior: o
   `properties.securityRules[].id` estava em `unverified` porque a página de *template* publica o
   tipo mas não a forma — e a página **REST** publica as duas (`id | string | Resource ID.`, com o
   exemplo do GET fixando `<id-do-NSG>/securityRules/<nome>`). O `nsg.id` do próprio recurso também
   é publicado lá, e o consumidor o lê (`security.py:121` e `:125`) para o `resource_id` do achado e
   para o `--resource-group` do comando de remediação.
3. **Os prefixos majoritariamente usam `'*'`, não um CIDR** — exceção: a regra crítica
   `AllowInternetInboundSsh` usa o service tag `Internet`, que a própria página publica como valor
   válido. Um CIDR exigiria afirmar a faixa da VNet, que o modelo não carrega, e um prefixo que não
   contivesse as NICs da mesma VNet seria uma afirmação **falsa** sobre a rede.

**A postura mudou no Incremento 7 por uma medição, não por gosto.** Com as duas regras anteriores
(`AllowVnetInboundTls` na 443 e `DenyInternetInboundRdp` na 3389), rodar a lógica real de
`_list_open_nsgs` sobre os artefatos entregues dava **0 achados** em 6/6 NSGs: 443 não está no
`_CRITICAL_PORTS` do consumidor, e a única regra com porta crítica era `Deny`, descartada pelo filtro
de acesso antes de a porta ser lida. Entrou `AllowInternetInboundSsh` (`Internet` → `22`, prioridade
100), e a mesma medição passou a dar **6 achados**. É o caso em que um estado "coerente" produz
silenciosamente uma assinatura limpa.

Verificação: `--matrix` → `gerado=21 falta=0 bloqueado=1 total=22`; `--audit` mede a superfície
nova em **12 artefatos / 16 caminhos / 0 colunas inventadas**; `--ready` → **exit 0** com
**21 superfícies**; suíte **754 passed, 10 skipped, 0 failed**; `ruff` e `mypy` limpos em
**111 arquivos**.

**O que continua aberto — e é do outro lado:** o `return []` de
`azure_sim/projections/network.py`. Ele agora é **escrevível** (o estado tem o NSG com as
regras, e `projections/arm.py` já mapeia o tipo `network_security_group`), mas a escrita é do
time do FinOps: a regra inviolável nº 1 deste repositório proíbe alterar aquele repositório.
O docstring de lá deve ser **substituído, não apagado em silêncio** — ele registra uma decisão
correta para o estado de então, e a mudança de premissa é a informação.

## G11 — o `gcp_rest_fixtures` sob contrato (2026-10-14, em andamento)

A G11 é a lacuna que o próprio `--matrix` denunciava: dois renderers **sem superfície
especificada**, e um deles é o caminho por onde o inventário GCP chega ao plano de API. A
reconhecimento mudou o escopo, e a mudança importa:

| Renderer | O que é, medido | Lacuna |
|---|---|---|
| `gcp_bigquery` (189 linhas) | probe Phase-1 que **deriva as colunas da spec** `gcp/billing-export-standard`, pelas mesmas funções do topology (`render/gcp_bigquery_topology.py:61-68`) | **nenhuma de superfície** — emite o mesmo contrato que o `gcp_bigquery_topology`, que já tem spec, golden e matriz. A matriz credita cada superfície a **um** renderer, então um segundo produtor do mesmo contrato aparece como "não mapeado" sem ser buraco de auditoria |
| `gcp_rest_fixtures` (590 linhas) | 13 fixtures de resposta de API em **6 famílias** | **é a lacuna** |

### O contrato foi levantado, e está preservado

As 6 famílias foram levantadas nas fontes que o Google publica **em máquina** — o documento de
descoberta de cada API e os `.proto` oficiais — porque as páginas do `docs.cloud.google.com` não
cabem no fetch (a navegação consome o orçamento antes das tabelas de campos). O resultado está em
[CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md), com URL e trecho por campo. Dois resultados que
mudam o trabalho:

1. **Nenhum erro de envelope existe.** Os dez nomes de campo de lista que o renderer usa estão
   todos **corretos** nos documentos oficiais.
2. **`resourceUuid` não é campo de nenhuma das 6 famílias** — zero ocorrências nos seis
   documentos completos. É uma chave de junção que o renderer inventou, emitida como campo de
   topo em cinco famílias. O risco foi **delimitado** pela documentação: a rejeição de campo
   desconhecido é do caminho **JSON → proto** (`ParseDict(..., ignore_unknown_fields=False)` é o
   default); o transporte **gRPC binário preserva** o campo em vez de falhar. Como o consumidor
   usa os dois caminhos, o campo é sempre não documentado — o que basta para a fidelidade — mas o
   efeito em produção depende do transporte, e isso está dito assim nas specs.

### Primeira família fechada: CAI `searchAllResources`

Superfície `gcp/asset-search-all-resources`, com **dois escopos** (o envelope e o item), spec
citada no proto oficial, renderer novo (`gcp_cai_search_all_resources`), projeção nos dois níveis
(`render/gcp_api_projection.py`, compartilhado pelas famílias restantes) e **13 testes golden**.

O `gcp_rest_fixtures` **não foi tocado**: ele alimenta o emulador e tem testes que o fixam, e
aposentá-lo — ou fazê-lo emitir a forma conforme — é decisão de produto (item **E2**), não efeito
colateral de uma auditoria.

Duas decisões de método que valem registro, porque a evidência as forçou:

* **A spec não usa o host do discovery document como `source_url`** — `cloudasset.googleapis.com`
  não está na lista fechada de domínios oficiais que a suíte verifica, e o teste de contrato
  **pegou** a primeira versão. O que o documento afirma está transcrito no `type_note`, e a
  citação aponta para a página oficial do método.
* **Um mapa é UMA coluna.** `labels` é `map<string,string>`, e a projeção não abre as suas chaves;
  o precedente é o `tags` do `azure-resource-graph-virtual-machines`. Abrir produzia
  `labels.app`, `labels.env`… e o auditor acusava de inventado cada campo do mapa.

**As 11 fixtures estão fechadas** (mesma data): cada endpoint virou uma superfície com contrato
conferido nos dois níveis — o envelope e o item —, num **driver de dados**
(`render/gcp_api_fixtures.py`) em vez de onze renderers copiados. A forma vive uma vez; cada
família entra como uma entrada de dados. As specs foram **geradas** de uma tabela compacta
(`.artifacts/gerar-specs-gcp-api.py`), porque escrever onze JSON com centenas de entradas à mão
convida ao erro de digitação numa citação — que é exatamente o defeito que a suíte existe para
pegar.

**Duas decisões de método que a evidência forçou**, e que valem para as próximas superfícies de
API:

* **A profundidade da projeção é decidida pela spec.** Descer sempre produziria `labels.app`,
  `labels.env`… e o auditor acusaria de inventado cada campo do **mapa**; nunca descer produziria
  `stateInfo` no lugar de `stateInfo.state` e acusaria ausência do filho declarado. Nenhuma das
  duas regras fixas funciona sozinha: a única fonte que sabe a diferença é o contrato — desce num
  objeto quando a spec declara um caminho por dentro dele, para quando a spec o nomeia como coluna.
* **O contrato é conferido na UNIÃO das linhas quando o campo é condicional.** Um mapa
  `resource.labels` carrega as chaves do **tipo monitorado**: `instance_id`/`zone` numa instância,
  `database_id`/`region` num banco. Numa linha só, metade está ausente por construção.

**Três defeitos que os testes pegaram** — todos meus, e todos silenciosos sem eles: as onze
classes de renderer não entravam no registro (o `__slots__` sombreava o atributo de classe que a
descoberta lê); a projeção de uma lista não descia para dentro dos itens (o separador `[]` entre
o prefixo e o filho); e o diretório de saída usava um nome derivado da superfície em vez do nome
**registrado** do renderer, então os arquivos caíam fora do lugar.

## E5 — o export OCSF do Security Hub (2026-10-14)

O E5 estava escrito como *"reespecificar `aws/security-hub-asff` para `CSV`/`OCSF_JSON`"*. A
leitura da fonte **reorientou o item**, e o resultado é uma superfície nova em vez de uma
reescrita:

* O `aws/security-hub-asff` **não estava errado**: ele descreve a **resposta da API**
  (`AwsSecurityFinding`), e a spec já registrava que ASFF não é formato de export.
* O que faltava era o artefato que a AWS **exporta**. A página do `FindingsOutput` fixa a forma:
  *"`OCSF_JSON` produces newline-delimited JSON records in the Open Cybersecurity Schema Framework
  (OCSF) format"* — ou seja, **JSON por linha**, e não um array.

**A analogia que a evidência recusou.** O candidato natural para o envelope seria a classe
`compliance_finding` (uid 3) do repositório normativo do OCSF. A lista de campos que a AWS publica
recusa essa analogia: ela mistura `vulnerabilities.*`, `malware.*`, `databucket.*` e `evidences.*`
com `cloud.*` e `finding_info.*`. Emitir o `compliance_finding` teria sido construir o contrato por
semelhança — e é o motivo de a superfície entregar **27 colunas** com o residual declarado, em vez
de um envelope inventado.

**O que fica declarado como lacuna, e não resolvido:** a **classe OCSF** do envelope
(`class_uid`/`category_uid`/`type_uid`) e o `metadata.version` — que o OCSF declara obrigatório e a
AWS não afirma qual revisão usa. A última lançada do OCSF foi verificada (`1.9.0`, via a API de
releases, `prerelease: false`), mas **escolhê-la para o artefato seria afirmar um fato que a fonte
da AWS não publica**. As duas ausências estão em `unverified` na spec e o teste **exige** que não
sejam emitidas — uma declaração que não falha quando violada não protege nada.

**O residual foi procurado de novo em 2026-10-15**, antes de ser dado por encerrado, e a busca
mudou o **motivo** (não o resultado). O que apareceu: (1) a AWS publica `class_name` como caminho
válido do próprio export, na lista de `FindingsOutput.SelectedFields` e na tabela de campos OCSF
das regras de automação — mas **não** publica o `class_uid`, nem a categoria, nem o tipo, nem os
valores possíveis de `class_name`; (2) a única frase da AWS sobre versão é *"Security Hub currently
supports findings in OCSF schema version 1.6"*, que fala da revisão **suportada** pelos achados do
serviço, e não do valor do campo no arquivo exportado — e a lista de campos do export nem publica
`metadata.version`. Ou seja: a fonte agora **nomeia** o discriminador de classe e não dá o valor,
e nomeia uma versão que não é a do arquivo. Continua fora do artefato, por um motivo mais forte:
não é mais só "a AWS não diz", é "quando a AWS diz, ela diz outra coisa". A página real da operação
de export (`securityhub-v2-findings-export.html`) também foi localizada e lida — o slug antigo
`securityhub-findings-export.html` redireciona para o índice, o que fez a primeira rodada achar que
ela não existia. Registro completo, com URLs e data, em
[`CONTRATO-APIS-GCP.md`](CONTRATO-APIS-GCP.md#o-residual-procurado-de-novo-2026-10-15).

**E a mesma rodada fechou uma lacuna: `severity_id`.** A entrada existia com um motivo honesto e
incompleto — *"a tabela literal->inteiro do OCSF não foi lida"* — e ela **esperava leitura, não
decisão**. O `base_event.json` que a spec procurava não existe em nenhuma tag: os atributos base
vivem no `dictionary.json` da raiz (258 KB), e é lá que a enum estava — 0 Unknown, 1 Informational,
2 Low, 3 Medium, 4 High, 5 Critical, 6 Fatal, 99 Other. O detalhe que dá solidez ao número: a enum
da tag `1.9.0` é **idêntica**, então o valor **não depende** de resolver a lacuna de
`metadata.version`, que segue declarada. E a leitura expôs uma inconsistência que ninguém tinha
percebido: o `severity` saía com o literal **nativo em maiúsculas** (`"HIGH"`), quando o
dicionário define o campo como *"normalized to the caption of the `severity_id` value"* — a
**legenda** (`"High"`). O par saía em desacordo com a fonte que o justificava, enquanto o par
vizinho `status`/`status_id` já saía certo. Corrigido junto, com a normalização de caixa declarada.
A superfície foi de 26 para **27 colunas** e o registro de não comprovados caiu de **299 para 296**
(AWS 117 → 114): as primeiras lacunas fechadas por evidência. Detalhe em
[`CONTRATO-APIS-GCP.md`](CONTRATO-APIS-GCP.md#a-lacuna-que-a-busca-fechou-severity_id-2026-10-15).

**O item 5 da fila foi aberto e rendeu mais uma leva.** Triando o registro, os itens da AWS quase
todos dizem *"a fonte não publica"* — mas dois deles registravam que a página **não tinha sido lida**,
o que é trabalho de leitura, não ausência de fonte. Lendo `API_Severity.html`: o `Severity.Label`
ganhou o **enum formal** (`Valid Values: INFORMATIONAL | LOW | MEDIUM | HIGH | CRITICAL`, que
substituiu o "guidance, not a formal enum" que estava na spec), e o `Severity.Normalized`, que era
declarado impossível, saiu `null` — agora sai com **o número que a AWS publica** para cada rótulo
(LOW=1, MEDIUM=40, HIGH=70, CRITICAL=90). O campo é *deprecated quanto à entrada*, mas o Security Hub
o preenche sozinho, e esta superfície descreve a resposta da API — `null` afirmava um retorno que não
acontece. Uma tentativa **não** fechou e virou evidência a favor da recusa: o padrão do `az-id` não
existe — `Placement.AvailabilityZone` é só `Type: String`, enquanto o mesmo objeto publica `Valid
Values` para `Tenancy`.

Verificação: `--matrix` `gerado=34 falta=0 bloqueado=1`; `--audit aws`: 1 arquivo, **59 registros**,
26 caminhos, **0 colunas inventadas**; `--ready` 34 superfícies PRONTO; 10 testes golden próprios.

## E4 — os labels condicionais do Monitoring (2026-10-14)

A auditoria da G11 deixou esta lacuna nomeada, e ela **não era de fidelidade, era funcional**: a
superfície `gcp/monitoring-time-series` declarava apenas o label `project_id` — o único comum aos
dois tipos de recurso monitorado —, então **a série não era atribuível ao recurso**. Um leitor que
resolvesse a métrica pelo label (`instance_id`, `database_id`) não achava o recurso por ali.

O contrato publicado diz que os labels são *"the labels listed in the associated monitored resource
descriptor"*, e o catálogo os publica **por tipo**: `gce_instance` tem `project_id`/`instance_id`/
`zone`, e `cloudsql_database` tem `project_id`/`database_id`/`region`. **Os dois conjuntos não
coexistem num registro** — e é por isso que a solução não foi declarar os cinco numa linha, o que
tornaria o contrato impossível de satisfazer.

**A condicionalidade é expressa pelo mecanismo de conjuntos nomeados do projeto**, que existia para
exatamente este caso e até então só era usado para contratos disjuntos de uma mesma superfície:

| Conjunto | Papel |
|---|---|
| `response` | o envelope (`timeSeries`, `nextPageToken`) |
| `timeSeries` | os campos comuns a qualquer tipo monitorado |
| `gce_instance_labels` | `instance_id`, `zone` |
| `cloudsql_database_labels` | `database_id`, `region` |

**Duas coisas que os testes ensinaram ao fazer isto, e que valem além do E4:**

* **O projetor não abre mapas, então nenhum teste que leia a projeção prova o conteúdo de um mapa.**
  A projeção mantém `labels` como UMA coluna (é o que impede `labels.app`, `labels.env`…), então a
  guarda do E4 teve de ler o **artefato** — os bytes do corpo — para afirmar que cada série carrega
  os labels do seu tipo. Um teste que olhasse só a projeção não veria a diferença entre emitir três
  labels e emitir um.
* **O auditor confere por CONJUNTO.** Com os labels em conjuntos próprios, conferir o item contra o
  conjunto `timeSeries` acusa de **inventado** o que está declarado no conjunto do tipo. A
  conferência de nomes ignora as colunas dos conjuntos condicionais, e a de valores é feita por
  conjunto — onde cada declaração vive.

Verificação: `--audit gcp`: a superfície entrega **3 arquivos, 50 registros, 16 caminhos, 0 colunas
inventadas**; `--matrix` `gerado=34`; `--ready` 34 PRONTO; a suíte passa a **857 passed, 20 skipped**
(os 10 skips novos são o teste de labels condicionais nos 10 endpoints que não declaram labels).

## Aceitação (2026-10-14)

`python -m tools.synthetic_clouds.fidelity --ready` → **exit 0** (na data da aceitação; a
contagem de superfícies mudou depois, com a G1 acima):

```
superficies avaliadas: 20
PRONTO: 20 superficies com registro, sem coluna inventada e com teste que
confronta a spec; contrato das specs e da matriz sem problema.
```

Acompanhado de:

| verificação | resultado |
|---|---|
| suíte completa | **637 passed, 10 skipped, 0 failed** |
| `mypy` | limpo em **100 arquivos** |
| `ruff` (de dentro do pacote) | All checks passed |
| contrato das specs | 21 superfícies, **2204 colunas**, 1579 geráveis, 173 não comprovadas, **0 problemas** |
| domínio da evidência | **0 especificações com problema**; nenhuma coluna sem URL |
| coluna inventada | **0** em todas as 20 superfícies |
| isolamento | **nada** escrito em `C:\Projetos\Simulador` nem em `<arvore-de-origem>` (conferido por data de modificação, no worktree e no `.git`) |

As `obrig.vazias` que restam estão **todas** declaradas com grupo e motivo, ou sob
ressalva de representação: `ProductArn` (o ARN exige ids de produto, e o modelo tem
nomes), `sku.description` do GCP (nenhuma fonte sustenta — o token é identificador,
o nome do serviço colapsaria SKUs), o container `finding` do SCC (representado pelos
68 filhos), as 7 do flow log do GCP, as 49 do FOCUS Azure (12 preenchidas, 7 não
aplicáveis, 42 lacuna de modelo, 2 não verificadas), as 11 do documento de execução
Azure, a do ARM (`dataDisks[].createOption`) e as do NSG/VNet, que são **posicionais**
(o artefato entrega `flowTuples` como string; a spec modela 13 caminhos).

## Auditoria independente das superfícies novas (2026-10-14)

Método: renderizar cada superfície sobre o estate do perfil `small` e comparar a
**união dos campos de todos os artefatos** com a especificação. Ler só o primeiro
arquivo dá cobertura falsamente baixa, porque várias superfícies entregam vários
(flow logs da AWS: 180 arquivos; ARM: 56; Config: 11).

| Superfície | Conjuntos conferidos | Veredito |
|---|---|---|
| `aws/vpc-flow-logs-s3` | 54/54 | completo |
| `aws/aws-config-snapshot-s3` | 21 + 6 + 6 de 3 conjuntos | **envelope do arquivo em 0/3** |
| `aws/security-hub-asff` | 46 + 12 + 38 | completo |
| `aws/ec2-describe-instances` | 3 + 5 + 61 + 6 | completo |
| `aws/config-describe-compliance-by-config-rule` | 2 + 2 + 2 + 2 + 3 | completo: 6 dos 11 campos têm valor, e os 5 vazios são lacuna declarada (`CapExceeded` sem teto publicado, `NextToken` de resposta e os 3 parâmetros de requisição) |
| `aws/ec2-describe-security-groups` | 3 + 9 + 7 + 2 + 2 + 2 + 7 + 2 + 6 | completo: 9 artefatos, 112 registros, 18 caminhos com valor, **0 colunas inventadas**. Os vazios são lacuna declarada (`securityGroupArn` sem partição no modelo, e os conjuntos que o estate não declara: IPv6, prefix list, referência a grupo) |
| `gcp/vpc-flow-logs-bigquery` | 181/181 | completo |
| `gcp/compute-instances-rest` | 48/48 | completo |
| `gcp/cloud-asset-inventory-compute-instance` | 9 de 10 conjuntos completos | `asset_message` 13/14 (o ausente é o obsoleto) |
| `gcp/security-command-center-findings-bigquery` | 68/74 | os 6 ausentes são as sem tipo publicado — correto |
| `azure/defender-for-cloud-continuous-export` | 35 + 23 + 35 | `attackpaths` 1/21 (não pertencem ao formato) |
| `azure/nsg-flow-logs-v2` | 13 de 26 no conjunto `record` | os 13 restantes são posições dentro da string |
| `azure/vnet-flow-logs` | 5 de 127 | **lacuna do modelo**: não há tipo de fluxo |
| `azure/azure-resource-graph-virtual-machines` | 32/33 das VMs | os conjuntos `securityresources` em 0 estão corretos |
| `azure/arm-resource-representation` | 301/327 | **4 chaves inventadas** (intermediário de achatamento) |

Duas descobertas que viraram regra ou trabalho nomeado:

1. **Proveniência dentro do export é invenção aos olhos de quem consome.** Quatro
   superfícies do GCP misturavam `surface`, `spec`, `model_gaps`, `rows` e afins
   com os campos do registro. Boa parte das "colunas inventadas" era isso. A regra
   está agora em `specs/README.md`: o export só tem campo documentado; o relatório
   vai em arquivo irmão.
2. **Teste golden que confere um conjunto só não protege os outros.** A lacuna do
   envelope do Config sobreviveu porque o teste olhava o `ConfigurationItem`.

## Cadência diária e agendamento (2026-10-14)

O requisito "gerar todo dia, das três clouds, num horário configurável" tinha a
**capacidade** desde a FR-22 e não tinha **ignição**. `daily/` gera qualquer dia, mas
exige uma data explícita, e nada — nem no repositório, nem no Windows — o disparava. A
prova estava no disco: `out/daily/` **não existia**, e a única coisa sob `out/` era sobra
da suíte (`out/pytest-daily/pid-*`). Nenhuma das 191 tarefas agendadas do sistema
mencionava o simulador.

Resolvido em `tools/synthetic_clouds/schedule/`; o detalhe operacional está em
[AGENDAMENTO.md](AGENDAMENTO.md). O que importa registrar aqui são as decisões:

| Decisão | Por quê |
|---|---|
| O relógio de parede mora **só** no `runner` | `daily/` continua sem ler relógio — é o que torna um dia reproduzível. O `runner` converte "que horas são" numa data explícita antes de gerar. |
| Alvo é `hoje - lag_days` (padrão **1**) | FR-B2: cobrança do dia `D` só é exportada em `D+1` às 00:00 UTC. Gerar hoje pediria um dia cuja exportação não existe. |
| O **ledger** decide, não a sorte | Dois gatilhos (diário + logon) e `StartWhenAvailable`: disparar duas vezes não gera duas vezes, e disparar atrasado gera exatamente os dias que faltam. |
| Primeira execução gera **um** dia | Ledger vazio é "nada foi gerado", não "falta um mês". Histórico é ato explícito (`daily --from/--to`). |
| Backfill com teto (31 dias), mais recentes primeiro | Recuperação não pode virar outage; o que ficou de fora é **dito**, não omitido. |
| Retenção **opt-in** (`retention_days`, padrão `null`) | Um dia `small` são 61,3 MB; sem poda o disco enche em silêncio (~1,8 GB/mês). A poda roda em todo tick, inclusive nos "em dia". Dia podado sai do ledger — `is_complete` não pode dizer "sim" para artefato apagado — e o backfill não o ressuscita, porque só preenche depois do dia mais recente. |
| Perfil **`medium`** (2026-10-14, E3) | Decisão de volume: medido no mesmo dia (2026-10-13, seed 123, 19 superfícies), `medium` são **12.006 arquivos / 281,3 MB / 49,4 s** contra **2.736 / 61,3 MB / 9,7 s** do `small` — 4,6× o volume, 4,4× os arquivos. O perfil **não** muda a janela gerada (que é *month-to-date*, derivada do dia); muda a densidade de recursos (370 contra 79 por escopo). Ressalva medida e **assumida**: com retenção de 30 dias o teto sobe para **~17 GB**; `D:` tinha 12,10 GB livres na medição da manhã e 26,67 GB às 17:54, por isso a decisão de 2026-10-14 foi manter os 30 dias por ora com revisão marcada (quando a ocupação acumulada se aproximar do livre), em vez de reduzir a retenção. O dia já publicado foi regerado em `medium` por `tick --force` (11.997 artefatos) e o diretório da densidade antiga foi removido. Ver [DECISOES-PENDENTES.md](DECISOES-PENDENTES.md). |
| Fuso configurado ≠ fuso da máquina | O Agendador só entende hora local. O `install` mostra as duas leituras e avisa quando os offsets divergem; quem garante o dia certo é a idempotência, não a coincidência. |
| `<LogonTrigger>` **sempre** com `<UserId>` | Um gatilho de logon sem conta é de **abrangência total** e só administrador registra — o `schtasks` responde "Acesso negado", que parece falta de privilégio e não é. O parâmetro virou obrigatório para a variante de máquina inteira não poder ser construída por omissão. Descoberto comparando o XML com uma tarefa mínima criada sem elevação. |
| O `status` lê o **XML**, não o relatório de texto | O relatório do Agendador é traduzido; filtrar por rótulos em inglês imprimia só "Status: Pronto" num Windows em português. Nomes de elemento do schema não se traduzem. |
| `init` cai em **UTC com aviso** | A biblioteca padrão não converte o identificador de fuso do Windows para IANA, e o projeto recusa adivinhar: 06:30 UTC seriam 03:30 em São Paulo, e um padrão silencioso pareceria ter funcionado. |
| Configuração que não se entende é **recusada** | Chave desconhecida não é ignorada: `"hour"` ao lado de `"time"` faria o job rodar na hora padrão enquanto o arquivo afirma outra. |

Verificação: a suíte foi de 637 para **737 passed, 10 skipped, 0 failed** (92 testes do
agendador e 8 de detecção de revisão), com `ruff` e `mypy` limpos em **109 arquivos**. Um dia
completo do perfil `small` com todas as 19 superfícies renderiza em **12,3 s** e produz
**2.736 arquivos / 61,3 MB**; o mesmo dia no perfil `medium` (adotado em 2026-10-14) produz
**12.006 arquivos / 281,3 MB** em 49,4 s. Entre os testes está o que prova a propriedade que faz
o backfill ser seguro: `--force` no mesmo dia reproduz os **mesmos bytes**.

O agendamento está **no ar** nesta máquina: tarefa `simulador-nuvem-daily`, próxima
execução `15/10/2026 06:30:00`, último resultado `0`. O gatilho diário foi verificado
disparando sozinho (horário antecipado de propósito, e o `runs.log` registrou o instante
exato) — não só por invocação manual.

**O que isto não resolve**, e continua valendo: a entrega ao FinOps. Os artefatos
nascem dentro de `tools/synthetic_clouds/out/daily/`; não há bucket, upload nem MinIO, e a
ponte que escrevia no banco do produto (`seed/`) foi deliberadamente deixada de fora.
Gerar todo dia não faz um artefato chegar a um lugar que ninguém lê — 10 das 21
superfícies continuam sem ponto de ingestão identificado
(<doc-de-ingestao>.md).

## Incremento 4 — a identidade da conta AWS (2026-10-18)

O `--matrix` estava em **40 geradas de 41 declaradas** e o `--ready` verde, e mesmo assim o
painel de postura de Config mostrava `INSUFFICIENT_DATA` em **102 das 126** respostas. Nenhuma
das duas medições via o problema: uma conta o número de artefatos que existem, e a outra o
número de artefatos fiéis. **Fidelidade de coluna não é dado presente** — a lição do G1
repetida numa escala onde ninguém a estava olhando.

### A lacuna era de MODELO, e nomeada

Três regras gerenciadas de identidade respondiam `INSUFFICIENT_DATA` pelo mesmo motivo, e pelo
mesmo motivo dos incrementos 2 e 3: o recurso **existia e era inventariado e faturado**, mas
nada no estate carregava o **conteúdo** que a regra leria.

| Regra | O que ela lê | O que o estate não tinha |
|---|---|---|
| `root-account-mfa-enabled` | o MFA da conta **root** | nenhuma entidade de IAM |
| `iam-password-policy` | a política de senha da **conta** | nenhuma entidade de IAM |
| `access-keys-rotated` | idade das chaves dos **usuários** | nenhuma entidade de IAM |

27 dos 102 `INSUFFICIENT_DATA` eram exatamente estes — 3 regras × 3 contas × 3 regiões.

### O que mudou

`CanonicalEstate.aws_identity_postures` (`model/iam.py`) carrega, por conta: MFA do root,
política de senha, usuários IAM e chaves de acesso com idade e último uso.

**A chave é a CONTA, não um recurso** — e essa é a diferença estrutURAL em relação aos
incrementos 2 e 3. IAM é global: a senha, o MFA do root e as chaves não têm região. Por isso a
regra responde **por conta** e **se repete** em cada escopo regional dela. Um veredito
diferente por região seria um fato que a AWS não tem.

Os três eixos da rotação são **independentes de propósito**, e cada um reprova numa conta
**diferente**:

```
conta 0  ->  só a SENHA reprova          (política de 8 caracteres, sem requisito)
conta 1  ->  só as CHAVES reprovam       (uma chave ATIVA de 410 dias)
conta 2  ->  só o ROOT reprova           (conta root sem MFA)
```

Isso não é estética. Se duas regras reprovassem na mesma conta, um renderer que as trocasse de
lugar receberia a mesma resposta e **passaria**. Com uma violação por conta, trocar duas
regras de lugar muda a contagem — e é isso que o teste golden mede.

### A medição

```
antes:  COMPLIANT 14   NON_COMPLIANT 10   INSUFFICIENT_DATA 102
depois: COMPLIANT 32   NON_COMPLIANT 19   INSUFFICIENT_DATA  75
```

Cada uma das três regras: **6 COMPLIANT, 3 NON_COMPLIANT, 0 INSUFFICIENT_DATA**.

### Um avaliador, não dois

`render/_config_evaluators.py` é a **única** implementação da semântica de veredito. O renderer
de Config chama para escrever o artefato; o diagnóstico retrospectivo chama para descrever o
que a tela mostraria. Divergência entre os dois é **impossível por construção**, e não por
disciplina — o que importa, porque o diagnóstico é o instrumento de confiança do incremento: um
diagnóstico com segunda implementação poderia dizer `COMPLIANT` onde a tela diz
`NON_COMPLIANT`, e aí seria a coisa menos confiável do projeto.

`RuleVerdict` devolve o veredito **e os `contributors`**. Não é enfeite: o contrato de
`ComplianceContributorCount` exige `CappedCount == 0` num `COMPLIANT` e `CappedCount > 0` num
`NON_COMPLIANT`, e um avaliador que não sabe dizer **que** reprovou não satisfaz o contrato.

### O diagnóstico retrospectivo (`--state IAM`)

Um `INSUFFICIENT_DATA` na tela é um sintoma com **três** causas que pedem ações opostas, e um
painel que só diz `INSUFFICIENT_DATA` obriga quem olha a escolher entre elas no escuro:

1. **a regra é avaliável com o estado atual** → a correção é no renderer;
2. **a regra tem carga mas falta o dado** → a correção é no **modelo**;
3. **falha de configuração** (regra não habilitada na conta) → a correção é na **conta**, e
   nenhuma correção de código resolve.

`fidelity/review.py` nomeia as três e diz qual é o caso, **medindo** o `ComplianceType` atual
nos **bytes gravados** em vez de recalculá-lo — é a medição que impede o diagnóstico de dizer
"não mudou" sobre uma tela que mudou.

### Três superfícies novas

- **`aws/iam-get-credential-report`** -- a leitura que uma ferramenta de postura REAL usa para
  achar "usuário de console sem MFA": o FinOps compara `password_enabled` e `mfa_active`
  **linha a linha** do credential report. É o único contrato **CSV** do repositório, e as
  diferenças não são cosméticas: booleanos em **`TRUE`/`FALSE` maiúsculo** (todos os outros
  artefatos são JSON), cabeçalho obrigatório na ordem documentada, e `N/A` / `not_supported` /
  `no_information` como **estados com significado próprio** — traduzi-los para `null` apagaria
  "este usuário não tem senha". Traz no máximo **duas** chaves por usuário (não existe
  `access_key_3_*`), e a **linha da conta root** vem primeiro e é a única que carrega
  `not_supported` em `password_next_rotation`.

  O **literal** do nome dessa linha não é publicado nem em `API_GetCredentialReport.html` nem
  na página de colunas do IAM User Guide (ambas lidas em 2026-10-18). A linha é emitida mesmo
  assim — sem ela `root-account-mfa-enabled` não tem linha nenhuma onde ler — e o literal vai
  marcado como não comprovado, com o motivo no `_provenance`. Emitir o necessário **e dizer**
  que não foi conferido é diferente de omitir, que quebraria a regra, e de afirmar sem prova,
  que a quebraria pelo outro lado.

- **`aws/iam-get-account-password-policy`** -- a ação que publica os nove requisitos que a
  regra da senha **compara** com os parâmetros dela. Dez membros, e o décimo é
  `ExpirePasswords`, que a página do tipo **define por meio de outro** ("Returns true if
  MaxPasswordAge contains a value greater than 0"). Por isso é **propriedade no modelo** e não
  campo: dois campos aceitariam `ExpirePasswords: true` ao lado de um `MaxPasswordAge`
  ausente, que a AWS nunca devolve. A resposta **não nomeia a conta** (a ação não leva
  parâmetro nenhum), então a atribuição fica no `_provenance`, por posição.

  **Um achado que o teste encontrou:** a primeira versão da rotação **não tinha nenhum usuário
  de console sem MFA** — `mfa_active` valia `TRUE` em todas as linhas de todas as contas. A
  superfície existir para achar uma coisa, num estado onde a coisa não existe, não prova nada
  sobre ela mesma. A correção foi no **modelo**: a conta cujo root está sem MFA é a mesma conta
  em que ninguém ligou o MFA, então ela recebe um `contoso-operacoes` de console sem MFA. Isso
  também dá ao estado uma conta em que root e usuário **discordam**, que é o que impede um
  renderer de trocar um pelo outro.
- **`gcp/observability-partial`** -- a mesma leitura de séries pedida num escopo de projeto
  **inteiro** (`projects/-`) e respondida em **parte**: um projeto de três, com o inventário do
  que sobrou de fora em `missing.json`. O pedido é **anônimo**: o escopo viaja em **dados**
  (curinga de projeto, filtro, janela) e não em credencial — nenhum campo de
  `accessToken`/`apiKey`/`Authorization` no conjunto `request-parameters`. É o contraste
  direto com a API de diagnóstico do FinOps, cujo `request_parameters` **preenche** com um
  token: copiar aquele `unverified` para cá viraria um fato inventado.

### O bloco regional do S3: declarado, não contratual

`RegionalAccessBlockConfiguration` tem **zero ocorrências** em `API_GetPublicAccessBlock.html`
**e** em `API_PutPublicAccessBlock.html` (medido em 2026-10-18), e o
`PublicAccessBlockConfiguration` que ambas documentam tem quatro membros, nenhum regional. O
recurso existe na API e os SDKs o publicam — mas a referência pública consultada não o
descreve.

Ele **não** entrou como quinto membro da resposta: seria uma coluna que o auditor de conjunto
acusaria de inventada, e esconderia o fato que importa — que ninguém conferiu a forma contra
uma página. Virou um conjunto **irmão**, com as **oito** colunas marcadas `unverified` e uma
entrada na lista `unverified` da spec.

A contagem importa porque circulam três números para a mesma coisa, e o certo é o maior. Medido na
spec em 2026-10-18: o conjunto `regional-access-block-configuration` tem **8 colunas, todas as 8
`unverified`** — `Bucket`, o próprio `RegionalAccessBlockConfiguration`, e os **seis** membros com
caminho (`Region`, `RegionPrefix`, `BlockPublicAcls`, `BlockPublicPolicy`, `IgnorePublicAcls`,
`RestrictPublicBuckets`). O "seis" da descrição da própria spec conta **só os membros**; o "sete"
que circularia por aqui não corresponde a nenhuma leitura. `Bucket` não é membro do bloco — pertence
ao artefato irmão, e é o que nomeia o bloco, já que a resposta não nomeia o bucket.

E para isso foi preciso um guarda **inverso**: `names_of` recusa qualquer conjunto com coluna
fora do esquema, o que é certo para os quatro conjuntos contratuais e errado para um conjunto
**admitido** como não contratual. `names_of_uncontracted` inverte a regra — e **os dois lados
falham fechado**: um conjunto que se declara contratual tem de ser todo verificado; um que se
declara não contratual tem de ser **todo** não verificado. A mistura é o que esconde, porque
uma forma meio verificada se lê como inteiramente verificada.

### As três superfícies que entraram fora do plano (categoria C)

O commit `d38b325` H-04 é monolítico: além do IAM, ele entregou três superfícies que **não** fazem
parte do plano de postura AWS. Elas estão declaradas aqui para que o próximo incremento não as
conte como IAM. Medido, não inferido — `git log -S` traz as três de volta para `d38b325` H-04.

| Superfície | O que é | Estado honesto | É um dos 4 checks de postura? |
|---|---|---|---|
| `gcp/observability-partial` | leitura de séries num escopo de projeto **inteiro** (`projects/-`) respondida **em parte**: um projeto de três, o resto em `missing.json`. Entrou junto do IAM e é de **outra nuvem**. | **parcial por construção** — não é dívida, é o contrato: a resposta parcial é o artefato, e o que sobrou de fora é inventário nomeado, não campo adivinhado. Gerada e com teste golden. | **não** — e não é AWS |
| bloco regional do S3 (`regional-access-block-configuration`) | conjunto **irmão** de `s3-get-public-access-block`, com as 8 colunas `unverified` e o artefato emitido separado da resposta. | **funcional e testado**, com a forma **não comprovada**: `RegionalAccessBlockConfiguration` não aparece em nenhuma das duas páginas da ação (medido em 2026-10-18). Os 2 conjuntos contratuais desta spec (`get-public-access-block-response`, `request-parameters`) seguem com 0 colunas `unverified`. | **não** — é uma forma herdada do check de S3, não um check |
| `fidelity/review.py` + `--state IAM` | diagnóstico **retrospectivo**: "o que a tela mostraria hoje, e de qual das três causas vem o `INSUFFICIENT_DATA`". | **funcional e testado**; roda com o mesmo avaliador do renderer, então divergência é impossível por construção. | **não** — é **instrumento** de leitura, não superfície |

A dívida aceita é de **granularidade**, não de conteúdo: nada aqui está vermelho, e nada aqui
pertence à fase IAM. O que o commit devia ter feito era separá-las.

### O que este incremento não faz

- **Não** torna respondível nenhuma regra nova. Das 14 do catálogo, **11** já são avaliadas do
  estado e **3** continuam `INSUFFICIENT_DATA` em **todos** os 9 escopos: `cloudtrail-enabled`,
  `securityhub-enabled` e `vpc-flow-logs-enabled` (medido em 2026-10-18, seed 123, perfil `small`).
  `lambda-function-tagged` **não** está nesse grupo — ela responde onde existe função Lambda
  (3 `NON_COMPLIANT`) e só dá `INSUFFICIENT_DATA` nos 6 escopos **sem** recurso do tipo, que é
  outra causa. E `fidelity/review.py --state` só tem o estado `IAM` porque IAM é o único que
  passou de `INSUFFICIENT_DATA` por lacuna de modelo **neste** incremento.
- **Não** entrega ao FinOps. O repositório segue autônomo (regra nº 1).
- **Não** modela o Block Public Access de **nível de conta**, que a página do `GetPublicAccessBlock`
  descreve ("the most restrictive combination") e que é um fato separado do do bucket.

## Incremento 4.3 — o resíduo de Config fecha: **0 regras sem fonte** (2026-10-18)

O Incremento 4 deixou **3** regras respondendo `INSUFFICIENT_DATA` em **todos** os 9 escopos.
Este incremento fecha as três e, com elas, **toda** a lacuna de modelo nomeada da superfície de
conformidade do Config.

### A medição, antes e depois

Medido em `build_estate(seed=123, profile="small", currency="USD")`, contando os 126 itens
emitidos (14 regras × 9 escopos de conta/região):

```
ANTES (HEAD 7974f46)   COMPLIANT 32   NON_COMPLIANT 19   INSUFFICIENT_DATA 75
DEPOIS                 COMPLIANT 45   NON_COMPLIANT 27   INSUFFICIENT_DATA 54
```

E por regra, as três que mudaram:

| Regra | Antes | Depois | Granularidade do veredito |
|---|---|---|---|
| `cloudtrail-enabled` | 0 C / 0 NC / **9 ID** | **6 C / 3 NC / 0 ID** | por **conta** |
| `securityhub-enabled` | 0 C / 0 NC / **9 ID** | **6 C / 3 NC / 0 ID** | por **conta** |
| `vpc-flow-logs-enabled` | 0 C / 0 NC / **9 ID** | **1 C / 2 NC / 6 ID** | por **VPC** |

Os 11 pontos de `INSUFFICIENT_DATA` que sobraram na regra de VPC **não são lacuna**: o estate põe
os 15 recursos `vpc` em uma região só por conta, então 6 dos 9 escopos não têm VPC nenhuma — é o
colapso `NOT_APPLICABLE`, que a API reporta como `INSUFFICIENT_DATA`. É o mesmo mecanismo que
produz os 48 das outras 8 regras por recurso. **54 = 48 + 6**, e a decomposição fecha sem resto.

### A decisão de modelagem, e por que ela não é uniforme

Esta é a primeira vez que um incremento de postura precisa de **duas** granularidades na mesma
família, e a distinção não é uma escolha de implementação — é o que as páginas publicam:

| Regra | O que a página publica | Consequência no modelo |
|---|---|---|
| `cloudtrail-enabled` | trigger `Periodic`, **nenhum** *Resource Types* | chave por `AwsAccount.account_id`; o veredito se repete nas 3 regiões da conta |
| `securityhub-enabled` | trigger `Periodic`, **nenhum** *Resource Types*, "Parameters: None" | idem |
| `vpc-flow-logs-enabled` | ***Resource Types:*** `AWS::EC2::VPC` | chave por `Resource.identity.uuid` do recurso `vpc` |

`model/audit.py` guarda as duas formas, em coleções separadas, porque são fatos que não têm
nada a ver entre si. `AwsAuditPosture` (conta) e `AwsVpcFlowLog` (VPC).

**`vpc-flow-logs-enabled` não mora em `NetworkSegment`, e a razão é o filtro por provedor.**
`NetworkSegment` é a estrutura de rede multi-provedor (`provider` em `aws|azure|gcp`); um campo
só de AWS dentro dela obrigaria os outros três a conhecerem um campo que só um preenche, e os
15 `NetworkSegment` de AWS não são sequer os 15 recursos `vpc` do inventário — moram em outra
região. O join pelo recurso `vpc` é o mesmo dos Incrementos 2 e 3, então
**`model/network.py` não foi tocado** e nenhum consumidor de rede muda.

O mesmo vale para `NetworkFlow`, que já existia: `render/vpc_flow_logs.py` projeta
`NetworkFlow` em **registros de entrega** de flow log, e o docstring dele diz que o recurso de
log na AWS é a **ENI**, não a VPC. "Houve tráfego entregue numa ENI" e "esta VPC tem flow log
habilitado" são fatos de granularidades diferentes — derivar um do outro seria responder a uma
pergunta que ninguém fez.

### Nenhuma superfície de API nova — decisão lida do consumidor

O `docs/<doc-de-cobertura>.md` já tinha refutado a hipótese (G2): o check de segurança do
FinOps **não** chama CloudTrail. Conferido de novo no consumidor, em
`security.py (modulo do consumidor)` (leitura, sem escrita):
`security.py` não tem `DescribeTrails`, `GetEnabledStandards` nem `DescribeVpcFlowLogs`. O que
ele faz é `_config_rule_severity(rule_name)`, que classifica severidade por **substring** do
`ConfigRuleName` do payload de Config.

Ou seja: **o payload de conformidade do Config já é o canal pelo qual o produto lê estas três
regras.** Modelar `cloudtrail:DescribeTrails` ou `securityhub:DescribeHub` aqui criaria uma
superfície que ninguém consome — fidelidade de vitrine. Nenhuma superfície nova foi criada, e o
`fidelity/matrix.py` não precisou de nova linha.

### O achado que a medição expôs sobre o FinOps

`_config_rule_severity` tem `cloud-trail-enabled` (com hífen) em `high_patterns`. O nome real da
regra é `cloudtrail-enabled`, **sem** hífen — e a própria página avisa que *"the rule identifier
(CLOUD_TRAIL_ENABLED) and rule name (cloudtrail-enabled) are different"*. O padrão casa com 0
nomes do catálogo, então a regra real cai no `return "MEDIUM"` do fim da função.

Isso já estava documentado no `<doc-de-cobertura>.md` (G2) **com base em 838 nomes**,
quando nenhuma das três regras existia aqui. O Incremento 4.3 dá a primeira ocorrência real no
catálogo, e o `vpc-flow-logs-enabled` — que o padrão casa corretamente — é agora avaliado de
verdade. **Não corrigido aqui**: o repositório é autônomo (regra nº 1) e o FinOps é
read-only nesta tarefa.

### O que este incremento não faz

- **Não** estende `fidelity/review.py --state`, que ainda só tem o estado `IAM`. O diagnóstico
  retrospectivo não cobre auditoria nem flow log, embora os avaliadores compartilhados
  (`ACCOUNT_AUDIT_RULE_EVALUATORS`, `VPC_FLOW_LOG_RULE_EVALUATORS`) já existam e sejam
  chamáveis por ele do mesmo jeito.
- **Não** modela o Block Public Access de **nível de conta**, que segue fora.
- **Não** entrega ao FinOps.
## Incremento 8 — a verificação de saúde do Defender para Cloud (2026-10-18)

### Por que o estado precisou de um fato novo

O consumidor filtra `assessments.list` por `properties.status.code` e **descarta** o que é
`Healthy`. O estado tinha achados (`NativeFinding`), que são — por definição — problemas: eles
não conseguem representar o ramo descartado. Um assessment `Healthy` não tem finding, e um
`NotApplicable` não tem finding **por ser** o assessment que não se aplica ao tipo de recurso.

A derivação a partir de `NativeFinding` **foi implementada e medida**, e caiu: no perfil
`small`/seed 123 ela produziu `Counter({'Unhealthy': 6, 'NotApplicable': 6})` — nenhum
`Healthy`, ou seja, um artefato sobre o qual o filtro do consumidor nunca descartaria nada.

### As sete peças

| # | Peça | Onde |
|---|---|---|
| 1 | Identidade da superfície | `azure/security-assessments-list` (nova) |
| 2 | Contrato citado | `specs/azure/security-assessments-list.{md,schema.json}` — **36 colunas** em 2 conjuntos, todas geráveis, **10 itens** em `unverified` (todos *tema*) |
| 3 | Modelo | `model/native.py`: `AzureDefenderAssessment` + `ASSESSMENT_HEALTH_CODES` + `ASSESSMENT_SEVERITIES` |
| 4 | Coleção | `model/estate.py`: `azure_defender_assessments`, **opt-in, default vazio** |
| 5 | Postura | `generate/constants.py`: `AZURE_DEFENDER_ASSESSMENT_POSTURES`, `SAUDE_ALTERNADA`/`SAUDE_NAO_APLICAVEL`, `ASSESSMENT_SEVERITY_BY_FINDING_SEVERITY` |
| 6 | Geração | `generate/estate_builder.py`: `_azure_defender_assessments` — estado alternado pelo índice do segmento DENTRO DA ASSINATURA |
| 7 | Renderer + teste | `render/azure_defender_assessments.py`, `tests/test_azure_defender_assessments_fidelity.py` (34 testes) |

O gate de integridade ganhou a FK: um assessment cujo `segment_uuid` não existe é órfão e
derruba `check_no_orphans` — sem segmento não haveria de onde sair o id que o assessment publica.

### Três decisões que valem registro, porque não são óbvias

**A âncora é o segmento, não o recurso.** `properties.resourceDetails.id` e o `id` do
assessment são ids ARM. O único objeto Azure do estado que carrega um id ARM verdadeiro é o
`NetworkSegment` (`segment_id`, o mesmo que a `azure_vnet_flow_logs` entrega). Ancorar num
`Resource` exigiria compor um id ARM de recurso de computação — e o estado **não modela
resource group**, como a própria `azure/arm-resource-representation` já registra ao usar o
literal `{resourceGroupName}`. Preferi a lacuna visível ao id inventado.

**A alternância é por assinatura, não por escopo.** A primeira tentativa alternou pelo índice do
**escopo** e produziu `[0, 0, 2]` descartes — dois envelopes de três sem nenhum descarte,
porque os segmentos se agrupam em assinaturas. A unidade que a resposta entrega é a assinatura.

**Os instantes vêm de stream próprio indexado pelo segmento**, igual a
`finding_provenance`: dado de segurança tem de ser exatamente repetível entre execuções, e
`now()` não é um valor de estado. O teste golden reconstrói o estate duas vezes e compara.

### O que este incremento não faz

- **Não** modela o **catálogo de avaliações** do Defender (`displayName`, `description`,
  `categories`, `threats`, `implementationEffort`, `userImpact`, `policyDefinitionId`,
  `preview`). O estado não tem qual verificação o Defender aplicou a uma VNet, e inventar um
  nome de avaliação seria afirmar sobre o provedor algo que nenhuma página consultada sustenta.
  O consumidor usa `display_name` como **título** do achado, então o título sai vazio — lacuna
  real e nomeada, não detalhe cosmético.
- **Não** corrige o `AttributeError` do FinOps em `assessment.properties.severity`
  (read-only, regra inviolável nº 1). Ver o **achado nº 3** da [seção canônica dos
  achados](INGESTAO-D3-SEGURANCA.md#achados-para-o-time-do-consumidor).
- **Não** entrega ao `azure-sim`.

## S4b1-E — o `k8s-sim` aceita o id nativo do cluster (2026-10-29)

**O resíduo era do lado do simulador, e ele fecha no commit `a64b8414`.** O consumidor
(CloudPilot) passou a **keyar a descoberta pelo id nativo** (ARN do EKS, id ARM do AKS,
`selfLink` do GKE) e a mandar `filter=cluster:"<id nativo>"`; o `k8s-sim` resolvia o filtro
só pelo **nome** e pelo **uuid do estate**, e o fixture não expunha o id nativo por cluster.
Com a configuração nova do consumidor, `/allocation/compute` respondia **200 com `data: []`** —
o filtro não selecionava nada e nada era inventado.

**O que o commit entrega.** O fixture versionado `k8s_sim/fixtures/clusters.json` passa a
carregar **`native_id`** por cluster — **309 clusters** (75 EKS, 111 GKE, 123 AKS), gerado por
`scripts/export_clusters.py` — e o filtro passa a aceitar **três aliases** da mesma identidade:

| Alias | Forma | Quem o manda |
|---|---|---|
| **nome** | o nome do estate — é o que o contrato publica | o consumidor legado, keyed by name |
| **uuid do estate** | o `cluster_id` do fixture | quem guardou o identificador canônico |
| **id nativo** | ARN do EKS, id ARM do AKS, `selfLink` do GKE | a descoberta do consumidor (C-IDENT) |

Os três são **aceitos, nunca publicados**: a resposta carrega o **nome**, então um pedido
respondido por qualquer alias é indistinguível de um respondido pelo nome. É o id nativo que
separa homônimos — os 309 clusters carregam **160 nomes distintos** (o nome é único dentro do
escopo, não no estate), e os **309 ids nativos são distintos** entre si (309 ids para 309
clusters). `/allocation/compute` e `/clusterInfo` aceitam os três e respondem o mesmo cluster.

**Medido:** **91 passed** na suíte do `k8s-sim` — 78 anteriores ao commit + 13 novos — e o
fixture é **idempotente**: regerado de um estate inalterado, sai byte a byte igual.

**O que continua aberto:** alinhar o ARN do EKS no Resource Groups Tagging API e no AWS Config
com o ARN oficial. Esse item **não** foi entregue pela S4b1-E e permanece aberto no
[mapa de impacto](regression/mapa-impacto-s4b1d.md#8-gaps-para-fases-seguintes).

## S4b2-C — o `k8s-sim` na rede do CloudPilot: alias, URL e docs (2026-10-30)

**O resíduo era do lado da rede, e ele fecha no commit `7fcbb7ca`.** A S4b2-A/B entregaram o
`Containerfile` e o `compose.k8s.yaml` do `k8s-sim`, e o container subia healthy em 8089 — mas
ele vivia **só** na `synthetic-clouds_synthclouds_net` (a rede dos simuladores), enquanto o
backend do CloudPilot vive na `cloudpilot-deploy_cloudpilot_net`. Duas redes, um nome, nenhum
caminho: do backend, `http://k8s-sim:8089` não existia.

**O que o commit entrega.** O `ensure-cloudpilot.ps1` passa a ser o dono do plano Kubernetes,
com o mesmo mecanismo dos outros emuladores:

| Peça | O que faz |
|---|---|
| `Ensure-K8sSimContainer` | cria o container a partir de `compose.k8s.yaml` com `--no-deps --no-build` (a imagem `localhost/k8s-sim:latest` é artefato da S4b2-B e **não** é reconstruída) quando ele não existe; se existe, só o inicia e espera o healthcheck |
| `Ensure-NetworkAliases` | anexa o `synthetic-clouds-k8s-sim-1` à `cloudpilot-deploy_cloudpilot_net` com o alias **`k8s-sim`** — o mesmo `disconnect`/`connect` idempotente que já publica `gcp-sim`, `aws-sim`, `s3mock` e `bigquery-emulator` |
| `Test-K8sSimFromBackend` | no `-Smoke`, probeia `/healthz` e `/clusterInfo` **de dentro do `cloudpilot_backend`**, porque é de lá que o alias importa |

O `cold-start.ps1` **não** ganhou um passo novo: o `k8s-sim` sobe pelo `ensure`, que ele já
encadeia por último — assim o container existe antes do alias, e o alias existe antes de o
backend precisar dele. Um `k8s-up.ps1` separado duplicaria a lógica; por isso ele não foi
criado. O `cold-start.ps1` ganhou o `k8s-sim` no resumo final de endpoints.

**Medido neste host.** Antes: `urllib.error.URLError: <urlopen error [Errno -2] Name or
service not known>` (exit 1). Depois: `/healthz` → **200** e
`/clusterInfo?filter=cluster:"TEMP-aks_cluster-0025"` → **200**, ambos do backend, com o corpo
`{"code":200,"data":{"version":"synthetic"}}`; e o `podman network inspect
cloudpilot-deploy_cloudpilot_net` mostra o `synthetic-clouds-k8s-sim-1` na `10.89.0.20/24`,
com o alias `k8s-sim`.

**O contrato HTTP não mudou** — nem um arquivo de `emulators/**` foi tocado, e o
`compose.k8s.yaml` (entregue pela S4b2-B) não foi editado. O que mudou foi o **caminho de
rede** até ele, e a documentação que dizia "fora do compose".

**O que continua aberto:**

- **TLS para o plano Kubernetes** — a URL é HTTP puro na bridge, sem hostname real e sem
  certificado. É o restante da S4b2, declarado no
  [contrato do k8s-sim](k8s-sim-opencost-contract.md) (§2.1 e §9).
- **`docs/DECISOES-PENDENTES.md`** ainda afirma que o `k8s-sim` "não tem Containerfile nem
  serviço de compose" — frase falsa desde a S4b2-B, em arquivo **fora da allowlist** desta
  fase, então o texto não foi corrigido aqui. O mesmo vale para o `AGENTS.md`.
- **`scripts/synthetic-clouds/up.ps1` não sobe o plano Kubernetes** — ele é dono dos três
  planos de nuvem e está fora da allowlist; a assimetria está escrita, não escondida.
- **A checagem de conexão AWS do `-Smoke` falha neste host, e é pré-existente.** Medido: o
  script **original** do `HEAD` anterior, rodado num worktree descartável, produz a mesma
  linha. Causa raiz: o container `aws-sim` está no ar com `PROFILE=small`, enquanto o `.env`
  documentado diz `PROFILE=medium` — as access keys do estate mudaram. A correção (recriar o
  `aws-sim` com o `.env` e refazer a credencial) é **restart dos outros emuladores**, fora do
  escopo desta fase. Detalhe em [regression/mapa-impacto-s4b2c.md](regression/mapa-impacto-s4b2c.md) §7.
- **A tarefa agendada `CloudPilot-Simulator-Ensure` aponta para `D:\Simulador\...`**, drive que
  não existe mais neste host: ela termina com `LastTaskResult=1` sem rodar nada. O wrapper
  versionado já aponta para `C:\Projetos\Simulador\...`; o que está desatualizado é a **ação
  registrada**, e a correção é re-registrar (`register-ensure-task.ps1 -RunNow`).

## S4b2-D — o `aws-sim` no perfil `medium` e a checagem de conexão AWS (2026-10-30)

**O resíduo era do namespace de variáveis — e a causa raiz que a S4b2-C mediu estava errada.**
O `-Smoke` falhava na conta AWS com `InvalidClientTokenId`. A leitura original dizia que *"as
access keys do estate derivam do perfil"*. **Não derivam**: o id de conta vem de
`aws_account_id(seed, "acct-NN")` — seed e índice, **não** o perfil. Medido, com o mesmo
seed 123: `small` e `medium` produzem os **mesmos três** ids (`911368690069`, `969191373337`,
`995394606788`); o perfil muda o **volume** (237 → 1.110 recursos AWS; 37.922 → 474.390
linhas de faturamento). E o `aws-sim` **não valida** a chave que chega: o `GetCallerIdentity`
decodifica `ASIA<12 dígitos>SYNT` e, sem chave decodificável, cai na primeira conta do
estate. O erro vinha do **AWS real** — o log do backend mostra o `botocore` resolvendo
`https://sts.us-east-1.amazonaws.com`, e a mesma credencial decifrada responde **200** contra
`http://aws-sim:8086` e `InvalidClientTokenId` contra a AWS real.

**A causa raiz real: o override de endpoint por conta estava inerte.** A conta guarda
`cur_config.endpoint_overrides.sts = http://aws-sim:8086` — o caminho que o front TLS
deliberadamente não publica, porque um hijack de `sts.amazonaws.com` quebraria as contas AWS
reais que o mesmo CloudPilot consome. Esse override só é lido por um backend que tenha
`endpoint_overrides.py` e propague `sts_endpoint_url` ao validador. A imagem em execução
**não tinha**: o container não tinha `app/services/providers/endpoint_overrides.py`, e
`connection_check.py`/`connection_validator.py` vinham sem `sts_endpoint_url` — desvio de
**3 arquivos ausentes + 15 diferentes** contra o `HEAD` (742 `.py`). A imagem era de
**2026-10-27 17:11 UTC** (label `acd18722`), **antes** de `dbd66cca` (2026-10-28 20:29),
que introduziu o feature e **é** ancestral do `HEAD`.

**O que a fase entrega.**

| Peça | O que faz |
|---|---|
| `deploy/synthetic-clouds/.env` (local, git-ignored) | fixa o **namespace do plano AWS**: `AWS_SIM_SEED=123` e `AWS_SIM_PROFILE=medium`. O `compose.aws.yaml` lê `${AWS_SIM_SEED:-123}`/`${AWS_SIM_PROFILE:-small}` — **não** os nomes genéricos `SEED`/`PROFILE` dos planos Azure/GCP. Sem o par `AWS_SIM_*`, o `aws-sim` cai no default `small` e serve um estate **diferente** do resto da pilha |
| `deploy/synthetic-clouds/.env.example` | **documenta** o par `AWS_SIM_*` e o motivo do namespace separado; o valor do exemplo passa a `medium`, o perfil da instalação registrada em `docs/AGENDAMENTO.md` |
| `deploy/synthetic-clouds/README.md` | nomeia o namespace do plano AWS, o default `small` do compose e o fato medido de que os **ids de conta são iguais** nos dois perfis (o perfil muda o volume) |
| `README.md` / `README.en.md` | como o CloudPilot alcança o `aws-sim`: endpoint **por conta**, e não um hijack de hostname |

**O que foi feito fora deste repo, e medido.**

1. `aws-sim` recriado pelo compose oficial → `PROFILE=medium`, `SEED=123`, healthy. Nenhuma
   imagem foi reconstruída, e os outros planos (Azure, GCP, Kubernetes, front TLS, s3mock,
   bigquery) ficaram intactos — mesmos container ids.
2. **Imagem do backend do CloudPilot reconstruída a partir do `HEAD`** (`3da29e76`) e os **5
   containers Python recriados** (`backend`, `celery_worker`, `celery_worker_drift`,
   `celery_beat`, `celery_worker_k8s`). `podman cp` não servia: `pyproject.toml`/`uv.lock`
   também mudaram (597+/427−), então um patch de arquivos deixaria o `.venv` desalinhado.
   Resultado: `[PARITY] Code parity OK (742 .py files, host == 5 running container(s))`.
3. **Defeito colateral encontrado e corrigido na configuração local.** A reconstrução subiu um
   backend em **crash-loop** (`ModuleNotFoundError: No module named 'psycopg'`): `1299fa0d`
   afrouxou o pin do SQLAlchemy para `<2.2`, o lock resolveu **2.1.6**, e essa versão trocou o
   driver default de `postgresql://` para o **psycopg3** — que o lock não entrega (só há
   `psycopg2-binary`). Como `scripts/compose-local.ps1:339` monta `LOCAL_DATABASE_URL_SYNC`
   **sem driver**, o container recebia a URL crua e o `alembic upgrade head` da entrypoint
   morria. Corrigido **só** em `backend/.env.local` (git-ignored):
   `LOCAL_DATABASE_URL_SYNC=postgresql+psycopg2://…`, o mesmo valor que o arquivo já
   declarava em `DATABASE_URL_SYNC`. **Nenhum arquivo do repo do CloudPilot foi editado.**
4. Credencial **re-mintada** pela UI, com a conta de homologação, na forma que o emulador
   decodifica (`ASIA<conta>SYNT` / `synthetic-secret-<conta>`): assim o `GetCallerIdentity`
   devolve **exatamente** a conta declarada (`911368690069`), sem depender da queda para a
   primeira conta do estate. `Verificar Conexão` → **conectado**.

**Medido neste host.** `ensure-cloudpilot.ps1 -Smoke` → `connection check aws = connected`,
`connection check gcp = connected`, `connection check azure = connected`,
`unified total 1042849 stale False`, `summary: integration OK (0 problems)`, **exit 0**.

**O que continua aberto:**

- **A árvore FOCUS/S3 servida pelo `aws-sim` foi renderizada para o perfil `small`** e **não**
  foi re-renderizada: o uploader é `scripts/synthetic-clouds/aws-up.ps1`, e `scripts/**` está
  fora da allowlist desta fase. O CUR que o CloudPilot ingere vem dessa árvore (small),
  enquanto as superfícies de API do `aws-sim` já servem o estate `medium`. A diferença é de
  **volume**, não de identidade (os ids de conta são os mesmos). A re-renderização é o
  próximo passo natural e precisa de uma fase que inclua `scripts/**`.
  **(Fechado pela S4b3-A — ver a seção abaixo.)**
- **As 2 contas `org_member` do workspace `[SYNTH]`** (`AWS Account 1`, `AWS Account 2`)
  aparecem como *"Credential resolution failed"* porque **não têm credencial** (colunas de
  chave com tamanho 0). **Pré-existente** — a última checagem delas é de 2026-10-28 — e
  **fora** do escopo desta fase, que trata da conta Payer (`[SYNTH] AWS acct-01`).
- **O defeito de dependência do CloudPilot (SQLAlchemy 2.1 sem psycopg3) não foi corrigido
  no repo dele** — o repo do CloudPilot é prohibited nesta fase. O contorno local está em
  `backend/.env.local`, e o próximo `compose-local.ps1 -Build` **precisa** dele para não
  repetir o crash-loop. O conserto estrutural (declarar `psycopg` no lock, ou fixar o driver
  no `compose-local.ps1`) é do projeto CloudPilot.
- **O default `small` do `compose.aws.yaml` continua lá** — `compose.aws.yaml` está fora da
  allowlist desta fase. A proteção é o `.env` da instalação mais a documentação do
  `.env.example`; endurecer o default (ou falhar o boot quando o perfil diverge) é fase
  própria.
- **A tarefa agendada `CloudPilot-Simulator-Ensure`** (drive `D:\Simulador\...`) continua
  desatualizada — registro pré-existente, não tocado aqui.

Detalhe em [regression/mapa-impacto-s4b2c.md](regression/mapa-impacto-s4b2c.md) §7 (revisão
datada de 2026-10-30).

## S4b3-A — a árvore FOCUS/S3 do `aws-sim` no perfil `medium` (2026-10-30)

**O `aws-sim` servia dois volumes: as APIs no `medium`, o export de faturamento no `small`.**
A S4b2-D deixou isso escrito como dívida — a árvore FOCUS/S3 tinha sido renderizada no perfil
`small` porque o uploader (`scripts/synthetic-clouds/aws-up.ps1`) resolvia o namespace do plano
AWS **só do ambiente de processo**, com default `small`. Esta fase re-renderiza a árvore no
perfil `medium`, publica-a e fecha o circuito até o `/costs/unified`.

**Três causas, todas medidas neste host.**

1. **O uploader lia o namespace no lugar errado.** `compose.aws.yaml` lê
   `${AWS_SIM_PROFILE:-small}` e o compose interpola o `.env` do diretório do compose — onde a
   instalação fixa `AWS_SIM_PROFILE=medium`. O gerador, porém, roda **no host**: o script só
   olhava o ambiente de processo, e um `aws-up.ps1` sem `export` renderizava `small`. Medido:
   `tools/synthetic_clouds/out/aws-plane/123-small-USD` (mtime 2026-10-29 20:21).
2. **O consumidor lia um nome de export que o renderer não emite.** O renderer fixa
   `EXPORT_NAME = "synthetic-focus12-daily-full"`; a conta de homologação estava com
   `export_name = cloudpilot-focus12-daily-full` (o nome do renderer **anterior** ao
   *standalone publish*, o que escrevia `Manifest.json` no export). O leitor busca
   `f"{s3_prefix}/{export_name}/"` — e media **0 chaves** no bucket do consumidor.
3. **A promoção do CUR é *fail-closed* sem id de conta de 12 dígitos.** A conta
   `HOMOLOGATION AWS [sim]` estava com `external_account_id` **vazio**; o erro ("CUR payer
   account configuration must be a 12-digit AWS account ID") é engolido e a promoção devolve
   `cost_promotion_status: "skipped"` com **zero linhas**. Pré-existente: a ingestão de
   2026-10-28 também não promoveu nada.

**O que o `aws-up.ps1` passou a fazer** (o arquivo que a fase autorizou): lê o `.env` da
instalação (ambiente de processo primeiro, arquivo depois), usa o **venv** do repositório,
**substitui** a árvore no volume em vez de mesclar, **não reconstrói** imagem por padrão
(`-Build` é explícito) e **confere** a árvore pela superfície S3 do próprio `aws-sim`.

**Medido.** `.\scripts\synthetic-clouds\aws-up.ps1` → **exit 0**, com os containers em
execução reutilizados (nenhum rebuild, nenhum recreate). A árvore no volume
(`synthetic-clouds_aws_sim_render`): **6 objetos / 14.011.803 B**, `_provenance.json` com
`"profile": "medium"`, **130.236 linhas** em 5 parquet (2026-01 → 2026-04) e **966** `ResourceId`
distintos — exatamente os **966** recursos AWS **com** linha de faturamento no estate canônico
(`apply_all(build_estate(123, "medium", "USD"))`: **1.110** recursos AWS, **474.390** linhas de
faturamento, **118.366** delas AWS). O `s3mock` publica as 6 chaves em
`focus12-full/synthetic-focus12-daily-full/data/billing_period=...`.

**No CloudPilot (conta de homologação).** Duas mudanças de **configuração**, nenhuma em
arquivo do repo dele: `cur_config.export_name` → `synthetic-focus12-daily-full` (pelo
`PUT /api/v1/cur-ingestion/accounts/{id}/config`) e `external_account_id` → `911368690069`
(a conta payer do estate; bucket, prefixo e `endpoint_url` não mudaram). A ingestão pelo
mecanismo oficial (`POST /api/v1/cur-ingestion/accounts/{id}/ingest`) → `status: ok`, 2
períodos (2026-03, 2026-04), `total_billed_cost: 166204.470549`; o log de promoção registra
`rows_promoted=58926`. No `/costs/unified` (janela 2026-01-01 → 2026-04-30):
`total_cost: 166204.47`, `by_account: aws · HOMOLOGATION AWS [sim] · 166204.47`,
`data_source: focus_cost_records`; no navegador, `/costs` com *Year to Date* → **US$ 225.578**
e **HOMOLOGATION AWS [sim] · US$ 166.204,47 (73,7%)**.

**O que continua aberto.** A entrega diária (FR-22) ainda publica no bucket
`cloudpilot-focus12-daily-full` com o export `cloudpilot-focus12-daily-full` — namespace que o
consumidor não lê (`tools/**` fora da allowlist) **(Fechado pela S4b3-B — ver a seção abaixo.)**;
a árvore cobre a **janela do perfil**
(2026-01-01 → 2026-04-30), não "até hoje"; o consumidor ingere os **2 períodos** mais novos
(`CUR_INGEST_LOOKBACK_PERIODS`); a conta de homologação é **uma** para as **três** contas do
estate; o default `PROFILE: small` do `compose.aws.yaml` continua lá (fora da allowlist), com
a proteção agora dupla (`.env` + uploader); a imagem do `aws-sim` é mais antiga que os fontes
do emulador (o script avisa; reconstruir é fase própria); e o store do `s3mock` é **em memória**
(recriar o container esvazia o bucket).

Detalhe em [regression/mapa-impacto-s4b3a.md](regression/mapa-impacto-s4b3a.md).

## S4b3-B — a entrega diária publica no export que o consumidor lê (2026-10-30)

**A entrega diária publicava num namespace que ninguém lê.** A S4b3-A fechou o lado do
*produtor* (a árvore FOCUS/S3 do `aws-sim`) e deixou escrito, como dívida: *"A entrega diária
(FR-22) ainda publica no bucket `cloudpilot-focus12-daily-full` com o export
`cloudpilot-focus12-daily-full` — namespace que o consumidor não lê"*. Esta fase fecha o lado do
**mecanismo de entrega**: o dia gerado precisa chegar ao consumidor, todo dia, no namespace que
ele lê.

**O namespace da entrega era decidido em três lugares, e só um estava certo.** O
`compose.aws.yaml` (`AWS_SIM_BUCKET`) e o `cur_config` da conta de homologação usavam
`synthetic-focus12-daily-full` — o mesmo nome que o renderer emite
(`render/focus_aws.py`: `EXPORT_NAME = "synthetic-focus12-daily-full"`). Só a entrega usava
`cloudpilot-focus12-daily-full`, em **dois** lugares: os defaults de `deliver_day`
(`deliver/core.py`) e os defaults das variáveis de ambiente do CLI (`deliver/__main__.py`).
Corrigir só o CLI não bastaria: a tarefa do Windows não passa pelo CLI —
`schedule/__main__.py:227` chama `deliver_day(day, daily_root=DEFAULT_OUT)` **sem argumento de
namespace**, então valem os defaults do código. O `.env` da instalação não resolvia (e não
resolveria): o wrapper da tarefa (`schedule/windows.py:86-104`) escreve um `.cmd` que só faz
`set PYTHONPATH` + `cd` antes do `tick`, e o `.env` não tem nenhuma variável `DELIVERY_*` —
**o namespace da entrega nunca foi configurável por arquivo nesta instalação**.

**O defeito era silencioso.** `deliver_aws` faz `PUT` das chaves e **não valida nada**: um `PUT`
bem-sucedido num bucket que ninguém lê produz o mesmo log (`ok: true`, `aws_objects: 1`) que um
`PUT` no bucket certo. O dia era gerado, o objeto subia, a ingestão reportava `status: ok` — e o
`/costs/unified` continuava sem AWS.

**A correção** (`tools/synthetic_clouds/deliver/**`, `+48 −9`, mais um teste de regressão de 47
linhas): `DEFAULT_AWS_BUCKET` e `DEFAULT_AWS_EXPORT_NAME` passam a ser
`synthetic-focus12-daily-full` — **uma** fonte de verdade, importada pelo CLI e re-exportada pelo
pacote. O renderer **não** foi renomeado; o `.env`, o compose e o CloudPilot **não** foram
tocados.

**Medido.** A entrega do dia `2026-10-26` (o mais recente **completo** do ledger; `2026-10-27`
está parcial, sem `aws_focus`) pelo mecanismo oficial → **exit 0**,
`{"aws_objects": 1, "errors": [], "ok": true}`; o caminho do agendado (a chamada exata de
`schedule/__main__.py:227`, com os três alvos) → **exit 0**,
`DeliveryResult(day='2026-10-26', aws_objects=1, gcp_rows=2268, azure_days=303, errors=[])`. No
S3: o bucket do consumidor passou de **6** para **7** chaves, com a chave nova
`focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/20261027T000000Z-eac552f3/synthetic-focus12-daily-full-00001.snappy.parquet`
(**2.734.569 B**, exatamente o tamanho do parquet de origem) — e o bucket
`cloudpilot-focus12-daily-full` **não existe**.

**No CloudPilot (conta de homologação).** Ingestão pelo mecanismo oficial
(`POST /api/v1/cur-ingestion/accounts/{id}/ingest`) → `status: ok`, 2 arquivos, 78 linhas
lidas, `periods_ingested: [2026-04-01, 2026-10-01]`, `total_billed_cost: 140108.435868`; o log
de promoção registra **`rows_promoted=54096`** (a resposta diz
`cost_promotion_status: "skipped"` — o campo mente, o guard *fail-closed* do
`external_account_id` só aparece no log). No `/costs/unified`: **antes** `total_cost: 59373.5`,
`HOMOLOGATION AWS [sim] · cost: null · data_state: "unavailable"`,
`provider_status.aws: "unavailable"`; **depois** `total_cost: 113517.05`,
`HOMOLOGATION AWS [sim] · 54143.54 · data_state: "available"`,
`provider_status.aws: "available"`, `source_by_provider.aws: "AWS Cost and Usage Report"`, e a
resposta do caminho frio com **`data_source: "focus_cost_records"`. O volume confere nos três
lugares: `EffectiveCost` do parquet entregue **54.143,544220** = `focus_cost_records` do período
2026-10 **54.143,54** = `/costs/unified` **54.143,54**.

**Efeito colateral declarado.** A prova do caminho do agendado rodou a entrega oficial com os
**três** alvos (é a chamada do `tick --deliver`, que não filtra alvo): **2.268 linhas** no BigQuery
emulado (1.134 por tabela, dia 2026-10-26) e a janela do `azure-sim` estendida até **303 dias**.
A conta `HOMOLOGATION GCP [sim]` saiu de `0.0` para **14.613,94** e o `total_cost` do workspace
saiu de **113.517,05** para **128.130,99** — o AWS ficou em **54.143,54** nas duas medições, e o
`data_source: "focus_cost_records"` continua valendo. Nada foi revertido: é o comportamento
correto da entrega diária, e a conta de homologação é o destino declarado para validação que
escreve.

**Um incidente na reingestão (não determinístico).** Na **segunda** execução da ingestão do
mesmo dia, o worker do uvicorn do backend morreu no meio da promoção (`Child process [34]
died`, sem traceback; o container **não** foi OOM-killed — `OOMKilled=false`,
`RestartCount=0`, sem limite de memória) e o uvicorn reergueu o worker sozinho. O estado ficou
**íntegro** (`focus_cost_records` com as mesmas 84.042 linhas / US$ 220.348,01,
`cur_last_ingest_error` vazio) e a **terceira** execução passou (exit 0, 25,8 s,
`rows_promoted=54096` de novo). É fragilidade do **lado do CloudPilot**, fora da allowlist
desta fase, e **não** é efeito da mudança daqui.

**O que continua aberto.** O nome do export continua em **dois** lugares independentes (o default
da entrega e o `cur_config.export_name` do CloudPilot) e nada os amarra — a correção alinha os
dois, mas **não** impede a divergência de voltar, e o guard que impediria isso é do lado do
CloudPilot (fora da allowlist). A entrega AWS **não valida** o que publica: há um teste de
regressão neste repositório que amarra o default ao nome do renderer, mas o guard que
impediria a divergência de **voltar** é do lado do CloudPilot. A tarefa do Windows
**não está registrada** (`simulador-nuvem-daily` não aparece no `schtasks`): a entrega está
pronta, mas nada a dispara — o backfill continua dependendo de alguém rodar o `tick`. O ledger
está **3 dias atrás** do alvo (11 dias completos, 2026-10-16 → 2026-10-26, e um diretório
parcial em 2026-10-27). A conta `[SYNTH] AWS acct-01` continua com o `export_name` morto
(`cloudpilot-focus12-daily-full`) — é a mesma dívida em outra conta, fora do alvo desta fase.

Detalhe em [regression/mapa-impacto-s4b3b.md](regression/mapa-impacto-s4b3b.md).


## S4b2-E — o `k8s-sim` por HTTPS: nome próprio, SAN e URL do consumidor (2026-10-30)

**O plano Kubernetes era o único que falava HTTP puro.** Todo o resto da stack fala TLS com o
CloudPilot pelos hostnames reais; o `k8s-sim` era alcançado por `http://k8s-sim:8089`, um alias
de rede na bridge — sem certificado e **sem nome de nuvem**. O contratempo: o OpenCost não é um
serviço de nuvem, é um contrato, e não há hostname real para imitar. Inventar um sequestraria o
nome de alguém (o que a stack já descobriu ser perigoso com `sts.*`); omitir o TLS deixaria o
plano como a única superfície HTTP da pilha. A saída foi o **checkpoint** da fase: o hostname é
**do front**, não da nuvem.

**O que foi aprovado.** `opencost.synthetic-clouds.test` — o contrato OpenCost nomeado, em TLD
reservada para testes (RFC 6761), que **não resolve na internet pública**. URL do consumidor e
valor do provider: **`https://opencost.synthetic-clouds.test`** (porta 443, a do front). O alias
`k8s-sim` **continua** — ele é o upstream do front.

**O que mudou.** O alias novo entra na `cloudpilot_net` do `compose.tls-front.yaml`; o
`nginx.conf` ganha `upstream k8s_opencost { server k8s-sim:8089; }` e um `server` com
`server_name opencost.synthetic-clouds.test`; o `ensure-cloudpilot.ps1` ganha o nome em
`$FrontAliases` (é a lista que **reassina a folha** quando um alias roteado não está no SAN) e
passa a medir as **duas** pontas — HTTPS (o caminho do consumidor) e HTTP (o upstream do front).
A **CA não foi tocada**: a folha tem 13 SANs agora (12 + o novo), e o bundle do CloudPilot
continua o mesmo.

**Medido.** Folha reassinada (`missing SANs: opencost.synthetic-clouds.test`), front recriado
pelo mecanismo oficial (`podman compose -f deploy/synthetic-clouds/compose.tls-front.yaml up -d`
→ `Recreate`/`Recreated`/`Started`, ID `846747b7…` → `9a313a73ab7f`, `health=healthy`) e **só
ele** — os outros containers mantiveram o ID. De dentro do `cloudpilot_backend`, com o contexto
TLS padrão (que confia na CA local por `SSL_CERT_FILE`):
`https://opencost.synthetic-clouds.test/healthz` → **200** `{"status":"ok","synthetic":true}`;
`…/clusterInfo?filter=cluster:"TEMP-aks_cluster-0025"` → **200** `{"code":200,"data":{"version":"synthetic"}}`.
O `nginx -t` → `syntax is ok`, e os outros planos continuam respondendo pelo front
(`compute.googleapis.com` → 404 do gcp-sim, `bigquery.googleapis.com` → 200,
`management.azure.com` → 404 do azure-sim).

**No CloudPilot (conta de homologação, workspace `[SYNTH] synthetic-homologation`).** O
provider `opencost` foi apontado para a URL HTTPS (`provider_endpoint =
https://opencost.synthetic-clouds.test`, `has_token: false` — o token ficou vazio de propósito).
Com a **config lida do banco** e o **provider real** do CloudPilot: `success: true`,
`latency_ms: 29`; e a leitura de custo devolve **5 linhas** para `TEMP-aks_cluster-0025` —
tanto pelo **nome** quanto pelo **id nativo**, ou seja, o alias do C-IDENT continua resolvendo
pelo caminho novo.

**Um defeito pré-existente do CloudPilot, encontrado no meio do caminho.** O botão "Verificar
Conexão" da UI **não chega ao provider**: `TypeError: OpenCostProvider.__init__() got an
unexpected keyword argument 'db'`. A causa raiz está no repo do CloudPilot — a factory passa
`db=` para todo provider (`factory.py:132`), mas `opencost.py:47` e `kubecost.py:44` não aceitam
`db` (ao contrário de `azure.py:285` e `gcp.py:242`). **Não é regressão desta fase:** o mesmo
`TypeError` foi registrado com **duas** URLs diferentes — a HTTPS aprovada e, de propósito, o
`http://k8s-sim:8089` antigo — e o código do container é idêntico, linha a linha, ao do repo
(`IGUAIS=True`). A correção é do lado do CloudPilot (uma linha por provider, espelhando
`azure.py`/`gcp.py`) e **esta fase não pode fazê-la**: `C:\Projetos\cloudpilot-deploy\**` está fora
da allowlist e a correção exigiria recriar os containers do CloudPilot, o que a fase proíbe.

**O que continua aberto.** O botão "Verificar Conexão" da UI (o defeito acima, do lado do
CloudPilot) e o **sync** (nenhum snapshot novo foi gravado). Fora da allowlist desta fase, e
portanto **não corrigidos**: o `deploy/synthetic-clouds/README.md` (ainda diz que o backend
alcança o `k8s-sim` em `http://k8s-sim:8089` e que o TLS é o restante da S4b2) e o
`deploy/synthetic-clouds/.env.example` (ainda documenta `K8S_SIM_URL=http://k8s-sim:8089` — o
valor correto é `https://opencost.synthetic-clouds.test`); o `docs/DECISOES-PENDENTES.md`, que
descreve o plano Kubernetes sem TLS; e o `AGENTS.md`, que descreve o `k8s-sim` como alcançado
por HTTP puro. A folha TLS é local e git-ignored: o repositório guarda o *contrato* (o nome, a
rota, o SAN via `$FrontAliases`), e uma instalação nova reassina a folha pelo
`ensure-cloudpilot.ps1`.

Detalhe em [regression/mapa-impacto-s4b2e.md](regression/mapa-impacto-s4b2e.md).


## S4b3-C — a entrega diária roda sozinha: tarefa registrada e ledger em dia (2026-10-31)

**A tarefa existia, mas apontava para uma instalação que não existe.** A S4b3-B entregou o
namespace e fechou com esta dívida escrita: *"A tarefa do Windows **não está registrada**
(`simulador-nuvem-daily` não aparece para o `schtasks`): a entrega está pronta, mas nada a
dispara — o backfill continua dependendo de alguém rodar o `tick`"*. A leitura real de 2026-10-31
corrige a premissa: a tarefa **existia**, com dois gatilhos (diário às 12:00 + no logon),
`StartWhenAvailable` e `Último Resultado: 1` — mas o wrapper apontava para
`D:\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd`, de uma instalação anterior num drive
que não existe nesta máquina (`Test-Path D:\Simulador` → `False`). Por isso o resultado era `1`:
o wrapper nem existia para ser executado.

**A causa é mecânica, e é a de uma árvore movida.** `install` resolve o caminho a partir da
localização do pacote (`schedule/windows.py:276`), então mover a instalação deixa um wrapper
obsoleto até alguém rodar `install` de novo. Não é bug do agendador, e o repositório não deve
detectar isso: registrar é operação de instalação, não de código. O mecanismo oficial
(`python -m tools.synthetic_clouds.schedule install`) **reescreve** o `run-daily.cmd` e o XML e
refaz o `schtasks /Create /TN simulador-nuvem-daily /XML … /F` → **exit 0**, comando agora
`cmd.exe /c "C:\Projetos\Simulador\tools\synthetic_clouds\schedule\run-daily.cmd"`, próximo disparo
`2026-11-01T12:00:00`. Disparada por `schtasks /run`, devolveu **`Último Resultado: 0`**.

**Houve um incidente de ambiente no caminho, e ele precisa ficar escrito.** O `podman ps` falhava
com `dial tcp 127.0.0.1:61926: … recusou ativamente`; a VM HyperV estava `Running`, mas nada
escutava na 61926. **ROOT CAUSE:** um socket Unix obsoleto — `%LOCALAPPDATA%\Temp\podman\podman-machine-default-api.sock`,
datado de **2026-10-30 10:13**. Com `UserModeNetworking: true`, o `gvproxy` precisa fazer `bind`
nesse caminho para abrir o forward da API; o `bind` falhou com *"Normalmente é permitida apenas
uma utilização de cada endereço de soquete"*, o `gvproxy` morreu antes de criar o forward SSH, e o
`podman machine start` passou a esperar por um socket que jamais abriria (a mensagem
`accept tcp 127.0.0.1:61926: use of closed network connection` no log do `gvproxy` é a
**consequência**, não a causa). Removido o socket obsoleto, `podman machine start` → *"started
successfully"*.

**A queda da VM tinha levado junto o estado em memória dos dois planos** — os containers estavam
parados há ~15 h, **antes** desta fase (a queda não foi causada aqui). O store do `s3mock` é em
memória e o `bigquery-emulator` roda DuckDB em memória (`Mounts: []`), então as tabelas de
billing não existiam mais. Restaurados **sem rebuild e sem recreate**: `podman start` nos
containers existentes (os aliases `s3mock`/`aws-sim` na bridge do CloudPilot sobreviveram no config
do container — conferido de dentro do backend: `s3mock -> 10.89.0.15`, `aws-sim -> 10.89.0.18`) e
o provisionador one-shot do BigQuery com a **imagem já em disco** (`--no-deps`, **sem** `--build` —
o `gcp-up.ps1` faria `--build --force-recreate`, que está fora do escopo).

**O backfill, pelo mecanismo oficial e em um comando só** (`schedule tick --deliver`, o mesmo que a
tarefa executa): **exit 0**, 830,5 s, `alvo: 2026-10-31`, `gerados: 2026-10-27, 2026-10-28,
2026-10-29, 2026-10-30, 2026-10-31` (**60.620 artefatos**), e as cinco entregas sem erro —
`aws=1 objetos`, `gcp=2260/2260/2256/2272/2282 linhas`, `azure=304 dias` cada. O ledger passou de
**11** para **16 dias** (`2026-10-16` → `2026-10-31`), com `target_day: 2026-10-31` e última
execução `ok`.

**O alvo é `2026-10-31`, não `2026-10-30`.** A fase foi escrita em 2026-10-30; a execução é de
2026-10-31 e, com `lag_days=0` (decisão de 2026-10-26), o alvo **é o dia corrente**. Parar em
`2026-10-30` seria truncar o backfill arbitrariamente.

**O dia `2026-10-27` deixou de ser parcial.** A fase condicionava a entrega dele a deixar de ser
parcial; a leitura de 2026-10-31 mostrava `render/` interrompido em `azure_arm_instances`, **sem**
`aws_focus`, e o dia **fora do ledger**. O `tick` reescreveu o dia inteiro: **45** diretórios de
render (45 renderers registrados = 45 diretórios), `aws_focus` presente, idêntico ao `2026-10-31`.
A lacuna condicional **não** se materializou.

**No CloudPilot (conta `HOMOLOGATION AWS [sim]`, `e6bc24c7…`, `external_account_id=911368690069`,
workspace *CloudPilot - Homologation's Workspace* `9ff4da5f…` — **não** o workspace padrão do
usuário, que é `[SYNTH] synthetic-homologation`).** Ingestão oficial → `status: ok`,
`periods_ingested: ["2026-10-01"]`, `files_read: 1`, `invoice_records_upserted: 3`,
`total_billed_cost: 65575.879831`; o log de promoção registra **`rows_promoted=29946`**
(`cur_cost_promoted_resource`, grão *resource*, sobre 30.542 linhas de origem). A resposta diz
`cost_rows_promoted: 0` e `cost_promotion_status: "skipped"` — **o campo mente**: no CloudPilot
esses dois campos são *defaults* do schema (`schemas/cur_ingestion.py:224-226`) e **nunca** são
atribuídos (zero ocorrências de atribuição em `backend/app`); o veredito real só existe no log.

**O `/costs/unified`** → `total_cost: 139563.32`, `HOMOLOGATION AWS [sim] · 65575.88` com
**`data_source: focus_cost_records`** (antes, na S4b3-B, `54.143,54`), `is_stale: true` — que é o
**caminho frio** do endpoint (`costs.py:524`), não cache velho. **O volume confere nos três
lugares**: `EffectiveCost` do parquet entregue **65.575,879831** = `focus_cost_records` do período
2026-10 (29.946 linhas, `ChargePeriodStart` de `2026-10-01` a `2026-10-31`) **65.575,88** =
`/costs/unified` **65.575,88**.

**Por que o valor subiu** de 54.143,54 para 65.575,88: o export do dia é um **snapshot
month-to-date**. O parquet do dia `2026-10-31` cobre `ChargePeriodStart` de `2026-10-01` a
`2026-10-31` (o do dia `2026-10-26` cobria até `2026-10-26`), e o leitor de CUR lê o **execution
mais recente** (`files_read: 1`) — ler os cinco e somar contaria o mês cinco vezes.

**A suíte de testes apagava o wrapper — a segunda armadilha, e a mais silenciosa.** Depois do
`install` das 12:21, a tarefa disparada às **13:02:33** respondeu **`Último resultado: 1`** sem
nenhuma linha nova no `task.log`: o wrapper não existia mais. Causa raiz: `schedule/windows.py`
derivava o caminho do wrapper da **localização do pacote**, e o teste
`test_written_files_have_no_doubled_carriage_return`
(`tools/synthetic_clouds/tests/test_schedule.py:647-673`) escreve os artefatos do plano **nesse
caminho de produção** e os apaga no `finally` — **rodar a suíte desligava a tarefa agendada**.
Correção (em `schedule/windows.py`, dentro da allowlist): wrapper e XML passam a ser derivados do
**diretório da configuração** (`config_path.parent`), o que mantém o caminho de produção
**idêntico** (`install` continua imprimindo `…\schedule\run-daily.cmd`) e impede que um teste
apague o que a tarefa de produção executa. Medido: `pytest tools\synthetic_clouds\tests\test_schedule.py
-q` → **92 passed**, e o `run-daily.cmd` **sobrevive** à suíte (mesmo `LastWriteTime` antes e
depois). Re-disparada às **13:06:47** → **`Último resultado: 0`** e a linha do `tick` no
`task.log` (`alvo: 2026-10-31 … nada a gerar: o ledger ja cobre o alvo`).

**O que continua aberto.** O `docs/AGENDAMENTO.en.md` (gêmeo inglês do documento de agendamento)
continua dizendo que a tarefa não está registrada e que o ledger para em `2026-10-26` — ele **não**
está na allowlist desta fase, então o texto não foi corrigido aqui. O **teste de regressão** da
correção acima mora em `tools/synthetic_clouds/tests/test_schedule.py`, também fora da allowlist:
a correção é verificável por medição, mas a rede de proteção automática fica para a fase que mexer
nos testes. A tabela de CUD do BigQuery não
fecha a contagem (`expected 3, got 9`, inconsistência pré-existente do render de 2026-10-29, numa
superfície que a entrega diária não toca). A resposta da ingestão não reporta a promoção (defaults
do schema nunca atribuídos — dívida do CloudPilot, fora da allowlist). E a árvore FOCUS/S3 do
`aws-sim` (2026-01 → 2026-04) **não** voltou ao bucket: o store do `s3mock` é em memória e
repopulá-lo exige `aws-up.ps1`, que re-renderiza a árvore e substitui o volume — "restart dos
planos", fora do escopo. Isso **não** altera a medição da janela corrente (o ledger é persistente
em Postgres e a janela de outubro depende só do export de outubro).

Detalhe em [regression/mapa-impacto-s4b3c.md](regression/mapa-impacto-s4b3c.md).
