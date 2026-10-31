# Mapa de impacto — Fase S4b2-C (o `k8s-sim` na rede do CloudPilot: alias, URL e docs)

**Data:** 2026-10-30 · **Revisão-base:** `9ccbc71c` (branch `feat/p76-security-posture-gcp-azure`) ·
**Escopo:** `deploy/synthetic-clouds/integration/**`, `deploy/synthetic-clouds/.env.example`,
`docs/**`, `README.md`, `README.en.md` ·
**Fora do escopo:** `emulators/**` (código, fixture, testes), `deploy/synthetic-clouds/compose.k8s.yaml`
(entregue pela S4b2-B — **não** editado), `deploy/synthetic-clouds/compose.yaml`,
`compose.tls-front.yaml`, `scripts/**`, `specs/**`, `tools/**`, `AGENTS.md`,
`docs/NAO-COMPROVADOS*` (gerado) e `C:\Projetos\cloudpilot-deploy/**`.

**Por que esta fase existe.** A S4b2-A/B entregaram o `Containerfile` do `k8s-sim` e o
compose `compose.k8s.yaml`; o container sobe healthy em 8089. Mas o `k8s-sim` ficava na
`network `synthetic-clouds_synthclouds_net`` — a rede dos simuladores — enquanto o backend do
CloudPilot vive na `cloudpilot-deploy_cloudpilot_net`. **Duas redes, um nome, nenhum caminho.**
Do ponto de vista do backend, `http://k8s-sim:8089` não existia: o nome não resolvia e o
endpoint do contrato OpenCost era inalcançável.

## 1. O que muda

| | Antes (S4b2-B) | Depois (S4b2-C) |
|---|---|---|
| **Rede** | o `k8s-sim` só na `synthetic-clouds_synthclouds_net` (compartilhada pelos planos de nuvem) | o `k8s-sim` **também** na `cloudpilot-deploy_cloudpilot_net` (a bridge do CloudPilot) |
| **Alias** | nenhum alias `k8s-sim` na bridge | alias **`k8s-sim`** na bridge, criado pelo `ensure-cloudpilot.ps1` |
| **URL interna** | não existia | **`http://k8s-sim:8089`** — resolvida pelo backend do CloudPilot pelo nome |
| **Quem sobe o container** | mão (`podman compose -f compose.k8s.yaml up -d`) | o **`ensure-cloudpilot.ps1`**, idempotentemente, a partir do compose e **sem rebuild** |
| **Como o CloudPilot chega lá** | não chegava | pelo alias da bridge — o mesmo mecanismo que já publica `gcp-sim`, `aws-sim`, `s3mock` e `bigquery-emulator` |
| **Prova** | nenhuma | o `-Smoke` do `ensure` roda o probe **de dentro do backend** |

**Nada disso muda o contrato HTTP.** O `k8s-sim` continua servindo exatamente o que o
`docs/k8s-sim-opencost-contract.md` descreve (`/allocation/compute`, `/clusterInfo`,
`/healthz`); o que muda é **o caminho de rede** até ele. Nenhum arquivo de `emulators/**`
foi tocado, e o `compose.k8s.yaml` não foi alterado.

## 2. Rede, alias e URL — o mapa

| Peça | Valor | Onde está |
|---|---|---|
| Container | `synthetic-clouds-k8s-sim-1` | `compose.k8s.yaml` (serviço `k8s-sim`, projeto `synthetic-clouds`) |
| Rede do simulador | `synthetic-clouds_synthclouds_net` (**external**) + `synthetic-clouds_synthclouds_k8s` (dedicada) | `compose.k8s.yaml` |
| Rede do CloudPilot | `cloudpilot-deploy_cloudpilot_net` | criada pela stack do CloudPilot (`docker-compose.local.yml`) |
| Alias na bridge | `k8s-sim` | criado pelo `ensure-cloudpilot.ps1` (`Ensure-NetworkAliases`) |
| URL interna | `http://k8s-sim:8089` | o que o backend do CloudPilot usa |
| URL no host | `http://localhost:8089/healthz` | só para o operador; a porta do host é `${K8S_SIM_PORT:-8089}` |
| Porta do container | `8089` (fixa) | `compose.k8s.yaml` fixa `K8S_SIM_PORT: "8089"` no ambiente do serviço |

