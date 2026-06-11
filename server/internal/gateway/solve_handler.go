// internal/gateway/solve_handler.go —— 解题接口:HTTP/SSE 进出 + 流程编排。
//
// 职责:解析请求 → 调 business(归属校验/落库)→ 调 client 拿流
//
//	→ 转 SSE 实时推出 + 攒缓冲 → 流结束调 business 落库回答。
//
// 注意:本文件不出现任何 gRPC/pb —— 那些被 client 包封装掉了。
package gateway

import (
	"encoding/base64"
	"encoding/json"
	"log"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"github.com/sicheng-svg/snap-solver/server/internal/business"
	"github.com/sicheng-svg/snap-solver/server/internal/client"
)

type sseEvent struct {
	Type    string `json:"type"`
	Stage   string `json:"stage"`
	Content string `json:"content"`
}

type solveBody struct {
	Text      string `json:"text"`
	Image     string `json:"image"`
	SessionID uint64 `json:"session_id"`
}

// HandleSolveGET GET /api/solve?text=...&session_id=...
func HandleSolveGET(c *gin.Context) {
	text := c.Query("text")
	sid, err := strconv.ParseUint(c.Query("session_id"), 10, 64)
	if text == "" || err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "需要 text 和 session_id"})
		return
	}
	solveAndStream(c, text, nil, sid)
}

// HandleSolvePOST POST /api/solve {text, image, session_id}
func HandleSolvePOST(c *gin.Context) {
	var body solveBody
	if err := c.ShouldBindJSON(&body); err != nil || body.SessionID == 0 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体需要 text/image 和 session_id"})
		return
	}
	if body.Text == "" && body.Image == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "text 和 image 至少要有一个"})
		return
	}
	var imageBytes []byte
	if body.Image != "" {
		decoded, err := base64.StdEncoding.DecodeString(body.Image)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": "image base64 解码失败"})
			return
		}
		imageBytes = decoded
	}
	solveAndStream(c, body.Text, imageBytes, body.SessionID)
}

func solveAndStream(c *gin.Context, text string, image []byte, sessionID uint64) {
	uid := c.GetUint64("user_id")

	// 1. 业务校验与用户消息落库
	sess, err := business.CheckOwnership(sessionID, uid)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	userContent := text
	if userContent == "" {
		userContent = "(图片题目)"
	}
	if err := business.SaveUserMessage(sess, userContent, nil); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "消息保存失败"})
		return
	}

	// 2. SSE 协议头
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")

	// 3. 调下游服务(client 封装),边转发边攒
	var answerBuf []byte
	var thinkings []sseEvent

	err = client.SolveStream(c.Request.Context(), client.SolveReq{
		Image:     image,
		Text:      text,
		SessionID: strconv.FormatUint(sessionID, 10),
		UserID:    strconv.FormatUint(uid, 10),
	}, func(ch client.Chunk) {
		ev := sseEvent{Type: ch.Type, Stage: ch.Stage, Content: ch.Content}
		writeSSE(c, ev)
		switch ev.Type {
		case "token":
			answerBuf = append(answerBuf, ev.Content...)
		case "thinking":
			thinkings = append(thinkings, ev)
		}
	})
	if err != nil {
		writeSSE(c, sseEvent{Type: "error", Content: "解题服务异常"})
	}

	// 4. 回答落库(即使中途出错,已攒到的内容也保存)
	if len(answerBuf) > 0 {
		tj, _ := json.Marshal(thinkings)
		if err := business.SaveAssistantMessage(sessionID, string(answerBuf), string(tj)); err != nil {
			log.Printf("AI 回答落库失败(session=%d): %v", sessionID, err)
		}
	}
}

func writeSSE(c *gin.Context, event sseEvent) {
	data, _ := json.Marshal(event)
	c.Writer.Write([]byte("data: "))
	c.Writer.Write(data)
	c.Writer.Write([]byte("\n\n"))
	c.Writer.Flush()
}
