// internal/business/session.go —— 会话业务逻辑。
//
// 核心职责:归属校验(防越权)+ 会话生命周期规则(自动命名等)。
package business

import (
	"errors"

	"github.com/sicheng-svg/snap-solver/server/internal/dao"
)

var ErrSessionNotFound = errors.New("会话不存在或无权访问")

// CreateSession 新建会话(默认标题,首问时自动改名)
func CreateSession(userID uint64) (*dao.Session, error) {
	return dao.CreateSession(userID, "新会话")
}

func ListSessions(userID uint64) ([]dao.Session, error) {
	return dao.ListSessions(userID)
}

// CheckOwnership 校验会话归属:存在且属于该用户才放行。
// 所有按 session_id 操作的入口(删除/拉历史/解题)都必须先过这个 —— 防水平越权。
func CheckOwnership(sessionID, userID uint64) (*dao.Session, error) {
	s, err := dao.GetSession(sessionID)
	if err != nil {
		return nil, err
	}
	if s == nil || s.UserID != userID {
		// 不存在和无权返回同一个错(不暴露"这个 id 存不存在")
		return nil, ErrSessionNotFound
	}
	return s, nil
}

func DeleteSession(sessionID, userID uint64) error {
	if _, err := CheckOwnership(sessionID, userID); err != nil {
		return err
	}
	return dao.DeleteSession(sessionID)
}

func ListMessages(sessionID, userID uint64) ([]dao.Message, error) {
	if _, err := CheckOwnership(sessionID, userID); err != nil {
		return nil, err
	}
	return dao.ListMessages(sessionID)
}

// SaveUserMessage 落库用户消息;若是该会话首条消息,用题目前 20 字自动命名会话。
func SaveUserMessage(s *dao.Session, content string, imagePath *string) error {
	msg := &dao.Message{SessionID: s.ID, Role: "user", Content: content, ImagePath: imagePath}
	if err := dao.CreateMessage(msg); err != nil {
		return err
	}
	if s.Title == "新会话" && content != "" {
		title := []rune(content)
		if len(title) > 20 {
			title = title[:20]
		}
		_ = dao.UpdateSessionTitle(s.ID, string(title)) // 命名失败不阻断主流程
	}
	return dao.TouchSession(s.ID)
}

// SaveAssistantMessage 落库 AI 回答(流式结束后调用)
func SaveAssistantMessage(sessionID uint64, content string, thinkingJSON string) error {
	var tj *string
	if thinkingJSON != "" {
		tj = &thinkingJSON
	}
	msg := &dao.Message{SessionID: sessionID, Role: "assistant", Content: content, ThinkingJSON: tj}
	if err := dao.CreateMessage(msg); err != nil {
		return err
	}
	return dao.TouchSession(sessionID)
}