**A rede compartilhada é `external: true` com `name:` explícito.** Isso é o que impede que
o teardown do plano Kubernetes alcance a rede dos outros planos — o `podman compose down`
tenta remover as redes que o compose considera próprias, e o podman recusa
("Resource is still in use") quando a rede tem endpoints vivos. Declarar `external` resolve
o problema na origem.

## 3. O mecanismo: `ensure-cloudpilot.ps1`

O script é o **único** dono do vínculo entre o simulador e o CloudPilot. A fase acrescenta
três coisas, todas no mesmo lugar onde as outras plataformas já são tratadas:

1. **`Ensure-K8sSimContainer`** — se o container não existe, ele é criado a partir de
   `compose.k8s.yaml` com `--no-deps --no-build` (a imagem `localhost/k8s-sim:latest` é
   artefato da S4b2-B; esta fase **não** reconstrói). Se já existe, ele é apenas
   reiniciado e esperado como healthy.
2. **`Ensure-NetworkAliases -Container $K8sSim -Network $CpNet -Aliases @('k8s-sim')`** —
   a mesma função que já publica `gcp-sim`, `aws-sim`, `s3mock` e `bigquery-emulator`.
   Ela reconecta **só** quando o alias falta (o `disconnect`/`connect` é o mecanismo
   idempotente já usado pelos outros).
3. **`Test-K8sSimFromBackend`** — o probe do `-Smoke`: roda **de dentro do
   `cloudpilot_backend`**, porque é de lá que o alias importa.

**O `cold-start.ps1` não ganhou um passo novo para o `k8s-sim`, e essa é a decisão.** O
plano Kubernetes é criado pelo `ensure-cloudpilot.ps1`, que o `cold-start.ps1` já encadeia
por último — de modo que o container existe antes de o alias ser criado, e o alias existe
antes de o backend precisar dele. Um `k8s-up.ps1` separado duplicaria essa lógica em dois
lugares, e a duplicação é exatamente o que a allowlist proíbe criar. O `cold-start.ps1`
ganhou o `k8s-sim` no **resumo final** de endpoints.

## 4. O teste da fase

O teste é o smoke do `ensure` mais o probe do backend, com saída real nos dois lados.

**Antes** (o container nem existia, e o nome não resolvia na bridge do CloudPilot):

```
$ podman exec cloudpilot_backend python -c "import urllib.request; print(urllib.request.urlopen('http://k8s-sim:8089/healthz', timeout=3).status)"
urllib.error.URLError: <urlopen error [Errno -2] Name or service not known>
exit=1
```

**Depois:**

```
$ podman exec cloudpilot_backend python -c "import urllib.request; print(urllib.request.urlopen('http://k8s-sim:8089/healthz', timeout=3).status)"
200
$ podman exec cloudpilot_backend python -c "import urllib.request; print(urllib.request.urlopen('http://k8s-sim:8089/clusterInfo?filter=cluster:%22TEMP-aks_cluster-0025%22', timeout=3).status)"
200
```

O `/clusterInfo` não é decoração: ele leva um cluster **real** do estate
(`TEMP-aks_cluster-0025`, o primeiro do fixture `k8s_sim/fixtures/clusters.json`) e prova
que quem respondeu foi o `k8s-sim` e não um serviço qualquer com o mesmo nome.

## 5. Documentos afetados

| Documento | O que mudou |
|---|---|
| `deploy/synthetic-clouds/README.md` | o `k8s-sim` sai de "fora do compose" e passa a ter compose, rede, alias e URL |
| `deploy/synthetic-clouds/integration/README.md` | o `ensure` passa a cobrir o plano Kubernetes; o `-Smoke` ganha o probe |
| `docs/INTEGRACAO-CLOUDPILOT-TLS.md` | a URL interna `http://k8s-sim:8089` e a nota de que **não** há front TLS para ela |
| `docs/k8s-sim-opencost-contract.md` | §9: o item "sem Dockerfile, compose, rede, URL" é fechado; §2: a URL |
| `docs/ESTADO.md` / `docs/ESTADO.en.md` | linha da entrega e a seção da S4b2-C |
| `README.md` / `README.en.md` | data/revisão, a linha do emulador e o débito |
| `deploy/synthetic-clouds/.env.example` | `K8S_SIM_PORT=8089` e a URL, comentado |
| `docs/regression/mapa-impacto-s4b2c.md` | este mapa |

