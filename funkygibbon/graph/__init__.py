"""
Graph operations module for FunkyGibbon

``GraphIndex`` is the data structure; ``GraphIndexService`` is its single owner
(ADR-003). Application code should reach the index through the service on
``app.state.graph_index`` / the dependencies in ``funkygibbon.api.dependencies``,
never by constructing a ``GraphIndex`` of its own.
"""

from .index import GraphIndex, GraphNode, is_tombstoned
from .index_service import (
    GraphIndexService,
    StorageMarker,
    assert_single_worker_posture,
    bind_graph_index_service,
    current_graph_index_service,
    graph_index_enabled,
    unbind_graph_index_service,
    write_through_applied_changes,
)

__all__ = [
    'GraphIndex',
    'GraphNode',
    'GraphIndexService',
    'StorageMarker',
    'assert_single_worker_posture',
    'bind_graph_index_service',
    'current_graph_index_service',
    'graph_index_enabled',
    'is_tombstoned',
    'unbind_graph_index_service',
    'write_through_applied_changes',
]
