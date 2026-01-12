using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;

namespace QBDesktopExtractor
{
    /// <summary>
    /// ENTERPRISE-GRADE Data Sanitizer (v4.0)
    /// 
    /// THE "HEALING" LOGIC:
    /// Instead of just warning about issues, this class FIXES them automatically during extraction.
    /// 
    /// FEATURES:
    /// - Auto-sanitizes illegal characters in names
    /// - Fixes invalid XML/JSON characters
    /// - Normalizes whitespace and special characters
    /// - Truncates overly long strings
    /// - Generates sanitization report for audit trail
    /// - Maintains original values in "OriginalValue" fields for reference
    /// 
    /// This is what transforms a tool from "warning you about problems" to "solving problems for you."
    /// </summary>
    public class DataSanitizer
    {
        // Characters that break XML/JSON APIs
        private static readonly char[] ILLEGAL_XML_CHARS = { '&', '<', '>', '"', '\'' };
        private static readonly char[] CONTROL_CHARS = { '\x00', '\x01', '\x02', '\x03', '\x04', '\x05', '\x06', '\x07', 
                                                          '\x08', '\x0B', '\x0C', '\x0E', '\x0F', '\x10', '\x11', '\x12', 
                                                          '\x13', '\x14', '\x15', '\x16', '\x17', '\x18', '\x19', '\x1A', 
                                                          '\x1B', '\x1C', '\x1D', '\x1E', '\x1F' };
        
        // Replacements that preserve meaning
        private static readonly Dictionary<char, string> SMART_REPLACEMENTS = new Dictionary<char, string>
        {
            { '&', " and " },
            { '<', " less than " },
            { '>', " greater than " },
            { '"', "'" },
            { '\t', " " },
            { '\n', " " },
            { '\r', " " }
        };

        private static readonly int MAX_NAME_LENGTH = 200;
        private static readonly int MAX_MEMO_LENGTH = 4000;
        
        public SanitizationReport Report { get; private set; }
        
        public DataSanitizer()
        {
            Report = new SanitizationReport();
        }

        /// <summary>
        /// Sanitize a name field (customer, vendor, account, etc.)
        /// </summary>
        public string SanitizeName(string name, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(name))
                return name;

            string original = name;
            string sanitized = name;
            List<string> changes = new List<string>();

            // Step 1: Replace illegal XML/JSON characters with smart alternatives
            foreach (var kvp in SMART_REPLACEMENTS)
            {
                if (sanitized.Contains(kvp.Key))
                {
                    sanitized = sanitized.Replace(kvp.Key.ToString(), kvp.Value);
                    changes.Add($"Replaced '{kvp.Key}' with '{kvp.Value}'");
                }
            }

            // Step 2: Remove control characters
            sanitized = RemoveControlCharacters(sanitized);
            if (sanitized != name && changes.Count == 0)
            {
                changes.Add("Removed control characters");
            }

            // Step 3: Normalize whitespace (collapse multiple spaces)
            sanitized = NormalizeWhitespace(sanitized);
            if (sanitized != name && !sanitized.Contains("  ") && name.Contains("  "))
            {
                changes.Add("Normalized whitespace");
            }

            // Step 4: Truncate if too long (ENHANCED v4.0 - Explicit warnings)
            if (sanitized.Length > MAX_NAME_LENGTH)
            {
                sanitized = sanitized.Substring(0, MAX_NAME_LENGTH).TrimEnd();
                int charsLost = original.Length - MAX_NAME_LENGTH;
                string truncationMsg = $"⚠️ TRUNCATED: {original.Length} chars → {MAX_NAME_LENGTH} chars (LOST {charsLost} chars)";
                changes.Add(truncationMsg);
                
                // Log as HIGH SEVERITY if significant data loss
                if (charsLost > 50)
                {
                    Console.WriteLine($"      ⚠️ WARNING: Significant truncation in {entityType} {entityId}");
                    Console.WriteLine($"         Original length: {original.Length} chars");
                    Console.WriteLine($"         Truncated to: {MAX_NAME_LENGTH} chars");
                    Console.WriteLine($"         Data loss: {charsLost} chars");
                }
            }

            // Step 5: Remove leading/trailing whitespace
            sanitized = sanitized.Trim();

            // Log if changes were made
            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Name",
                    OriginalValue = original,
                    SanitizedValue = sanitized,
                    ChangesMade = changes,
                    Severity = DetermineSeverity(changes)
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Sanitize a memo/description field (longer text allowed)
        /// </summary>
        public string SanitizeMemo(string memo, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(memo))
                return memo;

            string original = memo;
            string sanitized = memo;
            List<string> changes = new List<string>();

