"""S3 tests: the six operations, driven by a REAL boto3 client over path-style addressing.

The load-bearing tests are in :class:`TestRealClient`: the app is served on a real socket
and driven with ``boto3.client("s3")`` configured exactly the way
``AWS_SERVICE_ENDPOINT`` + ``AWS_S3_FORCE_PATH_STYLE`` configure FinOps client, so the
request goes through botocore's own serializer, signer and rest-xml parser. A wrong
envelope, a missing ``EncodingType`` echo, or a key that does not survive the URL round trip
fails there — which is precisely what this surface must not do.

The store is a real tree on disk, in the layout ``render/focus_aws`` emits and
``aws_sim.upload`` uploads, so the assertions are about the estate's own artefacts rather
than about a fixture shaped to suit the emulator.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import boto3
import pytest
import uvicorn
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from aws_sim import scope
from aws_sim.projections import s3 as projection
from aws_sim.s3_rest_xml import ENCODING_URL
from aws_sim.s3_store import S3Store, decode_token

_AWS_CREDENTIALS = {"aws_access_key_id": "x", "aws_secret_access_key": "y"}
_REGION = "us-east-1"

#: The bucket the uploader pushes the rendered tree into (``AWS_SIM_BUCKET``'s default).
_BUCKET = "synthetic-focus12-daily-full"
#: The Data Export prefix the reader lists under: ``{S3_PREFIX}/{EXPORT_NAME}``.
_PREFIX = f"focus12-full/{_BUCKET}"

#: The store tree, as the renderer lays it out: two deliveries of one period (the earlier
#: one is the pre-restatement view), one delivery of another, and a manifest.
_OBJECTS: tuple[tuple[str, bytes], ...] = (
    ("data/billing_period=2026-01/20260113T000000Z-80f388ff/part-00001.snappy.parquet", b"older"),
    ("data/billing_period=2026-01/20260201T000000Z-80f388ff/part-00001.snappy.parquet", b"newer"),
    ("data/billing_period=2026-02/20260215T000000Z-238acda6/part-00001.snappy.parquet", b"february"),
    ("metadata/billing_period=2026-01/20260201T000000Z-80f388ff/Manifest.json", b"{}"),
)


def _keys() -> list[str]:
    return sorted(f"{_PREFIX}/{relative}" for relative, _body in _OBJECTS)


def _app(store_root: Path | None) -> Any:
    """A composed app, with the artefact store wired the way ``compose.aws.yaml`` wires it."""
    from aws_sim.api.app import create_app
    from aws_sim.config import load_settings

    overrides: dict[str, object] = {"AWS_SIM_BUCKET": _BUCKET}
    if store_root is not None:
        overrides["AWS_SIM_S3_STORE_DIR"] = str(store_root)
    return create_app(load_settings(env={}, SEED="42", PROFILE="small", CURRENCY="USD", **overrides))


@pytest.fixture(scope="module")
def store_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The uploaded tree's root: a directory whose contents ARE the bucket's objects."""
    root = tmp_path_factory.mktemp("s3-store") / "aws_focus"
    for relative, body in _OBJECTS:
        path = root / _PREFIX / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
    return root


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture(scope="module")
def endpoint_url(store_root: Path) -> Iterator[str]:
    """The store-backed app served on a real socket, as the compose plane runs it."""
    app = _app(store_root)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "the app did not start listening"
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=20)


@pytest.fixture(scope="module")
def s3(endpoint_url: str) -> Any:
    """The client shape FinOps builds: path-style, pointed at the single endpoint."""
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=_REGION,
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        **_AWS_CREDENTIALS,
    )


@pytest.fixture(scope="module")
def bucket_names(s3: Any) -> list[str]:
    return [bucket["Name"] for bucket in s3.list_buckets()["Buckets"]]


