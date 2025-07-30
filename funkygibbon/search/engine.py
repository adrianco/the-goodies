"""
Search Engine for Entity Content

This module provides full-text and semantic search capabilities
across the entity graph.
"""

from typing import List, Optional, Dict, Any, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
import re
import json

from ..models import Entity, EntityType
from ..graph.index import GraphIndex


@dataclass
class SearchResult:
    """Search result with entity and relevance information"""
    entity: Entity
    score: float
    highlights: List[str]
    matched_fields: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "entity": self.entity.to_dict(),
            "score": self.score,
            "highlights": self.highlights,
            "matched_fields": self.matched_fields
        }


class SearchEngine:
    """Text and semantic search capabilities for entities"""
    
    def __init__(self, graph_index: GraphIndex):
        self.graph = graph_index
        # Common stop words to ignore in search
        self.stop_words = {
            "the", "a", "an", "and", "or", "but", "in", "on", "at",
            "to", "for", "of", "with", "by", "from", "as", "is",
            "was", "are", "were", "been", "be", "have", "has", "had",
            "do", "does", "did", "will", "would", "could", "should",
            "may", "might", "must", "can", "this", "that", "these",
            "those", "i", "you", "he", "she", "it", "we", "they"
        }
    
    def search_entities(
        self,
        query: str,
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10,
        min_score: float = 0.1
    ) -> List[SearchResult]:
        """
        Full-text search across entity content.
        
        Args:
            query: Search query string
            entity_types: Filter by entity types
            limit: Maximum results to return
            min_score: Minimum relevance score
            
        Returns:
            List of search results ordered by relevance
        """
        if not query.strip():
            return []
        
        # Tokenize and clean query
        query_tokens = self._tokenize(query.lower())
        
        results = []
        
        # Search through all entities
        for entity in self.graph.entities.values():
            # Filter by type if specified
            if entity_types and entity.entity_type not in entity_types:
                continue
            
            # Calculate relevance score
            score, highlights, matched_fields = self._calculate_score(
                entity, query_tokens, query.lower()
            )
            
            if score >= min_score:
                results.append(SearchResult(
                    entity=entity,
                    score=score,
                    highlights=highlights,
                    matched_fields=matched_fields
                ))
        
        # Sort by score and limit results
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def find_similar(
        self,
        entity_id: str,
        threshold: float = 0.7,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Find entities similar to the given entity.
        
        Args:
            entity_id: Reference entity ID
            threshold: Similarity threshold (0-1)
            limit: Maximum results
            
        Returns:
            List of similar entities
        """
        reference = self.graph.entities.get(entity_id)
        if not reference:
            return []
        
        # Extract features from reference entity
        ref_tokens = self._extract_entity_tokens(reference)
        ref_type = reference.entity_type
        
        results = []
        
        for entity in self.graph.entities.values():
            if entity.id == entity_id:
                continue
            
            # Calculate similarity
            similarity = self._calculate_similarity(
                reference, entity, ref_tokens
            )
            
            if similarity >= threshold:
                results.append(SearchResult(
                    entity=entity,
                    score=similarity,
                    highlights=[f"Similar to {reference.name}"],
                    matched_fields=["entity_type", "content"] if entity.entity_type == ref_type else ["content"]
                ))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def search_by_properties(
        self,
        properties: Dict[str, Any],
        entity_types: Optional[List[EntityType]] = None,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Search entities by specific property values.
        
        Args:
            properties: Property key-value pairs to match
            entity_types: Filter by entity types
            limit: Maximum results
            
        Returns:
            List of matching entities
        """
        results = []
        
        for entity in self.graph.entities.values():
            # Filter by type
            if entity_types and entity.entity_type not in entity_types:
                continue
            
            # Check property matches
            matches, matched_fields = self._match_properties(
                entity.content, properties
            )
            
            if matches > 0:
                score = matches / len(properties)  # Percentage of properties matched
                results.append(SearchResult(
                    entity=entity,
                    score=score,
                    highlights=[f"Matched {matches}/{len(properties)} properties"],
                    matched_fields=matched_fields
                ))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def search_connected(
        self,
        query: str,
        start_entity_id: str,
        max_distance: int = 2,
        limit: int = 10
    ) -> List[SearchResult]:
        """
        Search entities connected to a starting entity.
        
        Args:
            query: Search query
            start_entity_id: Entity to start from
            max_distance: Maximum graph distance
            limit: Maximum results
            
        Returns:
            List of connected matching entities
        """
        # First get connected entities
        connected = self.graph.get_connected_entities(
            start_entity_id,
            direction="both",
            max_depth=max_distance
        )
        
        # Extract unique entities
        connected_entities = {}
        for conn in connected:
            entity = conn["entity"]
            distance = conn["distance"]
            
            # Keep closest distance for each entity
            if entity.id not in connected_entities or distance < connected_entities[entity.id][1]:
                connected_entities[entity.id] = (entity, distance)
        
        # Search within connected entities
        query_tokens = self._tokenize(query.lower())
        results = []
        
        for entity, distance in connected_entities.values():
            score, highlights, matched_fields = self._calculate_score(
                entity, query_tokens, query.lower()
            )
            
            # Boost score based on proximity
            proximity_boost = 1.0 / (distance + 1)
            adjusted_score = score * (1 + proximity_boost)
            
            if score > 0:
                results.append(SearchResult(
                    entity=entity,
                    score=adjusted_score,
                    highlights=highlights + [f"Distance: {distance}"],
                    matched_fields=matched_fields
                ))
        
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]
    
    def _tokenize(self, text: str) -> Set[str]:
        """Tokenize text into words, removing stop words"""
        # Simple tokenization - split on non-alphanumeric
        tokens = re.findall(r'\w+', text.lower())
        # Remove stop words and short tokens
        return {t for t in tokens if len(t) > 2 and t not in self.stop_words}
    
    def _calculate_score(
        self,
        entity: Entity,
        query_tokens: Set[str],
        original_query: str
    ) -> Tuple[float, List[str], List[str]]:
        """Calculate relevance score for an entity"""
        score = 0.0
        highlights = []
        matched_fields = []
        
        # Score name field (highest weight)
        name_lower = entity.name.lower()
        if original_query in name_lower:
            score += 3.0  # Exact substring match
            highlights.append(f"Name: {entity.name}")
            matched_fields.append("name")
        else:
            name_tokens = self._tokenize(name_lower)
            name_matches = len(query_tokens & name_tokens)
            if name_matches > 0:
                score += 2.0 * (name_matches / len(query_tokens))
                highlights.append(f"Name: {entity.name}")
                matched_fields.append("name")
        
        # Score entity type
        if any(token in entity.entity_type.value for token in query_tokens):
            score += 1.0
            matched_fields.append("entity_type")
        
        # Score content fields
        content_score, content_highlights = self._score_content(
            entity.content, query_tokens, original_query
        )
        
        if content_score > 0:
            score += content_score
            highlights.extend(content_highlights)
            matched_fields.append("content")
        
        return score, highlights, matched_fields
    
    def _score_content(
        self,
        content: Dict[str, Any],
        query_tokens: Set[str],
        original_query: str
    ) -> Tuple[float, List[str]]:
        """Score JSON content recursively"""
        score = 0.0
        highlights = []
        
        def traverse(obj: Any, path: str = ""):
            nonlocal score, highlights
            
            if isinstance(obj, str):
                obj_lower = obj.lower()
                if original_query in obj_lower:
                    score += 1.5  # Exact match in content
                    highlights.append(f"{path}: {obj[:100]}...")
                else:
                    tokens = self._tokenize(obj_lower)
                    matches = len(query_tokens & tokens)
                    if matches > 0:
                        score += matches / len(query_tokens)
                        highlights.append(f"{path}: {obj[:100]}...")
                        
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    new_path = f"{path}.{key}" if path else key
                    traverse(value, new_path)
                    
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    traverse(item, f"{path}[{i}]")
        
        traverse(content)
        return score, highlights
    
    def _extract_entity_tokens(self, entity: Entity) -> Set[str]:
        """Extract all tokens from an entity for similarity comparison"""
        tokens = set()
        
        # Add name tokens
        tokens.update(self._tokenize(entity.name))
        
        # Add type
        tokens.add(entity.entity_type.value)
        
        # Extract from content
        def extract_text(obj: Any):
            if isinstance(obj, str):
                tokens.update(self._tokenize(obj))
            elif isinstance(obj, dict):
                for value in obj.values():
                    extract_text(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text(item)
        
        extract_text(entity.content)
        return tokens
    
    def _calculate_similarity(
        self,
        entity1: Entity,
        entity2: Entity,
        entity1_tokens: Set[str]
    ) -> float:
        """Calculate similarity between two entities"""
        # Type similarity
        type_score = 1.0 if entity1.entity_type == entity2.entity_type else 0.0
        
        # Token overlap (Jaccard similarity)
        entity2_tokens = self._extract_entity_tokens(entity2)
        
        if not entity1_tokens and not entity2_tokens:
            token_score = 0.0
        else:
            intersection = len(entity1_tokens & entity2_tokens)
            union = len(entity1_tokens | entity2_tokens)
            token_score = intersection / union if union > 0 else 0.0
        
        # Weighted combination
        return (type_score * 0.3) + (token_score * 0.7)
    
    def _match_properties(
        self,
        content: Dict[str, Any],
        target_props: Dict[str, Any]
    ) -> Tuple[int, List[str]]:
        """Check how many target properties match in content"""
        matches = 0
        matched_fields = []
        
        for key, target_value in target_props.items():
            if key in content:
                if content[key] == target_value:
                    matches += 1
                    matched_fields.append(key)
                elif isinstance(target_value, str) and isinstance(content[key], str):
                    # Partial string match
                    if target_value.lower() in str(content[key]).lower():
                        matches += 0.5
                        matched_fields.append(key)
        
        return matches, matched_fields