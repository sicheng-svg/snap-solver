// cmd/healthcheck/main.go —— 最小 gRPC 客户端,验证 Go↔Python 连通性。
//
// 用法:
//
//	先在 agent 目录 uv run python server.py 起 Python gRPC server(监听 50051)
//	再在 server 目录 go run ./cmd/healthcheck
//
// 它连 Python 的 50051,调 HealthCheck,打印返回的 status。
// 成功 = Go 和 Python 的 gRPC 通道打通了。
package main

import (
	"context"
	"log"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	// 生成的 gRPC 代码(包名 solverpb,见 proto 的 go_package)
	pb "github.com/sicheng-svg/snap-solver/server/gen"
)

func main() {
	// 1. 建立连接(明文,本地;NewClient 是新版推荐 API,替代 Dial)
	conn, err := grpc.NewClient(
		"localhost:50051",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("连接失败: %v", err)
	}
	defer conn.Close()

	// 2. 创建 client stub(用生成代码里的构造函数)
	client := pb.NewSolverAgentClient(conn)

	// 3. 调 HealthCheck(带超时的 context)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	reply, err := client.HealthCheck(ctx, &pb.HealthRequest{})
	if err != nil {
		log.Fatalf("HealthCheck 调用失败: %v", err)
	}

	log.Printf("✓ 连通成功!Python agent 返回 status = %q", reply.GetStatus())
}
