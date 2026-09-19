"""Text embedding with the self-hosted E5 encoder; see docs/research/embedding-model.md."""
from functools import lru_cache
from typing import TYPE_CHECKING, Iterable

from app.config import get_settings
from app.models import EMBEDDING_DIMENSIONS

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# E5 models are trained with asymmetric prefixes; omitting them degrades retrieval.
QUERY_PREFIX = "query: "
PASSAGE_PREFIX = "passage: "
MAX_SEQUENCE_LENGTH = 512


@lru_cache
def get_encoder() -> "SentenceTransformer":
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    encoder = SentenceTransformer(settings.embedding_model, device=settings.embedding_device)
    encoder.max_seq_length = MAX_SEQUENCE_LENGTH
    dimensions = encoder.get_embedding_dimension()
    if dimensions != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"{settings.embedding_model} emits {dimensions} dimensions; "
            f"the chunks column stores {EMBEDDING_DIMENSIONS}"
        )
    return encoder


def _encode(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    encoder = get_encoder()
    vectors = encoder.encode(texts, batch_size=get_settings().embedding_batch_size, normalize_embeddings=True)
    return [vector.tolist() for vector in vectors]


def embed_passages(texts: Iterable[str]) -> list[list[float]]:
    """Embed stored chunk text. Vectors are normalized, so cosine distance is a dot product."""
    return _encode([f"{PASSAGE_PREFIX}{text}" for text in texts])


def embed_query(text: str) -> list[float]:
    return _encode([f"{QUERY_PREFIX}{text}"])[0]
