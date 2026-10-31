# Mapa de impacto — Fase S4b3-F (o `AGENTS.md` e os docs de integração passam a falar do `k8s-sim` real)

**Data:** 2026-10-31 · **Revisão-base:** `e47c5fb8` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `AGENTS.md`, `deploy/synthetic-clouds/integration/README.md`,
`docs/k8s-sim-opencost-contract.md`, `docs/INTEGRACAO-CLOUDPILOT-TLS.md`, `docs/ESTADO.md`,
`docs/ESTADO.en.md`, este mapa.
**Fora do escopo:** `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`,
`deploy/synthetic-clouds/tls-front/**`, `specs/**`, `docs/NAO-COMPROVADOS*` (gerado),
`tools/**`, `scripts/**` e o código do `C:\Projetos\cloudpilot-deploy`.

**Por que esta fase existe.** O `AGENTS.md` é a bússola do repositório: quem lê as regras
permanentes lê também as afirmações factuais que elas carregam, e uma afirmação falsa ali vira
dedução na cabeça de quem lê. Duas dessas afirmações sobre o `k8s-sim` estavam paradas no tempo, e
os docs de integração/contrato ainda falavam do plano Kubernetes como se o TLS fosse o **restante**
da S4b2.

A primeira já tinha sido **vista e nomeada** em 2026-10-30: o
[`mapa-impacto-s4b2c.md`](mapa-impacto-s4b2c.md) §6 registra que o `AGENTS.md` dizia "o caso
extremo: sem `Containerfile`", que a frase "ficou falsa na S4b2-B" e que o arquivo estava
"explicitamente proibido de edição nesta fase". É um débito nomeado que ninguém pagou até aqui —
esta fase paga.

A segunda não tinha sido vista: o `AGENTS.md` declarava uma **lacuna aberta** sobre o id nativo do
cluster que a própria S4b1-E já tinha **fechado no mesmo dia** (§2.2).

**Nenhuma linha de código, de container, de tarefa agendada ou de configuração do CloudPilot foi
tocada.** Esta fase é documental, do começo ao fim.

## 1. O que muda

| | Antes (leitura de 2026-10-31, revisão `e47c5fb8`) | Depois |
|---|---|---|
| **`AGENTS.md` — "caso extremo"** | "O `k8s-sim` é o caso extremo: **sem `Containerfile`**" (falso desde a S4b2-B) | `Containerfile` e serviço no `compose.k8s.yaml` desde a **S4b2-B**; publicado por TLS no front desde a **S4b2-E** |
| **`AGENTS.md` — "lacuna aberta"** | "**Lacuna aberta em 2026-10-29 (S4b1-E)**… a correção é carregar o id nativo no fixture" | "**Fechado em 2026-10-29 pela S4b1-E**" — `a64b8414`, `native_id` por cluster (**309**) |
| **`AGENTS.md` — URL do consumidor** | ausente | `https://opencost.synthetic-clouds.test` |
| **`integration/README.md`** | "Não publica o `k8s-sim` por hostname real nem por TLS… **TLS para o plano Kubernetes é o restante da S4b2**" | o script garante o **caminho** (alias, SAN, front) e **não** configura o consumidor; `k8s-sim:8089` é o **upstream** do front |
| **`docs/k8s-sim-opencost-contract.md`** | o bloco "Atualizado em 2026-10-30 pela S4b2-C" lia como afirmação corrente | registro datado **preservado** + retificação datada da S4b3-F (o TLS fechou na S4b2-E) |
| **`docs/INTEGRACAO-CLOUDPILOT-TLS.md` L23** | só a URL do upstream (`http://k8s-sim:8089`) | a **URL do consumidor** (`https://opencost.synthetic-clouds.test`) na mesma linha |
| **URL do consumidor nos 4 docs** | ausente no `AGENTS.md` e no `integration/README.md` | presente nos **quatro** |
| **Regras permanentes** | — | **inalteradas** — o diff do `AGENTS.md` toca só as passagens do `k8s-sim` |

## 2. As duas passagens do `AGENTS.md`, e a prova de cada uma

### 2.1 "sem `Containerfile`" — fechado na S4b2-B

```powershell
git show --name-only --oneline 53a47ce9
# -> emulators/k8s-sim/Containerfile

git show --name-only --oneline 50245581
# -> deploy/synthetic-clouds/compose.k8s.yaml
```

`53a47ce9` (**S4b2-B**) criou o `Containerfile` do `k8s-sim`; `50245581` (**S4b2-B**) declarou o
serviço no `compose.k8s.yaml` — `image: localhost/k8s-sim:latest`, `build.context:
../../emulators/k8s-sim`, `K8S_SIM_PORT: "8089"`. Desde então o emulador é um emulador como os
outros: imagem própria, serviço próprio, porta fixa.

### 2.2 A "lacuna aberta" do id nativo — fechada na S4b1-E, no mesmo dia

