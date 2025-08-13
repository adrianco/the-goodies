# The Goodies - Smart Home Knowledge Graph MCP Library

## Project Overview

A standalone, reusable Swift/Python MCP server library optimized for knowledge graphs representing homes, rooms, devices, and their relationships. Uses the **Inbetweenies** protocol for distributed synchronization between **WildThing** (Swift) and **Blowing-Off** (Python) clients and **FunkyGibbon** (Python) server components.

Initial prototype in Python used a simplified protocol setup, and has been implemented successfully. No Swift code will be generated until fully tested Python is working.

## Repository Structure

TODO: This needs to be updated to add the current blowing-off structure. The WildThing layout won't be implemented until later. Inbetweenies includes the models that are shared for the protocol, and all shared models and protocol should use the Inbetweenies naming scheme for both Python and Swift versions.

```
the-goodies/
├── WildThing/                    # Swift Package
│   ├── Sources/
│   │   ├── WildThing/
│   │   │   ├── Core/              # Core data models and protocols
│   │   │   ├── Storage/           # SQLite storage implementation
│   │   │   ├── Graph/             # In-memory graph operations
│   │   │   ├── MCP/               # MCP server implementation
│   │   │   ├── Inbetweenies/      # Sync protocol implementation
│   │   │   ├── HomeKit/           # HomeKit integration (iOS only)
│   │   │   └── Extensions/        # Platform-specific extensions
│   │   └── WildThingCLI/          # Command-line tool for testing
│   ├── Tests/
│   │   ├── WildThingTests/        # Unit tests
│   │   ├── IntegrationTests/      # Integration tests
│   │   └── TestData/              # Sample data for testing
│   ├── Examples/
│   │   ├── iOS/                   # iOS example app
│   │   ├── macOS/                 # macOS example app
│   │   └── CLI/                   # Command-line examples
│   ├── Package.swift
│   └── README.md
├── FunkyGibbon/                   # Python Package
│   ├── funkygibbon/
│   │   ├── __init__.py
│   │   ├── core/                  # Core data models
│   │   ├── storage/               # Database implementations
│   │   ├── mcp/                   # MCP server implementation
│   │   ├── inbetweenies/          # Sync protocol implementation
│   │   └── api/                   # FastAPI endpoints
│   ├── tests/
│   ├── examples/
│   ├── pyproject.toml
│   └── README.md
├── Inbetweenies/                  # Protocol Specification
│   ├── protocol-spec.md           # Inbetweenies protocol documentation
│   ├── schemas/                   # JSON schemas for sync messages
│   ├── examples/                  # Protocol usage examples
│   └── README.md
├── Docs/
│   ├── api-reference/
│   ├── guides/
│   ├── examples/
│   └── deployment/
├── Scripts/
│   ├── setup-dev.sh
│   ├── test-all.sh
│   └── release.sh
└── README.md
```

## WildThing Swift Package Design

TODO: Old design, use as a guide only and update when Python version is complete

### Package Definition
```swift
// WildThing/Package.swift
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
        .library(name: "WildThing", targets: ["WildThing"]),
        .library(name: "WildThingHomeKit", targets: ["WildThingHomeKit"]),
        .executable(name: "wildthing-cli", targets: ["WildThingCLI"])
    ],
    dependencies: [
        .package(url: "https://github.com/modelcontextprotocol/swift-sdk.git", from: "0.9.0"),
        .package(url: "https://github.com/stephencelis/SQLite.swift.git", from: "0.14.1"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-crypto.git", from: "2.0.0"),
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
            ]
        ),
        .target(
            name: "WildThingHomeKit",
            dependencies: ["WildThing"],
            path: "Sources/WildThingHomeKit"
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
            resources: [.copy("TestData")]
        )
    ]
)
```

## Core Data Models

### Platform-Agnostic Models

TODO: These models should be Inbetweenies not WildThing naming scheme

```swift
// Sources/WildThing/Core/Models.swift
import Foundation

public protocol WildThingEntity: Codable, Identifiable {
    var id: String { get }
    var version: String { get }
    var entityType: EntityType { get }
    var content: [String: AnyCodable] { get }
    var userId: String { get }
    var createdAt: Date { get }
    var lastModified: Date { get }
}

public struct HomeEntity: WildThingEntity {
    public let id: String
    public let version: String
    public let entityType: EntityType
    public let parentVersions: [String]
    public let content: [String: AnyCodable]
    public let userId: String
    public let sourceType: SourceType
    public let createdAt: Date
    public var lastModified: Date
    
    public init(
        id: String = UUID().uuidString,
        entityType: EntityType,
        content: [String: AnyCodable],
        userId: String,
        sourceType: SourceType = .manual,
        parentVersions: [String] = []
    ) {
        self.id = id
        self.entityType = entityType
        self.content = content
        self.userId = userId
        self.sourceType = sourceType
        self.parentVersions = parentVersions
        self.version = Self.generateVersion(userId: userId)
        self.createdAt = Date()
        self.lastModified = Date()
    }
    
    private static func generateVersion(userId: String) -> String {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        return "\(timestamp)-\(userId)"
    }
}

public enum EntityType: String, CaseIterable, Codable {
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
    case homekit = "homekit"
    case matter = "matter"
    case manual = "manual"
    case imported = "imported"
    case generated = "generated"
}

public struct EntityRelationship: Codable, Identifiable {
    public let id: String
    public let fromEntityId: String
    public let toEntityId: String
    public let relationshipType: RelationshipType
    public let properties: [String: AnyCodable]
    public let userId: String
    public let createdAt: Date
    
    public init(
        fromEntityId: String,
        toEntityId: String,
        relationshipType: RelationshipType,
        properties: [String: AnyCodable] = [:],
        userId: String
    ) {
        self.id = UUID().uuidString
        self.fromEntityId = fromEntityId
        self.toEntityId = toEntityId
        self.relationshipType = relationshipType
        self.properties = properties
        self.userId = userId
        self.createdAt = Date()
    }
}

public enum RelationshipType: String, CaseIterable, Codable {
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

// Type-erased wrapper for heterogeneous JSON storage
public struct AnyCodable: Codable {
    public let value: Any
    
    public init(_ value: Any) {
        self.value = value
    }
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if let bool = try? container.decode(Bool.self) {
            value = bool
        } else if let int = try? container.decode(Int.self) {
            value = int
        } else if let double = try? container.decode(Double.self) {
            value = double
        } else if let string = try? container.decode(String.self) {
            value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            value = array.map { $0.value }
        } else if let dictionary = try? container.decode([String: AnyCodable].self) {
            value = dictionary.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Unsupported type"))
        }
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map(AnyCodable.init))
        case let dictionary as [String: Any]:
            try container.encode(dictionary.mapValues(AnyCodable.init))
        default:
            throw EncodingError.invalidValue(value, .init(codingPath: encoder.codingPath, debugDescription: "Unsupported type"))
        }
    }
}
```

