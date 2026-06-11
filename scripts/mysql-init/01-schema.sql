-- scripts/mysql-init/01-schema.sql
-- snap-solver 业务表(MySQL 容器首次启动自动执行)
-- 注意:只在数据卷为空的首次启动执行;已有数据后改表需手动迁移。

USE snap_solver;

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(64)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,          -- bcrypt 哈希(绝不存明文)
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_username (username)             -- 用户名唯一
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 会话表
CREATE TABLE IF NOT EXISTS sessions (
    id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT UNSIGNED NOT NULL,
    title      VARCHAR(255)    NOT NULL DEFAULT '新会话',  -- 可用首问前若干字自动命名
    created_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
               ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_user_updated (user_id, updated_at)    -- 按用户拉会话列表(按更新时间排序)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 消息表(用户提问 + AI 回答都落这里)
CREATE TABLE IF NOT EXISTS messages (
    id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    session_id    BIGINT UNSIGNED NOT NULL,
    role          ENUM('user','assistant') NOT NULL,
    content       MEDIUMTEXT      NOT NULL,        -- 题目文本 / 完整回答(MEDIUMTEXT 防长回答截断)
    image_path    VARCHAR(512)    NULL,            -- 用户上传图片的本地路径(可空)
    thinking_json JSON            NULL,            -- 该轮思考过程(assistant 行,可空)
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_session_created (session_id, created_at)  -- 按会话拉历史(按时间排序)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;