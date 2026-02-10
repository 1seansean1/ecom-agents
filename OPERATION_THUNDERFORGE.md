# OPERATION THUNDERFORGE
### ecom-agents Production ECS Deployment Plan — v3 (final)

---

## Context

ecom-agents runs locally (8050) with a Forge Console (frontend:5173 + backend:8060). The infrastructure Terraform is already written in `console/aws/` (9 .tf files, deploy.sh). **Gaps blocking production deployment:**

1. **No authentication** on the Forge Console (frontend has no login page, backend has no auth middleware, WebSocket endpoints completely open)
2. **No Dockerfile** for the ecom-agents service itself (only pyproject.toml, no requirements.txt)
3. **No ChromaDB** in ECS, **Ollama can't run on Fargate** (no GPU), **health check hard-fails** without Ollama
4. **Terraform env vars don't match code** (code reads `DATABASE_URL`, `REDIS_URL`, `CHROMA_URL`; Terraform sets `POSTGRES_HOST/PORT`, `REDIS_HOST/PORT`)
5. **CloudFront doesn't forward Content-Type** header, breaking JSON POSTs
6. **Import order bug**: `src.llm.config` imports before `load_dotenv()` in `serve.py`
7. **`ollama_fallback_active` flag** is set but never read anywhere — dead code

**Goal**: Deploy to AWS ECS. User visits CloudFront URL, logs in with `sean.p.allen9@gmail.com` / `admin`, sees Forge Console identical to localhost. Email the production URL when done.

---

## Step 0: Code Fixes (Pre-Deployment Blockers)

### 0a. Health Check: Graceful Ollama Degradation
**Files**: `src/serve.py`, `src/resilience/health.py`

**Problem**: `serve.py:116` — `all_healthy = all(v for v in health.values())` returns 503 if ANY check fails. ECS task health check hits `/health`; with no Ollama, it loops kill forever.

**Also**: The plan previously claimed `ollama_fallback_active` "routes TRIVIAL tasks to GPT-4o-mini" — this is **false**. That flag is only set in `health.py:20,33,36,40` but never imported or read by any other module. It's dead code.

**Fix** (serve.py):
```python
critical_checks = {k: v for k, v in health.items() if k != "ollama"}
all_critical_healthy = all(critical_checks.values())
status = "healthy" if all(health.values()) else "degraded" if all_critical_healthy else "unhealthy"
status_code = 200 if all_critical_healthy else 503
```

### 0b. Complexity Model Remap When Ollama Absent
**File**: `src/llm/config.py`, `src/serve.py`

**Problem 1**: `COMPLEXITY_MODEL_MAP` (line 82) hardcodes `TRIVIAL -> OLLAMA_QWEN`. No env override exists.

**Problem 2 (import order)**: `serve.py:24` imports `src.llm.config` BEFORE `serve.py:28` calls `load_dotenv()`. Any module-level `os.environ.get("OLLAMA_BASE_URL")` in `config.py` will see an empty env in local dev (where .env is the source), incorrectly remapping TRIVIAL even when Ollama is running.

**Fix**: Do NOT use `os.environ.get()` at module level. Perform the remap in `serve.py` AFTER both `load_dotenv()` (line 28) and `LLMSettings()` instantiation (line 39):

```python
# serve.py — after line 40 (router = LLMRouter(settings)):
if not settings.ollama_base_url:
    from src.llm.config import COMPLEXITY_MODEL_MAP, TaskComplexity, ModelID
    COMPLEXITY_MODEL_MAP[TaskComplexity.TRIVIAL] = ModelID.GPT4O_MINI
    logger.info("Ollama absent — TRIVIAL tasks routed to GPT-4o-mini")
```

`settings` is the `LLMSettings()` instance which reads `.env` via pydantic-settings (`model_config = {"env_file": ".env"}`). This is safe in both local dev and ECS.

### 0c. CloudFront Content-Type Forwarding
**File**: `console/aws/frontend.tf`

**Problem**: `/api/*` cache behavior (line 85) only forwards `Authorization, Origin, Accept`. Missing `Content-Type` means JSON POSTs (login, agent invocations) break.

**Fix**:
```hcl
headers = ["Authorization", "Origin", "Accept", "Content-Type"]
```

---

## Step 1: Console Authentication — Frontend

**Files to create/modify:**
- `console/frontend/src/pages/LoginPage.tsx` — **NEW** login form
- `console/frontend/src/lib/auth.tsx` — **NEW** auth context + guard component
- `console/frontend/src/lib/api.ts` — **MODIFY** add `credentials: 'include'` to all fetch calls + handle 401 redirect
- `console/frontend/src/App.tsx` — **MODIFY** add AuthProvider, /login route, AuthGuard wrapper

