# Decisões — registro do que foi decidido

> Idioma: **Português** | [English](DECISOES-PENDENTES.en.md)

Cada item aqui **travava** trabalho verificável. Este documento passou de "registro para
decisão" a **registro de decisão**: em **2026-10-14** as recomendações abaixo foram
aprovadas pelo responsável pelo produto, e o que resta em cada bloco é **execução**, não
escolha.

**Procedência.** Os itens **D1–D8** vêm da §7 do <doc-de-ingestao>.md,
levantados por leitura somente-leitura do repositório do FinOps. Os itens **E1–E3** vieram da
análise desta sessão (<doc-de-cobertura>.md).

**Como ler.** Cada bloco traz a pergunta que estava aberta, a **decisão aprovada** e o
**estado** dela. Onde o estado é *pendente*, o motivo está dito: em nenhum caso é falta de
decisão — é trabalho que ainda não foi feito, ou que pertence ao outro repositório.

---

## D1 — Qual gerador alimenta cada plano?

**A pergunta.** O `simulador-nuvem` (aqui) passa a ser a fonte de qual dos dois planos?

**Por que travava.** Existem dois modelos que não são intercambiáveis
(`INGESTAO:184-218`): **ingestão por arquivo** (CUR/FOCUS/blob/BigQuery) e **emulação de
API**. Este repositório cobre o primeiro por inteiro e **também** emite as 13 fixtures do
GCP com os mesmos nomes de arquivo. O que ele **não** tem é o **servidor** de emulação
(`app.py`, routers, `provision.py`) — esse só existe no repositório do FinOps. E existe
uma cópia local do gerador lá (`tools/synthetic_clouds`, 5 renderers)
que os scripts invocam hoje.

| Opção | O que acontecia | Custo |
|---|---|---|
| a) Adotar aqui só para o plano de arquivo; manter a cópia local para a API | metade do ganho; dois geradores vivos | baixo |
| **b) Adotar aqui para arquivo _e_ para as fixtures GCP, corrigindo o nome do manifesto (§6.1)** | um gerador só para o GCP; a cópia local encolhe | **uma palavra** (§6.1) + retrabalho dos scripts |
| c) Manter a cópia local e aposentar este repositório | perde-se a auditoria de fidelidade (2.204 colunas com URL) | alto, e joga fora o ativo |

**DECISÃO: (b), por plano.** O §6.1 mostra que o payload do `_provenance.json` já tem
exatamente as chaves que o provisionador consome — é troca de nome em 4 lugares, não de
contrato.

**Estado: pendente — executar do outro lado.** O plano de arquivo já é servido por este
repositório (é o que ele faz). A parte que falta é o FinOps **adotar estas fixtures**:
trocar `manifest.json` → `_provenance.json` em `deploy/synthetic-clouds/compose.gcp.yaml:54-55`,
`emulators/gcp-sim/gcp_sim/provision.py` (leitura em `:216`, chaves em
`:164,170,222,231,247-248`, CLI `:256`), `emulators/gcp-sim/tests/test_provision.py:34`
e `scripts/synthetic-clouds/gcp-smoke.ps1:45-48`. A cópia local
continua necessária **até** essa troca, porque são os scripts dela que a invocam.

**Verificado em 2026-10-14 na revisão `0f5e6da5` H-36:** os quatro caminhos existem e **nenhum mudou
de lugar**; a troca é de string em 4 arquivos, com contrato intacto — este repositório grava
`_provenance.json` (`render/gcp_bigquery_topology.py:138`, escrito em `:1754`) e o payload
(`:1649-1686`) tem exatamente as chaves que o provisionador lê. O detalhe que mantém a
divergência viva: **a cópia local do gerador dentro do FinOps ainda escreve `manifest.json`**
(`tools/synthetic_clouds\render\gcp_bigquery_topology.py:1103`).

**A regra nº 1 deste repositório segue de pé:** a troca é escrita dentro do FinOps, e
quem executa é o time de lá (ou o responsável, diretamente).

---

## D2 — Azure: descobrir entrega sem `manifest.json`?

**A pergunta.** O FinOps passa a descobrir entregas Azure **sem** manifesto, ou pede ao
simulador um artefato que ele hoje **recusa** emitir por contrato?

**Por que travava.** É a divergência **mais cara** das três (`INGESTAO:630-668`). O leitor
exige um blob terminando em `manifest.json` com `exportType` e `blobs`
(`blob_reader.py (modulo do consumidor):235-244,98-139`); o simulador entrega `export_run.json`
com os 12 campos do `ExportRun` e **sem** `exportType`/`blobs`. Resultado medido: `discover()`
devolve **lista vazia** e **o FinOps não descobre nenhuma entrega Azure** deste gerador.

| Opção | O que acontecia | Custo |
|---|---|---|
| **a) FinOps descobre sem manifesto (`export_run.json` para o tipo + partes por sufixo)** | preserva a política de fidelidade deste repo (não nomear os 29 campos `example-only`) | médio, no leitor |
| b) Simulador passa a emitir o manifesto | quebra a regra "nome não citado não é emitido": 29 dos 41 nomes só existem num exemplo | médio, aqui, e **muda a política** |
| c) Apontar a ingestão Azure para `azure-sim/exporter/`, que **já escreve** o manifesto | não mexe na política deste repo; cria **dois produtores** do mesmo artefato | baixo, mas exige decidir quem manda |

**DECISÃO: (a).** O `provision.py` do GCP já faz algo equivalente, então o padrão existe
no próprio produto.

**Estado: pendente — executar do outro lado.** O leitor de blob do FinOps passa a
descobrir por `export_run.json` + partes por sufixo, **e o simulador não muda nada**: a
entrega continua `focus.csv`, `focus.parquet` e `export_run.json`, sem `_manifest.json`
(há teste que exige isso: `tests/test_focus_azure_spec_fidelity.py:392-401`).

**Premissa reverificada em 2026-10-14** na revisão atual do FinOps (`0f5e6da5` H-36,
`feat/synthetic-clouds-phase6-aws`): o `blob_reader.py` ainda exige `exportType`/`blobs`, e
o caminho citado é `<arvore-do-consumidor>` (o `INGESTAO` cita
`<modulo-de-ingestao-do-consumidor>`, sem o prefixo `<arvore-do-consumidor>`). A divergência continua real.

---

## D3 — Rede (4 superfícies) e segurança (3): construir o caminho de ingestão?

**A pergunta.** Construir ingestão para as 10 superfícies em `NÃO IDENTIFICADO` — e, para
`aws/security-hub-asff`, o alvo é **ASFF** ou o formato real de export (`CSV`/`OCSF_JSON`)?

**Por que travava.** **Nenhuma superfície de rede tem ponto de ingestão**, e a razão é dupla e
independente (`INGESTAO:220-242`): nenhum dos três planos de API emite flow log, e não há
leitor por arquivo. O dado existe aqui — o `vpc_flow_logs` entrega **2.376 arquivos num único
dia**. E o ASFF tem uma decisão embutida: a AWS **não** exporta ASFF (`FindingsOutput.Format`
aceita só `CSV`/`OCSF_JSON`), então o alvo atual é um formato que a própria AWS não produz.

| Opção | O que acontecia | Custo |
|---|---|---|
| a) Construir ingestão das 4 de rede | destrava o domínio inteiro; hoje é 100% inconsumível | alto (leitor + destino + modelo) |
| b) Construir só as de segurança, deixar rede de fora | metade; rede continua sem destino | médio |
| **c) Trocar o alvo do ASFF para `CSV`/`OCSF_JSON` e mapear** | deixa de consumir um formato que a AWS não exporta | médio, nos dois lados |

**DECISÃO: separada em duas.** Para o ASFF, **(c)** — hoje a superfície é fiel a um formato
que não é de export. Para rede, **(a) só depois de D4**, porque o flow log sem dimensão de
recurso não junta com nada.

**Estado: pendente, e é o item de maior volume de trabalho.** Duas frentes:

