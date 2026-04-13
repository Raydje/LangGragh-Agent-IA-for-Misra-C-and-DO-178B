```
LangGraph-Agent-IA-for-Misra-C/
├── main.py                              # FastAPI app factory + lifespan (MongoDB checkpoint)
├── requirements.txt
├── pytest.ini
├── docker-compose.yml                   # Local stack (API, MongoDB, Redis)
├── Dockerfile                           # Multi-stage production build
│
├── app/
│   ├── config.py                        # Pydantic Settings (lru_cache), CORS, timeout config
│   ├── utils.py                         # structlog initialization, helper functions
│   ├── models_pricing.py                # Gemini model pricing table (30+ models)
│   │
│   ├── models/
│   │   └── state.py                     # ComplianceState TypedDict (with token tracking reducers)
│   │
│   ├── graph/
│   │   ├── builder.py                   # build_graph() with MongoDBSaver + inline assemble_node
│   │   ├── edges.py                     # route_after_rag, should_loop_or_finish
│   │   └── nodes/
│   │       ├── orchestrator.py          # Intent classifier (async, structured output)
│   │       ├── rag.py                   # Hybrid retrieval: Pinecone → MongoDB (async)
│   │       ├── validation.py            # MISRA compliance checker (async, structured output)
│   │       ├── critique.py              # 5-criteria hallucination reviewer (async)
│   │       └── remedier.py              # Code remediation (async, structured output)
│   │
│   ├── services/
│   │   ├── llm_service.py               # get_llm(), get_structured_llm() wrappers
│   │   ├── embedding_service.py         # Singleton, async embed + store
│   │   ├── pinecone_service.py          # Vector query/upsert via asyncio.to_thread
│   │   ├── mongodb_service.py           # Async Motor CRUD (rules) + sync pymongo (checkpoints)
│   │   ├── usage_service.py             # User-specific token and cost tracking
│   │   └── service_container.py         # Singleton container for easy service access
│   │
│   ├── api/
│   │   ├── dependencies.py              # Graph + DB dependencies, rate limiter injection
│   │   ├── rate_limit.py                # Redis-backed async rate limiter
│   │   └── v1/
│   │       ├── routes.py                # /health, /query, /seed, /replay, /history, /usage
│   │       ├── requests.py              # API Request schemas (Pydantic)
│   │       └── responses.py             # API Response schemas (Pydantic)
│   │
│   ├── auth/
│   │   ├── models.py                    # User, Token, and API Key schemas
│   │   ├── service.py                   # bcrypt, JWT, API key generation logic
│   │   ├── dependencies.py              # get_current_principal (dual JWT/API-key resolver)
│   │   └── router.py                    # /auth/register, /token, /refresh, /api-keys
│   │
│   └── data/
│       └── ingest.py                    # MISRA parser → MongoDB + Pinecone ingestion
│
├── data/
│   ├── misra_c_2023__headlines_for_cppcheck.txt       # ~250+ raw MISRA C:2023 rule definitions
│   ├── misra_c_plus_plus_2023__headlines_for_cppcheck.txt  # MISRA C++:2023 rule definitions
│   └── golden_dataset.json              # 10+ E2E test cases for non-regression suite
│
├── deploy/
│   └── k8s/                             # Kubernetes manifests (Deployment, Ingress, etc.)
│
│
└── tests/
    ├── conftest.py                      # Session-wide settings override with dummy keys
    ├── unit/                            # Unit tests for nodes, services, and API
    ├── integration/                     # Live API tests (requires mocked or real services)
    └── non_regression/                  # E2E tests against golden dataset (TNR suite)
```


---

## Auth System

### Strategy: Dual-Token (API Key + JWT)

All endpoints except `GET /health` and the `/auth/*` registration/login group require authentication via:

```
Authorization: Bearer <token>
```

The dependency `get_current_principal` (in `app/auth/dependencies.py`) detects the token type at runtime:
- Token starts with `ak_` → **API key path**: DB lookup by `key_id` + bcrypt verify of secret
- Anything else → **JWT path**: stateless HS256 signature + expiry verify

### Scopes (RBAC)

| Scope | Grants access to |
|---|---|
| `query:read` | `POST /query`, `GET /history/{thread_id}` |
| `admin:seed` | `POST /seed` |
| `admin:replay` | `POST /replay/{thread_id}/{checkpoint_id}` |
| `admin:all` | All of the above (wildcard — satisfies any scope check) |

### Auth Endpoints (`/api/v1/auth`)

| Method | Path | Auth required | Description |
|---|---|---|---|
| `POST` | `/auth/register` | No | Create account; add `admin_token` to get admin scopes |
| `POST` | `/auth/token` | No | OAuth2 password flow → access token (15 min) + refresh token (30 days) |
| `POST` | `/auth/refresh` | No | Rotate refresh token — old token revoked, new pair issued |
| `POST` | `/auth/api-keys` | Yes | Generate an API key (secret shown once) |
| `GET` | `/auth/api-keys` | Yes | List caller's active API keys |
| `DELETE` | `/auth/api-keys/{key_id}` | Yes | Soft-revoke an API key |

### MongoDB Collections

**`users`**
```json
{
  "_id": "uuid",
  "email": "unique",
  "hashed_password": "bcrypt",
  "scopes": ["query:read"],
  "is_active": true,
  "refresh_tokens": [{"token": "...", "issued_at": "ISO8601"}],
  "created_at": "ISO8601"
}
```
Index: `email` (unique)

**`api_keys`**
```json
{
  "key_id": "8 hex chars",
  "name": "human-readable label",
  "key_hash": "bcrypt hash of secret portion",
  "user_id": "ref → users._id",
  "scopes": ["query:read"],
  "expires_at": "ISO8601 | null",
  "is_active": true,
  "last_used_at": "ISO8601 | null",
  "created_at": "ISO8601"
}
```
Indexes: `key_id`, `user_id`

### API Key Format

```
ak_<key_id>_<secret>
   └──8 hex──┘ └──43 url-safe base64 chars──┘
```

`key_id` is stored plaintext — used for O(1) DB lookup before the expensive bcrypt verification.
`secret` is bcrypt-hashed — never stored in plaintext, shown to the caller only once.

### Privilege Escalation Prevention

When creating an API key, requested scopes are intersected with the caller's own scopes.
A `query:read` user cannot create a key with `admin:seed` scope.

### Admin Registration

Set `ADMIN_REGISTRATION_TOKEN` in `.env` to a strong random value.
Include `{"admin_token": "<value>"}` in the `POST /auth/register` body to receive scopes:
`["query:read", "admin:seed", "admin:replay", "admin:all"]`
