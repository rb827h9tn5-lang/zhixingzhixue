# 数据库迁移说明

数据库结构由 Flask-Migrate/Alembic 管理。迁移命令必须在 `backend` 目录执行。

## 全新数据库

```powershell
python -m flask --app run.py db upgrade
python -m flask --app run.py db current
```

成功标志：最后显示 `1ddb543ec69b (head)`。

## 已有 SQLite 开发库

先停止后端，备份数据库：

```powershell
Copy-Item instance/study_ai.db instance/study_ai.db.manual-backup
```

仅当数据库已有旧业务表、但没有 `alembic_version` 表时执行：

```powershell
python -m flask --app run.py db stamp 900e17ba0f92
python -m flask --app run.py db upgrade
python -m flask --app run.py db current
```

成功标志：

- 当前版本为 `1ddb543ec69b (head)`。
- 原有用户、测评、资源等记录数量不变。
- 新增 `courses`、`chapters`、`knowledge_points`、`knowledge_relations`、`knowledge_chunks`。
- 新增 `profile_versions`、`profile_evidence`，每条旧画像生成一个可追溯的 v1 当前快照。

不要对空数据库执行 `stamp`。空数据库应直接执行 `db upgrade`。

## 已有 MySQL / Docker 数据卷

先做数据库备份。若旧库没有 `alembic_version` 表，首次使用新版本前执行：

```powershell
docker compose run --rm backend python -m flask --app run.py db stamp 900e17ba0f92
docker compose run --rm backend python -m flask --app run.py db upgrade
```

之后正常执行 `docker compose up -d --build`。后端容器每次启动会先执行幂等的 `db upgrade`。

风险提示：`stamp` 只登记版本，不创建表。只有确认旧库已经包含基线的 12 张业务表时才能使用；结构不完整的库应先恢复备份或新建数据库。

## 回退

先备份，再执行：

```powershell
python -m flask --app run.py db downgrade 603a60d0b4ba
```

这只回退 P0-4 的画像版本和证据结构。若要继续回退课程知识结构，再执行：

```powershell
python -m flask --app run.py db downgrade 900e17ba0f92
```

降级会删除对应阶段新增的数据。若新表已有业务数据，优先恢复升级前备份，不建议直接降级。
