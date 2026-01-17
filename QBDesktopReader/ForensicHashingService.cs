using System;
using System.Collections.Generic;
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
            
            // Canonical field ordering for deterministic hashing
            var hashInput = new StringBuilder();
            hashInput.Append($"TxnID:{invoice.TxnID ?? ""}|");
            hashInput.Append($"RefNumber:{invoice.RefNumber ?? ""}|");
            hashInput.Append($"TxnDate:{invoice.TxnDate?.ToString("yyyy-MM-dd") ?? ""}|");
            hashInput.Append($"CustomerRefListID:{invoice.CustomerRefListID ?? ""}|");
            hashInput.Append($"Subtotal:{invoice.Subtotal?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"SalesTaxTotal:{invoice.SalesTaxTotal?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"AppliedAmount:{invoice.AppliedAmount?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"BalanceRemaining:{invoice.BalanceRemaining?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"IsPaid:{invoice.IsPaid ?? false}|");
            hashInput.Append($"EditSequence:{invoice.EditSequence ?? ""}");
            
            // Include line items in hash
            if (invoice.Lines != null && invoice.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in invoice.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
            hashInput.Append($"AmountDue:{bill.AmountDue?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"IsPaid:{bill.IsPaid ?? false}|");
            hashInput.Append($"EditSequence:{bill.EditSequence ?? ""}");
            
            // Include line items
            if (bill.Lines != null && bill.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in bill.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
            hashInput.Append($"TotalAmount:{payment.TotalAmount?.ToString("F2") ?? "0.00"}|");
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
            hashInput.Append($"Amount:{payment.Amount?.ToString("F2") ?? "0.00"}|");
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
            hashInput.Append($"TotalAmount:{creditMemo.TotalAmount?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"CreditRemaining:{creditMemo.CreditRemaining?.ToString("F2") ?? "0.00"}");
            
            if (creditMemo.Lines != null && creditMemo.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in creditMemo.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.JournalLineType ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
            hashInput.Append($"Amount:{check.Amount?.ToString("F2") ?? "0.00"}");
            
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
            hashInput.Append($"TotalAmount:{deposit.TotalAmount?.ToString("F2") ?? "0.00"}");
            
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
            hashInput.Append($"TotalAmount:{salesReceipt.TotalAmount?.ToString("F2") ?? "0.00"}");
            
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
            hashInput.Append($"TotalAmount:{po.TotalAmount?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"IsManuallyClosed:{po.IsManuallyClosed ?? false}|");
            hashInput.Append($"IsFullyReceived:{po.IsFullyReceived ?? false}");
            
            if (po.Lines != null && po.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in po.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
            hashInput.Append($"TotalAmount:{so.TotalAmount?.ToString("F2") ?? "0.00"}|");
            hashInput.Append($"IsManuallyClosed:{so.IsManuallyClosed ?? false}|");
            hashInput.Append($"IsFullyInvoiced:{so.IsFullyInvoiced ?? false}");
            
            if (so.Lines != null && so.Lines.Count > 0)
            {
                hashInput.Append("|Lines:");
                foreach (var line in so.Lines.OrderBy(l => l.TxnLineID))
                {
                    hashInput.Append($"[{line.TxnLineID ?? ""}:{line.Amount?.ToString("F2") ?? "0.00"}]");
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
            hashInput.Append($"TotalAmount:{estimate.TotalAmount?.ToString("F2") ?? "0.00"}|");
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
            hashInput.Append($"CreditAmount:{vendorCredit.CreditAmount?.ToString("F2") ?? "0.00"}|");
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
            hashInput.Append($"Amount:{transfer.Amount?.ToString("F2") ?? "0.00"}");
            
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
    }
}
