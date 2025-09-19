# The Goodies Chat System Integration Plan

## Executive Summary

This document outlines the design for a comprehensive chat system that integrates deeply with The Goodies smart home knowledge graph ecosystem. The system will provide natural language interaction with the 12 MCP tools while maintaining the existing architecture's integrity and performance characteristics.

## 1. Architecture Design

### 1.1 Event-Driven Architecture Overview

The chat system follows an event-driven, microservices-inspired architecture that maintains separation of concerns while enabling seamless integration:

```
┌─────────────────────────────────────────────────────────────────┐
│                    The Goodies Chat Ecosystem                   │
├─────────────────────────────────────────────────────────────────┤
│  Frontend Layer                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Streamlit Web   │  │ Enhanced CLI    │  │ REST API        │ │
│  │ Interface       │  │ (rich format)   │  │ Endpoints       │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Chat Orchestration Layer                                       │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ ChatInterface   │  │ ConversationMgr │  │ ResponseCache   │ │
│  │ (Main Entry)    │  │ (Context/Hist)  │  │ (Performance)   │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Processing Layer                                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ ToolExecutor    │  │ ModelManager    │  │ AuthManager     │ │
│  │ (MCP Tools)     │  │ (Multi-LLM)     │  │ (JWT/Security)  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Integration Layer                                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ FunkyGibbon     │  │ BlowingOff      │  │ Inbetweenies    │ │
│  │ Server          │  │ Client          │  │ Protocol        │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  Data Layer                                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ SQLite Graph    │  │ Local Cache     │  │ Conversation    │ │
│  │ Database        │  │ (BlowingOff)    │  │ Store           │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Core Integration Points

**FunkyGibbon Server Integration:**
- Extends existing FastAPI endpoints with `/api/v1/chat/*` routes
- Leverages existing JWT authentication and role-based access
- Uses existing MCP tool implementations directly
- Maintains graph database consistency

**BlowingOff Client Integration:**
- Adds chat client capabilities to existing sync client
- Utilizes local graph cache for offline responses
- Implements conversation queue for offline-to-online sync
- Maintains existing conflict resolution patterns

**Inbetweenies Protocol Extension:**
- Adds chat message models alongside existing entity models
- Extends MCP tools with chat-aware metadata
- Maintains backward compatibility with existing tools

### 1.3 Caching Architecture

**Multi-Level Caching Strategy:**
```
Request → Auth Cache → Response Cache → Tool Cache → DB
     ↓         ↓           ↓           ↓         ↓
   30s       5min       1hour      30min    Persistent
```

**Cache Types:**
- **Authentication Cache**: JWT validation results (30s TTL)
- **Response Cache**: Complete chat responses (5min TTL, invalidated by graph changes)
- **Tool Cache**: MCP tool execution results (1hour TTL, content-based)
- **Context Cache**: Conversation context windows (session-based)

### 1.4 Async/Await Patterns

**Concurrent Operation Flow:**
```python
async def process_chat_request(message: str, context: ConversationContext):
    # Parallel operations
    auth_task = asyncio.create_task(validate_authentication(context.token))
    tools_task = asyncio.create_task(identify_relevant_tools(message))
    history_task = asyncio.create_task(load_conversation_history(context.id))

    # Wait for critical path
    auth_result, relevant_tools = await asyncio.gather(auth_task, tools_task)

    # Parallel tool execution
    tool_tasks = [execute_tool(tool, message, context) for tool in relevant_tools]
    tool_results = await asyncio.gather(*tool_tasks, return_exceptions=True)

    # Response generation
    response = await generate_response(message, tool_results, await history_task)

    # Fire-and-forget operations
    asyncio.create_task(cache_response(message, response))
    asyncio.create_task(update_conversation_history(context.id, message, response))

    return response
```

## 2. Component Design

### 2.1 Enhanced ChatInterface Class

**File: `chat/interface/chat_interface.py`**

```python
class ChatInterface:
    """Main entry point for chat interactions with The Goodies ecosystem."""

    def __init__(self,
                 model_manager: ModelManager,
                 tool_executor: ToolExecutor,
                 conversation_manager: ConversationManager,
                 cache_manager: ResponseCache,
                 auth_manager: AuthManager):
        self.model_manager = model_manager
        self.tool_executor = tool_executor
        self.conversation_manager = conversation_manager
        self.cache_manager = cache_manager
        self.auth_manager = auth_manager

        # Event system for loose coupling
        self.events = EventEmitter()
        self._setup_event_handlers()

    async def process_message(self,
                            message: str,
                            user_context: UserContext,
                            conversation_id: Optional[str] = None) -> ChatResponse:
        """Process a chat message with full context awareness."""

        # Authentication and authorization
        auth_result = await self.auth_manager.validate_user_access(user_context)
        if not auth_result.is_valid:
            raise AuthenticationError(auth_result.error_message)

        # Check cache first
        cache_key = self._generate_cache_key(message, user_context, conversation_id)
        cached_response = await self.cache_manager.get(cache_key)
        if cached_response and not self._requires_fresh_data(message):
            return cached_response

        # Load conversation context
        conversation = await self.conversation_manager.get_or_create(
            conversation_id, user_context.user_id
        )

        # Plan tool execution
        execution_plan = await self.tool_executor.plan_execution(
            message, conversation.context, auth_result.permissions
        )

        # Execute tools concurrently
        tool_results = await self.tool_executor.execute_parallel(execution_plan)

        # Generate response
        response = await self.model_manager.generate_response(
            message=message,
            conversation_context=conversation.context,
            tool_results=tool_results,
            user_preferences=user_context.preferences
        )

        # Update conversation and cache
        await asyncio.gather(
            self.conversation_manager.add_exchange(conversation_id, message, response),
            self.cache_manager.set(cache_key, response),
            self._emit_analytics_event(message, response, tool_results)
        )

        return response

    def _setup_event_handlers(self):
        """Setup event handlers for system integration."""
        self.events.on('graph_updated', self._invalidate_related_cache)
        self.events.on('user_permissions_changed', self._clear_user_cache)
        self.events.on('tool_executed', self._update_tool_metrics)
```

**Key Features:**
- Modular component injection for testability
- Event-driven architecture for loose coupling
- Comprehensive caching with intelligent invalidation
- Parallel tool execution for performance
- Full integration with existing auth system

### 2.2 ToolExecutor for Structured Function Calling

**File: `chat/tools/tool_executor.py`**

```python
class ToolExecutor:
    """Executes The Goodies MCP tools with chat-aware context."""

    def __init__(self, mcp_tools: Dict[str, MCPTool], graph_client: GraphClient):
        self.tools = mcp_tools
        self.graph_client = graph_client
        self.execution_cache = TTLCache(maxsize=1000, ttl=1800)  # 30min

    async def plan_execution(self,
                           message: str,
                           context: ConversationContext,
                           permissions: UserPermissions) -> ExecutionPlan:
        """Plan which tools to execute based on message analysis."""

        # Natural language to tool mapping
        tool_candidates = await self._identify_candidate_tools(message)

        # Filter by permissions
        allowed_tools = [
            tool for tool in tool_candidates
            if permissions.can_execute_tool(tool.name)
        ]

        # Dependency analysis
        execution_graph = self._build_execution_graph(allowed_tools, context)

        # Optimization: parallel vs sequential execution
        parallel_groups = self._optimize_execution_order(execution_graph)

        return ExecutionPlan(
            tools=allowed_tools,
            execution_groups=parallel_groups,
            estimated_duration=self._estimate_execution_time(allowed_tools),
            context_requirements=self._analyze_context_needs(allowed_tools)
        )

    async def execute_parallel(self, plan: ExecutionPlan) -> List[ToolResult]:
        """Execute tools according to the execution plan."""
        results = []

        for group in plan.execution_groups:
            # Execute tools in parallel within each group
            group_tasks = [
                self._execute_single_tool(tool, plan.context)
                for tool in group
            ]

            group_results = await asyncio.gather(*group_tasks, return_exceptions=True)
            results.extend(group_results)

            # Check for critical failures that should stop execution
            if any(isinstance(r, CriticalToolError) for r in group_results):
                break

        return results

    async def _execute_single_tool(self,
                                 tool: MCPTool,
                                 context: ExecutionContext) -> ToolResult:
        """Execute a single MCP tool with caching and error handling."""

        # Generate cache key based on tool, parameters, and relevant context
        cache_key = self._generate_tool_cache_key(tool, context)

        # Check cache first
        if cache_key in self.execution_cache:
            cached_result = self.execution_cache[cache_key]
            if self._is_cache_valid(cached_result, tool):
                return cached_result

        try:
            # Execute the actual MCP tool
            start_time = time.time()
            result = await tool.execute(context.parameters)
            execution_time = time.time() - start_time

            # Wrap result with metadata
            tool_result = ToolResult(
                tool_name=tool.name,
                result=result,
                execution_time=execution_time,
                cache_key=cache_key,
                timestamp=datetime.utcnow()
            )

            # Cache successful results
            if tool_result.is_successful:
                self.execution_cache[cache_key] = tool_result

            return tool_result

        except Exception as e:
            return ToolResult(
                tool_name=tool.name,
                error=str(e),
                error_type=type(e).__name__,
                timestamp=datetime.utcnow()
            )

    async def _identify_candidate_tools(self, message: str) -> List[MCPTool]:
        """Use NLP to identify which tools are relevant to the message."""

        # Keyword-based mapping for The Goodies tools
        tool_mappings = {
            'device': ['get_devices_in_room', 'find_device_controls'],
            'room': ['get_devices_in_room', 'get_room_connections'],
            'automation': ['get_automations_in_room', 'get_procedures_for_device'],
            'search': ['search_entities', 'find_similar_entities'],
            'create': ['create_entity'],
            'update': ['update_entity'],
            'path': ['find_path'],
            'connection': ['get_room_connections', 'find_path']
        }

        # Extract keywords and intents
        keywords = self._extract_keywords(message.lower())
        candidate_tools = set()

        for keyword, tools in tool_mappings.items():
            if keyword in keywords:
                candidate_tools.update(tools)

        # Return actual tool instances
        return [self.tools[name] for name in candidate_tools if name in self.tools]
```

### 2.3 ModelManager for Multiple LLM Support

**File: `chat/models/model_manager.py`**

```python
class ModelManager:
    """Manages multiple LLM models with intelligent routing."""

    def __init__(self, model_configs: Dict[str, ModelConfig]):
        self.models = {}
        self.load_balancer = ModelLoadBalancer()
        self.response_cache = ResponseCache()

        for name, config in model_configs.items():
            self.models[name] = self._initialize_model(name, config)

    async def generate_response(self,
                              message: str,
                              conversation_context: ConversationContext,
                              tool_results: List[ToolResult],
                              user_preferences: UserPreferences) -> ChatResponse:
        """Generate a response using the most appropriate model."""

        # Model selection based on complexity and preferences
        selected_model = await self._select_optimal_model(
            message, tool_results, user_preferences
        )

        # Prepare context for the model
        context = self._prepare_model_context(
            message, conversation_context, tool_results
        )

        # Generate response with retries and fallbacks
        response = await self._generate_with_fallback(
            selected_model, context, user_preferences
        )

        # Post-process response
        processed_response = await self._post_process_response(
            response, tool_results, user_preferences
        )

        return ChatResponse(
            content=processed_response.content,
            model_used=selected_model.name,
            tool_results=tool_results,
            metadata=processed_response.metadata,
            timestamp=datetime.utcnow()
        )

    async def _select_optimal_model(self,
                                  message: str,
                                  tool_results: List[ToolResult],
                                  preferences: UserPreferences) -> Model:
        """Select the best model based on complexity and preferences."""

        complexity_score = self._calculate_complexity(message, tool_results)

        # Model selection rules
        if preferences.prefer_speed and complexity_score < 0.3:
            return self.models.get('claude-3-haiku', self.models['default'])
        elif complexity_score > 0.7 or len(tool_results) > 3:
            return self.models.get('claude-3-opus', self.models['default'])
        else:
            return self.models.get('claude-3-sonnet', self.models['default'])

    def _prepare_model_context(self,
                             message: str,
                             conversation_context: ConversationContext,
                             tool_results: List[ToolResult]) -> ModelContext:
        """Prepare context for model with smart truncation."""

        # System prompt specific to The Goodies
        system_prompt = self._build_system_prompt(conversation_context.user_role)

        # Format tool results for model consumption
        tool_context = self._format_tool_results(tool_results)

        # Conversation history with smart truncation
        history = self._truncate_conversation_history(
            conversation_context.history,
            target_tokens=4000  # Reserve space for response
        )

        return ModelContext(
            system_prompt=system_prompt,
            conversation_history=history,
            current_message=message,
            tool_context=tool_context,
            metadata=conversation_context.metadata
        )

    def _build_system_prompt(self, user_role: UserRole) -> str:
        """Build system prompt based on user role and The Goodies context."""

        base_prompt = """
        You are an AI assistant for The Goodies, a smart home knowledge graph system.
        You help users manage and interact with their smart home devices, rooms, and automations.

        Available tools provide access to:
        - Device discovery and control
        - Room and zone management
        - Automation and procedure execution
        - Graph navigation and search
        - Entity creation and updates

        Always be helpful, accurate, and security-conscious.
        """

        role_specific = {
            UserRole.ADMIN: "You have full access to all system capabilities.",
            UserRole.USER: "You have standard user access with some restrictions.",
            UserRole.GUEST: "You have read-only access for exploration."
        }

        return f"{base_prompt}\n\n{role_specific.get(user_role, '')}"
```

### 2.4 ConversationManager for Context and History

**File: `chat/conversation/conversation_manager.py`**

```python
class ConversationManager:
    """Manages conversation context, history, and persistence."""

    def __init__(self,
                 storage: ConversationStorage,
                 context_window_size: int = 8000):
        self.storage = storage
        self.context_window_size = context_window_size
        self.active_conversations = TTLCache(maxsize=1000, ttl=3600)

    async def get_or_create(self,
                          conversation_id: Optional[str],
                          user_id: str) -> Conversation:
        """Get existing conversation or create new one."""

        if conversation_id and conversation_id in self.active_conversations:
            return self.active_conversations[conversation_id]

        if conversation_id:
            # Load from storage
            conversation = await self.storage.load_conversation(conversation_id)
            if conversation and conversation.user_id == user_id:
                self.active_conversations[conversation_id] = conversation
                return conversation

        # Create new conversation
        new_conversation = Conversation(
            id=conversation_id or self._generate_conversation_id(),
            user_id=user_id,
            created_at=datetime.utcnow(),
            context=ConversationContext(),
            history=[]
        )

        await self.storage.save_conversation(new_conversation)
        self.active_conversations[new_conversation.id] = new_conversation

        return new_conversation

    async def add_exchange(self,
                         conversation_id: str,
                         user_message: str,
                         assistant_response: ChatResponse) -> None:
        """Add a message exchange to the conversation."""

        conversation = self.active_conversations.get(conversation_id)
        if not conversation:
            conversation = await self.storage.load_conversation(conversation_id)

        if conversation:
            # Add to history
            exchange = MessageExchange(
                user_message=user_message,
                assistant_response=assistant_response,
                timestamp=datetime.utcnow(),
                tool_results=assistant_response.tool_results
            )

            conversation.history.append(exchange)

            # Trim history if needed
            self._trim_conversation_history(conversation)

            # Update context
            self._update_conversation_context(conversation, exchange)

            # Persist changes
            await self.storage.save_conversation(conversation)
            self.active_conversations[conversation_id] = conversation

    def _trim_conversation_history(self, conversation: Conversation) -> None:
        """Trim conversation history to fit within context window."""

        total_tokens = sum(
            self._estimate_tokens(exchange)
            for exchange in conversation.history
        )

        while total_tokens > self.context_window_size and len(conversation.history) > 1:
            # Remove oldest exchange but keep system context
            removed_exchange = conversation.history.pop(0)
            total_tokens -= self._estimate_tokens(removed_exchange)

    def _update_conversation_context(self,
                                   conversation: Conversation,
                                   latest_exchange: MessageExchange) -> None:
        """Update conversation context based on latest exchange."""

        # Extract entities mentioned in the conversation
        entities = self._extract_entities(latest_exchange.user_message)
        conversation.context.mentioned_entities.update(entities)

        # Update topic tracking
        topics = self._extract_topics(latest_exchange.user_message)
        conversation.context.current_topics = topics

        # Update tool usage patterns
        if latest_exchange.tool_results:
            for tool_result in latest_exchange.tool_results:
                conversation.context.tool_usage_history.append(tool_result.tool_name)
```

### 2.5 ResponseCache for Performance Optimization

**File: `chat/cache/response_cache.py`**

```python
class ResponseCache:
    """High-performance caching system for chat responses."""

    def __init__(self,
                 redis_client: Optional[Redis] = None,
                 memory_cache_size: int = 1000):
        self.redis = redis_client
        self.memory_cache = TTLCache(maxsize=memory_cache_size, ttl=300)  # 5min
        self.cache_stats = CacheStats()

    async def get(self, cache_key: str) -> Optional[ChatResponse]:
        """Get cached response with multi-level lookup."""

        # Check memory cache first (fastest)
        if cache_key in self.memory_cache:
            self.cache_stats.memory_hits += 1
            return self.memory_cache[cache_key]

        # Check Redis cache (fast)
        if self.redis:
            cached_data = await self.redis.get(f"chat:{cache_key}")
            if cached_data:
                response = ChatResponse.from_json(cached_data)
                # Populate memory cache
                self.memory_cache[cache_key] = response
                self.cache_stats.redis_hits += 1
                return response

        self.cache_stats.misses += 1
        return None

    async def set(self,
                  cache_key: str,
                  response: ChatResponse,
                  ttl: int = 300) -> None:
        """Store response in multi-level cache."""

        # Store in memory cache
        self.memory_cache[cache_key] = response

        # Store in Redis with longer TTL
        if self.redis:
            await self.redis.setex(
                f"chat:{cache_key}",
                ttl * 2,  # Redis TTL is 2x memory TTL
                response.to_json()
            )

    async def invalidate_pattern(self, pattern: str) -> None:
        """Invalidate cache entries matching pattern."""

        # Clear matching entries from memory cache
        keys_to_remove = [
            key for key in self.memory_cache.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

        for key in keys_to_remove:
            del self.memory_cache[key]

        # Clear matching entries from Redis
        if self.redis:
            keys = await self.redis.keys(f"chat:{pattern}")
            if keys:
                await self.redis.delete(*keys)

    def generate_cache_key(self,
                         message: str,
                         user_context: UserContext,
                         conversation_context: Optional[ConversationContext] = None) -> str:
        """Generate cache key based on message content and context."""

        # Create hash of relevant context
        context_hash = hashlib.md5()
        context_hash.update(message.encode('utf-8'))
        context_hash.update(user_context.user_id.encode('utf-8'))
        context_hash.update(str(user_context.permissions).encode('utf-8'))

        if conversation_context:
            # Include recent context that might affect response
            recent_context = conversation_context.get_recent_context(max_exchanges=3)
            context_hash.update(str(recent_context).encode('utf-8'))

        return context_hash.hexdigest()
```

## 3. Integration Points

### 3.1 Deep Integration with The Goodies MCP Tools

**Enhanced Tool Integration:**
- All 12 existing MCP tools are wrapped with chat-aware metadata
- Tool execution results include natural language summaries
- Automatic parameter extraction from natural language queries
- Context-aware tool selection based on conversation history

**Tool Metadata Enhancement:**
```python
class ChatAwareMCPTool:
    """Wrapper for MCP tools with chat integration."""

    def __init__(self, base_tool: MCPTool):
        self.base_tool = base_tool
        self.chat_metadata = self._generate_chat_metadata()

    def _generate_chat_metadata(self) -> ToolChatMetadata:
        return ToolChatMetadata(
            natural_language_triggers=[
                "show me devices in {room}",
                "what's in the {room}",
                "devices in {room_name}"
            ],
            parameter_extraction_patterns={
                "room_id": r"(?:in|from|at)\s+(?:the\s+)?(\w+(?:\s+\w+)*)",
                "device_name": r"(?:device|light|switch|sensor)\s+(?:named\s+)?(['\"]?[\w\s]+['\"]?)"
            },
            response_formatting={
                "success": "Found {count} devices in {room_name}: {device_list}",
                "empty": "No devices found in {room_name}",
                "error": "Unable to access {room_name}: {error_message}"
            }
        )
```

### 3.2 Authentication Flow with JWT Tokens

**Seamless Auth Integration:**
```python
class ChatAuthManager:
    """Manages authentication for chat system using existing JWT infrastructure."""

    def __init__(self, jwt_handler: JWTHandler, user_service: UserService):
        self.jwt_handler = jwt_handler
        self.user_service = user_service
        self.auth_cache = TTLCache(maxsize=10000, ttl=30)  # 30s cache

    async def validate_user_access(self, user_context: UserContext) -> AuthResult:
        """Validate user access using existing JWT system."""

        cache_key = f"auth:{user_context.token_hash}"
        if cache_key in self.auth_cache:
            return self.auth_cache[cache_key]

        try:
            # Use existing JWT validation
            token_data = self.jwt_handler.decode_token(user_context.token)
            user = await self.user_service.get_user(token_data.user_id)

            auth_result = AuthResult(
                is_valid=True,
                user_id=user.id,
                role=user.role,
                permissions=self._calculate_permissions(user),
                expires_at=token_data.expires_at
            )

            self.auth_cache[cache_key] = auth_result
            return auth_result

        except JWTError as e:
            return AuthResult(is_valid=False, error_message=str(e))
```

### 3.3 Real-time Sync with FunkyGibbon Database

**Event-Driven Sync:**
```python
class ChatDatabaseSync:
    """Maintains real-time sync between chat system and graph database."""

    def __init__(self, graph_client: GraphClient, event_bus: EventBus):
        self.graph_client = graph_client
        self.event_bus = event_bus
        self._setup_event_handlers()

    def _setup_event_handlers(self):
        """Setup handlers for database change events."""

        self.event_bus.subscribe('entity.created', self._handle_entity_created)
        self.event_bus.subscribe('entity.updated', self._handle_entity_updated)
        self.event_bus.subscribe('entity.deleted', self._handle_entity_deleted)
        self.event_bus.subscribe('relationship.created', self._handle_relationship_changed)

    async def _handle_entity_created(self, event: EntityCreatedEvent):
        """Handle new entity creation for chat context."""

        # Invalidate relevant cache entries
        await self._invalidate_entity_cache(event.entity_type, event.entity_id)

        # Update conversation contexts that might be affected
        affected_conversations = await self._find_conversations_mentioning_entity(
            event.entity_type, event.entity_id
        )

        for conversation_id in affected_conversations:
            await self._update_conversation_context(
                conversation_id,
                f"New {event.entity_type} '{event.entity_id}' was created"
            )
```

### 3.4 Offline Mode with Local Graph Caching

**BlowingOff Client Enhancement:**
```python
class ChatOfflineManager:
    """Manages offline chat capabilities with local graph cache."""

    def __init__(self,
                 local_cache: LocalGraphCache,
                 conversation_store: LocalConversationStore):
        self.local_cache = local_cache
        self.conversation_store = conversation_store
        self.offline_queue = OfflineQueue()

    async def process_offline_message(self,
                                    message: str,
                                    user_context: UserContext) -> ChatResponse:
        """Process chat message using local cache when offline."""

        # Check if we can answer from local cache
        available_tools = self._get_offline_available_tools()

        # Simple keyword-based tool selection for offline mode
        relevant_tools = self._select_offline_tools(message, available_tools)

        # Execute tools against local cache
        tool_results = []
        for tool in relevant_tools:
            result = await self._execute_offline_tool(tool, message)
            tool_results.append(result)

        # Generate response (may be limited offline)
        response = await self._generate_offline_response(message, tool_results)

        # Queue for sync when online
        await self.offline_queue.add_message(message, response)

        return response

    async def sync_when_online(self):
        """Sync offline conversations when connection is restored."""

        queued_items = await self.offline_queue.get_all()

        for item in queued_items:
            try:
                # Re-process with online capabilities
                online_response = await self._reprocess_with_online_tools(item)

                # Update conversation history
                await self.conversation_store.update_response(
                    item.conversation_id,
                    item.message_id,
                    online_response
                )

                await self.offline_queue.mark_synced(item.id)

            except Exception as e:
                # Log error but continue with other items
                logger.error(f"Failed to sync item {item.id}: {e}")
```

## 4. User Interface Design

### 4.1 Streamlit-based Web Interface

**File: `chat/ui/streamlit_app.py`**

```python
import streamlit as st
from chat.interface.chat_interface import ChatInterface
from chat.models.chat_models import UserContext

def main():
    st.set_page_config(
        page_title="The Goodies Chat",
        page_icon="🏠",
        layout="wide"
    )

    # Initialize chat interface
    if 'chat_interface' not in st.session_state:
        st.session_state.chat_interface = ChatInterface.from_config()

    # Authentication sidebar
    with st.sidebar:
        st.title("🏠 The Goodies")
        auth_token = st.text_input("Access Token", type="password")

        if auth_token:
            user_context = UserContext(token=auth_token)
            st.session_state.user_context = user_context

            # Show user info
            try:
                auth_result = st.session_state.chat_interface.auth_manager.validate_user_sync(user_context)
                if auth_result.is_valid:
                    st.success(f"Logged in as: {auth_result.user_id}")
                    st.info(f"Role: {auth_result.role}")
                else:
                    st.error("Invalid token")
            except Exception as e:
                st.error(f"Auth error: {e}")

    # Main chat interface
    st.title("Smart Home Assistant")

    # Chat history
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

            # Show tool results if available
            if message.get("tool_results"):
                with st.expander("Tool Results"):
                    for tool_result in message["tool_results"]:
                        st.json(tool_result.to_dict())

    # Chat input
    if prompt := st.chat_input("Ask about your smart home..."):
        if 'user_context' not in st.session_state:
            st.error("Please provide an access token")
            return

        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    response = await st.session_state.chat_interface.process_message(
                        prompt,
                        st.session_state.user_context
                    )

                    st.markdown(response.content)

                    # Add assistant response to chat history
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_results": response.tool_results,
                        "model_used": response.model_used
                    })

                except Exception as e:
                    st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
```

### 4.2 Enhanced CLI with Rich Formatting

**File: `chat/cli/enhanced_cli.py`**

```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.progress import track
import asyncio

class EnhancedChatCLI:
    """Enhanced CLI for The Goodies chat with rich formatting."""

    def __init__(self, chat_interface: ChatInterface):
        self.chat_interface = chat_interface
        self.console = Console()
        self.conversation_id = None

    async def run_interactive(self):
        """Run interactive chat session."""

        self.console.print(Panel(
            "[bold blue]The Goodies Smart Home Assistant[/bold blue]\n"
            "Type 'help' for commands, 'quit' to exit",
            title="🏠 Welcome"
        ))

        # Authentication
        auth_token = self.console.input("[bold]Access Token: [/bold]")
        user_context = UserContext(token=auth_token)

        try:
            auth_result = await self.chat_interface.auth_manager.validate_user_access(user_context)
            if not auth_result.is_valid:
                self.console.print("[red]Authentication failed[/red]")
                return

            self.console.print(f"[green]Welcome, {auth_result.user_id}![/green]")

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return

        # Main chat loop
        while True:
            try:
                message = self.console.input("\n[bold cyan]You:[/bold cyan] ")

                if message.lower() in ['quit', 'exit']:
                    break
                elif message.lower() == 'help':
                    self._show_help()
                    continue
                elif message.lower() == 'clear':
                    self.console.clear()
                    continue
                elif message.lower() == 'stats':
                    await self._show_stats()
                    continue

                # Process message with progress indication
                with self.console.status("[bold green]Processing...") as status:
                    response = await self.chat_interface.process_message(
                        message, user_context, self.conversation_id
                    )

                    if not self.conversation_id:
                        self.conversation_id = response.conversation_id

                # Display response with formatting
                self._display_response(response)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Interrupted[/yellow]")
                break
            except Exception as e:
                self.console.print(f"[red]Error: {e}[/red]")

    def _display_response(self, response: ChatResponse):
        """Display chat response with rich formatting."""

        # Main response
        self.console.print(f"\n[bold magenta]Assistant:[/bold magenta] {response.content}")

        # Tool results if any
        if response.tool_results:
            self.console.print("\n[bold yellow]Tool Results:[/bold yellow]")

            for tool_result in response.tool_results:
                if tool_result.is_successful:
                    # Create table for structured data
                    if isinstance(tool_result.result, list):
                        table = Table(title=f"Results from {tool_result.tool_name}")

                        if tool_result.result and isinstance(tool_result.result[0], dict):
                            # Add columns from first item
                            for key in tool_result.result[0].keys():
                                table.add_column(key.replace('_', ' ').title())

                            # Add rows
                            for item in tool_result.result[:10]:  # Limit to 10 items
                                table.add_row(*[str(v) for v in item.values()])

                        self.console.print(table)
                    else:
                        # Simple result display
                        self.console.print(Panel(
                            str(tool_result.result),
                            title=tool_result.tool_name,
                            border_style="green"
                        ))
                else:
                    # Error display
                    self.console.print(Panel(
                        f"Error: {tool_result.error}",
                        title=f"{tool_result.tool_name} (Failed)",
                        border_style="red"
                    ))

        # Metadata
        metadata_text = f"Model: {response.model_used} | "
        metadata_text += f"Time: {response.timestamp.strftime('%H:%M:%S')}"

        if response.tool_results:
            tool_count = len(response.tool_results)
            metadata_text += f" | Tools: {tool_count}"

        self.console.print(f"[dim]{metadata_text}[/dim]")

    def _show_help(self):
        """Display help information."""

        help_table = Table(title="Available Commands")
        help_table.add_column("Command", style="cyan")
        help_table.add_column("Description", style="white")

        commands = [
            ("help", "Show this help message"),
            ("clear", "Clear the screen"),
            ("stats", "Show conversation statistics"),
            ("quit/exit", "Exit the chat")
        ]

        for cmd, desc in commands:
            help_table.add_row(cmd, desc)

        self.console.print(help_table)

        # Show available tools
        tools_panel = Panel(
            "get_devices_in_room • find_device_controls • get_room_connections\n"
            "search_entities • find_similar_entities • create_entity\n"
            "update_entity • find_path • get_automations_in_room\n"
            "get_procedures_for_device",
            title="Available MCP Tools",
            border_style="blue"
        )

        self.console.print(tools_panel)
```

### 4.3 API Endpoints for Programmatic Access

**File: `chat/api/chat_endpoints.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, WebSocket
from fastapi.security import HTTPBearer
from chat.interface.chat_interface import ChatInterface
from chat.models.api_models import *

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
security = HTTPBearer()

@router.post("/message", response_model=ChatResponse)
async def send_message(
    request: ChatMessageRequest,
    token: str = Depends(security),
    chat_interface: ChatInterface = Depends(get_chat_interface)
):
    """Send a message to the chat system."""

    try:
        user_context = UserContext(token=token.credentials)

        response = await chat_interface.process_message(
            message=request.message,
            user_context=user_context,
            conversation_id=request.conversation_id
        )

        return response

    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/conversations", response_model=List[ConversationSummary])
async def list_conversations(
    token: str = Depends(security),
    limit: int = 20,
    offset: int = 0,
    conversation_manager: ConversationManager = Depends(get_conversation_manager)
):
    """List user's conversations."""

    user_context = UserContext(token=token.credentials)
    auth_result = await chat_interface.auth_manager.validate_user_access(user_context)

    if not auth_result.is_valid:
        raise HTTPException(status_code=401, detail="Invalid token")

    conversations = await conversation_manager.list_user_conversations(
        user_id=auth_result.user_id,
        limit=limit,
        offset=offset
    )

    return conversations

@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    token: str = Depends(security),
    conversation_manager: ConversationManager = Depends(get_conversation_manager)
):
    """Get conversation details and history."""

    user_context = UserContext(token=token.credentials)
    auth_result = await chat_interface.auth_manager.validate_user_access(user_context)

    if not auth_result.is_valid:
        raise HTTPException(status_code=401, detail="Invalid token")

    conversation = await conversation_manager.get_conversation(conversation_id)

    if not conversation or conversation.user_id != auth_result.user_id:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return ConversationDetail.from_conversation(conversation)

@router.websocket("/ws/{conversation_id}")
async def websocket_chat(
    websocket: WebSocket,
    conversation_id: str,
    token: str,
    chat_interface: ChatInterface = Depends(get_chat_interface)
):
    """WebSocket endpoint for real-time chat."""

    await websocket.accept()

    try:
        # Validate token
        user_context = UserContext(token=token)
        auth_result = await chat_interface.auth_manager.validate_user_access(user_context)

        if not auth_result.is_valid:
            await websocket.close(code=1008, reason="Authentication failed")
            return

        # Chat loop
        while True:
            # Receive message
            data = await websocket.receive_json()
            message = data.get('message', '')

            if not message:
                continue

            # Process message
            response = await chat_interface.process_message(
                message=message,
                user_context=user_context,
                conversation_id=conversation_id
            )

            # Send response
            await websocket.send_json({
                'type': 'response',
                'data': response.to_dict()
            })

    except Exception as e:
        await websocket.close(code=1011, reason=str(e))

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    token: str = Depends(security),
    conversation_manager: ConversationManager = Depends(get_conversation_manager)
):
    """Delete a conversation."""

    user_context = UserContext(token=token.credentials)
    auth_result = await chat_interface.auth_manager.validate_user_access(user_context)

    if not auth_result.is_valid:
        raise HTTPException(status_code=401, detail="Invalid token")

    success = await conversation_manager.delete_conversation(
        conversation_id=conversation_id,
        user_id=auth_result.user_id
    )

    if not success:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return {"message": "Conversation deleted successfully"}
```

### 4.4 WebSocket Support for Real-time Updates

**File: `chat/websocket/websocket_manager.py`**

```python
class WebSocketManager:
    """Manages WebSocket connections for real-time chat updates."""

    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.connection_metadata: Dict[WebSocket, ConnectionMetadata] = {}

    async def connect(self,
                     websocket: WebSocket,
                     conversation_id: str,
                     user_id: str):
        """Connect a WebSocket to a conversation."""

        await websocket.accept()

        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = []

        self.active_connections[conversation_id].append(websocket)
        self.connection_metadata[websocket] = ConnectionMetadata(
            conversation_id=conversation_id,
            user_id=user_id,
            connected_at=datetime.utcnow()
        )

    def disconnect(self, websocket: WebSocket, conversation_id: str):
        """Disconnect a WebSocket."""

        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].remove(websocket)

            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

        if websocket in self.connection_metadata:
            del self.connection_metadata[websocket]

    async def broadcast_to_conversation(self,
                                      conversation_id: str,
                                      message: dict,
                                      exclude_websocket: Optional[WebSocket] = None):
        """Broadcast message to all connections in a conversation."""

        if conversation_id not in self.active_connections:
            return

        connections = self.active_connections[conversation_id].copy()

        for websocket in connections:
            if websocket == exclude_websocket:
                continue

            try:
                await websocket.send_json(message)
            except ConnectionClosedError:
                # Clean up dead connection
                self.disconnect(websocket, conversation_id)

    async def send_typing_indicator(self,
                                   conversation_id: str,
                                   user_id: str,
                                   is_typing: bool):
        """Send typing indicator to conversation participants."""

        message = {
            'type': 'typing',
            'data': {
                'user_id': user_id,
                'is_typing': is_typing,
                'timestamp': datetime.utcnow().isoformat()
            }
        }

        await self.broadcast_to_conversation(conversation_id, message)

    async def send_system_notification(self,
                                     conversation_id: str,
                                     notification: SystemNotification):
        """Send system notification to conversation participants."""

        message = {
            'type': 'system_notification',
            'data': notification.to_dict()
        }

        await self.broadcast_to_conversation(conversation_id, message)
```

## 5. Data Flow

### 5.1 Request → Authentication → Tool Planning → Execution → Response

**Complete Data Flow Diagram:**

```
┌─────────────────────────────────────────────────────────────────┐
│                        Chat Request Flow                         │
├─────────────────────────────────────────────────────────────────┤
│  1. Request Reception                                           │
│     ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│     │ Streamlit   │    │ CLI Client  │    │ API Request │      │
│     │ Interface   │    │             │    │             │      │
│     └─────────────┘    └─────────────┘    └─────────────┘      │
│            │                   │                   │           │
│            └───────────────────┼───────────────────┘           │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  2. Authentication & Authorization                              │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ ChatAuthManager                                         │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ JWT Token   │  │ User Role   │  │ Permissions │     │ │
│     │ │ Validation  │  │ Resolution  │  │ Check       │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  3. Context Loading & Cache Check                              │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ ConversationManager + ResponseCache                     │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ Load Conv   │  │ Check Cache │  │ Extract     │     │ │
│     │ │ History     │  │ (Memory+    │  │ Context     │     │ │
│     │ │             │  │ Redis)      │  │             │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  4. Tool Planning & Selection                                  │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ ToolExecutor.plan_execution()                           │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ NLP         │  │ Permission  │  │ Dependency  │     │ │
│     │ │ Analysis    │  │ Filtering   │  │ Analysis    │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  5. Parallel Tool Execution                                    │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ async/await Parallel Execution                          │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ MCP Tool 1  │  │ MCP Tool 2  │  │ MCP Tool N  │     │ │
│     │ │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │     │ │
│     │ │ │ Cache   │ │  │ │ Cache   │ │  │ │ Cache   │ │     │ │
│     │ │ │ Check   │ │  │ │ Check   │ │  │ │ Check   │ │     │ │
│     │ │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │     │ │
│     │ │ ┌─────────┐ │  │ ┌─────────┐ │  │ ┌─────────┐ │     │ │
│     │ │ │ Execute │ │  │ │ Execute │ │  │ │ Execute │ │     │ │
│     │ │ │ Tool    │ │  │ │ Tool    │ │  │ │ Tool    │ │     │ │
│     │ │ └─────────┘ │  │ └─────────┘ │  │ └─────────┘ │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  6. Response Generation                                        │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ ModelManager.generate_response()                        │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ Model       │  │ Context     │  │ Response    │     │ │
│     │ │ Selection   │  │ Assembly    │  │ Generation  │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  7. Response Processing & Caching                              │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ Parallel Post-Processing                                │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ Update      │  │ Cache       │  │ Analytics   │     │ │
│     │ │ Conversation│  │ Response    │  │ Event       │     │ │
│     │ │ History     │  │             │  │             │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                ▼                               │
├─────────────────────────────────────────────────────────────────┤
│  8. Response Delivery                                          │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ Format for Client                                       │ │
│     │ ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │ │
│     │ │ Streamlit   │  │ CLI Rich    │  │ JSON API    │     │ │
│     │ │ Formatting  │  │ Formatting  │  │ Response    │     │ │
│     │ └─────────────┘  └─────────────┘  └─────────────┘     │ │
│     └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Context Window Management Strategy

**Intelligent Context Management:**

```python
class ContextWindowManager:
    """Manages conversation context within LLM token limits."""

    def __init__(self, max_context_tokens: int = 6000):
        self.max_context_tokens = max_context_tokens
        self.token_estimator = TokenEstimator()

    def prepare_context(self,
                       conversation: Conversation,
                       current_message: str,
                       tool_results: List[ToolResult]) -> ContextWindow:
        """Prepare context window with smart truncation."""

        # Reserve tokens for response generation
        available_tokens = self.max_context_tokens - 2000

        # Priority order for context inclusion
        context_components = [
            ("system_prompt", self._get_system_prompt(), 500),  # Always include
            ("current_message", current_message, len(current_message) // 4),
            ("tool_results", self._format_tool_results(tool_results), 1000),
            ("conversation_summary", conversation.get_summary(), 300),
            ("recent_history", conversation.get_recent_exchanges(5), 2000),
            ("entity_context", conversation.get_mentioned_entities(), 500),
            ("older_history", conversation.get_older_exchanges(), 1000)
        ]

        # Build context within token budget
        included_components = {}
        remaining_tokens = available_tokens

        for component_name, content, max_tokens in context_components:
            estimated_tokens = self.token_estimator.estimate(content)

            if estimated_tokens <= min(remaining_tokens, max_tokens):
                included_components[component_name] = content
                remaining_tokens -= estimated_tokens
            elif component_name in ["system_prompt", "current_message", "tool_results"]:
                # Truncate critical components rather than exclude
                truncated_content = self._truncate_to_tokens(content, max_tokens)
                included_components[component_name] = truncated_content
                remaining_tokens -= max_tokens

        return ContextWindow(
            components=included_components,
            total_tokens=available_tokens - remaining_tokens,
            truncated_components=self._get_truncated_components(context_components, included_components)
        )
```

### 5.3 Conversation Persistence and Retrieval

**Efficient Storage Strategy:**

```python
class ConversationStorage:
    """Handles conversation persistence with performance optimization."""

    def __init__(self, db_connection: AsyncConnection):
        self.db = db_connection
        self.compression = ConversationCompression()

    async def save_conversation(self, conversation: Conversation):
        """Save conversation with compression and indexing."""

        # Compress conversation data
        compressed_data = self.compression.compress_conversation(conversation)

        # Update database with UPSERT pattern
        await self.db.execute("""
            INSERT INTO conversations (
                id, user_id, title, created_at, updated_at,
                compressed_data, entity_mentions, topic_tags,
                message_count, last_activity
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            ) ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                compressed_data = excluded.compressed_data,
                entity_mentions = excluded.entity_mentions,
                topic_tags = excluded.topic_tags,
                message_count = excluded.message_count,
                last_activity = excluded.last_activity
        """, (
            conversation.id,
            conversation.user_id,
            conversation.get_title(),
            conversation.created_at,
            datetime.utcnow(),
            compressed_data,
            json.dumps(list(conversation.get_mentioned_entities())),
            json.dumps(conversation.get_topic_tags()),
            len(conversation.history),
            datetime.utcnow()
        ))

        # Update search index
        await self._update_search_index(conversation)

    async def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Load conversation with decompression."""

        row = await self.db.fetch_one("""
            SELECT * FROM conversations WHERE id = ?
        """, (conversation_id,))

        if not row:
            return None

        # Decompress conversation data
        conversation = self.compression.decompress_conversation(row['compressed_data'])

        # Restore metadata
        conversation.id = row['id']
        conversation.user_id = row['user_id']
        conversation.created_at = row['created_at']

        return conversation

    async def search_conversations(self,
                                 user_id: str,
                                 query: str,
                                 limit: int = 20) -> List[ConversationSummary]:
        """Search conversations with full-text search."""

        results = await self.db.fetch_all("""
            SELECT id, title, created_at, updated_at, message_count, last_activity,
                   entity_mentions, topic_tags
            FROM conversations
            WHERE user_id = ?
            AND (
                title LIKE ? OR
                entity_mentions LIKE ? OR
                topic_tags LIKE ?
            )
            ORDER BY last_activity DESC
            LIMIT ?
        """, (
            user_id,
            f"%{query}%",
            f"%{query}%",
            f"%{query}%",
            limit
        ))

        return [ConversationSummary.from_row(row) for row in results]
```

### 5.4 Error Handling and Recovery Flows

**Comprehensive Error Management:**

```python
class ChatErrorHandler:
    """Handles errors with graceful degradation and recovery."""

    def __init__(self, fallback_responses: FallbackResponses):
        self.fallback_responses = fallback_responses
        self.error_metrics = ErrorMetrics()

    async def handle_tool_execution_error(self,
                                        error: ToolExecutionError,
                                        context: ExecutionContext) -> ToolResult:
        """Handle tool execution errors with smart fallbacks."""

        self.error_metrics.record_tool_error(error.tool_name, error.error_type)

        # Determine recovery strategy
        if error.error_type == "network_timeout":
            # Try local cache or offline mode
            return await self._try_offline_fallback(error.tool_name, context)

        elif error.error_type == "permission_denied":
            # Return informative error with suggestions
            return ToolResult(
                tool_name=error.tool_name,
                error="Permission denied. Please check your access level.",
                suggestions=["Contact administrator for elevated permissions"],
                error_type="permission_denied"
            )

        elif error.error_type == "database_error":
            # Try read-only operations or cached data
            return await self._try_readonly_fallback(error.tool_name, context)

        else:
            # Generic error handling
            return ToolResult(
                tool_name=error.tool_name,
                error=f"Tool execution failed: {error.message}",
                error_type=error.error_type,
                recovery_suggestions=self._get_recovery_suggestions(error)
            )

    async def handle_model_error(self,
                               error: ModelError,
                               context: ModelContext) -> ChatResponse:
        """Handle LLM model errors with fallback models."""

        self.error_metrics.record_model_error(error.model_name, error.error_type)

        if error.error_type == "rate_limit_exceeded":
            # Try alternative model
            fallback_model = self._get_fallback_model(error.model_name)
            if fallback_model:
                return await fallback_model.generate_response(context)

        elif error.error_type == "context_length_exceeded":
            # Truncate context and retry
            truncated_context = self._truncate_context(context, 0.7)
            return await error.model.generate_response(truncated_context)

        # Use template response as last resort
        return self.fallback_responses.get_generic_error_response(
            error_message=error.message,
            suggestions=["Try rephrasing your question", "Check system status"]
        )

    async def handle_authentication_error(self,
                                        error: AuthenticationError) -> dict:
        """Handle auth errors with clear guidance."""

        if error.error_type == "token_expired":
            return {
                "error": "Your session has expired",
                "action_required": "refresh_token",
                "instructions": "Please log in again to continue"
            }

        elif error.error_type == "insufficient_permissions":
            return {
                "error": "Insufficient permissions for this action",
                "action_required": "upgrade_access",
                "instructions": "Contact administrator for access upgrade"
            }

        else:
            return {
                "error": "Authentication failed",
                "action_required": "re_authenticate",
                "instructions": "Please check your credentials and try again"
            }
```

## 6. Security & Performance

### 6.1 Input Validation and Sanitization

**Comprehensive Input Security:**

```python
class ChatInputValidator:
    """Validates and sanitizes all chat inputs for security."""

    def __init__(self):
        self.sql_injection_patterns = [
            r"(?i)(union|select|insert|update|delete|drop|create|alter)",
            r"(?i)(script|javascript|vbscript|onload|onerror)",
            r"['\";].*(-{2}|#|/\*)"
        ]

        self.max_message_length = 10000
        self.max_conversation_depth = 100

    def validate_message(self, message: str, user_context: UserContext) -> ValidationResult:
        """Validate chat message for security and constraints."""

        errors = []
        warnings = []

        # Length validation
        if len(message) > self.max_message_length:
            errors.append(f"Message too long (max {self.max_message_length} characters)")

        if len(message.strip()) == 0:
            errors.append("Message cannot be empty")

        # SQL injection detection
        for pattern in self.sql_injection_patterns:
            if re.search(pattern, message):
                errors.append("Potentially malicious content detected")
                break

        # XSS prevention
        if self._contains_xss_patterns(message):
            errors.append("Cross-site scripting attempt detected")

        # Rate limiting check
        if not self._check_rate_limit(user_context.user_id):
            errors.append("Rate limit exceeded. Please wait before sending another message.")

        # Content policy check
        if self._violates_content_policy(message):
            warnings.append("Message may violate content policy")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_message=self._sanitize_message(message)
        )

    def _sanitize_message(self, message: str) -> str:
        """Sanitize message content while preserving intent."""

        # Remove potential XSS content
        message = re.sub(r'<[^>]+>', '', message)

        # Escape special characters
        message = html.escape(message)

        # Normalize whitespace
        message = re.sub(r'\s+', ' ', message).strip()

        return message

    def _contains_xss_patterns(self, message: str) -> bool:
        """Check for XSS patterns."""

        xss_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'vbscript:',
            r'on\w+\s*=',
            r'<iframe[^>]*>',
            r'<object[^>]*>',
            r'<embed[^>]*>'
        ]

        for pattern in xss_patterns:
            if re.search(pattern, message, re.IGNORECASE):
                return True

        return False

    def _check_rate_limit(self, user_id: str) -> bool:
        """Check if user is within rate limits."""

        # Implementation would use Redis or in-memory cache
        # to track user request rates
        return True  # Placeholder

    def _violates_content_policy(self, message: str) -> bool:
        """Check message against content policy."""

        # Implementation would use content moderation service
        # or predefined patterns for policy violations
        return False  # Placeholder
```

### 6.2 Rate Limiting and Abuse Prevention

**Multi-Layer Rate Limiting:**

```python
class ChatRateLimiter:
    """Multi-layer rate limiting for chat system."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

        # Rate limit configurations
        self.limits = {
            UserRole.GUEST: {
                "messages_per_minute": 5,
                "messages_per_hour": 30,
                "messages_per_day": 100,
                "concurrent_conversations": 1
            },
            UserRole.USER: {
                "messages_per_minute": 15,
                "messages_per_hour": 200,
                "messages_per_day": 1000,
                "concurrent_conversations": 3
            },
            UserRole.ADMIN: {
                "messages_per_minute": 100,
                "messages_per_hour": 2000,
                "messages_per_day": 10000,
                "concurrent_conversations": 10
            }
        }

    async def check_rate_limit(self,
                             user_id: str,
                             user_role: UserRole) -> RateLimitResult:
        """Check if user is within rate limits."""

        limits = self.limits[user_role]
        current_time = datetime.utcnow()

        # Check all time windows
        checks = [
            ("minute", 60, limits["messages_per_minute"]),
            ("hour", 3600, limits["messages_per_hour"]),
            ("day", 86400, limits["messages_per_day"])
        ]

        for window_name, window_seconds, max_requests in checks:
            key = f"rate_limit:{user_id}:{window_name}"

            # Use Redis sliding window counter
            count = await self._get_sliding_window_count(key, window_seconds)

            if count >= max_requests:
                return RateLimitResult(
                    allowed=False,
                    limit_type=window_name,
                    current_count=count,
                    max_allowed=max_requests,
                    reset_time=current_time + timedelta(seconds=window_seconds)
                )

        # Check concurrent conversations
        active_conversations = await self._get_active_conversation_count(user_id)
        if active_conversations >= limits["concurrent_conversations"]:
            return RateLimitResult(
                allowed=False,
                limit_type="concurrent_conversations",
                current_count=active_conversations,
                max_allowed=limits["concurrent_conversations"]
            )

        return RateLimitResult(allowed=True)

    async def record_request(self, user_id: str):
        """Record a request for rate limiting."""

        current_time = datetime.utcnow()
        timestamp = int(current_time.timestamp())

        # Record in all time windows
        for window_name, window_seconds, _ in [
            ("minute", 60, None),
            ("hour", 3600, None),
            ("day", 86400, None)
        ]:
            key = f"rate_limit:{user_id}:{window_name}"

            # Add current request to sliding window
            await self.redis.zadd(key, {timestamp: timestamp})

            # Remove old entries outside window
            cutoff = timestamp - window_seconds
            await self.redis.zremrangebyscore(key, 0, cutoff)

            # Set expiration
            await self.redis.expire(key, window_seconds)

    async def _get_sliding_window_count(self, key: str, window_seconds: int) -> int:
        """Get count of requests in sliding window."""

        current_time = int(datetime.utcnow().timestamp())
        cutoff = current_time - window_seconds

        return await self.redis.zcount(key, cutoff, current_time)

    async def _get_active_conversation_count(self, user_id: str) -> int:
        """Get count of active conversations for user."""

        # Count conversations with activity in last hour
        cutoff = datetime.utcnow() - timedelta(hours=1)

        count = await self.redis.get(f"active_conversations:{user_id}")
        return int(count) if count else 0
```

### 6.3 Response Caching Strategies

**Intelligent Multi-Level Caching:**

```python
class IntelligentCacheManager:
    """Advanced caching with invalidation and warming strategies."""

    def __init__(self,
                 redis_client: Redis,
                 memory_cache_size: int = 2000):
        self.redis = redis_client
        self.memory_cache = TTLCache(maxsize=memory_cache_size, ttl=300)
        self.cache_warming_queue = asyncio.Queue()
        self.invalidation_patterns = {}

    async def get_cached_response(self,
                                cache_key: str,
                                context: CacheContext) -> Optional[CachedResponse]:
        """Get cached response with context validation."""

        # Check memory cache first
        if cache_key in self.memory_cache:
            cached_response = self.memory_cache[cache_key]
            if self._is_cache_valid(cached_response, context):
                return cached_response

        # Check Redis cache
        cached_data = await self.redis.get(f"chat_response:{cache_key}")
        if cached_data:
            cached_response = CachedResponse.from_json(cached_data)

            if self._is_cache_valid(cached_response, context):
                # Populate memory cache
                self.memory_cache[cache_key] = cached_response
                return cached_response
            else:
                # Invalid cache entry, remove it
                await self.redis.delete(f"chat_response:{cache_key}")

        return None

    async def cache_response(self,
                           cache_key: str,
                           response: ChatResponse,
                           context: CacheContext):
        """Cache response with intelligent TTL."""

        # Determine TTL based on response characteristics
        ttl = self._calculate_ttl(response, context)

        cached_response = CachedResponse(
            response=response,
            cached_at=datetime.utcnow(),
            context_hash=context.get_hash(),
            ttl=ttl
        )

        # Store in memory cache
        self.memory_cache[cache_key] = cached_response

        # Store in Redis with longer TTL
        await self.redis.setex(
            f"chat_response:{cache_key}",
            ttl * 2,
            cached_response.to_json()
        )

        # Register invalidation patterns
        await self._register_invalidation_patterns(cache_key, response)

    def _calculate_ttl(self, response: ChatResponse, context: CacheContext) -> int:
        """Calculate TTL based on response characteristics."""

        base_ttl = 300  # 5 minutes

        # Reduce TTL for responses involving dynamic data
        if any(tool.tool_name in ["create_entity", "update_entity"]
               for tool in response.tool_results):
            return 60  # 1 minute for write operations

        # Increase TTL for static/reference data
        if all(tool.tool_name in ["search_entities", "find_similar_entities"]
               for tool in response.tool_results):
            return 1800  # 30 minutes for search results

        # Adjust based on user role
        if context.user_role == UserRole.GUEST:
            return base_ttl * 2  # Cache longer for guests

        return base_ttl

    async def invalidate_by_pattern(self, pattern: str):
        """Invalidate cache entries matching pattern."""

        # Invalidate memory cache
        keys_to_remove = [
            key for key in self.memory_cache.keys()
            if fnmatch.fnmatch(key, pattern)
        ]

        for key in keys_to_remove:
            del self.memory_cache[key]

        # Invalidate Redis cache
        redis_keys = await self.redis.keys(f"chat_response:*{pattern}*")
        if redis_keys:
            await self.redis.delete(*redis_keys)

    async def warm_cache(self, warming_requests: List[CacheWarmingRequest]):
        """Pre-warm cache with common queries."""

        for request in warming_requests:
            try:
                # Generate response for warming
                response = await self._generate_warming_response(request)

                # Cache the response
                await self.cache_response(
                    request.cache_key,
                    response,
                    request.context
                )

            except Exception as e:
                logger.warning(f"Cache warming failed for {request.cache_key}: {e}")

    async def _register_invalidation_patterns(self,
                                            cache_key: str,
                                            response: ChatResponse):
        """Register patterns for automatic cache invalidation."""

        # Extract entities mentioned in response
        entities = self._extract_entities_from_response(response)

        for entity in entities:
            pattern = f"*{entity.entity_type}*{entity.entity_id}*"

            if pattern not in self.invalidation_patterns:
                self.invalidation_patterns[pattern] = set()

            self.invalidation_patterns[pattern].add(cache_key)
```

### 6.4 Load Balancing for Multiple Models

**Smart Model Load Balancing:**

```python
class ModelLoadBalancer:
    """Intelligent load balancing across multiple LLM models."""

    def __init__(self, model_pool: Dict[str, List[ModelInstance]]):
        self.model_pool = model_pool
        self.model_metrics = ModelMetrics()
        self.circuit_breakers = {}
        self.load_balancing_strategy = "adaptive"

    async def select_model(self,
                         request: ModelRequest,
                         user_preferences: UserPreferences) -> ModelInstance:
        """Select optimal model instance based on current conditions."""

        # Get candidate models based on request characteristics
        candidate_models = self._get_candidate_models(request)

        # Filter out unhealthy models
        healthy_models = [
            model for model in candidate_models
            if self._is_model_healthy(model)
        ]

        if not healthy_models:
            raise NoHealthyModelsError("No healthy models available")

        # Select model based on strategy
        if self.load_balancing_strategy == "round_robin":
            return self._round_robin_selection(healthy_models)
        elif self.load_balancing_strategy == "least_connections":
            return self._least_connections_selection(healthy_models)
        elif self.load_balancing_strategy == "response_time":
            return self._fastest_response_selection(healthy_models)
        else:  # adaptive
            return await self._adaptive_selection(healthy_models, request)

    async def _adaptive_selection(self,
                                models: List[ModelInstance],
                                request: ModelRequest) -> ModelInstance:
        """Adaptive model selection based on multiple factors."""

        scores = {}

        for model in models:
            metrics = await self.model_metrics.get_recent_metrics(model.id)

            # Calculate composite score
            score = 0.0

            # Response time factor (lower is better)
            avg_response_time = metrics.average_response_time
            response_score = 1.0 / (1.0 + avg_response_time / 1000.0)  # Convert to seconds
            score += response_score * 0.4

            # Success rate factor
            success_rate = metrics.success_rate
            score += success_rate * 0.3

            # Current load factor (lower is better)
            current_load = metrics.current_connections / model.max_connections
            load_score = 1.0 - current_load
            score += load_score * 0.2

            # Model capability match
            capability_score = self._calculate_capability_match(model, request)
            score += capability_score * 0.1

            scores[model] = score

        # Select model with highest score
        best_model = max(scores.keys(), key=lambda m: scores[m])

        # Update connection count
        await self.model_metrics.increment_connections(best_model.id)

        return best_model

    def _is_model_healthy(self, model: ModelInstance) -> bool:
        """Check if model is healthy and available."""

        # Check circuit breaker
        if model.id in self.circuit_breakers:
            circuit_breaker = self.circuit_breakers[model.id]
            if circuit_breaker.is_open():
                return False

        # Check resource utilization
        if model.current_connections >= model.max_connections:
            return False

        # Check recent error rate
        recent_metrics = self.model_metrics.get_recent_metrics_sync(model.id)
        if recent_metrics.error_rate > 0.5:  # 50% error rate threshold
            return False

        return True

    async def handle_model_error(self,
                               model: ModelInstance,
                               error: ModelError):
        """Handle model errors and update circuit breakers."""

        # Record error in metrics
        await self.model_metrics.record_error(model.id, error)

        # Update circuit breaker
        if model.id not in self.circuit_breakers:
            self.circuit_breakers[model.id] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60
            )

        circuit_breaker = self.circuit_breakers[model.id]
        circuit_breaker.record_failure()

        # If circuit breaker opens, remove model from rotation temporarily
        if circuit_breaker.is_open():
            logger.warning(f"Circuit breaker opened for model {model.id}")

    async def handle_successful_response(self,
                                       model: ModelInstance,
                                       response_time: float):
        """Handle successful model response."""

        # Record success in metrics
        await self.model_metrics.record_success(model.id, response_time)

        # Update circuit breaker
        if model.id in self.circuit_breakers:
            self.circuit_breakers[model.id].record_success()

        # Decrement connection count
        await self.model_metrics.decrement_connections(model.id)
```

## 7. Implementation Priorities

### Phase 1: Core Infrastructure (Weeks 1-2)
1. **Foundation Setup**
   - Enhanced ChatInterface class with event system
   - ToolExecutor with parallel execution capabilities
   - Basic ModelManager with single model support
   - ConversationManager with SQLite persistence

2. **Authentication Integration**
   - ChatAuthManager using existing JWT system
   - Permission-based tool filtering
   - User context management

3. **Basic Caching**
   - Memory-based ResponseCache
   - Simple cache invalidation

### Phase 2: Advanced Features (Weeks 3-4)
1. **Multi-Model Support**
   - ModelManager with intelligent routing
   - Load balancing for model instances
   - Fallback model handling

2. **Enhanced Caching**
   - Redis-based distributed caching
   - Smart invalidation patterns
   - Cache warming strategies

3. **Offline Capabilities**
   - ChatOfflineManager for BlowingOff client
   - Local graph cache utilization
   - Offline message queuing

### Phase 3: User Interfaces (Weeks 5-6)
1. **Web Interface**
   - Streamlit-based chat application
   - Real-time updates via WebSocket
   - Rich tool result visualization

2. **Enhanced CLI**
   - Rich formatting for responses
   - Interactive conversation management
   - Progress indicators and status updates

3. **API Endpoints**
   - RESTful chat API
   - WebSocket support for real-time chat
   - Conversation management endpoints

### Phase 4: Performance & Security (Weeks 7-8)
1. **Security Hardening**
   - Input validation and sanitization
   - Advanced rate limiting
   - Abuse prevention mechanisms

2. **Performance Optimization**
   - Response caching strategies
   - Database query optimization
   - Async/await pattern refinement

3. **Monitoring & Analytics**
   - Performance metrics collection
   - Error tracking and alerting
   - Usage analytics dashboard

### Phase 5: Integration & Testing (Weeks 9-10)
1. **Deep Integration**
   - Real-time sync with graph database
   - Event-driven cache invalidation
   - Cross-component coordination

2. **Comprehensive Testing**
   - Unit tests for all components
   - Integration tests with existing system
   - Performance and load testing

3. **Documentation & Deployment**
   - API documentation
   - User guides and tutorials
   - Production deployment scripts

## Conclusion

This comprehensive chat integration plan provides a robust foundation for adding advanced conversational capabilities to The Goodies ecosystem. The design maintains compatibility with existing components while introducing powerful new features for natural language interaction with the smart home knowledge graph.

Key benefits of this architecture:
- **Seamless Integration**: Leverages existing authentication, database, and MCP tool infrastructure
- **High Performance**: Multi-level caching, parallel execution, and intelligent model routing
- **Scalability**: Event-driven architecture supports growth and feature expansion
- **Security**: Comprehensive input validation, rate limiting, and abuse prevention
- **User Experience**: Multiple interfaces (web, CLI, API) with rich formatting and real-time updates

The phased implementation approach ensures steady progress while maintaining system stability throughout the development process.