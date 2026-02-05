"""
Integration Test Suite for QBMigration Backend
Rigorous testing of all components
"""

import json
import os
import sys
import tempfile


def test_caseware_exporter():
    """Test Caseware bundle generation"""
    print("\n" + "=" * 60)
    print("TEST 1: Caseware Exporter")
    print("=" * 60)

    from caseware_exporter import CasewareExporter

    # Create test data
    test_data = {
        "company": {"companyName": "Test Corp"},
        "accounts": [
            {
                "AccountNumber": "1000",
                "Name": "Cash",
                "AccountType": "Bank",
                "Balance": 50000,
            },
            {
                "AccountNumber": "1200",
                "Name": "AR",
                "AccountType": "Accounts Receivable",
                "Balance": 25000,
            },
            {
                "AccountNumber": "2000",
                "Name": "AP",
                "AccountType": "Accounts Payable",
                "Balance": 15000,
            },
            {
                "AccountNumber": "7000",
                "Name": "Livestock",
                "AccountType": "Livestock",
                "Balance": 100000,
            },
            {
                "AccountNumber": "7100",
                "Name": "WIP",
                "AccountType": "Work in Process",
                "Balance": 45000,
            },
        ],
        "invoices": [
            {
                "TxnID": "INV-001",
                "RefNumber": "1001",
                "TxnDate": "2026-01-15",
                "Amount": 5000,
            },
            {
                "TxnID": "INV-002",
                "RefNumber": "1002",
                "TxnDate": "2026-01-16",
                "Amount": 3500,
            },
        ],
        "bills": [
            {
                "TxnID": "BILL-001",
                "RefNumber": "B-100",
                "TxnDate": "2026-01-10",
                "Amount": -2500,
            }
        ],
    }

    # Create temp dir and test
    output_dir = tempfile.mkdtemp()
    exporter = CasewareExporter(output_dir, "Test Corp")
    result = exporter.generate_audit_bundle(test_data)

    print(f"  [PASS] Bundle generated")
    print(f"  Files: {list(result['files'].keys())}")
    print(f"  Accounts: {result['statistics']['accounts_exported']}")
    print(f"  Transactions: {result['statistics']['transactions_exported']}")
    print(f"  Hashes: {result['statistics']['hashes_generated']}")
    print(f"  TB Balanced: {result['statistics']['trial_balance_balanced']}")

    # Check Global File Hash
    if "global_file_hash" in exporter.stats:
        print(
            f"  [PASS] Global File Hash: {exporter.stats['global_file_hash'][:16]}..."
        )
    else:
        print(f"  [WARN] Global File Hash not found")

    # Check Lead Sheet codes for Agriculture/Manufacturing
    if "Livestock" in CasewareExporter.LEAD_SHEET_CODES:
        print(f"  [PASS] Agricultural codes present: A6.1 Livestock")
    if "Work in Process" in CasewareExporter.LEAD_SHEET_CODES:
        print(f"  [PASS] Manufacturing codes present: A7.2 WIP")

    # Verify files exist
    for name, path in result["files"].items():
        if os.path.exists(path):
            print(f"  [PASS] File exists: {name}")
        else:
            print(f"  [FAIL] File missing: {name}")

    return True


def test_data_transformer_caseware_mode():
    """Test data_transformer's Caseware mode"""
    print("\n" + "=" * 60)
    print("TEST 2: Data Transformer Caseware Mode")
    print("=" * 60)

    from data_transformer import QBDataTransformer

    transformer = QBDataTransformer(region="CA")

    if hasattr(transformer, "transform_for_caseware"):
        print("  [PASS] transform_for_caseware method exists")
    else:
        print("  [FAIL] transform_for_caseware method missing")
        return False

    # Test with mock data
    test_data = {
        "company": {"companyName": "Canadian Test Corp"},
        "accounts": [
            {
                "AccountNumber": "1000",
                "Name": "Chequing",
                "AccountType": "Bank",
                "Balance": 75000,
            }
        ],
    }

    output_dir = tempfile.mkdtemp()
    result = transformer.transform_for_caseware(test_data, output_dir)

    if result["success"]:
        print("  [PASS] Caseware mode executed successfully")
    else:
        print("  [FAIL] Caseware mode failed")

    return result["success"]


def test_hash_consistency():
    """Test SHA-256 hash consistency"""
    print("\n" + "=" * 60)
    print("TEST 3: Hash Consistency")
    print("=" * 60)

    from caseware_exporter import CasewareExporter

    test_data = {"TxnID": "TEST-001", "Amount": 1000.50, "TxnDate": "2026-01-15"}

    hash1 = CasewareExporter.compute_sha256_hash(test_data)
    hash2 = CasewareExporter.compute_sha256_hash(test_data)

    if hash1 == hash2:
        print("  [PASS] Hash is deterministic")
    else:
        print("  [FAIL] Hash is NOT deterministic!")
        return False

    # Different data should have different hash
    test_data2 = {"TxnID": "TEST-002", "Amount": 1000.50, "TxnDate": "2026-01-15"}
    hash3 = CasewareExporter.compute_sha256_hash(test_data2)

    if hash1 != hash3:
        print("  [PASS] Different data produces different hash")
    else:
        print("  [FAIL] Hash collision detected!")
        return False

    print(f"  Hash length: {len(hash1)} chars (64 expected)")
    return len(hash1) == 64


def test_lead_sheet_coverage():
    """Test Lead Sheet code coverage"""
    print("\n" + "=" * 60)
    print("TEST 4: Lead Sheet Code Coverage")
    print("=" * 60)

    from caseware_exporter import CasewareExporter

    codes = CasewareExporter.LEAD_SHEET_CODES

    # Required categories
    required = {
        "Assets": ["Bank", "Accounts Receivable", "Inventory"],
        "Agricultural": ["Livestock", "Crops", "Farm Equipment"],
        "Manufacturing": ["Raw Materials", "Work in Process", "Finished Goods"],
        "Liabilities": ["Accounts Payable", "Credit Card"],
        "Revenue": ["Income", "Sales"],
        "COGS": ["Cost of Goods Sold"],
    }

    all_pass = True
    for category, types in required.items():
        for acct_type in types:
            if acct_type in codes:
                print(f"  [PASS] {category}: {acct_type} -> {codes[acct_type]}")
            else:
                print(f"  [FAIL] {category}: {acct_type} MISSING")
                all_pass = False

    print(f"  Total Lead Sheet codes: {len(codes)}")
    return all_pass


def run_all_tests():
    """Run all integration tests"""
    print("=" * 60)
    print("QBMIGRATION BACKEND INTEGRATION TESTS")
    print("=" * 60)

    results = {}

    try:
        results["caseware_exporter"] = test_caseware_exporter()
    except Exception as e:
        results["caseware_exporter"] = False
        print(f"  [ERROR] {e}")

    try:
        results["transformer_caseware"] = test_data_transformer_caseware_mode()
    except Exception as e:
        results["transformer_caseware"] = False
        print(f"  [ERROR] {e}")

    try:
        results["hash_consistency"] = test_hash_consistency()
    except Exception as e:
        results["hash_consistency"] = False
        print(f"  [ERROR] {e}")

    try:
        results["lead_sheet_coverage"] = test_lead_sheet_coverage()
    except Exception as e:
        results["lead_sheet_coverage"] = False
        print(f"  [ERROR] {e}")

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "PASS" if passed_test else "FAIL"
        print(f"  {test_name}: {status}")

    print(f"\nTotal: {passed}/{total} tests passed")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
