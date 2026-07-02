from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.data.runner import open_connector
from core.models import DataSource, Document, DocumentCollection
from core.prompts.renderer import render_template
from core.rag.engine import RagEngine


async def resolve_binding_context(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bindings: dict[str, Any] | None,
    variables: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Fetch context from a datasource, document collection, or uploaded file."""
    bindings = bindings or {}
    binding_type = str(bindings.get("type") or "none").lower()
    if binding_type in {"", "none"}:
        return "", {}

    if binding_type in {"sql", "datasource", "data"}:
        return await _resolve_sql_binding(db, tenant_id=tenant_id, bindings=bindings, variables=variables)
    if binding_type in {"rag", "documents", "docs"}:
        return await _resolve_rag_binding(db, tenant_id=tenant_id, bindings=bindings, variables=variables)
    if binding_type in {"file", "document"}:
        return await _resolve_file_binding(db, tenant_id=tenant_id, bindings=bindings)

    raise ValueError(f"unsupported binding type: {binding_type}")


def merge_template_variables(
    *,
    context_text: str,
    context_vars: dict[str, Any],
    variables: dict[str, Any],
) -> dict[str, Any]:
    """Merge run variables with binding output for Jinja rendering."""
    merged = {**context_vars, **variables}
    if context_text:
        merged.setdefault("context", context_text)
    return merged


async def _resolve_sql_binding(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bindings: dict[str, Any],
    variables: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    raw_id = bindings.get("datasource_id")
    sql_template = bindings.get("sql")
    if not raw_id or not sql_template:
        raise ValueError("sql binding requires datasource_id and sql")

    datasource_id = uuid.UUID(str(raw_id))
    res = await db.execute(
        select(DataSource).where(DataSource.id == datasource_id, DataSource.tenant_id == tenant_id)
    )
    ds = res.scalar_one_or_none()
    if ds is None:
        raise ValueError("datasource not found")

    sql = render_template(str(sql_template), variables)
    async with open_connector(ds.db_type, ds.connection_config_json) as connector:
        validation = await connector.validate_sql(sql)
        if not validation.ok:
            raise ValueError(validation.error or "invalid SQL")
        result = await connector.execute_query(sql)

    header = " | ".join(result.columns)
    rows = [" | ".join(str(cell) for cell in row) for row in result.rows[:100]]
    context = "\n".join([f"SQL: {sql}", header, *rows])
    if len(result.rows) > 100:
        context += f"\n... {len(result.rows) - 100} more rows"
    return context, {"sql_result_columns": result.columns, "sql_result_rows": result.rows[:100]}


async def _resolve_rag_binding(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bindings: dict[str, Any],
    variables: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    raw_id = bindings.get("collection_id")
    if not raw_id:
        raise ValueError("rag binding requires collection_id")

    collection_id = uuid.UUID(str(raw_id))
    res = await db.execute(
        select(DocumentCollection).where(
            DocumentCollection.id == collection_id,
            DocumentCollection.tenant_id == tenant_id,
        )
    )
    col = res.scalar_one_or_none()
    if col is None:
        raise ValueError("document collection not found")

    query_key = str(bindings.get("query_variable") or "question")
    query = str(variables.get(query_key) or variables.get("question") or "").strip()
    if not query:
        raise ValueError(f"rag binding requires variable '{query_key}' or 'question'")

    profile = str(bindings.get("rag_profile") or col.rag_profile or "standard")
    engine = RagEngine()
    result = await engine.run(
        query=query,
        tenant_id=str(tenant_id),
        collection_ids=[str(col.id)],
        profile_name=profile,
    )
    final = result.get("final") or {}
    answer = str(final.get("answer") or "")
    highlights = final.get("highlight_spans") or []
    snippet_lines = [
        f"- {h.get('text', '')}" for h in highlights[:8] if isinstance(h, dict) and h.get("text")
    ]
    context = f"Collection: {col.name}\nQuestion: {query}\nAnswer:\n{answer}"
    if snippet_lines:
        context += "\n\nSources:\n" + "\n".join(snippet_lines)
    return context, {"rag_answer": answer, "rag_highlights": highlights}


async def _resolve_file_binding(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    bindings: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    raw_id = bindings.get("document_id")
    if not raw_id:
        raise ValueError("file binding requires document_id")

    document_id = uuid.UUID(str(raw_id))
    res = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
    )
    doc = res.scalar_one_or_none()
    if doc is None:
        raise ValueError("document not found")

    content = (doc.content_markdown or "").strip()
    if not content:
        raise ValueError("document has no extracted text yet; wait for ingestion to finish")

    max_chars = int(bindings.get("max_chars") or 12000)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n... (truncated)"

    context = f"File: {doc.filename}\n\n{content}"
    return context, {"file_name": doc.filename, "file_excerpt": content}