## 6. Débitos e lacunas declaradas

- **`docs/DECISOES-PENDENTES.md` (e a gêmea `.en.md`) dizem que o `k8s-sim` "não tem
  Containerfile nem serviço de compose".** A frase virou falsa na S4b2-B e esta fase não
  pode corrigi-la: o arquivo está **fora da allowlist**. Fica como débitos nomeado.
- **`AGENTS.md` diz que o `k8s-sim` é "o caso extremo: sem `Containerfile`".** Também ficou
  falso na S4b2-B, e o `AGENTS.md` está explicitamente proibido de edição nesta fase.
- **`scripts/synthetic-clouds/up.ps1` não sobe o plano Kubernetes.** Ele é dono dos três
  planos de nuvem e está **fora da allowlist**; o `k8s-sim` entra pelo `ensure`. É uma
  assimetria real entre os planos, e ela está escrita em vez de escondida.
- **A checagem de conexão AWS do `-Smoke` falha neste host**, e a falha é **pré-existente** —
  ver §7.

## 7. A checagem AWS que falha: pré-existente, e por quê

O `-Smoke` do `ensure` roda "Verificar Conexão" nas três contas. Em 2026-10-30 a conta AWS
respondeu `failed (The AWS access key ID provided is invalid or has been deactivated.)`,
enquanto GCP e Azure responderam `connected`.

**Não é regressão desta fase.** Medido: o script **original** do `HEAD` (`9ccbc71c`), rodado
num worktree descartável (`git worktree add --detach`), produz **a mesma linha**:

```
[FAIL] connection check aws = failed (The AWS access key ID provided is invalid or has been deactivated.)
[INFO] connection check gcp = connected
[INFO] connection check azure = connected
```

**Causa raiz medida — REVISÃO DATADA DE 2026-10-30 (S4b2-D).** A leitura original desta
seção afirmava que *"as access keys do estate derivam do perfil"*. **Isso é falso**, e o
`-Smoke` não falhava por causa do perfil: o `InvalidClientTokenId` vinha do **AWS real**,
não do emulador.

**Prova de que o erro vinha da AWS real.** O log do backend mostra o `botocore` resolvendo o
endpoint por conta própria — `Looking for endpoint for sts via: environment_service /
environment_global / config_service / config_global / No configured endpoint found` — e a
chamada seguindo para `https://sts.us-east-1.amazonaws.com`. A **mesma** credencial
decifrada, testada contra os dois destinos: `http://aws-sim:8086` → **200**, conta
`911368690069`; AWS real → `InvalidClientTokenId`, a mensagem exata gravada em
`cloud_accounts.connection_error`.

**Prova de que o perfil não é a identidade.** O `aws-sim` **não valida** a chave que chega:
o `GetCallerIdentity` decodifica o formato `ASIA<12 dígitos>SYNT` e, sem chave
decodificável, **cai na primeira conta do estate**. E o id de conta deriva de
`aws_account_id(seed, "acct-NN")` — seed e índice, **não** o perfil. Medido com o mesmo
seed 123: `small` e `medium` produzem os **mesmos três** ids (`911368690069`,
`969191373337`, `995394606788`). O perfil muda o **volume**, não a identidade: 237 → 1.110
recursos AWS e 37.922 → 474.390 linhas de faturamento.

**A causa raiz real: o override de endpoint por conta estava inerte.** A conta tem
`cur_config.endpoint_overrides.sts = http://aws-sim:8086` — o caminho que o front TLS
deliberadamente **não** publica (um hijack de `sts.amazonaws.com` quebraria as contas AWS
reais que o mesmo CloudPilot consome). Esse override só é lido por um backend que tenha
`endpoint_overrides.py` e propague `sts_endpoint_url` ao validador — e a imagem em
execução **não tinha**: medido, o container não tinha
`app/services/providers/endpoint_overrides.py`, e `connection_check.py` e
`connection_validator.py` vinham sem `sts_endpoint_url`. O desvio contra o `HEAD` do repo
era de **3 arquivos ausentes + 15 diferentes** (de 742 `.py`). A imagem tinha sido
construída em **2026-10-27 17:11 UTC** (label `acd18722`), **antes** de `dbd66cca`
(2026-10-28 20:29), que introduziu o feature e **é** ancestral do `HEAD`.

