using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Mail;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Enterprise-grade Data Sanitizer v4.2
    /// 
    /// FIXES FROM REVIEW:
    /// - Removed XML escaping from JSON pipeline (mode-based)
    /// - Fixed missing SMART_REPLACEMENTS (removed dependency)
    /// - Stop leaking raw values in reports (hash + length by default)
    /// - Per-field limits from FieldLimits.cs
    /// - Preserve original in EmailOriginal with reason
    /// - Phone normalization with E.164 best-effort and extension
    /// - Address sanitization with whitespace + length
    /// - Comprehensive entity/field coverage
    /// - Severity enum instead of strings
    /// - No Console.WriteLine (uses logger)
    /// - Optimized control-char removal with HashSet
    /// </summary>
    public class DataSanitizer
    {
        // HashSet for O(1) control character lookup
        private static readonly HashSet<char> ControlChars = new HashSet<char>
        {
            '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07',
            '\x08', '\x0B', '\x0C', '\x0E', '\x0F', '\x10', '\x11', '\x12',
            '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1A',
            '\x1B', '\x1C', '\x1D', '\x1E', '\x1F'
        };

        private readonly SanitizationMode _mode;
        private readonly SanitizationConfig _config;
        private readonly IRedactingLogger _logger;

        public SanitizationReport Report { get; private set; }

        public DataSanitizer(
            SanitizationMode mode = SanitizationMode.Json,
            SanitizationConfig config = null,
            IRedactingLogger logger = null)
        {
            _mode = mode;
            _config = config ?? SanitizationConfig.Default;
            _logger = logger;
            Report = new SanitizationReport(_config.IncludeRawValuesInReport);
        }

        /// <summary>
        /// Sanitize a name field using FieldLimits for proper truncation
        /// </summary>
        public SanitizeResult SanitizeName(string value, string entityType, string entityId, string fieldName = "Name")
        {
            if (string.IsNullOrEmpty(value))
                return new SanitizeResult { Value = value };

            var result = new SanitizeResult
            {
                OriginalValue = value,
                OriginalLength = value.Length
            };

            string sanitized = value;
            var changes = new List<string>();

            // Step 1: Remove control characters (O(n) with HashSet)
            string cleaned = RemoveControlCharacters(sanitized);
            if (cleaned != sanitized)
            {
                changes.Add("Removed control characters");
                sanitized = cleaned;
            }

            // Step 2: Mode-specific escaping
            if (_mode == SanitizationMode.Xml)
            {
                string escaped = System.Security.SecurityElement.Escape(sanitized);
                if (escaped != sanitized)
                {
                    changes.Add("XML-escaped special characters");
                    sanitized = escaped;
                }
            }
            // JSON mode: no escaping needed - JSON serializer handles it

            // Step 3: Normalize whitespace
            string normalized = NormalizeWhitespace(sanitized);
            if (normalized != sanitized)
            {
                changes.Add("Normalized whitespace");
                sanitized = normalized;
            }

            // Step 4: Truncate using FieldLimits
            string truncated = FieldLimits.TruncateToLimit(entityType, fieldName, sanitized, out var truncResult);
            if (truncResult.WasTruncated)
            {
                changes.Add($"Truncated from {truncResult.OriginalLength} to {truncResult.AppliedLimit} chars");
                sanitized = truncated;
                result.CharactersLost = truncResult.CharactersLost;
                
                if (truncResult.Warning != null)
                {
                    _logger?.Log(LogLevel.Warning, truncResult.Warning);
                }
            }

            // Step 5: Trim
            sanitized = sanitized.Trim();

            result.Value = sanitized;
            result.WasModified = sanitized != value;
            result.Changes = changes;

            if (result.WasModified)
            {
                var severity = DetermineSeverity(changes, result.CharactersLost);
                RecordAction(entityType, entityId, fieldName, value, sanitized, changes, severity);
            }

            return result;
        }

        /// <summary>
        /// Sanitize a memo/description field
        /// </summary>
        public SanitizeResult SanitizeMemo(string value, string entityType, string entityId, string fieldName = "Memo")
        {
            if (string.IsNullOrEmpty(value))
                return new SanitizeResult { Value = value };

            var result = new SanitizeResult
            {
                OriginalValue = value,
                OriginalLength = value.Length
            };

            string sanitized = value;
            var changes = new List<string>();

            // Step 1: Remove control characters
            string cleaned = RemoveControlCharacters(sanitized);
            if (cleaned != sanitized)
            {
                changes.Add("Removed control characters");
                sanitized = cleaned;
            }

            // Step 2: Normalize whitespace (preserve newlines for memos)
            sanitized = CollapseMultipleSpaces(sanitized);

            // Step 3: Truncate using FieldLimits
            string truncated = FieldLimits.TruncateToLimit(entityType, fieldName, sanitized, out var truncResult);
            if (truncResult.WasTruncated)
            {
                changes.Add($"Truncated from {truncResult.OriginalLength} to {truncResult.AppliedLimit} chars");
                sanitized = truncated;
                result.CharactersLost = truncResult.CharactersLost;
            }

            result.Value = sanitized;
            result.WasModified = sanitized != value;
            result.Changes = changes;

            if (result.WasModified)
            {
                var severity = DetermineSeverity(changes, result.CharactersLost);
                RecordAction(entityType, entityId, fieldName, value, sanitized, changes, severity);
            }

            return result;
        }

        /// <summary>
        /// Sanitize an email address - preserves original if invalid
        /// </summary>
        public EmailSanitizeResult SanitizeEmail(string value, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(value))
                return new EmailSanitizeResult { Email = value };

            var result = new EmailSanitizeResult
            {
                EmailOriginal = value
            };

            // Clean whitespace
            string cleaned = value.Trim();
            cleaned = Regex.Replace(cleaned, @"\s+", "");

            // Validate email
            if (!IsValidEmail(cleaned))
            {
                result.Email = null;
                result.EmailInvalidReason = "Invalid email format";
                result.WasModified = true;

                RecordAction(entityType, entityId, "Email", value, null,
                    new List<string> { "Invalid email format - preserved in EmailOriginal" },
                    SanitizationSeverity.Warning);
            }
            else if (cleaned != value)
            {
                result.Email = cleaned;
                result.WasModified = true;

                RecordAction(entityType, entityId, "Email", value, cleaned,
                    new List<string> { "Removed whitespace" },
                    SanitizationSeverity.Info);
            }
            else
            {
                result.Email = value;
            }

            return result;
        }

        /// <summary>
        /// Sanitize a phone number with E.164 best-effort
        /// </summary>
        public PhoneSanitizeResult SanitizePhone(string value, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(value))
                return new PhoneSanitizeResult { Phone = value };

            var result = new PhoneSanitizeResult
            {
                PhoneOriginal = value
            };

            // Extract extension first
            var extMatch = Regex.Match(value, @"(?:ext|x|#|extension)\.?\s*(\d{1,6})", RegexOptions.IgnoreCase);
            if (extMatch.Success)
            {
                result.Extension = extMatch.Groups[1].Value;
                value = value.Substring(0, extMatch.Index).Trim();
            }

            // Extract digits and leading +
            bool hasPlus = value.TrimStart().StartsWith("+");
            string digits = Regex.Replace(value, @"[^\d]", "");

            // Format as E.164 best-effort
            if (digits.Length >= 10)
            {
                // North American: 10 digits -> +1XXXXXXXXXX
                if (digits.Length == 10)
                {
                    result.Phone = "+1" + digits;
                }
                // Already has country code: 11+ digits with leading 1
                else if (digits.Length == 11 && digits.StartsWith("1"))
                {
                    result.Phone = "+" + digits;
                }
                // International with +
                else if (hasPlus)
                {
                    result.Phone = "+" + digits;
                }
                else
                {
                    result.Phone = digits;
                }
            }
            else
            {
                // Short number - keep as-is
                result.Phone = digits;
            }

            // Compare against original, not the modified value variable
            result.WasModified = result.Phone != result.PhoneOriginal || result.Extension != null;

            if (result.WasModified)
            {
                RecordAction(entityType, entityId, "Phone", result.PhoneOriginal, result.Phone,
                    new List<string> { "Normalized phone format" },
                    SanitizationSeverity.Info);
            }

            return result;
        }

        /// <summary>
        /// Sanitize an address field
        /// </summary>
        public SanitizeResult SanitizeAddress(string value, string entityType, string entityId, string fieldName = "Address")
        {
            if (string.IsNullOrEmpty(value))
                return new SanitizeResult { Value = value };

            var result = new SanitizeResult
            {
                OriginalValue = value,
                OriginalLength = value.Length
            };

            string sanitized = value;
            var changes = new List<string>();

            // Step 1: Remove control characters
            string cleaned = RemoveControlCharacters(sanitized);
            if (cleaned != sanitized)
            {
                changes.Add("Removed control characters");
                sanitized = cleaned;
            }

            // Step 2: Normalize whitespace
            string normalized = NormalizeWhitespace(sanitized);
            if (normalized != sanitized)
            {
                changes.Add("Normalized whitespace");
                sanitized = normalized;
            }

            // Step 3: Remove truly problematic chars (keep #, -, /, etc.)
            char[] problematic = { '<', '>' };
            foreach (char c in problematic)
            {
                if (sanitized.Contains(c))
                {
                    sanitized = sanitized.Replace(c.ToString(), "");
                    changes.Add($"Removed '{c}'");
                }
            }

            // Step 4: Truncate using FieldLimits
            string truncated = FieldLimits.TruncateToLimit(entityType, fieldName, sanitized, out var truncResult);
            if (truncResult.WasTruncated)
            {
                changes.Add($"Truncated from {truncResult.OriginalLength} to {truncResult.AppliedLimit} chars");
                sanitized = truncated;
                result.CharactersLost = truncResult.CharactersLost;
            }

            result.Value = sanitized.Trim();
            result.WasModified = result.Value != value;
            result.Changes = changes;

            if (result.WasModified)
            {
                var severity = DetermineSeverity(changes, result.CharactersLost);
                RecordAction(entityType, entityId, fieldName, value, result.Value, changes, severity);
            }

            return result;
        }

        /// <summary>
        /// Sanitize a reference/document number
        /// </summary>
        public SanitizeResult SanitizeRefNumber(string value, string entityType, string entityId, string fieldName = "RefNumber")
        {
            if (string.IsNullOrEmpty(value))
                return new SanitizeResult { Value = value };

            var result = new SanitizeResult
            {
                OriginalValue = value,
                OriginalLength = value.Length
            };

            // Allow alphanumeric and common separators
            string sanitized = Regex.Replace(value, @"[^a-zA-Z0-9\-_\.]", "");
            var changes = new List<string>();

            if (sanitized != value)
            {
                changes.Add("Removed special characters");
            }

            // Truncate using FieldLimits
            string truncated = FieldLimits.TruncateToLimit(entityType, fieldName, sanitized, out var truncResult);
            if (truncResult.WasTruncated)
            {
                changes.Add($"Truncated from {truncResult.OriginalLength} to {truncResult.AppliedLimit} chars");
                sanitized = truncated;
                result.CharactersLost = truncResult.CharactersLost;
            }

            result.Value = sanitized;
            result.WasModified = sanitized != value;
            result.Changes = changes;

            if (result.WasModified)
            {
                var severity = DetermineSeverity(changes, result.CharactersLost);
                RecordAction(entityType, entityId, fieldName, value, sanitized, changes, severity);
            }

            return result;
        }

        /// <summary>
        /// Auto-sanitize an entire extracted data object
        /// </summary>
        public QBExtractedData SanitizeExtractedData(QBExtractedData data)
        {
            _logger?.Log(LogLevel.Info, "Starting data sanitization (mode: {0})", _mode);
            var startTime = DateTime.UtcNow;

            // Sanitize Customers
            if (data.Customers != null)
            {
                foreach (var customer in data.Customers)
                {
                    var nameResult = SanitizeName(customer.Name, "Customer", customer.ListID, "DisplayName");
                    customer.Name = nameResult.Value;
                    if (nameResult.WasModified) customer.NameOriginal = nameResult.OriginalValue;

                    var companyResult = SanitizeName(customer.CompanyName, "Customer", customer.ListID, "CompanyName");
                    customer.CompanyName = companyResult.Value;
                    if (companyResult.WasModified) customer.CompanyNameOriginal = companyResult.OriginalValue;

                    var emailResult = SanitizeEmail(customer.Email, "Customer", customer.ListID);
                    customer.Email = emailResult.Email;
                    if (emailResult.WasModified)
                    {
                        customer.EmailOriginal = emailResult.EmailOriginal;
                        customer.EmailInvalidReason = emailResult.EmailInvalidReason;
                    }

                    var phoneResult = SanitizePhone(customer.Phone, "Customer", customer.ListID);
                    customer.Phone = phoneResult.Phone;

                    // Bill Address
                    customer.BillAddressAddr1 = SanitizeAddress(customer.BillAddressAddr1, "Customer", customer.ListID, "Line1").Value;
                    customer.BillAddressAddr2 = SanitizeAddress(customer.BillAddressAddr2, "Customer", customer.ListID, "Line2").Value;
                    customer.BillAddressCity = SanitizeAddress(customer.BillAddressCity, "Customer", customer.ListID, "City").Value;
                    customer.BillAddressState = SanitizeAddress(customer.BillAddressState, "Customer", customer.ListID, "CountrySubDivisionCode").Value;
                    customer.BillAddressPostalCode = SanitizeAddress(customer.BillAddressPostalCode, "Customer", customer.ListID, "PostalCode").Value;

                    // Ship Address
                    customer.ShipAddressAddr1 = SanitizeAddress(customer.ShipAddressAddr1, "Customer", customer.ListID, "Line1").Value;
                    customer.ShipAddressAddr2 = SanitizeAddress(customer.ShipAddressAddr2, "Customer", customer.ListID, "Line2").Value;
                    customer.ShipAddressCity = SanitizeAddress(customer.ShipAddressCity, "Customer", customer.ListID, "City").Value;
                }
            }

            // Sanitize Vendors
            if (data.Vendors != null)
            {
                foreach (var vendor in data.Vendors)
                {
                    vendor.Name = SanitizeName(vendor.Name, "Vendor", vendor.ListID, "DisplayName").Value;
                    vendor.CompanyName = SanitizeName(vendor.CompanyName, "Vendor", vendor.ListID, "CompanyName").Value;
                    vendor.Email = SanitizeEmail(vendor.Email, "Vendor", vendor.ListID).Email;
                    vendor.Phone = SanitizePhone(vendor.Phone, "Vendor", vendor.ListID).Phone;

                    vendor.VendorAddressAddr1 = SanitizeAddress(vendor.VendorAddressAddr1, "Vendor", vendor.ListID, "Line1").Value;
                    vendor.VendorAddressAddr2 = SanitizeAddress(vendor.VendorAddressAddr2, "Vendor", vendor.ListID, "Line2").Value;
                    vendor.VendorAddressCity = SanitizeAddress(vendor.VendorAddressCity, "Vendor", vendor.ListID, "City").Value;
                }
            }

            // Sanitize Employees
            if (data.Employees != null)
            {
                foreach (var employee in data.Employees)
                {
                    employee.Name = SanitizeName(employee.Name, "Employee", employee.ListID, "DisplayName").Value;
                    employee.Email = SanitizeEmail(employee.Email, "Employee", employee.ListID).Email;
                    employee.Phone = SanitizePhone(employee.Phone, "Employee", employee.ListID).Phone;
                }
            }

            // Sanitize Items
            if (data.Items != null)
            {
                foreach (var item in data.Items)
                {
                    item.Name = SanitizeName(item.Name, "Item", item.ListID, "Name").Value;
                    item.Description = SanitizeMemo(item.Description, "Item", item.ListID, "Description").Value;
                    item.SalesDescription = SanitizeMemo(item.SalesDescription, "Item", item.ListID, "Description").Value;
                    item.PurchaseDescription = SanitizeMemo(item.PurchaseDescription, "Item", item.ListID, "PurchaseDesc").Value;
                }
            }

            // Sanitize Accounts
            if (data.Accounts != null)
            {
                foreach (var account in data.Accounts)
                {
                    var nameResult = SanitizeName(account.Name, "Account", account.ListID, "Name");
                    account.Name = nameResult.Value;
                    if (nameResult.WasModified) account.NameOriginal = nameResult.OriginalValue;

                    account.AccountNumber = SanitizeRefNumber(account.AccountNumber, "Account", account.ListID, "AcctNum").Value;
                    
                    var descResult = SanitizeMemo(account.Desc, "Account", account.ListID, "Description");
                    account.Desc = descResult.Value;
                    if (descResult.WasModified) account.DescOriginal = descResult.OriginalValue;
                }
            }

            // Sanitize Invoices
            if (data.Invoices != null)
            {
                foreach (var invoice in data.Invoices)
                {
                    invoice.RefNumber = SanitizeRefNumber(invoice.RefNumber, "Invoice", invoice.TxnID, "DocNumber").Value;
                    invoice.Memo = SanitizeMemo(invoice.Memo, "Invoice", invoice.TxnID, "PrivateNote").Value;
                    invoice.CustomerMsgRef = SanitizeMemo(invoice.CustomerMsgRef, "Invoice", invoice.TxnID, "CustomerMemo").Value;

                    if (invoice.Lines != null)
                    {
                        foreach (var line in invoice.Lines)
                        {
                            line.Description = SanitizeMemo(line.Description, "InvoiceLine", invoice.TxnID, "LineDescription").Value;
                        }
                    }
                }
            }

            // Sanitize Bills
            if (data.Bills != null)
            {
                foreach (var bill in data.Bills)
                {
                    bill.RefNumber = SanitizeRefNumber(bill.RefNumber, "Bill", bill.TxnID, "DocNumber").Value;
                    bill.Memo = SanitizeMemo(bill.Memo, "Bill", bill.TxnID, "PrivateNote").Value;
                }
            }

            // Sanitize Journal Entries
            if (data.JournalEntries != null)
            {
                foreach (var je in data.JournalEntries)
                {
                    je.RefNumber = SanitizeRefNumber(je.RefNumber, "JournalEntry", je.TxnID, "DocNumber").Value;

                    if (je.Lines != null)
                    {
                        foreach (var line in je.Lines)
                        {
                            line.Memo = SanitizeMemo(line.Memo, "JournalEntryLine", je.TxnID, "LineDescription").Value;
                        }
                    }
                }
            }

            // Sanitize Checks
            if (data.Checks != null)
            {
                foreach (var check in data.Checks)
                {
                    check.RefNumber = SanitizeRefNumber(check.RefNumber, "Check", check.TxnID, "DocNumber").Value;
                    check.Memo = SanitizeMemo(check.Memo, "Check", check.TxnID, "Memo").Value;
                }
            }

            // Sanitize Estimates
            if (data.Estimates != null)
            {
                foreach (var estimate in data.Estimates)
                {
                    estimate.RefNumber = SanitizeRefNumber(estimate.RefNumber, "Estimate", estimate.TxnID, "DocNumber").Value;
                    estimate.Memo = SanitizeMemo(estimate.Memo, "Estimate", estimate.TxnID, "PrivateNote").Value;
                }
            }

            // Sanitize Sales Receipts
            if (data.SalesReceipts != null)
            {
                foreach (var sr in data.SalesReceipts)
                {
                    sr.RefNumber = SanitizeRefNumber(sr.RefNumber, "SalesReceipt", sr.TxnID, "DocNumber").Value;
                    sr.Memo = SanitizeMemo(sr.Memo, "SalesReceipt", sr.TxnID, "PrivateNote").Value;
                }
            }

            // Sanitize Credit Memos
            if (data.CreditMemos != null)
            {
                foreach (var cm in data.CreditMemos)
                {
                    cm.RefNumber = SanitizeRefNumber(cm.RefNumber, "CreditMemo", cm.TxnID, "DocNumber").Value;
                    cm.Memo = SanitizeMemo(cm.Memo, "CreditMemo", cm.TxnID, "PrivateNote").Value;
                }
            }

            // Sanitize Purchase Orders
            if (data.PurchaseOrders != null)
            {
                foreach (var po in data.PurchaseOrders)
                {
                    po.RefNumber = SanitizeRefNumber(po.RefNumber, "PurchaseOrder", po.TxnID, "DocNumber").Value;
                    po.Memo = SanitizeMemo(po.Memo, "PurchaseOrder", po.TxnID, "Memo").Value;
                }
            }

            var elapsed = (DateTime.UtcNow - startTime).TotalSeconds;
            
            _logger?.Log(LogLevel.Info, "Sanitization complete in {0:F2}s. Changes: {1}", elapsed, Report.TotalActions);
            
            if (Report.TotalActions > 0)
            {
                _logger?.Log(LogLevel.Info, "  Info: {0}, Warning: {1}, Critical: {2}",
                    Report.InfoActions, Report.WarningActions, Report.CriticalActions);
            }

            return data;
        }

        /// <summary>
        /// Generate a sanitization report (optionally redacted)
        /// </summary>
        public string GenerateReport()
        {
            return Report.GenerateReport();
        }

        // ====================================================================
        // PRIVATE HELPER METHODS
        // ====================================================================

        private string RemoveControlCharacters(string text)
        {
            if (string.IsNullOrEmpty(text))
                return text;

            var sb = new StringBuilder(text.Length);
            foreach (char c in text)
            {
                if (!ControlChars.Contains(c))
                {
                    sb.Append(c);
                }
            }
            return sb.ToString();
        }

        private string NormalizeWhitespace(string text)
        {
            if (string.IsNullOrEmpty(text))
                return text;

            // Replace tabs/newlines with space, collapse multiple spaces
            text = text.Replace('\t', ' ').Replace('\n', ' ').Replace('\r', ' ');
            return Regex.Replace(text, @" {2,}", " ");
        }

        private string CollapseMultipleSpaces(string text)
        {
            if (string.IsNullOrEmpty(text))
                return text;

            return Regex.Replace(text, @" {2,}", " ");
        }

        private bool IsValidEmail(string email)
        {
            if (string.IsNullOrWhiteSpace(email))
                return false;

            try
            {
                // Use MailAddress for better validation than regex
                var addr = new MailAddress(email);
                return addr.Address == email;
            }
            catch (FormatException)
            {
                // Invalid email format
                return false;
            }
        }

        private SanitizationSeverity DetermineSeverity(List<string> changes, int charactersLost)
        {
            // Critical: significant data loss
            if (charactersLost > 50)
                return SanitizationSeverity.Critical;

            // Warning: any truncation
            if (charactersLost > 0)
                return SanitizationSeverity.Warning;

            // Warning: invalid email cleared
            if (changes.Any(c => c.Contains("Invalid email")))
                return SanitizationSeverity.Warning;

            // Info: everything else
            return SanitizationSeverity.Info;
        }

        private void RecordAction(
            string entityType,
            string entityId,
            string fieldName,
            string original,
            string sanitized,
            List<string> changes,
            SanitizationSeverity severity)
        {
            Report.RecordSanitization(new SanitizationAction
            {
                EntityType = entityType,
                EntityId = entityId,
                FieldName = fieldName,
                OriginalValue = original,
                SanitizedValue = sanitized,
                ChangesMade = changes,
                Severity = severity
            });
        }
    }

    /// <summary>
    /// Sanitization mode
    /// </summary>
    public enum SanitizationMode
    {
        Json,  // No XML escaping
        Xml    // Apply XML escaping
    }

    /// <summary>
    /// Sanitization severity levels
    /// </summary>
    public enum SanitizationSeverity
    {
        Info,
        Warning,
        Critical
    }

    /// <summary>
    /// Sanitization configuration
    /// </summary>
    public class SanitizationConfig
    {
        public bool IncludeRawValuesInReport { get; set; } = false;
        public bool TreatInvalidEmailAsWarning { get; set; } = true;
        public bool NormalizePhoneToE164 { get; set; } = true;

        public static SanitizationConfig Default => new SanitizationConfig();
    }

    /// <summary>
    /// Result of sanitizing a single value
    /// </summary>
    public class SanitizeResult
    {
        public string Value { get; set; }
        public string OriginalValue { get; set; }
        public int OriginalLength { get; set; }
        public bool WasModified { get; set; }
        public int CharactersLost { get; set; }
        public List<string> Changes { get; set; } = new List<string>();
    }

    /// <summary>
    /// Result of sanitizing an email
    /// </summary>
    public class EmailSanitizeResult
    {
        public string Email { get; set; }
        public string EmailOriginal { get; set; }
        public string EmailInvalidReason { get; set; }
        public bool WasModified { get; set; }
    }

    /// <summary>
    /// Result of sanitizing a phone number
    /// </summary>
    public class PhoneSanitizeResult
    {
        public string Phone { get; set; }
        public string PhoneOriginal { get; set; }
        public string Extension { get; set; }
        public bool WasModified { get; set; }
    }

    /// <summary>
    /// Represents a single sanitization action taken
    /// </summary>
    public class SanitizationAction
    {
        public string EntityType { get; set; }
        public string EntityId { get; set; }
        public string FieldName { get; set; }
        public string OriginalValue { get; set; }
        public string SanitizedValue { get; set; }
        public List<string> ChangesMade { get; set; } = new List<string>();
        public SanitizationSeverity Severity { get; set; }
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }

    /// <summary>
    /// Tracks all sanitization actions for audit trail
    /// </summary>
    public class SanitizationReport
    {
        private readonly bool _includeRawValues;
        public List<SanitizationAction> Actions { get; } = new List<SanitizationAction>();

        public int TotalActions => Actions.Count;
        public int InfoActions => Actions.Count(a => a.Severity == SanitizationSeverity.Info);
        public int WarningActions => Actions.Count(a => a.Severity == SanitizationSeverity.Warning);
        public int CriticalActions => Actions.Count(a => a.Severity == SanitizationSeverity.Critical);

        public SanitizationReport(bool includeRawValues = false)
        {
            _includeRawValues = includeRawValues;
        }

        public void RecordSanitization(SanitizationAction action)
        {
            Actions.Add(action);
        }

        public void Clear()
        {
            Actions.Clear();
        }

        /// <summary>
        /// Generate report with optional value redaction
        /// </summary>
        public string GenerateReport()
        {
            var sb = new StringBuilder();
            sb.AppendLine(new string('=', 80));
            sb.AppendLine("DATA SANITIZATION REPORT");
            sb.AppendLine(new string('=', 80));
            sb.AppendLine();

            sb.AppendLine($"Total Actions: {TotalActions}");
            sb.AppendLine($"INFO: {InfoActions}");
            sb.AppendLine($"WARNING: {WarningActions}");
            sb.AppendLine($"CRITICAL: {CriticalActions}");
            sb.AppendLine();

            if (Actions.Count == 0)
            {
                sb.AppendLine("✓ No sanitization needed - data is clean!");
                return sb.ToString();
            }

            // Group by entity type
            var grouped = Actions.GroupBy(a => a.EntityType);

            foreach (var group in grouped.OrderByDescending(g => g.Count()))
            {
                sb.AppendLine($"{group.Key} ({group.Count()} changes):");
                sb.AppendLine(new string('-', 40));

                foreach (var action in group.Take(10))
                {
                    sb.AppendLine($"  [{action.Severity}] {action.FieldName}");
                    
                    if (_includeRawValues)
                    {
                        // Include actual values (use with caution)
                        sb.AppendLine($"    Before: {Truncate(action.OriginalValue, 100)}");
                        sb.AppendLine($"    After:  {Truncate(action.SanitizedValue, 100)}");
                    }
                    else
                    {
                        // Hash + length for correlation without leaking data
                        sb.AppendLine($"    Original: {action.OriginalValue?.Length ?? 0} chars, hash: {ComputeShortHash(action.OriginalValue)}");
                        sb.AppendLine($"    Sanitized: {action.SanitizedValue?.Length ?? 0} chars, hash: {ComputeShortHash(action.SanitizedValue)}");
                    }
                    
                    sb.AppendLine($"    Changes: {string.Join(", ", action.ChangesMade)}");
                    sb.AppendLine();
                }

                if (group.Count() > 10)
                {
                    sb.AppendLine($"  ... and {group.Count() - 10} more");
                    sb.AppendLine();
                }
            }

            return sb.ToString();
        }

        private static string Truncate(string value, int maxLength)
        {
            if (string.IsNullOrEmpty(value))
                return "(null)";
            if (value.Length <= maxLength)
                return value;
            return value.Substring(0, maxLength) + "...";
        }

        private static string ComputeShortHash(string value)
        {
            if (string.IsNullOrEmpty(value))
                return "null";

            using (var sha256 = SHA256.Create())
            {
                byte[] hash = sha256.ComputeHash(Encoding.UTF8.GetBytes(value));
                return Convert.ToBase64String(hash).Substring(0, 8);
            }
        }
    }
}