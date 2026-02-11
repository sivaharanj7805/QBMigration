"""
Tests for Merkle Tree cryptographic properties (verifier.py).

Covers:
- CRIT-03 FIX: Domain separation (RFC 6962 §2.1)
- Second-preimage resistance
- Proof generation and verification
- Tree structural properties
- Edge cases: empty tree, single leaf, odd leaves, large trees
- Determinism
- build_merkle_tree_from_extraction helper
"""

import hashlib
import os
import sys

import pytest

# Ensure the QBMigrationService package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verifier import MerkleTreeBuilder, build_merkle_tree_from_extraction, verify_merkle_root


# ---------------------------------------------------------------------------
# DOMAIN SEPARATION (CRIT-03 FIX)
# ---------------------------------------------------------------------------

class TestDomainSeparation:
    """Verify RFC 6962 §2.1 domain-separated hashing."""

    def test_leaf_prefix_is_0x00(self):
        """Leaf hash uses 0x00 prefix."""
        assert MerkleTreeBuilder._LEAF_PREFIX == b"\x00"

    def test_internal_prefix_is_0x01(self):
        """Internal hash uses 0x01 prefix."""
        assert MerkleTreeBuilder._INTERNAL_PREFIX == b"\x01"

    def test_leaf_hash_includes_prefix(self):
        """Leaf hash = SHA-256(0x00 || data)."""
        data = "test_data"
        expected = hashlib.sha256(b"\x00" + data.encode("utf-8")).hexdigest()
        assert MerkleTreeBuilder._hash_leaf(data) == expected

    def test_internal_hash_includes_prefix(self):
        """Internal hash = SHA-256(0x01 || left || right)."""
        left = "abc123"
        right = "def456"
        expected = hashlib.sha256(
            b"\x01" + left.encode("utf-8") + right.encode("utf-8")
        ).hexdigest()
        assert MerkleTreeBuilder._hash_internal(left, right) == expected

    def test_leaf_and_internal_differ_for_same_input(self):
        """Domain separation ensures leaf(x) != internal(x, x)."""
        data = "same_input"
        leaf = MerkleTreeBuilder._hash_leaf(data)
        internal = MerkleTreeBuilder._hash_internal(data, data)
        assert leaf != internal

    def test_second_preimage_resistance(self):
        """
        An attacker cannot craft an internal node that collides with a leaf node.

        In a tree without domain separation, an attacker could present the hash of
        two leaves (H(left || right)) as a single leaf, because H is used the same
        way for both. With domain separation, H(0x00 || data) != H(0x01 || left || right)
        for any data, left, right — preventing this attack.
        """
        builder = MerkleTreeBuilder()
        builder.add_leaf("leaf1")
        builder.add_leaf("leaf2")
        root = builder.build_tree()

        # The root is H(0x01 || H(0x00 || "leaf1") || H(0x00 || "leaf2"))
        leaf1_hash = MerkleTreeBuilder._hash_leaf("leaf1")
        leaf2_hash = MerkleTreeBuilder._hash_leaf("leaf2")
        expected_root = MerkleTreeBuilder._hash_internal(leaf1_hash, leaf2_hash)
        assert root == expected_root

        # Now try to forge: treat the concatenation as a leaf
        forged_input = leaf1_hash + leaf2_hash
        forged_leaf = MerkleTreeBuilder._hash_leaf(forged_input)
        assert forged_leaf != root  # Attack fails


# ---------------------------------------------------------------------------
# TREE CONSTRUCTION
# ---------------------------------------------------------------------------

