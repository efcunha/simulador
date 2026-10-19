"""Golden tests for the Increment 4 IAM surface: ``aws/iam-get-account-password-policy``.

The point of this module is to confront the DELIVERED artifact with its spec -- names, values
and the empty contract -- and to hold the judgement calls this surface invites getting
quietly wrong:

1. **``ExpirePasswords`` is DERIVED, and the artifact may never contradict ``MaxPasswordAge``.
   The type page defines the member by means of another: "Returns true if MaxPasswordAge
   contains a value greater than 0. Returns false if MaxPasswordAge is 0 or not present."
   Two independent fields would let the artifact publish ``ExpirePasswords: true`` beside an
   absent ``MaxPasswordAge`` -- a state the AWS does not return. The test re-derives the
   member from the published ``MaxPasswordAge`` and fails on any disagreement;
2. **``HardExpiry`` is NOT "expiry enabled".** It answers whether the user may change their
   own expired password in the console. The official Sample Response carries ``MaxPasswordAge
   90`` with ``HardExpiry false``, so a reader who treats ``HardExpiry`` as the expiry switch
   would call a 90-day-rotation account one that never expires;
3. **the response cannot name its account, and that is the DOCUMENT's shape, not a gap.**
   The action's Sample Request carries no parameter and ``PasswordPolicy`` has no member
   naming the account, so attribution has to live outside the response. The test proves the
   map is present, is total, and is in the same order the responses are written;
4. **the published policy is the one the managed rule reads.** ``iam-password-policy``
   compares these members with the rule's own parameters, so the artifact and the evaluator
   must not read the estate through two different sets of fields;
5. **the account with NO expiry publishes ``MaxPasswordAge`` null, not ``0``** -- the page
   describes "0 or not present" as one state, and ``0`` would additionally claim a zero-day
   term that the page never names.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import matrix
from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render import _config_evaluators as ev
from tools.synthetic_clouds.render import iam_get_account_password_policy as mod
from tools.synthetic_clouds.render.base import registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The spec file, cited LITERALLY: ``report.golden_gaps`` requires a test to name the spec, not
#: to reach it through a variable, so that forgetting the citation shows up as a failure.
SPEC_FILE = "iam-get-account-password-policy.schema.json"

RESPONSE_SCOPE = "get-account-password-policy-response"

#: The ten members the type page documents, in the order it lists them.
_DEZ_MEMBROS = (
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
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_spec(_REPO_ROOT / "specs" / "aws" / SPEC_FILE)


@pytest.fixture(scope="module")
def entregues(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Render the surface once and return the delivered tree."""
    destino = tmp_path_factory.mktemp(mod.RENDER_DIR)
    mod.IamGetAccountPasswordPolicyRenderer().render(estate, destino)
    return destino / mod.RENDER_DIR


def _respostas(entregues: Path) -> list[dict[str, Any]]:
    return json.loads(
        (entregues / "get-account-password-policy-response.json").read_text(encoding="utf-8")
    )


def _provenance(entregues: Path) -> dict[str, Any]:
    return json.loads((entregues / "_provenance.json").read_text(encoding="utf-8"))


def test_a_superficie_esta_registrada_na_matriz() -> None:
    coverage = matrix.coverage_for(mod.SURFACE)
    assert coverage is not None, mod.SURFACE
    assert coverage.renderer == "iam_get_account_password_policy", mod.SURFACE
    assert mod.SURFACE in matrix.declared_surfaces()
    assert "iam_get_account_password_policy" in registered_names()


def test_a_spec_publica_os_dez_membros_da_pagina_do_tipo(spec: Any) -> None:
    """The set is the documented ``PasswordPolicy``, member for member -- not nine.

    Nine would be the count of the fields that are switches and numbers. The type page lists
    ten, and the tenth is the derived ``ExpirePasswords``.
    """
    assert spec.surface == mod.SURFACE
    nomes = [column.name for column in spec.columns_for(RESPONSE_SCOPE)]
    assert tuple(nomes) == _DEZ_MEMBROS
    assert len(nomes) == 10
    assert all(column.belongs_to_schema for column in spec.columns_for(RESPONSE_SCOPE))


