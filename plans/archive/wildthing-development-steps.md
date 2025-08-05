# WildThing Swift Package - Detailed Development Steps

## Overview

WildThing is the Swift Package component of The Goodies project, providing a local-first smart home knowledge graph with MCP server capabilities. This guide provides detailed steps for implementing WildThing from scratch.

## Prerequisites

- macOS 13+ with Xcode 15+
- Swift 5.9+
- SQLite 3.35+
- Basic knowledge of Swift concurrency (async/await)
- Familiarity with Swift Package Manager

## Step 1: Package Structure Setup

### 1.1 Initialize Swift Package

```bash
cd WildThing
swift package init --type library --name WildThing
```

### 1.2 Update Package.swift

```swift
// Package.swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "WildThing",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
        .tvOS(.v16),
        .watchOS(.v9)
    ],
    products: [
        .library(
            name: "WildThing",
            targets: ["WildThing"]),
        .executable(
            name: "wildthing-mcp",
            targets: ["WildThingMCP"])
    ],
    dependencies: [
        .package(url: "https://github.com/stephencelis/SQLite.swift.git", from: "0.14.0"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.5.0"),
        .package(url: "https://github.com/apple/swift-nio.git", from: "2.60.0"),
        .package(url: "https://github.com/swift-server/async-http-client.git", from: "1.19.0")
    ],
    targets: [
        .target(
            name: "WildThing",
            dependencies: [
                .product(name: "SQLite", package: "SQLite.swift"),
                .product(name: "Logging", package: "swift-log"),
                .product(name: "AsyncHTTPClient", package: "async-http-client")
            ]),
        .executableTarget(
            name: "WildThingMCP",
            dependencies: [
                "WildThing",
                .product(name: "NIO", package: "swift-nio"),
                .product(name: "NIOHTTP1", package: "swift-nio")
            ]),
        .testTarget(
            name: "WildThingTests",
            dependencies: ["WildThing"]),
    ]
)
```

### 1.3 Create Directory Structure

```bash
mkdir -p Sources/WildThing/{Core,Storage,Graph,MCP,Inbetweenies,Platform}
mkdir -p Sources/WildThing/Core/{Models,Protocols,Extensions}
mkdir -p Sources/WildThing/Storage/{SQLite,Memory}
mkdir -p Sources/WildThing/MCP/{Server,Tools,Handlers}
mkdir -p Sources/WildThing/Platform/{iOS,macOS,HomeKit}
mkdir -p Tests/WildThingTests/{Unit,Integration,Performance}
```

## Step 2: Core Data Models

### 2.1 Define Core Protocols

```swift
// Sources/WildThing/Core/Protocols/WildThingEntity.swift
import Foundation

public protocol WildThingEntity: Codable, Identifiable, Hashable {
    var id: String { get }
    var version: String { get }
    var entityType: EntityType { get }
    var parentVersions: [String] { get }
    var content: [String: Any] { get set }
    var userId: String { get }
    var sourceType: SourceType { get }
    var createdAt: Date { get }
    var lastModified: Date { get }
}

// Sources/WildThing/Core/Protocols/Storage.swift
public protocol WildThingStorage: Sendable {
    func save(_ entity: any WildThingEntity) async throws
    func saveMany(_ entities: [any WildThingEntity]) async throws
    func fetch(id: String) async throws -> (any WildThingEntity)?
    func fetchLatestVersion(id: String) async throws -> (any WildThingEntity)?
    func fetchAll(ofType type: EntityType, userId: String) async throws -> [any WildThingEntity]
    func fetchModifiedSince(_ date: Date, userId: String) async throws -> [any WildThingEntity]
    func delete(id: String, version: String) async throws
    func deleteAll(userId: String) async throws
}
```

### 2.2 Implement Entity Types

```swift
// Sources/WildThing/Core/Models/EntityType.swift
public enum EntityType: String, Codable, CaseIterable {
    case home = "home"
    case room = "room"
    case device = "device"
    case accessory = "accessory"
    case service = "service"
    case zone = "zone"
    case door = "door"
    case window = "window"
    case procedure = "procedure"
    case manual = "manual"
    case note = "note"
    case schedule = "schedule"
    case automation = "automation"
}

public enum SourceType: String, Codable {
    case manual = "manual"
    case homekit = "homekit"
    case matter = "matter"
    case imported = "imported"
    case automated = "automated"
}

public enum RelationshipType: String, Codable {
    case locatedIn = "located_in"
    case controls = "controls"
    case connectsTo = "connects_to"
    case partOf = "part_of"
    case manages = "manages"
    case documentedBy = "documented_by"
    case procedureFor = "procedure_for"
    case triggeredBy = "triggered_by"
    case dependsOn = "depends_on"
}
```

