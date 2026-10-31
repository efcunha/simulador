# Especificações de export

Esta pasta é a **fonte da verdade** do simulador. Nada é gerado sem que o formato
correspondente esteja especificado aqui, com citação de documentação oficial do
provedor.

O validador normativo é `tools/synthetic_clouds/fidelity/spec.py`. Este documento
descreve o mesmo contrato em prosa; em caso de divergência, **o código manda**.

```powershell
cd <raiz-do-repo>

# o validador: carrega as 49 specs, aplica validate_spec e sai 1 se houver problema
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity

# as três visões de aceitação
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready    # 47 superfícies PRONTO
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix   # gerado / falta / bloqueado
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit aws  # colunas inventadas
```

`python -m tools...` acha o pacote pelo próprio CWD — **não** precisa de `PYTHONPATH` (a nota
antiga que o exigia valia para os scripts de auditoria executados por caminho, que hoje inserem a
raiz no `sys.path` sozinhos).

## Estado em 2026-10-29 (revisão `9533b901`)

**Medido nesta árvore:** **49 superfícies** especificadas — AWS **15** · GCP **23** · Azure
**11** (`specs/<provedor>/*.schema.json`) —, das quais **47 PRONTO** (`--ready` →
`PRONTO: 47 superficies`, exit 0) e **2 bloqueadas** na matriz: `azure/cost-management-export-cost-details`
(a Microsoft publica nomes sem tipos) e `gcp/container-clusters` (a documentação sustenta a forma,
mas a superfície é resposta de API servida ao vivo, sem artefato durável a conferir). `--matrix`:
`gerado=47  falta=0  bloqueado=2  total=49`.

O registro derivado das lacunas, [`docs/NAO-COMPROVADOS.md`](../docs/NAO-COMPROVADOS.md), totaliza
**293 itens em 49 de 49 superfícies** (aws 88, azure 83, gcp 122), gerado a partir destas specs por
[`specs/_tools/gerar-registro-nao-comprovados.py`](_tools/gerar-registro-nao-comprovados.py).

**Contagem de prosa:** esta pasta tem **31 arquivos `.md`** — **30** nas pastas de provedor
(**29** são a prosa de uma superfície, com o mesmo nome do `.schema.json`, e **1** é o índice
`azure/datasets.md`) **+ este README**. Os **49** `.schema.json` são o inventário de máquina; **20**
superfícies têm só o schema, sem `.md` irmão.

## Estrutura

```
specs/
  README.md
  _tools/                      # utilitários de auditoria das specs
  <provider>/<superficie>.md            # spec legível, com citações
  <provider>/<superficie>.schema.json   # inventário de campos legível por máquina
```

## O que cada spec `.md` precisa conter

1. **Identificação** — nome oficial da superfície, documento oficial (título, URL,
   data de consulta) e versão/schema de referência.
2. **Mecanismo e entrega** — bucket/container/tabela, caminho e particionamento
   exatos, formato do arquivo, compressão, encoding, delimitador, cabeçalho, e o
   manifesto/metadados se a nuvem os emite.
3. **Campos** — uma linha por campo, com nome **exato e sensível a maiúsculas** e
   a URL da seção que documenta aquele campo.
4. **Campos não comprovados** — lista explícita, com o motivo.
5. **Divergências conhecidas** — quando a documentação se contradiz, registre os
   dois lados e **não escolha por conta própria**.

## Contrato do `*.schema.json`

```json
{
  "surface": "aws/bcm-data-exports-focus12",
  "provider": "aws",
  "reference": {
    "title": "…",
    "url": "https://…",
    "consulted_at": "2026-10-14"
  },
  "delivery": { "kind": "s3", "path_template": "…", "format": "parquet" },
  "sets": [
    {
      "name": "asff-top-level",
      "description": "Objetos de topo do ASFF",
      "columns": [
        {
          "name": "BilledCost",
          "type": "decimal",
          "required": true,
          "unit": "USD",
          "source_url": "https://…",
          "status": "verified",
          "evidence": "declared",
          "type_source": "documented"
        }
      ]
    }
  ],
  "unverified": [
    { "name": "x_InvoiceIssuerId", "reason": "a coluna não aparece na tabela oficial desta superfície" },
    { "item": "granularidade da partição", "target": "_PARTITIONTIME", "reason": "a página não declara o grão" }
  ],
  "reference_urls": { "discovery": "https://…/$discovery/rest?version=v1" }
}
```

- **`surface` e `provider`** são obrigatórios e não vazios; o `surface` é a identidade da spec
  (chave do documento gerado e da matriz).
- **`reference`** é obrigatório e exige **`title`**, **`url`** e **`consulted_at`** —
  `validate_spec` reprova a spec se faltar qualquer um dos três.
- **`delivery`** é preservado como dicionário; o validador não impõe esquema a ele.
- **`columns`** ou **`sets`** — um dos dois, nunca nenhum; se `sets` existir, `columns` é ignorado.
  Use `"columns": []` quando o provedor não publica schema e a lacuna está em `unverified`.
