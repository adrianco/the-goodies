# WildThing Interface Design for c11s-ios-house

## Overview

This document defines the interface design for c11s-ios-house to consume WildThing MCP service. It covers the API contracts, protocol definitions, and integration patterns that ensure a clean, maintainable, and extensible interface between the iOS app and the WildThing knowledge graph.

## Core Interface Principles

1. **Protocol-Oriented Design**: All interfaces defined as Swift protocols
2. **Async/Await**: Modern concurrency throughout
3. **Type Safety**: Strong typing with minimal use of `Any`
4. **Error Propagation**: Comprehensive error handling
5. **Testability**: All interfaces mockable for testing

## Primary Interface Protocols

### 1. WildThingServiceProtocol

The main entry point for all WildThing operations:

```swift
public protocol WildThingServiceProtocol: AnyObject {
    // MARK: - Initialization
    func initialize() async throws
    func shutdown() async throws
    
    // MARK: - Service Access
    var storage: WildThingStorageProtocol { get }
    var graph: HomeGraphProtocol { get }
    var mcp: MCPServerProtocol { get }
    var sync: SyncServiceProtocol? { get }
    var homeKit: HomeKitBridgeProtocol? { get }
    
    // MARK: - Status
    var isInitialized: Bool { get }
    var connectionStatus: ConnectionStatus { get }
}
```

### 2. WildThingStorageProtocol

Abstraction over the storage layer:

```swift
public protocol WildThingStorageProtocol: AnyObject {
    // MARK: - Entity Operations
    func store(entity: HomeEntity) async throws
    func getEntity(id: String) async throws -> HomeEntity?
    func getEntities(ofType type: EntityType, 
                    limit: Int?, 
                    offset: Int?) async throws -> [HomeEntity]
    func updateEntity(id: String, 
                     updates: [String: Any]) async throws -> HomeEntity
    func deleteEntity(id: String) async throws
    
    // MARK: - Batch Operations
    func batchStore(entities: [HomeEntity]) async throws
    func batchDelete(ids: [String]) async throws
    
    // MARK: - Querying
    func query(predicate: EntityPredicate, 
              sort: SortDescriptor?, 
              limit: Int?) async throws -> [HomeEntity]
}
```

### 3. HomeGraphProtocol

Graph operations interface:

```swift
public protocol HomeGraphProtocol: AnyObject {
    // MARK: - Graph Queries
    func entitiesInRoom(_ roomName: String,
                       types: [EntityType]?) async throws -> [HomeEntity]
    
    func findDevice(byName name: String) async throws -> HomeEntity?
    
    func findPath(from: String, to: String) async throws -> Path?
    
    func relatedEntities(to entityId: String,
                        relationshipTypes: [RelationshipType]?,
                        depth: Int) async throws -> [HomeEntity]
    
    // MARK: - Search
    func search(query: String,
                types: [EntityType]?,
                limit: Int) async throws -> [SearchResult]
    
    // MARK: - Analytics
    func analyze(entityId: String) async throws -> EntityAnalytics
}
```

### 4. MCPServerProtocol

MCP tool execution interface:

```swift
public protocol MCPServerProtocol: AnyObject {
    // MARK: - Tool Execution
    func executeTool(name: String, 
                    arguments: [String: Any]) async throws -> MCPToolResponse
    
    func executeToolBatch(requests: [MCPToolRequest]) async throws -> [MCPToolResponse]
    
    // MARK: - Tool Discovery
    func availableTools() -> [MCPToolInfo]
    func toolInfo(name: String) -> MCPToolInfo?
    
    // MARK: - Direct Handlers
    func handleRequest(_ request: MCPRequest) async throws -> MCPResponse
}
```

## Data Transfer Objects (DTOs)

### Entity Models

```swift
// MARK: - Core Entity Model
public struct HomeEntity: Codable, Identifiable {
    public let id: String
    public let version: String
    public let entityType: EntityType
    public let parentVersions: [String]
    public let content: EntityContent
    public let userId: String
    public let sourceType: SourceType
    public let createdAt: Date
    public let lastModified: Date
    
    // Convenience accessors
    public var displayName: String? {
        content["name"] as? String
    }
}

// MARK: - Entity Content Wrapper
public struct EntityContent: Codable {
    private var storage: [String: AnyCodable]
    
    public subscript(key: String) -> Any? {
        get { storage[key]?.value }
        set { storage[key] = newValue.map(AnyCodable.init) }
    }
}

// MARK: - Relationship Model
public struct EntityRelationship: Codable, Identifiable {
    public let id: String
    public let fromEntityId: String
    public let toEntityId: String
    public let relationshipType: RelationshipType
    public let properties: [String: AnyCodable]
    public let userId: String
    public let createdAt: Date
}
```

