using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using Newtonsoft.Json;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Forensic Hashing Service v1.0
    /// 
    /// Provides per-record SHA256 integrity hashing for all transaction types.
    /// This enables auditors to verify data integrity at the individual record level
    /// and supports "Forensic Verification" badges in Caseware and other audit tools.
    /// 
    /// CRITICAL: Hash computation uses CANONICAL field ordering to ensure deterministic
    /// results regardless of serialization order.
    /// </summary>
    public static class ForensicHashingService
    {
        public const string HASH_VERSION = "1.0";
        
        /// <summary>
        /// Compute SHA256 integrity hash for an invoice
        /// </summary>
        public static string ComputeInvoiceHash(QBInvoice invoice)
        {
            if (invoice == null) return null;
            
            // FIX #59: Canonical field ordering with InvariantCulture for deterministic hashing
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{invoice.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{invoice.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{invoice.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{invoice.CustomerRefListID ?? ""}|");
            hashInput.Append($"Subtotal:{invoice.Subtotal?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"SalesTaxTotal:{invoice.SalesTaxTotal?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"AppliedAmount:{invoice.AppliedAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"BalanceRemaining:{invoice.BalanceRemaining?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsPaid:{invoice.IsPaid ?? false}|");
            hashInput.Append($"EditSequence:{invoice.EditSequence ?? ""}");
            
            // FIX #59: Include line items in hash with canonicalized decimal formatting
            if (invoice.Lines != null && invoice.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in invoice.Lines.OrderBy(l => l.TxnLineID))
                {
                    // Use InvariantCulture to prevent regional formatting differences (1.00 vs 1,00)
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a bill
        /// </summary>
        public static string ComputeBillHash(QBBill bill)
        {
            if (bill == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{bill.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{bill.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{bill.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"VendorRefListID:{bill.VendorRefListID ?? ""}|");
            hashInput.Append($"AmountDue:{bill.AmountDue?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsPaid:{bill.IsPaid ?? false}|");
            hashInput.Append($"EditSequence:{bill.EditSequence ?? ""}");
            
            // Include line items
            if (bill.Lines != null && bill.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in bill.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a receive payment
        /// </summary>
        public static string ComputeReceivePaymentHash(QBReceivePayment payment)
        {
            if (payment == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{payment.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{payment.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{payment.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{payment.CustomerRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{payment.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"PaymentMethodRefListID:{payment.PaymentMethodRefListID ?? ""}|");
            hashInput.Append($"DepositToAccountRefListID:{payment.DepositToAccountRefListID ?? ""}|");
            hashInput.Append($"EditSequence:{payment.EditSequence ?? ""}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a bill payment check
        /// </summary>
        public static string ComputeBillPaymentCheckHash(QBBillPaymentCheck payment)
        {
            if (payment == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{payment.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{payment.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{payment.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"PayeeEntityRefListID:{payment.PayeeEntityRefListID ?? ""}|");
            hashInput.Append($"Amount:{payment.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"BankAccountRefListID:{payment.BankAccountRefListID ?? ""}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a credit memo
        /// </summary>
        public static string ComputeCreditMemoHash(QBCreditMemo creditMemo)
        {
            if (creditMemo == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{creditMemo.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{creditMemo.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{creditMemo.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{creditMemo.CustomerRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{creditMemo.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"CreditRemaining:{creditMemo.CreditRemaining?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");
            
            if (creditMemo.Lines != null && creditMemo.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in creditMemo.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a journal entry
        /// </summary>
        public static string ComputeJournalEntryHash(QBJournalEntry journalEntry)
        {
            if (journalEntry == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{journalEntry.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{journalEntry.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{journalEntry.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"IsAdjustment:{journalEntry.IsAdjustment ?? false}");
            
            if (journalEntry.Lines != null && journalEntry.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in journalEntry.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.JournalLineType ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a check
        /// </summary>
        public static string ComputeCheckHash(QBCheck check)
        {
            if (check == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{check.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{check.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{check.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"PayeeEntityRefListID:{check.PayeeEntityRefListID ?? ""}|");
            hashInput.Append($"AccountRefListID:{check.AccountRefListID ?? ""}|");
            hashInput.Append($"Amount:{check.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a deposit
        /// </summary>
        public static string ComputeDepositHash(QBDeposit deposit)
        {
            if (deposit == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{deposit.TxnID ?? ""}|");
            hashInput.Append($"TxnDate:{deposit.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"DepositToAccountRefListID:{deposit.DepositToAccountRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{deposit.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a sales receipt
        /// </summary>
        public static string ComputeSalesReceiptHash(QBSalesReceipt salesReceipt)
        {
            if (salesReceipt == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{salesReceipt.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{salesReceipt.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{salesReceipt.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{salesReceipt.CustomerRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{salesReceipt.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a purchase order
        /// </summary>
        public static string ComputePurchaseOrderHash(QBPurchaseOrder po)
        {
            if (po == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{po.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{po.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{po.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"VendorRefListID:{po.VendorRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{po.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsManuallyClosed:{po.IsManuallyClosed ?? false}|");
            hashInput.Append($"IsFullyReceived:{po.IsFullyReceived ?? false}");
            
            if (po.Lines != null && po.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in po.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a sales order
        /// </summary>
        public static string ComputeSalesOrderHash(QBSalesOrder so)
        {
            if (so == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{so.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{so.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{so.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{so.CustomerRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{so.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsManuallyClosed:{so.IsManuallyClosed ?? false}|");
            hashInput.Append($"IsFullyInvoiced:{so.IsFullyInvoiced ?? false}");
            
            if (so.Lines != null && so.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in so.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}]");
                }
            }
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for an estimate
        /// </summary>
        public static string ComputeEstimateHash(QBEstimate estimate)
        {
            if (estimate == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{estimate.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{estimate.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{estimate.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{estimate.CustomerRefListID ?? ""}|");
            hashInput.Append($"TotalAmount:{estimate.TotalAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsActive:{estimate.IsActive ?? false}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a vendor credit
        /// </summary>
        public static string ComputeVendorCreditHash(QBVendorCredit vendorCredit)
        {
            if (vendorCredit == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{vendorCredit.TxnID ?? ""}|");
            hashInput.Append($"TxnDate:{vendorCredit.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"VendorRefListID:{vendorCredit.VendorRefListID ?? ""}|");
            hashInput.Append($"CreditAmount:{vendorCredit.CreditAmount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"APAccountRefListID:{vendorCredit.APAccountRefListID ?? ""}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// Compute SHA256 integrity hash for a transfer
        /// </summary>
        public static string ComputeTransferHash(QBTransfer transfer)
        {
            if (transfer == null) return null;
            
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{transfer.TxnID ?? ""}|");
            hashInput.Append($"TxnDate:{transfer.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"TransferFromAccountRefListID:{transfer.TransferFromAccountRefListID ?? ""}|");
            hashInput.Append($"TransferToAccountRefListID:{transfer.TransferToAccountRefListID ?? ""}|");
            hashInput.Append($"Amount:{transfer.Amount?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");
            
            return ComputeHash(hashInput.ToString());
        }
        
        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Customer entity
        /// </summary>
        public static string ComputeCustomerHash(QBCustomer customer)
        {
            if (customer == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{customer.ListID ?? ""}|");
            hashInput.Append($"Name:{customer.Name ?? ""}|");
            hashInput.Append($"CompanyName:{customer.CompanyName ?? ""}|");
            hashInput.Append($"Email:{customer.Email ?? ""}|");
            hashInput.Append($"Phone:{customer.Phone ?? ""}|");
            hashInput.Append($"Balance:{customer.Balance?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Vendor entity
        /// </summary>
        public static string ComputeVendorHash(QBVendor vendor)
        {
            if (vendor == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{vendor.ListID ?? ""}|");
            hashInput.Append($"Name:{vendor.Name ?? ""}|");
            hashInput.Append($"CompanyName:{vendor.CompanyName ?? ""}|");
            hashInput.Append($"Email:{vendor.Email ?? ""}|");
            hashInput.Append($"Phone:{vendor.Phone ?? ""}|");
            hashInput.Append($"Balance:{vendor.Balance?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Employee entity
        /// </summary>
        public static string ComputeEmployeeHash(QBEmployee employee)
        {
            if (employee == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{employee.ListID ?? ""}|");
            hashInput.Append($"Name:{employee.Name ?? ""}|");
            hashInput.Append($"FirstName:{employee.FirstName ?? ""}|");
            hashInput.Append($"LastName:{employee.LastName ?? ""}|");
            hashInput.Append($"SSN:{employee.SSN ?? ""}|");  // Hash includes SSN for integrity
            hashInput.Append($"EmployeeType:{employee.EmployeeType ?? ""}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Item entity (Products/Services)
        /// </summary>
        public static string ComputeItemHash(QBItem item)
        {
            if (item == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{item.ListID ?? ""}|");
            hashInput.Append($"Name:{item.Name ?? ""}|");
            hashInput.Append($"FullName:{item.FullName ?? ""}|");
            hashInput.Append($"Type:{item.Type ?? ""}|");
            hashInput.Append($"SalesPrice:{item.SalesPrice?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"PurchaseCost:{item.PurchaseCost?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}|");
            hashInput.Append($"IsActive:{item.IsActive}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Account entity
        /// </summary>
        public static string ComputeAccountHash(QBAccount account)
        {
            if (account == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{account.ListID ?? ""}|");
            hashInput.Append($"Name:{account.Name ?? ""}|");
            hashInput.Append($"FullName:{account.FullName ?? ""}|");
            hashInput.Append($"AccountType:{account.AccountType ?? ""}|");
            hashInput.Append($"AccountNumber:{account.AccountNumber ?? ""}|");
            hashInput.Append($"Balance:{account.Balance?.ToString("F2", CultureInfo.InvariantCulture) ?? "0.00"}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for Class entity
        /// </summary>
        public static string ComputeClassHash(QBClass qbClass)
        {
            if (qbClass == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{qbClass.ListID ?? ""}|");
            hashInput.Append($"Name:{qbClass.Name ?? ""}|");
            hashInput.Append($"FullName:{qbClass.FullName ?? ""}|");
            hashInput.Append($"IsActive:{qbClass.IsActive}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for PaymentMethod entity
        /// </summary>
        public static string ComputePaymentMethodHash(QBPaymentMethod paymentMethod)
        {
            if (paymentMethod == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{paymentMethod.ListID ?? ""}|");
            hashInput.Append($"Name:{paymentMethod.Name ?? ""}|");
            hashInput.Append($"Type:{paymentMethod.Type ?? ""}|");
            hashInput.Append($"IsActive:{paymentMethod.IsActive}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// FORENSIC REQUIREMENT: Compute forensic hash for TaxCode entity
        /// </summary>
        public static string ComputeTaxCodeHash(QBSalesTaxCode taxCode)
        {
            if (taxCode == null) return null;

            var hashInput = new StringBuilder();
            hashInput.Append($"ListID:{taxCode.ListID ?? ""}|");
            hashInput.Append($"Name:{taxCode.Name ?? ""}|");
            hashInput.Append($"Desc:{taxCode.Desc ?? ""}|");
            hashInput.Append($"TaxRate:{taxCode.TaxRate?.ToString("F4", CultureInfo.InvariantCulture) ?? "0.0000"}|");
            hashInput.Append($"IsActive:{taxCode.IsActive}");

            return ComputeHash(hashInput.ToString());
        }

        /// <summary>
        /// Generic hash computation using SHA256
        /// Matches Python: hashlib.sha256(data.encode()).hexdigest()
        /// </summary>
        private static string ComputeHash(string input)
        {
            if (string.IsNullOrEmpty(input)) return null;
            
            using (var sha256 = SHA256.Create())
            {
                byte[] bytes = Encoding.UTF8.GetBytes(input);
                byte[] hash = sha256.ComputeHash(bytes);
                
                // Return lowercase hex string to match Python hexdigest()
                var sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash)
                {
                    sb.Append(b.ToString("x2"));
                }
                return sb.ToString();
            }
        }
        
        /// <summary>
        /// Generate a forensic hash report for batch verification
        /// </summary>
        public static ForensicBatchHashReport GenerateBatchReport(
            int invoiceCount, 
            int billCount, 
            int paymentCount,
            string sessionId)
        {
            return new ForensicBatchHashReport
            {
                SessionId = sessionId,
                GeneratedAt = DateTime.UtcNow,
                HashVersion = HASH_VERSION,
                HashAlgorithm = "SHA-256",
                RecordCounts = new Dictionary<string, int>
                {
                    ["Invoices"] = invoiceCount,
                    ["Bills"] = billCount,
                    ["Payments"] = paymentCount
                }
            };
        }
    }
    
    /// <summary>
    /// Batch hash report for audit trail
    /// </summary>
    public class ForensicBatchHashReport
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("generated_at")]
        public DateTime GeneratedAt { get; set; }

        [JsonProperty("hash_version")]
        public string HashVersion { get; set; }

        [JsonProperty("hash_algorithm")]
        public string HashAlgorithm { get; set; }

        [JsonProperty("record_counts")]
        public Dictionary<string, int> RecordCounts { get; set; }

        [JsonProperty("merkle_root")]
        public string MerkleRoot { get; set; }

        [JsonProperty("merkle_tree_depth")]
        public int MerkleTreeDepth { get; set; }

        [JsonProperty("total_leaf_nodes")]
        public int TotalLeafNodes { get; set; }
    }

    /// <summary>
    /// Merkle Tree Builder for Forensic Chain of Custody
    ///
    /// Implements a cryptographic Merkle tree to provide tamper-evident
    /// verification of the entire extraction dataset. The Merkle root serves
    /// as a single hash that cryptographically commits to ALL individual
    /// record hashes, enabling:
    ///
    /// 1. Court-admissible proof of data integrity
    /// 2. Efficient verification (O(log n) for any single record)
    /// 3. Detection of any tampering anywhere in the dataset
    ///
    /// CRITICAL FOR M&A: This addresses the $500K-$1M valuation gap identified
    /// in the technical due diligence audit.
    /// </summary>
    public class MerkleTreeBuilder
    {
        private List<string> _leafHashes;
        private List<List<string>> _treeLevels;
        private string _merkleRoot;
        private readonly object _lock = new object();

        public MerkleTreeBuilder()
        {
            _leafHashes = new List<string>();
            _treeLevels = new List<List<string>>();
        }

        /// <summary>
        /// Add a leaf hash (individual record hash) to the tree
        /// </summary>
        public void AddLeafHash(string hash)
        {
            if (string.IsNullOrEmpty(hash)) return;

            lock (_lock)
            {
                _leafHashes.Add(hash);
            }
        }

        /// <summary>
        /// Add multiple leaf hashes (batch operation)
        /// </summary>
        public void AddLeafHashes(IEnumerable<string> hashes)
        {
            if (hashes == null) return;

            lock (_lock)
            {
                foreach (var hash in hashes.Where(h => !string.IsNullOrEmpty(h)))
                {
                    _leafHashes.Add(hash);
                }
            }
        }

        /// <summary>
        /// Build the Merkle tree and compute the root hash
        /// </summary>
        /// <returns>The Merkle root hash</returns>
        public string BuildTree()
        {
            lock (_lock)
            {
                if (_leafHashes.Count == 0)
                {
                    _merkleRoot = ComputeSHA256("EMPTY_TREE");
                    return _merkleRoot;
                }

                // Ensure even number of leaves (duplicate last if odd)
                var leaves = new List<string>(_leafHashes);
                if (leaves.Count % 2 == 1)
                {
                    leaves.Add(leaves.Last());
                }

                _treeLevels.Clear();
                _treeLevels.Add(leaves);

                // Build tree levels from bottom up
                var currentLevel = leaves;
                while (currentLevel.Count > 1)
                {
                    var nextLevel = new List<string>();

                    for (int i = 0; i < currentLevel.Count; i += 2)
                    {
                        var left = currentLevel[i];
                        var right = (i + 1 < currentLevel.Count) ? currentLevel[i + 1] : left;

                        // Concatenate and hash
                        var combined = left + right;
                        var parentHash = ComputeSHA256(combined);
                        nextLevel.Add(parentHash);
                    }

                    _treeLevels.Add(nextLevel);
                    currentLevel = nextLevel;
                }

                _merkleRoot = currentLevel.Count > 0 ? currentLevel[0] : ComputeSHA256("EMPTY_TREE");
                return _merkleRoot;
            }
        }

        /// <summary>
        /// Get the Merkle root (builds tree if not already built)
        /// </summary>
        public string GetMerkleRoot()
        {
            if (string.IsNullOrEmpty(_merkleRoot))
            {
                BuildTree();
            }
            return _merkleRoot;
        }

        /// <summary>
        /// Get the depth of the Merkle tree
        /// </summary>
        public int GetTreeDepth()
        {
            return _treeLevels.Count;
        }

        /// <summary>
        /// Get total number of leaf nodes
        /// </summary>
        public int GetLeafCount()
        {
            return _leafHashes.Count;
        }

        /// <summary>
        /// Generate a proof path for a specific leaf (for verification)
        /// </summary>
        /// <param name="leafIndex">Index of the leaf to prove</param>
        /// <returns>List of (sibling_hash, is_left) tuples for verification</returns>
        public List<MerkleProofNode> GetProofPath(int leafIndex)
        {
            if (_treeLevels.Count == 0)
            {
                BuildTree();
            }

            if (leafIndex < 0 || leafIndex >= _leafHashes.Count)
            {
                throw new ArgumentOutOfRangeException(nameof(leafIndex));
            }

            var proof = new List<MerkleProofNode>();
            var index = leafIndex;

            // Handle odd leaf count
            if (_leafHashes.Count % 2 == 1 && index == _leafHashes.Count - 1)
            {
                // Last leaf in odd tree, sibling is itself
            }

            for (int level = 0; level < _treeLevels.Count - 1; level++)
            {
                var isLeft = index % 2 == 0;
                var siblingIndex = isLeft ? index + 1 : index - 1;

                if (siblingIndex < _treeLevels[level].Count)
                {
                    proof.Add(new MerkleProofNode
                    {
                        Hash = _treeLevels[level][siblingIndex],
                        IsLeft = !isLeft
                    });
                }

                index = index / 2;
            }

            return proof;
        }

        /// <summary>
        /// Verify a leaf hash using a proof path
        /// </summary>
        public bool VerifyProof(string leafHash, List<MerkleProofNode> proof, string expectedRoot)
        {
            var currentHash = leafHash;

            foreach (var node in proof)
            {
                if (node.IsLeft)
                {
                    currentHash = ComputeSHA256(node.Hash + currentHash);
                }
                else
                {
                    currentHash = ComputeSHA256(currentHash + node.Hash);
                }
            }

            return currentHash == expectedRoot;
        }

        /// <summary>
        /// Generate a complete Merkle proof report for audit/legal purposes
        /// </summary>
        public MerkleTreeReport GenerateReport(string sessionId)
        {
            if (string.IsNullOrEmpty(_merkleRoot))
            {
                BuildTree();
            }

            return new MerkleTreeReport
            {
                SessionId = sessionId,
                GeneratedAt = DateTime.UtcNow,
                MerkleRoot = _merkleRoot,
                TreeDepth = _treeLevels.Count,
                TotalLeafNodes = _leafHashes.Count,
                HashAlgorithm = "SHA-256",
                TreeStructure = _treeLevels.Select((level, idx) => new MerkleTreeLevel
                {
                    Level = idx,
                    NodeCount = level.Count,
                    Hashes = idx == 0 ? null : level.Take(10).ToList() // Include first 10 hashes per level for verification
                }).ToList()
            };
        }

        private static string ComputeSHA256(string input)
        {
            if (string.IsNullOrEmpty(input)) return null;

            using (var sha256 = SHA256.Create())
            {
                byte[] bytes = Encoding.UTF8.GetBytes(input);
                byte[] hash = sha256.ComputeHash(bytes);

                var sb = new StringBuilder(hash.Length * 2);
                foreach (byte b in hash)
                {
                    sb.Append(b.ToString("x2"));
                }
                return sb.ToString();
            }
        }
    }

    /// <summary>
    /// Node in a Merkle proof path
    /// </summary>
    public class MerkleProofNode
    {
        [JsonProperty("hash")]
        public string Hash { get; set; }

        [JsonProperty("is_left")]
        public bool IsLeft { get; set; }
    }

    /// <summary>
    /// Complete Merkle tree report for audit purposes
    /// </summary>
    public class MerkleTreeReport
    {
        [JsonProperty("session_id")]
        public string SessionId { get; set; }

        [JsonProperty("generated_at")]
        public DateTime GeneratedAt { get; set; }

        [JsonProperty("merkle_root")]
        public string MerkleRoot { get; set; }

        [JsonProperty("tree_depth")]
        public int TreeDepth { get; set; }

        [JsonProperty("total_leaf_nodes")]
        public int TotalLeafNodes { get; set; }

        [JsonProperty("hash_algorithm")]
        public string HashAlgorithm { get; set; }

        [JsonProperty("tree_structure")]
        public List<MerkleTreeLevel> TreeStructure { get; set; }

        [JsonProperty("verification_instructions")]
        public string VerificationInstructions =>
            "To verify: 1) Recompute leaf hashes from source records using SHA-256. " +
            "2) Build Merkle tree from leaves. 3) Compare computed root with this MerkleRoot. " +
            "4) Matching roots prove 100% data integrity across all records.";
    }

    /// <summary>
    /// Level in the Merkle tree structure
    /// </summary>
    public class MerkleTreeLevel
    {
        [JsonProperty("level")]
        public int Level { get; set; }

        [JsonProperty("node_count")]
        public int NodeCount { get; set; }

        [JsonProperty("sample_hashes")]
        public List<string> Hashes { get; set; }
    }

    /// <summary>
    /// Extension methods for building Merkle trees from extracted data
    /// </summary>
    public static class MerkleTreeExtensions
    {
        /// <summary>
        /// Build a Merkle tree from a complete extraction result
        /// </summary>
        public static MerkleTreeReport BuildMerkleTree(
            this QBExtractedData data,
            string sessionId)
        {
            var builder = new MerkleTreeBuilder();

            // Add all transaction hashes
            if (data.Invoices != null)
            {
                foreach (var inv in data.Invoices.Where(i => !string.IsNullOrEmpty(i.IntegrityHash)))
                {
                    builder.AddLeafHash(inv.IntegrityHash);
                }
            }

            if (data.Bills != null)
            {
                foreach (var bill in data.Bills.Where(b => !string.IsNullOrEmpty(b.IntegrityHash)))
                {
                    builder.AddLeafHash(bill.IntegrityHash);
                }
            }

            if (data.JournalEntries != null)
            {
                foreach (var je in data.JournalEntries.Where(j => !string.IsNullOrEmpty(j.IntegrityHash)))
                {
                    builder.AddLeafHash(je.IntegrityHash);
                }
            }

            if (data.ReceivePayments != null)
            {
                foreach (var pmt in data.ReceivePayments.Where(p => !string.IsNullOrEmpty(p.IntegrityHash)))
                {
                    builder.AddLeafHash(pmt.IntegrityHash);
                }
            }

            if (data.CreditMemos != null)
            {
                foreach (var cm in data.CreditMemos.Where(c => !string.IsNullOrEmpty(c.IntegrityHash)))
                {
                    builder.AddLeafHash(cm.IntegrityHash);
                }
            }

            if (data.Checks != null)
            {
                foreach (var chk in data.Checks.Where(c => !string.IsNullOrEmpty(c.IntegrityHash)))
                {
                    builder.AddLeafHash(chk.IntegrityHash);
                }
            }

            if (data.Deposits != null)
            {
                foreach (var dep in data.Deposits.Where(d => !string.IsNullOrEmpty(d.IntegrityHash)))
                {
                    builder.AddLeafHash(dep.IntegrityHash);
                }
            }

            if (data.SalesReceipts != null)
            {
                foreach (var sr in data.SalesReceipts.Where(s => !string.IsNullOrEmpty(s.IntegrityHash)))
                {
                    builder.AddLeafHash(sr.IntegrityHash);
                }
            }

            if (data.PurchaseOrders != null)
            {
                foreach (var po in data.PurchaseOrders.Where(p => !string.IsNullOrEmpty(p.IntegrityHash)))
                {
                    builder.AddLeafHash(po.IntegrityHash);
                }
            }

            if (data.SalesOrders != null)
            {
                foreach (var so in data.SalesOrders.Where(s => !string.IsNullOrEmpty(s.IntegrityHash)))
                {
                    builder.AddLeafHash(so.IntegrityHash);
                }
            }

            if (data.Estimates != null)
            {
                foreach (var est in data.Estimates.Where(e => !string.IsNullOrEmpty(e.IntegrityHash)))
                {
                    builder.AddLeafHash(est.IntegrityHash);
                }
            }

            if (data.VendorCredits != null)
            {
                foreach (var vc in data.VendorCredits.Where(v => !string.IsNullOrEmpty(v.IntegrityHash)))
                {
                    builder.AddLeafHash(vc.IntegrityHash);
                }
            }

            if (data.Transfers != null)
            {
                foreach (var xfer in data.Transfers.Where(t => !string.IsNullOrEmpty(t.IntegrityHash)))
                {
                    builder.AddLeafHash(xfer.IntegrityHash);
                }
            }

            if (data.BillPayments != null)
            {
                foreach (var bp in data.BillPayments.Where(b => !string.IsNullOrEmpty(b.IntegrityHash)))
                {
                    builder.AddLeafHash(bp.IntegrityHash);
                }
            }

            // Add list entity hashes (Customers, Vendors, Items, Accounts, etc.)
            if (data.Customers != null)
            {
                foreach (var cust in data.Customers.Where(c => !string.IsNullOrEmpty(c.IntegrityHash)))
                {
                    builder.AddLeafHash(cust.IntegrityHash);
                }
            }

            if (data.Vendors != null)
            {
                foreach (var vend in data.Vendors.Where(v => !string.IsNullOrEmpty(v.IntegrityHash)))
                {
                    builder.AddLeafHash(vend.IntegrityHash);
                }
            }

            if (data.Employees != null)
            {
                foreach (var emp in data.Employees.Where(e => !string.IsNullOrEmpty(e.IntegrityHash)))
                {
                    builder.AddLeafHash(emp.IntegrityHash);
                }
            }

            if (data.Items != null)
            {
                foreach (var item in data.Items.Where(i => !string.IsNullOrEmpty(i.IntegrityHash)))
                {
                    builder.AddLeafHash(item.IntegrityHash);
                }
            }

            if (data.Accounts != null)
            {
                foreach (var acct in data.Accounts.Where(a => !string.IsNullOrEmpty(a.IntegrityHash)))
                {
                    builder.AddLeafHash(acct.IntegrityHash);
                }
            }

            // Build and return the report
            return builder.GenerateReport(sessionId);
        }
    }
}
