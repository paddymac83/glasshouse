# infra/

Terraform for deploying `frontend/` (the Django + DRF dashboard) to a
personal AWS account. `api/`, `ingestion`, and `forecast` are not
deployed as their own services -- `frontend/` imports the other
packages the same way it always has, so deploying it deploys the whole
pricing engine.

This is being built in slices, each landing only once it's actually
working -- see "Status" below for what's real right now versus what's
still a plan.

## Why this shape

**Compute: Lambda, container images.** Scales to zero -- no idle cost
between visits, which matters for a portfolio demo that gets occasional
traffic rather than constant load. At that traffic level this should
sit entirely within AWS's free tier (1M requests + 400,000 GB-seconds
of compute, free every month, forever).

**Storage: S3, not EFS.** This is the single biggest cost lever in the
whole design. EFS requires the Lambda to run inside a VPC. A
VPC-attached Lambda that *also* needs internet access -- which the
ingestion Lambda does, to reach Elexon and Octopus -- needs a NAT
Gateway, a flat ~$32-35/month charge regardless of usage. That would
dwarf every other cost here combined. Staying VPC-free avoids it
entirely: a Lambda with no VPC config gets free internet access and
free same-region S3 access by default. Both Lambdas just download
`glasshouse.db` from S3 to `/tmp` when they start (and, for ingestion,
upload it back) -- zero changes needed in `ingestion`'s `Storage` or
`forecast`'s `SeasonalBaselineForecaster`, which don't care whether the
file was always local or just downloaded.

**Public entry: CloudFront -> Lambda Function URL, not a bare Function
URL, not API Gateway.** Function URLs cannot have AWS WAF attached
directly. CloudFront can, and Origin Access Control (OAC) locks the
Function URL down so it's only reachable through that specific
CloudFront distribution -- the raw Function URL becomes unreachable
directly. This also gets AWS Shield Standard automatically, at no
cost, for baseline DDoS protection.

**Cost circuit-breakers, honestly framed.** AWS does not offer a hard
spending cap -- there is no way to guarantee this can never produce a
bill. The realistic posture is defense in depth:
- Lambda reserved concurrency, set low, capping both cost and the
  blast radius of a traffic spike.
- A WAF rate-based rule on the CloudFront distribution.
- AWS Budgets with email alerts at 50/80/100% of a threshold.
- AWS Budget Actions -- attaches a deny-all IAM policy to the Lambda
  execution roles automatically if a threshold is breached. The
  closest thing to a real kill switch, with a real caveat: billing
  data can lag up to ~24 hours, so this is same-day, not instant.
- AWS Cost Anomaly Detection, free, catching spend patterns budgets
  alone might miss.

Rough estimate at portfolio-demo traffic: likely $5-10/month, mostly
the WAF WebACL's fixed fee. An estimate, not a guarantee -- which is
exactly why the Budget alert isn't optional.

## Status

| Piece | Status |
|---|---|
| Django production settings (env-driven `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`, WhiteNoise static files) | **done** -- see `frontend/README.md`'s "Deployment readiness" section |
| S3 sync glue, both packages (`db_sync.py`, `manage.py sync_db` in `frontend`; `db_sync.py` in `ingestion`) | **done**, tested with mocked `boto3` |
| Backfill loop extracted to `glasshouse_ingestion.backfill` | **done** -- shared by the CLI and the Lambda handler, 4 direct tests plus the CLI's existing tests as regressions |
| Ingestion Lambda handler (`glasshouse_ingestion/lambda_handler.py`) | **done**, 5 tests mocking `download_db`/`upload_db`/`run_backfill` |
| Dockerfiles (web + ingestion) | **written**, not built -- see limitation note below |
| Terraform: S3, ECR, IAM | **written** -- see limitation note below |
| Terraform: Lambda functions | not yet built |
| Terraform: CloudFront + WAF + OAC | not yet built |
| Terraform: EventBridge schedule | not yet built |
| Terraform: Budgets, Budget Actions, Cost Anomaly Detection | not yet built |
| CI: build + push container images | not yet built |

