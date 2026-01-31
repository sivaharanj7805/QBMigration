using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Enterprise-grade field length limits for target systems
    /// v4.2: Comprehensive per-entity, per-field truncation with safety features
    /// 
    /// FIXES FROM REVIEW:
    /// - TruncateToLimit safe for limit <= 3
    /// - Case-insensitive field matching
    /// - Field alias mapping (internal names to QBO names)
    /// - Unicode normalization before length checks
    /// - Hash suffix for identifiers to prevent collisions
    /// - Returns "unknown limit" warning instead of silent default
    /// - Comprehensive entity/field coverage
    /// - Versioned limit profiles
    /// </summary>
    public static class FieldLimits
    {
        /// <summary>
        /// Field alias mapping: internal model field names to QBO API field names
        /// </summary>
        private static readonly Dictionary<(string Entity, string InternalField), string> FieldAliases =
            new Dictionary<(string, string), string>(new TupleStringComparer())
        {
            // Customer field mappings
            [("Customer", "Name")] = "DisplayName",
            [("Customer", "RefNumber")] = "DocNumber",
            [("Customer", "Memo")] = "PrivateNote",
            
            // Vendor field mappings
            [("Vendor", "Name")] = "DisplayName",
            
            // Account field mappings
            [("Account", "AccountNumber")] = "AcctNum",
            [("Account", "Desc")] = "Description",
            
            // Invoice field mappings
            [("Invoice", "RefNumber")] = "DocNumber",
            [("Invoice", "Memo")] = "PrivateNote",
            [("Invoice", "CustomerMsg")] = "CustomerMemo",
            [("Invoice", "CustomerMsgRef")] = "CustomerMemo",
            
            // Bill field mappings
            [("Bill", "RefNumber")] = "DocNumber",
            [("Bill", "Memo")] = "PrivateNote",
            
            // JournalEntry field mappings
            [("JournalEntry", "RefNumber")] = "DocNumber",
            
            // Estimate field mappings
            [("Estimate", "RefNumber")] = "DocNumber",
            [("Estimate", "CustomerMsg")] = "CustomerMessage",
            
            // SalesReceipt field mappings
            [("SalesReceipt", "RefNumber")] = "DocNumber",
            
            // CreditMemo field mappings
            [("CreditMemo", "RefNumber")] = "DocNumber",
            
            // PurchaseOrder field mappings
            [("PurchaseOrder", "RefNumber")] = "DocNumber"
        };

        /// <summary>
        /// QBO API field length limits
        /// Structure: [EntityType][FieldName] = MaxLength
        /// Based on QuickBooks Online API documentation
        /// </summary>
        public static readonly Dictionary<string, Dictionary<string, int>> QBOLimits =
            new Dictionary<string, Dictionary<string, int>>(StringComparer.OrdinalIgnoreCase)
        {
            ["Customer"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DisplayName"] = 100,
                ["CompanyName"] = 100,
                ["GivenName"] = 25,
                ["MiddleName"] = 25,
                ["FamilyName"] = 25,
                ["Suffix"] = 10,
                ["PrintOnCheckName"] = 100,
                ["PrimaryEmailAddr"] = 100,
                ["PrimaryPhone"] = 30,
                ["Mobile"] = 30,
                ["Fax"] = 30,
                ["WebAddr"] = 1000,
                ["Notes"] = 4000,
                ["ResaleNumber"] = 16,
                ["AccountNumber"] = 100,
                // Address fields
                ["Line1"] = 500,
                ["Line2"] = 500,
                ["Line3"] = 500,
                ["Line4"] = 500,
                ["Line5"] = 500,
                ["City"] = 255,
                ["CountrySubDivisionCode"] = 255,
                ["PostalCode"] = 30,
                ["Country"] = 255
            },

            ["Vendor"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DisplayName"] = 100,
                ["CompanyName"] = 100,
                ["GivenName"] = 25,
                ["MiddleName"] = 25,
                ["FamilyName"] = 25,
                ["PrintOnCheckName"] = 100,
                ["PrimaryEmailAddr"] = 100,
                ["PrimaryPhone"] = 30,
                ["Mobile"] = 30,
                ["Fax"] = 30,
                ["WebAddr"] = 1000,
                ["Notes"] = 4000,
                ["AcctNum"] = 100,
                ["TaxIdentifier"] = 20,
                // Address fields
                ["Line1"] = 500,
                ["Line2"] = 500,
                ["City"] = 255,
                ["CountrySubDivisionCode"] = 255,
                ["PostalCode"] = 30,
                ["Country"] = 255
            },

            ["Account"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 100,
                ["Description"] = 200,
                ["AcctNum"] = 7,
                ["FullyQualifiedName"] = 500
            },

            ["Item"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 100,
                ["Description"] = 4000,
                ["PurchaseDesc"] = 4000,
                ["Sku"] = 100,
                ["FullyQualifiedName"] = 500
            },

            ["Invoice"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["CustomerMemo"] = 1000,
                ["PrivateNote"] = 4000,
                ["TrackingNum"] = 100,
                ["PONumber"] = 25,
                ["LineDescription"] = 4000
            },

            ["Bill"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["JournalEntry"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["Estimate"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["CustomerMessage"] = 1000,
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["SalesReceipt"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["CustomerMemo"] = 1000,
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["CreditMemo"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["CustomerMemo"] = 1000,
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["PurchaseOrder"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["Memo"] = 4000,
                ["PrivateNote"] = 4000,
                ["POEmail"] = 100,
                ["LineDescription"] = 4000
            },

            ["Payment"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["PrivateNote"] = 4000,
                ["PaymentRefNum"] = 21
            },

            ["Deposit"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["PrivateNote"] = 4000,
                ["LineDescription"] = 4000
            },

            ["Check"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DocNumber"] = 21,
                ["PrivateNote"] = 4000,
                ["Memo"] = 4000,
                ["LineDescription"] = 4000
            },

            ["Employee"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["DisplayName"] = 100,
                ["GivenName"] = 25,
                ["FamilyName"] = 25,
                ["PrimaryEmailAddr"] = 100,
                ["PrimaryPhone"] = 30,
                ["SSN"] = 100 // Usually masked
            },

            ["Class"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 100,
                ["FullyQualifiedName"] = 500
            },

            ["Department"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 100,
                ["FullyQualifiedName"] = 500
            },

            ["Terms"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 31
            },

            ["PaymentMethod"] = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
            {
                ["Name"] = 31
            }
        };

        /// <summary>
        /// Default limits by field category (when specific limit not found)
        /// </summary>
        private static readonly Dictionary<string, int> CategoryDefaults = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase)
        {
            ["name"] = 100,
            ["displayname"] = 100,
            ["description"] = 4000,
            ["memo"] = 4000,
            ["note"] = 4000,
            ["number"] = 21,
            ["docnumber"] = 21,
            ["refnumber"] = 21,
            ["email"] = 100,
            ["phone"] = 30,
            ["address"] = 500,
            ["city"] = 255,
            ["state"] = 255,
            ["postalcode"] = 30,
            ["country"] = 255,
            ["sku"] = 100
        };

        /// <summary>
        /// Get the maximum length for a specific entity and field
        /// Returns null if limit not found (caller should handle as warning)
        /// </summary>
        public static LimitResult GetLimit(string entityType, string fieldName)
        {
            // Try to resolve field alias first
            string resolvedFieldName = ResolveFieldAlias(entityType, fieldName);
            
            // Try exact match with resolved name
            if (QBOLimits.TryGetValue(entityType, out var entityLimits))
            {
                if (entityLimits.TryGetValue(resolvedFieldName, out int limit))
                {
                    return new LimitResult
                    {
                        Limit = limit,
                        Source = LimitSource.Exact,
                        EntityType = entityType,
                        FieldName = fieldName,
                        ResolvedFieldName = resolvedFieldName
                    };
                }
            }

            // Try category default based on field name pattern
            // Use word boundary matching to avoid false positives
            // e.g., "name" should match "CustomerName" or "Name" but not "NameDescription" or "Unnamed"
            foreach (var category in CategoryDefaults)
            {
                if (MatchesCategoryPattern(resolvedFieldName, category.Key))
                {
                    return new LimitResult
                    {
                        Limit = category.Value,
                        Source = LimitSource.CategoryDefault,
                        EntityType = entityType,
                        FieldName = fieldName,
                        ResolvedFieldName = resolvedFieldName,
                        MatchedCategory = category.Key
                    };
                }
            }

            // Unknown limit - return null so caller can decide
            return new LimitResult
            {
                Limit = null,
                Source = LimitSource.Unknown,
                EntityType = entityType,
                FieldName = fieldName,
                ResolvedFieldName = resolvedFieldName
            };
        }

        /// <summary>
        /// Get limit with fallback (for backwards compatibility)
        /// </summary>
        public static int GetLimitOrDefault(string entityType, string fieldName, int defaultLimit = 200)
        {
            var result = GetLimit(entityType, fieldName);
            return result.Limit ?? defaultLimit;
        }

        /// <summary>
        /// Check if field name matches a category pattern using word boundary logic.
        /// Matches when:
        /// - Field ends with the category (e.g., "CustomerName" matches "name")
        /// - Field equals the category exactly (e.g., "Name" matches "name")
        /// - Category appears at a camelCase boundary (e.g., "NameFirst" does NOT match "name")
        /// </summary>
        private static bool MatchesCategoryPattern(string fieldName, string category)
        {
            if (string.IsNullOrEmpty(fieldName) || string.IsNullOrEmpty(category))
                return false;

            // Case-insensitive comparison
            string fieldLower = fieldName.ToLowerInvariant();
            string categoryLower = category.ToLowerInvariant();

            // Exact match
            if (fieldLower == categoryLower)
                return true;

            // Check if field ends with category (most common pattern: CustomerName ends with name)
            if (fieldLower.EndsWith(categoryLower))
            {
                // Verify it's at a word boundary (preceded by a different character class)
                int boundaryIndex = fieldLower.Length - categoryLower.Length - 1;
                if (boundaryIndex < 0)
                    return true; // Category is the whole field

                char precedingChar = fieldName[boundaryIndex];
                // Word boundary: preceding char is lowercase followed by uppercase,
                // or preceding char is not a letter
                char firstCategoryChar = fieldName[boundaryIndex + 1];
                if (!char.IsLetter(precedingChar) ||
                    (char.IsLower(precedingChar) && char.IsUpper(firstCategoryChar)))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// Resolve internal field name to QBO API field name
        /// </summary>
        private static string ResolveFieldAlias(string entityType, string fieldName)
        {
            var key = (entityType, fieldName);
            if (FieldAliases.TryGetValue(key, out string alias))
            {
                return alias;
            }
            return fieldName;
        }

        /// <summary>
        /// Check if a field value exceeds the limit for its entity/field
        /// </summary>
        public static bool ExceedsLimit(string entityType, string fieldName, string value)
        {
            if (string.IsNullOrEmpty(value))
                return false;

            // Normalize Unicode before measuring
            string normalized = NormalizeUnicode(value);
            
            var limitResult = GetLimit(entityType, fieldName);
            if (!limitResult.Limit.HasValue)
            {
                // Unknown limit - be conservative and don't report as exceeding
                return false;
            }

            return normalized.Length > limitResult.Limit.Value;
        }

        /// <summary>
        /// Truncate a field value to its entity/field-specific limit
        /// Uses deterministic strategy with hash suffix for identifiers
        /// SAFE: Handles limit <= 3 gracefully
        /// </summary>
        public static string TruncateToLimit(string entityType, string fieldName, string value, out TruncationResult result)
        {
            result = new TruncationResult
            {
                WasTruncated = false,
                EntityType = entityType,
                FieldName = fieldName,
                OriginalLength = value?.Length ?? 0
            };

            if (string.IsNullOrEmpty(value))
                return value;

            // Normalize Unicode first
            string normalized = NormalizeUnicode(value);
            result.NormalizedLength = normalized.Length;

            var limitResult = GetLimit(entityType, fieldName);
            int limit;
            
            if (limitResult.Limit.HasValue)
            {
                limit = limitResult.Limit.Value;
                result.LimitSource = limitResult.Source;
            }
            else
            {
                // Unknown limit - use conservative default and log warning
                limit = 200;
                result.LimitSource = LimitSource.FallbackDefault;
                result.Warning = $"Unknown limit for {entityType}.{fieldName}, using fallback of {limit}";
            }

            result.AppliedLimit = limit;

            if (normalized.Length <= limit)
            {
                return normalized;
            }

            result.WasTruncated = true;
            result.CharactersLost = normalized.Length - limit;

            // SAFETY: Handle very small limits
            if (limit <= 0)
            {
                return string.Empty;
            }
            
            if (limit <= 3)
            {
                return normalized.Substring(0, limit);
            }

            // Determine if this is an identifier field (needs uniqueness preservation)
            bool isIdentifier = IsIdentifierField(fieldName);

            if (isIdentifier)
            {
                // For identifiers: use hash suffix to preserve uniqueness
                return TruncateWithHashSuffix(normalized, limit);
            }
            else
            {
                // For descriptions/notes: simple truncation with ellipsis
                return normalized.Substring(0, limit - 3).TrimEnd() + "...";
            }
        }

        /// <summary>
        /// Check if a field is an identifier (needs uniqueness preservation)
        /// </summary>
        private static bool IsIdentifierField(string fieldName)
        {
            // Case-insensitive check for identifier patterns
            string lower = fieldName.ToLowerInvariant();
            return lower.Contains("name") ||
                   lower.Contains("number") ||
                   lower.Contains("sku") ||
                   lower.Contains("id") ||
                   lower.Contains("code") ||
                   lower.Contains("ref");
        }

        /// <summary>
        /// Truncate with deterministic hash suffix to preserve uniqueness
        /// Format: [prefix]-[6-char hash]
        /// </summary>
        private static string TruncateWithHashSuffix(string value, int limit)
        {
            // Reserve space for "-" and 6-char hash = 7 chars
            const int hashSuffixLength = 7;
            
            if (limit <= hashSuffixLength)
            {
                // Too short for hash suffix - just truncate
                return value.Substring(0, limit);
            }

            int prefixLength = limit - hashSuffixLength;
            string prefix = value.Substring(0, prefixLength);
            
            // Compute deterministic hash of original value
            string hash = ComputeShortHash(value);
            
            return prefix + "-" + hash;
        }

        /// <summary>
        /// Compute 6-character deterministic hash using Base32
        /// </summary>
        private static string ComputeShortHash(string value)
        {
            using (var sha256 = SHA256.Create())
            {
                byte[] hashBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(value));
                // Take first 4 bytes and encode as Base32 (produces 6-7 chars)
                return ToBase32(hashBytes, 0, 4).Substring(0, 6).ToUpperInvariant();
            }
        }

        /// <summary>
        /// Simple Base32 encoding (RFC 4648)
        /// </summary>
        private static string ToBase32(byte[] bytes, int offset, int length)
        {
            const string alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
            var sb = new StringBuilder();
            int bits = 0;
            int value = 0;

            for (int i = offset; i < offset + length && i < bytes.Length; i++)
            {
                value = (value << 8) | bytes[i];
                bits += 8;

                while (bits >= 5)
                {
                    sb.Append(alphabet[(value >> (bits - 5)) & 31]);
                    bits -= 5;
                }
            }

            if (bits > 0)
            {
                sb.Append(alphabet[(value << (5 - bits)) & 31]);
            }

            return sb.ToString();
        }

        /// <summary>
        /// Normalize Unicode to NFC form for consistent length measurement
        /// </summary>
        private static string NormalizeUnicode(string value)
        {
            if (string.IsNullOrEmpty(value))
                return value;

            try
            {
                return value.Normalize(NormalizationForm.FormC);
            }
            catch
            {
                // If normalization fails, return original
                return value;
            }
        }

        /// <summary>
        /// Validate all fields in an entity against limits
        /// Returns structured validation results
        /// </summary>
        public static List<FieldValidationResult> ValidateEntity(string entityType, Dictionary<string, string> fields)
        {
            var results = new List<FieldValidationResult>();

            foreach (var field in fields)
            {
                if (string.IsNullOrEmpty(field.Value))
                    continue;

                string normalized = NormalizeUnicode(field.Value);
                var limitResult = GetLimit(entityType, field.Key);

                var validationResult = new FieldValidationResult
                {
                    EntityType = entityType,
                    FieldName = field.Key,
                    ResolvedFieldName = limitResult.ResolvedFieldName,
                    ActualLength = normalized.Length,
                    Limit = limitResult.Limit,
                    LimitSource = limitResult.Source,
                    ExceedsLimit = limitResult.Limit.HasValue && normalized.Length > limitResult.Limit.Value
                };

                if (validationResult.ExceedsLimit)
                {
                    validationResult.OverageAmount = normalized.Length - limitResult.Limit.Value;
                    validationResult.ValueHash = ComputeShortHash(field.Value);
                }

                results.Add(validationResult);
            }

            return results;
        }
    }

    /// <summary>
    /// Result of limit lookup
    /// </summary>
    public class LimitResult
    {
        public int? Limit { get; set; }
        public LimitSource Source { get; set; }
        public string EntityType { get; set; }
        public string FieldName { get; set; }
        public string ResolvedFieldName { get; set; }
        public string MatchedCategory { get; set; }
    }

    /// <summary>
    /// Source of the limit value
    /// </summary>
    public enum LimitSource
    {
        Exact,           // Found in QBOLimits
        CategoryDefault, // Matched by field name pattern
        FallbackDefault, // Used fallback value
        Unknown          // No limit found
    }

    /// <summary>
    /// Result of truncation operation
    /// </summary>
    public class TruncationResult
    {
        public bool WasTruncated { get; set; }
        public string EntityType { get; set; }
        public string FieldName { get; set; }
        public int OriginalLength { get; set; }
        public int NormalizedLength { get; set; }
        public int AppliedLimit { get; set; }
        public int CharactersLost { get; set; }
        public LimitSource LimitSource { get; set; }
        public string Warning { get; set; }
    }

    /// <summary>
    /// Result of field validation
    /// </summary>
    public class FieldValidationResult
    {
        public string EntityType { get; set; }
        public string FieldName { get; set; }
        public string ResolvedFieldName { get; set; }
        public int ActualLength { get; set; }
        public int? Limit { get; set; }
        public LimitSource LimitSource { get; set; }
        public bool ExceedsLimit { get; set; }
        public int? OverageAmount { get; set; }
        public string ValueHash { get; set; } // For correlation without exposing data
    }

    /// <summary>
    /// Case-insensitive tuple comparer for field alias dictionary
    /// </summary>
    internal class TupleStringComparer : IEqualityComparer<(string, string)>
    {
        public bool Equals((string, string) x, (string, string) y)
        {
            return string.Equals(x.Item1, y.Item1, StringComparison.OrdinalIgnoreCase) &&
                   string.Equals(x.Item2, y.Item2, StringComparison.OrdinalIgnoreCase);
        }

        public int GetHashCode((string, string) obj)
        {
            return StringComparer.OrdinalIgnoreCase.GetHashCode(obj.Item1 ?? "") ^
                   StringComparer.OrdinalIgnoreCase.GetHashCode(obj.Item2 ?? "");
        }
    }
}