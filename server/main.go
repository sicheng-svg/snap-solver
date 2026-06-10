// main.go —— Gin HTTP 网关(一期集中版,先打通闭环)。
//
// 双重身份在一个 handler 里整合:
//   - 对前端是 HTTP server(Gin):GET /api/solve?text=... ,用 SSE 流式推回结果
//   - 对 Python 是 gRPC client:调 agent 的 Solve,循环 Recv 收 SolveChunk
//   - 中间转换:每个 SolveChunk -> 一个 SSE 事件,实时 flush 给浏览器
//
// 用法:
//
//	先 uv run python server.py 起 agent(50051)
//	go run .                          起网关(默认 :8080)
//	浏览器/curl 访问 http://localhost:8080/api/solve?text=求lim(x->0)sinx/x
//
// 跑通后再拆分 internal/gateway、internal/client 分层。
package main

import (
	"encoding/json"
	"io"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/sicheng-svg/snap-solver/server/gen"
)

const agentAddr = "localhost:50051"

// sseEvent 推送给前端的事件结构(SolveChunk 转成 JSON 作为 SSE data)
type sseEvent struct {
	Type    string `json:"type"`    // thinking / token / done / error
	Stage   string `json:"stage"`   // 思考阶段
	Content string `json:"content"` // 内容
}

func main() {
	r := gin.Default()

	// CORS:开发期允许前端跨域(前端 dev server 端口和网关不同)
	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Headers", "Content-Type")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	r.GET("/api/solve", handleSolve)

	log.Println("网关启动,监听 :8080")
	if err := r.Run(":8080"); err != nil {
		log.Fatalf("网关启动失败: %v", err)
	}
}

func handleSolve(c *gin.Context) {
	userText := c.Query("text")
	if userText == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少 text 参数"})
		return
	}

	// 1. 设置 SSE 响应头(告诉浏览器这是事件流)
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")

	// 2. 连接 Python agent(gRPC client 身份)
	conn, err := grpc.NewClient(agentAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		writeSSE(c, sseEvent{Type: "error", Content: "连接 agent 失败: " + err.Error()})
		return
	}
	defer conn.Close()
	client := pb.NewSolverAgentClient(conn)

	// 用请求的 context:浏览器断开时,ctx 会被取消,gRPC 调用随之中止
	ctx := c.Request.Context()

	stream, err := client.Solve(ctx, &pb.SolveRequest{
		UserText:  userText,
		SessionId: "web-session", // 一期固定;以后按用户/会话区分
		UserId:    "web-user",
	})
	if err != nil {
		writeSSE(c, sseEvent{Type: "error", Content: "调用 Solve 失败: " + err.Error()})
		return
	}

	// 3. 循环接收 gRPC 流,每个 chunk 转成 SSE 事件推给前端
	for {
		chunk, err := stream.Recv()
		if err == io.EOF {
			break // 流正常结束
		}
		if err != nil {
			writeSSE(c, sseEvent{Type: "error", Content: "接收流出错: " + err.Error()})
			return
		}

		writeSSE(c, sseEvent{
			Type:    chunk.GetType(),
			Stage:   chunk.GetStage(),
			Content: chunk.GetContent(),
		})
	}
}

// writeSSE 把一个事件按 SSE 格式写入响应,并立即 flush(关键:不 flush 就不是实时流)
func writeSSE(c *gin.Context, event sseEvent) {
	data, _ := json.Marshal(event)
	// SSE 格式:data: <内容>\n\n
	c.Writer.Write([]byte("data: "))
	c.Writer.Write(data)
	c.Writer.Write([]byte("\n\n"))
	c.Writer.Flush() // 立即推送,不缓冲
}
