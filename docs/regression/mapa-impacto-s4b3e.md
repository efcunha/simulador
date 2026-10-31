# Mapa de impacto — Fase S4b3-E (a dívida documental que não existia é apagada, e as URLs do `k8s-sim` passam a ser as do front TLS)

**Data:** 2026-10-31 · **Revisão-base:** `aee05eb9` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `README.md`, `README.en.md`, `docs/regression/mapa-impacto-s4b3d.md`,
`docs/DECISOES-PENDENTES.md`, `docs/DECISOES-PENDENTES.en.md`,
`deploy/synthetic-clouds/README.md`, `deploy/synthetic-clouds/.env.example`,
`docs/ESTADO.md`, `docs/ESTADO.en.md`, este mapa.
**Fora do escopo:** `AGENTS.md`, `emulators/**`, `deploy/synthetic-clouds/compose.*.yaml`,
`deploy/synthetic-clouds/integration/**`, `deploy/synthetic-clouds/tls-front/**`, `specs/**`,
`docs/NAO-COMPROVADOS*` (gerado), `docs/AGENDAMENTO.md`, `docs/AGENDAMENTO.en.md`,
`tools/**`, `scripts/**` e o código do `C:\Projetos\cloudpilot-deploy`.

**Por que esta fase existe.** A S4b3-D corrigiu o `docs/AGENDAMENTO.en.md` e, no mesmo fôlego,
**escreveu uma dívida que não existia**: a de que o `docs/AGENDAMENTO.md` (o gêmeo em português)
continuava desatualizado — "11 dias", ledger até `2026-10-26`, tarefa não registrada. Não
continuava: a **S4b3-C** (`77a6a03a`) já o tinha corrigido. A dívida foi escrita por **dedução**
(o EN estava errado, então o PT também estaria), e dedução não é leitura. A segunda metade da
fase fecha as **URLs antigas do `k8s-sim`** — o `http://k8s-sim:8089` ainda era declarado como a
URL do consumidor em três lugares, embora o **front TLS** o publique desde a S4b2-E sob o nome
próprio `opencost.synthetic-clouds.test`.

**Nenhuma linha de código, de container, de tarefa agendada ou de configuração do CloudPilot foi
tocada.** Esta fase é documental, do começo ao fim.

## 1. O que muda

| | Antes (leitura de 2026-10-31, revisão `aee05eb9`) | Depois |
|---|---|---|
| **`docs/AGENDAMENTO.md` (PT)** | registrado como **desatualizado** em 4 pontos (dois READMEs + mapa S4b3-D §7.1 + §3) | registrado como **correto** — a S4b3-C já o tinha corrigido; a dívida **não existia** |
| **Prova da dívida falsa** | nenhuma — a afirmação não tinha evidência | `git diff 77a6a03a HEAD -- docs/AGENDAMENTO.md` → **vazio** (exit 0) |
| **URL do consumidor do `k8s-sim`** | `http://k8s-sim:8089` (em 4 pontos do deploy) | **`https://opencost.synthetic-clouds.test`** (front TLS, desde a S4b2-E) |
| **`http://k8s-sim:8089`** | apresentado como a URL **do consumidor** | apresentado só como o **upstream do front** — que é o que ele é |
| **Frase do `Containerfile`** | "`k8s-sim` não tem Containerfile nem serviço de compose" (falsa desde a S4b2-B) | "`k8s-sim` **tem** `Containerfile` e serviço de compose desde a S4b2-B" |
| **Bloco "Sem TLS"** | "o TLS para este plano é o restante da S4b2" (falso desde a S4b2-E) | "**TLS desde a S4b2-E**", com o hostname próprio e o SAN na folha |
| **Histórico** | a mensagem de `dadba889` continha a afirmação falsa | **preservada** — o histórico não se reescreve; o registro falso é corrigido nos arquivos vivos |

## 2. A dívida que não existia

### 2.1 O que a S4b3-D escreveu

