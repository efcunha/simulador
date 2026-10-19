"""Golden tests for the Increment 4 IAM identity surface: ``aws/iam-get-credential-report``.

This is the only **CSV** contract in the repository, and every difference from the other 43
surfaces is a place a consumer can quietly get the wrong answer. So the tests here are mostly
about the things that LOOK like typography:

1. **booleans are ``TRUE``/``FALSE``, uppercase.** Every other artifact in this repo is JSON
   and spells them ``true``/``false``. A consumer comparing with ``true`` reads every row in
   the account as false -- and since this surface exists precisely to find console users
   without MFA, that mistake inverts the finding;
2. **the header is mandatory and ordered.** A CSV without the documented header in the
   documented order is not deterministically parseable, so the header is asserted against the
   spec rather than against a literal in this file;
3. **the literals are STATES.** ``N/A`` means the object does not exist, ``not_supported``
   appears ONLY on the root row, and ``no_information`` is a third thing again. Translating any
   of them to ``null`` erases "this user has no password";
4. **two access keys per user, never three.** There is no ``access_key_3_*`` column, so the row
   list is not "every key in the account";
5. **the root row is first and it is the only one that is not a user.** It is what
   ``root-account-mfa-enabled`` reads, and its row name is the one value here nobody verified
   against an official page -- so the provenance has to say so;
6. **the consumer's cross-check works.** ``password_enabled and not mfa_active`` has to find
   console users and EXCLUDE API-only users, because that is the finding a posture tool makes.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
from typing import Any

import pytest

from tools.synthetic_clouds.fidelity import matrix
from tools.synthetic_clouds.fidelity.checker import check_artifact, is_faithful
from tools.synthetic_clouds.fidelity.spec import load_spec
from tools.synthetic_clouds.generate.estate_builder import build_estate
from tools.synthetic_clouds.model.estate import CanonicalEstate
from tools.synthetic_clouds.render import iam_get_credential_report as mod
from tools.synthetic_clouds.render.base import registered_names

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: The spec file, cited LITERALLY: ``report.golden_gaps`` requires a test to name the spec.
SPEC_FILE = "iam-get-credential-report.schema.json"

CSV_SCOPE = "get-credential-report-response"

#: The 23 columns, in the order the User Guide lists them.
_VIGESIM_COLUNAS = (
    "user",
    "arn",
    "user_creation_time",
    "password_enabled",
    "password_last_used",
    "password_last_changed",
    "password_next_rotation",
    "mfa_active",
    "access_key_1_active",
    "access_key_1_last_rotated",
    "access_key_1_last_used_date",
    "access_key_1_last_used_region",
    "access_key_1_last_used_service",
    "access_key_2_active",
    "access_key_2_last_rotated",
    "access_key_2_last_used_date",
    "access_key_2_last_used_region",
    "access_key_2_last_used_service",
    "cert_1_active",
    "cert_1_last_rotated",
    "cert_2_active",
    "cert_2_last_rotated",
    "additional_credentials_info",
)


@pytest.fixture(scope="module")
def estate() -> CanonicalEstate:
    return build_estate(seed=123, profile="small", currency="USD")


@pytest.fixture(scope="module")
def spec() -> Any:
    return load_spec(_REPO_ROOT / "specs" / "aws" / SPEC_FILE)


@pytest.fixture(scope="module")
def entregues(estate: CanonicalEstate, tmp_path_factory: pytest.TempPathFactory) -> Path:
    destino = tmp_path_factory.mktemp(mod.RENDER_DIR)
    mod.IamGetCredentialReportRenderer().render(estate, destino)
    return destino / mod.RENDER_DIR


def _csv_rows(entregues: Path) -> list[dict[str, str]]:
    texto = (entregues / "credential-report.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(texto, newline="")))


def _provenance(entregues: Path) -> dict[str, Any]:
    return json.loads((entregues / "_provenance.json").read_text(encoding="utf-8"))


def test_a_superficie_esta_registrada_na_matriz() -> None:
    coverage = matrix.coverage_for(mod.SURFACE)
    assert coverage is not None, mod.SURFACE
    assert coverage.renderer == "iam_get_credential_report", mod.SURFACE
    assert mod.SURFACE in matrix.declared_surfaces()
    assert "iam_get_credential_report" in registered_names()


def test_a_spec_tem_as_vinte_e_tras_colunas_na_ordem_da_pagina(spec: Any) -> None:
    nomes = tuple(column.name for column in spec.columns_for(CSV_SCOPE))
    assert nomes == _VIGESIM_COLUNAS
    assert len(nomes) == 23
    assert all(column.belongs_to_schema for column in spec.columns_for(CSV_SCOPE))


def test_o_cabecalho_e_derivado_da_spec_e_nao_redigitado(spec: Any, entregues: Path) -> None:
    """The header is the contract; typing it here would let the two drift apart silently."""
    primeira = (entregues / "credential-report.csv").read_text(encoding="utf-8").splitlines()[0]
    esperado = ",".join(column.name for column in spec.columns_for(CSV_SCOPE))
    assert primeira == esperado
    assert mod._CSV_COLUMNS == _VIGESIM_COLUNAS


def test_o_artefato_confere_com_a_spec(spec: Any, entregues: Path) -> None:
    achado = check_artifact(spec, entregues / "credential-report.json", scope=CSV_SCOPE)
    assert is_faithful(achado), achado


def test_os_booleanos_sao_maiusculos_e_nunca_json(entregues: Path) -> None:
    """``TRUE``/``FALSE``, and never the JSON spelling.

    This is the one that inverts a finding silently: a consumer comparing with ``true`` sees
    every row as false, so "console user without MFA" becomes "no console user at all".

    ``N/A`` is also legal in an ``access_key_N_active`` cell -- and only there: it means the
    slot is EMPTY, which is a different fact from a slot holding an inactive key.
    """
    linhas = _csv_rows(entregues)
    assert linhas
    booleanas = ("password_enabled", "mfa_active")
    for linha in linhas:
        for coluna in booleanas:
            assert linha[coluna] in {"TRUE", "FALSE"}, (coluna, linha[coluna])
        for coluna in ("access_key_1_active", "access_key_2_active"):
            assert linha[coluna] in {"TRUE", "FALSE", mod.LITERAL_NA}, (coluna, linha[coluna])

    # e nenhum booleano JSON sobreviveu em lugar nenhum do arquivo.
    bruto = (entregues / "credential-report.csv").read_text(encoding="utf-8")
    for grafia in (",true,", ",false,"):
        assert grafia not in bruto, f"o CSV trouxe o booleano JSON {grafia!r}"


def test_os_literais_sao_estados_e_nao_ausencias(entregues: Path) -> None:
    """``N/A``, ``not_supported`` and ``no_information`` each mean something, and differ.

    ``N/A`` = the object does not exist; ``not_supported`` = only ever on the root row;
    ``no_information`` = the password never signed in. Collapsing any of them into ``null``
    would erase "this user has no password", which is the finding.
    """
    linhas = _csv_rows(entregues)
    assert any(
        mod.LITERAL_NA in linha.values() for linha in linhas
    ), "nenhuma celula N/A: o literal documentado sumiu"

    # not_supported: SO na linha da conta root, e em toda linha de conta root
    com_ns = [linha for linha in linhas if any(v == mod.LITERAL_NOT_SUPPORTED for v in linha.values())]
    assert com_ns, "nenhuma linha com not_supported: o literal documentado sumiu"
    for linha in com_ns:
        assert linha["user"] == mod.ROOT_ACCOUNT_USER_LITERAL, linha["user"]
        assert linha["password_next_rotation"] == mod.LITERAL_NOT_SUPPORTED

    # no_information: so onde nao ha data de uso de senha, e nunca na coluna de senha ausente
    for linha in linhas:
        if linha["password_last_used"] == mod.LITERAL_NO_INFORMATION:
            assert linha["password_enabled"] == "TRUE", (
                "no_information numa linha sem senha: a coluna documenta 'N/A' nesse caso"
            )

    # e nenhum dos tres virou null/ausente em lugar nenhum. A celula VAZIA continua
    # legitima em duas colunas -- ``password_next_rotation`` e
    # ``additional_credentials_info`` sao vazias por contrato nas linhas de usuario, e a
    # pagina nao declara literal para elas -- mas nunca no lugar de um dos tres.
    bruto = (entregues / "credential-report.csv").read_text(encoding="utf-8")
    assert ",null," not in bruto
    for coluna in ("password_last_used", "password_last_changed", "mfa_active"):
        for linha in linhas:
            assert linha[coluna] != "", f"{coluna} veio vazia onde ha literal documentado"


def test_a_linha_da_conta_root_vem_primeiro_e_e_a_unica(entregues: Path, estate: CanonicalEstate) -> None:
    """One root row per account, first, and it is what the MFA rule reads."""
    linhas = _csv_rows(entregues)
    roots = [linha for linha in linhas if linha["user"] == mod.ROOT_ACCOUNT_USER_LITERAL]
    assert len(roots) == len(estate.aws_identity_postures)
    assert len(roots) > 0

    # A raiz e a PRIMEIRA linha de cada conta: um consumidor que separa por conta precisa acha-la
    # sem ler o arquivo inteiro.
    accounts = [linha["arn"].split(":")[4] for linha in linhas]
    for indice, conta in enumerate(accounts):
        if indice == 0 or accounts[indice - 1] != conta:
            assert linhas[indice]["user"] == mod.ROOT_ACCOUNT_USER_LITERAL, (conta, linhas[indice]["user"])
        else:
            assert linhas[indice]["user"] != mod.ROOT_ACCOUNT_USER_LITERAL

    # e o MFA publicado na raiz e o MFA que a regra le -- o MESMO avaliador da tela de Config
    from tools.synthetic_clouds.render import _config_evaluators as ev

    por_conta = {posture.account_id: posture for posture in estate.aws_identity_postures}
    for linha in roots:
        conta = linha["arn"].split(":")[4]
        posture = por_conta[conta]
        assert (linha["mfa_active"] == "TRUE") is posture.root_mfa.mfa_active
        esperado = ev.COMPLIANT if posture.root_mfa.mfa_active else ev.NON_COMPLIANT
        assert ev.evaluate_root_account_mfa_enabled(posture).compliance_type == esperado


def test_o_nome_da_linha_root_e_declarado_nao_comprovado(entregues: Path, spec: Any) -> None:
    """The one value nobody checked against a page has to SAY so, in the artifact.

    The row is emitted anyway -- without it the rule has no row to read -- so the artifact is
    the only place a consumer can learn that the literal is unverified.
    """
    declarados = [campo.name for campo in spec.unverified_fields]
    assert any("root" in nome.lower() for nome in declarados), declarados
    emitida = _provenance(entregues)["unverified_emitted"]
    assert emitida, "o report emite o literal da raiz sem declarar que ele nao foi verificado"
    entrada = emitida[0]
    assert entrada["value"] == mod.ROOT_ACCOUNT_USER_LITERAL
    assert "2026-10-18" in entrada["reason"], "o motivo precisa dizer onde a fonte foi lida"


def test_duas_chaves_por_usuario_e_nunca_tres(entregues: Path, spec: Any) -> None:
    """There is no ``access_key_3_*`` column, so the rows are not 'every key in the account'."""
    nomes = {column.name for column in spec.columns_for(CSV_SCOPE)}
    assert not any(nome.startswith("access_key_3") for nome in nomes)
    assert mod.ACCESS_KEY_SLOTS == (1, 2)


def test_o_cruze_do_consumidor_encontra_e_exclui(entregues: Path) -> None:
    """``password_enabled and not mfa_active`` finds console users and EXCLUDES API-only ones.

    This is the finding a posture tool makes off this surface. An API-only user has no console
    and therefore no screen to protect with MFA -- counting it would be accusing a service
    account of being an unprotected human.
    """
    linhas = _csv_rows(entregues)
    achados = [
        linha
        for linha in linhas
        if linha["password_enabled"] == "TRUE"
        and linha["mfa_active"] == "FALSE"
        and linha["user"] != mod.ROOT_ACCOUNT_USER_LITERAL
    ]
    assert achados, "o estado nao tem nenhum console-user sem MFA: o cruzamento nao e testavel"
    for linha in achados:
        assert linha["arn"].endswith(tuple(linha["user"])) or ":user/" in linha["arn"], linha["arn"]

    so_de_api = [
        linha
        for linha in linhas
        if linha["password_enabled"] == "FALSE" and linha["user"] != mod.ROOT_ACCOUNT_USER_LITERAL
    ]
    assert so_de_api, "o estado nao tem usuario so de API: o filtro nao e testavel"
    assert all(linha["password_last_used"] == mod.LITERAL_NA for linha in so_de_api)


def test_o_envelope_carrega_o_csv_em_base64_e_decodifica(entregues: Path) -> None:
    """``Content`` is the CSV in Base64, and it decodes to the CSV that was written.

    Not a style choice: a consumer that reads the envelope instead of the CSV has to get the
    same bytes, and the only way to know it does is to decode and compare.
    """
    envelope = json.loads((entregues / "response-envelope.json").read_text(encoding="utf-8"))
    assert envelope["ReportFormat"] == "text/csv"
    assert isinstance(envelope["GeneratedTime"], str)

    decodificado = base64.b64decode(envelope["Content"]).decode("utf-8")
    assert decodificado == (entregues / "credential-report.csv").read_text(encoding="utf-8")


def test_o_relatorio_e_byte_a_byte_deterministico(
    estate: CanonicalEstate, tmp_path: Path
) -> None:
    """Two renders of the same estate, same bytes -- the CSV included."""
    primeiro = tmp_path / "a"
    segundo = tmp_path / "b"
    mod.IamGetCredentialReportRenderer().render(estate, primeiro)
    mod.IamGetCredentialReportRenderer().render(estate, segundo)
    for nome in ("credential-report.csv", "credential-report.json", "_provenance.json"):
        assert (primeiro / mod.RENDER_DIR / nome).read_bytes() == (
            segundo / mod.RENDER_DIR / nome
        ).read_bytes(), nome


def test_o_cartao_de_atribuicao_cobre_toda_linha(entregues: Path) -> None:
    """Every row belongs to an account the map names, and the map is total."""
    linhas = _csv_rows(entregues)
    mapa = _provenance(entregues)["response_order"]
    accounted = {indice for entrada in mapa for indice in entrada["rows"]}
    assert accounted == set(range(len(linhas))), (
        "ha linhas que o response_order nao atribui a nenhuma conta"
    )
    for entrada in mapa:
        assert entrada["rows"], entrada["account"]