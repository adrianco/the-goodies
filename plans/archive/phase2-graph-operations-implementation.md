# Phase 2: Graph Operations Implementation Plan

## Overview
This document outlines the implementation strategy for building a graph-based knowledge system for FunkyGibbon. The system provides powerful entity and relationship management capabilities with MCP server integration for advanced querying and operations.

## Architecture Design

### Core Components
1. **Entity System**: Flexible nodes representing any type of object in the system
2. **Relationship Engine**: Typed connections between entities forming a knowledge graph
3. **Graph Operations**: Fast traversal, search, and query capabilities
4. **MCP Interface**: Tool-based access for AI agents and external systems

### Technology Stack
- **Database**: SQLite with SQLAlchemy ORM
- **Framework**: FastAPI for REST endpoints
- **Protocol**: MCP (Model Context Protocol) for AI integration
- **Language**: Python 3.9+ with modern async support

## Data Models

### Entity Model
```python
# funkygibbon/models/entity.py
class EntityType(str, Enum):
    # Core entity types
    HOME = "home"
    ROOM = "room"
    DEVICE = "device"
    ZONE = "zone"
    DOOR = "door"
    WINDOW = "window"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    NOTE = "note"
    SCHEDULE = "schedule"
    AUTOMATION = "automation"

class Entity(Base, InbetweeniesTimestampMixin):
    """Core entity representing any node in the knowledge graph"""
    __tablename__ = "entities"
    
    id = Column(String(36), primary_key=True)
    entity_type = Column(Enum(EntityType), nullable=False)
    name = Column(String(255), nullable=False)
    content = Column(JSON, nullable=False, default={})
    source_type = Column(String(50), default="manual")
    user_id = Column(String(36), ForeignKey("users.id"))
    
    # Version tracking for immutability
    version = Column(String(255), nullable=False)
    parent_versions = Column(JSON, default=[])
```

### Relationship Model
```python
# funkygibbon/models/relationship.py
class RelationshipType(str, Enum):
    LOCATED_IN = "located_in"
    CONTROLS = "controls"
    CONNECTS_TO = "connects_to"
    PART_OF = "part_of"
    MANAGES = "manages"
    DOCUMENTED_BY = "documented_by"
    PROCEDURE_FOR = "procedure_for"
    TRIGGERED_BY = "triggered_by"
    DEPENDS_ON = "depends_on"

class EntityRelationship(Base, InbetweeniesTimestampMixin):
    """Edges connecting entities in the knowledge graph"""
    __tablename__ = "entity_relationships"
    
    id = Column(String(36), primary_key=True)
    from_entity_id = Column(String(36), ForeignKey("entities.id"))
    to_entity_id = Column(String(36), ForeignKey("entities.id"))
    relationship_type = Column(Enum(RelationshipType), nullable=False)
    properties = Column(JSON, default={})
    user_id = Column(String(36), ForeignKey("users.id"))
```

## Graph Storage Implementation

### Repository Pattern
```python
# funkygibbon/repositories/graph.py
class GraphRepository:
    """Repository for graph operations"""
    
    async def store_entity(self, entity: Entity) -> Entity:
        """Store entity with version tracking"""
        
    async def get_entity(self, entity_id: str, version: str = None) -> Entity:
        """Get specific version or latest"""
        
    async def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a type"""
        
    async def store_relationship(self, relationship: EntityRelationship):
        """Store relationship between entities"""
        
    async def get_relationships(self, from_id: str = None, to_id: str = None, 
                               rel_type: RelationshipType = None) -> List[EntityRelationship]:
        """Query relationships with filters"""
```

