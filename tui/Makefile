.PHONY: build run clean test

build:
	go build -o waze-tui ./cmd/waze-tui/

run: build
	./waze-tui

clean:
	rm -f waze-tui

test:
	go test ./... -v