### Request/Response Models

```swift
// MARK: - Query Models
public struct EntityPredicate {
    public enum Operator {
        case equals, notEquals, contains, greaterThan, lessThan
    }
    
    public let field: String
    public let op: Operator
    public let value: Any
    
    // Compound predicates
    public static func and(_ predicates: EntityPredicate...) -> EntityPredicate
    public static func or(_ predicates: EntityPredicate...) -> EntityPredicate
}

public struct SortDescriptor {
    public let field: String
    public let ascending: Bool
}

// MARK: - Search Models
public struct SearchResult {
    public let entity: HomeEntity
    public let score: Double
    public let highlights: [SearchHighlight]
}

public struct SearchHighlight {
    public let field: String
    public let snippet: String
    public let range: Range<String.Index>
}

// MARK: - MCP Models
public struct MCPToolRequest {
    public let name: String
    public let arguments: [String: Any]
    public let timeout: TimeInterval?
}

public struct MCPToolResponse {
    public let content: [MCPContent]
    public let metadata: [String: Any]?
    
    public enum MCPContent {
        case text(String)
        case resource(uri: String, mimeType: String, data: Data)
        case error(MCPError)
    }
}

// MARK: - Sync Models
public struct SyncStatus {
    public let state: SyncState
    public let lastSyncDate: Date?
    public let pendingChanges: Int
    public let conflicts: [SyncConflict]
    
    public enum SyncState {
        case idle, syncing, completed, failed(Error)
    }
}

public struct SyncConflict {
    public let entityId: String
    public let localVersion: String
    public let remoteVersion: String
    public let conflictType: ConflictType
    
    public enum ConflictType {
        case versionConflict, typeConflict, deletionConflict
    }
}
```

## Error Handling

### Error Types

```swift
public enum WildThingInterfaceError: LocalizedError {
    // Initialization errors
    case notInitialized
    case alreadyInitialized
    case initializationFailed(Error)
    
    // Storage errors
    case entityNotFound(id: String)
    case invalidEntityType(String)
    case storageError(Error)
    
    // Graph errors
    case invalidGraphQuery(String)
    case pathNotFound(from: String, to: String)
    case cyclicDependency([String])
    
    // MCP errors
    case toolNotFound(String)
    case invalidArguments(tool: String, reason: String)
    case toolExecutionFailed(Error)
    
    // Sync errors
    case syncNotAvailable
    case syncInProgress
    case syncFailed(Error)
    
    public var errorDescription: String? {
        switch self {
        case .notInitialized:
            return "WildThing service not initialized"
        case .entityNotFound(let id):
            return "Entity not found: \(id)"
        case .toolNotFound(let tool):
            return "MCP tool not found: \(tool)"
        // ... other cases
        }
    }
}
```

## Service Implementation Patterns

### 1. Service Factory

```swift
public final class WildThingServiceFactory {
    public static func createService(
        configuration: WildThingConfiguration
    ) async throws -> WildThingServiceProtocol {
        
        let storage = try createStorage(configuration: configuration)
        let mcpServer = WildThingMCPServer(storage: storage)
        
        // Optional components
        let syncClient = try? createSyncClient(configuration: configuration)
        let homeKitBridge = try? createHomeKitBridge(storage: storage)
        
        let service = WildThingService(
            storage: storage,
            mcpServer: mcpServer,
            syncClient: syncClient,
            homeKitBridge: homeKitBridge
        )
        
        try await service.initialize()
        return service
    }
    
    private static func createStorage(
        configuration: WildThingConfiguration
    ) throws -> WildThingStorage {
        switch configuration.storageType {
        case .sqlite(let path):
            return try SQLiteWildThingStorage(databasePath: path)
        case .inMemory:
            return InMemoryWildThingStorage()
        }
    }
}
```

### 2. Async Operation Queue

```swift
public actor WildThingOperationQueue {
    private var pendingOperations: [WildThingOperation] = []
    private var isProcessing = false
    
    public func enqueue(_ operation: WildThingOperation) async {
        pendingOperations.append(operation)
        await processQueueIfNeeded()
    }
    
    private func processQueueIfNeeded() async {
        guard !isProcessing, !pendingOperations.isEmpty else { return }
        
        isProcessing = true
        defer { isProcessing = false }
        
        while !pendingOperations.isEmpty {
            let operation = pendingOperations.removeFirst()
            
            do {
                try await operation.execute()
            } catch {
                await handleOperationError(operation, error: error)
            }
        }
    }
}
```

