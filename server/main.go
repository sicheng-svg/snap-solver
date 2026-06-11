// main.go —— Gin HTTP 网关(支持 POST 传图 + GET 兼容)。
//
//   - GET  /api/solve?text=...        文本解题(EventSource 兼容,保留)
//   - POST /api/solve {text, image}   文本/图片解题(前端 fetch+ReadableStream 用)
//     image 为 base64 字符串(不带 data-uri 前缀),解码成 bytes 经 gRPC 传给 agent。
//
// 两个入口共用同一套 gRPC 调用 + SSE 推送逻辑(solveAndStream)。
package main

import (
	"encoding/base64"
	"encoding/json"
	"io"
	"log"
	"net/http"

	"github.com/gin-gonic/gin"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/sicheng-svg/snap-solver/server/gen"
	"github.com/sicheng-svg/snap-solver/server/internal/dao"
	"github.com/sicheng-svg/snap-solver/server/internal/gateway"
)

const agentAddr = "localhost:50051"

type sseEvent struct {
	Type    string `json:"type"`
	Stage   string `json:"stage"`
	Content string `json:"content"`
}

// POST 请求体
type solveBody struct {
	Text  string `json:"text"`
	Image string `json:"image"` // base64(可空)
}

func main() {
	dao.Init()
	r := gin.Default()

	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	r.POST("/api/register", gateway.HandleRegister)
	r.POST("/api/login", gateway.HandleLogin)

	authed := r.Group("/api", gateway.AuthMiddleware())
	authed.GET("/solve", handleSolveGET)
	authed.POST("/solve", handleSolvePOST)

	log.Println("网关启动,监听 :8080")
	if err := r.Run(":8080"); err != nil {
		log.Fatalf("网关启动失败: %v", err)
	}
}

func handleSolveGET(c *gin.Context) {
	text := c.Query("text")
	if text == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少 text 参数"})
		return
	}
	solveAndStream(c, text, nil)
}

func handleSolvePOST(c *gin.Context) {
	var body solveBody
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体格式错误"})
		return
	}
	if body.Text == "" && body.Image == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "text 和 image 至少要有一个"})
		return
	}

	// base64 -> bytes(前端传纯 base64,不带 data:image/...;base64, 前缀)
	var imageBytes []byte
	if body.Image != "" {
		decoded, err := base64.StdEncoding.DecodeString(body.Image)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "image base64 解码失败"})
			return
		}
		imageBytes = decoded
	}

	solveAndStream(c, body.Text, imageBytes)
}

// 共用:调 agent gRPC Solve,把流转 SSE 推给客户端
func solveAndStream(c *gin.Context, text string, image []byte) {
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")

	conn, err := grpc.NewClient(agentAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		writeSSE(c, sseEvent{Type: "error", Content: "连接 agent 失败: " + err.Error()})
		return
	}
	defer conn.Close()
	client := pb.NewSolverAgentClient(conn)

	ctx := c.Request.Context()

	stream, err := client.Solve(ctx, &pb.SolveRequest{
		Image:     image,
		UserText:  text,
		SessionId: "web-session",
		UserId:    "web-user",
	})
	if err != nil {
		writeSSE(c, sseEvent{Type: "error", Content: "调用 Solve 失败: " + err.Error()})
		return
	}

	for {
		chunk, err := stream.Recv()
		if err == io.EOF {
			break
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

func writeSSE(c *gin.Context, event sseEvent) {
	data, _ := json.Marshal(event)
	c.Writer.Write([]byte("data: "))
	c.Writer.Write(data)
	c.Writer.Write([]byte("\n\n"))
	c.Writer.Flush()
}
