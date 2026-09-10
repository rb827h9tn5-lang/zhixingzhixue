# 改进记录

## 2026-06-13：顶部导航区域重构——企业级 Header + Tabs 标签栏

### 变更内容
1. **布局重构**：
   - 移除旧 `.app-shell` 的 grid 布局，改为 flex 布局
   - 新增 `.main-layout` 作为侧栏右侧的主内容容器（flex 列方向）
   - 将面包屑从 main 区域移至顶部 Header 行
2. **顶部 Header 行**：
   - 新增 `.top-header`，高度 44px，白色背景，底部浅灰边框
   - 左侧：折叠按钮（32px，hover 浅灰背景）+ 系统标题（动态变化）+ 面包屑
   - 右侧：用户标签 + 退出按钮
   - 系统标题根据当前页面动态切换：总览/画像/路径/测评→"多智能体学习平台"，资源→"资源生成"，辅导→"学习中心"，知识库→"知识库管理"
3. **页面 Tabs 标签行**：
   - 新增 `.tab-bar`，高度 36px，白色背景，底部浅灰边框
   - 点击左侧菜单自动新增标签，dashboard 为固定标签
   - 当前标签高亮（蓝色 #3B82F6），非固定标签可关闭
   - 关闭当前标签后自动跳转相邻标签
   - 刷新后从 localStorage 恢复标签状态
4. **Tabs 状态管理**：
   - 新增 `stores/tabs.ts`（Pinia store）
   - 方法：addTab / removeTab / setActiveTab / saveTabs / restoreTabs
   - 支持 localStorage 持久化
5. **CSS 清理**：
   - 删除旧 `.topbar` / `.topbar-left` / `.brand` / `.breadcrumb-bar` 样式
   - `.main` → `.page-content`
   - 响应式样式适配新布局（sidebar mobile top 64px→80px）
6. **新增文件**：
   - `frontend/src/stores/tabs.ts`

## 2026-06-13：智能辅导页面布局优化

### 变更内容
1. **主页面加宽**：
   - `.chat-shell` 侧栏宽度从 280px 缩减至 220px，为主内容区腾出 60px 空间
   - `.chat-messages` 内边距从 28px 缩减至 24px，内容展示区域更宽敞
2. **影响范围**：
   - `frontend/src/style.css`（两处 CSS 调整）

## 2026-06-13：思维导图组件重构——使用 simple-mind-map 库替代 Mermaid

### 变更内容
1. **技术方案切换**：
   - 旧方案：Mermaid.js 渲染 mindmap 文本 → SVG，纯 CSS 布局，无交互能力
   - 新方案：`simple-mind-map` 专业思维导图库，支持中心放射型布局（XMind 风格）
2. **MindMapViewer.vue 重写**：
   - 安装 `simple-mind-map@0.14.0-fix.2` 依赖
   - 自动解析后端返回的 Mermaid mindmap 文本 → 树状 JSON → 渲染导图
   - 中心放射型布局（`layout: 'mindMap'`），节点向右展开
   - 不同一级分支使用不同颜色（RainbowLines 插件）
   - 平滑曲线连线，自动布局
   - 支持缩放、拖拽、适应画布
   - 支持导出 SVG / PNG
   - 工具栏：放大/缩小/适应画布/导出 PNG/导出 SVG
   - 只读模式（`readonly: true`），专注展示
   - 保留原 `content` prop 接口，向后兼容
3. **ResourcesView.vue 适配**：
   - 添加 `mindMapViewerRef` 模板引用
   - `downloadMindMap()` 改为调用组件暴露的 `exportSvg()` 方法
   - 移除旧的 `getMindMapSvg()` DOM 查询函数
4. **新增文件**：
   - `frontend/src/types/simple-mind-map.d.ts`（类型声明）
5. **影响范围**：
   - `frontend/package.json`（新增依赖）
   - `frontend/src/components/MindMapViewer.vue`（完全重写）
   - `frontend/src/views/ResourcesView.vue`（`downloadMindMap` 适配）
   - `frontend/src/types/simple-mind-map.d.ts`（新增）

### 影响范围
- `frontend/src/App.vue`
- `frontend/src/style.css`
- `frontend/src/stores/tabs.ts`（新增）

## 2026-06-13：总览/个人画像/学习路径顶栏匹配测评评估风格

### 变更内容
- `App.vue`：恢复被误删的 `isMobile` ref 和 `onResize` 函数
- `App.vue`：新增 `isOverviewPage` 计算属性（检测 dashboard/profile/path 页面）
- `App.vue`：`<header>` 添加 `:class="{ 'topbar--overview': isOverviewPage }"`
- `style.css`：移除旧 `.topbar--overview`（浅蓝色），新增匹配测评评估页面的渐变背景
- `style.css`：`.topbar--overview` 使用 `linear-gradient(135deg, #eff6ff 0%, #f8faff 50%, #e0f2fe 100%)` + `border-color: #bfdbfe`

### 影响范围
- `frontend/src/App.vue`
- `frontend/src/style.css`

## 2026-06-10：四大数据流增强——防止模块生成时因缺少数据参照而产生幻觉

### 变更内容
1. **新增 4 个功能开关（默认关闭）**：
   - `rag_config.py`：`ENABLE_EVAL_HISTORY_REF`（测评历史参照）、`ENABLE_PATH_LEARNED_TRACKING`（路径已学/未学标记）、`ENABLE_QUIZ_WEAK_POINTS_PRIORITY`（错题优先出题）、`ENABLE_TUTOR_LEARNING_RECORD`（辅导学习记录）

2. **新增 4 个数据摘要构建函数（learning.py）**：
   - `_build_quiz_history_summary()`：从 QuizResult 表提取最近分数趋势和薄弱点汇总
   - `_build_learning_record_summary()`：从 Resource/QuizResult/CodingCaseRecord 表提取资源类型、测评分数、实操完成情况
   - `_build_weak_points_summary()`：从 QuizResult 表提取历史错题知识点列表
   - `_build_learned_knowledge_summary()`：从 Resource/KnowledgeDocument/QuizResult 表构建已学/未学知识点概览
   - 所有函数在数据不存在时返回空字符串/空字典，不会影响原有流程

3. **Gap 1：测评评估增加历史参照**：
   - `learning.py` `evaluate_quiz()`：调用 `_build_quiz_history_summary()` 获取历史测评摘要，传入 `generate_quiz_evaluation()`
   - `study_agent.py` `generate_quiz_evaluation()`：新增 `history_summary` 参数，在评估报告和 LLM 改进建议中注入历史对比参照

4. **Gap 2：学习路径标记已学/未学**：
   - `learning.py` `plan_path()`：调用 `_build_learned_knowledge_summary()` 构建概览，加入 context 字典
   - `study_agent.py` `plan_path()`：新增 `_format_learned_knowledge()` 方法，在 prompt 中展示已学/未学知识点概览

5. **Gap 3：题库生成错题优先**：
   - `learning.py` `generate_quiz()`：调用 `_build_weak_points_summary()`，传入 `generate_structured_quiz()`
   - `study_agent.py` `generate_structured_quiz()`：新增 `weak_points_summary` 参数，传递到 `_generate_question_plan()` 和 `_generate_single_question()` 的 prompt 中

6. **Gap 4：智能辅导关联学习记录**：
   - `learning.py` `ask_tutor()`：调用 `_build_learning_record_summary()`，分别注入到 text-only 路径的 context 变量和多模态路径的 question 文本中

### 影响范围
- `backend/app/services/rag_config.py`：新增 4 个环境变量开关
- `backend/app/routes/learning.py`：新增 4 个摘要函数，修改 4 个路由端点
- `backend/app/services/study_agent.py`：新增 1 个辅助方法，修改 4 个方法签名

### 启用方式
在 `.env` 中添加以下配置即可开启对应增强（默认全部关闭）：
```
ENABLE_EVAL_HISTORY_REF=true
ENABLE_PATH_LEARNED_TRACKING=true
ENABLE_QUIZ_WEAK_POINTS_PRIORITY=true
ENABLE_TUTOR_LEARNING_RECORD=true
```

## 2026-06-10：进度条实时计时（第二次迭代）

### 变更内容
1. **ResourcesView.vue**：新增 `liveElapsed`、`liveTimerInterval`、`startLiveTimer()`/`stopLiveTimer()`、`formatLiveTime()`，在 generateCurrentResource()、handleGenerateExerciseBank()、generateCodingCase() 中集成实时计时
2. **PathView.vue**：同上，在 `planPath()` 中集成
3. **QuizView.vue**：同上，在 `handleGenerateQuiz()` 中集成
4. **PptWorkbench.vue**：同上，在 `outlineGenerate()`、`startPolling()`、`resetAll()` 中集成
5. **TutorView.vue**：新增 `liveElapsed` 实时计时，在 askTutor()、submitEditedMessage()、regenerateAssistantMessage()、continueTutorAnswer() 中集成，消息上方显示"已耗时 XX秒"
6. 所有视图统一 CSS：`.live-timer` 带 timer-pulse 脉冲动画
7. **PPT 布局修复**：将创新面板（MultiAgentDebatePanel、TrustReport、ResourceQualityCard）从 `.ppt-workbench-body` 外部移入 `<main class="ppt-center">` 内部，防止评估报告出现时挤压主内容区高度

### 影响范围
- `frontend/src/views/ResourcesView.vue`
- `frontend/src/views/PathView.vue`
- `frontend/src/views/QuizView.vue`
- `frontend/src/components/PptWorkbench.vue`
- `frontend/src/views/TutorView.vue`

### 启用方式
确保 `frontend/.env` 中 `VITE_ENABLE_RESOURCE_TIMING=true`

### 验收标准
1. 配置关闭时（默认），所有功能表现与修改前完全一致
2. 开启后，测评评估报告中出现"历史对比"章节
3. 开启后，学习路径中出现"已学/未学知识点概览"章节
4. 开启后，生成的练习题优先覆盖历史错题知识点
5. 开启后，智能辅导的回答参考了学生的完整学习记录

## 2026-06-10：资源生成增加计时并显示（前端本地计时，不写数据库）

### 变更内容
1. **后端计时测量**：
   - `study_agent.py`：`generate_resource()`、`generate_structured_quiz()`、`generate_coding_case_question()` 方法增加 `time.time()` 计时，将 `duration_seconds` 写入返回的 meta 字典

2. **前端计时显示（本地计时，不写数据库）**：
   - `.env` / `.env.example` 新增 `VITE_ENABLE_RESOURCE_TIMING=true`
   - `ResourcesView.vue`：新增 `generationDuration` ref，在 `generateCurrentResource()` 开始/结束时计时
   - 生成完成后显示紫色"生成耗时 XX 秒"徽章，切换资源类型后自动清除
   - `env.d.ts`：新增 `ImportMetaEnv` 类型声明

3. **后续改为纯前端本地计时，不再存入数据库**：
   - 见 2026-06-10「计时数据移除数据库」条目

### 影响范围
- `backend/app/services/study_agent.py`：generate_resource 等 3 个方法增加计时（meta 返回）
- `frontend/.env` / `frontend/.env.example`：新增 VITE_ENABLE_RESOURCE_TIMING
- `frontend/src/env.d.ts`：新增 ImportMetaEnv 类型声明
- `frontend/src/views/ResourcesView.vue`：前端本地计时 + 显示徽章

### 验收标准
1. 前端 `VITE_ENABLE_RESOURCE_TIMING=true` 时，资源生成完成后显示紫色"生成耗时 XX 秒"徽章
2. 切换资源类型后计时自动清除
3. 计时数据不保存到后端数据库，仅前端显示

## 2026-06-10：前端超时 + 后端 LLM 超时配置化 + 测评评估并行化