**Auth transport: httpOnly cookie** (not Bearer header, not localStorage).

The backend `POST /api/auth/login` sets:
```
Set-Cookie: forge_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400
```

The frontend `api.ts` adds `credentials: 'include'` to every `fetch()` call. The browser automatically attaches the cookie on all same-origin requests. No token storage in JavaScript, no Bearer injection, no XSS exposure.

**WebSocket auth**: The browser automatically sends cookies on WebSocket handshake via the `Cookie` header. No changes needed to `ws.ts` — it already constructs same-origin URLs (line 29: `${protocol}//${window.location.host}${path}`). The backend reads the cookie from the WS handshake headers. This is the simplest and most secure approach.

**Note**: `SameSite=Lax` (not `Strict`) because `Strict` blocks cookies on initial navigation from external links.

**api.ts changes** — all 4 functions (`fetchJson`, `postJson`, `putJson`, `deleteJson`) get `credentials: 'include'`:
```typescript
const res = await fetch(`${BASE}${path}`, { credentials: 'include' });
```
On 401 response, `window.location.href = '/login'`.

**LoginPage**: Email + password form, dark theme. POST `/api/auth/login` with `credentials: 'include'` -> cookie set automatically -> redirect to `/`.

---

## Step 2: Console Authentication — Backend

**Files to create/modify:**
- `console/backend/app/routers/auth.py` — **NEW** `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout`
- `console/backend/app/auth.py` — **NEW** JWT create/verify + cookie extraction + `require_auth` FastAPI dependency
- `console/backend/app/config.py` — **MODIFY** add `console_user_email`, `console_user_password`, `console_jwt_secret`
- `console/backend/app/main.py` — **MODIFY** mount auth router, add auth middleware
- `console/backend/app/routers/execution.py` — **MODIFY** add cookie-based auth to WS endpoints
- `console/backend/app/routers/health.py` — **MODIFY** propagate upstream status code
- `console/backend/pyproject.toml` — **MODIFY** add `python-jose[cryptography]`

**Login endpoint**: Validate email+password with `hmac.compare_digest` (constant-time). Set `forge_token` httpOnly cookie (24h expiry). Return `{"email": "..."}` in JSON body (no token in body).

**Logout endpoint**: Clear cookie via `Set-Cookie: forge_token=; Max-Age=0; Path=/`.

**Auth middleware skip list** (exact path + method match, NOT prefix):
- `POST /api/auth/login`
- `GET /api/health` (exact — NOT `/api/health/*` or `/api/health/circuit-breakers`)

**WebSocket auth** (execution.py): Before `accept()`, read cookie from handshake:
```python
@router.websocket("/ws/execution")
async def ws_execution(websocket: WebSocket):
    token = websocket.cookies.get("forge_token")
    if not token or not verify_console_token(token):
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    # ... rest unchanged
```

Apply same pattern to `/ws/logs`.

**Console health proxy fix** (`health.py:14`): Currently returns 200 regardless of upstream status. Fix:
```python
return JSONResponse(data, status_code=resp.status_code)
```

---

## Step 3: ecom-agents Dockerfile

**File to create**: `ecom-agents/Dockerfile`

**IMPORTANT**: No `requirements.txt` exists. The project uses `pyproject.toml` with setuptools (`build-system` at `pyproject.toml:66`). Dockerfile uses `pip install .`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .
ENV PYTHONUTF8=1
EXPOSE 8050
CMD ["python", "-m", "uvicorn", "src.serve:app", "--host", "0.0.0.0", "--port", "8050"]
```

---

## Step 4: Terraform Fixes

### ecs.tf — Environment Variable Fixes
Replace the wrong individual vars with what the code actually reads:

```hcl
# REMOVE from ecom-agents container:
#   POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER
#   REDIS_HOST, REDIS_PORT, OLLAMA_BASE_URL (localhost ref)