## Storage Layer

### Storage Protocol
```swift
// Sources/WildThing/Storage/StorageProtocol.swift
import Foundation

public protocol WildThingStorage {
    // Entity Management
    func store(entity: HomeEntity) async throws
    func getEntity(id: String) async throws -> HomeEntity?
    func getLatestVersion(for entityId: String) async throws -> HomeEntity?
    func getAllVersions(for entityId: String) async throws -> [HomeEntity]
    func getEntities(ofType type: EntityType) async throws -> [HomeEntity]
    func deleteEntity(id: String, version: String?) async throws
    
    // Relationship Management
    func store(relationship: EntityRelationship) async throws
    func getRelationships(from entityId: String) async throws -> [EntityRelationship]
    func getRelationships(to entityId: String) async throws -> [EntityRelationship]
    func getRelationships(ofType type: RelationshipType) async throws -> [EntityRelationship]
    func deleteRelationship(id: String) async throws
    
    // Search and Query
    func searchEntities(query: String, types: [EntityType]?) async throws -> [HomeEntity]
    func getEntitiesInRoom(_ roomId: String) async throws -> [HomeEntity]
    func findPath(from: String, to: String) async throws -> [String]
    
    // Sync Support
    func getChangedEntities(since: Date, userId: String?) async throws -> [HomeEntity]
    func getVectorClock() async throws -> [String: String]
    func updateVectorClock(_ clock: [String: String]) async throws
    func markSynced(entityId: String, version: String) async throws
    
    // Binary Content
    func storeBinaryContent(_ content: BinaryContent) async throws
    func getBinaryContent(id: String) async throws -> BinaryContent?
    func deleteBinaryContent(id: String) async throws
}

public struct BinaryContent: Identifiable, Codable {
    public let id: String
    public let entityId: String
    public let entityVersion: String
    public let contentType: String
    public let fileName: String?
    public let data: Data
    public let checksum: String
    public let createdAt: Date
    
    public init(
        entityId: String,
        entityVersion: String,
        contentType: String,
        fileName: String? = nil,
        data: Data
    ) {
        self.id = UUID().uuidString
        self.entityId = entityId
        self.entityVersion = entityVersion
        self.contentType = contentType
        self.fileName = fileName
        self.data = data
        self.checksum = data.sha256
        self.createdAt = Date()
    }
}
```

