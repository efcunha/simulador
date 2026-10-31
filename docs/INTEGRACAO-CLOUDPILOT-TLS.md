# Integração CloudPilot ↔ simulador sem código de simulador no CloudPilot

> Última atualização: **2026-10-31** (S4b3-F; revisão-base `e47c5fb8`). A decisão de 2026-10-28 que
> removeu o sequestro do `sts.*` continua valendo.

Este documento registra a configuração que faz o CloudPilot falar com o
simulador **pelos nomes e pelo TLS da nuvem real**. Nenhum código de ingestão do
CloudPilot conhece o simulador: ele constrói o cliente de produção e resolve o
hostname de produção. Quem se adapta é esta stack.

## O que é deployment (CloudPilot) e o que é simulador

| Lado | Arquivo | Papel |
|---|---|---|
| CloudPilot | `docker-compose.local.yml` | monta `./.local/tls/ca-bundle.pem` em `/certs` e define `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` e `HTTPLIB2_CA_CERTS` |
| CloudPilot | `C:\Projetos\cloudpilot-deploy\.local\tls\ca-bundle.pem` | bundle certifi + CA local (não versionado; reaplicado por `ensure-cloudpilot.ps1`) |
| Simulador | `emulators/azure-sim/tls/` | CA local e folhas TLS (git-ignored; geradas pelos scripts abaixo) |
| Simulador | `deploy/synthetic-clouds/compose.yaml` | `azure-sim` serve ARM/OAuth em **443 (TLS)** além de 8080 (API), com `net.ipv4.ip_unprivileged_port_start=0`; `azurite` é o backend de blob |
| Simulador | `deploy/synthetic-clouds/compose.gcp.yaml` | `bigquery-emulator` (9050/9060) e `gcp-sim` (REST 8085, gRPC 8087; plano SCC gRPC interno em 8088) |
| Simulador | `deploy/synthetic-clouds/compose.aws.yaml` | `s3mock` (9090) e `aws-sim` (8086) |
| Simulador | `deploy/synthetic-clouds/compose.tls-front.yaml` | front nginx para os **oito** hostnames servidos ao CloudPilot (os sete `*.googleapis.com` + o nome do plano Kubernetes) |
| Simulador | `deploy/synthetic-clouds/tls-front/nginx.conf` | roteia cada hostname para o emulador certo |
| Simulador | `deploy/synthetic-clouds/compose.k8s.yaml` | `k8s-sim` — contrato **OpenCost** em `http://k8s-sim:8089` (o **upstream** do front, HTTP puro); o **consumidor** usa **`https://opencost.synthetic-clouds.test`** |