# ADD as secret (contains password in URL):
{ name = "DATABASE_URL", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:DATABASE_URL::" }

# ADD as plain environment:
{ name = "REDIS_URL",       value = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0" }
{ name = "CHROMA_URL",      value = "http://chromadb.${var.project_name}.local:8000" }
{ name = "OLLAMA_BASE_URL", value = "" }
```

### secrets.tf — Compute full DATABASE_URL
```hcl
locals {
  database_url = "postgresql://ecom_admin:${random_password.db_password.result}@${aws_db_instance.postgres.address}:5432/ecom_agents"
}

resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id
  secret_string = jsonencode({
    LANGSMITH_API_KEY      = var.langsmith_api_key
    OPENAI_API_KEY         = var.openai_api_key
    ANTHROPIC_API_KEY      = var.anthropic_api_key
    SHOPIFY_ACCESS_TOKEN   = var.shopify_access_token
    STRIPE_SECRET_KEY      = var.stripe_secret_key
    PRINTFUL_API_KEY       = var.printful_api_key
    INSTAGRAM_ACCESS_TOKEN = var.instagram_access_token
    DATABASE_URL           = local.database_url
    AUTH_SECRET_KEY        = var.auth_secret_key
    CONSOLE_JWT_SECRET     = var.console_jwt_secret
    CONSOLE_PASSWORD       = var.console_password
  })
}
```

### ecs.tf — ChromaDB Service + EFS
Add ChromaDB task definition (image: `chromadb/chroma:latest`, port 8000), ECS service, Service Discovery (`chromadb.forge-console.local`), EFS volume mount at `/chroma/chroma`.

### EFS Resources
```hcl
resource "aws_efs_file_system" "chromadb" {
  tags = { Name = "${var.project_name}-chromadb-efs" }
}

resource "aws_security_group" "efs" {
  name_prefix = "${var.project_name}-efs-"
  vpc_id      = aws_vpc.main.id
  ingress {
    from_port       = 2049    # NFS
    to_port         = 2049
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }
}

resource "aws_efs_mount_target" "chromadb" {
  count           = 2                                    # One per AZ
  file_system_id  = aws_efs_file_system.chromadb.id
  subnet_id       = aws_subnet.private[count.index].id
  security_groups = [aws_security_group.efs.id]
}
```

ChromaDB task definition `volume` + `mountPoints`:
```hcl
volumes = [{
  name = "chromadb-data"
  efsVolumeConfiguration = {
    fileSystemId = aws_efs_file_system.chromadb.id
  }
}]
# In container definition:
mountPoints = [{
  sourceVolume  = "chromadb-data"
  containerPath = "/chroma/chroma"
}]
```

### forge-backend Console Auth Env Vars
```hcl
{ name = "FORGE_CONSOLE_USER_EMAIL",    value = "sean.p.allen9@gmail.com" }
{ name = "FORGE_CONSOLE_USER_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONSOLE_PASSWORD::" }
{ name = "FORGE_CONSOLE_JWT_SECRET",    valueFrom = "${aws_secretsmanager_secret.app_secrets.arn}:CONSOLE_JWT_SECRET::" }
```

### variables.tf — New Variables
```hcl
variable "console_jwt_secret" { type = string; sensitive = true }
variable "auth_secret_key"    { type = string; sensitive = true }
variable "console_password"   { type = string; sensitive = true; default = "admin" }
```

### frontend.tf — Content-Type Header
Add `Content-Type` to forwarded headers (Step 0c).

### deploy.sh — Fix Dockerfile Path
```bash
ECOM_ROOT="$(dirname "$PROJECT_ROOT")"  # ecom-agents/ root
docker build -t forge-console/ecom-agents:latest "$ECOM_ROOT"
```

**Service token**: Generate scoped `operator` JWT (365d TTL) signed with production `AUTH_SECRET_KEY`. Store in Secrets Manager. Rotate annually.

---

## Step 5: Pre-Deploy Checklist

- [ ] AWS CLI: `aws sts get-caller-identity` succeeds
- [ ] Terraform >= 1.5
- [ ] Docker Desktop running
- [ ] Step 0 code fixes implemented and tested locally
- [ ] Console auth (Steps 1-2) implemented and tested locally
- [ ] ecom-agents Dockerfile builds: `docker build -t ecom-agents .`
- [ ] `console/aws/terraform.tfvars` created from `drawbridge.txt`
- [ ] Production secrets generated (`console_jwt_secret`, `auth_secret_key`)
- [ ] `terraform.tfvars` and `drawbridge.txt` in `.gitignore`
- [ ] Full local test: login -> 12 pages -> WS streaming -> 401 on /api -> 4001 on /ws

---

## Step 6: Deploy Sequence

All commands assume you start from the workspace root: `c:\Users\seanp\Workspace\ecom-agents\`

```bash
cd c:\Users\seanp\Workspace\ecom-agents\console\aws
./deploy.sh init        # terraform init
./deploy.sh build       # docker build ecom-agents + forge-backend
./deploy.sh deploy      # terraform apply (VPC, ECS, RDS, Redis, EFS, ALB, CloudFront)
./deploy.sh push        # docker push to ECR
./deploy.sh deploy      # force ECS redeployment with new images
./deploy.sh frontend    # npm build + S3 upload + CloudFront invalidation
```

---

## Step 7: Post-Deploy Verification

1. ECS tasks: 3 services `runningCount: 1` (ecom-agents, forge-backend, chromadb)
2. Health: `curl https://<cf-url>/api/health` -> 200 `"status": "degraded"` (Ollama absent)
3. Auth HTTP: `curl https://<cf-url>/api/agents` -> 401
4. Auth WS: `wscat -c wss://<cf-url>/ws/logs` -> closed 4001
5. Login: CloudFront URL -> `/login` -> creds -> dashboard
6. All 12 pages load
7. WS: Logs page streams real-time (cookie sent on handshake)
8. CloudWatch: No ERROR entries

---

## Step 8: Email Production URL

Email `sean.p.allen9@gmail.com`:
- Subject: "Forge Console — Live"
- Body: CloudFront URL only

---

## Implementation Order

1. **Step 0** — Code fixes (health, model remap, CloudFront headers)
2. **Steps 1-2** — Console auth (cookie-based, frontend + backend + WS)
3. **Step 3** — ecom-agents Dockerfile (pyproject.toml-based)
4. **Step 4** — Terraform (env vars, DATABASE_URL secret, EFS, ChromaDB, auth vars)
5. **Step 5** — Pre-deploy checklist
6. **Step 6** — Deploy
7. **Steps 7-8** — Verify + Email

---

## Cost Estimate (~$132/mo)

| Resource | Est. Cost |
|---|---|
| ECS Fargate (3 tasks x 0.5 vCPU / 1 GB) | ~$45 |
| NAT Gateway | ~$35 |
| ALB | ~$18 |
| RDS db.t4g.micro | ~$15 |
| ElastiCache cache.t4g.micro | ~$12 |
| EFS (ChromaDB persistence) | ~$5 |
| CloudFront + S3 + Secrets Manager | ~$2 |

---

## Review Findings Addressed (v1 -> v2 -> v3 Changelog)

| # | Finding | Sev | Resolution |
|---|---|---|---|
| 1 | Ollama hard-fail blocks ECS health | Crit | 0a: `/health` returns 200 degraded when only Ollama down |
| 2 | `CHROMADB_HOST` -> `CHROMA_URL` | Crit | Step 4: Terraform uses `CHROMA_URL` |
| 3 | `POSTGRES_HOST/PORT` -> `DATABASE_URL` | Crit | Step 4: Full URL in TF `locals`, stored as single secret |
| 4 | `REDIS_HOST/PORT` -> `REDIS_URL` | Crit | Step 4: Terraform uses `REDIS_URL` |
| 5 | WS endpoints unauthenticated | Crit | Step 2: Cookie from WS handshake headers |
| 6 | `ORCHESTRATOR_MODEL` phantom env var | Crit | 0b: Remap via `LLMSettings` after `load_dotenv()` |
| 7 | Step 0b import order race | Crit | 0b: Remap in `serve.py` post-init, not at config.py module level |
| 8 | No requirements.txt | Crit | Step 3: Dockerfile uses `pip install .` with pyproject.toml |
| 9 | DATABASE_URL can't compose from secret | Crit | Step 4: TF `locals {}` computes URL at apply time |
| 10 | Static admin token = full compromise | High | Step 4: `operator` role, 365d TTL, rotation doc |
| 11 | localStorage XSS risk | High | Step 1: httpOnly cookie |
| 12 | Bearer vs cookie doc inconsistency | High | Steps 1-2: Cookie only throughout |
| 13 | WS auth needs ws.ts changes | High | Step 1: Cookie-based, zero ws.ts changes |
| 14 | `ollama_fallback_active` dead code | High | 0a: Acknowledged, not relied upon |
| 15 | Emailing credentials | High | Step 8: URL only |
| 16 | ChromaDB data loss on restart | Med | Step 4: EFS mount with NFS SG + per-AZ targets |
| 17 | CloudFront missing Content-Type | Med | 0c: Added to forwarded headers |
| 18 | `/api/health` prefix vs exact match | Med | Step 2: Exact path match in skip list |
| 19 | Console health swallows 503 | Med | Step 2: Propagate upstream status code |
| 20 | EFS NFS SG / mount targets per AZ | Med | Step 4: Port 2049 SG, 2 mount targets |