### 2.3 Create Concrete Entity Models

```swift
// Sources/WildThing/Core/Models/HomeEntity.swift
import Foundation

public struct HomeEntity: WildThingEntity {
    public let id: String
    public let version: String
    public let entityType: EntityType = .home
    public let parentVersions: [String]
    public var content: [String: Any]
    public let userId: String
    public let sourceType: SourceType
    public let createdAt: Date
    public let lastModified: Date
    
    // Custom properties for Home
    public var name: String {
        get { content["name"] as? String ?? "" }
        set { content["name"] = newValue }
    }
    
    public var address: String? {
        get { content["address"] as? String }
        set { content["address"] = newValue }
    }
    
    public init(
        id: String = UUID().uuidString,
        version: String? = nil,
        parentVersions: [String] = [],
        content: [String: Any] = [:],
        userId: String,
        sourceType: SourceType,
        createdAt: Date = Date(),
        lastModified: Date = Date()
    ) {
        self.id = id
        self.version = version ?? Self.generateVersion(deviceId: UIDevice.current.identifierForVendor?.uuidString ?? "unknown")
        self.parentVersions = parentVersions
        self.content = content
        self.userId = userId
        self.sourceType = sourceType
        self.createdAt = createdAt
        self.lastModified = lastModified
    }
    
    static func generateVersion(deviceId: String) -> String {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        let sequence = String(format: "%03d", Int.random(in: 0...999))
        return "\(timestamp)-\(deviceId)-\(sequence)"
    }
}

// Sources/WildThing/Core/Models/RoomEntity.swift
public struct RoomEntity: WildThingEntity {
    // Similar implementation with room-specific properties
    public var homeId: String? {
        get { content["homeId"] as? String }
        set { content["homeId"] = newValue }
    }
    
    public var floor: Int? {
        get { content["floor"] as? Int }
        set { content["floor"] = newValue }
    }
}

// Sources/WildThing/Core/Models/DeviceEntity.swift
public struct DeviceEntity: WildThingEntity {
    // Device-specific properties
    public var roomId: String? {
        get { content["roomId"] as? String }
        set { content["roomId"] = newValue }
    }
    
    public var manufacturer: String? {
        get { content["manufacturer"] as? String }
        set { content["manufacturer"] = newValue }
    }
    
    public var model: String? {
        get { content["model"] as? String }
        set { content["model"] = newValue }
    }
    
    public var capabilities: [String] {
        get { content["capabilities"] as? [String] ?? [] }
        set { content["capabilities"] = newValue }
    }
}
```

## Step 3: Storage Implementation

### 3.1 SQLite Schema

```swift
// Sources/WildThing/Storage/SQLite/Schema.swift
import SQLite

struct Schema {
    static let entities = Table("entities")
    static let id = Expression<String>("id")
    static let version = Expression<String>("version")
    static let entityType = Expression<String>("entity_type")
    static let parentVersions = Expression<String>("parent_versions") // JSON
    static let content = Expression<String>("content") // JSON
    static let userId = Expression<String>("user_id")
    static let sourceType = Expression<String>("source_type")
    static let createdAt = Expression<Date>("created_at")
    static let lastModified = Expression<Date>("last_modified")
    
    static let relationships = Table("relationships")
    static let relationshipId = Expression<String>("id")
    static let fromEntityId = Expression<String>("from_entity_id")
    static let toEntityId = Expression<String>("to_entity_id")
    static let relationshipType = Expression<String>("relationship_type")
    static let properties = Expression<String?>("properties") // JSON
    
    static let binaryContent = Table("binary_content")
    static let binaryId = Expression<String>("id")
    static let entityId = Expression<String>("entity_id")
    static let entityVersion = Expression<String>("entity_version")
    static let contentType = Expression<String>("content_type")
    static let fileName = Expression<String?>("file_name")
    static let data = Expression<Data>("data")
    static let checksum = Expression<String>("checksum")
    
    static func createTables(in db: Connection) throws {
        // Create entities table
        try db.run(entities.create(ifNotExists: true) { t in
            t.column(id)
            t.column(version)
            t.column(entityType)
            t.column(parentVersions)
            t.column(content)
            t.column(userId)
            t.column(sourceType)
            t.column(createdAt)
            t.column(lastModified)
            t.primaryKey(id, version)
        })
        
        // Create indexes
        try db.run(entities.createIndex(entityType, ifNotExists: true))
        try db.run(entities.createIndex(lastModified, ifNotExists: true))
        try db.run(entities.createIndex([id, createdAt.desc], ifNotExists: true))
        
        // Create relationships table
        try db.run(relationships.create(ifNotExists: true) { t in
            t.column(relationshipId, primaryKey: true)
            t.column(fromEntityId)
            t.column(toEntityId)
            t.column(relationshipType)
            t.column(properties)
            t.column(userId)
            t.column(createdAt)
            t.foreignKey(fromEntityId, references: entities, id)
            t.foreignKey(toEntityId, references: entities, id)
        })
        
        // Create binary content table
        try db.run(binaryContent.create(ifNotExists: true) { t in
            t.column(binaryId, primaryKey: true)
            t.column(entityId)
            t.column(entityVersion)
            t.column(contentType)
            t.column(fileName)
            t.column(data)
            t.column(checksum)
            t.column(createdAt)
            t.foreignKey((entityId, entityVersion), references: entities, (id, version))
        })
    }
}
```