Em três arquivos, a S4b3-D registrou que o `docs/AGENDAMENTO.md` (PT) continuava desatualizado:

| Arquivo | O que dizia |
|---|---|
| `README.md` | "…**deixa um da mesma espécie**: o `docs/AGENDAMENTO.md` (o gêmeo em português) continua afirmando que a tarefa não está registrada e que o ledger para em `2026-10-26` — ele **não** está na allowlist desta fase, então o texto não foi corrigido aqui." |
| `README.en.md` | "…**leaves one of the same kind**: `docs/AGENDAMENTO.md` (the Portuguese twin) still says the task is not registered and that the ledger stops at `2026-10-26` — it is **not** in this phase's allowlist, so the text was not corrected here." |
| `docs/regression/mapa-impacto-s4b3d.md` §7.1 | "**`docs/AGENDAMENTO.md` (a versão em português) continua desatualizado.** Ele ainda diz '11 dias', ledger até `2026-10-26` e tarefa não registrada." |

O raciocínio era: o gêmeo EN (`docs/AGENDAMENTO.en.md`) **estava** errado, logo o PT também
estaria. A segunda premissa nunca foi testada.

### 2.2 A prova: o git

```powershell
git diff 77a6a03a HEAD -- docs/AGENDAMENTO.md
# -> vazio (exit 0)

git grep -n "11 dias\|não registrada\|not registered" -- docs/AGENDAMENTO.md
# -> nenhum match (exit 1)
```

`77a6a03a` é a **S4b3-C** — a fase em que o `docs/AGENDAMENTO.md` foi corrigido. O diff contra
`HEAD` sai **vazio**: desde aquela revisão, o arquivo PT **não mudou uma linha**. A frase
"11 dias" / "tarefa não registrada" **não está no arquivo** — a dívida foi escrita contra um
texto que o repositório já não tinha.

### 2.3 O texto real do PT

O bloco "Estado desta instalação" do `docs/AGENDAMENTO.md` (L289-326) diz:

| O que a dívida afirmava | O que o arquivo diz |
|---|---|
| "11 dias" | **16 dias** — de `2026-10-16` a `2026-10-31` |
| ledger até `2026-10-26` | ledger **em dia**, até `2026-10-31` |
| tarefa não registrada | tarefa **registrada** (próxima execução `2026-11-01T12:00:00`, disparo no logon, `StartWhenAvailable=true`) |
| — | `Último Resultado: 0` no disparo de `2026-10-31 13:06:47` |

**O `docs/AGENDAMENTO.md` estava — e está — fora da allowlist desta fase, e mesmo assim não
precisava de correção nenhuma.** A allowlist nunca foi o problema; a premissa é que era.

## 3. As URLs do `k8s-sim` — o mapa

A fonte canônica é a §3 do [mapa da S4b2-E](mapa-impacto-s4b2e.md) (rede, alias e URL). O
`opencost.synthetic-clouds.test` é o **nome do front**, não um hostname de nuvem — o OpenCost é
um contrato, não um serviço de nuvem, e inventar um nome sequestraria o nome de alguém (como o
`sts.*`).

| Contexto | URL | Onde está |
|---|---|---|
| **Consumidor** (backend do CloudPilot) | **`https://opencost.synthetic-clouds.test`** | `provider_endpoint` do `opencost`; SAN na folha do front (S4b2-E) |
| **Front → plano** (upstream, **na rede**) | `http://k8s-sim:8089` | `tls-front/nginx.conf` (`upstream k8s_opencost { server k8s-sim:8089; }`) |
| **Operador** (no host) | `http://localhost:8089/healthz` | porta `${K8S_SIM_PORT:-8089}` |

**O alias `k8s-sim:8089` continua existindo, e é por isso que ele não pode ser removido**: ele é
o **upstream** do front. O nginx resolve os upstreams no *startup* — se `k8s-sim` não existisse
quando o front sobe, o front não sobe. Apagar a ocorrência do endereço do documento de deploy
**não** apagaria a peça: apagaria o único lugar onde o leitor descobre **qual** peça é a
consumidora e qual é o upstream.

