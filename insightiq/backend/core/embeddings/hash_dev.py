from __future__ import annotations

import hashlib
import math

from core.embeddings.base import IEmbedder
from core.embeddings.factory import EMBEDDERS


@EMBEDDERS.register("hash-dev")
class HashDevEmbedder(IEmbedder):
    """Deterministic dev embedder. TODO(phase3): swap to BGE-M3 in production."""

    def __init__(self) -> None:
        self.model_name = "hash-dev"
        self.dimension = 384

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_to_vector(t, self.dimension) for t in texts]


def _hash_to_vector(text: str, dim: int) -> list[float]:
    digest = hashlib.sha256(text.encode()).digest()
    values: list[float] = []
    for i in range(dim):
        b = digest[i % len(digest)]
        values.append((b / 127.5) - 1.0)
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]
