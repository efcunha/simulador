# AGENTS.md — simulador-nuvem (fidelidade de contratos de API)

Repositório local do simulador de nuvem. O trabalho aqui é **fidelidade de contrato**: cada
superfície em `specs/<provedor>/*.schema.json` declara colunas que precisam existir na documentação
**oficial** do provedor, com URL e data. Nada é preenchido por analogia, por plausibilidade ou por
exemplo inventado — o que a fonte não publica fica em `unverified`, **fora** do artefato.

## Rodar

A config de pytest, ruff e mypy **já existe** em `tools/synthetic_clouds/pyproject.toml`. Não
crie config na raiz — o próprio arquivo registra que isso violaria o NFR-5 deste projeto.

```powershell
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready        # 47 superficies PRONTO
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix       # gerado / falta / bloqueado
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit aws    # colunas inventadas
```

`python -m tools...` acha o pacote pelo próprio CWD e **não** precisa de `PYTHONPATH`. Os scripts
de auditoria em `specs\_tools\` são executados por caminho e inserem a raiz no `sys.path` sozinhos
(`audit_sources.py`, `gerar-registro-nao-comprovados.py`), então `PYTHONPATH` também não é
necessário para eles.

**A suíte completa é `pytest tools\synthetic_clouds\tests`, nunca `pytest` puro.** Medido em
2026-10-29: um `pytest` sem caminho coleta também os testes dos **emuladores**
(`emulators/*/**/tests`), que exigem `boto3`/`botocore` e o próprio pacote no `sys.path` — coisas
que o `.venv` do gerador não tem —, além de diretórios alheios (`uvcache/`, `pytest-of-*`): a
rodada coletou **1661 casos com 23 erros de coleção** e abortou antes de rodar qualquer teste. A
nota anterior sobre `attic/` ficou obsoleta: `attic/` não existe na árvore nem no histórico git
deste repositório (`git ls-tree HEAD attic` vazio), e o `collect_ignore_glob` do `conftest.py` da
raiz é vestigial. A suíte leva ~12–14 min: duas rodadas medidas em 2026-10-29, na revisão
`9533b901`, ambas com **1106 passed, 20 skipped** (1126 casos coletados) — 12m13s (733 s) e 14m00s
(840 s). `collected` e `passed` não são o mesmo número — os 20 skip são testes que não rodam por
**decisão** (a fixture `real_parser` e as fixtures GCP sem label condicional). Se for citar
"quantos testes tem", diga qual dos dois está usando; rode em background.

**ruff: a forma oficial é com `--config` (medido em 2026-10-29, ruff 0.17.1).**
`ruff check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml` responde
**Found 4 errors**: `deliver/core.py:76` (`S310`), `deliver/core.py:176` (`S608`) e
`tests/test_gcp_topology_render.py:99`/`:281` (`N802`, nomes de teste com "FinOps"). Sem
`--config`, o mesmo comando responde **Found 42 errors**: os mesmos 4 **+ 38 `I001`**. A diferença
é a classificação first-party de `tools.*`, que depende do `src` — `src = ["."]` resolve contra o
`project_root`, e o `project_root` muda conforme a config é descoberta (hierarquicamente) ou
passada (`--config`). Só a forma com `--config` classifica `tools.synthetic_clouds` como
first-party; por isso os 38 `I001` da outra execução são falso positivo, não dívida. A medição
anterior (2026-10-15, ruff 0.17.0) era o inverso — `All checks passed!` sem `--config` e 31 erros
com; os números mudaram com a versão/descoberta, e a causa exata dessa inversão **não foi
fechada**. O que importa hoje: os **4 erros reais** são dívida nomeada (2 de segurança em
`deliver/core.py`, 2 de nome de teste), e `ruff check … --config …` é o relatório oficial.

**Não rode `ruff --fix`.** Na forma sem `--config` ele reordenaria 38 imports por uma
classificação errada; e os 4 achados da forma correta não são auto-corrigíveis.

**mypy é `-p`, não caminho.** `mypy -p tools.synthetic_clouds --config-file
tools\synthetic_clouds\pyproject.toml` funciona e usa a config do pacote
(`explicit_package_bases`, `mypy_path = "../.."`). Medido em 2026-10-29 (mypy 2.4.0): **10 erros**
— 6 `no-any-return`, 3 `no-untyped-call`, 1 `call-arg` — em 5758 arquivos checados; os 21
`import-untyped` de stubs de pyarrow não aparecem mais. `mypy tools\synthetic_clouds` — a mesma
coisa escrevendo um **caminho** em vez do **nome do pacote** — falha com *"Source file found twice
under different module names"* e **não checa nada**. Não é `PYTHONPATH`: o erro é idêntico com e
sem ele.

## Documentos gerados — nunca editar à mão

`docs/NAO-COMPROVADOS.md` (e a gêmea `.en.md`) são **derivados das specs**. Cada linha vem de um
`unverified` com o motivo que a spec já registrava. Mudou um motivo numa spec? Regere:

```powershell
.\.venv\Scripts\python.exe specs\_tools\gerar-registro-nao-comprovados.py   # -> "293 itens em 49 superficies"
```

O gerador **está versionado** em `specs/_tools/`; a nota anterior de que ele existia só na árvore
local (`.artifacts/`, fora do git) ficou obsoleta. Ele é **não destrutivo por construção**: o
preâmbulo de cada documento é preservado byte a byte (a única exceção é a citação do próprio
gerador), os três números do bloco "Números" são recalculados das specs, o corpo das seções é
reconciliado com a spec e rodar duas vezes não muda nada (idempotente). Ele mantém PT e EN a partir
das mesmas specs.

Os documentos de `docs/` são **versionados e limpos** (`git ls-files docs` rastreia 24 arquivos em
2026-10-29). Para conferir o próprio trabalho em qualquer doc, use `git status --porcelain --
<arquivo>` e releia o arquivo — `git diff` sozinho não mostra arquivo nunca commitado.

## Quando a evidência não existe

Caminho honesto e o esperado, não uma falha:

1. Procurar de novo, e **registrar as URLs consultadas com data e o que cada uma devolveu**.
2. Se a fonte nomeia o campo e não o valor (ou nomeia outra coisa), isso é **evidência a favor da
   recusa** — escreva no motivo, não só a ausência.
3. Deixar o item em `unverified` com motivo citável, espelhado no `model_gaps` do relatório de
   proveniência.
4. Não fechar a lacuna por dedução. Um residual declarado não é dívida; um valor inventado é dívida
   que mente em silêncio.

**Um residual pode ser uma lacuna esperando só uma leitura.** O `severity_id` do export OCSF estava
declarado como *"a tabela não foi lida nesta execução"* — e era verdade. `base_event.json` não existe
em nenhuma tag do OCSF: os atributos base vivem no `dictionary.json` da raiz (258 KB na 1.6.0), que
é grande demais para `web_fetch` ler no meio. Baixe com `gh api` e leia localmente com grep. Ao ler um
enum, confira se ele é **igual em outra tag**: um valor estável entre versões fecha a lacuna sem
depender da versão, que em geral é a lacuna vizinha.

## Duas regras que os testes já impõem (aprendidas em 2026-10-15)

**Coluna cita DOCUMENTAÇÃO; contrato de máquina é evidência de leitura, não citação.**
`is_official_url()` aceita o host de documentação (`cloud.google.com`, `docs.cloud.google.com`,
`docs.aws.amazon.com`) e **rejeita** o endpoint de discovery (`…googleapis.com/$discovery/…`).
Ao ler uma enum ou um schema num discovery, grave a **página de documentação** no `source_url` da
coluna e ponha o endpoint em `reference_urls`, com uma nota dizendo onde cada coisa foi lida.
Um teste (`test_todo_campo_cita_documentacao_oficial`) reprova o resto — e ele tem razão: a
citação precisa ser legível por uma pessoa, não por uma máquina.

**Preencher uma coluna exige declarar a fonte, e o guard exige declarar ANTES.**
Os renderers chamam `_require_projection(...)` contra o conjunto `*_PROJECTED` (o nome concreto
varia por renderer: `_ITEM_PROJECTED`, `_GROUP_PROJECTED`, `_FIREWALL_PROJECTED`, ...): um valor
não nulo numa coluna fora desse conjunto é erro de render, com a mensagem *"preencheu colunas sem
fonte no modelo canonico (lacuna, nao valor)"*. É proposital: quando um campo deixa de ser `None`,
você tem de dizer de onde vem o valor. Ao entrar no conjunto, escreva **por que** entra —
*"renomear o campo do consumidor não é inventar o campo"* é uma justificativa válida; abrir o portão
em silêncio não é.

## Como o consumidor final consome este artefato (D3)

O `AwsSecurityFinding` não tem membro para `evidence`, `exposure`, `impact` e `fingerprint`, que o
FinOps exige como `NOT NULL`. A solução está em `UserDefinedFields`, o mapa livre que a AWS
publica para isso — e o renderer ASFF preenche com fatias do modelo. A regra da impressão está em
`render/security_hub.py::_fingerprint` e em `docs/INGESTAO-D3-SEGURANCA.md` (seção *"O que já está
entregue e onde isso vale"*). **Se você mudar a regra da impressão, o deduplicador do consumidor
para de deduplicar** — ela não inclui o status justamente por isso.

Terceiros (blog, fórum, relato) **não** entram na spec. Podem ser citados no
`CONTRATO-APIS-GCP.md` como sinal não normativo, com data, quando decidem o mesmo ponto.

## O que mais existe hoje (e não passa pelo gate de export)

As **49 superfícies** de `specs/` são o gate do gerador: spec + renderer + teste golden. O que os
emuladores servem é maior do que esse gate, e há duas categorias para não confundir:

- **Rotas ao vivo de superfícies que também têm export.** O `gcp-sim` serve SCC findings (gRPC
  :8088), Compute firewalls (REST) e a lista de clusters do Kubernetes Engine
  (`container.googleapis.com`) ao vivo. O export correspondente existe em `specs/` e é gerado — ou,
  no caso de `gcp/container-clusters`, está **especificado e bloqueado**: a doc sustenta a forma,
  mas não há renderer que produza o artefato conferível.
- **Contratos que não têm superfície de export.** A descoberta de cluster EKS/AKS (resposta de API)
  e o contrato OpenCost do `k8s-sim`. Eles não entram na matriz de fidelidade porque não há artefato
  a conferir contra uma spec; o contrato está nos documentos específicos e nos testes do emulador
  (`docs/k8s-sim-opencost-contract.md`, `docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/regression/`).

**Lacuna aberta em 2026-10-29 (S4b1-E).** O consumidor passou a keyar a descoberta pelo **id
nativo** do cluster (EKS ARN / AKS ARM id / GKE selfLink) e a enviar `filter=cluster:"<id nativo>"`
ao OpenCost, mas o `k8s-sim` só resolve o **nome** e o **uuid do estate** (o fixture
`clusters.json` não carrega o id nativo) — com a config nova o allocation responde `200` com
`data: []`. O addendum datado está em `docs/k8s-sim-opencost-contract.md` e em
`docs/regression/mapa-impacto-s4b1d.md`; a correção é carregar o id nativo no fixture e aceitá-lo
como alias, sem publicá-lo.

## Armadilhas de ambiente (medidas em 2026-10-15 e 2026-10-29)

**A documentação do GCP mudou de slug.** O padrão antigo
`cloud.google.com/<produto>/docs/reference/rest/v1/...` devolve **404 numa página HTML** — uma
página de erro, não um "não existe". O conteúdo real migrou para `docs.cloud.google.com`. Ao ver
404 com boilerplate, troque o host antes de concluir que a página não existe: foi exatamente o que
aconteceu com a página de recommenders e com a do Recommender REST, e me custou duas buscas inúteis.

**O `web_search` falhou com `MATRIX_TOOL_REQUEST_FAILED`** (duas vezes seguidas, com queries
diferentes e que já tinham funcionado antes no mesmo dia). Não reexperimente três vezes: o
contorno é buscar a fonte de máquina, que é melhor de qualquer jeito para evidência:
`Invoke-WebRequest "https://<api>/$discovery/rest?version=v1" -OutFile <arquivo>` e ler local.
Para o Recommender, o discovery de 216 KB foi a leitura que **fez o trabalho**: tem o template de
path, os padrões regex e o `Valid Values` do parâmetro, e é a mesma máquina que a AWS usa no
`API_Reference` (`API_*.md`, que devolve a lista completa onde o `.html` trunca).

**Fonte de máquina grande demais para `web_fetch`.** `web_fetch` trunca o meio do arquivo. Para
JSON de 100 KB ou mais, baixe e leia local: foi assim que o `dictionary.json` do OCSF (258 KB na
tag 1.6.0) entregou a enum de `severity_id` e fechou aquela lacuna. Para GitHub, use
`gh api repos/ocsf/ocsf-schema/contents/dictionary.json?ref=1.6.0 --jq .content`.

**Classificadores por regex sobre texto livre erram em silêncio.** A triagem da fila
(`inventario-nao-comprovados.py`) devolveu "1 item em espera de leitura no GCP" quando eram 6,
porque os motivos dizem *"a página publica isto, mas não foi transcrito nesta passada"* — espera
de leitura escrita numa palavra que a regex não procurava. A correção não foi afinar a regex: foi
escrever `auditar-classificador.py`, que **importa** o padrão do inventário e compara com uma rede
de captura mais ampla, para tornar o furo visível. Se um item casar na rede e não no padrão do
inventário, o inventário tem furo — corrija o inventário, nunca o auditor.

**Testes dos emuladores não rodam no `.venv` do gerador.** Cada emulador fixa o próprio ambiente no
`Containerfile`; os testes do `aws-sim`, por exemplo, importam `boto3`/`botocore`, que não estão
instalados no venv da raiz. Rodaram lá, eles falham na coleção — não é defeito do teste. O
`k8s-sim` é o caso extremo: sem `Containerfile`, com `fastapi`/`uvicorn` e um `pyproject.toml`
próprio (`pytest` roda a partir de `emulators/k8s-sim`).