1. **ASFF (c):** o FinOps passa a mirar `CSV`/`OCSF_JSON` e a mapear; **e este
   repositório tem uma consequência a apurar** — a superfície `aws/security-hub-asff` é
   gerada hoje com os campos do ASFF. Se o alvo de consumo muda, a superfície precisa ser
   reespecificada (spec + renderer + teste golden) para o formato que a AWS exporta de
   verdade, com citação por campo. **Não foi feito**: reespecificar é trabalho de spec, com
   URL de evidência por campo, e a regra nº 2 deste repositório proíbe presumir o
   mapeamento.

   **A verificação de 2026-10-14 mudou a natureza deste item: é construção do zero, não
   adaptação.** Medido na revisão `0f5e6da5` H-36: **nada** no FinOps consome ASFF (`ASFF`,
   `FindingsOutput`, `OCSF`, `security-hub` → **0 ocorrências** em `<arvore-do-consumidor>`), e o único
   `service="security-hub"` do backend é um **rótulo de span OTel**
   (`security.py (modulo do consumidor):99`) dentro de um scan que na verdade executa checks de
   S3/SG/IAM/Config — não chama a API do Security Hub. Os outros hits são regex sobre o
   **nome da regra do AWS Config** (`securityhub-<rule>-<8 hex>`). Ou seja: **hoje a
   superfície ASFF não tem destino nenhum no produto**, e a decisão (c) implica construir
   leitor **e** destino.
2. **Rede (a):** só faz sentido depois de D4. São 4 superfícies `aws/vpc-flow-logs-s3`,
   `gcp/vpc-flow-logs-bigquery`, `azure/nsg-flow-logs-v2` e `azure/vnet-flow-logs` — o
   destino de ingestão é do FinOps; este repositório já entrega o dado. **Confirmado
   inconsumível em 2026-10-14:** não há leitor de arquivo para flow log algum
   (`vpcflowlogs`, `flowTuples`, `network_flows`, `flow_log` → 0 leitores; `network_flows` →
   0 ocorrências em todo o backend). Os únicos hits são nome de controle de compliance e
   ação de remediação do agente — nenhum lê o dado.

---

## D4 — Dimensão de recurso: tabela própria ou normalizar `resource_id`?

**A pergunta.** Criar tabela/modelo de recurso (com o `resource_uuid` deste simulador como
chave canônica e uma coluna de id nativo por nuvem), ou normalizar `resource_id` na carga?

**Por que travava.** **Hoje nenhuma junção custo ↔ inventário ↔ achado fecha**
(`INGESTAO:335-360`). Sem uma chave de recurso comum, cada superfície é uma ilha: o custo
sabe o `resource_uuid`, o inventário sabe o id nativo, o achado sabe o que a nuvem publicou.
É a decisão de maior alcance da lista — ela condiciona D3.

| Opção | O que acontecia | Custo |
|---|---|---|
| **a) Tabela de recurso com `resource_uuid` canônico + id nativo por nuvem** | junções passam a fechar; é o desenho que o simulador já sustenta (`model/identity.py`) | alto, mas é fundação |
| b) Normalizar `resource_id` na carga | mais barato; cada leitor normaliza do seu jeito e a divergência volta | médio e recorrente |

**DECISÃO: (a).** Este repositório já cunha `resource_uuid` determinístico e o id nativo
**na forma documentada** por nuvem — a fundação existe e está testada.

**Estado: pendente — executar do outro lado, e a verificação de 2026-10-14 agravou o item.**
Do lado de cá **nada a fazer**: o `resource_uuid` determinístico é emitido hoje e é o que a
decisão adota como canônico. Do lado de lá, **criar a tabela não basta** — medido na revisão
`0f5e6da5` H-36:

- `resource_uuid` tem **0 ocorrências** em `<arvore-do-consumidor>`: o id canônico do simulador **nunca
  chega ao banco**. Ele vive no gerador e nos emuladores (`model/identity.py`, `render/*`,
  `services/*-sim`), não no produto.
- **O custo não carrega identidade de recurso.** Os promotores gravam uma **sentinela**:
  AWS CUR usa `__cur_no_resource__` (`promotion.py (modulo do consumidor):16-18,220`) quando não há
  ARN, e **Azure e GCP gravam sentinela sempre** (`promotion.py (modulo do consumidor):173`,
  `promotion.py (modulo do consumidor):128-136` — "has no resource_id field").
- Não existe tabela de recurso (0 `create_table("resources")`; nenhuma das 71 tabelas de
  `<modelo-de-recurso-do-consumidor>` é de recurso). Inventário e achado usam **strings diferentes** no mesmo
  conceito: `findings.resource_id String(2048)` — a tabela do achado é `findings`, **não**
  `security_findings` —, `ica_observations.resource_identity String(2048)`,
  `ec2_resource_names.resource_id String(64)`, `focus_cost_records.resource_id String(512)`.
- **Nenhum JOIN** liga custo a inventário ou a achado (`join findings|resources|ica_*` em
  `<arvore-do-consumidor>` → 0).

Ou seja: a decisão (a) é a certa, mas o trabalho é maior do que "criar tabela + migração" —
inclui **parar de gravar sentinela** nos promotores Azure/GCP e fazer o custo carregar a chave
de recurso. Enquanto isso, D3-rede fica parado por decisão, não por esquecimento.

---

## D5 — Serviços de ingestão GCP/Azure já escritos e **não plugados**

**A pergunta.** Ligar (`beat_schedule`/endpoint, como o `cur-ingestion`) ou remover?

**Por que travava.** `GcpIngestionService` e `AzureIngestionService` existem, têm testes e
estão sob flag (`config.py:684-687`) — mas **não têm task nem rota**. É código pronto e
inalcançável: o caminho mais curto para ingestão GCP/Azure está a um agendamento de distância.

**DECISÃO: ligar.** É o melhor custo-benefício da lista inteira, e depende de D2 para a
Azure (sem isso, o serviço Azure liga e não descobre nada).

**Estado: pendente — executar do outro lado, na ordem D6 → D2 → D5.** A migração (D6) vem
primeiro porque é onde a fonte de custo GCP/Azure é registrada. **Premissa reverificada em
2026-10-14** na revisão atual: os dois serviços continuam sem chamador fora do próprio
pacote — as únicas células que os citam são `service.py (modulo do consumidor)`,
`service.py (modulo do consumidor)`, `parity.py (modulo do consumidor)` e `promotion.py (modulo do consumidor)`, e as
flags continuam `OFF` por padrão no `config.py (modulo do consumidor):684-685` (o `INGESTAO` cita
`config.py (modulo do consumidor)`; o arquivo é `config.py (modulo do consumidor)`).

**Os dois modelos a copiar já existem, com linha exata** (levantado em `0f5e6da5` H-36): o
agendamento em `celery_app.py (modulo do consumidor):61-80` (`"ingest-cur-periodic"` → task
`sync_all_cur_exports (modulo do consumidor)`, intervalo por
`CUR_INGEST_INTERVAL_MINUTES`, fila `costs`, `time_limit` 3600; gate `:72`), o módulo da task em
`cur_ingestion_sync.py (modulo do consumidor)`, e a rota em `cur_ingestion.py (modulo do consumidor):198`,
montada em `router.py (modulo do consumidor):106` com `prefix="/cur-ingestion"`. Ligar GCP/Azure é
seguir esse par — não há desenho novo a inventar.

---

## D6 — Migração `128_v128_multicloud_cost_sources.py`

**A pergunta.** Aplicar ou não?

**Por que travava.** A migração está marcada "**PROPOSED, NOT APPLIED**" no próprio arquivo
(`:4-6`) e é **pré-requisito** para registrar fonte de custo GCP/Azure sem afrouxar o caminho
AWS (`INGESTAO:789-791`).

**DECISÃO: aplicar**, senão D5 nasce sem onde registrar a fonte.

**Estado: pendente — executar do outro lado.** Reverificado em 2026-10-14 na revisão
`0f5e6da5` H-36: o arquivo está em `consumidor/128_v128_multicloud_cost_sources.py`
(o `INGESTAO` cita `consumidor/...`, sem `consumidor/`), e a marca "PROPOSED, NOT
APPLIED" continua no cabeçalho (`:3-7`).

