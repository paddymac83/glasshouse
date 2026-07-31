# Web Lambda: runs frontend/ (Django + DRF) behind AWS Lambda Web
# Adapter, which lets a normal HTTP server run on Lambda with zero
# Lambda-specific handler code -- gunicorn just runs as if it were on
# any other host, and the Adapter (a Lambda extension) translates
# Lambda invoke events into real HTTP requests against it.
#
# Two stages: compile the Rust settlement-engine extension first (a
# plain wheel, architecture-matched to this image), then a slim
# runtime image that never needs a Rust toolchain at all.
#
# Build from the REPO ROOT, not this directory -- the COPY paths below
# are relative to the repo root:
#   docker build -f infra/docker/web.Dockerfile -t glasshouse-web .
#
# NOTE: never actually built in the environment this was written in --
# neither Docker nor network access to any container registry was
# available there. See infra/README.md. Base image, Lambda Web Adapter
# image+tag, and the Dockerfile shape below were checked against AWS's
# own current example (github.com/awslabs/aws-lambda-web-adapter/blob/
# main/examples/fastapi/app/Dockerfile) rather than guessed.

FROM public.ecr.aws/docker/library/python:3.12-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl build-essential pkg-config \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"
RUN pip install --no-cache-dir maturin

WORKDIR /build/settlement-engine
COPY settlement-engine/Cargo.toml settlement-engine/Cargo.lock ./
COPY settlement-engine/pyproject.toml ./
COPY settlement-engine/src ./src
RUN maturin build --release --out /wheels


FROM public.ecr.aws/docker/library/python:3.12-slim

COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1 /lambda-adapter /opt/extensions/lambda-adapter

# uv, not plain pip, to install frontend/: frontend/pyproject.toml's
# local path dependencies on glasshouse-ingestion/-forecast/-settlement
# are declared via [tool.uv.sources], which plain pip does not
# understand -- it would try (and fail) to fetch those three from
# PyPI, where they don't exist. Same reasoning as every local dev/CI
# install in this repo, just inside a container this time.
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY --from=rust-builder /wheels /wheels
COPY ingestion ./ingestion
COPY forecast ./forecast
COPY frontend ./frontend

RUN uv pip install --system /wheels/*.whl \
    && cd frontend && uv pip install --system -e ".[deploy]"

WORKDIR /app/frontend
RUN python manage.py collectstatic --no-input

ENV PORT=8000
EXPOSE 8000

# sync_db download pulls glasshouse.db from S3 into /tmp before
# gunicorn starts serving -- see pricing/db_sync.py. `exec` replaces
# the shell process rather than spawning a child, so the container's
# PID 1 is gunicorn itself and responds correctly to Lambda's
# termination signals.
CMD ["sh", "-c", "python manage.py sync_db download && exec gunicorn glasshouse_frontend.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --timeout 30"]