### 变更内容
1. **前端 API 超时（5 分钟可配）**：
   - `frontend/.env` / `.env.example` 新增 `VITE_API_TIMEOUT_MS=300000`（默认 5 分钟）
   - `learning.ts`：新增 `abortWithTimeout()`、`combineSignals()` 工具函数
   - `generateResourceStream()` 集成超时信号，与外部 AbortSignal 合并
   - `env.d.ts`：已有 `ImportMetaEnv` 类型声明

2. **后端 LLM 超时（10 分钟可配）**：
   - `backend/.env.example` 新增 `LLM_CHAT_TIMEOUT=600`、`LLM_MULTIMODAL_TIMEOUT=600`
   - `ai_client.py`：`chat_timeout_s` 默认值从 300 改为 600（环境变量 `LLM_CHAT_TIMEOUT` 控制）

3. **测评评估改用 1 次规划 + N 道题并行生成模式**：
   - `study_agent.py`：`generate_quiz_evaluation()` 重写为三阶段并行模式
   - 阶段 1（`_build_evaluation_plan`）：将错题逐题规划为独立评估项，正确题按概念去重后抽样确认
   - 阶段 2（`_evaluate_single_question`）：通过 `ThreadPoolExecutor(max_workers=min(N, 8))` 并行调用 LLM 逐题评估
   - 阶段 3（`_merge_evaluation`）：合并结构化报告（总分、薄弱点）+ 逐题评估 + 最终 LLM 调用生成改进建议
   - 错误时回退到原有的 `_local_quiz_evaluation()` 兜底

### 影响范围
- `frontend/.env` / `frontend/.env.example`：新增 VITE_API_TIMEOUT_MS
- `frontend/src/api/learning.ts`：新增 abortWithTimeout / combineSignals
- `frontend/src/env.d.ts`：已有 ImportMetaEnv
- `backend/.env.example`：新增 LLM_CHAT_TIMEOUT、LLM_MULTIMODAL_TIMEOUT
- `backend/app/services/ai_client.py`：chat_timeout_s 默认 600
- `backend/app/services/study_agent.py`：重写 generate_quiz_evaluation（3 阶段并行）

### 验收标准
1. 前端生成资源超过 5 分钟自动超时中断，显示错误提示
2. 后端调用大模型超过 10 分钟自动超时，不阻塞其他请求
3. 测评评估改为 N+1 次 LLM 调用并行生成，每道错题独立评估，正确题按概念抽样确认
4. 评估结果包含逐题分析和整体改进建议，与原格式兼容

## 2026-06-10：计时数据移除数据库 + plan_path 上下文摘要优化

### 变更内容
1. **计时数据改为纯前端本地计时，不再存入数据库**：
   - `models.py`：移除 `Resource.generation_duration` 字段
   - `schema.sql`：移除 `resources.generation_duration` 列及兼容迁移 SQL
   - `learning.py`：移除所有 Resource 创建时的 `generation_duration` 参数（共 9 处）
   - `ResourcesView.vue`：改为前端 `generationDuration` ref 本地计时，不依赖后端返回字段

2. **学习路径上下文摘要优化（plan_path 路由）**：
   - `quiz_results`：改用 `with_entities` 只查询 `score`、`wrong_questions`、`created_at`，跳过 `quiz_content` 和 `answers` 大字段
   - `resources`：改用 `with_entities` 只查询 `resource_type`，跳过 `content` 大字段
   - `knowledge_documents`：保留已有摘要逻辑（240 字 excerpt）
   - `plan_path()` 方法内部早已做了摘要提取，路由层补充避免大量数据在内存中传递

### 影响范围
- `backend/app/models.py`：移除 generation_duration
- `database/schema.sql`：移除 generation_duration 列及迁移 SQL
- `backend/app/routes/learning.py`：9 处清除 generation_duration；plan_path 改用 with_entities 轻量查询
- `frontend/src/views/ResourcesView.vue`：改为前端本地计时
- `improvement.md`：本次记录

### 验收标准
1. 资源生成完成后，前端依然显示生成耗时（前端本地计时，不依赖后端）
2. 切换资源类型后计时自动清除
3. 生成学习路径时，不再加载完整的 quiz_content/answers 和 resource content 大字段到内存
4. 已有数据库不受影响（generation_duration 列保留旧数据但不再写入）

## 2026-06-08：今日推荐任务新增独立刷新按钮，与"刷新数据"解耦

### 变更内容
1. **新增任务独立刷新按钮**：
   - 在"今日推荐任务"模块头部添加一个圆形刷新按钮（Refresh 图标）
   - 点击仅刷新任务列表（清除缓存 + 重新请求），不影响成绩趋势、画像摘要等数据
   - 新增 `taskLoading` 状态，刷新按钮独立旋转

2. **"刷新数据"按钮不再影响任务**：
   - `refreshAll()` 移除 `clearTasksCache()` 和 `loadTasks()` 调用
   - `loadDashboard()` 不再调用 `loadTasks()`，职责分离
   - `onMounted` 分别调用 `loadDashboard()` 和 `loadTasks()`

### 影响范围
- `frontend/src/views/DashboardView.vue`：模板新增刷新按钮，逻辑拆分
- `improvement.md`：本次记录

### 验收标准
1. 点击任务模块的圆圈刷新按钮，任务重新随机选取（3-5 条），不清除其他数据
2. 点击"刷新数据"按钮，只更新成绩趋势、画像信息等，不影响当前任务列表

## 2026-06-08：今日推荐任务改为 10 种类型每日轮转（3-5 个/天）

### 变更内容
1. **重写 `recommended_tasks()` 任务构建逻辑**：
   - 移除原有的条件型任务（薄弱点、入门水平、低分重测、错题、6 种缺失资源逐个检查、PPT 检查、轮转任务、保底逻辑等 200+ 行）
   - 改为一个 `DAILY_POOL` 包含 10 种核心学习类型（测评评估、学习路径、讲解文档、思维导图、练习题库、拓展阅读、实操案例、教学视频、PPT演示文稿、智能辅导）
   - 每天随机选取 3-5 个，确保不同日子看到不同组合
   - **已完成的任务类型优先保留**：先查 `today_actions`，已完成的类型始终出现在列表中，未完成的随机补到 3-5 个。切换页面回来后，已完成的任务仍然可见
   - 每种类型根据用户数据个性化：
     - 测评：低分→"重新测评"、无记录→"首次测评"、有记录→"每日一练"
     - 路径：有→"继续"、无→"规划"
     - 资源类：已生成→"复习"+ 黄色标签、未生成→"生成"+ 绿色标签
     - 智能辅导：固定"智能辅导问答"
   - 移除 `review_wrong_questions` 特例完成判断
2. **丰富任务名称和描述文案**：为每个场景配置 2-4 条不重复的名称和描述，每次刷新随机选取（如"纸上得来终觉浅，亲手编码才是真功夫"、"巩固讲解文档"、"再测一次（上次 45 分）"）
3. **移除固定日期种子**：改为每次刷新重新随机选取类型组合，避免同一天刷不出某些类型的问题

2. **前端 `mergeTaskLists()`**：
   - 移除硬编码 `.slice(0, 6)`，直接返回合并结果，数量由后端决定

### 影响范围
- `backend/app/routes/learning.py`：recommended_tasks() 完全重写
- `frontend/src/views/DashboardView.vue`：mergeTaskLists() 移除 slice 限制
- `improvement.md`：本次记录

### 验收标准
1. 登录总览页面后看到 3-5 个任务（不是固定的 6 个）
2. 刷新页面后任务顺序改变，且不同日子的任务组合不同
3. 10 种类型（测评评估、学习路径、讲解文档、思维导图、练习题库、拓展阅读、实操案例、教学视频、PPT、智能辅导）都能在不同日子出现
4. 访问对应页面后任务自动勾选

### 变更内容
1. **新增每日轮转任务池（`recommended_tasks()`）**：
   - 在条件任务（画像、测评、路径、缺失资源）之后，新增 3 个每日轮转任务：
     - `ai_tutor_chat`（AI 问答练习 → 跳转智能辅导，完成需 `visit_tutor`）
     - `explore_knowledge`（探索知识库 → 跳转知识库管理，完成需 `visit_knowledge`）
     - `daily_quiz_challenge`（每日一练 → 跳转测评，完成需 `visit_quiz`）
   - 轮转任务根据"同类型最多 2 个"原则动态加入，确保任务类型视觉多样性
   - 刷新时不再只是打乱顺序，每次可能呈现不同的任务组合

2. **`log_task_action()` 新增有效 action 类型**：
   - 新增 `visit_tutor`、`visit_knowledge`、`visit_dashboard` 三种有效 action

3. **前端新增页面访问记录**：
   - `TutorView.vue` 在 `onMounted` 中调用 `api.logTaskAction('visit_tutor')`
   - `KnowledgeView.vue` 在 `onMounted` 中调用 `api.logTaskAction('visit_knowledge')`

### 影响范围
- `backend/app/routes/learning.py`：recommended_tasks() 新增轮转任务池，log_task_action() 新增 action 类型
- `frontend/src/views/TutorView.vue`：新增 visit_tutor 行为记录
- `frontend/src/views/KnowledgeView.vue`：新增 visit_knowledge 行为记录
- `improvement.md`：本次记录

### 验收标准
1. 用户登录总览页面后看到的推荐任务中，每次刷新可能包含 AI 问答练习、探索知识库、每日一练等不同类型的轮转任务
2. 用户访问智能辅导页面后，`ai_tutor_chat` 任务自动勾选为完成
3. 用户访问知识库管理页面后，`explore_knowledge` 任务自动勾选为完成
4. 用户做一次测评后，`daily_quiz_challenge` 任务自动勾选为完成
5. 同类型任务不会超过 2 个，保持视觉多样性

## 2026-06-08：DB 通道机制实现 — 统一 critical / async / background 三通道

### 变更内容
1. **新增 `backend/app/services/db_channel.py`**：
   - 定义 `DbChannel` 枚举：CRITICAL / ASYNC / BACKGROUND
   - 统一入口函数 `enqueue_db_task(channel, task_name, handler, app, **payload)`
   - CRITICAL：同步阻塞，返回 handler 结果，错误向上传播
   - ASYNC：`ThreadPoolExecutor(max_workers=4)` 异步执行，自动捕获错误、打印 error log 和耗时日志，失败不影响当前响应
   - BACKGROUND：内存 `Queue` + 后台 worker 线程消费，保留 `put`/`get`/`shutdown` 接口，后续可替换为 Redis/Celery/BullMQ
   - `reset_channel_metrics()` / `get_channel_metrics()`：请求级 metrics 管理
   - `shutdown()`：优雅关闭

2. **修改 `backend/app/routes/learning.py`**：
   - 导入 `DbChannel`、`enqueue_db_task`、`get_channel_metrics`、`reset_channel_metrics`
   - 新增 4 个 handler 函数：
     - `_handler_save_resource` → async_channel（保存资源记录）
     - `_handler_update_profile` → async/background_channel（更新学习画像）
     - `_handler_update_conversation` → async_channel（保存对话消息）
     - `_handler_save_quiz` → background_channel（保存测评结果）
     - `_handler_log_action` → background_channel（记录任务操作）
   - 智能辅导 `/tutor/ask` 端点：
     - 请求开始调用 `reset_channel_metrics()`
     - `auto_update_profile` + `db.session.commit()` 从同步改为 async_channel 提交
     - 流式路径：`enqueue_db_task(ASYNC, "tutor_ask_update_profile", ...)` 在返回 Response 前调用，不阻塞 generate_func 首字输出
     - 非流式路径：同上，通过 async_channel 提交，不阻塞 jsonify 响应
     - `_rag_timing.record("db_channels", ...)` 记录 `dbCriticalMs`、`dbAsyncQueuedMs`、`dbBackgroundQueuedMs`、`dbAsyncTaskCount`、`dbBackgroundTaskCount`、`dbChannelErrors`

