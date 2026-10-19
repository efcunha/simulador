# Especificações de export

Esta pasta é a **fonte da verdade** do simulador. Nada é gerado sem que o formato
correspondente esteja especificado aqui, com citação de documentação oficial do
provedor.

O validador normativo é `tools/synthetic_clouds/fidelity/spec.py`. Este documento
descreve o mesmo contrato em prosa; em caso de divergência, **o código manda**.

```powershell
# rodar o validador (exit 1 enquanto houver qualquer problema)
cd <raiz-do-repo>
$env:PYTHONPATH='<raiz-do-repo>'
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity
```

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
          "evidence": "declared"
        }
      ]
    }
  ],
  "unverified": []
}
```

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

- **`status`**: estritamente `"verified"` ou `"unverified"`. É o eixo binário —
  a documentação afirma ou não afirma.
- **`evidence`**: a *qualidade* da afirmação. `"declared"` (ou o campo ausente)
  significa que a documentação enuncia a coluna como contrato. Qualquer outro
  valor descreve documentação real porém insuficiente: `"example-only"`,
  `"name-only"`, `"null-empty"`, `"deprecated"`, `"author-classification"`.

### `type_source` — de onde veio o tipo

- **`"documented"`** (ou o campo ausente): o provedor publica o tipo — tabela de
  campos, schema, DDL.
- **`"format-observed"`**: o provedor **não** publica tabela de tipos, mas
  descreve o campo normativamente **e** o formato oficial fixa a representação:
  valor entre aspas ⇒ string, numeral nu ⇒ número, `{}` ⇒ objeto, `[]` ⇒ array.
  Use `type_note` para citar o trecho do exemplo oficial que fixa a forma.

`format-observed` **não** é licença para adivinhar. Ele exige que o campo seja
declarado (`evidence: declared`): derivar a forma de um exemplo para um campo que
só existe no exemplo é recusado pelo validador. Um `type_source` desconhecido
também não gera — falha fechada.

O validador informa quantas colunas dependem de `format-observed`, para que o
qualificador mais fraco fique visível em vez de diluído.

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
