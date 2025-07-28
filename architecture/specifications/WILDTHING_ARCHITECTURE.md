# WildThing Swift Package - Detailed Architecture Specification

## Overview

WildThing is a Swift Package that provides a local-first MCP server for smart home knowledge graph operations. It's designed to run on iOS, macOS, watchOS, and tvOS devices, offering offline-capable home automation data management with optional cloud synchronization.

## Package Structure

```
WildThing/
├── Package.swift                      # Swift Package Manager manifest
├── Sources/
│   ├── WildThing/                    # Main library target
│   │   ├── Core/
│   │   │   ├── Models/
│   │   │   │   ├── HomeEntity.swift
│   │   │   │   ├── EntityRelationship.swift
│   │   │   │   ├── EntityTypes.swift
│   │   │   │   └── AnyCodable.swift
│   │   │   ├── Protocols/
│   │   │   │   ├── WildThingEntity.swift
│   │   │   │   ├── StorageProtocol.swift
│   │   │   │   └── NetworkService.swift
│   │   │   └── Extensions/
│   │   │       ├── Date+Extensions.swift
│   │   │       ├── Data+Extensions.swift
│   │   │       └── String+Extensions.swift
│   │   ├── Storage/
│   │   │   ├── SQLiteStorage.swift
│   │   │   ├── MemoryStorage.swift
│   │   │   ├── Migration/
│   │   │   │   ├── MigrationManager.swift
│   │   │   │   └── Migrations/
│   │   │   └── Indexing/
│   │   │       ├── SearchIndex.swift
│   │   │       └── GraphIndex.swift
│   │   ├── Graph/
│   │   │   ├── HomeGraph.swift
│   │   │   ├── GraphTraversal.swift
│   │   │   ├── PathFinding.swift
│   │   │   └── GraphCache.swift
│   │   ├── MCP/
│   │   │   ├── WildThingMCPServer.swift
│   │   │   ├── Tools/
│   │   │   │   ├── QueryTools.swift
│   │   │   │   ├── EntityTools.swift
│   │   │   │   ├── RelationshipTools.swift
│   │   │   │   └── ContentTools.swift
│   │   │   └── Handlers/
│   │   │       ├── RequestHandler.swift
│   │   │       └── ResponseBuilder.swift
│   │   ├── Inbetweenies/
│   │   │   ├── InbetweeniesClient.swift
│   │   │   ├── SyncManager.swift
│   │   │   ├── ConflictResolver.swift
│   │   │   ├── VectorClock.swift
│   │   │   └── ChangeTracking.swift
│   │   └── Utilities/
│   │       ├── Logger.swift
│   │       ├── Metrics.swift
│   │       └── ErrorHandling.swift
│   ├── WildThingHomeKit/            # HomeKit integration (iOS/macOS only)
│   │   ├── HomeKitBridge.swift
│   │   ├── DeviceImporter.swift
│   │   ├── ServiceMapper.swift
│   │   └── CharacteristicConverter.swift
│   └── WildThingCLI/                # Command-line tool
│       ├── main.swift
│       ├── Commands/
│       └── Utilities/
└── Tests/
    ├── WildThingTests/
    ├── IntegrationTests/
    └── PerformanceTests/
```

## Core Components

### 1. Data Models

#### HomeEntity Model
```swift
public struct HomeEntity: WildThingEntity, Codable {
    public let id: String
    public let version: String
    public let entityType: EntityType
    public let parentVersions: [String]
    public var content: [String: AnyCodable]
    public let userId: String
    public let sourceType: SourceType
    public let createdAt: Date
    public var lastModified: Date
    
    // Computed properties
    public var displayName: String? {
        content["name"]?.value as? String
    }
    
    public var isActive: Bool {
        content["active"]?.value as? Bool ?? true
    }
    
    // Version generation
    public static func generateVersion(userId: String) -> String {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let random = UUID().uuidString.prefix(8)
        return "\(timestamp)-\(userId)-\(random)"
    }
    
    // Content helpers
    public mutating func updateContent(_ key: String, value: Any) {
        content[key] = AnyCodable(value)
        lastModified = Date()
    }
}
```

