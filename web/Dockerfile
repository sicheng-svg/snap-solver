# web/Dockerfile —— 前端(多阶段:node 构建 + nginx 托管)
FROM node:20-alpine AS builder
WORKDIR /app

# 国内 npm 源(加速 npm install)
RUN npm config set registry https://registry.npmmirror.com

COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

# 运行阶段:nginx 托管
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]