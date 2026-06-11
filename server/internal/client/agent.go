// internal/client/agent.go —— 对 Python agent(gRPC 下游服务)的访问封装。
//
// 地位类比:dao 封装"对 MySQL 的访问",client 封装"对其他服务的访问"。
// gRPC 的一切细节(连接、stub、pb 类型、Recv 循环)都锁在这个包里,
// 上层(gateway)只看到本包定义的 Chunk 结构和回调接口,完全不知道 gRPC 存在。
//
// 连接复用:gRPC 连接是多路复用且并发安全的,启动时建一次、全程共用;
// 之前"每请求 NewClient + Close"是反模式,这次一并修正。
package client

import (
	"context"
	"io"
	"log"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	pb "github.com/sicheng-svg/snap-solver/server/gen"
)

var solver pb.SolverAgentClient

// Init 建立到 agent 的 gRPC 连接(惰性:首次调用时才真正连),程序启动时调用一次。
func Init() {
	addr := os.Getenv("AGENT_ADDR")
	if addr == "" {
		addr = "localhost:50051"
	}
	conn, err := grpc.NewClient(addr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("初始化 agent 连接失败: %v", err)
	}
	solver = pb.NewSolverAgentClient(conn)
	log.Printf("agent gRPC 客户端就绪(%s)", addr)
}

// Chunk 是本包对外的流式数据单元(不暴露 pb 类型,隔离 gRPC 细节)。
type Chunk struct {
	Type    string // thinking / token / done / error
	Stage   string
	Content string
}

// SolveReq 解题请求参数。
type SolveReq struct {
	Image     []byte
	Text      string
	SessionID string // 作 agent 侧 thread_id
	UserID    string
}

// SolveStream 发起流式解题,每收到一个 chunk 调一次 onChunk。
// 流正常结束返回 nil;中途出错返回 error(已收到的 chunk 均已回调)。
func SolveStream(ctx context.Context, req SolveReq, onChunk func(Chunk)) error {
	stream, err := solver.Solve(ctx, &pb.SolveRequest{
		Image:     req.Image,
		UserText:  req.Text,
		SessionId: req.SessionID,
		UserId:    req.UserID,
	})
	if err != nil {
		return err
	}
	for {
		c, err := stream.Recv()
		if err == io.EOF {
			return nil // 正常结束
		}
		if err != nil {
			return err
		}
		onChunk(Chunk{Type: c.GetType(), Stage: c.GetStage(), Content: c.GetContent()})
	}
}
