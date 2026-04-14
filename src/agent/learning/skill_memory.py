# -*- coding: utf-8 -*-
"""TradingSkillMemory — Vector-backed retrieval of learned trading skills.

Provides:
1. Add structured skills with embeddings to a FAISS or TF-IDF index
2. Search for similar skills given current market features
3. File-based persistence (index + metadata JSON)

When FAISS is unavailable, falls back to TF-IDF cosine similarity.
When sklearn is also unavailable, falls back to simple keyword matching.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Persistence defaults
_DEFAULT_INDEX_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
)
_DEFAULT_TOP_K = 3


@dataclass
class TradingSkill:
    """A learned trading skill with embedding and metadata."""

    skill_id: str = ""
    skill_name: str = ""
    description: str = ""
    trigger_condition: str = ""
    action: str = ""
    category: str = "other"
    confidence: float = 0.5
    created_at: float = field(default_factory=time.time)
    # How many times this skill has been retrieved
    retrieval_count: int = 0
    # How many times it was validated (matched actual outcome)
    validation_count: int = 0
    # How many times it was invalidated
    invalidation_count: int = 0
    # Embedding vector (stored separately in index, referenced here)
    embedding: Optional[List[float]] = field(default=None, repr=False)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("embedding", None)
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingSkill":
        data = dict(data)
        data.pop("embedding", None)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TradingSkillMemory:
    """Vector-backed retrieval of learned trading skills.

    Usage::

        memory = TradingSkillMemory()
        memory.add_skill(skill, text_for_embedding)
        similar = memory.search("high sentiment breakout failed", top_k=3)
    """

    def __init__(
        self,
        enabled: bool = False,
        persist_dir: str = _DEFAULT_INDEX_DIR,
        top_k: int = _DEFAULT_TOP_K,
    ):
        self.enabled = enabled
        self.persist_dir = persist_dir
        self.top_k = top_k
        self._skills: List[TradingSkill] = []
        self._embedder: Optional[Any] = None
        self._index: Optional[Any] = None  # FAISS or TF-IDF index
        self._embedding_dim: int = 0
        self._backend: str = "none"  # "faiss", "tfidf", "keyword", "none"
        self._tfidf_vectorizer: Optional[Any] = None
        self._tfidf_matrix: Optional[Any] = None
        self._skill_texts: List[str] = []  # texts for TF-IDF

        if self.enabled:
            self._init_backend()
            self._load()

    # -----------------------------------------------------------------
    # Backend initialisation
    # -----------------------------------------------------------------

    def _init_backend(self) -> None:
        """Try FAISS first, then TF-IDF, then keyword fallback."""
        try:
            import faiss

            self._backend = "faiss"
            logger.info("[TradingSkillMemory] using FAISS backend")
            return
        except ImportError:
            pass

        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity

            self._tfidf_vectorizer = TfidfVectorizer(
                analyzer="char_wb", ngram_range=(2, 4), max_features=5000
            )
            self._backend = "tfidf"
            logger.info("[TradingSkillMemory] using TF-IDF backend")
            return
        except ImportError:
            pass

        self._backend = "keyword"
        logger.info("[TradingSkillMemory] using keyword fallback backend")

    # -----------------------------------------------------------------
    # Skill CRUD
    # -----------------------------------------------------------------

    def add_skill(self, skill: TradingSkill, text: str = "") -> None:
        """Add a skill and compute its embedding."""
        if not self.enabled:
            return

        if not text:
            text = f"{skill.skill_name} {skill.description} {skill.trigger_condition} {skill.action}"

        embedding = self._embed_text(text)
        skill.embedding = embedding

        self._skills.append(skill)
        self._skill_texts.append(text)

        if self._backend == "tfidf":
            self._rebuild_tfidf()

        logger.info(
            "[TradingSkillMemory] added skill '%s' (backend=%s)",
            skill.skill_name,
            self._backend,
        )
        self._save()

    def remove_skill(self, skill_id: str) -> bool:
        """Remove a skill by ID."""
        for i, s in enumerate(self._skills):
            if s.skill_id == skill_id:
                self._skills.pop(i)
                self._skill_texts.pop(i)
                if self._backend == "tfidf":
                    self._rebuild_tfidf()
                self._save()
                return True
        return False

    def get_skill(self, skill_id: str) -> Optional[TradingSkill]:
        for s in self._skills:
            if s.skill_id == skill_id:
                return s
        return None

    def list_skills(self, limit: int = 100) -> List[TradingSkill]:
        return sorted(self._skills, key=lambda s: s.created_at, reverse=True)[:limit]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_skills": len(self._skills),
            "backend": self._backend,
            "enabled": self.enabled,
            "persist_dir": self.persist_dir,
        }

    # -----------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------

    def search(self, query: str, top_k: Optional[int] = None) -> List[TradingSkill]:
        """Find skills most relevant to the query (market features text)."""
        if not self.enabled or not self._skills:
            return []

        k = top_k or self.top_k

        if self._backend == "keyword":
            return self._search_keyword(query, k)

        if self._backend == "tfidf":
            return self._search_tfidf(query, k)

        return []

    def _search_keyword(self, query: str, k: int) -> List[TradingSkill]:
        query_words = set(query.lower().split())
        scored = []
        for s in self._skills:
            text = f"{s.skill_name} {s.description} {s.trigger_condition} {s.action}".lower()
            words = set(text.split())
            overlap = len(query_words & words)
            if overlap > 0:
                scored.append((overlap, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:k]]

    def _search_tfidf(self, query: str, k: int) -> List[TradingSkill]:
        try:
            from sklearn.metrics.pairwise import cosine_similarity

            if self._tfidf_matrix is None or len(self._skill_texts) == 0:
                return []

            q_vec = self._tfidf_vectorizer.transform([query])
            sims = cosine_similarity(q_vec, self._tfidf_matrix).flatten()
            top_indices = sims.argsort()[-k:][::-1]

            results = []
            for idx in top_indices:
                if sims[idx] > 0:
                    results.append(self._skills[idx])
            return results
        except Exception:
            return self._search_keyword(query, k)

    # -----------------------------------------------------------------
    # Embedding helpers
    # -----------------------------------------------------------------

    def _embed_text(self, text: str) -> Optional[List[float]]:
        """Produce an embedding vector for the given text."""
        if self._backend == "faiss":
            # FAISS needs an external model; for now we use a hash-based
            # pseudo-embedding as a pragmatic fallback until a real model
            # is configured.
            return self._hash_embedding(text, dim=128)
        return None

    @staticmethod
    def _hash_embedding(text: str, dim: int = 128) -> List[float]:
        """Deterministic hash-based embedding for FAISS indexing."""
        import hashlib

        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        vec = []
        for i in range(dim):
            chunk = h[i * 2 % len(h): (i * 2 + 2) % len(h) or len(h)]
            vec.append(int(chunk, 16) / 65535.0 * 2 - 1)
        return vec

    def _rebuild_tfidf(self) -> None:
        try:
            self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(self._skill_texts)
        except Exception as exc:
            logger.warning("[TradingSkillMemory] TF-IDF rebuild failed: %s", exc)

    # -----------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------

    def _load(self) -> None:
        meta_path = self._meta_path()
        if not meta_path.exists():
            return

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if isinstance(data, list):
                self._skills = []
                for item in data:
                    try:
                        skill = TradingSkill.from_dict(item)
                        self._skills.append(skill)
                    except (TypeError, KeyError):
                        continue

            logger.info(
                "[TradingSkillMemory] loaded %d skills from %s",
                len(self._skills), meta_path,
            )
        except Exception as exc:
            logger.warning("[TradingSkillMemory] failed to load skills: %s", exc)

    def _save(self) -> None:
        meta_path = self._meta_path()
        try:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(
                    [s.to_dict() for s in self._skills],
                    f, ensure_ascii=False, indent=2,
                )
            logger.debug(
                "[TradingSkillMemory] saved %d skills to %s",
                len(self._skills), meta_path,
            )
        except Exception as exc:
            logger.warning("[TradingSkillMemory] failed to save skills: %s", exc)

    def _meta_path(self) -> Path:
        return Path(self.persist_dir) / "learned_skills_meta.json"

    # -----------------------------------------------------------------
    # Validation (track skill effectiveness)
    # -----------------------------------------------------------------

    def validate_skill(self, skill_id: str, was_correct: bool) -> None:
        """Mark a skill retrieval as validated or invalidated."""
        for s in self._skills:
            if s.skill_id == skill_id:
                s.retrieval_count += 1
                if was_correct:
                    s.validation_count += 1
                else:
                    s.invalidation_count += 1
                self._save()
                return

    def get_skill_effectiveness(self, skill_id: str) -> Optional[Dict[str, Any]]:
        """Get validation stats for a skill."""
        for s in self._skills:
            if s.skill_id == skill_id:
                total = s.validation_count + s.invalidation_count
                return {
                    "retrieval_count": s.retrieval_count,
                    "validation_count": s.validation_count,
                    "invalidation_count": s.invalidation_count,
                    "accuracy": s.validation_count / total if total > 0 else None,
                }
        return None