### SQLite Implementation
```swift
// Sources/WildThing/Storage/SQLiteStorage.swift
import SQLite
import Foundation
import Crypto

public class SQLiteWildThingStorage: WildThingStorage {
    private let db: Connection
    
    // Table definitions
    private let entities = Table("entities")
    private let entityId = Expression<String>("id")
    private let entityVersion = Expression<String>("version")
    private let entityType = Expression<String>("entity_type")
    private let parentVersions = Expression<String>("parent_versions")
    private let content = Expression<String>("content")
    private let userId = Expression<String>("user_id")
    private let sourceType = Expression<String>("source_type")
    private let createdAt = Expression<Int64>("created_at")
    private let lastModified = Expression<Int64>("last_modified")
    
    private let relationships = Table("relationships")
    private let relId = Expression<String>("id")
    private let fromEntityId = Expression<String>("from_entity_id")
    private let toEntityId = Expression<String>("to_entity_id")
    private let relationshipType = Expression<String>("relationship_type")
    private let relProperties = Expression<String>("properties")
    private let relUserId = Expression<String>("user_id")
    private let relCreatedAt = Expression<Int64>("created_at")
    
    private let binaryContent = Table("binary_content")
    private let binId = Expression<String>("id")
    private let binEntityId = Expression<String>("entity_id")
    private let binEntityVersion = Expression<String>("entity_version")
    private let binContentType = Expression<String>("content_type")
    private let binFileName = Expression<String?>("file_name")
    private let binData = Expression<Data>("data")
    private let binChecksum = Expression<String>("checksum")
    private let binCreatedAt = Expression<Int64>("created_at")
    
    public init(databasePath: String) throws {
        db = try Connection(databasePath)
        try setupTables()
        try createIndices()
    }
    
    private func setupTables() throws {
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
        
        try db.run(relationships.create(ifNotExists: true) { t in
            t.column(relId, primaryKey: true)
            t.column(fromEntityId)
            t.column(toEntityId)
            t.column(relationshipType)
            t.column(relProperties)
            t.column(relUserId)
            t.column(relCreatedAt)
        })
        
        try db.run(binaryContent.create(ifNotExists: true) { t in
            t.column(binId, primaryKey: true)
            t.column(binEntityId)
            t.column(binEntityVersion)
            t.column(binContentType)
            t.column(binFileName)
            t.column(binData)
            t.column(binChecksum)
            t.column(binCreatedAt)
        })
    }
    
    private func createIndices() throws {
        try db.run(entities.createIndex([entityType], ifNotExists: true))
        try db.run(entities.createIndex([lastModified], ifNotExists: true))
        try db.run(entities.createIndex([entityId, createdAt.desc], ifNotExists: true))
        try db.run(relationships.createIndex([fromEntityId], ifNotExists: true))
        try db.run(relationships.createIndex([toEntityId], ifNotExists: true))
        try db.run(relationships.createIndex([relationshipType], ifNotExists: true))
    }
    
    public func store(entity: HomeEntity) async throws {
        let parentVersionsJson = try JSONEncoder().encode(entity.parentVersions)
        let contentJson = try JSONEncoder().encode(entity.content)
        
        try db.run(entities.insert(or: .replace,
            entityId <- entity.id,
            entityVersion <- entity.version,
            entityType <- entity.entityType.rawValue,
            parentVersions <- String(data: parentVersionsJson, encoding: .utf8)!,
            content <- String(data: contentJson, encoding: .utf8)!,
            userId <- entity.userId,
            sourceType <- entity.sourceType.rawValue,
            createdAt <- Int64(entity.createdAt.timeIntervalSince1970),
            lastModified <- Int64(entity.lastModified.timeIntervalSince1970)
        ))
    }
    
    public func getEntity(id: String) async throws -> HomeEntity? {
        // Get latest version
        let query = entities
            .filter(entityId == id)
            .order(createdAt.desc)
            .limit(1)
        
        guard let row = try db.pluck(query) else { return nil }
        return try homeEntityFromRow(row)
    }
    
    public func getEntities(ofType type: EntityType) async throws -> [HomeEntity] {
        let query = entities.filter(entityType == type.rawValue)
        var result: [HomeEntity] = []
        
        for row in try db.prepare(query) {
            result.append(try homeEntityFromRow(row))
        }
        
        return result
    }
    
    public func getEntitiesInRoom(_ roomId: String) async throws -> [HomeEntity] {
        // Find all entities with "located_in" relationship to the room
        let locatedInRelationships = try db.prepare(relationships
            .filter(toEntityId == roomId && relationshipType == RelationshipType.locatedIn.rawValue))
        
        var entities: [HomeEntity] = []
        for relationshipRow in locatedInRelationships {
            let entityId = relationshipRow[fromEntityId]
            if let entity = try await getEntity(id: entityId) {
                entities.append(entity)
            }
        }
        
        return entities
    }
    
    public func store(relationship: EntityRelationship) async throws {
        let propertiesJson = try JSONEncoder().encode(relationship.properties)
        
        try db.run(relationships.insert(or: .replace,
            relId <- relationship.id,
            fromEntityId <- relationship.fromEntityId,
            toEntityId <- relationship.toEntityId,
            relationshipType <- relationship.relationshipType.rawValue,
            relProperties <- String(data: propertiesJson, encoding: .utf8)!,
            relUserId <- relationship.userId,
            relCreatedAt <- Int64(relationship.createdAt.timeIntervalSince1970)
        ))
    }
    
    public func getRelationships(from entityId: String) async throws -> [EntityRelationship] {
        let query = relationships.filter(fromEntityId == entityId)
        var result: [EntityRelationship] = []
        
        for row in try db.prepare(query) {
            result.append(try relationshipFromRow(row))
        }
        
        return result
    }
    
    public func getRelationships(to entityId: String) async throws -> [EntityRelationship] {
        let query = relationships.filter(toEntityId == entityId)
        var result: [EntityRelationship] = []
        
        for row in try db.prepare(query) {
            result.append(try relationshipFromRow(row))
        }
        
        return result
    }
    
    public func getRelationships(ofType type: RelationshipType) async throws -> [EntityRelationship] {
        let query = relationships.filter(relationshipType == type.rawValue)
        var result: [EntityRelationship] = []
        
        for row in try db.prepare(query) {
            result.append(try relationshipFromRow(row))
        }
        
        return result
    }
    
    public func searchEntities(query: String, types: [EntityType]?) async throws -> [HomeEntity] {
        var sqlQuery = entities.filter(content.like("%\(query)%"))
        
        if let types = types {
            let typeStrings = types.map { $0.rawValue }
            sqlQuery = sqlQuery.filter(typeStrings.contains(entityType))
        }
        
        var result: [HomeEntity] = []
        for row in try db.prepare(sqlQuery) {
            result.append(try homeEntityFromRow(row))
        }
        
        return result
    }
    
    public func findPath(from: String, to: String) async throws -> [String] {
        // Simple breadth-first search implementation
        var queue: [(String, [String])] = [(from, [from])]
        var visited: Set<String> = [from]
        
        while !queue.isEmpty {
            let (currentEntity, path) = queue.removeFirst()
            
            if currentEntity == to {
                return path
            }
            
            // Get all outgoing relationships
            let outgoingRels = try await getRelationships(from: currentEntity)
            for rel in outgoingRels where rel.relationshipType == .connectsTo || rel.relationshipType == .partOf {
                let nextEntity = rel.toEntityId
                if !visited.contains(nextEntity) {
                    visited.insert(nextEntity)
                    queue.append((nextEntity, path + [nextEntity]))
                }
            }
        }
        
        return [] // No path found
    }
    
    public func storeBinaryContent(_ content: BinaryContent) async throws {
        try db.run(binaryContent.insert(or: .replace,
            binId <- content.id,
            binEntityId <- content.entityId,
            binEntityVersion <- content.entityVersion,
            binContentType <- content.contentType,
            binFileName <- content.fileName,
            binData <- content.data,
            binChecksum <- content.checksum,
            binCreatedAt <- Int64(content.createdAt.timeIntervalSince1970)
        ))
    }
    
    public func getBinaryContent(id: String) async throws -> BinaryContent? {
        let query = binaryContent.filter(binId == id)
        guard let row = try db.pluck(query) else { return nil }
        
        return BinaryContent(
            entityId: row[binEntityId],
            entityVersion: row[binEntityVersion],
            contentType: row[binContentType],
            fileName: row[binFileName],
            data: row[binData]
        )
    }
    
    public func deleteBinaryContent(id: String) async throws {
        try db.run(binaryContent.filter(binId == id).delete())
    }
    
    // Sync support methods
    public func getChangedEntities(since: Date, userId: String?) async throws -> [HomeEntity] {
        let timestamp = Int64(since.timeIntervalSince1970)
        var query = entities.filter(lastModified > timestamp)
        
        if let userId = userId {
            query = query.filter(self.userId == userId)
        }
        
        var result: [HomeEntity] = []
        for row in try db.prepare(query) {
            result.append(try homeEntityFromRow(row))
        }
        
        return result
    }
    
    public func getVectorClock() async throws -> [String: String] {
        // Implementation would depend on how vector clocks are stored
        // For now, return empty dictionary
        return [:]
    }
    
    public func updateVectorClock(_ clock: [String: String]) async throws {
        // Implementation would store vector clock in a metadata table
    }
    
    public func markSynced(entityId: String, version: String) async throws {
        // Mark entity as synced - could update a sync_status field
    }
    
    public func deleteEntity(id: String, version: String?) async throws {
        if let version = version {
            try db.run(entities.filter(entityId == id && entityVersion == version).delete())
        } else {
            try db.run(entities.filter(entityId == id).delete())
        }
    }
    
    public func deleteRelationship(id: String) async throws {
        try db.run(relationships.filter(relId == id).delete())
    }
    
    // Helper methods
    private func homeEntityFromRow(_ row: Row) throws -> HomeEntity {
        let parentVersionsData = Data(row[parentVersions].utf8)
        let contentData = Data(row[content].utf8)
        
        let parentVersionsArray = try JSONDecoder().decode([String].self, from: parentVersionsData)
        let contentDict = try JSONDecoder().decode([String: AnyCodable].self, from: contentData)
        
        var entity = HomeEntity(
            id: row[entityId],
            entityType: EntityType(rawValue: row[entityType]) ?? .device,
            content: contentDict,
            userId: row[userId],
            sourceType: SourceType(rawValue: row[sourceType]) ?? .manual,
            parentVersions: parentVersionsArray
        )
        
        // Override the generated values with stored ones
        entity.lastModified = Date(timeIntervalSince1970: TimeInterval(row[lastModified]))
        
        return entity
    }
    
    private func relationshipFromRow(_ row: Row) throws -> EntityRelationship {
        let propertiesData = Data(row[relProperties].utf8)
        let propertiesDict = try JSONDecoder().decode([String: AnyCodable].self, from: propertiesData)
        
        return EntityRelationship(
            fromEntityId: row[fromEntityId],
            toEntityId: row[toEntityId],
            relationshipType: RelationshipType(rawValue: row[relationshipType]) ?? .locatedIn,
            properties: propertiesDict,
            userId: row[relUserId]
        )
    }
}

extension Data {
    var sha256: String {
        let hash = SHA256.hash(data: self)
        return hash.compactMap { String(format: "%02x", $0) }.joined()
    }
}
```

