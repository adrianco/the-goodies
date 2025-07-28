import XCTest
@testable import WildThing

final class InbetweeniesIntegrationTests: XCTestCase {
    var localStorage: SQLiteWildThingStorage!
    var remoteStorage: SQLiteWildThingStorage!
    var localClient: InbetweeniesClient!
    var mockServer: MockInbetweeniesServer!
    
    override func setUp() async throws {
        // Set up local and "remote" storage
        localStorage = try SQLiteWildThingStorage(databasePath: ":memory:")
        remoteStorage = try SQLiteWildThingStorage(databasePath: ":memory:")
        
        // Set up mock server with remote storage
        mockServer = MockInbetweeniesServer(storage: remoteStorage)
        
        // Set up client with mock network service
        let networkService = MockNetworkService()
        networkService.server = mockServer
        localClient = InbetweeniesClient(storage: localStorage, networkService: networkService)
    }
    
    // MARK: - Basic Sync Tests
    
    func testSimpleEntitySync() async throws {
        // Arrange - Create entity on local
        let localEntity = HomeEntity(
            entityType: .device,
            content: ["name": AnyCodable("Local Device")],
            userId: "test-user"
        )
        try await localStorage.store(entity: localEntity)
        
        // Act - Perform sync
        let result = try await localClient.performFullSync()
        
        // Assert
        XCTAssertEqual(result.uploaded, 1)
        XCTAssertEqual(result.downloaded, 0)
        XCTAssertEqual(result.conflicts, 0)
        
        // Verify entity exists on remote
        let remoteEntity = try await remoteStorage.getEntity(id: localEntity.id)
        XCTAssertNotNil(remoteEntity)
        XCTAssertEqual(remoteEntity?.content["name"]?.value as? String, "Local Device")
    }
    
    func testBidirectionalSync() async throws {
        // Arrange - Create entities on both sides
        let localEntity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Local Room")],
            userId: "user1"
        )
        try await localStorage.store(entity: localEntity)
        
