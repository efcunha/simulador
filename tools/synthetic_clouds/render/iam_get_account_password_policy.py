"""AWS IAM ``GetAccountPasswordPolicy`` renderer -- os dez membros da politica de senha da conta.

Projects the canonical estate's identity postures into the **10 documented fields** of
``specs/aws/iam-get-account-password-policy.schema.json`` -- os membros de
``PasswordPolicy``, que a acao lista como o unico elemento de resposta.

WHY THIS SURFACE EXISTS
-----------------------
``iam-password-policy`` is the managed rule that compares each of these members against the
rule's own integer parameters. Until the Increment 4 the estate carried no identity entity at
all, so the rule was ``INSUFFICIENT_DATA`` for a MODEL reason: not "we do not know whether the
password is strong", but "we have no password policy to look at". This surface is where the
fact the rule reads becomes a published reading.

IT IS ONE RESPONSE PER ACCOUNT, NOT PER (ACCOUNT, REGION)
---------------------------------------------------------
IAM is global. The ``Sample Request`` on the action's page carries no parameter at all --
no account id, no region -- and ``PasswordPolicy`` has no member naming the account. So the
response cannot name its own account, and an artifact holding several accounts would be
ambiguous without something the documentation does not provide.

That is why the attribution is written into the artifact's ``response_order``, in the
provenance file and never in the response: a consumer joins a response to its account by
position, and the position map is shipped beside the data.

``ExpirePasswords`` IS NOT INVENTED
------------------------------------
The type page does not describe ``ExpirePasswords`` as a switch. It says the member "Returns
true if MaxPasswordAge contains a value greater than 0. Returns false if MaxPasswordAge is 0
or not present." This renderer therefore publishes ``model.iam.AwsPasswordPolicy``'s
``expire_passwords`` property, which is that derivation, and never an independent flag. Two
independent fields would let the artifact claim ``ExpirePasswords: true`` next to an absent
``MaxPasswordAge``, which the AWS does not return.

WHAT IS NEVER EMITTED
---------------------
Nothing in this response set is null-empty, and nothing is omitted. All ten members are
``Required: No``, which the documentation states without a presence condition; the renderer
emits a value for each. The one member whose absence the page DOES describe is
``MaxPasswordAge`` -- "0 or not present" -- and a policy with no expiry publishes it as
``null``, with ``ExpirePasswords`` false derived from that null. A document with a missing
member would assert a shape the type page does not publish; a document with ``0`` would assert
an expiry of zero days, which is not what the page means.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.synthetic_clouds.fidelity.spec import SurfaceSpec, load_spec
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.model.iam import AwsIdentityPosture
from tools.synthetic_clouds.render._config_evaluators import IAM_RULE_EVALUATORS, RULE_PASSWORD_POLICY
from tools.synthetic_clouds.render.base import RenderError

SURFACE = "aws/iam-get-account-password-policy"
RENDER_DIR = "iam_get_account_password_policy"

RESPONSE_SCOPE = "get-account-password-policy-response"

SPEC_PATH = Path(__file__).resolve().parents[3] / "specs" / "aws" / "iam-get-account-password-policy.schema.json"


def specification() -> SurfaceSpec:
    """Load the cited specification for ``aws/iam-get-account-password-policy``."""
    return load_spec(SPEC_PATH)


def _names_of(scope: str) -> tuple[str, ...]:
    """Return a set's column names in documentation order, refusing to drop one.

    Same contract as the sibling surfaces: a column the documentation describes without
    contracting it must never reach an artifact, and a documented column must never be
    dropped. Both are hard errors.
    """
    columns = specification().columns_for(scope)
    refused = tuple(column.name for column in columns if not column.belongs_to_schema)
    if refused:
        raise RenderError(
            f"{RENDER_DIR}: o conjunto {scope!r} da especificacao {SURFACE} marcou colunas "
            f"documentadas como fora do formato: {list(refused)}"
        )
    return tuple(column.name for column in columns)


#: The single documented set, in documentation order -- derived, not retyped.
_RESPONSE_COLUMNS: tuple[str, ...] = _names_of(RESPONSE_SCOPE)

#: The model facts this set may project. A non-null value anywhere else is a value the
#: canonical model does not carry -- ``require_projection`` fails closed on it.
_RESPONSE_PROJECTED: frozenset[str] = frozenset(
    {
        "AllowUsersToChangePassword",
        "ExpirePasswords",
        "HardExpiry",
        "MaxPasswordAge",
        "MinimumPasswordLength",
        "PasswordReusePrevention",
        "RequireLowercaseCharacters",
        "RequireNumbers",
        "RequireSymbols",
        "RequireUppercaseCharacters",
    }
)


def _is_empty(value: Any) -> bool:
    """True when ``value`` is this fixture's shape for "no value" (never for zero or false).

    Both are real values here: ``MinimumPasswordLength`` is never 0 (the page publishes a
    minimum of 6), ``MaxPasswordAge`` is 0 in the "no expiry" reading, and every
    ``Require*`` is legitimately ``false`` on a weak policy. Treating either as empty would
    erase the posture a Config rule reads.
    """
    return value is None or value == "" or value == {} or value == []


def _require_projection(record: dict[str, Any], where: str) -> None:
    """Fail closed when the document is not exactly the set's members, or fills a gap."""
    fields = set(record)
    expected = set(_RESPONSE_COLUMNS)
    if fields != expected:
        raise RenderError(
            f"{RENDER_DIR}: {where} com campos diferentes do conjunto emitido: "
            f"sobram={sorted(fields - expected)} faltam={sorted(expected - fields)}"
        )
    null_empty = specification().null_empty_names
    filled = sorted(name for name in null_empty & fields if not _is_empty(record[name]))
    if filled:
        raise RenderError(f"{RENDER_DIR}: colunas null-empty receberam valor: {filled}")
    invented = sorted(name for name in fields if not _is_empty(record[name]) and name not in _RESPONSE_PROJECTED)
    if invented:
        raise RenderError(
            f"{RENDER_DIR}: {where} preencheu colunas sem fonte no modelo canonico "
            f"(lacuna, nao valor): {invented}"
        )


