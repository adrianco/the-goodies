# The Goodies - Architecture Diagrams

## System Architecture Overview

```mermaid
graph TB
    subgraph "Client Layer"
        iOS[iOS App]
        macOS[macOS App]
        watchOS[watchOS App]
        CLI[WildThing CLI]
    end
    
    subgraph "WildThing Package"
        WT[WildThing Core]
        WTMCP[MCP Server]
        WTHK[HomeKit Bridge]
        WTSync[Inbetweenies Client]
        WTDB[(SQLite)]
    end
    
    subgraph "Network Layer"
        IB[Inbetweenies Protocol]
        REST[REST API]
        WS[WebSocket]
    end
    
    subgraph "FunkyGibbon Service"
        FG[FunkyGibbon Core]
        FGAPI[FastAPI]
        FGSync[Inbetweenies Server]
        FGMCP[MCP Wrapper]
        FGDB[(PostgreSQL)]
        FGCache[(Redis)]
    end
    
    subgraph "External Services"
        HK[HomeKit Cloud]
        GH[Google Home]
        AX[Alexa]
        IFTTT[IFTTT]
    end
    
    iOS --> WT
    macOS --> WT
    watchOS --> WT
    CLI --> WT
    
    WT --> WTMCP
    WT --> WTHK
    WT --> WTSync
    WT --> WTDB
    
    WTSync <--> IB
    IB <--> FGSync
    
    iOS --> REST
    macOS --> REST
    REST --> FGAPI
    
    iOS --> WS
    WS --> FGAPI
    
    FG --> FGAPI
    FG --> FGSync
    FG --> FGMCP
    FG --> FGDB
    FG --> FGCache
    
    FGAPI --> HK
    FGAPI --> GH
    FGAPI --> AX
    FGAPI --> IFTTT
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant User
    participant WildThing
    participant SQLite
    participant InbetweeniesClient
    participant Network
    participant InbetweeniesServer
    participant FunkyGibbon
    participant PostgreSQL
    
    User->>WildThing: Create/Update Entity
    WildThing->>SQLite: Store with Version
    WildThing->>SQLite: Track Change
    
    alt Sync Triggered
        WildThing->>InbetweeniesClient: Prepare Sync
        InbetweeniesClient->>SQLite: Get Changes Since Last Sync
        InbetweeniesClient->>InbetweeniesClient: Generate Vector Clock
        InbetweeniesClient->>Network: Send InbetweeniesRequest
        Network->>InbetweeniesServer: Forward Request
        
        InbetweeniesServer->>FunkyGibbon: Validate & Process
        FunkyGibbon->>PostgreSQL: Apply Changes
        FunkyGibbon->>PostgreSQL: Detect Conflicts
        FunkyGibbon->>PostgreSQL: Get Changes for Client
        FunkyGibbon->>InbetweeniesServer: Prepare Response
        
        InbetweeniesServer->>Network: Send InbetweeniesResponse
        Network->>InbetweeniesClient: Forward Response
        
        InbetweeniesClient->>InbetweeniesClient: Process Conflicts
        InbetweeniesClient->>SQLite: Apply Server Changes
        InbetweeniesClient->>WildThing: Notify Completion
    end
    
    WildThing->>User: Update UI
```

## Component Architecture

### WildThing Internal Architecture

```mermaid
graph TB
    subgraph "WildThing Swift Package"
        subgraph "Core Layer"
            Models[Data Models]
            Protocols[Protocols]
            Extensions[Extensions]
        end
        
        subgraph "Storage Layer"
            StorageProtocol[Storage Protocol]
            SQLiteImpl[SQLite Storage]
            MemoryImpl[Memory Storage]
            Migration[Migration Manager]
        end
        
        subgraph "Graph Layer"
            HomeGraph[Home Graph]
            Traversal[Graph Traversal]
            Search[Search Engine]
            Cache[Graph Cache]
        end
        
        subgraph "MCP Layer"
            MCPServer[MCP Server]
            QueryTools[Query Tools]
            MgmtTools[Management Tools]
            ContentTools[Content Tools]
        end
        
        subgraph "Sync Layer"
            SyncClient[Inbetweenies Client]
            ConflictResolver[Conflict Resolver]
            VectorClock[Vector Clock]
            ChangeTracker[Change Tracker]
        end
        
        subgraph "Platform Layer"
            iOSBridge[iOS Extensions]
            macOSBridge[macOS Extensions]
            HomeKitBridge[HomeKit Bridge]
        end
    end
    
    Models --> StorageProtocol
    StorageProtocol --> SQLiteImpl
    StorageProtocol --> MemoryImpl
    
    SQLiteImpl --> HomeGraph
    HomeGraph --> Search
    HomeGraph --> Traversal
    HomeGraph --> Cache
    
    HomeGraph --> MCPServer
    MCPServer --> QueryTools
    MCPServer --> MgmtTools
    MCPServer --> ContentTools
    
    SQLiteImpl --> SyncClient
    SyncClient --> ConflictResolver
    SyncClient --> VectorClock
    SyncClient --> ChangeTracker
    
    HomeKitBridge --> Models
    iOSBridge --> MCPServer
    macOSBridge --> MCPServer
```

