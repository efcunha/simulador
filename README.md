# Simulador  
# Gerador de nuvens sinteticas + emuladores de API

> Idioma: **Português** | [English](README.en.md)

Simulador multi-nuvem **independente**. Gera todos os dados necessarios —
FinOps, seguranca, rede, instancias e **drift/what-if** — para **AWS, GCP e
Azure** e para um **cluster Kubernetes sintetico**, e os entrega seguindo o
mecanismo e o formato de export que **cada nuvem realmente usa**. As mesmas
APIs que o consumidor chama na nuvem real sao servidas pelos emuladores.

![Synthetic multi-cloud data, real API contracts](docs/img/hero.svg)

O repositorio tem tres partes:

| Parte | Onde | O que e |
|---|---|---|
| **Gerador** | `tools/synthetic_clouds/` | Deriva os artefatos a partir das specs citadas; tem os gates de fidelidade. |
| **Emuladores** | `emulators/` | Servem os mesmos dados pelas APIs de cada nuvem: `aws-sim`, `azure-sim`, `gcp-sim` e `k8s-sim` (OpenCost). |
| **Deployment** | `deploy/`, `scripts/` | Compose de cada plano, front TLS com os hostnames reais e a automacao da integracao com o CloudPilot. |

> Os numeros de "Estado atual" foram medidos em **2026-10-30**, na revisao
> `9ccbc71c`. A coluna "Como medir" diz exatamente qual comando reproduz cada
> um — se um numero divergir do codigo, o comando ganha do numero.

## Estado atual

| Metrica | Valor | Como medir |
|---|---|---|
| Superficies especificadas | **49** — AWS 15 · GCP 23 · Azure 11 | `specs/**/*.schema.json` |
| Superficies **PRONTO** | **47** | `fidelity --ready` → `PRONTO: 47`, exit 0 |
| Bloqueadas pela documentacao | **2** — `azure/cost-management-export-cost-details` e `gcp/container-clusters` | `fidelity --matrix` → `bloqueado=2` |
| Falta gerar | **0** | `fidelity --matrix` → `falta=0` |
| Coluna inventada (qualquer provedor) | **0** | `fidelity --audit aws` → `com coluna inventada=0` |
| Itens nao comprovados | **293** em 49 superficies — AWS 88 · GCP 122 · Azure 83 | `specs\_tools\gerar-registro-nao-comprovados.py` |
| Testes | **1106 passam, 20 skip** (1126 coletados; 12–14 min) | `pytest tools\synthetic_clouds\tests -q` |
| Specs em prosa | **30** | `specs/<provedor>/*.md` |
| Emuladores | **4** — AWS · Azure · GCP · Kubernetes/OpenCost | `emulators/` |
| Arquivos versionados | **492** | `git ls-files` |

As duas superficies bloqueadas sao **recusas deliberadas**, nao faltas:

* `azure/cost-management-export-cost-details` — a Microsoft publica os 132
  nomes **sem tipos**, e nenhum deles aparece nos cinco contratos ao mesmo
  tempo. Gerar exigiria inventar o tipo e escolher um contrato — exatamente o
  que a regra 3 abaixo proibe.
* `gcp/container-clusters` — a documentacao sustenta a **forma** (o envelope
  `ListClustersResponse` e 4 dos 87 membros publicados de `Cluster`), mas a
  superficie e uma **resposta de API** servida ao vivo pelo `gcp-sim` em
  `container.googleapis.com`, e nao um arquivo de export. Sem um renderer que
  produza um artefato conferivel contra a spec, chamar a superficie de
  "implementada" seria mentira. A forma publicada e a citacao oficial estao em
  [`specs/gcp/container-clusters.md`](specs/gcp/container-clusters.md).

O motivo de cada uma — e de cada uma das 293 lacunas declaradas — esta em
[`docs/NAO-COMPROVADOS.md`](docs/NAO-COMPROVADOS.md), que e derivado das specs
e nunca editado à mao.

![Coverage, measured](docs/img/cobertura.svg)

## Regras inviolaveis

1. **Nada fora desta arvore.** O simulador e autonomo: nao escreve em nenhum
   banco, container ou repositorio de terceiros, e nunca fala com a nuvem real.
