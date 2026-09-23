/*
 * CONTEXT & PURPOSE:
 * HomeKitModels.swift defines the data models for HomeKit entities. These models represent
 * homes, rooms, and accessories from HomeKit and provide a bridge to convert them into
 * notes for the NotesService. This enables the app to store HomeKit configuration as
 * persistent notes that can be used for AI context and user reference.
 *
 * DECISION HISTORY:
 * - 2025-07-23: Initial implementation
 *   - Models for Home, Room, and Accessory entities
 *   - Support for converting HomeKit objects to our domain models
 *   - Methods to generate note content from HomeKit data
 *   - Structured format for summary and individual notes
 *   - Codable support for potential future persistence
 *
 * FUTURE UPDATES:
 * - [Add future changes and decisions here]
 */

//
//  HomeKitModels.swift
//  C11SHouse
//
//  Data models for HomeKit entities and note conversion
//

import Foundation
import HomeKit

/// Represents a HomeKit home with its configuration
struct HomeKitHome: Codable {
    let id: UUID
    let name: String
    let isPrimary: Bool
    let rooms: [HomeKitRoom]
    let accessories: [HomeKitAccessory]
    let createdAt: Date
    
    init(from home: HMHome) {
        self.id = home.uniqueIdentifier
        self.name = home.name
        self.isPrimary = home.isPrimary
        self.rooms = home.rooms.map { HomeKitRoom(from: $0) }
        self.accessories = home.accessories.map { HomeKitAccessory(from: $0) }
        self.createdAt = Date()
    }
    
    // Memberwise initializer for testing
    init(
        id: UUID,
        name: String,
        isPrimary: Bool,
        rooms: [HomeKitRoom],
        accessories: [HomeKitAccessory],
        createdAt: Date
    ) {
        self.id = id
        self.name = name
        self.isPrimary = isPrimary
        self.rooms = rooms
        self.accessories = accessories
        self.createdAt = createdAt
    }
    
    /// Generate a summary note for the entire home configuration
    func generateSummaryNote() -> String {
        var summary = "🏠 HomeKit Configuration for \(name)\n\n"
        
        if isPrimary {
            summary += "This is your primary home.\n\n"
        }
        
        summary += "📊 Overview:\n"
        summary += "• Total Rooms: \(rooms.count)\n"
        summary += "• Total Accessories: \(accessories.count)\n\n"
        
        if !rooms.isEmpty {
            summary += "🏠 Rooms:\n"
            for room in rooms.sorted(by: { $0.name < $1.name }) {
                let accessoryCount = accessories.filter { $0.roomId == room.id }.count
                summary += "• \(room.name) (\(accessoryCount) accessories)\n"
            }
            summary += "\n"
        }
        
        // Group accessories by category
        let accessoriesByCategory = Dictionary(grouping: accessories) { $0.category }
        
        if !accessoriesByCategory.isEmpty {
            summary += "🔌 Accessories by Type:\n"
            for (category, items) in accessoriesByCategory.sorted(by: { $0.key < $1.key }) {
                summary += "• \(category): \(items.count)\n"
            }
        }
        
        return summary
    }
}

/// Represents a room in HomeKit
struct HomeKitRoom: Codable {
    let id: UUID
    let name: String
    
    init(from room: HMRoom) {
        self.id = room.uniqueIdentifier
        self.name = room.name
    }
    
    // Memberwise initializer for testing
    init(id: UUID, name: String) {
        self.id = id
        self.name = name
    }
    
    /// Generate a note for this room with its accessories
    func generateNote(with accessories: [HomeKitAccessory]) -> String {
        var note = "🏠 Room: \(name)\n\n"
        
        if accessories.isEmpty {
            note += "No accessories configured in this room yet."
        } else {
            note += "🔌 Accessories (\(accessories.count)):\n"
            
            // Group by category
            let grouped = Dictionary(grouping: accessories) { $0.category }
            
            for (category, items) in grouped.sorted(by: { $0.key < $1.key }) {
                note += "\n\(category):\n"
                for accessory in items.sorted(by: { $0.name < $1.name }) {
                    note += "• \(accessory.name)"
                    if accessory.isReachable {
                        note += " ✅"
                    } else {
                        note += " ❌ (unreachable)"
                    }
                    if let state = accessory.currentState {
                        note += " - \(state)"
                    }
                    note += "\n"
                }
            }
        }
        
        return note
    }
}

