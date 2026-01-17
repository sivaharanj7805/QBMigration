# QBDesktopReader Update: Forensic Hashing & Transaction Linking

**Date:** January 16, 2026  
**Version:** 4.4

---

## Summary

Implemented two critical forensic accounting features:

### 1. Per-Record SHA256 Integrity Hashing

Every transaction row now includes a `sha256IntegrityHash` field that allows auditors to verify data integrity at the individual record level. This supports "Forensic Verification" badges in Caseware and similar audit tools.

**Key Benefits:**
- Cryptographic proof of data integrity
- Deterministic hashing (same data = same hash on every run)
- Matches Python hashlib.sha256() hexdigest format for cross-system verification

**Covered Transaction Types:** Invoice, Bill, ReceivePayment, BillPaymentCheck, CreditMemo, SalesReceipt, Estimate, JournalEntry, Check, Deposit, PurchaseOrder, SalesOrder, Transfer, VendorCredit

### 2. Recursive Transaction Linker

Standard migration tools often break the links between Payments and Invoices on large files. The new `RecursiveTransactionLinker` uses AppliedTo metadata from the QuickBooks SDK to ensure that every payment remains "mathematically married" to its invoice(s).

**Key Benefits:**
- Prevents weeks of manual credit application by accountants
- Tracks partial payments across multiple invoices
- Detects orphan payments with no linked invoice
- Verifies link balance integrity

---

## New Files

| File | Description |
|------|-------------|
| `ForensicHashingService.cs` | SHA256 hashing utilities for 13+ transaction types |
| `RecursiveTransactionLinker.cs` | Payment-invoice link reconstruction engine |
| `tests/test_forensic_hashing.cs` | Unit tests for hash determinism and correctness |
| `tests/test_transaction_linking.cs` | Unit tests for link reconstruction scenarios |

## Modified Files

| File | Changes |
|------|---------|
| `Models.cs` | Added `sha256IntegrityHash` to 15 transaction classes; Enhanced `QBLinkedTxn` with 5 new fields |

---

## Configuration

The existing `enableForensicHashing` flag in `config.json` controls whether hashing is applied:

```json
{
  "advanced": {
    "enableForensicHashing": true
  }
}
```

---

## Usage Example

```csharp
// After extracting invoice data
invoice.Sha256IntegrityHash = ForensicHashingService.ComputeInvoiceHash(invoice);

// Process all transaction links
var linker = new RecursiveTransactionLinker(logger);
var result = linker.ProcessLinks(extractedData);

// Check results
Console.WriteLine($"Links processed: {result.TotalLinksProcessed}");
Console.WriteLine($"Orphan payments found: {result.OrphanPaymentsFound}");
```

---

## Remaining Work

To fully integrate these features into the extraction pipeline:

1. Modify `QBDataExtractor.cs` to call `ForensicHashingService` after parsing each transaction
2. Call `RecursiveTransactionLinker.ProcessLinks()` after all transactions are extracted
3. Include link summary in the output manifest

---

## Testing

Run the new unit tests to verify functionality:

```powershell
# From QBDesktopReader directory
csc tests/test_forensic_hashing.cs ForensicHashingService.cs Models.cs /reference:Newtonsoft.Json.dll
test_forensic_hashing.exe

csc tests/test_transaction_linking.cs RecursiveTransactionLinker.cs Models.cs /reference:Newtonsoft.Json.dll
test_transaction_linking.exe
```

---

## Version History

- **v4.4** - Added ForensicHashingService, RecursiveTransactionLinker, enhanced QBLinkedTxn model
- **v4.3** - Previous stable version