#### Entity Types Hierarchy
```swift
public enum EntityType: String, CaseIterable, Codable {
    // Physical spaces
    case home = "home"
    case room = "room"
    case zone = "zone"
    
    // Devices and accessories
    case device = "device"
    case accessory = "accessory"
    case service = "service"
    
    // Connectors
    case door = "door"
    case window = "window"
    case passage = "passage"
    
    // Documentation
    case manual = "manual"
    case procedure = "procedure"
    case note = "note"
    
    // Automation
    case schedule = "schedule"
    case automation = "automation"
    case scene = "scene"
    
    // Categories for UI organization
    public var category: EntityCategory {
        switch self {
        case .home, .room, .zone:
            return .spaces
        case .device, .accessory, .service:
            return .devices
        case .door, .window, .passage:
            return .connectors
        case .manual, .procedure, .note:
            return .documentation
        case .schedule, .automation, .scene:
            return .automation
        }
    }
}

public enum EntityCategory: String, CaseIterable {
    case spaces, devices, connectors, documentation, automation
}
```

### 2. Storage Layer

#### Storage Protocol
```swift
public protocol WildThingStorage: AnyObject {
    // MARK: - Entity Operations
    func store(entity: HomeEntity) async throws
    func getEntity(id: String) async throws -> HomeEntity?
    func getLatestVersion(for entityId: String) async throws -> HomeEntity?
    func getAllVersions(for entityId: String) async throws -> [HomeEntity]
    func getEntities(ofType type: EntityType) async throws -> [HomeEntity]
    func deleteEntity(id: String, version: String?) async throws
    
    // MARK: - Relationship Operations
    func store(relationship: EntityRelationship) async throws
    func getRelationships(from entityId: String) async throws -> [EntityRelationship]
    func getRelationships(to entityId: String) async throws -> [EntityRelationship]
    func getRelationships(ofType type: RelationshipType) async throws -> [EntityRelationship]
    func deleteRelationship(id: String) async throws
    
    // MARK: - Query Operations
    func searchEntities(query: String, types: [EntityType]?) async throws -> [HomeEntity]
    func getEntitiesInRoom(_ roomId: String) async throws -> [HomeEntity]
    func findPath(from: String, to: String) async throws -> [String]
    func getRelatedEntities(to entityId: String, depth: Int) async throws -> [HomeEntity]
    
    // MARK: - Sync Operations
    func getChangedEntities(since: Date, userId: String?) async throws -> [HomeEntity]
    func getVectorClock() async throws -> [String: String]
    func updateVectorClock(_ clock: [String: String]) async throws
    func markSynced(entityId: String, version: String) async throws
    
    // MARK: - Binary Content
    func storeBinaryContent(_ content: BinaryContent) async throws
    func getBinaryContent(id: String) async throws -> BinaryContent?
    func deleteBinaryContent(id: String) async throws
    
    // MARK: - Maintenance
    func vacuum() async throws
    func exportDatabase() async throws -> Data
    func importDatabase(_ data: Data) async throws
}
```

#### SQLite Implementation Details
```swift
public actor SQLiteWildThingStorage: WildThingStorage {
    private let db: Connection
    private let queue: DispatchQueue
    
    // Table definitions with proper indices
    private func setupSchema() throws {
        // Entities table with composite primary key
        try db.run(entities.create(ifNotExists: true) { t in
            t.column(entityId)
            t.column(entityVersion)
            t.column(entityType)
            t.column(parentVersions)
            t.column(content)
            t.column(userId)
            t.column(sourceType)
            t.column(createdAt)
            t.column(lastModified)
            t.primaryKey(entityId, entityVersion)
        })
        
        // Performance indices
        try db.run(entities.createIndex(
            [entityType, lastModified.desc], 
            ifNotExists: true
        ))
        
        try db.run(entities.createIndex(
            [entityId, createdAt.desc], 
            unique: true, 
            ifNotExists: true
        ))
        
        // Full-text search
        try db.run("""
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts 
            USING fts5(entity_id, content, content_type)
        """)
    }
    
    // Optimized queries
    public func getEntitiesInRoom(_ roomId: String) async throws -> [HomeEntity] {
        // Use indexed relationship lookup
        let query = """
            SELECT e.* FROM entities e
            JOIN relationships r ON e.id = r.from_entity_id
            WHERE r.to_entity_id = ? 
            AND r.relationship_type = ?
            AND e.version IN (
                SELECT MAX(version) FROM entities 
                GROUP BY id
            )
        """
        
        return try db.prepare(query, roomId, RelationshipType.locatedIn.rawValue)
            .compactMap(homeEntityFromRow)
    }
}
```

