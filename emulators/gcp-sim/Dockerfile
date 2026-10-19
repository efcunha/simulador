# gcp-sim image (Phase 3 / Phase 6): serves the REST plane and runs the DDL provisioner.
#
# Build context = the WORKTREE ROOT (the dir containing tools/ and deploy/), mirroring
# emulators/aws-sim/Containerfile. The Phase 6 inventory routers import the Phase 1
# generator as ``tools.synthetic_clouds.*`` resolved via PYTHONPATH — never a wheel
# install — so the image must bake tools/ in. Build from the worktree root with:
#   podman build -f emulators/gcp-sim/Dockerfile -t gcp-sim .
# Used by BOTH the gcp-sim service and the one-shot gcp-bq-provision container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install runtime deps first (layer cache). wget is present for the compose
# healthcheck probe against /healthz.
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# pandas + pyarrow are pulled in at import time by the Phase 1 package (same reason
# azure-sim and aws-sim ship them). google-cloud-monitoring + grpcio are the FR-25
# monitoring gRPC plane: the sim serves Cloud Monitoring from the CLIENT's own proto
# descriptors, so the client package is the schema of record and the sim cannot drift
# from the wire contract (there is no rest.py to serve instead -- see config.py).
RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn>=0.29" "httpx>=0.27" "pandas" "pyarrow" \
    "grpcio>=1.60" "google-cloud-monitoring>=2.31,<3"

# Bake both trees in; the build context is the worktree root, so these are relative to it.
# tools.synthetic_clouds resolves via PYTHONPATH=/app.
COPY tools/synthetic_clouds /app/tools/synthetic_clouds
COPY specs /app/specs
COPY emulators/gcp-sim/gcp_sim /app/gcp_sim/
COPY emulators/gcp-sim/pyproject.toml /app/pyproject.toml

# Default fixtures dir (mounted via named volume at runtime); the service exits
# non-zero at boot if it is missing/empty.
ENV GCP_SIM_FIXTURES_DIR=/fixtures
ENV PYTHONPATH=/app
# Enables the Cloud Monitoring gRPC plane (FR-25) inside the process uvicorn runs.
# Unset = REST-only, which is what a bare `uvicorn gcp_sim.app:app` outside this image does.
ENV GCP_SIM_GRPC_PORT=8087

EXPOSE 8085
# 8087: the Cloud Monitoring gRPC plane (FR-25). It starts from the same process as the
# REST plane because the GCP_SIM_GRPC_PORT above is set -- compose's `command:` only names
# the uvicorn app, so the plane is switched on here, in the image.
EXPOSE 8087

# Default command serves the REST plane; the provision container overrides it
# with `python -m gcp_sim.provision ...` in compose.gcp.yaml.
CMD ["uvicorn", "gcp_sim.app:app", "--host", "0.0.0.0", "--port", "8085"]
