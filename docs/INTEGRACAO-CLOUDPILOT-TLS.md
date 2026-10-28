# Integração CloudPilot ↔ simulador sem código de simulador no CloudPilot

Este documento registra a configuração que faz o CloudPilot falar com o
simulador **pelos nomes e pelo TLS da nuvem real**. Nenhum código de ingestão do
CloudPilot conhece o simulador: ele constrói o cliente de produção e resolve o
hostname de produção. Quem se adapta é esta stack.

## O que é deployment (CloudPilot) e o que é simulador

| Lado | Arquivo | Papel |
|---|---|---|
| CloudPilot | `docker-compose.local.yml` | monta `./.local/tls/ca-bundle.pem` em `/certs` e define `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`, `CURL_CA_BUNDLE` e `HTTPLIB2_CA_CERTS` |
| CloudPilot | `D:\cloudpilot-deploy\.local\tls\ca-bundle.pem` | bundle certifi + CA local (não versionado) |
| Simulador | `emulators/azure-sim/tls/` | CA local e folhas TLS (git-ignored; geradas pelos scripts abaixo) |
| Simulador | `deploy/synthetic-clouds/compose.yaml` | azure-sim serve 443 (TLS) além de 8080, com `net.ipv4.ip_unprivileged_port_start=0` |
| Simulador | `deploy/synthetic-clouds/compose.tls-front.yaml` | front nginx para `bigquery.googleapis.com`, `oauth2.googleapis.com` e `cloudresourcemanager.googleapis.com` |
| Simulador | `deploy/synthetic-clouds/tls-front/nginx.conf` | roteia cada hostname para o emulador certo |

## Hostnames e destinos

Na rede `cloudpilot-deploy_cloudpilot_net`:

| Hostname | Serve | Implementação |
|---|---|---|
| `management.azure.com` | azure-sim (TLS 443) | alias de rede no próprio azure-sim |
| `login.microsoftonline.com` | azure-sim (TLS 443) | OIDC discovery + token JWT (HS256, claims marcadas) |
| `bigquery.googleapis.com` | bqemulator:9050 | front nginx |
| `oauth2.googleapis.com` | gcp-sim:8085 | front nginx (`POST /token`) |
| `cloudresourcemanager.googleapis.com` | gcp-sim:8085 | front nginx (`GET /v1/projects`; o `googleapiclient` usa o discovery estático embutido) |

`sts.amazonaws.com` e `sts.us-east-1.amazonaws.com` **não** são publicados
nesta rede: o STS resolve na AWS de verdade. Ver a seção "STS" abaixo.

## STS: por que o simulador não sequestra o hostname

O `aws-sim` responde `GetCallerIdentity` com a primeira conta do estate
(`911368690069` no seed 123). Publicar `sts.amazonaws.com` para o front por
DNS fazia o validador do CloudPilot resolver **toda** conta AWS da rede —
inclusive as contas REAIS, com chaves válidas — contra o simulador. A guarda
anti-confused-deputy (`backend/app/services/providers/aws/connection_validator.py`)
então rejeitava a conexão com `reason=account_mismatch`, e o banner
"Credenciais Expiradas" aparecia para uma credencial perfeitamente válida.

A conta AWS do simulador precisa de um endpoint STS **por conta** — hoje
`cur_config.endpoint_url` cobre apenas S3 — e não de um sequestro global de
hostname: sequestrar `sts.*` quebra qualquer conta real que compartilhe a
rede com o simulador.

## Certificados

A CA é gerada uma vez e não deve ser regenerada sem refazer o bundle do
CloudPilot:

```powershell
.\.venv\Scripts\python.exe emulators\azure-sim\scripts\gen_dev_tls.py
.\.venv\Scripts\python.exe emulators\azure-sim\scripts\gen_cloud_front_tls.py
```

O primeiro script cria `ca.crt`/`ca.key` e a folha `server.crt` (hostnames Azure,
já embutida na imagem do azure-sim). O segundo assina com a MESMA CA a folha
`server-clouds.crt` usada pelo front (GCP). O bundle do CloudPilot é
`certifi/cacert.pem` do container + `ca.crt`, copiado para
`D:\cloudpilot-deploy\.local\tls\ca-bundle.pem`.

Se a CA mudar, o bundle precisa ser refeito e os containers do CloudPilot
recriados. As folhas podem ser regeradas sem tocar na CA.

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

1. `podman compose -f deploy/synthetic-clouds/compose.yaml up -d azure-sim`
2. `podman network connect --alias management.azure.com --alias login.microsoftonline.com cloudpilot-deploy_cloudpilot_net synthetic-clouds-azure-sim-1`
3. `podman compose -f deploy/synthetic-clouds/compose.tls-front.yaml up -d`
4. CloudPilot: `scripts/compose-local.ps1 -Action build -Services backend` e
   `-Action up`.

O azure-sim leva ~1–2 min para construir o estate (`PROFILE=medium`,
`WINDOW_DAYS=297`) antes de abrir 8080/443; a entrega diária estende a janela
com `POST /admin/estate/refresh?days=N`.

## Automação do que não sobrevive a restart

`deploy/synthetic-clouds/integration/ensure-cloudpilot.ps1` reaplica, de forma
idempotente, containers/aliases DNS, CA confiável, janela do estate e (com
`-Smoke`) “Verificar Conexão” + `/costs/unified`. Ele só reconecta uma rede
quando falta um alias e só reconstrói o estate quando a janela está vencida.

A tarefa `CloudPilot-Simulator-Ensure` (logon + a cada 30 min) é registrada por
`register-ensure-task.ps1` com XML **por usuário** (`LogonTrigger` com
`UserId`), que é o que dispensa elevação. Ver
`deploy/synthetic-clouds/integration/README.md`.
