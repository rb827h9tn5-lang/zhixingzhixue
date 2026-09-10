# Multi_Agent-Study-Assistant

基于大模型的个性化资源生成与学习辅助平台。当前实现包含 Flask 后端、Vue 3 前端、SQLite/MySQL 数据库和 Docker 编排。

## 功能

- 对话式动态学生画像，覆盖知识基础、学习目标、学习风格、认知偏好、经验、时间、动机、参与习惯等维度
- 个性化资源生成，覆盖讲解文档、思维导图、题库、拓展阅读、PPT 和实操案例
- 个性化学习路径规划和资源推送策略
- 在线测评、学习效果评估、错题反馈和画像更新
- 智能辅导问答，支持通过环境变量配置 MiMo 等兼容接口
- 结构化课程知识库，支持课程、章节、知识点、页级分块和来源引用
- 关键词检索始终可用，配置嵌入服务后可使用向量检索

## 本地运行

如果希望本地 `python run.py` 写入 MySQL，而不是默认 SQLite，先准备 `.env`：

```bash
copy .env.mysql.example .env
```

然后按你的 MySQL 修改 `.env` 中的 `MYSQL_USER` 和 `MYSQL_PASSWORD`。

后端安装和启动：

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m flask --app run.py db upgrade
python -X utf8 run.py
```

启动时终端会打印当前数据库连接。看到 `mysql+pymysql://...` 才表示正在写入 MySQL；如果看到 `sqlite:///study_ai.db`，说明 `.env` 没有配置 `MYSQL_HOST`。

数据库升级和旧库基线登记详见 [backend/MIGRATIONS.md](backend/MIGRATIONS.md)。

前端：

```bash
cd frontend
npm install
npm run dev
```

访问地址：

- 前端：http://localhost:5173
- 后端健康检查：http://localhost:5000/api/health

## Docker 运行

```bash
copy .env.example .env
docker compose up -d --build
```

访问地址：

- Nginx 入口：http://localhost
- 前端容器端口：http://localhost:5173
- Flask API：http://localhost/api/health

停止：

```bash
docker compose down
```

## 默认账号

系统不内置账号。首次进入前端后点击“注册并进入”，即可创建演示学生账号。

## AI 配置

复制 `backend/.env.example` 为 `backend/.env`，再填写自己的服务地址、模型名和密钥。不要把真实密钥提交到源码。

对话、代码分析和语音功能使用 `MIMO_BASE_URL`、`MIMO_API_KEY` 及对应模型变量；向量检索可通过 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_EMBEDDING_MODEL` 配置。未配置嵌入服务时，知识库会保留关键词检索能力。

资源工厂中的思维导图和 PPT 制作可分别配置 `MINDMAP_MODEL_API_URL`、`PPT_MODEL_API_URL` 接入外部画图/PPT 模型 API；未配置时会返回 Mermaid 结构或 PPT 大纲。