### 3.2 SQLite Storage Implementation

```swift
// Sources/WildThing/Storage/SQLite/SQLiteStorage.swift
import Foundation
import SQLite
import Logging

public actor SQLiteStorage: WildThingStorage {
    private let db: Connection
    private let logger = Logger(label: "WildThing.SQLiteStorage")
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    
    public init(path: String = "wildthing.db") throws {
        if path == ":memory:" {
            db = try Connection(.inMemory)
        } else {
            let url = URL(fileURLWithPath: path)
            db = try Connection(url.path)
        }
        
        // Configure SQLite for better performance
        try db.execute("PRAGMA journal_mode = WAL")
        try db.execute("PRAGMA synchronous = NORMAL")
        try db.execute("PRAGMA temp_store = MEMORY")
        try db.execute("PRAGMA mmap_size = 30000000000")
        
        // Create schema
        try Schema.createTables(in: db)
    }
    
    public func save(_ entity: any WildThingEntity) async throws {
        let contentData = try encoder.encode(entity.content)
        let contentString = String(data: contentData, encoding: .utf8)!
        
        let parentVersionsData = try encoder.encode(entity.parentVersions)
        let parentVersionsString = String(data: parentVersionsData, encoding: .utf8)!
        
        let insert = Schema.entities.insert(or: .replace,
            Schema.id <- entity.id,
            Schema.version <- entity.version,
            Schema.entityType <- entity.entityType.rawValue,
            Schema.parentVersions <- parentVersionsString,
            Schema.content <- contentString,
            Schema.userId <- entity.userId,
            Schema.sourceType <- entity.sourceType.rawValue,
            Schema.createdAt <- entity.createdAt,
            Schema.lastModified <- entity.lastModified
        )
        
        try db.run(insert)
        logger.debug("Saved entity: \(entity.id) v\(entity.version)")
    }
    
    public func saveMany(_ entities: [any WildThingEntity]) async throws {
        try db.transaction {
            for entity in entities {
                try await save(entity)
            }
        }
    }
    
    public func fetch(id: String) async throws -> (any WildThingEntity)? {
        let query = Schema.entities
            .filter(Schema.id == id)
            .order(Schema.createdAt.desc)
            .limit(1)
        
        guard let row = try db.pluck(query) else { return nil }
        return try entityFromRow(row)
    }
    
    public func fetchLatestVersion(id: String) async throws -> (any WildThingEntity)? {
        return try await fetch(id: id)
    }
    
    public func fetchAll(ofType type: EntityType, userId: String) async throws -> [any WildThingEntity] {
        let query = Schema.entities
            .filter(Schema.entityType == type.rawValue)
            .filter(Schema.userId == userId)
            .order(Schema.lastModified.desc)
        
        var entities: [any WildThingEntity] = []
        for row in try db.prepare(query) {
            if let entity = try entityFromRow(row) {
                entities.append(entity)
            }
        }
        return entities
    }
    
    public func fetchModifiedSince(_ date: Date, userId: String) async throws -> [any WildThingEntity] {
        let query = Schema.entities
            .filter(Schema.userId == userId)
            .filter(Schema.lastModified > date)
            .order(Schema.lastModified.asc)
        
        var entities: [any WildThingEntity] = []
        for row in try db.prepare(query) {
            if let entity = try entityFromRow(row) {
                entities.append(entity)
            }
        }
        return entities
    }
    
    private func entityFromRow(_ row: Row) throws -> (any WildThingEntity)? {
        let typeString = row[Schema.entityType]
        guard let type = EntityType(rawValue: typeString) else { return nil }
        
        let contentString = row[Schema.content]
        let contentData = contentString.data(using: .utf8)!
        let content = try decoder.decode([String: Any].self, from: contentData)
        
        let parentVersionsString = row[Schema.parentVersions]
        let parentVersionsData = parentVersionsString.data(using: .utf8)!
        let parentVersions = try decoder.decode([String].self, from: parentVersionsData)
        
        let sourceTypeString = row[Schema.sourceType]
        guard let sourceType = SourceType(rawValue: sourceTypeString) else { return nil }
        
        switch type {
        case .home:
            return HomeEntity(
                id: row[Schema.id],
                version: row[Schema.version],
                parentVersions: parentVersions,
                content: content,
                userId: row[Schema.userId],
                sourceType: sourceType,
                createdAt: row[Schema.createdAt],
                lastModified: row[Schema.lastModified]
            )
        case .room:
            return RoomEntity(
                id: row[Schema.id],
                version: row[Schema.version],
                parentVersions: parentVersions,
                content: content,
                userId: row[Schema.userId],
                sourceType: sourceType,
                createdAt: row[Schema.createdAt],
                lastModified: row[Schema.lastModified]
            )
        case .device:
            return DeviceEntity(
                id: row[Schema.id],
                version: row[Schema.version],
                parentVersions: parentVersions,
                content: content,
                userId: row[Schema.userId],
                sourceType: sourceType,
                createdAt: row[Schema.createdAt],
                lastModified: row[Schema.lastModified]
            )
        default:
            // Handle other entity types
            return nil
        }
    }
}
```

