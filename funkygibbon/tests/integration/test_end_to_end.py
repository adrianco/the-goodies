"""End-to-end integration tests for FunkyGibbon API."""

import pytest
import asyncio
from datetime import datetime, UTC, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from funkygibbon.repositories import HomeRepository, RoomRepository, AccessoryRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestEndToEndScenarios:
    """Test complete user scenarios end-to-end."""
    
    async def test_complete_home_setup(self, async_client: AsyncClient):
        """Test setting up a complete smart home from scratch."""
        # Step 1: Create a new home
        home_response = await async_client.post(
            "/api/v1/homes/",
            params={"name": "Smart Home", "is_primary": True}
        )
        assert home_response.status_code == 200
        home = home_response.json()
        
        # Step 2: Add rooms to the home
        room_names = ["Living Room", "Kitchen", "Master Bedroom", "Guest Bedroom", "Office"]
        rooms = []
        for room_name in room_names:
            room_response = await async_client.post(
                "/api/v1/rooms/",
                params={"home_id": home["id"], "name": room_name}
            )
            assert room_response.status_code == 200
            rooms.append(room_response.json())
        
        # Step 3: Add accessories to rooms
        accessory_configs = [
            ("Living Room", "Smart TV", "LG", "OLED55"),
            ("Living Room", "Ceiling Light", "Philips", "Hue"),
            ("Kitchen", "Smart Fridge", "Samsung", "Family Hub"),
            ("Master Bedroom", "Thermostat", "Nest", "Learning"),
            ("Office", "Smart Lock", "August", "Pro")
        ]
        
        accessories = []
        for room_name, accessory_name, manufacturer, model in accessory_configs:
            # Find the room
            room = next(r for r in rooms if r["name"] == room_name)
            
            accessory_response = await async_client.post(
                "/api/v1/accessories/",
                params={
                    "home_id": home["id"],
                    "room_ids": [room["id"]],
                    "name": accessory_name,
                    "manufacturer": manufacturer,
                    "model": model
                }
            )
            assert accessory_response.status_code == 200
            accessories.append(accessory_response.json())
        
        # Step 4: Add users to the home
        user_specs = [
            ("John Doe", True, True),  # Owner and admin
            ("Jane Doe", True, False),  # Admin but not owner
            ("Guest User", False, False)  # Regular user
        ]
        
        users = []
        for name, is_administrator, is_owner in user_specs:
            user_response = await async_client.post(
                "/api/v1/users/",
                params={
                    "home_id": home["id"],
                    "name": name,
                    "is_administrator": is_administrator,
                    "is_owner": is_owner
                }
            )
            assert user_response.status_code == 200
            users.append(user_response.json())
        
        # Step 5: Verify complete setup
        home_detail_response = await async_client.get(
            f"/api/v1/homes/{home['id']}",
            params={"include_rooms": True}
        )
        assert home_detail_response.status_code == 200
        home_detail = home_detail_response.json()
        
        # Verify data was created properly
        assert home_detail["name"] == "Smart Home"
        assert home_detail["is_primary"] == True
        
        # Events removed - focusing on HomeKit compatibility