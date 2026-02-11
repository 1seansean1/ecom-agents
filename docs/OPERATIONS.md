# Operations

> How to run, deploy, monitor, and fix Holly Grace.
> Last validated: 2026-02-11

---

## Quick Start (Local Dev)

```bash
# 1. Clone
git clone https://github.com/1seansean1/ecom-agents.git
cd ecom-agents

# 2. Python environment
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. Docker services
docker compose up -d
# Verify: postgres:5434, redis:6381, chromadb:8100, ollama:11435

# 4. Environment
cp .env.example .env   # Fill in API keys

# 5. Ollama model (if using local LLM)
docker exec holly-ollama ollama pull qwen2.5:3b

# 6. Start agents server
set PYTHONUTF8=1
python -m uvicorn src.serve:app --host 0.0.0.0 --port 8050

# 7. Start console
cd console/backend && pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8060
cd ../frontend && npm install && npm run dev  # :3000
```

**Verify**: `curl http://localhost:8050/health` → `{"status": "healthy"}`.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | Yes | — | Redis connection string |
| `OPENAI_API_KEY` | Yes | — | GPT-4o, GPT-4o-mini |
| `ANTHROPIC_API_KEY` | Yes | — | Claude Opus 4.6 (Holly) |
| `SHOPIFY_ACCESS_TOKEN` | Yes | — | Shopify store access |
| `SHOPIFY_SHOP_URL` | Yes | — | e.g., liberty-forge-2.myshopify.com |
| `STRIPE_SECRET_KEY` | Yes | — | Stripe payments |
| `PRINTFUL_API_KEY` | Yes | — | Print-on-demand fulfillment |
| `OLLAMA_BASE_URL` | No | — | Empty = remap to GPT-4o-mini |
| `CHROMA_URL` | No | http://localhost:8100 | ChromaDB vector store |
| `LANGSMITH_API_KEY` | No | — | Tracing (optional but recommended) |
| `LANGSMITH_TRACING_V2` | No | false | Enable LangSmith tracing |
| `AUTH_SECRET_KEY` | Yes | — | JWT signing key (agents + console) |
| `HOLLY_AUTONOMOUS` | No | 0 | Set to 1 for autonomous mode |
| `HOLLY_COOKIE_SECURE` | No | — | Force Secure cookie flag |
| `CORS_ALLOWED_ORIGINS` | No | localhost:3000,localhost:8050 | Allowed CORS origins |

### Docker Compose Ports (Local Dev)

| Service | Host Port | Container Port |
|---------|-----------|----------------|
| PostgreSQL | 5434 | 5432 |
| Redis | 6381 | 6379 |
| ChromaDB | 8100 | 8000 |
| Ollama | 11435 | 11434 |

---

## Deployment (AWS ECS Fargate)

### Pre-Deploy Checklist

- [ ] All tests pass locally
- [ ] Secrets updated in AWS Secrets Manager if changed
- [ ] `HOLLY_AUTONOMOUS=1` set in task definition
- [ ] Current image tag noted (for rollback)
- [ ] No active Tower runs in progress (check `/tower/runs?status=running`)

### Deploy Pipeline (7 Steps)

```powershell
# 0. Find current image tag
aws ecr describe-images --repository-name holly-grace/holly-grace --region us-east-2 `
  --query 'sort_by(imageDetails,& imagePushedAt)[-1].imageTags[0]' --output text
# Increment this → vN

# 1. Build (exit code 1 is normal — Docker Scout prints a suggestion)
docker build -f Dockerfile.production -t holly-grace:vN .

# 2. Tag
docker tag holly-grace:vN 327416545926.dkr.ecr.us-east-2.amazonaws.com/holly-grace/holly-grace:vN

# 3. Auth
aws ecr get-login-password --region us-east-2 | docker login --username AWS --password-stdin 327416545926.dkr.ecr.us-east-2.amazonaws.com

# 4. Push
docker push 327416545926.dkr.ecr.us-east-2.amazonaws.com/holly-grace/holly-grace:vN

# 5. Update task definition
# Edit deploy/task-definition.json → change image tag to :vN
aws ecs register-task-definition --cli-input-json file://deploy/task-definition.json --region us-east-2

# 6. Deploy (use the revision number from step 5 output)
aws ecs update-service --cluster holly-grace-cluster --service holly-grace `
  --task-definition holly-grace-holly-grace:REVISION `
  --force-new-deployment --desired-count 1 --region us-east-2

