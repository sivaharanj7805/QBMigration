"""
Comprehensive Test Suite for Batch API Migration Integration

Tests the batch migration methods added to MigrationOrchestrator:
1. _migrate_entity_batch() — main entry point with parent-child routing
2. _split_parent_child_layers() — dependency layer splitting
3. _get_parent_id() — parent reference extraction
4. _batch_create_layer() — transform + batch create with TaxService routing
5. _send_batch_request() — QBO /batch endpoint interaction
6. Full integration: batch migration through the orchestrator flow
"""

import pytest
import sys
import os
import json
import tempfile
import sqlite3
from unittest.mock import MagicMock, patch, call, PropertyMock
from datetime import datetime, timezone

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import MigrationOrchestrator


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def orchestrator():
    """Create a MigrationOrchestrator with mock credentials."""
    return MigrationOrchestrator(
        qbo_client_id="test_id",
        qbo_client_secret="test_secret",
        qbo_refresh_token="test_token",
        realm_id="1234567890",
        qbo_environment="sandbox"
    )


@pytest.fixture
def mock_qbo_client():
    """Create a mock QBO client with all required methods."""
    client = MagicMock()
    client.max_workers = 3
    client._enforce_batch_rate_limit = MagicMock()
    client.record_created = MagicMock()
    client._make_request = MagicMock()
    client.create_entity = MagicMock()
    client.create_tax_service = MagicMock()
    return client


@pytest.fixture
def mock_transformer():
    """Create a mock data transformer."""
    transformer = MagicMock()
    transformer.transform_entity = MagicMock()
    return transformer


@pytest.fixture
def mock_oauth():
    """Create a mock OAuth manager."""
    return MagicMock()


# ============================================================================
# _get_parent_id() TESTS
# ============================================================================

class TestGetParentId:
    """Tests for parent reference extraction from QBD records."""

    def test_no_parent_returns_none(self):
        record = {'ListID': 'ACC-001', 'Name': 'Checking'}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_dict_parent_ref_with_list_id(self):
        record = {'ListID': 'ACC-002', 'ParentRef': {'ListID': 'ACC-001'}}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_dict_parent_ref_with_value(self):
        record = {'ListID': 'ACC-002', 'ParentRef': {'value': 'ACC-001'}}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_dict_parent_ref_with_fullname(self):
        record = {'ListID': 'ACC-002', 'ParentRef': {'FullName': 'Parent:Child'}}
        assert MigrationOrchestrator._get_parent_id(record) == 'Parent:Child'

    def test_string_parent_ref(self):
        record = {'ListID': 'ACC-002', 'ParentRef': 'ACC-001'}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_flat_parent_ref_listid(self):
        record = {'ListID': 'ACC-002', 'ParentRef_ListID': 'ACC-001'}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_flat_parent_listid(self):
        record = {'ListID': 'ACC-002', 'ParentListID': 'ACC-001'}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_camelcase_parent_ref(self):
        record = {'ListID': 'ACC-002', 'parentRef': {'listID': 'ACC-001'}}
        assert MigrationOrchestrator._get_parent_id(record) == 'ACC-001'

    def test_empty_parent_ref_dict_returns_none(self):
        record = {'ListID': 'ACC-002', 'ParentRef': {}}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_empty_string_parent_ref_returns_none(self):
        record = {'ListID': 'ACC-002', 'ParentRef': ''}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_flat_parent_ref_fullname(self):
        record = {'ListID': 'CLS-002', 'ParentRef_FullName': 'TopLevel'}
        assert MigrationOrchestrator._get_parent_id(record) == 'TopLevel'


# ============================================================================
# _split_parent_child_layers() TESTS
# ============================================================================

