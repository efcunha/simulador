# `vpc-flow-logs-bigquery` — VPC Flow Logs entregues ao BigQuery via Log Analytics

> **Achado principal (ver secção 1.1):** o Google **não** documenta uma entrega
> direta de VPC Flow Logs ao BigQuery. O destino oficial do VPC Flow Logs é o
> **Cloud Logging**. O caminho documentado até ao BigQuery é *consultar* os logs
> a partir do BigQuery através de um **linked dataset** ligado a um log bucket
> com Observability Analytics (Log Analytics) — em que o BigQuery lê os dados
> **sem os exportar**. Esta spec documenta o formato do registro de flow log
> (a parte com campos verificados) e registra a lacuna do schema do linked
> dataset.

## 1. Identificação

- **Nome oficial da superfície:** VPC Flow Logs (registro de flow log);
  entrega ao BigQuery por *linked BigQuery dataset* (Observability Analytics /
  Log Analytics).
- **Documentos oficiais e datas de consulta (2026-10-14):**

| Documento | URL | Consultado em |
|---|---|---|
| "VPC Flow Logs" (visão geral; destino = Cloud Logging) | <https://cloud.google.com/vpc/docs/flow-logs> | 2026-10-14 |
| "About VPC Flow Logs records" (formato do registro — **fonte dos campos**) | <https://cloud.google.com/vpc/docs/about-flow-logs-records> | 2026-10-14 |
| "Analyze logs using Logs Explorer and Observability Analytics" | <https://cloud.google.com/logging/docs/analyze> | 2026-10-14 |
| "Create a linked BigQuery dataset on a log bucket" | <https://cloud.google.com/logging/docs/analyze/query-linked-dataset> | 2026-10-14 |

- **Versão/schema de referência:** o registro de VPC Flow Logs é publicado na
  API `compute.googleapis.com` (logs de sub-rede); o documento não publica um
  número de versão do formato. O linked dataset do Logging mapeia **log views**
  para *virtual views* do BigQuery, sendo `_AllLogs` o nome da view citado nos
  exemplos oficiais.

### 1.1 Mecanismo e entrega — o que é comprovado

| Item | O que a documentação afirma | Fonte |
|---|---|---|
| Destino do flow log | "This data is then sent to **Logging** in the Google Cloud project of the VPC network that reported the flow." | <https://cloud.google.com/vpc/docs/flow-logs#logs_collection> |
| Retenção | "Logs are stored in Logging for 30 days by default. If you want to keep logs longer than that, you can either set a custom retention period or **export them to a supported destination**." | <https://cloud.google.com/vpc/docs/flow-logs#logs_collection> |
| Export suportado (genérico) | "You can view flow logs in Cloud Logging, and you can export logs to any destination that Cloud Logging export supports." | <https://cloud.google.com/vpc/docs/flow-logs> |
| Caminho BigQuery documentado | "Cloud Logging also lets you query your log data from BigQuery, **without exporting that data to BigQuery**. After you upgrade your log bucket to use Observability Analytics, create a linked BigQuery dataset." | <https://cloud.google.com/logging/docs/analyze> |
| Objeto BigQuery resultante | "a new dataset becomes available to BigQuery. [...] Any log views within the log bucket are automatically mapped to **virtual views** in the dataset. The name of a virtual view is the same as the corresponding log view." Exemplo oficial: bucket `example` + view `_AllLogs` → dataset `my_dataset` com a virtual view `_AllLogs`. | <https://cloud.google.com/logging/docs/analyze/query-linked-dataset#how_log_buckets_and_log_views_map_to_bigquery_objects> |
| Cardinalidade do link | "A log bucket can be linked to **at most one** BigQuery dataset." | <https://cloud.google.com/logging/docs/analyze/query-linked-dataset> |
| Leitura é read-only | "A linked BigQuery dataset is a **read-only pointer** to your log bucket." | <https://cloud.google.com/logging/docs/analyze/query-linked-dataset> |
| Criação | UI (Logs Storage → Edit bucket → "Create a new BigQuery dataset that links to this bucket") ou `gcloud logging links create LINK_ID --bucket=BUCKET_ID --location=LOCATION` | <https://cloud.google.com/logging/docs/analyze/query-linked-dataset> |
| Formato de arquivo (Parquet/CSV/NDJSON), compressão, delimitador, cabeçalho | **Não documentado** para este caminho — não há arquivo intermediário. Ver secção 4. | — |
| Nome de partição / caminho `gs://` | **Não documentado** para este caminho. Ver secção 4. | — |
| Schema do virtual view `_AllLogs` (nomes de coluna BigQuery) | **Não documentado** na página do linked dataset. Ver secção 4. | — |

