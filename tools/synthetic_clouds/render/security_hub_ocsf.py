"""Security Hub — o export OCSF (``FindingsOutput.Format = OCSF_JSON``).

Superficie: ``specs/aws/security-hub-ocsf-export.schema.json``.

POR QUE ESTA SUPERFICIE EXISTE
------------------------------
O item D3(c) mandava trocar o alvo do ASFF para ``CSV``/``OCSF_JSON``. A leitura da fonte mostrou
que o ``aws/security-hub-asff`` **nao esta errado**: ele descreve a RESPOSTA da API
(``AwsSecurityFinding``), que e o que o Security Hub devolve a quem chama a API. O que faltava era
o artefato que a AWS **exporta**, e a pagina do ``FindingsOutput`` fecha a questao com a forma
exata:

    "``OCSF_JSON`` produces newline-delimited JSON records in the Open Cybersecurity Schema
    Framework (OCSF) format used elsewhere in Security Hub."
    -- https://docs.aws.amazon.com/securityhub/1.0/APIReference/API_FindingsOutput.html

Entao o arquivo e **JSON por linha** -- um registro OCSF por linha --, e nao um array. E o
``SelectedFields`` (que a AWS publica como lista de caminhos OCSF) **nao** se aplica a este
formato, porque ele inclui o achado inteiro: a lista e usada aqui como o CATALOGO DE CAMPOS do
formato, e nao como um mecanismo de selecao.

AS DUAS COISAS QUE A INVESTIGACAO **NAO** ENCONTROU, E QUE POR ISSO NAO SAO INVENTADAS
---------------------------------------------------------------------------------------
* **A classe OCSF.** O candidato natural seria ``compliance_finding`` (uid 3, do repositorio
  normativo do OCSF), e emitir contra ela seria construir o contrato por analogia. A lista de
  campos da AWS recusa essa analogia: ela mistura ``vulnerabilities.*``, ``malware.*``,
  ``databucket.*`` e ``evidences.*`` com ``cloud.*`` e ``finding_info.*``, o que indica que o
  export **nao** usa uma classe so como envelope. ``class_uid``/``category_uid``/``type_uid``
  ficam fora do artefato e registrados como nao comprovados.
* **O ``metadata.version``.** O OCSF o declara obrigatorio (a versao do schema), e a AWS nao
  afirma qual revisao o export usa. A ultima LANCADA do OCSF foi verificada (1.9.0), mas escolher
  uma para o artefato seria afirmar um fato que a fonte da AWS nao publica.

O residual foi **reprocurado em 2026-10-15**, antes de ser declarado encerrado. A consulta deu
duas respostas, e nenhuma delas serve como valor:

* A AWS publica ``class_name`` como caminho valido **do proprio export** (na lista de
  ``FindingsOutput.SelectedFields`` e na tabela de campos OCSF da pagina de automation rules), mas
  nao publica o ``class_uid`` correspondente, nem a categoria, nem o tipo, nem a lista de valores
  de ``class_name``. A fonte afirma o *nome* do campo, nunca o valor.
* A unica frase da AWS sobre uma versao -- *"Security Hub currently supports findings in OCSF
  schema version 1.6"* -- declara a revisao de schema que o servico **suporta** para os achados em
  geral. Nao e o valor do campo no arquivo exportado. E a propria lista de campos do export (119
  caminhos, conferida no ``.md``) nao publica ``metadata.version``: publica ``metadata.uid`` e
  ``metadata.product.*``, e nao a revisao.

As duas ausencias estao em ``unverified`` na spec: um artefato que as inventasse passaria a
auditoria contra um contrato que ninguem publicou.

O QUE SAI VAZIO, E POR QUE
--------------------------
``compliance.status``: o caminho e publicado pela AWS e o estado **nao** carrega resultado de
avaliacao de conformidade -- o mapeamento ASFF do mesmo achado tambem emite ``Compliance: None``,
com a justificativa registrada. Os campos de framework (``compliance.control``,
``compliance.standards``) ficam FORA do contrato em vez de vazios, pela mesma razao.

O QUE MUDOU DEPOIS: ``severity_id`` DEIXOU DE SER LACUNA (2026-10-15)
---------------------------------------------------------------------
O enum foi lido no repositorio normativo do OCSF -- ``dictionary.json``, na tag ``1.6.0`` --
e reconferido na ``1.9.0``, onde e identico. O campo passou a ser emitido com o par
``(severity, severity_id)`` saindo do mesmo literal, como o status ja fazia. E o ``severity``
deixou de sair com o literal NATIVO em maiusculas (``HIGH``) para sair com a **legenda** do enum
(``High``): e o que o mesmo ``dictionary.json`` define -- *"normalized to the caption of the
``severity_id`` value"* -- e o que o par ``status``/``status_id`` deste modulo ja fazia. Emitir
``severity: "HIGH"`` ao lado de ``severity_id: 4`` afirmava um par que a fonte nao publica.

O MAPEAMENTO REUSA O DO ASFF
----------------------------
``render/security_hub.py`` ja projeta os mesmos fatos (severidade, produto, data do achado, nome
da conta) para o formato ASFF. Este modulo importa os ajudantes de la em vez de reimplementar o
mapeamento: duas copias da mesma projecao acabariam discordando -- e e exatamente o defeito que o
item E2 registra sobre dois produtores do mesmo contrato.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import (
    DEFAULT_SPECS_ROOT,
    SpecError,
    SurfaceSpec,
    load_spec,
)
from tools.synthetic_clouds.generate.constants import PROVIDER_KEY_AWS
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.native import NativeFinding
from tools.synthetic_clouds.model.resource import Resource
from tools.synthetic_clouds.render.azure_arm_instances import PROVENANCE_FILE, provenance, write_json
from tools.synthetic_clouds.render.base import RenderError
from tools.synthetic_clouds.render.security_hub import (
    _PROVIDER_LITERAL,
    _aws_findings,
    _raised_at,
    _text,
)

#: O caminho da especificacao normativa DENTRO de ``specs/`` (a proveniencia cita este texto).
_SPEC_FILE = "aws/security-hub-ocsf-export.schema.json"

#: A especificacao normativa desta superficie (fonte da verdade; NUNCA editada aqui).
SPEC_PATH = DEFAULT_SPECS_ROOT / _SPEC_FILE

#: O nome do arquivo entregue. A AWS nao publica nome de arquivo para este export (so o
#: ``ObjectPrefix``), entao o nome e do simulador -- e esta dito no relatorio de proveniencia.
_ARTIFACT_NAME = "security_hub_ocsf_findings.jsonl"

#: ``activity_id = 1`` e "Create" no OCSF, e o rotulo e o que a AWS publica como ``activity_name``.
_ACTIVITY_NAME = "Create"

#: O status do achado no vocabulario OCSF. O mapeamento parte do MESMO literal nativo que o
#: renderer ASFF usa (``_RECORD_STATE: open -> ACTIVE``): aqui o par e (rotulo ``status``,
#: identificador ``status_id``), porque o OCSF publica os dois e a AWS lista ambos.
_STATUS_OCSF: dict[str, tuple[str, int]] = {
    "open": ("New", 1),
    "acknowledged": ("In Progress", 2),
    "resolved": ("Resolved", 4),
}

#: O par ``(severity, severity_id)``, com o enum lido no **repositorio normativo do OCSF**:
#: ``dictionary.json`` na tag ``1.6.0`` (258 KB) declara ``severity_id`` como ``integer_t`` com
#: 0 Unknown, 1 Informational, 2 Low, 3 Medium, 4 High, 5 Critical, 6 Fatal e 99 Other. O enum
#: foi conferido tambem na tag ``1.9.0`` e e **identico** -- o que importa aqui, porque a revisao
#: do schema que o export usa continua nao documentada: um valor que nao muda entre 1.6 e 1.9 nao
#: depende de resolver essa lacuna.
#:
#: O mesmo ``dictionary.json`` define ``severity`` como "normalized to the caption of the
#: ``severity_id`` value" -- a legenda do enum, em caixa de titulo. ``NativeFinding.severity`` e o
#: vocabulario NATIVO em MAIUSCULAS (``model/native.py``), e a entrada abaixo normaliza a caixa e
#: traz as DUAS metades do mesmo literal, exatamente como ``_STATUS_OCSF`` faz com o status.
_SEVERITY_OCSF: dict[str, tuple[str, int]] = {
    "LOW": ("Low", 2),
    "MEDIUM": ("Medium", 3),
    "HIGH": ("High", 4),
    "CRITICAL": ("Critical", 5),
}


def _spec() -> SurfaceSpec:
    """A spec normativa, carregada a cada chamada; falha FECHADO se nao servir."""
    try:
        return load_spec(SPEC_PATH)
    except SpecError as exc:
        raise RenderError(f"{SPEC_PATH}: {exc}") from exc


def _compliance_status(finding: NativeFinding) -> str | None:
    """O rotulo de conformidade, ou ``None`` quando o estado nao carrega avaliacao.

    O OCSF publica ``compliance.status`` como o rotulo normalizado do resultado da verificacao
    (Pass/Warning/Fail). O estado NAO carrega resultado de conformidade -- o mapeamento ASFF do
    mesmo achado tambem emite ``Compliance: None`` --, entao o campo sai vazio em vez de receber
    um resultado escolhido por semelhanca.
    """
    return None


def _resource_of(finding: NativeFinding, por_uuid: Mapping[str, Resource]) -> Resource | None:
    return por_uuid.get(finding.resource_uuid)


def ocsf_record(finding: NativeFinding, resource: Resource | None, *, account_name: str | None) -> dict[str, Any]:
    """Um registro OCSF para o achado, com os campos que o ESTADO sustenta.

    Os caminhos sao os que a AWS publica na lista de ``SelectedFields`` do ``FindingsOutput`` --
    nao foram deduzidos do repositorio normativo do OCSF, porque as duas fontes divergem em forma
    e a que descreve ESTE arquivo e a da AWS.
    """
    status = _STATUS_OCSF.get(finding.status)
    severity = _SEVERITY_OCSF.get(finding.severity)
    return {
        "metadata": {
            "uid": finding.finding_id,
            "product": {
                "name": _text(finding.product_name),
                "vendor_name": _text(finding.company_name),
            },
        },
        "activity_name": _ACTIVITY_NAME,
        "cloud": {
            "account": {
                "name": account_name,
                "uid": resource.parent_scope_id if resource is not None else None,
            },
            "provider": _PROVIDER_LITERAL,
            "region": resource.region_id if resource is not None else None,
        },
        "compliance": {"status": _compliance_status(finding)},
        "finding_info": {
            "uid": finding.finding_id,
            "title": _text(finding.title),
            "desc": _text(finding.description),
            "types": list(finding.types) or None,
            "created_time_dt": _raised_at(finding.raised_on),
        },
        "resources": (
            [
                {
                    "name": resource.resource_name,
                    "type": resource.resource_type,
                    "provider": _PROVIDER_LITERAL,
                    "region": resource.region_id,
                }
            ]
            if resource is not None
            else None
        ),
        "severity": severity[0] if severity is not None else None,
        "severity_id": severity[1] if severity is not None else None,
        "status": status[0] if status is not None else None,
        "status_id": status[1] if status is not None else None,
    }


class SecurityHubOcsfExportRenderer:
    """Entrega o export de findings do Security Hub em OCSF_JSON (JSON por linha)."""

    name = "security_hub_ocsf_export"

    def build_records(self, estate: CanonicalEstate) -> list[dict[str, Any]]:
        """Um registro por achado AWS do estado, em ordem deterministica.

        O nome da conta vem do mesmo lugar que o renderer ASFF usa (``AwsAccountName``), e um
        achado cujo recurso nao esta no estado **nao** e descartado: ele perde os campos de
        ``cloud``/``resources``, e nao o registro inteiro -- o achado existe mesmo quando o
        recurso nao esta no inventario.
        """
        por_uuid = {r.identity.uuid: r for r in estate.resources if r.identity.provider == PROVIDER_KEY_AWS}
        nomes_de_conta = {a.billing_account_id: a.name for a in estate.billing_accounts}
        registros: list[dict[str, Any]] = []
        for finding in _aws_findings(estate):
            resource = _resource_of(finding, por_uuid)
            escopo = resource.parent_scope_id if resource is not None else None
            registros.append(ocsf_record(finding, resource, account_name=nomes_de_conta.get(escopo or "")))
        return registros

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Escreve o arquivo de linhas JSON e o relatorio de proveniencia irmao."""
        target = out_dir / self.name
        registros = self.build_records(estate)
        artefato = target / _ARTIFACT_NAME
        artefato.parent.mkdir(parents=True, exist_ok=True)
        # JSON POR LINHA, e nao um array: e a forma que a propria AWS publica para o
        # ``Format = OCSF_JSON`` ("newline-delimited JSON records").
        artefato.write_text(
            "".join(json.dumps(registro, sort_keys=True) + "\n" for registro in registros),
            encoding="utf-8",
        )

        spec = _spec()
        write_json(
            target / PROVENANCE_FILE,
            provenance(
                spec,
                spec_file=_SPEC_FILE,
                artifacts=[_ARTIFACT_NAME, PROVENANCE_FILE],
                mechanism={
                    "kind": "s3",
                    "format": "ocsf-json-lines",
                    "file_name": _ARTIFACT_NAME,
                    "file_name_note": (
                        "a AWS nao publica nome de arquivo para este export (so ObjectPrefix, ate 512 "
                        "caracteres); o nome e do simulador"
                    ),
                    "path_template": None,
                    "path_template_note": "NOT DOCUMENTED: sem template de particionamento publicado",
                    "compression": None,
                    "encoding": "UTF-8 (JSON)",
                    "manifest": None,
                    "root": "one OCSF record per line",
                    "delivery_note": (
                        "artefato que a AWS EXPORTA (StartExportJobV2 -> FindingsOutput.Format = "
                        "OCSF_JSON), distinto da RESPOSTA da API que a superficie aws/security-hub-asff "
                        "descreve: mesma origem, dois formatos"
                    ),
                    "selected_fields": (
                        "NAO se aplica a OCSF_JSON (a AWS responde ValidationException se for enviado): o "
                        "formato inclui o achado inteiro, e a lista de caminhos da AWS foi usada como "
                        "CATALOGO DE CAMPOS do formato"
                    ),
                },
                columns={
                    "documented": len(spec.columns),
                    "generated": len(spec.columns),
                    "sets": list(spec.set_names),
                },
                counts={
                    "records": len(registros),
                    "findings_aws_no_estado": len(_aws_findings(estate)),
                    "findings_sem_recurso_no_estado": sum(
                        1 for f in _aws_findings(estate) if f.resource_uuid not in por_uuids(estate)
                    ),
                },
                model_gaps=[
                    {
                        "item": "``class_uid`` / ``category_uid`` / ``type_uid``",
                        "reason": (
                            "o OCSF identifica a classe por identificador numerico no envelope, e nem a "
                            "lista de campos da AWS nem as paginas de API consultadas afirmam qual classe "
                            "este export usa. O candidato natural (``compliance_finding``, uid 3) foi lido "
                            "no repositorio normativo do OCSF, mas a lista da AWS mistura campos de "
                            "vulnerabilidade, malware e databucket -- o que recusa a analogia. Escolher uma "
                            "classe seria construir o contrato por semelhanca. Em 2026-10-15 a AWS foi "
                            "reconsultada: ela publica ``class_name`` como caminho do export e nao publica "
                            "o identificador numerico nem os valores possiveis"
                        ),
                    },
                    {
                        "item": "``metadata.version``",
                        "reason": (
                            "o OCSF o declara obrigatorio (versao do schema) e a AWS nao afirma qual "
                            "revisao o export usa; a ultima LANCADA (1.9.0) foi verificada na API de "
                            "releases do repositorio, e escolhe-la seria afirmar um fato que a fonte da AWS "
                            "nao publica. Em 2026-10-15 a AWS foi reconsultada: a pagina do export nao "
                            "declara versao, e a frase 'supports findings in OCSF schema version 1.6' e "
                            "sobre a revisao suportada pelos achados do servico, nao sobre o campo no "
                            "arquivo exportado"
                        ),
                    },
                    {
                        "item": "``compliance.control`` / ``compliance.standards``",
                        "reason": (
                            "os caminhos sao publicados pela AWS e o estado nao carrega framework nem "
                            "controle -- o mapeamento ASFF do mesmo achado tambem emite Compliance: None"
                        ),
                    },
                ],
            ),
        )
        return [artefato, target / PROVENANCE_FILE]


def por_uuids(estate: CanonicalEstate) -> set[str]:
    """Os uuids de recurso do estado -- usado so para contar os achados sem recurso."""
    return {r.identity.uuid for r in estate.resources}


__all__ = ["SecurityHubOcsfExportRenderer", "ocsf_record"]
