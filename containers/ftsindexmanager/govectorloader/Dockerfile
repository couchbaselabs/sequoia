FROM golang:alpine AS builder

RUN apk add --no-cache wget

WORKDIR /app

COPY . .

WORKDIR /app/cmd

RUN go mod download

RUN go build -o main .

WORKDIR /app

ENTRYPOINT ["/app/cmd/main"]