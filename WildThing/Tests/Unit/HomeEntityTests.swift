import XCTest
@testable import WildThing

final class HomeEntityTests: XCTestCase {
    
    // MARK: - Entity Creation Tests
    
    func testBasicEntityCreation() {
        // Arrange
        let entityType = EntityType.room
        let content: [String: AnyCodable] = [
            "name": AnyCodable("Living Room"),
            "area": AnyCodable(250.5)
        ]
        let userId = "test-user"
        
        // Act
        let entity = HomeEntity(
            entityType: entityType,
            content: content,
            userId: userId
        )
        
        // Assert
        XCTAssertEqual(entity.entityType, entityType)
        XCTAssertEqual(entity.content["name"]?.value as? String, "Living Room")
        XCTAssertEqual(entity.content["area"]?.value as? Double, 250.5)
        XCTAssertEqual(entity.userId, userId)
        XCTAssertEqual(entity.sourceType, .manual)
        XCTAssertFalse(entity.id.isEmpty)
        XCTAssertFalse(entity.version.isEmpty)
        XCTAssertTrue(entity.parentVersions.isEmpty)
    }
    
    func testEntityWithAllFields() {
        // Arrange
        let id = "custom-id"
        let entityType = EntityType.device
        let content: [String: AnyCodable] = [
            "name": AnyCodable("Smart Thermostat"),
            "brand": AnyCodable("Nest"),
            "model": AnyCodable("Learning Thermostat"),
            "firmware": AnyCodable("5.1.2")
        ]
        let userId = "user-123"
        let sourceType = SourceType.homekit
        let parentVersions = ["parent-v1", "parent-v2"]
        
        // Act
        let entity = HomeEntity(
            id: id,
            entityType: entityType,
            content: content,
            userId: userId,
            sourceType: sourceType,
            parentVersions: parentVersions
        )
        
        // Assert
        XCTAssertEqual(entity.id, id)
        XCTAssertEqual(entity.entityType, entityType)
        XCTAssertEqual(entity.sourceType, sourceType)
        XCTAssertEqual(entity.parentVersions, parentVersions)
    }
    
    // MARK: - Version Generation Tests
    
    func testVersionFormat() {
        // Arrange & Act
        let entity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Test Room")],
            userId: "test-user"
        )
        