- **`type`** e **`required`** são opcionais (`required` tem default `false`); sem `type` a coluna
  pode pertencer ao formato só se o tipo vier por outra via — na prática, a coluna não é emitível
  (ver abaixo). **`scope`** qualifica o contexto de uma coluna quando `sets` não é usado.
- **`unverified`** aceita duas formas:
  - **string** — só o nome, sem motivo;
  - **objeto** — `name`/`field`/`column` registra um **campo** que não pertence ao contrato;
    `item`/`topic`/`gap` registra um **tópico** (lacuna que não é nome de campo); `reason`/`note`/
    `detail` carrega o motivo, e `target` é um rótulo opcional do tópico. As duas naturezas
    importam: `field` entra em `forbidden_names` (emitir o nome é falha), `topic` **não** —
    senão uma lacuna de particionamento proibiria um nome de coluna por coincidência.
- **Chaves extras de proveniência** — `notes`, `structure`, `reference_urls`, `armadilhas`, etc. —
  são aceitas no JSON e **ignoradas pelo parser**. `reference_urls` é o mapa dos endereços de
  máquina lidos (discovery, proto, página de referência): a citação que vale para a coluna é a
  `source_url`, e o endpoint de máquina fica ali como evidência de leitura, não como citação.

### `columns` ou `sets`

- **`columns`** — esquema único e plano.
- **`sets`** — vários esquemas numa mesma superfície. Use quando o provedor
  publica estruturas distintas que repetem nomes: os cinco esquemas de contrato
  do dataset clássico de custo da Microsoft (EA/MCA/MPA/CSP/PAYG), as tabelas
  `Resources` e `securityresources` do Azure Resource Graph, ou o topo do ASFF
  versus `Resources[]`.

Dentro de um **mesmo** conjunto, nome repetido é erro. Entre conjuntos
diferentes, repetir é legítimo — é para isso que `sets` existe. Cada coluna herda
o nome do conjunto como `scope`; alternativamente, numa lista plana, qualifique a
coluna com `"scope": "<contexto>"`.

### Ordem das colunas

A ordem em que as colunas aparecem na spec é a ordem da **documentação**, e não
um contrato de entrega. Só existe contrato de ordem quando o provedor publica uma
ordem fixa para o artefato (por exemplo, um CSV cujo cabeçalho o provedor
determina). Quando a ordem é definida pelo próprio consumidor — como num Data
Export da AWS, cuja ordem vem do `SELECT` da definição do export — a verificação
compara **conjunto**, não sequência.

Quem confere escolhe o eixo: `check(spec, colunas)` compara conjunto;
`check(spec, colunas, ordered=True)` exige a ordem, e só se justifica onde a
ordem é contratual. `check(spec, colunas, scope=...)` é obrigatório quando a
superfície tem mais de um conjunto nomeado, porque conjuntos podem ser disjuntos
(no dataset clássico de custo da Microsoft, **nenhum** dos 132 nomes aparece nos
cinco contratos ao mesmo tempo — comparar contra a união acusaria ausência de
tudo o que os outros quatro declaram).

### `status` e `evidence`

- **`status`**: estritamente `"verified"` ou `"unverified"` (default `verified` quando ausente).
  Uma coluna `verified` **sem `source_url` é erro** de carregamento. É o eixo binário — a
  documentação afirma ou não afirma.
- **`evidence`**: a *qualidade* da afirmação. `"declared"` (ou o campo ausente) significa que a
  documentação enuncia a coluna como contrato. `"null-empty"` é o caso especial em que a
  documentação afirma que a coluna **existe no arquivo e nunca tem valor**: ela pertence ao
  formato (é emitida vazia) e não pode ser preenchida. Os demais qualificadores descrevem
  documentação real porém insuficiente para virar contrato — os que aparecem nas 49 specs são
  `"example-only"`, `"name-only"`, `"deprecated"`, `"author-classification"` e `"derived"` — e
  deixam a coluna **fora** do artefato. A lista de `evidence` **não** é fechada no parser: um
  valor desconhecido falha fechado (não gera), nunca vira `declared`.

### `type_source` — de onde veio o tipo

- **`"documented"`** (ou o campo ausente): o provedor publica o tipo — tabela de
  campos, schema, DDL.
- **`"format-observed"`**: o provedor **não** publica tabela de tipos, mas
  descreve o campo normativamente **e** o formato oficial fixa a representação:
  valor entre aspas ⇒ string, numeral nu ⇒ número, `{}` ⇒ objeto, `[]` ⇒ array.
  Use `type_note` (opcional, recomendado) para citar o trecho do exemplo oficial que fixa a
  forma.

Só esses dois valores (e a ausência) autorizam a gerar valor. `format-observed` **não** é licença
para adivinhar: ele exige que o campo seja declarado (`evidence` declarativa), e derivar a forma
de um exemplo para um campo que só existe no exemplo é recusado pelo validador. Qualquer outro
`type_source` — nas specs atuais há **5** colunas com `"derived"` — **não gera**: falha fechada.

