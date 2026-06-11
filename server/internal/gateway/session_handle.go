// internal/gateway/session_handler.go —— 会话 CRUD 的 HTTP handler。
package gateway

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"github.com/sicheng-svg/snap-solver/server/internal/business"
)

// HandleCreateSession POST /api/sessions
func HandleCreateSession(c *gin.Context) {
	uid := c.GetUint64("user_id") // 鉴权中间件注入的
	s, err := business.CreateSession(uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "创建会话失败"})
		return
	}
	c.JSON(http.StatusOK, s)
}

// HandleListSessions GET /api/sessions
func HandleListSessions(c *gin.Context) {
	uid := c.GetUint64("user_id")
	list, err := business.ListSessions(uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "获取会话列表失败"})
		return
	}
	c.JSON(http.StatusOK, list)
}

// HandleDeleteSession DELETE /api/sessions/:id
func HandleDeleteSession(c *gin.Context) {
	uid := c.GetUint64("user_id")
	sid, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "会话 id 非法"})
		return
	}
	if err := business.DeleteSession(sid, uid); err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

// HandleListMessages GET /api/sessions/:id/messages
func HandleListMessages(c *gin.Context) {
	uid := c.GetUint64("user_id")
	sid, err := strconv.ParseUint(c.Param("id"), 10, 64)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "会话 id 非法"})
		return
	}
	list, err := business.ListMessages(sid, uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, list)
}