/// Represents an accessory in HomeKit
struct HomeKitAccessory: Codable {
    let id: UUID
    let name: String
    let roomId: UUID?
    let category: String
    let manufacturer: String?
    let model: String?
    let isReachable: Bool
    let isBridged: Bool
    let currentState: String?
    let services: [String]
    
    init(from accessory: HMAccessory) {
        self.id = accessory.uniqueIdentifier
        self.name = accessory.name
        self.roomId = accessory.room?.uniqueIdentifier
        self.category = Self.categoryName(for: accessory.category)
        self.manufacturer = accessory.manufacturer
        self.model = accessory.model
        self.isReachable = accessory.isReachable
        self.isBridged = accessory.isBridged
        self.currentState = Self.extractCurrentState(from: accessory)
        self.services = accessory.services.compactMap { service in
            guard !service.isPrimaryService else { return nil }
            return service.name
        }
    }
    
    // Memberwise initializer for testing
    init(
        id: UUID,
        name: String,
        roomId: UUID?,
        category: String,
        manufacturer: String?,
        model: String?,
        isReachable: Bool,
        isBridged: Bool,
        currentState: String?,
        services: [String]
    ) {
        self.id = id
        self.name = name
        self.roomId = roomId
        self.category = category
        self.manufacturer = manufacturer
        self.model = model
        self.isReachable = isReachable
        self.isBridged = isBridged
        self.currentState = currentState
        self.services = services
    }
    
    /// Generate a note for this accessory
    func generateNote() -> String {
        var note = "🔌 \(name)\n\n"
        
        note += "📋 Details:\n"
        note += "• Type: \(category)\n"
        
        if let manufacturer = manufacturer {
            note += "• Manufacturer: \(manufacturer)\n"
        }
        
        if let model = model {
            note += "• Model: \(model)\n"
        }
        
        note += "• Status: "
        if isReachable {
            note += "✅ Reachable\n"
        } else {
            note += "❌ Unreachable\n"
        }
        
        if isBridged {
            note += "• Connection: Via Bridge\n"
        }
        
        if let state = currentState {
            note += "• Current State: \(state)\n"
        }
        
        if !services.isEmpty {
            note += "\n🔧 Services:\n"
            for service in services {
                note += "• \(service)\n"
            }
        }
        
        return note
    }
    
