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

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import MigrationOrchestrator  # noqa: E402

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
        qbo_environment="sandbox",
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
    # Dedup check — return None by default (not previously created)
    client.was_entity_created = MagicMock(return_value=None)
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
        record = {"ListID": "ACC-001", "Name": "Checking"}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_dict_parent_ref_with_list_id(self):
        record = {"ListID": "ACC-002", "ParentRef": {"ListID": "ACC-001"}}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_dict_parent_ref_with_value(self):
        record = {"ListID": "ACC-002", "ParentRef": {"value": "ACC-001"}}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_dict_parent_ref_with_fullname(self):
        record = {"ListID": "ACC-002", "ParentRef": {"FullName": "Parent:Child"}}
        assert MigrationOrchestrator._get_parent_id(record) == "Parent:Child"

    def test_string_parent_ref(self):
        record = {"ListID": "ACC-002", "ParentRef": "ACC-001"}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_flat_parent_ref_listid(self):
        record = {"ListID": "ACC-002", "ParentRef_ListID": "ACC-001"}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_flat_parent_listid(self):
        record = {"ListID": "ACC-002", "ParentListID": "ACC-001"}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_camelcase_parent_ref(self):
        record = {"ListID": "ACC-002", "parentRef": {"listID": "ACC-001"}}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_empty_parent_ref_dict_returns_none(self):
        record = {"ListID": "ACC-002", "ParentRef": {}}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_empty_string_parent_ref_returns_none(self):
        record = {"ListID": "ACC-002", "ParentRef": ""}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_flat_parent_ref_fullname(self):
        record = {"ListID": "CLS-002", "ParentRef_FullName": "TopLevel"}
        assert MigrationOrchestrator._get_parent_id(record) == "TopLevel"


# ============================================================================
# _split_parent_child_layers() TESTS
# ============================================================================