**A ressalva do id 128 duplicado caiu — não é mais trabalho.** O `WORKSPACE.md` registrava dois
`128` (a linha principal com `128_v128_opportunity_economic_score` e esta migração) e dizia que
aplicar exigiria reencadear o grafo. Na revisão atual **esse duplicado não existe**: só há
`128_v128_multicloud_cost_sources.py` (nem arquivo, nem revisão, em `git rev-list --all`), o
`down_revision` é `127_v127_add_requested_by_to_policy_remediation`, **nada aponta para 128 como
`down_revision`** e a cadeia é linear até aqui — a migração **já é o topo** (o reencadeamento foi
feito nos commits `72bb40f9` e `9857d77c`, ambos ancestrais de HEAD). O que resta é a decisão de
aplicar e tirar o selo "never run".

*Ressalva de escopo:* essa verificação é do head **deste branch**
(`feat/synthetic-clouds-phase6-aws`); este clone não tem `main`/`master` para comparar.

---

## D7 — `source` em `focus_cost_records`: `'cur'` ou `'synthetic'`?

**A pergunta.** Manter `'cur'` (como os promotores gravam hoje) ou passar a `'synthetic'`?

**Por que travava.** A coluna aceita `'synthetic'` (`consumidor/128:119-120`), mas **todos os
leitores FOCUS fixam `source = 'cur'`** — uma linha sob qualquer outro valor fica **invisível**
(OA-2, respondida com evidência em `ESTADO.md:325`). Trocar exige ajustar todos os leitores.

**DECISÃO: manter `'cur'` e registrar a dívida.** O ganho de marcar o sintético é de
auditoria, e este repositório **já marca** todo dado gerado (`markers.py`) — o consumidor
consegue distinguir sintético do real sem depender desta coluna.

**Estado: decidido e vigente — nada a executar.** Confirmado no lado de cá: os promotores
gravam `SOURCE_CUR = "cur"` e o docstring deles diz por quê (`promotion.py (modulo do consumidor):10-12`,
`promotion.py (modulo do consumidor)`). A dívida está registrada aqui e **não** vira mudança.

---

## D8 — Fixar a revisão do simulador que alimenta o ambiente

**A pergunta.** Qual revisão é a fonte, e quem reexecuta o `--audit` ao trocar?

**Por que travava.** Este repositório muda a cada commit. O `--matrix` de 2026-10-14 confirma
`gerado=20 falta=0 bloqueado=1`; a medição de **2026-10-29** (revisão `9533b901`) já é
**`gerado=47 falta=0 bloqueado=2`**, com **49** superfícies especificadas — contra **21** naquela
medição (20 geradas + 1 bloqueada). **Sem revisão fixada, "o simulador" não é um artefato
reproduzível** — e duas medições em revisões diferentes não são comparáveis.

**DECISÃO: registrar a revisão (commit) junto do ambiente e reexecutar `--audit` na troca.**

**Estado: decidido e implementado do lado de cá — falta o lado do ambiente.** Registrar a
revisão à mão em um documento envelhece no commit seguinte, e um documento que afirma a
revisão errada é pior do que um que não a afirma. Então a revisão passou a ser **impressa
pela própria medição** (`fidelity/revision.py`): `--audit`, `--matrix`, `--golden`,
`--ready` e a auditoria de specs terminam com

```
revisao=d44624c  branch=master  arvore=com alteracoes nao commitadas
```

*(O bloco acima é o exemplo de 2026-10-14. A medição de 2026-10-29 imprime, na última linha,
`revisao=9533b901  branch=feat/p76-security-posture-gcp-azure  arvore=limpa` — o formato não
mudou; o valor é que é de outra revisão.)*

Três propriedades deliberadas: fora de um repositório git a revisão vira `desconhecida` e a
medição continua valendo (a auditoria mede artefatos, não git); `arvore` distingue uma
medição reproduzível (limpa) de uma que nenhum commit contém; e o campo nunca mente "limpa"
sem ter olhado. O que falta é do ambiente: **quem acompanha a ingestão fixa o commit que
adota e reexecuta `--audit` na troca** — a saída passa a trazer o commit para conferência.

---

## E1 — Quem aplica as especificações no repositório do FinOps?

**A pergunta.** As três lacunas confirmadas que vivem lá — projeção de **NSG** (`azure-sim`),
router **`sqladmin`** (`gcp-sim`), router **`container` + API Kubernetes** (`gcp-sim`) — são
aplicadas por quem?

**Por que travava.** A regra inviolável nº 1 deste projeto proíbe escrever lá, e você confirmou
mantê-la. A especificação está pronta
(<doc-de-lacunas>.md), com contrato,
arquivo e como provar. **Ela não se aplica sozinha.**

| Opção | O que acontecia |
|---|---|
| **a) Time do FinOps aplica a partir da especificação** | mantém a fronteira; depende de alguém pegar |
| b) Autorizar a escrita pontual neste repo para esses 3 itens | fecha mais rápido; **revoga a regra nº 1** |
| c) Fica parado | as 3 lacunas continuam abertas |

**DECISÃO: (a).** A especificação foi escrita para não exigir reinvestigação.

**Estado: pendente — executar do outro lado.** As três lacunas continuam abertas até alguém
aplicar a especificação; do lado de cá nada muda, e a regra nº 1 continua valendo.
**Verificado em 2026-10-14 na revisão `0f5e6da5` H-36**, com uma correção de caminho e um achado que
muda a ordem:

- **(a) NSG — aberta do lado do FinOps, e a metade de cá está FEITA (2026-10-14).** A rota
  existe e a projeção é vazio-por-desenho
  (`emulators/azure-sim/azure_sim/projections/network.py:29-31` →
  `"""Always empty: the estate models no network security group"""`), com teste próprio do vazio
  (`tests/test_api_resource_plane.py:186`). O consumidor é o mesmo
  (`security.py (modulo do consumidor):107,109`). **Trocar o `return []` sozinho
  não fechava**, porque o estado não tinha `NetworkSecurityGroup`/`SecurityRule` — essa era a
  G1 deste repositório, e ela foi executada: o estado agora tem um NSG por segmento Azure com
  as duas posturas (`Inbound/Allow` e `Deny`), e há superfície nova
  (`azure/arm-network-security-group-rules`) com spec citada, renderer, teste golden e matriz
  (`--matrix`: `gerado=21 falta=0 bloqueado=1`; `--audit`: 12 artefatos, 16 caminhos, 0 colunas
  inventadas). O que falta é a troca do `return []` no `azure-sim`, que continua sendo escrita
  no repositório do FinOps.

  **Atualização de 2026-10-29 — a metade de cá está como estava, e ganhou uma peça.** O
  `azure-sim` passou a aceitar **`api-version` `2026-03-01`** (e mantém `2025-05-01`) nas rotas de
  network security groups, desde **2026-10-26** (commit `211f21c2`); a lista fechada está em
  `emulators/azure-sim/azure_sim/api/network.py:34`, e o comentário do arquivo registra que o valor
  foi lido, não adivinhado (é o default do SDK `33.1.0`). A projeção
  `project_network_security_groups` **continua** devolvendo lista vazia
  (`emulators/azure-sim/azure_sim/projections/network.py:29-31`), então o que falta do lado de cá
  segue sendo exatamente a troca do `return []` — agora com o `api-version` que o cliente real
  envia já aceito pela rota.
- **(b) `sqladmin` — aberta, e o caminho citado mudou.** **Não existe `services/gcp-sim`**: o
  emulador está em `emulators/gcp-sim`, com 11 routers e nenhum `sqladmin`
  (`sqladmin|sql/v1beta4` → 0). O consumidor segue igual
  (`resources.py (modulo do consumidor):118,134`).

  **Atualização de 2026-10-29:** o `gcp-sim` tem hoje **14 routers**
  (`emulators/gcp-sim/gcp_sim/routers/`) e continua **sem** `sqladmin` (`sqladmin|sql/v1beta4` → 0
  na árvore do pacote). A correção de caminho de 2026-10-14 (é `emulators/gcp-sim`, não
  `services/gcp-sim`) continua valendo; entre os routers que entraram depois daquela data estão
  `container` e `infra_manager`, ambos de **2026-10-27**.
