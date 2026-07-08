# Backend compute migration: App Runner → ECS Fargate + ALB

> **⛔ SUPERSEDED — 2026-07-08.** We're moving backend compute to **GCP Cloud Run +
> serverless Postgres** instead of ECS Fargate, while **keeping AWS Cognito**. The
> driver is cost: Cloud Run scales to zero, whereas Fargate's always-on ALB + task
> is lateral-to-worse. This Fargate plan is retained for reference only; a GCP
> Cloud Run plan will replace it.

**Status:** superseded (was: planned, not started; written 2026-06-25).

## Why

App Runner went to maintenance mode / closed to new customers on **2026-04-30**. Existing
accounts can still recreate services for now, but it's a dead-end — no new features, eventual
forced migration. BrokeLads is torn down and redeployed frequently (skills showcase), so we're
already living on the "recreate" path that AWS is winding down. Move to **ECS Fargate behind an
ALB** while it's cheap to do — fully Terraform-supported, no provider gaps.

**Rejected:** ECS Express Mode (the App-Runner-like ECS wrapper) — Terraform provider coverage
is incomplete as of writing; we'd be back to click-ops / patched-on config like the current
Cognito callback hack.

## Current shape (what we're replacing)

- `terraform/modules/apprunner/` owns: the **ECR repo + lifecycle policy**, two IAM roles
  (instance role, ECR-access build role), and the `aws_apprunner_service`. Health check already
  hits `/health`.
- `terraform/dev/main.tf` wires env vars into the service (DATABASE_URL, Cognito ids, cron key…).
- `terraform/modules/scheduler/` is **coupled to App Runner**: it consumes
  `apprunner.service_url` (EventBridge API-destination target), `apprunner.instance_role_id`
  (attaches a secrets-read policy), and `apprunner.service_name` (naming). All three move.
- `.github/workflows/dev.yml` does a **two-phase apply**: targeted `apply -target=…ecr_repository`
  → docker build/push → full `apply`. Then a post-apply `aws cognito-idp update-user-pool-client`
  patches the OAuth callback URL onto the admin client (avoids an App-Runner↔Cognito TF cycle).

## Target architecture

```
Internet
  → ALB (HTTP/HTTPS listener, eu-west-2)
    → Target Group (health check: GET /health, expect 200 {"status":"ok"})
      → ECS Service (Fargate launch type, desired_count=1)
        → Task Definition (1 container, port 8000, env vars + secrets)
ECR (persistent, separate bootstrap stack) ← pushed image
VPC: 2+ public subnets for the ALB; tasks in public subnets w/ assign_public_ip (no NAT cost)
     or private subnets + NAT (costs more — skip for a demo)
```

### New / changed Terraform

1. **`modules/ecr/` (NEW, persistent bootstrap stack)** — move the `aws_ecr_repository` +
   lifecycle policy out of the compute module into its own stack/state that the teardown does
   NOT destroy. This kills the two-phase apply: the workflow no longer needs `apply -target` to
   create the repo before the image push, because the repo already exists. Compute stack
   references it via a `data "aws_ecr_repository"` or a remote-state output. **This also fixes
   the ~8-min "ECR only" targeted apply** — that step is a slow no-op today because a `-target`
   apply still refreshes the whole state graph; removing the step removes the cost.

2. **`modules/network/` (NEW)** — VPC (or default VPC + data sources to start), 2 public
   subnets across AZs, internet gateway, route table, ALB security group (ingress 80/443 from
   0.0.0.0/0), task security group (ingress 8000 from ALB SG only).

3. **`modules/fargate/` (REPLACES apprunner)** —
   - `aws_lb` (application), `aws_lb_target_group` (target_type `ip`, port 8000, health check
     `/health`), `aws_lb_listener` (80 → forward; add 443 + ACM cert if we want TLS — App Runner
     gave us HTTPS free, ALB does not, so this is a real decision).
   - `aws_ecs_cluster`, `aws_ecs_task_definition` (Fargate, cpu/memory mirror current 256/512,
     `container_definitions` with port 8000 + env vars; pull secrets from Secrets Manager via
     `secrets` block rather than plaintext env where sensible).
   - `aws_ecs_service` (launch_type FARGATE, `load_balancer` block → target group,
     `network_configuration` → subnets + task SG, `assign_public_ip = true`).
   - **Task execution role** (pull from ECR, write logs, read Secrets Manager) +
     **task role** (app runtime perms — replaces the App Runner instance role).
   - CloudWatch log group for `awslogs` driver.
   - Outputs: `alb_dns_name`, `service_name`, `cluster_name`, `task_role_arn` — the seams the
     scheduler + workflow consume.