## Step 4: Graph Operations

### 4.1 Home Graph Implementation

```swift
// Sources/WildThing/Graph/HomeGraph.swift
import Foundation

public actor HomeGraph {
    private let storage: WildThingStorage
    private var cache: [String: any WildThingEntity] = [:]
    private var relationships: [String: [EntityRelationship]] = [:]
    
    public init(storage: WildThingStorage) {
        self.storage = storage
    }
    
    // Load graph for user
    public func loadGraph(userId: String) async throws {
        // Clear cache
        cache.removeAll()
        relationships.removeAll()
        
        // Load all entities
        for type in EntityType.allCases {
            let entities = try await storage.fetchAll(ofType: type, userId: userId)
            for entity in entities {
                cache[entity.id] = entity
            }
        }
        
        // Load relationships
        // TODO: Implement relationship loading
    }
    
    // Find entities by type
    public func findEntities(ofType type: EntityType) -> [any WildThingEntity] {
        return cache.values.filter { $0.entityType == type }
    }
    
    // Find rooms in home
    public func findRooms(inHome homeId: String) -> [RoomEntity] {
        return cache.values.compactMap { entity in
            guard let room = entity as? RoomEntity,
                  room.homeId == homeId else { return nil }
            return room
        }
    }
    
    // Find devices in room
    public func findDevices(inRoom roomId: String) -> [DeviceEntity] {
        return cache.values.compactMap { entity in
            guard let device = entity as? DeviceEntity,
                  device.roomId == roomId else { return nil }
            return device
        }
    }
    
    // Path finding between rooms
    public func findPath(from: String, to: String) -> [String]? {
        // Implement BFS/DFS for path finding
        var visited = Set<String>()
        var queue = [(from, [from])]
        
        while !queue.isEmpty {
            let (current, path) = queue.removeFirst()
            
            if current == to {
                return path
            }
            
            if visited.contains(current) {
                continue
            }
            visited.insert(current)
            
            // Get connected rooms
            let connections = relationships[current]?.filter { 
                $0.relationshipType == .connectsTo 
            } ?? []
            
            for connection in connections {
                let next = connection.toEntityId
                if !visited.contains(next) {
                    queue.append((next, path + [next]))
                }
            }
        }
        
        return nil
    }
}
```

### 4.2 Graph Traversal

```swift
// Sources/WildThing/Graph/Traversal.swift
public struct GraphTraversal {
    let graph: HomeGraph
    
    // Find all devices controlled by a switch
    public func findControlledDevices(switchId: String) async -> [DeviceEntity] {
        // Implementation
    }
    
    // Find all entities in a zone
    public func findEntitiesInZone(zoneId: String) async -> [any WildThingEntity] {
        // Implementation
    }
    
    // Find automation dependencies
    public func findAutomationDependencies(automationId: String) async -> [any WildThingEntity] {
        // Implementation
    }
}
```

## Step 5: Inbetweenies Sync Protocol

### 5.1 Sync Messages