### FunkyGibbon Internal Architecture

```mermaid
graph TB
    subgraph "FunkyGibbon Python Service"
        subgraph "Core Layer"
            PydanticModels[Pydantic Models]
            Validators[Validators]
            Exceptions[Exceptions]
        end
        
        subgraph "Storage Layer"
            StorageBase[Storage Interface]
            PostgreSQL[PostgreSQL Storage]
            RedisCache[Redis Cache]
            Migrations[Alembic Migrations]
        end
        
        subgraph "Sync Layer"
            SyncServer[Inbetweenies Server]
            VectorClockMgr[Vector Clock Manager]
            ConflictDetector[Conflict Detector]
            ChangeLog[Change Logger]
        end
        
        subgraph "API Layer"
            FastAPIApp[FastAPI Application]
            Middleware[Middleware Stack]
            Routes[API Routes]
            WebSocketMgr[WebSocket Manager]
        end
        
        subgraph "Analytics Layer"
            Aggregator[Data Aggregator]
            Reports[Report Generator]
            MLInsights[ML Insights]
        end
        
        subgraph "Integration Layer"
            HomeKitInt[HomeKit Integration]
            GoogleInt[Google Home]
            AlexaInt[Alexa]
            IFTTTInt[IFTTT]
        end
    end
    
    PydanticModels --> StorageBase
    StorageBase --> PostgreSQL
    PostgreSQL --> RedisCache
    
    PostgreSQL --> SyncServer
    SyncServer --> VectorClockMgr
    SyncServer --> ConflictDetector
    SyncServer --> ChangeLog
    
    FastAPIApp --> Middleware
    Middleware --> Routes
    Routes --> SyncServer
    Routes --> PostgreSQL
    
    WebSocketMgr --> FastAPIApp
    
    PostgreSQL --> Aggregator
    Aggregator --> Reports
    Aggregator --> MLInsights
    
    FastAPIApp --> HomeKitInt
    FastAPIApp --> GoogleInt
    FastAPIApp --> AlexaInt
    FastAPIApp --> IFTTTInt
```

## Inbetweenies Protocol Flow

```mermaid
stateDiagram-v2
    [*] --> Idle
    
    Idle --> CollectingChanges: Sync Triggered
    CollectingChanges --> PreparingRequest: Changes Collected
    PreparingRequest --> SendingRequest: Request Ready
    SendingRequest --> WaitingResponse: Request Sent
    
    WaitingResponse --> ProcessingResponse: Response Received
    WaitingResponse --> RetryingRequest: Timeout/Error
    
    ProcessingResponse --> CheckingConflicts: Changes Extracted
    CheckingConflicts --> ResolvingConflicts: Conflicts Found
    CheckingConflicts --> ApplyingChanges: No Conflicts
    
    ResolvingConflicts --> ApplyingChanges: Conflicts Resolved
    ResolvingConflicts --> ManualResolution: Auto-Resolution Failed
    
    ApplyingChanges --> UpdatingVectorClock: Changes Applied
    UpdatingVectorClock --> SyncComplete: Clock Updated
    
    ManualResolution --> SyncComplete: User Resolved
    RetryingRequest --> SendingRequest: Retry Attempt
    RetryingRequest --> SyncFailed: Max Retries
    
    SyncComplete --> Idle: Success
    SyncFailed --> Idle: Failed
```

## Security Architecture

