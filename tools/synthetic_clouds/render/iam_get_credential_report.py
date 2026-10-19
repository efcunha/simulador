"""AWS IAM ``GetCredentialReport`` renderer -- o CSV de credenciais, decodificado.

Projects the canonical estate's identity postures into the **23 documented columns** of
``specs/aws/iam-get-credential-report.schema.json`` -- the columns the IAM User Guide lists for
the credential report CSV -- plus the **1 request parameter** and the **3 response envelope**
elements.

WHY THIS SURFACE AND NOT JUST THE PASSWORD POLICY
--------------------------------------------------
``aws/iam-get-account-password-policy`` publishes the account's password requirements.
This one publishes the IDENTITIES: who exists, who has a console password, who has MFA, and
when each key was last rotated. It is the surface a real posture tool reads to answer "which
console users have no MFA" -- the FinOps security service compares ``user``,
``password_enabled`` and ``mfa_active`` row by row -- and it is the only place the **root
account** has a row at all, which is what ``root-account-mfa-enabled`` reads.

THE FORMAT IS THE POINT
-----------------------
This is the only CSV contract in the repository, and the differences are not cosmetic:

* **booleans are ``TRUE``/``FALSE``**, uppercase, because they are CSV text. Every other
  artifact here is JSON and spells them ``true``/``false``. A consumer that compares with
  ``true`` reads every row in the account as false;
* **the header is mandatory and ordered.** A CSV without the documented header in the
  documented order is not parseable deterministically, so the header is written first and the
  column list is derived from the spec, never typed;
* **two access keys per user, and no more.** There is no ``access_key_3_*`` column, so the row
  list cannot be read as "every key in the account" -- it is "the first two of each user".

THE LITERALS ARE STATES, NOT ABSENCES
-------------------------------------
``N/A``, ``not_supported`` and ``no_information`` are documented values, and each one means
something specific:

* ``N/A`` -- the object does not exist: no password (``password_last_*``), or no such key
  (``access_key_N_last_rotated``);
* ``not_supported`` -- always, and **only** on the root row, for ``password_next_rotation``:
  the root has no manageable password and therefore nothing to rotate;
* ``no_information`` -- ``password_last_used`` never signed in, or there is no sign-in data
  since 2014-10-20.

Translating any of them to ``null`` would turn a documented state into a missing value, and the
consumer would stop being able to tell "this user has no password" from "this column came
empty".

THE ROOT ROW'S NAME IS DECLARED UNVERIFIED
-------------------------------------------
Neither ``API_GetCredentialReport.html`` nor the User Guide columns page, both read on
2026-10-18, publishes the literal in the ``user`` column of the root row. The row is emitted
anyway -- without it ``root-account-mfa-enabled`` has no row to read -- and the literal is
marked ``unverified`` in the spec, with the reason in the ``_provenance``. A consumer matching
that column against the string needs to know nobody checked it against an official page.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iam import AwsAccessKey, AwsIamUser, AwsIdentityPosture
from tools.synthetic_clouds.render._config_evaluators import IAM_RULE_EVALUATORS, RULE_ROOT_MFA
from tools.synthetic_clouds.render.base import RenderError

SURFACE = "aws/iam-get-credential-report"
RENDER_DIR = "iam_get_credential_report"

CSV_SCOPE = "get-credential-report-response"
REQUEST_SCOPE = "request-parameters"
ENVELOPE_SCOPE = "response-envelope"

SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "iam-get-credential-report.schema.json"

#: O nome da linha da conta root na coluna ``user``. NAO COMPROVADO: ver o docstring e a
#: entrada homonima da lista ``unverified`` da spec. Declarado num unico lugar para que o
#: valor e o motivo de desconfiar dele nao possam divergir.
ROOT_ACCOUNT_USER_LITERAL = "<root_account>"

#: Os literais documentados. Cada um e um ESTADO com significado proprio -- ver o docstring.
LITERAL_NA = "N/A"
LITERAL_NOT_SUPPORTED = "not_supported"
LITERAL_NO_INFORMATION = "no_information"

#: O report traz no MAXIMO duas chaves por usuario, e nao existe coluna de terceira.
ACCESS_KEY_SLOTS = (1, 2)


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/iam-get-credential-report``."""
    return load_spec(SPEC_PATH)


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one."""
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"{RENDER_DIR}: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


#: O cabecalho do CSV, derivado da spec e nunca redigitado: a ordem do cabecalho E o contrato.
_CSV_COLUMNS: tuple[str, ...] = _names_of(CSV_SCOPE)
_REQUEST_COLUMNS: tuple[str, ...] = _names_of(REQUEST_SCOPE)
_ENVELOPE_COLUMNS: tuple[str, ...] = _names_of(ENVELOPE_SCOPE)


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" -- never for ``False``/``0``.

    ``password_enabled`` is legitimately ``FALSE`` and ``cert_*_active`` is legitimately
    ``FALSE`` on most users, and ``additional_credentials_info`` is genuinely empty for a user
    with no AD or WorkDocs credential. Treating any of them as empty would delete a value the
    report publishes.
    """
    return value is None or value == "" or value == {} or value == []


