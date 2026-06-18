# server/Dockerfile —— Go 网关(多阶段:构建 + 运行)
FROM golang:1.26.2-alpine AS builder

# 国内 Go 模块代理(大幅加速 go mod download)
ENV GOPROXY=https://goproxy.cn,direct

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/gateway .

# 运行阶段:极小镜像
FROM alpine:latest
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /app/gateway .
EXPOSE 8080
CMD ["./gateway"]