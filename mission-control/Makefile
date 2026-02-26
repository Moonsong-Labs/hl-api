.PHONY: tidy fmt lint test run build ci

tidy:
	go mod tidy

fmt:
	gofmt -w $(shell find . -name '*.go' -not -path './vendor/*')

lint:
	go vet ./...

test:
	go test ./...

run:
	go run ./cmd/mission-control

build:
	go build -o bin/mission-control ./cmd/mission-control

ci: tidy fmt lint test build