@pytest.fixture(scope="module")
def estate_bucket(bucket_names: list[str]) -> str:
    """One of the estate's own bucket names, taken from the served answer."""
    return next(name for name in bucket_names if name.startswith("bucket-"))


@pytest.fixture(scope="module")
def artifact_bucket(bucket_names: list[str]) -> str:
    """The bucket the rendered artefacts live in."""
    return next(name for name in bucket_names if name == _BUCKET)


class TestRealClient:
    """The six operations, through botocore's own transport, signer and parser."""

    def test_serves_all_six_operations(self, s3: Any, estate_bucket: str) -> None:
        """Every operation the coverage matrix names is reached by a real client.

        ``get_bucket_policy`` and ``get_public_access_block`` answer a ``ClientError``
        rather than a body, and that IS the operation being served: the estate declares
        neither setting, and the code that arrives is the one the auditing callers branch
        on (``security.py (modulo do consumidor):304`` and ``:218``).
        """
        buckets = s3.list_buckets()
        listing = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX)
        obj = s3.get_object(Bucket=_BUCKET, Key=listing["Contents"][0]["Key"])
        acl = s3.get_bucket_acl(Bucket=estate_bucket)

        assert buckets["Buckets"]
        assert listing["Contents"]
        assert obj["Body"].read()
        assert acl["Grants"]

        with pytest.raises(ClientError) as policy:
            s3.get_bucket_policy(Bucket=estate_bucket)
        with pytest.raises(ClientError) as block:
            s3.get_public_access_block(Bucket=estate_bucket)
        assert policy.value.response["Error"]["Code"] == "NoSuchBucketPolicy"
        assert block.value.response["Error"]["Code"] == "NoSuchPublicAccessBlockConfiguration"

    def test_list_buckets_answers_the_estate_and_the_artefact_bucket(self, s3: Any) -> None:
        names = [bucket["Name"] for bucket in s3.list_buckets()["Buckets"]]
        assert names == sorted(names)
        assert _BUCKET in names
        assert len(names) > 1  # noqa: PLR2004 - the estate carries buckets of its own
        # CreationDate reaches the client as a parsed datetime wherever the estate asserts
        # one; a bucket the estate never billed is listed without it.
        created = [bucket["CreationDate"] for bucket in s3.list_buckets()["Buckets"] if "CreationDate" in bucket]
        assert created and all(hasattr(moment, "year") for moment in created)

    def test_list_buckets_names_are_what_the_app_projects(self, s3: Any, endpoint_url: str) -> None:
        """The names are the estate's ids plus the store's bucket — nothing else."""
        served = {bucket["Name"] for bucket in s3.list_buckets()["Buckets"]}
        assert served == set(projection.names(_app(Path("/nonexistent")).state.estate)) | {_BUCKET}
        assert all(name.startswith("bucket-") for name in served if name != _BUCKET)

    def test_list_objects_v2_returns_the_rendered_artefacts_verbatim(self, s3: Any, store_root: Path) -> None:
        """Keys survive the URL round trip, including the ``=`` in the partition path."""
        response = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX)
        keys = [obj["Key"] for obj in response["Contents"]]
        assert keys == _keys()
        assert response["KeyCount"] == len(keys)
        assert response["IsTruncated"] is False
        assert response["Name"] == _BUCKET
        assert all(obj["Size"] > 0 for obj in response["Contents"])
        # The key addresses the file the uploader pushed, and nothing rewrote it.
        assert all((store_root / key).is_file() for key in keys)

    def test_list_objects_v2_last_modified_follows_the_execution_stamp(self, s3: Any) -> None:
        """The reader pins the newest execution by ``LastModified``, so the store must order it.

        For billing period 2026-01 the estate delivered twice, and the later delivery is
        the one whose lines the reader must bill. The order comes from the execution
        directory's own stamp, not from the copy's mtimes, so it survives ``podman cp``.
        """
        response = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX)
        by_key = {obj["Key"]: obj["LastModified"] for obj in response["Contents"]}
        older = next(moment for key, moment in by_key.items() if "20260113T000000Z" in key)
        newer = next(moment for key, moment in by_key.items() if "20260201T000000Z" in key)
        assert newer > older
        assert older.year == 2026  # noqa: PLR2004 - the stamp's year, not the fixture's clock

    def test_list_objects_v2_paginates_with_the_token_it_issues(self, s3: Any) -> None:
        first = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX, MaxKeys=1)
        assert first["IsTruncated"] is True
        assert first["KeyCount"] == 1  # noqa: PLR2004
        # The token reaches the caller unmangled: botocore does not decode it, so a token
        # that needed escaping would come back escaped and fail to be read as a position.
        assert "%" not in first["NextContinuationToken"]
        second = s3.list_objects_v2(
            Bucket=_BUCKET,
            Prefix=_PREFIX,
            MaxKeys=1,
            ContinuationToken=first["NextContinuationToken"],
        )
        assert second["Contents"][0]["Key"] == _keys()[1]

    def test_get_object_returns_the_bytes_the_uploader_pushed(self, s3: Any, store_root: Path) -> None:
        key = next(candidate for candidate in _keys() if candidate.endswith(".snappy.parquet"))
        response = s3.get_object(Bucket=_BUCKET, Key=key)
        assert response["Body"].read() == (store_root / key).read_bytes()
        assert response["ContentLength"] == (store_root / key).stat().st_size
        # The quoted MD5 a single PutObject would have stored as the ETag, quotes included.
        assert response["ETag"].startswith('"') and response["ETag"].endswith('"')

    def test_get_bucket_acl_is_the_private_default(self, s3: Any, estate_bucket: str) -> None:
        """No public grantee, and the owner's own FULL_CONTROL.

        The estate models no ACL, so this is the ACL S3 gives a bucket nobody has changed.
        Asserted as the *absence* of a public grantee because that is what the auditing
        caller looks for (``security.py:244-266``): any URI grant would make the next line
        of that function raise a CRITICAL finding.
        """
        acl = s3.get_bucket_acl(Bucket=estate_bucket)
        assert [grant["Permission"] for grant in acl["Grants"]] == ["FULL_CONTROL"]
        assert acl["Grants"][0]["Grantee"]["Type"] == "CanonicalUser"
        assert acl["Grants"][0]["Grantee"].get("URI") is None
        assert acl["Owner"]["ID"] == acl["Grants"][0]["Grantee"]["ID"]
        assert len(acl["Owner"]["ID"]) == 64  # noqa: PLR2004 - the canonical-id shape

    def test_an_estate_bucket_with_no_artefacts_lists_empty(self, s3: Any, estate_bucket: str) -> None:
        """A bucket the estate has and the store does not is empty, not an error."""
        response = s3.list_objects_v2(Bucket=estate_bucket)
        assert response["KeyCount"] == 0
        assert response["IsTruncated"] is False
        assert "Contents" not in response


