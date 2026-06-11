// main.go —— 纯组装:初始化各层资源 + 挂路由。不含任何业务/协议逻辑。
package main

import (
	"log"
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/sicheng-svg/snap-solver/server/internal/client"
	"github.com/sicheng-svg/snap-solver/server/internal/dao"
	"github.com/sicheng-svg/snap-solver/server/internal/gateway"
)

func main() {
	dao.Init()    // MySQL
	client.Init() // agent gRPC 连接(复用一条)

	r := gin.Default()

	r.Use(func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Authorization")
		c.Header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	})

	r.POST("/api/register", gateway.HandleRegister)
	r.POST("/api/login", gateway.HandleLogin)

	authed := r.Group("/api", gateway.AuthMiddleware())
	authed.POST("/sessions", gateway.HandleCreateSession)
	authed.GET("/sessions", gateway.HandleListSessions)
	authed.DELETE("/sessions/:id", gateway.HandleDeleteSession)
	authed.GET("/sessions/:id/messages", gateway.HandleListMessages)
	authed.GET("/solve", gateway.HandleSolveGET)
	authed.POST("/solve", gateway.HandleSolvePOST)

	log.Println("网关启动,监听 :8080")
	if err := r.Run(":8080"); err != nil {
		log.Fatalf("网关启动失败: %v", err)
	}
}