**A correção (fase S4b2-D, medida).**

1. `.env` local com o **namespace do plano AWS** — `AWS_SIM_SEED=123` e
   `AWS_SIM_PROFILE=medium`. O `compose.aws.yaml` lê `${AWS_SIM_SEED:-123}` /
   `${AWS_SIM_PROFILE:-small}`, **não** os nomes genéricos `SEED`/`PROFILE` dos planos
   Azure/GCP; sem o par `AWS_SIM_*` o `aws-sim` cai no default `small` e serve um estate
   **diferente** do resto da pilha. O `compose.aws.yaml` **não** foi editado (fora da
   allowlist): o default `small` continua lá, e é o `.env` que fixa o perfil da
   instalação. `.env.example` agora **documenta** o par e o seu motivo.
2. `aws-sim` recriado pelo compose oficial → `PROFILE=medium`, `SEED=123`, healthy.
3. **Imagem do backend do CloudPilot reconstruída a partir do `HEAD`** (`3da29e76`) e os
   **5 containers Python recriados** — `podman cp` não servia: `pyproject.toml`/`uv.lock`
   também mudaram (597+/427−), então um patch de arquivos deixaria o `.venv` desalinhado.
   Resultado: `[PARITY] Code parity OK (742 .py files, host == 5 running container(s))`.
4. **Defeito colateral encontrado e corrigido na configuração local.** A reconstrução subiu
   um backend em **crash-loop**: `ModuleNotFoundError: No module named 'psycopg'`. Causa:
   `1299fa0d` afrouxou o pin do SQLAlchemy para `<2.2` e o lock resolveu **2.1.6**, que
   trocou o driver default de `postgresql://` para o **psycopg3** — e o lock só entrega
   `psycopg2-binary`. Como `scripts/compose-local.ps1:339` monta `LOCAL_DATABASE_URL_SYNC`
   **sem driver**, o container recebia a URL crua e o `alembic upgrade head` da entrypoint
   morria. Corrigido **só na configuração local** (`backend/.env.local`, git-ignored):
   `LOCAL_DATABASE_URL_SYNC=postgresql+psycopg2://…`, o mesmo valor que o arquivo já
   declarava em `DATABASE_URL_SYNC`. **O repo do CloudPilot não foi editado** — o defeito
   de dependência lá é dele e está declarado no registro da fase (`docs/ESTADO.md`,
   seção S4b2-D).
5. Credencial **re-mintada** na forma que o emulador decodifica —
   `ASIA<conta>SYNT` / `synthetic-secret-<conta>` — pela UI, com a conta de homologação.
   Assim o `GetCallerIdentity` devolve **exatamente** a conta declarada
   (`911368690069`), sem depender da queda para a primeira conta do estate.

**Efeito no critério de aceite:** `ensure-cloudpilot.ps1 -Smoke` sai com **0** e
`summary: integration OK (0 problems)`, com `connection check aws = connected`.

## 8. O que esta fase **não** faz

- Não toca `emulators/**`: nem o código, nem o fixture, nem os testes do `k8s-sim`.
- Não edita `compose.k8s.yaml` (entregue pela S4b2-B).
- Não reconstrói imagem: o `k8s-sim` sobe com `--no-build` sobre `localhost/k8s-sim:latest`.
- Não reinicia os outros emuladores nem o front TLS.
- Não publica o `k8s-sim` no **front TLS**: a URL é HTTP puro na bridge, sem hostname
  real e sem certificado. TLS para o plano Kubernetes é a **restante da S4b2**.
- Não roda a suíte canônica (`pytest tools\synthetic_clouds\tests`): a fase não toca código
  de produção. O `scripts/verify.ps1` **não existe** neste repositório.