2. **Fidelidade aferida, nao presumida.** Todo nome de campo, tipo, unidade,
   formato de data, layout de path e tipo de arquivo vem de **documentacao
   oficial do provedor**, citada com URL e data de consulta.
3. **Nenhum campo inventado.** O que nao estiver documentado e marcado como
   `UNVERIFIED` e permanece fora da geracao ate ser comprovado. Nao existe
   "parece razoavel" neste projeto.
4. **Nada de credencial ou chamada faturavel.** O simulador nunca fala com a
   nuvem real. O `aws-sim` ainda recusa subir se detectar material de
   credencial real no ambiente (`emulators/aws-sim/aws_sim/guard.py`).

## Layout

| Caminho | Papel |
|---|---|
| `specs/` | Especificacoes de export por nuvem, com citacao da doc oficial. **Fonte da verdade.** |
| `specs/<cloud>/*.schema.json` | Inventario de campos legivel por maquina, derivado da spec e usado pelos testes de fidelidade. |
| `specs/_tools/` | Utilitarios de auditoria versionados (procedencia, colunas por spec, URLs, gerador do registro de nao-comprovados). |
| `tools/synthetic_clouds/` | O gerador, com o motor de fidelidade, o agendador diario, a entrega aos emuladores e a suite de testes. |
| `docs/` | Notas de metodo, decisoes, auditorias, contratos de API emulada e os mapas de impacto em `docs/regression/`. |
| `emulators/aws-sim/` | Emulador AWS (Query + S3 REST, STS, EC2, S3, Config, IAM, EKS, ECS, ELB, RDS, Lambda, DynamoDB, CloudWatch, CloudFormation, SSO) + `Containerfile`. |
| `emulators/azure-sim/` | Emulador Azure (ARM, Resource Graph, network, Container Service, cost export, Defender, Monitor, deployment stacks, token) + `Containerfile`. |
| `emulators/gcp-sim/` | Emulador GCP (REST: compute, container, Config/Infra Manager, recommender, monitoring, catalog, budgets, CRM, storage; gRPC: monitoring e SCC) + `Dockerfile`. |
| `emulators/k8s-sim/` | Emulador Kubernetes/OpenCost (`/allocation/compute`, `/clusterInfo`, `/healthz`) + `Containerfile`. |
| `deploy/synthetic-clouds/` | Um compose por plano (Azure, GCP, AWS, Kubernetes), o front TLS (`tls-front/`) e a automacao da integracao (`integration/`). |
| `scripts/synthetic-clouds/` | Orquestracao (`up`, `down`, `smoke` de AWS/GCP, `export_once`, `run_azure_sim`). |

O caminho `tools/synthetic_clouds` e deliberado: o codigo se auto-importa como
`tools.synthetic_clouds` em **871** pontos, e move-lo exigiria uma renomeacao em
massa sem ganho. A configuracao de `ruff`/`mypy`/`pytest` do pacote esta em
`tools/synthetic_clouds/pyproject.toml` — **nao** crie config na raiz.

## Metodo

O trabalho avanca nesta ordem, sempre:

1. **Especificar** — levantar o formato oficial em `specs/`, com citacao.
2. **Gerar** — implementar o renderer a partir da spec, nunca a partir de memoria.
3. **Provar** — teste de fidelidade que compara o artefato gerado contra
   `specs/<cloud>/*.schema.json`: conjunto de colunas exato, ordem,
   unidades e formatos.

Uma superficie so e considerada pronta quando os tres passos fecham.

## Arquitetura

![How the data flows](docs/img/pipeline.svg)

O caminho e sempre o mesmo: a **spec** e a fonte da verdade, o **gerador** e
deterministico, os **emuladores** servem o mesmo dado pelas APIs de cada nuvem,
e o **consumidor** ingere pelo proprio caminho de producao. Na rede do
CloudPilot, os emuladores e um **front TLS** publicam os hostnames reais
(`management.azure.com` pelo `azure-sim`; `bigquery.googleapis.com`,
`container.googleapis.com`, `securitycenter.googleapis.com`, ... pelo front
nginx) e os encaminham para o emulador certo — o codigo do consumidor nunca
sabe que fala com um simulador. O simulador nao fala com a nuvem real em
momento algum.

## O que e emulado

![What is emulated, by domain](docs/img/dominios.svg)