## 2. Campos do registro de VPC Flow Logs

Base de todas as URLs desta secção:
`https://cloud.google.com/vpc/docs/about-flow-logs-records#<campo>`
(consulta em **2026-10-14**). A coluna **Fonte** indica o fragmento exato.

Classificação documentada: o registro contém **base fields** ("the core fields
of every log record", sempre incluídos) e **metadata fields** ("add additional
information", que "may be omitted to save storage costs"). Os campos
multi-valor são descritos em secções próprias (`IpConnection`, `InstanceDetails`,
etc.).

### 2.1 Campos de topo do registro

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `connection` | IpConnection | sim (Base) | — | — | formado por `src_ip`, `dest_ip`, `src_port`, `dest_port`, `protocol` | "5-tuple describing the flow." | `#record_format` |
| `reporter` | string | sim (Base) | — | — | VMs/serverless: `SRC`, `DEST`; gateways: `SRC_GATEWAY`, `DEST_GATEWAY` | "The side that reported the flow" | `#record_format` |
| `connection_direction` | string | sim (Base) | — | — | `EGRESS`, `INGRESS` | "Direction of the TCP connection relative to the reporter. Populated for VMs and serverless endpoints when TCP connection logging is enabled and an outbound SYN or SYN-ACK packet is observed during the aggregation interval." | `#record_format` |
| `round_trip_time` | Latencies | sim (Base) | ms | — | — | "RTT in milliseconds with sub-millisecond precision as measured during the aggregation interval." | `#record_format` |
| `rtt_msec` | int64 | sim (Base) | ms | — | — | "Round-trip time (RTT) in milliseconds as measured during the aggregation interval." | `#record_format` |
| `bytes_sent` | int64 | sim (Base) | bytes | — | — | "Estimated number of user payload bytes sent from the source to the destination." | `#record_format` |
| `packets_sent` | int64 | sim (Base) | pacotes | — | — | "Estimated number of packets sent from the source to the destination." | `#record_format` |
| `start_time` | string | sim (Base) | — | RFC 3339 date string | — | "Timestamp (RFC 3339 date string format) of the first observed packet during the aggregated time interval." | `#record_format` |
| `end_time` | string | sim (Base) | — | RFC 3339 date string | — | "Timestamp (RFC 3339 date string format) of the last observed packet during the aggregated time interval." | `#record_format` |
| `disposition` | string | sim (Base) | — | — | `DROPPED` | "Populated only for log records that capture packet drops. This field is set to DROPPED." | `#record_format` |
| `drop_reason` | string | sim (Base) | — | — | ver 2.2 | "Populated only for log records with disposition=DROPPED." | `#record_format` |
| `bytes_dropped` | int64 | sim (Base) | bytes | — | — | "Estimated number of user payload bytes dropped from the source to the destination. Populated only for log records with disposition=DROPPED." | `#record_format` |
| `packets_dropped` | int64 | sim (Base) | pacotes | — | — | "Estimated number of packets dropped from the source to the destination. Populated only for log records with disposition=DROPPED." | `#record_format` |
| `throughput_inclusion` | string | sim (Base) | — | — | `INCLUDED`, `EXCLUDED` | "Populated only for log records with disposition=DROPPED. Indicates whether the dropped traffic is included (INCLUDED) or excluded (EXCLUDED) from the bytes_sent and packets_sent fields [...]" | `#record_format` |
| `src_gateway` | GatewayDetails | não (Metadata) | — | — | — | Detalhes do gateway de origem (VLAN attachment / Cloud VPN tunnel). | `#record_format` |
| `dest_gateway` | GatewayDetails | não (Metadata) | — | — | — | Detalhes do gateway de destino. | `#record_format` |
| `src_gke_details` | GkeDetails | não (Metadata) | — | — | — | "If the source of the flow is a Google Kubernetes Engine (GKE) endpoint, this field is populated with GKE endpoint details." | `#record_format` |
| `dest_gke_details` | GkeDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_google_service` | GoogleServiceDetails | não (Metadata) | — | — | — | "If the source of the flow is a Google service, this field is populated with service details." | `#record_format` |
| `dest_google_service` | GoogleServiceDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_instance` | InstanceDetails | não (Metadata) | — | — | — | "If the source of the flow is a VM located in a VPC network [...] this field is populated with VM instance details." | `#record_format` |
| `dest_instance` | InstanceDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_location` | GeographicDetails | não (Metadata) | — | — | — | "If the source of the flow is a public IP address outside of the VPC network, this field is populated with available location metadata." | `#record_format` |
| `dest_location` | GeographicDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_serverless_details` | ServerlessDetails | não (Metadata) | — | — | — | Metadados de endpoint serverless (Cloud Run / App Engine com Direct VPC egress) de origem. | `#record_format` |
| `dest_serverless_details` | ServerlessDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_psc_interface` | PrivateServiceConnectInterfaceDetails | não (Metadata) | — | — | — | "If the source of the flow is a Private Service Connect interface, this field is populated with Private Service Connect interface details and is reported in the consumer project, by both the source and destination." | `#record_format` |
| `dest_psc_interface` | PrivateServiceConnectInterfaceDetails | não (Metadata) | — | — | — | Idem, para o destino. | `#record_format` |
| `src_vpc` | VpcDetails | não (Metadata) | — | — | — | Detalhes da rede VPC de origem. | `#record_format` |
| `dest_vpc` | VpcDetails | não (Metadata) | — | — | — | Detalhes da rede VPC de destino. | `#record_format` |
| `internet_routing_details` | InternetRoutingDetails | não (Metadata) | — | — | — | "If the flow is between Google Cloud and the internet, this field is populated with routing details. Available only for egress flows." | `#record_format` |
| `load_balancing` | LoadBalancingDetails | não (Metadata) | — | — | — | "If the flow passes through a load balancer [...] this field is populated with Cloud Load Balancing details." | `#record_format` |
| `network_service` | NetworkServiceDetails | não (Metadata) | — | — | — | "If the Differentiated Services Code Point (DSCP) header is set, this field is populated with network service details." | `#record_format` |
| `psc` | PrivateServiceConnectDetails | não (Metadata) | — | — | — | "If the flow is associated with a Private Service Connect connection [...] this field is populated with Private Service Connect details." | `#record_format` |
| `rdma_traffic_type` | string | não (Metadata) | — | — | `GPUDirect-TCPXO`, `Falcon`, `RoCE` | "Type of RDMA traffic. Populated for GPU-to-GPU traffic between VMs." | `#record_format` |

### 2.2 Valores documentados de `drop_reason`

Fonte: <https://cloud.google.com/vpc/docs/about-flow-logs-records#packet_drop_reasons>

- Reportados por `SRC` ou `SRC_GATEWAY`: `FIREWALL_DENY`, `NO_MATCHING_ROUTE`,
  `QUEUE_OVERFLOW`, `SPOOFED_SOURCE`, `TOO_MANY_CONNECTIONS`.
- Reportados por `DEST` ou `DEST_GATEWAY`: `EARLY_DROPS_FULL_FAIR_QUEUE`,
  `FIREWALL_DENY`, `INVALID_L4_CHECKSUM_INTERNET`, `INVALID_L4_CHECKSUM_INTERNAL`,
  `PSC_NAT_OUT_OF_CONNECTIONS`, `PSC_NAT_OUT_OF_PORTS`, `QUEUE_OVERFLOW`,
  `TOO_MANY_CONNECTIONS`.

### 2.3 Sub-estruturas (todos os campos com fonte verificada)

Fonte base: `https://cloud.google.com/vpc/docs/about-flow-logs-records#<campo>`.

| Campo | Tipo | Obrigatório | Unidade | Formato data/hora | Valores permitidos | Descrição | Fonte |
|---|---|---|---|---|---|---|---|
| `connection.src_ip` | string | sim | — | — | — | "Source IP address. Populated for all flows." | `#ipconnection_field_format` |
| `connection.dest_ip` | string | sim | — | — | — | "Destination IP address. Populated for all flows." | `#ipconnection_field_format` |
| `connection.src_port` | int32 | condicional | — | — | — | "Populated for TCP and UDP flows. Not populated for ICMP, ESP, GRE, and RDMA flows" | `#ipconnection_field_format` |
| `connection.dest_port` | int32 | condicional | — | — | — | "Populated for TCP and UDP flows. Not populated for ICMP, ESP, GRE, and RDMA flows" | `#ipconnection_field_format` |
| `connection.protocol` | int32 | condicional | — | — | "The IANA protocol number" | "Populated for TCP, UDP, ICMP, ESP, and GRE flows. Not populated for RDMA flows" | `#ipconnection_field_format` |
| `round_trip_time.median_msec` | double | não | ms | — | — | "The median latency in milliseconds as measured during the aggregation interval." | `#latencies_field_format` |
| `src_gateway.project_id` / `dest_gateway.project_id` | string | não | — | — | — | "Google Cloud project ID of the gateway" | `#gatewaydetails_field_format` |
| `src_gateway.location` / `dest_gateway.location` | string | não | — | — | — | "Region of the gateway" | `#gatewaydetails_field_format` |
| `src_gateway.name` / `dest_gateway.name` | string | não | — | — | — | "Name of the gateway" | `#gatewaydetails_field_format` |
| `src_gateway.type` / `dest_gateway.type` | string | não | — | — | `INTERCONNECT_ATTACHMENT`, `VPN_TUNNEL` | "Type of the gateway." | `#gatewaydetails_field_format` |
| `src_gateway.vpc` / `dest_gateway.vpc` | VpcDetails | não | — | — | — | "VPC network details of the gateway" | `#gatewaydetails_field_format` |
| `src_gateway.interconnect_name` / `dest_gateway.interconnect_name` | string | não | — | — | — | "If the type of the gateway is INTERCONNECT_ATTACHMENT, this field is populated with the name of the Cloud Interconnect connection on which the VLAN attachment is configured." | `#gatewaydetails_field_format` |
| `src_gateway.interconnect_project_number` / `dest_gateway.interconnect_project_number` | int64 | não | — | — | — | "If the type of the gateway is INTERCONNECT_ATTACHMENT, this field is populated with the Google Cloud project number of the Cloud Interconnect connection [...]" | `#gatewaydetails_field_format` |
| `src_location.asn` / `dest_location.asn` | int32 | não | — | — | — | "The ASN of the external network to which this endpoint belongs" | `#geographicdetails_field_format` |
| `src_location.city` / `dest_location.city` | string | não | — | — | — | "City for external endpoints" | `#geographicdetails_field_format` |
| `src_location.continent` / `dest_location.continent` | string | não | — | — | — | "Continent for external endpoints" | `#geographicdetails_field_format` |
| `src_location.country` / `dest_location.country` | string | não | — | — | ISO 3166-1 Alpha-3 | "Country for external endpoints, represented as ISO 3166-1 Alpha-3 country codes" | `#geographicdetails_field_format` |
| `src_location.region` / `dest_location.region` | string | não | — | — | — | "Region for external endpoints" | `#geographicdetails_field_format` |
| `src_instance.project_id` / `dest_instance.project_id` | string | não | — | — | — | "ID of the Google Cloud project that contains the VM resource" | `#instancedetails_field_format` |
| `src_instance.region` / `dest_instance.region` | string | não | — | — | — | "Region of the VM" | `#instancedetails_field_format` |
| `src_instance.vm_name` / `dest_instance.vm_name` | string | não | — | — | — | "Instance name of the VM" | `#instancedetails_field_format` |
| `src_instance.zone` / `dest_instance.zone` | string | não | — | — | — | "Zone of the VM" | `#instancedetails_field_format` |
| `src_instance.managed_instance_group` / `dest_instance.managed_instance_group` | InstanceGroupDetails | não | — | — | — | "If the VM is part of a managed instance group, this field is populated with instance group details." | `#instancedetails_field_format` |
| `…managed_instance_group.name` | string | não | — | — | — | "Name of the instance group" | `#instancegroupdetails_field_format` |
| `…managed_instance_group.region` | string | não | — | — | — | "If the instance group is regional, this field is populated with the region of the instance group." | `#instancegroupdetails_field_format` |
| `…managed_instance_group.zone` | string | não | — | — | — | "If the instance group is zonal, this field is populated with the zone of the instance group." | `#instancegroupdetails_field_format` |
| `src_vpc.project_id` / `dest_vpc.project_id` | string | não | — | — | — | "ID of the Google Cloud project that contains the VPC. In a Shared VPC configuration, the project ID is the ID of the host project." | `#vpcdetails_field_format` |
| `src_vpc.subnetwork_name` / `dest_vpc.subnetwork_name` | string | não | — | — | — | "Name of the subnet, if applicable" | `#vpcdetails_field_format` |
| `src_vpc.subnetwork_region` / `dest_vpc.subnetwork_region` | string | não | — | — | — | "Region of the subnet, if applicable" | `#vpcdetails_field_format` |
| `src_vpc.vpc_name` / `dest_vpc.vpc_name` | string | não | — | — | — | "Name of the network" | `#vpcdetails_field_format` |
| `src_google_service.type` / `dest_google_service.type` | string | não | — | — | `GOOGLE_API`, `GOOGLE_VPC_HOSTED_SERVICE` | "The type of service" | `#googleservicedetails_field_format` |
| `src_google_service.service_name` / `dest_google_service.service_name` | string | não | — | — | ex.: `pubsub.googleapis.com` | "Name of the service." | `#googleservicedetails_field_format` |
| `src_google_service.connectivity` / `dest_google_service.connectivity` | string | não | — | — | `PUBLIC_IP`, `PRIVATE_GOOGLE_ACCESS`, `DIRECT_CONNECTIVITY`, `PRIVATE_SERVICE_CONNECT_FOR_GOOGLE_APIS`, `PRIVATE_SERVICES_ACCESS`, `PRIVATE_SERVICE_CONNECT_ENDPOINT`, `PRIVATE_SERVICE_CONNECT_INTERFACE` | "Access method." (o documento associa valores distintos a `GOOGLE_API` e a `GOOGLE_VPC_HOSTED_SERVICE`) | `#googleservicedetails_field_format` |
| `src_google_service.private_domain` / `dest_google_service.private_domain` | string | não | — | — | `private.googleapis.com`, `restricted.googleapis.com`, `all-apis`, `vpc-sc` | "Private domain or Private Service Connect API bundle." | `#googleservicedetails_field_format` |
| `internet_routing_details.egress_as_path` | AsPath | não | — | — | — | "List of relevant AS paths. If there are multiple AS paths available to the flow, the field might contain more than one AS path." | `#internetroutingdetails_field_format` |
| `…egress_as_path.as_details` | AsDetails | não | — | — | — | "List of AS details for all systems in the AS path." | `#aspath_field_format` |
| `…as_details.asn` | uint32 | não | — | — | — | "The autonomous system number (ASN) of the AS" | `#asdetails_field_format` |
| `load_balancing.forwarding_rule_project_id` | string | não | — | — | — | "Google Cloud project ID of the forwarding rule" | `#loadbalancingdetails_field_format` |
| `load_balancing.reporter` | string | não | — | — | `CLIENT`, `BACKEND` | "Cloud Load Balancing reporter." | `#loadbalancingdetails_field_format` |
| `load_balancing.type` | string | não | — | — | `APPLICATION_LOAD_BALANCER`, `PROXY_NETWORK_LOAD_BALANCER`, `PASSTHROUGH_NETWORK_LOAD_BALANCER`, `PROTOCOL_FORWARDING` | "Load balancer type." | `#loadbalancingdetails_field_format` |
| `load_balancing.scheme` | string | não | — | — | `EXTERNAL_MANAGED`, `INTERNAL_MANAGED`, `EXTERNAL`, `INTERNAL`, `INTERNAL_SELF_MANAGED` | "Load balancer scheme." | `#loadbalancingdetails_field_format` |
| `load_balancing.url_map_name` | string | não | — | — | — | "Name of the URL map. Populated if the type of the load balancer is APPLICATION_LOAD_BALANCER." | `#loadbalancingdetails_field_format` |
| `load_balancing.forwarding_rule_name` | string | não | — | — | — | "Name of the forwarding rule" | `#loadbalancingdetails_field_format` |
| `load_balancing.backend_service_name` | string | não | — | — | — | "Name of the backend service. Populated if the reporter is BACKEND and load balancer type is PASSTHROUGH_NETWORK_LOAD_BALANCER. If the backend group type is TARGET_POOL, this field isn't populated." | `#loadbalancingdetails_field_format` |
| `load_balancing.backend_service_project_id` | string | não | — | — | — | "Project ID of the backend service. [...]" | `#loadbalancingdetails_field_format` |
| `load_balancing.backend_group_name` | string | não | — | — | — | "Name of the backend group. [...]" | `#loadbalancingdetails_field_format` |
| `load_balancing.backend_group_type` | string | não | — | — | `INSTANCE_GROUP`, `NETWORK_ENDPOINT_GROUP`, `TARGET_POOL` | "Type of the backend group. [...]" | `#loadbalancingdetails_field_format` |
| `load_balancing.backend_group_location` | string | não | — | — | — | "Location of the backend group. Can be a zone or a region [...]" | `#loadbalancingdetails_field_format` |
| `load_balancing.vpc` | VpcDetails | não | — | — | — | "VPC network details of the load balancer" | `#loadbalancingdetails_field_format` |
| `network_service.dscp` | int32 | não | — | — | — | "If the Differentiated Services field is present in packet headers, this field is populated with the DSCP value." | `#networkservicedetails_field_format` |
| `psc.reporter` | string | não | — | — | `CONSUMER`, `PRODUCER` | "Private Service Connect reporter." | `#privateserviceconnectdetails_field_format` |
| `psc.consumer_connection` | IpConnection | não | — | — | — | "The pre-NAT 5-tuple that describes the flow from the consumer's perspective. Populated if the reporter is PRODUCER." | `#privateserviceconnectdetails_field_format` |
| `psc.psc_endpoint` | PrivateServiceConnectEndpointDetails | não | — | — | — | "Consumer endpoint details" | `#privateserviceconnectdetails_field_format` |
| `psc.psc_attachment` | PrivateServiceConnectAttachmentDetails | não | — | — | — | "Producer service attachment details" | `#privateserviceconnectdetails_field_format` |
| `psc.psc_endpoint.name` | string | não | — | — | — | "Name of the Private Service Connect endpoint. Populated only if target_service_type is PUBLISHED_SERVICE." | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_endpoint.project_id` | string | não | — | — | — | "Google Cloud project ID of the endpoint." | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_endpoint.region` | string | não | — | — | — | "Region of the endpoint. Not populated if the target service type is GLOBAL_GOOGLE_APIS." | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_endpoint.psc_connection_id` | string | não | — | — | — | "Private Service Connect connection ID" | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_endpoint.target_service_type` | string | não | — | — | `GLOBAL_GOOGLE_APIS`, `PUBLISHED_SERVICE` | "Target service type." | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_endpoint.vpc` | VpcDetails | não | — | — | — | "VPC network details of the endpoint. If the reporter is PRODUCER, the subnetwork_name and subnetwork_region fields aren't populated." | `#privateserviceconnectendpointdetails_field_format` |
| `psc.psc_attachment.name` | string | não | — | — | — | "Name of the service attachment" | `#privateserviceconnectattachmentdetails_field_format` |
| `psc.psc_attachment.project_id` | string | não | — | — | — | "Google Cloud project ID of the service attachment" | `#privateserviceconnectattachmentdetails_field_format` |
| `psc.psc_attachment.region` | string | não | — | — | — | "Region of the service attachment" | `#privateserviceconnectattachmentdetails_field_format` |
| `psc.psc_attachment.vpc` | VpcDetails | não | — | — | — | "VPC network details of the service attachment" | `#privateserviceconnectattachmentdetails_field_format` |
| `src_psc_interface.network_attachment` / `dest_psc_interface.network_attachment` | NetworkAttachmentDetails | não | — | — | — | "Metadata for the consumer's network attachment" | `#privateserviceconnectinterfacedetails_field_format` |
| `src_psc_interface.producer` / `dest_psc_interface.producer` | ProducerDetails | não | — | — | — | "Metadata for the producer that initiated the connection" | `#privateserviceconnectinterfacedetails_field_format` |
| `…network_attachment.name` | string | não | — | — | — | "Name of the network attachment" | `#networkattachmentdetails_field_format` |
| `…network_attachment.project_id` | string | não | — | — | — | "Google Cloud project ID of the network attachment" | `#networkattachmentdetails_field_format` |
| `…network_attachment.region` | string | não | — | — | — | "Region of the network attachment" | `#networkattachmentdetails_field_format` |
| `…producer.project_id` | string | não | — | — | — | "Google Cloud project ID of the producer. Populated only if the service_class_id field isn't available." | `#producerdetails_field_format` |
| `…producer.region` | string | não | — | — | — | "Region of the producer VM" | `#producerdetails_field_format` |
| `…producer.service_class_id` | string | não | — | — | — | "ID of the producer's service class (if available)" | `#producerdetails_field_format` |
| `…producer.zone` | string | não | — | — | — | "Zone of the producer VM" | `#producerdetails_field_format` |
| `src_serverless_details.project_id` / `dest_serverless_details.project_id` | string | não | — | — | — | "ID of the Google Cloud project that contains the Cloud Run or App Engine resource. [...]" | `#serverlessdetails_field_format` |
| `src_serverless_details.region` / `dest_serverless_details.region` | string | não | — | — | — | "Region of the Cloud Run or App Engine resource" | `#serverlessdetails_field_format` |
| `…cloud_run_service_details.service_name` | string | não | — | — | — | "Name of the Cloud Run service" | `#cloudrunservicedetails_field_format` |
| `…cloud_run_job_details.job_name` | string | não | — | — | — | "Name of the Cloud Run job" | `#cloudrunjobdetails_field_format` |
| `…cloud_run_worker_pool_details.worker_pool_name` | string | não | — | — | — | "Name of the Cloud Run worker pool" | `#cloudrunworkerpooldetails_field_format` |
| `…app_engine_service_details.service_name` | string | não | — | — | — | "Name of the App Engine service" | `#appengineservicedetails_field_format` |
| `src_serverless_details.<…>` / `dest_serverless_details.<…>` (campo do nome) | `CloudRunServiceDetails` \| `CloudRunJobDetails` \| `CloudRunWorkerPoolDetails` \| `AppEngineServiceDetails` | não | — | — | o documento diz "One of the following: cloud_run_service_details, cloud_run_job_details, cloud_run_worker_pool_details, app_engine_service_details" | "Name of the Cloud Run or App Engine resource" | `#serverlessdetails_field_format` |
| `src_gke_details.cluster` / `dest_gke_details.cluster` | ClusterDetails | não | — | — | — | "GKE cluster metadata" | `#gkedetails_field_format` |
| `src_gke_details.pod` / `dest_gke_details.pod` | PodDetails | não | — | — | — | "GKE Pod metadata, populated when the source or destination of the traffic is a Pod" | `#gkedetails_field_format` |
| `src_gke_details.service` / `dest_gke_details.service` | ServiceDetails | não | — | — | — | "GKE Service metadata, populated in Service endpoints only. The record contains up to two Services. If there are more than two relevant Services, this field contains a single Service with a special MANY_SERVICES marker." | `#gkedetails_field_format` |
| `…cluster.cluster_location` | string | não | — | — | — | "Location of the cluster. This can be a zone or a region depending if the cluster is zonal or regional." | `#clusterdetails_field_format` |
| `…cluster.cluster_name` | string | não | — | — | — | "GKE cluster name." | `#clusterdetails_field_format` |
| `…pod.pod_name` | string | não | — | — | — | "Name of the Pod" | `#poddetails_field_format` |
| `…pod.pod_namespace` | string | não | — | — | — | "Namespace of the Pod" | `#poddetails_field_format` |
| `…pod.workload` | WorkloadDetails | não | — | — | — | "Metadata about the top-level workload resource that controls the Pod" | `#poddetails_field_format` |
| `…workload.workload_name` | string | não | — | — | — | "Name of the top-level workload controller" | `#workloaddetails_field_format` |
| `…workload.workload_type` | string | não | — | — | `DEPLOYMENT`, `REPLICA_SET`, `STATEFUL_SET`, `DAEMON_SET`, `JOB`, `CRON_JOB`, `REPLICATION_CONTROLLER` | "Type of the top-level workload controller." | `#workloaddetails_field_format` |
| `…service.service_name` | string | não | — | — | `MANY_SERVICES` (marcador especial) | "Name of the Service. If there are more than two relevant Services, the field is set to a special MANY_SERVICES marker." | `#servicedetails_field_format` |
| `…service.service_namespace` | string | não | — | — | — | "Namespace of the Service" | `#servicedetails_field_format` |

> **Contagem (verificada no `.schema.json`):** 35 campos de topo do registro
> (13 `Base` + 22 `Metadata`) + 146 subcampos aninhados = **181 entradas de
> campo**. As tabelas 2.1–2.3 cobrem todas as secções de formato publicadas na
> página oficial, incluindo `IpConnection`, `Latencies`, `GatewayDetails`,
> `GeographicDetails`, `InstanceDetails`/`InstanceGroupDetails`,
> `GkeDetails`/`ClusterDetails`/`PodDetails`/`WorkloadDetails`/`ServiceDetails`,
> `GoogleServiceDetails`, `InternetRoutingDetails`/`AsPath`/`AsDetails`,
> `LoadBalancingDetails`, `NetworkServiceDetails`,
> `PrivateServiceConnectDetails`/`PrivateServiceConnectEndpointDetails`/`PrivateServiceConnectAttachmentDetails`,
> `PrivateServiceConnectInterfaceDetails`/`NetworkAttachmentDetails`/`ProducerDetails`,
> `ServerlessDetails`/`CloudRunServiceDetails`/`CloudRunJobDetails`/`CloudRunWorkerPoolDetails`/`AppEngineServiceDetails`,
> e `VpcDetails`.

## 3. Manifesto e metadados

- **Manifesto:** não documentado para este caminho. O linked dataset expõe
  *virtual views*, não um arquivo com manifesto.
- **Sobre a estimativa:** "Estimated total based on sampled packets. For best
  accuracy, aggregate logs across longer time periods or multiple resources."
  (nota de rodapé 1 da tabela de formato do registro) —
  <https://cloud.google.com/vpc/docs/about-flow-logs-records#record_format>
- **Rodapé 2 (Falcon):** para tráfego Falcon o valor de bytes enviados é
  calculado de forma diferente conforme o reporter seja a VM de origem ou de
  destino — <https://cloud.google.com/vpc/docs/about-flow-logs-records#record_format>
- **Anotações de metadados configuráveis:** "If you select all metadata, all
  metadata fields in the VPC Flow Logs record format are included [...] If you
  select no metadata, this omits all metadata fields." —
  <https://cloud.google.com/vpc/docs/about-flow-logs-records#metadata_annotations>
- **Anotações cross-project:** habilitadas por padrão quando o VPC Flow Logs é
  configurado no nível de organização —
  <https://cloud.google.com/vpc/docs/about-flow-logs-records#cross-project_annotations>

## 4. Campos não comprovados

| Item | Estado | Motivo |
|---|---|---|
| Existência de um export **direto** de VPC Flow Logs para BigQuery | UNVERIFIED / **não existe na documentação** | A página oficial de VPC Flow Logs afirma que os dados são enviados ao **Cloud Logging** e que se pode "export them to a supported destination" (genérico). Nenhuma página oficial descreve um sink/export específico VPC Flow Logs → BigQuery com schema próprio. |
| Schema (nomes de coluna) do virtual view `_AllLogs` no linked BigQuery dataset | UNVERIFIED | A página "Create a linked BigQuery dataset on a log bucket" descreve o mapeamento view→virtual view e o nome `_AllLogs`, mas **não** publica a lista de colunas nem os tipos. O mapeamento do registro de flow log para `jsonPayload`/colunas do BigQuery não é documentado nessa página. |
| Formato de arquivo, compressão, encoding, delimitador, cabeçalho | UNVERIFIED | Não há arquivo intermediário documentado neste caminho; o linked dataset é "read-only pointer". |
| Caminho/particionamento (`gs://…`, prefixos, shards) | UNVERIFIED | Não documentado para este caminho. |
| Manifesto | UNVERIFIED | Não documentado para este caminho. |
| Nome da tabela/view que contém os flow logs especificamente | UNVERIFIED | A documentação cita `_AllLogs` como exemplo de log view do bucket; não afirma que os flow logs ficam nessa view nem com que nome. |
| Tipo BigQuery de cada campo (`jsonPayload.<campo>`) | UNVERIFIED | A página de formato do registro dá o tipo do registro (`int64`, `string`, `int32`, `double`, `uint32`, mensagens), mas **não** o tipo BigQuery correspondente. |

## 5. Divergências conhecidas

- O nome da superfície pedido no escopo é "VPC Flow Logs → BigQuery". A
  documentação oficial descreve (a) destino **Cloud Logging** e (b) leitura a
  partir do BigQuery via **linked dataset**, explicitamente "without exporting
  that data to BigQuery". As duas descrições não são equivalentes a um export
  com entrega em tabela; registradas ambas, sem escolha unilateral.