```swift
// Sources/WildThing/Inbetweenies/Messages.swift
import Foundation

public struct InbetweeniesRequest: Codable {
    let protocolVersion: String = "inbetweenies-v1"
    let deviceId: String
    let userId: String
    let sessionId: String
    let vectorClock: [String: String]
    let changes: [EntityChange]
    let compression: CompressionType
    let capabilities: [String]
    let metadata: RequestMetadata
}

public struct EntityChange: Codable {
    let changeType: ChangeType
    let entityId: String
    let entityVersion: String
    let entityType: String?
    let parentVersions: [String]
    let content: [String: Any]?
    let timestamp: Date
    let checksum: String?
    let deviceId: String
    let userId: String
}

public enum ChangeType: String, Codable {
    case create, update, delete
}

public struct InbetweeniesResponse: Codable {
    let protocolVersion: String
    let serverTime: Date
    let sessionId: String
    let vectorClock: [String: String]
    let changes: [EntityChange]
    let conflicts: [ConflictInfo]
    let nextSyncToken: String?
    let syncStatus: SyncStatus
    let serverCapabilities: [String]
    let rateLimit: RateLimitInfo?
}

public enum SyncStatus: String, Codable {
    case success, partial, failed
}
```

### 5.2 Sync Manager

```swift
// Sources/WildThing/Inbetweenies/SyncManager.swift
import Foundation
import AsyncHTTPClient
import Logging

public actor SyncManager {
    private let storage: WildThingStorage
    private let httpClient: HTTPClient
    private let serverURL: URL
    private let deviceId: String
    private var vectorClock: VectorClock
    private let logger = Logger(label: "WildThing.SyncManager")
    
    public init(storage: WildThingStorage, serverURL: URL) {
        self.storage = storage
        self.serverURL = serverURL
        self.httpClient = HTTPClient(eventLoopGroupProvider: .createNew)
        self.deviceId = UIDevice.current.identifierForVendor?.uuidString ?? "unknown"
        self.vectorClock = VectorClock()
    }
    
    public func sync(userId: String) async throws {
        logger.info("Starting sync for user: \(userId)")
        
        // 1. Collect local changes
        let lastSync = try await getLastSyncTime(userId: userId)
        let changes = try await collectLocalChanges(since: lastSync, userId: userId)
        
        // 2. Update vector clock
        vectorClock.increment(nodeId: deviceId)
        
        // 3. Prepare sync request
        let request = InbetweeniesRequest(
            deviceId: deviceId,
            userId: userId,
            sessionId: UUID().uuidString,
            vectorClock: vectorClock.toDict(),
            changes: changes,
            compression: .gzip,
            capabilities: ["batch_1000", "compression_gzip"],
            metadata: RequestMetadata(
                clientVersion: "1.0.0",
                platform: "iOS",
                syncReason: .periodic
            )
        )
        
        // 4. Send to server
        let response = try await sendSyncRequest(request)
        
        // 5. Process response
        try await processResponse(response, userId: userId)
        
        // 6. Update last sync time
        try await updateLastSyncTime(userId: userId)
        
        logger.info("Sync completed successfully")
    }
    
    private func collectLocalChanges(since: Date?, userId: String) async throws -> [EntityChange] {
        let modifiedEntities = try await storage.fetchModifiedSince(since ?? .distantPast, userId: userId)
        
        return modifiedEntities.map { entity in
            EntityChange(
                changeType: .update, // TODO: Detect create/delete
                entityId: entity.id,
                entityVersion: entity.version,
                entityType: entity.entityType.rawValue,
                parentVersions: entity.parentVersions,
                content: entity.content,
                timestamp: entity.lastModified,
                checksum: nil, // TODO: Calculate checksum
                deviceId: deviceId,
                userId: userId
            )
        }
    }
    
    private func sendSyncRequest(_ request: InbetweeniesRequest) async throws -> InbetweeniesResponse {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let requestData = try encoder.encode(request)
        
        var httpRequest = HTTPClientRequest(url: serverURL.appendingPathComponent("/sync"))
        httpRequest.method = .POST
        httpRequest.headers.add(name: "Content-Type", value: "application/json")
        httpRequest.body = .bytes(requestData)
        
        let httpResponse = try await httpClient.execute(httpRequest, timeout: .seconds(30))
        let responseData = try await httpResponse.body.collect(upTo: 10_000_000) // 10MB limit
        
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(InbetweeniesResponse.self, from: responseData)
    }
    
    private func processResponse(_ response: InbetweeniesResponse, userId: String) async throws {
        // 1. Apply server changes
        for change in response.changes {
            try await applyChange(change)
        }
        
        // 2. Handle conflicts
        for conflict in response.conflicts {
            try await resolveConflict(conflict)
        }
        
        // 3. Update vector clock
        vectorClock.merge(response.vectorClock)
    }
}
```

### 5.3 Vector Clock Implementation