**Cinco dominios de dados** — custo/FinOps, seguranca, rede, instancias e
**drift/what-if** — nas tres nuvens. Cada celula corresponde a superficies com
spec, gerador e teste de fidelidade proprios.

Alem das superficies especificadas, os emuladores expõem as **rotas ao vivo**
correspondentes a varias delas — SCC findings (gRPC) e Compute firewalls (REST)
no `gcp-sim`, `container.googleapis.com` para a lista de clusters — e servem
dois contratos que **nao tem superficie de export** (por isso nao entram nas
49): a **descoberta de cluster** EKS/AKS, que e resposta de API, e o contrato
**OpenCost** do `k8s-sim`. Para esses dois, o que existe e o contrato medido no
codigo e nos testes do emulador, registrado nos mapas de impacto
(`docs/regression/`) e em `docs/k8s-sim-opencost-contract.md`.

**Como o CloudPilot alcanca o `k8s-sim`.** Desde a S4b2-C ele esta anexado a rede
`cloudpilot-deploy_cloudpilot_net` com o alias `k8s-sim`; desde a **S4b2-E** o consumidor
chega ate ele por **HTTPS**, no nome proprio do front TLS,
`https://opencost.synthetic-clouds.test` — o alias `k8s-sim` continua sendo o upstream do
front, em `http://k8s-sim:8089`. O vinco e reaplicado
idempotentemente por `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`, que
tambem cria o container a partir de `compose.k8s.yaml` quando ele falta — sem rebuild.
Detalhe em [regression/mapa-impacto-s4b2c.md](docs/regression/mapa-impacto-s4b2c.md) e
[regression/mapa-impacto-s4b2e.md](docs/regression/mapa-impacto-s4b2e.md).

**Como o CloudPilot alcanca o `aws-sim`.** O plano AWS tem o **proprio namespace** de
variaveis: `compose.aws.yaml` le `AWS_SIM_SEED`/`AWS_SIM_PROFILE`, nao os nomes genericos
`SEED`/`PROFILE` dos planos Azure/GCP. Sem o par `AWS_SIM_*`, o `aws-sim` cai no default
`small` e serve um estate **diferente** do resto da pilha. O `sts` do emulador e alcancado
pelo **endpoint por conta** (`cur_config.endpoint_overrides.sts`), e nao por um hijack do
hostname `sts.amazonaws.com` — hijack global quebraria as contas AWS reais que o
CloudPilot tambem consome. Detalhe em
[regression/mapa-impacto-s4b2c.md](docs/regression/mapa-impacto-s4b2c.md) §7.

**Como o CloudPilot alcanca o CUR do `aws-sim`.** O leitor de CUR usa o `endpoint_url` **por
conta** (`cur_config.endpoint_url`): nesta instalacao, `http://s3mock:9090` em *path style*,
no bucket `AWS_SIM_BUCKET` (`synthetic-focus12-daily-full`), com o prefixo
`focus12-full/<export_name>/`. O `export_name` precisa ser o nome que o **renderer emite**
(`synthetic-focus12-daily-full`); o `cloudpilot-focus12-daily-full` pertence ao renderer
anterior ao *standalone publish* (o que escrevia `Manifest.json` no export) e **nao encontra as
chaves publicadas** — medido na S4b3-A. O `aws-sim` expoe a **mesma arvore** pela superficie S3
REST (volume `aws_sim_render`, `AWS_SIM_S3_STORE_DIR=/render/aws_focus`); o store do `s3mock` e
em memoria, entao recriar o container esvazia o bucket e o `aws-up.ps1` precisa rodar de novo.
Medido na S4b3-A: a arvore FOCUS/S3 foi re-renderizada no perfil **`medium`** (130.236 linhas,
966 recursos com faturamento), publicada e **ingerida** — 58.926 linhas / US$ 166.204,47 no
`/costs/unified` da conta de homologacao. Detalhe em
[regression/mapa-impacto-s4b3a.md](docs/regression/mapa-impacto-s4b3a.md).