O validador informa quantas colunas dependem de `format-observed` (medido em 2026-10-29: **45**
colunas), para que o qualificador mais fraco fique visível em vez de diluído.

### Quando uma coluna entra no artefato, e quando ela recebe valor

São **duas** decisões, e confundi-las custa fidelidade nos dois sentidos.

**Pertence ao formato** (`belongs_to_schema`) — a coluna tem de existir no
artefato:

| Requisito | Por quê |
|---|---|
| `name` | sem nome não há campo |
| `type` | em alvo tipado (Parquet, DDL) escrever sem tipo obriga a inventar |
| `status: verified` | a documentação precisa afirmar |
| `source_url` | sem a URL não há evidência |
| `evidence` ∈ {`declared`, `null-empty`} | a documentação estabelece a coluna |

**Pode receber valor** (`is_generatable`) — a coluna pode ser preenchida:

| Requisito adicional | Por quê |
|---|---|
| `evidence: declared` | um exemplo não é contrato |
| `type_source` ∈ {`documented`, `format-observed`} | a origem do tipo precisa ser nomeada |

A diferença é o `null-empty`: a documentação afirma que a coluna **existe no
arquivo** e que **nunca tem valor**. Omiti-la seria infiel ao formato;
preenchê-la seria infiel ao contrato. O único resultado correto é emiti-la vazia.
Já `example-only` não pertence ao formato: um exemplo de payload não estabelece
um schema.

O validador informa separadamente `geraveis` (podem ter valor) e
`nao_comprovadas`, e o `--matrix` mostra o que falta gerar.

Uma coluna que falhe em qualquer um fica **descrita e não-gerável**. Isso é um
resultado correto e esperado, não uma pendência: significa que o simulador não
pode emitir aquele campo sem inventar. O efeito prático é deliberado — o dataset
clássico de custo da Microsoft (só nomes, sem tipos publicados) e o manifesto de
export (definido por um único exemplo) não são gerados, enquanto a FOCUS 1.2, que
a Microsoft publica com tipos, é.

### O que o validador reprova (e o que ele não impõe)

`load_spec`/`validate_spec` são **fail-closed**: cada linha abaixo é erro de carregamento, não
aviso.

| Reprova | Onde |
|---|---|
| `surface` ou `provider` ausente/vazio | `load_spec` |
| nem `columns` nem `sets` (use `[]` quando o provedor não publica schema) | `load_spec` |
| conjunto com `columns` ausente, não-lista ou vazio | `load_spec` |
| coluna sem `name` | `load_spec` |
| `status` fora de `verified`/`unverified` | `load_spec` |
| coluna `verified` sem `source_url` | `load_spec` |
| `type_source: format-observed` num campo cuja `evidence` não é declarativa | `load_spec` |
| nome repetido dentro do mesmo conjunto (mesmo `scope`) | `load_spec` |
| `reference.title`/`.url`/`.consulted_at` ausente | `validate_spec` |
| nome **de campo** em `columns` **e** em `unverified` ao mesmo tempo (tópico não conta) | `validate_spec` |
| coluna `required` com status `unverified` | `validate_spec` |
| spec sem colunas **e** sem `unverified` | `validate_spec` |

O validador **não** impõe: lista fechada de `evidence`/`type_source` (qualificador desconhecido
falha fechado, mas não é erro de parse), o esquema de `delivery`, nem as chaves extras de
proveniência. A citação em `source_url` precisa ser **documentação oficial legível**, não endpoint
de máquina: isso é imposto pela suíte
(`test_specs_contract.py::test_todo_campo_cita_documentacao_oficial`, via
`fidelity/sources.is_official_url`), que aceita `docs.aws.amazon.com`, `aws.amazon.com`,
`cloud.google.com`, `docs.cloud.google.com`, `learn.microsoft.com`, `focus.finops.org`,
`github.com` e `raw.githubusercontent.com` — e reprova o resto.

## Regra de ouro

Se a documentação não afirma, o simulador não afirma. `UNVERIFIED` é uma resposta
válida e esperada; um palpite plausível não é.

## O artefato de export não carrega proveniência

O arquivo que representa o export contém **apenas** os campos que a nuvem
documenta — nada mais. Proveniência (`spec`, `mechanism`, `model_gaps`, contagens,
notas de cobertura, o que o modelo não tinha) é informação valiosa, mas vai para um
arquivo **irmão**, por exemplo `_meta.json`, e nunca para dentro do export.

A razão é prática: quem ingere o artefato vê as chaves que estão lá. Uma chave de
proveniência misturada com os registros é, do ponto de vista de quem consome, um
campo que nuvem nenhuma documenta — e o auditor de fidelidade a acusa como
invenção, com razão. Boa parte das "colunas inventadas" encontradas na auditoria
de 2026-10-14 era exatamente isso.

Vale também para as superfícies cuja entrega é uma resposta de API: o que sai é o
registro documentado; o relatório fica ao lado.
