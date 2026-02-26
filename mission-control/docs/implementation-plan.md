# Mission Control - Implementation Plan

## 1) Bootstrap and Lifecycle

1. Parse config from environment with defaults.
2. Initialize structured logger.
3. Open SQLite connection with pragmas.
4. Run migrations before serving traffic.
5. Construct services + handlers via dependency injection.
6. Start HTTP server and support graceful shutdown.

## 2) Domain Modeling

1. Add explicit status enums for mission/task state machine.
2. Add constructor/validator helpers for aggregate integrity.
3. Centralize domain errors for transport mapping.

## 3) Storage Layer

1. Create repository interfaces in service package.
2. Implement SQLite repos in `internal/store/sqlite`.
3. Use transactions for multi-step writes.
4. Add pagination helpers for list queries.

## 4) HTTP API

1. Version routes under `/api/v1`.
2. Add middleware chain (request ID, logging, recovery, timeout).
3. Implement mission/task/event handlers.
4. Map domain errors to typed JSON error responses.

## 5) Testing Strategy

1. Unit tests for domain invariants and services.
2. Handler tests with `httptest`.
3. Store tests against temporary SQLite files.
4. Add race detector and coverage threshold in CI.

## 6) Operational Readiness

1. Add `/metrics` endpoint.
2. Add readiness checks for DB connectivity.
3. Add version/build metadata endpoint.
4. Document local/dev/prod runbooks.