class TestSplitParentChildLayers:
    """Tests for dependency layer splitting."""

    def test_all_roots(self, orchestrator):
        """All records have no parent — single layer."""
        data = [
            {"ListID": "A", "Name": "Checking"},
            {"ListID": "B", "Name": "Savings"},
            {"ListID": "C", "Name": "Credit Card"},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 1
        assert len(layers[0]) == 3

    def test_two_level_hierarchy(self, orchestrator):
        """Root accounts and sub-accounts — two layers."""
        data = [
            {"ListID": "P1", "Name": "Bank"},
            {"ListID": "P2", "Name": "Expenses"},
            {"ListID": "C1", "Name": "Checking", "ParentRef": {"ListID": "P1"}},
            {"ListID": "C2", "Name": "Savings", "ParentRef": {"ListID": "P1"}},
            {"ListID": "C3", "Name": "Office", "ParentRef": {"ListID": "P2"}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2
        assert len(layers[0]) == 2  # roots
        assert len(layers[1]) == 3  # children

    def test_three_level_hierarchy(self, orchestrator):
        """Grandparent → Parent → Child — three layers."""
        data = [
            {"ListID": "GP", "Name": "Assets"},
            {"ListID": "P", "Name": "Current Assets", "ParentRef": {"ListID": "GP"}},
            {"ListID": "C", "Name": "Cash", "ParentRef": {"ListID": "P"}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 3
        assert layers[0][0]["ListID"] == "GP"
        assert layers[1][0]["ListID"] == "P"
        assert layers[2][0]["ListID"] == "C"

    def test_mixed_roots_and_children(self, orchestrator):
        """Children interleaved with roots in source data."""
        data = [
            {"ListID": "C1", "Name": "Checking", "ParentRef": {"ListID": "P1"}},
            {"ListID": "P1", "Name": "Bank"},
            {"ListID": "C2", "Name": "Savings", "ParentRef": {"ListID": "P1"}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2
        root_ids = {r["ListID"] for r in layers[0]}
        child_ids = {r["ListID"] for r in layers[1]}
        assert root_ids == {"P1"}
        assert child_ids == {"C1", "C2"}

    def test_circular_references_handled(self, orchestrator):
        """Circular references — placed in one layer with warning."""
        data = [
            {"ListID": "A", "Name": "A", "ParentRef": {"ListID": "B"}},
            {"ListID": "B", "Name": "B", "ParentRef": {"ListID": "A"}},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        # Both should end up somewhere (not lost)
        total = sum(len(layer) for layer in layers)
        assert total == 2

    def test_missing_parent_reference(self, orchestrator):
        """Record references a parent that doesn't exist in the data."""
        data = [
            {"ListID": "A", "Name": "Root"},
            {"ListID": "B", "Name": "Orphan", "ParentRef": {"ListID": "NONEXISTENT"}},
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
            {"ListID": "P1", "Name": "Parent"},
            {"ListID": "C1", "Name": "Child", "ParentRef_ListID": "P1"},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2

    def test_string_parent_ref_format(self, orchestrator):
        """String-style parent reference."""
        data = [
            {"ListID": "P1", "Name": "Parent"},
            {"ListID": "C1", "Name": "Child", "ParentRef": "P1"},
        ]
        layers = orchestrator._split_parent_child_layers(data)
        assert len(layers) == 2

    def test_name_fallback_for_id(self, orchestrator):
        """Records without ListID use Name for layer tracking."""
        data = [
            {"Name": "Parent"},
            {"Name": "Child", "ParentRef": {"FullName": "Parent"}},
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
            ("CUST-001", {"DisplayName": "Acme Corp"}),
            ("CUST-002", {"DisplayName": "Global Inc"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Customer": {"Id": "101", "SyncToken": "0"}},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 2
        assert fails == 0
        assert mappings[0] == ("CUST-001", "100")
        assert mappings[1] == ("CUST-002", "101")

        # Verify rate limit was enforced
        mock_qbo_client._enforce_batch_rate_limit.assert_called_once()

        # Verify record_created was called for each success
        assert mock_qbo_client.record_created.call_count == 2

    def test_partial_failure(self, orchestrator, mock_qbo_client):
        """Some items succeed, some fail."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme Corp"}),
            ("CUST-002", {"DisplayName": ""}),  # will fail validation
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
                {
                    "bId": "bid_1",
                    "Fault": {
                        "Error": [
                            {
                                "Message": "Validation error",
                                "Detail": "Name is required",
                            }
                        ],
                        "type": "ValidationFault",
                    },
                },
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 1
        assert fails == 1
        assert mappings[0] == ("CUST-001", "100")

    def test_entire_batch_fails(self, orchestrator, mock_qbo_client):
        """Network error causes entire batch to fail."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme Corp"}),
            ("CUST-002", {"DisplayName": "Global Inc"}),
        ]

        mock_qbo_client._make_request.side_effect = Exception("Network error")

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 0
        assert fails == 2

    def test_empty_batch_response(self, orchestrator, mock_qbo_client):
        """QBO returns empty BatchItemResponse."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme Corp"}),
        ]

        mock_qbo_client._make_request.return_value = {"BatchItemResponse": []}

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 0
        assert fails == 1

    def test_batch_item_without_id(self, orchestrator, mock_qbo_client):
        """Response entity missing Id field."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme Corp"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Name": "Acme Corp"}},  # No Id
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 0
        assert fails == 1

    def test_empty_batch_items_list(self, orchestrator, mock_qbo_client):
        """Empty batch items list — no request made."""
        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", [], None
        )

        assert len(mappings) == 0
        assert fails == 0
        mock_qbo_client._make_request.assert_not_called()

    def test_bid_correlation(self, orchestrator, mock_qbo_client):
        """Responses returned in different order are correctly correlated."""
        batch_items = [
            ("CUST-A", {"DisplayName": "Alpha"}),
            ("CUST-B", {"DisplayName": "Beta"}),
            ("CUST-C", {"DisplayName": "Charlie"}),
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
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 3
        assert fails == 0
        mapping_dict = dict(mappings)
        assert mapping_dict["CUST-A"] == "100"
        assert mapping_dict["CUST-B"] == "200"
        assert mapping_dict["CUST-C"] == "300"

    def test_oauth_manager_passed_through(
        self, orchestrator, mock_qbo_client, mock_oauth
    ):
        """OAuth manager is passed to _make_request."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, mock_oauth
        )

        _, kwargs = mock_qbo_client._make_request.call_args
        assert kwargs.get("oauth_manager") is mock_oauth

    def test_source_id_none(self, orchestrator, mock_qbo_client):
        """Records without a source ID still succeed."""
        batch_items = [
            (None, {"DisplayName": "No ID"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 1
        assert mappings[0] == (None, "100")
        # record_created should use fallback ID
        mock_qbo_client.record_created.assert_called_once()
        call_args = mock_qbo_client.record_created.call_args
        assert call_args[1].get("sync_token") == "0" or call_args[0][1] == "batch_bid_0"

    def test_unexpected_response_format(self, orchestrator, mock_qbo_client):
        """Batch item has neither entity nor Fault."""
        batch_items = [
            ("CUST-001", {"DisplayName": "Acme"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "SomethingElse": True},
            ]
        }

        mappings, fails = orchestrator._send_batch_request(
            mock_qbo_client, "Customer", batch_items, None
        )

        assert len(mappings) == 0
        assert fails == 1


# ============================================================================
# _batch_create_layer() TESTS
# ============================================================================


class TestBatchCreateLayer:
    """Tests for the transform + batch-create layer method."""

    def test_basic_batch_layer(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Basic batch layer with all records succeeding."""
        records = [
            {"ListID": "V-001", "Name": "Vendor A"},
            {"ListID": "V-002", "Name": "Vendor B"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": "Vendor A"},
            {"DisplayName": "Vendor B"},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "101", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Vendors",
            "Vendor",
            records,
            existing_maps,
            mock_oauth,
        )

        assert success == 2
        assert fail == 0
        assert skip == 0
        assert existing_maps["Vendors"]["V-001"] == "100"
        assert existing_maps["Vendors"]["V-002"] == "101"

    def test_transform_skip(self, orchestrator, mock_qbo_client, mock_transformer):
        """Records that transform to None are counted as skipped."""
        records = [
            {"ListID": "V-001", "Name": "Active Vendor"},
            {"ListID": "V-002", "Name": "Inactive Vendor"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": "Active Vendor"},
            None,  # skipped
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert success == 1
        assert fail == 0
        assert skip == 1

    def test_transform_exception(self, orchestrator, mock_qbo_client, mock_transformer):
        """Transform exceptions are counted as failures."""
        records = [
            {"ListID": "V-001", "Name": "Good"},
            {"ListID": "V-002", "Name": "Bad"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": "Good"},
            Exception("Transform error"),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert success == 1
        assert fail == 1
        assert skip == 0

    def test_tax_service_routing(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Entities with _use_tax_service are routed to create_tax_service."""
        records = [
            {"ListID": "TC-001", "Name": "State Tax"},
        ]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "State Tax",
            "TaxRateDetails": [{"TaxRateName": "CA", "RateValue": 7.25}],
        }

        mock_qbo_client.create_tax_service.return_value = {
            "TaxCodeId": "5",
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "TaxCodes",
            "TaxCode",
            records,
            existing_maps,
            mock_oauth,
        )

        assert success == 1
        assert fail == 0
        mock_qbo_client.create_tax_service.assert_called_once()
        assert existing_maps["TaxCodes"]["TC-001"] == "5"

    def test_tax_service_failure(self, orchestrator, mock_qbo_client, mock_transformer):
        """Failed TaxService creation is counted as failure."""
        records = [{"ListID": "TC-001", "Name": "Bad Tax"}]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "Bad Tax",
            "TaxRateDetails": [],
        }

        mock_qbo_client.create_tax_service.side_effect = ValueError("TaxService error")

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "TaxCodes", "TaxCode", records, {}, None
        )

        assert success == 0
        assert fail == 1

    def test_mixed_tax_and_regular(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Mix of TaxService and regular entities."""
        records = [
            {"ListID": "TC-001", "Name": "Tax Code 1"},
            {"ListID": "TC-002", "Name": "Tax Code 2"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {
                "_use_tax_service": True,
                "TaxCode": "Tax Code 1",
                "TaxRateDetails": [{"TaxRateName": "CA"}],
            },
            {"Name": "Tax Code 2", "TaxRateRef": {"value": "1"}},
        ]

        mock_qbo_client.create_tax_service.return_value = {"TaxCodeId": "10"}
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "TaxCode": {"Id": "11", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "TaxCodes",
            "TaxCode",
            records,
            existing_maps,
            mock_oauth,
        )

        assert success == 2
        assert fail == 0
        assert existing_maps["TaxCodes"]["TC-001"] == "10"
        assert existing_maps["TaxCodes"]["TC-002"] == "11"

    def test_all_transforms_skipped(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """All records skip during transform — no batch request made."""
        records = [
            {"ListID": "V-001"},
            {"ListID": "V-002"},
        ]

        mock_transformer.transform_entity.return_value = None

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert success == 0
        assert fail == 0
        assert skip == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_large_batch_splits_correctly(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """More than 30 records split into multiple batch requests."""
        records = [{"ListID": f"V-{i:03d}", "Name": f"Vendor {i}"} for i in range(50)]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": f"Vendor {i}"} for i in range(50)
        ]

        # Mock batch responses: each batch returns success for all items
        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get("data", {})
            items = batch_data.get("BatchItemRequest", [])
            return {
                "BatchItemResponse": [
                    {
                        "bId": item["bId"],
                        "Vendor": {"Id": str(100 + i), "SyncToken": "0"},
                    }
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert success == 50
        assert fail == 0
        # Should have made 2 batch requests (30 + 20)
        assert mock_qbo_client._make_request.call_count == 2

    def test_parallel_batches(self, orchestrator, mock_qbo_client, mock_transformer):
        """Multiple batches run in parallel when workers > 1."""
        # Need enough records to make multiple batches AND multiple workers
        records = [{"ListID": f"V-{i:03d}", "Name": f"V{i}"} for i in range(90)]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": f"V{i}"} for i in range(90)
        ]

        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get("data", {})
            items = batch_data.get("BatchItemRequest", [])
            return {
                "BatchItemResponse": [
                    {"bId": item["bId"], "Vendor": {"Id": str(i), "SyncToken": "0"}}
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response
        mock_qbo_client.max_workers = 3

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Vendors",
            "Vendor",
            records,
            existing_maps,
            None,
        )

        assert success == 90
        assert fail == 0
        # 90 records / 30 per batch = 3 batches
        assert mock_qbo_client._make_request.call_count == 3

    def test_tax_service_with_taxcode_id_in_response(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """TaxService response with Id field."""
        records = [{"ListID": "TC-001"}]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "SalesTax",
            "TaxRateDetails": [],
        }
        mock_qbo_client.create_tax_service.return_value = {"Id": "42"}

        existing_maps = {}
        success, _, _ = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "TaxCodes",
            "TaxCode",
            records,
            existing_maps,
            None,
        )

        assert success == 1
        assert existing_maps["TaxCodes"]["TC-001"] == "42"

    def test_tax_service_nested_taxcode_id(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """TaxService response with nested TaxCode.Id."""
        records = [{"ListID": "TC-001"}]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "SalesTax",
            "TaxRateDetails": [],
        }
        mock_qbo_client.create_tax_service.return_value = {
            "TaxCode": {"Id": "99", "Name": "SalesTax"}
        }

        existing_maps = {}
        success, _, _ = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "TaxCodes",
            "TaxCode",
            records,
            existing_maps,
            None,
        )

        assert success == 1
        assert existing_maps["TaxCodes"]["TC-001"] == "99"

    def test_tax_service_no_id_in_response(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """TaxService response without any Id field — counted as failure."""
        records = [{"ListID": "TC-001"}]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "SalesTax",
            "TaxRateDetails": [],
        }
        mock_qbo_client.create_tax_service.return_value = {"Name": "SalesTax"}

        success, fail, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "TaxCodes", "TaxCode", records, {}, None
        )

        assert success == 0
        assert fail == 1

    def test_tax_service_returns_none(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """TaxService returns None — counted as failure."""
        records = [{"ListID": "TC-001"}]

        mock_transformer.transform_entity.return_value = {
            "_use_tax_service": True,
            "TaxCode": "SalesTax",
            "TaxRateDetails": [],
        }
        mock_qbo_client.create_tax_service.return_value = None

        success, fail, _ = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "TaxCodes", "TaxCode", records, {}, None
        )

        assert success == 0
        assert fail == 1


# ============================================================================
# _migrate_entity_batch() TESTS
# ============================================================================


class TestMigrateEntityBatch:
    """Tests for the main batch migration entry point."""

    def test_single_entity_falls_back_to_sequential(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Single entity skips batch overhead, uses _migrate_entity."""
        records = [{"ListID": "V-001", "Name": "Solo Vendor"}]

        mock_transformer.transform_entity.return_value = {"DisplayName": "Solo Vendor"}
        mock_qbo_client.create_entity.return_value = {"Id": "100", "SyncToken": "0"}

        with patch.object(
            orchestrator, "_migrate_entity", return_value=(1, 0, 0)
        ) as mock_seq:
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, "Vendors", records, {}, mock_oauth
            )

            mock_seq.assert_called_once()
            assert success == 1

    def test_parent_child_type_uses_layers(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Accounts (parent-child type) use layered processing."""
        records = [
            {"ListID": "P", "Name": "Bank"},
            {"ListID": "C", "Name": "Checking", "ParentRef": {"ListID": "P"}},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"Name": "Bank", "AccountType": "Bank"},
            {"Name": "Checking", "AccountType": "Bank", "ParentRef": {"value": "100"}},
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
            mock_qbo_client,
            mock_transformer,
            "Accounts",
            records,
            existing_maps,
            mock_oauth,
        )

        assert success == 2
        assert fail == 0
        assert "Accounts" in existing_maps
        assert existing_maps["Accounts"]["P"] == "100"
        assert existing_maps["Accounts"]["C"] == "101"

    def test_flat_type_no_layers(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """Non-parent-child types (Vendors) batch all at once."""
        records = [
            {"ListID": "V-001", "Name": "V1"},
            {"ListID": "V-002", "Name": "V2"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": "V1"},
            {"DisplayName": "V2"},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "200", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "201", "SyncToken": "0"}},
            ]
        }

        with patch.object(orchestrator, "_split_parent_child_layers") as mock_split:
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, "Vendors", records, {}, mock_oauth
            )

            # Should NOT call _split_parent_child_layers for Vendors
            mock_split.assert_not_called()

        assert success == 2

    def test_plural_to_singular_mapping(self, orchestrator):
        """All entity_order entries have correct singular mappings."""
        entity_order_types = [
            "CompanyCurrencies",
            "TaxAgencies",
            "TaxRates",
            "TaxCodes",
            "Terms",
            "PaymentMethods",
            "Classes",
            "Departments",
            "Accounts",
            "Customers",
            "Vendors",
            "Employees",
            "Items",
            "JournalEntries",
            "InventoryAdjustments",
            "Estimates",
            "Invoices",
            "SalesReceipts",
            "PurchaseOrders",
            "Purchases",
            "Bills",
            "Payments",
            "BillPayments",
            "Deposits",
            "Transfers",
            "CreditMemos",
            "VendorCredits",
            "RefundReceipts",
            "TimeActivities",
            "TaxPayments",
            "Attachables",
        ]

        for entity_type in entity_order_types:
            assert (
                entity_type in orchestrator.PLURAL_TO_SINGULAR
            ), f"Missing PLURAL_TO_SINGULAR mapping for '{entity_type}'"

    def test_existing_maps_updated_across_layers(
        self, orchestrator, mock_qbo_client, mock_transformer, mock_oauth
    ):
        """ID mappings from layer 0 are available to layer 1 transforms."""
        records = [
            {"ListID": "P", "Name": "Parent"},
            {"ListID": "C", "Name": "Child", "ParentRef": {"ListID": "P"}},
        ]

        transform_calls = []

        def mock_transform(entity_name, record, id_mapping=None):
            transform_calls.append(dict(id_mapping) if id_mapping else {})
            if record.get("ListID") == "P":
                return {"Name": "Parent", "AccountType": "Bank"}
            else:
                return {
                    "Name": "Child",
                    "AccountType": "Bank",
                    "ParentRef": {"value": "100"},
                }

        mock_transformer.transform_entity.side_effect = mock_transform

        mock_qbo_client._make_request.side_effect = [
            {
                "BatchItemResponse": [
                    {"bId": "bid_0", "Account": {"Id": "100", "SyncToken": "0"}}
                ]
            },
            {
                "BatchItemResponse": [
                    {"bId": "bid_0", "Account": {"Id": "101", "SyncToken": "0"}}
                ]
            },
        ]

        existing_maps = {}
        orchestrator._migrate_entity_batch(
            mock_qbo_client,
            mock_transformer,
            "Accounts",
            records,
            existing_maps,
            mock_oauth,
        )

        # By the time layer 1 transform runs, existing_maps should contain
        # the mapping from layer 0
        assert len(transform_calls) == 2
        # Layer 1 transform should see 'Accounts': {'P': '100'}
        assert "Accounts" in transform_calls[1]
        assert transform_calls[1]["Accounts"]["P"] == "100"


# ============================================================================
# INTEGRATION WITH PLURAL_TO_SINGULAR
# ============================================================================


class TestBatchPluralToSingular:
    """Verify batch methods use correct singular types for QBO API."""

    def test_accounts_singular(self, orchestrator, mock_qbo_client, mock_transformer):
        """Accounts → Account in batch request."""
        records = [
            {"ListID": "A1", "Name": "Cash"},
            {"ListID": "A2", "Name": "AR"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"Name": "Cash", "AccountType": "Bank"},
            {"Name": "AR", "AccountType": "AccountsReceivable"},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "1", "SyncToken": "0"}},
                {"bId": "bid_1", "Account": {"Id": "2", "SyncToken": "0"}},
            ]
        }

        orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, {}, None
        )

        # Verify the batch request uses 'Account' (singular)
        call_args = mock_qbo_client._make_request.call_args
        batch_data = (
            call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("data")
        )
        for item in batch_data["BatchItemRequest"]:
            assert "Account" in item
            assert "Accounts" not in item

    def test_invoices_singular(self, orchestrator, mock_qbo_client, mock_transformer):
        """Invoices → Invoice in batch request."""
        records = [
            {"TxnID": "INV-1", "RefNumber": "001"},
            {"TxnID": "INV-2", "RefNumber": "002"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DocNumber": "001", "Line": []},
            {"DocNumber": "002", "Line": []},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "10", "SyncToken": "0"}},
                {"bId": "bid_1", "Invoice": {"Id": "11", "SyncToken": "0"}},
            ]
        }

        orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Invoices", records, {}, None
        )

        call_args = mock_qbo_client._make_request.call_args
        batch_data = (
            call_args[0][2] if len(call_args[0]) > 2 else call_args[1].get("data")
        )
        for item in batch_data["BatchItemRequest"]:
            assert "Invoice" in item


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestBatchEdgeCases:
    """Tests for edge cases in batch migration."""

    def test_empty_source_data(self, orchestrator, mock_qbo_client, mock_transformer):
        """Empty source data list returns zeros."""
        # Empty list → len <= 1, falls back to _migrate_entity
        with patch.object(orchestrator, "_migrate_entity", return_value=(0, 0, 0)):
            success, fail, skip = orchestrator._migrate_entity_batch(
                mock_qbo_client, mock_transformer, "Vendors", [], {}, None
            )
        assert success == 0
        assert fail == 0
        assert skip == 0

    def test_all_entities_fail_transform(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """All entities fail transform — no batch request."""
        records = [
            {"ListID": "V-001"},
            {"ListID": "V-002"},
        ]

        mock_transformer.transform_entity.side_effect = Exception("Bad data")

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Vendors", records, {}, None
        )

        assert success == 0
        assert fail == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_records_with_txnid(self, orchestrator, mock_qbo_client, mock_transformer):
        """Transaction records use TxnID as source ID."""
        records = [
            {"TxnID": "TXN-001", "DocNumber": "001"},
            {"TxnID": "TXN-002", "DocNumber": "002"},
        ]

        mock_transformer.transform_entity.side_effect = [
            {"DocNumber": "001", "Line": []},
            {"DocNumber": "002", "Line": []},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "50", "SyncToken": "0"}},
                {"bId": "bid_1", "Invoice": {"Id": "51", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Invoices", records, existing_maps, None
        )

        assert success == 2
        assert existing_maps["Invoices"]["TXN-001"] == "50"
        assert existing_maps["Invoices"]["TXN-002"] == "51"

    def test_items_treated_as_parent_child(self, orchestrator):
        """Items entity type is in PARENT_CHILD_ENTITY_TYPES."""
        assert "Items" in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_customers_treated_as_parent_child(self, orchestrator):
        """Customers entity type is in PARENT_CHILD_ENTITY_TYPES."""
        assert "Customers" in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_invoices_not_parent_child(self, orchestrator):
        """Invoices are NOT parent-child — batched flat."""
        assert "Invoices" not in orchestrator.PARENT_CHILD_ENTITY_TYPES

    def test_batch_with_max_workers_1(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """With max_workers=1, batches are processed sequentially."""
        mock_qbo_client.max_workers = 1

        records = [{"ListID": f"V-{i}", "Name": f"V{i}"} for i in range(60)]

        mock_transformer.transform_entity.side_effect = [
            {"DisplayName": f"V{i}"} for i in range(60)
        ]

        def make_batch_response(*args, **kwargs):
            batch_data = args[2] if len(args) > 2 else kwargs.get("data", {})
            items = batch_data.get("BatchItemRequest", [])
            return {
                "BatchItemResponse": [
                    {"bId": item["bId"], "Vendor": {"Id": str(i), "SyncToken": "0"}}
                    for i, item in enumerate(items)
                ]
            }

        mock_qbo_client._make_request.side_effect = make_batch_response

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Vendors", records, {}, None
        )

        assert success == 60
        assert fail == 0


# ============================================================================
# FULL ORCHESTRATOR INTEGRATION
# ============================================================================


class TestBatchOrchestratorIntegration:
    """Tests verifying batch migration is wired into run_migration correctly."""

    def test_run_migration_calls_batch_method(self, orchestrator):
        """run_migration uses _migrate_entity_batch, not _migrate_entity."""
        with patch.object(orchestrator, "_init_encryption") as mock_enc, patch.object(
            orchestrator, "_init_oauth"
        ) as mock_oauth_init, patch.object(
            orchestrator, "_init_qbo_client"
        ) as mock_qbo_init, patch.object(
            orchestrator, "_init_transformer"
        ) as mock_tx_init, patch.object(
            orchestrator, "_init_verifier"
        ) as mock_ver_init, patch.object(
            orchestrator, "_migrate_entity_batch", return_value=(5, 0, 0)
        ) as mock_batch, patch.object(
            orchestrator, "_migrate_entity", return_value=(5, 0, 0)
        ) as mock_seq:

            # Setup mocks
            mock_enc_mgr = MagicMock()
            mock_enc_mgr.decrypt_chunked.return_value = json.dumps(
                {"Customers": [{"ListID": f"C-{i}", "Name": f"C{i}"} for i in range(5)]}
            )
            mock_enc.return_value = mock_enc_mgr

            mock_oauth = MagicMock()
            mock_oauth.get_valid_access_token.return_value = "test_token"
            mock_oauth_init.return_value = mock_oauth

            mock_qbo = MagicMock()
            mock_qbo.query_tax_agencies.return_value = []
            mock_qbo_init.return_value = mock_qbo

            mock_transformer = MagicMock()
            mock_transformer.id_mapping = {"tax_agencies": {}}
            mock_tx_init.return_value = mock_transformer

            mock_verifier = MagicMock()
            mock_verifier.verify_migration.return_value = {"status": "OK"}
            mock_ver_init.return_value = mock_verifier

            result = orchestrator.run_migration(
                encrypted_data=b"test",
                encryption_metadata={"key": "k", "iv": "i", "tag": "t"},
                company_name="Test Co",
            )

            # batch method should have been called (not sequential)
            assert mock_batch.called
            assert not mock_seq.called
            assert result["success"] is True

    def test_run_migration_passes_migration_id(self, orchestrator):
        """run_migration passes migration_id kwarg to _migrate_entity_batch."""
        with patch.object(orchestrator, "_init_encryption") as mock_enc, patch.object(
            orchestrator, "_init_oauth"
        ) as mock_oauth_init, patch.object(
            orchestrator, "_init_qbo_client"
        ) as mock_qbo_init, patch.object(
            orchestrator, "_init_transformer"
        ) as mock_tx_init, patch.object(
            orchestrator, "_init_verifier"
        ) as mock_ver_init, patch.object(
            orchestrator, "_migrate_entity_batch", return_value=(5, 0, 0)
        ) as mock_batch:

            mock_enc_mgr = MagicMock()
            mock_enc_mgr.decrypt_chunked.return_value = json.dumps(
                {"Customers": [{"ListID": f"C-{i}", "Name": f"C{i}"} for i in range(5)]}
            )
            mock_enc.return_value = mock_enc_mgr

            mock_oauth = MagicMock()
            mock_oauth.get_valid_access_token.return_value = "test_token"
            mock_oauth_init.return_value = mock_oauth

            mock_qbo = MagicMock()
            mock_qbo.query_tax_agencies.return_value = []
            mock_qbo_init.return_value = mock_qbo

            mock_transformer = MagicMock()
            mock_transformer.id_mapping = {"tax_agencies": {}}
            mock_tx_init.return_value = mock_transformer

            mock_verifier = MagicMock()
            mock_verifier.verify_migration.return_value = {"status": "OK"}
            mock_ver_init.return_value = mock_verifier

            orchestrator.run_migration(
                encrypted_data=b"test",
                encryption_metadata={"key": "k", "iv": "i", "tag": "t"},
                company_name="Test Co",
            )

            # Verify migration_id was passed as a keyword argument
            call_kwargs = mock_batch.call_args[1]
            assert "migration_id" in call_kwargs
            assert call_kwargs["migration_id"] is not None
            assert call_kwargs["migration_id"].startswith("mig_")


# ============================================================================
# DEDUPLICATION / CRASH RECOVERY TESTS
# ============================================================================


class TestBatchDeduplication:
    """Tests for crash recovery dedup via was_entity_created."""

    def test_already_migrated_entities_skipped(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Entities found in SQLite are skipped and their IDs restored."""
        records = [
            {"ListID": "V-001", "Name": "Already Done"},
            {"ListID": "V-002", "Name": "New One"},
        ]

        # V-001 was already created in a prior run
        mock_qbo_client.was_entity_created.side_effect = [
            "999",  # V-001 already exists with QBO ID 999
            None,  # V-002 not yet created
        ]

        mock_transformer.transform_entity.return_value = {"DisplayName": "New One"}

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "200", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Vendors",
            "Vendor",
            records,
            existing_maps,
            None,
        )

        assert skip == 1  # V-001 was skipped
        assert success == 1  # V-002 was created
        # V-001's mapping was restored from SQLite
        assert existing_maps["Vendors"]["V-001"] == "999"
        # V-002 was created fresh
        assert existing_maps["Vendors"]["V-002"] == "200"

    def test_all_already_migrated(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """All entities already migrated — no batch request sent."""
        records = [
            {"ListID": "V-001", "Name": "Done1"},
            {"ListID": "V-002", "Name": "Done2"},
        ]

        mock_qbo_client.was_entity_created.return_value = "42"

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert skip == 2
        assert success == 0
        assert fail == 0
        mock_qbo_client._make_request.assert_not_called()
        mock_transformer.transform_entity.assert_not_called()

    def test_dedup_restores_mappings_for_downstream(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Restored dedup mappings are available for downstream entity types."""
        records = [
            {"ListID": "CUST-001", "Name": "Acme"},
        ]

        mock_qbo_client.was_entity_created.return_value = "555"

        existing_maps = {}
        orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Customers",
            "Customer",
            records,
            existing_maps,
            None,
        )

        # The restored ID should be in existing_maps for Invoices to reference
        assert existing_maps["Customers"]["CUST-001"] == "555"

    def test_no_source_id_skips_dedup_check(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Records without ListID/TxnID/Id skip the dedup check."""
        records = [
            {"Name": "No ID Record"},
        ]

        mock_transformer.transform_entity.return_value = {"DisplayName": "No ID"}
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        success, fail, skip = orchestrator._batch_create_layer(
            mock_qbo_client, mock_transformer, "Vendors", "Vendor", records, {}, None
        )

        assert success == 1
        # was_entity_created should NOT have been called (no source_id)
        mock_qbo_client.was_entity_created.assert_not_called()


# ============================================================================
# IDEMPOTENCY AND MIGRATION_ID TESTS
# ============================================================================


class TestBatchIdempotency:
    """Tests for idempotency key and migration_id passthrough."""

    def test_idempotency_key_sent(self, orchestrator, mock_qbo_client):
        """_send_batch_request sends idempotency_key to _make_request."""
        batch_items = [("CUST-001", {"DisplayName": "Acme"})]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        orchestrator._send_batch_request(
            mock_qbo_client,
            "Customer",
            batch_items,
            None,
            migration_id="mig_abc123",
            batch_idx=7,
        )

        call_kwargs = mock_qbo_client._make_request.call_args[1]
        assert call_kwargs["idempotency_key"] == "batch_Customer_7_mig_abc123"

    def test_no_migration_id_no_idempotency(self, orchestrator, mock_qbo_client):
        """Without migration_id, idempotency_key is None."""
        batch_items = [("CUST-001", {"DisplayName": "Acme"})]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        orchestrator._send_batch_request(
            mock_qbo_client,
            "Customer",
            batch_items,
            None,
            migration_id=None,
            batch_idx=0,
        )

        call_kwargs = mock_qbo_client._make_request.call_args[1]
        assert call_kwargs["idempotency_key"] is None

    def test_migration_id_passed_to_record_created(self, orchestrator, mock_qbo_client):
        """record_created receives migration_id as 4th positional arg."""
        batch_items = [("CUST-001", {"DisplayName": "Acme"})]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        orchestrator._send_batch_request(
            mock_qbo_client,
            "Customer",
            batch_items,
            None,
            migration_id="mig_xyz",
            batch_idx=0,
        )

        # record_created(entity_type, qbd_id, qbo_id, migration_id, sync_token)
        mock_qbo_client.record_created.assert_called_once_with(
            "Customer", "CUST-001", "100", "mig_xyz", "0"
        )


# ============================================================================
# REAL TRANSFORMER INTEGRATION TESTS (no mocks)
# ============================================================================


class TestBatchWithRealTransformer:
    """
    Tests the batch path using the REAL QBDataTransformer (not mocked).
    Catches field-level issues like ID mapping key mismatches, ParentRef
    resolution, and transform failures that mock-based tests miss.
    """

    @pytest.fixture
    def real_transformer(self):
        from data_transformer import QBDataTransformer

        return QBDataTransformer(region="US")

    def test_accounts_parent_child_id_mapping(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """
        Full flow: Transform parent account → batch create → capture ID →
        Transform child account → child resolves parent QBO ID.
        """
        records = [
            {
                "ListID": "P1",
                "Name": "Bank Accounts",
                "AccountType": "Bank",
                "IsActive": True,
            },
            {
                "ListID": "C1",
                "Name": "Checking",
                "AccountType": "Bank",
                "IsActive": True,
                "ParentRef": "P1",
            },
        ]

        # Simulate QBO batch responses
        mock_qbo_client._make_request.side_effect = [
            # Layer 0 (root): Bank Accounts → QBO ID 500
            {
                "BatchItemResponse": [
                    {"bId": "bid_0", "Account": {"Id": "500", "SyncToken": "0"}},
                ]
            },
            # Layer 1 (child): Checking → QBO ID 501
            {
                "BatchItemResponse": [
                    {"bId": "bid_0", "Account": {"Id": "501", "SyncToken": "0"}},
                ]
            },
        ]

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "Accounts", records, existing_maps, None
        )

        assert success == 2
        assert fail == 0
        assert existing_maps["Accounts"]["P1"] == "500"
        assert existing_maps["Accounts"]["C1"] == "501"

        # Verify the child's batch request included ParentRef
        # The second _make_request call is the child batch
        second_call = mock_qbo_client._make_request.call_args_list[1]
        child_batch_data = second_call[0][2]  # 3rd positional arg = data
        child_entity = child_batch_data["BatchItemRequest"][0]["Account"]
        # ParentRef should reference the parent's QBO ID (500)
        assert child_entity.get("SubAccount") is True
        assert child_entity.get("ParentRef", {}).get("value") == "500"

    def test_customer_transform_and_batch(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """Customers with real transformer produce correct QBO format."""
        records = [
            {
                "ListID": "CUST-001",
                "Name": "Acme Corp",
                "IsActive": True,
                "CompanyName": "Acme Inc",
                "Phone": "555-1234",
            },
            {"ListID": "CUST-002", "Name": "Global LLC", "IsActive": True},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Customer": {"Id": "10", "SyncToken": "0"}},
                {"bId": "bid_1", "Customer": {"Id": "11", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "Customers", records, existing_maps, None
        )

        assert success == 2
        assert existing_maps["Customers"]["CUST-001"] == "10"
        assert existing_maps["Customers"]["CUST-002"] == "11"

        # Verify QBO format was correct
        call_data = mock_qbo_client._make_request.call_args[0][2]
        cust_1 = call_data["BatchItemRequest"][0]["Customer"]
        assert "DisplayName" in cust_1

    def test_cross_type_id_propagation(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """
        IDs from Accounts phase are available when transforming Items.
        Tests the full cross-entity-type ID mapping chain.
        """
        # Phase 1: Migrate accounts first
        account_records = [
            {
                "ListID": "INC-001",
                "Name": "Sales Income",
                "AccountType": "Income",
                "IsActive": True,
            },
            {
                "ListID": "EXP-001",
                "Name": "Cost of Sales",
                "AccountType": "Cost of Goods Sold",
                "IsActive": True,
            },
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "700", "SyncToken": "0"}},
                {"bId": "bid_1", "Account": {"Id": "701", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        orchestrator._migrate_entity_batch(
            mock_qbo_client,
            real_transformer,
            "Accounts",
            account_records,
            existing_maps,
            None,
        )

        assert existing_maps["Accounts"]["INC-001"] == "700"
        assert existing_maps["Accounts"]["EXP-001"] == "701"

        # Phase 2: Migrate items — they reference accounts via IncomeAccountRef
        # Need 2+ records so the batch path runs (≤1 falls back to sequential)
        item_records = [
            {
                "ListID": "ITEM-001",
                "Name": "Widget",
                "ItemType": "Inventory",
                "IsActive": True,
                "UnitPrice": "25.00",
                "QuantityOnHand": "10",
                "AsOfDate": "2024-01-01",
                "IncomeAccountRef": "INC-001",
                "ExpenseAccountRef": "EXP-001",
            },
            {
                "ListID": "ITEM-002",
                "Name": "Gadget",
                "ItemType": "Service",
                "IsActive": True,
                "UnitPrice": "15.00",
            },
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Item": {"Id": "800", "SyncToken": "0"}},
                {"bId": "bid_1", "Item": {"Id": "801", "SyncToken": "0"}},
            ]
        }

        orchestrator._migrate_entity_batch(
            mock_qbo_client,
            real_transformer,
            "Items",
            item_records,
            existing_maps,
            None,
        )

        assert existing_maps["Items"]["ITEM-001"] == "800"
        assert existing_maps["Items"]["ITEM-002"] == "801"

        # Verify the Inventory item's IncomeAccountRef was resolved to QBO ID
        call_data = mock_qbo_client._make_request.call_args[0][2]
        item_entities = {
            req["bId"]: req["Item"]
            for req in call_data["BatchItemRequest"]
            if "Item" in req
        }
        inv_item = item_entities.get("bid_0", {})
        income_ref = inv_item.get("IncomeAccountRef", {})
        assert income_ref.get("value") == "700"

    def test_vendor_batch_with_real_transformer(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """Vendors produce valid QBO format through batch pipeline."""
        records = [
            {
                "ListID": "VEND-001",
                "Name": "Supply Corp",
                "IsActive": True,
                "CompanyName": "Supply Corp LLC",
            },
            {"ListID": "VEND-002", "Name": "Parts Inc", "IsActive": True},
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "300", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "301", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "Vendors", records, existing_maps, None
        )

        assert success == 2
        assert fail == 0

        call_data = mock_qbo_client._make_request.call_args[0][2]
        vendor_1 = call_data["BatchItemRequest"][0]["Vendor"]
        assert "DisplayName" in vendor_1

    def test_taxcode_routes_to_tax_service(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """
        TaxCode entities with real transformer set _use_tax_service flag
        and are routed to create_tax_service, not the batch endpoint.
        """
        # Pre-populate tax agency mapping (normally done during run_migration)
        real_transformer.id_mapping["tax_agencies"]["AGENCY-001"] = "1"

        records = [
            {
                "ListID": "TC-001",
                "Name": "CA Sales Tax",
                "TaxRates": [
                    {
                        "Name": "CA State",
                        "Rate": "7.25",
                        "AgencyRef": "AGENCY-001",
                        "ApplicableOn": "Sales",
                    }
                ],
            },
            {
                "ListID": "TC-002",
                "Name": "OR Sales Tax",
                "TaxRates": [
                    {
                        "Name": "OR State",
                        "Rate": "0",
                        "AgencyRef": "AGENCY-001",
                        "ApplicableOn": "Sales",
                    }
                ],
            },
        ]

        mock_qbo_client.create_tax_service.side_effect = [
            {"TaxCodeId": "50"},
            {"TaxCodeId": "51"},
        ]

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "TaxCodes", records, existing_maps, None
        )

        assert success == 2
        assert fail == 0
        # TaxService route, not batch endpoint
        mock_qbo_client._make_request.assert_not_called()
        assert mock_qbo_client.create_tax_service.call_count == 2
        assert existing_maps["TaxCodes"]["TC-001"] == "50"
        assert existing_maps["TaxCodes"]["TC-002"] == "51"

    def test_taxagency_returns_none_all_skipped(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """TaxAgency entities return None from transformer — all skipped."""
        records = [
            {"ListID": "TA-001", "Name": "IRS"},
            {"ListID": "TA-002", "Name": "State Board"},
        ]

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "TaxAgencies", records, {}, None
        )

        assert success == 0
        assert fail == 0
        assert skip == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_invoice_skipped_without_customer_ref(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """
        Invoices without a valid CustomerRef mapping are skipped by the
        real transformer (returns None), not sent to QBO.
        """
        records = [
            {
                "TxnID": "INV-001",
                "RefNumber": "1001",
                "CustomerRef": "NONEXISTENT",
                "TxnDate": "2024-01-15",
                "InvoiceLines": [],
            },
            {
                "TxnID": "INV-002",
                "RefNumber": "1002",
                "CustomerRef": "NONEXISTENT",
                "TxnDate": "2024-01-16",
                "InvoiceLines": [],
            },
        ]

        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "Invoices", records, {}, None
        )

        # Both should be skipped (no customer mapping)
        assert success == 0
        assert skip == 2
        mock_qbo_client._make_request.assert_not_called()

    def test_mixed_success_and_skip_with_real_transformer(
        self, orchestrator, mock_qbo_client, real_transformer
    ):
        """Some entities transform successfully, others skip."""
        # Pre-populate customer and item mappings so valid invoice can resolve
        real_transformer.id_mapping["customers"]["CUST-001"] = "10"
        real_transformer.id_mapping["items"]["SVC-001"] = "50"

        records = [
            # This one has a valid customer ref and valid line item
            {
                "TxnID": "INV-001",
                "RefNumber": "1001",
                "CustomerRef": "CUST-001",
                "TxnDate": "2024-01-15",
                "InvoiceLines": [
                    {
                        "Amount": "100.00",
                        "Description": "Service",
                        "ItemRef": "SVC-001",
                        "Quantity": "1",
                        "Rate": "100.00",
                    }
                ],
            },
            # This one references a nonexistent customer — will be skipped
            {
                "TxnID": "INV-002",
                "RefNumber": "1002",
                "CustomerRef": "NONEXISTENT",
                "TxnDate": "2024-01-16",
                "InvoiceLines": [{"Amount": "50.00", "ItemRef": "SVC-001"}],
            },
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "900", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, real_transformer, "Invoices", records, existing_maps, None
        )

        assert success == 1
        assert skip >= 1  # At least INV-002 skipped
        assert existing_maps.get("Invoices", {}).get("INV-001") == "900"


# ============================================================================
# CORNER CASE: SEQUENTIAL FALLBACK CRASH RECOVERY
# ============================================================================


class TestSequentialFallbackCrashRecovery:
    """
    When source_data has ≤1 record, _migrate_entity_batch falls back to
    the sequential _migrate_entity path. That path must also perform
    crash recovery via was_entity_created().
    """

    def test_single_record_fallback_skips_already_migrated(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Single-record fallback checks was_entity_created and skips."""
        records = [{"ListID": "ACC-001", "Name": "Checking"}]

        mock_qbo_client.was_entity_created.return_value = "42"

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert skip == 1
        assert success == 0
        assert fail == 0
        # The restored mapping should be in existing_maps
        assert existing_maps["Accounts"]["ACC-001"] == "42"
        # create_entity should NOT have been called
        mock_qbo_client.create_entity.assert_not_called()
        mock_transformer.transform_entity.assert_not_called()

    def test_single_record_fallback_creates_when_not_migrated(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Single-record fallback creates entity when not previously migrated."""
        records = [{"ListID": "ACC-001", "Name": "Checking"}]

        mock_qbo_client.was_entity_created.return_value = None
        mock_transformer.transform_entity.return_value = {
            "Name": "Checking",
            "AccountType": "Bank",
        }
        mock_qbo_client.create_entity.return_value = {"Id": "99", "SyncToken": "0"}

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert success == 1
        assert fail == 0
        assert existing_maps["Accounts"]["ACC-001"] == "99"
        mock_qbo_client.create_entity.assert_called_once()

    def test_empty_records_returns_zeros(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Empty source_data returns (0, 0, 0) without calling any APIs."""
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Vendors", [], {}, None
        )

        assert success == 0
        assert fail == 0
        assert skip == 0
        mock_qbo_client._make_request.assert_not_called()
        mock_qbo_client.create_entity.assert_not_called()


# ============================================================================
# CORNER CASE: MISSING / EXTRA BATCH RESPONSES
# ============================================================================


class TestBatchResponseAccounting:
    """
    QBO may return fewer BatchItemResponse entries than we sent.
    Missing items must be counted as failures.
    """

    def test_missing_responses_counted_as_failures(self, orchestrator, mock_qbo_client):
        """If QBO returns fewer responses, missing items are failed."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
            ("V-002", {"DisplayName": "Vendor 2"}),
            ("V-003", {"DisplayName": "Vendor 3"}),
        ]

        # QBO only returns 1 response for 3 items sent
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
            ]
        }

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        assert len(mappings) == 1
        assert fail_count == 2  # V-002 and V-003 unaccounted

    def test_all_responses_present_no_extra_failures(
        self, orchestrator, mock_qbo_client
    ):
        """When all responses are present, no extra failures counted."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
            ("V-002", {"DisplayName": "Vendor 2"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Vendor": {"Id": "101", "SyncToken": "0"}},
            ]
        }

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        assert len(mappings) == 2
        assert fail_count == 0

    def test_partial_success_partial_fault_fully_accounted(
        self, orchestrator, mock_qbo_client
    ):
        """Mix of successes and faults — all items accounted for."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
            ("V-002", {"DisplayName": "Vendor 2"}),
            ("V-003", {"DisplayName": "Vendor 3"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_1", "Fault": {"Error": [{"Message": "Duplicate name"}]}},
                {"bId": "bid_2", "Vendor": {"Id": "102", "SyncToken": "0"}},
            ]
        }

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        assert len(mappings) == 2  # V-001 and V-003
        assert fail_count == 1  # V-002 faulted
        # Total accounted = 2 + 1 = 3 = len(batch_items), so no extra

    def test_network_error_all_items_failed(self, orchestrator, mock_qbo_client):
        """Network exception counts all items as failed."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
            ("V-002", {"DisplayName": "Vendor 2"}),
        ]

        mock_qbo_client._make_request.side_effect = ConnectionError("timeout")

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        assert len(mappings) == 0
        assert fail_count == 2

    def test_extra_bids_in_response_ignored_gracefully(
        self, orchestrator, mock_qbo_client
    ):
        """Extra bIds in response that we didn't send don't cause errors."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
        ]

        # QBO returns 2 responses but we only sent 1
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"Id": "100", "SyncToken": "0"}},
                {"bId": "bid_99", "Vendor": {"Id": "999", "SyncToken": "0"}},
            ]
        }

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        # bid_0 matched, bid_99 is extra (source_id=None)
        assert len(mappings) == 2  # Both are "successes" per response
        # No unaccounted items (2 success + 0 fail >= 1 sent)
        # Extra response doesn't cause negative unaccounted

    def test_response_with_no_id_counted_as_failure(
        self, orchestrator, mock_qbo_client
    ):
        """Entity in response but no 'Id' field is counted as failure."""
        batch_items = [
            ("V-001", {"DisplayName": "Vendor 1"}),
        ]

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Vendor": {"SyncToken": "0"}},  # No Id
            ]
        }

        mappings, fail_count = orchestrator._send_batch_request(
            mock_qbo_client, "Vendor", batch_items, None
        )

        assert len(mappings) == 0
        assert fail_count == 1


# ============================================================================
# CORNER CASE: LAYER PROCESSING EDGE CASES
# ============================================================================


class TestLayerProcessingEdgeCases:
    """Edge cases in parent-child layer splitting and processing."""

    def test_deeply_nested_hierarchy(self, orchestrator):
        """5 levels of parent-child nesting resolves correctly."""
        records = [
            {"ListID": "L5", "Name": "Level 5", "ParentRef": "L4"},
            {"ListID": "L4", "Name": "Level 4", "ParentRef": "L3"},
            {"ListID": "L3", "Name": "Level 3", "ParentRef": "L2"},
            {"ListID": "L2", "Name": "Level 2", "ParentRef": "L1"},
            {"ListID": "L1", "Name": "Level 1"},  # root
        ]

        layers = orchestrator._split_parent_child_layers(records)

        assert len(layers) == 5
        # Root is in first layer
        assert layers[0][0]["ListID"] == "L1"
        # Deepest child is in last layer
        assert layers[4][0]["ListID"] == "L5"

    def test_multiple_roots_multiple_children(self, orchestrator):
        """Multiple roots each with children split into 2 layers."""
        records = [
            {"ListID": "R1", "Name": "Root 1"},
            {"ListID": "R2", "Name": "Root 2"},
            {"ListID": "C1", "Name": "Child of R1", "ParentRef": "R1"},
            {"ListID": "C2", "Name": "Child of R2", "ParentRef": "R2"},
        ]

        layers = orchestrator._split_parent_child_layers(records)

        assert len(layers) == 2
        root_ids = {r["ListID"] for r in layers[0]}
        child_ids = {r["ListID"] for r in layers[1]}
        assert root_ids == {"R1", "R2"}
        assert child_ids == {"C1", "C2"}

    def test_all_records_are_children_of_missing_parents(self, orchestrator):
        """When all parents are missing, records dumped into single layer."""
        records = [
            {"ListID": "C1", "Name": "Orphan 1", "ParentRef": "MISSING"},
            {"ListID": "C2", "Name": "Orphan 2", "ParentRef": "MISSING"},
        ]

        layers = orchestrator._split_parent_child_layers(records)

        # All placed in one layer (orphan handling)
        assert len(layers) == 1
        assert len(layers[0]) == 2

    def test_parent_child_with_batch_creates_layers_sequentially(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """
        Parent layer batch completes before child layer starts.
        Verifies layer ordering: parent QBO IDs available for children.
        """
        records = [
            {"ListID": "P1", "Name": "Parent"},
            {"ListID": "C1", "Name": "Child", "ParentRef": "P1"},
        ]

        mock_transformer.transform_entity.return_value = {"Name": "Entity"}

        # Track call order
        call_order = []

        def track_make_request(*args, **kwargs):
            data = args[2] if len(args) > 2 else kwargs.get("data", {})
            batch_items = data.get("BatchItemRequest", [])
            bids = [item.get("bId") for item in batch_items]
            call_order.append(bids)

            responses = []
            for item in batch_items:
                bid = item["bId"]
                responses.append(
                    {"bId": bid, "Account": {"Id": f"QBO-{bid}", "SyncToken": "0"}}
                )
            return {"BatchItemResponse": responses}

        mock_qbo_client._make_request.side_effect = track_make_request

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert success == 2
        # Layer 0 (parent) processed before Layer 1 (child)
        assert len(call_order) == 2
        assert call_order[0] == ["bid_0"]  # Parent layer
        assert call_order[1] == ["bid_0"]  # Child layer

    def test_single_layer_for_flat_entity_types(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Flat entity types (Invoices, Bills) skip layer splitting."""
        records = [
            {"TxnID": "INV-001", "RefNumber": "1001"},
            {"TxnID": "INV-002", "RefNumber": "1002"},
        ]

        mock_transformer.transform_entity.return_value = {
            "CustomerRef": {"value": "10"},
            "Line": [],
        }

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Invoice": {"Id": "500", "SyncToken": "0"}},
                {"bId": "bid_1", "Invoice": {"Id": "501", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Invoices", records, existing_maps, None
        )

        assert success == 2
        # Only 1 _make_request call (no layer splitting)
        assert mock_qbo_client._make_request.call_count == 1


# ============================================================================
# CORNER CASE: DEDUP ACROSS DEPENDENCY LAYERS
# ============================================================================


class TestDedupAcrossLayers:
    """Crash recovery between dependency layers within a single entity type."""

    def test_parent_already_migrated_child_still_creates(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """
        Parent was migrated in prior run (deduped), child is new.
        The restored parent mapping must be available for child transform.
        """
        records = [
            {"ListID": "P1", "Name": "Parent"},
            {"ListID": "C1", "Name": "Child", "ParentRef": "P1"},
        ]

        # P1 already created with QBO ID 42
        def was_entity_created(entity_type, qbd_id):
            if qbd_id == "P1":
                return "42"
            return None

        mock_qbo_client.was_entity_created.side_effect = was_entity_created

        mock_transformer.transform_entity.return_value = {
            "Name": "Child",
            "ParentRef": {"value": "42"},
        }

        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {"bId": "bid_0", "Account": {"Id": "99", "SyncToken": "0"}},
            ]
        }

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert skip == 1  # P1 deduped
        assert success == 1  # C1 created
        assert existing_maps["Accounts"]["P1"] == "42"
        assert existing_maps["Accounts"]["C1"] == "99"

    def test_all_layers_already_migrated(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Full parent-child hierarchy already migrated — no API calls."""
        records = [
            {"ListID": "P1", "Name": "Parent"},
            {"ListID": "C1", "Name": "Child", "ParentRef": "P1"},
        ]

        mock_qbo_client.was_entity_created.return_value = "42"

        existing_maps = {}
        success, fail, skip = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert skip == 2
        assert success == 0
        assert fail == 0
        mock_qbo_client._make_request.assert_not_called()
        mock_transformer.transform_entity.assert_not_called()


# ============================================================================
# C# EXTRACTOR CAMELCASE FIELD HANDLING TESTS
# ============================================================================


class TestExtractSourceId:
    """Tests for _extract_source_id helper — handles both PascalCase and camelCase."""

    def test_pascal_list_id(self):
        record = {"ListID": "ACC-001", "Name": "Checking"}
        assert MigrationOrchestrator._extract_source_id(record) == "ACC-001"

    def test_camel_list_id(self):
        """C# extractor outputs listId, not ListID."""
        record = {"listId": "80000001-1234", "name": "Savings"}
        assert MigrationOrchestrator._extract_source_id(record) == "80000001-1234"

    def test_pascal_txn_id(self):
        record = {"TxnID": "TXN-001", "RefNumber": "1001"}
        assert MigrationOrchestrator._extract_source_id(record) == "TXN-001"

    def test_camel_txn_id(self):
        """C# extractor outputs txnId, not TxnID."""
        record = {"txnId": "80000002-5678", "refNumber": "1002"}
        assert MigrationOrchestrator._extract_source_id(record) == "80000002-5678"

    def test_qbo_style_id(self):
        record = {"Id": "42", "Name": "QBO Entity"}
        assert MigrationOrchestrator._extract_source_id(record) == "42"

    def test_no_id_returns_none(self):
        record = {"Name": "No ID Entity"}
        assert MigrationOrchestrator._extract_source_id(record) is None

    def test_empty_record_returns_none(self):
        assert MigrationOrchestrator._extract_source_id({}) is None

    def test_prefers_pascal_list_id_over_camel(self):
        """When both PascalCase and camelCase exist, PascalCase wins (already normalized)."""
        record = {"ListID": "PASCAL-ID", "listId": "camel-id"}
        assert MigrationOrchestrator._extract_source_id(record) == "PASCAL-ID"

    def test_numeric_id_returned_as_string(self):
        record = {"ListID": 12345}
        assert MigrationOrchestrator._extract_source_id(record) == "12345"

    def test_camel_list_id_falls_through_to_txn_id(self):
        """Record with only txnId (no listId)."""
        record = {"txnId": "TXN-CAMEL", "txnDate": "2024-01-01"}
        assert MigrationOrchestrator._extract_source_id(record) == "TXN-CAMEL"


class TestGetParentIdCamelCase:
    """Tests for _get_parent_id with C# extractor camelCase field names."""

    def test_camel_parent_ref_list_id_flat(self):
        """C# extractor outputs parentRefListId as a flat field."""
        record = {"listId": "ACC-002", "parentRefListId": "ACC-001"}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_camel_parent_ref_full_name_flat(self):
        """C# extractor outputs parentRefFullName as a flat field."""
        record = {"listId": "CLS-002", "parentRefFullName": "Parent:Child"}
        assert MigrationOrchestrator._get_parent_id(record) == "Parent:Child"

    def test_pascal_parent_ref_full_name(self):
        """Already-normalized ParentRefFullName."""
        record = {"ListID": "CLS-002", "ParentRefFullName": "TopLevel"}
        assert MigrationOrchestrator._get_parent_id(record) == "TopLevel"

    def test_dict_parent_ref_with_camel_list_id(self):
        """parentRef dict with listId (camelCase) inside."""
        record = {"listId": "ACC-002", "parentRef": {"listId": "ACC-001"}}
        assert MigrationOrchestrator._get_parent_id(record) == "ACC-001"

    def test_no_parent_camel_record(self):
        """C# extractor record with no parent ref."""
        record = {"listId": "ACC-001", "name": "Root Account"}
        assert MigrationOrchestrator._get_parent_id(record) is None

    def test_camel_parent_ref_list_id_vs_pascal(self):
        """Both parentRefListId and ParentRef_ListID — PascalCase wins (checked first)."""
        record = {
            "listId": "ACC-003",
            "ParentRef_ListID": "PASCAL-PARENT",
            "parentRefListId": "CAMEL-PARENT",
        }
        assert MigrationOrchestrator._get_parent_id(record) == "PASCAL-PARENT"


class TestSplitParentChildLayersCamelCase:
    """Tests for _split_parent_child_layers with C# extractor camelCase records."""

    def test_camel_case_two_layers(self, orchestrator):
        """Layering works with camelCase listId and parentRefListId."""
        records = [
            {"listId": "C1", "name": "Child", "parentRefListId": "P1"},
            {"listId": "P1", "name": "Parent"},
        ]
        layers = orchestrator._split_parent_child_layers(records)
        assert len(layers) == 2
        # Layer 0 = root (P1), Layer 1 = child (C1)
        layer0_ids = {r["listId"] for r in layers[0]}
        layer1_ids = {r["listId"] for r in layers[1]}
        assert "P1" in layer0_ids
        assert "C1" in layer1_ids

    def test_camel_case_three_layers(self, orchestrator):
        """Three-level hierarchy with camelCase fields."""
        records = [
            {"listId": "GC1", "name": "Grandchild", "parentRefListId": "C1"},
            {"listId": "C1", "name": "Child", "parentRefListId": "P1"},
            {"listId": "P1", "name": "Parent"},
        ]
        layers = orchestrator._split_parent_child_layers(records)
        assert len(layers) == 3

    def test_mixed_pascal_and_camel(self, orchestrator):
        """Mix of PascalCase and camelCase records in same dataset."""
        records = [
            {"ListID": "P1", "Name": "PascalParent"},
            {"listId": "C1", "name": "CamelChild", "parentRefListId": "P1"},
            {"ListID": "C2", "Name": "PascalChild", "ParentRef": "P1"},
        ]
        layers = orchestrator._split_parent_child_layers(records)
        assert len(layers) == 2
        # All three records should be correctly layered
        root_ids = {MigrationOrchestrator._extract_source_id(r) for r in layers[0]}
        child_ids = {MigrationOrchestrator._extract_source_id(r) for r in layers[1]}
        assert root_ids == {"P1"}
        assert child_ids == {"C1", "C2"}

    def test_camel_all_roots(self, orchestrator):
        """All camelCase records are roots (no parent refs)."""
        records = [
            {"listId": "A1", "name": "Account1"},
            {"listId": "A2", "name": "Account2"},
        ]
        layers = orchestrator._split_parent_child_layers(records)
        assert len(layers) == 1
        assert len(layers[0]) == 2


class TestBatchCreateLayerCamelCase:
    """Tests for _batch_create_layer dedup with camelCase source IDs."""

    def test_dedup_with_camel_list_id(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Crash recovery dedup works when records have camelCase listId."""
        records = [
            {"listId": "80000001", "name": "Already Migrated"},
            {"listId": "80000002", "name": "New Record"},
        ]

        # First record already migrated
        def was_created_side_effect(entity_type, qbd_id):
            if qbd_id == "80000001":
                return "42"
            return None

        mock_qbo_client.was_entity_created.side_effect = was_created_side_effect

        mock_transformer.transform_entity.return_value = {
            "Name": "New Record",
            "AccountType": "Bank",
        }

        # Mock batch response for the one new record
        mock_qbo_client._make_request.return_value = {
            "BatchItemResponse": [
                {
                    "bId": "bid-0",
                    "Account": {"Id": "99", "SyncToken": "0", "Name": "New Record"},
                }
            ]
        }

        existing_maps = {}
        s, f, sk = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Accounts",
            "Account",
            records,
            existing_maps,
            None,
            "mig-001",
        )

        assert sk == 1  # 80000001 skipped (already migrated)
        assert s == 1  # 80000002 created
        assert existing_maps["Accounts"]["80000001"] == "42"

    def test_dedup_with_camel_txn_id(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Crash recovery dedup works with camelCase txnId."""
        records = [
            {"txnId": "TXN-001", "refNumber": "1001"},
        ]

        mock_qbo_client.was_entity_created.return_value = "55"

        existing_maps = {}
        s, f, sk = orchestrator._batch_create_layer(
            mock_qbo_client,
            mock_transformer,
            "Invoices",
            "Invoice",
            records,
            existing_maps,
            None,
            "mig-002",
        )

        assert sk == 1
        assert s == 0
        assert existing_maps["Invoices"]["TXN-001"] == "55"

    def test_sequential_fallback_with_camel_source_id(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Sequential fallback (_migrate_entity) handles camelCase listId for dedup."""
        records = [
            {"listId": "80000001", "name": "Already Done"},
        ]

        mock_qbo_client.was_entity_created.return_value = "42"

        existing_maps = {}
        # With 1 record, _migrate_entity_batch falls back to _migrate_entity
        s, f, sk = orchestrator._migrate_entity_batch(
            mock_qbo_client,
            mock_transformer,
            "Accounts",
            records,
            existing_maps,
            None,
            "mig-003",
        )

        assert sk == 1
        assert s == 0
        assert existing_maps["Accounts"]["80000001"] == "42"

    def test_sequential_fallback_post_success_mapping_with_camel(
        self, orchestrator, mock_qbo_client, mock_transformer
    ):
        """Sequential fallback correctly maps source_id after successful create with camelCase."""
        records = [
            {"listId": "80000001", "name": "New Account"},
        ]

        mock_qbo_client.was_entity_created.return_value = None
        mock_transformer.transform_entity.return_value = {
            "Name": "New Account",
            "AccountType": "Bank",
        }
        mock_qbo_client.create_entity.return_value = {"Id": "99", "SyncToken": "0"}

        existing_maps = {}
        s, f, sk = orchestrator._migrate_entity_batch(
            mock_qbo_client, mock_transformer, "Accounts", records, existing_maps, None
        )

        assert s == 1
        assert existing_maps["Accounts"]["80000001"] == "99"
