// internal/dao/user.go —— 用户模型与数据访问。
//
// 表已用 SQL 建好(scripts/mysql-init),GORM 模型只做映射,不用 AutoMigrate。
// dao 层职责:纯数据库操作,不含业务判断(查重逻辑属于 business)。
package dao

import (
	"errors"
	"time"

	"gorm.io/gorm"
)

// User 映射 users 表。
// GORM 默认表名是结构体复数小写(users),字段默认蛇形(password_hash),正好对齐,
// 无需额外标签;CreatedAt 是 GORM 约定字段,插入时自动填。
type User struct {
	ID           uint64 `gorm:"primaryKey"`
	Username     string `gorm:"size:64;uniqueIndex"`
	PasswordHash string `gorm:"size:255"`
	CreatedAt    time.Time
}

// CreateUser 插入新用户,返回带 ID 的记录。
func CreateUser(username, passwordHash string) (*User, error) {
	u := &User{Username: username, PasswordHash: passwordHash}
	if err := DB.Create(u).Error; err != nil {
		return nil, err
	}
	return u, nil // Create 成功后 u.ID 已被 GORM 回填
}

// GetUserByUsername 按用户名查;不存在返回 (nil, nil)(把"没找到"和"出错"区分开)。
func GetUserByUsername(username string) (*User, error) {
	var u User
	err := DB.Where("username = ?", username).First(&u).Error
	if errors.Is(err, gorm.ErrRecordNotFound) {
		return nil, nil // 没找到不算错误,业务层据此判断"用户名可用"或"用户不存在"
	}
	if err != nil {
		return nil, err
	}
	return &u, nil
}