### 3. Graph Operations

#### HomeGraph Architecture
```swift
public class HomeGraph {
    private var nodes: [String: GraphNode] = [:]
    private var edges: [String: Set<GraphEdge>] = [:]
    private let storage: WildThingStorage
    private let cache: GraphCache
    
    // Graph node representation
    private struct GraphNode {
        let entity: HomeEntity
        var incomingEdges: Set<String> = []
        var outgoingEdges: Set<String> = []
        
        var degree: Int { incomingEdges.count + outgoingEdges.count }
    }
    
    // Graph edge representation
    private struct GraphEdge: Hashable {
        let relationship: EntityRelationship
        let weight: Double
        
        static func == (lhs: GraphEdge, rhs: GraphEdge) -> Bool {
            lhs.relationship.id == rhs.relationship.id
        }
        
        func hash(into hasher: inout Hasher) {
            hasher.combine(relationship.id)
        }
    }
    
    // Advanced graph operations
    public func findShortestPath(from: String, to: String) async throws -> Path? {
        // Dijkstra's algorithm with A* heuristic
        var distances: [String: Double] = [from: 0]
        var previous: [String: String] = [:]
        var unvisited = Set(nodes.keys)
        
        while !unvisited.isEmpty {
            guard let current = unvisited.min(by: { 
                (distances[$0] ?? .infinity) < (distances[$1] ?? .infinity) 
            }) else { break }
            
            if current == to {
                return reconstructPath(from: from, to: to, previous: previous)
            }
            
            unvisited.remove(current)
            
            for edge in edges[current] ?? [] {
                let alt = (distances[current] ?? .infinity) + edge.weight
                let neighbor = edge.relationship.toEntityId
                
                if alt < (distances[neighbor] ?? .infinity) {
                    distances[neighbor] = alt
                    previous[neighbor] = current
                }
            }
        }
        
        return nil
    }
    
    // Semantic search with ranking
    public func semanticSearch(
        query: String,
        types: [EntityType]? = nil,
        limit: Int = 20
    ) async throws -> [SearchResult] {
        // Multi-factor scoring
        let searchTerms = query.lowercased().split(separator: " ")
        var results: [SearchResult] = []
        
        for node in nodes.values {
            guard types?.contains(node.entity.entityType) ?? true else { continue }
            
            var score = 0.0
            
            // Name matching (highest weight)
            if let name = node.entity.displayName?.lowercased() {
                for term in searchTerms {
                    if name.contains(term) {
                        score += term.count > 3 ? 10.0 : 5.0
                    }
                }
            }
            
            // Content matching
            for (key, value) in node.entity.content {
                if let stringValue = value.value as? String {
                    let lowercased = stringValue.lowercased()
                    for term in searchTerms {
                        if lowercased.contains(term) {
                            score += key == "description" ? 3.0 : 1.0
                        }
                    }
                }
            }
            
            // Graph importance (PageRank-style)
            score += Double(node.degree) * 0.1
            
            if score > 0 {
                results.append(SearchResult(
                    entity: node.entity,
                    score: score,
                    highlights: extractHighlights(node.entity, terms: searchTerms)
                ))
            }
        }
        
        return results
            .sorted { $0.score > $1.score }
            .prefix(limit)
            .map { $0 }
    }
}
```

### 4. MCP Server Implementation

