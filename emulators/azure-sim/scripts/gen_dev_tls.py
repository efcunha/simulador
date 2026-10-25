"""Generate the local development CA and the TLS leaf the emulators serve.

The CloudPilot ingestion is expected to address the REAL cloud hostnames
(``management.azure.com``, ``login.microsoftonline.com``,
``bigquery.googleapis.com``, ``oauth2.googleapis.com``). For that to happen
inside the CloudPilot container network, those names must resolve to the
simulator and the simulator must present a certificate those containers trust.
This script produces both halves:

* ``ca.crt`` / ``ca.key`` — the local CA. ``ca.crt`` is copied into the
  CloudPilot containers' trust bundle (``REQUESTS_CA_BUNDLE`` / ``SSL_CERT_FILE``);
  ``ca.key`` never leaves this machine.
* ``server.crt`` / ``server.key`` — one leaf carrying every hostname the
  emulators answer for. Served by azure-sim on 443 (and later by the GCP
  emulator front). It is baked into the azure-sim image by the Containerfile's
  ``COPY emulators/azure-sim`` line.

Output defaults to ``emulators/azure-sim/tls`` and that directory is
git-ignored: a private key is not source, and the CA is re-generated per
machine. Run with the repository venv:

    .\\.venv\\Scripts\\python.exe emulators\\azure-sim\\scripts\\gen_dev_tls.py

The script is idempotent only in the sense that it OVERWRITES: re-running it
invalidates the previous CA, so the CloudPilot trust bundle must be refreshed
from the new ``ca.crt`` as well.
"""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

# Hostnames the emulator stack must answer for. Keeping them in one SAN list is
# what lets a single leaf serve both the Azure and the GCP fronts.
DEFAULT_DNS_NAMES = (
    "management.azure.com",
    "login.microsoftonline.com",
    "bigquery.googleapis.com",
    "oauth2.googleapis.com",
    "storage.googleapis.com",
    "sts.amazonaws.com",
    "sts.us-east-1.amazonaws.com",
    "s3.amazonaws.com",
    # Direct container names, used by the smoke checks and by tests that do not
    # go through the CloudPilot network.
    "azure-sim",
    "bigquery-emulator",
    "gcp-sim",
    "localhost",
)


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _name(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "synthetic-clouds-dev"),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _write_key(path: Path, key: rsa.RSAPrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def generate(out_dir: Path, *, dns_names: tuple[str, ...], days: int) -> None:
    """Write ``ca.crt``/``ca.key`` and ``server.crt``/``server.key`` under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.UTC)
    not_before = now - dt.timedelta(minutes=5)
    not_after = now + dt.timedelta(days=days)

    ca_key = _key()
    ca_subject = _name("synthetic-clouds dev CA")
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    server_key = _key()
    san = [x509.DNSName(name) for name in dns_names]
    san.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    server_cert = (
        x509.CertificateBuilder()
        .subject_name(_name(dns_names[0]))
        .issuer_name(ca_subject)
        .public_key(server_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage((ExtendedKeyUsageOID.SERVER_AUTH,)), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    _write_key(out_dir / "ca.key", ca_key)
    (out_dir / "ca.crt").write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    _write_key(out_dir / "server.key", server_key)
    (out_dir / "server.crt").write_bytes(server_cert.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {out_dir} (CA valid {days}d, SANs: {', '.join(dns_names)})")


def main() -> int:
    parser = argparse.ArgumentParser(prog="gen_dev_tls")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "tls"),
        help="output directory (default: emulators/azure-sim/tls)",
    )
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--extra-dns", action="append", default=[])
    args = parser.parse_args()
    names = tuple(dict.fromkeys((*DEFAULT_DNS_NAMES, *args.extra_dns)))
    generate(Path(args.out), dns_names=names, days=args.days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
