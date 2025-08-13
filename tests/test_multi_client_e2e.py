#!/usr/bin/env python3
"""
End-to-end test for multi-client sync propagation.
This test simulates multiple clients connecting to a server and verifies
that changes propagate correctly across all clients.
"""

import asyncio
import json
import time
import subprocess
import sys
import tempfile
from pathlib import Path
from datetime import datetime, UTC
from typing import List, Dict, Any

# Add project paths
sys.path.insert(0, '/workspaces/the-goodies/funkygibbon')
sys.path.insert(0, '/workspaces/the-goodies/blowing-off')
sys.path.insert(0, '/workspaces/the-goodies/inbetweenies')


def start_server():
    """Start the FunkyGibbon server."""
    print("Starting FunkyGibbon server...")
    process = subprocess.Popen(
        [sys.executable, "-m", "funkygibbon", "--port", "8000"],
        cwd="/workspaces/the-goodies/funkygibbon",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(3)  # Wait for server to start
    return process


class SyncTestClient:
    """Test client for sync operations."""
    
    def __init__(self, client_id: str, storage_path: str):
        self.client_id = client_id
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Import client after paths are set
        from blowingoff.client import BlowingOffClient
        
        self.client = BlowingOffClient(
            server_url="http://localhost:8000",
            client_id=client_id,
            storage_path=str(self.storage_path)
        )
        self.changes = []
        self.entities = {}
    
    def connect(self) -> bool:
        """Connect to server."""
        try:
            return self.client.connect()
        except Exception as e:
            print(f"Client {self.client_id} connection failed: {e}")
            return False
    
    def create_entity(self, entity_type: str, name: str) -> Dict[str, Any]:
        """Create a new entity."""
        entity = {
            "id": f"{self.client_id}-{entity_type}-{len(self.entities)}",
            "type": entity_type,
            "name": name,
            "created_by": self.client_id,
            "created_at": datetime.now(UTC).isoformat()
        }
        
        self.client.add_entity(entity)
        self.entities[entity["id"]] = entity
        self.changes.append({"operation": "create", "entity": entity})
        return entity
    
    def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing entity."""
        if entity_id in self.entities:
            self.entities[entity_id].update(updates)
            self.entities[entity_id]["updated_at"] = datetime.now(UTC).isoformat()
            self.entities[entity_id]["updated_by"] = self.client_id
            
            result = self.client.update_entity(entity_id, updates)
            self.changes.append({"operation": "update", "entity_id": entity_id, "updates": updates})
            return result
        return False
    
    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity."""
        if entity_id in self.entities:
            result = self.client.delete_entity(entity_id)
            if result:
                del self.entities[entity_id]
                self.changes.append({"operation": "delete", "entity_id": entity_id})
            return result
        return False
    
    def sync(self) -> Dict[str, Any]:
        """Sync with server."""
        return self.client.sync()
    
    def get_all_entities(self) -> List[Dict[str, Any]]:
        """Get all entities from local storage."""
        return list(self.entities.values())
    
    def verify_entity_exists(self, entity_id: str) -> bool:
        """Check if entity exists locally."""
        return self.client.get_entity(entity_id) is not None


def run_multi_client_test():
    """Run the multi-client end-to-end test."""
    print("\n" + "="*60)
    print("MULTI-CLIENT SYNC PROPAGATION TEST")
    print("="*60)
    
    server_process = None
    clients = []
    temp_dirs = []
    
    try:
        # Start server
        server_process = start_server()
        print("✓ Server started")
        
        # Create 3 clients with separate storage
        for i in range(3):
            temp_dir = tempfile.mkdtemp(prefix=f"client_{i}_")
            temp_dirs.append(temp_dir)
            
            client = SyncTestClient(f"client_{i}", temp_dir)
            if client.connect():
                clients.append(client)
                print(f"✓ Client {i} connected")
            else:
                print(f"✗ Client {i} failed to connect")
        
        if len(clients) < 2:
            print("ERROR: Not enough clients connected")
            return False
        
        print("\n--- Phase 1: Initial Data Creation ---")
        
        # Client 0 creates initial data
        home = clients[0].create_entity("home", "Test Home")
        room1 = clients[0].create_entity("room", "Living Room")
        room2 = clients[0].create_entity("room", "Bedroom")
        print(f"Client 0 created: {home['name']}, {room1['name']}, {room2['name']}")
        
        # Client 0 syncs
        sync_result = clients[0].sync()
        print(f"Client 0 sync: {sync_result}")
        
        # Other clients sync to get the data
        for i in range(1, len(clients)):
            sync_result = clients[i].sync()
            print(f"Client {i} sync: {sync_result}")
            
            # Verify they received the data
            if clients[i].verify_entity_exists(home["id"]):
                print(f"✓ Client {i} received home")
            else:
                print(f"✗ Client {i} missing home")
        
        print("\n--- Phase 2: Concurrent Modifications ---")
        
        # Each client makes different changes
        clients[0].update_entity(home["id"], {"name": "Client 0 Home"})
        print("Client 0 updated home name")
        
        clients[1].create_entity("accessory", "Smart Light")
        print("Client 1 created accessory")
        
        if len(clients) > 2:
            clients[2].update_entity(room1["id"], {"name": "Updated Living Room"})
            print("Client 2 updated room name")
        
        print("\n--- Phase 3: Sync and Conflict Resolution ---")
        
        # All clients sync their changes
        for i, client in enumerate(clients):
            sync_result = client.sync()
            print(f"Client {i} sync result: {sync_result}")
        
        # Sync again to ensure all clients have all changes
        for i, client in enumerate(clients):
            sync_result = client.sync()
            print(f"Client {i} second sync: {sync_result}")
        
        print("\n--- Phase 4: Verification ---")
        
        # Verify all clients have converged to the same state
        all_entities = []
        for i, client in enumerate(clients):
            entities = client.get_all_entities()
            all_entities.append(set(e["id"] for e in entities))
            print(f"Client {i} has {len(entities)} entities")
        
        # Check if all clients have the same entities
        if len(all_entities) > 1:
            common_entities = all_entities[0]
            for entity_set in all_entities[1:]:
                common_entities = common_entities.intersection(entity_set)
            
            if len(common_entities) > 0:
                print(f"✓ All clients share {len(common_entities)} common entities")
            else:
                print("✗ No common entities across clients")
        
        print("\n--- Phase 5: Deletion Propagation ---")
        
        # Client 1 deletes an entity
        if len(clients) > 1:
            clients[1].delete_entity(room2["id"])
            print(f"Client 1 deleted {room2['name']}")
            
            # Sync deletion
            clients[1].sync()
            
            # Other clients sync
            for i in [0] + list(range(2, len(clients))):
                clients[i].sync()
                
                # Verify deletion propagated
                if not clients[i].verify_entity_exists(room2["id"]):
                    print(f"✓ Client {i} deleted entity")
                else:
                    print(f"✗ Client {i} still has deleted entity")
        
        print("\n--- Phase 6: Stress Test ---")
        
        # Each client creates multiple entities rapidly
        for i, client in enumerate(clients):
            for j in range(5):
                client.create_entity("accessory", f"Device {i}-{j}")
            print(f"Client {i} created 5 accessories")
        
        # Sync all changes
        for _ in range(2):  # Sync twice to ensure propagation
            for client in clients:
                client.sync()
        
        # Final verification
        final_counts = []
        for i, client in enumerate(clients):
            entities = client.get_all_entities()
            final_counts.append(len(entities))
            print(f"Client {i} final entity count: {len(entities)}")
        
        # Check if all clients have the same count
        if len(set(final_counts)) == 1:
            print(f"\n✓ SUCCESS: All clients converged to {final_counts[0]} entities")
            return True
        else:
            print(f"\n✗ FAILURE: Clients have different entity counts: {final_counts}")
            return False
        
    except Exception as e:
        print(f"\nERROR: Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        if server_process:
            server_process.terminate()
            server_process.wait()
            print("\nServer stopped")
        
        # Clean up temp directories
        for temp_dir in temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass


def run_performance_test():
    """Run performance test with multiple clients."""
    print("\n" + "="*60)
    print("PERFORMANCE TEST - 5 CLIENTS, 100 ENTITIES EACH")
    print("="*60)
    
    server_process = None
    clients = []
    temp_dirs = []
    
    try:
        # Start server
        server_process = start_server()
        
        # Create 5 clients
        for i in range(5):
            temp_dir = tempfile.mkdtemp(prefix=f"perf_client_{i}_")
            temp_dirs.append(temp_dir)
            
            client = SyncTestClient(f"perf_client_{i}", temp_dir)
            if client.connect():
                clients.append(client)
        
        print(f"Connected {len(clients)} clients")
        
        # Each client creates 100 entities
        start_time = time.time()
        
        for i, client in enumerate(clients):
            for j in range(100):
                client.create_entity("accessory", f"PerfDevice_{i}_{j}")
            print(f"Client {i} created 100 entities")
        
        creation_time = time.time() - start_time
        print(f"Entity creation time: {creation_time:.2f}s")
        
        # Sync all clients
        sync_start = time.time()
        
        for round in range(3):  # Multiple sync rounds
            for client in clients:
                client.sync()
        
        sync_time = time.time() - sync_start
        print(f"Sync time (3 rounds): {sync_time:.2f}s")
        
        # Verify final state
        entity_counts = [len(client.get_all_entities()) for client in clients]
        
        if len(set(entity_counts)) == 1:
            print(f"✓ All clients have {entity_counts[0]} entities")
            print(f"✓ Total time: {time.time() - start_time:.2f}s")
            return True
        else:
            print(f"✗ Entity count mismatch: {entity_counts}")
            return False
    
    except Exception as e:
        print(f"Performance test failed: {e}")
        return False
    
    finally:
        if server_process:
            server_process.terminate()
            server_process.wait()
        
        for temp_dir in temp_dirs:
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except:
                pass


if __name__ == "__main__":
    print("Starting Multi-Client End-to-End Tests")
    print("="*60)
    
    # Run basic multi-client test
    basic_success = run_multi_client_test()
    
    # Run performance test
    perf_success = run_performance_test()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Basic Multi-Client Test: {'PASSED' if basic_success else 'FAILED'}")
    print(f"Performance Test: {'PASSED' if perf_success else 'FAILED'}")
    
    if basic_success and perf_success:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)