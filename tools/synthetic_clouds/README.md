# synthetic_clouds — simulador multi-nuvem independente

Gera um estado sintético **determinístico e correlacionado** de AWS, GCP e Azure e o
projeta em **artefatos de export fiéis ao formato oficial de cada nuvem**, para
FinOps, segurança, rede e instâncias.

> Última atualização: **2026-10-29** (revisão `9533b901`).

Este pacote é autônomo. **Nada é criado ou alterado** em `C:\Projetos\Simulador`, em
`<arvore-de-origem>` ou em qualquer banco/container do FinOps. Fora de
`tools/synthetic_clouds/` ele escreve apenas dois alvos: o gabarito fixo
`docs/synthetic-clouds/scenarios.json` (NFR-5, nunca outro caminho) e a **entrega aos
emuladores** (`tools.synthetic_clouds.deliver` / `tick --deliver`), que escreve nos
simuladores (`s3mock`/`aws-sim`, BigQuery, `azure-sim`) e só quando invocada. O desenho de
ingestão do lado do FinOps, no que foi verificado, está em
[`docs/INGESTAO-D3-SEGURANCA.md`](../../docs/INGESTAO-D3-SEGURANCA.md) (domínio D3) e o
estado geral em [`docs/ESTADO.md`](../../docs/ESTADO.md).

## O princípio: se a documentação não afirma, o simulador não afirma

Cada coluna de cada superfície carrega **URL da documentação oficial e data de
consulta** (`specs/<provedor>/<superfície>.schema.json`). Duas perguntas são
separadas de propósito, e confundi-las é o erro que o projeto existe para evitar:

| eixo | pergunta | exigência |
|---|---|---|
| `belongs_to_schema` | a coluna existe no formato? | nome + tipo + `status: verified` + `source_url` |
| `is_generatable` | o simulador pode emitir valor nela? | `evidence: declared` **e** `type_source` válido |

`evidence` admite `declared`, `null-empty`, `example-only`, `name-only`,
`deprecated` e `author-classification`. Onde a documentação não declara o tipo mas
o formato o revela, o valor é `type_source: format-observed` — uma **qualificação
auditável**, nunca dedução silenciosa.

Um campo marcado como não comprovado é **resultado esperado**, não pendência a
preencher com palpite: o artefato entrega a coluna vazia. O validador é
*fail-closed*: uma spec inválida não vira código.

## Quick start

```powershell
cd <raiz-do-repo>
# o pacote se importa pelo diretório de trabalho; PYTHONPATH não é necessário
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds --seed 123 --profile small --currency USD
```

| flag | valores | padrão |
|---|---|---|
| `--seed` | inteiro | **obrigatório** |
| `--profile` | `small` / `medium` / `large` | **obrigatório** |
| `--currency` | `USD` / `BRL` | `USD` |
| `--sim-start` | `YYYY-MM-DD` | época canônica `2026-01-01` |
| `--window-days` | inteiro | janela do perfil |
| `--emit` | lista de nomes de renderer, separada por vírgula | **todos os renderers registrados** |
| `--out` | diretório de saída | `tools/synthetic_clouds/out`; o caminho resolvido precisa ficar **dentro** do pacote (NFR-5) |
| `--scenarios-out` | caminho do gabarito de cenários | **fixo** em `docs/synthetic-clouds/scenarios.json`; qualquer outro caminho é recusado (NFR-5) |

Fluxo: **construir → aplicar cenários → gate (fail-closed) → armazenar → renderizar**.
A validação roda antes de qualquer escrita; uma violação levanta
`IntegrityError`/`QualityError` e nada é publicado.

## Geração diária agendada

O gerador diário (`daily/`) produz **um dia por vez** e exige a data: ele nunca lê o
relógio. Quem decide *qual* dia é devido, gera e registra é o agendador
(`schedule/`), e é ele que a tarefa do Windows executa.

Dois níveis de configuração, medidos em 2026-10-29:

| Campo | Padrão de fábrica (`config.py`, o que `init` escreve num checkout limpo) | Config desta instalação (`schedule/config.json`, versionado) |
|---|---|---|
| `time` | `06:30` | `12:00` |
| `time_zone` | fuso da máquina; `UTC` **com aviso** quando não resolve | `America/Sao_Paulo` |
| `profile` | `small` | `medium` |
| `seed` / `currency` | `123` / `USD` | `123` / `USD` |
| `lag_days` | `1` (FR-B2: export de D só em D+1 00:00 UTC) | `0` desde 2026-10-26 (`1f674563`) — o dashboard precisa fechar em "hoje"; voltar ao FR-B2 com `set --lag-days 1` |
| `retention_days` | `null` (guarda tudo) | `30` |