```powershell
git show --name-only --oneline a64b8414
# -> docs/k8s-sim-opencost-contract.md
#    emulators/k8s-sim/k8s_sim/app.py
#    emulators/k8s-sim/k8s_sim/fixtures/clusters.json
#    emulators/k8s-sim/k8s_sim/projections/allocation.py
#    emulators/k8s-sim/k8s_sim/tests/test_allocation.py
#    emulators/k8s-sim/scripts/export_clusters.py
```

O commit `a64b8414` (**S4b1-E**, 2026-10-29) carregou o `native_id` por cluster no fixture
versionado (**309 clusters**: 75 EKS, 111 GKE, 123 AKS) e passou o filtro a aceitá-lo como
**alias** — sem publicá-lo: o contrato continua publicando o **nome**. O próprio
[`mapa-impacto-s4b1d.md`](mapa-impacto-s4b1d.md) §8 já listava o item sob "**Fechados em S4b1-E
(2026-10-29)**", e o `docs/k8s-sim-opencost-contract.md` já abria o bloco "**Fechado em 2026-10-29
pela S4b1-E**". O `AGENTS.md` é o único lugar que ainda o descrevia como pendência — e é o lugar que
todos leem primeiro.

**Esta correção vai além da passagem listada no enunciado** (que apontava só para o `Containerfile`).
Ela entra porque o objetivo da fase é "corrigir as últimas afirmações obsoletas sobre o `k8s-sim` no
`AGENTS.md`", o fato é **verificado** por commit (não por dedução) e a afirmação era exatamente do
mesmo tipo da listada: uma verdade que o próprio repositório já tinha desmentido. Nenhuma regra
permanente do `AGENTS.md` foi tocada.

### 2.3 O caminho de rede — por que a URL do consumidor é essa

Três arquivos do deploy, todos versionados, fecham a cadeia:

| Arquivo | O que declara |
|---|---|
| `deploy/synthetic-clouds/tls-front/nginx.conf` | `upstream k8s_opencost { server k8s-sim:8089; }` e o `server { server_name opencost.synthetic-clouds.test; location / { proxy_pass http://k8s_opencost; } }` |
| `deploy/synthetic-clouds/compose.tls-front.yaml` | o alias `opencost.synthetic-clouds.test` na bridge `cloudpilot-deploy_cloudpilot_net` |
| `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1` | `$K8sSimUrl = 'https://opencost.synthetic-clouds.test'` (a rota do consumidor) e `$K8sSimAliasUrl = 'http://k8s-sim:8089'` (o upstream, medido em HTTP pelo `-Smoke`) |

O nome é do **front**, não da nuvem: o plano Kubernetes não tem hostname real para imitar, e `.test`
é a TLD reservada para testes (RFC 6761) — não resolve na internet pública. O `k8s-sim:8089`
continua sendo o **upstream** do front: a rota do consumidor é HTTPS, o HTTP é o que o front fala
com o plano.

## 3. O que foi corrigido, arquivo por arquivo

| Arquivo | O que mudou |
|---|---|
| `AGENTS.md` | a passagem "caso extremo / sem `Containerfile`" passa a dizer `Containerfile` + compose desde a **S4b2-B**, TLS no front desde a **S4b2-E**, com a URL do consumidor; a "lacuna aberta (S4b1-E)" passa a registro **fechado** com o commit `a64b8414`; o cabeçalho da seção ganha a data da medição (2026-10-31). **A regra** — "os testes dos emuladores não rodam no `.venv` do gerador", e o `pytest` do `k8s-sim` rodando a partir de `emulators/k8s-sim` — fica **intacta**. |
| `deploy/synthetic-clouds/integration/README.md` | o bullet "O que ele **não** faz" deixa de dizer que o TLS é o restante da S4b2 e passa a dizer o que o script faz (garantir o caminho: alias, SAN, front) e o que ele não faz (apontar o consumidor, que é configuração do CloudPilot, e escrever a rota, que está no `nginx.conf`); a URL do consumidor entra no arquivo; a data/revisão do cabeçalho vai para 2026-10-31 / `e47c5fb8`. |
| `docs/k8s-sim-opencost-contract.md` | o bloco "Atualizado em 2026-10-30 pela S4b2-C" é **preservado** como registro datado e recebe uma **retificação datada** (S4b3-F) que aponta o TLS fechado na S4b2-E e a URL do consumidor; o título passa a listar as fases que o documento cobre (S4b2-E e S4b3-F). O §2.1 e o §9 já estavam corretos e não foram tocados. |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | a linha 23 da tabela de deployment passa a trazer a **URL do consumidor** junto do upstream, e o cabeçalho vai para 2026-10-31 / `e47c5fb8`. |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | a linha da entrega da fase. |
| `docs/regression/mapa-impacto-s4b3f.md` | este mapa. |

## 4. Lacunas declaradas (o que esta fase **não** resolve)

1. **`scripts/synthetic-clouds/up.ps1` não sobe o plano Kubernetes** — dívida **real**, mantida. O
   `k8s-sim` entra pelo `ensure-cloudpilot.ps1`; a assimetria está escrita, não escondida.
