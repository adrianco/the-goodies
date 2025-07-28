import pytest
import asyncio
from datetime import datetime, timedelta
import json
from typing import List, Dict, Any

from funkygibbon.core.models import (
    HomeEntity, EntityType, SourceType,
    InbetweeniesRequest, InbetweeniesResponse
)
from funkygibbon.inbetweenies.sync_service import InbetweeniesServer
from funkygibbon.storage.base import StorageInterface


class TestEndToEndSync:
    """End-to-end tests for complete sync workflows"""
    
    @pytest.fixture
    async def wildthing_client(self):
        """Mock WildThing client"""
        return MockWildThingClient()
    
    @pytest.fixture
    async def funkygibbon_server(self):
        """FunkyGibbon server instance"""
        storage = MockStorage()
        server = InbetweeniesServer(storage)
        return server
    
    async def test_full_sync_flow(self, wildthing_client, funkygibbon_server):
        """Test complete sync cycle between WildThing and FunkyGibbon"""
        # Step 1: Create entities on WildThing
        wildthing_entities = [
            HomeEntity(
                entity_type=EntityType.ROOM,
                content={"name": "Living Room", "area": 300},
                user_id="user1"
            ),
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"name": "Smart TV", "brand": "Samsung"},
                user_id="user1"
            )
        ]
        
        for entity in wildthing_entities:
            await wildthing_client.store_entity(entity)
        
        # Step 2: Initiate sync from WildThing
        sync_request = await wildthing_client.prepare_sync_request()
        sync_response = await funkygibbon_server.handle_sync_request(sync_request)
        
        # Step 3: Verify data on FunkyGibbon
        assert len(sync_response.conflicts) == 0
        server_entities = await funkygibbon_server.storage.get_all_entities()
        assert len(server_entities) == 2
        
        # Step 4: Create entities on FunkyGibbon
        server_entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={"name": "Smart Light", "brand": "Philips"},
            user_id="user2"
        )
        await funkygibbon_server.storage.store_entity(server_entity)
        
        # Step 5: Sync back to WildThing
        await wildthing_client.apply_sync_response(sync_response)
        sync_request2 = await wildthing_client.prepare_sync_request()
        sync_response2 = await funkygibbon_server.handle_sync_request(sync_request2)
        
        # Step 6: Verify consistency
        await wildthing_client.apply_sync_response(sync_response2)
        
        client_entities = await wildthing_client.get_all_entities()
        server_entities = await funkygibbon_server.storage.get_all_entities()
        
        assert len(client_entities) == 3
        assert len(server_entities) == 3
        
        # Verify all entities exist on both sides
        client_ids = {e.id for e in client_entities}
        server_ids = {e.id for e in server_entities}
        assert client_ids == server_ids
    
    async def test_conflict_resolution_e2e(self, wildthing_client, funkygibbon_server):
        """Test conflict handling in real sync scenario"""
        # Create same entity on both sides
        entity_id = "shared-device-123"
        
        client_entity = HomeEntity(
            id=entity_id,
            entity_type=EntityType.DEVICE,
            content={"name": "Device", "value": 100, "updated_by": "client"},
            user_id="user1"
        )
        await wildthing_client.store_entity(client_entity)
        
        server_entity = HomeEntity(
            id=entity_id,
            entity_type=EntityType.DEVICE,
            content={"name": "Device", "value": 200, "updated_by": "server"},
            user_id="user2"
        )
        await funkygibbon_server.storage.store_entity(server_entity)
        
        # Wait to ensure different timestamps
        await asyncio.sleep(0.1)
        
        # Modify independently
        client_entity.content["value"] = 150
        client_entity.content["client_update"] = True
        client_entity.last_modified = datetime.utcnow()
        await wildthing_client.store_entity(client_entity)
        
        server_entity.content["value"] = 250
        server_entity.content["server_update"] = True
        server_entity.last_modified = datetime.utcnow()
        await funkygibbon_server.storage.store_entity(server_entity)
        
        # Sync and verify conflict detection
        sync_request = await wildthing_client.prepare_sync_request()
        sync_response = await funkygibbon_server.handle_sync_request(sync_request)
        
        assert len(sync_response.conflicts) > 0
        assert entity_id in sync_response.conflicts
        
        # Apply last-write-wins resolution
        resolved_entity = await self._resolve_conflict_lww(
            client_entity, server_entity
        )
        await wildthing_client.store_entity(resolved_entity)
        await funkygibbon_server.storage.store_entity(resolved_entity)
        
        # Verify final state
        final_client = await wildthing_client.get_entity(entity_id)
        final_server = await funkygibbon_server.storage.get_entity(entity_id)
        
        assert final_client.content == final_server.content
        assert final_client.version == final_server.version
    
    async def test_multi_device_sync(self, funkygibbon_server):
        """Test sync with multiple WildThing devices"""
        # Set up 3 WildThing instances
        devices = [
            MockWildThingClient(device_id=f"device-{i}")
            for i in range(3)
        ]
        
        # Each device creates different entities
        for i, device in enumerate(devices):
            for j in range(2):
                entity = HomeEntity(
                    entity_type=EntityType.ROOM if j == 0 else EntityType.DEVICE,
                    content={
                        "name": f"Entity from device {i}",
                        "index": i * 10 + j
                    },
                    user_id=f"user-{i}"
                )
                await device.store_entity(entity)
        
        # Each device syncs with server
        for device in devices:
            request = await device.prepare_sync_request()
            response = await funkygibbon_server.handle_sync_request(request)
            await device.apply_sync_response(response)
        
        # Sync all devices again to get updates from others
        for device in devices:
            request = await device.prepare_sync_request()
            response = await funkygibbon_server.handle_sync_request(request)
            await device.apply_sync_response(response)
        
        # Verify eventual consistency
        entity_counts = []
        entity_ids_sets = []
        
        for device in devices:
            entities = await device.get_all_entities()
            entity_counts.append(len(entities))
            entity_ids_sets.append({e.id for e in entities})
        
        # All devices should have same number of entities
        assert all(count == 6 for count in entity_counts)
        
        # All devices should have same entities
        for i in range(1, len(entity_ids_sets)):
            assert entity_ids_sets[0] == entity_ids_sets[i]
    
    async def test_incremental_sync(self, wildthing_client, funkygibbon_server):
        """Test incremental sync with vector clocks"""
        # Initial full sync
        initial_entities = [
            HomeEntity(
                entity_type=EntityType.ROOM,
                content={"name": f"Room {i}"},
                user_id="user"
            )
            for i in range(5)
        ]
        
        for entity in initial_entities:
            await wildthing_client.store_entity(entity)
        
        # First sync
        request1 = await wildthing_client.prepare_sync_request()
        response1 = await funkygibbon_server.handle_sync_request(request1)
        await wildthing_client.apply_sync_response(response1)
        
        initial_vector_clock = response1.vector_clock.copy()
        
        # Make incremental changes
        new_entity = HomeEntity(
            entity_type=EntityType.DEVICE,
            content={"name": "New Device"},
            user_id="user"
        )
        await wildthing_client.store_entity(new_entity)
        
        # Incremental sync - should only send new changes
        request2 = await wildthing_client.prepare_sync_request()
        
        # Verify only new changes are included
        assert len(request2.changes) == 1
        assert request2.changes[0]["entity_id"] == new_entity.id
        
        response2 = await funkygibbon_server.handle_sync_request(request2)
        
        # Vector clock should be updated
        assert response2.vector_clock != initial_vector_clock
    
    async def test_large_batch_sync(self, wildthing_client, funkygibbon_server):
        """Test sync performance with large number of entities"""
        # Create 1000 entities
        batch_size = 1000
        entities = []
        
        for i in range(batch_size):
            entity = HomeEntity(
                entity_type=EntityType.DEVICE if i % 2 == 0 else EntityType.ROOM,
                content={
                    "name": f"Entity {i}",
                    "index": i,
                    "metadata": {
                        "created": datetime.utcnow().isoformat(),
                        "tags": [f"tag{j}" for j in range(5)]
                    }
                },
                user_id="batch-test"
            )
            entities.append(entity)
            await wildthing_client.store_entity(entity)
        
        # Measure sync time
        start_time = datetime.utcnow()
        
        request = await wildthing_client.prepare_sync_request()
        response = await funkygibbon_server.handle_sync_request(request)
        await wildthing_client.apply_sync_response(response)
        
        sync_duration = (datetime.utcnow() - start_time).total_seconds()
        
        # Verify all entities synced
        server_entities = await funkygibbon_server.storage.get_all_entities()
        assert len(server_entities) == batch_size
        
        # Performance assertion
        assert sync_duration < 5.0  # Should complete within 5 seconds
        
        # Calculate throughput
        throughput = batch_size / sync_duration
        print(f"Sync throughput: {throughput:.2f} entities/second")
    
    async def test_sync_with_relationships(self, wildthing_client, funkygibbon_server):
        """Test syncing entities with relationships"""
        # Create home structure
        home = HomeEntity(
            entity_type=EntityType.HOME,
            content={"name": "Test Home", "address": "123 Test St"},
            user_id="user"
        )
        
        rooms = [
            HomeEntity(
                entity_type=EntityType.ROOM,
                content={"name": name},
                user_id="user"
            )
            for name in ["Living Room", "Kitchen", "Bedroom"]
        ]
        
        devices = [
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"name": name, "room": room_name},
                user_id="user"
            )
            for name, room_name in [
                ("TV", "Living Room"),
                ("Light", "Living Room"),
                ("Fridge", "Kitchen"),
                ("Bed Light", "Bedroom")
            ]
        ]
        
        # Store all entities
        await wildthing_client.store_entity(home)
        for room in rooms:
            await wildthing_client.store_entity(room)
        for device in devices:
            await wildthing_client.store_entity(device)
        
        # Create relationships
        # Home -> Rooms
        for room in rooms:
            await wildthing_client.store_relationship(home.id, room.id, "contains")
        
        # Rooms -> Devices
        room_map = {r.content["name"]: r.id for r in rooms}
        for device in devices:
            room_name = device.content["room"]
            room_id = room_map[room_name]
            await wildthing_client.store_relationship(device.id, room_id, "located_in")
        
        # Sync everything
        request = await wildthing_client.prepare_sync_request()
        response = await funkygibbon_server.handle_sync_request(request)
        
        # Verify structure on server
        server_home = await funkygibbon_server.storage.get_entities_by_type(
            EntityType.HOME, "user"
        )
        assert len(server_home) == 1
        
        server_rooms = await funkygibbon_server.storage.get_entities_by_type(
            EntityType.ROOM, "user"
        )
        assert len(server_rooms) == 3
        
        server_devices = await funkygibbon_server.storage.get_entities_by_type(
            EntityType.DEVICE, "user"
        )
        assert len(server_devices) == 4
    
    async def test_sync_recovery_after_failure(self, wildthing_client, funkygibbon_server):
        """Test sync recovery after partial failure"""
        # Create entities
        entities = [
            HomeEntity(
                entity_type=EntityType.DEVICE,
                content={"name": f"Device {i}", "batch": 1},
                user_id="user"
            )
            for i in range(10)
        ]
        
        for entity in entities:
            await wildthing_client.store_entity(entity)
        
        # Simulate partial sync (only first 5 succeed)
        partial_request = await wildthing_client.prepare_sync_request()
        partial_request.changes = partial_request.changes[:5]
        
        partial_response = await funkygibbon_server.handle_sync_request(partial_request)
        await wildthing_client.mark_synced(partial_request.changes)
        
        # Verify only partial data on server
        server_entities = await funkygibbon_server.storage.get_all_entities()
        assert len(server_entities) == 5
        
        # Complete sync with remaining entities
        recovery_request = await wildthing_client.prepare_sync_request()
        assert len(recovery_request.changes) == 5  # Only unsynced entities
        
        recovery_response = await funkygibbon_server.handle_sync_request(recovery_request)
        await wildthing_client.apply_sync_response(recovery_response)
        
        # Verify all entities now on server
        server_entities = await funkygibbon_server.storage.get_all_entities()
        assert len(server_entities) == 10
    
    # Helper methods
    
    async def _resolve_conflict_lww(self, entity1: HomeEntity, entity2: HomeEntity) -> HomeEntity:
        """Last-write-wins conflict resolution"""
        if entity1.last_modified > entity2.last_modified:
            return entity1
        else:
            return entity2