# 7. Wait and verify
aws ecs wait services-stable --cluster holly-grace-cluster --services holly-grace --region us-east-2
Invoke-RestMethod -Uri 'http://holly-grace-alb-708960690.us-east-2.elb.amazonaws.com/api/health'
```

> **Note — Windows/PowerShell gotchas:**
> - Use `Invoke-RestMethod` not `curl` (PowerShell aliases `curl` to `Invoke-WebRequest` which has different flags)
> - Use backtick `` ` `` for line continuation, not `\`
> - Use `;` to chain commands, not `&&` (which is invalid in PowerShell 5.x)
> - Docker build may return exit code 1 even on success due to Docker Scout output — check for "naming to docker.io/..." in the output to confirm the image was created

### Post-Deploy Verification

**Without auth (immediate — run from terminal):**

1. Health check: `GET /api/health` → expect `"status": "degraded"` (not "healthy" — Ollama is absent in production, which is expected per ADR-001; critical checks postgres/redis/chromadb must all be `true`)
2. CloudWatch: No ERROR-level logs in the first 5 minutes:
   ```powershell
   aws logs filter-log-events --log-group-name '/ecs/holly-grace/holly-grace' `
     --filter-pattern 'ERROR' `
     --start-time ([DateTimeOffset]::UtcNow.AddMinutes(-5).ToUnixTimeMilliseconds()) `
     --region us-east-2 --query 'events[*].message' --output json
   ```

**With auth (requires browser login to console):**

3. Login: Console login works at `http://holly-grace-alb-708960690.us-east-2.elb.amazonaws.com`
4. Holly: Send a message in the Holly sidebar — should stream a response
5. Scheduler: `GET /api/scheduler/jobs` shows 18+ jobs (visible on Scheduler page)
6. Autonomy: `GET /api/holly/autonomy/status` shows `running: true`, `thread_alive: true` (if HOLLY_AUTONOMOUS=1)

> **Why "degraded" is normal:** The health check includes an Ollama check. Production doesn't run Ollama (it remaps to GPT-4o-mini). The ALB health check targets `/api/health` with a 200 status code expectation — this passes because all *critical* checks (postgres, redis, chromadb) are healthy (HTTP 200). Ollama failure only downgrades status text to "degraded", not the HTTP status code.

### Rollback

**A. Quick rollback (revert to previous task definition):**
```bash
aws ecs update-service --cluster holly-grace-cluster --service holly-grace --task-definition holly-grace-holly-grace:PREVIOUS_REVISION --force-new-deployment --desired-count 1 --region us-east-2
```

**B. Image rollback (revert to previous image tag):**
Edit `deploy/task-definition.json` → revert image tag → register + deploy.

**C. Emergency stop:**
```bash
aws ecs update-service --cluster holly-grace-cluster --service holly-grace --desired-count 0 --region us-east-2
```

---

## Runbooks

### A. Ticket Backlog

**Symptom**: Tower inbox shows 10+ pending tickets with no decisions.

**Diagnosis**:
```bash
curl http://localhost:8050/tower/inbox?status=pending
```

**Resolution**:
1. Check if Holly autonomy is running: `GET /holly/autonomy/status`
2. If paused → resume: `POST /holly/autonomy/resume`
3. If running but not processing → check Anthropic API credits
4. Bulk approve low-risk tickets via console Tower page
5. For high-risk: review individually in Holly sidebar

### B. Workflow Failure

**Symptom**: Tower run stuck in `failed` status.

**Diagnosis**:
```bash
curl http://localhost:8050/tower/runs/RUN_ID
curl http://localhost:8050/tower/runs/RUN_ID/events
```

**Resolution**:
1. Check events for error cause (timeout, API error, tool failure)
2. If API error → check API key validity and balance
3. If timeout → check if task is too complex for 5-min timeout
4. Retry: `POST /tower/runs/start` with same input
5. Check DLQ: `GET /scheduler/dlq` — failed scheduled tasks land here

### C. Autonomy Degradation

**Symptom**: Holly's autonomy status shows `consecutive_errors > 5` or `paused`.

**Diagnosis**:
```bash
curl http://localhost:8050/holly/autonomy/status
curl http://localhost:8050/holly/autonomy/audit?limit=10
```

**Resolution**:
1. Check audit log for error patterns
2. If credit_paused → top up Anthropic credits at console.anthropic.com
3. If repeated failures → check system health: `GET /health`
4. Resume after fixing: `POST /holly/autonomy/resume`
5. Clear stuck tasks if needed: `DELETE /holly/autonomy/queue`

### D. Deployment Recovery

**Symptom**: ECS task STOPPED or unhealthy after deployment.

**Diagnosis**:
```bash
aws ecs describe-tasks --cluster holly-grace-cluster --tasks $(aws ecs list-tasks --cluster holly-grace-cluster --service-name holly-grace --query 'taskArns[0]' --output text --region us-east-2) --region us-east-2
# Check stoppedReason
aws logs tail /ecs/holly-grace/holly-grace --since 5m --region us-east-2
```