### Graph Index for Performance
```python
# funkygibbon/graph/index.py
class GraphIndex:
    """In-memory graph structure for fast operations"""
    
    def __init__(self):
        self.entities: Dict[str, Entity] = {}
        self.relationships_by_source: Dict[str, List[EntityRelationship]] = {}
        self.relationships_by_target: Dict[str, List[EntityRelationship]] = {}
    
    async def load_from_storage(self, graph_repo: GraphRepository):
        """Initialize graph from persistent storage"""
        
    def find_path(self, from_id: str, to_id: str) -> List[str]:
        """BFS path finding between entities"""
        
    def get_connected_entities(self, entity_id: str, rel_type: RelationshipType = None):
        """Get all connected entities with optional relationship filter"""
```

## Search and Query Engine

### Full-Text Search
```python
# funkygibbon/search/engine.py
class SearchEngine:
    """Text and semantic search capabilities"""
    
    def search_entities(self, query: str, entity_types: List[EntityType] = None) -> List[SearchResult]:
        """Full-text search across entity content"""
        
    def find_similar(self, entity_id: str, threshold: float = 0.7) -> List[SearchResult]:
        """Find similar entities using content analysis"""
        
    def search_by_properties(self, properties: Dict[str, Any]) -> List[SearchResult]:
        """Search entities by specific property values"""
```

## MCP Server Integration

### Tool Definitions
```python
# funkygibbon/mcp/tools.py
MCP_TOOLS = [
    {
        "name": "get_devices_in_room",
        "description": "Get all devices in a specific room",
        "parameters": {
            "room_id": {"type": "string", "description": "Room entity ID"}
        }
    },
    {
        "name": "find_device_controls", 
        "description": "Get available controls for a device",
        "parameters": {
            "device_id": {"type": "string", "description": "Device entity ID"}
        }
    },
    {
        "name": "get_room_connections",
        "description": "Find doors and passages between rooms",
        "parameters": {
            "room_id": {"type": "string", "description": "Room entity ID"}
        }
    },
    {
        "name": "search_entities",
        "description": "Search for entities by content",
        "parameters": {
            "query": {"type": "string", "description": "Search query"},
            "entity_types": {"type": "array", "description": "Filter by entity types"}
        }
    },
    {
        "name": "create_entity",
        "description": "Create a new entity in the graph",
        "parameters": {
            "entity_type": {"type": "string", "description": "Type of entity"},
            "name": {"type": "string", "description": "Entity name"},
            "content": {"type": "object", "description": "Entity properties"}
        }
    },
    {
        "name": "create_relationship",
        "description": "Create relationship between entities",
        "parameters": {
            "from_entity_id": {"type": "string", "description": "Source entity"},
            "to_entity_id": {"type": "string", "description": "Target entity"},
            "relationship_type": {"type": "string", "description": "Type of relationship"}
        }
    }
]
```

### MCP Server Implementation
```python
# funkygibbon/mcp/server.py
class FunkyGibbonMCPServer:
    """MCP server exposing graph operations"""
    
    def __init__(self, graph_index: GraphIndex):
        self.graph = graph_index
        self.register_tools()
    
    async def handle_tool_call(self, tool_name: str, arguments: dict):
        """Route tool calls to appropriate handlers"""
        
    async def get_devices_in_room(self, room_id: str):
        """Implementation of room device query"""
        
    async def find_device_controls(self, device_id: str):
        """Get controls for a specific device"""
```

## API Layer

### REST Endpoints
```python
# funkygibbon/api/routers/graph.py
@router.post("/entities")
async def create_entity(entity: EntityCreate):
    """Create new graph entity"""

@router.get("/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Get entity by ID"""

@router.get("/entities/{entity_id}/relationships")
async def get_entity_relationships(entity_id: str):
    """Get all relationships for an entity"""

@router.post("/relationships")
async def create_relationship(relationship: RelationshipCreate):
    """Create new relationship"""

@router.post("/search")
async def search_graph(query: SearchQuery):
    """Search across the graph"""
```

### MCP Endpoint
```python
# funkygibbon/api/routers/mcp.py
@router.post("/mcp/tools/{tool_name}")
async def execute_mcp_tool(tool_name: str, arguments: dict):
    """Execute MCP tool and return results"""
    
@router.get("/mcp/tools")
async def list_available_tools():
    """List all available MCP tools"""
```