## WildThing Graph Operations

### Graph Layer
```swift
// Sources/WildThing/Graph/HomeGraph.swift
import Foundation

public class HomeGraph {
    private var entities: [String: HomeEntity] = [:]
    private var relationshipsBySource: [String: [EntityRelationship]] = [:]
    private var relationshipsByTarget: [String: [EntityRelationship]] = [:]
    private let storage: WildThingStorage
    
    public init(storage: WildThingStorage) {
        self.storage = storage
    }
    
    public func loadFromStorage() async throws {
        // Load all latest versions of entities
        for entityType in EntityType.allCases {
            let typeEntities = try await storage.getEntities(ofType: entityType)
            for entity in typeEntities {
                entities[entity.id] = entity
            }
        }
        
        // Load and index relationships
        await indexRelationships()
    }
    
    private func indexRelationships() async {
        relationshipsBySource.removeAll()
        relationshipsByTarget.removeAll()
        
        // This would need to be implemented to load all relationships
        // For now, we'll build indices as relationships are accessed
    }
    
    public func entitiesInRoom(_ roomName: String) async throws -> [HomeEntity] {
        // Find room entity by name
        let room = entities.values.first { entity in
            entity.entityType == .room &&
            (entity.content["name"]?.value as? String) == roomName
        }
        
        guard let room = room else { return [] }
        
        // Get entities located in this room
        return try await storage.getEntitiesInRoom(room.id)
    }
    
    public func findDevice(byName name: String) async throws -> HomeEntity? {
        return entities.values.first { entity in
            entity.entityType == .device &&
            (entity.content["name"]?.value as? String) == name
        }
    }
    
    public func findRoomConnections(from roomName: String) async throws -> [String] {
        guard let room = entities.values.first(where: { entity in
            entity.entityType == .room &&
            (entity.content["name"]?.value as? String) == roomName
        }) else {
            return []
        }
        
        let connections = try await storage.getRelationships(from: room.id)
        return connections
            .filter { $0.relationshipType == .connectsTo }
            .compactMap { relationship in
                entities[relationship.toEntityId]?.content["name"]?.value as? String
            }
    }
    
    public func findPath(from fromRoom: String, to toRoom: String) async throws -> [String] {
        // Find room entities
        guard let fromRoomEntity = entities.values.first(where: { entity in
            entity.entityType == .room &&
            (entity.content["name"]?.value as? String) == fromRoom
        }),
        let toRoomEntity = entities.values.first(where: { entity in
            entity.entityType == .room &&
            (entity.content["name"]?.value as? String) == toRoom
        }) else {
            return []
        }
        
        let path = try await storage.findPath(from: fromRoomEntity.id, to: toRoomEntity.id)
        
        // Convert entity IDs back to room names
        return path.compactMap { entityId in
            entities[entityId]?.content["name"]?.value as? String
        }
    }
    
    public func semanticSearch(query: String, types: [EntityType]? = nil) async throws -> [SearchResult] {
        // Simple text-based search for now
        // Could be enhanced with embeddings/vector search
        let entities = try await storage.searchEntities(query: query, types: types)
        
        return entities.map { entity in
            let score = calculateRelevanceScore(entity: entity, query: query)
            return SearchResult(entity: entity, score: score)
        }
    }
    
    public func latestVersion(for entityId: String) async throws -> String {
        guard let entity = try await storage.getLatestVersion(for: entityId) else {
            throw WildThingError.entityNotFound(entityId)
        }
        return entity.version
    }
    
    private func calculateRelevanceScore(entity: HomeEntity, query: String) -> Double {
        let queryLower = query.lowercased()
        var score: Double = 0
        
        // Check name field
        if let name = entity.content["name"]?.value as? String {
            if name.lowercased().contains(queryLower) {
                score += 1.0
            }
        }
        
        // Check other content fields
        for (_, value) in entity.content {
            if let stringValue = value.value as? String,
               stringValue.lowercased().contains(queryLower) {
                score += 0.5
            }
        }
        
        return score
    }
}

public struct SearchResult {
    public let entity: HomeEntity
    public let score: Double
}

public enum WildThingError: Error {
    case entityNotFound(String)
    case invalidEntityType
    case storageError(Error)
    case syncError(String)
}
```