        // Assert
        // Version should be in format: ISO8601-timestamp-userId
        XCTAssertTrue(entity.version.contains("-test-user"))
        XCTAssertTrue(entity.version.contains("T")) // ISO8601 format
        XCTAssertTrue(entity.version.contains("Z")) // UTC timezone
    }
    
    func testUniqueVersionGeneration() {
        // Arrange & Act
        let entity1 = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Room 1")],
            userId: "user"
        )
        
        let entity2 = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Room 2")],
            userId: "user"
        )
        
        // Assert
        XCTAssertNotEqual(entity1.version, entity2.version)
    }
    
    // MARK: - Serialization Tests
    
    func testJSONEncoding() throws {
        // Arrange
        let entity = HomeEntity(
            entityType: .device,
            content: [
                "name": AnyCodable("Smart Light"),
                "brightness": AnyCodable(75),
                "on": AnyCodable(true),
                "colors": AnyCodable(["red", "green", "blue"])
            ],
            userId: "test-user"
        )
        
        // Act
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(entity)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        
        // Assert
        XCTAssertNotNil(json)
        XCTAssertEqual(json?["entity_type"] as? String, "device")
        XCTAssertEqual(json?["user_id"] as? String, "test-user")
        XCTAssertNotNil(json?["content"] as? [String: Any])
    }
    
    func testJSONDecoding() throws {
        // Arrange
        let jsonString = """
        {
            "id": "test-id",
            "version": "2024-01-01T00:00:00Z-user",
            "entity_type": "room",
            "parent_versions": ["v1", "v2"],
            "content": {
                "name": "Kitchen",
                "area": 150.0
            },
            "user_id": "test-user",
            "source_type": "manual",
            "created_at": "2024-01-01T00:00:00Z",
            "last_modified": "2024-01-01T00:00:00Z"
        }
        """
        
        // Act
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let entity = try decoder.decode(HomeEntity.self, from: Data(jsonString.utf8))
        
        // Assert
        XCTAssertEqual(entity.id, "test-id")
        XCTAssertEqual(entity.entityType, .room)
        XCTAssertEqual(entity.content["name"]?.value as? String, "Kitchen")
        XCTAssertEqual(entity.content["area"]?.value as? Double, 150.0)
    }
    
    // MARK: - AnyCodable Tests
    
    func testAnyCodableWithPrimitives() throws {
        // Test Boolean
        let boolCodable = AnyCodable(true)
        XCTAssertEqual(boolCodable.value as? Bool, true)
        
        // Test Integer
        let intCodable = AnyCodable(42)
        XCTAssertEqual(intCodable.value as? Int, 42)
        
        // Test Double
        let doubleCodable = AnyCodable(3.14159)
        XCTAssertEqual(doubleCodable.value as? Double, 3.14159)
        
        // Test String
        let stringCodable = AnyCodable("Hello World")
        XCTAssertEqual(stringCodable.value as? String, "Hello World")
    }
    
    func testAnyCodableWithCollections() throws {
        // Test Array
        let arrayCodable = AnyCodable(["one", "two", "three"])
        let arrayValue = arrayCodable.value as? [String]
        XCTAssertEqual(arrayValue, ["one", "two", "three"])
        
        // Test Dictionary
        let dictCodable = AnyCodable(["key": "value", "number": 42])
        let dictValue = dictCodable.value as? [String: Any]
        XCTAssertEqual(dictValue?["key"] as? String, "value")
        XCTAssertEqual(dictValue?["number"] as? Int, 42)
    }
    
    // MARK: - Entity Type Tests
    
    func testAllEntityTypes() {
        // Test that all entity types are properly defined
        let expectedTypes: [EntityType] = [
            .home, .room, .device, .accessory, .service,
            .zone, .door, .window, .procedure, .manual,
            .note, .schedule, .automation
        ]
        
        XCTAssertEqual(EntityType.allCases.count, expectedTypes.count)
        
        for type in expectedTypes {
            XCTAssertTrue(EntityType.allCases.contains(type))
        }
    }
    
    // MARK: - Validation Tests
    
    func testEntityWithEmptyContent() {
        // Should be able to create entity with empty content
        let entity = HomeEntity(
            entityType: .device,
            content: [:],
            userId: "user"
        )
        
        XCTAssertTrue(entity.content.isEmpty)
        XCTAssertEqual(entity.entityType, .device)
    }
    
    func testEntityTimestamps() {
        // Arrange
        let beforeCreation = Date()
        
        // Act
        let entity = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Test")],
            userId: "user"
        )
        
        let afterCreation = Date()
        
        // Assert
        XCTAssertTrue(entity.createdAt >= beforeCreation)
        XCTAssertTrue(entity.createdAt <= afterCreation)
        XCTAssertEqual(entity.createdAt, entity.lastModified)
    }
    
    // MARK: - Performance Tests
    
    func testEntityCreationPerformance() {
        measure {
            // Create 1000 entities
            for i in 0..<1000 {
                _ = HomeEntity(
                    entityType: .device,
                    content: ["name": AnyCodable("Device \(i)")],
                    userId: "perf-test"
                )
            }
        }
    }
    
    func testEntitySerializationPerformance() throws {
        let entity = HomeEntity(
            entityType: .device,
            content: [
                "name": AnyCodable("Complex Device"),
                "properties": AnyCodable([
                    "nested": ["deeply": ["nested": "value"]]
                ])
            ],
            userId: "perf-test"
        )
        
        measure {
            let encoder = JSONEncoder()
            _ = try? encoder.encode(entity)
        }
    }
}