```powershell
cd <raiz-do-repo>
$py = '.\.venv\Scripts\python.exe'

& $py -m tools.synthetic_clouds.schedule show                  # config efetiva (já validada)
# num checkout SEM config.json, primeiro:  & $py -m tools.synthetic_clouds.schedule init
# (o `init` recusa sobrescrever: neste repositório o config.json já existe e é versionado)
& $py -m tools.synthetic_clouds.schedule set --profile medium --time-zone America/Sao_Paulo --time 12:00 --lag-days 0 --retention-days 30
& $py -m tools.synthetic_clouds.schedule install --dry-run     # mostra o que faria
& $py -m tools.synthetic_clouds.schedule install               # registra no Windows (sem admin)
& $py -m tools.synthetic_clouds.schedule status                # config + ledger + tarefa
& $py -m tools.synthetic_clouds.schedule tick                  # gera o dia devido agora
```

Duas propriedades fazem disso um job seguro de deixar rodando sem supervisão: **é
idempotente** (um dia já registrado no ledger não é regerado, então disparar duas vezes é
inofensivo) e **recupera dias perdidos** (máquina desligada no horário → o `tick`
seguinte gera os dias que faltam, com teto configurável). O detalhe está em
[`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md).

## Entrega aos emuladores

O `tick` da tarefa roda com `--deliver`: depois de gerar, entrega o dia aos emuladores que o
CloudPilot lê pelos conectores de produção. Rodar manualmente:

```powershell
# entregar um dia já gerado (sem gerar de novo)
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23
& $py -m tools.synthetic_clouds.deliver --day 2026-10-23 --targets aws,gcp
```

Alvos e endpoints padrão: `aws` → `http://localhost:9090` (S3), `gcp` →
`http://localhost:9050` (BigQuery `insertAll`) e `azure` → `http://localhost:8080`
(`POST /admin/estate/refresh`). Endpoints, bucket, prefixo e nome do export podem ser
trocados pelas variáveis `DELIVERY_AWS_*`, `DELIVERY_GCP_*`, `DELIVERY_AZURE_ENDPOINT` e
`DELIVERY_TARGETS`. A entrega é idempotente por dia; falha de entrega não desfaz o dia no
ledger, mas o `tick` sai com código 1. Tabela completa em
[`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md#entrega-aos-emuladores---deliver).

## Verificação

```powershell
cd <raiz-do-repo>

# contrato das specs: exit 1 se alguma spec estiver inválida ou sem evidência
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity

# o que falta gerar / provar
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --golden

# renderiza cada superfície e MEDE: registros, caminhos com valor, colunas
# inventadas e colunas obrigatórias vazias em todas as linhas
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit azure

# aceitação: contrato das specs + coerência da matriz + golden + entrega
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready
```

Leitura de 2026-10-29 (revisão `9533b901`): `--matrix` →
`gerado=47 falta=0 bloqueado=2 total=49`; `--ready` → `PRONTO: 47 superficies`; `--audit`
sai com 1 quando há superfície com erro de render ou coluna inventada (não é o caso nesta
data).

### Suíte, lint e tipos

```powershell
# a suíte canônica é a do pacote, nunca `pytest` puro (ver nota abaixo)
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests -q

# ruff: a config do pacote PRECISA ser passada com --config
& .\.venv\Scripts\ruff.exe check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml --no-cache

# mypy: -p (nome do pacote), NUNCA o caminho
& .\.venv\Scripts\mypy.exe -p tools.synthetic_clouds --config-file tools\synthetic_clouds\pyproject.toml
```

Notas medidas em 2026-10-29:

* **`pytest` sem caminho não serve.** Ele coleta também os testes dos emuladores
  (`emulators/*/**/tests`), que exigem `boto3`/`botocore` e o próprio pacote no `sys.path`
  — coisas que o `.venv` do gerador não tem — e aborta na coleção: **1661 casos com 23
  erros de coleção**. O caminho `pytest tools\synthetic_clouds\tests` é o canônico; a suíte
  medida nesta data (revisão `9533b901`) foi **1106 passed / 20 skipped** (1126 coletados).
  `collected` e `passed` não são o mesmo número — os 20 skip são decisão, não falha.
* **ruff sem `--config` mede outra coisa.** Na forma oficial (acima) o relatório é **4
  erros**: 2 de segurança em `deliver/core.py` (`S310`, `S608`) e 2 `N802` em
  `tests/test_gcp_topology_render.py`. Sem `--config`, o mesmo comando acusa **42** — os
  mesmos 4 + 38 `I001`, falso positivo da classificação first-party de `tools.*` (o `src`
  depende de como a config é descoberta). **Não rode `ruff --fix`:** os 4 achados corretos
  não são auto-corrigíveis e os 38 são falsos. `--no-cache` só evita escrever o cache
  quando a árvore não é gravável; o relatório é o mesmo.
* **mypy é `-p`, não caminho.** `mypy -p tools.synthetic_clouds --config-file …` usa a
  config do pacote e, nesta data, acusa **10 erros** (6 `no-any-return`, 3
  `no-untyped-call`, 1 `call-arg`) em 5758 arquivos checados. `mypy tools\synthetic_clouds`
  (caminho em vez do nome do pacote) falha com *"Source file found twice under different
  module names"* e **não checa nada**.

A leitura das duas colunas de preenchimento do `--audit`: **`caminhos`** conta os caminhos
que a spec enumera (`invoice.month`, `networkInterfaces[].id`) com valor no artefato, e
**`topo`** conta só os nomes de nível de topo. O artefato de billing do GCP aninha os campos
enquanto a spec enumera caminhos pontuados, então `topo` subconta; o SCC achata a chave, e
ali `topo` é a leitura certa. Olhar só uma das formas erra para baixo na outra.

## Modelo e determinismo

O modelo canônico é um conjunto de dataclasses congeladas (`model/`): hierarquia,
recursos, consumo, faturamento, compromissos, créditos, impostos, rede
(`NetworkSegment`/`NetworkInterface`/`NetworkFlow`), instâncias (`InstanceProfile`)
e achados (`NativeFinding`/`NativeRecommendation`).

Tudo é determinístico a partir de `--seed`:

* identidade por **UUIDv5** sobre caminho lógico (`identity_for`), nunca `hash()`;
* aleatoriedade por **streams nomeados** (`stream_rng(seed, nome)`), para que
  acrescentar um registro não desloque os outros nem dependa da ordem de iteração;
* os ids que o provedor cunha (o `i-` da AWS, o GUID da assinatura Azure, o SKU do
  GCP) são derivados **na forma documentada**, em `model/identity.py` — um lugar só.
  São ids derivados **na forma**, não identificadores oficiais; a entropia real do
  provedor não é reproduzível offline, e isso está no docstring de cada um.

## Marcadores sintéticos

Todo dado gerado é marcado (`render/markers.py`), para que um consumidor possa distinguir
o sintético do real sem inferência.

## Documentos

| documento | o que responde |
|---|---|
| [`docs/ESTADO.md`](../../docs/ESTADO.md) | estado vivo: cobertura, decisões, o que falta e por quê |
| [`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md) | como configurar o horário, o que acontece quando a máquina fica desligada, e os limites |
| [`docs/MODELO-REDE.md`](../../docs/MODELO-REDE.md) | o modelo de rede derivado das quatro specs |
| [`docs/POSTURA-SEGURANCA.md`](../../docs/POSTURA-SEGURANCA.md) | o domínio de postura: os checks do consumidor e a superfície que produz cada um |
| [`docs/INGESTAO-D3-SEGURANCA.md`](../../docs/INGESTAO-D3-SEGURANCA.md) | como o consumidor do domínio D3 ingere os achados (ASFF/OCSF, deduplicação) |
| [`docs/CONTRATO-APIS-GCP.md`](../../docs/CONTRATO-APIS-GCP.md) | o contrato das APIs GCP lidas (fonte não normativa, com data) |
| [`docs/DECISOES-PENDENTES.md`](../../docs/DECISOES-PENDENTES.md) | registro das decisões de produto que travam a cobertura, com opções, custo e consequência de não decidir |
| [`docs/k8s-sim-opencost-contract.md`](../../docs/k8s-sim-opencost-contract.md) | o contrato HTTP do `k8s-sim` (OpenCost) e as fontes de cada campo |
| [`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](../../docs/INTEGRACAO-CLOUDPILOT-TLS.md) | como o CloudPilot fala com os emuladores pelos hostnames reais, com TLS local |
| [`docs/NAO-COMPROVADOS.md`](../../docs/NAO-COMPROVADOS.md) | derivado das specs (não editar à mão): os itens `unverified` e o motivo de cada um |
| [`docs/regression/`](../../docs/regression/) | mapas de impacto das fases recentes (S3, S4b1-D) |
| [`specs/README.md`](../../specs/README.md) | o contrato das especificações |

## Ambiente

CPython 3.12 no venv `.venv` na raiz do repositório (leitura de 2026-10-29: **3.12.10**;
ruff **0.17.1**, mypy **2.4.0**). O núcleo de fidelidade não depende de `pyarrow` (o import
é local), para poder conferir artefatos sem o conjunto completo de dependências de
renderização.