def _require_row(row: dict[str, Any], who: str) -> None:
    """Fail closed when a row is not exactly the CSV's columns, or fills an empty-only one."""
    fields = set(row)
    expected = set(_CSV_COLUMNS)
    if fields != expected:
        raise RenderError(
            f"{RENDER_DIR}: linha de {who} com campos diferentes do CSV emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    empty_only = specification().null_empty_names & fields
    filled = sorted(name for name in empty_only if not _is_empty(row[name]))
    if filled:
        raise RenderError(f"{RENDER_DIR}: colunas vazias-por-contrato receberam valor: {filled}")


def _key_cell(slot: int, chave: AwsAccessKey | None, campo: str) -> str:
    """One ``access_key_N_*`` cell, with the documented ``N/A`` where the slot is empty.

    The ``N/A`` is per-SLOT, not per-row: a user with one key has slot 1 filled and slot 2
    ``N/A``, and writing ``FALSE`` into slot 2 would claim there is a second, inactive key --
    which is a different fact from there being no second key.
    """
    if chave is None:
        return LITERAL_NA
    if campo == "active":
        return "TRUE" if chave.status == "Active" else "FALSE"
    if campo == "last_rotated":
        return chave.create_date
    if campo == "last_used_date":
        return LITERAL_NA if chave.last_used_date is None else chave.last_used_date
    return LITERAL_NA


def _cert_cell(slot: int) -> str:
    """The ``cert_N_*`` cells. The state carries no signing certificate, so these are ``N/A``.

    ``N/A`` and not ``FALSE``: a user with no certificate is not a user with an inactive one.
    The distinction is the same one ``_key_cell`` makes, and filling these with ``FALSE``
    would be asserting a certificate the state does not have.
    """
    return LITERAL_NA


def _user_row(usuario: AwsIamUser) -> dict[str, Any]:
    """The one CSV row of one IAM user."""
    chaves = {slot: usuario.access_keys[slot - 1] if len(usuario.access_keys) >= slot else None for slot in ACCESS_KEY_SLOTS}
    row: dict[str, Any] = {
        "user": usuario.user_name,
        "arn": usuario.arn,
        "user_creation_time": usuario.user_creation_time,
        # CSV booleans are UPPERCASE text -- see the module docstring.
        "password_enabled": "TRUE" if usuario.password_enabled else "FALSE",
        "password_last_used": (
            LITERAL_NO_INFORMATION
            if usuario.password_last_used is None and usuario.password_enabled
            else LITERAL_NA if usuario.password_last_used is None
            else usuario.password_last_used
        ),
        "password_last_changed": LITERAL_NA if usuario.password_last_changed is None else usuario.password_last_changed,
        # A conta root e a UNICA linha com 'not_supported'; para um usuario a pagina nao
        # declara esse literal, entao a coluna fica com o valor derivado da politica.
        "password_next_rotation": "",
        "mfa_active": "TRUE" if usuario.mfa_active else "FALSE",
        "access_key_1_active": _key_cell(1, chaves[1], "active"),
        "access_key_1_last_rotated": _key_cell(1, chaves[1], "last_rotated"),
        "access_key_1_last_used_date": _key_cell(1, chaves[1], "last_used_date"),
        "access_key_1_last_used_region": _key_cell(1, chaves[1], "last_used_region"),
        "access_key_1_last_used_service": _key_cell(1, chaves[1], "last_used_service"),
        "access_key_2_active": _key_cell(2, chaves[2], "active"),
        "access_key_2_last_rotated": _key_cell(2, chaves[2], "last_rotated"),
        "access_key_2_last_used_date": _key_cell(2, chaves[2], "last_used_date"),
        "access_key_2_last_used_region": _key_cell(2, chaves[2], "last_used_region"),
        "access_key_2_last_used_service": _key_cell(2, chaves[2], "last_used_service"),
        "cert_1_active": _cert_cell(1),
        "cert_1_last_rotated": _cert_cell(1),
        "cert_2_active": _cert_cell(2),
        "cert_2_last_rotated": _cert_cell(2),
        "additional_credentials_info": "",
    }
    _require_row(row, f"usuario {usuario.user_name}")
    return row


def _root_row(posture: AwsIdentityPosture) -> dict[str, Any]:
    """The root account's CSV row -- the one row that is not an IAM user.

    Three things here are the root's and not a user's, and each is written the way the columns
    page writes it:

    * ``password_next_rotation`` is ``not_supported``, ALWAYS, and only here;
    * ``password_enabled`` is ``TRUE``: the root has a console password, it just cannot be
      managed as one, which is why the rotation column says ``not_supported`` rather than
      ``N/A``;
    * the ``user`` literal is the unverified one declared at module level.
    """
    root = posture.root_mfa
    ativa = root.root_access_keys > 0
    row: dict[str, Any] = {
        "user": ROOT_ACCOUNT_USER_LITERAL,
        "arn": f"arn:aws:iam::{posture.account_id}:root",
        "user_creation_time": root.user_creation_time,
        "password_enabled": "TRUE",
        "password_last_used": LITERAL_NO_INFORMATION,
        "password_last_changed": LITERAL_NA,
        "password_next_rotation": LITERAL_NOT_SUPPORTED,
        "mfa_active": "TRUE" if root.mfa_active else "FALSE",
        "access_key_1_active": "TRUE" if ativa else "FALSE",
        "access_key_1_last_rotated": LITERAL_NA
        if root.root_access_key_last_rotated is None
        else root.root_access_key_last_rotated,
        "access_key_1_last_used_date": LITERAL_NA,
        "access_key_1_last_used_region": LITERAL_NA,
        "access_key_1_last_used_service": LITERAL_NA,
        "access_key_2_active": "FALSE",
        "access_key_2_last_rotated": LITERAL_NA,
        "access_key_2_last_used_date": LITERAL_NA,
        "access_key_2_last_used_region": LITERAL_NA,
        "access_key_2_last_used_service": LITERAL_NA,
        "cert_1_active": LITERAL_NA,
        "cert_1_last_rotated": LITERAL_NA,
        "cert_2_active": LITERAL_NA,
        "cert_2_last_rotated": LITERAL_NA,
        "additional_credentials_info": "",
    }
    _require_row(row, f"conta root {posture.account_id}")
    return row


def _rows(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Every CSV row of the estate: the root row first, then the users, by account.

    The root row comes FIRST because that is where the report puts it, and a consumer that
    splits by account has to find it without reading the whole file. Within an account the
    order is the model's, and the account order is sorted so the file is byte-stable.
    """
    linhas: list[dict[str, Any]] = []
    for posture in sorted(estate.aws_identity_postures, key=lambda item: item.account_id):
        linhas.append(_root_row(posture))
        linhas.extend(_user_row(usuario) for usuario in posture.users)
    return linhas


def _csv(linhas: list[dict[str, Any]]) -> str:
    """The CSV bytes: documented header in documented order, then one line per row.

    The dialect is declared rather than assumed: UTF-8, no BOM, ``\\n`` line endings and no
    quoting -- and nothing needs quoting because every value here comes from a vocabulary with
    no comma and no quote in it. A user name with a comma would reopen that question, and the
    reason is in the spec's ``unverified`` list.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(_CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    writer.writerows(linhas)
    return buffer.getvalue()


def _request_parameters() -> dict[str, Any]:
    """The action's only request parameter: the format. The action takes no account filter."""
    record: dict[str, Any] = {"report_format": "text/csv"}
    shared_shape = set(record) == set(_REQUEST_COLUMNS)
    if not shared_shape:
        raise RenderError(
            f"{RENDER_DIR}: request-parameters com campos diferentes do conjunto emitido: "
            f"{sorted(set(record) ^ set(_REQUEST_COLUMNS))}"
        )
    return record


def _envelope(csv_text: str, estate: CanonicalEstate) -> dict[str, Any]:
    """The three response elements, with ``Content`` carrying the report in Base64."""
    record: dict[str, Any] = {
        "Content": base64.b64encode(csv_text.encode("utf-8")).decode("ascii"),
        "ReportFormat": "text/csv",
        "GeneratedTime": estate.sim_now.isoformat(),
    }
    if set(record) != set(_ENVELOPE_COLUMNS):
        raise RenderError(
            f"{RENDER_DIR}: envelope com campos diferentes do conjunto emitido: "
            f"{sorted(set(record) ^ set(_ENVELOPE_COLUMNS))}"
        )
    return record


class IamGetCredentialReportRenderer:
    """Renders one CSV credential report per account, plus the decoded and encoded forms."""

    name = "iam_get_credential_report"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/iam_get_credential_report/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []

        linhas = _rows(estate)
        csv_text = _csv(linhas)

        _write_text(target / "credential-report.csv", csv_text, written)
        _write_text(
            target / "credential-report.json",
            json.dumps(linhas, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "response-envelope.json",
            json.dumps(_envelope(csv_text, estate), indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(
            target / "request-parameters.json",
            json.dumps(_request_parameters(), indent=2, ensure_ascii=False) + "\n",
            written,
        )
        _write_text(target / "_provenance.json", self._provenance(estate, linhas, csv_text), written)
        return written

    def _provenance(self, estate: CanonicalEstate, linhas: list[dict[str, Any]], csv_text: str) -> str:
        """The sibling provenance report: the spec, the counts, the literals, the gaps."""
        spec = specification()
        spec_relative = (
            spec.path.relative_to(spec.path.parents[2]).as_posix() if spec.path is not None else SPEC_PATH.name
        )
        postures = sorted(estate.aws_identity_postures, key=lambda item: item.account_id)

        return (
            json.dumps(
                {
                    "kind": "provenance",
                    "surface": SURFACE,
                    "spec": spec_relative,
                    "renderer": self.name,
                    "mechanism": {
                        "kind": "read_api",
                        "action": "iam:GetCredentialReport",
                        "permission": spec.reference.get("permission"),
                        "format": "csv",
                        "artifact_format": "csv",
                        "csv_dialect": (
                            "UTF-8, sem BOM, \\n como fim de linha, delimitador virgula e SEM "
                            "citacao -- nenhum valor deste vocabulario tem virgula ou aspas, entao "
                            "nada precisa de escape. Um usuario com virgula no nome reabriria a "
                            "questao, e o motivo esta na lista unverified da spec."
                        ),
                        "encoding": (
                            "O Content da resposta e o CSV em BASE64. O artifact escreve o CSV "
                            "DECODIFICADO em credential-report.csv e o envelope com o Base64 em "
                            "response-envelope.json, para que a forma da resposta continue "
                            "verificavel sem que o artifact seja duas coisas."
                        ),
                        "scope": "CONTA",
                        "scope_note": (
                            "Um report por conta. A resposta traz GeneratedTime e nao traz o id "
                            "da conta, entao a atribuicao esta em response_order."
                        ),
                    },
                    "counts": {
                        "accounts": len(postures),
                        "rows": len(linhas),
                        "root_rows": sum(1 for linha in linhas if linha["user"] == ROOT_ACCOUNT_USER_LITERAL),
                        "user_rows": sum(1 for linha in linhas if linha["user"] != ROOT_ACCOUNT_USER_LITERAL),
                        "console_users_without_mfa": sum(
                            1
                            for linha in linhas
                            if linha["password_enabled"] == "TRUE"  # noqa: S105 -- nome de COLUNA do CSV
                            and linha["mfa_active"] == "FALSE"
                            and linha["user"] != ROOT_ACCOUNT_USER_LITERAL
                        ),
                        "literal_NA": sum(
                            1 for linha in linhas for value in linha.values() if value == LITERAL_NA
                        ),
                        "literal_not_supported": sum(
                            1 for linha in linhas for value in linha.values() if value == LITERAL_NOT_SUPPORTED
                        ),
                        "literal_no_information": sum(
                            1 for linha in linhas for value in linha.values() if value == LITERAL_NO_INFORMATION
                        ),
                        "cert_columns_all_NA": all(
                            linha[campo] == LITERAL_NA
                            for linha in linhas
                            for campo in ("cert_1_active", "cert_1_last_rotated", "cert_2_active", "cert_2_last_rotated")
                        ),
                    },
                    "columns": {set_.name: [column.name for column in set_.columns] for set_ in spec.sets},
                    "response_order": [
                        {
                            "account": posture.account_id,
                            "rows": [
                                index for index, linha in enumerate(linhas) if _linha_da_conta(linha, posture)
                            ],
                        }
                        for posture in postures
                    ],
                    "model_gaps": [
                        {
                            "field": "signing certificate (cert_1_*, cert_2_*)",
                            "reason": (
                                "AUSENTE DE MODELO. O estado nao carrega certificado de assinatura, "
                                "e por isso as quatro colunas vao N/A. N/A e nao FALSE: um usuario "
                                "SEM certificado nao e um usuario com certificado inativo, e e a "
                                "mesma distincao que a coluna access_key_N_last_rotated faz com o "
                                "slot vazio."
                            ),
                        },
                        {
                            "field": "access_key_N_last_used_region / access_key_N_last_used_service",
                            "reason": (
                                "AUSENTE DE MODELO. O estado carrega a DATA do ultimo uso e nao a "
                                "regiao nem o servico, entao as duas colunas vao N/A. Isso nao "
                                "confunde com 'chave nunca usada', que e tambem N/A: e por isso "
                                "que o estado nao afirma nada sobre regiao de uso, em vez de "
                                "preencher uma regiao que seria inventada."
                            ),
                        },
                        {
                            "field": "password_next_rotation (linhas de usuario)",
                            "reason": (
                                "VAZIO POR CONTRATO nas linhas de usuario. A pagina de colunas "
                                "declara 'not_supported' para a CONTA ROOT e nao declara esse "
                                "literal para usuario nenhum. O estado carrega a idade da senha "
                                "(password_last_changed) e nao um prazo de rotacao configurado, "
                                "entao a coluna fica vazia em vez de receber uma data derivada -- "
                                "que seria uma rotacao que o estado nao descreve."
                            ),
                        },
                        {
                        "field": "additional_credentials_info",
                            "reason": (
                                "VAZIO POR CONTRATO. A coluna se aplica a usuario com "
                                "credencial AD ou WorkDocs, e o estado nao modela nenhum dos "
                                "dois. A pagina diz que a coluna vem vazia para quem nao tem "
                                "esse tipo de credencial."
                            ),
                        },
                    ],
                    "not_generated": [],
                    "unverified_emitted": [
                        {
                            "field": "user (linha da conta root)",
                            "value": ROOT_ACCOUNT_USER_LITERAL,
                            "reason": (
                                "NAO COMPROVADO. Nem API_GetCredentialReport.html nem a pagina de "
                                "colunas do IAM User Guide, ambas lidas em 2026-10-18, declaram o "
                                "valor desta coluna na linha da conta root. A linha e emitida "
                                "porque sem ela a regra root-account-mfa-enabled nao teria linha "
                                "alguma onde ler o MFA da raiz. Um consumidor que compare esta "
                                "coluna contra a string precisa saber que ela nao foi conferida "
                                "contra uma pagina oficial."
                            ),
                        }
                    ],
                    "rules_read": {
                        RULE_ROOT_MFA: (
                            "A regra le o MFA da CONTA ROOT, e a unica linha do report que o "
                            "publica. O avaliador e render/_config_evaluators."
                            "evaluate_root_account_mfa_enabled -- o mesmo que a tela de Config "
                            "chama. Uma conta cujo root tem MFA e aprovada mesmo que um usuario "
                            "de servico nao tenha, e o estate tem contas em que as duas coisas "
                            "discordam justamente para que essa troca nao possa passar."
                        ),
                        "console_users_without_mfa": (
                            "A contagem que uma ferramenta de postura REAL le: usuario com "
                            "senha (tem console) e sem MFA. E o cruzamento de password_enabled e "
                            "mfa_active linha a linha, e por isso que um usuario de API sem senha "
                            "NAO entra: nao ha tela para proteger."
                        ),
                    },
                    "evaluated_rule_now": {
                        regra: {
                            "account": posture.account_id,
                            "contributors": list(
                                IAM_RULE_EVALUATORS[regra](posture, estate.sim_now).contributors
                            ),
                        }
                        for regra in (RULE_ROOT_MFA,)
                        for posture in postures
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )


def _linha_da_conta(linha: dict[str, Any], posture: AwsIdentityPosture) -> bool:
    """Whether a CSV row belongs to ``posture``.

    The root row names the account in its ARN; a user row carries the account in its ARN too.
    Both go through the ARN, because the ``user`` column is the one column this artifact cannot
    be trusted to join on -- its root value is unverified.
    """
    return linha["arn"].startswith(f"arn:aws:iam::{posture.account_id}:")


def _write_text(path: Path, text: str, written: list[Path]) -> Path:
    """Write one artifact as UTF-8, newline-terminated, and record it exactly once."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)
    return path