```swift
// Sources/WildThing/Inbetweenies/VectorClock.swift
import Foundation

struct VectorClock {
    private var clocks: [String: String] = [:]
    
    mutating func increment(nodeId: String) {
        let current = clocks[nodeId] ?? zeroVersion()
        let (_, _, seq) = parseVersion(current)
        let newSeq = (Int(seq) ?? 0) + 1
        let timestamp = ISO8601DateFormatter().string(from: Date())
        clocks[nodeId] = "\(timestamp)-\(nodeId)-\(String(format: "%03d", newSeq))"
    }
    
    mutating func merge(_ other: [String: String]) {
        for (nodeId, version) in other {
            if let currentVersion = clocks[nodeId] {
                if compareVersions(version, currentVersion) > 0 {
                    clocks[nodeId] = version
                }
            } else {
                clocks[nodeId] = version
            }
        }
    }
    
    func toDict() -> [String: String] {
        return clocks
    }
    
    private func zeroVersion() -> String {
        return "1970-01-01T00:00:00Z-unknown-000"
    }
    
    private func parseVersion(_ version: String) -> (String, String, String) {
        let parts = version.split(separator: "-")
        guard parts.count >= 3 else {
            return ("", "", "")
        }
        let timestamp = String(parts[0..<parts.count-2].joined(separator: "-"))
        let nodeId = String(parts[parts.count-2])
        let sequence = String(parts[parts.count-1])
        return (timestamp, nodeId, sequence)
    }
    
    private func compareVersions(_ v1: String, _ v2: String) -> Int {
        let (t1, _, s1) = parseVersion(v1)
        let (t2, _, s2) = parseVersion(v2)
        
        if t1 < t2 { return -1 }
        if t1 > t2 { return 1 }
        
        let seq1 = Int(s1) ?? 0
        let seq2 = Int(s2) ?? 0
        
        if seq1 < seq2 { return -1 }
        if seq1 > seq2 { return 1 }
        
        return 0
    }
}
```

## Step 6: MCP Server Implementation

### 6.1 MCP Server

```swift
// Sources/WildThing/MCP/Server/WildThingMCPServer.swift
import Foundation
import NIO
import NIOHTTP1
import Logging

public class WildThingMCPServer {
    private let storage: WildThingStorage
    private let homeGraph: HomeGraph
    private let syncManager: SyncManager
    private let port: Int
    private let logger = Logger(label: "WildThing.MCPServer")
    private var channel: Channel?
    
    public init(storage: WildThingStorage, port: Int = 8080) {
        self.storage = storage
        self.homeGraph = HomeGraph(storage: storage)
        self.syncManager = SyncManager(storage: storage, serverURL: URL(string: "https://funkygibbon.local")!)
        self.port = port
    }
    
    public func start() async throws {
        let group = MultiThreadedEventLoopGroup(numberOfThreads: System.coreCount)
        
        let bootstrap = ServerBootstrap(group: group)
            .serverChannelOption(ChannelOptions.backlog, value: 256)
            .serverChannelOption(ChannelOptions.socketOption(.so_reuseaddr), value: 1)
            .childChannelInitializer { channel in
                channel.pipeline.configureHTTPServerPipeline().flatMap {
                    channel.pipeline.addHandler(MCPHandler(server: self))
                }
            }
        
        channel = try await bootstrap.bind(host: "localhost", port: port).get()
        logger.info("MCP Server started on port \(port)")
        
        try await channel?.closeFuture.get()
    }
    
    func handleRequest(_ request: MCPRequest) async throws -> MCPResponse {
        switch request.tool {
        case "create_entity":
            return try await handleCreateEntity(request.parameters)
        case "query_graph":
            return try await handleQueryGraph(request.parameters)
        case "update_entity":
            return try await handleUpdateEntity(request.parameters)
        case "delete_entity":
            return try await handleDeleteEntity(request.parameters)
        case "sync_now":
            return try await handleSyncNow(request.parameters)
        default:
            throw MCPError.unknownTool(request.tool)
        }
    }
}
```

### 6.2 MCP Tools