**Resolution**:
1. Check `stoppedReason` — usually OOM, health check fail, or startup crash
2. If OOM → increase memory in task definition (current: 2048 MB)
3. If health check → check startup logs for module import errors
4. If startup crash → rollback to previous task definition revision
5. Ensure `--desired-count 1` is set (service may have scaled to 0)

### E. Secrets Exposure

**Symptom**: Secret detected in logs, git history, or API response.

**Immediate**:
1. Rotate the exposed key immediately (API provider dashboard)
2. Update in AWS Secrets Manager: `holly-grace/production/secrets-TVmKFm`
3. Redeploy with new task definition revision
4. Check output_validator.py patterns — add new pattern if not covered
5. Scan git history: `git log --all -p | grep -i "sk-\|AKIA\|shpat_"`
6. If in git history → consider repo rotation (secrets are in git forever)

---

## Monitoring

### Key Health Endpoints

| Endpoint | What It Shows |
|----------|--------------|
| `GET /health` | Service health — returns "degraded" in prod (no Ollama); critical: postgres, redis, chromadb must be `true` |
| `GET /holly/autonomy/status` | Autonomy loop: running, paused, queue depth, errors |
| `GET /scheduler/jobs` | All 18 scheduled jobs with next run time |
| `GET /scheduler/dlq` | Dead letter queue (failed tasks awaiting retry) |
| `GET /tower/inbox?status=pending` | Pending Tower tickets |
| `GET /tower/runs?status=running` | Currently executing runs |
| `GET /hierarchy/gate` | Gate status for all 7 levels |
| `GET /holly/autonomy/audit?limit=10` | Recent autonomous task outcomes |
| `GET /circuit-breakers` | Circuit breaker states |

### CloudWatch Commands

```powershell
# Tail logs (Linux/WSL)
aws logs tail /ecs/holly-grace/holly-grace --follow --region us-east-2

# Search for errors (PowerShell — last hour)
aws logs filter-log-events --log-group-name '/ecs/holly-grace/holly-grace' `
  --filter-pattern 'ERROR' `
  --start-time ([DateTimeOffset]::UtcNow.AddHours(-1).ToUnixTimeMilliseconds()) `
  --region us-east-2 --query 'events[*].message' --output json

# Search for errors (Linux/WSL — last hour)
aws logs filter-log-events --log-group-name /ecs/holly-grace/holly-grace \
  --filter-pattern "ERROR" --start-time $(date -d '1 hour ago' +%s000) --region us-east-2
```

---

## Feature Intake — Four Questions Gate

Before adding any new feature, answer:

1. **Does it serve an active goal in the hierarchy?** If not, it's a distraction.
2. **Does it increase Jacobian rank?** If yes, it needs Tier 2 approval and governance margin check.
3. **Can an existing agent handle it?** If yes, reconfigure — don't spawn.
4. **Is the ε interval feasible?** If you can't measure success, don't build it.

### Project-Specific Gotchas

**Code:**
- SQL: Never use f-strings in SQL — use parameterized queries (scanner flags violations)
- Hypothesis tests: Always use `deadline=None` + `suppress_health_check` with function-scoped fixtures
- Mock paths: Lazy imports inside functions → patch at source module, not caller
- LangGraph 0.6.x: `interrupt()` with checkpointer doesn't raise `GraphInterrupt` — detect via `snapshot.next`
- Cookies: ALB over HTTP → don't set `Secure` flag (conditional on X-Forwarded-Proto)

**Testing:**
- Any test calling `_execute_task()` must mock `_log_audit` — it connects to Postgres and will hang without Docker
- `bool(MagicMock())` is `True` — always set `.return_value` explicitly when code checks truthiness
- Thread liveness tests: mock long-running targets to block (not return instantly) to avoid timing races with `is_alive()`

**Environment (Windows):**
- Set `PYTHONUTF8=1` before running agents server
- Use `py -3.11` (3.14 is default but too new for most packages)
- Docker build exit code 1 is normal (Docker Scout output) — check for "naming to docker.io/..." to confirm success
- PowerShell: use `Invoke-RestMethod` not `curl`, use `;` not `&&`, use heredoc (`@' ... '@`) for multiline git commit messages
- Docker: GPU passthrough needs `deploy.resources.reservations.devices` in compose

**Deployment:**
- Always pin the task definition revision in `update-service` (e.g., `holly-grace-holly-grace:16`), don't rely on `:latest`
- Commit `deploy/task-definition.json` image tag bump separately so it's in git history for rollback reference
- `/health` returns "degraded" in production (Ollama absent) — this is expected; verify critical checks are `true`
- Most API endpoints require JWT auth — only `/health` is verifiable without logging in