#### MCP Server Architecture
```swift
public class WildThingMCPServer: MCPServer {
    private let graph: HomeGraph
    private let storage: WildThingStorage
    private let tools: [String: MCPTool]
    private let metrics: MetricsCollector
    
    public override init(storage: WildThingStorage) {
        self.storage = storage
        self.graph = HomeGraph(storage: storage)
        self.metrics = MetricsCollector()
        self.tools = [:]
        
        super.init()
        registerAllTools()
    }
    
    private func registerAllTools() {
        // Query tools
        registerTool(GetDevicesInRoomTool(graph: graph))
        registerTool(FindDeviceControlsTool(graph: graph))
        registerTool(GetRoomConnectionsTool(graph: graph))
        registerTool(SearchEntitiesTool(graph: graph))
        
        // Entity management tools
        registerTool(CreateEntityTool(storage: storage))
        registerTool(UpdateEntityTool(storage: storage))
        registerTool(DeleteEntityTool(storage: storage))
        
        // Relationship tools
        registerTool(CreateRelationshipTool(storage: storage))
        registerTool(RemoveRelationshipTool(storage: storage))
        
        // Content tools
        registerTool(AddDeviceManualTool(storage: storage))
        registerTool(CreateProcedureTool(storage: storage))
        registerTool(AddDeviceImageTool(storage: storage))
        
        // Advanced tools
        registerTool(FindOptimalPathTool(graph: graph))
        registerTool(AnalyzeEnergyUsageTool(graph: graph))
        registerTool(SuggestAutomationsTool(graph: graph))
    }
    
    // Request handling with metrics
    public override func handleRequest(_ request: MCPRequest) async throws -> MCPResponse {
        let startTime = Date()
        
        do {
            let response = try await super.handleRequest(request)
            metrics.recordSuccess(tool: request.method, duration: Date().timeIntervalSince(startTime))
            return response
        } catch {
            metrics.recordError(tool: request.method, error: error)
            throw error
        }
    }
}

// Example MCP Tool Implementation
class GetDevicesInRoomTool: MCPTool {
    private let graph: HomeGraph
    
    init(graph: HomeGraph) {
        self.graph = graph
        super.init(
            name: "get_devices_in_room",
            description: "Get all devices located in a specific room",
            inputSchema: MCPToolInputSchema(
                type: .object,
                properties: [
                    "room_name": MCPToolProperty(
                        type: .string,
                        description: "Name of the room"
                    ),
                    "device_types": MCPToolProperty(
                        type: .array,
                        description: "Filter by device types (optional)",
                        items: MCPToolProperty(type: .string),
                        required: false
                    )
                ],
                required: ["room_name"]
            )
        )
    }
    
    override func execute(arguments: [String: Any]) async throws -> MCPToolResponse {
        guard let roomName = arguments["room_name"] as? String else {
            throw MCPError.invalidArguments("room_name is required")
        }
        
        let deviceTypes = arguments["device_types"] as? [String]
        let devices = try await graph.entitiesInRoom(roomName, types: deviceTypes)
        
        let deviceList = devices.map { device in
            DeviceInfo(
                id: device.id,
                name: device.displayName ?? "Unknown",
                type: device.content["device_type"]?.value as? String ?? "unknown",
                manufacturer: device.content["manufacturer"]?.value as? String,
                isOnline: device.content["online"]?.value as? Bool ?? false
            )
        }
        
        return MCPToolResponse(
            content: [
                .text("Found \(devices.count) devices in \(roomName)"),
                .resource(
                    uri: "wildthing://devices/\(roomName)",
                    mimeType: "application/json",
                    text: try JSONEncoder().encode(deviceList).string
                )
            ]
        )
    }
}
```

### 5. Inbetweenies Sync Client