### DB 操作分类清单

| 通道 | DB 操作 | handler | 端点/位置 |
|------|---------|---------|-----------|
| **critical_channel** | 读取用户权限 | 直接调用 `current_profile()` | 所有 @jwt_required 端点开头 |
| | 读取 agent 配置 | `current_profile().to_dict()` | 所有资源生成端点 |
| | 读取会话历史 | `ChatConversation.query` | `/tutor/ask`、`/chat-conversations` |
| | 读取知识库配置/文档 | `KnowledgeDocument.query` | `/tutor/ask` → `retrieve_knowledge_context()` |
| | 读取资源生成参数 | `Profile`/`Resource` 查询 | `/resources/generate`、`/path/plan` |
| **async_channel** | 保存用户消息 | `_handler_update_conversation` | `/chat-conversations` PATCH |
| | 保存助手回复 | `_handler_update_conversation` | `/tutor/ask` 流式结束后 |
| | 保存 token usage | (预留) | — |
| | 保存 retrievedDocIds | (预留) | — |
| | 保存 citations | (预留) | — |
| | 保存生成耗时 | (预留) | — |
| | 保存资源生成记录 | `_handler_save_resource` | `/resources/generate` |
| | 更新学习画像 | `_handler_update_profile` | `/tutor/ask`（async 已实现） |
| **background_channel** | 生成会话标题 | `_handler_update_conversation` | (预留) |
| | 更新学习画像（低优） | `_handler_update_profile` | `/quiz/submit`、`/evaluation` |
| | 生成资源索引 | (预留) | — |
| | PPT 文件生成记录 | `_handler_save_resource` | `/ppt/*` |
| | 思维导图图片生成记录 | (预留) | — |
| | 教学视频素材生成记录 | (预留) | — |
| | 题库入库 | `_handler_save_quiz` | `/quiz/*` |
| | 测评报告生成 | (预留) | — |
| | 统计分析 | (预留) | — |

### 关键设计说明

- **主聊天流只 await critical_channel**：`/tutor/ask` 中 `current_profile()` 和 `retrieve_knowledge_context()` 使用 critical（同步），`auto_update_profile` 使用 async（不阻塞首字和流式输出）
- **async/background 完全不阻塞 stream**：通过 `ThreadPoolExecutor.submit()` + 后台 worker 线程实现，enqueue 耗时仅 0.1ms 级
- **流式输出不写 DB**：`generate_multimodal()` 和 `generate_text_only()` 全程不调用 `db.session` 写操作，`assistantAnswer` 在内存中累计，通过 async_channel 在流结束后一次性写入
- **错误隔离**：async/background 任务自动 try/except，打印 `[db_channel]` 前缀的 error log，失败不影响用户响应

### 如何查看 DB channel 日志

```
# 标准 error log（stderr）
[db_channel] ASYNC task 'tutor_ask_update_profile' OK in 15.3ms
[db_channel] ASYNC task 'tutor_ask_update_profile' FAILED: ... (traceback)

# RAG timing log 中附带 channel metrics（需开启 ENABLE_RAG_TIMING_LOG=true）
[rag_timing] ... dbCriticalMs=12.3 | dbAsyncQueuedMs=0.1 | dbBackgroundQueuedMs=0.0 | dbAsyncTaskCount=1 | dbBackgroundTaskCount=0 | dbChannelErrors=0

# 关闭 async executor 的方式（应用退出时）
from app.services.db_channel import shutdown
shutdown()
```

### 影响范围
- `backend/app/services/db_channel.py`（新建）
- `backend/app/routes/learning.py`（修改）

### 后续可扩展
- 将 background_queue 替换为 Redis (RQ) 或 Celery，只需替换 `_background_queue.put/get` 和 worker 逻辑
- 在更多端点中逐步将写操作迁移到 async/background 通道
- 增加 DB channel 的 Prometheus / Grafana 监控指标

## 2026-06-08：智能辅导页面 UI 改进 — 输入框边界优化 + RAG 开关移入输入区

### 变更内容
1. **增强聊天输入框边界清晰度**：
   - `.chat-composer` 增加 2px 实线边框（surface-300），focus-within 时变为主色（primary-400）并增加发光阴影
   - 增加浅灰背景（surface-50）、圆角（14px）和内边距，使输入区域视觉上独立于聊天消息区

2. **RAG 知识库开关从头部移至输入区域**：
   - 移除聊天头部（chat-header）中的 `knowledge-base-switch` 区域
   - 在 `composer-line` 中新增 `composer-footer` 栏，左侧放置知识库开关（kb-switch），右侧保留发送/停止按钮
   - 布局：textarea 在上方占满宽度，底部 footer 行用 space-between 排列开关和按钮

### 影响范围
- `frontend/src/views/TutorView.vue` — 修改 template 布局和 CSS 样式

## 2026-06-08：RAG 链路优化 + 智能辅导知识库模式切换

### 变更内容
1. **新增 `rag_config.py` 策略配置模块**：
   - `detectResourceType()`：通过关键词规则识别 10 种资源类型（normal_chat/explanation_doc/mindmap/question_bank/extended_reading/practical_case/teaching_video/ppt_generation/assessment/tutoring）
   - `shouldUseRAG()`：根据 knowledgeBaseMode（auto/on/off）和资源类型判断是否使用 RAG
   - `getRagMode()`：返回 none/light/standard/deep 四级 RAG 模式
   - `getRagPolicy()`：返回每种资源类型的完整 RAG 策略（topK/candidateK/rerank/timeoutMs）
   - `RAG_POLICIES` 配置字典：deep/standard/light/none 四级配置
   - `ragCacheGet/Set/Clear`：简易内存缓存，TTL 可配置
   - `RagTimingLogger`：结构化计时日志记录
   - 全局开关（默认关闭）：ENABLE_RAG_OPTIMIZATION、ENABLE_RAG_CACHE、ENABLE_RAG_TIMING_LOG

2. **修改 `rag_store.py` 支持 RAG 模式分级**：
   - `hybrid_query_chunks()` 增加 `mode` 和 `timeout_ms` 参数
   - light 模式：仅关键词检索，跳过 FAISS
   - standard 模式：FAISS 优先，关键词回退（保持原有逻辑）
   - deep 模式：FAISS + 关键词评分融合，提高覆盖率
   - 超时包装（ThreadPoolExecutor），超时返回空结果
   - 集成缓存和计时日志

3. **修改 `study_agent.py` 注入 RAG 上下文**：
   - `__init__` 增加可选 `user_id` 参数
   - 新增 `_retrieve_context()` 方法，根据资源类型检索知识库
   - `_generate_document_outline()`、`_generate_chapter_content()`、`_generate_reading_outline()`、`_generate_reading_section()`、`_generate_single_question()`、`generate_coding_case_question()` 均在 prompt 末尾注入知识库材料

4. **修改 `learning.py` 路由**：
   - `retrieve_knowledge_context()` 增加 `mode` 和 `timeout_ms` 参数
   - `ask_tutor()` 读取 `knowledge_base_mode` 请求字段（auto/on/off）
   - 使用 detectResourceType + shouldUseRAG + getRagMode 决策 RAG 策略
   - 记录完整 timing log（含 knowledgeBaseMode、ragDecisionReason）
   - 所有 `StudyResourceAgent(profile.to_dict())` 调用增加 `user_id=profile.user_id`

5. **修改 `TutorView.vue` 前端**：
   - 聊天头部增加知识库模式切换 `el-radio-group`（自动/开启/关闭）
   - 新增 `knowledgeBaseMode` 响应式状态，默认 "auto"
   - 发送请求时携带 `knowledge_base_mode` 字段

### 影响范围
- `backend/app/services/rag_config.py`：新建
- `backend/app/services/rag_store.py`：hybrid_query_chunks 增加 mode/timeout 参数
- `backend/app/services/study_agent.py`：增加 user_id 参数、_retrieve_context 方法、RAG 上下文注入
- `backend/app/routes/learning.py`：retrieve_knowledge_context 增加参数、ask_tutor 集成 RAG 决策
- `frontend/src/views/TutorView.vue`：增加知识库模式切换 UI 和传参
- `improvement.md`：本次记录

### 如何使用
在后端 `.env` 中设置：
```
ENABLE_RAG_OPTIMIZATION=true
ENABLE_RAG_CACHE=true
ENABLE_RAG_TIMING_LOG=true
```

### 验收标准
1. 智能辅导页面支持 knowledgeBaseMode 切换，默认 "auto"
2. off 模式完全跳过 RAG，不检索知识库、不返回 citations
3. on 模式强制尝试 RAG，AI 回答优先基于知识库
4. auto 模式根据资源类型和消息内容智能判断
5. 资源生成（讲解文档、题库等）在开启优化后注入知识库上下文
6. timing log 包含 rag_mode、used_rag、knowledgeBaseMode、ragDecisionReason

## 2026-06-08：生成学习路径时后台自动生成 5 类个性化资源

### 变更内容
1. **后端 plan_path 路由自动生成资源**：
   - 生成学习路径后，自动调用 `StudyResourceAgent.generate_resource()` 分别生成 course_document、mind_map、exercise_bank、extension_reading、coding_case 共 5 类资源
   - 使用 `LocalStudyGenerator` 作为 LLM 不可用时的本地兜底
   - 生成的资源保存到数据库，随路径响应一起返回前端

2. **前端 PathView 接收并提示**：
   - `planPath()` 成功后读取 `data.resources` 长度
   - 显示"学习路径已生成，后台自动生成 X 类个性化资源"的提示

### 影响范围
- `backend/app/routes/learning.py`：plan_path 路由新增资源生成逻辑
- `frontend/src/views/PathView.vue`：planPath 函数新增资源计数和提示

## 2026-06-08：B站 Cookie 支持 .env 配置 + 前端输入优先

### 变更内容
1. **search_bili.py 从环境变量读取 Cookie**：
   - 新增 `os.getenv("BILI_COOKIE", hardcoded_fallback)`，可在 `.env` 文件中设置 `BILI_COOKIE`
   - 硬编码值作为兜底，`.env` 中设置的 Cookie 会覆盖硬编码值
   - 所有内部函数和公开函数新增 `cookie` 可选参数，由调用方决定是否传入

2. **搜索 API 支持前端传入 Cookie**：
   - `POST /api/resources/search-bili` 接受 `cookie` 字段
   - 前端用户输入的 Cookie 会传到后端并优先使用

### 影响范围
- `backend/app/services/search_bili.py`：新增 `_build_headers()`、`os.getenv` 读取、所有函数增加 `cookie` 参数
- `backend/app/routes/learning.py`：搜索路由接受 `cookie` 字段
- `frontend/src/api/learning.ts` / `learning.js`：`searchBiliVideo` 增加 `cookie` 参数
- `frontend/src/views/ResourcesView.vue`：调用搜索时传入 `biliCookie`

### 如何使用
在后端 `backend/.env` 中添加：
```
BILI_COOKIE=你的B站完整Cookie字符串
```

## 2026-06-08：教学视频新增 B站搜索/播放模式

### 变更内容
1. **新增后端 B站视频搜索 API**：
   - `POST /api/resources/search-bili` — 接收关键词，调用 `search_bili_video_simple` 返回视频列表
   - 支持 JWT 鉴权，返回标准 JSON 结构

