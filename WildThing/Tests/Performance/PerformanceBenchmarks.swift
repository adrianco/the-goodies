import XCTest
@testable import WildThing

final class WildThingPerformanceBenchmarks: XCTestCase {
    var storage: SQLiteWildThingStorage!
    var graph: HomeGraph!
    
    override func setUp() async throws {
        // Use file-based storage for more realistic performance tests
        let tempPath = NSTemporaryDirectory() + "performance_test.db"
        try? FileManager.default.removeItem(atPath: tempPath)
        storage = try SQLiteWildThingStorage(databasePath: tempPath)
        graph = HomeGraph(storage: storage)
    }
    
    override func tearDown() async throws {
        // Clean up
        storage = nil
        graph = nil
    }
    
    // MARK: - Entity Creation Benchmarks
    
    func testBulkEntityCreationPerformance() throws {
        let entityCount = 10_000
        
        measure {
            let entities = (0..<entityCount).map { i in
                HomeEntity(
                    entityType: .device,
                    content: [
                        "name": AnyCodable("Device \(i)"),
                        "index": AnyCodable(i),
                        "metadata": AnyCodable([
                            "created": Date().timeIntervalSince1970,
                            "tags": ["smart", "iot", "connected"]
                        ])
                    ],
                    userId: "perf-test"
                )
            }
            
            // Measure creation time
            _ = entities.count
        }
    }
    