**E a entrega diaria (FR-22).** O dia gerado sobe para o S3 pelo mecanismo oficial
(`tools.synthetic_clouds.deliver`), e ela publica no **mesmo namespace** que o consumidor le:
bucket e segmento de export `synthetic-focus12-daily-full`, prefixo `focus12-full`. Antes da
S4b3-B a entrega publicava em `cloudpilot-focus12-daily-full` — o nome do renderer anterior ao
*standalone publish* — e o dia era gerado, subia para o S3, a ingestao reportava `status: ok` e o
`/costs/unified` continuava **sem AWS**: uma entrega silenciosa. Medido na S4b3-B: entrega do dia
`2026-10-26` → **exit 0**, 1 objeto novo em
`focus12-full/synthetic-focus12-daily-full/data/billing_period=2026-10/...` e **nenhum** bucket
`cloudpilot-focus12-daily-full` criado; ingestao oficial → `rows_promoted=54096`;
`/costs/unified` → `HOMOLOGATION AWS [sim] · 54.143,54` com
`data_source: focus_cost_records` (antes: `cost: null`, `data_state: "unavailable"`). Detalhe em
[regression/mapa-impacto-s4b3b.md](docs/regression/mapa-impacto-s4b3b.md).

**Debitos desta frente.** O plano Kubernetes **já tem** TLS desde a S4b2-E (nome próprio
`opencost.synthetic-clouds.test`, com SAN na folha do front), mas segue **sem** hostname de
nuvem real para imitar; `scripts/synthetic-clouds/up.ps1` **nao** sobe esse
plano (ele sobe pela integracao, que e o dono do vinco); e
`docs/DECISOES-PENDENTES.md` ainda afirma que o `k8s-sim` "nao tem Containerfile nem
servico de compose" — frase que ficou falsa na S4b2-B e que este arquivo esta fora da
allowlist da fase, entao o texto nao foi corrigido aqui.

## Ambiente

```powershell
# interpretador proprio do projeto (CPython 3.12)
& "C:\Users\ECUNHA\AppData\Local\Programs\Python\Python312\python.exe" -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -U pip
& .\.venv\Scripts\python.exe -m pip install pandas pyarrow pydantic pytest ruff mypy
```

Os emuladores tem dependencias proprias — `fastapi`/`uvicorn` em todos, `boto3`
e `botocore` nos testes do `aws-sim` — e cada um fixa o proprio ambiente no
`Containerfile`; eles **nao** rodam no `.venv` do gerador.

`python -m tools...` acha o pacote pelo proprio CWD e **nao** precisa de
`PYTHONPATH`; so os scripts executados por caminho (`specs\_tools\*.py`) precisam
— e esses ja inserem a raiz no `sys.path` sozinhos.

### Verificacao do gerador

```powershell
# contrato das specs e estado de prontidao (exit != 0 enquanto houver problema)
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --ready
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --matrix   # gerado / falta / bloqueado
& .\.venv\Scripts\python.exe -m tools.synthetic_clouds.fidelity --audit aws # colunas inventadas

# lint e tipo usam a configuracao de registro do pacote: SEMPRE com --config
& .\.venv\Scripts\ruff.exe check tools\synthetic_clouds --config tools\synthetic_clouds\pyproject.toml
& .\.venv\Scripts\mypy.exe -p tools.synthetic_clouds --config-file tools\synthetic_clouds\pyproject.toml
& .\.venv\Scripts\python.exe -m pytest tools\synthetic_clouds\tests -q
```

**A suite e `pytest tools\synthetic_clouds\tests`.** O `mypy` e `-p`, nao
caminho: `mypy tools\synthetic_clouds` falha com *"Source file found twice under
different module names"* e **nao checa nada**.

### Os 20 skips da suite sao decisoes, nao falhas

Os skips vem de dois guardas deliberados: a fixture `real_parser` carrega o
parser CUR/FOCUS da plataforma **consumidora** para conferir o round-trip — essa
plataforma nao faz parte deste repositorio, entao a fixture **skipa** quando ele
nao esta presente (o guard e `pytest.skip`, nao erro); e os testes de fixtures
GCP que dependem de labels condicionais **skipam** quando a superficie
declarada nao tem label condicional. Nenhum dos dois esconde falha: um skip nao
e um teste que passou.

## Emuladores

A pilha sobe com `podman compose`. Cada plano tem o seu fragmento, e
`up.ps1` sequencia os tres planos de nuvem:

| Compose | Servicos | Portas (host) |
|---|---|---|
| `compose.yaml` | `azurite` + `azure-sim` | 8080 (API) · 10000 (blob) — 443/TLS dentro da rede |
| `compose.gcp.yaml` | `bigquery-emulator` + `gcp-bq-provision` + `gcp-sim` | 9050 (BigQuery REST) · 9060 (BigQuery gRPC) · 8085 (REST) · 8087 (gRPC) — o gRPC do SCC (8088) e o 443 do Azure são internos à rede |
| `compose.aws.yaml` | `s3mock` + `aws-sim` | 9090 (S3) · 8086 (Query/JSON) |
| `compose.tls-front.yaml` | front nginx | 443 (hostnames reais, rede do CloudPilot) |

```powershell
cd deploy\synthetic-clouds
Copy-Item .env.example .env      # ajuste as portas se preciso
..\..\scripts\synthetic-clouds\up.ps1
```

O quarto emulador, o `k8s-sim`, serve o contrato OpenCost
(`/allocation/compute`, `/clusterInfo`, `/healthz`) a partir do fixture versionado
`k8s_sim/fixtures/clusters.json`. Desde a **S4b2-B** ele tem `Containerfile` e servico
de compose (`deploy/synthetic-clouds/compose.k8s.yaml`); desde a **S4b2-C** ele e
**anexado a rede do CloudPilot** com o alias `k8s-sim`; e desde a **S4b2-E** o backend do
CloudPilot o alcanca por **HTTPS**, em `https://opencost.synthetic-clouds.test` (o nome
proprio do front TLS — o plano nao imita hostname de nuvem). O contrato e o comando de
execucao estao em
[`docs/k8s-sim-opencost-contract.md`](docs/k8s-sim-opencost-contract.md).

O `gcp-sim` precisa dos *fixtures* renderizados para responder; o
`gcp-smoke.ps1` faz o ciclo inteiro (render → provision → leitura).

Para o CloudPilot falar com a pilha pelos **hostnames reais** (DNS + TLS local),
use a automacao idempotente de `deploy/synthetic-clouds/integration/`
(`cold-start.ps1`, `ensure-cloudpilot.ps1`) e leia
[`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](docs/INTEGRACAO-CLOUDPILOT-TLS.md).

### Como as imagens sao construidas

O **contexto de build** e a raiz deste repositorio, e cada `Containerfile`
copia **apenas** o que precisa:

```dockerfile
COPY tools/synthetic_clouds      /app/tools/synthetic_clouds
COPY emulators/aws-sim           /app/emulators/aws-sim
```

O gerador entra na imagem como namespace `tools.synthetic_clouds.*`, resolvido
por `PYTHONPATH=/app` — nunca como wheel instalado. Nenhum outro diretorio
participa do build, e o `k8s-sim` usa o **proprio** pacote como contexto de build
(o gerador nao e importado por ele).

## Onde ler mais

| Documento | Para que |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Contrato operacional para agentes: como rodar, o que nunca editar a mao, o que fazer quando a evidencia nao existe. |
| [`specs/README.md`](specs/README.md) | O contrato que cada spec `.md` e cada `*.schema.json` precisa cumprir. |
| [`docs/ESTADO.md`](docs/ESTADO.md) | Estado do simulador: o que esta pronto, o que esta bloqueado e por que, e o que mudou em cada onda. |
| [`docs/NAO-COMPROVADOS.md`](docs/NAO-COMPROVADOS.md) | As 293 lacunas declaradas, com o motivo que a spec registra; derivado das specs. |
| [`docs/POSTURA-SEGURANCA.md`](docs/POSTURA-SEGURANCA.md) | Os checks de seguranca do gerador e dos emuladores. |
| [`docs/INTEGRACAO-CLOUDPILOT-TLS.md`](docs/INTEGRACAO-CLOUDPILOT-TLS.md) | Hostnames reais, TLS, STS e a automacao que sobrevive a restart. |
| [`docs/k8s-sim-opencost-contract.md`](docs/k8s-sim-opencost-contract.md) | O contrato do `/allocation/compute` do `k8s-sim`, com a fonte de cada campo. |
| [`docs/AGENDAMENTO.md`](docs/AGENDAMENTO.md) | Geracao diaria: horario, lag, retencao e a entrega aos emuladores. |
| [`tools/synthetic_clouds/README.md`](tools/synthetic_clouds/README.md) | O gerador em detalhe: estrutura, metodo e armadilhas conhecidas. |
