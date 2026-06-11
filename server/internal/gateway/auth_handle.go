// internal/gateway/auth_handler.go —— 注册/登录的 HTTP handler + JWT 鉴权中间件。
//
// gateway 层职责:HTTP 进出(参数绑定/校验、状态码、响应格式),调 business 做事。
package gateway

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/sicheng-svg/snap-solver/server/internal/business"
)

type authReq struct {
	Username string `json:"username" binding:"required,min=2,max=64"`
	Password string `json:"password" binding:"required,min=6,max=72"` // bcrypt 上限 72 字节
}

// HandleRegister POST /api/register
func HandleRegister(c *gin.Context) {
	var req authReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "参数错误:用户名2-64位,密码6-72位"})
		return
	}
	token, err := business.Register(req.Username, req.Password)
	if err == business.ErrUsernameTaken {
		c.JSON(http.StatusConflict, gin.H{"error": err.Error()})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "注册失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token})
}

// HandleLogin POST /api/login
func HandleLogin(c *gin.Context) {
	var req authReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "参数错误"})
		return
	}
	token, err := business.Login(req.Username, req.Password)
	if err == business.ErrAuthFailed {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "登录失败"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token})
}

// AuthMiddleware JWT 鉴权中间件:校验 Authorization: Bearer <token>,
// 解析出 user_id 注入 gin.Context,后续 handler 用 c.GetUint64("user_id") 取。
// 这就是一期"预留鉴权中间件"位置的实装。
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		auth := c.GetHeader("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "未登录"})
			return
		}
		uid, err := business.ParseToken(strings.TrimPrefix(auth, "Bearer "))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "登录已失效,请重新登录"})
			return
		}
		c.Set("user_id", uid) // 注入,后续 handler 直接取
		c.Next()
	}
}
