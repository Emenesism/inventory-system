FROM golang:1.25.7-bookworm AS builder
WORKDIR /src

COPY go.mod go.sum ./
RUN set -eux; \
    export GOPROXY="https://proxy.golang.org,direct"; \
    n=0; \
    until [ "$n" -ge 5 ]; do \
    go mod download && break; \
    n=$((n+1)); \
    echo "go mod download failed, retry $n/5" >&2; \
    sleep $((n * 2)); \
    done; \
    [ "$n" -lt 5 ]

COPY . .

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 GOFLAGS=-mod=mod \
    go build -trimpath -ldflags="-s -w" -o /out/reza-backend ./cmd/server

FROM scratch
WORKDIR /app

COPY --from=builder /out/reza-backend /app/reza-backend

ENV PORT=1234
EXPOSE 1234

USER 65532:65532
ENTRYPOINT ["/app/reza-backend"]