- **(c) `container` + API Kubernetes — aberta.** Sem `container.py`, e `container.googleapis.com`/
  `kubernetes`/`/api/v1/namespaces` → 0 na árvore do `gcp-sim`. O consumidor segue igual
  (`gcp.py (modulo do consumidor):407,409,415` e `:100,111`).

  **Atualização de 2026-10-29 — a premissa desta alínea mudou, e é a maior mudança da rodada.**
  O `gcp-sim` passou a servir o plano de controle do Kubernetes Engine:
  `emulators/gcp-sim/gcp_sim/routers/container.py` serve
  `GET /container/v1/projects/{project}/locations/{location}/clusters`
  (`projects.locations.clusters.list`), o front TLS publica `container.googleapis.com` desde
  **2026-10-26** (`deploy/synthetic-clouds/tls-front/nginx.conf`), e a superfície
  **`gcp/container-clusters`** foi especificada em **2026-10-27** — ela está na matriz como
  **BLOQUEADA**, e não como gerada, porque é uma **resposta de API servida ao vivo**, não um
  arquivo de export: a documentação sustenta a forma (envelope `ListClustersResponse` e 4 dos 87
  membros de `Cluster`), mas não há renderer que produza um artefato conferível contra a spec.
  O que **continua** sem nada é a **API server do Kubernetes**: `kubernetes` e
  `/api/v1/namespaces` → 0 na árvore do `gcp-sim` — o emulador serve o contrato de descoberta do
  cluster, não o plano de dados dele. Portanto (c) deixou de ser "aberta do zero" do lado do
  emulador: a metade que faltava foi entregue; o que resta é do lado do FinOps, como em (a).

---

## E2 — Prioridade da G11: auditoria do `gcp_rest_fixtures`

**A pergunta.** Trazer `gcp_rest_fixtures` e `gcp_bigquery` para a matriz de fidelidade agora
ou depois?

**Por que travava.** São os artefatos que **carregam o inventário GCP** para o plano de API — e
estão **fora da auditoria**: o próprio `--matrix` denuncia `renderer sem superficie
especificada`. Ou seja, o caminho por onde o dado GCP chega ao FinOps é o único sem spec
com URL de evidência nem teste golden.

**DECISÃO: depois de G1.** É caro (13 famílias de endpoint) e não bloqueia nada hoje.

**Estado: EM EXECUÇÃO desde 2026-10-14 (G1 fechou). E o escopo mudou ao abrir o item — para
menos, em um lado, e para mais claro do outro.** A frase "`gcp_bigquery` também está fora da
auditoria" era **imprecisa**, e a imprecisão importava:

| Renderer | O que ele é, medido | Lacuna real |
|---|---|---|
| `gcp_bigquery` (189 linhas) | probe Phase-1 que **deriva as colunas da spec** `gcp/billing-export-standard` pelas mesmas funções do topology (`render/gcp_bigquery_topology.py:61-68`) | **nenhuma de superfície.** Ele emite a MESMA superfície que `gcp_bigquery_topology` (que já tem spec, golden e entrada na matriz). O `--matrix` o acusa porque a matriz credita a superfície a **um** renderer — um segundo produtor do mesmo contrato aparece como "não mapeado" sem ser lacuna |
| `gcp_rest_fixtures` (590 linhas) | 13 fixtures de resposta de API em **6 famílias** (Cloud Asset Inventory, SCC, Recommender, Billing Catalog, Cloud Monitoring 3×, Budgets); o próprio docstring admite "best-effort official-shaped" com `TODO-verificar #7` em quase todo campo | **é a lacuna.** São os artefatos por onde o inventário GCP chega ao plano de API, sem spec com URL de evidência nem teste golden |

Ou seja: das duas, **uma não é lacuna de superfície e a outra tem 6 famílias, não uma**. O
trabalho daqui é (i) escrever o contrato oficial das famílias do `gcp_rest_fixtures` e
confrontar o artefato com ele — o que vai exigir **evidência nova**, porque o renderer foi
escrito de memória —; e (ii) decidir o que fazer com o `gcp_bigquery`, que hoje é um segundo
produtor da mesma superfície: declará-lo como tal na matriz, ou aposentá-lo. A decisão (ii)
não é técnica: é escolher se o repositório mantém dois renderers para o mesmo contrato.

**Um risco concreto, agora medido com a documentação oficial do protobuf — e ele é mais estreito
do que eu escrevi antes, e mais interessante por isso.** O `gcp_rest_fixtures` emite uma chave de
topo sintética — `resourceUuid` — em cinco famílias (CAI `searchAllResources` e
`searchAllIamPolicies`, SCC findings, Recommender recommendations e insights), como junção entre
planos. Verificado: **`resourceUuid` ocorre ZERO vezes nos seis documentos oficiais completos** —
não é campo de `ResourceSearchResult`, `IamPolicySearchResult`, `Finding`, `Recommendation`,
`Insight` nem `AlertPolicy`. O código do renderer já registra, para `alertPolicies`, que o campo
**quebrou o parse** do cliente (*"ParseDict fails with has no field named resourceUuid"*).

O que a documentação oficial acrescenta é a **delimitação**: a rejeição de campo desconhecido é do
caminho **JSON → proto** (`ParseDict(..., ignore_unknown_fields=False)` é o default, e o ProtoJSON
*"should reject unknown fields by default"*); o transporte **gRPC binário preserva** campo
desconhecido em vez de falhar (*"Proto3 messages preserve unknown fields and include them during
parsing"*). Como o consumidor usa **os dois** caminhos, o campo é sempre **não documentado** — o que
basta para a fidelidade —, mas o efeito em produção **depende do transporte**. A remoção é correta
por contrato e *potencialmente* necessária por função; não é uma falha garantida.

O levantamento completo das 6 famílias, com URL e trecho por campo, está em
[CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md) — escrito para a auditoria das famílias restantes não
ter de ser refeita. Dois resultados que ele fixa: **nenhum erro de envelope existe** (os dez nomes
de campo de lista que o renderer usa estão todos corretos), e há **valores sintéticos dentro de
campos reais** em quatro famílias (o `name` do CAI, o `resourceName` do SCC, o `projects/-` do
Recommender e dois labels do Monitoring) — esses não são campos a remover, são valores a marcar.

**Primeira família FECHADA (2026-10-14): Cloud Asset Inventory `searchAllResources`.** Superfície
`gcp/asset-search-all-resources`, com spec citada no proto oficial (nível do envelope e nível do
item), renderer novo, projeção nos dois níveis, teste golden e entrada na matriz — sem tocar no
`gcp_rest_fixtures`. **As outras 10 fixtures também estão FECHADAS** (mesma data): cada endpoint
virou uma superfície com contrato conferido nos dois níveis, num driver de dados
(`render/gcp_api_fixtures.py`) em vez de dez renderers copiados. São elas: CAI
`searchAllIamPolicies`, SCC `sources` e `findings`, Recommender `recommendations` e `insights`,
Billing Catalog `services` e `skus`, Monitoring `timeSeries`, `metricDescriptors` e
`alertPolicies`, e Billing Budgets `budgets`.

`--matrix`: **`gerado=33 falta=0 bloqueado=1`**; `--ready`: **33 superfícies PRONTO**; `--audit
gcp`: 19 superfícies, **0 colunas inventadas**. O `gcp_rest_fixtures` e o `gcp_bigquery` seguem
sem superfície própria — e é a decisão que fica aberta: o primeiro é o produtor antigo das mesmas
11 superfícies, e o segundo é um **segundo produtor** da superfície de billing que o
`gcp_bigquery_topology` já serve. Manter dois produtores por contrato, ou aposentar um, é escolha
de produto.

**Efeitos funcionais que a auditoria revelou, e que não são só de fidelidade:** o artefato
conforme do Monitoring entrega apenas o label `project_id` — o único comum aos dois tipos
monitorados —, então um leitor que resolva a série pelo label do recurso (`instance_id`/
`database_id`) não acha o recurso por ali. Emitir as chaves condicionais exigiria uma spec com
**dois contratos disjuntos** (o mecanismo de `sets` que este repositório já usa), e é trabalho
nomeado, não um ajuste de uma linha.

**Estado em 2026-10-29 — a decisão de produto continua aberta, e nada foi aposentado.** A medição
desta data (revisão `9533b901`) é **`gerado=47 falta=0 bloqueado=2 total=49`**, e a matriz continua
reportando os mesmos dois *renderers sem superfície especificada*: `gcp_bigquery` e
`gcp_rest_fixtures`. Os números `gerado=33` / `33 PRONTO` acima são a medição de 2026-10-14 e
ficam como evidência datada. As 11 superfícies do G11 continuam **geradas**, e o
`gcp_rest_fixtures` continua com **590 linhas e 13 fixtures** — a única delas sem superfície é
`cai_analyze_iam_policy.json` (`analyzeIamPolicy`), como registra
[CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md). Nenhuma escolha entre "manter os dois" e "aposentar
um" foi tomada nesta rodada. *(O parágrafo de "efeitos funcionais" acima é a leitura de
2026-10-14; o E4, na tabela de estado consolidado, registra o que foi feito depois: as chaves
condicionais entraram por conjuntos nomeados.)*