## WildThing MCP Server

### Core MCP Server
```swift
// Sources/WildThing/MCP/WildThingMCPServer.swift
import ModelContextProtocol
import Foundation

public class WildThingMCPServer: MCPServer {
    private let graph: HomeGraph
    private let storage: WildThingStorage
    
    public init(storage: WildThingStorage) {
        self.storage = storage
        self.graph = HomeGraph(storage: storage)
    }
    
    public func start() async throws {
        try await graph.loadFromStorage()
        // Register all MCP tools
        registerAllTools()
    }
    
    private func registerAllTools() {
        registerGraphQueryTools()
        registerEntityManagementTools()
        registerContentTools()
        registerSearchTools()
    }
    
    private func registerGraphQueryTools() {
        registerTool(MCPTool(
            name: "get_devices_in_room",
            description: "Get all devices located in a specific room",
            inputSchema: [
                "room_name": ["type": "string", "description": "Name of the room"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let roomName = arguments["room_name"] as? String else {
                throw MCPError.invalidArguments
            }
            
            let devices = try await self.graph.entitiesInRoom(roomName)
            let deviceList = devices.map { device in
                let name = device.content["name"]?.value as? String ?? "Unknown"
                let type = device.content["device_type"]?.value as? String ?? "Unknown type"
                return "• \(name) (\(type))"
            }.joined(separator: "\n")
            
            if devices.isEmpty {
                return MCPToolResponse(content: [.text("No devices found in '\(roomName)'")])
            } else {
                return MCPToolResponse(content: [.text("Devices in \(roomName):\n\(deviceList)")])
            }
        })
        
        registerTool(MCPTool(
            name: "find_device_controls",
            description: "Get available controls and current state for a device",
            inputSchema: [
                "device_name": ["type": "string", "description": "Name of the device"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let deviceName = arguments["device_name"] as? String else {
                throw MCPError.invalidArguments
            }
            
            let device = try await self.graph.findDevice(byName: deviceName)
            guard let device = device else {
                return MCPToolResponse(content: [.text("Device '\(deviceName)' not found")])
            }
            
            // Get HomeKit services and characteristics
            let controls = device.content["services"]?.value as? [[String: Any]] ?? []
            let controlList = controls.compactMap { service in
                service["characteristics"] as? [[String: Any]]
            }.flatMap { $0 }.compactMap { char in
                char["type"] as? String
            }.joined(separator: ", ")
            
            return MCPToolResponse(content: [
                .text("Available controls for \(deviceName): \(controlList)")
            ])
        })
        
        registerTool(MCPTool(
            name: "get_room_connections",
            description: "Find doors and passages between rooms",
            inputSchema: [
                "from_room": ["type": "string", "description": "Starting room name"],
                "to_room": ["type": "string", "description": "Destination room name", "required": false]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let fromRoom = arguments["from_room"] as? String else {
                throw MCPError.invalidArguments
            }
            
            if let toRoom = arguments["to_room"] as? String {
                let path = try await self.graph.findPath(from: fromRoom, to: toRoom)
                if path.isEmpty {
                    return MCPToolResponse(content: [.text("No path found from '\(fromRoom)' to '\(toRoom)'")])
                } else {
                    return MCPToolResponse(content: [.text("Path: \(path.joined(separator: " → "))")])
                }
            } else {
                // List all connections from this room
                let connections = try await self.graph.findRoomConnections(from: fromRoom)
                
                if connections.isEmpty {
                    return MCPToolResponse(content: [.text("No connections found from '\(fromRoom)'")])
                } else {
                    return MCPToolResponse(content: [.text("Rooms connected to '\(fromRoom)': \(connections.joined(separator: ", "))")])
                }
            }
        })
    }
    
    private func registerEntityManagementTools() {
        registerTool(MCPTool(
            name: "create_entity",
            description: "Create a new entity in the home graph",
            inputSchema: [
                "entity_type": ["type": "string", "enum": EntityType.allCases.map(\.rawValue)],
                "name": ["type": "string", "description": "Name of the entity"],
                "properties": ["type": "object", "description": "Additional properties for the entity"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let entityTypeString = arguments["entity_type"] as? String,
                  let entityType = EntityType(rawValue: entityTypeString),
                  let name = arguments["name"] as? String else {
                throw MCPError.invalidArguments
            }
            
            var content: [String: AnyCodable] = ["name": AnyCodable(name)]
            
            if let properties = arguments["properties"] as? [String: Any] {
                for (key, value) in properties {
                    content[key] = AnyCodable(value)
                }
            }
            
            let entity = HomeEntity(
                entityType: entityType,
                content: content,
                userId: "default" // This would come from authentication
            )
            
            try await self.storage.store(entity: entity)
            
            return MCPToolResponse(content: [.text("Created \(entityType.rawValue): \(name) (ID: \(entity.id))")])
        })
        
        registerTool(MCPTool(
            name: "create_relationship",
            description: "Create a relationship between two entities",
            inputSchema: [
                "from_entity_id": ["type": "string", "description": "Source entity ID"],
                "to_entity_id": ["type": "string", "description": "Target entity ID"],
                "relationship_type": ["type": "string", "enum": RelationshipType.allCases.map(\.rawValue)],
                "properties": ["type": "object", "description": "Additional relationship properties"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let fromEntityId = arguments["from_entity_id"] as? String,
                  let toEntityId = arguments["to_entity_id"] as? String,
                  let relationshipTypeString = arguments["relationship_type"] as? String,
                  let relationshipType = RelationshipType(rawValue: relationshipTypeString) else {
                throw MCPError.invalidArguments
            }
            
            var properties: [String: AnyCodable] = [:]
            if let props = arguments["properties"] as? [String: Any] {
                for (key, value) in props {
                    properties[key] = AnyCodable(value)
                }
            }
            
            let relationship = EntityRelationship(
                fromEntityId: fromEntityId,
                toEntityId: toEntityId,
                relationshipType: relationshipType,
                properties: properties,
                userId: "default"
            )
            
            try await self.storage.store(relationship: relationship)
            
            return MCPToolResponse(content: [.text("Created \(relationshipType.rawValue) relationship between \(fromEntityId) and \(toEntityId)")])
        })
    }
    
    private func registerContentTools() {
        registerTool(MCPTool(
            name: "add_device_manual",
            description: "Add documentation for a device",
            inputSchema: [
                "device_id": ["type": "string", "description": "Device entity ID"],
                "title": ["type": "string", "description": "Manual title"],
                "content": ["type": "string", "description": "Manual content"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let deviceId = arguments["device_id"] as? String,
                  let manualContent = arguments["content"] as? String else {
                throw MCPError.invalidArguments
            }
            
            let manual = HomeEntity(
                entityType: .manual,
                content: [
                    "title": AnyCodable(arguments["title"] as? String ?? "Device Manual"),
                    "content": AnyCodable(manualContent),
                    "device_id": AnyCodable(deviceId)
                ],
                userId: "default"
            )
            
            try await self.storage.store(entity: manual)
            
            // Create relationship
            let relationship = EntityRelationship(
                fromEntityId: deviceId,
                toEntityId: manual.id,
                relationshipType: .documentedBy,
                userId: "default"
            )
            
            try await self.storage.store(relationship: relationship)
            
            return MCPToolResponse(content: [.text("Added manual for device \(deviceId)")])
        })
        
        registerTool(MCPTool(
            name: "create_procedure",
            description: "Create a step-by-step procedure",
            inputSchema: [
                "title": ["type": "string", "description": "Procedure title"],
                "steps": ["type": "array", "items": ["type": "string"], "description": "List of steps"],
                "description": ["type": "string", "description": "Procedure description"],
                "category": ["type": "string", "description": "Procedure category"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let title = arguments["title"] as? String,
                  let steps = arguments["steps"] as? [String] else {
                throw MCPError.invalidArguments
            }
            
            let procedure = HomeEntity(
                entityType: .procedure,
                content: [
                    "title": AnyCodable(title),
                    "description": AnyCodable(arguments["description"] as? String ?? ""),
                    "steps": AnyCodable(steps),
                    "category": AnyCodable(arguments["category"] as? String ?? "general")
                ],
                userId: "default"
            )
            
            try await self.storage.store(entity: procedure)
            
            return MCPToolResponse(content: [.text("Created procedure: \(title) (ID: \(procedure.id))")])
        })
        
        registerTool(MCPTool(
            name: "add_device_image",
            description: "Add an image for a device",
            inputSchema: [
                "device_id": ["type": "string", "description": "Device entity ID"],
                "image_data": ["type": "string", "description": "Base64 encoded image data"],
                "file_name": ["type": "string", "description": "Image file name"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let deviceId = arguments["device_id"] as? String,
                  let imageDataString = arguments["image_data"] as? String,
                  let imageData = Data(base64Encoded: imageDataString) else {
                throw MCPError.invalidArguments
            }
            
            let binaryContent = BinaryContent(
                entityId: deviceId,
                entityVersion: try await self.graph.latestVersion(for: deviceId),
                contentType: "image/jpeg",
                fileName: arguments["file_name"] as? String,
                data: imageData
            )
            
            try await self.storage.storeBinaryContent(binaryContent)
            
            return MCPToolResponse(content: [.text("Added image for device \(deviceId)")])
        })
    }
    
    private func registerSearchTools() {
        registerTool(MCPTool(
            name: "search_entities",
            description: "Search for entities by name or content",
            inputSchema: [
                "query": ["type": "string", "description": "Search query"],
                "entity_types": ["type": "array", "items": ["type": "string"], "description": "Filter by entity types"]
            ]
        ) { [weak self] arguments in
            guard let self = self,
                  let query = arguments["query"] as? String else {
                throw MCPError.invalidArguments
            }
            
            let entityTypes: [EntityType]?
            if let typeStrings = arguments["entity_types"] as? [String] {
                entityTypes = typeStrings.compactMap { EntityType(rawValue: $0) }
            } else {
                entityTypes = nil
            }
            
            let results = try await self.graph.semanticSearch(query: query, types: entityTypes)
            
            if results.isEmpty {
                return MCPToolResponse(content: [.text("No results found for '\(query)'")])
            }
            
            let resultList = results.map { result in
                let name = result.entity.content["name"]?.value as? String ?? result.entity.id
                return "• \(result.entity.entityType.rawValue): \(name) (score: \(String(format: "%.2f", result.score)))"
            }.joined(separator: "\n")
            
            return MCPToolResponse(content: [.text("Search results for '\(query)':\n\(resultList)")])
        })
    }
    
    // Helper methods
    private func getCurrentUserId() -> String {
        return "default" // This would be implemented with proper authentication
    }
    
    private func generateVersion() -> String {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        return "\(timestamp)-\(getCurrentUserId())"
    }
}
```

