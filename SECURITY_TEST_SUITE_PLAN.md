# Security Test Suite Plan for ecom-agents

## Context

The ecom-agents codebase is a **live, 24/7 autonomous e-commerce system** processing real Shopify orders, Stripe payments, and Instagram posts. A security review has identified **critical vulnerabilities** — every API endpoint and the WebSocket are completely unauthenticated, there is no rate limiting, secrets are managed in plaintext, and the system exposes internal architecture publicly. No security tests exist today (0 out of 60 current tests address security).

This plan defines the security test suite to be written **alongside** (and immediately after) each security fix, following the "production bugs must become tests" principle (Google SRE) and shift-left methodology from the *Software Testing Analysis* document. Each test is designed to **falsify** the security property — per Myers, "testing is running a program with the intention of finding errors."

---

## Guiding Principles (from Software_Testing_Analysis_Claude.pdf)

| Principle | Application |
|-----------|-------------|
| **Risk-Based School** (FMEA) | Prioritize tests by severity: Critical auth/authz first, then rate limiting, then secrets, then info disclosure |
| **Test Pyramid** (60-30-10 for microservices) | ~60% unit tests (input validation, secret handling), ~30% integration (endpoint auth, middleware), ~10% E2E (full attack scenarios) |
| **FIRST** (Feathers) | Fast (no real APIs), Isolated (mock externals), Repeatable (no timing deps), Self-checking (assert-based), Timely (written with fixes) |
| **AAA Pattern** (Wake) | Every test: Arrange (setup state/request), Act (call endpoint/function), Assert (verify security property) |
| **Narrow Integration Tests** (Fowler) | Test only the security boundary code with test doubles for LLMs/APIs |
| **Property-Based Testing** (Hypothesis) | Fuzz input validation boundaries with random payloads |
| **Contract Testing** | API endpoints enforce auth contracts — consumer tests verify rejection of unauthorized requests |
| **Falsificationism** (Dijkstra/Myers) | Tests prove the *presence* of security — each test must fail without the fix and pass with it |

---

## Test Architecture

### New Files

```
tests/
    security/
        __init__.py
        conftest.py                    # Security test fixtures (auth tokens, attack payloads, test client)
        test_api_authentication.py     # P1: All endpoints require auth
        test_api_authorization.py      # P1: Role-based access where applicable
        test_rate_limiting.py          # P2: Rate limit middleware enforcement
        test_websocket_security.py     # P1: WebSocket auth + origin validation
        test_cors.py                   # P3: CORS middleware rejects disallowed origins
        test_input_validation.py       # P3: Injection/malformed input handling
        test_secrets_management.py     # P2: Secrets not leaked in responses/logs/errors
        test_information_disclosure.py # P3: Sensitive internals not exposed
        test_tool_api_security.py      # P2: External API credential handling
        test_sql_safety.py             # P4: Parameterized query verification
```

### Shared Fixtures (`tests/security/conftest.py`)

Tests are written against a **generic auth interface** — a `require_auth` FastAPI dependency that returns an authenticated user/context. The specific mechanism (JWT, API key, OAuth) is pluggable. Tests validate behavior, not implementation.

```python
# Key fixtures to create:
# - `client` — FastAPI TestClient with no auth (attacker perspective)
# - `authenticated_client` — TestClient with valid credentials (mechanism-agnostic)
# - `invalid_auth_client` — TestClient with malformed/expired/wrong credentials
# - `admin_client` — TestClient with admin-level credentials (for write endpoints)
# - `viewer_client` — TestClient with read-only credentials
# - `malicious_payloads` — List of common injection strings (SQLi, XSS, path traversal)
# - `oversized_payloads` — Payloads exceeding expected size limits
#
# Auth fixtures use a factory pattern so the auth mechanism is swappable:
# def make_auth_header(role="viewer") -> dict:
#     """Returns {"Authorization": "..."} or {"X-API-Key": "..."} etc."""
```

---

## Test Specifications by Priority

### Priority 1 — CRITICAL: Authentication & WebSocket Security

**Severity**: System is completely open to the internet. Any actor can trigger jobs, read configs, switch APS partitions, and stream all internal events.

#### `test_api_authentication.py` (~25 tests)

Tests verify that **every endpoint returns 401/403 without valid credentials**.