---

## E3 — Volume e retenção com o horário novo

**DECIDIDO em 2026-10-14: perfil `medium`**, com a ressalva de disco medida abaixo. A
configuração em `schedule/config.json` foi alterada (`profile: small → medium`) e validada por
`schedule show`; o restante (`12:00`, `America/Sao_Paulo`, retenção **30**, seed 123) não mudou.

**Atualização de 2026-10-29 — o agendador mudou de novo, e não foi o perfil.** A configuração
desta instalação (`tools/synthetic_clouds/schedule/config.json`, **não versionado**) está com
`profile=medium`, `lag_days=0`, `time=12:00`, `time_zone=America/Sao_Paulo`,
`retention_days=30`, `seed=123`, `currency=USD`. O **`lag_days=0`** entrou em **2026-10-26**
(commit `1f674563`): o simulador gera dias completos e entrega o dia corrente — não há export
parcial a esperar. O código (`schedule/config.py`) mantém o **padrão de fábrica** (`lag_days=1`,
`time=06:30`, fuso UTC com aviso); voltar ao padrão é `schedule set --lag-days 1`. O perfil e a
retenção **não** mudaram nesta rodada, e a revisão marcada do teto de disco continua valendo.

**Segunda decisão, no mesmo dia: a retenção fica em 30 dias por ora, com revisão marcada.** A
opção (i) abaixo (15 dias) foi apresentada com o teto medido e **não** foi adotada: o disco
enche antes da primeira poda fazer efeito, e o risco é assumido de forma explícita, não
silenciosa. Revisar é o gatilho — quando a ocupação acumulada de `out/daily/` se aproximar do
espaço livre de `D:` no momento, ou no primeiro tick que falhar por espaço —, e a escolha volta
para a mesa com o mesmo número. Na leitura de `2026-10-14T17:54` isso deixou de ser urgente:
`D:` tinha **26,67 GB** livres contra um teto de ~17 GB.

**A pergunta.** Com o agendador em **12:00** e retenção de **30 dias**, manter perfil `small`
(61,3 MB/dia, ~1,8 GB/mês sem poda) ou subir para `medium`/`large`?

**Por que importa.** `medium` (janela de 120 dias) e `large` (400) **multiplicam o volume por
execução**, e a retenção de 30 dias passa a ser o teto do disco.

### Medição que sustenta a decisão (2026-10-14, dia 2026-10-13)

Método: `build_day` + `emit_day` para o mesmo dia, com as 19 superfícies, em diretório de
rascunho fora de `out/daily` (não toca o ledger nem os artefatos publicados). Seed 123, USD.

| | `small` | `medium` | fator |
|---|---|---|---|
| recursos por escopo × 9 escopos | 79 × 9 = **711** | 370 × 9 = **3.330** | 4,7× |
| `billing_lines` | 9.031 | 42.247 | 4,7× |
| `findings` | 86 | 368 | 4,3× |
| `inventory_assets` | 711 | 3.330 | 4,7× |
| `network_flows` | 2.664 | 12.312 | 4,6× |
| artefatos escritos | 2.727 | **11.997** | 4,4× |
| arquivos em disco | 2.736 | **12.006** | 4,4× |
| **bytes em disco** | **61,3 MB** | **281,3 MB** | **4,6×** |
| build + render | 9,7 s | 49,4 s | 5,1× |

Duas correções de leitura que a medição impõe:

1. **A janela `medium` (120 dias) não é a janela gerada.** O dia é *month-to-date* por
   construção (`daily/window.py`); o perfil entra pela **densidade de recursos**
   (`_resources_per_scope`, `PROFILE_WINDOW_DAYS` = 45/120/400 contra `PROFILE_TARGET_ROWS`
   = 40 k/500 k/2 M). Por isso `medium` multiplica o volume por ~4,6× **no mesmo dia**, e o
   volume de um dia cresce ao longo do mês (a janela de 2026-10-13 tem 13 dias; a de
   2026-10-31 teria 31).
2. **49,4 s por dia é irrelevante para o agendador** — o limite da tarefa é 4 h, e o backfill
   máximo são 31 dias.

### O teto de disco — a ressalva

Retenção de 30 dias com `medium` não é 30 × 281 MB: cada dia carrega uma janela de tamanho
diferente. No regime permanente (janelas de 13 a 31 dias), a média fica em ~24–26 dias de
janela, ou seja **~17 GB** para 30 dias retidos (30 × ~560 MB); o pior caso teórico (30
janelas de 31 dias) é **~20 GB**.

**Espaço em `D:`: 26,67 GB livres** — leitura de `2026-10-14T17:54`, já **depois** da regeração
em `medium`. Foi 12,10 GB medidos às `17:36` do mesmo dia; a diferença de +14,57 GB **não** vem
desta sessão (a única remoção feita aqui foi o diretório `123-small-USD`, 61,3 MB, e os
diretórios de topo do workspace somam ~1,25 GB), então não atribuo causa — registro a leitura.

Consequência para a decisão: os ~17 GB de teto para 30 dias **cabem** nos 26,67 GB livres, e a
saída (ii) deixa de exigir liberar espaço. O teto continua sendo o teto — a revisão marcada
abaixo é o que impede o disco de encher em silêncio quando o volume acumulado se aproximar do
livre.

As duas saídas, medidas:

| Saída | O que custa |
|---|---|
| **(i) retenção 15 dias** (`schedule set --retention-days 15`) | teto medido ~8–10 GB; metade do histórico retido |
| **(ii) manter 30 dias** | teto ~17 GB, que **cabe** nos 26,67 GB livres de hoje — mas não nos 12,10 GB medidos de manhã |

**Escolhido: manter 30 dias por ora e revisar depois** — ou seja, (ii). Com o espaço livre de
hoje a opção deixa de ser arriscada no curto prazo; a revisão continua marcada porque o teto
de 30 dias cresce com a janela e o livre pode voltar ao valor da manhã. `large` (2 M linhas)
segue fora de questão: seriam ~4× o `medium`.

### Efeito colateral da troca de perfil — resolvido no mesmo dia

O ledger conta **dias**, não perfis, então o dia `2026-10-13` já estava `complete` e **não**
seria regerado sob `medium`; e a poda apaga o diretório do **dia**, não o da densidade — as
duas conviveriam. Resolvido no mesmo dia: `tick --force` regerou o dia (**11.997 artefatos**) e
o diretório da densidade antiga foi removido.

```
out/daily/2026-10-13/123-small-USD/     <- removido (2.736 arquivos / 61,3 MB)
out/daily/2026-10-13/123-medium-USD/    <- o dia publicado, em medium
```

O ledger ficou com `artifacts: 11997` para `2026-10-13` e `last_run.status = ok`. Vale notar o
que **não** foi tocado: a retenção continua em 30 dias, e nenhum dia saiu do ledger.

---

## Estado consolidado

Verificação de premissas feita em **2026-10-14** por leitura somente-leitura do FinOps na
revisão `0f5e6da5` H-36 (`feat/synthetic-clouds-phase6-aws`), arquivo:linha. **Nada foi escrito lá** —
o que a verificação mudou está marcado abaixo. *Escopo:* este clone só tem refs
`feat/synthetic-clouds*`; não há `main`/`master` para comparar, então as afirmações valem para o
head deste branch.