            // Step 1: Replace illegal XML/JSON characters
            foreach (var kvp in SMART_REPLACEMENTS)
            {
                if (sanitized.Contains(kvp.Key))
                {
                    sanitized = sanitized.Replace(kvp.Key.ToString(), kvp.Value);
                    changes.Add($"Replaced '{kvp.Key}' with '{kvp.Value}'");
                }
            }

            // Step 2: Remove control characters
            sanitized = RemoveControlCharacters(sanitized);

            // Step 3: Truncate if too long (memos can be longer)
            if (sanitized.Length > MAX_MEMO_LENGTH)
            {
                sanitized = sanitized.Substring(0, MAX_MEMO_LENGTH).TrimEnd() + "...";
                changes.Add($"Truncated from {original.Length} to {MAX_MEMO_LENGTH} characters");
            }

            // Log if changes were made
            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Memo/Description",
                    OriginalValue = original.Length > 100 ? original.Substring(0, 100) + "..." : original,
                    SanitizedValue = sanitized.Length > 100 ? sanitized.Substring(0, 100) + "..." : sanitized,
                    ChangesMade = changes,
                    Severity = "INFO"
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Sanitize an email address
        /// </summary>
        public string SanitizeEmail(string email, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(email))
                return email;

            string original = email;
            string sanitized = email.Trim();

            // Remove any whitespace
            sanitized = Regex.Replace(sanitized, @"\s+", "");

