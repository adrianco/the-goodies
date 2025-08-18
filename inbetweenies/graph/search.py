"""
Graph search functionality.

Provides search capabilities across entities with scoring and highlighting.
"""

from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import re
from difflib import SequenceMatcher

from ..models import Entity, EntityType


class SearchResult:
    """Container for search results with scoring"""

    def __init__(self, entity: Entity, score: float, highlights: Dict[str, List[str]]):
        self.entity = entity
        self.score = score
        self.highlights = highlights

    def to_dict(self) -> dict:
        """Convert to dictionary representation"""
        return {
            "id": self.entity.id,
            "version": self.entity.version,
            "entity_type": self.entity.entity_type.value,
            "name": self.entity.name,
            "score": self.score,
            "highlights": self.highlights,
            "content_preview": self._get_content_preview()
        }

    def _get_content_preview(self) -> Optional[str]:
        """Get a preview of content if available"""
        if not self.entity.content:
            return None

        # Take first few key-value pairs
        preview_items = []
        for key, value in list(self.entity.content.items())[:3]:
            preview_items.append(f"{key}: {str(value)[:50]}")

        return ", ".join(preview_items) + "..." if preview_items else None


class GraphSearch(ABC):
    """Abstract base class for graph search operations"""

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """Search entities by query"""
        pass

    def calculate_score(self, entity: Entity, query: str) -> tuple[float, Dict[str, List[str]]]:
        """
        Calculate relevance score and generate highlights.

        Args:
            entity: Entity to score
            query: Search query

        Returns:
            Tuple of (score, highlights)
        """
        query_lower = query.lower()
        query_words = query_lower.split()
        score = 0.0
        highlights = {}

        # Score name matches (highest weight)
        name_lower = entity.name.lower()
        if query_lower in name_lower:
            score += 3.0
            highlights["name"] = [entity.name]
        else:
            # Check individual words
            word_matches = sum(1 for word in query_words if word in name_lower)
            if word_matches:
                score += 1.5 * word_matches
                highlights["name"] = [entity.name]

        # Score content matches
        if entity.content:
            content_matches = []
            content_str = json.dumps(entity.content).lower()

            if query_lower in content_str:
                score += 2.0
                content_matches.append(f"Content contains '{query}'")
            else:
                # Check individual words in content
                word_matches = sum(1 for word in query_words if word in content_str)
                if word_matches:
                    score += 0.5 * word_matches
                    content_matches.append(f"Content matches {word_matches} word(s)")

            # Check specific fields
            for key, value in entity.content.items():
                if isinstance(value, str):
                    value_lower = value.lower()
                    if query_lower in value_lower:
                        score += 1.0
                        content_matches.append(f"{key}: {value[:50]}...")

            if content_matches:
                highlights["content"] = content_matches

        # Boost score for exact matches
        if entity.name.lower() == query_lower:
            score *= 2.0

        # Use fuzzy matching for typos
        similarity = SequenceMatcher(None, entity.name.lower(), query_lower).ratio()
        if similarity > 0.8:
            score += similarity

        return score, highlights

    def filter_and_rank_results(
        self,
        entities: List[Entity],
        query: str,
        limit: int
    ) -> List[SearchResult]:
        """
        Filter, score, and rank search results.

        Args:
            entities: List of entities to search through
            query: Search query
            limit: Maximum results to return

        Returns:
            Ranked list of search results
        """
        results = []

        for entity in entities:
            score, highlights = self.calculate_score(entity, query)

            if score > 0:
                results.append(SearchResult(entity, score, highlights))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        # Return top results
        return results[:limit]

    async def find_similar_entities(
        self,
        entity_id: str,
        limit: int = 5
    ) -> List[SearchResult]:
        """
        Find entities similar to a given entity.

        Args:
            entity_id: Entity to find similar ones to
            limit: Maximum results to return

        Returns:
            List of similar entities
        """
        # Get the reference entity
        from .operations import GraphOperations
        if isinstance(self, GraphOperations):
            reference = await self.get_entity(entity_id)
            if not reference:
                return []

            # Get all entities of the same type
            candidates = await self.get_entities_by_type(reference.entity_type)

            # Remove the reference entity
            candidates = [e for e in candidates if e.id != entity_id]

            # Score based on similarity
            results = []
            for candidate in candidates:
                score = self._calculate_similarity(reference, candidate)
                if score > 0.1:  # Minimum threshold
                    results.append(SearchResult(
                        candidate,
                        score,
                        {"similarity": [f"Similar to {reference.name}"]}
                    ))

            # Sort and return top results
            results.sort(key=lambda r: r.score, reverse=True)
            return results[:limit]

        return []

    def _calculate_similarity(self, entity1: Entity, entity2: Entity) -> float:
        """Calculate similarity score between two entities"""
        score = 0.0

        # Same entity type
        if entity1.entity_type == entity2.entity_type:
            score += 0.2

        # Name similarity
        name_similarity = SequenceMatcher(
            None,
            entity1.name.lower(),
            entity2.name.lower()
        ).ratio()
        score += name_similarity * 0.3

        # Content similarity
        if entity1.content and entity2.content:
            # Count common keys
            keys1 = set(entity1.content.keys())
            keys2 = set(entity2.content.keys())
            common_keys = keys1 & keys2

            if keys1 or keys2:
                key_overlap = len(common_keys) / len(keys1 | keys2)
                score += key_overlap * 0.3

            # Check value similarity for common keys
            value_matches = 0
            for key in common_keys:
                if entity1.content[key] == entity2.content[key]:
                    value_matches += 1

            if common_keys:
                value_similarity = value_matches / len(common_keys)
                score += value_similarity * 0.2

        return score


# Need to import json for content matching
import json
