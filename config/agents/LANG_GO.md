# Go conventions

- `gofmt`/`goimports` clean; `go vet` and `golangci-lint` pass before done.
- Errors: wrap with `fmt.Errorf("...: %w", err)`; never discard with `_` silently.
- Context-first: `func(ctx context.Context, ...)` for anything I/O-bound.
- Table-driven tests; `go test ./...` before claiming done.
- Keep modules tidy: `go mod tidy`; pin tool deps via `go.mod`/`tools.go`.
- Prefer the standard library; justify each third-party dependency.
