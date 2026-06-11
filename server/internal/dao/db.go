// internal/dao/db.go —— 数据库初始化(GORM + MySQL)。
//
// DSN 从环境变量 MYSQL_DSN 读,未设置用本地开发默认值(docker compose 起的 3308)。
// 开发期开启 SQL 日志:GORM 每次执行的真实 SQL 都会打印 —— 保持对底层 SQL 的感知。
package dao

import (
	"log"
	"os"

	"gorm.io/driver/mysql"
	"gorm.io/gorm"
	"gorm.io/gorm/logger"
)

var DB *gorm.DB

// Init 连接 MySQL,程序启动时调用一次。
func Init() {
	dsn := os.Getenv("MYSQL_DSN")
	if dsn == "" {
		// 开发默认:docker compose 的 MySQL(端口 3308,库 snap_solver)
		// parseTime=True 让 DATETIME 正确扫进 time.Time;charset 与建表一致
		dsn = "root:snap123456@tcp(127.0.0.1:3308)/snap_solver?charset=utf8mb4&parseTime=True&loc=Local"
	}

	db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
		Logger: logger.Default.LogMode(logger.Info), // 打印每条 SQL(开发期)
	})
	if err != nil {
		log.Fatalf("连接 MySQL 失败: %v", err)
	}
	DB = db
	log.Println("MySQL 连接成功")
}