def test_o_artefato_confere_com_a_spec(
    spec: Any, estate: CanonicalEstate, entregues: Path
) -> None:
    """Names, values and the empty contract, against the delivered bytes."""
    respostas = _respostas(entregues)
    assert len(respostas) == len(estate.aws_identity_postures) > 0
    colunas = [column.name for column in spec.columns_for(RESPONSE_SCOPE)]
    for indice, resposta in enumerate(respostas):
        assert list(resposta) == colunas, f"resposta {indice}"

    # A conferencia de conjunto roda sobre os BYTES gravados, nao sobre a memoria do renderer:
    # e a leitura da resposta inteira (todas as contas num arquivo) que o auditor avalia.
    achado = check_artifact(spec, entregues / "get-account-password-policy-response.json")
    assert is_faithful(achado), achado


def test_expire_passwords_e_derivado_e_nao_pode_contradizer_max_password_age(
    estate: CanonicalEstate, entregues: Path
) -> None:
    """Re-derive the member from the published ``MaxPasswordAge`` and fail on disagreement.

    This is the whole reason ``expire_passwords`` is a property on the model instead of a
    field: with two fields the artifact could publish ``ExpirePasswords: true`` next to an
    absent ``MaxPasswordAge``, a state the AWS does not return.
    """
    respostas = _respostas(entregues)
    assert respostas, "sem resposta nao ha o que conferir"
    for indice, resposta in enumerate(respostas):
        max_age = resposta["MaxPasswordAge"]
        esperado = bool(max_age and max_age > 0)
        assert resposta["ExpirePasswords"] is esperado, (
            f"resposta {indice}: ExpirePasswords={resposta['ExpirePasswords']} com "
            f"MaxPasswordAge={max_age!r}; a pagina do tipo define um pelo outro"
        )


def test_a_conta_sem_expiracao_publica_nulo_e_nao_zero(
    estate: CanonicalEstate, entregues: Path
) -> None:
    """``MaxPasswordAge`` null, not ``0`` -- and never a zero-day term.

    The page names "0 or not present" as one state. Publishing ``0`` would additionally claim
    a zero-day password term, which the page never names and which no account has.
    """
    respostas = _respostas(entregues)
    sem_expiracao = [r for r in respostas if r["MaxPasswordAge"] is None]
    assert sem_expiracao, (
        "o estado nao tem nenhuma conta sem expiracao, entao o caso 'MaxPasswordAge ausente' "
        "deixaria de ser conferido -- e ele e o estado que a pagina descreve"
    )
    for indice, resposta in enumerate(sem_expiracao):
        assert resposta["MaxPasswordAge"] is None, indice
        assert resposta["ExpirePasswords"] is False, indice


def test_a_resposta_nao_nomeia_a_conta_e_a_atribuicao_esta_no_lado_de_fora(
    estate: CanonicalEstate, entregues: Path
) -> None:
    """The response is account-identical; the map that fixes which account is beside it.

    Not a gap and not a nicety: ``PasswordPolicy`` has no member naming the account and the
    Sample Request carries no parameter, so a reader of the response alone cannot know whose
    policy it is. That is why the map is total, ordered, and in the artifact.
    """
    respostas = _respostas(entregues)
    mapa = _provenance(entregues)["response_order"]

    assert len(mapa) == len(respostas), "o mapa tem de cobrir todas as respostas"
    assert [entrada["index"] for entrada in mapa] == list(range(len(respostas)))
    assert [entrada["account"] for entrada in mapa] == sorted(
        postura.account_id for postura in estate.aws_identity_postures
    )

    # O corpo nao pode carregar nenhum membro que nomeie a conta: um_member assim seria um
    # campo inventado, e o auditor de conjunto acima ja teria acusado o conjunto.
    for indice, resposta in enumerate(respostas):
        assert not any(
            chave.lower().endswith("accountid") or chave.lower() == "account"
            for chave in resposta
        ), f"resposta {indice} nomeia a conta, e o contrato nao declara tal membro"


