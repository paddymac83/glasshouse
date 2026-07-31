# Ingestion Lambda: a scheduled batch job, not a web server. Uses AWS's
# own managed Lambda Python base image and the standard container
# handler pattern -- CMD names the handler function directly, the base
# image's own runtime bootstrap (already baked in) invokes it. No Rust
# needed here at all: ingestion depends on httpx + pydantic + boto3
# only, never glasshouse-settlement.
#
# Build from the REPO ROOT, not this directory -- the COPY paths below
# are relative to the repo root:
#   docker build -f infra/docker/ingestion.Dockerfile -t glasshouse-ingestion .
#
# NOTE: never actually built in the environment this was written in --
# neither Docker nor network access to any container registry was
# available there. See infra/README.md.

FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

COPY ingestion/pyproject.toml ./ingestion/pyproject.toml
COPY ingestion/glasshouse_ingestion ./ingestion/glasshouse_ingestion

RUN pip install --no-cache-dir "./ingestion[deploy]"

CMD ["glasshouse_ingestion.lambda_handler.handler"]