### 3. Caching Layer

```swift
public protocol WildThingCacheProtocol {
    func get<T: Codable>(_ key: String, type: T.Type) async -> T?
    func set<T: Codable>(_ key: String, value: T, ttl: TimeInterval?) async
    func remove(_ key: String) async
    func clear() async
}

public final class WildThingCache: WildThingCacheProtocol {
    private let memoryCache = NSCache<NSString, CacheEntry>()
    private let diskCache: DiskCache?
    
    private final class CacheEntry {
        let value: Any
        let expiration: Date?
        
        var isExpired: Bool {
            guard let expiration = expiration else { return false }
            return Date() > expiration
        }
    }
}
```

## Integration Patterns

### 1. Dependency Injection

```swift
// MARK: - App Dependencies
public protocol AppDependencies {
    var wildThingService: WildThingServiceProtocol { get }
    var homeGraphService: HomeGraphServiceProtocol { get }
    var syncManager: SyncManagerProtocol { get }
}

@MainActor
public final class DefaultAppDependencies: AppDependencies {
    public let wildThingService: WildThingServiceProtocol
    public let homeGraphService: HomeGraphServiceProtocol
    public let syncManager: SyncManagerProtocol
    
    public init() async throws {
        let configuration = WildThingConfiguration.default
        
        self.wildThingService = try await WildThingServiceFactory
            .createService(configuration: configuration)
        
        self.homeGraphService = HomeGraphService(
            wildThingService: wildThingService
        )
        
        self.syncManager = SyncManager(
            syncService: wildThingService.sync
        )
    }
}
```

### 2. View Model Integration

```swift
// MARK: - Base ViewModel with WildThing
@MainActor
public class WildThingViewModel: ObservableObject {
    protected let dependencies: AppDependencies
    @Published public var isLoading = false
    @Published public var error: Error?
    
    public init(dependencies: AppDependencies) {
        self.dependencies = dependencies
    }
    
    protected func performOperation<T>(
        _ operation: () async throws -> T
    ) async -> T? {
        isLoading = true
        error = nil
        
        do {
            let result = try await operation()
            isLoading = false
            return result
        } catch {
            self.error = error
            isLoading = false
            return nil
        }
    }
}
```

### 3. SwiftUI Environment

```swift
// MARK: - Environment Keys
private struct WildThingServiceKey: EnvironmentKey {
    static let defaultValue: WildThingServiceProtocol? = nil
}

private struct HomeGraphServiceKey: EnvironmentKey {
    static let defaultValue: HomeGraphServiceProtocol? = nil
}

extension EnvironmentValues {
    public var wildThingService: WildThingServiceProtocol? {
        get { self[WildThingServiceKey.self] }
        set { self[WildThingServiceKey.self] = newValue }
    }
    
    public var homeGraphService: HomeGraphServiceProtocol? {
        get { self[HomeGraphServiceKey.self] }
        set { self[HomeGraphServiceKey.self] = newValue }
    }
}

// MARK: - App Root
@main
struct C11sIOSHouseApp: App {
    @StateObject private var dependencies = AppDependenciesContainer()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.wildThingService, dependencies.wildThingService)
                .environment(\.homeGraphService, dependencies.homeGraphService)
        }
    }
}
```

## Testing Interfaces

### Mock Implementations

```swift
// MARK: - Mock Storage
public final class MockWildThingStorage: WildThingStorageProtocol {
    public var entities: [String: HomeEntity] = [:]
    public var storeEntityCalled = false
    public var getEntityCalled = false
    
    public func store(entity: HomeEntity) async throws {
        storeEntityCalled = true
        entities[entity.id] = entity
    }
    
    public func getEntity(id: String) async throws -> HomeEntity? {
        getEntityCalled = true
        return entities[id]
    }
}

// MARK: - Mock MCP Server
public final class MockMCPServer: MCPServerProtocol {
    public var mockResponses: [String: MCPToolResponse] = [:]
    
    public func executeTool(
        name: String, 
        arguments: [String: Any]
    ) async throws -> MCPToolResponse {
        guard let response = mockResponses[name] else {
            throw WildThingInterfaceError.toolNotFound(name)
        }
        return response
    }
}
```

### Test Helpers