#### Sync Architecture
```swift
public class InbetweeniesClient {
    private let storage: WildThingStorage
    private let networkService: NetworkService
    private let conflictResolver: ConflictResolver
    private let changeTracker: ChangeTracker
    
    // Sync state management
    private struct SyncState {
        var lastSyncTime: Date?
        var vectorClock: VectorClock
        var pendingChanges: Set<String>
        var syncInProgress: Bool = false
    }
    
    @Published private var syncState = SyncState(
        vectorClock: VectorClock(),
        pendingChanges: []
    )
    
    // Incremental sync with retry logic
    public func performSync() async throws -> SyncResult {
        // Prevent concurrent syncs
        guard !syncState.syncInProgress else {
            throw SyncError.syncInProgress
        }
        
        syncState.syncInProgress = true
        defer { syncState.syncInProgress = false }
        
        var result = SyncResult()
        
        // Phase 1: Prepare local changes
        let localChanges = try await prepareLocalChanges()
        
        // Phase 2: Send changes and receive updates
        let request = InbetweeniesRequest(
            protocolVersion: "inbetweenies-v1",
            deviceId: getDeviceId(),
            userId: getUserId(),
            vectorClock: syncState.vectorClock.toDict(),
            changes: localChanges
        )
        
        let response = try await withRetry(maxAttempts: 3) {
            try await networkService.sendInbetweeniesRequest(request)
        }
        
        // Phase 3: Process incoming changes
        for change in response.changes {
            do {
                try await processIncomingChange(change)
                result.downloaded += 1
            } catch ConflictError.versionConflict(let conflict) {
                try await conflictResolver.resolveConflict(conflict)
                result.conflicts += 1
            }
        }
        
        // Phase 4: Update sync state
        syncState.vectorClock.merge(response.vectorClock)
        syncState.lastSyncTime = Date()
        result.uploaded = localChanges.count
        
        return result
    }
    
    // Conflict resolution strategies
    private func processIncomingChange(_ change: EntityChange) async throws {
        guard let existingEntity = try await storage.getLatestVersion(for: change.entityId) else {
            // New entity, no conflict
            try await applyChange(change)
            return
        }
        
        // Check for conflicts
        if !change.parentVersions.contains(existingEntity.version) {
            // Versions have diverged
            let conflict = VersionConflict(
                entityId: change.entityId,
                localVersion: existingEntity.version,
                remoteVersion: change.entityVersion,
                localEntity: existingEntity,
                remoteChange: change
            )
            
            let resolution = try await conflictResolver.resolveConflict(conflict)
            try await applyResolution(resolution)
        } else {
            // No conflict, apply change
            try await applyChange(change)
        }
    }
}

// Vector Clock Implementation
public struct VectorClock {
    private var clocks: [String: Int] = [:]
    
    mutating func increment(_ nodeId: String) {
        clocks[nodeId] = (clocks[nodeId] ?? 0) + 1
    }
    
    func isGreaterThan(_ other: VectorClock) -> Bool {
        for (node, value) in clocks {
            if value > (other.clocks[node] ?? 0) {
                return true
            }
        }
        return false
    }
    
    func isConcurrent(with other: VectorClock) -> Bool {
        !isGreaterThan(other) && !other.isGreaterThan(self)
    }
    
    mutating func merge(_ other: [String: String]) {
        for (node, value) in other {
            if let intValue = Int(value) {
                clocks[node] = max(clocks[node] ?? 0, intValue)
            }
        }
    }
}
```

### 6. HomeKit Integration