```mermaid
graph TB
    subgraph "Client Security"
        ClientAuth[Device Certificate]
        ClientJWT[JWT Token]
        ClientTLS[TLS 1.3]
        ClientEnc[Local Encryption]
    end
    
    subgraph "Transport Security"
        HTTPS[HTTPS/TLS]
        WSS[WSS Protocol]
        CertPin[Certificate Pinning]
    end
    
    subgraph "Server Security"
        ServerAuth[Authentication]
        ServerAuthz[Authorization]
        RateLimit[Rate Limiting]
        WAF[Web Application Firewall]
    end
    
    subgraph "Data Security"
        AtRest[Encryption at Rest]
        InTransit[Encryption in Transit]
        KeyMgmt[Key Management]
        Audit[Audit Logging]
    end
    
    ClientAuth --> ClientJWT
    ClientJWT --> ClientTLS
    ClientTLS --> HTTPS
    
    HTTPS --> ServerAuth
    WSS --> ServerAuth
    
    ServerAuth --> ServerAuthz
    ServerAuthz --> RateLimit
    RateLimit --> WAF
    
    WAF --> AtRest
    WAF --> InTransit
    
    AtRest --> KeyMgmt
    InTransit --> KeyMgmt
    KeyMgmt --> Audit
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Client Deployment"
        AppStore[App Store]
        TestFlight[TestFlight]
        SPM[Swift Package Manager]
    end
    
    subgraph "Load Balancer"
        LB[NGINX/ALB]
    end
    
    subgraph "Application Tier"
        FG1[FunkyGibbon Instance 1]
        FG2[FunkyGibbon Instance 2]
        FG3[FunkyGibbon Instance 3]
    end
    
    subgraph "Data Tier"
        PGMaster[(PostgreSQL Master)]
        PGReplica1[(PostgreSQL Replica 1)]
        PGReplica2[(PostgreSQL Replica 2)]
        RedisCluster[(Redis Cluster)]
    end
    
    subgraph "Monitoring"
        Prometheus[Prometheus]
        Grafana[Grafana]
        ELK[ELK Stack]
    end
    
    AppStore --> SPM
    TestFlight --> SPM
    
    SPM --> LB
    LB --> FG1
    LB --> FG2
    LB --> FG3
    
    FG1 --> PGMaster
    FG2 --> PGMaster
    FG3 --> PGMaster
    
    FG1 --> RedisCluster
    FG2 --> RedisCluster
    FG3 --> RedisCluster
    
    PGMaster --> PGReplica1
    PGMaster --> PGReplica2
    
    FG1 --> Prometheus
    FG2 --> Prometheus
    FG3 --> Prometheus
    
    Prometheus --> Grafana
    FG1 --> ELK
    FG2 --> ELK
    FG3 --> ELK
```

## Storage Schema Relationships

```mermaid
erDiagram
    ENTITIES ||--o{ ENTITY_VERSIONS : has
    ENTITIES ||--o{ RELATIONSHIPS : from
    ENTITIES ||--o{ RELATIONSHIPS : to
    ENTITIES ||--o{ BINARY_CONTENT : contains
    ENTITIES ||--o{ ENTITY_CHANGES : tracks
    
    ENTITIES {
        uuid id PK
        string current_version
        string entity_type
        string user_id
        timestamp created_at
        timestamp deleted_at
    }
    
    ENTITY_VERSIONS {
        uuid entity_id FK
        string version PK
        json parent_versions
        json content
        string source_type
        timestamp created_at
        timestamp last_modified
    }
    
    RELATIONSHIPS {
        uuid id PK
        uuid from_entity_id FK
        uuid to_entity_id FK
        string relationship_type
        json properties
        string user_id
        timestamp created_at
        timestamp deleted_at
    }
    
    BINARY_CONTENT {
        uuid id PK
        uuid entity_id FK
        string entity_version FK
        string content_type
        string file_name
        blob data
        string checksum
        timestamp created_at
    }
    
    ENTITY_CHANGES {
        bigint id PK
        string change_type
        uuid entity_id
        string entity_version
        json content
        string device_id
        string user_id
        timestamp timestamp
    }
    
    VECTOR_CLOCKS {
        string user_id PK
        string device_id PK
        string clock_value
        timestamp updated_at
    }
    
    SYNC_CONFLICTS {
        uuid id PK
        uuid entity_id
        string local_version
        string remote_version
        string conflict_type
        json conflict_data
        string resolution_status
        timestamp created_at
    }
```

## Performance Architecture

```mermaid
graph LR
    subgraph "Caching Layers"
        L1[L1: In-Memory Cache]
        L2[L2: Redis Cache]
        L3[L3: CDN Cache]
    end
    
    subgraph "Query Optimization"
        QP[Query Planner]
        IDX[Index Strategy]
        MAT[Materialized Views]
    end
    
    subgraph "Async Processing"
        TQ[Task Queue]
        WK[Workers]
        BG[Background Jobs]
    end
    
    Request --> L3
    L3 --> L2
    L2 --> L1
    L1 --> QP
    
    QP --> IDX
    IDX --> MAT
    
    Request --> TQ
    TQ --> WK
    WK --> BG
```

