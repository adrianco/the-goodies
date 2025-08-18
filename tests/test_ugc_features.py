"""
Test suite for User Generated Content (UGC) features

Tests the new functionality for:
- APP entity type
- BLOB storage for PDFs and photos
- User notes storage
- Mitsubishi thermostat integration
- PDF summarization
- Photo metadata extraction
"""

import pytest
import pytest_asyncio
import asyncio
import base64
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select, text

from inbetweenies.models import (
    Base, Entity, EntityType, SourceType,
    EntityRelationship, RelationshipType,
    Blob, BlobType, BlobStatus
)
from inbetweenies.utils.pdf_summarizer import (
    create_manual_summary, extract_photo_metadata,
    link_manual_to_device
)


@pytest_asyncio.fixture
async def async_session():
    """Create a test database session"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session_maker() as session:
        yield session
        await session.rollback()

    await engine.dispose()


class TestAppEntityType:
    """Test APP entity type functionality"""

    @pytest.mark.asyncio
    async def test_create_app_entity(self, async_session):
        """Test creating an APP entity"""
        app = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.APP,
            name="Test App",
            content={
                "platform": "iOS",
                "url_scheme": "testapp://",
                "icon": "app.icon",
                "description": "Test application"
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(app)
        await async_session.commit()

        # Verify app was created
        result = await async_session.execute(
            select(Entity).where(Entity.entity_type == EntityType.APP)
        )
        apps = result.scalars().all()

        assert len(apps) == 1
        assert apps[0].name == "Test App"
        assert apps[0].content["platform"] == "iOS"
        assert apps[0].content["url_scheme"] == "testapp://"

    @pytest.mark.asyncio
    async def test_link_device_to_app(self, async_session):
        """Test linking a device to an app using CONTROLLED_BY_APP relationship"""
        # Create device
        device = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Smart Thermostat",
            content={"manufacturer": "Test Corp", "model": "T-1000"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        # Create app
        app = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.APP,
            name="Control App",
            content={"platform": "iOS"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(device)
        async_session.add(app)
        await async_session.flush()

        # Create relationship
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=device.id,
            from_entity_version=device.version,
            to_entity_id=app.id,
            to_entity_version=app.version,
            relationship_type=RelationshipType.CONTROLLED_BY_APP,
            properties={"integration": "wifi"},
            user_id="test-user"
        )

        async_session.add(relationship)
        await async_session.commit()

        # Verify relationship
        result = await async_session.execute(
            select(EntityRelationship).where(
                EntityRelationship.relationship_type == RelationshipType.CONTROLLED_BY_APP
            )
        )
        relationships = result.scalars().all()

        assert len(relationships) == 1
        assert relationships[0].from_entity_id == device.id
        assert relationships[0].to_entity_id == app.id
        assert relationships[0].properties["integration"] == "wifi"


class TestBlobStorage:
    """Test BLOB storage functionality"""

    @pytest.mark.asyncio
    async def test_create_blob(self, async_session):
        """Test creating a BLOB entity"""
        # Create test data
        test_data = b"This is test PDF content"
        checksum = hashlib.sha256(test_data).hexdigest()

        blob = Blob(
            id=str(uuid4()),
            name="test_document.pdf",
            blob_type=BlobType.PDF,
            mime_type="application/pdf",
            size=len(test_data),
            data=test_data,
            blob_metadata={"pages": 10, "author": "Test Author"},
            checksum=checksum,
            sync_status=BlobStatus.PENDING_UPLOAD,
            user_id="test-user"
        )

        async_session.add(blob)
        await async_session.commit()

        # Verify blob was created
        result = await async_session.execute(
            select(Blob).where(Blob.name == "test_document.pdf")
        )
        blobs = result.scalars().all()

        assert len(blobs) == 1
        assert blobs[0].size == len(test_data)
        assert blobs[0].checksum == checksum
        assert blobs[0].blob_type == BlobType.PDF
        assert blobs[0].data == test_data

    @pytest.mark.asyncio
    async def test_blob_set_data_method(self, async_session):
        """Test the set_data method of Blob"""
        blob = Blob(
            id=str(uuid4()),
            name="photo.jpeg",
            blob_type=BlobType.JPEG,
            mime_type="image/jpeg",
            size=0,
            user_id="test-user"
        )

        # Set data using the method
        test_data = b"JPEG binary data here"
        blob.set_data(test_data)

        assert blob.size == len(test_data)
        assert blob.data == test_data
        assert blob.checksum == hashlib.sha256(test_data).hexdigest()
        assert blob.sync_status == BlobStatus.PENDING_UPLOAD

        async_session.add(blob)
        await async_session.commit()

    @pytest.mark.asyncio
    async def test_blob_sync_status(self, async_session):
        """Test blob sync status transitions"""
        blob = Blob(
            id=str(uuid4()),
            name="document.pdf",
            blob_type=BlobType.PDF,
            size=1024,
            sync_status=BlobStatus.PENDING_UPLOAD,
            user_id="test-user"
        )

        async_session.add(blob)
        await async_session.flush()

        # Mark as uploaded
        blob.mark_uploaded("https://server.com/blob/123")

        assert blob.sync_status == BlobStatus.UPLOADED
        assert blob.server_url == "https://server.com/blob/123"
        assert blob.last_sync_at is not None

        # Mark as downloaded
        blob.mark_downloaded()

        assert blob.sync_status == BlobStatus.DOWNLOADED
        assert blob.last_sync_at is not None

        await async_session.commit()


class TestUserNotes:
    """Test user-provided notes functionality"""

    @pytest.mark.asyncio
    async def test_create_user_note(self, async_session):
        """Test creating a NOTE entity with user-provided content"""
        note = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.NOTE,
            name="Installation Notes",
            content={
                "content": "Thermostat installed on kitchen wall, controls multiple zones",
                "category": "user_provided",
                "device_references": ["device-123", "device-456"],
                "created": datetime.now(timezone.utc).isoformat()
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(note)
        await async_session.commit()

        # Verify note was created
        result = await async_session.execute(
            select(Entity).where(Entity.entity_type == EntityType.NOTE)
        )
        notes = result.scalars().all()

        assert len(notes) == 1
        assert notes[0].name == "Installation Notes"
        assert notes[0].content["category"] == "user_provided"
        assert len(notes[0].content["device_references"]) == 2

    @pytest.mark.asyncio
    async def test_link_note_to_device(self, async_session):
        """Test linking a note to a device"""
        # Create device
        device = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Test Device",
            content={"model": "TD-100"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        # Create note
        note = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.NOTE,
            name="Device Notes",
            content={"content": "Important device information"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(device)
        async_session.add(note)
        await async_session.flush()

        # Create relationship
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=note.id,
            from_entity_version=note.version,
            to_entity_id=device.id,
            to_entity_version=device.version,
            relationship_type=RelationshipType.DOCUMENTED_BY,
            properties={"note_type": "user_provided"},
            user_id="test-user"
        )

        async_session.add(relationship)
        await async_session.commit()

        # Verify relationship
        result = await async_session.execute(
            select(EntityRelationship).where(
                EntityRelationship.from_entity_id == note.id
            )
        )
        relationships = result.scalars().all()

        assert len(relationships) == 1
        assert relationships[0].to_entity_id == device.id
        assert relationships[0].relationship_type == RelationshipType.DOCUMENTED_BY


class TestPDFSummarization:
    """Test PDF summarization functionality"""

    def test_create_manual_summary(self):
        """Test creating a manual summary from PDF data"""
        # Create fake PDF data
        pdf_data = b"PDF content goes here" * 100
        filename = "PAR-42MAAUB_Instruction Book.pdf"

        summary = create_manual_summary(pdf_data, filename)

        assert summary["original_filename"] == filename
        assert summary["file_size"] == len(pdf_data)
        assert summary["checksum"] == hashlib.sha256(pdf_data).hexdigest()
        assert summary["model_number"] == "PAR-42MAAUB"  # Extracted from filename
        assert summary["document_type"] == "instruction_manual"
        assert "summary" in summary

    def test_extract_photo_metadata(self):
        """Test extracting metadata from photo data"""
        # Create fake photo data
        photo_data = b"JPEG binary data" * 50
        filename = "PVFY-Serial_Number.jpeg"

        metadata = extract_photo_metadata(photo_data, filename)

        assert metadata["original_filename"] == filename
        assert metadata["file_size"] == len(photo_data)
        assert metadata["checksum"] == hashlib.sha256(photo_data).hexdigest()
        assert metadata["photo_type"] == "serial_number"
        assert metadata["format"] == "JPEG"
        assert metadata["mime_type"] == "image/jpeg"

    def test_link_manual_to_device(self):
        """Test linking manual metadata to a device"""
        manual_metadata = {
            "summary": "Test summary",
            "original_filename": "manual.pdf",
            "file_size": 1024,
            "checksum": "abc123"
        }

        linked = link_manual_to_device(manual_metadata, "Test Device")

        assert linked["device_name"] == "Test Device"
        assert linked["relationship_type"] == "DOCUMENTED_BY"
        assert linked["summary"] == "Test summary"


class TestMitsubishiIntegration:
    """Test Mitsubishi thermostat integration"""

    @pytest.mark.asyncio
    async def test_create_mitsubishi_thermostat(self, async_session):
        """Test creating Mitsubishi thermostat entity"""
        thermostat = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Mitsubishi PAR-42MAA Thermostat",
            content={
                "manufacturer": "Mitsubishi",
                "model": "PAR-42MAAUB",
                "type": "climate",
                "capabilities": ["temperature", "fan_speed", "mode", "schedule", "remote_control"],
                "network": "proprietary",
                "location_notes": "Kitchen wall",
                "remote_app": "Mitsubishi Comfort"
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(thermostat)
        await async_session.commit()

        # Verify thermostat was created
        result = await async_session.execute(
            select(Entity).where(
                Entity.name == "Mitsubishi PAR-42MAA Thermostat"
            )
        )
        devices = result.scalars().all()

        assert len(devices) == 1
        assert devices[0].content["manufacturer"] == "Mitsubishi"
        assert devices[0].content["model"] == "PAR-42MAAUB"
        assert "remote_control" in devices[0].content["capabilities"]
        assert devices[0].content["remote_app"] == "Mitsubishi Comfort"

    @pytest.mark.asyncio
    async def test_link_mitsubishi_to_comfort_app(self, async_session):
        """Test linking Mitsubishi thermostat to Comfort app"""
        # Create thermostat
        thermostat = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="Mitsubishi Thermostat",
            content={"model": "PAR-42MAAUB"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        # Create Comfort app
        comfort_app = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.APP,
            name="Mitsubishi Comfort",
            content={
                "platform": "iOS",
                "url_scheme": "mitsubishicomfort://"
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(thermostat)
        async_session.add(comfort_app)
        await async_session.flush()

        # Create relationship
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=thermostat.id,
            from_entity_version=thermostat.version,
            to_entity_id=comfort_app.id,
            to_entity_version=comfort_app.version,
            relationship_type=RelationshipType.CONTROLLED_BY_APP,
            properties={
                "integration": "wifi_adapter",
                "features": ["remote_control", "scheduling", "energy_monitoring"]
            },
            user_id="test-user"
        )

        async_session.add(relationship)
        await async_session.commit()

        # Verify relationship
        result = await async_session.execute(
            select(EntityRelationship).where(
                EntityRelationship.from_entity_id == thermostat.id
            )
        )
        relationships = result.scalars().all()

        assert len(relationships) == 1
        assert relationships[0].to_entity_id == comfort_app.id
        assert relationships[0].relationship_type == RelationshipType.CONTROLLED_BY_APP
        assert "remote_control" in relationships[0].properties["features"]


class TestPhotoDocumentation:
    """Test photo documentation functionality"""

    @pytest.mark.asyncio
    async def test_create_photo_documentation(self, async_session):
        """Test creating photo documentation notes with blob references"""
        photo_note = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.NOTE,
            name="Equipment Photos",
            content={
                "content": "Photos of HVAC equipment",
                "category": "photo_documentation",
                "photo_filenames": ["unit1.jpeg", "unit2.jpeg"],
                "has_blob": True,
                "blob_references": ["blob_unit1", "blob_unit2"]
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(photo_note)
        await async_session.commit()

        # Verify photo note was created
        result = await async_session.execute(
            select(Entity).where(
                Entity.name == "Equipment Photos"
            )
        )
        notes = result.scalars().all()

        assert len(notes) == 1
        assert notes[0].content["category"] == "photo_documentation"
        assert notes[0].content["has_blob"] is True
        assert len(notes[0].content["blob_references"]) == 2

    @pytest.mark.asyncio
    async def test_link_photo_to_device_with_blob(self, async_session):
        """Test linking photo documentation to device with HAS_BLOB relationship"""
        # Create device
        device = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.DEVICE,
            name="HVAC Unit",
            content={"model": "PVFY"},
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        # Create photo note
        photo_note = Entity(
            id=str(uuid4()),
            version=Entity.create_version("test-user"),
            entity_type=EntityType.NOTE,
            name="Unit Photos",
            content={
                "category": "photo_documentation",
                "has_blob": True
            },
            source_type=SourceType.MANUAL,
            user_id="test-user",
            parent_versions=[]
        )

        async_session.add(device)
        async_session.add(photo_note)
        await async_session.flush()

        # Create HAS_BLOB relationship
        relationship = EntityRelationship(
            id=str(uuid4()),
            from_entity_id=photo_note.id,
            from_entity_version=photo_note.version,
            to_entity_id=device.id,
            to_entity_version=device.version,
            relationship_type=RelationshipType.HAS_BLOB,
            properties={"blob_type": "photo"},
            user_id="test-user"
        )

        async_session.add(relationship)
        await async_session.commit()

        # Verify relationship
        result = await async_session.execute(
            select(EntityRelationship).where(
                EntityRelationship.relationship_type == RelationshipType.HAS_BLOB
            )
        )
        relationships = result.scalars().all()

        assert len(relationships) == 1
        assert relationships[0].from_entity_id == photo_note.id
        assert relationships[0].to_entity_id == device.id
        assert relationships[0].properties["blob_type"] == "photo"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