#### HomeKit Bridge
```swift
#if canImport(HomeKit)
import HomeKit

public class HomeKitBridge: NSObject {
    private let storage: WildThingStorage
    private let homeManager: HMHomeManager
    private var homes: [HMHome] = []
    
    public override init(storage: WildThingStorage) {
        self.storage = storage
        self.homeManager = HMHomeManager()
        super.init()
        homeManager.delegate = self
    }
    
    public func importAllHomes() async throws {
        await withCheckedContinuation { continuation in
            if homeManager.homes.isEmpty {
                // Wait for homes to load
                homeManagerDidUpdateHomes = { [weak self] in
                    self?.importHomes()
                    continuation.resume()
                }
            } else {
                importHomes()
                continuation.resume()
            }
        }
    }
    
    private func importHome(_ home: HMHome) async throws {
        // Import home entity
        let homeEntity = HomeEntity(
            entityType: .home,
            content: [
                "name": AnyCodable(home.name),
                "isPrimary": AnyCodable(home.isPrimary),
                "uniqueIdentifier": AnyCodable(home.uniqueIdentifier.uuidString)
            ],
            userId: getUserId(),
            sourceType: .homekit
        )
        
        try await storage.store(entity: homeEntity)
        
        // Import rooms
        for room in home.rooms {
            let roomEntity = try await importRoom(room, in: homeEntity.id)
            
            // Import accessories in room
            for accessory in room.accessories {
                try await importAccessory(accessory, in: roomEntity.id)
            }
        }
        
        // Import zones
        for zone in home.zones {
            try await importZone(zone, in: homeEntity.id)
        }
    }
    
    private func importAccessory(_ accessory: HMAccessory, in roomId: String) async throws -> HomeEntity {
        let deviceEntity = HomeEntity(
            entityType: .device,
            content: [
                "name": AnyCodable(accessory.name),
                "manufacturer": AnyCodable(accessory.manufacturer),
                "model": AnyCodable(accessory.model),
                "firmwareVersion": AnyCodable(accessory.firmwareVersion),
                "isReachable": AnyCodable(accessory.isReachable),
                "uniqueIdentifier": AnyCodable(accessory.uniqueIdentifier.uuidString),
                "category": AnyCodable(accessory.category.categoryType)
            ],
            userId: getUserId(),
            sourceType: .homekit
        )
        
        try await storage.store(entity: deviceEntity)
        
        // Create location relationship
        let relationship = EntityRelationship(
            fromEntityId: deviceEntity.id,
            toEntityId: roomId,
            relationshipType: .locatedIn,
            userId: getUserId()
        )
        
        try await storage.store(relationship: relationship)
        
        // Import services
        for service in accessory.services {
            try await importService(service, for: deviceEntity.id)
        }
        
        return deviceEntity
    }
}

extension HomeKitBridge: HMHomeManagerDelegate {
    public func homeManagerDidUpdateHomes(_ manager: HMHomeManager) {
        homes = manager.homes
        homeManagerDidUpdateHomes?()
    }
}
#endif
```

## Performance Optimizations

### 1. Caching Strategy

```swift
// Multi-level caching
class GraphCache {
    private let memoryCache: NSCache<NSString, CacheEntry>
    private let diskCache: DiskCache
    
    // L1: In-memory cache with TTL
    private class CacheEntry {
        let value: Any
        let expiration: Date
        
        var isExpired: Bool {
            Date() > expiration
        }
    }
    
    // L2: Disk cache for larger datasets
    private class DiskCache {
        private let cacheURL: URL
        private let maxSize: Int64 = 100_000_000 // 100MB
        
        func store(_ key: String, data: Data) throws {
            let fileURL = cacheURL.appendingPathComponent(key.sha256)
            try data.write(to: fileURL)
            cleanupIfNeeded()
        }
    }
}
```

### 2. Batch Operations

```swift
extension SQLiteWildThingStorage {
    // Batch insert with transaction
    public func storeEntities(_ entities: [HomeEntity]) async throws {
        try await db.transaction { connection in
            let statement = try connection.prepare("""
                INSERT OR REPLACE INTO entities 
                (id, version, entity_type, content, user_id, created_at, last_modified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """)
            
            for entity in entities {
                try statement.run(
                    entity.id,
                    entity.version,
                    entity.entityType.rawValue,
                    entity.content.jsonString,
                    entity.userId,
                    entity.createdAt.timeIntervalSince1970,
                    entity.lastModified.timeIntervalSince1970
                )
            }
        }
    }
}
```

### 3. Lazy Loading

```swift
// Lazy property loading for large content
extension HomeEntity {
    private struct LazyContent {
        private let loader: () async throws -> [String: AnyCodable]
        private var cached: [String: AnyCodable]?
        
        mutating func value() async throws -> [String: AnyCodable] {
            if let cached = cached {
                return cached
            }
            let loaded = try await loader()
            cached = loaded
            return loaded
        }
    }
}
```

