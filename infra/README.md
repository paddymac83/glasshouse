# infra/ (not yet built)

AWS CDK (Python) definitions for running this for real: scheduled
ingestion (EventBridge -> Lambda, matching how Tem and Fuse's own job
postings describe their event-driven, serverless-first stacks), a
Postgres/TimescaleDB instance, the API service, and the static
frontend build. CDK in Python rather than Terraform/TypeScript so the
infrastructure code lives in the same language as most of the rest of
this repo.
