"""Extracao do conjunto de campos de um artefato gerado.

A fidelidade tem de ser medida no ARTEFATO, nao no codigo que o produziu: um
renderer pode declarar a coluna certa e escrever vazio, ou declarar 60 colunas e
gravar 59. Aqui o conjunto de campos vem do proprio arquivo entregue.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO


class ArtifactError(ValueError):
    """Artefato ilegivel ou em formato nao suportado."""


@contextmanager
def _open_text(path: Path, encoding: str) -> Iterator[IO[str]]:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding=encoding, newline="") as handle:
            yield handle
    else:
        with path.open("r", encoding=encoding, newline="") as handle:
            yield handle


def _parquet_columns(path: Path) -> tuple[str, ...]:
    import pyarrow.parquet as pq  # import local: o nucleo nao depende de pyarrow

    schema = pq.read_schema(path)
    return tuple(schema.names)


def _csv_columns(path: Path, delimiter: str, encoding: str) -> tuple[str, ...]:
    with _open_text(path, encoding) as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        for row in reader:
            if row:
                return tuple(cell.strip().lstrip("\ufeff") for cell in row)
        return ()


def _json_columns(path: Path, encoding: str) -> tuple[str, ...]:
    # Nao usar ``path.read_text()``: a entrega documentada de algumas nuvens e
    # JSON GZIPADO (o snapshot do AWS Config, por exemplo). Ler direto estoura
    # UnicodeDecodeError e o efeito e cruel -- a ferramenta fica cega para o
    # arquivo e o ausente parece ser um campo que o renderer nao emitiu.
    with _open_text(path, encoding) as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        # Objeto unico: as chaves sao os campos.
        return tuple(payload.keys())
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return tuple(item.keys())
        return ()
    raise ArtifactError(f"{path}: JSON precisa ser objeto ou lista de objetos")


def _jsonl_columns(path: Path, encoding: str) -> tuple[str, ...]:
    with _open_text(path, encoding) as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                return tuple(item.keys())
    return ()


def columns_of(
    path: Path | str,
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> tuple[str, ...]:
    """Devolve a lista de campos do artefato, na ordem em que aparecem.

    Formatos: ``.parquet``, ``.csv`` (e ``.csv.gz``), ``.json`` (objeto ou
    lista de objetos) e ``.jsonl``/``.ndjson``. A ordem e preservada porque em
    CSV ela faz parte do formato.
    """
    path = Path(path)
    if not path.is_file():
        raise ArtifactError(f"artefato nao encontrado: {path}")

    suffixes = [suffix.lower() for suffix in path.suffixes]
    if ".gz" in suffixes:
        suffixes.remove(".gz")
    suffix = suffixes[-1] if suffixes else ""

    if suffix == ".parquet":
        return _parquet_columns(path)
    if suffix == ".csv":
        return _csv_columns(path, delimiter, encoding)
    if suffix == ".json":
        return _json_columns(path, encoding)
    if suffix in {".jsonl", ".ndjson"}:
        return _jsonl_columns(path, encoding)
    raise ArtifactError(f"{path}: formato nao suportado ({suffix or 'sem extensao'})")


# Representacoes de "sem valor". Nao basta None e "": um export que declara a
# coluna como sempre vazia escreve `{}` num campo JSON e `[]` numa lista, e
# esses tambem sao ausencia de valor -- nao conteudo.
_EMPTY_TOKENS = frozenset({"", "{}", "[]", "null", "none", "nan"})


def is_empty_value(value: object) -> bool:
    """Verdadeiro se o valor representa ausencia de conteudo.

    Zero e falso NAO sao vazios: sao valores legitimos e distintos de ausencia.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_TOKENS
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def populated_of(
    path: Path | str,
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> tuple[str, ...]:
    """Campos que tem AO MENOS UM valor nao vazio no artefato.

    Existe porque conferir so o nome da coluna deixa passar o defeito simetrico:
    o renderer declara ``CapacityReservationId`` e escreve um valor inventado
    nela. Uma coluna que a documentacao marca como sempre vazia tem de estar
    vazia no arquivo.

    Devolve os nomes do NIVEL DE TOPO do artefato. Ver ``populated_paths`` para a
    pergunta diferente -- e frequentemente a que se quer -- "quais dos caminhos
    que a especificacao enumera tem valor?".
    """
    path = Path(path)
    if not path.is_file():
        raise ArtifactError(f"artefato nao encontrado: {path}")

    suffixes = [suffix.lower() for suffix in path.suffixes]
    if ".gz" in suffixes:
        suffixes.remove(".gz")
    suffix = suffixes[-1] if suffixes else ""

    if suffix == ".parquet":
        return _parquet_populated(path)
    if suffix == ".csv":
        return _csv_populated(path, delimiter, encoding)
    if suffix == ".json":
        return _json_populated(path, encoding)
    if suffix in {".jsonl", ".ndjson"}:
        return _jsonl_populated(path, encoding)
    raise ArtifactError(f"{path}: formato nao suportado ({suffix or 'sem extensao'})")


def _populated_from_rows(rows: list[dict[str, object]]) -> tuple[str, ...]:
    if not rows:
        return ()
    names: list[str] = list(rows[0])
    return tuple(
        name for name in names if any(not is_empty_value(row.get(name)) for row in rows)
    )


def _resolve_path(row: object, parts: list[str]) -> list[object]:
    """Valores alcancados por um caminho pontuado dentro de ``row``.

    Duas formas de lista, porque as especificacoes usam as DUAS (e uma terceira, que
    e a mesma coisa escrita sem marcador):

    * ``networkInterfaces[].id`` -- qualquer item serve;
    * ``flowTuples[0]`` -- a POSICAO importa (o NSG publica as 13 posicoes do
      tuplo como caminhos indexados);
    * ``labels.key`` -- a spec NAO escreve o marcador, mas ``labels`` e uma lista
      de structs. Descer so quando o nome traz ``[]`` contava como vazio o que tem
      valor: nas tabelas de billing do GCP isso escondia 11 caminhos na standard,
      11 na detailed e 4 na pricing.

    Tratar qualquer dessas formas como nome literal de chave devolvia nada, e a
    coluna obrigatoria aparecia vazia onde havia valor -- falso positivo que mandaria
    alguem procurar defeito inexistente.
    """
    if not parts:
        return [row]
    if not isinstance(row, dict):
        return []
    head, rest = parts[0], parts[1:]

    if head.endswith("[]"):
        valor = row.get(head[:-2])
        if not isinstance(valor, list):
            return []
        alcancados: list[object] = []
        for item in valor:
            alcancados.extend(_resolve_path(item, rest))
        return alcancados

    indexado = re.fullmatch(r"(.+)\[(\d+)\]", head)
    if indexado:
        valor = row.get(indexado.group(1))
        posicao = int(indexado.group(2))
        if isinstance(valor, list) and posicao < len(valor):
            return _resolve_path(valor[posicao], rest)
        return []

    if head not in row:
        return []
    valor = row[head]
    if isinstance(valor, list):
        # Repeticao IMPLICITA: `labels.key` sobre `labels: [{key: ...}]`.
        repetidos: list[object] = []
        for item in valor:
            repetidos.extend(_resolve_path(item, rest))
        return repetidos
    return _resolve_path(valor, rest)


def _json_rows(path: Path, encoding: str) -> list[dict[str, object]]:
    with _open_text(path, encoding) as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ArtifactError(f"{path}: JSON precisa ser objeto ou lista de objetos")


def populated_paths(
    path: Path | str,
    names: Iterable[str],
    *,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> tuple[str, ...]:
    """Quais dos ``names`` (caminhos da especificacao) tem valor no artefato.

    Pergunta diferente da de ``populated_of``, e frequentemente a que se quer: o
    artefato e ANINHADO (os campos de um registro de billing do GCP vivem dentro
    de ``invoice``/``service``/``project``) enquanto a especificacao enumera
    CAMINHOS pontuados. Comparar chave de topo com caminho pontuado subconta de
    forma brutal -- no billing do GCP, 50 dos 71 nomes tem ponto, e a contagem por
    topo dizia 17 onde a contagem por caminho diz 58.

    Formatos planos (CSV, Parquet) nao tem profundidade: a resposta e a mesma de
    ``populated_of`` restrita aos nomes pedidos.

    As DUAS formas de artefato contam, e e preciso aceitar as duas: um registro de
    billing do GCP ANINHA os campos (``{"invoice": {"month": ...}}``), enquanto o
    finding do SCC e o flow log do GCP ACHATAM o caminho numa chave literal
    (``{"finding.name": ...}``). Olhar so uma das formas erra para baixo na outra:
    resolver so o aninhamento zerava o SCC, como se ele nao entregasse nada.
    """
    alvo = Path(path)
    restantes = tuple(names)
    suffixes = [suffix.lower() for suffix in alvo.suffixes]
    if ".gz" in suffixes:
        suffixes.remove(".gz")
    suffix = suffixes[-1] if suffixes else ""

    if suffix not in {".json", ".jsonl", ".ndjson"}:
        preenchidos = set(populated_of(alvo, delimiter=delimiter, encoding=encoding))
        return tuple(nome for nome in restantes if nome in preenchidos)

    if suffix == ".json":
        rows = _json_rows(alvo, encoding)
    else:
        rows = []
        with _open_text(alvo, encoding) as handle:
            for line in handle:
                texto = line.strip()
                if texto:
                    item = json.loads(texto)
                    if isinstance(item, dict):
                        rows.append(item)

    achados: list[str] = []
    for nome in restantes:
        partes = nome.split(".")
        for linha in rows:
            if not is_empty_value(linha.get(nome)):  # chave literal achatada
                achados.append(nome)
                break
            if any(not is_empty_value(valor) for valor in _resolve_path(linha, partes)):
                achados.append(nome)
                break
    return tuple(achados)


def _parquet_populated(path: Path) -> tuple[str, ...]:
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    return tuple(
        name
        for name in table.column_names
        if any(not is_empty_value(value) for value in table.column(name).to_pylist())
    )


def _csv_populated(path: Path, delimiter: str, encoding: str) -> tuple[str, ...]:
    with _open_text(path, encoding) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return _populated_from_rows([dict(row) for row in reader])


def _json_populated(path: Path, encoding: str) -> tuple[str, ...]:
    with _open_text(path, encoding) as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        return _populated_from_rows([payload])
    if isinstance(payload, list):
        return _populated_from_rows([item for item in payload if isinstance(item, dict)])
    raise ArtifactError(f"{path}: JSON precisa ser objeto ou lista de objetos")


def _jsonl_populated(path: Path, encoding: str) -> tuple[str, ...]:
    rows: list[dict[str, object]] = []
    with _open_text(path, encoding) as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            item = json.loads(text)
            if isinstance(item, dict):
                rows.append(item)
    return _populated_from_rows(rows)