## Testing Strategy

### 1. Unit Tests

```swift
class HomeEntityTests: XCTestCase {
    func testVersionGeneration() {
        let version1 = HomeEntity.generateVersion(userId: "test")
        let version2 = HomeEntity.generateVersion(userId: "test")
        
        XCTAssertNotEqual(version1, version2)
        XCTAssertTrue(version1.contains("test"))
        XCTAssertTrue(version1.contains("T")) // ISO8601 timestamp
    }
    
    func testEntitySerialization() throws {
        let entity = HomeEntity(
            entityType: .device,
            content: ["name": AnyCodable("Test Device")],
            userId: "test"
        )
        
        let encoded = try JSONEncoder().encode(entity)
        let decoded = try JSONDecoder().decode(HomeEntity.self, from: encoded)
        
        XCTAssertEqual(entity.id, decoded.id)
        XCTAssertEqual(entity.entityType, decoded.entityType)
    }
}
```

### 2. Integration Tests

```swift
class StorageIntegrationTests: XCTestCase {
    var storage: WildThingStorage!
    
    override func setUp() async throws {
        storage = try SQLiteWildThingStorage(databasePath: ":memory:")
    }
    
    func testEntityLifecycle() async throws {
        // Create
        let entity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Living Room")],
            userId: "test"
        )
        
        try await storage.store(entity: entity)
        
        // Read
        let retrieved = try await storage.getEntity(id: entity.id)
        XCTAssertEqual(retrieved?.id, entity.id)
        
        // Update
        var updated = retrieved!
        updated.updateContent("color", value: "blue")
        try await storage.store(entity: updated)
        
        // Verify version history
        let versions = try await storage.getAllVersions(for: entity.id)
        XCTAssertEqual(versions.count, 2)
        
        // Delete
        try await storage.deleteEntity(id: entity.id, version: nil)
        let deleted = try await storage.getEntity(id: entity.id)
        XCTAssertNil(deleted)
    }
}
```

### 3. Performance Tests

```swift
class PerformanceTests: XCTestCase {
    func testBulkImportPerformance() throws {
        let storage = try SQLiteWildThingStorage(databasePath: ":memory:")
        
        measure {
            let entities = (0..<1000).map { i in
                HomeEntity(
                    entityType: .device,
                    content: ["name": AnyCodable("Device \(i)")],
                    userId: "test"
                )
            }
            
            let expectation = expectation(description: "Bulk import")
            
            Task {
                try await storage.storeEntities(entities)
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 10.0)
        }
    }
}
```

## Error Handling

### Error Types

```swift
public enum WildThingError: LocalizedError {
    case entityNotFound(String)
    case versionConflict(String, String)
    case invalidEntityType(String)
    case storageError(Error)
    case syncError(String)
    case networkError(Error)
    case authenticationRequired
    case quotaExceeded(limit: Int, current: Int)
    
    public var errorDescription: String? {
        switch self {
        case .entityNotFound(let id):
            return "Entity not found: \(id)"
        case .versionConflict(let local, let remote):
            return "Version conflict: local=\(local), remote=\(remote)"
        case .invalidEntityType(let type):
            return "Invalid entity type: \(type)"
        case .storageError(let error):
            return "Storage error: \(error.localizedDescription)"
        case .syncError(let message):
            return "Sync error: \(message)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .authenticationRequired:
            return "Authentication required"
        case .quotaExceeded(let limit, let current):
            return "Quota exceeded: \(current)/\(limit)"
        }
    }
}
```

## Memory Management

### 1. Automatic Reference Counting

```swift
// Weak references to prevent cycles
class HomeGraph {
    private weak var delegate: HomeGraphDelegate?
    
    // Capture lists in closures
    func loadData() {
        Task { [weak self] in
            guard let self = self else { return }
            try await self.storage.loadEntities()
        }
    }
}
```

### 2. Memory Pressure Handling

```swift
// Respond to memory warnings
class GraphCache {
    init() {
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(handleMemoryWarning),
            name: UIApplication.didReceiveMemoryWarningNotification,
            object: nil
        )
    }
    
    @objc private func handleMemoryWarning() {
        memoryCache.removeAllObjects()
        // Keep only essential data
    }
}
```