2. **教学视频切换搜索/生成模式**：
   - 新增 `el-segmented` 切换组件，在"搜索"和"生成"模式间切换
   - 搜索模式：B站 Cookie 输入框（可选）、关键词搜索、结果以 iframe 内嵌播放
   - 生成模式：保持原有视频生成逻辑不变
   - 每个搜索结果卡片展示标题、iframe 播放器、播放量/时长/UP主信息

### 影响范围
- `backend/app/routes/learning.py`：新增 `search_bili_video` 路由，导入 `search_bili_video_simple`
- `frontend/src/api/learning.ts`：新增 `searchBiliVideo` 方法
- `frontend/src/views/ResourcesView.vue`：新增搜索模式模板、状态变量、搜索函数、CSS 样式

## 2026-06-07：全局字号微调（11px→12px→13px→14px）

### 变更内容
1. **统一提升 `.vue` 文件 `<style scoped>` 中的字号**：
   - `font-size: 11px` → `font-size: 12px`（极小标签、辅助文本）
   - `font-size: 12px` → `font-size: 13px`（标签、描述、次要文本）
   - `font-size: 13px` → `font-size: 14px`（正文、表单标签、条目文本）
   - 原有 `14px` 保持不变
   - 仅修改 `<style scoped>` 内部，不触及模板内联样式

### 影响范围
- `frontend/src/views/DashboardView.vue`
- `frontend/src/views/KnowledgeView.vue`
- `frontend/src/views/PathView.vue`
- `frontend/src/views/ProfileView.vue`
- `frontend/src/views/QuizView.vue`
- `frontend/src/views/ResourcesView.vue`
- `frontend/src/views/TutorView.vue`
- `frontend/src/components/MindMapViewer.vue`
- `frontend/src/components/MultiAgentDebatePanel.vue`
- `frontend/src/components/PathReplanPanel.vue`
- `frontend/src/components/ProfileEvolutionTimeline.vue`
- `frontend/src/components/PptWorkbench.vue`
- `frontend/src/components/ResourceQualityCard.vue`
- `frontend/src/components/TrustReport.vue`

## 2026-06-06：智能辅导输出改为结构化 JSON（消除配图标记混入用户文本）

### 变更内容
1. **新增 JSON 流式提取函数**：
   - `_extract_answer_from_json(text)`：状态机解析流式 JSON 中的 `answer` 字段，支持转义字符和跨 chunk 边界
   - `_stream_json_answer(stream_gen, guard, rag_context, refusal_keywords)`：包装流式生成器，实时产出 `answer` 事件和最终的 `image_prompt_raw` 事件

2. **修改两处流式生成路径的 system prompt**：
   - 多模态路径（MultimodalTutorAgent）：`【图像生成能力】` 标记改为 JSON 格式要求
   - 纯文本路径（`generate_text_only`）：`【配图：...】` 标记改为 JSON 格式要求
   - 两处 prompt 均要求模型返回 `{"answer": "...", "image_prompt": "..."}` 结构

3. **修改两处流式循环**：
   - 移除 `re.findall(r'【配图：(.*?)】', chunk)` 和 `re.sub(r'【配图：(.*?)】', '', chunk)` 正则提取逻辑
   - 改用 `_stream_json_answer()` 统一处理，`answer` 增量实时推送到前端，`image_prompt_raw` 在流结束后用于触发图片生成

### 影响范围
- `backend/app/routes/learning.py`：新增 `_extract_answer_from_json`、`_stream_json_answer`，修改两处 system prompt 和流式处理循环
- 前端无需改动（SSE 的 `answer` / `image` 事件格式保持不变）

## 2026-06-06：修复今日推荐任务无法完成的问题

### 变更内容
1. **修复 `continue_path` 永远无法完成的问题**：
   - 后端完成条件从硬编码 `False` 改为 `latest_path is not None`（有学习路径即视为已继续）

2. **修复 `retake_assessment` 完成条件过于严格的问题**：
   - 原条件：`latest_score >= 60`（要求重新测评分数 ≥60 才能完成）
   - 新条件：`len(recent_results) >= 2`（只要有 ≥2 次测评提交记录即表明已重新做卷）

3. **修复 `review_wrong_questions` 完成条件不合理的问题**：
   - 原条件：`not wrong_questions_set`（要求错题数为 0 才能完成）
   - 新条件：`len(recent_results) >= 2`（只要有 ≥2 次测评提交记录即表明已查看解析）

### 影响范围
- `backend/app/routes/learning.py`：修改 `recommended_tasks()` 中的 `completion` 字典

## 2026-06-06：测评成绩按答卷顺序排列

### 变更内容
1. **修复测评成绩排序问题**：
   - 练习题库提交时（`submit_structured_quiz`），若使用已有 `record_id`（先存草稿后提交），`created_at` 更新为提交时间
   - 确保历次测评成绩按"做卷顺序"而非"生成题目顺序"排列

### 影响范围
- `backend/app/routes/learning.py`：新增 `from datetime import datetime`，提交时更新 `created_at`

## 2026-06-06：移除测评页面重复的路径重规划面板

### 变更内容
1. **测评评估页面（QuizView.vue）**：
   - 移除 `PathReplanPanel`（测评驱动路径重规划 / 学习路径动态调整建议）
   - 学习路径页面已显示此面板，测评页面重复展示属于冗余

### 影响范围
- `frontend/src/views/QuizView.vue`：移除模板、导入和样式

## 2026-06-06：Agent 真实评估接入

### 变更内容
1. **新增 `ResourceEvaluationAgent`**：
   - 新建后端 Agent 类，通过 LLM 对生成的资源/题库/案例进行多维度质量评估
   - 三个评估方法：`evaluate_resource()`、`evaluate_quiz()`、`evaluate_coding()`
   - 继承 `BaseAgent.chat()`，通义千问 LLM 驱动，返回结构化 JSON（评分、Agent 意见、共识文本）

2. **新增后端评估 API**：
   - `POST /api/resources/evaluate` — 接收评估类型和数据，返回评估结果
   - 由环境变量 `ENABLE_AGENT_EVALUATION` 控制开关（默认 `true`）
   - 开关关闭或 LLM 不可用时返回空，前端自动 fallback 到启发式计算

3. **前端改造**：
   - 新增 `enableAgentEvaluation` 开关（默认 `true`）
   - 三个面板的数据源优先使用后端真实评估结果，不可用时回退到原有前端计算
   - 通过 watcher 监听资源/题库/案例数据变化自动触发评估

### 影响范围
- `backend/app/services/agents/resource_evaluation_agent.py`：新增
- `backend/app/services/agents/__init__.py`：注册导出
- `backend/app/routes/learning.py`：新增评估路由和开关
- `frontend/src/api/learning.ts`：新增 `evaluateResource` 方法
- `frontend/src/views/ResourcesView.vue`：新增评估状态、触发函数、watcher、条件渲染

## 2026-06-04：UI 布局优化

### 变更内容
1. **学习路径页面（PathView.vue）**：
   - 画像迷你卡片从 2×2 网格布局改为 1×4 行布局（`profile-mini-grid` 改为 `flex-direction: row`）
   - 学习路径内容改为抽屉（Drawer）形式展示，页面仅显示入口卡片，点击后从右侧滑出抽屉
   - 生成路径后自动打开抽屉

2. **知识库管理页面（KnowledgeView.vue）**：
   - 刷新按钮添加独立旋转动画，点击后 Refresh 图标旋转 0.6s
   - 新增 `refreshing` 状态变量，与 `loading` 分离，避免与其他操作冲突

3. **智能辅导页面（TutorView.vue）**：
   - 用户消息最大宽度从 70% 增大至 85%，对话区域更宽阔

### 影响范围
- `frontend/src/views/PathView.vue`：布局修改、新增抽屉组件和样式
- `frontend/src/views/KnowledgeView.vue`：新增刷新状态和旋转动画样式
- `frontend/src/views/TutorView.vue`：调整消息宽度样式

## 2026-06-06：今日推荐任务改为行为触发 + 每日重置

### 变更内容
1. **新增 `TaskActionLog` 模型**：
   - 新建 `task_action_logs` 表，记录用户页面访问行为（visit_path、visit_quiz、visit_resources）
   - 同一天同一用户同一 action 只记录一次（幂等）

2. **新增后端 API**：
   - `POST /api/tasks/log-action` — 前端页面 mount 时调用，记录用户行为

3. **所有任务完成条件统一为"今日是否访问对应页面"**：
   - 访问资源页面（`visit_resources`）→ 完成：`review_weak_points`、`build_foundation`、`generate_resources`、`generate_ppt_deck`
   - 访问测评页面（`visit_quiz`）→ 完成：`take_first_assessment`、`retake_assessment`、`review_wrong_questions`
   - 访问学习路径页面（`visit_path`）→ 完成：`continue_path`、`plan_learning_path`
   - 所有任务每日 0 点 (UTC) 自动重置，不再依赖数据存在性判定

4. **前端恢复为仅跳转 + 页面触发**：
   - `clickTask()` 恢复为仅跳转，不再手动标记完成
   - `PathView.vue` mount 时调用 `api.logTaskAction('visit_path')`
   - `QuizView.vue` mount 时调用 `api.logTaskAction('visit_quiz')`
   - `ResourcesView.vue` mount 时调用 `api.logTaskAction('visit_resources')`

### 影响范围
- `backend/app/models.py`：新增 `TaskActionLog` 模型
- `backend/app/routes/learning.py`：新增 `POST /api/tasks/log-action`、修改 `recommended_tasks()` 完成条件
- `frontend/src/api/learning.ts`：新增 `logTaskAction` 方法
- `frontend/src/views/DashboardView.vue`：删除手动标记代码，缓存改为每日 TTL
- `frontend/src/views/PathView.vue`：mount 时记录 visit_path
- `frontend/src/views/QuizView.vue`：mount 时记录 visit_quiz
- `frontend/src/views/ResourcesView.vue`：mount 时记录 visit_resources

## 2026-06-06：修复 v-show 导致页面组件提前挂载的问题

### 变更内容
1. **App.vue 中所有页面级组件从 `v-show` 改为 `v-if`**：
   - `v-show` 会在应用启动时立即渲染所有组件（仅 CSS 隐藏），导致三个页面的 `onMounted` 同时触发
   - 三条 `api.logTaskAction()` 在用户未实际访问页面时就被写入数据库
   - 改为 `v-if` 后，组件仅在用户点击对应菜单导航时才挂载，`onMounted` 中的 log 行为才触发

### 影响范围
- `frontend/src/App.vue`：所有 `<section v-show="activeMenu ===...">` 改为 `v-if`

## 2026-06-06：任务完成条件改为动态匹配（覆盖所有资源子类型）

### 变更内容
1. **`POST /api/tasks/log-action` 支持 `sub_type` 参数**：
   - `visit_resources` + `course_document` → 存储为 `visit_resources_course_document`
   - 支持按资源子类型精确判定

2. **完成条件改为动态计算**：
   - 不再使用硬编码的 completion 字典，改为遍历任务列表，根据每个任务的 `action` 字段自动匹配
   - 资源任务（`action` 以 `resources_` 开头）→ 提取子类型，检查 `visit_resources_{subtype}`
   - 7 种子类型全自动覆盖：course_document、mind_map、exercise_bank、extension_reading、coding_case、multimedia_video、ppt_deck
   - 测评任务（`action == "quiz"`）→ 检查 `visit_quiz`
   - 路径任务（`action == "path"`）→ 检查 `visit_path`
   - 通用资源跳转（`action == "resources"`）→ 任一子类型即可

3. **ResourcesView 切换子类型时也触发记录**：
   - mount 时带当前子类型调用 `logTaskAction`
   - 切换子类型 tab 时（`watch(selectedResourceType)`）也调用