**Consequência na verificação.** O critério "o grep de `http://k8s-sim:8089` nos dois arquivos de
deploy sai vazio" **não** é satisfeita — e não deve ser. A forma correta do critério é sobre a
**URL do consumidor**, e ela sai vazia:

```powershell
git grep -n "K8S_SIM_URL=http://k8s-sim:8089" -- deploy/synthetic-clouds/README.md deploy/synthetic-clouds/.env.example
# -> nenhum match (exit 1)
```

O inventário da ocorrência, antes e depois:

| | Baseline (`aee05eb9`) | Depois |
|---|---|---|
| `.env.example` | 1 — `# K8S_SIM_URL=http://k8s-sim:8089` (**consumidor**) | **0** |
| `deploy/synthetic-clouds/README.md` | 3 — duas como **consumidor**, uma como URL do backend | **3 — todas como upstream do front**, nenhuma como consumidor |

## 4. O que foi corrigido, arquivo por arquivo

| Arquivo | Correção |
|---|---|
| `README.md` | o bloco "Débitos desta frente" deixa de afirmar que o `docs/AGENDAMENTO.md` (PT) está desatualizado e passa a dizer a verdade (a S4b3-C já o corrigiu) |
| `README.en.md` | idem, em inglês — "The debt S4b3-D wrote on this file … **never existed**" |
| `docs/regression/mapa-impacto-s4b3d.md` | §7.1 reescrito (a dívida registrada ali não existia); §3 e o cabeçalho apontam para esta fase, sem reescrever o registro histórico das tabelas §1/§3 |
| `deploy/synthetic-clouds/README.md` | URL do consumidor → `https://opencost.synthetic-clouds.test`; tabela de URLs com as **três** camadas (consumidor / upstream / operador); bloco "**Sem TLS.**" → "**TLS desde a S4b2-E**"; bloco do `.env` Kubernetes |
| `deploy/synthetic-clouds/.env.example` | `K8S_SIM_URL` documentado como `https://opencost.synthetic-clouds.test`, com a nota de que o alias `k8s-sim:8089` continua sendo o upstream do front |
| `docs/DECISOES-PENDENTES.md` | a linha "emuladores" da tabela de baseline: o `k8s-sim` **tem** `Containerfile` e serviço de compose desde a S4b2-B, e é publicado por TLS desde a S4b2-E |
| `docs/DECISOES-PENDENTES.en.md` | idem, em inglês |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | linha da entrega na tabela "Entregas registradas", linha de "Última atualização" e a seção da fase no fim do arquivo |

**O que NÃO foi reescrito.** As tabelas §1/§3 do `mapa-impacto-s4b3d.md` e as seções datadas
das fases anteriores no `docs/ESTADO.md` citam o texto antigo do `docs/AGENDAMENTO.en.md`
("11 days", "not registered"). Elas são **registros históricos** — documentam o que o documento
EN dizia **antes** da S4b3-D — e são preservados. Só a afirmação sobre o **PT** foi corrigida.

**A mensagem de `dadba889`** (o commit `docs(estado): record the S4b3-D delivery`) contém a
afirmação falsa. **Não há amend, nem reescrita de histórico.** O registro falso é corrigido nos
arquivos vivos e a nota de que ele existiu fica escrita neste mapa e no `docs/ESTADO.md`.

## 5. O que a fase entregou, em uma linha

**A dívida que a S4b3-D deixou escrita contra o `docs/AGENDAMENTO.md` (PT) não existia — o
arquivo já estava correto desde a S4b3-C, e o git prova; e o `k8s-sim` é consumido em
`https://opencost.synthetic-clouds.test`, com o alias `k8s-sim:8089` corretamente identificado
como o upstream do front.**

## 6. Lacunas declaradas (o que esta fase **não** resolve)

