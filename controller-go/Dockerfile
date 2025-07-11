# Dockerfile for SceneScape Controller Go

# Build stage
FROM golang:1.19-alpine AS builder

# Install build dependencies for CGO
RUN apk add --no-cache gcc g++ musl-dev

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo -o controller ./cmd/controller

# Runtime stage
FROM alpine:latest

# Install runtime dependencies
RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Copy binary and configuration
COPY --from=builder /app/controller .
COPY --from=builder /app/config/ ./config/

# Create non-root user
RUN adduser -D -s /bin/sh scenescape

USER scenescape

ENTRYPOINT ["./controller"]