class TestStore:
    """The store's own answers, with no server in the way."""

    def _store(self, root: Path) -> S3Store:
        return S3Store(root, _BUCKET)

    def test_page_size_is_honoured_and_the_token_resumes(self, store_root: Path) -> None:
        store = self._store(store_root)
        first = store.listing(prefix=_PREFIX, max_keys=1)
        assert len(first.objects) == 1  # noqa: PLR2004
        assert first.is_truncated and first.next_token
        second = store.listing(prefix=_PREFIX, max_keys=1, start_after=decode_token(first.next_token or "") or "")
        assert [obj.key for obj in second.objects] != [obj.key for obj in first.objects]

    def test_a_delimiter_rolls_up_directories_once(self, store_root: Path) -> None:
        listing = self._store(store_root).listing(prefix=f"{_PREFIX}/", delimiter="/", max_keys=100)
        assert listing.objects == ()
        assert listing.common_prefixes == (f"{_PREFIX}/data/", f"{_PREFIX}/metadata/")

    def test_absence_is_absence(self, store_root: Path) -> None:
        store = self._store(store_root)
        assert store.listing(prefix=f"{_PREFIX}/nothing/here").objects == ()
        assert store.read(f"{_PREFIX}/no-such-object.snappy.parquet") is None

    def test_a_key_cannot_escape_the_store(self, store_root: Path) -> None:
        """The key is untrusted input: a traversal must read nothing, not the filesystem."""
        store = self._store(store_root)
        for hostile in ("../../../etc/passwd", "/etc/passwd", "..\\windows\\win.ini", "..", ""):
            assert store.read(hostile) is None, hostile

    def test_a_symlink_out_of_the_tree_is_not_an_object(self, store_root: Path, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("not part of the estate", encoding="utf-8")
        link = store_root / _PREFIX / "leak.txt"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):  # pragma: no cover - needs a privileged shell
            pytest.skip("symlinks are not available to this process")
        try:
            store = self._store(store_root)
            assert store.read(f"{_PREFIX}/leak.txt") is None
            assert f"{_PREFIX}/leak.txt" not in [obj.key for obj in store.listing(prefix=_PREFIX).objects]
        finally:
            link.unlink()

    def test_an_unset_store_contributes_nothing(self) -> None:
        """Behaviour with the settings unset: no bucket, no objects, no exception."""
        assert S3Store(None, _BUCKET).configured is False
        assert S3Store(None, _BUCKET).buckets == ()
        assert S3Store(None, _BUCKET).listing().objects == ()
        assert S3Store(Path("does-not-exist"), _BUCKET).buckets == ()
        assert S3Store(Path("does-not-exist"), "").buckets == ()