1. **`AGENTS.md` ainda descreve o `k8s-sim` como "o caso extremo: sem `Containerfile`"** (L188-189)
   — falso desde a S4b2-B. O arquivo está **proibido de edição** nesta fase; fica como **nota ao
   usuário**, para uma fase que o tenha na allowlist.
2. **`deploy/synthetic-clouds/integration/README.md` (L141-143)** ainda diz: "Não publica o
   `k8s-sim` por hostname real nem por TLS: o alcance é o alias de rede `k8s-sim` na bridge, em
   `http://k8s-sim:8089` (HTTP puro). TLS para o plano Kubernetes é o restante da S4b2." — falso
   desde a S4b2-E. Fora da allowlist.
3. **`docs/k8s-sim-opencost-contract.md` (L37-43)** carrega o bloco "Atualizado em 2026-10-30 pela
   S4b2-C", que diz que a URL `http://k8s-sim:8089` "passou a resolver de dentro do backend do
   CloudPilot" e que "o que ainda falta é **TLS** … o restante da S4b2" — a primeira afirmação é
   superada (a URL do consumidor é HTTPS desde a S4b2-E) e a segunda está **falsa** desde a
   S4b2-E. O restante do documento (§2.1, a tabela de URLs e a §9) está **correto**. Fora da
   allowlist.
4. **`docs/INTEGRACAO-CLOUDPILOT-TLS.md` (L23)** descreve o `k8s-sim` como "contrato **OpenCost**
   em `http://k8s-sim:8089` (HTTP puro, atrás do front TLS)" — não está errado (é o upstream, e
   está atrás do front), mas não dá a URL do consumidor. Fora da allowlist.
5. **O plano Kubernetes segue sem hostname de nuvem real para imitar** — dívida **real**, mantida
   nos dois READMEs. Não é dívida do PT e não foi tocada.
6. **`scripts/synthetic-clouds/up.ps1` não sobe o plano Kubernetes** — dívida **real**, mantida
   nos dois READMEs (confirmado: nenhum match de `k8s` no arquivo).
7. **O botão "Verificar Conexão" da UI do CloudPilot continua quebrado** — defeito **pré-existente**
   do CloudPilot (`opencost.py:47`, `kubecost.py:44`); fora da allowlist e fora do escopo.
8. **A árvore FOCUS/S3 do `aws-sim` (2026-01 → 2026-04) não está no bucket** e a **tabela CUD do
   BigQuery diverge** (esperado 3, veio 9) — débitos herdados, fora do escopo.
9. **A `.env` local desta instalação não precisa de mudança** (`K8S_SIM_PORT=8089`): a URL do
   consumidor é configuração do **CloudPilot**, não do compose.

## 7. Verificação

```powershell
# a dívida do PT não existia: o PT não mudou desde a S4b3-C
git diff 77a6a03a HEAD -- docs/AGENDAMENTO.md
# -> vazio (exit 0)

git grep -n "11 dias\|não registrada\|not registered" -- docs/AGENDAMENTO.md
# -> nenhum match (exit 1)

# a URL do consumidor do k8s-sim não é mais a antiga
git grep -n "K8S_SIM_URL=http://k8s-sim:8089" -- deploy/synthetic-clouds/README.md deploy/synthetic-clouds/.env.example
# -> nenhum match (exit 1)

# a frase do Containerfile foi corrigida nos dois DECISOES-PENDENTES
git grep -n "sem Containerfile\|no Containerfile" -- docs/DECISOES-PENDENTES.md docs/DECISOES-PENDENTES.en.md
# -> nenhum match (exit 1)

# integridade
git diff --check
# -> vazio (exit 0)

git status --porcelain
# -> vazio (exit 0)
```

**A fase não roda a suíte do gerador** (`pytest tools\synthetic_clouds\tests`): ela não toca
nenhuma linha de código — nem do gerador, nem dos emuladores, nem do CloudPilot. A última
medição da suíte é a da revisão `aee05eb9` (**1111 passed · 20 skipped**), registrada no
`docs/ESTADO.md`.