## Platform Considerations

### iOS Specific

```swift
#if os(iOS)
extension WildThingMCPServer {
    // Background task handling
    func scheduleBackgroundSync() {
        BGTaskScheduler.shared.register(
            forTaskWithIdentifier: "com.wildthing.sync",
            using: nil
        ) { task in
            self.handleBackgroundSync(task: task as! BGProcessingTask)
        }
    }
    
    // App group sharing
    var sharedStorageURL: URL {
        FileManager.default.containerURL(
            forSecurityApplicationGroupIdentifier: "group.com.wildthing"
        )!
    }
}
#endif
```

### macOS Specific

```swift
#if os(macOS)
extension WildThingMCPServer {
    // Menu bar integration
    func setupStatusItem() {
        let statusItem = NSStatusBar.system.statusItem(
            withLength: NSStatusItem.variableLength
        )
        statusItem.button?.title = "🏠"
        statusItem.menu = createMenu()
    }
}
#endif
```

## Deployment

### Swift Package Manager

```swift
// Package.swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "WildThing",
    platforms: [
        .iOS(.v15),
        .macOS(.v12),
        .watchOS(.v8),
        .tvOS(.v15)
    ],
    products: [
        .library(
            name: "WildThing",
            targets: ["WildThing"]
        ),
        .library(
            name: "WildThingHomeKit",
            targets: ["WildThingHomeKit"]
        ),
        .executable(
            name: "wildthing",
            targets: ["WildThingCLI"]
        )
    ],
    dependencies: [
        .package(url: "https://github.com/modelcontextprotocol/swift-sdk.git", from: "0.9.0"),
        .package(url: "https://github.com/stephencelis/SQLite.swift.git", from: "0.14.1"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-crypto.git", from: "3.0.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.0.0")
    ],
    targets: [
        .target(
            name: "WildThing",
            dependencies: [
                .product(name: "ModelContextProtocol", package: "swift-sdk"),
                .product(name: "SQLite", package: "SQLite.swift"),
                .product(name: "Logging", package: "swift-log"),
                .product(name: "Crypto", package: "swift-crypto")
            ],
            resources: [
                .process("Resources")
            ]
        ),
        .target(
            name: "WildThingHomeKit",
            dependencies: ["WildThing"]
        ),
        .executableTarget(
            name: "WildThingCLI",
            dependencies: [
                "WildThing",
                .product(name: "ArgumentParser", package: "swift-argument-parser")
            ]
        ),
        .testTarget(
            name: "WildThingTests",
            dependencies: ["WildThing"],
            resources: [
                .copy("TestData")
            ]
        )
    ]
)
```

## Future Enhancements

### 1. Machine Learning Integration

```swift
// On-device ML for pattern recognition
#if canImport(CoreML)
class SmartAutomation {
    private let model: MLModel
    
    func suggestAutomations(for entities: [HomeEntity]) -> [AutomationSuggestion] {
        // Use CoreML to analyze usage patterns
        // Return automation suggestions
    }
}
#endif
```

### 2. Advanced Analytics

```swift
// Analytics and insights
class HomeAnalytics {
    func energyUsageReport(period: DateInterval) async throws -> EnergyReport {
        // Aggregate device usage data
        // Calculate costs and trends
        // Identify optimization opportunities
    }
    
    func predictiveMaintenence() async throws -> [MaintenanceAlert] {
        // Analyze device age and usage
        // Predict maintenance needs
        // Generate alerts
    }
}
```

### 3. Voice Integration

```swift
// Siri Shortcuts and voice commands
#if canImport(Intents)
class WildThingIntentHandler: INExtension {
    override func handler(for intent: INIntent) -> Any {
        switch intent {
        case is ControlDeviceIntent:
            return ControlDeviceIntentHandler()
        case is QueryRoomIntent:
            return QueryRoomIntentHandler()
        default:
            return self
        }
    }
}
#endif
```