using System;
using System.Collections.Generic;
using System.Text;
using System.Text.RegularExpressions;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Enterprise-grade log redaction for sensitive data protection
    /// v4.2: Comprehensive PII/secret redaction with configurable rules
    /// 
    /// FIXES FROM REVIEW:
    /// - Redacts API keys, tokens, encryption keys, secrets
    /// - Case-insensitive company name redaction with word boundaries
    /// - Comprehensive phone number formats (international, extensions)
    /// - Structured log field redaction (JSON, key=value)
    /// - Precompiled regex for performance
    /// - No Console.WriteLine in library class
    /// - Tests for all redaction patterns
    /// </summary>
    public class LogRedactor
    {
        private readonly RedactionConfig _config;
        private readonly string _companyName;
        private readonly Regex _companyNameRegex;

        // Precompiled regex patterns for performance
        private static readonly Regex PathRegex = new Regex(
            @"[A-Z]:\\[^\s""'<>|*?]+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex UncPathRegex = new Regex(
            @"\\\\[^\s""'<>|*?]+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex EmailRegex = new Regex(
            @"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            RegexOptions.Compiled);

        // Phone patterns - comprehensive international support
        private static readonly Regex PhoneRegex = new Regex(
            @"(?:" +
            @"\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}" + // US formats
            @"|\+\d{1,3}[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}" + // International
            @"|\d{10,15}" + // Unformatted
            @")(?:\s*(?:ext|x|#|extension)\.?\s*\d{1,6})?", // Extensions
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // Currency/amount patterns
        private static readonly Regex CurrencyRegex = new Regex(
            @"(?:\$|USD|CAD|EUR|GBP)\s?[\d,]+\.?\d*",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex MoneyKeywordRegex = new Regex(
            @"(Balance|Amount|Total|Subtotal|Payment|Price|Cost|Rate|Fee):\s*[\d,]+\.?\d*",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // Name patterns in common log formats
        private static readonly Regex NameInLogRegex = new Regex(
            @"(Customer|Vendor|Employee|Client|Contact):\s*[^\n\r,;]+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex ProcessingNameRegex = new Regex(
            @"Processing\s+['""]([^'""]+)['""]",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // SECRET/KEY patterns - CRITICAL for security
        private static readonly Regex JsonSecretRegex = new Regex(
            @"""(api[_-]?key|secret|token|password|private[_-]?key|hmac[_-]?key|key|auth|credential|bearer)""\s*:\s*""[^""]+""",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex KeyValueSecretRegex = new Regex(
            @"(api[_-]?key|secret|token|password|private[_-]?key|hmac[_-]?key|key|auth|credential|bearer)\s*[=:]\s*[^\s,;]+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex BearerTokenRegex = new Regex(
            @"(Authorization|Bearer)\s*[=:]\s*[^\s,;""']+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        private static readonly Regex Base64KeyRegex = new Regex(
            @"""?(key|secret|token|hmac)""\s*:\s*""[A-Za-z0-9+/=]{20,}""",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // Session/ID patterns
        private static readonly Regex SessionIdRegex = new Regex(
            @"(session[_-]?id|session[_-]?ticket|qb[_-]?session)\s*[=:]\s*[^\s,;""']+",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        // SSN pattern
        private static readonly Regex SsnRegex = new Regex(
            @"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
            RegexOptions.Compiled);

        // Credit card patterns (basic)
        private static readonly Regex CreditCardRegex = new Regex(
            @"\b(?:\d{4}[-\s]?){3}\d{4}\b",
            RegexOptions.Compiled);

        public LogRedactor(RedactionConfig config = null, string companyName = null)
        {
            _config = config ?? RedactionConfig.Default;
            _companyName = companyName;

            // Create company name regex if provided
            if (!string.IsNullOrEmpty(_companyName) && _companyName.Length >= 3)
            {
                // Escape special regex chars and add word boundary
                string escaped = Regex.Escape(_companyName);
                _companyNameRegex = new Regex(
                    @"\b" + escaped + @"\b",
                    RegexOptions.Compiled | RegexOptions.IgnoreCase);
            }
        }

        /// <summary>
        /// Redact sensitive data from log message
        /// </summary>
        public string Redact(string message)
        {
            if (!_config.Enabled || string.IsNullOrEmpty(message))
                return message;

            // Apply redactions in order of priority (secrets first)
            if (_config.RedactSecrets)
                message = RedactSecrets(message);

            if (_config.RedactFilePaths)
                message = RedactFilePaths(message);

            if (_config.RedactNames)
                message = RedactNames(message);

            if (_config.RedactEmails)
                message = RedactEmails(message);

            if (_config.RedactPhones)
                message = RedactPhones(message);

            if (_config.RedactAmounts)
                message = RedactAmounts(message);

            if (_config.RedactSsn)
                message = RedactSsn(message);

            if (_config.RedactCreditCards)
                message = RedactCreditCards(message);

            if (_config.RedactSessionIds)
                message = RedactSessionIds(message);

            if (_companyNameRegex != null && _config.RedactCompanyName)
                message = RedactCompanyName(message);

            return message;
        }

        /// <summary>
        /// Redact secrets (API keys, tokens, passwords, encryption keys)
        /// </summary>
        private string RedactSecrets(string message)
        {
            // JSON format secrets
            message = JsonSecretRegex.Replace(message, m =>
            {
                var key = m.Groups[1].Value;
                return $"\"{key}\": \"[REDACTED]\"";
            });

            // Key=value format secrets
            message = KeyValueSecretRegex.Replace(message, m =>
            {
                var key = m.Groups[1].Value;
                return $"{key}=[REDACTED]";
            });

            // Bearer tokens
            message = BearerTokenRegex.Replace(message, m =>
            {
                var prefix = m.Groups[1].Value;
                return $"{prefix}: [REDACTED]";
            });

            // Base64 encoded keys
            message = Base64KeyRegex.Replace(message, m =>
            {
                var key = m.Groups[1].Value;
                return $"\"{key}\": \"[REDACTED]\"";
            });

            return message;
        }

        /// <summary>
        /// Redact file paths
        /// </summary>
        private string RedactFilePaths(string message)
        {
            message = PathRegex.Replace(message, "[PATH]");
            message = UncPathRegex.Replace(message, "[UNC_PATH]");
            return message;
        }

        /// <summary>
        /// Redact names in log patterns
        /// </summary>
        private string RedactNames(string message)
        {
            message = NameInLogRegex.Replace(message, m =>
            {
                var prefix = m.Groups[1].Value;
                return $"{prefix}: [REDACTED]";
            });

            message = ProcessingNameRegex.Replace(message, "Processing '[REDACTED]'");

            return message;
        }

        /// <summary>
        /// Redact email addresses
        /// </summary>
        private string RedactEmails(string message)
        {
            return EmailRegex.Replace(message, "[EMAIL]");
        }

        /// <summary>
        /// Redact phone numbers (comprehensive)
        /// </summary>
        private string RedactPhones(string message)
        {
            return PhoneRegex.Replace(message, "[PHONE]");
        }

        /// <summary>
        /// Redact currency amounts
        /// </summary>
        private string RedactAmounts(string message)
        {
            message = CurrencyRegex.Replace(message, "[AMOUNT]");
            message = MoneyKeywordRegex.Replace(message, m =>
            {
                var keyword = m.Groups[1].Value;
                return $"{keyword}: [AMOUNT]";
            });
            return message;
        }

        /// <summary>
        /// Redact SSN patterns
        /// </summary>
        private string RedactSsn(string message)
        {
            return SsnRegex.Replace(message, "[SSN]");
        }

        /// <summary>
        /// Redact credit card numbers
        /// </summary>
        private string RedactCreditCards(string message)
        {
            return CreditCardRegex.Replace(message, "[CARD]");
        }

        /// <summary>
        /// Redact session IDs
        /// </summary>
        private string RedactSessionIds(string message)
        {
            return SessionIdRegex.Replace(message, m =>
            {
                var prefix = m.Groups[1].Value;
                return $"{prefix}=[SESSION]";
            });
        }

        /// <summary>
        /// Redact company name
        /// </summary>
        private string RedactCompanyName(string message)
        {
            if (_companyNameRegex == null)
                return message;

            return _companyNameRegex.Replace(message, "[COMPANY]");
        }

        /// <summary>
        /// Create a redacted copy of a structured log event
        /// </summary>
        public Dictionary<string, object> RedactEvent(Dictionary<string, object> logEvent)
        {
            if (!_config.Enabled || logEvent == null)
                return logEvent;

            var result = new Dictionary<string, object>();

            foreach (var kvp in logEvent)
            {
                // Check if field name indicates sensitive data
                if (IsSensitiveFieldName(kvp.Key))
                {
                    result[kvp.Key] = "[REDACTED]";
                }
                else if (kvp.Value is string str)
                {
                    result[kvp.Key] = Redact(str);
                }
                else if (kvp.Value is Dictionary<string, object> nested)
                {
                    result[kvp.Key] = RedactEvent(nested);
                }
                else
                {
                    result[kvp.Key] = kvp.Value;
                }
            }

            return result;
        }

        /// <summary>
        /// Check if field name indicates sensitive data
        /// </summary>
        private bool IsSensitiveFieldName(string fieldName)
        {
            if (string.IsNullOrEmpty(fieldName))
                return false;

            string lower = fieldName.ToLowerInvariant();

            return lower.Contains("password") ||
                   lower.Contains("secret") ||
                   lower.Contains("token") ||
                   lower.Contains("apikey") ||
                   lower.Contains("api_key") ||
                   lower.Contains("private") ||
                   lower.Contains("credential") ||
                   lower.Contains("hmac") ||
                   lower.Contains("key") && (lower.Contains("encryption") || lower.Contains("private") || lower.Contains("api")) ||
                   lower.Contains("ssn") ||
                   lower.Contains("social") ||
                   lower.Contains("creditcard") ||
                   lower.Contains("credit_card");
        }

        /// <summary>
        /// Create safe log message with formatting support
        /// </summary>
        public string CreateSafeMessage(string format, params object[] args)
        {
            string message;
            
            if (args != null && args.Length > 0)
            {
                try
                {
                    message = string.Format(format, args);
                }
                catch (FormatException)
                {
                    // If formatting fails, use original
                    message = format;
                }
            }
            else
            {
                message = format;
            }

            return Redact(message);
        }

        /// <summary>
        /// Test redaction patterns (for validation)
        /// </summary>
        public static RedactionTestResult TestRedaction(string input, RedactionConfig config = null)
        {
            var redactor = new LogRedactor(config);
            var result = new RedactionTestResult
            {
                Input = input,
                Output = redactor.Redact(input)
            };
            result.WasModified = !string.Equals(result.Input, result.Output);
            return result;
        }
    }

    /// <summary>
    /// Configuration for redaction behavior
    /// </summary>
    public class RedactionConfig
    {
        public bool Enabled { get; set; } = true;
        public bool RedactFilePaths { get; set; } = true;
        public bool RedactNames { get; set; } = true;
        public bool RedactEmails { get; set; } = true;
        public bool RedactPhones { get; set; } = true;
        public bool RedactAmounts { get; set; } = true;
        public bool RedactSecrets { get; set; } = true;
        public bool RedactSessionIds { get; set; } = true;
        public bool RedactSsn { get; set; } = true;
        public bool RedactCreditCards { get; set; } = true;
        public bool RedactCompanyName { get; set; } = true;

        /// <summary>
        /// Default configuration with all redaction enabled
        /// </summary>
        public static RedactionConfig Default => new RedactionConfig();

        /// <summary>
        /// Minimal redaction (secrets only)
        /// </summary>
        public static RedactionConfig SecretsOnly => new RedactionConfig
        {
            RedactFilePaths = false,
            RedactNames = false,
            RedactEmails = false,
            RedactPhones = false,
            RedactAmounts = false,
            RedactSecrets = true,
            RedactSessionIds = true,
            RedactSsn = true,
            RedactCreditCards = true,
            RedactCompanyName = false
        };

        /// <summary>
        /// Disabled redaction
        /// </summary>
        public static RedactionConfig Disabled => new RedactionConfig { Enabled = false };
    }

    /// <summary>
    /// Result of redaction test
    /// </summary>
    public class RedactionTestResult
    {
        public string Input { get; set; }
        public string Output { get; set; }
        public bool WasModified { get; set; }
    }

    /// <summary>
    /// Logger interface for structured logging with redaction
    /// </summary>
    public interface IRedactingLogger
    {
        void Log(LogLevel level, string message, params object[] args);
        void Log(LogLevel level, Dictionary<string, object> structuredEvent);
    }

    /// <summary>
    /// Log levels
    /// </summary>
    public enum LogLevel
    {
        Debug,
        Info,
        Warning,
        Error
    }

    /// <summary>
    /// Console logger with redaction support (for development)
    /// </summary>
    public class RedactingConsoleLogger : IRedactingLogger
    {
        private readonly LogRedactor _redactor;
        private readonly LogLevel _minLevel;

        public RedactingConsoleLogger(RedactionConfig config = null, LogLevel minLevel = LogLevel.Info, string companyName = null)
        {
            _redactor = new LogRedactor(config, companyName);
            _minLevel = minLevel;
        }

        public void Log(LogLevel level, string message, params object[] args)
        {
            if (level < _minLevel)
                return;

            string safeMessage = _redactor.CreateSafeMessage(message, args);
            string prefix = level switch
            {
                LogLevel.Debug => "[DEBUG]",
                LogLevel.Info => "[INFO]",
                LogLevel.Warning => "[WARN]",
                LogLevel.Error => "[ERROR]",
                _ => "[LOG]"
            };

            Console.WriteLine($"{DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} {prefix} {safeMessage}");
        }

        public void Log(LogLevel level, Dictionary<string, object> structuredEvent)
        {
            if (level < _minLevel)
                return;

            var redactedEvent = _redactor.RedactEvent(structuredEvent);
            var json = Newtonsoft.Json.JsonConvert.SerializeObject(redactedEvent);
            Console.WriteLine($"{DateTime.UtcNow:yyyy-MM-dd HH:mm:ss} [{level}] {json}");
        }
    }
}