| Test | What It Falsifies |
|------|-------------------|
| `test_health_allows_unauthenticated` | Health endpoint is the ONE public endpoint |
| `test_scheduler_jobs_requires_auth` | GET /scheduler/jobs rejects without token |
| `test_scheduler_trigger_requires_auth` | POST /scheduler/trigger/{job_id} rejects without token |
| `test_graph_definition_requires_auth` | GET /graph/definition rejects without token |
| `test_circuit_breakers_requires_auth` | GET /circuit-breakers rejects without token |
| `test_aps_metrics_requires_auth` | GET /aps/metrics rejects without token |
| `test_aps_switch_requires_auth` | POST /aps/switch/{channel}/{theta} rejects without token |
| `test_aps_evaluate_requires_auth` | POST /aps/evaluate rejects without token |
| `test_aps_chain_capacity_requires_auth` | GET /aps/chain-capacity rejects without token |
| `test_aps_trace_requires_auth` | GET /aps/trace/{id} rejects without token |
| `test_agents_list_requires_auth` | GET /agents rejects without token |
| `test_agents_get_requires_auth` | GET /agents/{id} rejects without token |
| `test_agents_update_requires_auth` | PUT /agents/{id} rejects without token |
| `test_agent_invoke_requires_auth` | POST /agent/invoke rejects without token |
| `test_invalid_credentials_rejected` | Request with malformed credentials returns 401 |
| `test_expired_credentials_rejected` | Request with expired/revoked credentials returns 401 |
| `test_valid_credentials_allows_access` | Request with valid credentials returns 200 |
| `test_aps_cache_requires_auth` | GET /aps/cache rejects without credentials |
| `test_aps_metrics_channel_requires_auth` | GET /aps/metrics/{channel_id} rejects without credentials |

**Pattern** (AAA, mechanism-agnostic):
```python
def test_scheduler_trigger_requires_auth(client):
    # Arrange — unauthenticated client (no credentials of any kind)
    # Act
    response = client.post("/scheduler/trigger/order_check")
    # Assert — must reject, regardless of auth mechanism
    assert response.status_code in (401, 403)
    assert "detail" in response.json()
```

#### `test_websocket_security.py` (~10 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_ws_rejects_without_token` | Connection without auth token is refused |
| `test_ws_rejects_invalid_token` | Connection with bad token is refused |
| `test_ws_rejects_disallowed_origin` | Connection from unknown origin refused |
| `test_ws_valid_token_connects` | Valid token establishes connection |
| `test_ws_disconnects_on_token_expiry` | Long-lived connection terminated when token expires |
| `test_ws_no_sensitive_data_in_events` | Events don't contain API keys, tokens, or passwords |
| `test_ws_rate_limits_connections` | Rapid reconnection attempts are throttled |

#### `test_api_authorization.py` (~8 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_aps_switch_requires_admin` | Partition switching restricted to admin role |
| `test_agent_update_requires_admin` | Agent config modification restricted to admin |
| `test_scheduler_trigger_requires_operator` | Job triggering restricted to operator+ role |
| `test_readonly_endpoints_allow_viewer` | GET endpoints work with viewer role |
| `test_write_endpoints_reject_viewer` | POST/PUT endpoints reject viewer role |

---

### Priority 2 — HIGH: Rate Limiting, Secrets, External API Security

#### `test_rate_limiting.py` (~12 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_rate_limit_on_invoke_endpoint` | /agent/invoke limited to N req/min |
| `test_rate_limit_on_trigger_endpoint` | /scheduler/trigger limited to N req/min |
| `test_rate_limit_on_aps_evaluate` | /aps/evaluate limited to N req/min |
| `test_rate_limit_returns_429` | Exceeded limit returns 429 with Retry-After header |
| `test_rate_limit_per_ip` | Different IPs have independent limits |
| `test_rate_limit_headers_present` | X-RateLimit-Limit, X-RateLimit-Remaining headers on responses |
| `test_rate_limit_resets_after_window` | Limit resets after the window expires |
| `test_burst_protection` | 100 rapid requests don't crash the server |

**Pattern** (loop + assert):
```python
def test_rate_limit_returns_429(authenticated_client):
    # Arrange — send requests up to the limit
    for _ in range(RATE_LIMIT + 1):
        resp = authenticated_client.post("/aps/evaluate")
    # Assert — last request is rejected
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
```

#### `test_secrets_management.py` (~10 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_error_responses_no_secrets` | 500 error bodies don't contain API keys |
| `test_agent_list_no_api_keys` | /agents response doesn't include api_key fields |
| `test_health_check_no_credentials` | /health doesn't expose database URLs with passwords |
| `test_logs_redact_secrets` | Logger output sanitizes known secret patterns |
| `test_ws_events_no_secrets` | WebSocket events don't leak tokens in tool output previews |
| `test_env_vars_validated_on_startup` | Missing critical env vars raise clear error, not silent empty string |
| `test_database_url_not_in_responses` | No endpoint returns the DATABASE_URL |

**Pattern** (property-based with Hypothesis):
```python
from hypothesis import given, strategies as st

SECRET_PATTERNS = [r"sk-[a-zA-Z0-9]+", r"shpat_[a-zA-Z0-9]+", r"Bearer\s+\S+"]

def test_error_responses_no_secrets(authenticated_client):
    # Act — trigger a 500 by sending malformed input
    resp = authenticated_client.post("/agent/invoke", json={"invalid": True})
    body = resp.text
    # Assert — no secret patterns in response body
    for pattern in SECRET_PATTERNS:
        assert not re.search(pattern, body), f"Secret pattern {pattern} found in error response"
```