class TestTreeConstruction:
    """Tests for Merkle tree building."""

    def test_empty_tree(self):
        """Empty tree produces deterministic hash."""
        builder = MerkleTreeBuilder()
        root = builder.build_tree()
        assert root is not None
        assert len(root) == 64  # SHA-256 hex
        assert root == hashlib.sha256("EMPTY_TREE".encode("utf-8")).hexdigest()

    def test_single_leaf(self):
        """Single leaf tree: root = H(0x00 || leaf)."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("only_leaf")
        root = builder.build_tree()

        expected = MerkleTreeBuilder._hash_leaf("only_leaf")
        assert root == expected

    def test_two_leaves(self):
        """Two leaves: root = H(0x01 || H(0x00 || left) || H(0x00 || right))."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("L1")
        builder.add_leaf("L2")
        root = builder.build_tree()

        l1 = MerkleTreeBuilder._hash_leaf("L1")
        l2 = MerkleTreeBuilder._hash_leaf("L2")
        expected = MerkleTreeBuilder._hash_internal(l1, l2)
        assert root == expected

    def test_three_leaves_odd_promotion(self):
        """
        Three leaves: odd leaf is promoted without duplication.

        CRIT-03 FIX: Instead of duplicating the odd leaf (which creates
        ambiguous tree structures), the odd leaf is promoted directly.
        """
        builder = MerkleTreeBuilder()
        builder.add_leaf("A")
        builder.add_leaf("B")
        builder.add_leaf("C")
        root = builder.build_tree()

        # Level 0: [H(A), H(B), H(C)]
        # Level 1: [H_internal(H(A), H(B)), H(C)]  (H(C) promoted)
        # Level 2 (root): H_internal(H_internal(H(A), H(B)), H(C))
        ha = MerkleTreeBuilder._hash_leaf("A")
        hb = MerkleTreeBuilder._hash_leaf("B")
        hc = MerkleTreeBuilder._hash_leaf("C")
        hab = MerkleTreeBuilder._hash_internal(ha, hb)
        expected = MerkleTreeBuilder._hash_internal(hab, hc)
        assert root == expected

    def test_four_leaves_balanced(self):
        """Four leaves: produces a balanced tree."""
        builder = MerkleTreeBuilder()
        for leaf in ["W", "X", "Y", "Z"]:
            builder.add_leaf(leaf)
        root = builder.build_tree()

        hw = MerkleTreeBuilder._hash_leaf("W")
        hx = MerkleTreeBuilder._hash_leaf("X")
        hy = MerkleTreeBuilder._hash_leaf("Y")
        hz = MerkleTreeBuilder._hash_leaf("Z")
        hwx = MerkleTreeBuilder._hash_internal(hw, hx)
        hyz = MerkleTreeBuilder._hash_internal(hy, hz)
        expected = MerkleTreeBuilder._hash_internal(hwx, hyz)
        assert root == expected

    def test_large_tree(self):
        """Tree with 1000 leaves builds successfully."""
        builder = MerkleTreeBuilder()
        for i in range(1000):
            builder.add_leaf(f"record_{i}")
        root = builder.build_tree()

        assert root is not None
        assert len(root) == 64
        assert builder.get_leaf_count() == 1000
        assert builder.get_tree_depth() > 0

    def test_empty_hashes_ignored(self):
        """Empty/None leaf hashes are silently ignored."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("")
        builder.add_leaf("valid")
        builder.add_leaf("")
        assert builder.get_leaf_count() == 1  # Only "valid" counted

    def test_add_leaves_batch(self):
        """add_leaves() adds multiple leaves at once."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["h1", "h2", "h3"])
        assert builder.get_leaf_count() == 3

    def test_add_leaves_skips_empty(self):
        """add_leaves() skips empty strings."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["h1", "", "h3", ""])
        assert builder.get_leaf_count() == 2


# ---------------------------------------------------------------------------
# DETERMINISM
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Verify tree is deterministic."""

    def test_same_input_same_root(self):
        """Same leaves in same order → same root."""
        roots = []
        for _ in range(3):
            builder = MerkleTreeBuilder()
            for i in range(100):
                builder.add_leaf(f"hash_{i}")
            roots.append(builder.build_tree())

        assert roots[0] == roots[1] == roots[2]

    def test_different_order_different_root(self):
        """Different leaf order → different root (order matters)."""
        b1 = MerkleTreeBuilder()
        b1.add_leaf("A")
        b1.add_leaf("B")
        root1 = b1.build_tree()

        b2 = MerkleTreeBuilder()
        b2.add_leaf("B")
        b2.add_leaf("A")
        root2 = b2.build_tree()

        assert root1 != root2

    def test_different_data_different_root(self):
        """Any change in data produces different root."""
        b1 = MerkleTreeBuilder()
        b1.add_leaves(["h1", "h2", "h3"])
        root1 = b1.build_tree()

        b2 = MerkleTreeBuilder()
        b2.add_leaves(["h1", "h2", "h3_modified"])
        root2 = b2.build_tree()

        assert root1 != root2


# ---------------------------------------------------------------------------
# PROOF GENERATION & VERIFICATION
# ---------------------------------------------------------------------------

class TestProofVerification:
    """Tests for get_proof_path() and verify_proof()."""

    def test_verify_proof_two_leaves(self):
        """Proof verification succeeds for a 2-leaf tree."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("A")
        builder.add_leaf("B")
        root = builder.build_tree()

        # Verify leaf 0 ("A")
        proof = builder.get_proof_path(0)
        assert builder.verify_proof("A", proof, root) is True

        # Verify leaf 1 ("B")
        proof = builder.get_proof_path(1)
        assert builder.verify_proof("B", proof, root) is True

    def test_verify_proof_fails_for_wrong_data(self):
        """Proof verification fails when data is tampered."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("original_data")
        builder.add_leaf("other_data")
        root = builder.build_tree()

        proof = builder.get_proof_path(0)
        assert builder.verify_proof("tampered_data", proof, root) is False

    def test_verify_proof_large_tree(self):
        """Proof verification works for larger trees."""
        builder = MerkleTreeBuilder()
        leaves = [f"record_{i}" for i in range(128)]
        builder.add_leaves(leaves)
        root = builder.build_tree()

        # Verify every leaf
        for idx, leaf in enumerate(leaves):
            proof = builder.get_proof_path(idx)
            assert builder.verify_proof(leaf, proof, root) is True, \
                f"Proof failed for leaf {idx}"

    def test_proof_path_invalid_index(self):
        """Raises ValueError for out-of-range leaf index."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["A", "B", "C"])
        builder.build_tree()

        with pytest.raises(ValueError, match="out of range"):
            builder.get_proof_path(5)

        with pytest.raises(ValueError, match="out of range"):
            builder.get_proof_path(-1)

    def test_proof_path_odd_tree(self):
        """Proof works for trees with odd number of leaves."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["A", "B", "C", "D", "E"])
        root = builder.build_tree()

        for idx in range(5):
            proof = builder.get_proof_path(idx)
            assert builder.verify_proof(
                ["A", "B", "C", "D", "E"][idx], proof, root
            ) is True