## Real-time Updates Architecture

```mermaid
sequenceDiagram
    participant Client
    participant WebSocket
    participant WSManager
    participant EventBus
    participant Storage
    participant OtherClients
    
    Client->>WebSocket: Connect
    WebSocket->>WSManager: Register Connection
    WSManager->>Client: Connection Confirmed
    
    Client->>WSManager: Subscribe to Entity
    WSManager->>WSManager: Update Subscriptions
    
    Storage->>EventBus: Entity Changed Event
    EventBus->>WSManager: Notify Change
    WSManager->>WSManager: Find Subscribers
    WSManager->>Client: Send Update
    WSManager->>OtherClients: Send Update
    
    Client->>WSManager: Unsubscribe
    WSManager->>WSManager: Remove Subscription
    
    Client->>WebSocket: Disconnect
    WebSocket->>WSManager: Cleanup Connection
```

## Error Handling Flow

```mermaid
graph TB
    Operation[Operation] --> Try{Try Block}
    Try --> Success[Success]
    Try --> Error[Error Thrown]
    
    Error --> ErrorType{Error Type?}
    
    ErrorType --> Validation[Validation Error]
    ErrorType --> NotFound[Not Found]
    ErrorType --> Conflict[Conflict]
    ErrorType --> Network[Network Error]
    ErrorType --> Internal[Internal Error]
    
    Validation --> Return400[Return 400]
    NotFound --> Return404[Return 404]
    Conflict --> Return409[Return 409]
    Network --> Retry{Retry?}
    Internal --> Return500[Return 500]
    
    Retry --> Yes[Exponential Backoff]
    Retry --> No[Return Error]
    
    Yes --> Operation
    
    Return400 --> Log[Log Error]
    Return404 --> Log
    Return409 --> Log
    Return500 --> Log
    No --> Log
    
    Log --> Metrics[Update Metrics]
    Metrics --> Response[Error Response]
```

## Migration Architecture

```mermaid
graph TB
    subgraph "Version Detection"
        Current[Current Version]
        Target[Target Version]
        Diff[Version Diff]
    end
    
    subgraph "Migration Planning"
        Plan[Migration Plan]
        Backup[Backup Strategy]
        Rollback[Rollback Plan]
    end
    
    subgraph "Migration Execution"
        Schema[Schema Migration]
        Data[Data Migration]
        Index[Index Rebuild]
    end
    
    subgraph "Validation"
        Test[Test Migration]
        Verify[Verify Data]
        Monitor[Monitor Performance]
    end
    
    Current --> Diff
    Target --> Diff
    Diff --> Plan
    
    Plan --> Backup
    Backup --> Rollback
    
    Plan --> Schema
    Schema --> Data
    Data --> Index
    
    Index --> Test
    Test --> Verify
    Verify --> Monitor
```

## Monitoring Dashboard Layout

```mermaid
graph TB
    subgraph "System Health"
        CPU[CPU Usage]
        Memory[Memory Usage]
        Disk[Disk I/O]
        Network[Network I/O]
    end
    
    subgraph "Application Metrics"
        RPS[Requests/Second]
        Latency[Response Latency]
        Errors[Error Rate]
        ActiveUsers[Active Users]
    end
    
    subgraph "Sync Metrics"
        SyncRate[Sync Success Rate]
        Conflicts[Conflict Rate]
        SyncTime[Avg Sync Time]
        QueueSize[Sync Queue Size]
    end
    
    subgraph "Business Metrics"
        Entities[Total Entities]
        DailyActive[Daily Active Devices]
        Storage[Storage Usage]
        Features[Feature Usage]
    end
```

## Conclusion

These architectural diagrams provide a comprehensive view of The Goodies system architecture, showing:

1. **System Overview**: How components interact at a high level
2. **Data Flow**: The lifecycle of data through the system
3. **Component Details**: Internal architecture of major components
4. **Protocol Flow**: State machine for the Inbetweenies protocol
5. **Security Layers**: Defense in depth approach
6. **Deployment Strategy**: Production deployment architecture
7. **Database Schema**: Entity relationships
8. **Performance Optimization**: Caching and optimization strategies
9. **Real-time Updates**: WebSocket communication flow
10. **Error Handling**: Comprehensive error management
11. **Migration Process**: Safe upgrade procedures
12. **Monitoring Layout**: Key metrics to track

Each diagram focuses on a specific aspect while maintaining consistency with the overall architecture.