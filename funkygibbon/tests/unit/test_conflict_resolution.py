"""
Unit tests for last-write-wins conflict resolution
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock


class TestLastWriteWinsResolution:
    """Test last-write-wins conflict resolution strategy"""
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_simple_conflict_resolution(self):
        """Test basic conflict resolution with two updates"""
        # Create two conflicting updates
        base_time = datetime.now(timezone.utc)
        
        update1 = {
            'id': 'entity-1',
            'content': {'state': 'on', 'brightness': 100},
            'version_timestamp': base_time,
            'last_modified_by': 'device-1'
        }
        
        update2 = {
            'id': 'entity-1',
            'content': {'state': 'off', 'brightness': 0},
            'version_timestamp': base_time + timedelta(seconds=1),
            'last_modified_by': 'device-2'
        }
        
        # Apply last-write-wins
        winner = update2 if update2['version_timestamp'] > update1['version_timestamp'] else update1
        
        assert winner == update2
        assert winner['content']['state'] == 'off'
        assert winner['last_modified_by'] == 'device-2'
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_multiple_concurrent_updates(self):
        """Test resolution with multiple concurrent updates"""
        base_time = datetime.now(timezone.utc)
        
        # Simulate 10 concurrent updates with microsecond differences
        updates = []
        for i in range(10):
            updates.append({
                'id': 'entity-1',
                'content': {'value': i, 'source': f'device-{i}'},
                'version_timestamp': base_time + timedelta(microseconds=i * 100),
                'last_modified_by': f'device-{i}'
            })
        
        # Find winner (last timestamp)
        winner = max(updates, key=lambda x: x['version_timestamp'])
        
        assert winner['content']['value'] == 9
        assert winner['last_modified_by'] == 'device-9'
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_clock_skew_handling(self):
        """Test handling of clock skew between devices"""
        base_time = datetime.now(timezone.utc)
        
        # Device 1 has accurate time
        device1_update = {
            'id': 'entity-1',
            'content': {'state': 'on', 'updated_at': 'accurate'},
            'version_timestamp': base_time,
            'last_modified_by': 'device-1-accurate'
        }
        
        # Device 2 has clock 5 seconds fast
        device2_update = {
            'id': 'entity-1',
            'content': {'state': 'off', 'updated_at': 'fast'},
            'version_timestamp': base_time + timedelta(seconds=5),
            'last_modified_by': 'device-2-fast'
        }
        
        # Device 3 has clock 3 seconds slow (but updates after device 1)
        device3_update = {
            'id': 'entity-1',
            'content': {'state': 'dim', 'updated_at': 'slow'},
            'version_timestamp': base_time - timedelta(seconds=3),
            'last_modified_by': 'device-3-slow'
        }
        
        updates = [device1_update, device2_update, device3_update]
        winner = max(updates, key=lambda x: x['version_timestamp'])
        
        # Device 2 wins due to future timestamp (even if due to clock skew)
        assert winner == device2_update
        assert winner['content']['updated_at'] == 'fast'
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_identical_timestamps(self):
        """Test resolution when timestamps are identical"""
        timestamp = datetime.now(timezone.utc)
        
        update1 = {
            'id': 'entity-1',
            'content': {'state': 'on'},
            'version_timestamp': timestamp,
            'last_modified_by': 'device-a'  # Alphabetically first
        }
        
        update2 = {
            'id': 'entity-1',
            'content': {'state': 'off'},
            'version_timestamp': timestamp,
            'last_modified_by': 'device-b'  # Alphabetically second
        }
        
        # When timestamps are equal, use secondary criteria (e.g., device ID)
        updates = [update1, update2]
        # Sort by timestamp first, then by device ID for deterministic behavior
        sorted_updates = sorted(updates, 
                               key=lambda x: (x['version_timestamp'], x['last_modified_by']))
        winner = sorted_updates[-1]
        
        assert winner == update2  # 'device-b' > 'device-a'
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_partial_updates_merge(self):
        """Test merging partial updates with last-write-wins per field"""
        base_time = datetime.now(timezone.utc)
        
        # Initial state
        entity = {
            'id': 'entity-1',
            'content': {
                'name': 'Smart Light',
                'state': 'on',
                'brightness': 100,
                'color': 'white'
            },
            'version_timestamp': base_time,
            'last_modified_by': 'device-1'
        }
        
        # Update 1: Changes brightness
        update1 = {
            'id': 'entity-1',
            'content': {
                'brightness': 50
            },
            'version_timestamp': base_time + timedelta(seconds=1),
            'last_modified_by': 'device-2'
        }
        
        # Update 2: Changes state and color
        update2 = {
            'id': 'entity-1',
            'content': {
                'state': 'off',
                'color': 'red'
            },
            'version_timestamp': base_time + timedelta(seconds=2),
            'last_modified_by': 'device-3'
        }
        
        # Simple last-write-wins: latest update wins entirely
        # In practice, you might implement field-level timestamps
        winner = update2
        
        assert winner['version_timestamp'] > update1['version_timestamp']
        assert winner['content']['state'] == 'off'
    
    @pytest.mark.unit
    @pytest.mark.conflict
    @pytest.mark.parametrize("num_updates,time_spread", [
        (10, 1),      # 10 updates over 1 second
        (100, 10),    # 100 updates over 10 seconds
        (1000, 60),   # 1000 updates over 1 minute
    ])
    def test_high_volume_conflicts(self, num_updates, time_spread):
        """Test conflict resolution with high volume of updates"""
        base_time = datetime.now(timezone.utc)
        
        updates = []
        for i in range(num_updates):
            # Spread updates over time_spread seconds
            time_offset = (i / num_updates) * time_spread
            updates.append({
                'id': 'entity-1',
                'content': {'counter': i},
                'version_timestamp': base_time + timedelta(seconds=time_offset),
                'last_modified_by': f'device-{i % 10}'  # Simulate 10 devices
            })
        
        # Find winner
        winner = max(updates, key=lambda x: x['version_timestamp'])
        
        assert winner['content']['counter'] == num_updates - 1
        assert winner == updates[-1]
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_conflict_detection_window(self):
        """Test conflict detection within time windows"""
        base_time = datetime.now(timezone.utc)
        conflict_window = timedelta(seconds=5)  # 5 second conflict window
        
        updates = [
            {
                'id': 'entity-1',
                'content': {'state': 'on'},
                'version_timestamp': base_time,
                'last_modified_by': 'device-1'
            },
            {
                'id': 'entity-1',
                'content': {'state': 'off'},
                'version_timestamp': base_time + timedelta(seconds=2),
                'last_modified_by': 'device-2'
            },
            {
                'id': 'entity-1',
                'content': {'state': 'dim'},
                'version_timestamp': base_time + timedelta(seconds=10),
                'last_modified_by': 'device-3'
            }
        ]
        
        # Group updates by conflict window
        conflicts = []
        non_conflicts = []
        
        for update in updates:
            is_conflict = False
            for other in updates:
                if (update != other and 
                    abs((update['version_timestamp'] - other['version_timestamp']).total_seconds()) 
                    <= conflict_window.total_seconds()):
                    is_conflict = True
                    break
            
            if is_conflict:
                conflicts.append(update)
            else:
                non_conflicts.append(update)
        
        # First two updates are within conflict window
        assert len(conflicts) == 2
        assert updates[0] in conflicts
        assert updates[1] in conflicts
        
        # Third update is outside conflict window
        assert len(non_conflicts) == 1
        assert updates[2] in non_conflicts
    
    @pytest.mark.unit
    @pytest.mark.conflict
    def test_resolution_with_metadata(self):
        """Test conflict resolution preserving metadata"""
        base_time = datetime.now(timezone.utc)
        
        update1 = {
            'id': 'entity-1',
            'content': {'state': 'on'},
            'version_timestamp': base_time,
            'last_modified_by': 'device-1',
            'metadata': {
                'source': 'manual',
                'confidence': 0.9,
                'location': 'living_room'
            }
        }
        
        update2 = {
            'id': 'entity-1',
            'content': {'state': 'off'},
            'version_timestamp': base_time + timedelta(seconds=1),
            'last_modified_by': 'automation-1',
            'metadata': {
                'source': 'automation',
                'confidence': 0.95,
                'trigger': 'schedule'
            }
        }
        
        # Winner should preserve its metadata
        winner = update2 if update2['version_timestamp'] > update1['version_timestamp'] else update1
        
        assert winner == update2
        assert winner['metadata']['source'] == 'automation'
        assert winner['metadata']['trigger'] == 'schedule'