class MockWildThingClient:
    """Mock WildThing client for testing"""
    
    def __init__(self, device_id: str = "test-device"):
        self.device_id = device_id
        self.user_id = "test-user"
        self.entities: Dict[str, HomeEntity] = {}
        self.relationships: List[Dict[str, Any]] = []
        self.vector_clock: Dict[str, str] = {}
        self.synced_versions: set = set()
    
    async def store_entity(self, entity: HomeEntity):
        self.entities[entity.id] = entity
    
    async def get_entity(self, entity_id: str) -> HomeEntity:
        return self.entities.get(entity_id)
    
    async def get_all_entities(self) -> List[HomeEntity]:
        return list(self.entities.values())
    
    async def store_relationship(self, from_id: str, to_id: str, rel_type: str):
        self.relationships.append({
            "from_id": from_id,
            "to_id": to_id,
            "type": rel_type
        })
    
    async def prepare_sync_request(self) -> InbetweeniesRequest:
        changes = []
        
        for entity in self.entities.values():
            if entity.version not in self.synced_versions:
                changes.append({
                    "change_type": "create" if len(entity.parent_versions) == 0 else "update",
                    "entity_id": entity.id,
                    "entity_version": entity.version,
                    "entity_type": entity.entity_type.value,
                    "content": entity.content,
                    "timestamp": entity.last_modified.isoformat() + "Z"
                })
        
        return InbetweeniesRequest(
            device_id=self.device_id,
            user_id=self.user_id,
            vector_clock=self.vector_clock,
            changes=changes
        )
    
    async def apply_sync_response(self, response: InbetweeniesResponse):
        # Apply incoming changes
        for change in response.changes:
            entity = HomeEntity(
                id=change["entity_id"],
                version=change.get("entity_version", "unknown"),
                entity_type=EntityType(change.get("entity_type", "device")),
                content=change.get("content", {}),
                user_id=self.user_id
            )
            self.entities[entity.id] = entity
        
        # Update vector clock
        self.vector_clock = response.vector_clock
    
    async def mark_synced(self, changes: List[Dict[str, Any]]):
        for change in changes:
            self.synced_versions.add(change["entity_version"])


class MockStorage(StorageInterface):
    """Mock storage for testing"""
    
    def __init__(self):
        self.entities: Dict[str, HomeEntity] = {}
        self.vector_clock: Dict[str, str] = {}
    
    async def store_entity(self, entity: HomeEntity):
        self.entities[entity.id] = entity
    
    async def get_entity(self, entity_id: str) -> HomeEntity:
        return self.entities.get(entity_id)
    
    async def get_all_entities(self) -> List[HomeEntity]:
        return list(self.entities.values())
    
    async def get_entities_by_type(self, entity_type: EntityType, user_id: str) -> List[HomeEntity]:
        return [
            e for e in self.entities.values()
            if e.entity_type == entity_type and e.user_id == user_id
        ]
    
    async def delete_entity(self, entity_id: str, version: str = None):
        if entity_id in self.entities:
            del self.entities[entity_id]
    
    async def get_vector_clock(self) -> Dict[str, str]:
        return self.vector_clock.copy()
    
    async def update_vector_clock(self, clock: Dict[str, str]):
        self.vector_clock = clock.copy()