        let remoteEntity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Remote Room")],
            userId: "user2"
        )
        try await remoteStorage.store(entity: remoteEntity)
        
        // Act - Perform sync
        let result = try await localClient.performFullSync()
        
        // Assert
        XCTAssertEqual(result.uploaded, 1)
        XCTAssertEqual(result.downloaded, 1)
        
        // Verify both entities exist on both sides
        let localHasRemote = try await localStorage.getEntity(id: remoteEntity.id)
        let remoteHasLocal = try await remoteStorage.getEntity(id: localEntity.id)
        
        XCTAssertNotNil(localHasRemote)
        XCTAssertNotNil(remoteHasLocal)
    }
    
    // MARK: - Conflict Detection Tests
    
    func testVersionConflictDetection() async throws {
        // Arrange - Create same entity on both sides with different content
        let entityId = "shared-entity"
        
        let localEntity = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["name": AnyCodable("Local Version"), "value": AnyCodable(1)],
            userId: "user1"
        )
        try await localStorage.store(entity: localEntity)
        
        let remoteEntity = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["name": AnyCodable("Remote Version"), "value": AnyCodable(2)],
            userId: "user2"
        )
        try await remoteStorage.store(entity: remoteEntity)
        
        // Act - Perform sync
        let result = try await localClient.performFullSync()
        
        // Assert - Should detect conflict
        XCTAssertEqual(result.conflicts, 1)
        
        // Local version should be preserved (conflict not auto-resolved)
        let localVersion = try await localStorage.getEntity(id: entityId)
        XCTAssertEqual(localVersion?.content["value"]?.value as? Int, 1)
    }
    
    func testParentVersionTracking() async throws {
        // Arrange - Create base entity
        let entityId = "evolving-entity"
        let baseEntity = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["version": AnyCodable("v1")],
            userId: "user"
        )
        try await localStorage.store(entity: baseEntity)
        
        // Sync to remote
        _ = try await localClient.performFullSync()
        
        // Update on local with parent version
        let updatedEntity = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["version": AnyCodable("v2")],
            userId: "user",
            parentVersions: [baseEntity.version]
        )
        try await localStorage.store(entity: updatedEntity)
        
        // Act - Sync again
        let result = try await localClient.performFullSync()
        
        // Assert - No conflict because parent version is known
        XCTAssertEqual(result.conflicts, 0)
        XCTAssertEqual(result.uploaded, 1)
        
        // Remote should have the update
        let remoteVersion = try await remoteStorage.getLatestVersion(for: entityId)
        XCTAssertEqual(remoteVersion?.content["version"]?.value as? String, "v2")
        XCTAssertEqual(remoteVersion?.parentVersions.first, baseEntity.version)
    }
    
    // MARK: - Relationship Sync Tests
    
    func testRelationshipSync() async throws {
        // Arrange - Create entities and relationships
        let room = HomeEntity(entityType: .room, content: ["name": AnyCodable("Living Room")], userId: "user")
        let device = HomeEntity(entityType: .device, content: ["name": AnyCodable("TV")], userId: "user")
        
        try await localStorage.store(entity: room)
        try await localStorage.store(entity: device)
        
        let relationship = EntityRelationship(
            fromEntityId: device.id,
            toEntityId: room.id,
            relationshipType: .locatedIn,
            userId: "user"
        )
        try await localStorage.store(relationship: relationship)
        
        // Act - Sync
        let result = try await localClient.performFullSync()
        
        // Assert
        XCTAssertEqual(result.uploaded, 3) // 2 entities + 1 relationship
        
        // Verify relationship exists on remote
        let remoteRelationships = try await remoteStorage.getRelationships(from: device.id)
        XCTAssertEqual(remoteRelationships.count, 1)
        XCTAssertEqual(remoteRelationships.first?.relationshipType, .locatedIn)
    }
    
    // MARK: - Bulk Sync Tests
    
    func testBulkEntitySync() async throws {
        // Arrange - Create many entities
        let entities = (0..<100).map { i in
            HomeEntity(
                entityType: .device,
                content: ["name": AnyCodable("Device \(i)"), "index": AnyCodable(i)],
                userId: "bulk-user"
            )
        }
        
        for entity in entities {
            try await localStorage.store(entity: entity)
        }
        
        // Act - Sync
        let start = Date()
        let result = try await localClient.performFullSync()
        let duration = Date().timeIntervalSince(start)
        
        // Assert
        XCTAssertEqual(result.uploaded, 100)
        XCTAssertEqual(result.conflicts, 0)
        XCTAssertLessThan(duration, 5.0) // Should complete within 5 seconds
        
        // Verify all entities on remote
        let remoteDevices = try await remoteStorage.getEntities(ofType: .device)
        XCTAssertEqual(remoteDevices.count, 100)
    }
    
    // MARK: - Error Handling Tests
    
    func testSyncWithNetworkError() async throws {
        // Arrange
        let networkService = FailingNetworkService()
        let failingClient = InbetweeniesClient(storage: localStorage, networkService: networkService)
        
        let entity = HomeEntity(
            entityType: .device,
            content: ["name": AnyCodable("Test")],
            userId: "user"
        )
        try await localStorage.store(entity: entity)
        
        // Act & Assert
        do {
            _ = try await failingClient.performFullSync()
            XCTFail("Should have thrown network error")
        } catch {
            // Expected error
            XCTAssertTrue(error is URLError)
        }
    }
    
    func testPartialSyncRecovery() async throws {
        // Arrange - Create entities that will partially fail
        let goodEntity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Good Room")],
            userId: "user"
        )
        
        let badEntity = HomeEntity(
            entityType: .device,
            content: ["name": AnyCodable("Bad Device"), "corrupt": AnyCodable("💥")],
            userId: "user"
        )
        
        try await localStorage.store(entity: goodEntity)
        try await localStorage.store(entity: badEntity)
        
        // Configure server to reject corrupt entities
        mockServer.shouldRejectCorrupt = true
        
        // Act - Sync
        let result = try await localClient.performFullSync()
        
        // Assert - Good entity synced, bad entity failed
        XCTAssertEqual(result.uploaded, 1) // Only good entity
        XCTAssertEqual(result.errors.count, 1)
        
        let remoteGood = try await remoteStorage.getEntity(id: goodEntity.id)
        let remoteBad = try await remoteStorage.getEntity(id: badEntity.id)
        
        XCTAssertNotNil(remoteGood)
        XCTAssertNil(remoteBad)
    }
    
    // MARK: - Vector Clock Tests
    
    func testVectorClockMerging() async throws {
        // This would test the vector clock algorithm
        // For now, simplified test
        
        // Arrange - Set initial vector clocks
        try await localStorage.updateVectorClock(["device1": "10", "device2": "5"])
        try await remoteStorage.updateVectorClock(["device1": "8", "device2": "7", "device3": "3"])
        
        // Act - Sync
        _ = try await localClient.performFullSync()
        
        // Assert - Vector clocks should be merged (max of each component)
        let localClock = try await localStorage.getVectorClock()
        let remoteClock = try await remoteStorage.getVectorClock()
        
        // Both should have the maximum values
        XCTAssertEqual(localClock["device1"], "10")
        XCTAssertEqual(localClock["device2"], "7")
        XCTAssertEqual(localClock["device3"], "3")
        
        // Remote should match
        XCTAssertEqual(remoteClock["device1"], "10")
        XCTAssertEqual(remoteClock["device2"], "7")
        XCTAssertEqual(remoteClock["device3"], "3")
    }
}

