"""
Test HomeKit models integration.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from funkygibbon.models import Home, Room, Accessory, Service, Characteristic, User, accessory_rooms


@pytest.mark.asyncio
async def test_create_home(async_session):
    """Test creating a home."""
    home = Home(
        id="test-home-1",
        name="Test Home",
        is_primary=True
    )
    async_session.add(home)
    await async_session.commit()
    
    # Verify it was saved
    result = await async_session.execute(
        select(Home).where(Home.id == "test-home-1")
    )
    saved_home = result.scalar_one()
    assert saved_home.name == "Test Home"
    assert saved_home.is_primary is True


@pytest.mark.asyncio
async def test_create_room(async_session, test_home):
    """Test creating a room."""
    room = Room(
        id="test-room-1",
        home_id=test_home.id,
        name="Living Room"
    )
    async_session.add(room)
    await async_session.commit()
    
    # Verify it was saved
    result = await async_session.execute(
        select(Room).where(Room.id == "test-room-1")
    )
    saved_room = result.scalar_one()
    assert saved_room.name == "Living Room"
    assert saved_room.home_id == test_home.id


@pytest.mark.asyncio
async def test_create_accessory(async_session, test_home, test_room):
    """Test creating an accessory."""
    accessory = Accessory(
        id="test-acc-1",
        home_id=test_home.id,
        name="Smart Light",
        manufacturer="Philips",
        model="Hue White",
        serial_number="SN-12345",
        firmware_version="1.0.0",
        is_reachable=True,
        is_blocked=False,
        is_bridge=False
    )
    async_session.add(accessory)
    
    # Link to room
    await async_session.execute(
        accessory_rooms.insert().values(
            accessory_id=accessory.id,
            room_id=test_room.id
        )
    )
    
    await async_session.commit()
    
    # Verify it was saved
    result = await async_session.execute(
        select(Accessory).where(Accessory.id == "test-acc-1")
    )
    saved_acc = result.scalar_one()
    assert saved_acc.name == "Smart Light"
    assert saved_acc.manufacturer == "Philips"


@pytest.mark.asyncio
async def test_create_service_with_characteristics(async_session, test_accessory):
    """Test creating a service with characteristics."""
    service = Service(
        id="test-svc-1",
        accessory_id=test_accessory.id,
        service_type="lightbulb",
        name="Light",
        is_primary=True,
        is_user_interactive=True
    )
    async_session.add(service)
    await async_session.flush()
    
    # Create characteristics
    char1 = Characteristic(
        id="test-char-1",
        service_id=service.id,
        characteristic_type="power_state",
        value="true",
        format="bool",
        is_readable=True,
        is_writable=True,
        supports_event_notification=True
    )
    
    char2 = Characteristic(
        id="test-char-2",
        service_id=service.id,
        characteristic_type="brightness",
        value="75",
        format="uint8",
        unit="percentage",
        min_value=0,
        max_value=100,
        is_readable=True,
        is_writable=True,
        supports_event_notification=True
    )
    
    async_session.add_all([char1, char2])
    await async_session.commit()
    
    # Verify service
    result = await async_session.execute(
        select(Service).where(Service.id == "test-svc-1")
    )
    saved_svc = result.scalar_one()
    assert saved_svc.service_type == "lightbulb"
    
    # Verify characteristics
    result = await async_session.execute(
        select(Characteristic).where(Characteristic.service_id == service.id)
    )
    chars = result.scalars().all()
    assert len(chars) == 2
    assert any(c.characteristic_type == "power_state" for c in chars)
    assert any(c.characteristic_type == "brightness" for c in chars)


@pytest.mark.asyncio
async def test_create_user(async_session, test_home):
    """Test creating a user."""
    user = User(
        id="test-user-1",
        home_id=test_home.id,
        name="John Doe",
        is_administrator=True,
        is_owner=False,
        remote_access_allowed=True
    )
    async_session.add(user)
    await async_session.commit()
    
    # Verify it was saved
    result = await async_session.execute(
        select(User).where(User.id == "test-user-1")
    )
    saved_user = result.scalar_one()
    assert saved_user.name == "John Doe"
    assert saved_user.is_administrator is True
    assert saved_user.is_owner is False


@pytest.mark.asyncio
async def test_homekit_model_relationships(async_session):
    """Test full HomeKit model relationships."""
    # Create home
    home = Home(id="h1", name="Smart Home", is_primary=True)
    async_session.add(home)
    
    # Create rooms
    room1 = Room(id="r1", home_id=home.id, name="Living Room")
    room2 = Room(id="r2", home_id=home.id, name="Bedroom")
    async_session.add_all([room1, room2])
    
    # Create accessories
    acc1 = Accessory(
        id="a1", home_id=home.id, name="Light 1",
        manufacturer="Philips", model="Hue", serial_number="SN1",
        firmware_version="1.0", is_reachable=True, is_blocked=False, is_bridge=False
    )
    acc2 = Accessory(
        id="a2", home_id=home.id, name="Thermostat",
        manufacturer="Ecobee", model="Smart", serial_number="SN2",
        firmware_version="1.0", is_reachable=True, is_blocked=False, is_bridge=False
    )
    async_session.add_all([acc1, acc2])
    
    # Link accessories to rooms
    await async_session.execute(
        accessory_rooms.insert().values([
            {"accessory_id": acc1.id, "room_id": room1.id},
            {"accessory_id": acc2.id, "room_id": room1.id}
        ])
    )
    
    # Create services
    svc1 = Service(
        id="s1", accessory_id=acc1.id, service_type="lightbulb",
        name="Light", is_primary=True, is_user_interactive=True
    )
    svc2 = Service(
        id="s2", accessory_id=acc2.id, service_type="thermostat",
        name="Thermostat", is_primary=True, is_user_interactive=True
    )
    async_session.add_all([svc1, svc2])
    
    # Create users
    user1 = User(
        id="u1", home_id=home.id, name="Owner",
        is_administrator=True, is_owner=True, remote_access_allowed=True
    )
    user2 = User(
        id="u2", home_id=home.id, name="Guest",
        is_administrator=False, is_owner=False, remote_access_allowed=False
    )
    async_session.add_all([user1, user2])
    
    await async_session.commit()
    
    # Verify everything was created
    homes = await async_session.execute(select(Home))
    assert len(homes.scalars().all()) == 1
    
    rooms = await async_session.execute(select(Room))
    assert len(rooms.scalars().all()) == 2
    
    accessories = await async_session.execute(select(Accessory))
    assert len(accessories.scalars().all()) == 2
    
    services = await async_session.execute(select(Service))
    assert len(services.scalars().all()) == 2
    
    users = await async_session.execute(select(User))
    assert len(users.scalars().all()) == 2