### 影响范围
- `backend/app/routes/learning.py`：端点支持 sub_type，完成条件改为动态计算
- `frontend/src/api/learning.ts`：`logTaskAction` 接受可选的 `subType`
- `frontend/src/views/ResourcesView.vue`：mount 和切换子类型时传入 sub_type

## 2026-06-08：智能辅导新增配图开关 + UI 视觉增强

### 变更内容
1. **前端新增配图开关**：
   - 在聊天输入区 footer 知识库开关旁新增 `el-switch` 配图开关（默认开启）
   - 开关关闭时，请求携带 `image_gen_enabled: false`
   - 开关状态独立存储，与知识库模式互不影响

2. **后端 `ask_tutor()` 新增 `image_gen_enabled` 参数，关闭时 LLM 也不生成 image_prompt**：
   - 请求解析时读取 `image_gen_enabled`（默认 `True`）
   - 流式路径：`image_prompt_raw` 处理前增加 `and image_gen_enabled` 条件
   - 非流式路径：文生图检测前增加 `and image_gen_enabled` 条件
   - **关键改进**：配图关闭时，LLM 的 system prompt 中移除 `image_prompt` 字段要求，JSON 格式简化为 `{"answer": "..."}`，避免 LLM 浪费 token 生成无用的图片描述

3. **UI 视觉增强**：
   - "停止生成"按钮文字改为红色（`var(--danger, #ef4444)`）加粗，更醒目
   - 配图开关开启时文字高亮为主色（`var(--primary-500)`）加粗，关闭时保持中等权重灰色，视觉更清晰

### 影响范围
- `backend/app/routes/learning.py`：ask_tutor() 中两处 system prompt 根据 `image_gen_enabled` 条件构建 JSON 格式指令
- `frontend/src/views/TutorView.vue`：新增 `enableImageGen` ref、`img-switch` UI、CSS（停止按钮红色 + 开关文字样式）、请求参数 `image_gen_enabled`
- `improvement.md`：本次记录

### 验收标准
1. 配图开关默认开启，行为与之前一致
2. 关闭配图开关后，发送问题不会触发文生图调用，回答中不显示配图
3. 开关不影响知识库模式和回答内容本身，仅控制是否配图

## 2026-06-08：修复每日任务确定性选取与刷新完成状态保留

### 变更内容
1. **后端 `recommended_tasks()` 使用日期种子确保全天任务一致**：
   - 新增 `rng = random.Random(str(today))`，用当天日期字符串作为种子
   - `random.randint(3, 5)` → 固定 `target = 5`，每天始终选取 5 个任务
   - `random.sample()` / `random.shuffle()` / `random.choice()` → 全部改用 `rng.*()` 版本
   - 同一个用户在同一天内每次刷新看到的任务组合完全相同，解决"只有显示的每日任务才能被完成，没有显示的每日任务则不做记录"的 Bug

2. **前端 `refreshTasks()` 不再清空完成记录**：
   - 移除 `api.resetTasks()` 调用（不再删除数据库中的 TaskActionLog）
   - 移除 `clearTasksCache()` 调用（保留缓存作为 fallback）
   - 刷新时仅重新请求服务端数据，不破坏已有完成状态

3. **`POST /api/tasks/reset` 端点保留**：登录时仍然调用以清空跨日完成记录

### 影响范围
- `backend/app/routes/learning.py`：recommended_tasks() 使用日期种子的 rng 对象
- `frontend/src/views/DashboardView.vue`：refreshTasks() 简化，无 reset/clear
- `frontend/src/views/DashboardView.vue.js`：同步更新编译版本
- `improvement.md`：本次记录

### 验收标准
1. 多次刷新页面，任务列表保持不变（不再出现"今日已完成的某任务下次刷新消失"的 Bug）
2. 访问对应页面后，任务自动勾选为完成，刷新后已完成任务保持勾选
3. 不同日期登录，看到不同的任务组合（日期种子变化）

## 2026-06-09：测评评估三份报告持久化到 QuizResult

### 变更内容
1. **后端 `POST /api/resources/evaluate` 新增持久化逻辑**：
   - 请求体新增可选参数 `record_id`
   - **缓存优先**：传了 `record_id` 且 `eval_type == "quiz"` 时，先查询 `QuizResult.answers.innovation_evaluation`，有缓存直接返回，不再调用 LLM
   - **生成后保存**：多智能体评估完成后，将结果写入 `QuizResult.answers["innovation_evaluation"]` 并 commit
   - 资源（resource）和编码（coding）类型评估不变，不参与持久化

2. **前端 `runPostSubmitAnalysis()` 传递 `record_id`**：
   - 调用 `api.evaluateResource()` 时传入 `record_id: selectedQuizRecord.value?.id`
   - 后端据此关联到对应的 `QuizResult` 记录

3. **历史记录查看时恢复多智能体评估数据**：
   - `selectQuizHistory()` 在构建 `quizResult` 时新增 `innovation_evaluation: payload.innovation_evaluation || null`
   - `QuizView.vue` 新增 `watch(selectedQuizRecord)`，检测到 `quizResult.innovation_evaluation` 时自动设置 `quizInnovation`，历史记录中也能看到多智能体协商式生成、Trust-RAG 可信生成、资源质量自动评价三份报告

4. **TypeScript 类型更新**：
   - `api/learning.ts` 中 `evaluateResource` 参数新增 `record_id?: number | string`

### 影响范围
- `backend/app/routes/learning.py`：evaluate_resource() 新增 record_id 参数、缓存读取、结果持久化
- `frontend/src/views/QuizView.vue`：runPostSubmitAnalysis() 传 record_id；新增 watch(selectedQuizRecord) 恢复创新数据
- `frontend/src/composables/useQuiz.ts`：selectQuizHistory() 新增 innovation_evaluation
- `frontend/src/composables/useQuiz.js`：同步更新
- `frontend/src/api/learning.ts`：evaluateResource 类型增加 record_id
- `frontend/src/views/QuizView.vue.js`：同步更新 evaluateResource 传参
- `improvement.md`：本次记录

### 验收标准
1. 完成测评后，多智能体协商式生成、Trust-RAG 可信生成、资源质量自动评价三份报告生成完成并自动保存
2. 刷新 Quiz 页面或重新进入，查看历史测评记录，三份报告依然可见（不再需要重新生成）
3. 不传 record_id 时（如资源评估），行为与之前完全一致，不受影响

## 2026-06-09：修复创新评估持久化与历史记录显示

### 变更内容
1. **后端 `evaluate_resource()` 修复 SQLAlchemy 变更检测**：
   - 原代码 `answers = record.answers or {}` 获取的是同一 dict 引用，原地修改后 `record.answers = answers` 赋回同一对象，SQLAlchemy 无法检测到变更，数据实际未写入数据库
   - 改为 `new_answers = dict(record.answers or {})` 创建新 dict，确保 SQLAlchemy 检测到属性变更并正确 commit

2. **前端 `shouldShowTrustEvaluation` 放宽显示条件**：
   - 移除 `quizResult.value.evaluation` 要求（旧记录可能没有保存 evaluation 文本）
   - 只要 `quizResult` 存在且 `quizInnovation` 有值即可展示三份创新报告

### 影响范围
- `backend/app/routes/learning.py`：evaluate_resource() 持久化改用新 dict
- `frontend/src/views/QuizView.vue`：shouldShowTrustEvaluation 移除 evaluation 依赖
- `frontend/src/views/QuizView.vue.js`：同步更新
- `improvement.md`：本次记录

### 验收标准
1. 新完成的测评，三份报告在历史记录中可正常查看
2. 已有旧记录（即使没有 evaluation 文本），只要 answers 中包含 innovation_evaluation，也能显示三份报告
3. 刷新页面后查看历史记录，报告数据完整显示（不缺失 agents、trustScore 等字段）

## 2026-06-09：进度条不再计时器驱动完成，等待后端数据

### 变更内容
1. **QuizView.vue `animateQuizGenSteps()`**：移除步骤 3（内容审核）的 7800ms 自动完成计时器，保持 `running` 状态直到后端数据返回
2. **QuizView.vue `waitForQuizGenStepsComplete()`**：不再计算剩余时间等待，直接调用 `finishQuizGenSteps()` 立即完成
3. **ResourcesView.vue `animateAgentSteps()`**：同样移除步骤 3（内容审核）的 7800ms 自动完成计时器
4. **ResourcesView.vue `waitForAgentStepsComplete()`**：同样直接完成，不再等待剩余时间
5. **PathView.vue 已正确**：之前已实现步骤 3 等待后端数据的模式，无需修改
6. 移除不再使用的 `QUIZ_GEN_PROGRESS_DURATION` 和 `AGENT_PROGRESS_DURATION` 常量

### 影响范围
- `frontend/src/views/QuizView.vue`：animate/waitFor 改写，移除 QUIZ_GEN_PROGRESS_DURATION
- `frontend/src/views/QuizView.vue.js`：同步更新
- `frontend/src/views/ResourcesView.vue`：animate/waitFor 改写，移除 AGENT_PROGRESS_DURATION
- `frontend/src/views/ResourcesView.vue.js`：同步更新
- `improvement.md`：本次记录

### 验收标准
1. 点击生成测评/资源/学习路径，进度条依次显示前 3 步，第 4 步（内容审核）保持运行中动画
2. 后端返回数据后，进度条立即显示"生成完成"
3. 如果后端超时或报错，进度条停止在"内容审核"步骤，不会错误地显示完成

## 2026-06-09：填空题/简答题改用 LLM 语义判分

### 变更内容
1. **`StudyResourceAgent` 新增 `judge_open_answer()` 方法**：
   - 将题目、参考答案、学生答案和解析发给 LLM，由 LLM 判断语义正确性
   - 返回 `1.0`（完全正确）/ `0.5`（部分正确）/ `0.0`（错误）/ `None`（LLM 不可用时降级）
   - 遵循现有 Agent 的 JSON 输出模式：`self._chat()` + `self._extract_json()`

2. **`LocalStudyGenerator._score_answer()` 新增 `llm_judge` 参数**：
   - `grade_structured_quiz()` 和 `_score_answer()` 均可选接受 `llm_judge` 回调
   - 填空题（`fill_blank`）优先走 LLM 判分，LLM 返回 `None` 时回退到子串匹配
   - 简答题（`short_answer`）优先走 LLM 判分，LLM 返回 `None` 时回退到字符长度估算
   - 选择题/判断题保持原有精确匹配逻辑，不受影响

3. **`/quiz/submit-structured` 路由创建 Agent 并传入 `llm_judge`**：
   - 创建 `StudyResourceAgent` 实例，将 `judge_open_answer` 方法包装为回调传入

4. **实操案例判分保持不变**：
   - `StudyResourceAgent.grade_coding_case()` 已通过 LLM 判分，无需修改
   - 本地回退关键词匹配作为降级保留

### 影响范围
- `backend/app/services/study_agent.py`：新增 `judge_open_answer()` 方法
- `backend/app/services/local_generator.py`：`grade_structured_quiz()` 和 `_score_answer()` 新增 `llm_judge` 参数
- `backend/app/routes/learning.py`：`submit_structured_quiz()` 创建 Agent 并传入回调
- `improvement.md`：本次记录

### 验收标准
1. 填空题答"1"（参考答案含链式法则表达式），LLM 判为错误，不再误判为正确
2. 简答题答"我不知道啊啊啊啊啊"（超 12 字但内容无关），LLM 判为错误
3. 正确答案（语义一致）判为完全正确（1.0），相近但不完整的判部分正确（0.5）
4. 选择题/判断题判分行为不变
5. LLM 不可用时自动降级到本地判分逻辑

## 2026-06-09：知识库删除文档优化——独立删除状态 + 前端优先移除

