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

**Causa raiz medida.** O container `synthetic-clouds-aws-sim-1` está no ar com
`PROFILE=small` (`podman inspect … --format '{{range .Config.Env}}{{println .}}{{end}}'`),
enquanto o `.env` documentado da instalação diz `PROFILE=medium` (`SEED=123` nos dois). As
access keys do estate derivam do perfil: o `aws-sim` re-renderizado com outro perfil gera
**outro conjunto de chaves**, e a credencial guardada no CloudPilot — que aponta para o
estate `medium` — deixa de existir para o `aws-sim` atual. Daí o `InvalidClientTokenId`.

**Por que esta fase não corrige.** Recriar o `aws-sim` com o perfil correto é *restart dos
outros emuladores*, que a fase lista como **fora de escopo** e whose integrity is an
acceptance criterion ("os 7 containers dos outros planos e o front intactos"). E a
credencial mora em `C:\Projetos\cloudpilot-deploy`, **fora da allowlist**. A correção
cabe numa fase de deployment própria: recriar o `aws-sim` com o `.env` do diretório
(`podman compose -f compose.aws.yaml up -d`, a partir de `deploy/synthetic-clouds/`, onde o
`.env` é lido) e refazer a credencial da conta `f4b259ca-3a0d-49bb-ade9-bf75101317c8`.

**Efeito no critério de aceite:** `ensure-cloudpilot.ps1 -Smoke -SkipEstate` sai com **1**
(esse), e não com 0, por causa do item pré-existente acima. As medições **desta fase** — o
probe do `k8s-sim` por dentro do backend, o alias na bridge e o `network inspect` — estão
todas verdes.

## 8. O que esta fase **não** faz

- Não toca `emulators/**`: nem o código, nem o fixture, nem os testes do `k8s-sim`.
- Não edita `compose.k8s.yaml` (entregue pela S4b2-B).
- Não reconstrói imagem: o `k8s-sim` sobe com `--no-build` sobre `localhost/k8s-sim:latest`.
- Não reinicia os outros emuladores nem o front TLS.
- Não publica o `k8s-sim` no **front TLS**: a URL é HTTP puro na bridge, sem hostname
  real e sem certificado. TLS para o plano Kubernetes é a **restante da S4b2**.
- Não roda a suíte canônica (`pytest tools\synthetic_clouds\tests`): a fase não toca código
  de produção. O `scripts/verify.ps1` **não existe** neste repositório.