def _password_policy(posture: AwsIdentityPosture) -> dict[str, Any]:
    """Return the documented 10-member ``PasswordPolicy`` of one account."""
    policy = posture.password_policy
    record: dict[str, Any] = {
        "AllowUsersToChangePassword": policy.allow_users_to_change_password,
        # Derived, per the type page's own wording -- see the module docstring.
        "ExpirePasswords": policy.expire_passwords,
        "HardExpiry": policy.hard_expiry,
        # ``None`` is the state the page calls "MaxPasswordAge is 0 or not present": a policy
        # whose passwords never expire. It is the only member this surface emits as null, and
        # ``ExpirePasswords`` is false because of it.
        "MaxPasswordAge": policy.max_password_age_days,
        "MinimumPasswordLength": policy.minimum_password_length,
        "PasswordReusePrevention": policy.password_reuse_prevention,
        "RequireLowercaseCharacters": policy.require_lowercase,
        "RequireNumbers": policy.require_numbers,
        "RequireSymbols": policy.require_symbols,
        "RequireUppercaseCharacters": policy.require_uppercase,
    }
    _require_projection(record, f"PasswordPolicy de {posture.account_id}")
    return record


def _account_order(estate: CanonicalEstate) -> list[dict[str, Any]]:
    """Map each response to its account, by position, for the provenance document.

    The order is ``(account_id)`` sorted, so it is total and deterministic, and the map is
    shipped beside the data because the response itself cannot say which account it is.
    """
    postures = sorted(estate.aws_identity_postures, key=lambda posture: posture.account_id)
    return [{"index": index, "account": posture.account_id} for index, posture in enumerate(postures)]