```swift
// Sources/WildThing/MCP/Tools/CreateEntityTool.swift
struct CreateEntityTool {
    let storage: WildThingStorage
    
    func execute(parameters: [String: Any]) async throws -> [String: Any] {
        guard let type = parameters["type"] as? String,
              let entityType = EntityType(rawValue: type),
              let content = parameters["content"] as? [String: Any],
              let userId = parameters["userId"] as? String else {
            throw MCPError.invalidParameters
        }
        
        let entity: any WildThingEntity
        
        switch entityType {
        case .home:
            entity = HomeEntity(
                content: content,
                userId: userId,
                sourceType: .manual
            )
        case .room:
            entity = RoomEntity(
                content: content,
                userId: userId,
                sourceType: .manual
            )
        case .device:
            entity = DeviceEntity(
                content: content,
                userId: userId,
                sourceType: .manual
            )
        default:
            throw MCPError.unsupportedEntityType(type)
        }
        
        try await storage.save(entity)
        
        return [
            "id": entity.id,
            "version": entity.version,
            "type": entity.entityType.rawValue,
            "created": ISO8601DateFormatter().string(from: entity.createdAt)
        ]
    }
}
```

## Step 7: Platform Integration

### 7.1 HomeKit Bridge

```swift
// Sources/WildThing/Platform/HomeKit/HomeKitBridge.swift
import HomeKit

@available(iOS 16.0, *)
public class HomeKitBridge {
    private let storage: WildThingStorage
    private let homeManager = HMHomeManager()
    
    public init(storage: WildThingStorage) {
        self.storage = storage
    }
    
    public func importHomes() async throws {
        // Request permission
        guard homeManager.authorizationStatus == .authorized else {
            throw HomeKitError.notAuthorized
        }
        
        // Import all homes
        for home in homeManager.homes {
            try await importHome(home)
        }
    }
    
    private func importHome(_ home: HMHome) async throws {
        // Create home entity
        let homeEntity = HomeEntity(
            id: home.uniqueIdentifier.uuidString,
            content: [
                "name": home.name,
                "isPrimary": home.isPrimary
            ],
            userId: getCurrentUserId(),
            sourceType: .homekit
        )
        
        try await storage.save(homeEntity)
        
        // Import rooms
        for room in home.rooms {
            try await importRoom(room, homeId: homeEntity.id)
        }
        
        // Import accessories
        for accessory in home.accessories {
            try await importAccessory(accessory, homeId: homeEntity.id)
        }
    }
    
    private func importRoom(_ room: HMRoom, homeId: String) async throws {
        let roomEntity = RoomEntity(
            id: room.uniqueIdentifier.uuidString,
            content: [
                "name": room.name,
                "homeId": homeId
            ],
            userId: getCurrentUserId(),
            sourceType: .homekit
        )
        
        try await storage.save(roomEntity)
    }
    
    private func importAccessory(_ accessory: HMAccessory, homeId: String) async throws {
        let deviceEntity = DeviceEntity(
            id: accessory.uniqueIdentifier.uuidString,
            content: [
                "name": accessory.name,
                "manufacturer": accessory.manufacturer ?? "Unknown",
                "model": accessory.model ?? "Unknown",
                "roomId": accessory.room?.uniqueIdentifier.uuidString,
                "isReachable": accessory.isReachable,
                "isBridged": accessory.isBridged,
                "category": accessory.category.categoryType
            ],
            userId: getCurrentUserId(),
            sourceType: .homekit
        )
        
        try await storage.save(deviceEntity)
        
        // Import services
        for service in accessory.services {
            try await importService(service, deviceId: deviceEntity.id)
        }
    }
}
```

## Step 8: Testing

### 8.1 Unit Tests

```swift
// Tests/WildThingTests/Unit/HomeEntityTests.swift
import XCTest
@testable import WildThing

class HomeEntityTests: XCTestCase {
    func testEntityCreation() {
        let entity = HomeEntity(
            content: ["name": "Test Home"],
            userId: "test-user",
            sourceType: .manual
        )
        
        XCTAssertNotNil(entity.id)
        XCTAssertEqual(entity.entityType, .home)
        XCTAssertEqual(entity.name, "Test Home")
        XCTAssertEqual(entity.userId, "test-user")
        XCTAssertEqual(entity.sourceType, .manual)
    }
    
    func testVersionGeneration() {
        let version = HomeEntity.generateVersion(deviceId: "test-device")
        XCTAssertTrue(version.contains("test-device"))
        XCTAssertTrue(version.contains("-"))
    }
}

// Tests/WildThingTests/Unit/SQLiteStorageTests.swift
class SQLiteStorageTests: XCTestCase {
    var storage: SQLiteStorage!
    
    override func setUp() async throws {
        storage = try SQLiteStorage(path: ":memory:")
    }
    
    func testSaveAndFetch() async throws {
        let entity = HomeEntity(
            content: ["name": "Test Home"],
            userId: "test-user",
            sourceType: .manual
        )
        
        try await storage.save(entity)
        
        let fetched = try await storage.fetch(id: entity.id)
        XCTAssertNotNil(fetched)
        XCTAssertEqual(fetched?.id, entity.id)
        XCTAssertEqual((fetched as? HomeEntity)?.name, "Test Home")
    }
    
    func testBulkSave() async throws {
        let entities = (0..<100).map { i in
            HomeEntity(
                content: ["name": "Home \(i)"],
                userId: "test-user",
                sourceType: .manual
            )
        }
        
        let start = Date()
        try await storage.saveMany(entities)
        let duration = Date().timeIntervalSince(start)
        
        XCTAssertLessThan(duration, 1.0) // Should complete in under 1 second
        
        let allHomes = try await storage.fetchAll(ofType: .home, userId: "test-user")
        XCTAssertEqual(allHomes.count, 100)
    }
}
```