class TestSplitParentChildLayers:
    """Tests for dependency layer splitting."""

    def test_all_roots(self, orchestrator):
        """All records have no parent — single layer."""
        data = [
            {'ListID': 'A', 'Name': 'Checking'},
            {'ListID': 'B', 'Name': 'Savings'},
            {'ListID': 'C', 'Name': 'Credit Card'},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_two_level_hierarchy(self, orchestrator):
        """Root accounts and sub-accounts — two layers."""
        data = [
            {'ListID': 'P1', 'Name': 'Bank'},
            {'ListID': 'P2', 'Name': 'Expenses'},
            {'ListID': 'C1', 'Name': 'Checking', 'ParentRef': {'ListID': 'P1'}},
            {'ListID': 'C2', 'Name': 'Savings', 'ParentRef': {'ListID': 'P1'}},
            {'ListID': 'C3', 'Name': 'Office', 'ParentRef': {'ListID': 'P2'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2
        assert len(layers[0]) == 2  # roots
        assert len(layers[1]) == 3  # children

    def test_three_level_hierarchy(self, orchestrator):
        """Grandparent → Parent → Child — three layers."""
        data = [
            {'ListID': 'GP', 'Name': 'Assets'},
            {'ListID': 'P', 'Name': 'Current Assets', 'ParentRef': {'ListID': 'GP'}},
            {'ListID': 'C', 'Name': 'Cash', 'ParentRef': {'ListID': 'P'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 3
        assert layers[0][0]['ListID'] == 'GP'
        assert layers[1][0]['ListID'] == 'P'
        assert layers[2][0]['ListID'] == 'C'

    def test_mixed_roots_and_children(self, orchestrator):
        """Children interleaved with roots in source data."""
        data = [
            {'ListID': 'C1', 'Name': 'Checking', 'ParentRef': {'ListID': 'P1'}},
            {'ListID': 'P1', 'Name': 'Bank'},
            {'ListID': 'C2', 'Name': 'Savings', 'ParentRef': {'ListID': 'P1'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2
        root_ids = {r['ListID'] for r in layers[0]}
        child_ids = {r['ListID'] for r in layers[1]}
        assert root_ids == {'P1'}
        assert child_ids == {'C1', 'C2'}

    def test_circular_references_handled(self, orchestrator):
        """Circular references — placed in one layer with warning."""
        data = [
            {'ListID': 'A', 'Name': 'A', 'ParentRef': {'ListID': 'B'}},
            {'ListID': 'B', 'Name': 'B', 'ParentRef': {'ListID': 'A'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        # Both should end up somewhere (not lost)
        total = sum(len(layer) for layer in layers)
        assert total == 2

    def test_missing_parent_reference(self, orchestrator):
        """Record references a parent that doesn't exist in the data."""
        data = [
            {'ListID': 'A', 'Name': 'Root'},
            {'ListID': 'B', 'Name': 'Orphan', 'ParentRef': {'ListID': 'NONEXISTENT'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        total = sum(len(layer) for layer in layers)
        assert total == 2

    def test_empty_data(self, orchestrator):
        """Empty source data returns empty layers."""
        layers = orchestrator._split_parent_child_layers([])
        assert layers == []

    def test_flat_parent_ref_format(self, orchestrator):
        """C# extractor flat field format."""
        data = [
            {'ListID': 'P1', 'Name': 'Parent'},
            {'ListID': 'C1', 'Name': 'Child', 'ParentRef_ListID': 'P1'},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2

    def test_string_parent_ref_format(self, orchestrator):
        """String-style parent reference."""
        data = [
            {'ListID': 'P1', 'Name': 'Parent'},
            {'ListID': 'C1', 'Name': 'Child', 'ParentRef': 'P1'},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2

    def test_name_fallback_for_id(self, orchestrator):
        """Records without ListID use Name for layer tracking."""
        data = [
            {'Name': 'Parent'},
            {'Name': 'Child', 'ParentRef': {'FullName': 'Parent'}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2


# ============================================================================
# _send_batch_request() TESTS
# ============================================================================

class TestSendBatchRequest:
    """Tests for the QBO /batch endpoint interaction."""

    def test_successful_batch(self, orchestrator, mock_qbo_client):
        """All items in batch succeed."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme Corp'}),
            ('CUST-002', {'DisplayName': 'Global Inc'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Customer": {"Id": "101", "SyncToken": "0"}},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 2
        assert fails == 0
        assert mappings[0] == ('CUST-001', '100')
        assert mappings[1] == ('CUST-002', '101')

        # Verify rate limit was enforced
        mock_qbo_client._enforce_batch_rate_limit.assert_called_once()

        # Verify record_created was called for each success
        assert mock_qbo_client.record_created.call_count == 2

    def test_partial_failure(self, orchestrator, mock_qbo_client):
        """Some items succeed, some fail."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme Corp'}),
            ('CUST-002', {'DisplayName': ''}),  # will fail validation
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Fault": {
                    "Error": [{"Message": "Validation error", "Detail": "Name is required"}],
                    "type": "ValidationFault"
                }},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 1
        assert fails == 1
        assert mappings[0] == ('CUST-001', '100')

    def test_entire_batch_fails(self, orchestrator, mock_qbo_client):
        """Network error causes entire batch to fail."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme Corp'}),
            ('CUST-002', {'DisplayName': 'Global Inc'}),
        ]

        mock_qbo_client._make_request.side_effect = Exception("Network error")

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 0
        assert fails == 2

    def test_empty_batch_response(self, orchestrator, mock_qbo_client):
        """QBO returns empty BatchItemResponse."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme Corp'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": []
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 0
        assert fails == 1

    def test_batch_item_without_id(self, orchestrator, mock_qbo_client):
        """Response entity missing Id field."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme Corp'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Name": "Acme Corp"}},  # No Id
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 0
        assert fails == 1

    def test_empty_batch_items_list(self, orchestrator, mock_qbo_client):
        """Empty batch items list — no request made."""
        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', [], None)

        assert len(mappings) == 0
        assert fails == 0
        mock_qbo_client._make_request.assert_not_called()

    def test_bid_correlation(self, orchestrator, mock_qbo_client):
        """Responses returned in different order are correctly correlated."""
        batch_items = [
            ('CUST-A', {'DisplayName': 'Alpha'}),
            ('CUST-B', {'DisplayName': 'Beta'}),
            ('CUST-C', {'DisplayName': 'Charlie'}),
        ]

        # QBO returns responses in reverse order
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_2", "Customer": {"Id": "300", "SyncToken": "0"}},
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Customer": {"Id": "200", "SyncToken": "0"}},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 3
        assert fails == 0
        mapping_dict = dict(mappings)
        assert mapping_dict['CUST-A'] == '100'
        assert mapping_dict['CUST-B'] == '200'
        assert mapping_dict['CUST-C'] == '300'

    def test_oauth_manager_passed_through(self, orchestrator, mock_qbo_client, mock_oauth):
        """OAuth manager is passed to _make_request."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, mock_oauth)

        _, kwargs = mock_qbo_client._make_request.call_args
        assert kwargs.get('oauth_manager') is mock_oauth

    def test_source_id_none(self, orchestrator, mock_qbo_client):
        """Records without a source ID still succeed."""
        batch_items = [
            (None, {'DisplayName': 'No ID'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 1
        assert mappings[0] == (None, '100')
        # record_created should use fallback ID
        mock_qbo_client.record_created.assert_called_once()
        call_args = mock_qbo_client.record_created.call_args
        assert call_args[1].get('sync_token') == '0' or call_args[0][1] == 'batch_bid_0'

    def test_unexpected_response_format(self, orchestrator, mock_qbo_client):
        """Batch item has neither entity nor Fault."""
        batch_items = [
            ('CUST-001', {'DisplayName': 'Acme'}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "SomethingElse": True},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, 'Customer', batch_items, None)

        assert len(mappings) == 0
        assert fails == 1


# ============================================================================
# _batch_create_layer() TESTS
# ============================================================================

class TestBatchCreateLayer:
    """Tests for the transform + batch-create layer method."""

    def test_basic_batch_layer(self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Basic batch layer with all records succeeding."""
        records = [
            {'ListID': 'V-001', 'Name': 'Vendor A'},
            {'ListID': 'V-002', 'Name': 'Vendor B'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': 'Vendor A'},
            {'DisplayName': 'Vendor B'},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "101", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, existing_maps, mock_oauth)

        assert success == 2
        assert fail == 0
        assert skip == 0
        assert existing_maps['Vendors']['V-001'] == '100'
        assert existing_maps['Vendors']['V-002'] == '101'

    def test_transform_skip(self, orchestrator, mock_qbo_client, mock_transformer):
        """Records that transform to None are counted as skipped."""
        records = [
            {'ListID': 'V-001', 'Name': 'Active Vendor'},
            {'ListID': 'V-002', 'Name': 'Inactive Vendor'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': 'Active Vendor'},
            None,  # skipped
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, {}, None)

        assert success == 1
        assert fail == 0
        assert skip == 1

    def test_transform_exception(self, orchestrator, mock_qbo_client, mock_transformer):
        """Transform exceptions are counted as failures."""
        records = [
            {'ListID': 'V-001', 'Name': 'Good'},
            {'ListID': 'V-002', 'Name': 'Bad'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': 'Good'},
            Exception("Transform error"),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, {}, None)

        assert success == 1
        assert fail == 1
        assert skip == 0

    def test_tax_service_routing(self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Entities with _use_tax_service are routed to create_tax_service."""
        records = [
            {'ListID': 'TC-001', 'Name': 'State Tax'},
        ]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'State Tax',
            'TaxRateDetails': [{'TaxRateName': 'CA', 'RateValue': 7.25}],
        }

        mock_qbo_client.create_tax_service.return_value = {
            'TaxCodeId': '5',
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, existing_maps, mock_oauth)

        assert success == 1
        assert fail == 0
        mock_qbo_client.create_tax_service.assert_called_once()
        assert existing_maps['TaxCodes']['TC-001'] == '5'

    def test_tax_service_failure(self, orchestrator, mock_qbo_client, mock_transformer):
        """Failed TaxService creation is counted as failure."""
        records = [{'ListID': 'TC-001', 'Name': 'Bad Tax'}]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'Bad Tax',
            'TaxRateDetails': [],
        }

        mock_qbo_client.create_tax_service.side_effect = ValueError("TaxService error")

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, {}, None)

        assert success == 0
        assert fail == 1

    def test_mixed_tax_and_regular(self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Mix of TaxService and regular entities."""
        records = [
            {'ListID': 'TC-001', 'Name': 'Tax Code 1'},
            {'ListID': 'TC-002', 'Name': 'Tax Code 2'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {
                '_use_tax_service': True,
                'TaxCode': 'Tax Code 1',
                'TaxRateDetails': [{'TaxRateName': 'CA'}],
            },
            {'Name': 'Tax Code 2', 'TaxRateRef': {'value': '1'}},
        ]

        mock_qbo_client.create_tax_service.return_value = {'TaxCodeId': '10'}
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "TaxCode": {"Id": "11", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, existing_maps, mock_oauth)

        assert success == 2
        assert fail == 0
        assert existing_maps['TaxCodes']['TC-001'] == '10'
        assert existing_maps['TaxCodes']['TC-002'] == '11'

    def test_all_transforms_skipped(self, orchestrator, mock_qbo_client, mock_transformer):
        """All records skip during transform — no batch request made."""
        records = [
            {'ListID': 'V-001'},
            {'ListID': 'V-002'},
        ]

        mock_transformer.transform_entity.return_value = None

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, {}, None)

        assert success == 0
        assert fail == 0
        assert skip == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_large_batch_splits_correctly(self, orchestrator, mock_qbo_client, mock_transformer):
        """More than 30 records split into multiple batch requests."""
        records = [{'ListID': f'V-{i:03d}', 'Name': f'Vendor {i}'} for i in range(50)]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': f'Vendor {i}'} for i in range(50)
        ]

        # Mock batch responses: each batch returns success for all items
        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get('data', {})
            items = batch_data.get('BatchItemRequest', [])
            return {
                "BatchItemResponse": [
                    {
                        "bId": item['bId'],
                        "Vendor": {"Id": str(100 + i), "SyncToken": "0"}
                    }
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, {}, None)

        assert success == 50
        assert fail == 0
        # Should have made 2 batch requests (30 + 20)
        assert mock_qbo_client._make_request.call_count == 2

    def test_parallel_batches(self, orchestrator, mock_qbo_client, mock_transformer):
        """Multiple batches run in parallel when workers > 1."""
        # Need enough records to make multiple batches AND multiple workers
        records = [{'ListID': f'V-{i:03d}', 'Name': f'V{i}'} for i in range(90)]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': f'V{i}'} for i in range(90)
        ]

        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get('data', {})
            items = batch_data.get('BatchItemRequest', [])
            return {
                "BatchItemResponse": [
                    {"bId": item['bId'], "Vendor": {"Id": str(i), "SyncToken": "0"}}
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response
        mock_qbo_client.max_workers = 3

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'Vendors', 'Vendor',
            records, existing_maps, None)

        assert success == 90
        assert fail == 0
        # 90 records / 30 per batch = 3 batches
        assert mock_qbo_client._make_request.call_count == 3

    def test_tax_service_with_taxcode_id_in_response(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """TaxService response with Id field."""
        records = [{'ListID': 'TC-001'}]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'SalesTax',
            'TaxRateDetails': [],
        }
        mock_qbo_client.create_tax_service.return_value = {'Id': '42'}

        existing_maps = {}
        success, _, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, existing_maps, None)

        assert success == 1
        assert existing_maps['TaxCodes']['TC-001'] == '42'

    def test_tax_service_nested_taxcode_id(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """TaxService response with nested TaxCode.Id."""
        records = [{'ListID': 'TC-001'}]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'SalesTax',
            'TaxRateDetails': [],
        }
        mock_qbo_client.create_tax_service.return_value = {
            'TaxCode': {'Id': '99', 'Name': 'SalesTax'}
        }

        existing_maps = {}
        success, _, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, existing_maps, None)

        assert success == 1
        assert existing_maps['TaxCodes']['TC-001'] == '99'

    def test_tax_service_no_id_in_response(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """TaxService response without any Id field — counted as failure."""
        records = [{'ListID': 'TC-001'}]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'SalesTax',
            'TaxRateDetails': [],
        }
        mock_qbo_client.create_tax_service.return_value = {'Name': 'SalesTax'}

        success, fail, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, {}, None)

        assert success == 0
        assert fail == 1

    def test_tax_service_returns_none(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """TaxService returns None — counted as failure."""
        records = [{'ListID': 'TC-001'}]

        mock_transformer.transform_entity.return_value = {
            '_use_tax_service': True,
            'TaxCode': 'SalesTax',
            'TaxRateDetails': [],
        }
        mock_qbo_client.create_tax_service.return_value = None

        success, fail, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, 'TaxCodes', 'TaxCode',
            records, {}, None)

        assert success == 0
        assert fail == 1


# ============================================================================
# _migrate_entity_batch() TESTS
# ============================================================================

class TestMigrateEntityBatch:
    """Tests for the main batch migration entry point."""

    def test_single_entity_falls_back_to_sequential(
            self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Single entity skips batch overhead, uses _migrate_entity."""
        records = [{'ListID': 'V-001', 'Name': 'Solo Vendor'}]

        mock_transformer.transform_entity.return_value = {'DisplayName': 'Solo Vendor'}
        mock_qbo_client.create_entity.return_value = {'Id': '100', 'SyncToken': '0'}

        with patch.object(orchestrator, '_migrate_entity', return_value=(1, 0, 0)) as mock_seq:
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, 'Vendors', records,
                {}, mock_oauth)

            mock_seq.assert_called_once()
            assert success == 1

    def test_parent_child_type_uses_layers(
            self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Accounts (parent-child type) use layered processing."""
        records = [
            {'ListID': 'P', 'Name': 'Bank'},
            {'ListID': 'C', 'Name': 'Checking', 'ParentRef': {'ListID': 'P'}},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'Name': 'Bank', 'AccountType': 'Bank'},
            {'Name': 'Checking', 'AccountType': 'Bank', 'ParentRef': {'value': '100'}},
        ]

        # First batch (root)
        first_response = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "100", "SyncToken": "0"}},
            ]
        }
        # Second batch (child)
        second_response = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "101", "SyncToken": "0"}},
            ]
        }
        mock_qbo_client._make_request.side_effect = [first_response, second_response]

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Accounts', records,
            existing_maps, mock_oauth)

        assert success == 2
        assert fail == 0
        assert 'Accounts' in existing_maps
        assert existing_maps['Accounts']['P'] == '100'
        assert existing_maps['Accounts']['C'] == '101'

    def test_flat_type_no_layers(
            self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """Non-parent-child types (Vendors) batch all at once."""
        records = [
            {'ListID': 'V-001', 'Name': 'V1'},
            {'ListID': 'V-002', 'Name': 'V2'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': 'V1'},
            {'DisplayName': 'V2'},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "200", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "201", "SyncToken": "0"}},
            ]
        }

        with patch.object(orchestrator, '_split_parent_child_layers') as mock_split:
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, 'Vendors', records,
                {}, mock_oauth)

            # Should NOT call _split_parent_child_layers for Vendors
            mock_split.assert_not_called()

        assert success == 2

    def test_plural_to_singular_mapping(self, orchestrator):
        """All entity_order entries have correct singular mappings."""
        entity_order_types = [
            'CompanyCurrencies', 'TaxAgencies', 'TaxRates', 'TaxCodes',
            'Terms', 'PaymentMethods', 'Classes', 'Departments',
            'Accounts', 'Customers', 'Vendors', 'Employees', 'Items',
            'JournalEntries', 'InventoryAdjustments', 'Estimates',
            'Invoices', 'SalesReceipts', 'PurchaseOrders', 'Purchases',
            'Bills', 'Payments', 'BillPayments', 'Deposits', 'Transfers',
            'CreditMemos', 'VendorCredits', 'RefundReceipts',
            'TimeActivities', 'TaxPayments', 'Attachables',
        ]

        for entity_type in entity_order_types:
            assert entity_type in orchestrator.PLURAL_TO_SINGULAR, \
                f"Missing PLURAL_TO_SINGULAR mapping for '{entity_type}'"

    def test_existing_maps_updated_across_layers(
            self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth):
        """ID mappings from layer 0 are available to layer 1 transforms."""
        records = [
            {'ListID': 'P', 'Name': 'Parent'},
            {'ListID': 'C', 'Name': 'Child', 'ParentRef': {'ListID': 'P'}},
        ]

        transform_calls = []

        def mock_transform(entity_name, record, id_mapping=None):
            transform_calls.append(dict(id_mapping) if id_mapping else {})
            if record.get('ListID') == 'P':
                return {'Name': 'Parent', 'AccountType': 'Bank'}
            else:
                return {'Name': 'Child', 'AccountType': 'Bank',
                        'ParentRef': {'value': '100'}}

        mock_transformer.transform_entity.side_effect = mock_transform

        mock_qbo_client._make_request.side_effect = [
            {"BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "100", "SyncToken": "0"}}
            ]},
            {"BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "101", "SyncToken": "0"}}
            ]},
        ]

        existing_maps = {}
        orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Accounts', records,
            existing_maps, mock_oauth)

        # By the time layer 1 transform runs, existing_maps should contain
        # the mapping from layer 0
        assert len(transform_calls) == 2
        # Layer 1 transform should see 'Accounts': {'P': '100'}
        assert 'Accounts' in transform_calls[1]
        assert transform_calls[1]['Accounts']['P'] == '100'


# ============================================================================
# INTEGRATION WITH PLURAL_TO_SINGULAR
# ============================================================================

class TestBatchPluralToSingular:
    """Verify batch methods use correct singular types for QBO API."""

    def test_accounts_singular(self, orchestrator, mock_qbo_client, mock_transformer):
        """Accounts → Account in batch request."""
        records = [
            {'ListID': 'A1', 'Name': 'Cash'},
            {'ListID': 'A2', 'Name': 'AR'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'Name': 'Cash', 'AccountType': 'Bank'},
            {'Name': 'AR', 'AccountType': 'AccountsReceivable'},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "1", "SyncToken": "0"}},
                {"bId": "bid_1", "Account": {"Id": "2", "SyncToken": "0"}},
            ]
        }

        orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Accounts', records, {}, None)

        # Verify the batch request uses 'Account' (singular)
        call_args = mock_qbo_client._make_request.call_args
        batch_data = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('data')
        for item in batch_data['BatchItemRequest']:
            assert 'Account' in item
            assert 'Accounts' not in item

    def test_invoices_singular(self, orchestrator, mock_qbo_client, mock_transformer):
        """Invoices → Invoice in batch request."""
        records = [
            {'TxnID': 'INV-1', 'RefNumber': '001'},
            {'TxnID': 'INV-2', 'RefNumber': '002'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DocNumber': '001', 'Line': []},
            {'DocNumber': '002', 'Line': []},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "10", "SyncToken": "0"}},
                {"bId": "bid_1", "Invoice": {"Id": "11", "SyncToken": "0"}},
            ]
        }

        orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Invoices', records, {}, None)

        call_args = mock_qbo_client._make_request.call_args
        batch_data = call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get('data')
        for item in batch_data['BatchItemRequest']:
            assert 'Invoice' in item


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================

class TestBatchEdgeCases:
    """Tests for edge cases in batch migration."""

    def test_empty_source_data(self, orchestrator, mock_qbo_client, mock_transformer):
        """Empty source data list returns zeros."""
        # Empty list → len <= 1, falls back to _migrate_entity
        with patch.object(orchestrator, '_migrate_entity', return_value=(0, 0, 0)):
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, 'Vendors', [], {}, None)
        assert success == 0
        assert fail == 0
        assert skip == 0

    def test_all_entities_fail_transform(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """All entities fail transform — no batch request."""
        records = [
            {'ListID': 'V-001'},
            {'ListID': 'V-002'},
        ]

        mock_transformer.transform_entity.side_effect = Exception("Bad data")

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Vendors', records, {}, None)

        assert success == 0
        assert fail == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_records_with_txnid(self, orchestrator, mock_qbo_client, mock_transformer):
        """Transaction records use TxnID as source ID."""
        records = [
            {'TxnID': 'TXN-001', 'DocNumber': '001'},
            {'TxnID': 'TXN-002', 'DocNumber': '002'},
        ]

        mock_transformer.transform_entity.side_effect = [
            {'DocNumber': '001', 'Line': []},
            {'DocNumber': '002', 'Line': []},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "50", "SyncToken": "0"}},
                {"bId": "bid_1", "Invoice": {"Id": "51", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Invoices', records,
            existing_maps, None)

        assert success == 2
        assert existing_maps['Invoices']['TXN-001'] == '50'
        assert existing_maps['Invoices']['TXN-002'] == '51'

    def test_items_treated_as_parent_child(self, orchestrator):
        """Items entity type is in PARENT_CHILD_ENTITY_TYPES."""
        assert 'Items' in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_customers_treated_as_parent_child(self, orchestrator):
        """Customers entity type is in PARENT_CHILD_ENTITY_TYPES."""
        assert 'Customers' in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_invoices_not_parent_child(self, orchestrator):
        """Invoices are NOT parent-child — batched flat."""
        assert 'Invoices' not in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_batch_with_max_workers_1(
            self, orchestrator, mock_qbo_client, mock_transformer):
        """With max_workers=1, batches are processed sequentially."""
        mock_qbo_client.max_workers = 1

        records = [{'ListID': f'V-{i}', 'Name': f'V{i}'} for i in range(60)]

        mock_transformer.transform_entity.side_effect = [
            {'DisplayName': f'V{i}'} for i in range(60)
        ]

        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get('data', {})
            items = batch_data.get('BatchItemRequest', [])
            return {
                "BatchItemResponse": [
                    {"bId": item['bId'], "Vendor": {"Id": str(i), "SyncToken": "0"}}
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, 'Vendors', records, {}, None)

        assert success == 60
        assert fail == 0


# ============================================================================
# FULL ORCHESTRATOR INTEGRATION
# ============================================================================

class TestBatchOrchestratorIntegration:
    """Tests verifying batch migration is wired into run_migration correctly."""

    def test_run_migration_calls_batch_method(self, orchestrator):
        """run_migration uses _migrate_entity_batch, not _migrate_entity."""
        with patch.object(orchestrator, '_init_encryption') as mock_enc, \
             patch.object(orchestrator, '_init_oauth') as mock_oauth_init, \
             patch.object(orchestrator, '_init_qbo_client') as mock_qbo_init, \
             patch.object(orchestrator, '_init_transformer') as mock_tx_init, \
             patch.object(orchestrator, '_init_verifier') as mock_ver_init, \
             patch.object(orchestrator, '_migrate_entity_batch',
                          return_value=(5, 0, 0)) as mock_batch, \
             patch.object(orchestrator, '_migrate_entity',
                          return_value=(5, 0, 0)) as mock_seq:

            # Setup mocks
            mock_enc_mgr = MagicMock()
            mock_enc_mgr.decrypt_chunked.return_value = json.dumps({
                'Customers': [{'ListID': f'C-{i}', 'Name': f'C{i}'} for i in range(5)]
            })
            mock_enc.return_value = mock_enc_mgr

            mock_oauth = MagicMock()
            mock_oauth.get_valid_access_token.return_value = 'test_token'
            mock_oauth_init.return_value = mock_oauth

            mock_qbo = MagicMock()
            mock_qbo.query_tax_agencies.return_value = []
            mock_qbo_init.return_value = mock_qbo

            mock_transformer = MagicMock()
            mock_transformer.id_mapping = {'tax_agencies': {}}
            mock_tx_init.return_value = mock_transformer

            mock_verifier = MagicMock()
            mock_verifier.verify_migration.return_value = {'status': 'OK'}
            mock_ver_init.return_value = mock_verifier

            result = orchestrator.run_migration(
                encrypted_data=b"test",
                encryption_metadata={'key': 'k', 'iv': 'i', 'tag': 't'},
                company_name="Test Co"
            )

            # batch method should have been called (not sequential)
            assert mock_batch.called
            assert not mock_seq.called
            assert result['success'] is True
