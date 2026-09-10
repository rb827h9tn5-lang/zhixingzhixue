from __future__ import annotations

import hashlib
import re

RESOURCE_LABELS = {
    "course_document": "讲解文档",
    "mind_map": "思维导图",
    "exercise_bank": "练习题库",
    "extension_reading": "拓展阅读",
    "coding_case": "实操案例",
    "multimedia_video": "教学视频",
}


class LocalStudyGenerator:
    def __init__(self, profile: dict | None = None):
        self.profile = profile or {}
        self.topic = self.profile.get("topic") or "人工智能导论"
        self.knowledge_level = self.profile.get("knowledge_level") or "beginner"
        self.learning_goal = self.profile.get("learning_goal") or "系统掌握课程核心知识并完成实践项目"
        self.learning_style = self.profile.get("learning_style") or "mixed"
        self.time_availability = self.profile.get("time_availability") or "3-5 hours per week"

    def extract_profile(self, payload: dict, previous: dict | None = None) -> dict:
        dialogue = payload.get("dialogue", "")
        previous = previous or {}
        weak_points = self._extract_after(dialogue, ["不懂", "薄弱", "困难", "不会", "错在"]) or previous.get("weak_points")
        interest = self._extract_after(dialogue, ["喜欢", "想做", "兴趣", "目标是"]) or previous.get("motivation_driver")
        return {
            "topic": payload.get("topic") or previous.get("topic") or self.topic,
            "major": payload.get("major") or previous.get("major") or "计算机相关专业",
            "knowledge_level": payload.get("knowledge_level") or previous.get("knowledge_level") or "beginner",
            "learning_goal": payload.get("learning_goal") or previous.get("learning_goal") or self.learning_goal,
            "learning_style": payload.get("learning_style") or previous.get("learning_style") or "mixed",
            "cognitive_preference": payload.get("cognitive_preference") or previous.get("cognitive_preference") or self._style_strategy(),
            "prior_experience": payload.get("prior_experience") or previous.get("prior_experience") or "待通过对话继续补充",
            "time_availability": payload.get("time_availability") or previous.get("time_availability") or self.time_availability,
            "motivation_driver": interest or "课程掌握、项目展示与能力提升",
            "engagement_pattern": payload.get("engagement_pattern") or previous.get("engagement_pattern") or "阶段学习 + 测评复盘",
            "weak_points": weak_points or "概念边界、知识迁移、综合应用",
            "raw_dialogue": "\n".join([previous.get("raw_dialogue", ""), dialogue]).strip(),
        }

    def build_profile_summary(self, profile: dict) -> str:
        weak = profile.get("weak_points", "") or "暂无明显短板"
        return f"""## 动态学生画像

### 当前薄弱环节
{weak}

### 自适应学习策略
- 正确率低于 70% 时推送基础讲义、导图和基础题
- 连续两次高于 85% 时推送综合项目和拓展阅读
- 学生提出新目标时重新排序学习路径和资源推荐

### 学习建议
根据当前画像，建议优先巩固薄弱知识点，然后通过测评检验掌握程度，再进入下一阶段学习。"""

    def plan_path(self, context: dict | None = None) -> str:
        context = context or {}
        quizzes = context.get("quiz_results") or []
        documents = context.get("knowledge_documents") or []
        resources = context.get("resources") or []
        wrong_points = self._path_wrong_points(quizzes)
        recent_scores = [float(item.get("score") or 0) for item in quizzes[:3]]
        average_score = round(sum(recent_scores) / len(recent_scores), 1) if recent_scores else None
        resource_types = {item.get("resource_type") for item in resources}
        document_titles = [item.get("title", "未命名文档") for item in documents[:5]]

        if average_score is None:
            strategy = "先诊断后学习：当前缺少测评记录，路径优先安排诊断题和基础概念校准。"
            first_goal = "建立术语表、目标树和诊断题，形成第一份测评记录"
        elif average_score < 70:
            strategy = "补基础优先：最近测评低于 70 分，路径优先围绕错题概念回炉讲解和同类变式练习。"
            first_goal = f"补齐薄弱点：{wrong_points or self.profile.get('weak_points') or '基础概念与题目迁移'}"
        elif average_score >= 85:
            strategy = "进阶迁移优先：最近测评表现较好，路径增加项目实践、拓展阅读和综合任务。"
            first_goal = "用综合案例和项目任务验证知识迁移"
        else:
            strategy = "巩固提升优先：最近测评处于中间区间，路径采用讲解、练习、复盘交替推进。"
            first_goal = f"巩固易错概念：{wrong_points or '核心概念边界'}"

        resource_hint = self._path_resource_hint(resource_types)
        knowledge_hint = "；".join(document_titles) if document_titles else "当前知识库材料不足，建议先在知识库管理中上传课程讲义或补充材料"
        steps = [
            {
                "title": "完成起点诊断",
                "time": "第 1 次学习 / 30-45 分钟",
                "goal": first_goal,
                "task": "生成 3-5 道诊断题，确认当前知识水平、学习目标和主要短板。",
                "action": "进入“测评评估”生成题目并完成作答；提交后查看答案解析。",
                "resource": self._phase_resources("诊断与路径校准", resource_types),
                "output": "一份诊断得分记录和需要补齐的知识点清单。",
                "checkpoint": "完成诊断题；若正确率低于 70%，下一步优先补基础。",
            },
            {
                "title": "精读课程知识库",
                "time": "第 2 次学习 / 45-60 分钟",
                "goal": "从课程材料中提炼术语、流程、公式和易混概念。",
                "task": f"阅读并整理知识库材料：{knowledge_hint}。",
                "action": "进入“知识库管理”确认材料已加载；再到“智能辅导”追问不理解的概念。",
                "resource": self._phase_resources("知识库精读与概念补齐", resource_types),
                "output": "一份 8-12 条的核心概念笔记。",
                "checkpoint": "能用自己的话解释 3 个核心概念，并指出至少 1 个易混点。",
            },
            {
                "title": "补齐错题概念",
                "time": "第 3 次学习 / 45-60 分钟",
                "goal": f"集中补齐 {wrong_points or self.profile.get('weak_points') or '当前短板'}。",
                "task": "围绕错题概念重新阅读讲解文档和思维导图，并记录错误原因。",
                "action": "进入“知识学习”生成或查看讲解文档、思维导图；把不理解的问题交给“智能辅导”。",
                "resource": self._phase_resources("错题驱动分层练习", resource_types),
                "output": "每个错题概念写出“定义、适用条件、例子、常见误区”。",
                "checkpoint": self._phase_checkpoint("错题驱动分层练习", average_score),
            },
            {
                "title": "进行分层练习",
                "time": "第 4 次学习 / 45-60 分钟",
                "goal": "用基础题、应用题和变式题验证是否真正掌握。",
                "task": "完成一组 5-10 题练习，先独立作答，再查看答案和解析。",
                "action": "进入“测评评估”生成题目；全部答完后提交，记录错题概念。",
                "resource": "练习题库；缺失时先在“知识学习”生成练习题库",
                "output": "一次新的测评记录和错题复盘。",
                "checkpoint": "同类题正确率达到 70% 以上；若已达到 85%，进入实践迁移。",
            },
            {
                "title": "完成资源复述",
                "time": "第 5 次学习 / 30-45 分钟",
                "goal": "把学过的知识组织成可讲解、可展示的结构。",
                "task": "借助讲解文档或拓展阅读材料，把核心概念整理成一份学习总结。",
                "action": "进入“知识学习”查看讲解文档或拓展阅读材料；用自己的话补充例子。",
                "resource": self._phase_resources("资源组合学习", resource_types),
                "output": "一份学习总结或一张思维导图。",
                "checkpoint": "能按“问题 -> 方法 -> 例子 -> 易错点”讲清本阶段内容。",
            },
            {
                "title": "完成实操迁移",
                "time": "第 6 次学习 / 60-90 分钟",
                "goal": "把概念迁移到实操题或小项目。",
                "task": "完成一个实操案例，提交答案后根据 AI 判题修改。",
                "action": "进入“知识学习”的实操案例，生成题目并提交答案。",
                "resource": self._phase_resources("实操迁移与综合评估", resource_types),
                "output": "一份实操答案、参考答案对照和改进记录。",
                "checkpoint": "AI 判题达到 60 分以上，并能说明改进点。",
            },
            {
                "title": "复测并更新下一轮路径",
                "time": "第 7 次学习 / 30-45 分钟",
                "goal": "用新测评结果决定下一轮是补基础、巩固还是进阶。",
                "task": "重新完成一组测评题，对比本轮和上一轮得分变化。",
                "action": "提交测评后再次点击“生成学习路径”，系统会根据新错题和资源状态重排计划。",
                "resource": "测评评估、学习画像、知识学习全部参与下一轮路径更新",
                "output": "下一轮动态学习路径。",
                "checkpoint": "错题概念减少，或明确下一轮需要继续补齐的知识点。",
            },
        ]
        lines = [
            "## {topic} 动态学习计划路径".format(topic=self.topic),
            "- 学习目标：{learning_goal}".format(learning_goal=self.learning_goal),
            "- 当前基础：{knowledge_level}".format(knowledge_level=self.knowledge_level),
            "- 学习风格：{learning_style}".format(learning_style=self.learning_style),
            "- 可投入时间：{time_availability}".format(time_availability=self.time_availability),
            f"- 最近测评均分：{average_score if average_score is not None else '暂无测评记录'}",
            f"- 识别出的错题/短板：{wrong_points or self.profile.get('weak_points') or '暂无明确错题，先做诊断题'}",
            f"- 知识库依据：{knowledge_hint}",
            f"- 已生成资源：{self._resource_titles(resources)}",
            f"- 动态策略：{strategy}",
            "",
            "### 学习计划总览",
            "- 按顺序完成下面 7 个步骤；每完成一次测评或上传新材料后，都可以重新生成路径。",
            "- 每一步都有明确的学习任务、入口操作、资源和完成标准。",
            "- 不建议跳过诊断和复测，否则路径无法根据真实掌握情况更新。",
            "",
        ]
        for index, step in enumerate(steps, 1):
            lines.extend([
                "### 第 {index} 步：{title}".format(index=index, title=step["title"]),
                "- 时间：{time}".format(time=step["time"]),
                "- 学习目标：{goal}".format(goal=step["goal"]),
                "- 学习任务：{task}".format(task=step["task"]),
                "- 操作入口：{action}".format(action=step["action"]),
                "- 使用资源：{resource}".format(resource=step["resource"]),
                "- 产出物：{output}".format(output=step["output"]),
                "- 完成标准：{checkpoint}".format(checkpoint=step["checkpoint"]),
            ])
        lines.append(
            "\n### 下一轮更新规则\n"
            "- 新增知识库材料后，优先把第 2 步的阅读依据替换为新上传的课程资料。\n"
            "- 测评低于 70 分时，下一轮路径前置讲解文档、思维导图和基础题。\n"
            "- 测评高于 85 分且错题减少时，下一轮路径前置实操案例、拓展阅读和综合复述任务。\n"
            "- 每次提交练习或实操后，将错题概念写回画像短板，用于重新排序学习路径。"
        )
        import time as _time
        lines.append(f"\n> 路径生成时间：{_time.strftime('%Y-%m-%d %H:%M:%S')} | 本次侧重：{strategy.split('：')[0]}")
        return "\n".join(lines)

    def generate_resource(self, resource_type: str, extra_input: str = "") -> str:
        return {
            "course_document": lambda: self._course_document(extra_input),
            "mind_map": lambda: self._mind_map(extra_input),
            "exercise_bank": self._exercise_bank,
            "extension_reading": lambda: self._extension_reading(extra_input),
            "multimedia_video": lambda: self._multimedia_video(extra_input),
            "coding_case": lambda: self._coding_case(extra_input),
        }.get(resource_type, lambda: self._course_document(extra_input))()

    def structured_quiz(self, difficulty: str, focus: str, count: int) -> dict:
        concepts = self._concepts(focus)
        questions = []
        question_types = ["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"]
        for index in range(1, max(1, min(count, 10)) + 1):
            concept = concepts[(index - 1) % len(concepts)]
            question_type = question_types[(index - 1) % len(question_types)]
            question = {
                "id": index,
                "type": question_type,
                "concept": concept,
                "explanation": "这道题检查你是否能把 {concept} 从记忆层迁移到应用层。".format(concept=concept),
            }
            if question_type == "single_choice":
                question.update({
                    "prompt": "关于“{concept}”的学习方式，哪一项最合理？".format(concept=concept),
                    "options": ["只记忆定义", "解释概念并说明适用场景", "跳过基础直接做项目", "只看视频不练习"],
                    "answer": "解释概念并说明适用场景",
                    "hint": "比较四个选项是否同时覆盖“{concept}”的理解和应用场景。".format(concept=concept),
                })
            elif question_type == "multiple_choice":
                question.update({
                    "prompt": "学习“{concept}”时，哪些做法有助于真正掌握？".format(concept=concept),
                    "options": ["写出通俗定义", "给出应用例子", "记录常见误区", "完全依赖背诵"],
                    "answer": ["写出通俗定义", "给出应用例子", "记录常见误区"],
                    "hint": "多选题通常不止一个正确项，优先选择能帮助你解释、举例和避错的做法。",
                })
            elif question_type == "true_false":
                question.update({
                    "prompt": "判断：学习“{concept}”只要记住术语定义即可，不需要结合场景或例子。".format(concept=concept),
                    "options": ["正确", "错误"],
                    "answer": "错误",
                    "hint": "判断这个说法是否忽略了“{concept}”的应用条件和例子验证。".format(concept=concept),
                })
            elif question_type == "fill_blank":
                question.update({
                    "prompt": "填空：“{concept}”的学习至少应包含定义、适用条件和____。".format(concept=concept),
                    "options": [],
                    "answer": "具体例子",
                    "hint": "空格应填写能把“{concept}”从抽象概念落到真实场景的内容。".format(concept=concept),
                })
            else:
                question.update({
                    "prompt": "请说明“{concept}”在 {topic} 中的作用，并给出一个学习或应用例子。".format(concept=concept, topic=self.topic),
                    "options": [],
                    "answer": "{concept} 需要同时说明含义、使用条件和具体例子，不能只背术语。".format(concept=concept),
                    "hint": "简答题建议按“定义 -> 作用 -> 适用条件 -> 例子”组织“{concept}”的答案。".format(concept=concept),
                })
            questions.append(question)
        return {
            "title": "{topic} 分层练习".format(topic=self.topic),
            "difficulty": difficulty,
            "focus": focus or "综合",
            "questions": questions,
        }

    def grade_structured_quiz(self, quiz: dict, answers: dict, llm_judge=None) -> dict:
        questions = quiz.get("questions", [])
        correct_count = 0
        details = []
        for question in questions:
            raw_answer = answers.get(str(question["id"]), answers.get(question["id"], ""))
            score = self._score_answer(question, raw_answer, llm_judge)
            correct_count += score
            details.append({
                "id": question["id"],
                "concept": question.get("concept", ""),
                "user_answer": self._format_answer(raw_answer),
                "reference_answer": self._format_answer(question["answer"]),
                "explanation": question["explanation"],
                "is_correct": score == 1,
                "status": self._answer_status(score),
                "score_fraction": round(float(score), 4),
                "primary_knowledge_point_id": question.get("primary_knowledge_point_id"),
                "knowledge_point_mapping_status": question.get(
                    "knowledge_point_mapping_status",
                    "unmapped",
                ),
            })
        total = len(questions) or 1
        score = round(correct_count * 100 / total, 1)
        summary = (
            "本次练习得分 {score}/100。"
            "建议优先复盘回答过短或没有例子的题目，并把错题关联到知识画像中的易错点。"
        ).format(score=score)
        return {"score": score, "details": details, "summary": summary}

    def _score_answer(self, question: dict, raw_answer, llm_judge=None) -> float:
        expected = question.get("answer", "")
        question_type = question.get("type", "")
        if question_type == "multiple_choice":
            selected = self._choice_answer_set(question, raw_answer)
            expected_set = self._choice_answer_set(question, expected)
            if selected == expected_set:
                return 1
            if selected and selected.issubset(expected_set):
                return 0.5
            return 0
        answer = str(raw_answer or "").strip()
        if question_type in {"single_choice", "true_false"}:
            return int(
                self._choice_answer_set(question, answer)
                == self._choice_answer_set(question, expected)
            )
        if question_type == "fill_blank":
            if llm_judge:
                score = llm_judge(answer, question)
                if score is not None:
                    return score
            # 本地回退：子串匹配
            if str(expected) in answer or answer in str(expected):
                return 1
            return 0.5 if answer else 0
        # 简答题及其他开放题型
        if llm_judge:
            score = llm_judge(answer, question)
            if score is not None:
                return score
        # 本地回退：按字符长度估算
        if len(answer) >= 12:
            return 1
        return 0.5 if len(answer) >= 6 else 0

    @staticmethod
    def _answer_status(score: float) -> str:
        if score >= 1:
            return "correct"
        if score > 0:
            return "partial"
        return "wrong"

    def _format_answer(self, answer) -> str:
        if isinstance(answer, list):
            return "、".join(str(item) for item in answer)
        return str(answer or "")

    def _choice_answer_set(self, question: dict, value) -> set[str]:
        if isinstance(value, list):
            items = value
        elif isinstance(value, tuple):
            items = list(value)
        else:
            text = str(value or "").strip()
            items = re.split(r"[,，、/；;]\s*", text) if text else []
        return {letter for item in items if (letter := self._choice_answer_letter(question, item))}

    @staticmethod
    def _strip_option_prefix(value: str) -> str:
        return re.sub(r"^\s*[A-Za-z]\s*[.、．)]\s*", "", value or "").strip()

    def _choice_answer_letter(self, question: dict, value) -> str:
        text = str(value or "").strip()
        if not text:
            return ""

        direct = re.match(r"^\s*([A-Za-z])(?:\s*[.、．)]|\s*$)", text)
        if direct:
            return direct.group(1).upper()

        normalized = self._strip_option_prefix(text)
        for index, option in enumerate(question.get("options") or []):
            option_text = str(option or "").strip()
            option_normalized = self._strip_option_prefix(option_text)
            if text == option_text or normalized == option_normalized:
                return chr(65 + index)

        return text.upper()

    def coding_case_question(self, extra_input: str = "") -> dict:
        hint = "\n### 用户补充\n{extra_input}".format(extra_input=extra_input) if extra_input else ""
        return {
            "title": "{topic} 实操题".format(topic=self.topic),
            "prompt": "给定一组学生练习正确率，请写出一个函数计算平均正确率，并判断是否需要推送基础讲义。正确率低于 70% 时返回“需要补基础”，否则返回“进入进阶练习”。{hint}".format(hint=hint),
            "requirements": [
                "输入：一个 0-100 的数字列表",
                "输出：平均正确率和学习建议",
                "需要处理空列表",
            ],
            "reference_answer": "空列表返回平均值 0 和需要补基础；否则计算 sum(scores)/len(scores)，低于 70 返回需要补基础。",
        }

    def grade_coding_case(self, question: dict, answer: str) -> dict:
        answer_text = answer or ""
        keywords = ["sum", "len", "70", "空", "平均"]
        matched = [keyword for keyword in keywords if keyword.lower() in answer_text.lower()]
        score = min(100, len(matched) * 20)
        return {
            "score": score,
            "is_passed": score >= 60,
            "reference_answer": question.get("reference_answer"),
            "analysis": "命中关键点：{matched}。建议补充边界情况、平均值计算和阈值判断。".format(matched=", ".join(matched) or "暂无"),
        }

    def generate_quiz(self, difficulty: str, focus: str, count: int) -> str:
        concepts = self._concepts(focus)
        questions = []
        for index in range(1, max(1, min(count, 20)) + 1):
            concept = concepts[(index - 1) % len(concepts)]
            questions.append(
                """### Question {index}
题型：{question_type}
知识点：{concept}
题目：请说明 {concept} 在 {topic} 学习中的作用，并给出一个应用例子。
参考答案：应包含概念含义、适用条件、例子和常见误区。
解析：本题检查是否能从记忆迁移到应用。""".format(
                    index=index,
                    question_type="选择题" if index % 2 else "简答题",
                    concept=concept,
                    topic=self.topic,
                )
            )
        return "## {topic} 自适应测验\n\n难度：{difficulty}\n聚焦：{focus or '综合'}\n\n".format(
            topic=self.topic, difficulty=difficulty, focus=focus or "综合"
        ) + "\n\n".join(questions)

    def evaluate(self, practice_summary: str, resource_feedback: str, progress_notes: str) -> dict:
        seed = int(hashlib.sha256((practice_summary + resource_feedback + progress_notes).encode("utf-8")).hexdigest(), 16)
        score = 62 + seed % 31
        wrong = self._extract_after(practice_summary, ["错在", "不会", "混淆"]) or "需继续记录错题"
        analysis = """## 学习效果评估

- 综合掌握度：{score}/100
- 易错点：{wrong}
- 资源反馈：{resource_feedback or '暂无'}
- 学习行为：{progress_notes or '暂无'}

### 调整建议
1. 回到错题关联知识点，补读讲义和导图。
2. 追加 5 道同主题变式题。
3. 将新的易错点写回画像，用于下一轮资源推送。
""".format(score=score, wrong=wrong, resource_feedback=resource_feedback, progress_notes=progress_notes)
        return {"score": score, "wrong_questions": wrong, "analysis": analysis}

    def tutor(self, question: str, context: str = "") -> str:
        focus = self._pick_focus(question)
        context_block = "\n### 补充上下文\n{context}".format(context=context) if context else ""
        return """## 解答
你问的是 **{focus}**。建议用“定义 -> 作用 -> 适用条件 -> 例子 -> 练习”的顺序理解。

### 分步说明
1. 先写出 {focus} 的通俗解释。
2. 判断它解决什么问题，以及不适合什么场景。
3. 用一个与 {topic} 相关的小例子验证理解。
4. 做一道变式题，确认能够迁移。

### 练习
- 用 3 句话解释 {focus}
- 给出一个正例和一个反例
- 说明它与相邻概念的区别

{context_block}
""".format(focus=focus, topic=self.topic, context_block=context_block)

    def _course_document(self, extra_input: str = "") -> str:
        hint = "\n### 用户补充\n{extra_input}".format(extra_input=extra_input) if extra_input else ""
        return """## {topic} 个性化讲解文档

### 学习目标
围绕“{learning_goal}”，建立课程概念框架，并通过例题完成第一轮理解。

### 核心知识点
{concepts}

### 学习步骤
1. 阅读术语解释并标注问题。
2. 通过最小例子理解输入、过程和输出。
3. 完成 3 道基础题。
4. 写 100 字总结并记录疑问。
{hint}
""".format(
            topic=self.topic,
            learning_goal=self.learning_goal,
            concepts=", ".join(self._concepts("")),
            hint=hint,
        )

    def _mind_map(self, extra_input: str = "") -> str:
        topic = re.sub(r"[^0-9A-Za-z一-鿿]+", "", self.topic) or "学习主题"
        concepts = self._concepts("")
        hint = "\n    用户补充\n      {extra}".format(extra=extra_input[:40]) if extra_input else ""
        return """## {topic} 思维导图

```mermaid
mindmap
  root(({topic}))
    学生画像
      水平: {level}
      风格: {style}
    核心概念
      {c1}
      {c2}
      {c3}
    学习资源
      讲义
      题库
      拓展阅读
      实操案例
    评估闭环
      测验
      错题
      路径调整{hint}
```""".format(
            topic=topic,
            level=self.knowledge_level,
            style=self.learning_style,
            c1=concepts[0],
            c2=concepts[1],
            c3=concepts[2],
            hint=hint,
        )

    def _exercise_bank(self) -> str:
        return """## {topic} 分层练习题库

### 基础理解
1. 用一句话解释核心概念。
2. 判断题：只看讲义就等于掌握。请说明理由。

### 应用分析
1. 给出一个课程应用场景，并说明输入、过程、输出。
2. 比较两个相近概念的边界。

### 综合实践
设计一个 30 分钟小实验，包含目标、步骤、结果和复盘。
""".format(topic=self.topic)

    def _extension_reading(self, extra_input: str = "") -> str:
        hint = "\n- 用户补充：{extra_input}".format(extra_input=extra_input) if extra_input else ""
        return """## {topic} 拓展阅读材料

- 必读：课程讲义核心章节、教材入门章节、官方文档。
- 选读：经典案例、工具实践文档、错题 FAQ。
- 阅读任务：每篇材料摘录 3 个关键词、1 个疑问、1 个可练习知识点。
- 防幻觉要求：记录标题、机构、链接或出处，关键事实需与课程知识库交叉核验。{hint}
""".format(topic=self.topic, hint=hint)

    def _coding_case(self, extra_input: str = "") -> str:
        hint = "\n### 用户补充\n{extra_input}".format(extra_input=extra_input) if extra_input else ""
        return """## {topic} 实操案例

### 目标
完成一个最小可运行任务，把概念转化为可观察结果。

```python
steps = ["定义问题", "选择方法", "执行验证", "复盘改进"]
for step in steps:
    print(f"{step}: {topic}")
```

### 提交物
- 运行输出
- 100 字复盘
- 一个改进问题
{hint}
""".format(topic=self.topic, hint=hint)

    def _multimedia_video(self, extra_input: str = "") -> str:
        hint = "\n### 用户补充\n{extra_input}".format(extra_input=extra_input) if extra_input else ""
        return """## {topic} 教学视频生成提示

### 推荐视频描述（可直接用于文生视频 API）
1. **知识点精讲视频**：一段 10 秒的教学动画，展示 {topic} 的核心概念，使用 2D 动画风格，包含关键术语标注和过渡效果
2. **案例演示视频**：展示 {topic} 在实际操作中的应用过程，带步骤说明和结果展示，画面清晰流畅
3. **概念对比视频**：用分屏动画对比展示 {topic} 中的正确和错误做法，带文字标注和颜色区分

### 使用说明
- 上述描述可通过“教学视频”功能直接生成教学视频
- 视频时长可在生成时调整（默认 10 秒）
- 可选择开启或关闭配音（音频）
{hint}
""".format(topic=self.topic, hint=hint)

    def _style_strategy(self) -> str:
        mapping = {
            "visual": "流程图、导图、对比表",
            "auditory": "讲解稿、问答讨论和口头复述",
            "kinesthetic": "实验、项目、代码和操作步骤",
            "reading_writing": "讲义、摘要、清单和书面反思",
            "mixed": "讲义、导图、练习和项目组合推进",
        }
        return mapping.get(self.learning_style, "多类型资源组合推进")

    def _concepts(self, focus: str) -> list[str]:
        items = [item for item in re.split(r"[,，、\s]+", focus or "") if item]
        return (items + ["核心概念", "工作流程", "典型应用", "常见误区", "实践评估"])[:5]

    def _path_wrong_points(self, quizzes: list[dict]) -> str:
        points = []
        for quiz in quizzes[:5]:
            wrong = quiz.get("wrong_questions") or ""
            analysis = quiz.get("analysis") or ""
            points.extend(re.findall(r"[一-鿿A-Za-z0-9_]{2,}", wrong))
            if not wrong:
                points.extend(re.findall(r"[一-鿿A-Za-z0-9_]{2,}", analysis)[:2])
        seen = []
        for point in points:
            if point not in seen and point not in {"本次", "练习", "得分", "建议", "优先", "复盘"}:
                seen.append(point)
        return "、".join(seen[:6])

    def _path_resource_hint(self, resource_types: set[str]) -> str:
        missing = [label for key, label in RESOURCE_LABELS.items() if key not in resource_types]
        if missing:
            return "已生成资源可直接使用；建议补齐：{missing}".format(missing="、".join(missing[:4]))
        return "各类资源已较完整，可按阶段组合调用并根据测评结果调整顺序"

    def _resource_titles(self, resources: list[dict]) -> str:
        if not resources:
            return "暂无，建议先在知识学习生成讲解文档、题库和实操案例"
        return "、".join("{title}".format(title=item.get('title', '未命名资源')) for item in resources[:6])

    def _quiz_evidence(self, quizzes: list[dict]) -> str:
        if not quizzes:
            return "暂无测评结果，先生成一组诊断题作为路径校准依据"
        latest = quizzes[0]
        return "最近一次得分 {score}，错题/短板：{wrong}".format(
            score=latest.get('score', 0),
            wrong=latest.get('wrong_questions') or '暂无记录',
        )

    def _phase_resources(self, title: str, resource_types: set[str]) -> str:
        preferred = {
            "诊断与路径校准": ["exercise_bank", "course_document"],
            "知识库精读与概念补齐": ["course_document", "mind_map", "extension_reading"],
            "错题驱动分层练习": ["exercise_bank", "mind_map"],
            "资源组合学习": ["course_document", "extension_reading", "multimedia_video"],
            "实操迁移与综合评估": ["coding_case", "exercise_bank", "extension_reading"],
        }.get(title, ["course_document"])
        labels = [RESOURCE_LABELS[item] for item in preferred if item in RESOURCE_LABELS]
        missing = [RESOURCE_LABELS[item] for item in preferred if item not in resource_types and item in RESOURCE_LABELS]
        suffix = "；缺失时先生成：{missing}".format(missing="、".join(missing)) if missing else "；资源已可直接使用"
        return "、".join(labels) + suffix

    def _phase_checkpoint(self, title: str, average_score: float | None) -> str:
        if title == "诊断与路径校准":
            return "完成 3-5 道诊断题，并确认画像中的知识水平与学习目标"
        if title == "错题驱动分层练习":
            target = 70 if average_score is None or average_score < 70 else 85
            return "同类题正确率达到 {target}% 以上，再进入下一阶段".format(target=target)
        if title == "实操迁移与综合评估":
            return "提交实操答案，完成一次测评，并用错题更新画像"
        return "输出 1 份笔记或概念复述，并完成 5 道配套练习"

    @staticmethod
    def _extract_after(text: str, prefixes: list[str]) -> str:
        for prefix in prefixes:
            match = re.search(prefix + r"([^。；;,\n]{1,40})", text or "")
            if match:
                return match.group(1).strip()
        return ""

    @staticmethod
    def _pick_focus(text: str) -> str:
        words = re.findall(r"[一-鿿A-Za-z0-9_]{2,}", text or "")
        return words[0] if words else "当前问题"
