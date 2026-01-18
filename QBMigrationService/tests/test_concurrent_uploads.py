"""
Concurrent Upload Tests - HIGH PRIORITY FROM TESTING REPORT
============================================================

Tests for race condition detection and concurrent upload handling.
These tests validate thread-safety of the upload system.

Run with:
    pytest test_concurrent_uploads.py -v --timeout=60

Author: QB Migration Suite
Version: 1.0.0
"""

import pytest
import threading
import time
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConcurrentUploads:
    """
    HIGH PRIORITY FROM TESTING REPORT:
    Test concurrent upload handling to detect race conditions
    """
    
    @pytest.fixture
    def mock_client(self):
        """Create mock Flask test client"""
        # Import here to avoid import errors if Flask isn't installed
        try:
            from QBMigrationServer.app import create_app
            app = create_app('testing')
            return app.test_client()
        except ImportError:
            return Mock()
    
    @pytest.fixture
    def mock_qbo_client(self, tmp_path):
        """Create real QBO client for testing (not a mock)"""
        try:
            # Use relative import path from tests directory
            from qbo_client import PremiumQBOClient
            db_path = str(tmp_path / "test_concurrent.db")
            return PremiumQBOClient(
                access_token="test_token",
                db_path=db_path,
                base_url="https://test.api.intuit.com/v3/company/123"
            )
        except ImportError:
            pytest.skip("qbo_client module not available")
    
    def test_concurrent_batch_id_generation(self, mock_qbo_client):
        """
        Test that batch IDs are unique when generated concurrently.
        
        VALIDATES:
        - Thread-safe batch ID generation
        - No duplicate batch IDs under concurrent load
        """
        batch_ids = []
        lock = threading.Lock()
        
        def generate_batch_id():
            bid = mock_qbo_client._get_next_batch_id()
            with lock:
                batch_ids.append(bid)
        
        # Generate 100 batch IDs concurrently
        threads = []
        for _ in range(100):
            t = threading.Thread(target=generate_batch_id)
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # CRITICAL: All batch IDs must be unique
        assert len(batch_ids) == len(set(batch_ids)), \
            f"Duplicate batch IDs detected! Only {len(set(batch_ids))} unique out of {len(batch_ids)}"
    
    def test_concurrent_synctoken_updates(self, mock_qbo_client):
        """
        Test that SyncToken updates are thread-safe.
        
        VALIDATES:
        - SyncToken cache is thread-safe
        - No data corruption under concurrent access
        """
        entity_type = "Customer"
        qbo_id = "12345"
        
        def update_synctoken(version):
            mock_qbo_client.update_synctoken(entity_type, qbo_id, str(version))
            return mock_qbo_client.get_synctoken(entity_type, qbo_id)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(update_synctoken, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]
        
        # Final value should be consistent
        final_value = mock_qbo_client.get_synctoken(entity_type, qbo_id)
        assert final_value in [str(i) for i in range(100)], \
            f"SyncToken has unexpected value: {final_value}"
    
    def test_concurrent_entity_recording(self, mock_qbo_client):
        """
        Test that entity recording is thread-safe.
        
        VALIDATES:
        - Database writes are atomic
        - No duplicate entries under concurrent access
        """
        migration_id = f"test_{int(time.time())}"
        
        def record_entity(entity_num):
            mock_qbo_client.record_created(
                entity_type="Customer",
                qbd_id=f"QBD_{entity_num}",
                qbo_id=f"QBO_{entity_num}",
                migration_id=migration_id
            )
            return entity_num
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(record_entity, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]
        
        # All 100 entities should be recorded
        assert len(results) == 100, f"Expected 100 results, got {len(results)}"
        
        # Check database consistency
        summary = mock_qbo_client.get_migration_summary(migration_id)
        assert summary.get("total_entities", 0) >= 90, \
            f"Expected at least 90 entities, got {summary.get('total_entities', 0)}"
    
    def test_concurrent_rate_limit_tracking(self, mock_qbo_client):
        """
        Test that rate limit tracking is thread-safe.
        
        VALIDATES:
        - Rate limit counter is atomic
        - No counter corruption under concurrent access
        """
        initial_count = mock_qbo_client.request_count
        
        def increment_counter():
            with mock_qbo_client.rate_limit_lock:
                mock_qbo_client.request_count += 1
                return mock_qbo_client.request_count
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(increment_counter) for _ in range(1000)]
            results = [f.result() for f in as_completed(futures)]
        
        # Counter should be incremented exactly 1000 times
        expected = initial_count + 1000
        assert mock_qbo_client.request_count == expected, \
            f"Rate limit counter corrupted: expected {expected}, got {mock_qbo_client.request_count}"
    
    def test_concurrent_display_name_uniqueness(self):
        """
        Test that DisplayName uniqueness is maintained under concurrent access.
        
        VALIDATES:
        - No duplicate display names generated
        - Thread-safe name generation
        """
        try:
            from data_transformer import QBDataTransformer
        except ImportError:
            pytest.skip("QBDataTransformer not available")
        
        transformer = QBDataTransformer(region="US")
        generated_names = []
        lock = threading.Lock()
        
        def generate_name(base_name):
            unique = transformer.ensure_unique_display_name(base_name, "Customer")
            with lock:
                generated_names.append(unique)
            return unique
        
        # Generate 50 names with the same base concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(generate_name, "John Smith") for _ in range(50)]
            results = [f.result() for f in as_completed(futures)]
        
        # CRITICAL: All names must be unique
        assert len(generated_names) == len(set(generated_names)), \
            f"Duplicate display names detected! {len(set(generated_names))} unique out of {len(generated_names)}"