class IamGetAccountPasswordPolicyRenderer:
    """Renders the account password policy of every AWS account in the estate."""

    name = "iam_get_account_password_policy"

    def render(self, estate: CanonicalEstate, out_dir: Path) -> list[Path]:
        """Write the fixtures under ``out_dir/iam_get_account_password_policy/``; return written paths."""
        target = out_dir / RENDER_DIR
        written: list[Path] = []

        responses: list[dict[str, Any]] = []
        for posture in sorted(estate.aws_identity_postures, key=lambda item: item.account_id):
            record = _password_policy(posture)
            responses.append(record)

        _write_text(
            target / "get-account-password-policy-response.json",
            json.dumps(responses, indent=2, ensure_ascii=False) + "\n",
            written,
        )
        written.append(self._write_provenance(target, estate, responses, written))
        return written

    def _write_provenance(
        self, target: Path, estate: CanonicalEstate, responses: list[dict[str, Any]], written: list[Path]
    ) -> Path:
        """Write the sibling provenance report: the spec, the mechanism, the counts, the gaps."""
        spec = specification()
        if spec.path is None:  # pragma: no cover - load_spec sempre anexa o caminho
            raise RenderError(f"{SURFACE}: a especificacao foi carregada sem caminho de origem")
        spec_relative = spec.path.relative_to(spec.path.parents[2]).as_posix()
        posture_por_conta = {p.account_id: p for p in estate.aws_identity_postures}

        counts: dict[str, Any] = {
            "responses": len(responses),
            "accounts_total": len(estate.aws_identity_postures),
        }
        for member in _RESPONSE_COLUMNS:
            counts[f"true_{member}"] = sum(1 for record in responses if record[member] is True)

        return _write_text(
            target / "_provenance.json",
            json.dumps(
                {
                    "kind": "provenance",
                    "surface": SURFACE,
                    "spec": spec_relative,
                    "renderer": self.name,
                    "mechanism": {
                        "kind": "read_api",
                        "action": "iam:GetAccountPasswordPolicy",
                        "format": "xml",
                        "artifact_format": "json",
                        "scope": "account",
                        "scope_note": (
                            "IAM e global e a acao nao leva nenhum parametro de servico -- o "
                            "Sample Request da pagina e '?Action=GetAccountPasswordPolicy&Version="
                            "2010-05-08', sem conta e sem regiao. E PasswordPolicy nao tem membro "
                            "que nomeie a conta, entao a resposta e IDENTICA em relacao a conta e a "
                            "atribuicao fica no response_order deste relatorio."
                        ),
                        "permission": spec.reference.get("permission"),
                        "boolean_representation": (
                            "A Sample Response oficial escreve true/false dentro de um envelope XML. "
                            "O tipo publicado e 'Boolean' sem fixar representacao textual. O "
                            "artefacto emite true/false, que e o booleano correspondente em JSON, e "
                            "a conversao esta declarada na spec."
                        ),
                    },
                    "counts": counts,
                    "columns": {
                        column_set.name: [column.name for column in column_set.columns] for column_set in spec.sets
                    },
                    "response_order": _account_order(estate),
                    "model_gaps": [
                        {
                            "field": "MaxPasswordAge",
                            "reason": (
                                "AUSENTE POR CONTRATO, E PUBLICAVEL. A pagina do tipo descreve a "
                                "ausencia como parte do estado ('MaxPasswordAge is 0 or not "
                                "present'), e ExpirePasswords e definido a partir dela. Uma "
                                "politica sem expiracao publica MaxPasswordAge nulo e "
                                "ExpirePasswords falso; emitir 0 affirmaria um prazo de zero "
                                "dias, que nao e o estado que a pagina nomeia."
                            ),
                        },
                        {
                            "field": "account_id",
                            "reason": (
                                "AUSENTE DO CONTRATO DESTA SUPERFICIE, E DECLARADO POR ISSO. Nem "
                                "PasswordPolicy nem a resposta da acao carregam o id da conta, e o "
                                "estado nao modela a requisicao que disparou a leitura. O mapa "
                                "conta -> indice da resposta esta em response_order."
                            ),
                        },
                    ],
                    "not_generated": [],
                    "derivations": [
                        {
                            "field": "ExpirePasswords",
                            "reason": (
                                "DERIVADO, NAO INDEPENDENTE. A pagina do tipo define o membro por "
                                "meio de outro: 'Returns true if MaxPasswordAge contains a value "
                                "greater than 0. Returns false if MaxPasswordAge is 0 or not "
                                "present.' O valor publicado vem da propriedade "
                                "AwsPasswordPolicy.expire_passwords, e por isso nao pode "
                                "contradizer MaxPasswordAge na mesma resposta."
                            ),
                        },
                        {
                            "field": "HardExpiry",
                            "reason": (
                                "NAO E 'expiracao ativada'. HardExpiry responde se o usuario pode "
                                "trocar a propria senha expirada pelo console apos expirar; quem "
                                "responde se a senha expira e MaxPasswordAge, via ExpirePasswords. A "
                                "Sample Response oficial traz os dois com MaxPasswordAge 90 e "
                                "HardExpiry false, entao os dois sao verdadeiros ao mesmo tempo."
                            ),
                        },
                    ],
                    "rules_read": {
                        RULE_PASSWORD_POLICY: (
                            "A regra compara MinimumPasswordLength com o parametro "
                            "minimumPasswordLength da regra (um PISO) e os quatro Require* com os "
                            "parametros inteiros da regra, onde -1 significa 'nao avaliar'. O "
                            "avaliador que faz essa comparacao e "
                            "render/_config_evaluators.evaluate_iam_password_policy -- o mesmo "
                            "que o diagnostico retrospectivo chama, e nao uma segunda implementacao "
                            "aqui."
                        ),
                    },
                    "evaluated_rule_now": {
                        regra: {
                            "account": posture.account_id,
                            "contributors": list(
                                IAM_RULE_EVALUATORS[regra](posture, estate.sim_now).contributors
                            ),
                        }
                        for regra in (RULE_PASSWORD_POLICY,)
                        for posture in sorted(
                            posture_por_conta.values(), key=lambda item: item.account_id
                        )
                    },
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            written,
        )


def _write_text(path: Path, text: str, written: list[Path]) -> Path:
    """Write one artifact as UTF-8, newline-terminated, and record it exactly once.

    The trailing newline is what makes a rebuild byte-identical, and the de-duplication is
    what keeps the returned path list total without repeating an entry when a caller writes
    the same path twice.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if path not in written:
        written.append(path)
    return path