## Testing Strategy

### Unit Tests
```python
# tests/unit/test_entity_operations.py
- Test entity creation with all required fields
- Test entity versioning and parent tracking
- Test entity type validation
- Test JSON content storage and retrieval

# tests/unit/test_relationship_operations.py
- Test relationship creation between entities
- Test relationship type validation
- Test bidirectional relationship queries
- Test relationship property storage

# tests/unit/test_graph_index.py
- Test graph loading from storage
- Test path finding algorithms
- Test connected entity queries
- Test performance with large graphs
```

### Integration Tests
```python
# tests/integration/test_graph_api.py
- Test complete entity lifecycle via API
- Test relationship creation and querying
- Test search functionality
- Test concurrent operations

# tests/integration/test_mcp_tools.py
- Test each MCP tool implementation
- Test tool parameter validation
- Test error handling and responses
- Test tool discovery endpoint
```

### Performance Tests
```python
# tests/performance/test_graph_scale.py
- Benchmark graph operations with 10k+ entities
- Test query performance under load
- Measure memory usage of graph index
- Test concurrent read/write operations

# tests/performance/test_search_performance.py
- Test search speed with large datasets
- Benchmark similarity calculations
- Test index rebuild performance
```

### End-to-End Tests
```python
# tests/e2e/test_smart_home_scenarios.py
- Test device discovery in rooms
- Test automation rule creation
- Test procedure documentation
- Test cross-entity queries
```

## Implementation Timeline

### Week 1: Core Foundation
- **Day 1**: Set up project structure and database schema
- **Day 2**: Implement Entity and Relationship models
- **Day 3**: Build GraphRepository and basic CRUD operations
- **Day 4**: Implement GraphIndex and traversal algorithms
- **Day 5**: Unit tests and integration testing

### Week 2: Advanced Features
- **Day 1**: Build SearchEngine with full-text search
- **Day 2**: Implement MCP server and tool handlers
- **Day 3**: Create REST API endpoints
- **Day 4**: Performance optimization and caching
- **Day 5**: End-to-end testing and documentation

## Performance Targets

- **Entity Creation**: < 5ms per entity
- **Relationship Creation**: < 5ms per relationship
- **Graph Traversal**: < 10ms for typical queries
- **Search Operations**: < 50ms for full-text search
- **MCP Tool Execution**: < 100ms per tool call
- **Memory Usage**: < 500MB for 10k entities

## Dependencies

### Core Dependencies
```toml
# pyproject.toml additions
sqlalchemy = "^2.0.0"
fastapi = "^0.100.0"
pydantic = "^2.0.0"
asyncio = "^3.11.0"
```

### Optional Performance Libraries
```toml
# For advanced features
networkx = "^3.0"  # Graph algorithms
pyarrow = "^12.0"  # Efficient serialization
redis = "^4.5"     # Caching layer
```

## Risk Assessment

### Technical Risks
- **Risk**: Performance degradation with large graphs
  - **Mitigation**: Implement efficient indexing, caching, and lazy loading
  
- **Risk**: Complex query performance
  - **Mitigation**: Pre-compute common traversals, optimize algorithms

### Operational Risks
- **Risk**: Data consistency in distributed environment
  - **Mitigation**: Use proper transaction boundaries, implement eventual consistency

- **Risk**: Schema evolution challenges
  - **Mitigation**: Design flexible content field, version entities

## Success Criteria

1. **Performance**: All operations meet target latencies
2. **Scalability**: System handles 10k+ entities efficiently
3. **Reliability**: 99.9% uptime with proper error handling
4. **Extensibility**: Easy to add new entity and relationship types
5. **Testing**: >90% test coverage with comprehensive scenarios

## Next Steps

Upon completion of Phase 2:
1. Implement Phase 3: Enhanced Inbetweenies Protocol for graph synchronization
2. Build Phase 4: Swift/WildThing client implementation
3. Deploy monitoring and analytics
4. Gather user feedback and iterate