## Inbetweenies Sync Protocol

### Protocol Specification
The **Inbetweenies** protocol handles distributed synchronization and all shared models between WildThing (Swift) and Blowing-off (Python) clients and FunkyGibbon (Python) servers.

```json
// Inbetweenies/schemas/sync-request.json
{
  "type": "object",
  "properties": {
    "protocol_version": {"type": "string", "const": "inbetweenies-v1"},
    "device_id": {"type": "string"},
    "user_id": {"type": "string"},
    "vector_clock": {
      "type": "object",
      "additionalProperties": {"type": "string"}
    },
    "changes": {
      "type": "array",
      "items": {"$ref": "#/definitions/EntityChange"}
    }
  },
  "required": ["protocol_version", "device_id", "user_id", "vector_clock", "changes"],
  "definitions": {
    "EntityChange": {
      "type": "object",
      "properties": {
        "change_type": {"type": "string", "enum": ["create", "update", "delete"]},
        "entity_id": {"type": "string"},
        "entity_version": {"type": "string"},
        "entity_type": {"type": "string"},
        "content": {"type": "object"},
        "timestamp": {"type": "string", "format": "date-time"}
      },
      "required": ["change_type", "entity_id", "entity_version", "timestamp"]
    }
  }
}
```


## FunkyGibbon Python Package