# ---------------------------------------------------------------------------
# REPORT GENERATION
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """Tests for generate_report()."""

    def test_report_structure(self):
        """Report contains all required fields."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["h1", "h2", "h3", "h4"])
        report = builder.generate_report("session-001")

        assert report["session_id"] == "session-001"
        assert "generated_at" in report
        assert "merkle_root" in report
        assert report["total_leaf_nodes"] == 4
        assert report["hash_algorithm"] == "SHA-256"
        assert "tree_structure" in report
        assert "verification_instructions" in report

    def test_report_auto_builds_tree(self):
        """Report generation auto-builds tree if not already built."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["h1", "h2"])
        # Don't call build_tree() explicitly
        report = builder.generate_report("session-002")
        assert report["merkle_root"] is not None

    def test_report_tree_depth(self):
        """Report includes correct tree depth."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["h1", "h2", "h3", "h4"])
        report = builder.generate_report("session-003")
        # 4 leaves → depth 3 (leaves, intermediate, root)
        assert report["tree_depth"] == 3


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

class TestBuildMerkleTreeFromExtraction:
    """Tests for build_merkle_tree_from_extraction helper."""

    def test_builds_from_extraction_data(self):
        """Builds tree from typical extraction data structure."""
        extracted_data = {
            "invoices": [
                {"IntegrityHash": "hash_inv_1"},
                {"IntegrityHash": "hash_inv_2"},
            ],
            "customers": [
                {"integrity_hash": "hash_cust_1"},
            ],
            "vendors": [
                {"IntegrityHash": "hash_vend_1"},
            ],
        }

        report = build_merkle_tree_from_extraction(extracted_data, "session-test")
        assert report["total_leaf_nodes"] == 4
        assert report["merkle_root"] is not None

    def test_handles_empty_extraction(self):
        """Empty extraction produces valid report."""
        report = build_merkle_tree_from_extraction({}, "session-empty")
        assert report["total_leaf_nodes"] == 0

    def test_skips_records_without_hash(self):
        """Records without IntegrityHash/integrity_hash are skipped."""
        extracted_data = {
            "invoices": [
                {"IntegrityHash": "valid_hash"},
                {"Name": "no hash here"},
            ],
        }
        report = build_merkle_tree_from_extraction(extracted_data, "session-skip")
        assert report["total_leaf_nodes"] == 1


class TestVerifyMerkleRoot:
    """Tests for verify_merkle_root helper."""

    def test_verify_matching_root(self):
        """Verification passes when roots match."""
        extracted_data = {
            "invoices": [{"IntegrityHash": "h1"}, {"IntegrityHash": "h2"}],
        }
        report = build_merkle_tree_from_extraction(extracted_data, "test")
        expected_root = report["merkle_root"]

        result = verify_merkle_root(extracted_data, expected_root, "test")
        assert result["is_valid"] is True
        assert result["verification_status"] == "VERIFIED"

    def test_verify_mismatched_root(self):
        """Verification fails when roots don't match."""
        extracted_data = {
            "invoices": [{"IntegrityHash": "h1"}, {"IntegrityHash": "h2"}],
        }

        result = verify_merkle_root(extracted_data, "wrong_root_hash", "test")
        assert result["is_valid"] is False
        assert result["verification_status"] == "MISMATCH_DETECTED"
        assert "WARNING" in result["forensic_note"]


# ---------------------------------------------------------------------------
# GET MERKLE ROOT LAZY BUILD
# ---------------------------------------------------------------------------

class TestGetMerkleRoot:
    """Tests for get_merkle_root auto-build."""

    def test_auto_builds_on_first_call(self):
        """get_merkle_root builds tree if not already built."""
        builder = MerkleTreeBuilder()
        builder.add_leaf("lazy")
        root = builder.get_merkle_root()
        assert root == MerkleTreeBuilder._hash_leaf("lazy")

    def test_returns_same_root_on_subsequent_calls(self):
        """Subsequent calls return the same root without rebuilding."""
        builder = MerkleTreeBuilder()
        builder.add_leaves(["a", "b", "c"])
        root1 = builder.get_merkle_root()
        root2 = builder.get_merkle_root()
        assert root1 == root2
