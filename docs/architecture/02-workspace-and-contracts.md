# 02. Workspace & Contract Registry — Eliminating LLM Hallucinations

In real-world engineering environments, software systems consist of multiple linked Git repositories. When an AI Agent is constrained to a single local repository, it lacks context for other services and begins to **hallucinate** interface shapes.

---

## 1. Cross-Repo Contract Registry

The Contract Registry is a structured repository capturing all interface contracts across a Workspace:

1. **HTTP Routes**: `POST /api/v1/auth/login`, `GET /api/v1/users/{id}` (with headers, query params, auth policies).
2. **DTO Schemas**: Pydantic models, TypeScript interfaces, Go structs, Java classes.
3. **Protobuf / gRPC**: Service definitions, RPC request/response messages.
4. **Event Messages**: Kafka topic payloads, RabbitMQ event models.
5. **Database Models**: SQLAlchemy / Prisma / TypeORM entity definitions.

---

## 2. Operation Flow: `minder_search_contracts`

```
┌──────────────────────────────┐
│  Developer on `frontend-web` │
│  "Need to call login API"    │
└──────────────┬───────────────┘
               │
               ▼ Call MCP Tool: minder_search_contracts(query="login user payload")
┌─────────────────────────────────────────────────────────────────────────────┐
│ Minder Server queries the Workspace Contract Registry:                      │
│                                                                             │
│ -> Found Contract `ctr_auth_login` at `auth-service/dto/login.go`:          │
│    type LoginRequest struct {                                               │
│        Email    string `json:"email" binding:"required,email"`             │
│        Password string `json:"password" binding:"required,min=8"`           │
│    }                                                                        │
│    type LoginResponse struct {                                              │
│        AccessToken  string `json:"access_token"`                            │
│        RefreshToken string `json:"refresh_token"`                           │
│        ExpiresIn    int64  `json:"expires_in"`                              │
│    }                                                                        │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼ Returns exact definition (100% accurate)
┌─────────────────────────────────────────────────────────────────────────────┐
│  AI Agent generates TypeScript code precisely matching the Backend:         │
│  interface LoginPayload { email: string; password: string; }                │
│  => ZERO HALLUCINATION GAP                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```
