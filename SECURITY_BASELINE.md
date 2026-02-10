# Security Baseline - ecom-agents

**Date**: 2026-02-08
**Commit**: 5c6c334 (verified via pip freeze)
**Audited by**: Automated + manual review

## Route Inventory (53 endpoints)

All routes extracted from `src/serve.py` app.routes introspection.

| # | Method | Path | Auth | Category |
|---|--------|------|------|----------|
| 1 | GET | `/` | NONE | Info |
| 2 | GET | `/health` | NONE | Health |
| 3 | GET | `/scheduler/jobs` | NONE | Scheduler |
| 4 | POST | `/scheduler/trigger/{job_id}` | NONE | Scheduler |
| 5 | GET | `/graph/definition` | NONE | Graph |
| 6 | GET | `/graph/metadata` | NONE | Graph |
| 7 | GET | `/circuit-breakers` | NONE | Resilience |
| 8 | WS | `/ws/events` | NONE | WebSocket |
| 9 | GET | `/aps/metrics` | NONE | APS |
| 10 | GET | `/aps/metrics/{channel_id}` | NONE | APS |
| 11 | GET | `/aps/partitions` | NONE | APS |
| 12 | POST | `/aps/switch/{channel_id}/{theta_id}` | NONE | APS |
| 13 | GET | `/aps/chain-capacity` | NONE | APS |
| 14 | POST | `/aps/evaluate` | NONE | APS |
| 15 | GET | `/aps/trace/{trace_id}` | NONE | APS |
| 16 | GET | `/aps/cache` | NONE | APS |
| 17 | GET | `/agents/{agent_id}/efficacy` | NONE | Efficacy |
| 18 | POST | `/agents/efficacy/compute` | NONE | Efficacy |
| 19 | GET | `/agents` | NONE | Agent CRUD |
| 20 | GET | `/agents/{agent_id}` | NONE | Agent CRUD |
| 21 | POST | `/agents` | NONE | Agent CRUD |
| 22 | PUT | `/agents/{agent_id}` | NONE | Agent CRUD |
| 23 | DELETE | `/agents/{agent_id}` | NONE | Agent CRUD |
| 24 | GET | `/agents/{agent_id}/versions` | NONE | Agent CRUD |
| 25 | GET | `/agents/{agent_id}/versions/{version}` | NONE | Agent CRUD |
| 26 | POST | `/agents/{agent_id}/rollback` | NONE | Agent CRUD |
| 27 | GET | `/agents/{agent_id}/default` | NONE | Agent CRUD |
| 28 | GET | `/tools` | NONE | Tool Registry |
| 29 | GET | `/workflows` | NONE | Workflow CRUD |
| 30 | GET | `/workflows/{workflow_id}` | NONE | Workflow CRUD |
| 31 | POST | `/workflows` | NONE | Workflow CRUD |
| 32 | PUT | `/workflows/{workflow_id}` | NONE | Workflow CRUD |
| 33 | DELETE | `/workflows/{workflow_id}` | NONE | Workflow CRUD |
| 34 | POST | `/workflows/{workflow_id}/activate` | NONE | Workflow CRUD |
| 35 | POST | `/workflows/{workflow_id}/compile` | NONE | Workflow CRUD |
| 36 | GET | `/workflows/{workflow_id}/versions` | NONE | Workflow CRUD |
| 37 | GET | `/workflows/{workflow_id}/versions/{version}` | NONE | Workflow CRUD |
| 38 | POST | `/workflows/{workflow_id}/rollback` | NONE | Workflow CRUD |
| 39 | GET | `/scheduler/dlq` | NONE | DLQ |
| 40 | POST | `/scheduler/dlq/{dlq_id}/retry` | NONE | DLQ |
| 41 | GET | `/approvals` | NONE | Approvals |
| 42 | GET | `/approvals/stats` | NONE | Approvals |
| 43 | GET | `/approvals/{approval_id}` | NONE | Approvals |
| 44 | POST | `/approvals/{approval_id}/approve` | NONE | Approvals |
| 45 | POST | `/approvals/{approval_id}/reject` | NONE | Approvals |
| 46 | POST | `/eval/run` | NONE | Eval |
| 47 | GET | `/eval/results` | NONE | Eval |
| 48 | GET | `/eval/results/{suite_id}` | NONE | Eval |
| 49 | GET | `/morphogenetic/snapshot` | NONE | Morphogenetic |
| 50 | GET | `/morphogenetic/trajectory` | NONE | Morphogenetic |
| 51 | GET | `/morphogenetic/goals` | NONE | Morphogenetic |
| 52 | GET | `/morphogenetic/assembly` | NONE | Morphogenetic |
| 53 | GET | `/morphogenetic/cascade` | NONE | Morphogenetic |
| 54 | POST | `/morphogenetic/evaluate` | NONE | Morphogenetic |
| 55 | POST | `/morphogenetic/goals` | NONE | Goal CRUD |
| 56 | PUT | `/morphogenetic/goals/{goal_id}` | NONE | Goal CRUD |
| 57 | DELETE | `/morphogenetic/goals/{goal_id}` | NONE | Goal CRUD |
| 58 | POST | `/morphogenetic/goals/reset` | NONE | Goal CRUD |
| 59 | GET | `/morphogenetic/cascade/config` | NONE | Cascade Config |
| 60 | PUT | `/morphogenetic/cascade/config` | NONE | Cascade Config |
| 61 | POST | `/morphogenetic/cascade/config/reset` | NONE | Cascade Config |
| 62 | GET | `/system/export` | NONE | System |
| 63 | POST | `/system/import` | NONE | System |
| 64 | POST | `/system/import/preview` | NONE | System |
| 65 | GET | `/system/images` | NONE | System |
| 66 | GET | `/system/images/{image_id}` | NONE | System |
| 67 | GET | `/executions/{thread_id}/checkpoints` | NONE | Checkpoints |
| L1 | POST | `/agent/invoke` | NONE | LangServe |
| L2 | POST | `/agent/batch` | NONE | LangServe |
| L3 | POST | `/agent/stream` | NONE | LangServe |
| L4 | POST | `/agent/stream_log` | NONE | LangServe |
| L5 | GET | `/agent/input_schema` | NONE | LangServe |
| L6 | GET | `/agent/output_schema` | NONE | LangServe |
| L7 | GET | `/agent/config_schema` | NONE | LangServe |
| L8 | GET | `/agent/playground/*` | NONE | LangServe |

