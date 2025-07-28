import XCTest
@testable import WildThing

final class SQLiteStorageTests: XCTestCase {
    var storage: SQLiteWildThingStorage!
    
    override func setUp() async throws {
        // Use in-memory database for tests
        storage = try SQLiteWildThingStorage(databasePath: ":memory:")
    }
    
    override func tearDown() async throws {
        storage = nil
    }
    
    // MARK: - Entity CRUD Tests
    
    func testStoreAndRetrieveEntity() async throws {
        // Arrange
        let entity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Test Room")],
            userId: "test-user"
        )
        
        // Act
        try await storage.store(entity: entity)
        let retrieved = try await storage.getEntity(id: entity.id)
        
        // Assert
        XCTAssertNotNil(retrieved)
        XCTAssertEqual(retrieved?.id, entity.id)
        XCTAssertEqual(retrieved?.entityType, entity.entityType)
        XCTAssertEqual(retrieved?.content["name"]?.value as? String, "Test Room")
    }
    
    func testGetLatestVersion() async throws {
        // Arrange - Create multiple versions
        let entityId = "test-entity"
        let entity1 = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["name": AnyCodable("Device v1")],
            userId: "user"
        )
        
        try await storage.store(entity: entity1)
        
        // Wait to ensure different timestamp
        try await Task.sleep(nanoseconds: 10_000_000) // 10ms
        
        let entity2 = HomeEntity(
            id: entityId,
            entityType: .device,
            content: ["name": AnyCodable("Device v2")],
            userId: "user",
            parentVersions: [entity1.version]
        )
        
        try await storage.store(entity: entity2)
        
        // Act
        let latest = try await storage.getLatestVersion(for: entityId)
        
        // Assert
        XCTAssertNotNil(latest)
        XCTAssertEqual(latest?.content["name"]?.value as? String, "Device v2")
        XCTAssertEqual(latest?.parentVersions.first, entity1.version)
    }
    
    func testGetAllVersions() async throws {
        // Arrange
        let entityId = "versioned-entity"
        let versions = ["v1", "v2", "v3"]
        
        for (index, versionName) in versions.enumerated() {
            let entity = HomeEntity(
                id: entityId,
                entityType: .device,
                content: ["version": AnyCodable(versionName)],
                userId: "user"
            )
            try await storage.store(entity: entity)
            
            if index < versions.count - 1 {
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        
        // Act
        let allVersions = try await storage.getAllVersions(for: entityId)
        
        // Assert
        XCTAssertEqual(allVersions.count, 3)
        // Versions should be ordered by creation time
        XCTAssertEqual(allVersions[0].content["version"]?.value as? String, "v1")
        XCTAssertEqual(allVersions[2].content["version"]?.value as? String, "v3")
    }
    
    func testGetEntitiesByType() async throws {
        // Arrange
        let room1 = HomeEntity(entityType: .room, content: ["name": AnyCodable("Room 1")], userId: "user")
        let room2 = HomeEntity(entityType: .room, content: ["name": AnyCodable("Room 2")], userId: "user")
        let device = HomeEntity(entityType: .device, content: ["name": AnyCodable("Device")], userId: "user")
        
        try await storage.store(entity: room1)
        try await storage.store(entity: room2)
        try await storage.store(entity: device)
        
        // Act
        let rooms = try await storage.getEntities(ofType: .room)
        let devices = try await storage.getEntities(ofType: .device)
        
        // Assert
        XCTAssertEqual(rooms.count, 2)
        XCTAssertEqual(devices.count, 1)
        XCTAssertTrue(rooms.allSatisfy { $0.entityType == .room })
    }
    
    func testDeleteEntity() async throws {
        // Arrange
        let entity = HomeEntity(
            entityType: .device,
            content: ["name": AnyCodable("To Delete")],
            userId: "user"
        )
        try await storage.store(entity: entity)
        
        // Act
        try await storage.deleteEntity(id: entity.id, version: nil)
        let retrieved = try await storage.getEntity(id: entity.id)
        
        // Assert
        XCTAssertNil(retrieved)
    }
    
    // MARK: - Relationship Tests
    
    func testStoreAndRetrieveRelationship() async throws {
        // Arrange
        let fromEntity = HomeEntity(entityType: .device, content: [:], userId: "user")
        let toEntity = HomeEntity(entityType: .room, content: [:], userId: "user")
        
        try await storage.store(entity: fromEntity)
        try await storage.store(entity: toEntity)
        
        let relationship = EntityRelationship(
            fromEntityId: fromEntity.id,
            toEntityId: toEntity.id,
            relationshipType: .locatedIn,
            properties: ["distance": AnyCodable(5.0)],
            userId: "user"
        )
        
        // Act
        try await storage.store(relationship: relationship)
        let fromRelationships = try await storage.getRelationships(from: fromEntity.id)
        let toRelationships = try await storage.getRelationships(to: toEntity.id)
        
        // Assert
        XCTAssertEqual(fromRelationships.count, 1)
        XCTAssertEqual(toRelationships.count, 1)
        XCTAssertEqual(fromRelationships.first?.relationshipType, .locatedIn)
        XCTAssertEqual(fromRelationships.first?.properties["distance"]?.value as? Double, 5.0)
    }
    
    func testGetRelationshipsByType() async throws {
        // Arrange
        let device1 = HomeEntity(entityType: .device, content: [:], userId: "user")
        let device2 = HomeEntity(entityType: .device, content: [:], userId: "user")
        let room = HomeEntity(entityType: .room, content: [:], userId: "user")
        
        try await storage.store(entity: device1)
        try await storage.store(entity: device2)
        try await storage.store(entity: room)
        
        let rel1 = EntityRelationship(
            fromEntityId: device1.id,
            toEntityId: room.id,
            relationshipType: .locatedIn,
            userId: "user"
        )
        
        let rel2 = EntityRelationship(
            fromEntityId: device2.id,
            toEntityId: device1.id,
            relationshipType: .controls,
            userId: "user"
        )
        
        try await storage.store(relationship: rel1)
        try await storage.store(relationship: rel2)
        
        // Act
        let locatedInRels = try await storage.getRelationships(ofType: .locatedIn)
        let controlsRels = try await storage.getRelationships(ofType: .controls)
        
        // Assert
        XCTAssertEqual(locatedInRels.count, 1)
        XCTAssertEqual(controlsRels.count, 1)
    }
    
    func testDeleteRelationship() async throws {
        // Arrange
        let relationship = EntityRelationship(
            fromEntityId: "from",
            toEntityId: "to",
            relationshipType: .connectsTo,
            userId: "user"
        )
        
        try await storage.store(relationship: relationship)
        
        // Act
        try await storage.deleteRelationship(id: relationship.id)
        let relationships = try await storage.getRelationships(from: "from")
        
        // Assert
        XCTAssertTrue(relationships.isEmpty)
    }
    
    // MARK: - Query Tests
    
    func testSearchEntities() async throws {
        // Arrange
        let entities = [
            HomeEntity(entityType: .room, content: ["name": AnyCodable("Living Room"), "description": AnyCodable("Main living area")], userId: "user"),
            HomeEntity(entityType: .room, content: ["name": AnyCodable("Bedroom"), "description": AnyCodable("Master bedroom")], userId: "user"),
            HomeEntity(entityType: .device, content: ["name": AnyCodable("Living Room Light"), "brand": AnyCodable("Philips")], userId: "user")
        ]
        
        for entity in entities {
            try await storage.store(entity: entity)
        }
        
        // Act
        let livingResults = try await storage.searchEntities(query: "Living", types: nil)
        let roomResults = try await storage.searchEntities(query: "Room", types: [.room])
        
        // Assert
        XCTAssertEqual(livingResults.count, 2) // Living Room and Living Room Light
        XCTAssertEqual(roomResults.count, 1) // Only Living Room (filtered by type)
    }
    
    func testGetEntitiesInRoom() async throws {
        // Arrange
        let room = HomeEntity(entityType: .room, content: ["name": AnyCodable("Kitchen")], userId: "user")
        let device1 = HomeEntity(entityType: .device, content: ["name": AnyCodable("Fridge")], userId: "user")
        let device2 = HomeEntity(entityType: .device, content: ["name": AnyCodable("Oven")], userId: "user")
        let otherDevice = HomeEntity(entityType: .device, content: ["name": AnyCodable("TV")], userId: "user")
        
        try await storage.store(entity: room)
        try await storage.store(entity: device1)
        try await storage.store(entity: device2)
        try await storage.store(entity: otherDevice)
        
        // Create relationships
        try await storage.store(relationship: EntityRelationship(
            fromEntityId: device1.id,
            toEntityId: room.id,
            relationshipType: .locatedIn,
            userId: "user"
        ))
        
        try await storage.store(relationship: EntityRelationship(
            fromEntityId: device2.id,
            toEntityId: room.id,
            relationshipType: .locatedIn,
            userId: "user"
        ))
        
        // Act
        let entitiesInRoom = try await storage.getEntitiesInRoom(room.id)
        
        // Assert
        XCTAssertEqual(entitiesInRoom.count, 2)
        let deviceNames = entitiesInRoom.compactMap { $0.content["name"]?.value as? String }
        XCTAssertTrue(deviceNames.contains("Fridge"))
        XCTAssertTrue(deviceNames.contains("Oven"))
        XCTAssertFalse(deviceNames.contains("TV"))
    }
    
    func testFindPath() async throws {
        // Arrange - Create a simple path: Room1 -> Hall -> Room2
        let room1 = HomeEntity(entityType: .room, content: ["name": AnyCodable("Room1")], userId: "user")
        let hall = HomeEntity(entityType: .room, content: ["name": AnyCodable("Hall")], userId: "user")
        let room2 = HomeEntity(entityType: .room, content: ["name": AnyCodable("Room2")], userId: "user")
        
        try await storage.store(entity: room1)
        try await storage.store(entity: hall)
        try await storage.store(entity: room2)
        
        try await storage.store(relationship: EntityRelationship(
            fromEntityId: room1.id,
            toEntityId: hall.id,
            relationshipType: .connectsTo,
            userId: "user"
        ))
        
        try await storage.store(relationship: EntityRelationship(
            fromEntityId: hall.id,
            toEntityId: room2.id,
            relationshipType: .connectsTo,
            userId: "user"
        ))
        
        // Act
        let path = try await storage.findPath(from: room1.id, to: room2.id)
        
        // Assert
        XCTAssertEqual(path.count, 3)
        XCTAssertEqual(path[0], room1.id)
        XCTAssertEqual(path[1], hall.id)
        XCTAssertEqual(path[2], room2.id)
    }
    
    // MARK: - Binary Content Tests
    
    func testStoreBinaryContent() async throws {
        // Arrange
        let entity = HomeEntity(entityType: .device, content: [:], userId: "user")
        try await storage.store(entity: entity)
        
        let imageData = Data("fake-image-data".utf8)
        let binaryContent = BinaryContent(
            entityId: entity.id,
            entityVersion: entity.version,
            contentType: "image/jpeg",
            fileName: "device-photo.jpg",
            data: imageData
        )
        
        // Act
        try await storage.storeBinaryContent(binaryContent)
        let retrieved = try await storage.getBinaryContent(id: binaryContent.id)
        
        // Assert
        XCTAssertNotNil(retrieved)
        XCTAssertEqual(retrieved?.contentType, "image/jpeg")
        XCTAssertEqual(retrieved?.fileName, "device-photo.jpg")
        XCTAssertEqual(retrieved?.data, imageData)
    }
    
    // MARK: - Sync Support Tests
    
    func testGetChangedEntities() async throws {
        // Arrange
        let baseTime = Date()
        
        let entity1 = HomeEntity(entityType: .room, content: [:], userId: "user1")
        try await storage.store(entity: entity1)
        
        // Wait and create another entity
        try await Task.sleep(nanoseconds: 100_000_000) // 100ms
        
        let entity2 = HomeEntity(entityType: .device, content: [:], userId: "user2")
        try await storage.store(entity: entity2)
        
        // Act
        let changedSinceBase = try await storage.getChangedEntities(since: baseTime, userId: nil)
        let changedForUser2 = try await storage.getChangedEntities(since: baseTime, userId: "user2")
        
        // Assert
        XCTAssertEqual(changedSinceBase.count, 2)
        XCTAssertEqual(changedForUser2.count, 1)
        XCTAssertEqual(changedForUser2.first?.userId, "user2")
    }
    
    // MARK: - Concurrent Access Tests
    
    func testConcurrentWrites() async throws {
        // Test that concurrent writes don't cause issues
        await withTaskGroup(of: Void.self) { group in
            for i in 0..<10 {
                group.addTask {
                    let entity = HomeEntity(
                        entityType: .device,
                        content: ["name": AnyCodable("Device \(i)")],
                        userId: "concurrent-user"
                    )
                    try? await self.storage.store(entity: entity)
                }
            }
        }
        
        // Verify all entities were stored
        let devices = try await storage.getEntities(ofType: .device)
        XCTAssertEqual(devices.count, 10)
    }
    
    // MARK: - Performance Tests
    
    func testBulkInsertPerformance() async throws {
        let entities = (0..<1000).map { i in
            HomeEntity(
                entityType: .device,
                content: ["name": AnyCodable("Device \(i)")],
                userId: "perf-user"
            )
        }
        
        let start = Date()
        
        for entity in entities {
            try await storage.store(entity: entity)
        }
        
        let duration = Date().timeIntervalSince(start)
        
        // Should complete in reasonable time
        XCTAssertLessThan(duration, 2.0) // Less than 2 seconds for 1000 entities
    }
}