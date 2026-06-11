// internal/dao/session.go —— 会话/消息模型与数据访问。
package dao

import (
	"time"

	"gorm.io/gorm"
)

// Session 映射 sessions 表
type Session struct {
	ID        uint64    `gorm:"primaryKey" json:"id"`
	UserID    uint64    `json:"user_id"`
	Title     string    `gorm:"size:255" json:"title"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"` // GORM 约定字段:Create/Update 自动维护
}

// Message 映射 messages 表
type Message struct {
	ID           uint64    `gorm:"primaryKey" json:"id"`
	SessionID    uint64    `json:"session_id"`
	Role         string    `gorm:"size:16" json:"role"` // user / assistant
	Content      string    `gorm:"type:mediumtext" json:"content"`
	ImagePath    *string   `gorm:"size:512" json:"image_path"`     // 指针:可空列用 *string,NULL 映射 nil
	ThinkingJSON *string   `gorm:"type:json" json:"thinking_json"` // 同上;存 JSON 字符串
	CreatedAt    time.Time `json:"created_at"`
}

// ---- Session ----

func CreateSession(userID uint64, title string) (*Session, error) {
	s := &Session{UserID: userID, Title: title}
	if err := DB.Create(s).Error; err != nil {
		return nil, err
	}
	return s, nil
}

// ListSessions 某用户的会话列表,最近活跃在前(走 idx_user_updated 索引)
func ListSessions(userID uint64) ([]Session, error) {
	var list []Session
	err := DB.Where("user_id = ?", userID).Order("updated_at DESC").Find(&list).Error
	return list, err
}

// GetSession 按 id 查(归属校验在 business 层做);没找到返回 (nil, nil)
func GetSession(id uint64) (*Session, error) {
	var s Session
	err := DB.First(&s, id).Error
	if err == gorm.ErrRecordNotFound {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &s, nil
}

// DeleteSession 删会话 + 其全部消息(事务:要么都删,要么都不删)
func DeleteSession(id uint64) error {
	return DB.Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("session_id = ?", id).Delete(&Message{}).Error; err != nil {
			return err
		}
		return tx.Delete(&Session{}, id).Error
	})
}

// TouchSession 更新会话的 updated_at(每次新消息后调,让列表按活跃排序)
func TouchSession(id uint64) error {
	return DB.Model(&Session{}).Where("id = ?", id).
		Update("updated_at", time.Now()).Error
}

// UpdateSessionTitle 重命名(也用于首问自动命名)
func UpdateSessionTitle(id uint64, title string) error {
	return DB.Model(&Session{}).Where("id = ?", id).Update("title", title).Error
}

// ---- Message ----

func CreateMessage(m *Message) error {
	return DB.Create(m).Error
}

// ListMessages 某会话全部消息,按时间正序(走 idx_session_created 索引)
func ListMessages(sessionID uint64) ([]Message, error) {
	var list []Message
	err := DB.Where("session_id = ?", sessionID).Order("created_at ASC").Find(&list).Error
	return list, err
}