### 变更内容
1. **新增独立 `deleting` 状态**：
   - 新增 `const deleting = ref(false)`，与 `loading` 分离
   - 删除文档时不再使用 `loading`（上传按钮的 `:loading="loading"` 不再受影响）
   - 上传按钮保持正常状态，不会在删除时显示"上传中"旋转

2. **前端优先移除（optimistic removal）**：
   - 确认删除后立即从本地 `documents` 数组中移除目标文档（`splice`）
   - 后端 API 成功后直接提示成功，不再调用 `loadDocuments()` 重新拉取
   - 后端 API 失败时恢复被移除的文档到原位置（`splice(index, 0, deletedDoc)`）
   - 用户取消删除时无声退出

### 影响范围
- `frontend/src/views/KnowledgeView.vue`：新增 deleting ref、deleteKnowledgeDocument 重写为乐观移除
- `frontend/src/views/KnowledgeView.vue.js`：同步更新编译版本
- `improvement.md`：本次记录

### 验收标准
1. 点击删除文档，"上传文本资料"按钮不显示上传中旋转动画
2. 点击确定后文档立即从表格中消失，体验流畅
3. 若后端删除失败（网络错误等），文档自动恢复到原位置并提示错误原因
4. 用户取消删除对话框，表格无变化，无错误提示

## 2026-06-09：学习路径配套资源生成改为 ThreadPoolExecutor 并行

### 变更内容
1. **`rag_config.py` 新增 `ENABLE_PARALLEL_RESOURCE_GEN` 开关**：
   - 默认 `true`（`.env` 可设 `ENABLE_PARALLEL_RESOURCE_GEN=false` 关闭）
   - 与其他 RAG 开关放在同一全局开关区

2. **`_generate_path_resources_in_background()` 重写为线程池并行**：
   - 提取 `_generate_one(rtype)` 内部函数，每个资源类型在独立 `app.app_context()` 中执行
   - 并行模式：`ThreadPoolExecutor(max_workers=5)` 一次性提交 5 类资源生成任务
   - 串行回退模式：开关关闭时依次逐个生成
   - 每个线程独立处理 `db.session`，完成后调用 `db.session.remove()` 避免 session 泄漏
   - 生成结构包含各自的 `StudyResourceAgent` + `LocalStudyGenerator` + `ContentGuard`

### 影响范围
- `backend/app/services/rag_config.py`：新增 ENABLE_PARALLEL_RESOURCE_GEN 开关
- `backend/app/routes/learning.py`：_generate_path_resources_in_background 重写

### 验收标准
1. 生成学习路径后，5 类资源（讲解文档、思维导图、练习题库、拓展阅读、实操案例）在后台并发生成
2. 总等待时间从 5 次串行 LLM 调用（约 50-150 秒）缩短为单次最长 LLM 调用时间（约 10-30 秒）
3. 开关关闭时回退到原有串行行为，功能不变
4. 任一资源生成失败不影响其他资源（失败的类型跳过，其余正常入库）

## 2026-06-09：学习路径页面显示 5 类资源后台生成进度

### 变更内容
1. **后端新增 `GET /api/resources/auto-status` 端点**：
   - 接收 `since` 参数（ISO 时间戳），检查当前用户 5 类资源是否已生成
   - 返回每类资源的状态（completed/generating）和总体完成标志
   - 无需新增 DB 字段或 schema 变更，直接查询 Resource 表

2. **前端 API 新增 `getAutoResourceStatus()`**：
   - `learning.ts` 和 `learning.js` 同步新增此方法

3. **PathView 新增资源生成进度显示区域**：
   - 学习路径生成后，在路径内容下方显示"正在自动生成配套资源"进度区
   - 5 个资源（讲解文档、思维导图、练习题库、拓展阅读、实操案例）初始为"generating"状态（旋转图标）
   - 每 2 秒轮询后端状态，完成后变为勾选图标，文字变绿
   - 全部完成后自动停止轮询，显示完成提示
   - 刷新页面后进度区不显示（资源已在 DB 中）

### 影响范围
- `backend/app/routes/learning.py`：新增 auto_resource_generation_status 端点
- `frontend/src/api/learning.ts`：新增 getAutoResourceStatus 方法
- `frontend/src/api/learning.js`：同步新增
- `frontend/src/views/PathView.vue`：新增进度区模板 + reactive 状态 + 轮询逻辑 + CSS
- `frontend/src/views/PathView.vue.js`：同步更新编译版本 + VLS 注解
- `improvement.md`：本次记录

### 验收标准
1. 点击生成学习路径，路径内容显示后下方出现进度区，5 个资源显示"generating"旋转图标
2. 后台每完成一个资源，对应步骤变为"completed"勾选图标
3. 全部 5 类资源完成后自动停止轮询，提示"5类个性化资源已全部自动生成"
4. 刷新页面后进度区不显示，资源可在 ResourcesView 中查看

## 2026-06-09：资源生成速度优化（6 项并行/缓存/RAG 优化）

### 变更内容
1. **开启 RAG 缓存（`rag_config.py`）**：
   - `ENABLE_RAG_CACHE` 默认值从 `"false"` 改为 `"true"`
   - 同一用户对相同查询的 RAG 结果在 5 分钟内直接返回缓存，避免重复 API 调用
   - 影响：文档大纲/章节/阅读材料生成中每次 RAG 检索都受益

2. **RAG 移出重试循环（`study_agent.py`）**：
   - `_generate_section_with_retry()`、`_generate_chapter_content()`、`_generate_reading_section()` 增加可选 `rag_context` 参数
   - 提供 `rag_context` 时跳过内部 `_retrieve_context()` 调用，避免重试时重复检索
   - `_generate_document()` 和 `_generate_reading()` 在并行章节循环前预检索一次 RAG，所有章节共享同一份知识库上下文
   - 影响：讲解文档/拓展阅读的章节生成 RAG 调用从 N 次降为 1 次（N=章节数）

3. **同步 `/resources/generate` 端点并行化（`learning.py`）**：
   - 顺序 for 循环改为 `ThreadPoolExecutor(max_workers=5)` 并行生成
   - 每个线程在独立 `app.app_context()` 中执行，独立处理 `db.session`
   - 结果按原始 `selected_types` 顺序排列，保持响应格式不变
   - 影响：批量生成 5 类资源时总耗时从 5 次串行 LLM 调用缩短为单次最长 LLM 调用时间

4. **Orchestrator Agent 注入 RAG（`resource_agent.py`）**：
   - `BaseAgent` 新增 `_retrieve_context()` 方法，供所有子 Agent 使用
   - `CourseDocumentAgent._generate_outline()` 和 `_generate_chapter()` 注入 RAG 上下文
   - `ExtensionReadingAgent._generate_outline()` 和 `_generate_section()` 注入 RAG 上下文
   - `CourseDocumentAgent.generate()` 和 `ExtensionReadingAgent.generate()` 在并行章节循环前预检索一次 RAG
   - 影响：SSE 流式路径（course_document、extension_reading）也获得 RAG 注入，与同步路径质量一致

5. **修复死代码（`study_agent.py`）**：
   - 移除 `generate_resource()` 中 `course_document` 和 `extension_reading` 的不可达分支（已被 Orchestrator 在 148-151 行提前拦截）

### 影响范围
- `backend/app/services/rag_config.py`：ENABLE_RAG_CACHE 默认开启
- `backend/app/services/study_agent.py`：RAG 移出重试循环、死代码删除
- `backend/app/services/agents/base_agent.py`：新增 _retrieve_context() 方法
- `backend/app/services/agents/resource_agent.py`：CourseDocumentAgent 和 ExtensionReadingAgent 注入 RAG
- `backend/app/routes/learning.py`：同步 generate 端点并行化
- `improvement.md`：本次记录

### 验收标准
1. RAG 缓存开启后，同一主题的第二次生成不再重复检索知识库
2. 讲解文档 8 章节生成只调用 1 次 RAG（原为 8 次），拓展阅读同理
3. 批量生成 5 类资源时，总耗时从串行 50-150 秒缩短到 10-30 秒
4. SSE 流式路径生成的讲解文档/拓展阅读内容包含知识库参考信息
5. 死代码移除后不影响已有功能，所有资源类型正常生成

## 2026-06-09：资源生成异步化 + 前端轮询（非流式类型）

### 变更内容
1. **后端新增异步生成端点**：
   - `POST /api/resources/generate-async` — 非流式资源（mind_map、exercise_bank、coding_case、multimedia_video）后台生成，立即返回 `{"status":"started","started_at":"..."}`
   - `GET /api/resources/generate-async-status` — 前端轮询状态，根据 `type + started_at` 判断是否完成
   - `_generate_single_resource_in_background()` — 后台线程函数，独立 app_context + db.session

2. **前端 API 新增方法**：
   - `learning.ts` / `learning.js` 新增 `generateResourceAsync()`、`getAsyncGenerationStatus()`

3. **前端轮询工具 `useResourceProgress.ts`**：
   - 新增 `pollGenerationStatus()` — 2s 间隔轮询，5 分钟超时，返回 `{stop}` 用于清理

4. **ResourcesView.vue 非流式路径改造**：
   - `generateCurrentResource()` 中 mind_map、multimedia_video 改为异步触发 + 轮询
   - `generateCodingCase()` 和 `handleGenerateExerciseBank()` 同样改造
   - 组件卸载时自动停止轮询，防止内存泄漏

### 影响范围
- `backend/app/routes/learning.py`：新增 2 个端点 + 后台线程函数
- `frontend/src/api/learning.ts`：新增 2 个异步 API 方法
- `frontend/src/api/learning.js`：同步新增
- `frontend/src/composables/useResourceProgress.ts`：新增 pollGenerationStatus
- `frontend/src/views/ResourcesView.vue`：非流式路径异步 + 轮询
- `frontend/src/views/ResourcesView.vue.js`：同步更新
- `improvement.md`：本次记录

### 验收标准
1. 点击生成 mind_map → 进度条立即出现，轮询 2s/次 → 生成完成后进度条结束
2. 流式类型（course_document、extension_reading）保持 SSE 不变
3. 5 分钟超时 → 进度条取消，提示"生成超时，请重试"
4. 切换标签页再回来 → 进度条仍然可见

## 2026-06-09：思维导图布局优化 — JSON 节点数组输出

### 变更内容
1. **后端 `mindmap_sanitizer.py` 新增 `convert_to_layout_json()`**：
   - 将 Mermaid mindmap 文本转换为扁平的 JSON 节点数组，格式：`{id, label, parent, level, children_count}`
   - 根节点 level=0，无父节点；子节点通过 `parent` 字段引用
   - 优化策略：
     - 过长标签自动精简为核心关键词（不超过 24 字）
     - 同一父节点下子节点数控制在 6 个以内，超出的自动降级
     - 确保层级连续（不跳级），布局紧凑
   - 输出格式可直接导入 ai-mindmap.app / DeepSeek 等 mindmap API

2. **后端 `learning.py` 同步和异步端点**：
   - 同步 `/resources/generate`：mind_map 的 artifact 中增加 `layout_json`
   - 异步 `/resources/generate-async-status`：mind_map 资源返回 `artifact.layout_json`

3. **前端 `ResourcesView.vue` 导出按钮**：
   - 思维导图区域由单个"下载 SVG"按钮改为 `.mindmap-actions` 容器含两个按钮："下载 SVG" + "导出 JSON 布局"
   - 新增 `copyLayoutJson()`：clipboard API 复制 JSON，降级到 textarea 选中复制
   - 修复 artifact 管道：轮询回调中提取并设置 `resourceArtifact.value`

