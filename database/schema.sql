-- Multi_Agent-Study-Assistant 数据库建表脚本（修正版）
-- 适用数据库：MySQL 8.x
-- 编码：UTF-8 / utf8mb4
-- 注意：此文件仅用于查看或手工创建全新数据库。
-- 已有数据库必须使用 backend/migrations，并按 backend/MIGRATIONS.md 升级。
-- 修复重点：
-- 1. profiles.cognitive_preference 改为 TEXT，避免结构化测评提交时报 Data too long。
-- 2. 将可能保存 AI 生成长文本的画像字段改为 TEXT。
-- 3. 移除重复 ALTER TABLE quiz_results ADD COLUMN category，避免重复建库/导入时报错。
-- 4. 将后置索引合并进建表语句，并在底部提供兼容已有数据库的安全迁移逻辑。

CREATE DATABASE IF NOT EXISTS study_ai
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE study_ai;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(30) NOT NULL DEFAULT 'student',
  email VARCHAR(120) NOT NULL DEFAULT '',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profile_versions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  version INT NOT NULL,
  snapshot_json JSON NOT NULL,
  change_summary TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_profile_version_user_version (user_id, version),
  INDEX idx_profile_versions_user_id (user_id),
  CONSTRAINT fk_profile_versions_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profile_evidence (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  profile_version_id INT NOT NULL,
  dimension VARCHAR(80) NOT NULL,
  old_value_json JSON,
  new_value_json JSON,
  evidence_type VARCHAR(40) NOT NULL,
  evidence_source_id VARCHAR(120) DEFAULT '',
  evidence_description TEXT,
  confidence FLOAT NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_profile_evidence_user_id (user_id),
  INDEX idx_profile_evidence_version_id (profile_version_id),
  CONSTRAINT ck_profile_evidence_type CHECK (
    evidence_type IN (
      'dialogue', 'assessment', 'question_error', 'tutor_session',
      'learning_behavior', 'resource_feedback', 'migration_snapshot'
    )
  ),
  CONSTRAINT fk_profile_evidence_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_profile_evidence_version_id
    FOREIGN KEY (profile_version_id) REFERENCES profile_versions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS profiles (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL UNIQUE,
  topic VARCHAR(180) NOT NULL DEFAULT '人工智能导论',
  major VARCHAR(120) NOT NULL DEFAULT '计算机相关专业',
  knowledge_level VARCHAR(80) NOT NULL DEFAULT 'beginner',

  -- 以下字段可能承载用户画像、测评总结或 AI 生成分析，使用 TEXT 更稳妥
  learning_goal TEXT NULL,
  learning_style TEXT NULL,
  cognitive_preference TEXT NULL,
  prior_experience TEXT NULL,
  time_availability VARCHAR(120) NOT NULL DEFAULT '3-5 hours per week',
  motivation_driver TEXT NULL,
  engagement_pattern TEXT NULL,
  weak_points TEXT NULL,
  raw_dialogue TEXT NULL,
  preferred_resource_types JSON,
  weekly_time_minutes INT,
  practice_level VARCHAR(40) NOT NULL DEFAULT 'beginner',
  current_version_id INT,

  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_profiles_current_version_id (current_version_id),
  CONSTRAINT fk_profiles_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_profiles_current_version_id
    FOREIGN KEY (current_version_id) REFERENCES profile_versions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resources (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  resource_type VARCHAR(80) NOT NULL,
  title VARCHAR(180) NOT NULL,
  content LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_resources_user_id (user_id),
  INDEX idx_resources_type (resource_type),
  CONSTRAINT fk_resources_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS learning_paths (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  content LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_learning_paths_user_id (user_id),
  CONSTRAINT fk_learning_paths_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS quiz_results (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  quiz_content LONGTEXT NOT NULL,
  answers JSON,
  score FLOAT NOT NULL DEFAULT 0,
  wrong_questions TEXT,
  analysis LONGTEXT,
  category VARCHAR(20) NOT NULL DEFAULT 'exercise',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_quiz_results_user_id (user_id),
  INDEX idx_quiz_results_category (category),
  CONSTRAINT fk_quiz_results_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS courses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(80) NOT NULL UNIQUE,
  title VARCHAR(180) NOT NULL,
  description TEXT,
  status VARCHAR(30) NOT NULL DEFAULT 'draft',
  source_coverage JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_courses_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chapters (
  id INT AUTO_INCREMENT PRIMARY KEY,
  course_id INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  chapter_order INT NOT NULL,
  start_page INT,
  end_page INT,
  summary TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_chapter_course_order (course_id, chapter_order),
  INDEX idx_chapters_course_id (course_id),
  CONSTRAINT fk_chapters_course_id
    FOREIGN KEY (course_id) REFERENCES courses(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_points (
  id INT AUTO_INCREMENT PRIMARY KEY,
  course_id INT NOT NULL,
  chapter_id INT NOT NULL,
  code VARCHAR(80) NOT NULL,
  name VARCHAR(180) NOT NULL,
  description TEXT,
  difficulty VARCHAR(30) NOT NULL DEFAULT 'beginner',
  learning_objectives_json JSON,
  aliases_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_knowledge_point_course_code (course_id, code),
  INDEX idx_knowledge_points_course_id (course_id),
  INDEX idx_knowledge_points_chapter_id (chapter_id),
  CONSTRAINT fk_knowledge_points_course_id
    FOREIGN KEY (course_id) REFERENCES courses(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_points_chapter_id
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  course_id INT,
  chapter_id INT,
  title VARCHAR(180) NOT NULL,
  doc_type VARCHAR(20) DEFAULT '文本',
  source_filename VARCHAR(255) DEFAULT '',
  source_type VARCHAR(30) NOT NULL DEFAULT 'upload',
  processing_status VARCHAR(30) NOT NULL DEFAULT 'parsed',
  page_count INT NOT NULL DEFAULT 0,
  content_hash VARCHAR(64),
  metadata_json JSON,
  content LONGTEXT NOT NULL,
  chunks JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_knowledge_document_user_hash (user_id, content_hash),
  INDEX idx_knowledge_documents_user_id (user_id),
  INDEX idx_knowledge_documents_course_id (course_id),
  INDEX idx_knowledge_documents_chapter_id (chapter_id),
  INDEX idx_knowledge_documents_content_hash (content_hash),
  CONSTRAINT fk_knowledge_documents_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_documents_course_id
    FOREIGN KEY (course_id) REFERENCES courses(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_knowledge_documents_chapter_id
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  document_id INT NOT NULL,
  course_id INT,
  chapter_id INT,
  knowledge_point_id INT,
  chunk_index INT NOT NULL,
  page_start INT,
  page_end INT,
  section VARCHAR(180) DEFAULT '',
  chunk_text LONGTEXT NOT NULL,
  content_hash VARCHAR(64) NOT NULL,
  vector_ref VARCHAR(180) DEFAULT '',
  metadata_json JSON,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_knowledge_chunk_document_index (document_id, chunk_index),
  INDEX idx_knowledge_chunks_document_id (document_id),
  INDEX idx_knowledge_chunks_course_id (course_id),
  INDEX idx_knowledge_chunks_chapter_id (chapter_id),
  INDEX idx_knowledge_chunks_knowledge_point_id (knowledge_point_id),
  INDEX idx_knowledge_chunks_content_hash (content_hash),
  CONSTRAINT fk_knowledge_chunks_document_id
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_chunks_course_id
    FOREIGN KEY (course_id) REFERENCES courses(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_knowledge_chunks_chapter_id
    FOREIGN KEY (chapter_id) REFERENCES chapters(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_knowledge_chunks_knowledge_point_id
    FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_relations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  course_id INT NOT NULL,
  source_knowledge_point_id INT NOT NULL,
  target_knowledge_point_id INT NOT NULL,
  relation_type VARCHAR(30) NOT NULL,
  strength FLOAT NOT NULL DEFAULT 1,
  evidence_chunk_id INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_knowledge_relation_edge (
    source_knowledge_point_id,
    target_knowledge_point_id,
    relation_type
  ),
  INDEX idx_knowledge_relations_course_id (course_id),
  INDEX idx_knowledge_relations_source_id (source_knowledge_point_id),
  INDEX idx_knowledge_relations_target_id (target_knowledge_point_id),
  CONSTRAINT ck_knowledge_relation_type CHECK (
    relation_type IN ('prerequisite', 'related_to', 'belongs_to', 'confused_with', 'applied_to')
  ),
  CONSTRAINT fk_knowledge_relations_course_id
    FOREIGN KEY (course_id) REFERENCES courses(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_relations_source_id
    FOREIGN KEY (source_knowledge_point_id) REFERENCES knowledge_points(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_relations_target_id
    FOREIGN KEY (target_knowledge_point_id) REFERENCES knowledge_points(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_knowledge_relations_evidence_chunk_id
    FOREIGN KEY (evidence_chunk_id) REFERENCES knowledge_chunks(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- FAISS 向量索引文件存储在 uploads/vector_index/ 目录下
-- 文件命名规则: user_{user_id}.index (FAISS 索引二进制文件)
--              user_{user_id}_meta.json (分块元数据 JSON)
-- 索引在文档上传/删除时自动重建，无需数据库存储嵌入向量

-- 对话记录表（用于保存智能辅导的聊天历史）
CREATE TABLE IF NOT EXISTS chat_conversations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  title VARCHAR(180) NOT NULL DEFAULT '新学习辅导',
  messages JSON NOT NULL DEFAULT (JSON_ARRAY()),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_chat_conversations_user_id (user_id),
  INDEX idx_chat_conversations_user_id_updated_at (user_id, updated_at),
  CONSTRAINT fk_chat_conversations_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 实操案例答题记录表（保存用户答案和 AI 评分结果）
CREATE TABLE IF NOT EXISTS coding_case_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  resource_id INT NOT NULL,
  case_content LONGTEXT NOT NULL,
  answer LONGTEXT NOT NULL,
  score FLOAT NOT NULL DEFAULT 0,
  is_passed TINYINT(1) NOT NULL DEFAULT 0,
  analysis LONGTEXT,
  reference_answer LONGTEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_coding_case_records_user_id (user_id),
  INDEX idx_coding_case_records_resource_id (resource_id),
  CONSTRAINT fk_coding_case_records_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_coding_case_records_resource_id
    FOREIGN KEY (resource_id) REFERENCES resources(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 任务行为日志表（用于今日推荐任务的完成状态判定）
CREATE TABLE IF NOT EXISTS task_action_logs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  action VARCHAR(50) NOT NULL COMMENT 'visit_path, visit_quiz, visit_resources',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_action_logs_user_id (user_id),
  INDEX idx_task_action_logs_action (action),
  INDEX idx_task_action_logs_created_at (created_at),
  CONSTRAINT fk_task_action_logs_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 资源创新分析评估表（多智能体协商评估结果）
CREATE TABLE IF NOT EXISTS resource_innovation_analyses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  resource_id INT NOT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'ready',
  generated_by VARCHAR(120) DEFAULT '',
  evaluation JSON DEFAULT NULL,
  basis JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_resource_innovation_analysis_resource (resource_id),
  INDEX idx_resource_innovation_user_id (user_id),
  CONSTRAINT fk_resource_innovation_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resource_innovation_resource_id
    FOREIGN KEY (resource_id) REFERENCES resources(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PPT 生成记录表
CREATE TABLE IF NOT EXISTS ppt_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  sid VARCHAR(120) DEFAULT '',
  title VARCHAR(180) NOT NULL,
  template_id VARCHAR(120) DEFAULT '',
  remote_url TEXT DEFAULT NULL,
  local_url TEXT DEFAULT NULL,
  local_path TEXT DEFAULT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'generating',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_ppt_records_user_id (user_id),
  INDEX idx_ppt_records_sid (sid),
  CONSTRAINT fk_ppt_records_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- PPT 创新分析评估表（多智能体协商评估）
CREATE TABLE IF NOT EXISTS ppt_innovation_analyses (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  ppt_record_id INT NOT NULL,
  sid VARCHAR(120) DEFAULT '',
  status VARCHAR(30) NOT NULL DEFAULT 'pending',
  generated_by VARCHAR(120) DEFAULT '',
  evaluation JSON DEFAULT NULL,
  basis JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_ppt_innovation_analysis_record (ppt_record_id),
  INDEX idx_ppt_innovation_user_id (user_id),
  INDEX idx_ppt_innovation_ppt_record_id (ppt_record_id),
  INDEX idx_ppt_innovation_sid (sid),
  CONSTRAINT fk_ppt_innovation_user_id
    FOREIGN KEY (user_id) REFERENCES users(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_ppt_innovation_ppt_record_id
    FOREIGN KEY (ppt_record_id) REFERENCES ppt_records(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 兼容已有数据库的安全迁移
-- 说明：
-- - CREATE TABLE IF NOT EXISTS 不会修改已存在表的字段类型。
-- - 如果你已经建过旧表，下面这些 ALTER / 动态语句会把旧字段修正过来。
-- ============================================================

-- 修复本次报错字段：Data too long for column 'cognitive_preference'
ALTER TABLE profiles MODIFY COLUMN cognitive_preference TEXT NULL;

-- 其他可能保存 AI 生成长文本的画像字段一并放宽，防止后续类似报错
ALTER TABLE profiles MODIFY COLUMN learning_style TEXT NULL;
ALTER TABLE profiles MODIFY COLUMN motivation_driver TEXT NULL;
ALTER TABLE profiles MODIFY COLUMN engagement_pattern TEXT NULL;

-- 兼容旧版本 quiz_results 表：如果没有 category 字段，则补充
SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE quiz_results ADD COLUMN category VARCHAR(20) NOT NULL DEFAULT ''exercise'' AFTER analysis',
    'SELECT ''quiz_results.category already exists'' AS message'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'quiz_results'
    AND COLUMN_NAME = 'category'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 兼容旧版本 quiz_results 表：如果没有 category 索引，则补充
SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_quiz_results_category ON quiz_results(category)',
    'SELECT ''idx_quiz_results_category already exists'' AS message'
  )
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'quiz_results'
    AND INDEX_NAME = 'idx_quiz_results_category'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 兼容旧版本 chat_conversations 表：如果没有复合索引，则补充
SET @sql := (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_chat_conversations_user_id_updated_at ON chat_conversations(user_id, updated_at)',
    'SELECT ''idx_chat_conversations_user_id_updated_at already exists'' AS message'
  )
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'chat_conversations'
    AND INDEX_NAME = 'idx_chat_conversations_user_id_updated_at'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ── 兼容迁移 SQL 结束 ──────────────────────────