**Total**: 67+ HTTP routes + 1 WebSocket. **All unauthenticated.**

## Existing Security Controls

| Control | Status | Location | Notes |
|---------|--------|----------|-------|
| Authentication middleware | MISSING | - | No auth on any endpoint |
| Authorization/RBAC | MISSING | - | No role checks |
| CORS middleware | MISSING | - | CORSMiddleware not imported |
| Rate limiting | MISSING | - | No API-level rate limiting |
| Input validation (guardrails) | PRESENT | `src/guardrails/input_validator.py` | Max 10K chars, PII detection, prompt injection detection (6 patterns), SQL injection detection, secret detection |
| Output sanitization | PRESENT | `src/guardrails/output_validator.py` | Redacts Stripe keys, Shopify tokens, AWS keys, Bearer tokens, passwords, SSN, credit cards |
| SQL parameterization | PRESENT | `src/aps/store.py` | All 400+ queries use %s placeholders -- verified safe |
| Idempotency | PRESENT | `src/resilience/idempotency.py` | Redis-based dedup |
| Circuit breakers | PRESENT | `src/resilience/circuit_breaker.py` | Per-tool breakers |
| WebSocket auth | MISSING | `src/serve.py:207` | Accepts all connections |
| WebSocket origin check | MISSING | `src/serve.py:207` | No origin validation |

## Secret Exposure Audit

### Endpoints that expose sensitive data

| Endpoint | Exposure | Severity |
|----------|----------|----------|
| GET `/agents` | Returns `system_prompt` for all agents | HIGH |
| GET `/agents/{agent_id}` | Returns full `system_prompt` | HIGH |
| GET `/agents/{agent_id}/versions/{version}` | Returns historical system prompts | HIGH |
| GET `/system/export` | Returns full system config including all agent prompts | CRITICAL |
| GET `/graph/definition` | Exposes internal graph structure | MEDIUM |
| GET `/graph/metadata` | Exposes model IDs and internal metrics | MEDIUM |
| Any error response | `str(e)` may leak internal paths/config | MEDIUM |

### Secrets NOT directly exposed in responses
- API keys (OPENAI, ANTHROPIC, STRIPE, SHOPIFY, PRINTFUL, INSTAGRAM) -- loaded from env, not returned in responses
- Database URL -- not returned in any response
- Redis URL -- not returned in any response

## External API Key Handling

| Tool | Key Source | Transport | Issue |
|------|-----------|-----------|-------|
| Instagram | `INSTAGRAM_ACCESS_TOKEN` env var | Query parameter in URL | Token in URL (logged by intermediaries) |
| Shopify | `SHOPIFY_ACCESS_TOKEN` env var | `X-Shopify-Access-Token` header | OK |
| Stripe | `STRIPE_SECRET_KEY` env var | SDK-managed | OK |
| Printful | `PRINTFUL_API_KEY` env var | `Authorization: Bearer` header | OK |

## Test Suite Status

- **Total tests**: 341 (collected via pytest --collect-only)
- **Test files**: 20 (in tests/)
- **Security tests**: 0
- **tests/security/ directory**: Does not exist

## Dependency Snapshot

- **Python**: 3.11.9
- **Total packages**: 150 (pip freeze)
- **Key versions**: FastAPI 0.128.2, uvicorn 0.40.0, langchain 0.3.27, langgraph 0.6.11, psycopg 3.3.2, redis 5.3.1, stripe 11.6.0
- **Docker services**: Postgres 16-alpine, Redis 7-alpine, ChromaDB latest, Ollama latest

## Docker Compose

- Postgres: port 5434 (external) -> 5432 (internal)
- Redis: port 6381 (external) -> 6379 (internal)
- ChromaDB: port 8100 (external) -> 8000 (internal)
- Ollama: port 11435 (external) -> 11434 (internal), GPU passthrough enabled