def test_o_pedido_desta_superficie_nao_tem_credencial(spec: Any) -> None:
    """The contrast that names the surface: an IAM read carries no credential.

    The FinOps diagnostic API fills ``request_parameters`` with an access token. Here the
    read is of an account's own policy, the caller is the account, and there is no token --
    so neither the spec nor the artifact may name one.
    """
    nomes = {column.name.lower() for column in spec.columns}
    for proibido in ("accesstoken", "apikey", "authorization", "bearer", "token"):
        assert proibido not in nomes, f"a spec declara um campo de credencial: {proibido}"


def test_a_politica_publicada_e_a_mesma_que_a_regra_leh(
    estate: CanonicalEstate, entregues: Path
) -> None:
    """The artifact and ``iam-password-policy`` must not read the estate through two fields.

    The managed rule compares the policy against its own parameters. If the published artifact
    and the evaluator read different members, a posture screen reading the artifact would
    disagree with the Config verdict about the same account.
    """
    respostas = _respostas(entregues)
    for postura, resposta in zip(
        sorted(estate.aws_identity_postures, key=lambda p: p.account_id),
        respostas,
        strict=True,
    ):
        politica = postura.password_policy
        assert resposta["MinimumPasswordLength"] == politica.minimum_password_length
        assert resposta["RequireSymbols"] == politica.require_symbols
        assert resposta["RequireNumbers"] == politica.require_numbers
        assert resposta["RequireUppercaseCharacters"] == politica.require_uppercase
        assert resposta["RequireLowercaseCharacters"] == politica.require_lowercase
        assert resposta["AllowUsersToChangePassword"] == politica.allow_users_to_change_password
        assert resposta["HardExpiry"] == politica.hard_expiry
        assert resposta["MaxPasswordAge"] == politica.max_password_age_days
        # E a regra le o MESMO estado, pelo mesmo avaliador que a tela de Config usa.
        veredito = ev.evaluate_iam_password_policy(postura)
        if veredito.compliance_type == ev.NON_COMPLIANT:
            # Toda violacao nomeia um requisito que a resposta publica como falso/curto.
            for requisito in veredito.contributors:
                if requisito == "minimumPasswordLength":
                    assert resposta["MinimumPasswordLength"] < 14
                else:
                    chave = {
                        "requireSymbols": "RequireSymbols",
                        "requireNumbers": "RequireNumbers",
                        "requireUppercaseCharacters": "RequireUppercaseCharacters",
                        "requireLowercaseCharacters": "RequireLowercaseCharacters",
                    }[requisito]
                    assert resposta[chave] is False


def test_a_conta_fraca_e_a_conta_forte_produzem_vereditos_opostos(
    estate: CanonicalEstate, entregues: Path
) -> None:
    """Both sides of the rule exist in the same state, or the artifact teaches nothing.

    A surface where every account is compliant is indistinguishable from one that never
    looked at the password policy.
    """
    vereditos = {
        postura.account_id: ev.evaluate_iam_password_policy(postura).compliance_type
        for postura in estate.aws_identity_postures
    }
    assert set(vereditos.values()) == {ev.COMPLIANT, ev.NON_COMPLIANT}, vereditos
    respostas = _respostas(entregues)
    for postura, resposta in zip(
        sorted(estate.aws_identity_postures, key=lambda p: p.account_id),
        respostas,
        strict=True,
    ):
        curto = resposta["MinimumPasswordLength"] < 14
        assert (ev.NON_COMPLIANT if curto else ev.COMPLIANT) == ev.evaluate_iam_password_policy(
            postura
        ).compliance_type