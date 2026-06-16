from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from core.rag.state import RagProfile


PROFILES_DIR = Path(__file__).resolve().parents[2] / "config" / "rag_profiles"


class TransformConfig(BaseModel):
    rewrite: bool = False
    decompose: bool = False
    variations: int = 1
    hyde: bool = False


class RagProfileConfig(BaseModel):
    profile: str
    gating: bool = False
    transform: TransformConfig = Field(default_factory=TransformConfig)
    routing: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    fusion: str = "none"
    rerank: dict[str, Any] = Field(default_factory=dict)
    curation: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)
    reflection: dict[str, Any] = Field(default_factory=dict)
    highlight: dict[str, Any] = Field(default_factory=dict)


def load_profile(name: str) -> RagProfileConfig:
    path = PROFILES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"RAG profile not found: {name}")
    data = yaml.safe_load(path.read_text())
    return RagProfileConfig.model_validate(data)


def to_rag_profile(cfg: RagProfileConfig) -> RagProfile:
    return RagProfile(profile=cfg.profile, raw=cfg.model_dump())
