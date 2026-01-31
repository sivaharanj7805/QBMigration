using System;

namespace QBDesktopExtractor
{
    /// <summary>
    /// FIX MED-16: Centralized constants to eliminate magic numbers throughout the codebase
    /// </summary>
    public static class Constants
    {
        /// <summary>
        /// Encryption-related constants
        /// </summary>
        public static class Encryption
        {
            public const string AlgorithmName = "AES-256-GCM-Chunked";
            public const int KeySizeBits = 256;
            public const int KeySizeBytes = KeySizeBits / 8;
            public const int NonceSizeBytes = 12;
            public const int TagSizeBytes = 16;
            public const int DefaultChunkSizeBytes = 64 * 1024; // 64KB
            public const int MaxChunkSizeBytes = 10 * 1024 * 1024; // 10MB
            public const string FileMagicHeader = "QBEX";
            public const ushort CurrentFileVersion = 2;
        }

        /// <summary>
        /// Upload-related constants
        /// </summary>
        public static class Upload
        {
            public const int DefaultChunkSizeKB = 512;
            public const int DefaultChunkedUploadThresholdMB = 50;
            public const int DefaultUploadTimeoutMinutes = 10;
            public const int MaxUploadTimeoutMinutes = 30;
            public const int DefaultChunkTimeoutSeconds = 120;
            public const int MultipartThresholdBytes = 100 * 1024 * 1024; // 100MB
            public const int S3PartSizeBytes = 5 * 1024 * 1024; // 5MB
        }

        /// <summary>
        /// Retry-related constants
        /// </summary>
        public static class Retry
        {
            public const int DefaultMaxAttempts = 3;
            public const int DefaultDelayMs = 1000;
            public const int DefaultMaxDelayMs = 60000;
            public const int MinDelayMs = 100;
            public const int MaxDelayMs = 300000; // 5 minutes
            public const int DefaultJitterPercent = 25;
            public const int MaxExponent = 20;
        }

        /// <summary>
        /// Session validation constants
        /// </summary>
        public static class Session
        {
            public const string SessionIdPrefix = "FB-";
            public const int TimestampLength = 14;
            public const int SuffixLength = 8;
            public const int ChecksumLength = 2;
            public const long MinTimestamp = 20200101000000;
            public const long MaxTimestamp = 20501231235959;
            public const int CacheDays = 7;
        }

        /// <summary>
        /// Buffer and memory constants
        /// </summary>
        public static class Buffer
        {
            public const int DefaultStreamBufferSize = 65536; // 64KB
            public const int HashDisplayLength = 16;
            public const int FingerprintDisplayLength = 12;
            public const long MinAvailableMemoryGB = 2;
        }

        /// <summary>
        /// Progress reporting constants
        /// </summary>
        public static class Progress
        {
            public const long ReportIntervalBytes = 5 * 1024 * 1024; // 5MB
            public const int ChunkReportInterval = 10;
        }

        /// <summary>
        /// File operation constants
        /// </summary>
        public static class FileOps
        {
            public const int SecureDeletePasses = 3;
            public const int TempFileCleanupHours = 1;
            public const string TempFilePrefix = "qbex_";
        }

        /// <summary>
        /// QODBC-related constants
        /// </summary>
        public static class QODBC
        {
            public const int DefaultCommandTimeoutSeconds = 300;
            public const int LargeQueryTimeoutSeconds = 600;
        }

        /// <summary>
        /// QuickBooks version constants
        /// </summary>
        public static class QuickBooks
        {
            public const double DefaultQBXMLVersion = 13.0;
            public const short MinQBXMLMajorVersion = 1;
            public const short MaxQBXMLMajorVersion = 16;
        }

        /// <summary>
        /// HTTP client constants
        /// </summary>
        public static class Http
        {
            public const int DefaultTimeoutSeconds = 30;
            public const string UserAgent = "QBExtractor/4.2";
            public const string ClientVersion = "4.2.0";
        }

        /// <summary>
        /// Known URLs
        /// </summary>
        public static class Urls
        {
            public const string ForensicBridge = "https://forensicbridge.ca";
            public const string ForensicBridgeNewProject = "https://forensicbridge.ca/dashboard/new-project";
            public const string IntuitDeveloperSDK = "https://developer.intuit.com/app/developer/qbdesktop/docs/get-started";
            public const string QODBCDownloads = "https://qodbc.com/qodbc-downloads/";
        }
    }
}