Os cinco composes e a ordem de subida estão no quick-start
[`deploy/synthetic-clouds/README.md`](../deploy/synthetic-clouds/README.md). O front TLS
**não** é iniciado pelo `scripts/synthetic-clouds/up.ps1` — ele depende da rede do CloudPilot
e dos upstreams já anexados (ver [Ordem de subida](#ordem-de-subida)).

### O plano Kubernetes não tem hostname de nuvem — tem nome próprio

Todos os outros emuladores são alcançados por um **hostname real** (o do Cloud na nuvem) e,
quando o plano é GCP, pelo front TLS. O `k8s-sim` é a exceção: não existe hostname de nuvem
para ele imitar, então o front TLS o serve **sob um nome próprio**,
**`opencost.synthetic-clouds.test`** (decidido no checkpoint da S4b2-E). O sufixo `.test` é a
TLD reservada para testes (RFC 6761) — o nome **não resolve na internet pública**, e é por isso
que ele pode ser publicado na bridge do CloudPilot sem sequestrar o nome de ninguém.

O contrato OpenCost é falado por **HTTPS** nesse nome:

```
https://opencost.synthetic-clouds.test/healthz
https://opencost.synthetic-clouds.test/clusterInfo?filter=cluster:"<id nativo>"
https://opencost.synthetic-clouds.test/allocation/compute?window=...
```

**Desde a S4b2-G (2026-10-31) o mesmo nome fala também a API do Kubernetes** — o subconjunto que o
consumidor chama, e que vive no mesmo container e na mesma porta:

```
https://opencost.synthetic-clouds.test/api/v1/namespaces
https://opencost.synthetic-clouds.test/api/v1/pods
https://opencost.synthetic-clouds.test/api/v1/namespaces/<namespace>/pods
```

Não foi preciso nenhum hostname novo, nem certificado novo, nem mudança no `nginx.conf` (que está
**fora** da allowlist da fase): o front já encaminha `location /` para o upstream `k8s-sim:8089`, e
as rotas novas moram **dentro** desse encaminhamento. As rotas do plano Kubernetes pedem
`Authorization: Bearer <token>`; as do contrato OpenCost **não** pedem token — cada plano tem seu
contrato, e nenhum dos dois mudou.

A porta é a do front (**443**); o `k8s-sim` continua em `8089`, **atrás** do front. O alias de
rede `k8s-sim` continua existindo na bridge `cloudpilot-deploy_cloudpilot_net` — é ele que o
front usa como *upstream* (`upstream k8s_opencost { server k8s-sim:8089; }`) e é ele que o
probe do `ensure-cloudpilot.ps1` mede em HTTP para provar que o alias continua de pé.

O certificado: o nome entra na lista `$FrontAliases` do `ensure-cloudpilot.ps1`, que **reassina a
folha** do front (mesma CA, bundle do CloudPilot intocado) quando um alias roteado não está no
SAN. Rota e certificado continuam sendo um contrato só — o cliente verifica o nome que discou.

## Hostnames e destinos

Na rede `cloudpilot-deploy_cloudpilot_net`, **dez hostnames** são atendidos: dois por alias
de rede no próprio `azure-sim`, sete pelo front nginx e um pelo front nginx também — o nome
próprio do plano Kubernetes.

| Hostname | Serve | Implementação | O que o cliente chama |
|---|---|---|---|
| `management.azure.com` | `azure-sim` (TLS 443) | alias de rede no `azure-sim` | ARM (Cost Management, Resource Graph, Monitor, Defender, …) |
| `login.microsoftonline.com` | `azure-sim` (TLS 443) | alias de rede no `azure-sim` | OIDC discovery + token JWT (HS256, claims marcadas) |
| `bigquery.googleapis.com` | `bigquery-emulator:9050` | front nginx (`proxy_pass`) | REST do BigQuery (`insertAll`, queries da leitura de billing) |
| `oauth2.googleapis.com` | `gcp-sim:8085` | front nginx | `POST /token` |
| `cloudresourcemanager.googleapis.com` | `gcp-sim:8085` | front nginx | `GET /v1/projects` (o `googleapiclient` usa o discovery estático embutido) |
| `compute.googleapis.com` | `gcp-sim:8085` | front nginx | `GET /compute/v1/projects/<project>/global/firewalls` (check de postura) |
| `config.googleapis.com` | `gcp-sim:8085` | front nginx | `resourceDrifts.list` do Infrastructure Manager |
| `container.googleapis.com` | `gcp-sim:8085` | front nginx | `projects.locations.clusters.list` (GKE) |
| `securitycenter.googleapis.com` | `gcp-sim:8088` | front nginx com `grpc_pass` (TLS + HTTP/2) | `SecurityCenter/ListFindings` por gRPC |
| `opencost.synthetic-clouds.test` | `k8s-sim:8089` | front nginx (TLS) | contrato OpenCost: `/healthz`, `/clusterInfo`, `/allocation/compute` — e, desde a S4b2-G, a API do Kubernetes: `/api/v1/namespaces`, `/api/v1/pods`, `/api/v1/namespaces/{ns}/pods` |

Quatro detalhes que a tabela esconde:

* **O plano SCC é gRPC.** A biblioteca `google-cloud-securitycenter` registra os transports
  na ordem `("grpc", "grpc_asyncio", "rest")` e escolhe o **primeiro** quando o chamador não
  nomeia um; por isso o hostname recebe HTTP/2 no front (`listen 443 ssl http2`) e é
  encaminhado com `grpc_pass` para `gcp-sim:8088`. A porta 8088 **não é publicada no host**:
  o plano sobe no mesmo processo do `gcp-sim` (`GCP_SIM_SCC_GRPC_PORT`, padrão 8088 — ver
  `emulators/gcp-sim/gcp_sim/routers/scc.py`) e só o front a alcança, pela rede compartilhada.
* **`config` é Infra Manager, não Config Connector.** É a rota de `resourceDrifts`
  (`config.googleapis.com/v1/projects/<project>/locations/<location>/previews/<preview>/resourceDrifts`).
* **`compute`, `config` e `container` dividem o mesmo upstream REST** (`gcp-sim:8085`), como
  `oauth2` e `cloudresourcemanager`.
* **O plano Kubernetes não imita ninguém.** `opencost.synthetic-clouds.test` não é o hostname
  de nenhum serviço de nuvem real — é o nome do contrato OpenCost dentro do simulador, em uma
  TLD que não resolve na internet. O front o encaminha para o alias `k8s-sim:8089`, que
  continua sendo o endereço **interno** do plano.

`sts.amazonaws.com` e `sts.us-east-1.amazonaws.com` **não** são publicados nesta rede: o STS
resolve na AWS de verdade. Ver a seção "STS" abaixo.

### O upstream `aws-sim` mantido de propósito

O `nginx.conf` declara `upstream aws_sim { server aws-sim:8086; }` **sem nenhuma rota que o
use**. Isso é deliberado: o nginx resolve **todos** os upstreams no *startup* e sai com
`host not found in upstream` quando um deles não existe. Manter o upstream é o que mantém o
`aws-sim` como dependência dura do front — a ordem de subida passa a ser verificada pelo
próprio nginx, em vez de virar um erro silencioso na primeira chamada. Se o `aws-sim` for
removido do deployment, remova o upstream junto (e o `ensure-cloudpilot.ps1` deixa de
anexar o alias).

## STS: por que o simulador não sequestra o hostname

O `aws-sim` responde `GetCallerIdentity` com a primeira conta do estate
(`911368690069` no seed 123). Publicar `sts.amazonaws.com` para o front por
DNS fazia o validador do CloudPilot resolver **toda** conta AWS da rede —
inclusive as contas REAIS, com chaves válidas — contra o simulador. A guarda
anti-confused-deputy (`backend/app/services/providers/aws/connection_validator.py`)
então rejeitava a conexão com `reason=account_mismatch`, e o banner
"Credenciais Expiradas" aparecia para uma credencial perfeitamente válida.

A correção é de **2026-10-28** (commit `e461f572`): os aliases `sts.*` saíram do compose e
do script de integração, a rota que os proxiava saiu do nginx, e o STS real voltou a
resolver. A conta AWS do simulador precisa de um endpoint STS **por conta** — hoje
`cur_config.endpoint_url` cobre apenas S3 — e não de um sequestro global de hostname:
sequestrar `sts.*` quebra qualquer conta real que compartilhe a rede com o simulador.

## Certificados

A CA é gerada uma vez e **não deve ser regenerada** sem refazer o bundle do CloudPilot:

```powershell
.\.venv\Scripts\python.exe emulators\azure-sim\scripts\gen_dev_tls.py
.\.venv\Scripts\python.exe emulators\azure-sim\scripts\gen_cloud_front_tls.py
```

O primeiro script cria `ca.crt`/`ca.key` e a folha `server.crt` (hostnames Azure e nomes
diretos dos containers, usados pelos smoke checks; já embutida na imagem do `azure-sim`,
que copia `emulators/azure-sim` inteiro no build). O segundo assina com a MESMA CA a folha
`server-clouds.crt` usada pelo front: a lista padrão é a tabela de hostnames roteados mais
nomes que o front não publica hoje (`www`, `storage`, `s3`, `sts.*`) — nomes extras no SAN
não fazem mal, e o `ensure-cloudpilot.ps1` **reassina a folha** (com a mesma CA, sem tocar no
bundle) quando a lista de aliases roteados não está contida no SAN. A regra é: o cliente
verifica o nome que discou, então **rota e certificado são um contrato só**.

Desde a S4b2-E a folha do front carrega também o nome do plano Kubernetes
(`opencost.synthetic-clouds.test`), assinado pela mesma CA — 13 SANs na instalação atual. A
folha **não** é versionada: ela vive em `emulators/azure-sim/tls/` (git-ignored) e é
regerada/reassinada localmente.

O bundle do CloudPilot é `certifi/cacert.pem` do container + `ca.crt`, copiado para
`C:\Projetos\cloudpilot-deploy\.local\tls\ca-bundle.pem`. Se a CA mudar, o bundle precisa ser refeito
e os containers do CloudPilot recriados. As folhas podem ser regeradas sem tocar na CA —
mas o front precisa ser **reiniciado** para ler a folha nova (o nginx lê o certificado no
início do processo).

## Configuração de conta usada na validação

- Azure: `subscription_id` alinhado ao GUID que o estate stampa no
  `SubAccountId` (`azure_subscription_guid(seed=123, "sub-01")` =
  `61a34ffc-2128-56dd-b7ac-46c52a64fb77`). O valor anterior
  (`0de2e68d-…`) não correspondia a nenhuma assinatura do estate e fazia o
  `subscriptions.get` do "Verificar Conexão" responder 404.
- GCP: a credencial passou a ser um service account com chave RSA válida
  (`private_key` de verdade; antes era `synth:not-a-private-key`, que o
  `google-auth` não consegue assinar), `token_uri` =
  `https://oauth2.googleapis.com/token`. O campo `synthetic_endpoint` foi
  removido.
- Azure: `synthetic_endpoint` removido da credencial.
- AWS: `cur_config.endpoint_url` foi MANTIDO (decisão do operador). É um
  recurso genérico de S3-compatível (MinIO/LocalStack) já exposto no schema
  `cur_ingestion`; não é branch, credencial sintética nem override de SDK.

## Ordem de subida

A ordem completa é a do `cold-start.ps1` (um comando, depois de
`podman machine stop` ou reboot): **máquina podman → stack CloudPilot → planos de nuvem →
integração**. A integração é o que **anexa** os emuladores à rede do CloudPilot com os
aliases; sem ela o `tls-front` entra em crash-loop com
`host not found in upstream "bigquery-emulator:9050"`.

```powershell
# começo frio (ou reaplicação idempotente)
.\deploy\synthetic-clouds\integration\cold-start.ps1
```

Equivalente manual, na mesma ordem:

1. **CloudPilot** (cria a rede `cloudpilot-deploy_cloudpilot_net`):
   `pwsh -File C:\Projetos\cloudpilot-deploy\scripts\compose-local.ps1 -Action up`. Se o backend
   mudou, rode antes `-Action build -Services backend`.
2. **Três planos** do simulador: `pwsh -File scripts\synthetic-clouds\up.ps1`
   (Azure, GCP, AWS; ver o quick-start de `deploy/synthetic-clouds/`).
3. **Integração**: `deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1`. Ele anexa
   `azure-sim` com os dois aliases Azure, anexa o front com os sete hostnames `.googleapis.com`
   **e com o nome do plano Kubernetes** (`opencost.synthetic-clouds.test`) e anexa `gcp-sim`,
   `bigquery-emulator`, `aws-sim`, `s3mock` e **`k8s-sim`** com os nomes que
   o nginx — e o backend — resolvem. **O front é iniciado só depois dos aliases**: o nginx
   resolve os upstreams no *startup*, então subi-lo antes queima o timeout inteiro em restart
   loop (defeito medido em 2026-10-28, corrigido no `ensure-cloudpilot.ps1`).

   O **plano Kubernetes é criado aqui**, a partir de `compose.k8s.yaml` e **sem rebuild**
   (`--no-deps --no-build`), quando o container não existe — `scripts/synthetic-clouds/up.ps1`
   é dono dos três planos de nuvem e não sobe este. Por isso o `k8s-sim` já está no ar quando o
   alias é criado, e o alias já existe quando o backend precisa dele.

O `azure-sim` leva ~1–2 min para construir o estate (nesta instalação, `.env` com
`PROFILE=medium`, `SEED=123`, `WINDOW_DAYS=297`) antes de abrir 8080/443; a entrega diária
estende a janela com `POST /admin/estate/refresh?days=N`, e o `ensure-cloudpilot.ps1` reaplica
isso até o dia UTC atual.

## Automação do que não sobrevive a restart

`deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1` reaplica, de forma
idempotente, containers/aliases DNS, CA confiável, folha do front (reassina se o SAN
estiver atrás dos aliases), janela do estate e (com `-Smoke`) o probe do `k8s-sim` por
dentro do backend — **pelo nome HTTPS** (`https://opencost.synthetic-clouds.test`, o caminho
do consumidor) e **pelo alias HTTP** (`http://k8s-sim:8089`, o upstream do front) —,
"Verificar Conexão" + `/costs/unified`. Ele só reconecta uma rede quando
falta um alias, só reconstrói o estate quando a janela está vencida e só cria o container do
`k8s-sim` (a partir de `compose.k8s.yaml`, sem rebuild) quando ele não existe.

A tarefa `CloudPilot-Simulator-Ensure` (logon + a cada 30 min) é registrada por
`register-ensure-task.ps1` com XML **por usuário** (`LogonTrigger` com `UserId`), que é o
que dispensa elevação. **Na leitura de 2026-10-29 ela não está registrada nesta máquina**
(`schtasks /Query /TN CloudPilot-Simulator-Ensure` → "O sistema não pode encontrar o
caminho especificado"); registre com `.\register-ensure-task.ps1 -RunNow`. Ver
[`deploy/synthetic-clouds/integration/README.md`](../deploy/synthetic-clouds/integration/README.md).

### O que mais não sobrevive a um `up -d --build k8s-sim` (medido em 2026-10-31, S4b2-G)

O `up -d --build k8s-sim` **recria o container**, e a recriação quebra **duas** coisas que o
frontend do CloudPilot usava. As duas são medidas, e as duas têm correção **sem** recriar o front:

| O que se perde | Por quê | Como voltar |
|---|---|---|
| o alias `k8s-sim` na bridge `cloudpilot-deploy_cloudpilot_net` | a bridge **não** está no `compose.k8s.yaml`; quem a anexa é o `ensure-cloudpilot.ps1` | `podman network connect --alias k8s-sim cloudpilot-deploy_cloudpilot_net synthetic-clouds-k8s-sim-1` |
| o **IP** do upstream no nginx | o `nginx.conf` **não tem `resolver`**: o nome do upstream é resolvido **uma vez**, na carga da configuração (`nginx.conf:44-46`) | `podman exec synthetic-clouds-tls-front nginx -s reload` |

O sintoma do segundo item é **502 Bad Gateway** em **todas** as rotas do nome — inclusive nas que
já funcionavam antes da recriação — e a causa **não** é o serviço novo: é o nginx apontando para o
IP antigo. O `nginx -s reload` re-lê a configuração e resolve o upstream de novo, **sem** reiniciar
o container do front (mesmo PID, mesmo uptime, mesmos aliases). Um `podman restart` do front
resolveria também, mas derruba o container e é desnecessário.

O `ensure-cloudpilot.ps1` reanexa o alias quando falta, mas **não** recarrega o nginx: o front
precisa do reload depois de qualquer recriação do `k8s-sim`.