### 影响范围
- `backend/app/services/mindmap_sanitizer.py`：新增 convert_to_layout_json()
- `backend/app/routes/learning.py`：同步/异步端点增加 layout_json
- `frontend/src/views/ResourcesView.vue`：双按钮布局 + copyLayoutJson + artifact 管道修复
- `frontend/src/views/ResourcesView.vue.js`：同步更新编译版本 + VLS 注解
- `improvement.md`：本次记录

### 验收标准
1. 生成思维导图后，artifact 中包含 layout_json 字段
2. "导出 JSON 布局"按钮在 layout_json 存在时可点击
3. 点击后复制有效 JSON 到剪贴板（格式符合 `{id, label, parent, level, children_count}`）
4. JSON 可直接导入 ai-mindmap.app 使用

## 2026-06-10：全资源生成计时覆盖（前端本地计时）

### 变更内容
1. **ResourcesView.vue（exercise_bank + coding_case）**：
   - `handleGenerateExerciseBank()` 增加 `generationDuration` 计时，完成后在题库标题旁显示紫色耗时徽章
   - `generateCodingCase()` 增加 `generationDuration` 计时，完成后在案例标题旁显示紫色耗时徽章

2. **PptWorkbench.vue**：
   - 新增 `showTiming` 计算属性检查 `VITE_ENABLE_RESOURCE_TIMING`
   - 生成中进度条的"预计剩余 X 秒"受 `showTiming` 控制显示/隐藏
   - 生成完成后在"PPT 生成完成"横幅旁显示紫色耗时徽章
   - `startPolling()` 完成分支记录 `generationDuration`

3. **PathView.vue**：
   - 新增 `genStartedAt` / `generationDuration` ref、`showTiming` computed、`formatDuration` 函数
   - `planPath()` 成功后在进度条下方显示"路径生成耗时 XX 秒"
   - 新增 `.resource-timing-badge` CSS 样式

4. **QuizView.vue**：
   - 新增 `quizGenerationDuration` ref、`showTiming` computed、`formatDuration` 函数
   - `handleGenerateQuiz()` 成功后在题库标题旁显示"生成耗时 XX 秒"

5. **TutorView.vue**：
   - `ChatMessage` 接口新增可选 `duration` 字段（per-message 计时）
   - `askTutor()`、`regenerateAssistantMessage()`、`continueTutorAnswer()` 均记录回答耗时
   - 已完成助手消息下方显示"回答耗时 XX 秒"徽章

### 影响范围
- `frontend/src/views/ResourcesView.vue`：2 个函数增加计时 + 2 处模板徽章
- `frontend/src/components/PptWorkbench.vue`：showTiming + generationDuration + formatDuration
- `frontend/src/views/PathView.vue`：planPath 计时 + 模板徽章 + CSS
- `frontend/src/views/QuizView.vue`：handleGenerateQuiz 计时 + 模板徽章 + CSS
- `frontend/src/views/TutorView.vue`：ChatMessage.duration + 3 函数计时 + 模板徽章
- `improvement.md`：本次记录

### 验收标准
1. `VITE_ENABLE_RESOURCE_TIMING=true` 时，10 种资源生成完成后均显示对应耗时徽章
2. `VITE_ENABLE_RESOURCE_TIMING=false` 时，所有计时徽章隐藏
3. 所有计时为前端 `Date.now()` 本地计时，不依赖后端
4. 生成失败时不显示计时徽章

## 2026-06-10：进度条实时计时（第二次迭代）

### 变更内容
1. **计时从"生成后徽章"改为"进度条实时计数"**：
   - 生成过程中在进度条区域显示从 0 开始计时的实时读数，每秒更新
   - 生成完成后自动停止，显示最终耗时

2. **4 个视图统一修改**：
   - `ResourcesView.vue`、`PathView.vue`、`QuizView.vue`、`PptWorkbench.vue`：
     - 新增 `liveElapsed` ref、`liveTimerInterval` 变量、`startLiveTimer()`/`stopLiveTimer()` 函数
     - `startLiveTimer()` 在生成开始时调用（`loading.value = true` 后）
     - `stopLiveTimer()` + `liveElapsed` 赋值在生成完成/失败时调用
     - 组件卸载时 `onUnmounted`/`onBeforeUnmount` 中调用 `stopLiveTimer()` 防止泄漏

3. **计时格式统一**：
   - `formatDuration()` 在全部视图中统一为 `Math.floor(seconds)秒` / `${mins}分${secs}秒`（整数秒，无空格）
   - 移除不再使用的 `formatLiveTime()` 函数

4. **智能辅导（TutorView.vue）**：
   - 保持原有回答耗时徽章格式，已验证为 `Math.floor(seconds)秒` / `${mins}分${secs}秒`

5. **进度条 CSS**：
   - 新增 `.live-timer` 样式：紫色字体、淡紫色背景、圆角标签、脉冲呼吸动画

### 影响范围
- `frontend/src/views/ResourcesView.vue`：进度条实时计时 + 统一格式
- `frontend/src/views/PathView.vue`：进度条实时计时 + 统一格式
- `frontend/src/views/QuizView.vue`：进度条实时计时 + 统一格式 + 移除 formatLiveTime
- `frontend/src/components/PptWorkbench.vue`：进度条实时计时 + 统一格式 + 移除 formatLiveTime
- `frontend/src/views/TutorView.vue`：已验证格式正确
- `improvement.md`：本次记录

### 验收标准
1. `VITE_ENABLE_RESOURCE_TIMING=true` 时，生成过程中进度条上立即显示"已耗时 0秒"，每秒更新
2. 生成完成后计时自动停止，显示最终耗时（如"已耗时 45秒"或"已耗时 1分23秒"）
3. `VITE_ENABLE_RESOURCE_TIMING=false` 时，所有实时计时隐藏
4. 生成失败时计时停止，不显示异常值
5. 切换页面或组件卸载时计时器正确清理

## 2026-06-10：PPT 模板弹窗改造

### 变更内容
1. **删除左侧悬浮展开侧边栏**：移除 `.ppt-left-zone` 及其全部相关 CSS，不再使用 hover 展开的模板选择方式
2. **新增模板选择弹窗**：点击"选择模板"/"更换"按钮弹出 `el-dialog`，内嵌搜索框 + 模板网格，复用现有模板卡片 CSS
3. **改造 selected-template-info**：快速生成和大纲定制两个 tab 中，已选模板信息区旁增加"更换"（有模板时）或"选择模板"（无模板时）按钮
4. **新增 `templateDialogVisible` ref**，`openTemplateDialog()` / `selectTemplateInDialog()` 函数控制弹窗状态

### 影响范围
- `frontend/src/components/PptWorkbench.vue`：模板删除、弹窗新增、脚本/CSS 清理

### 验证
1. PPT 页面不再显示左侧模板栏
2. 快速生成和大纲定制 tab 中，点击按钮弹出模板选择弹窗
3. 弹窗中可搜索、预览、选择模板，选择后自动关闭并更新已选模板信息

## 2026-06-10：修复快速生成 PPT 缺少内容页

### 变更内容
1. **后端 Step 1 大纲生成提示词**：从生成扁平章节标题改为生成带子主题的层级大纲（每个章节 2-4 个子主题，两个空格缩进），让 LLM 输出包含子节的结构化大纲
2. **后端 Step 2 JSON 转换提示词**：删除"不要子节"限制，改为"缩进的行作为子节 chapterContents"，使 XFYUN API 能根据子节生成实际内容幻灯片
3. **前端 sanitizeOutline()**：改为保留行首缩进（仅清除行尾空格和空行），使 outlineGenerate 路径也能利用缩进生成子节

### 影响范围
- `backend/app/routes/ppt.py`：quick_create 的两个 LLM 提示词
- `frontend/src/components/PptWorkbench.vue`：sanitizeOutline 函数

## 2026-06-11：动态学生画像演化进度条改为雷达图

### 变更内容
1. **ProfileEvolutionTimeline.vue 改造**：
   - 删除 `ability-panel` 中的 4 个 `<el-progress>` 进度条（概念理解、实践迁移、自我纠错、学习稳定性）
   - 改用 ECharts 雷达图展示四维能力，利用项目已存在的 `echarts` 依赖
   - 雷达图显示每个维度的百分比标签、支持 tooltip 悬浮查看
   - 颜色风格：主色 `#6366f1` 紫色系，与页面现有设计一致
   - 删除旧 CSS（`.ability-row`、`.ability-text` 等），新增 `.radar-chart` 样式

### 影响范围
- `frontend/src/components/ProfileEvolutionTimeline.vue`：模板、脚本、CSS 修改

## 2026-06-13：全局紫色/靛蓝色主题切换为蓝色

### 变更内容
将所有 `.vue` 文件中硬编码的紫色/靛蓝色值（非 CSS `var()` 回退值）统一替换为蓝色系，保持与 CSS 变量（已更新为蓝色）的视觉一致性。

### 颜色映射
| 原色 | 新色 | 用途 |
|------|------|------|
| `#4f46e5` | `#3b82f6` | 主色（靛蓝→蓝） |
| `#6366f1` | `#3b82f6` | 渐变色/文本色 |
| `#eef2ff` | `#eff6ff` | 浅背景 |
| `#c7d2fe` | `#bfdbfe` | 边框/浅色 |
| `#e0e7ff` | `#dbeafe` | 边框/浅背景 |
| `#312e81` | `#1e40af` | 深色文字 |
| `#818cf8` | `#60a5fa` | 中色 |
| `#f5f3ff` | `#eff6ff` | 浅背景 |
| `#ede9fe` | `#dbeafe` | 浅背景 |
| `#7c3aed` | `#3b82f6` | 紫色→蓝色 |
| `#a5b4fc` | `#bfdbfe` | 边框 |
| `#8b5cf6` | `#3b82f6` | 紫色→蓝色 |
| `#ddd6fe` | `#bfdbfe` | 填充色 |
| `#a78bfa` | `#60a5fa` | 中色 |
| `#f0f4ff` | `#eff6ff` | 浅背景 |
| `#4338ca` | `#1d4ed8` | 深蓝色 |

### 修改的文件
- `frontend/src/views/KnowledgeView.vue`
- `frontend/src/views/PathView.vue`
- `frontend/src/views/ProfileView.vue`
- `frontend/src/views/DashboardView.vue`
- `frontend/src/views/QuizView.vue`
- `frontend/src/views/TutorView.vue`
- `frontend/src/views/ResourcesView.vue`
- `frontend/src/components/MultiAgentDebatePanel.vue`
- `frontend/src/components/MindMapViewer.vue`
- `frontend/src/components/PptWorkbench.vue`
- `frontend/src/components/TrustReport.vue`
- `frontend/src/components/ProfileEvolutionTimeline.vue`

### 说明
- CSS `var()` 回退值（如 `var(--primary-600, #4f46e5)`）保持不变，因为 CSS 变量本身已解析为蓝色
- `.vue.js` 编译文件未修改（按规则跳过）
- 所有替换为精确字符串匹配，不涉及正则或模糊替换

## 2026-06-13：UI 改进 — 蓝色主题补充 + 顶栏区分 + 移动端适配

### 变更内容
1. **index.html theme-color 更新**：`#4f46e5` → `#3b82f6`，匹配蓝色主题

2. **DashboardView.vue 英雄区颜色修正**：
   - 背景渐变从暗紫色（`#1e1b4b`/`#312e81`/`#3730a3`）改为深蓝色（`#1e3a5f`/`#1e4a7a`/`#2563eb`）
   - 装饰径向光晕从靛蓝改为蓝色
   - 按钮渐变色和阴影从紫色改为蓝色
   - Agent 图标颜色、快速操作颜色从紫色改为蓝色

3. **顶栏浅蓝色背景区分（总览/个人画像/学习路径）**：
   - `App.vue` 新增 `isOverviewPage` 计算属性，识别 dashboard/profile/path 页面
   - `style.css` 新增 `.topbar--overview` 样式：浅蓝渐变背景（`#eff6ff → #dbeafe`），蓝色底边

