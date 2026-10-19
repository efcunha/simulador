"""Raiz do repositorio: a unica regra de coleta que o simulador precisa.

POR QUE ESTE ARQUIVO EXISTE
----------------------------
`attic/README.md` comeca com a regra do proprio diretorio: *"nada nesta pasta entra na suite
de testes padrao, no lint ou no type-check do pacote. Se algum dia voltar a ser util, sai
daqui de forma deliberada -- nao por accident."*

A regra estava escrita e nao estava codificada. Sem isto, um `pytest` sem argumento na raiz
recolhe `attic/product-coupled/test_coverage_matrix.py` e ABORTA com erro de colecao antes de
rodar um unico teste -- e o motivo do abort e duplo:

1. o import do teste aponta para `tools.synthetic_clouds.coverage`, caminho onde o pacote
   vivia antes de ser arquivado (ele esta agora em `attic/product-coupled/coverage/`); e
2. mesmo com o import corrigido, as 17 provas daquele pacote medem `<arvore-do-consumidor>` do
   FinOps, arvore que o simulador independente nao tem e nao deve depender.

Ou seja: o `attic/` nao entra na suite por DECISAO, e este arquivo e a decisao virando
codigo. O material continua no git, com o valor historico que o README descreve -- inclusive
o achado do gap de versao 1.2 -> 1.4 do FOCUS -- e volta a ser testavel de forma
deliberada, no produto, na fase de ingestao.

POR QUE UM CONFTEST E NAO UM `pytest.ini`
-----------------------------------------
O `tools/synthetic_clouds/pyproject.toml` registra que configuração na raiz viola o NFR-5
deste projeto. Este arquivo nao e configuracao: ele nao altera `testpaths`, nao registra
markers e nao muda o inifile. Ele so diz ao pytest para nao descer no `attic/`, e por isso
nao carrega nenhum dos efeitos que a regra proibe. O rootdir continua sendo
`tools/synthetic_clouds` quando se roda a suite do pacote, e o `pyproject.toml` continua
sendo o configfile -- medido antes e depois desta mudanca: 880 testes, os mesmos rootdir e
configfile.
"""

from __future__ import annotations

#: Caminhos, relativos a este arquivo, que o pytest nao deve recolher. `attic/` e a regra
#: escrita do `attic/README.md`; `.venv/`, caches e `out/` ja entram no `norecursedirs`
#: padrao do pytest, mas ficam aqui para que a lista diga o que ela quer em vez de depender
#: do que o pytest ja faz por conta propria.
collect_ignore_glob = [
    "attic/*",
]
