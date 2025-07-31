# Phase 4: Swift/WildThing Implementation Plan

## Overview
This document outlines the implementation plan for WildThing, the Swift package that provides native iOS/macOS/watchOS/tvOS support for The Goodies smart home knowledge graph system.

## Goals

1. **Native Swift Implementation**: Pure Swift code for Apple platforms
2. **HomeKit Integration**: Seamless data import from HomeKit
3. **Local-First Design**: Full offline functionality
4. **Cross-Platform**: Support iOS, macOS, watchOS, tvOS
5. **Developer-Friendly**: Easy integration into existing apps

## Package Structure

### Swift Package Definition
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
            targets: ["WildThing"]),
        .library(
            name: "WildThingHomeKit",
            targets: ["WildThingHomeKit"]),
        .executable(
            name: "wildthing-cli",
            targets: ["WildThingCLI"])
    ],
    dependencies: [
        .package(url: "https://github.com/stephencelis/SQLite.swift.git", from: "0.14.1"),
        .package(url: "https://github.com/apple/swift-log.git", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-crypto.git", from: "2.0.0"),
        .package(url: "https://github.com/apple/swift-argument-parser.git", from: "1.0.0"),
        .package(url: "https://github.com/swift-server/async-http-client.git", from: "1.19.0")
    ],
    targets: [
        .target(
            name: "WildThing",
            dependencies: [
                .product(name: "SQLite", package: "SQLite.swift"),
                .product(name: "Logging", package: "swift-log"),
                .product(name: "Crypto", package: "swift-crypto"),
                .product(name: "AsyncHTTPClient", package: "async-http-client")
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
            dependencies: ["WildThing", "WildThingHomeKit"]
        )
    ]
)
```

## Core Data Models

### Entity Model
```swift
// Sources/WildThing/Models/Entity.swift
import Foundation

public enum EntityType: String, CaseIterable, Codable {
    case home = "home"
    case room = "room"
    case device = "device"
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

public struct Entity: Codable, Identifiable {
    public let id: String
    public let version: String
    public let entityType: EntityType
    public let parentVersions: [String]
    public let content: [String: AnyJSON]
    public let userId: String
    public let sourceType: SourceType
    public let createdAt: Date
    public let lastModified: Date
    
    public init(
        id: String = UUID().uuidString,
        entityType: EntityType,
        content: [String: AnyJSON],
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
    
    static func generateVersion(userId: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return "\(formatter.string(from: Date()))-\(userId)"
    }
}
```

### Type-Erased JSON Support
```swift
// Type-erased JSON wrapper
public enum AnyJSON: Codable {
    case null
    case bool(Bool)
    case int(Int)
    case double(Double)
    case string(String)
    case array([AnyJSON])
    case object([String: AnyJSON])
    
    public init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if container.decodeNil() {
            self = .null
        } else if let bool = try? container.decode(Bool.self) {
            self = .bool(bool)
        } else if let int = try? container.decode(Int.self) {
            self = .int(int)
        } else if let double = try? container.decode(Double.self) {
            self = .double(double)
        } else if let string = try? container.decode(String.self) {
            self = .string(string)
        } else if let array = try? container.decode([AnyJSON].self) {
            self = .array(array)
        } else if let object = try? container.decode([String: AnyJSON].self) {
            self = .object(object)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unable to decode AnyJSON")
        }
    }
    
    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch self {
        case .null:
            try container.encodeNil()
        case .bool(let value):
            try container.encode(value)
        case .int(let value):
            try container.encode(value)
        case .double(let value):
            try container.encode(value)
        case .string(let value):
            try container.encode(value)
        case .array(let value):
            try container.encode(value)
        case .object(let value):
            try container.encode(value)
        }
    }
}
```

## Storage Implementation

### SQLite Storage Layer
```swift
// Sources/WildThing/Storage/SQLiteStorage.swift
import SQLite
import Foundation

public class SQLiteStorage: StorageProtocol {
    private let db: Connection
    
    // Table definitions
    private let entities = Table("entities")
    private let id = Expression<String>("id")
    private let version = Expression<String>("version")
    private let entityType = Expression<String>("entity_type")
    private let parentVersions = Expression<String>("parent_versions")
    private let content = Expression<String>("content")
    private let userId = Expression<String>("user_id")
    private let sourceType = Expression<String>("source_type")
    private let createdAt = Expression<Int64>("created_at")
    private let lastModified = Expression<Int64>("last_modified")
    
    public init(path: String) throws {
        db = try Connection(path)
        try createTables()
    }
    
    private func createTables() throws {
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
        
        // Create indices for performance
        try db.run(entities.createIndex([entityType], ifNotExists: true))
        try db.run(entities.createIndex([lastModified], ifNotExists: true))
    }
    
    public func store(entity: Entity) async throws {
        let encoder = JSONEncoder()
        let contentData = try encoder.encode(entity.content)
        let parentVersionsData = try encoder.encode(entity.parentVersions)
        
        try db.run(entities.insert(or: .replace,
            id <- entity.id,
            version <- entity.version,
            entityType <- entity.entityType.rawValue,
            parentVersions <- String(data: parentVersionsData, encoding: .utf8)!,
            content <- String(data: contentData, encoding: .utf8)!,
            userId <- entity.userId,
            sourceType <- entity.sourceType.rawValue,
            createdAt <- Int64(entity.createdAt.timeIntervalSince1970),
            lastModified <- Int64(entity.lastModified.timeIntervalSince1970)
        ))
    }
}
```

## HomeKit Integration

### HomeKit Import Module
```swift
// Sources/WildThingHomeKit/HomeKitImporter.swift
import HomeKit
import WildThing

@available(iOS 13.0, macOS 10.15, *)
public class HomeKitImporter {
    private let homeManager: HMHomeManager
    private let storage: StorageProtocol
    
    public init(storage: StorageProtocol) {
        self.homeManager = HMHomeManager()
        self.storage = storage
    }
    
    public func importHomes() async throws {
        // Request HomeKit access
        guard homeManager.authorizationStatus == .authorized else {
            throw HomeKitError.notAuthorized
        }
        
        for home in homeManager.homes {
            // Convert HMHome to Entity
            let homeEntity = Entity(
                id: home.uniqueIdentifier.uuidString,
                entityType: .home,
                content: [
                    "name": .string(home.name),
                    "isPrimary": .bool(home.isPrimary)
                ],
                userId: "homekit-import",
                sourceType: .homekit
            )
            
            try await storage.store(entity: homeEntity)
            
            // Import rooms
            for room in home.rooms {
                try await importRoom(room, homeId: home.uniqueIdentifier.uuidString)
            }
            
            // Import accessories
            for accessory in home.accessories {
                try await importAccessory(accessory, homeId: home.uniqueIdentifier.uuidString)
            }
        }
    }
    
    private func importRoom(_ room: HMRoom, homeId: String) async throws {
        let roomEntity = Entity(
            id: room.uniqueIdentifier.uuidString,
            entityType: .room,
            content: [
                "name": .string(room.name),
                "homeId": .string(homeId)
            ],
            userId: "homekit-import",
            sourceType: .homekit
        )
        
        try await storage.store(entity: roomEntity)
    }
    
    private func importAccessory(_ accessory: HMAccessory, homeId: String) async throws {
        let deviceEntity = Entity(
            id: accessory.uniqueIdentifier.uuidString,
            entityType: .device,
            content: [
                "name": .string(accessory.name),
                "manufacturer": .string(accessory.manufacturer ?? "Unknown"),
                "model": .string(accessory.model ?? "Unknown"),
                "isReachable": .bool(accessory.isReachable),
                "homeId": .string(homeId),
                "roomId": .string(accessory.room?.uniqueIdentifier.uuidString ?? "")
            ],
            userId: "homekit-import",
            sourceType: .homekit
        )
        
        try await storage.store(entity: deviceEntity)
    }
}
```

## Inbetweenies Sync Client

### Sync Client Implementation
```swift
// Sources/WildThing/Sync/InbetweeniesClient.swift
import Foundation
import AsyncHTTPClient

public class InbetweeniesClient {
    private let serverURL: String
    private let httpClient: HTTPClient
    private let storage: StorageProtocol
    
    public init(serverURL: String, storage: StorageProtocol) {
        self.serverURL = serverURL
        self.storage = storage
        self.httpClient = HTTPClient(eventLoopGroupProvider: .createNew)
    }
    
    public func sync() async throws {
        // Get local changes
        let lastSync = try await storage.getLastSyncTime()
        let localChanges = try await storage.getChangedEntities(since: lastSync)
        
        // Prepare sync request
        let syncRequest = InbetweeniesRequest(
            protocolVersion: "inbetweenies-v2",
            deviceId: getDeviceId(),
            userId: getCurrentUserId(),
            vectorClock: try await storage.getVectorClock(),
            changes: localChanges.map { entity in
                [
                    "change_type": "create",
                    "entity": entity.toDictionary()
                ]
            }
        )
        
        // Send sync request
        let response = try await sendSyncRequest(syncRequest)
        
        // Apply remote changes
        for change in response.changes {
            if let entity = Entity.fromDictionary(change["entity"] as? [String: Any]) {
                try await storage.store(entity: entity)
            }
        }
        
        // Update sync metadata
        try await storage.updateVectorClock(response.vectorClock)
        try await storage.setLastSyncTime(Date())
    }
}
```

## Graph Operations

### Graph Index
```swift
// Sources/WildThing/Graph/GraphIndex.swift
import Foundation

public class GraphIndex {
    private var entities: [String: Entity] = [:]
    private var relationshipsBySource: [String: [EntityRelationship]] = [:]
    private var relationshipsByTarget: [String: [EntityRelationship]] = [:]
    
    public func loadFromStorage(_ storage: StorageProtocol) async throws {
        // Load all entities
        for entityType in EntityType.allCases {
            let typeEntities = try await storage.getEntities(ofType: entityType)
            for entity in typeEntities {
                entities[entity.id] = entity
            }
        }
        
        // Load relationships
        let relationships = try await storage.getAllRelationships()
        for relationship in relationships {
            relationshipsBySource[relationship.fromEntityId, default: []].append(relationship)
            relationshipsByTarget[relationship.toEntityId, default: []].append(relationship)
        }
    }
    
    public func findPath(from: String, to: String) -> [String] {
        // BFS implementation
        var queue: [(String, [String])] = [(from, [from])]
        var visited: Set<String> = [from]
        
        while !queue.isEmpty {
            let (current, path) = queue.removeFirst()
            
            if current == to {
                return path
            }
            
            let outgoing = relationshipsBySource[current] ?? []
            for rel in outgoing {
                let next = rel.toEntityId
                if !visited.contains(next) {
                    visited.insert(next)
                    queue.append((next, path + [next]))
                }
            }
        }
        
        return []
    }
    
    public func entitiesInRoom(_ roomId: String) -> [Entity] {
        let incoming = relationshipsByTarget[roomId] ?? []
        return incoming
            .filter { $0.relationshipType == .locatedIn }
            .compactMap { entities[$0.fromEntityId] }
            .filter { $0.entityType == .device }
    }
}
```

## Search Implementation

### Search Engine
```swift
// Sources/WildThing/Search/SearchEngine.swift
import Foundation

public struct SearchResult {
    public let entity: Entity
    public let score: Double
    public let highlights: [String]
}

public class SearchEngine {
    private let index: GraphIndex
    
    public init(index: GraphIndex) {
        self.index = index
    }
    
    public func search(
        query: String,
        entityTypes: [EntityType]? = nil,
        limit: Int = 10
    ) -> [SearchResult] {
        let lowercaseQuery = query.lowercased()
        var results: [SearchResult] = []
        
        for entity in index.allEntities() {
            // Filter by type if specified
            if let types = entityTypes, !types.contains(entity.entityType) {
                continue
            }
            
            let score = calculateScore(entity: entity, query: lowercaseQuery)
            if score > 0 {
                results.append(SearchResult(
                    entity: entity,
                    score: score,
                    highlights: findHighlights(entity: entity, query: lowercaseQuery)
                ))
            }
        }
        
        return results
            .sorted { $0.score > $1.score }
            .prefix(limit)
            .map { $0 }
    }
    
    private func calculateScore(entity: Entity, query: String) -> Double {
        var score: Double = 0
        
        // Check name field
        if case .string(let name) = entity.content["name"],
           name.lowercased().contains(query) {
            score += name.lowercased() == query ? 2.0 : 1.0
        }
        
        // Check other fields
        for (_, value) in entity.content {
            if let text = extractText(from: value),
               text.lowercased().contains(query) {
                score += 0.5
            }
        }
        
        return score
    }
}
```

## Platform Integration

### iOS Integration
```swift
// Sources/WildThing/Platform/iOSIntegration.swift
#if os(iOS)
import UIKit

public extension Entity {
    /// Create a shareable activity for this entity
    func createUserActivity() -> NSUserActivity {
        let activity = NSUserActivity(activityType: "com.thegoodies.wildthing.viewEntity")
        activity.title = self.name
        activity.userInfo = ["entityId": self.id]
        activity.isEligibleForSearch = true
        activity.isEligibleForHandoff = true
        return activity
    }
}

public class WildThingViewController: UIViewController {
    private let graph: GraphIndex
    
    public init(graph: GraphIndex) {
        self.graph = graph
        super.init(nibName: nil, bundle: nil)
    }
    
    // UI implementation
}
#endif
```

## API Design

### Simple Integration
```swift
// Example app integration
import WildThing
import WildThingHomeKit

class SmartHomeApp {
    let wildThing: WildThingManager
    
    init() async throws {
        // Initialize with default storage
        wildThing = try await WildThingManager()
        
        // Import HomeKit data
        try await wildThing.importFromHomeKit()
        
        // Start sync if server configured
        if let serverURL = UserDefaults.standard.string(forKey: "syncServerURL") {
            try await wildThing.startSync(serverURL: serverURL)
        }
    }
    
    func findDevice(named name: String) async -> Entity? {
        return await wildThing.search(query: name, types: [.device]).first?.entity
    }
}
```

## Testing Strategy

### Unit Tests
```swift
// Tests/WildThingTests/EntityTests.swift
import XCTest
@testable import WildThing

class EntityTests: XCTestCase {
    func testEntityCreation() {
        let entity = Entity(
            entityType: .device,
            content: ["name": .string("Test Device")],
            userId: "test-user"
        )
        
        XCTAssertEqual(entity.entityType, .device)
        XCTAssertEqual(entity.content["name"], .string("Test Device"))
        XCTAssertNotNil(entity.version)
    }
    
    func testVersionGeneration() {
        let entity1 = Entity(entityType: .room, content: [:], userId: "user1")
        let entity2 = Entity(entityType: .room, content: [:], userId: "user1")
        
        XCTAssertNotEqual(entity1.version, entity2.version)
    }
}
```

### Integration Tests
```swift
// Tests/WildThingTests/IntegrationTests.swift
import XCTest
@testable import WildThing
@testable import WildThingHomeKit

class IntegrationTests: XCTestCase {
    func testHomeKitImport() async throws {
        let storage = try SQLiteStorage(path: ":memory:")
        let importer = HomeKitImporter(storage: storage)
        
        try await importer.importHomes()
        
        let homes = try await storage.getEntities(ofType: .home)
        XCTAssertFalse(homes.isEmpty)
    }
}
```

## Performance Optimization

### Memory Management
- Lazy loading of entities
- LRU cache for frequently accessed data
- Background cleanup of old versions

### Query Optimization
- Pre-computed indices for common queries
- Denormalized views for performance
- Batch operations for bulk updates

## Security Considerations

### Data Encryption
```swift
// Sources/WildThing/Security/Encryption.swift
import CryptoKit

extension Entity {
    func encrypted(using key: SymmetricKey) throws -> Entity {
        let encoder = JSONEncoder()
        let data = try encoder.encode(content)
        let sealedBox = try AES.GCM.seal(data, using: key)
        
        var copy = self
        copy.content = ["encrypted": .string(sealedBox.combined.base64EncodedString())]
        return copy
    }
}
```

### Keychain Integration
- Store sync credentials securely
- Biometric authentication for sensitive operations
- Encrypted local storage option

## Success Criteria

1. **Feature Parity**: All graph operations available in Swift
2. **Performance**: <5ms query time for common operations
3. **Reliability**: Robust offline operation and sync
4. **Developer Experience**: Clear API and documentation
5. **Platform Integration**: Native feel on all Apple platforms

## Implementation Timeline

### Week 1: Core Foundation
- **Days 1-2**: Implement data models and storage
- **Days 3-4**: Build SQLite persistence layer
- **Day 5**: Create HomeKit integration

### Week 2: Advanced Features
- **Days 1-2**: Implement Inbetweenies sync client
- **Days 3-4**: Build graph operations and indexing
- **Day 5**: Add search functionality
- **Days 6-7**: Platform-specific integrations

## Next Steps

Upon completion of Phase 4:
1. Publish to Swift Package Index
2. Create sample apps for each platform
3. Performance profiling and optimization
4. Community feedback and iteration
5. Consider additional integrations (Matter, Thread)