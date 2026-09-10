from pathlib import Path

from flask_jwt_extended import create_access_token

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import (
    Chapter,
    Course,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgePoint,
    User,
)
from app.routes import knowledge
from app.services.knowledge_ingestion import prepare_ingestion
from app.services.rag_store import format_source_citation, query_chunks


class KnowledgeTestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    MIMO_API_KEY = ""


def build_client():
    app = create_app(KnowledgeTestConfig)
    with app.app_context():
        user = User(username="knowledge-owner", role="student", email="")
        user.set_password("test")
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
        return app, app.test_client(), token, user.id


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_builtin_pdf_parser_reports_real_source_coverage():
    pdf_path = Path(knowledge.__file__).resolve().parents[2] / "knowledge_base" / "artificial_intelligence.pdf"
    pages = knowledge.extract_pdf_pages(pdf_path.read_bytes())
    report = prepare_ingestion(pages).report()

    assert report["total_pages"] == 41
    assert report["successful_pages"] == list(range(11, 42))
    assert len(report["expected_chapters"]) == 11
    assert report["imported_chapters"] == [{"order": 1, "title": "绪论"}]
    assert report["chapter_coverage"] == 0.0909
    assert report["chunk_count"] == 80
    assert report["mapped_chunk_count"] == 77
    assert report["unmapped_chunk_count"] == 3


def test_builtin_course_import_is_idempotent_and_persists_structure(monkeypatch):
    app, client, token, user_id = build_client()
    monkeypatch.setattr(knowledge, "rebuild_user_index", lambda *_args, **_kwargs: False)

    first = client.post("/api/knowledge/courses/import-builtin", headers=headers(token))
    second = client.post("/api/knowledge/courses/import-builtin", headers=headers(token))

    assert first.status_code == 200
    assert second.status_code == 200
    first_payload = first.get_json()
    second_payload = second.get_json()
    assert first_payload["idempotent"] is False
    assert second_payload["idempotent"] is True
    assert first_payload["import_report"]["vector_indexed"] is False
    assert first_payload["document"]["processing_status"] == "parsed"

    with app.app_context():
        course = Course.query.filter_by(code=knowledge.BUILTIN_COURSE_CODE).one()
        document = KnowledgeDocument.query.filter_by(user_id=user_id).one()

        assert course.status == "draft"
        assert course.source_coverage["chapter_coverage"] == 0.0909
        assert Chapter.query.filter_by(course_id=course.id).count() == 1
        assert KnowledgePoint.query.filter_by(course_id=course.id).count() > 0
        assert KnowledgeChunk.query.filter_by(document_id=document.id).count() == 80
        assert document.page_count == 41
        assert document.metadata_json["is_builtin"] is True


def test_keyword_rag_returns_course_chapter_page_and_document_source(monkeypatch):
    app, client, token, user_id = build_client()
    monkeypatch.setattr(knowledge, "rebuild_user_index", lambda *_args, **_kwargs: False)
    response = client.post("/api/knowledge/courses/import-builtin", headers=headers(token))
    assert response.status_code == 200

    with app.app_context():
        documents = KnowledgeDocument.query.filter_by(user_id=user_id).all()
        results = query_chunks(
            "人工智能的特点",
            [document.to_dict() for document in documents],
            limit=4,
        )

        assert results
        source = results[0]
        assert source["course_title"] == "人工智能导论"
        assert source["chapter"] == "绪论"
        assert source["page_start"] is not None
        assert source["source_filename"] == "artificial_intelligence.pdf"
        citation = format_source_citation(source)
        assert "课程：人工智能导论" in citation
        assert "章节：绪论" in citation
        assert "物理页：" in citation
        assert "文档：artificial_intelligence.pdf" in citation
