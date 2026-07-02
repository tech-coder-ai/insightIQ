from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

from core.llm.base import LLMMessage
from core.llm.factory import LLMProviderFactory


class ExtractedEntity(BaseModel):
    name: str
    type: str = "concept"


class ExtractedRelationship(BaseModel):
    source: str
    relation: str = "related_to"
    target: str


class ExtractionResult(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relationships: list[ExtractedRelationship] = Field(default_factory=list)


_SYSTEM = (
    "Extract the key named entities (people, organizations, products, financial "
    "metrics, dates) and the relationships between them from the passage below, "
    "for building a knowledge graph. Reply with ONLY compact JSON: "
    '{"entities": [{"name": "...", "type": "..."}], '
    '"relationships": [{"source": "...", "relation": "...", "target": "..."}]}. '
    "Keep it to at most 8 entities and 8 relationships. Use short canonical names "
    "so the same entity is referred to consistently."
)


async def extract_entities(text: str, *, provider_key: str = "openai") -> ExtractionResult:
    """GraphRAG entity/relationship extraction (Workstream 2). Falls back to a
    lightweight proper-noun heuristic when no LLM is configured, so local/dev
    environments (no OPENAI_API_KEY) still populate a usable graph."""
    if not text.strip():
        return ExtractionResult()
    llm = LLMProviderFactory.create(provider_key)
    try:
        raw = await llm.complete(system=_SYSTEM, messages=[LLMMessage(role="user", content=text[:4000])])
        data = _parse_json(raw)
        return ExtractionResult.model_validate(data)
    except Exception:  # noqa: BLE001 - degrade to the heuristic extractor
        return _heuristic_extract(text)


def _parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


_PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-zA-Z0-9&.]{2,}(?:\s+[A-Z][a-zA-Z0-9&.]{2,}){0,3}\b")
_STOPWORDS = {"the", "this", "these", "those", "for", "and", "with"}


def _heuristic_extract(text: str) -> ExtractionResult:
    """Dev-mode fallback: pulls capitalized phrases out as entities and links
    consecutive ones with a generic co-occurrence relation, so GraphRAG has a
    graph to traverse even without an LLM configured."""
    names: list[str] = []
    seen: set[str] = set()
    for m in _PROPER_NOUN_RE.finditer(text):
        name = m.group(0).strip()
        key = name.lower()
        if key not in seen and key not in _STOPWORDS:
            seen.add(key)
            names.append(name)
    names = names[:8]
    entities = [ExtractedEntity(name=n, type="concept") for n in names]
    relationships = [
        ExtractedRelationship(source=names[i], relation="co_occurs_with", target=names[i + 1])
        for i in range(len(names) - 1)
    ]
    return ExtractionResult(entities=entities, relationships=relationships)