### Python Package Structure
```python
# FunkyGibbon/pyproject.toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "funkygibbon"
version = "0.1.0"
description = "FunkyGibbon - Python backend for The Goodies smart home knowledge graph"
authors = [{name = "Your Name", email = "your.email@example.com"}]
license = {text = "MIT"}
requires-python = ">=3.9"
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "pydantic>=2.5.0",
    "redis>=5.0.0",
    "python-multipart>=0.0.6"
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "isort>=5.12.0",
    "mypy>=1.6.0"
]

[project.scripts]
funkygibbon-server = "funkygibbon.cli:main"
```

### Core Python Models

TODO: this needs to be modified to fit in with the Inbetweenies model packaging that has already been implemented, but with new capabilities added

```python
# funkygibbon/core/models.py
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid

class EntityType(str, Enum):
    HOME = "home"
    ROOM = "room"
    DEVICE = "device"
    ACCESSORY = "accessory"
    SERVICE = "service"
    ZONE = "zone"
    DOOR = "door"
    WINDOW = "window"
    PROCEDURE = "procedure"
    MANUAL = "manual"
    NOTE = "note"
    SCHEDULE = "schedule"
    AUTOMATION = "automation"

class SourceType(str, Enum):
    HOMEKIT = "homekit"
    MATTER = "matter"
    MANUAL = "manual"
    IMPORTED = "imported"
    GENERATED = "generated"

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

class HomeEntity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str = Field(default_factory=lambda: f"{datetime.utcnow().isoformat()}Z-default")
    entity_type: EntityType
    parent_versions: List[str] = Field(default_factory=list)
    content: Dict[str, Any]
    user_id: str
    source_type: SourceType = SourceType.MANUAL
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_modified: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }

class EntityRelationship(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_entity_id: str
    to_entity_id: str
    relationship_type: RelationshipType
    properties: Dict[str, Any] = Field(default_factory=dict)
    user_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class InbetweeniesRequest(BaseModel):
    protocol_version: str = "inbetweenies-v1"
    device_id: str
    user_id: str
    vector_clock: Dict[str, str]
    changes: List[Dict[str, Any]]

class InbetweeniesResponse(BaseModel):
    changes: List[Dict[str, Any]]
    vector_clock: Dict[str, str]
    conflicts: List[str] = Field(default_factory=list)
```

