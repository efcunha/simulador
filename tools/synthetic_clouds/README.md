# synthetic_clouds — simulador multi-nuvem independente

Gera um estado sintético **determinístico e correlacionado** de AWS, GCP e Azure e o
projeta em **artefatos de export fiéis ao formato oficial de cada nuvem**, para
FinOps, segurança, rede e instâncias.

Este pacote é autônomo. **Nada é criado ou alterado** em `D:\synthetic-clouds`, em
`<arvore-de-origem>` ou em qualquer banco/container do FinOps. Como o
FinOps consumiria estes artefatos está em
`docs/<doc-de-ingestao>.md` — desenho, não
implementação.

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
* fail-closed*: uma spec inválida não vira código.

## Quick start

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'

# gerar (o `--out` precisa resolver DENTRO de tools/synthetic_clouds/)
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds --seed 123 --profile small --currency USD
```

| flag | valores | padrão |
|---|---|---|
| `--seed` | inteiro | obrigatório |
| `--profile` | `small` / `medium` / `large` | obrigatório |
| `--currency` | `USD` / `BRL` | `USD` |
| `--sim-start` | `YYYY-MM-DD` | `2026-01-01` |
| `--window-days` | inteiro | padrão do perfil |
| `--emit` | lista de nomes de renderer | — |
| `--out` | diretório de saída (sob o pacote) | `tools/synthetic_clouds/out` |
| `--scenarios-out` | caminho do gabarito de cenários | — |

Fluxo: **construir → aplicar cenários → gate (fail-closed) → armazenar → renderizar**.
A validação roda antes de qualquer escrita; uma violação levanta
`IntegrityError`/`QualityError` e nada é publicado.

## Geração diária agendada

O gerador diário (`daily/`) produz **um dia por vez** e exige a data: ele nunca lê o
relógio. Quem decide *qual* dia é devido, gera e registra é o agendador
(`schedule/`), e é ele que a tarefa do Windows executa.

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'
$py = '.\.venv\Scripts\python.exe'

& $py -m tools.synthetic_clouds.schedule init                        # cria a configuracao
& $py -m tools.synthetic_clouds.schedule set --time-zone America/Sao_Paulo --time 06:30
& $py -m tools.synthetic_clouds.schedule install --dry-run           # mostra o que faria
& $py -m tools.synthetic_clouds.schedule install                     # registra no Windows
& $py -m tools.synthetic_clouds.schedule status                      # config + ledger + tarefa
& $py -m tools.synthetic_clouds.schedule tick                        # gera o dia devido agora
```

Duas propriedades fazem disso um job seguro de deixar rodando sem supervisão: **é
idempotente** (um dia já registrado no ledger não é regerado, então disparar duas vezes é
inofensivo) e **recupera dias perdidos** (máquina desligada no horário → o `tick`
seguinte gera os dias que faltam, com teto configurável). O detalhe está em
[`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md).

## Verificação

```powershell
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'

# contrato das specs: exit 1 se alguma estiver sem evidência
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

# suíte, lint e tipos
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests -q
cd tools\synthetic_clouds; & ..\..\.venv\Scripts\ruff.exe check .
cd <raiz-do-repo>
& .\.venv\Scripts\mypy.exe --config-file tools\synthetic_clouds\pyproject.toml tools\synthetic_clouds
```

O `ruff` deve rodar **de dentro do pacote**: `per-file-ignores` e `isort` dependem
de a raiz do projeto ser o pacote. Rodando da raiz do repositório ele acusa falsos
positivos.

Leitura das duas colunas de preenchimento do `--audit`: **`caminhos`** conta os
caminhos que a spec enumera (`invoice.month`, `networkInterfaces[].id`) com valor no
artefato, e **`topo`** conta só os nomes de nível de topo. O artefato de billing do
GCP aninha os campos enquanto a spec enumera caminhos pontuados, então `topo`
subconta; o SCC achata a chave, e ali `topo` é a leitura certa. Olhar só uma das
formas erra para baixo na outra.

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

Todo dado gerado é marcado (`markers.py`), para que um consumidor possa distinguir
o sintético do real sem inferência.

## Documentos

| documento | o que responde |
|---|---|
| [`docs/ESTADO.md`](../../docs/ESTADO.md) | estado vivo: cobertura, decisões, o que falta e por quê |
| [`docs/AGENDAMENTO.md`](../../docs/AGENDAMENTO.md) | como configurar o horário, o que acontece quando a máquina fica desligada, e os limites |
| [`docs/MODELO-REDE.md`](../../docs/MODELO-REDE.md) | o modelo de rede derivado das quatro specs |
| `docs/<doc-de-ingestao>.md` | como o FinOps ingeriria isto, e o que hoje não fecha |
| `docs/<doc-de-cobertura>.md` | o que o FinOps consome da nuvem × o que os três planos de simulação entregam, com as lacunas ranqueadas |
| `docs/<doc-de-lacunas>.md` | especificação implementável das lacunas que vivem no repositório do FinOps (que este repo não escreve) |
| [`docs/DECISOES-PENDENTES.md`](../../docs/DECISOES-PENDENTES.md) | registro das decisões de produto que travam a cobertura, com opções, custo e consequência de não decidir |
| [`specs/README.md`](../../specs/README.md) | o contrato das especificações |

## Ambiente

CPython 3.12 no venv `.venv` na raiz do repositório. O núcleo de fidelidade não
depende de `pyarrow` (o import é local), para poder conferir artefatos sem o
conjunto completo de dependências de renderização.
