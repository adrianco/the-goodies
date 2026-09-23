/*
 * CONTEXT & PURPOSE:
 * Tests for HomeKitService to ensure proper discovery and note conversion functionality.
 * Since HomeKit requires actual device permissions and setup, these tests focus on
 * the data transformation and note generation logic.
 *
 * DECISION HISTORY:
 * - 2025-07-23: Initial implementation
 *   - Tests for model conversion and note generation
 *   - Mock HomeKit data for testing
 *   - Verify note format and content
 *
 * FUTURE UPDATES:
 * - [Add future changes and decisions here]
 */

//
//  HomeKitServiceTests.swift
//  C11SHouseTests
//
//  Tests for HomeKit service functionality
//

import XCTest
@testable import C11SHouse
import HomeKit
import Combine

// MARK: - Test Helpers for HomeKit Models
// Note: HomeKit models are structs with all let properties, so they have automatic memberwise initializers.
// We don't need to add custom initializers in extensions.

class HomeKitServiceTests: XCTestCase {
    
    var mockNotesService: MockHomeKitNotesService!
    
    override func setUp() {
        super.setUp()
        mockNotesService = MockHomeKitNotesService()
    }
    
    override func tearDown() {
        mockNotesService = nil
        super.tearDown()
    }
    
    // MARK: - Model Tests
    
    func testHomeKitHomeSummaryGeneration() {
        // Given
        let room1 = HomeKitRoom(id: UUID(), name: "Living Room")
        let room2 = HomeKitRoom(id: UUID(), name: "Kitchen")
        
        let accessory1 = HomeKitAccessory(
            id: UUID(),
            name: "Ceiling Light",
            roomId: room1.id,
            category: "Lights",
            manufacturer: "Philips",
            model: "Hue Go",
            isReachable: true,
            isBridged: true,
            currentState: "On",
            services: ["Lightbulb"]
        )
        
        let accessory2 = HomeKitAccessory(
            id: UUID(),
            name: "Smart Plug",
            roomId: room2.id,
            category: "Outlets",
            manufacturer: "Eve",
            model: "Energy",
            isReachable: true,
            isBridged: false,
            currentState: "Off",
            services: ["Outlet", "Power Monitoring"]
        )
        
        let home = HomeKitHome(
            id: UUID(),
            name: "My Home",
            isPrimary: true,
            rooms: [room1, room2],
            accessories: [accessory1, accessory2],
            createdAt: Date()
        )
        
        // When
        let summary = home.generateSummaryNote()
        
        // Then
        XCTAssertTrue(summary.contains("HomeKit Configuration for My Home"))
        XCTAssertTrue(summary.contains("This is your primary home"))
        XCTAssertTrue(summary.contains("Total Rooms: 2"))
        XCTAssertTrue(summary.contains("Total Accessories: 2"))
        XCTAssertTrue(summary.contains("Living Room (1 accessories)"))
        XCTAssertTrue(summary.contains("Kitchen (1 accessories)"))
        XCTAssertTrue(summary.contains("Lights: 1"))
        XCTAssertTrue(summary.contains("Outlets: 1"))
    }
    
    func testRoomNoteGeneration() {
        // Given
        let room = HomeKitRoom(id: UUID(), name: "Bedroom")
        let accessories = [
            HomeKitAccessory(
                id: UUID(),
                name: "Bedside Lamp",
                roomId: room.id,
                category: "Lights",
                manufacturer: "IKEA",
                model: "TRADFRI",
                isReachable: true,
                isBridged: false,
                currentState: "Brightness: 50%",
                services: ["Lightbulb"]
            ),
            HomeKitAccessory(
                id: UUID(),
                name: "Window Sensor",
                roomId: room.id,
                category: "Sensors",
                manufacturer: "Aqara",
                model: "Door and Window Sensor",
                isReachable: false,
                isBridged: true,
                currentState: nil as String?,
                services: ["Contact Sensor", "Battery"]
            )
        ]
        
        // When
        let note = room.generateNote(with: accessories)
        
        // Then
        XCTAssertTrue(note.contains("Room: Bedroom"))
        XCTAssertTrue(note.contains("Accessories (2)"))
        XCTAssertTrue(note.contains("Lights:"))
        XCTAssertTrue(note.contains("Bedside Lamp ✅ - Brightness: 50%"))
        XCTAssertTrue(note.contains("Sensors:"))
        XCTAssertTrue(note.contains("Window Sensor ❌ (unreachable)"))
    }
    
