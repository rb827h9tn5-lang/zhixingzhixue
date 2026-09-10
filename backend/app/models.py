from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), default="student", nullable=False)
    email = db.Column(db.String(120), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    profile = db.relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "email": self.email,
        }


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    topic = db.Column(db.String(180), default="人工智能导论")
    major = db.Column(db.String(120), default="计算机相关专业")
    knowledge_level = db.Column(db.String(80), default="beginner")
    learning_goal = db.Column(db.Text, default="")
    learning_style = db.Column(db.String(80), default="mixed")
    cognitive_preference = db.Column(db.String(120), default="结构化讲解")
    prior_experience = db.Column(db.Text, default="")
    time_availability = db.Column(db.String(120), default="3-5 hours per week")
    motivation_driver = db.Column(db.String(120), default="课程掌握与项目展示")
    engagement_pattern = db.Column(db.String(120), default="阶段学习 + 测评复盘")
    weak_points = db.Column(db.Text, default="")
    raw_dialogue = db.Column(db.Text, default="")
    preferred_resource_types = db.Column(db.JSON, default=list)
    weekly_time_minutes = db.Column(db.Integer)
    practice_level = db.Column(db.String(40), default="beginner")
    current_version_id = db.Column(
        db.Integer,
        db.ForeignKey("profile_versions.id", ondelete="SET NULL"),
        index=True,
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="profile")
    current_version = db.relationship("ProfileVersion", foreign_keys=[current_version_id], post_update=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "topic": self.topic,
            "major": self.major,
            "knowledge_level": self.knowledge_level,
            "learning_goal": self.learning_goal,
            "learning_style": self.learning_style,
            "cognitive_preference": self.cognitive_preference,
            "prior_experience": self.prior_experience,
            "time_availability": self.time_availability,
            "motivation_driver": self.motivation_driver,
            "engagement_pattern": self.engagement_pattern,
            "weak_points": self.weak_points,
            "raw_dialogue": self.raw_dialogue,
            "preferred_resource_types": self.preferred_resource_types or [],
            "weekly_time_minutes": self.weekly_time_minutes,
            "practice_level": self.practice_level,
            "current_version_id": self.current_version_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ProfileVersion(db.Model):
    __tablename__ = "profile_versions"
    __table_args__ = (
        db.UniqueConstraint("user_id", "version", name="uq_profile_version_user_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    snapshot_json = db.Column(db.JSON, nullable=False)
    change_summary = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    evidence = db.relationship(
        "ProfileEvidence",
        back_populates="profile_version",
        cascade="all, delete-orphan",
        order_by="ProfileEvidence.id",
    )

    def to_dict(self, include_evidence: bool = False) -> dict:
        payload = {
            "id": self.id,
            "user_id": self.user_id,
            "version": self.version,
            "snapshot": self.snapshot_json or {},
            "change_summary": self.change_summary or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_evidence:
            payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


class ProfileEvidence(db.Model):
    __tablename__ = "profile_evidence"
    __table_args__ = (
        db.CheckConstraint(
            "evidence_type IN ('dialogue','assessment','question_error','tutor_session',"
            "'learning_behavior','resource_feedback','migration_snapshot')",
            name="ck_profile_evidence_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_version_id = db.Column(
        db.Integer,
        db.ForeignKey("profile_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension = db.Column(db.String(80), nullable=False)
    old_value_json = db.Column(db.JSON)
    new_value_json = db.Column(db.JSON)
    evidence_type = db.Column(db.String(40), nullable=False)
    evidence_source_id = db.Column(db.String(120), default="")
    evidence_description = db.Column(db.Text, default="")
    confidence = db.Column(db.Float, default=1.0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    profile_version = db.relationship("ProfileVersion", back_populates="evidence")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "profile_version_id": self.profile_version_id,
            "dimension": self.dimension,
            "old_value": self.old_value_json,
            "new_value": self.new_value_json,
            "evidence_type": self.evidence_type,
            "evidence_source_id": self.evidence_source_id or "",
            "evidence_description": self.evidence_description or "",
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="draft", nullable=False)
    source_coverage = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    chapters = db.relationship(
        "Chapter",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Chapter.chapter_order",
    )

    def to_dict(self, include_chapters: bool = False) -> dict:
        payload = {
            "id": self.id,
            "code": self.code,
            "title": self.title,
            "description": self.description or "",
            "status": self.status,
            "source_coverage": self.source_coverage or {},
            "chapter_count": len(self.chapters),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_chapters:
            payload["chapters"] = [chapter.to_dict(include_knowledge_points=True) for chapter in self.chapters]
        return payload


class Chapter(db.Model):
    __tablename__ = "chapters"
    __table_args__ = (
        db.UniqueConstraint("course_id", "chapter_order", name="uq_chapter_course_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    chapter_order = db.Column(db.Integer, nullable=False)
    start_page = db.Column(db.Integer)
    end_page = db.Column(db.Integer)
    summary = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    course = db.relationship("Course", back_populates="chapters")
    knowledge_points = db.relationship(
        "KnowledgePoint",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="KnowledgePoint.code",
    )

    def to_dict(self, include_knowledge_points: bool = False) -> dict:
        payload = {
            "id": self.id,
            "course_id": self.course_id,
            "title": self.title,
            "chapter_order": self.chapter_order,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "summary": self.summary or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_knowledge_points:
            payload["knowledge_points"] = [point.to_dict() for point in self.knowledge_points]
        return payload


class KnowledgePoint(db.Model):
    __tablename__ = "knowledge_points"
    __table_args__ = (
        db.UniqueConstraint("course_id", "code", name="uq_knowledge_point_course_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)
    code = db.Column(db.String(80), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    difficulty = db.Column(db.String(30), default="beginner", nullable=False)
    learning_objectives_json = db.Column(db.JSON, default=list)
    aliases_json = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    course = db.relationship("Course")
    chapter = db.relationship("Chapter", back_populates="knowledge_points")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "chapter_id": self.chapter_id,
            "code": self.code,
            "name": self.name,
            "description": self.description or "",
            "difficulty": self.difficulty,
            "learning_objectives": self.learning_objectives_json or [],
            "aliases": self.aliases_json or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class KnowledgeRelation(db.Model):
    __tablename__ = "knowledge_relations"
    __table_args__ = (
        db.UniqueConstraint(
            "source_knowledge_point_id",
            "target_knowledge_point_id",
            "relation_type",
            name="uq_knowledge_relation_edge",
        ),
        db.CheckConstraint(
            "relation_type IN ('prerequisite','related_to','belongs_to','confused_with','applied_to')",
            name="ck_knowledge_relation_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    source_knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relation_type = db.Column(db.String(30), nullable=False)
    strength = db.Column(db.Float, default=1.0, nullable=False)
    evidence_chunk_id = db.Column(db.Integer, db.ForeignKey("knowledge_chunks.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    source = db.relationship("KnowledgePoint", foreign_keys=[source_knowledge_point_id])
    target = db.relationship("KnowledgePoint", foreign_keys=[target_knowledge_point_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "source_knowledge_point_id": self.source_knowledge_point_id,
            "target_knowledge_point_id": self.target_knowledge_point_id,
            "relation_type": self.relation_type,
            "strength": self.strength,
            "evidence_chunk_id": self.evidence_chunk_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Resource(db.Model):
    __tablename__ = "resources"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resource_type = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resource_type": self.resource_type,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }


class ResourceInnovationAnalysis(db.Model):
    __tablename__ = "resource_innovation_analyses"
    __table_args__ = (
        db.UniqueConstraint("resource_id", name="uq_resource_innovation_analysis_resource"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False, index=True)
    status = db.Column(db.String(30), default="ready", nullable=False)
    generated_by = db.Column(db.String(120), default="")
    evaluation = db.Column(db.JSON, default=dict)
    basis = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "status": self.status,
            "generated_by": self.generated_by,
            "evaluation": self.evaluation or None,
            "basis": self.basis or None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PptRecord(db.Model):
    __tablename__ = "ppt_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    sid = db.Column(db.String(120), default="", index=True)
    title = db.Column(db.String(180), nullable=False)
    template_id = db.Column(db.String(120), default="")
    remote_url = db.Column(db.Text, default="")
    local_url = db.Column(db.Text, default="")
    local_path = db.Column(db.Text, default="")
    status = db.Column(db.String(30), default="generating", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "sid": self.sid,
            "title": self.title,
            "template_id": self.template_id,
            "remote_url": self.remote_url,
            "local_url": self.local_url,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class PptInnovationAnalysis(db.Model):
    __tablename__ = "ppt_innovation_analyses"
    __table_args__ = (
        db.UniqueConstraint("ppt_record_id", name="uq_ppt_innovation_analysis_record"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    ppt_record_id = db.Column(db.Integer, db.ForeignKey("ppt_records.id"), nullable=False, index=True)
    sid = db.Column(db.String(120), default="", index=True)
    status = db.Column(db.String(30), default="pending", nullable=False)
    generated_by = db.Column(db.String(120), default="")
    evaluation = db.Column(db.JSON, default=dict)
    basis = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "ppt_record_id": self.ppt_record_id,
            "sid": self.sid,
            "status": self.status,
            "generated_by": self.generated_by,
            "evaluation": self.evaluation or None,
            "basis": self.basis or None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class LearningPath(db.Model):
    __tablename__ = "learning_paths"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    versions = db.relationship(
        "LearningPathVersion",
        back_populates="path",
        cascade="all, delete-orphan",
        order_by="LearningPathVersion.version_number",
    )

    def to_dict(self, include_version: bool = False) -> dict:
        payload = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
        }
        if include_version:
            latest = self.versions[-1] if self.versions else None
            payload["latest_version"] = latest.to_dict(include_nodes=True) if latest else None
        return payload


class LearningEvent(db.Model):
    __tablename__ = "learning_events"
    __table_args__ = (
        db.UniqueConstraint("user_id", "event_key", name="uq_learning_event_user_key"),
        db.CheckConstraint(
            "event_type IN ("
            "'question_correct','question_wrong','question_partial','assessment_complete',"
            "'hint_request','resource_open','resource_complete','node_open','node_complete',"
            "'code_run','code_error','tutor_help','replan_trigger','learning_block_detected'"
            ")",
            name="ck_learning_event_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_key = db.Column(db.String(220), nullable=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    path_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_paths.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    path_version_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    question_id = db.Column(db.String(120), default="")
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type = db.Column(db.String(60), default="", nullable=False)
    source_id = db.Column(db.String(120), default="", nullable=False)
    value_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    knowledge_point = db.relationship("KnowledgePoint")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_key": self.event_key or "",
            "event_type": self.event_type,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": self.knowledge_point.name if self.knowledge_point else "",
            "path_id": self.path_id,
            "path_version_id": self.path_version_id,
            "node_id": self.node_id,
            "resource_id": self.resource_id,
            "question_id": self.question_id or "",
            "assessment_id": self.assessment_id,
            "source_type": self.source_type or "",
            "source_id": self.source_id or "",
            "value": self.value_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserKnowledgeMastery(db.Model):
    __tablename__ = "user_knowledge_mastery"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "knowledge_point_id",
            name="uq_user_knowledge_mastery_user_point",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mastery_score = db.Column(db.Float, nullable=False, default=50.0)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    alpha = db.Column(db.Float, nullable=False, default=1.0)
    beta = db.Column(db.Float, nullable=False, default=1.0)
    evidence_weight = db.Column(db.Float, nullable=False, default=0.0)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    correct_count = db.Column(db.Integer, nullable=False, default=0)
    wrong_count = db.Column(db.Integer, nullable=False, default=0)
    partial_count = db.Column(db.Integer, nullable=False, default=0)
    hint_count = db.Column(db.Integer, nullable=False, default=0)
    assessment_count = db.Column(db.Integer, nullable=False, default=0)
    last_event_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    knowledge_point = db.relationship("KnowledgePoint")
    evidence = db.relationship(
        "MasteryEvidence",
        back_populates="mastery",
        cascade="all, delete-orphan",
        order_by="MasteryEvidence.created_at",
    )

    def to_dict(self, include_evidence: bool = False) -> dict:
        state = "assessed" if self.confidence >= 0.5 else "insufficient_evidence"
        payload = {
            "id": self.id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": self.knowledge_point.name if self.knowledge_point else "",
            "knowledge_point_code": self.knowledge_point.code if self.knowledge_point else "",
            "chapter_id": self.knowledge_point.chapter_id if self.knowledge_point else None,
            "mastery_score": round(float(self.mastery_score), 2),
            "confidence": round(float(self.confidence), 4),
            "state": state,
            "attempt_count": self.attempt_count,
            "correct_count": self.correct_count,
            "wrong_count": self.wrong_count,
            "partial_count": self.partial_count,
            "hint_count": self.hint_count,
            "assessment_count": self.assessment_count,
            "last_event_id": self.last_event_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_evidence:
            payload["evidence"] = [row.to_dict() for row in reversed(self.evidence)]
        return payload


class MasteryEvidence(db.Model):
    __tablename__ = "mastery_evidence"
    __table_args__ = (
        db.UniqueConstraint("mastery_id", "event_id", name="uq_mastery_evidence_event"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mastery_id = db.Column(
        db.Integer,
        db.ForeignKey("user_knowledge_mastery.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_score = db.Column(db.Float, nullable=False)
    new_score = db.Column(db.Float, nullable=False)
    delta = db.Column(db.Float, nullable=False)
    evidence_type = db.Column(db.String(40), nullable=False)
    weight = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    mastery = db.relationship("UserKnowledgeMastery", back_populates="evidence")
    event = db.relationship("LearningEvent")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_id": self.event_id,
            "event_type": self.event.event_type if self.event else self.evidence_type,
            "old_score": round(float(self.old_score), 2),
            "new_score": round(float(self.new_score), 2),
            "delta": round(float(self.delta), 2),
            "evidence_type": self.evidence_type,
            "weight": self.weight,
            "description": self.description or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class LearningPathVersion(db.Model):
    __tablename__ = "learning_path_versions"
    __table_args__ = (
        db.UniqueConstraint("path_id", "version_number", name="uq_learning_path_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    path_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number = db.Column(db.Integer, nullable=False)
    parent_version_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason_event_id = db.Column(db.Integer, nullable=True, index=True)
    replanning_reason = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    path = db.relationship("LearningPath", back_populates="versions")
    parent_version = db.relationship("LearningPathVersion", remote_side=[id])
    nodes = db.relationship(
        "LearningPathNode",
        back_populates="path_version",
        cascade="all, delete-orphan",
        order_by="LearningPathNode.node_order",
    )

    def to_dict(self, include_nodes: bool = False) -> dict:
        payload = {
            "id": self.id,
            "path_id": self.path_id,
            "version_number": self.version_number,
            "parent_version_id": self.parent_version_id,
            "reason_event_id": self.reason_event_id,
            "replanning_reason": self.replanning_reason or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_nodes:
            payload["nodes"] = [node.to_dict(include_resources=True) for node in self.nodes]
        return payload


class LearningPathNode(db.Model):
    __tablename__ = "learning_path_nodes"
    __table_args__ = (
        db.UniqueConstraint("path_version_id", "node_order", name="uq_learning_path_node_order"),
        db.CheckConstraint(
            "status IN ('locked','ready','learning','completed','remediation')",
            name="ck_learning_path_node_status",
        ),
        db.CheckConstraint(
            "node_type IN ('normal','review','remediation','assessment')",
            name="ck_learning_path_node_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    path_version_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_order = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="locked")
    difficulty = db.Column(db.String(30), nullable=False, default="beginner")
    mastery_before = db.Column(db.Float, nullable=True)
    mastery_target = db.Column(db.Float, nullable=False, default=70.0)
    estimated_minutes = db.Column(db.Integer, nullable=False, default=30)
    reason = db.Column(db.Text, default="")
    node_type = db.Column(db.String(30), nullable=False, default="normal")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    path_version = db.relationship("LearningPathVersion", back_populates="nodes")
    knowledge_point = db.relationship("KnowledgePoint")
    resources = db.relationship(
        "NodeResource",
        back_populates="node",
        cascade="all, delete-orphan",
        order_by="NodeResource.priority",
    )

    def to_dict(self, include_resources: bool = False) -> dict:
        payload = {
            "id": self.id,
            "path_version_id": self.path_version_id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": self.knowledge_point.name if self.knowledge_point else "",
            "knowledge_point_code": self.knowledge_point.code if self.knowledge_point else "",
            "node_order": self.node_order,
            "status": self.status,
            "difficulty": self.difficulty,
            "mastery_before": self.mastery_before,
            "mastery_target": self.mastery_target,
            "estimated_minutes": self.estimated_minutes,
            "reason": self.reason or "",
            "node_type": self.node_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_resources:
            payload["resources"] = [item.to_dict() for item in self.resources]
        return payload


class NodeResource(db.Model):
    __tablename__ = "node_resources"
    __table_args__ = (
        db.UniqueConstraint("node_id", "resource_id", name="uq_node_resource"),
    )

    id = db.Column(db.Integer, primary_key=True)
    node_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type = db.Column(db.String(80), nullable=False)
    priority = db.Column(db.Integer, nullable=False, default=1)
    personalization_reason = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    node = db.relationship("LearningPathNode", back_populates="resources")
    resource = db.relationship("Resource")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "priority": self.priority,
            "personalization_reason": self.personalization_reason or "",
            "resource": self.resource.to_dict() if self.resource else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AgentRun(db.Model):
    __tablename__ = "agent_runs"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('running','passed','failed','revised')",
            name="ck_agent_run_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type = db.Column(db.String(60), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="running")
    input_json = db.Column(db.JSON, default=dict)
    output_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    steps = db.relationship(
        "AgentStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AgentStep.sequence",
    )

    def to_dict(self, include_steps: bool = False) -> dict:
        payload = {
            "id": self.id,
            "task_type": self.task_type,
            "status": self.status,
            "input": self.input_json or {},
            "output": self.output_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_steps:
            payload["steps"] = [step.to_dict() for step in self.steps]
        return payload


class AgentStep(db.Model):
    __tablename__ = "agent_steps"
    __table_args__ = (
        db.UniqueConstraint("run_id", "sequence", name="uq_agent_step_run_sequence"),
        db.CheckConstraint(
            "status IN ('running','passed','failed','revised','skipped')",
            name="ck_agent_step_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence = db.Column(db.Integer, nullable=False)
    agent_name = db.Column(db.String(60), nullable=False)
    action = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="running")
    input_json = db.Column(db.JSON, default=dict)
    output_json = db.Column(db.JSON, default=dict)
    evidence_count = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    run = db.relationship("AgentRun", back_populates="steps")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "agent_name": self.agent_name,
            "action": self.action,
            "status": self.status,
            "input": self.input_json or {},
            "output": self.output_json or {},
            "evidence_count": self.evidence_count,
            "error_message": self.error_message or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class RemediationPlan(db.Model):
    __tablename__ = "remediation_plans"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ready','active','completed','adjusted')",
            name="ck_remediation_plan_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path_version_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_versions.id", ondelete="SET NULL"),
        index=True,
    )
    agent_run_id = db.Column(
        db.Integer,
        db.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        index=True,
    )
    status = db.Column(db.String(30), nullable=False, default="ready")
    initial_mastery = db.Column(db.Float)
    target_mastery = db.Column(db.Float, nullable=False, default=60.0)
    estimated_minutes = db.Column(db.Integer, nullable=False, default=40)
    reason = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    target_knowledge_point = db.relationship("KnowledgePoint")
    path_version = db.relationship("LearningPathVersion")
    agent_run = db.relationship("AgentRun")
    steps = db.relationship(
        "RemediationPlanStep",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="RemediationPlanStep.step_order",
    )

    def to_dict(self, include_steps: bool = True) -> dict:
        current_mastery = UserKnowledgeMastery.query.filter_by(
            user_id=self.user_id,
            knowledge_point_id=self.target_knowledge_point_id,
        ).first()
        payload = {
            "id": self.id,
            "target_knowledge_point_id": self.target_knowledge_point_id,
            "target_knowledge_point": (
                self.target_knowledge_point.name
                if self.target_knowledge_point
                else ""
            ),
            "path_version_id": self.path_version_id,
            "path_version_number": (
                self.path_version.version_number if self.path_version else None
            ),
            "agent_run_id": self.agent_run_id,
            "status": self.status,
            "initial_mastery": self.initial_mastery,
            "current_mastery": (
                round(float(current_mastery.mastery_score), 2)
                if current_mastery
                else None
            ),
            "target_mastery": self.target_mastery,
            "estimated_minutes": self.estimated_minutes,
            "reason": self.reason or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_steps:
            payload["steps"] = [step.to_dict() for step in self.steps]
        return payload


class RemediationPlanStep(db.Model):
    __tablename__ = "remediation_plan_steps"
    __table_args__ = (
        db.UniqueConstraint(
            "plan_id",
            "step_order",
            name="uq_remediation_plan_step_order",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(
        db.Integer,
        db.ForeignKey("remediation_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_nodes.id", ondelete="SET NULL"),
        index=True,
    )
    step_order = db.Column(db.Integer, nullable=False)
    step_type = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    estimated_minutes = db.Column(db.Integer, nullable=False, default=10)
    reason = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    plan = db.relationship("RemediationPlan", back_populates="steps")
    node = db.relationship("LearningPathNode")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "plan_id": self.plan_id,
            "node_id": self.node_id,
            "step_order": self.step_order,
            "step_type": self.step_type,
            "title": self.title,
            "estimated_minutes": self.estimated_minutes,
            "reason": self.reason or "",
            "status": self.node.status if self.node else "pending",
            "resource": (
                self.node.resources[0].to_dict()
                if self.node and self.node.resources
                else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AdaptiveExam(db.Model):
    __tablename__ = "adaptive_exams"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('blueprint','ready','in_progress','completed')",
            name="ck_adaptive_exam_status",
        ),
        db.CheckConstraint(
            "goal IN ('diagnosis','reinforcement','mock','comprehensive','transfer')",
            name="ck_adaptive_exam_goal",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("courses.id", ondelete="SET NULL"),
        index=True,
    )
    result_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    agent_run_id = db.Column(
        db.Integer,
        db.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        index=True,
    )
    duration_minutes = db.Column(db.Integer, nullable=False)
    goal = db.Column(db.String(30), nullable=False)
    difficulty = db.Column(db.String(30), nullable=False, default="intermediate")
    status = db.Column(db.String(30), nullable=False, default="blueprint")
    blueprint_json = db.Column(db.JSON, nullable=False, default=dict)
    quiz_json = db.Column(db.JSON, default=dict)
    pre_mastery_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    course = db.relationship("Course")
    result = db.relationship("QuizResult")
    agent_run = db.relationship("AgentRun")

    def to_dict(self, include_quiz: bool = True) -> dict:
        payload = {
            "id": self.id,
            "course_id": self.course_id,
            "course": self.course.title if self.course else "",
            "result_id": self.result_id,
            "agent_run_id": self.agent_run_id,
            "duration_minutes": self.duration_minutes,
            "goal": self.goal,
            "difficulty": self.difficulty,
            "status": self.status,
            "blueprint": self.blueprint_json or {},
            "pre_mastery": self.pre_mastery_json or {},
            "result": self.result.to_dict() if self.result else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_quiz:
            payload["quiz"] = self.quiz_json or {}
        return payload


class CognitiveDiagnosis(db.Model):
    __tablename__ = "cognitive_diagnoses"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "assessment_id",
            "question_id",
            name="uq_cognitive_diagnosis_question",
        ),
        db.CheckConstraint(
            "overall_status IN ('no_error','root_error','insufficient_evidence')",
            name="ck_cognitive_diagnosis_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = db.Column(db.String(120), nullable=False)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    first_error_step = db.Column(db.Integer)
    root_cause_knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    overall_status = db.Column(db.String(40), nullable=False)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    summary = db.Column(db.Text, default="")
    propagation_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    knowledge_point = db.relationship(
        "KnowledgePoint",
        foreign_keys=[knowledge_point_id],
    )
    root_cause_knowledge_point = db.relationship(
        "KnowledgePoint",
        foreign_keys=[root_cause_knowledge_point_id],
    )
    assessment = db.relationship("QuizResult")
    steps = db.relationship(
        "CognitiveStep",
        back_populates="diagnosis",
        cascade="all, delete-orphan",
        order_by="CognitiveStep.step_index",
    )

    def to_dict(self, include_steps: bool = True) -> dict:
        payload = {
            "id": self.id,
            "assessment_id": self.assessment_id,
            "question_id": self.question_id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "first_error_step": self.first_error_step,
            "root_cause_knowledge_point_id": self.root_cause_knowledge_point_id,
            "root_cause_knowledge_point": (
                self.root_cause_knowledge_point.name
                if self.root_cause_knowledge_point
                else ""
            ),
            "overall_status": self.overall_status,
            "confidence": round(float(self.confidence), 4),
            "summary": self.summary or "",
            "propagation": self.propagation_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_steps:
            payload["steps"] = [step.to_dict() for step in self.steps]
        return payload


class CognitiveStep(db.Model):
    __tablename__ = "cognitive_steps"
    __table_args__ = (
        db.UniqueConstraint(
            "diagnosis_id",
            "step_index",
            name="uq_cognitive_step_index",
        ),
        db.CheckConstraint(
            "status IN ('correct','incorrect','uncertain','not_observed')",
            name="ck_cognitive_step_status",
        ),
        db.CheckConstraint(
            "error_role IN ('none','root_error','derived_error','independent_error','uncertain')",
            name="ck_cognitive_step_error_role",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    diagnosis_id = db.Column(
        db.Integer,
        db.ForeignKey("cognitive_diagnoses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_index = db.Column(db.Integer, nullable=False)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    concept = db.Column(db.String(180), default="")
    expected_text = db.Column(db.Text, default="")
    student_text = db.Column(db.Text, default="")
    status = db.Column(db.String(30), nullable=False)
    error_role = db.Column(db.String(30), nullable=False, default="none")
    error_type = db.Column(db.String(80), default="")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    evidence_json = db.Column(db.JSON, default=list)
    course_sources_json = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    diagnosis = db.relationship("CognitiveDiagnosis", back_populates="steps")
    knowledge_point = db.relationship("KnowledgePoint")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "diagnosis_id": self.diagnosis_id,
            "step_index": self.step_index,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "concept": self.concept or "",
            "expected": self.expected_text or "",
            "student": self.student_text or "",
            "status": self.status,
            "error_role": self.error_role,
            "error_type": self.error_type or "",
            "confidence": round(float(self.confidence), 4),
            "evidence": self.evidence_json or [],
            "course_sources": self.course_sources_json or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Misconception(db.Model):
    __tablename__ = "misconceptions"
    __table_args__ = (
        db.UniqueConstraint("course_id", "code", name="uq_misconception_course_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(
        db.Integer,
        db.ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = db.Column(db.String(100), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default="")
    correction_strategy = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    knowledge_point = db.relationship("KnowledgePoint")
    course = db.relationship("Course")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "code": self.code,
            "name": self.name,
            "description": self.description or "",
            "correction_strategy": self.correction_strategy or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserMisconception(db.Model):
    __tablename__ = "user_misconceptions"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "misconception_id",
            name="uq_user_misconception",
        ),
        db.CheckConstraint(
            "status IN ('suspected','confirmed','improving','resolved')",
            name="ck_user_misconception_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    misconception_id = db.Column(
        db.Integer,
        db.ForeignKey("misconceptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = db.Column(db.String(30), nullable=False, default="suspected")
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    evidence_count = db.Column(db.Integer, nullable=False, default=0)
    first_detected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_detected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)

    misconception = db.relationship("Misconception")
    evidence = db.relationship(
        "MisconceptionEvidence",
        back_populates="user_misconception",
        cascade="all, delete-orphan",
        order_by="MisconceptionEvidence.created_at",
    )

    def to_dict(self, include_evidence: bool = True) -> dict:
        payload = {
            "id": self.id,
            "misconception": (
                self.misconception.to_dict() if self.misconception else None
            ),
            "status": self.status,
            "confidence": round(float(self.confidence), 4),
            "evidence_count": self.evidence_count,
            "first_detected_at": (
                self.first_detected_at.isoformat()
                if self.first_detected_at
                else None
            ),
            "last_detected_at": (
                self.last_detected_at.isoformat()
                if self.last_detected_at
                else None
            ),
            "resolved_at": (
                self.resolved_at.isoformat() if self.resolved_at else None
            ),
        }
        if include_evidence:
            payload["evidence"] = [
                item.to_dict() for item in reversed(self.evidence)
            ]
        return payload


class MisconceptionEvidence(db.Model):
    __tablename__ = "misconception_evidence"
    __table_args__ = (
        db.UniqueConstraint(
            "user_misconception_id",
            "source_type",
            "source_id",
            name="uq_misconception_evidence_source",
        ),
        db.CheckConstraint(
            "source_type IN ('question_wrong','reasoning_step','assessment','tutor_response','hint_request','code_error','transfer_question','correct_response')",
            name="ck_misconception_evidence_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_misconception_id = db.Column(
        db.Integer,
        db.ForeignKey("user_misconceptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cognitive_step_id = db.Column(
        db.Integer,
        db.ForeignKey("cognitive_steps.id", ondelete="SET NULL"),
        index=True,
    )
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    source_type = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    payload_json = db.Column(db.JSON, default=dict)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user_misconception = db.relationship(
        "UserMisconception",
        back_populates="evidence",
    )
    cognitive_step = db.relationship("CognitiveStep")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "cognitive_step_id": self.cognitive_step_id,
            "assessment_id": self.assessment_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "description": self.description or "",
            "payload": self.payload_json or {},
            "confidence": round(float(self.confidence), 4),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TeachingStrategyDecision(db.Model):
    __tablename__ = "teaching_strategy_decisions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    agent_run_id = db.Column(
        db.Integer,
        db.ForeignKey("agent_runs.id", ondelete="SET NULL"),
        index=True,
    )
    strategy_type = db.Column(db.String(60), nullable=False, index=True)
    previous_strategy_type = db.Column(db.String(60), default="")
    reason_codes_json = db.Column(db.JSON, default=list)
    actions_json = db.Column(db.JSON, default=list)
    input_snapshot_json = db.Column(db.JSON, default=dict)
    switched = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    knowledge_point = db.relationship("KnowledgePoint")
    assessment = db.relationship("QuizResult")
    agent_run = db.relationship("AgentRun")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "assessment_id": self.assessment_id,
            "agent_run_id": self.agent_run_id,
            "strategy": self.strategy_type,
            "previous_strategy": self.previous_strategy_type or "",
            "reason_codes": self.reason_codes_json or [],
            "actions": self.actions_json or [],
            "input_snapshot": self.input_snapshot_json or {},
            "switched": bool(self.switched),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TeachingIntervention(db.Model):
    __tablename__ = "teaching_interventions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active','completed','cancelled')",
            name="ck_teaching_intervention_status",
        ),
        db.CheckConstraint(
            "block_type IN ('KNOWLEDGE_GAP','MISCONCEPTION','PROCESS_ERROR','REPEATED_FAILURE','TRANSFER_FAILURE','INSUFFICIENT_EVIDENCE')",
            name="ck_teaching_intervention_block_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_decision_id = db.Column(
        db.Integer,
        db.ForeignKey("teaching_strategy_decisions.id", ondelete="SET NULL"),
        index=True,
    )
    resource_id = db.Column(
        db.Integer,
        db.ForeignKey("resources.id", ondelete="SET NULL"),
        index=True,
    )
    path_node_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_nodes.id", ondelete="SET NULL"),
        index=True,
    )
    path_version_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_path_versions.id", ondelete="SET NULL"),
        index=True,
    )
    trigger_event_id = db.Column(
        db.Integer,
        db.ForeignKey("learning_events.id", ondelete="SET NULL"),
        index=True,
    )
    assessment_before = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    assessment_after = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    strategy_type = db.Column(db.String(60), nullable=False)
    block_type = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="active")
    mastery_before = db.Column(db.Float)
    mastery_after = db.Column(db.Float)
    confidence_before = db.Column(db.Float)
    confidence_after = db.Column(db.Float)
    observed_gain = db.Column(db.Float)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    finished_at = db.Column(db.DateTime)

    knowledge_point = db.relationship("KnowledgePoint")
    strategy_decision = db.relationship("TeachingStrategyDecision")
    resource = db.relationship("Resource")
    path_node = db.relationship("LearningPathNode")
    path_version = db.relationship("LearningPathVersion")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "strategy_decision_id": self.strategy_decision_id,
            "strategy_type": self.strategy_type,
            "block_type": self.block_type,
            "status": self.status,
            "resource_id": self.resource_id,
            "resource": self.resource.to_dict() if self.resource else None,
            "path_node_id": self.path_node_id,
            "path_version_id": self.path_version_id,
            "path_version_number": (
                self.path_version.version_number if self.path_version else None
            ),
            "trigger_event_id": self.trigger_event_id,
            "assessment_before": self.assessment_before,
            "assessment_after": self.assessment_after,
            "mastery_before": self.mastery_before,
            "mastery_after": self.mastery_after,
            "confidence_before": self.confidence_before,
            "confidence_after": self.confidence_after,
            "observed_gain": self.observed_gain,
            "effect_statement": (
                f"完成 {self.strategy_type} 干预后，后续测评观察到 Mastery "
                f"从 {round(self.mastery_before, 2)}% 变为 {round(self.mastery_after, 2)}%"
                if self.mastery_before is not None and self.mastery_after is not None
                else "等待后续测评观察学习变化"
            ),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class TeachingStrategyStat(db.Model):
    __tablename__ = "teaching_strategy_stats"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "strategy_type",
            name="uq_teaching_strategy_stat",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    strategy_type = db.Column(db.String(60), nullable=False, index=True)
    use_count = db.Column(db.Integer, nullable=False, default=0)
    completed_count = db.Column(db.Integer, nullable=False, default=0)
    average_observed_gain = db.Column(db.Float, nullable=False, default=0.0)
    gain_variance = db.Column(db.Float, nullable=False, default=0.0)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    stability = db.Column(db.String(30), nullable=False, default="insufficient")
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_type": self.strategy_type,
            "use_count": self.use_count,
            "completed_count": self.completed_count,
            "average_observed_gain": round(
                float(self.average_observed_gain),
                2,
            ),
            "gain_variance": round(float(self.gain_variance), 4),
            "confidence": round(float(self.confidence), 4),
            "stability": self.stability,
            "minimum_evidence_met": self.completed_count >= 3,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class MasteryDimension(db.Model):
    __tablename__ = "mastery_dimensions"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "knowledge_point_id",
            "dimension",
            name="uq_mastery_dimension",
        ),
        db.CheckConstraint(
            "dimension IN ('conceptual_understanding','procedural_application','reasoning','coding','transfer')",
            name="ck_mastery_dimension_type",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dimension = db.Column(db.String(50), nullable=False, index=True)
    mastery_score = db.Column(db.Float, nullable=False, default=50.0)
    confidence = db.Column(db.Float, nullable=False, default=0.0)
    alpha = db.Column(db.Float, nullable=False, default=1.0)
    beta = db.Column(db.Float, nullable=False, default=1.0)
    evidence_count = db.Column(db.Integer, nullable=False, default=0)
    last_assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    knowledge_point = db.relationship("KnowledgePoint")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "dimension": self.dimension,
            "mastery_score": round(float(self.mastery_score), 2),
            "confidence": round(float(self.confidence), 4),
            "evidence_count": self.evidence_count,
            "last_assessment_id": self.last_assessment_id,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TransferAssessment(db.Model):
    __tablename__ = "transfer_assessments"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "result_id",
            "knowledge_point_id",
            name="uq_transfer_assessment_result_point",
        ),
        db.CheckConstraint(
            "status IN ('ready','completed')",
            name="ck_transfer_assessment_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    adaptive_exam_id = db.Column(
        db.Integer,
        db.ForeignKey("adaptive_exams.id", ondelete="SET NULL"),
        index=True,
    )
    result_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="SET NULL"),
        index=True,
    )
    status = db.Column(db.String(30), nullable=False, default="ready")
    levels_json = db.Column(db.JSON, default=dict)
    score = db.Column(db.Float)
    passed = db.Column(db.Boolean, nullable=False, default=False)
    capability_state = db.Column(db.String(40), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)

    knowledge_point = db.relationship("KnowledgePoint")
    adaptive_exam = db.relationship("AdaptiveExam")
    result = db.relationship("QuizResult")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "adaptive_exam_id": self.adaptive_exam_id,
            "result_id": self.result_id,
            "status": self.status,
            "levels": self.levels_json or {},
            "score": self.score,
            "passed": bool(self.passed),
            "capability_state": self.capability_state or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class SelfConfidenceRecord(db.Model):
    __tablename__ = "self_confidence_records"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "assessment_id",
            "question_id",
            name="uq_self_confidence_question",
        ),
        db.CheckConstraint(
            "calibration_signal IN ('calibrated','overconfidence','underconfidence','insufficient')",
            name="ck_self_confidence_signal",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id = db.Column(
        db.Integer,
        db.ForeignKey("quiz_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id = db.Column(db.String(120), nullable=False)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    self_confidence = db.Column(db.Integer, nullable=False)
    actual_score = db.Column(db.Float, nullable=False)
    calibration_signal = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    knowledge_point = db.relationship("KnowledgePoint")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "assessment_id": self.assessment_id,
            "question_id": self.question_id,
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": (
                self.knowledge_point.name if self.knowledge_point else ""
            ),
            "self_confidence": self.self_confidence,
            "actual_score": round(float(self.actual_score), 4),
            "calibration_signal": self.calibration_signal,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class QuizResult(db.Model):
    __tablename__ = "quiz_results"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    quiz_content = db.Column(db.Text, nullable=False)
    answers = db.Column(db.JSON, default=dict)
    score = db.Column(db.Float, default=0)
    wrong_questions = db.Column(db.Text, default="")
    analysis = db.Column(db.Text, default="")
    category = db.Column(db.String(20), default="exercise", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "quiz_content": self.quiz_content,
            "answers": self.answers or {},
            "score": self.score,
            "wrong_questions": self.wrong_questions,
            "analysis": self.analysis,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
        }


class KnowledgeDocument(db.Model):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        db.UniqueConstraint("user_id", "content_hash", name="uq_knowledge_document_user_hash"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.id", ondelete="SET NULL"), index=True)
    title = db.Column(db.String(180), nullable=False)
    doc_type = db.Column(db.String(20), default='文本')
    source_filename = db.Column(db.String(255), default="")
    source_type = db.Column(db.String(30), default="upload", nullable=False)
    processing_status = db.Column(db.String(30), default="parsed", nullable=False)
    page_count = db.Column(db.Integer, default=0, nullable=False)
    content_hash = db.Column(db.String(64), index=True)
    metadata_json = db.Column(db.JSON, default=dict)
    content = db.Column(db.Text, nullable=False)
    chunks = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    course = db.relationship("Course")
    chapter = db.relationship("Chapter")
    structured_chunks = db.relationship(
        "KnowledgeChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="KnowledgeChunk.chunk_index",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "course_id": self.course_id,
            "chapter_id": self.chapter_id,
            "title": self.title,
            "doc_type": self.doc_type or '文本',
            "source_filename": self.source_filename or self.title,
            "source_type": self.source_type,
            "processing_status": self.processing_status,
            "page_count": self.page_count,
            "content_hash": self.content_hash,
            "metadata": self.metadata_json or {},
            "content": self.content,
            "chunks": self.chunks or [],
            "structured_chunks": [chunk.to_dict() for chunk in self.structured_chunks],
            "created_at": self.created_at.isoformat(),
        }


class KnowledgeChunk(db.Model):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        db.UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunk_document_index"),
    )

    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), index=True)
    chapter_id = db.Column(db.Integer, db.ForeignKey("chapters.id", ondelete="SET NULL"), index=True)
    knowledge_point_id = db.Column(
        db.Integer,
        db.ForeignKey("knowledge_points.id", ondelete="SET NULL"),
        index=True,
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    page_start = db.Column(db.Integer)
    page_end = db.Column(db.Integer)
    section = db.Column(db.String(180), default="")
    chunk_text = db.Column(db.Text, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False, index=True)
    vector_ref = db.Column(db.String(180), default="")
    metadata_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    document = db.relationship("KnowledgeDocument", back_populates="structured_chunks")
    course = db.relationship("Course")
    chapter = db.relationship("Chapter")
    knowledge_point = db.relationship("KnowledgePoint")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "course_id": self.course_id,
            "course_title": self.course.title if self.course else "",
            "chapter_id": self.chapter_id,
            "chapter": self.chapter.title if self.chapter else "",
            "knowledge_point_id": self.knowledge_point_id,
            "knowledge_point": self.knowledge_point.name if self.knowledge_point else "",
            "chunk_index": self.chunk_index,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "section": self.section or "",
            "content": self.chunk_text,
            "chunk_text": self.chunk_text,
            "content_hash": self.content_hash,
            "vector_ref": self.vector_ref or "",
            "metadata": self.metadata_json or {},
        }


class ChatConversation(db.Model):
    __tablename__ = "chat_conversations"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(180), nullable=False, default="新学习辅导")
    messages = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "messages": self.messages or [],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class CodingCaseRecord(db.Model):
    __tablename__ = "coding_case_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    resource_id = db.Column(db.Integer, db.ForeignKey("resources.id"), nullable=False)
    case_content = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False, default="")
    score = db.Column(db.Float, default=0)
    is_passed = db.Column(db.Boolean, default=False)
    analysis = db.Column(db.Text, default="")
    reference_answer = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "case_content": self.case_content,
            "answer": self.answer,
            "score": self.score,
            "is_passed": self.is_passed,
            "analysis": self.analysis,
            "reference_answer": self.reference_answer,
            "created_at": self.created_at.isoformat(),
        }


class TaskActionLog(db.Model):
    """记录用户今日任务相关行为（页面访问、做题等），用于判断任务完成状态"""
    __tablename__ = "task_action_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    action = db.Column(db.String(50), nullable=False)  # visit_path, visit_quiz, visit_resources
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