class TestRoutes:
    """Wire-level behaviour the real client cannot reach, on an app with no store."""

    @pytest.fixture(scope="class")
    def client(self) -> Iterator[TestClient]:
        with TestClient(_app(None)) as test_client:
            yield test_client

    def test_list_buckets_with_no_store_lists_only_the_estate(self, client: TestClient) -> None:
        """The setting unset changes nothing about the estate's answer."""
        response = client.get("/")
        assert response.status_code == 200  # noqa: PLR2004
        assert "<ListAllMyBucketsResult" in response.text
        assert _BUCKET not in response.text
        names = re.findall(r"<Name>([^<]+)</Name>", response.text)
        assert names == sorted(names)
        # Meaningful only if the estate really carries buckets: a profile change that
        # emptied it would otherwise let the assertion above pass on nothing.
        assert names == sorted(projection.names(_app(None).state.estate))

    def test_an_unknown_bucket_lists_empty_rather_than_failing(self, client: TestClient) -> None:
        """Absence is answered as a well-formed empty page, never as a fabricated object."""
        response = client.get("/no-such-bucket", params={"list-type": "2"})
        assert response.status_code == 200  # noqa: PLR2004
        assert "<KeyCount>0</KeyCount>" in response.text
        assert "<IsTruncated>false</IsTruncated>" in response.text
        assert "<Contents>" not in response.text

    def test_a_nonsense_max_keys_is_refused_rather_than_defaulted(self, client: TestClient) -> None:
        """A parameter that arrived and could not be read is not one that never arrived."""
        response = client.get("/no-such-bucket", params={"list-type": "2", "max-keys": "lots"})
        assert response.status_code == 400  # noqa: PLR2004
        assert "<Code>InvalidArgument</Code>" in response.text

    def test_an_unknown_bucket_is_a_no_such_bucket_for_the_bucket_settings(self, client: TestClient) -> None:
        """The single-bucket sub-resources name a bucket, so a missing one is an error."""
        for query in ("acl", "policy", "publicAccessBlock"):
            response = client.get("/no-such-bucket", params={query: ""})
            assert response.status_code == 404, query  # noqa: PLR2004
            assert "<Code>NoSuchBucket</Code>" in response.text

    def test_an_unknown_object_is_a_no_such_key(self, store_root: Path) -> None:
        """``get_object``'s caller parses the body, so absence cannot be an empty body."""
        with TestClient(_app(store_root)) as stored:
            response = stored.get(f"/{_BUCKET}/{_PREFIX}/missing.snappy.parquet")
        assert response.status_code == 404  # noqa: PLR2004
        assert "<Code>NoSuchKey</Code>" in response.text

    def test_get_object_for_a_bucket_the_estate_lacks_is_a_no_such_bucket(self, client: TestClient) -> None:
        """Without a store the artefact bucket is not in the estate at all."""
        response = client.get(f"/{_BUCKET}/{_PREFIX}/part-00001.snappy.parquet")
        assert response.status_code == 404  # noqa: PLR2004
        assert "<Code>NoSuchBucket</Code>" in response.text

    def test_a_bucket_request_with_no_supported_query_is_refused(self, client: TestClient) -> None:
        """:meth:`ListObjects` (v1) is not served; FinOps issues only the v2 call."""
        response = client.get(f"/{_BUCKET}")
        assert response.status_code == 400  # noqa: PLR2004
        assert "<Code>InvalidRequest</Code>" in response.text

    def test_the_listing_echoes_the_encoding_it_encoded_with(self, store_root: Path) -> None:
        """The echo and the escaping ship together — see ``s3_rest_xml``.

        Asserted on the raw body because it is invisible through the client: botocore sets
        ``encoding-type=url`` itself and decodes the answer back, so a missing echo would
        surface only as a key with the percent-escapes still in it.
        """
        with TestClient(_app(store_root)) as stored:
            response = stored.get(
                f"/{_BUCKET}",
                params={"list-type": "2", "prefix": _PREFIX, "encoding-type": ENCODING_URL},
            )
        assert response.status_code == 200  # noqa: PLR2004
        assert f"<EncodingType>{ENCODING_URL}</EncodingType>" in response.text
        assert "billing_period%3D2026-01" in response.text

    def test_the_other_aws_wires_still_own_their_paths(self, client: TestClient) -> None:
        """S3's router is registered last so the REST-JSON services keep their paths."""
        assert client.get("/healthz").status_code == 200  # noqa: PLR2004
        # EKS answers ``GET /clusters``; if S3's ``/{bucket}`` had claimed it, this would be
        # a bucket request and answer XML instead.
        clusters = client.get("/clusters")
        assert clusters.status_code == 200  # noqa: PLR2004
        assert "AccessControlPolicy" not in clusters.text
        # SSO answers ``GET /federation/credentials``; S3's ``/{bucket}/{key}`` would
        # otherwise match it and answer XML.
        federation = client.get("/federation/credentials", params={"account_id": "1", "role_name": "r"})
        assert "<Error>" not in federation.text


class TestDeterminism:
    """The answer is a function of the tree, not of the moment it is asked."""

    def test_two_listings_are_identical(self, s3: Any) -> None:
        first = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX)
        second = s3.list_objects_v2(Bucket=_BUCKET, Prefix=_PREFIX)
        for response in (first, second):
            response.pop("ResponseMetadata", None)
        assert first == second

    def test_two_acl_reads_are_identical(self, s3: Any, estate_bucket: str) -> None:
        first = s3.get_bucket_acl(Bucket=estate_bucket)
        second = s3.get_bucket_acl(Bucket=estate_bucket)
        first.pop("ResponseMetadata", None)
        second.pop("ResponseMetadata", None)
        assert first == second

    def test_the_bucket_list_is_the_estate_projection(self) -> None:
        """Two independently composed apps answer the same buckets, and the same scopes."""
        estate = _app(None).state.estate
        assert projection.names(estate) == projection.names(_app(None).state.estate)
        assert scope.PROVIDER == "aws"