    func testAccessoryNoteGeneration() {
        // Given
        let accessory = HomeKitAccessory(
            id: UUID(),
            name: "Front Door Lock",
            roomId: nil as UUID?,
            category: "Locks",
            manufacturer: "August",
            model: "Smart Lock Pro",
            isReachable: true,
            isBridged: false,
            currentState: "Locked",
            services: ["Lock Management", "Battery"]
        )
        
        // When
        let note = accessory.generateNote()
        
        // Then
        XCTAssertTrue(note.contains("Front Door Lock"))
        XCTAssertTrue(note.contains("Type: Locks"))
        XCTAssertTrue(note.contains("Manufacturer: August"))
        XCTAssertTrue(note.contains("Model: Smart Lock Pro"))
        XCTAssertTrue(note.contains("Status: ✅ Reachable"))
        XCTAssertTrue(note.contains("Current State: Locked"))
        XCTAssertTrue(note.contains("Lock Management"))
        XCTAssertTrue(note.contains("Battery"))
    }
    
    func testDiscoverySummaryGeneration() {
        // Given
        let home = HomeKitHome(
            id: UUID(),
            name: "Test Home",
            isPrimary: false,
            rooms: [
                HomeKitRoom(id: UUID(), name: "Room 1"),
                HomeKitRoom(id: UUID(), name: "Room 2")
            ],
            accessories: [
                HomeKitAccessory(
                    id: UUID(),
                    name: "Device 1",
                    roomId: nil as UUID?,
                    category: "Other Accessories",
                    manufacturer: nil as String?,
                    model: nil as String?,
                    isReachable: true,
                    isBridged: false,
                    currentState: nil as String?,
                    services: []
                )
            ],
            createdAt: Date()
        )
        
        let summary = HomeKitDiscoverySummary(
            homes: [home],
            discoveredAt: Date()
        )
        
        // When
        let fullSummary = summary.generateFullSummary()
        
        // Then
        XCTAssertTrue(fullSummary.contains("HomeKit Discovery Summary"))
        XCTAssertTrue(fullSummary.contains("Found 1 home(s) with 2 rooms and 1 accessories"))
        XCTAssertTrue(fullSummary.contains("Test Home"))
        XCTAssertEqual(summary.totalRooms, 2)
        XCTAssertEqual(summary.totalAccessories, 1)
    }
    
    func testEmptyHomesSummary() {
        // Given
        let summary = HomeKitDiscoverySummary(homes: [], discoveredAt: Date())
        
        // When
        let fullSummary = summary.generateFullSummary()
        
        // Then
        XCTAssertTrue(fullSummary.contains("No HomeKit homes configured yet"))
        XCTAssertTrue(fullSummary.contains("Add homes and accessories in the Home app"))
    }
    
    // MARK: - Integration Tests
    