2. **O botão "Verificar Conexão" da UI do CloudPilot continua quebrado** — defeito
   **pré-existente** do CloudPilot (`opencost.py:47`, `kubecost.py:44`); fora da allowlist e fora do
   escopo.
3. **O plano Kubernetes segue sem hostname de nuvem real para imitar** — por desenho: o nome é do
   front, em `.test`.
4. **O restante da S4b2 continua aberto**: API server do Kubernetes, Prometheus, Kubecost, UI e
   migration. Esta fase não mexe nele — o TLS era uma peça desse conjunto, e só ele estava fechado.
5. **`docs/k8s-sim-opencost-contract.en.md`** — a gêmea em inglês continua **não existindo**; a
   pendência é da fase S4b1 e segue declarada no §9 do próprio documento.
6. **Os READMEs da raiz e o `deploy/synthetic-clouds/README.md` já estavam corretos** desde a
   S4b3-E (`6765522b`) — eles não estão na allowlist e não precisavam de nada.
7. **A reconciliação de billing do OpenCost** — os números do `k8s-sim` são sintéticos e não
   reconciliam com uma linha de billing (o contrato declara isso no §6 e no §9).
8. **A suíte do gerador não roda nesta fase**: ela não toca nenhuma linha de código — nem do
   gerador, nem dos emuladores, nem do CloudPilot. A última medição é a da revisão `aee05eb9`
   (**1111 passed · 20 skipped**), registrada no `docs/ESTADO.md` — as revisões seguintes são
   documentais.

## 5. Verificação

```powershell
# o AGENTS.md não afirma mais "sem Containerfile" nem "caso extremo"
git grep -n "sem Containerfile\|no Containerfile\|caso extremo" -- AGENTS.md
# -> nenhum match (exit 1)

# a lacuna do id nativo não é mais declarada aberta no AGENTS.md
git grep -n "Lacuna aberta em 2026-10-29" -- AGENTS.md
# -> nenhum match (exit 1)

# a URL do consumidor está nos quatro documentos
git grep -c "https://opencost.synthetic-clouds.test" -- AGENTS.md deploy/synthetic-clouds/integration/README.md docs/k8s-sim-opencost-contract.md docs/INTEGRACAO-CLOUDPILOT-TLS.md
# -> AGENTS.md:1
#    deploy/synthetic-clouds/integration/README.md:1
#    docs/INTEGRACAO-CLOUDPILOT-TLS.md:5
#    docs/k8s-sim-opencost-contract.md:4
#    (exit 0)

# nenhum dos três docs afirma que o TLS do plano Kubernetes é o restante da S4b2
git grep -n "restante da S4b2\|is not registered\|not registered" -- deploy/synthetic-clouds/integration/README.md docs/k8s-sim-opencost-contract.md docs/INTEGRACAO-CLOUDPILOT-TLS.md
# -> docs/k8s-sim-opencost-contract.md:42:  migration — o restante da S4b2. Detalhe no
#    docs/k8s-sim-opencost-contract.md:56:  restante da S4b2 (API server do Kubernetes, Prometheus, Kubecost, UI e migration) e um defeito
#    (exit 0)

# integridade
git diff --check
# -> vazio (exit 0)

git status --porcelain
# -> vazio (exit 0)
```

### 5.1 Os dois matches que sobram — e por que eles não são a falsehood

O grep acima **não** sai vazio, e isso é o resultado **real**, não um resíduo esquecido. Os dois
matches estão no contrato e nenhum dos dois afirma que o TLS está pendente:

| Linha | O que é | Por que fica |
|---|---|---|
| `docs/k8s-sim-opencost-contract.md:42` | o **registro datado** da S4b2-C (2026-10-30): o que ainda faltava *naquele* dia | é o histórico da fase, e a data é a informação que o torna verdadeiro. A **retificação datada** desta fase vem logo abaixo, dizendo que o TLS fechou na S4b2-E. Apagar a linha seria reescrever o histórico — o que o próprio repositório não faz (§4 do `mapa-impacto-s4b3e.md`) |
| `docs/k8s-sim-opencost-contract.md:56` | o bloco da **S4b2-E**: "o que continua aberto é o restante da S4b2 (**API server do Kubernetes, Prometheus, Kubecost, UI e migration**)" | é **verdade hoje**: o TLS não está nessa lista. A frase enumera o que segue aberto, e o TLS não está no que segue aberto |

A afirmação que a fase apaga é a do `integration/README.md` (L141-143 antes da mudança): "TLS para o
plano Kubernetes é o restante da S4b2" — que **era** falsa e **não** tinha data que a tornasse
verdadeira. Ela saiu.

**Como o `git status` fica vazio com dois commits.** A linha da entrega no `docs/ESTADO.md` nomeia o
commit que entrega a fase, e esse hash só existe depois do commit — como nas **oito** fases
anteriores (S4b2-C, S4b2-D, S4b2-E, S4b3-A, S4b3-B, S4b3-C, S4b3-D, S4b3-E), o registro do estado
vai em um commit próprio, logo depois do da fase. Os dois commits são em inglês e só tocam a
allowlist.