```swift
// MARK: - Test Factories
public enum TestEntityFactory {
    public static func makeRoom(
        name: String = "Test Room",
        id: String = UUID().uuidString
    ) -> HomeEntity {
        HomeEntity(
            id: id,
            entityType: .room,
            content: EntityContent(["name": name]),
            userId: "test-user",
            sourceType: .manual
        )
    }
    
    public static func makeDevice(
        name: String = "Test Device",
        roomId: String? = nil
    ) -> HomeEntity {
        HomeEntity(
            entityType: .device,
            content: EntityContent([
                "name": name,
                "roomId": roomId
            ]),
            userId: "test-user",
            sourceType: .manual
        )
    }
}
```

## Performance Considerations

### 1. Batch Operations

```swift
extension WildThingServiceProtocol {
    // Batch entity operations
    public func batchOperation<T>(
        _ operation: (HomeEntity) async throws -> T,
        entities: [HomeEntity],
        maxConcurrency: Int = 5
    ) async throws -> [T] {
        try await withThrowingTaskGroup(of: T.self) { group in
            var results: [T] = []
            
            for entity in entities {
                group.addTask {
                    try await operation(entity)
                }
            }
            
            for try await result in group {
                results.append(result)
            }
            
            return results
        }
    }
}
```

### 2. Lazy Loading

```swift
// MARK: - Lazy Entity Loader
public final class LazyEntityLoader {
    private let storage: WildThingStorageProtocol
    private var cache: [String: HomeEntity] = [:]
    
    public func entity(id: String) async throws -> HomeEntity {
        if let cached = cache[id] {
            return cached
        }
        
        guard let entity = try await storage.getEntity(id: id) else {
            throw WildThingInterfaceError.entityNotFound(id: id)
        }
        
        cache[id] = entity
        return entity
    }
    
    public func preload(ids: [String]) async throws {
        let entities = try await storage.batchGet(ids: ids)
        for entity in entities {
            cache[entity.id] = entity
        }
    }
}
```

### 3. Query Optimization

```swift
// MARK: - Query Builder
public struct WildThingQueryBuilder {
    private var predicates: [EntityPredicate] = []
    private var sortDescriptors: [SortDescriptor] = []
    private var limit: Int?
    private var offset: Int?
    
    public func `where`(_ field: String, equals value: Any) -> Self {
        var builder = self
        builder.predicates.append(
            EntityPredicate(field: field, op: .equals, value: value)
        )
        return builder
    }
    
    public func orderBy(_ field: String, ascending: Bool = true) -> Self {
        var builder = self
        builder.sortDescriptors.append(
            SortDescriptor(field: field, ascending: ascending)
        )
        return builder
    }
    
    public func limit(_ limit: Int) -> Self {
        var builder = self
        builder.limit = limit
        return builder
    }
    
    public func build() -> WildThingQuery {
        WildThingQuery(
            predicates: predicates,
            sortDescriptors: sortDescriptors,
            limit: limit,
            offset: offset
        )
    }
}
```

## Migration Support

### Migration Protocol

```swift
public protocol WildThingMigrationProtocol {
    func migrate(from source: LegacyDataSource) async throws
    func validate() async throws -> ValidationResult
    func rollback() async throws
}

public struct ValidationResult {
    public let isValid: Bool
    public let errors: [ValidationError]
    public let warnings: [ValidationWarning]
}
```

## Monitoring and Analytics

### Analytics Interface

```swift
public protocol WildThingAnalyticsProtocol {
    func track(event: AnalyticsEvent) async
    func startTimer(for operation: String) -> TimerToken
    func endTimer(_ token: TimerToken) async
}

public struct AnalyticsEvent {
    public let name: String
    public let properties: [String: Any]
    public let timestamp: Date
}
```

## Security Considerations

### Encryption Interface

```swift
public protocol WildThingEncryptionProtocol {
    func encrypt(data: Data) async throws -> Data
    func decrypt(data: Data) async throws -> Data
    func encryptEntity(_ entity: HomeEntity) async throws -> HomeEntity
    func decryptEntity(_ entity: HomeEntity) async throws -> HomeEntity
}
```

## Future Extensibility

### Plugin Architecture

```swift
public protocol WildThingPlugin {
    var identifier: String { get }
    var version: String { get }
    
    func initialize(context: PluginContext) async throws
    func handleRequest(_ request: PluginRequest) async throws -> PluginResponse
}

public struct PluginContext {
    public let storage: WildThingStorageProtocol
    public let graph: HomeGraphProtocol
    public let configuration: [String: Any]
}
```

## Conclusion

This interface design provides a comprehensive, type-safe, and extensible foundation for integrating WildThing into c11s-ios-house. The protocol-oriented approach ensures testability and flexibility, while the async/await patterns provide modern concurrency support. The design supports gradual migration, comprehensive error handling, and future extensibility through plugins and additional protocols.