## Trying it (S3 + ECR + IAM only, so far)

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # defaults are fine as-is
terraform init
terraform plan     # review carefully -- this is the real first test
terraform apply
```

This creates the S3 bucket, both ECR repositories, and both Lambda IAM
roles -- but no actual Lambda functions yet (next slice), so there's
nothing to push a container image to run, and nothing publicly
reachable. Safe to `apply` now if you want to see it for real and
confirm the plan looks sane; safe to `terraform destroy` afterward if
you'd rather wait until there's something to actually see. Either way,
this uses `terraform.tfstate` locally (see `versions.tf`'s comment on
backends) -- don't lose that file if you want `terraform destroy` to
work cleanly later.

You'll need AWS credentials available to the `aws` provider (an IAM
user or role able to create S3/ECR/IAM resources -- not root, ideally
a dedicated user for Terraform itself, scoped down once you know
exactly what this needs long-term). The standard ways: `aws configure`
(writes `~/.aws/credentials`), or environment variables
(`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` if
using temporary credentials).

## A real limitation, stated plainly

Neither `terraform` nor `docker` is available in the environment this
was built in, and their registries (`registry.terraform.io`,
`registry-1.docker.io`, `releases.hashicorp.com`) are network-blocked
there too -- confirmed directly, not assumed. That means the two
Dockerfiles have never actually been through `docker build`, and none
of the Terraform in this folder has ever been through `terraform init`
/ `validate` / `plan`, the way every other piece of this repo was
verified before being called done.

What *was* verified, without needing either tool:

- The application-level deployment code (`db_sync.py` in both
  packages, the `sync_db` management command, the ingestion Lambda
  handler, the extracted `run_backfill`) -- all pure Python, tested
  with mocked `boto3`/`ElexonClient`, no real network needed.
- The production Django settings, by actually booting `gunicorn`
  locally with production-like settings and confirming the dashboard
  and static CSS both respond correctly.
- Every file path either Dockerfile's `COPY` instructions reference
  actually exists in the repo, checked directly.
- Both Dockerfiles parse as structurally valid (via `dockerfile-parse`,
  installed from PyPI -- Docker Hub and Docker itself weren't
  reachable, but this at least confirms instruction syntax and
  multi-stage `FROM ... AS` structure are well-formed).
- The AWS Lambda Web Adapter image reference, tag, and Dockerfile shape
  were checked against AWS's own current published example
  (`github.com/awslabs/aws-lambda-web-adapter`) rather than
  reconstructed from memory.
- Every `.tf` file (`versions.tf`, `data.tf`, `variables.tf`, `s3.tf`,
  `ecr.tf`, `iam.tf`, `outputs.tf`) parses as syntactically valid HCL2
  (via `python-hcl2`, from PyPI -- `registry.terraform.io` wasn't
  reachable, so this can't check anything against the real AWS
  provider's actual resource schema, but it does catch malformed
  syntax). Beyond that, every `var.*`, `data.*`, and resource
  cross-reference across all seven files was checked programmatically
  against what's actually declared -- e.g. confirming `aws_s3_bucket.data.arn`
  really does refer to a declared `resource "aws_s3_bucket" "data"`
  block, not a typo'd name. This catches a real, common class of
  Terraform mistake, though it's still not the same guarantee
  `terraform validate` gives against the live provider schema.

What's still genuinely unverified: whether `terraform init` resolves
the provider versions cleanly, whether every resource argument is
accepted by the real `aws` provider schema (attribute names/types this
review didn't happen to get wrong), whether the actual `docker build`
succeeds, whether the compiled Rust wheel installs cleanly into the
runtime stage, and whether `uv pip install --system` behaves as
expected inside that specific base image. Treat all of it as a
well-reasoned first draft -- your first `docker build` and your first
`terraform init && plan` are the real tests, not a formality.
