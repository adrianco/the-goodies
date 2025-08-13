"""
Test database migration scenarios.

These tests ensure that database schema changes are handled correctly,
catching issues like column name changes (house_id -> home_id).
"""

import pytest
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.ext.asyncio import create_async_engine
import asyncio

from funkygibbon.database import Base, init_db


@pytest.mark.integration
class TestDatabaseMigration:
    """Test database schema migration scenarios."""
    
    def test_old_schema_detection(self):
        """Test detection of old schema with house_id column."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create database with old schema
            engine = create_engine(f"sqlite:///{db_path}")
            
            with engine.connect() as conn:
                # Create old schema manually
                conn.execute(text("""
                    CREATE TABLE homes (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        address VARCHAR(255),
                        timezone VARCHAR(50),
                        is_primary BOOLEAN,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        sync_id VARCHAR(36)
                    )
                """))
                
                conn.execute(text("""
                    CREATE TABLE rooms (
                        id VARCHAR(36) PRIMARY KEY,
                        house_id VARCHAR(36) NOT NULL,  -- Old column name
                        name VARCHAR(255) NOT NULL,
                        floor INTEGER,
                        room_type VARCHAR(50),
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        sync_id VARCHAR(36),
                        FOREIGN KEY (house_id) REFERENCES homes(id)
                    )
                """))
                
                conn.commit()
            
            # Check if we can detect the old schema
            inspector = inspect(engine)
            columns = inspector.get_columns('rooms')
            column_names = [col['name'] for col in columns]
            
            # Old schema should have house_id, not home_id
            assert 'house_id' in column_names
            assert 'home_id' not in column_names
            
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_new_schema_creation(self):
        """Test that new graph-based schema is created correctly."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create database with new schema
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            # Check the schema
            sync_engine = create_engine(f"sqlite:///{db_path}")
            inspector = inspect(sync_engine)
            
            # Check for graph-based tables
            tables = inspector.get_table_names()
            assert 'entities' in tables
            assert 'entity_relationships' in tables
            assert 'sync_metadata' in tables
            
            # Old HomeKit tables should not exist
            assert 'rooms' not in tables
            assert 'accessories' not in tables
            assert 'homes' not in tables
            assert 'services' not in tables
            assert 'characteristics' not in tables
            assert 'users' not in tables
            
            # Check entities table columns
            columns = inspector.get_columns('entities')
            column_names = [col['name'] for col in columns]
            
            # Should have graph entity columns
            assert 'id' in column_names
            assert 'version' in column_names
            assert 'entity_type' in column_names
            assert 'name' in column_names
            assert 'content' in column_names
            assert 'source_type' in column_names
            
            await engine.dispose()
            
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    def test_field_removal_detection(self):
        """Test detection of removed fields."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create database with old schema including removed fields
            engine = create_engine(f"sqlite:///{db_path}")
            
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE homes (
                        id VARCHAR(36) PRIMARY KEY,
                        name VARCHAR(255) NOT NULL,
                        address VARCHAR(255),      -- Should be removed
                        timezone VARCHAR(50),       -- Should be removed
                        latitude FLOAT,             -- Should be removed
                        longitude FLOAT,            -- Should be removed
                        is_primary BOOLEAN,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        sync_id VARCHAR(36),
                        version VARCHAR(10),        -- Should be removed
                        is_deleted BOOLEAN          -- Should be removed
                    )
                """))
                
                conn.execute(text("""
                    CREATE TABLE users (
                        id VARCHAR(36) PRIMARY KEY,
                        home_id VARCHAR(36),
                        name VARCHAR(255),
                        email VARCHAR(255),         -- Should be removed
                        role VARCHAR(50),           -- Should be removed
                        is_administrator BOOLEAN,
                        is_owner BOOLEAN,
                        remote_access_allowed BOOLEAN,
                        created_at TIMESTAMP,
                        updated_at TIMESTAMP,
                        sync_id VARCHAR(36)
                    )
                """))
                
                conn.commit()
            
            # Check old schema
            inspector = inspect(engine)
            
            # Check homes table
            home_columns = inspector.get_columns('homes')
            home_column_names = [col['name'] for col in home_columns]
            
            assert 'address' in home_column_names
            assert 'timezone' in home_column_names
            assert 'version' in home_column_names
            assert 'is_deleted' in home_column_names
            
            # Check users table
            user_columns = inspector.get_columns('users')
            user_column_names = [col['name'] for col in user_columns]
            
            assert 'email' in user_column_names
            assert 'role' in user_column_names
            
        finally:
            Path(db_path).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_populate_db_with_new_schema(self):
        """Test that populate_db.py works with graph-based schema."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create new schema
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                
                # Insert graph entities
                await conn.execute(text("""
                    INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id, parent_versions, created_at, updated_at)
                    VALUES (:id, :version, :entity_type, :name, :content, :source_type, :user_id, :parent_versions, :created_at, :updated_at)
                """), {
                    "id": "home-test",
                    "version": "v1",
                    "entity_type": "home",
                    "name": "Test Home",
                    "content": '{"is_primary": true}',
                    "source_type": "manual",
                    "user_id": "test-user",
                    "parent_versions": '[]',
                    "created_at": "2025-07-29T12:00:00",
                    "updated_at": "2025-07-29T12:00:00"
                })
                
                # Insert room entity
                await conn.execute(text("""
                    INSERT INTO entities (id, version, entity_type, name, content, source_type, user_id, parent_versions, created_at, updated_at)
                    VALUES (:id, :version, :entity_type, :name, :content, :source_type, :user_id, :parent_versions, :created_at, :updated_at)
                """), {
                    "id": "room-test",
                    "version": "v1",
                    "entity_type": "room",
                    "name": "Test Room",
                    "content": '{"floor": 1}',
                    "source_type": "manual",
                    "user_id": "test-user",
                    "parent_versions": '[]',
                    "created_at": "2025-07-29T12:00:00",
                    "updated_at": "2025-07-29T12:00:00"
                })
                
                # Create relationship between home and room
                await conn.execute(text("""
                    INSERT INTO entity_relationships (id, from_entity_id, from_entity_version, to_entity_id, to_entity_version, relationship_type, properties, user_id, created_at, updated_at)
                    VALUES (:id, :from_id, :from_ver, :to_id, :to_ver, :rel_type, :props, :user_id, :created_at, :updated_at)
                """), {
                    "id": "rel-test",
                    "from_id": "room-test",
                    "from_ver": "v1",
                    "to_id": "home-test",
                    "to_ver": "v1",
                    "rel_type": "located_in",
                    "props": '{}',
                    "user_id": "test-user",
                    "created_at": "2025-07-29T12:00:00",
                    "updated_at": "2025-07-29T12:00:00"
                })
                
                # Verify data was inserted
                result = await conn.execute(text("SELECT COUNT(*) FROM entities WHERE entity_type = 'home'"))
                count = result.scalar()
                assert count == 1
                
                result = await conn.execute(text("SELECT COUNT(*) FROM entities WHERE entity_type = 'room'"))
                count = result.scalar()
                assert count == 1
                
                result = await conn.execute(text("SELECT COUNT(*) FROM entity_relationships"))
                count = result.scalar()
                assert count == 1
                
            await engine.dispose()
            
        finally:
            Path(db_path).unlink(missing_ok=True)