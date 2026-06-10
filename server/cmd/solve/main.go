package main

// cmd/solve/main.go —— gRPC 流式客户端,调 Python agent 的 Solve。
//
// 用法:
//   先 uv run python server.py 起 Python server(50051)
//   再 go run ./cmd/solve "求 lim(x->0) sinx/x 的值"
//
// 与 HealthCheck 的区别:Solve 返回的是【流】。
//   - HealthCheck: reply, err := client.HealthCheck(...)   一次拿单个结果
//   - Solve:       stream, err := client.Solve(...)        拿到流,循环 Recv() 收
//     直到 Recv() 返回 io.EOF(流正常结束)。
//
// 收到的每个 SolveChunk 按 type 处理:thinking(思考)/ token(回答逐字)/ done / error。

import (
	"context"
	"fmt"
	"io"
	"log"
	"os"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/sicheng-svg/snap-solver/server/gen"
)

func main() {
	// 命令行第一个参数当题目文本,没传用默认
	userText := "求 lim(x->0) sinx/x 的值"
	if len(os.Args) > 1 {
		userText = os.Args[1]
	}

	// 1. 建连接(同 HealthCheck)
	conn, err := grpc.NewClient(
		"localhost:50051",
		grpc.WithTransportCredentials(insecure.NewCredentials()),
	)
	if err != nil {
		log.Fatalf("连接失败: %v", err)
	}
	defer conn.Close()

	// 2. 创建 client stub(同 HealthCheck,同一个 stub 类型)
	client := pb.NewSolverAgentClient(conn)

	// 3. 发起流式调用。注意:解题可能耗时几十秒,超时设长一点(或不设超时用 Background)
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()

	stream, err := client.Solve(ctx, &pb.SolveRequest{
		UserText:  userText,
		SessionId: "go-test-session",
		UserId:    "go-test-user",
	})
	if err != nil {
		log.Fatalf("Solve 调用失败: %v", err)
	}

	fmt.Printf("[输入] %s\n", userText)
	fmt.Println("============================================================")

	// 4. 循环接收流,直到 io.EOF
	answerStarted := false
	for {
		chunk, err := stream.Recv()
		if err == io.EOF {
			// 流正常结束
			break
		}
		if err != nil {
			log.Fatalf("接收流出错: %v", err)
		}

		switch chunk.GetType() {
		case "thinking":
			fmt.Printf("[思考·%s] %s\n", chunk.GetStage(), chunk.GetContent())
		case "token":
			if !answerStarted {
				fmt.Println("\n============================================================")
				fmt.Println("【最终回答】")
				answerStarted = true
			}
			// 逐字打印(不换行),模拟打字机
			fmt.Print(chunk.GetContent())
		case "done":
			fmt.Println("\n============================================================")
			fmt.Println("[完成]")
		case "error":
			fmt.Printf("\n[错误] %s\n", chunk.GetContent())
		}
	}
}