| Item | Decisão | Estado |
|---|---|---|
| D1 | (b) por plano: este repo para arquivo e fixtures GCP | **pendente** — trocar o nome do manifesto em 4 arquivos no FinOps (verificado: nada mudou de lugar) |
| D2 | (a) FinOps descobre Azure sem manifesto | **pendente** — leitor de blob; simulador não muda (verificado) |
| D3 | (c) ASFF para `CSV`/`OCSF_JSON`; rede (a) **depois de D4** | **ESPECIFICAÇÃO PRONTA em 2026-10-15** — [INGESTAO-D3-SEGURANCA.md](INGESTAO-D3-SEGURANCA.md). **A linha anterior deste registro ("não é adaptação, é construção do zero") estava errada, e a medição desmente.** O que existe no FinOps: a tabela `findings` (19 colunas), o `SecurityFindingAdapter`, o lift Celery `ingest_security_findings` com batching de 500, a flag `OPPORTUNITY_SECURITY_PRODUCER_ENABLED` (fail-closed) e o agendamento CIP com `allowlist`. O que não existe: o **writer** — hoje o canônico é `scan_security.scan_workspace_security`, que chama a API da nuvem e não tem credencial em homologação. Placar do mapeamento ASFF → `findings`, medido: **9 colunas diretas, 4 derivações, 5 ausentes no formato, 2 chaves estrangeiras**. E o achado que encolhe o trabalho: `_SEVERITY_TO_RISK` do adapter usa `CRITICAL/HIGH/MEDIUM/LOW/INFORMATIONAL`, **exatamente** o `Valid Values` do `Severity.Label` que o simulador emite, e normaliza com `.upper()` — o contrato já foi feito para tolerar o que o simulador produz. **A decisão que bloqueia a execução:** `evidence`, `exposure` e `impact` são `Text NOT NULL` e o ASFF **não tem equivalente algum**; `fingerprint` é único por workspace e **não pode ser o `Id` do ASFF**. Três saídas na então §5 do documento (numeração de 2026-10-15; ver a atualização de 2026-10-29 nesta linha): sintetizar no writer, sentinela explícita, ou tornar as colunas `nullable` — todas mudam o produto, todas são suas. **Atualização de 2026-10-29 — a referência e o placar envelheceram, e são dois fatos distintos:** (a) a INGESTAO foi **renumerada** (§6→§5, §7→§6) e a §5 hoje é *«O que já está entregue e onde isso vale»*; mais do que isso, a reescrita de 2026-10-16 **removeu** aquelas três saídas do documento, e o que a §5 registra hoje é que o simulador carrega `category`, `evidence`, `exposure`, `impact` e `fingerprint` no `UserDefinedFields` do ASFF (commit `b3dd315` H-18), com a impressão recalculável a partir do documento — a ponte passa a existir se o caminho for o ASFF, e isso vale como molde da superfície nova; (b) o **placar do mapeamento** desta linha (9 diretas / 4 derivações / 5 ausentes / 2 chaves estrangeiras) é a medição de **2026-10-15**, e a §5 da INGESTAO registra hoje **13 diretas · 1 derivação de cardinalidade · 1 de vocabulário · 2 chaves estrangeiras (`workspace_id`, `cloud_account_id`) · 0 ausentes** — o placar **vigente** é esse, porque a INGESTAO é o documento canônico da ponte, reescrito em 2026-10-16 e atualizado em 2026-10-29; o placar de 2026-10-15 fica como evidência datada, e a diferença entre os dois **não foi reexplicada nesta rodada** |
| D4 | (a) tabela de recurso com `resource_uuid` canônico | **pendente** — e **maior do que parecia**: o custo nem carrega identidade de recurso (promotores gravam sentinela) |
| D5 | ligar os serviços de ingestão | **pendente** — ordem D6 → D2 → D5; os dois modelos a copiar existem (beat `celery_app.py:61-80`, rota `router.py:106`) |
| D6 | aplicar a migração 128 | **pendente, e mais simples do que estava escrito** — o id 128 duplicado **não existe** nesta revisão: a migração já é o head da cadeia, então não há reencadeamento a fazer |
| D7 | manter `'cur'` | **vigente** — nada a executar (verificado) |
| D8 | fixar a revisão e reexecutar `--audit` na troca | **implementado aqui** (a revisão sai na medição); o ambiente fixa o commit |
| E1 | time do FinOps aplica a especificação | **pendente do lado de lá** — **(a) NSG**: a metade de cá está feita (estado com NSG + superfície `azure/arm-network-security-group-rules`); falta trocar o `return []` no `azure-sim`. **(b)** e **(c)** seguem abertas; o caminho do GCP é `emulators/gcp-sim`, **não** `services/gcp-sim` |
| E2 | auditoria do `gcp_rest_fixtures` depois de G1 | **FEITO em 2026-10-14** — 11 superfícies novas (as 11 fixtures), com spec, golden e matriz; `--matrix` `gerado=33`, `--ready` 33 PRONTO. **Resta uma escolha de produto:** o que fazer com o `gcp_rest_fixtures` (produtor antigo das mesmas 11) e com o `gcp_bigquery` (segundo produtor da superfície de billing) |
| E3 | perfil `medium`, retenção 30 com revisão marcada | **feito** |
| E4 | **lacuna funcional de Monitoring** — os labels condicionais ao tipo | **FEITO em 2026-10-14** — a superfície `gcp/monitoring-time-series` voltou a emitir os labels do **tipo monitorado** (`gce_instance`: `instance_id`/`zone`; `cloudsql_database`: `database_id`/`region`), sem os quais a série **não é atribuível ao recurso**. A condicionalidade é expressa pelo mecanismo de **conjuntos nomeados** do projeto (`gce_instance_labels`, `cloudsql_database_labels`), e não em prosa: nenhum registro carrega os cinco, e um conjunto por tipo é o que permite conferir cada um. `--matrix` `gerado=34`; `--audit gcp`: a superfície entrega 3 arquivos, 50 registros, 16 caminhos, **0 colunas inventadas** |
| E5 | **ASFF/OCSF: a superfície do formato que a AWS exporta** | **FEITO em 2026-10-14** — superfície nova `aws/security-hub-ocsf-export` (27 colunas, JSON por linha), com a forma do arquivo, os caminhos OCSF e o residual citados na fonte: [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md#contrato-ocsf-do-security-hub-aws--levantado-para-o-item-e5). O `aws/security-hub-asff` **não foi reescrito** — a leitura mostrou que ele descreve corretamente a **resposta da API**, e que o D3(c) pedia uma superfície **nova** para o export. `--matrix` `gerado=34`; `--audit aws`: 1 arquivo, 59 registros, 27 caminhos, **0 colunas inventadas**. **Duas lacunas ficam declaradas, não resolvidas por analogia:** a **classe OCSF** do envelope (`class_uid`/`category_uid`/`type_uid`) e o `metadata.version`. **Residual reprocurado em 2026-10-15 e declarado encerrado sem valor**: a AWS publica `class_name` como caminho do export e nunca o identificador numérico nem os valores, e a única frase de versão da AWS ("supports findings in OCSF schema version 1.6") é sobre a revisão suportada pelos achados do serviço, não sobre o campo no arquivo — registro com URLs em [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md#o-residual-procurado-de-novo-2026-10-15). **Uma terceira lacuna foi FECHADA por evidência no mesmo dia:** `severity_id`, cuja enum estava apenas "não lida nesta execução" — ver [CONTRATO-APIS-GCP.md](CONTRATO-APIS-GCP.md#a-lacuna-que-a-busca-fechou-severity_id-2026-10-15) |

## Estado consolidado (2026-10-29)

Medição desta data, revisão **`9533b901`**, branch **`feat/p76-security-posture-gcp-azure`**,
árvore limpa no início da revisão; `main` está em **2026-10-24** e esta branch está **18 commits à
frente**. A tabela de 2026-10-14 acima **não foi reescrita** — ela é a evidência daquela data. O
que é medido hoje está aqui.

| Medida | 2026-10-29 |
|---|---|
| superfícies especificadas | **49** — AWS **15** · GCP **23** · Azure **11** |
| `fidelity --matrix` | **`gerado=47 falta=0 bloqueado=2`** |
| `fidelity --ready` | **47 superfícies PRONTO** |
| bloqueadas pela documentação | **2** — `azure/cost-management-export-cost-details` (a Microsoft publica nomes sem tipos; nenhum dos 132 nomes aparece nos cinco contratos ao mesmo tempo) e `gcp/container-clusters` (**nova desde 2026-10-27**: a doc sustenta a forma, mas é resposta de API servida ao vivo pelo `gcp-sim`, não export — sem renderer, "implemented" seria mentira) |
| colunas declaradas nas 49 specs | **2.637** (soma de `columns` e `sets`) — a opção (b) do D1 citava 2.204 em 2026-10-14 |
| colunas obrigatórias sem tipo publicado | **401**, em **4** superfícies: `cost-details` 272, `vnet-flow-logs` 107, `nsg-flow-logs-v2` 18, `scc-findings-bigquery` 4 |
| itens em `docs/NAO-COMPROVADOS.md` | **293 em 49 de 49 superfícies** — AWS **88** · Azure **83** · GCP **122** |
| renderers sem superfície especificada | `gcp_bigquery`, `gcp_rest_fixtures` — a decisão de produto do E2 continua aberta |
| arquivos versionados | **492** (`git ls-files`) |
| suíte de testes (medida da rodada) | **1106 passed · 20 skipped** — 1126 casos coletados — em **14m00s**, revisão `9533b901`, com o comando `pytest tools\synthetic_clouds\tests` |
| specs em prosa | **30** arquivos `.md` em `specs/<provedor>/` (aws 8 · azure 12 · gcp 10) — 31 se o `specs/README.md` entrar na conta, e ele não é spec de superfície |
| emuladores | **4** — `aws-sim`, `azure-sim`, `gcp-sim`, `k8s-sim` (o `k8s-sim` **tem** `Containerfile` e serviço de compose — `compose.k8s.yaml` — desde a S4b2-B, e é publicado por TLS no front desde a S4b2-E) |

**O que mudou nas decisões desde a baseline de 2026-10-19, e o que não mudou:**

* **D3/E5 — fechado, e agora com número.** A superfície `aws/security-hub-ocsf-export` é **gerada**
  (renderer `security_hub_ocsf_export`); a spec dela declara hoje **29 colunas** (o "27 colunas"
  das linhas acima é a medição de 2026-10-14/15) e mantém **quatro** temas em `unverified`: a
  classe OCSF, o `metadata.version`, o particionamento e
  `compliance.assessments/control/standards`. O `aws/security-hub-asff` continua com 96 colunas,
  todas verificadas.
* **E1(a)** — a metade de cá segue feita, e o `azure-sim` passou a aceitar **`api-version`
  `2026-03-01`** nas rotas de network security groups (2026-10-26, commit `211f21c2`). A projeção
  `networkSecurityGroups` continua vazia por desenho; falta a troca no FinOps.
* **E1(b)** — o `gcp-sim` está em `emulators/gcp-sim` com **14 routers** e continua sem `sqladmin`.
* **E1(c) — a premissa mudou, e é a mudança mais concreta da rodada.** O `gcp-sim` serve
  `container v1` (`projects.locations.clusters.list`) desde 2026-10-26, o front TLS publica
  `container.googleapis.com`, e a superfície `gcp/container-clusters` foi especificada em
  2026-10-27 (bloqueada por não haver artefato durável). A API server do Kubernetes continua não
  servida.
* **D8** — a medição de hoje imprime, na última linha,
  `revisao=9533b901  branch=feat/p76-security-posture-gcp-azure  arvore=limpa`. O ambiente ainda
  não fixou o commit que adota.
* **E2** — nenhuma escolha nova: os dois renderers seguem sem superfície e nada foi aposentado.
* **E3** — o perfil e a retenção não mudaram; o `lag_days=0` entrou em 2026-10-26 (commit
  `1f674563`).
* **Nenhuma decisão D1–D7 nem E2/E3 foi resolvida pela onda de 2026-10-24..28.** Ela mexeu em
  emuladores (TLS com hostnames reais, `container v1`, drift, what-if), no agendamento (lag 0) e no
  `k8s-sim` (contrato OpenCost) — isto é, mudou a **evidência disponível** e as superfícies
  entregues, não as escolhas que dependem do outro repositório.

**O que esta rodada não reverificou, e não pode ser lido como estado de hoje:** as premissas de
D1–D7 e E1 que vivem no repositório do FinOps (`cur_ingestion.py`, `promotion.py`,
`celery_app.py`, `blob_reader.py`, a migração 128 e as flags de ingestão). Essa árvore **não está
neste workspace** — não há `promotion.py` nem `cur_ingestion.py` nela —, então as medições
`0f5e6da5` H-36 continuam sendo a evidência datada de 2026-10-14, preservada como tal. Remedi-las
exigiria a árvore do outro repositório; o que esta rodada fez foi atualizar o que é medível aqui
(superfícies, matriz, specs, emuladores, agendamento e as metades de cá de E1).

## O que este repositório segue fazendo

**A fila de execução — trabalho que não depende de ninguém atravessar a regra nº 1:**

| Ordem | Trabalho | Tamanho | Por quê nesta ordem |
|---|---|---|---|
| 1 | **A classe OCSF do export** (`class_uid`/`category_uid`/`type_uid`) e o `metadata.version` | evidência, depois pequeno | **FECHADO em 2026-10-15 — com o residual DECLARADO, não resolvido.** Deixados fora do artefato de propósito no E5; esta rodada procurou a página (ou um exemplo de saída) que dissesse a classe. O que a AWS publica é o **nome** do discriminador (`class_name`, no catálogo do export e na tabela das regras de automação) sem o identificador numérico e sem os valores; e a única frase de versão da AWS é sobre a revisão **suportada** pelos achados, não sobre o campo no arquivo exportado, cuja lista de campos sequer publica `metadata.version`. Sem valor, o contrato fica fiel a uma omissão declarada. Se um dia aparecer exemplo de saída, é evidência de campo — e o item reabre como peça nova, não como dedução |
| 2 | **Os dois produtores** (`gcp_rest_fixtures`, `gcp_bigquery`) | decisão de produto, **já revisada** | **DECIDIDO em 2026-10-15: manter os dois, e não_write spec.** O enquadramento original ("dois produtores do mesmo contrato") estava **errado**, e vale registrar por quê. (a) `gcp_api_projection.py` não é produtor nenhum: é **biblioteca compartilhada**, importada por `gcp_api_fixtures.py` e por `gcp_cai_search_all_resources.py`, e some com qualquer cenário. (b) Os dois renderers **não concorrem pelo mesmo contrato**: `gcp_rest_fixtures` é o plano REST (590 linhas, alimenta o emulador, tem teste próprio, e as specs o citam como origem de duas chaves de junção que o contrato oficial recusa) e `gcp_bigquery` é a **sonda da Fase 1**, que o próprio `gcp_bigquery_topology.py` declara substituir. (c) O que o auditor acusa não é concorrência, é **`[renderer sem superfície]`**: os dois estão registrados e **nenhuma spec os reclama**. A resposta que bate com a disciplina do projeto é **escrever spec**, não aposentar: aposentar o `gcp_rest_fixtures` derrubaria justamente o produtor que expõe o conflito com o contrato oficial. O `gcp_bigquery` é o único candidato real a aposentadoria — e isso quebra dois arquivos de teste, o que é trabalho, não decisão |
| 3 | **O `attic/` quebrando o `pytest` na raiz** | uma linha, decisão tomada | **FECHADO em 2026-10-15 por sua decisão: `conftest.py` na raiz com `collect_ignore_glob = ["attic/*"]`.** O enquadramento original (meu) era que o teste importava "um módulo que não existe mais" e que a pasta deveria ser **quarentenada**. Lendo o `attic/README.md`, as duas coisas estavam erradas: o pacote `coverage/` inteiro (~1.800 linhas) está lá, **arquivado junto com as suas 17 provas**, e a pasta é uma decisão documentada, com a regra escrita na primeira linha. Quarentenar o arquivo teria jogado fora um artefato escolhido para ser guardado. O conserto correto era **codificar a regra**: medido antes e depois, `pytest` na raiz e `pytest tools\synthetic_clouds\tests` coletam os **mesmos 880 testes**, mesmo `rootdir`, mesmo `configfile`. Um detalhe que fica registrado: se a fase de ingestão reativar o material, o import precisa apontar para `attic/product-coupled/coverage/`, que tem **hífen** no caminho e exige `importlib`. **Nota de 2026-10-29 — este registro vale para a árvore original; neste repositório ele está duplamente obsoleto:** (a) `attic/` **não existe** nesta árvore nem no histórico git (`git ls-tree HEAD attic` vazio), então o `collect_ignore_glob = ["attic/*"]` do `conftest.py` da raiz é **vestigial**; (b) `pytest` na raiz **hoje** coleta **1661 casos com 23 erros de coleção** — os testes dos emuladores exigem `boto3`/`botocore`, que não estão no `.venv` do gerador, e a coleta ainda entra em diretórios alheios (`uvcache/`, `pytest-of-*`) —, e a suíte canônica é `pytest tools\synthetic_clouds\tests`, medida em 2026-10-29 na revisão `9533b901` em **1126 casos coletados / 1106 passed / 20 skipped**. O "880 testes" é o número daquela árvore em 2026-10-15 e fica como evidência datada. |
| 4 | **Vigiar o teto de disco de E3** | barato | A retenção de 30 dias com `medium` pede ~17 GB; `D:` tinha 12,10 GB de manhã e 26,67 GB às 17:54. Revisar quando a ocupação se aproximar do livre |
| 5 | **Manter a documentação viva** | contínuo | `ESTADO.md`, `<doc-de-cobertura>.md` e este registro |
| 6 | **Atacar o registro dos não comprovados** (295 em 2026-10-15; **293** em 2026-10-29) | fila contínua, cada item é pequeno | [NAO-COMPROVADOS.md](NAO-COMPROVADOS.md) consolida o que o projeto **ainda não provou** (114 na AWS, 70 na Azure, 111 no GCP), com o motivo que cada spec já registrava e a distinção **campo** (nome que não pertence ao contrato) × **tema** (nome que existe e cuja prova falta). É a lista de onde saem os próximos trabalhos de evidência — e é gerada, não escrita à mão. *O total cai quando uma lacuna é fechada por evidência: 299 → 296 → **295** em 2026-10-15 (`severity_id` do export OCSF, `Severity.Label` e `Severity.Normalized` do ASFF, e as quatro enums do `scc-findings`). Correção de uma afirmação minha que saiu errada: eu havia escrito que "o registro conta cada entrada **duas** vezes, então fechar 1 item baixa 2 no total". Não é uma regra — a medição desmentiu. Uma entrada removida do `scc-findings` baixou o total em **1**, e o GCP foi de 112 para 111. A contagem é o que o gerador derivar das specs, e ela varia com a forma como a spec declara a entrada. O que vale é a contagem observada no momento da geração, nunca uma regra sobre ela.* **Nota de 2026-10-29 — o registro atual tem outro número:** regenerado nesta data pelo gerador versionado (`specs/_tools/gerar-registro-nao-comprovados.py`), `docs/NAO-COMPROVADOS.md` tem **293 itens em 49 de 49 superfícies — AWS 88 · Azure 83 · GCP 122**; os números 295/114/70/111 desta linha são a contagem de 2026-10-15 e ficam como histórico. A diferença entre as duas contagens **não foi reexplicada nesta rodada** — o que vale, como a própria frase acima diz, é a contagem observada na geração de hoje. |

**Triagem da fila (2026-10-15) — a informação que decide se vale atacar:** nem todo item do registro é trabalho de leitura. Dois classificadores foram escritos para separar *"a fonte não publica"* de *"a página existe e ninguém a leu"*: `.artifacts/inventario-nao-comprovados.py` (lista) e `.artifacts/auditar-classificador.py` (audita o classificador). Resultado corrigido:

| Provedor | Itens | Em espera de leitura | Onde estão |
|---|---|---|---|
| AWS | 114 | 0 | — |
| Azure | 70 | **1** | template de VM: `osDisk` transcrito só para `dataDisks` |
| GCP | 111 | **0** | — (as 3 que estavam aqui foram fechadas ou reclassificadas na mesma leva: ver abaixo) |
| **Total** | **295** | **1** | |

Ou seja: **294 dos 295 itens só fecham se o provedor mudar a documentação.** Sobrou **uma** leitura
de verdade em toda a fila: o `osDisk.managedDiskProperties.*` do template de VM na Azure. Tudo o
mais é lacuna estrutural do provedor ou trabalho de modelagem — e modelagem **não** é leitura.

**Terceira leva, 2026-10-15, e ela muda a recomendação acima.** As três entradas que ainda estavam
nesta tabela como "leitura pendente" no GCP foram resolvidas, cada uma do seu jeito:
1. **As quatro enums do `scc-findings` (`State`, `Severity`, `Mute`, `FindingClass`) foram FECHADAS**
   — lidas no discovery v1 e transcritas como `allowed_values`. Uma delas ainda estava escrita na
   seção anterior como "transcrita"; agora saiu de `unverified` de verdade.
2. **Os campos internos dos sub-objetos do `scc-findings` (67) foram RECLASSIFICADOS como trabalho
   de modelo**, não de leitura: a fonte publica, mas o renderer emite `finding.indicator`,
   `finding.vulnerability` e `finding.access` como objetos VAZIOS.
3. **Os campos aninhados de `compute-instances-rest` foram RECLASSIFICADOS pelo mesmo motivo**: o
   renderer emite `disks[]` e `guestAccelerators[]` como listas vazias.

A tabela original dizia GCP **3** e total **4**. A medição de agora, depois dessas três ações, é
GCP **0** e total **1**. Registrar a tabela sem reexecutar o classificador é como ela ficou
desmentida — por isso o número aqui é o que o `inventario-nao-comprovados.py` imprime, e não uma
estimativa.

**Segunda reclassificação, na mesma leva (2026-10-15):** três itens que a triagem markava como
"leitura pendente" (`ACCESS_POLICY`/VPCSC, `OS_INVENTORY` e `RELATIONSHIP` do
`cloud-asset-inventory-compute-instance`) **não eram leituras pendentes — eram divergência de
escopo**. A página publica esses três schemas, mas eles descrevem os contentTypes
`ACCESS_POLICY`, `OS_INVENTORY` e `RELATIONSHIP`, enquanto o escopo da superfície é a tabela de
`compute.googleapis.com/Instance`. Transcrevê-los teria colocado colunas de outro content type na
tabela de uma instância de computação. Isso derrubou a conta de pendentes de leitura de 6 para 3
no GCP. Um item que parece trabalho pendente às vezes é, na verdade, uma pergunta errada — e o
classificador, por ser cego para escopo, não tinha como dizer isso.

**Lição de método que a triagem produziu, e que vale mais que o número:** o primeiro classificador devuelveu **1** item em GCP e **0** na Azure, e essa conclusão estava errada. O motivo de 6 deles é *"a página publica isto, mas não foi transcrito nesta passada"* — espera de leitura escrita numa palavra que a regex não procurava. Um classificador por regex sobre texto livre herda o vocabulário de quem escreveu o texto, e erra em silêncio. A correção foi ampliar o padrão e **auditar o classificador contra a distribuição real das frases**, não contra a regex. Foi por isso que a mesma sessão produziu dois números: o primeiro foi o que a ferramenta disse, o segundo é o que a ferramenta viu depois de ser conferida. |

**O que ficou feito e não volta à fila:** G1 (NSG da Azure), D7, D8, E2/G11 (as 11 fixtures de API
do GCP sob contrato), E4 (os labels condicionais do Monitoring), E5 (a superfície OCSF do export
do Security Hub), a leva que fechou `severity_id` e `Severity.Normalized`, a leva do mecanismo de
export do ASFF, a triagem do registro de não comprovados, e agora a regra do `attic/` codificada
em `conftest.py` — `--matrix` `gerado=34 falta=0 bloqueado=1`, `--ready` 34 PRONTO, 860 testes.

O que **não** posso fazer sozinho: D1–D6 (escrita no repositório do FinOps, que a regra
nº 1 proíbe), E1 (idem) e a liberação de espaço em `D:`.
