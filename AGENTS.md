# AGENTS.md — simulador-nuvem (fidelidade de contratos de API)

Repositório local do simulador de nuvem. O trabalho aqui é **fidelidade de contrato**: cada
superfície em `specs/<provedor>/*.schema.json` declara colunas que precisam existir na documentação
**oficial** do provedor, com URL e data. Nada é preenchido por analogia, por plausibilidade ou por
exemplo inventado — o que a fonte não publica fica em `unverified`, **fora** do artefato.

## Rodar

A config de pytest, ruff e mypy **já existe** em `tools/synthetic_clouds/pyproject.toml`. Não
crie config na raiz — o próprio arquivo registra que isso violaria o NFR-5 deste projeto.

```powershell
$env:PYTHONPATH='<raiz-do-repo>'      # só para scripts .artifacts\*.py
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready        # 40 superfícies PRONTO
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix       # gerado / falta / bloqueado
.\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit aws    # colunas inventadas
```

`python -m tools...` acha o pacote pelo próprio CWD e **não** precisa de `PYTHONPATH`; os scripts
`.artifacts\*.py` são executados por caminho e precisam dele.

**A suíte completa é `pytest tools\synthetic_clouds\tests`, nunca `pytest` puro.** Um `pytest` sem
caminho recolhe `attic/product-coupled/test_coverage_matrix.py`, que importa
`tools.synthetic_clouds.coverage` — um módulo que **não existe mais** (virou `fidelity`) — e aborta
com erro de coleção antes de rodar qualquer teste. Corrigir isso exigiria escrever fora de
`tools/synthetic_clouds/`, então o caminho certo é o de cima. A suíte leva ~10 min: última rodada
medida em 2026-10-15, na revisão `9a51425` H-16, com **859 passed, 20 skipped** (879 casos coletados)
em 9m43s. `collected` e `passed` não são o mesmo número — os 20 skip são os testes que não rodam
por marcação. Se for citar "quantos testes tem", diga qual dos dois está usando; rode em background.

**ruff precisa de `--config`, e o porquê ainda não está fechado (2026-10-15, ruff 0.17.0).**
`ruff check tools\synthetic_clouds` **sem** `--config` responde `All checks passed!`;
com `--config tools\synthetic_clouds\pyproject.toml`, o mesmo comando responde `Found 31
errors` (29 `I001`, 1 `S104`, 1 `ANN001`). Não é cache (`--no-cache` reproduz) nem diretório
de trabalho (reproduz de dentro do pacote). As duas execuções listam os mesmos 118 `.py`,
resolvem o **mesmo** `Settings path` e diferem em 7 linhas de settings — `cache_dir`,
`project_root`, `src` e o `absolute_matcher` de `per-file-ignores`. Sem `--config`, forçar
`--select I` pela CLI também não acusa nada e `unsorted-imports` não aparece em
`--show-settings`: as regras do arquivo não estão sendo aplicadas, **mas não sabemos por
quê**.

**Não rode `ruff --fix` para "resolver" os 31.** 29 são `I001`, e a classificação
first-party/third-party depende do `src` — que é justamente o que muda entre as duas
execuções. Auto-corrigir agora pode reordenar 29 arquivos para uma classificação errada.
Use `ruff check … --config …` como relatório, e feche a causa antes de tratar como dívida.

**mypy é `-p`, não caminho.** `mypy -p tools.synthetic_clouds` funciona e usa a config do pacote
(`explicit_package_bases`, `mypy_path = "../.."`). `mypy tools\synthetic_clouds` — a mesma coisa
escrevendo um **caminho** em vez do **nome do pacote** — falha com *"Source file found twice under
different module names"* e **não checa nada**. Não é `PYTHONPATH`: o erro é idêntico com e sem ele.
Os 21 `import-untyped` (stubs de pyarrow) são ruído de ambiente, não erro de tipo.

## Documentos gerados — nunca editar à mão

`docs/NAO-COMPROVADOS.md` é **derivado das specs**. Cada linha vem de um `unverified` com o motivo
que a spec já registrava. Mudou um motivo numa spec? Regere:

```powershell
.\.venv\Scripts\python.exe .artifacts\gerar-registro-nao-comprovados.py   # -> "295 itens em 35 superficies"
```

**Esse script não está no repositório.** `.artifacts/` está no `.gitignore` (linha 22) e
`git ls-files .artifacts` devolve 0 arquivos: ele existe só na árvore de trabalho local. Um clone
novo não regenera o documento. Se a fase de ingestão precisar disso em outra máquina, versionar o
script (ou movê-lo para `specs/_tools/`, que já é versionado) é decisão pendente — não assuma que o
comando funciona em qualquer checkout.

`docs/CONTRATO-APIS-GCP.md` e `docs/DECISOES-PENDENTES.md` estão **versionados e limpos** — em
2026-10-15 `git ls-files` rastreia os 9 arquivos de `docs/` e `git status --porcelain` não acusa
nada. A nota anterior de que seriam "untracked" ficou obsoleta: eles já foram commitados. Para
conferir o próprio trabalho em qualquer doc, use `git status --porcelain -- <arquivo>` e releia o
arquivo — `git diff` sozinho não mostra arquivo nunca commitado, que é o caso que aquela nota
descrevia.

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
Os renderers chamam `_require_projection(...)` contra o conjunto `*_PROJECTED`: um valor não nulo
numa coluna fora desse conjunto é erro de render, com a mensagem *"preencheu colunas sem fonte no
modelo canonico (lacuna, nao valor)"*. É proposital: quando um campo deixa de ser `None`, você tem
de dizer de onde vem o valor. Ao entrar no conjunto, escreva **por que** entra — *"renomear o
campo do consumidor não é inventar o campo"* é uma justificativa válida; abrir o portão em
silêncio não é.

## Como o consumidor final consome este artefato (D3)

O `AwsSecurityFinding` não tem membro para `evidence`, `exposure`, `impact` e `fingerprint`, que o
FinOps exige como `NOT NULL`. A solução está em `UserDefinedFields`, o mapa livre que a AWS
publica para isso — e o renderer ASFF preenche com fatias do modelo. A regra da impressão está em
`render/security_hub.py::_fingerprint` e em `docs/INGESTAO-D3-SEGURANCA.md` §5. **Se você mudar a
regra da impressão, o deduplicador do consumidor para de deduplicar** — ela não inclui o status
justamente por isso.

Terceiros (blog, fórum, relato) **não** entram na spec. Podem ser citados no
`CONTRATO-APIS-GCP.md` como sinal não normativo, com data, quando decidem o mesmo ponto.

## Armadilhas de ambiente (medidas em 2026-10-15)

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