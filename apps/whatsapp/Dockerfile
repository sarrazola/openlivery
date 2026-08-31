FROM golang:1.27-bookworm AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go vet ./... && go test ./... && CGO_ENABLED=0 go build -trimpath -o bridge .

FROM debian:bookworm-slim AS runner

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 bridge \
    && useradd --uid 10001 --gid bridge --create-home bridge

ENV WHATSAPP_BRIDGE_HOST=0.0.0.0 \
    WHATSAPP_BRIDGE_PORT=3101

WORKDIR /app
COPY --from=builder --chown=bridge:bridge /app/bridge ./bridge

USER bridge

EXPOSE 3101

CMD ["/app/bridge"]
