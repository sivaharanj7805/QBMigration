using System;

namespace QBMigrationLauncher
{
    /// <summary>
    /// FIX LOW: Centralized constants to eliminate magic numbers throughout the codebase.
    /// Provides consistent values for timeouts, limits, and configuration defaults.
    /// </summary>
    public static class Constants
    {
        /// <summary>
        /// Login and authentication constants
        /// </summary>
        public static class Auth
        {
            /// <summary>Maximum email length per RFC 5321</summary>
            public const int MaxEmailLength = 254;

            /// <summary>Maximum local part length per RFC 5321</summary>
            public const int MaxEmailLocalPartLength = 64;

            /// <summary>Maximum password length</summary>
            public const int MaxPasswordLength = 128;

            /// <summary>Maximum failed login attempts before lockout</summary>
            public const int MaxFailedAttempts = 5;

            /// <summary>Lockout duration after max failed attempts</summary>
            public static readonly TimeSpan LockoutDuration = TimeSpan.FromMinutes(5);

            /// <summary>Default session expiry time</summary>
            public static readonly TimeSpan DefaultSessionExpiry = TimeSpan.FromHours(24);
        }

        /// <summary>
        /// HTTP and network timeouts
        /// </summary>
        public static class Timeouts
        {
            /// <summary>Default HTTP request timeout</summary>
            public static readonly TimeSpan HttpRequest = TimeSpan.FromSeconds(30);

            /// <summary>UI loading indicator timeout</summary>
            public static readonly TimeSpan UiLoading = TimeSpan.FromSeconds(30);

            /// <summary>Process execution timeout</summary>
            public static readonly TimeSpan ProcessExecution = TimeSpan.FromMinutes(30);

            /// <summary>Health check timeout</summary>
            public static readonly TimeSpan HealthCheck = TimeSpan.FromSeconds(60);
        }

        /// <summary>
        /// HTTP client configuration
        /// </summary>
        public static class HttpClient
        {
            /// <summary>Connection pool lifetime</summary>
            public static readonly TimeSpan PooledConnectionLifetime = TimeSpan.FromMinutes(5);

            /// <summary>Connection pool idle timeout</summary>
            public static readonly TimeSpan PooledConnectionIdleTimeout = TimeSpan.FromMinutes(2);

            /// <summary>Maximum connections per server</summary>
            public const int MaxConnectionsPerServer = 10;
        }

        /// <summary>
        /// Log buffer and UI constants
        /// </summary>
        public static class Logging
        {
            /// <summary>Maximum log lines to keep in circular buffer</summary>
            public const int MaxLogBufferLines = 1000;

            /// <summary>Log prefix for info messages</summary>
            public const string InfoPrefix = "[INFO]";

            /// <summary>Log prefix for warning messages</summary>
            public const string WarnPrefix = "[WARN]";

            /// <summary>Log prefix for error messages</summary>
            public const string ErrorPrefix = "[ERROR]";

            /// <summary>Log prefix for debug messages</summary>
            public const string DebugPrefix = "[DEBUG]";
        }

        /// <summary>
        /// File operation constants
        /// </summary>
        public static class FileOps
        {
            /// <summary>Buffer size for file operations</summary>
            public const int BufferSize = 8192;

            /// <summary>QuickBooks company file extension</summary>
            public const string QbwExtension = ".qbw";

            /// <summary>NDJSON file extension</summary>
            public const string NdjsonExtension = ".ndjson";

            /// <summary>JSON file extension</summary>
            public const string JsonExtension = ".json";
        }

        /// <summary>
        /// Migration constants
        /// </summary>
        public static class Migration
        {
            /// <summary>Migration ID length</summary>
            public const int MigrationIdLength = 12;

            /// <summary>Default output directory name</summary>
            public const string OutputDirectoryName = "QBMigration";

            /// <summary>Reports subdirectory name</summary>
            public const string ReportsDirectoryName = "Reports";

            /// <summary>Extracted data subdirectory name</summary>
            public const string ExtractedDirectoryName = "extracted";

            /// <summary>Run manifest filename</summary>
            public const string ManifestFileName = "run_manifest.json";

            /// <summary>Errors file name</summary>
            public const string ErrorsFileName = "errors.ndjson";
        }

        /// <summary>
        /// URL constants
        /// </summary>
        public static class Urls
        {
            /// <summary>Default API base URL</summary>
            public const string DefaultApiBaseUrl = "https://api.forensicbridge.ca";

            /// <summary>Registration URL</summary>
            public const string RegistrationUrl = "https://app.forensicbridge.ca/register";

            /// <summary>Pricing URL</summary>
            public const string PricingUrl = "https://forensicbridge.ca/pricing";
        }

        /// <summary>
        /// Status messages
        /// </summary>
        public static class Messages
        {
            /// <summary>Ready status message</summary>
            public const string Ready = "Ready to start.";

            /// <summary>Searching status message</summary>
            public const string SearchingQuickBooks = "Searching for QuickBooks...";

            /// <summary>License validation message</summary>
            public const string ValidatingLicense = "Validating license...";

            /// <summary>Migration complete message</summary>
            public const string MigrationComplete = "Migration Complete!";

            /// <summary>Health check running message</summary>
            public const string RunningHealthCheck = "Running health check...";
        }
    }
}