    private static func categoryName(for category: HMAccessoryCategory) -> String {
        switch category.categoryType {
        case HMAccessoryCategoryTypeLightbulb:
            return "Lights"
        case HMAccessoryCategoryTypeSwitch:
            return "Switches"
        case HMAccessoryCategoryTypeThermostat:
            return "Thermostats"
        case HMAccessoryCategoryTypeSensor:
            return "Sensors"
        case HMAccessoryCategoryTypeDoor:
            return "Doors"
        case HMAccessoryCategoryTypeWindow:
            return "Windows"
        case HMAccessoryCategoryTypeFan:
            return "Fans"
        case HMAccessoryCategoryTypeGarageDoorOpener:
            return "Garage Doors"
        case HMAccessoryCategoryTypeDoorLock:
            return "Locks"
        case HMAccessoryCategoryTypeOutlet:
            return "Outlets"
        case HMAccessoryCategoryTypeTelevision:
            return "TVs"
        case HMAccessoryCategoryTypeSpeaker:
            return "Speakers"
        case HMAccessoryCategoryTypeIPCamera:
            return "Cameras"
        case HMAccessoryCategoryTypeVideoDoorbell:
            return "Video Doorbells"
        case HMAccessoryCategoryTypeAirPurifier:
            return "Air Purifiers"
        case HMAccessoryCategoryTypeAirHeater:
            return "Heaters"
        case HMAccessoryCategoryTypeAirConditioner:
            return "Air Conditioners"
        case HMAccessoryCategoryTypeAirHumidifier:
            return "Humidifiers"
        case HMAccessoryCategoryTypeAirDehumidifier:
            return "Dehumidifiers"
        case HMAccessoryCategoryTypeBridge:
            return "Bridges"
        case HMAccessoryCategoryTypeSecuritySystem:
            return "Security Systems"
        case HMAccessoryCategoryTypeProgrammableSwitch:
            return "Programmable Switches"
        case HMAccessoryCategoryTypeRangeExtender:
            return "Range Extenders"
        case HMAccessoryCategoryTypeFaucet:
            return "Faucets"
        case HMAccessoryCategoryTypeShowerHead:
            return "Shower Heads"
        case HMAccessoryCategoryTypeSprinkler:
            return "Sprinklers"
        default:
            // For any truly unknown categories, use the localized description
            // This ensures we always provide a specific name rather than generic "Other"
            let categoryDescription = category.localizedDescription
            // If we have a meaningful description, use it
            if !categoryDescription.isEmpty && categoryDescription != "Unknown" {
                return categoryDescription
            }
            // As a last resort, extract from the category type string
            let typeString = String(describing: category.categoryType)
            if typeString.hasPrefix("HMAccessoryCategoryType") {
                let name = typeString.dropFirst("HMAccessoryCategoryType".count)
                // Convert from CamelCase to Title Case
                let readable = name.unicodeScalars.reduce("") { result, scalar in
                    if CharacterSet.uppercaseLetters.contains(scalar) && !result.isEmpty {
                        return result + " " + String(scalar)
                    }
                    return result + String(scalar)
                }
                return readable.isEmpty ? "Accessories" : readable
            }
            return "Accessories"
        }
    }
    
    private static func extractCurrentState(from accessory: HMAccessory) -> String? {
        // This is a simplified state extraction
        // In a full implementation, you would check specific characteristics
        for service in accessory.services {
            for characteristic in service.characteristics {
                if characteristic.characteristicType == HMCharacteristicTypePowerState {
                    if let value = characteristic.value as? Bool {
                        return value ? "On" : "Off"
                    }
                }
                if characteristic.characteristicType == HMCharacteristicTypeBrightness {
                    if let value = characteristic.value as? Int {
                        return "Brightness: \(value)%"
                    }
                }
                if characteristic.characteristicType == HMCharacteristicTypeTargetTemperature {
                    if let value = characteristic.value as? Double {
                        return "Target Temp: \(Int(value))°"
                    }
                }
            }
        }
        return nil
    }
}

/// Configuration summary for HomeKit discovery
struct HomeKitDiscoverySummary {
    let homes: [HomeKitHome]
    let discoveredAt: Date
    
    var totalRooms: Int {
        homes.reduce(0) { $0 + $1.rooms.count }
    }
    
    var totalAccessories: Int {
        homes.reduce(0) { $0 + $1.accessories.count }
    }
    
    func generateFullSummary() -> String {
        var summary = "🏡 HomeKit Discovery Summary\n"
        summary += "Discovered at: \(DateFormatter.localizedString(from: discoveredAt, dateStyle: .medium, timeStyle: .short))\n\n"
        
        if homes.isEmpty {
            summary += "No HomeKit homes configured yet.\n"
            summary += "Add homes and accessories in the Home app to get started."
        } else {
            summary += "Found \(homes.count) home(s) with \(totalRooms) rooms and \(totalAccessories) accessories.\n\n"
            
            for (index, home) in homes.enumerated() {
                if index > 0 {
                    summary += "\n" + String(repeating: "-", count: 40) + "\n\n"
                }
                summary += home.generateSummaryNote()
            }
        }
        
        return summary
    }
}