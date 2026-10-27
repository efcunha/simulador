"""Generate the extra TLS leaf the GCP/AWS front serves.

``gen_dev_tls.py`` creates the local CA and the Azure leaf (management/login
hostnames). The GCP and AWS clients resolve additional names
(``cloudresourcemanager.googleapis.com``, ``sts.amazonaws.com``, ...), so the
front needs one leaf whose SAN list covers them. It is signed by the SAME CA, so
the CloudPilot trust bundle does not have to be rebuilt.

Run after ``gen_dev_tls.py`` (the CA must already exist):

    .\\.venv\\Scripts\\python.exe emulators\\azure-sim\\scripts\\gen_cloud_front_tls.py

Writes ``server-clouds.crt`` / ``server-clouds.key`` next to the CA. The
directory is git-ignored.
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

DEFAULT_DNS_NAMES = (
    "bigquery.googleapis.com",
    "oauth2.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "config.googleapis.com",
    "securitycenter.googleapis.com",
    "www.googleapis.com",
    "storage.googleapis.com",
    "sts.amazonaws.com",
    "sts.us-east-1.amazonaws.com",
    "s3.amazonaws.com",
)


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def generate(out_dir: Path, *, days: int, dns_names: tuple[str, ...]) -> None:
    ca_cert = x509.load_pem_x509_certificate((out_dir / "ca.crt").read_bytes())
    ca_key = serialization.load_pem_private_key((out_dir / "ca.key").read_bytes(), password=None)
    if not isinstance(ca_key, rsa.RSAPrivateKey):
        raise SystemExit("ca.key is not an RSA key")

    now = dt.datetime.now(dt.UTC)
    leaf_key = _key()
    san = [x509.DNSName(name) for name in dns_names]
    san.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    cert = (
        x509.CertificateBuilder()
        .subject_name(
            x509.Name(
                [
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "synthetic-clouds-dev"),
                    x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0]),
                ]
            )
        )
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=days))
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

    (out_dir / "server-clouds.key").write_bytes(
        leaf_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (out_dir / "server-clouds.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {out_dir / 'server-clouds.crt'} (SANs: {', '.join(dns_names)})")


def main() -> int:
    parser = argparse.ArgumentParser(prog="gen_cloud_front_tls")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "tls"),
        help="directory holding ca.crt/ca.key (default: emulators/azure-sim/tls)",
    )
    parser.add_argument("--days", type=int, default=3650)
    args = parser.parse_args()
    generate(Path(args.out), days=args.days, dns_names=DEFAULT_DNS_NAMES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