// MARK: - Mock Implementations

class MockInbetweeniesServer {
    let storage: WildThingStorage
    var shouldRejectCorrupt = false
    
    init(storage: WildThingStorage) {
        self.storage = storage
    }
    
    func handleSyncRequest(_ request: InbetweeniesRequest) async throws -> InbetweeniesResponse {
        var conflicts: [String] = []
        
        // Process incoming changes
        for change in request.changes {
            if shouldRejectCorrupt && (change.content?["corrupt"] != nil) {
                throw NSError(domain: "MockServer", code: 400, userInfo: [NSLocalizedDescriptionKey: "Corrupt entity rejected"])
            }
            
            do {
                try await applyChange(change)
            } catch {
                conflicts.append(change.entityId)
            }
        }
        
        // Get changes to send back
        let serverChanges = try await getChangesForClient(request.vectorClock)
        
        // Merge vector clocks
        var mergedClock = request.vectorClock
        let serverClock = try await storage.getVectorClock()
        for (key, value) in serverClock {
            if let clientValue = mergedClock[key] {
                mergedClock[key] = max(clientValue, value)
            } else {
                mergedClock[key] = value
            }
        }
        
        try await storage.updateVectorClock(mergedClock)
        
        return InbetweeniesResponse(
            changes: serverChanges,
            vectorClock: mergedClock,
            conflicts: conflicts
        )
    }
    
    private func applyChange(_ change: EntityChange) async throws {
        switch change.changeType {
        case .create, .update:
            let entity = HomeEntity(
                id: change.entityId,
                entityType: EntityType(rawValue: change.entityType ?? "device") ?? .device,
                content: change.content ?? [:],
                userId: "server-sync",
                parentVersions: []
            )
            
            // Check for conflicts
            if let existing = try await storage.getEntity(id: entity.id) {
                if existing.version != change.entityVersion {
                    throw WildThingError.syncError("Version conflict")
                }
            }
            
            try await storage.store(entity: entity)
            
        case .delete:
            try await storage.deleteEntity(id: change.entityId, version: change.entityVersion)
        }
    }
    
    private func getChangesForClient(_ clientClock: [String: String]) async throws -> [EntityChange] {
        // For simplicity, return all entities as changes
        var changes: [EntityChange] = []
        
        for entityType in EntityType.allCases {
            let entities = try await storage.getEntities(ofType: entityType)
            for entity in entities {
                changes.append(EntityChange(
                    changeType: .update,
                    entityId: entity.id,
                    entityVersion: entity.version,
                    entityType: entity.entityType.rawValue,
                    content: entity.content,
                    timestamp: entity.lastModified
                ))
            }
        }
        
        return changes
    }
}

class MockNetworkService: NetworkService {
    var server: MockInbetweeniesServer?
    
    func sendInbetweeniesRequest(_ request: InbetweeniesRequest) async throws -> InbetweeniesResponse {
        guard let server = server else {
            throw URLError(.badURL)
        }
        
        return try await server.handleSyncRequest(request)
    }
}

class FailingNetworkService: NetworkService {
    func sendInbetweeniesRequest(_ request: InbetweeniesRequest) async throws -> InbetweeniesResponse {
        throw URLError(.networkConnectionLost)
    }
}