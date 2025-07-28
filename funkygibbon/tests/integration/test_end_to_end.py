"""
End-to-end integration tests simulating real usage scenarios.
"""

import json
from datetime import datetime, timedelta, UTC

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from funkygibbon.api.app import create_app
from funkygibbon.repositories import (
    HouseRepository,
    RoomRepository,
    DeviceRepository,
    UserRepository,
    EventRepository
)


@pytest.mark.integration
@pytest.mark.asyncio
class TestEndToEndScenarios:
    """Test complete user scenarios."""
    
    @pytest.fixture
    def app(self):
        """Create test app."""
        return create_app()
    
    async def test_complete_house_setup(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test setting up a complete house with rooms and devices."""
        # Step 1: Create house
        house_response = await async_client.post(
            "/api/v1/houses/",
            params={
                "name": "Smart Home",
                "address": "123 Tech Lane",
                "timezone": "America/Los_Angeles"
            }
        )
        assert house_response.status_code == 200
        house = house_response.json()
        
        # Step 2: Add rooms
        rooms = []
        room_specs = [
            ("Living Room", "living_room", 1),
            ("Kitchen", "kitchen", 1),
            ("Master Bedroom", "bedroom", 2),
            ("Office", "office", 2)
        ]
        
        for name, room_type, floor in room_specs:
            room_response = await async_client.post(
                "/api/v1/rooms/",
                params={
                    "house_id": house["id"],
                    "name": name,
                    "room_type": room_type,
                    "floor": floor
                }
            )
            assert room_response.status_code == 200
            rooms.append(room_response.json())
        
        # Step 3: Add devices to rooms
        device_specs = [
            (rooms[0]["id"], "Smart TV", "entertainment"),
            (rooms[0]["id"], "Ceiling Light", "light"),
            (rooms[1]["id"], "Smart Fridge", "appliance"),
            (rooms[1]["id"], "Overhead Light", "light"),
            (rooms[2]["id"], "Bedside Lamp", "light"),
            (rooms[2]["id"], "Smart Thermostat", "climate"),
            (rooms[3]["id"], "Desk Lamp", "light"),
            (rooms[3]["id"], "Smart Speaker", "entertainment")
        ]
        
        devices = []
        for room_id, name, device_type in device_specs:
            device_response = await async_client.post(
                "/api/v1/devices/",
                params={
                    "room_id": room_id,
                    "name": name,
                    "device_type": device_type
                }
            )
            assert device_response.status_code == 200
            devices.append(device_response.json())
        
        # Step 4: Add users
        user_specs = [
            ("Admin User", "admin@home.com", "admin"),
            ("Family Member", "family@home.com", "member"),
            ("Guest User", "guest@home.com", "guest")
        ]
        
        users = []
        for name, email, role in user_specs:
            user_response = await async_client.post(
                "/api/v1/users/",
                params={
                    "house_id": house["id"],
                    "name": name,
                    "email": email,
                    "role": role
                }
            )
            assert user_response.status_code == 200
            users.append(user_response.json())
        
        # Step 5: Verify complete setup
        house_detail_response = await async_client.get(
            f"/api/v1/houses/{house['id']}",
            params={"include_rooms": True}
        )
        assert house_detail_response.status_code == 200
        house_detail = house_detail_response.json()
        
        assert house_detail["room_count"] == 4
        assert house_detail["device_count"] == 8
        assert house_detail["user_count"] == 3
        assert len(house_detail["rooms"]) == 4
        
        # Verify events were logged
        event_repo = EventRepository()
        events = await event_repo.get_recent_events(db_session, limit=20)
        assert len(events) > 0
    
    async def test_device_state_changes(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test changing device states and tracking history."""
        # Setup
        house_repo = HouseRepository()
        room_repo = RoomRepository()
        device_repo = DeviceRepository()
        user_repo = UserRepository()
        
        house = await house_repo.create(db_session, name="State Test House")
        room = await room_repo.create_with_house_name(
            db_session, house.id, house.name, name="Test Room"
        )
        device = await device_repo.create_with_names(
            db_session,
            room_id=room.id,
            room_name=room.name,
            house_id=house.id,
            house_name=house.name,
            name="Smart Light",
            device_type="light"
        )
        user = await user_repo.create(
            db_session,
            house_id=house.id,
            name="Test User",
            role="member"
        )
        
        # Change states multiple times
        state_changes = [
            ("on_off", "on", {"brightness": 100}),
            ("on_off", "on", {"brightness": 75}),
            ("on_off", "on", {"brightness": 50}),
            ("on_off", "off", {"brightness": 0})
        ]
        
        for state_type, state_value, state_data in state_changes:
            response = await async_client.put(
                f"/api/v1/devices/{device.id}/state",
                params={
                    "state_type": state_type,
                    "state_value": state_value,
                    "user_id": user.id
                },
                json=state_data
            )
            assert response.status_code == 200
        
        # Get device with states
        device_response = await async_client.get(
            f"/api/v1/devices/{device.id}",
            params={"include_states": True}
        )
        assert device_response.status_code == 200
        device_data = device_response.json()
        
        assert len(device_data["states"]) >= 4
        
        # Verify state history
        latest_state = device_data["states"][0]
        assert latest_state["state_value"] == "off"
        assert json.loads(latest_state["state_json"])["brightness"] == 0
    
    async def test_sync_between_clients(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test syncing data between multiple clients."""
        # Client 1: Create initial data
        house_response = await async_client.post(
            "/api/v1/houses/",
            params={"name": "Sync Test House"}
        )
        house = house_response.json()
        
        room_response = await async_client.post(
            "/api/v1/rooms/",
            params={
                "house_id": house["id"],
                "name": "Sync Test Room"
            }
        )
        room = room_response.json()
        
        # Record sync checkpoint
        checkpoint = datetime.now(UTC)
        
        # Client 2: Make changes
        await async_client.put(
            f"/api/v1/houses/{house['id']}",
            params={"name": "Updated House Name"}
        )
        
        await async_client.post(
            "/api/v1/rooms/",
            params={
                "house_id": house["id"],
                "name": "New Room Added"
            }
        )
        
        # Client 1: Get changes since checkpoint
        changes_response = await async_client.get(
            "/api/v1/sync/changes",
            params={"since": checkpoint.isoformat()}
        )
        assert changes_response.status_code == 200
        changes = changes_response.json()
        
        # Verify changes
        assert len(changes["changes"]["houses"]) >= 1
        assert len(changes["changes"]["rooms"]) >= 1
        
        updated_house = next(
            h for h in changes["changes"]["houses"] 
            if h["id"] == house["id"]
        )
        assert updated_house["name"] == "Updated House Name"
        
        new_rooms = [
            r for r in changes["changes"]["rooms"]
            if r["name"] == "New Room Added"
        ]
        assert len(new_rooms) == 1
    
    async def test_conflict_resolution_scenario(self, app, async_client: AsyncClient, db_session: AsyncSession):
        """Test realistic conflict resolution scenario."""
        # Create base entity
        house_response = await async_client.post(
            "/api/v1/houses/",
            params={"name": "Conflict Test House"}
        )
        house = house_response.json()
        
        # Simulate two clients modifying the same entity
        # Client 1 changes
        client1_data = house.copy()
        client1_data["name"] = "Client 1 Name"
        client1_data["address"] = "Client 1 Address"
        client1_data["updated_at"] = datetime.now(UTC).isoformat()
        
        # Client 2 changes (slightly newer)
        client2_data = house.copy()
        client2_data["name"] = "Client 2 Name"
        client2_data["timezone"] = "Europe/London"
        client2_data["updated_at"] = (
            datetime.now(UTC) + timedelta(seconds=5)
        ).isoformat()
        
        # Sync both changes
        sync_request = {
            "houses": [client1_data, client2_data],
            "rooms": [],
            "devices": [],
            "users": []
        }
        
        sync_response = await async_client.post(
            "/api/v1/sync/",
            json=sync_request
        )
        assert sync_response.status_code == 200
        sync_result = sync_response.json()
        
        # Verify conflict was detected and resolved
        assert len(sync_result["conflicts"]) >= 1
        conflict = sync_result["conflicts"][0]
        assert conflict["winner"]["name"] == "Client 2 Name"
        assert conflict["reason"] == "remote has newer timestamp"
        
        # Verify final state
        final_response = await async_client.get(f"/api/v1/houses/{house['id']}")
        final_house = final_response.json()
        assert final_house["name"] == "Client 2 Name"
        assert final_house["timezone"] == "Europe/London"