#### `test_tool_api_security.py` (~8 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_instagram_token_not_in_url_params` | Instagram API uses header auth, not query params |
| `test_shopify_token_in_header_only` | Shopify requests use X-Shopify-Access-Token header |
| `test_stripe_uses_sdk_auth` | Stripe uses official SDK, not raw header |
| `test_printful_bearer_in_header` | Printful uses Authorization header |
| `test_missing_api_key_raises_clear_error` | Empty API key produces actionable error, not silent failure |
| `test_http_requests_use_https` | All external tool calls use HTTPS, not HTTP |
| `test_circuit_breaker_enforced_on_tools` | Tool calls go through circuit breaker |
| `test_tool_timeout_configured` | HTTP requests have explicit timeout (not infinite) |

---

### Priority 3 — MEDIUM: CORS, Input Validation, Information Disclosure

#### `test_cors.py` (~8 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_cors_rejects_unknown_origin` | Request from evil.com gets no Access-Control-Allow-Origin |
| `test_cors_allows_configured_origin` | Request from allowed origin gets proper CORS headers |
| `test_cors_preflight_handled` | OPTIONS request returns correct preflight response |
| `test_cors_no_wildcard_in_production` | Access-Control-Allow-Origin is never `*` |
| `test_cors_credentials_header_set` | Access-Control-Allow-Credentials present when needed |

#### `test_input_validation.py` (~15 tests, includes property-based)

| Test | What It Falsifies |
|------|-------------------|
| `test_agent_update_rejects_xss_in_display_name` | HTML/script tags stripped or rejected |
| `test_agent_update_rejects_oversized_prompt` | System prompt > 50KB rejected |
| `test_trigger_job_validates_job_id` | Invalid job_id patterns rejected (no path traversal) |
| `test_aps_switch_validates_channel_id` | Only K1-K7 accepted, not arbitrary strings |
| `test_aps_switch_validates_theta_id` | Only registered theta_ids accepted |
| `test_agent_id_validates_format` | Agent IDs must match expected pattern |
| `test_invoke_rejects_empty_messages` | Empty message list rejected with 400 |
| `test_invoke_rejects_oversized_messages` | Message > 100KB rejected |
| `test_fuzz_agent_update_body` | Property-based: random JSON bodies don't crash server |
| `test_fuzz_path_parameters` | Property-based: random path strings return 4xx, not 5xx |
| `test_json_parsing_handles_malformed` | Non-JSON body returns 400/422, not 500 |
| `test_sql_meta_characters_in_inputs` | `'; DROP TABLE --` in inputs doesn't cause errors |

**Pattern** (Hypothesis property-based):
```python
@given(st.text(min_size=1, max_size=1000))
def test_fuzz_channel_id(authenticated_client, channel_id):
    resp = authenticated_client.get(f"/aps/metrics/{channel_id}")
    # Must never return 500 — always 400 or 404
    assert resp.status_code in (200, 400, 404, 422)
```

#### `test_information_disclosure.py` (~8 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_graph_definition_requires_auth` | (Covered in auth tests — cross-ref) |
| `test_error_responses_no_stack_traces` | 500 errors return generic message, not Python tracebacks |
| `test_404_no_path_disclosure` | 404 response doesn't reveal filesystem paths |
| `test_server_header_minimal` | Response headers don't reveal exact framework versions |
| `test_agent_configs_no_internal_ids` | Agent list doesn't expose database PKs or internal identifiers |
| `test_aps_trace_scoped_to_user` | Can't access traces from other sessions |

### Priority 4 — LOW: SQL Safety & Defensive Coding

#### `test_sql_safety.py` (~6 tests)

| Test | What It Falsifies |
|------|-------------------|
| `test_aps_observations_parameterized` | SQL queries use %s placeholders, not f-strings for values |
| `test_agent_config_update_safe_columns` | Dynamic SET clause only allows whitelisted column names |
| `test_sql_injection_in_channel_id` | Malicious channel_id doesn't alter query behavior |
| `test_sql_injection_in_theta_id` | Malicious theta_id doesn't alter query behavior |
| `test_observation_metadata_safely_stored` | JSONB metadata doesn't allow SQL escape |

---

## Implementation Sequence

The tests are written **in lockstep with the security fixes**, not after all fixes are complete. Per the PDF's shift-left principle, each fix phase produces its corresponding test phase:

### Phase 1: Test Infrastructure + Auth Tests (write first, RED)
1. Create `tests/security/conftest.py` with fixtures
2. Write all `test_api_authentication.py` tests — they should **all fail** (RED) against current code
3. Write `test_websocket_security.py` tests — they should **all fail**
4. **Implement auth middleware** (FastAPI dependency with Bearer token validation)
5. Run tests — they should **all pass** (GREEN)
6. Add `test_api_authorization.py` tests (RED), implement RBAC, verify (GREEN)

### Phase 2: Rate Limiting Tests
1. Write `test_rate_limiting.py` tests (RED)
2. **Implement rate limiting middleware** (slowapi or custom)
3. Run tests (GREEN)

### Phase 3: Secrets & External API Tests
1. Write `test_secrets_management.py` tests (RED for leak tests)
2. **Implement response sanitization, startup validation, log redaction**
3. Write `test_tool_api_security.py` tests (RED for Instagram URL param issue)
4. **Fix Instagram token placement, add timeouts, enforce circuit breakers**
5. Run tests (GREEN)

### Phase 4: CORS, Validation, Info Disclosure Tests
1. Write `test_cors.py` (RED)
2. **Add CORSMiddleware to FastAPI**
3. Write `test_input_validation.py` including property-based fuzz tests (RED)
4. **Add input validation to endpoints**
5. Write `test_information_disclosure.py` (RED)
6. **Sanitize error responses, remove verbose outputs**
7. Run all tests (GREEN)

### Phase 5: SQL Safety + Full Regression
1. Write `test_sql_safety.py` (mostly GREEN already — verification tests)
2. Run **entire test suite** (existing 60 + new ~100 security tests)
3. Verify no regressions in existing functionality

---

## Dependencies

**New packages** (add to `pyproject.toml` `[project.optional-dependencies]` under a `security` group):
```
hypothesis>=6.0.0        # Property-based testing / fuzzing
slowapi>=0.1.9           # Rate limiting middleware (if chosen)
python-jose[cryptography]>=3.3.0  # JWT token handling (for auth implementation)
```

**Existing packages leveraged** (no new installs):
- `pytest` + `pytest-asyncio` — test runner (already in dev deps)
- `httpx` — FastAPI TestClient backend (already installed)
- `fastapi.testclient` — sync test client

---

## Critical Files to Modify

| File | Change |
|------|--------|
| `src/serve.py` | Add auth middleware, CORS middleware, rate limiting, input validation |
| `src/events.py` | WebSocket auth check, event sanitization |
| `src/tools/instagram_tool.py` | Move token from URL params to headers |
| `src/tools/shopify_tool.py` | Add timeout, circuit breaker enforcement |
| `src/tools/stripe_tool.py` | Add timeout, circuit breaker enforcement |
| `src/tools/printful_tool.py` | Add timeout, circuit breaker enforcement |
| `tests/conftest.py` | Extend with security-aware env setup |
| `pyproject.toml` | Add security test dependencies |

---

## Verification

After all phases complete:

1. **Run full test suite**: `py -3.11 -m pytest tests/ -v --tb=short`
   - Existing 60 tests still pass (no regressions)
   - ~100 new security tests pass
2. **Coverage check**: `py -3.11 -m pytest tests/security/ --cov=src --cov-report=term-missing`
   - Target: 100% branch coverage on auth middleware, rate limiting, CORS, input validation code
   - Note per PDF: "Coverage is not strongly correlated with test suite effectiveness" — quality of assertions matters more than coverage numbers
3. **Manual smoke test**: Start server, attempt unauthenticated `curl` against every endpoint — all should return 401 except /health
4. **Property-based verification**: `py -3.11 -m pytest tests/security/test_input_validation.py -v` — Hypothesis runs 100+ random inputs per property test, verifying no 500s from malformed input

---

## Test Count Summary

| File | Unit | Integration | Property-Based | Total |
|------|------|-------------|----------------|-------|
| test_api_authentication.py | 0 | 19 | 0 | 19 |
| test_api_authorization.py | 0 | 5 | 0 | 5 |
| test_websocket_security.py | 0 | 7 | 0 | 7 |
| test_rate_limiting.py | 0 | 8 | 0 | 8 |
| test_secrets_management.py | 3 | 4 | 0 | 7 |
| test_tool_api_security.py | 4 | 4 | 0 | 8 |
| test_cors.py | 0 | 5 | 0 | 5 |
| test_input_validation.py | 3 | 5 | 4 | 12 |
| test_information_disclosure.py | 0 | 5 | 0 | 5 |
| test_sql_safety.py | 4 | 2 | 0 | 6 |
| **Total** | **14** | **64** | **4** | **~82** |

Ratio: ~17% unit / ~78% integration / ~5% property-based — appropriate for a microservices system with API security focus, aligned with the PDF's recommendation that "the Microservice has become our new Unit" (Spotify Testing Honeycomb) and the 60-30-10 guideline where integration tests dominate for API-heavy systems.