4. **移动端适配**：
   - `App.vue` 新增 `isMobile` 响应式状态 + window resize 监听
   - 移动端侧栏改为固定定位 overlay 抽屉（`position: fixed` + `transform` 切换）
   - 新增 `.sidebar-backdrop` 遮罩层（`position: fixed` + 半透明黑背景）
   - 新增 `.mobile-menu-btn` 汉堡菜单按钮（移动端显示，桌面端隐藏）
   - 桌面端 `.collapse-btn` 在移动端隐藏
   - 移动端选择菜单后自动关闭侧栏
   - 移动端禁用 hover 展开行为
   - 顶栏在 600px 以下缩小内边距并隐藏用户标签

### 影响范围
- `frontend/index.html`：theme-color 更新
- `frontend/src/App.vue`：新增 isOverviewPage/computed、isMobile/onResize、mobile-menu-btn、sidebar-backdrop、onMenuSelect 移动端关闭、resize 监听
- `frontend/src/style.css`：新增 .topbar--overview、.mobile-menu-btn、.sidebar-backdrop、移动端 overlay 抽屉 CSS
- `frontend/src/views/DashboardView.vue`：英雄区颜色改为蓝色系

## 2026-06-13：登录注册页面美化

### 变更内容
1. **背景美化**：从纯 `var(--surface-50)` 改为柔和渐变色（`#f8fafc → #eef2ff → #f0f7ff`），增加两个大型半透明装饰圆作为背景层次
2. **登录卡片**：移除边框（`border`），增强阴影使其更现代
3. **左侧面板（品牌区）**：
   - 背景从纯白改为微渐变（`#ffffff → #fafcff`）
   - 顶部边框从单色改为蓝色渐变（`primary-400 → primary-500 → primary-600`）
   - 右上角增加装饰性网格点阵
   - 标题第一行"多智能体"使用蓝色渐变文字（`primary-500 → primary-700`）
4. **右侧面板（表单区）**：
   - 背景改为微渐变，与左侧面板统一
   - 右上角增加装饰性渐变圆点
   - 头像增大至 52px，增加柔和阴影
   - 标题字号微调（24px → 22px），间距优化
5. **表单输入框**：增加浅灰背景（`surface-50`），hover/focus 时变白，交互更清晰
6. **提交按钮**：阴影微调（更柔和）
7. **演示账号提示**：从虚线灰框改为浅蓝实线框（`primary-50` + `primary-200`），更融入整体风格

### 影响范围
- `frontend/src/style.css`：登录页面相关样式重写

## 2026-06-13：智能辅导输入框规范化输入示例浮层

### 变更内容
1. **模板改造**：将原有的单示例硬编码内容改为通过 `v-for` 循环渲染 4 个快捷示例卡片，每个卡片显示标题（示例 1/2/3/4）和内容预览（最多 3 行），点击直接调用 `useExamplePrompt(idx)` 填入输入框
2. **CSS 新增**：
   - `.tutor-input-wrapper`：相对定位容器
   - `.input-example-popover`：绝对定位浮层，位于输入框左上方上浮 10px，蓝白配色，12px 圆角，16ms 淡入动画
   - `.example-title` / `.example-sub`：标题与副标题样式
   - `.example-card`：可点击的示例卡片，hover 时上移 1px 加阴影
   - `.example-card-label` / `.example-card-text`：标签与文本截断样式
   - `@keyframes inputExampleFadeIn`：opacity + translateY 过渡动画
3. **保留现有逻辑**：所有发送/上传/知识库开关/配图开关/拖拽上传功能不变；状态管理（`isInputFocused`/`isInputHovered`/`showInputExample`）保持不变

### 影响范围
## 2026-06-17：文档整合（12 个旧文件 → 4 个新文件）

### 变更内容
根据题目要求，将 docs/ 目录下原先分散的 12 个文档文件整合为 4 个逻辑清晰的文档，采用更自然的口语化写作风格以降低 AI 痕迹。

### 新文档结构
1. **项目开发说明书.md** — 合并了原 01(项目说明书)、02(系统开发说明书)、08(多智能体架构设计)、09(防幻觉)、10(AI工具与开源组件) 的内容
2. **系统测试与部署说明书.md** — 合并了原 03(系统测试说明书)、05(部署运行说明书)、06(数据库设计说明书)、07(接口设计说明书) 的内容
3. **用户使用手册.md** — 基于原 04(用户使用手册) 重写为更自然的问答式风格
4. **演示材料.md** — 合并了原 11(演示PPT内容大纲)、12(演示视频脚本) 的内容

### 删除的旧文件
删除了 12 个文件：01_项目说明书.md、02_系统开发说明书.md、03_系统测试说明书.md、04_用户使用手册.md、05_部署运行说明书.md、06_数据库设计说明书.md、07_接口设计说明书.md、08_多智能体架构设计说明书.md、09_防幻觉与内容安全机制说明.md、10_AI工具与开源组件使用说明.md、11_演示PPT内容大纲.md、12_演示视频脚本.md

### 影响范围
- docs/ 目录结构变更，仅保留 4 个新文档 + 1 个 pic_for_ppt.doc

## 2026-06-24：知识库入库乱码修复 — 文本清洗 + PyMuPDF + 坏块过滤

### 变更内容
在文档入库全流程中增加了文本清洗、乱码检测、目录页过滤、坏 chunk 跳过逻辑，从根源解决 PDF 解析后出现大量  的问题。

### 修改详情

1. **新增 `backend/app/services/text_cleaner.py`**：
   - `clean_extracted_text()` — Unicode 规范化（NFKC）、删除  替换字符、删除控制字符、删除目录点线引导符、合并空白
   - `is_bad_text()` — 检测坏文本：乱码比例 >1% 丢弃、有效字符比例 <25% 丢弃、文本过短丢弃
   - `is_toc_like_text()` — 检测目录页：包含"目录"关键词、章节编号行、行尾页码、点线引导符，综合评分 >=3 判定为目录
   - `is_header_footer_like()` — 检测页眉/页脚：纯数字页码、"第 X 页"模式、短章节标题
   - `filter_document_pages()` — 逐页过滤：清洗 → 坏文本检测 → 目录页检测 → 页眉页脚检测
   - `filter_chunks()` — 对已切分的 chunk 逐块过滤

2. **修改 `backend/app/routes/knowledge.py`**：
   - PDF 解析器从单一的 pypdf 改为优先使用 **PyMuPDF (fitz)**，解析质量更好，逐页提取
   - 新增 `_should_ocr()` 判断是否需要 OCR 兜底（文本过短或有效比例过低时）
   - 新增 `_ocr_page()` — 使用 PaddleOCR 兜底扫描页（将 PDF 渲染为 300dpi 图片后 OCR），可选依赖不影响现有功能
   - `extract_pdf_text()` 改为逐页提取 → `filter_document_pages()` 清洗过滤 → 组装有效页
   - `upload_document()` 中上传的文本内容先经过 `clean_extracted_text()` 再入库
   - `split_text()` 分块后经过 `filter_chunks()` 逐块过滤
   - 新增 `POST /knowledge/reindex/<id>` 端点：对已入库文档重新提取、清洗、分块、重建 FAISS 索引

3. **修改 `backend/requirements.txt`**：
   - 新增 PyMuPDF>=1.23.0、Pillow>=10.0.0
   - 注释添加 paddlepaddle / paddleocr 作为 OCR 可选依赖说明

4. **修改 `frontend/src/api/learning.ts`**：
   - 新增 `reindexDocument(id)` API 方法

5. **修改 `frontend/src/views/KnowledgeView.vue`**：
   - `reindexDocument()` 从空壳函数改为调用后端 API
   - 新增 `cleanDisplayText()` 前端兜底函数，在搜索结果展示中过滤乱码字符

### 入库流程（修复后）
```
PDF/文档 → PyMuPDF 逐页提取
    → 逐页清洗（clean_extracted_text）
    → 逐页坏文本检测（is_bad_text）
    → 目录页过滤（is_toc_like_text）
    → 有效文本分块（split_text）
    → 逐块过滤（filter_chunks）
    → embedding → FAISS 入库
```

### 影响范围
- `backend/app/services/text_cleaner.py` — 新增
- `backend/app/routes/knowledge.py` — 重写 PDF 解析、upload/reindex 逻辑
- `backend/requirements.txt` — 新增 PyMuPDF、Pillow
- `frontend/src/api/learning.ts` — 新增 reindexDocument
- `frontend/src/views/KnowledgeView.vue` — reindex 功能、cleanDisplayText
- `improvement.md` — 本次记录

### 验收标准
1. PDF 目录页不会进入向量数据库
2. 包含大量  的文本不会入库
3. 类似"残差连接 124"的文本不会再出现在知识库预览中
4. 文档重新入库后，检索结果不再出现乱码
5. 已入库的旧乱码数据可通过"重新索引"按钮清除
6. 不影响正常中文、英文、Markdown 文本入库

### 补充说明
- PyMuPDF (fitz) 为必装依赖（`pip install PyMuPDF`）
- OCR 兜底依赖 PaddleOCR（`pip install paddlepaddle paddleocr`），按需安装，未安装时不影响正常功能，仅扫描 PDF 的乱码页无法恢复

## 2026-06-24：PPT 模板 ID 修复 — 使用讯飞 API 真实模板 ID

### 变更内容
两个问题：
1. 讯飞 API `/themeList` 返回的字段与代码预期不符：实际字段为 `templateIndexId`、`color`、`style`、`detailImage(JSON)`，但代码使用了不存在的 `key`、`name`、`thumbnail` 字段，导致 `KeyError` 被 catch 后始终降级到静态兜底主题。
2. 静态兜底主题列表的 value 使用颜色名（如 `"purple"`），不是有效模板 ID。

### 修改详情

1. **后端 `backend/app/routes/ppt.py`** — `themes()` 端点重写：
   - 使用 `t["templateIndexId"]` 作为 value（真实模板 ID，如 `"202407171E27C9D"`）
   - 从 `t.get("style", "")` + `t.get("color", "")` 拼接 label
   - `detailImage` 解析：若为 JSON 字符串则提取 `titleCoverImageLarge` 作为缩略图；否则直接作为图片 URL
   - 静态 `THEMES` 的非 auto 项 value 改为空字符串 `""`（保留 label 仅供展示兜底）
   - `STATIC_THEME_VALUES` 收缩为仅含 `"auto"`
   - `normalize_template_id()` 简化

2. **前端 `frontend/src/components/PptWorkbench.vue`**：
   - 所有 `template_id`/`theme` 传入点补 `|| 'auto'` 兜底
   - 按钮禁用条件从 `!selectedTemplateId` 改为 `!selectedTemplate`
   - 所有模板 `<img>` 添加 `@error` 处理：加载失败时自动切换到占位图标，避免显示破碎图片

### 影响范围
- `backend/app/routes/ppt.py` — THEMES 值修改、STATIC_THEME_VALUES 收缩、normalize_template_id 简化
- `frontend/src/components/PptWorkbench.vue` — 所有 template_id 传入点补 `|| 'auto'` 兜底、按钮禁用条件改用 computed
- `improvement.md` — 本次记录

### 验收标准
1. 静态主题（如"典雅紫"、"清新绿"）在模板选择弹窗中正常显示且可选择
2. 选择静态主题后，"已选模板"标签正常展示主题名称
3. 生成 PPT 时向后端传递 `template_id: "auto"` 而非颜色名
4. 点击生成按钮不会被空字符串误阻断
5. 讯飞 API 可用时，模板 ID 正常传递不受影响