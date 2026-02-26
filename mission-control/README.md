# Mission Control (Scaffold)

Mission Control is a Go-based control plane scaffold with SQLite persistence, a layered architecture, and CI ready for extension.

## Tech Stack

- Go `1.26`
- SQLite (`github.com/mattn/go-sqlite3`)
- HTTP server with Chi
- Structured logging with Zap
- SQL access via `sqlx`
- Migrations via Goose

## Project Layout

- `cmd/mission-control`: executable entrypoint
- `internal/app`: application bootstrap and lifecycle
- `internal/config`: environment-driven configuration
- `internal/domain`: domain model stubs
- `internal/service`: business service stubs
- `internal/store/sqlite`: SQLite repository + migration runner
- `internal/transport/httpapi`: HTTP API wiring and handlers
- `docs`: design, planning, and implementation docs

## Quick Start

```bash
go mod tidy
go run ./cmd/mission-control
```

By default, server listens on `:8080` and uses `./mission_control.db`.

## Current Endpoints

- `GET /healthz`
- `GET /readyz`

## Next Steps

Follow `docs/project-plan.md` and `docs/implementation-plan.md` to move from scaffold to production-ready service.
