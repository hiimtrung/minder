# Requirements: Phase 4 Observability Stack (P4-T05)

**Date**: 2026-04-08
**Status**: Draft
**Author**: FE

---

## Goal

Provide a comprehensive observability foundation for Minder, including OpenTelemetry tracing, Prometheus metrics, structured JSON logging, and dedicated audit trails for auth and workflow events, ensuring production readiness.

## Users

| Role   | Need                               |
| ------ | ---------------------------------- |
| Admin / Operator | Needs visibility into system performance, error rates, and security events. |
| Developer | Needs traces to debug latency and graph execution paths. |

---

## User Stories

### Story 1: System Metrics
**As an** Operator
**I want to** scrape Prometheus metrics from `/metrics`
**So that** I can monitor API latency, success rates, token usage, and graph execution counts.

**Acceptance Criteria**:
```gherkin
Given the server is running
When a client requests GET /metrics
Then the server returns Prometheus formatted metrics
And the metrics include HTTP request duration, graph token usage, and error counters
```

### Story 2: Request Tracing
**As a** Developer
**I want to** view OpenTelemetry distributed traces for MCP tool calls and Graph runs
**So that** I can identify bottlenecks and debug complex reasoning loops.

**Acceptance Criteria**:
```gherkin
Given OpenTelemetry configuration is enabled
When an MCP tool call is processed or a graph workflow runs
Then spans are emitted and exported via OTLP
And context is propagated across internal service boundaries
```

### Story 3: Structured Logging
**As an** Operator
**I want to** configure the application to output structured JSON logs
**So that** logs can be easily aggregated and queried in an ELK or Datadog stack.

**Acceptance Criteria**:
```gherkin
Given log configuration sets format to JSON
When the application writes logs
Then the output is standard JSON strings
And context such as correlation IDs and user/client principals are included
```

### Story 4: Audit Trails
**As a** Security Admin
**I want to** view specialized audit trails for critical auth and workflow events
**So that** I can comply with security policies and review historical usage.

**Acceptance Criteria**:
```gherkin
Given the audit logging system is active
When a key is revoked, a token is exchanged, or a workflow state changes
Then a distinct, durable audit log entry is written to the configured store
And it includes the principal ID, action, timestamp, and relevant metadata
```

---

## Scope

### In Scope (v1)
- Prometheus endpoint (`/metrics`) using Prometheus client library for Python.
- OpenTelemetry instrumentation for Starlette/FastAPI, HTTP requests (httpx), and Graph Node execution.
- Structured Python logging (using `structlog` or `json-logging`).
- Audit logging interface abstracting over MongoDB.

### Out of Scope
- Actually setting up Prometheus, Grafana, or Jaeger servers (this is for `P4-T06` Production Docker Compose).
- Dashboard UI for viewing these logs (`P4-T10`).

---

## Edge Cases and Error Handling

| Scenario    | Expected Behavior         |
| ----------- | ------------------------- |
| OTLP endpoint unreachable | Application must not crash; traces drop silently or log warning. |
| Metrics scrape fails | Should not affect application performance. |
| Audit log fails to persist | Should either fail the request (strict audit) or log an error (loose audit); need to decide standard behavior. |

---

## Integration Points

| System / Module | Dependency Type       | Notes    |
| --------------- | --------------------- | -------- |
| Starlette / FastAPI | Upstream | Needs middleware for both metrics and tracing. |
| LangGraph Pipeline | Upstream | Needs manual instrumentation or callback hook for tracing node transitions. |
| MongoDB `AuditLog` | Downstream | Writing the structured audit entries (already partially introduced in Phase 4.0). |

---

## Non-Functional Requirements

- **Performance**: Metrics and tracing overhead should add < 10ms to P95 latency.
- **Reliability**: Observability failures MUST NOT crash core application flows.

---

## Open Questions

- [ ] Will we use `structlog` or just standard `logging` with JSON formatting?
- [ ] For OTLP, should we default to exporting via HTTP or gRPC?
- [ ] Do we need strict (blocking) or loose (non-blocking) audit logging?

---

## Decisions Log

| Date       | Decision   | Rationale |
| ---------- | ---------- | --------- |
| 2026-04-08 | Use OpenTelemetry | Standard for distributed systems. |