    @MainActor
    func testSaveHomeKitConfigurationAsNotes() async throws {
        // Given: Test HomeKit data and a mock notes service
        let mockNotesService = MockHomeKitNotesService()
        
        // Create test HomeKit data
        let room1 = HomeKitRoom(id: UUID(), name: "Living Room")
        let room2 = HomeKitRoom(id: UUID(), name: "Kitchen")
        let room3 = HomeKitRoom(id: UUID(), name: "Bedroom")
        
        let accessory1 = HomeKitAccessory(
            id: UUID(),
            name: "Living Room Light",
            roomId: room1.id,
            category: "Lights",
            manufacturer: "Philips",
            model: "Hue",
            isReachable: true,
            isBridged: true,
            currentState: "On",
            services: ["Lightbulb"]
        )
        
        let accessory2 = HomeKitAccessory(
            id: UUID(),
            name: "Kitchen Outlet",
            roomId: room2.id,
            category: "Outlets",
            manufacturer: "Eve",
            model: "Energy",
            isReachable: true,
            isBridged: false,
            currentState: "Off",
            services: ["Outlet"]
        )
        
        let accessory3 = HomeKitAccessory(
            id: UUID(),
            name: "Front Door Lock",
            roomId: nil, // Unassigned accessory
            category: "Locks",
            manufacturer: "August",
            model: "Smart Lock",
            isReachable: false,
            isBridged: false,
            currentState: "Locked",
            services: ["Lock Management"]
        )
        
        let home = HomeKitHome(
            id: UUID(),
            name: "Test Home",
            isPrimary: true,
            rooms: [room1, room2, room3],
            accessories: [accessory1, accessory2, accessory3],
            createdAt: Date()
        )
        
        let discoverySummary = HomeKitDiscoverySummary(
            homes: [home],
            discoveredAt: Date()
        )
        
        // Create a real HomeKitService with the mock notes service
        let homeKitService = HomeKitService(notesService: mockNotesService)
        
        // When: Save configuration as notes
        try await homeKitService.saveConfigurationAsNotes(summary: discoverySummary)
        
        // Then: Verify notes were saved correctly
        XCTAssertEqual(mockNotesService.savedCustomNotes.count, 4) // 1 summary + 2 rooms with accessories + 1 unassigned accessory
        
        // Check summary note
        let summaryNote = mockNotesService.savedCustomNotes.first { $0.category == "homekit_summary" }
        XCTAssertNotNil(summaryNote)
        XCTAssertEqual(summaryNote?.title, "HomeKit Configuration Summary")
        XCTAssertTrue(summaryNote?.content.contains("Test Home") ?? false)
        XCTAssertTrue(summaryNote?.content.contains("Total Rooms: 3") ?? false)
        XCTAssertTrue(summaryNote?.content.contains("Total Accessories: 3") ?? false)
        
        // Check room notes
        let livingRoomNote = mockNotesService.savedCustomNotes.first { $0.title.contains("Living Room") }
        XCTAssertNotNil(livingRoomNote)
        XCTAssertEqual(livingRoomNote?.category, "homekit_room")
        XCTAssertTrue(livingRoomNote?.content.contains("Living Room Light") ?? false)
        XCTAssertTrue(livingRoomNote?.content.contains("Philips") ?? false)
        
        let kitchenNote = mockNotesService.savedCustomNotes.first { $0.title.contains("Kitchen") }
        XCTAssertNotNil(kitchenNote)
        XCTAssertEqual(kitchenNote?.category, "homekit_room")
        XCTAssertTrue(kitchenNote?.content.contains("Kitchen Outlet") ?? false)
        XCTAssertTrue(kitchenNote?.content.contains("Eve") ?? false)
        
        // Check unassigned accessory note
        let lockNote = mockNotesService.savedCustomNotes.first { $0.title.contains("Front Door Lock") }
        XCTAssertNotNil(lockNote)
        XCTAssertEqual(lockNote?.category, "homekit_device")
        XCTAssertTrue(lockNote?.content.contains("August") ?? false)
        XCTAssertTrue(lockNote?.content.contains("Locked") ?? false)
        
        // Verify bedroom has no note (no accessories)
        let bedroomNote = mockNotesService.savedCustomNotes.first { $0.title.contains("Bedroom") }
        XCTAssertNil(bedroomNote)
    }
    
    func testHomeKitDiscoveryAndNoteSaving() async throws {
        // Given: A complete HomeKit discovery flow
        let mockHomeKitService = MockHomeKitService()
        let mockNotesService = SharedMockNotesService()
        
        // Set up mock to authorize
        mockHomeKitService.mockAuthorizationResult = true
        
        // Create test data
        let testHome = HomeKitHome(
            id: UUID(),
            name: "My Smart Home",
            isPrimary: true,
            rooms: [
                HomeKitRoom(id: UUID(), name: "Master Bedroom"),
                HomeKitRoom(id: UUID(), name: "Living Room")
            ],
            accessories: [
                HomeKitAccessory(
                    id: UUID(),
                    name: "Bedroom Light",
                    roomId: nil,
                    category: "Lights",
                    manufacturer: "LIFX",
                    model: "A19",
                    isReachable: true,
                    isBridged: false,
                    currentState: "On",
                    services: ["Lightbulb", "Color"]
                )
            ],
            createdAt: Date()
        )
        
        mockHomeKitService.mockDiscoverySummary = HomeKitDiscoverySummary(
            homes: [testHome],
            discoveredAt: Date()
        )
        
        // When: Request authorization and discover homes
        let authorized = await mockHomeKitService.requestAuthorization()
        XCTAssertTrue(authorized)
        XCTAssertTrue(mockHomeKitService.requestAuthorizationCalled)
        
        let summary = try await mockHomeKitService.discoverHomes()
        XCTAssertTrue(mockHomeKitService.discoverHomesCalled)
        XCTAssertEqual(summary.homes.count, 1)
        XCTAssertEqual(summary.homes.first?.name, "My Smart Home")
        
        // Save configuration as notes
        try await mockHomeKitService.saveConfigurationAsNotes(summary: summary)
        XCTAssertTrue(mockHomeKitService.saveConfigurationAsNotesCalled)
        
        // Then: Verify the complete flow worked
        XCTAssertEqual(summary.totalRooms, 2)
        XCTAssertEqual(summary.totalAccessories, 1)
        
        // Verify we can retrieve the homes
        let retrievedHome = await mockHomeKitService.getHome(named: "My Smart Home")
        XCTAssertNotNil(retrievedHome)
        XCTAssertEqual(retrievedHome?.name, "My Smart Home")
        
        let allHomes = await mockHomeKitService.getAllHomes()
        XCTAssertEqual(allHomes.count, 1)
    }
}