    func testEntityStoragePerformance() async throws {
        let entityCount = 1000
        let entities = (0..<entityCount).map { i in
            HomeEntity(
                entityType: .device,
                content: ["name": AnyCodable("Device \(i)")],
                userId: "perf-test"
            )
        }
        
        measure {
            let expectation = self.expectation(description: "Storage complete")
            
            Task {
                for entity in entities {
                    try await storage.store(entity: entity)
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 10.0)
        }
    }
    
    // MARK: - Graph Operations Benchmarks
    
    func testGraphTraversalPerformance() async throws {
        // Create a complex graph structure
        let roomCount = 20
        let devicesPerRoom = 10
        
        // Create rooms
        var rooms: [HomeEntity] = []
        for i in 0..<roomCount {
            let room = HomeEntity(
                entityType: .room,
                content: ["name": AnyCodable("Room \(i)")],
                userId: "perf-test"
            )
            rooms.append(room)
            try await storage.store(entity: room)
        }
        
        // Create devices and relationships
        for (roomIndex, room) in rooms.enumerated() {
            for deviceIndex in 0..<devicesPerRoom {
                let device = HomeEntity(
                    entityType: .device,
                    content: ["name": AnyCodable("Device \(roomIndex)-\(deviceIndex)")],
                    userId: "perf-test"
                )
                try await storage.store(entity: device)
                
                let relationship = EntityRelationship(
                    fromEntityId: device.id,
                    toEntityId: room.id,
                    relationshipType: .locatedIn,
                    userId: "perf-test"
                )
                try await storage.store(relationship: relationship)
            }
        }
        
        // Create room connections
        for i in 0..<roomCount-1 {
            let connection = EntityRelationship(
                fromEntityId: rooms[i].id,
                toEntityId: rooms[i+1].id,
                relationshipType: .connectsTo,
                userId: "perf-test"
            )
            try await storage.store(relationship: connection)
        }
        
        // Load graph
        try await graph.loadFromStorage()
        
        // Benchmark path finding
        measure {
            let expectation = self.expectation(description: "Path finding complete")
            
            Task {
                // Find paths between distant rooms
                for _ in 0..<10 {
                    _ = try await graph.findPath(from: "Room 0", to: "Room 19")
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 5.0)
        }
    }
    
    // MARK: - Search Performance
    
    func testSearchPerformance() async throws {
        // Populate with diverse content
        let entityCount = 5000
        let searchTerms = ["smart", "light", "sensor", "camera", "thermostat", "lock", "switch"]
        
        for i in 0..<entityCount {
            let searchTerm = searchTerms[i % searchTerms.count]
            let entity = HomeEntity(
                entityType: .device,
                content: [
                    "name": AnyCodable("\(searchTerm) Device \(i)"),
                    "description": AnyCodable("This is a \(searchTerm) with advanced features"),
                    "tags": AnyCodable(["iot", searchTerm, "connected"])
                ],
                userId: "perf-test"
            )
            try await storage.store(entity: entity)
        }
        
        try await graph.loadFromStorage()
        
        // Benchmark searches
        measure {
            let expectation = self.expectation(description: "Search complete")
            
            Task {
                for term in searchTerms {
                    _ = try await graph.semanticSearch(query: term)
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 5.0)
        }
    }
    
    // MARK: - MCP Server Performance
    
    func testMCPToolExecutionPerformance() async throws {
        let server = WildThingMCPServer(storage: storage)
        try await server.start()
        
        // Populate test data
        let room = HomeEntity(
            entityType: .room,
            content: ["name": AnyCodable("Test Room")],
            userId: "perf-test"
        )
        try await storage.store(entity: room)
        
        for i in 0..<100 {
            let device = HomeEntity(
                entityType: .device,
                content: ["name": AnyCodable("Device \(i)")],
                userId: "perf-test"
            )
            try await storage.store(entity: device)
            
            let rel = EntityRelationship(
                fromEntityId: device.id,
                toEntityId: room.id,
                relationshipType: .locatedIn,
                userId: "perf-test"
            )
            try await storage.store(relationship: rel)
        }
        
        // Benchmark tool execution
        measure {
            let expectation = self.expectation(description: "Tool execution complete")
            
            Task {
                for _ in 0..<10 {
                    _ = try await server.handleToolCall(MCPToolRequest(
                        name: "get_devices_in_room",
                        arguments: ["room_name": "Test Room"]
                    ))
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 5.0)
        }
    }
    
    // MARK: - Sync Performance
    
    func testSyncPerformance() async throws {
        // Create sync client with mock network
        let networkService = MockNetworkService()
        let remoteStorage = try SQLiteWildThingStorage(databasePath: ":memory:")
        networkService.server = MockInbetweeniesServer(storage: remoteStorage)
        
        let syncClient = InbetweeniesClient(storage: storage, networkService: networkService)
        
        // Create many entities to sync
        let entityCount = 1000
        for i in 0..<entityCount {
            let entity = HomeEntity(
                entityType: i % 2 == 0 ? .device : .room,
                content: [
                    "name": AnyCodable("Entity \(i)"),
                    "data": AnyCodable(Array(repeating: "x", count: 100).joined())
                ],
                userId: "sync-test"
            )
            try await storage.store(entity: entity)
        }
        
        // Benchmark sync
        measure {
            let expectation = self.expectation(description: "Sync complete")
            
            Task {
                let result = try await syncClient.performFullSync()
                XCTAssertEqual(result.uploaded, entityCount)
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 10.0)
        }
    }
    
    // MARK: - Memory Usage Tests
    
    func testMemoryEfficiency() async throws {
        // Monitor memory usage during large operations
        let initialMemory = getMemoryUsage()
        
        // Create and store many entities
        for i in 0..<5000 {
            autoreleasepool {
                let entity = HomeEntity(
                    entityType: .device,
                    content: [
                        "name": AnyCodable("Device \(i)"),
                        "largeData": AnyCodable(String(repeating: "x", count: 1000))
                    ],
                    userId: "memory-test"
                )
                
                Task {
                    try? await storage.store(entity: entity)
                }
            }
        }
        
        let peakMemory = getMemoryUsage()
        let memoryIncrease = peakMemory - initialMemory
        
        // Memory increase should be reasonable (less than 100MB for 5000 entities)
        XCTAssertLessThan(memoryIncrease, 100_000_000) // 100MB
    }
    
    // MARK: - Concurrent Access Performance
    
    func testConcurrentAccessPerformance() async throws {
        let concurrentOperations = 100
        let operationsPerTask = 10
        
        measure {
            let expectation = self.expectation(description: "Concurrent operations complete")
            
            Task {
                await withTaskGroup(of: Void.self) { group in
                    for i in 0..<concurrentOperations {
                        group.addTask {
                            for j in 0..<operationsPerTask {
                                let entity = HomeEntity(
                                    entityType: .device,
                                    content: ["name": AnyCodable("Concurrent \(i)-\(j)")],
                                    userId: "concurrent-test"
                                )
                                try? await self.storage.store(entity: entity)
                            }
                        }
                    }
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: 10.0)
        }
    }
    
    // MARK: - Helper Methods
    
    private func getMemoryUsage() -> Int64 {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size) / 4
        
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: 1) {
                task_info(mach_task_self_,
                         task_flavor_t(MACH_TASK_BASIC_INFO),
                         $0,
                         &count)
            }
        }
        
        return result == KERN_SUCCESS ? Int64(info.resident_size) : 0
    }
}

// MARK: - Performance Test Extensions

extension XCTestCase {
    func measureAsync(timeout: TimeInterval = 10.0, block: @escaping () async throws -> Void) {
        measure {
            let expectation = self.expectation(description: "Async measurement")
            
            Task {
                do {
                    try await block()
                } catch {
                    XCTFail("Async block threw error: \(error)")
                }
                expectation.fulfill()
            }
            
            wait(for: [expectation], timeout: timeout)
        }
    }
}