# sync services
TODO: sync service with last write wins has already been implemented, the initial idea to use vector clocks and support large scale was abandoned as unneccesary
TODO: immutable versioned entities will be used, so writes create a new version rather than an update. Sync obtains all versions so that history of changes is available to the app.



## Development Roadmap

TODO: this section has been updated to reflect the desired project phases

### Phase 1: The-Goodies Foundation (COMPLETED)
- [ ] Python package with HomeKit based data models and Inbetweenies protocol
- [ ] SQLite Storage implementation
- [ ] FunkyGibbon Python backend and Blowing-off front end with shared models
- [ ] Comprehensive test suite for both packages

### Phase 2: Graph Operations in Python on server (2 weeks)
- [ ] In-memory graph with relationship indexing in Python
- [ ] Path finding and traversal algorithms
- [ ] Search and query optimization
- [ ] MCPServer interface with tools and resources
- [ ] New Oook CLI tool for FunkyGibbon development and testing directly against the API

### Phase 3: Inbetweenies Protocol in Python (2 weeks)
- [ ] Inbetweenies protocol specification and JSON schemas for immutable versioned entities
- [ ] InbetweeniesServer implementation in FunkyGibbon
- [ ] InbetweeniesClient Python implementation in Blowing-off
- [ ] Basic sync functionality with last-write-wins conflict resolution

### Phase 4: Swift Implementation (2 weeks)
- [ ] InbetweeniesClient Swift implementation in WildThing
- [ ] HomeKit integration module (iOS/macOS)
- [ ] Matter/Thread support investigation
- [ ] Binary content storage (images, PDFs)
- [ ] Integrate into c11s-house-ios project

## Success Metrics

### Functionality
- [ ] All entity types and relationships supported
- [ ] Fast graph queries (< 10ms for typical operations)
- [ ] Reliable Inbetweenies sync between WildThing and FunkyGibbon
- [ ] Comprehensive test coverage (> 90%) for both packages

### Usability
- [ ] Simple integration of WildThing into existing iOS/macOS projects
- [ ] Clear documentation for WildThing, FunkyGibbon, and Inbetweenies protocol
- [ ] Intuitive Oook (server) and Blowing-off (client) CLI tools for development
- [ ] Helpful error messages and debugging across all components

### Performance
- [ ] The-Goodies handles 1000 entities, 10 user clients, and 2 houses efficiently
- [ ] Memory usage < 10MB for typical home graphs, and < 500MB storage for photos
- [ ] Inbetweenies sync operations complete in < 1 second over local networks
- [ ] Works reliably on iOS devices with FunkyGibbon backend

## Technical Dependencies

### WildThing Dependencies
```swift
// WildThing/Package.swift
dependencies: [
    .package(url: "https://github.com/modelcontextprotocol/swift-sdk.git", from: "0.9.0"),
    .package(url: "https://github.com/apple/swift-log.git", from: "1.0.0"),
    .package(url: "https://github.com/stephencelis/SQLite.swift.git", from: "0.14.1"),
    .package(url: "https://github.com/apple/swift-crypto.git", from: "2.0.0")
]
```

### FunkyGibbon Dependencies
```python
# FunkyGibbon/requirements.txt
fastapi>=0.104.0
uvicorn>=0.24.0
sqlalchemy>=2.0.0
asyncpg>=0.29.0
pydantic>=2.5.0
redis>=5.0.0
```

## Risk Mitigation

### Technical Risks
- **MCP Specification Changes**: Use official Swift SDK as API model, implement version compatibility
- **iOS Memory Constraints**: Implement intelligent caching, lazy loading
- **Data Corruption**: Implement checksums, transaction logging

### Business Risks
- **User Adoption**: Focus on clear value proposition, smooth onboarding
- **Scaling Costs**: Design for efficient resource usage
- **Privacy Concerns**: Local-first design, clear data policies
- **Competition**: Rapid iteration, unique AI features



---

