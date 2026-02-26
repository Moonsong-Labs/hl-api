# Mission Control Design Doc (Initial)

## Purpose

Mission Control provides a lightweight operations control plane for managing mission entities, task execution state, and event timelines. This scaffold implements the foundational architecture and lifecycle boundaries.

## Functional Requirements (MVP)

1. API service exposes health and readiness endpoints.
2. Persist missions, tasks, and events in SQLite.
3. Support idempotent mission creation/update flows.
4. Track mission state transitions.
5. Provide audit-friendly timestamps and metadata fields.

## Non-Functional Requirements

- Idiomatic Go architecture (clear package boundaries, small interfaces).
- Deterministic startup (config -> logger -> storage -> migration -> server).
- Testability through dependency injection and service/repository abstractions.
- CI baseline for formatting, vetting, tests, and build.

## Architecture

- **Transport layer** (`internal/transport/httpapi`): HTTP routing and handlers.
- **Service layer** (`internal/service`): domain logic orchestration.
- **Store layer** (`internal/store/sqlite`): SQLite-backed repositories and migrations.
- **Domain layer** (`internal/domain`): core entity types and state definitions.

## Data Model (Initial)

- `missions`: top-level mission metadata and lifecycle status.
- `tasks`: mission-scoped execution units.
- `events`: append-only timeline records.

## Risk Areas

- SQLite write contention under high concurrency.
- Schema evolution/migration discipline.
- State machine correctness for mission/task transitions.

## Future Evolutions

- Add OpenTelemetry tracing and metrics.
- Introduce background worker queue.
- Add authn/authz boundaries.
- Promote storage abstraction to support Postgres.
