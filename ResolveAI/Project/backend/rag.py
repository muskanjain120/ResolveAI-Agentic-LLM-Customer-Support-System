"""
Knowledge base retrieval using SQLite FTS5.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.models import KnowledgeBase, TicketCategory


def search_knowledge_base(
    db: Session,
    query: str,
    category: TicketCategory = None,
    top_k: int = 4,
) -> list[KnowledgeBase]:
    """
    Full-text search over the KnowledgeBase using SQLite FTS5.
    Optionally pre-filters by category.
    """
    if not query.strip():
        return []

    # BM25 ranking via FTS5 — lower rank = more relevant
    fts_query = text("""
        SELECT kb.id
        FROM kb_fts
        JOIN knowledge_base kb ON kb.id = kb_fts.rowid
        WHERE kb_fts MATCH :query
          AND kb.is_active = 1
          AND (:cat IS NULL OR kb.category = :cat)
        ORDER BY rank
        LIMIT :topk
    """)

    rows = db.execute(fts_query, {
        "query": query,
        "cat": category.value if category else None,
        "topk": top_k,
    }).fetchall()

    ids = [r[0] for r in rows]
    if not ids:
        return []

    articles = db.query(KnowledgeBase).filter(KnowledgeBase.id.in_(ids)).all()
    # Preserve ranking order
    id_to_article = {a.id: a for a in articles}
    return [id_to_article[i] for i in ids if i in id_to_article]
