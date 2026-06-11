// internal/business/auth.go —— 注册/登录业务逻辑。
//
// 职责:业务规则(查重、密码校验)+ 密码哈希(bcrypt)+ JWT 签发。
// 不碰 HTTP(那是 gateway 的事),不写裸 SQL(那是 dao 的事)。
package business

import (
	"errors"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"

	"github.com/sicheng-svg/snap-solver/server/internal/dao"
)

// JWT 密钥:环境变量 JWT_SECRET,开发期有默认值(生产必须改!)
func jwtSecret() []byte {
	if s := os.Getenv("JWT_SECRET"); s != "" {
		return []byte(s)
	}
	return []byte("snap-solver-dev-secret-change-me")
}

var (
	ErrUsernameTaken = errors.New("用户名已被注册")
	ErrAuthFailed    = errors.New("用户名或密码错误")
)

// Register 注册:查重 -> bcrypt 哈希 -> 入库。成功返回签好的 JWT(注册即登录)。
func Register(username, password string) (string, error) {
	// 1. 查重
	exist, err := dao.GetUserByUsername(username)
	if err != nil {
		return "", err
	}
	if exist != nil {
		return "", ErrUsernameTaken
	}

	// 2. bcrypt 哈希(自带盐,同一密码每次哈希结果不同;cost 用默认 10)
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", err
	}

	// 3. 入库
	u, err := dao.CreateUser(username, string(hash))
	if err != nil {
		return "", err
	}

	// 4. 注册即登录:直接签 JWT
	return signToken(u.ID)
}

// Login 登录:查用户 -> bcrypt 比对 -> 签 JWT。
// 注意:用户不存在和密码错误返回同一个错误(不暴露"用户名是否存在",防撞库探测)。
func Login(username, password string) (string, error) {
	u, err := dao.GetUserByUsername(username)
	if err != nil {
		return "", err
	}
	if u == nil {
		return "", ErrAuthFailed
	}
	// bcrypt 比对:把明文密码和存的哈希比(内部重做哈希)
	if bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(password)) != nil {
		return "", ErrAuthFailed
	}
	return signToken(u.ID)
}

// signToken 签发 JWT:payload 含 user_id,7 天过期,HMAC-SHA256 签名。
func signToken(userID uint64) (string, error) {
	claims := jwt.MapClaims{
		"user_id": userID,
		"exp":     time.Now().Add(7 * 24 * time.Hour).Unix(),
	}
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	return token.SignedString(jwtSecret())
}

// ParseToken 校验并解析 JWT,返回 user_id。鉴权中间件用。
func ParseToken(tokenStr string) (uint64, error) {
	token, err := jwt.Parse(tokenStr, func(t *jwt.Token) (interface{}, error) {
		// 防算法替换攻击:只接受 HMAC 族
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, errors.New("非法签名算法")
		}
		return jwtSecret(), nil
	})
	if err != nil || !token.Valid {
		return 0, errors.New("token 无效或已过期")
	}
	claims, ok := token.Claims.(jwt.MapClaims)
	if !ok {
		return 0, errors.New("claims 解析失败")
	}
	// JSON 数字解析成 float64,转回 uint64
	uid, ok := claims["user_id"].(float64)
	if !ok {
		return 0, errors.New("token 缺少 user_id")
	}
	return uint64(uid), nil
}