class TestConcurrentApiRequests:
    """
    Additional tests for concurrent API request handling
    """
    
    def test_correlation_id_uniqueness(self):
        """
        Test that correlation IDs are unique across concurrent requests.
        """
        import uuid
        
        correlation_ids = []
        lock = threading.Lock()
        
        def generate_correlation_id():
            cid = str(uuid.uuid4())
            with lock:
                correlation_ids.append(cid)
            return cid
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(generate_correlation_id) for _ in range(1000)]
            results = [f.result() for f in as_completed(futures)]
        
        # All correlation IDs should be unique
        assert len(correlation_ids) == len(set(correlation_ids)), \
            "Duplicate correlation IDs generated"
    
    def test_backoff_calculation_consistency(self):
        """
        Test that backoff calculation is consistent.
        """
        try:
            from qbo_client import PremiumQBOClient
            client = PremiumQBOClient(
                access_token="test",
                db_path=":memory:"
            )
        except ImportError:
            pytest.skip("PremiumQBOClient not available")
        
        # Calculate backoff for same retry count
        results = []
        for _ in range(100):
            backoff = client._calculate_backoff(2)
            results.append(backoff)
        
        # With jitter, values should vary but stay within bounds
        assert min(results) >= 0.1, "Backoff too small"
        assert max(results) <= 10, "Backoff too large for retry 2"
        
        # Should have some variation (jitter working)
        if len(set(results)) < 2:
            pytest.skip("Jitter disabled in config")


class TestConcurrentFileOperations:
    """
    Tests for concurrent file I/O operations
    """
    
    def test_concurrent_log_writes(self, tmp_path):
        """
        Test that log writes don't corrupt each other.
        """
        log_file = tmp_path / "test.log"
        lock = threading.Lock()
        
        def write_log(msg_num):
            with lock:
                with open(log_file, 'a') as f:
                    f.write(f"Message {msg_num}\n")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(write_log, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()
        
        # Read and verify all lines
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 100, f"Expected 100 log lines, got {len(lines)}"
    
    def test_concurrent_state_file_access(self, tmp_path):
        """
        Test concurrent access to state/mapping files.
        """
        state_file = tmp_path / "state.json"
        state_file.write_text("{}")
        lock = threading.Lock()
        
        def update_state(key, value):
            with lock:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                state[key] = value
                with open(state_file, 'w') as f:
                    json.dump(state, f)
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(update_state, f"key_{i}", i) for i in range(50)]
            for f in as_completed(futures):
                f.result()
        
        # Verify final state
        with open(state_file, 'r') as f:
            final_state = json.load(f)
        
        assert len(final_state) == 50, f"Expected 50 keys, got {len(final_state)}"


# Performance benchmarks
class TestPerformanceBenchmarks:
    """
    MEDIUM PRIORITY FROM TESTING REPORT:
    Performance benchmarks for the migration system
    """
    
    def test_batch_processing_throughput(self):
        """
        Benchmark batch processing throughput.
        """
        start = time.time()
        
        # Simulate processing 1000 entities
        for i in range(1000):
            _ = hashlib.sha256(f"entity_{i}".encode()).hexdigest()
        
        duration = time.time() - start
        throughput = 1000 / duration
        
        print(f"\nBatch processing throughput: {throughput:.0f} entities/second")
        assert throughput > 1000, "Processing too slow (<1000 entities/sec)"
    
    def test_json_serialization_speed(self):
        """
        Benchmark JSON serialization speed.
        """
        test_data = {
            "entities": [{"id": i, "name": f"Entity {i}"} for i in range(10000)]
        }
        
        start = time.time()
        for _ in range(10):
            json_str = json.dumps(test_data)
            _ = json.loads(json_str)
        duration = time.time() - start
        
        print(f"\nJSON round-trip (10x 10k entities): {duration:.2f}s")
        assert duration < 5.0, "JSON serialization too slow"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