            // Basic email validation and cleanup
            if (!IsValidEmail(sanitized))
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Email",
                    OriginalValue = original,
                    SanitizedValue = null,
                    ChangesMade = new List<string> { "Invalid email format - cleared" },
                    Severity = "WARNING"
                });
                return null; // Clear invalid email
            }

            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Email",
                    OriginalValue = original,
                    SanitizedValue = sanitized,
                    ChangesMade = new List<string> { "Removed whitespace" },
                    Severity = "INFO"
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Sanitize a phone number
        /// </summary>
        public string SanitizePhone(string phone, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(phone))
                return phone;

            string original = phone;
            
            // Remove all non-digit characters except + (for international)
            string sanitized = Regex.Replace(phone, @"[^\d+x]", "");

            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Phone",
                    OriginalValue = original,
                    SanitizedValue = sanitized,
                    ChangesMade = new List<string> { "Removed non-numeric characters" },
                    Severity = "INFO"
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Sanitize an address field
        /// </summary>
        public string SanitizeAddress(string address, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(address))
                return address;

            string original = address;
            string sanitized = address;
            List<string> changes = new List<string>();

            // Only sanitize truly problematic characters (keep #, -, /)
            char[] addressProblematic = { '<', '>', '"', '\'' };
            foreach (char c in addressProblematic)
            {
                if (sanitized.Contains(c))
                {
                    sanitized = sanitized.Replace(c.ToString(), "");
                    changes.Add($"Removed '{c}'");
                }
            }

            // Remove control characters
            sanitized = RemoveControlCharacters(sanitized);

            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "Address",
                    OriginalValue = original,
                    SanitizedValue = sanitized,
                    ChangesMade = changes,
                    Severity = "INFO"
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Sanitize a numeric string (account numbers, etc.)
        /// </summary>
        public string SanitizeAccountNumber(string accountNum, string entityType, string entityId)
        {
            if (string.IsNullOrEmpty(accountNum))
                return accountNum;

            string original = accountNum;
            
            // Allow alphanumeric and common separators (-, _, .)
            string sanitized = Regex.Replace(accountNum, @"[^a-zA-Z0-9\-_\.]", "");

            if (sanitized != original)
            {
                Report.RecordSanitization(new SanitizationAction
                {
                    EntityType = entityType,
                    EntityId = entityId,
                    FieldName = "AccountNumber",
                    OriginalValue = original,
                    SanitizedValue = sanitized,
                    ChangesMade = new List<string> { "Removed special characters" },
                    Severity = "INFO"
                });
            }

            return sanitized;
        }

        /// <summary>
        /// Auto-sanitize an entire extracted data object
        /// </summary>
        public QBExtractedData SanitizeExtractedData(QBExtractedData data)
        {
            Console.WriteLine("\n🧹 AUTO-SANITIZING DATA (Healing Mode)...");
            
            var startTime = DateTime.Now;

            // Sanitize Customers
            if (data.Customers != null)
            {
                foreach (var customer in data.Customers)
                {
                    customer.Name = SanitizeName(customer.Name, "Customer", customer.ListID);
                    customer.CompanyName = SanitizeName(customer.CompanyName, "Customer", customer.ListID);
                    customer.Email = SanitizeEmail(customer.Email, "Customer", customer.ListID);
                    customer.Phone = SanitizePhone(customer.Phone, "Customer", customer.ListID);
                    
                    if (customer.BillAddress != null)
                    {
                        customer.BillAddress.Addr1 = SanitizeAddress(customer.BillAddress.Addr1, "Customer", customer.ListID);
                        customer.BillAddress.Addr2 = SanitizeAddress(customer.BillAddress.Addr2, "Customer", customer.ListID);
                        customer.BillAddress.City = SanitizeAddress(customer.BillAddress.City, "Customer", customer.ListID);
                    }
                    
                    if (customer.ShipAddress != null)
                    {
                        customer.ShipAddress.Addr1 = SanitizeAddress(customer.ShipAddress.Addr1, "Customer", customer.ListID);
                        customer.ShipAddress.Addr2 = SanitizeAddress(customer.ShipAddress.Addr2, "Customer", customer.ListID);
                        customer.ShipAddress.City = SanitizeAddress(customer.ShipAddress.City, "Customer", customer.ListID);
                    }
                }
            }

            // Sanitize Vendors
            if (data.Vendors != null)
            {
                foreach (var vendor in data.Vendors)
                {
                    vendor.Name = SanitizeName(vendor.Name, "Vendor", vendor.ListID);
                    vendor.CompanyName = SanitizeName(vendor.CompanyName, "Vendor", vendor.ListID);
                    vendor.Email = SanitizeEmail(vendor.Email, "Vendor", vendor.ListID);
                    vendor.Phone = SanitizePhone(vendor.Phone, "Vendor", vendor.ListID);
                    
                    if (vendor.VendorAddress != null)
                    {
                        vendor.VendorAddress.Addr1 = SanitizeAddress(vendor.VendorAddress.Addr1, "Vendor", vendor.ListID);
                        vendor.VendorAddress.Addr2 = SanitizeAddress(vendor.VendorAddress.Addr2, "Vendor", vendor.ListID);
                        vendor.VendorAddress.City = SanitizeAddress(vendor.VendorAddress.City, "Vendor", vendor.ListID);
                    }
                }
            }

            // Sanitize Employees
            if (data.Employees != null)
            {
                foreach (var employee in data.Employees)
                {
                    employee.Name = SanitizeName(employee.Name, "Employee", employee.ListID);
                    employee.Email = SanitizeEmail(employee.Email, "Employee", employee.ListID);
                    employee.Phone = SanitizePhone(employee.Phone, "Employee", employee.ListID);
                }
            }

            // Sanitize Items
            if (data.Items != null)
            {
                foreach (var item in data.Items)
                {
                    item.Name = SanitizeName(item.Name, "Item", item.ListID);
                    item.Description = SanitizeMemo(item.Description, "Item", item.ListID);
                    item.SalesDescription = SanitizeMemo(item.SalesDescription, "Item", item.ListID);
                    item.PurchaseDescription = SanitizeMemo(item.PurchaseDescription, "Item", item.ListID);
                }
            }

            // Sanitize Accounts
            if (data.Accounts != null)
            {
                foreach (var account in data.Accounts)
                {
                    account.Name = SanitizeName(account.Name, "Account", account.ListID);
                    account.AccountNumber = SanitizeAccountNumber(account.AccountNumber, "Account", account.ListID);
                    account.Description = SanitizeMemo(account.Description, "Account", account.ListID);
                }
            }

            // Sanitize Invoices
            if (data.Invoices != null)
            {
                foreach (var invoice in data.Invoices)
                {
                    invoice.RefNumber = SanitizeAccountNumber(invoice.RefNumber, "Invoice", invoice.TxnID);
                    invoice.Memo = SanitizeMemo(invoice.Memo, "Invoice", invoice.TxnID);
                    invoice.CustomerMsgRef = SanitizeMemo(invoice.CustomerMsgRef, "Invoice", invoice.TxnID);
                    
                    if (invoice.Lines != null)
                    {
                        foreach (var line in invoice.Lines)
                        {
                            line.Description = SanitizeMemo(line.Description, "InvoiceLine", invoice.TxnID);
                        }
                    }
                }
            }

            // Sanitize Bills
            if (data.Bills != null)
            {
                foreach (var bill in data.Bills)
                {
                    bill.RefNumber = SanitizeAccountNumber(bill.RefNumber, "Bill", bill.TxnID);
                    bill.Memo = SanitizeMemo(bill.Memo, "Bill", bill.TxnID);
                }
            }

            // Sanitize Journal Entries
            if (data.JournalEntries != null)
            {
                foreach (var je in data.JournalEntries)
                {
                    je.RefNumber = SanitizeAccountNumber(je.RefNumber, "JournalEntry", je.TxnID);
                    
                    if (je.Lines != null)
                    {
                        foreach (var line in je.Lines)
                        {
                            line.Memo = SanitizeMemo(line.Memo, "JournalEntryLine", je.TxnID);
                        }
                    }
                }
            }

            var elapsed = (DateTime.Now - startTime).TotalSeconds;
            
            Console.WriteLine($"   ✓ Sanitization complete in {elapsed:F2} seconds");
            Console.WriteLine($"   Changes made: {Report.TotalActions}");
            
            if (Report.TotalActions > 0)
            {
                Console.WriteLine($"   - INFO level: {Report.InfoActions}");
                Console.WriteLine($"   - WARNING level: {Report.WarningActions}");
                Console.WriteLine($"   - CRITICAL level: {Report.CriticalActions}");
            }

            return data;
        }

        /// <summary>
        /// Generate a detailed sanitization report
        /// </summary>
        public string GenerateSanitizationReport()
        {
            var sb = new StringBuilder();
            sb.AppendLine("=" * 80);
            sb.AppendLine("DATA SANITIZATION REPORT");
            sb.AppendLine("=" * 80);
            sb.AppendLine();
            
            sb.AppendLine($"Total Actions: {Report.TotalActions}");
            sb.AppendLine($"INFO: {Report.InfoActions}");
            sb.AppendLine($"WARNING: {Report.WarningActions}");
            sb.AppendLine($"CRITICAL: {Report.CriticalActions}");
            sb.AppendLine();

            if (Report.Actions.Count == 0)
            {
                sb.AppendLine("✓ No sanitization needed - data is clean!");
                return sb.ToString();
            }

            // Group by entity type
            var grouped = Report.Actions.GroupBy(a => a.EntityType);
            
            foreach (var group in grouped.OrderByDescending(g => g.Count()))
            {
                sb.AppendLine($"{group.Key} ({group.Count()} changes):");
                sb.AppendLine(new string('-', 40));
                
                foreach (var action in group.Take(10)) // Show first 10 per type
                {
                    sb.AppendLine($"  [{action.Severity}] {action.FieldName}");
                    sb.AppendLine($"    Before: {action.OriginalValue}");
                    sb.AppendLine($"    After:  {action.SanitizedValue}");
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

        // ====================================================================
        // PRIVATE HELPER METHODS
        // ====================================================================

        private string RemoveControlCharacters(string text)
        {
            if (string.IsNullOrEmpty(text))
                return text;

            var sb = new StringBuilder();
            foreach (char c in text)
            {
                if (!CONTROL_CHARS.Contains(c))
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

            // Replace multiple spaces with single space
            return Regex.Replace(text, @"\s+", " ");
        }

        private bool IsValidEmail(string email)
        {
            if (string.IsNullOrWhiteSpace(email))
                return false;

            try
            {
                // Simple regex for basic email validation
                var regex = new Regex(@"^[^@\s]+@[^@\s]+\.[^@\s]+$");
                return regex.IsMatch(email);
            }
            catch
            {
                return false;
            }
        }

        private string DetermineSeverity(List<string> changes)
        {
            // HIGH_SEVERITY: Significant truncation (data loss > 20 chars)
            if (changes.Any(c => c.Contains("TRUNCATED") && c.Contains("LOST")))
            {
                var lostMatch = System.Text.RegularExpressions.Regex.Match(
                    changes.First(c => c.Contains("LOST")), 
                    @"LOST (\d+) chars");
                if (lostMatch.Success && int.Parse(lostMatch.Groups[1].Value) > 20)
                    return "HIGH_SEVERITY";
            }
            
            // Critical: if we had to replace XML chars that could break APIs
            if (changes.Any(c => c.Contains("'&'") || c.Contains("'<'") || c.Contains("'>'")))
                return "CRITICAL";
            
            // Warning: if we truncated
            if (changes.Any(c => c.Contains("Truncated") || c.Contains("TRUNCATED")))
                return "WARNING";
            
            // Info: everything else
            return "INFO";
        }
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
        public string Severity { get; set; } // INFO, WARNING, CRITICAL
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }

    /// <summary>
    /// Tracks all sanitization actions for audit trail
    /// </summary>
    public class SanitizationReport
    {
        public List<SanitizationAction> Actions { get; set; } = new List<SanitizationAction>();
        
        public int TotalActions => Actions.Count;
        public int InfoActions => Actions.Count(a => a.Severity == "INFO");
        public int WarningActions => Actions.Count(a => a.Severity == "WARNING");
        public int CriticalActions => Actions.Count(a => a.Severity == "CRITICAL");

        public void RecordSanitization(SanitizationAction action)
        {
            Actions.Add(action);
        }

        public void Clear()
        {
            Actions.Clear();
        }
    }
}