4. **`modules/scheduler/` (rewire)** — replace the three App Runner inputs:
   - `apprunner_service_url` → `alb_dns_name` (EventBridge API destination target becomes
     `http://<alb_dns>/rapid-api/run-jobs`; use HTTPS once a cert exists).
   - `apprunner_instance_role_id` → `task_role` (secrets-read policy attaches to the task role).
   - `apprunner_service_name` → fargate service name (naming only).

5. **`dev/main.tf`** — swap `module.apprunner` for `module.fargate` + `module.network`; env-var
   map is unchanged (DATABASE_URL etc.). Keep `random_password.db` with `special = false` —
   **the DATABASE_URL raw-interpolation gotcha is unchanged by this migration.**

### `dev.yml` workflow changes

- **Drop** the "Terraform Plan/Apply (ECR only)" two steps once ECR is in the bootstrap stack.
  Build/push targets the pre-existing repo (read its URL from the bootstrap stack output or a
  hardcoded `${account}.dkr.ecr.eu-west-2.amazonaws.com/brokelads-api`).
- **Cognito callback patch**: `APPRUNNER_HOST` → ALB DNS (or custom domain). Same
  `update-user-pool-client` post-apply step, new host source.
- **Fix green≠healthy** (the standing gotcha): App Runner couldn't be gated in-pipeline; ECS can.
  Add after the full apply:
  ```
  aws ecs wait services-stable --cluster <cluster> --services <service>
  ```
  and/or poll target-group health until `healthy`. This makes the workflow actually fail when the
  container won't start — closing the "terraform apply is green but the service is down" trap.
  Still worth a final `curl https://<host>/health` for belt-and-braces.

## Decisions to make before starting

- **TLS**: App Runner gave HTTPS for free. ALB needs an ACM cert + a domain (Route53 or the
  Vercel/registrar). Options: (a) HTTP-only for the demo, FE talks to `http://<alb>` — but the FE
  is HTTPS on Vercel, so mixed-content will be blocked by browsers → effectively forces TLS;
  (b) ACM cert on a custom domain. **Likely need (b).** This is the biggest scope addition.
- **Cost**: App Runner scales to zero between demos; an ALB bills ~£12–16/mo flat whether or not
  traffic flows, plus the always-on Fargate task. For a frequently-torn-down demo, confirm we
  tear the ALB down too, or accept the idle cost.
- **VPC**: start with the default VPC + subnet data sources (less code) or a purpose-built VPC
  module (cleaner, more to write). Default VPC is fine for a demo.

## Auth hardening to fold in (cheap, pre-existing — surfaced in the Ask the Pundit security review, 2026-06-25)

Both predate the pundit work and aren't blockers; do them while touching the backend.

- **`verify_token` doesn't assert `token_use == "id"`** (`api/src/client/utils/cognito.py`). A Cognito
  *access* token with the right audience currently passes signature/issuer/expiry checks. It's
  caught downstream today only because access tokens lack the `email` claim and `get_current_user`
  401s without it — i.e. defence by accident. Add an explicit `claims["token_use"] == "id"` check
  in `verify_token` so only idTokens authenticate, by design rather than side effect.
- **`get_jwks()` is `@lru_cache`'d with no TTL** (`cognito.py`). Cognito's signing keys are cached
  for the process lifetime, so a key rotation breaks token verification until the container
  restarts. Low odds, but on long-lived Fargate tasks (vs App Runner's churn) it matters more. Give
  the cache a TTL (e.g. `cachetools.TTLCache` ~1h) or drop the cache and let the SDK/JWKS client
  handle caching.

## Rough order of work

1. Bootstrap ECR stack; repoint workflow build/push at it; delete the two-phase apply. *(Ships
   independently of the rest — do this first, it's the cheap win + kills the 8-min no-op.)*
2. Network module (default VPC data sources + SGs + ALB).
3. Fargate module (cluster, task def, service, target group, roles, logs).
4. Rewire scheduler to ALB DNS + task role.
5. Swap modules in `dev/main.tf`; sort TLS/domain.
6. Workflow: callback host → ALB, add `ecs wait services-stable` health gate.
7. Destroy the old App Runner module/resources.