### 8.2 Integration Tests

```swift
// Tests/WildThingTests/Integration/InbetweeniesIntegrationTests.swift
class InbetweeniesIntegrationTests: XCTestCase {
    var storage: SQLiteStorage!
    var syncManager: SyncManager!
    
    override func setUp() async throws {
        storage = try SQLiteStorage(path: ":memory:")
        syncManager = SyncManager(
            storage: storage,
            serverURL: URL(string: "http://localhost:8000")!
        )
    }
    
    func testSyncFlow() async throws {
        // Create local entities
        let home = HomeEntity(
            content: ["name": "Test Home"],
            userId: "test-user",
            sourceType: .manual
        )
        try await storage.save(home)
        
        // Perform sync
        try await syncManager.sync(userId: "test-user")
        
        // Verify sync completed
        // This would require a mock server or test server
    }
}
```

### 8.3 Performance Tests

```swift
// Tests/WildThingTests/Performance/PerformanceBenchmarks.swift
class PerformanceBenchmarks: XCTestCase {
    var storage: SQLiteStorage!
    
    override func setUp() async throws {
        storage = try SQLiteStorage(path: ":memory:")
    }
    
    func testBulkInsertPerformance() {
        measure {
            let entities = (0..<1000).map { _ in
                HomeEntity(
                    content: ["name": "Home"],
                    userId: "test-user",
                    sourceType: .manual
                )
            }
            
            Task {
                try await storage.saveMany(entities)
            }
        }
    }
    
    func testGraphTraversalPerformance() {
        // Setup test graph
        // Measure traversal performance
    }
}
```

## Step 9: Build and Package

### 9.1 Build Script

```bash
#!/bin/bash
# build.sh

echo "Building WildThing..."

# Clean
swift package clean

# Build for iOS
swift build -c release --arch arm64 --sdk iphoneos

# Build for macOS
swift build -c release

# Run tests
swift test

# Generate documentation
swift-doc generate Sources/WildThing --module-name WildThing --output docs

echo "Build complete!"
```

### 9.2 Package Distribution

```swift
// Create XCFramework for distribution
// Package.swift additions for binary distribution
```

## Step 10: Integration with c11s-ios-house

### 10.1 Add WildThing Dependency

```swift
// In c11s-ios-house Package.swift or Xcode project
dependencies: [
    .package(path: "../the-goodies/WildThing")
]
```

### 10.2 Initialize in App

```swift
// In c11s-ios-house AppDelegate or App
import WildThing

@main
struct C11sHouseApp: App {
    let wildThingServer: WildThingMCPServer
    
    init() {
        do {
            let storage = try SQLiteStorage()
            wildThingServer = WildThingMCPServer(storage: storage)
            
            Task {
                try await wildThingServer.start()
            }
        } catch {
            fatalError("Failed to initialize WildThing: \(error)")
        }
    }
}
```

## Troubleshooting

### Common Issues

1. **SQLite Threading Issues**
   - Use actor isolation for storage
   - Enable WAL mode for concurrent reads

2. **Memory Leaks**
   - Profile with Instruments
   - Use weak references in graph cycles

3. **Sync Conflicts**
   - Implement proper vector clock comparison
   - Add UI for manual conflict resolution

4. **Performance Issues**
   - Add indexes to SQLite tables
   - Implement caching layer
   - Use batch operations

## Next Steps

1. Implement remaining entity types
2. Add relationship management
3. Implement full MCP tool set
4. Add Matter/Thread support
5. Create SwiftUI components
6. Add CloudKit backup
7. Implement end-to-end encryption
8. Add analytics and monitoring

## Resources

- [Swift Concurrency Guide](https://docs.swift.org/swift-book/LanguageGuide/Concurrency.html)
- [SQLite.swift Documentation](https://github.com/stephencelis/SQLite.swift)
- [HomeKit Developer Guide](https://developer.apple.com/homekit/)
- [MCP Specification](https://modelcontextprotocol.org/)