#if USE_QBFC

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Threading;
using QBFC16Lib;

namespace QBDesktopExtractor
{
    // =================================================================
    // NULL-SAFE GetAt() HELPER METHODS
    // CRITICAL FIX: Prevents NullReferenceException and ArgumentOutOfRangeException
    // when accessing QBFC list elements
    // =================================================================

    /// <summary>
    /// Static helpers for safe list access in QBFC operations
    /// </summary>
    public static class QBFCSafeAccessHelpers
    {
        /// <summary>
        /// Safely get a response from ResponseList, returning null if index out of range
        /// </summary>
        public static IResponse SafeGetResponse(this IResponseList responseList, int index)
        {
            if (responseList == null) return null;
            if (index < 0 || index >= responseList.Count) return null;
            return responseList.GetAt(index);
        }

        /// <summary>
        /// Safely get the first response, returning null if list is empty
        /// </summary>
        public static IResponse SafeGetFirstResponse(this IResponseList responseList)
        {
            return SafeGetResponse(responseList, 0);
        }

        /// <summary>
        /// Check if response list has items and first response is successful (StatusCode == 0)
        /// </summary>
        public static bool HasSuccessfulResponse(this IResponseList responseList)
        {
            if (responseList == null || responseList.Count == 0) return false;
            var first = responseList.GetAt(0);
            return first != null && first.StatusCode == 0;
        }

        /// <summary>
        /// Get response or throw with descriptive error message
        /// </summary>
        public static IResponse GetResponseOrThrow(this IResponseList responseList, int index, string context)
        {
            if (responseList == null)
                throw new InvalidOperationException($"ResponseList is null ({context})");
            if (index < 0 || index >= responseList.Count)
                throw new InvalidOperationException($"ResponseList index {index} out of range (Count: {responseList.Count}) ({context})");
            return responseList.GetAt(index);
        }
    }

    /// <summary>
    /// Query capability result for tracking unsupported features
    /// </summary>
    public class QueryCapabilityResult
    {
        public bool Success { get; set; }
        public string FeatureName { get; set; }
        public string QueryType { get; set; }
        public string Reason { get; set; }
        public DateTime Timestamp { get; set; } = DateTime.UtcNow;
    }

    /// <summary>
    /// Defines what features each query type supports
    /// </summary>
    public class QueryCapabilities
    {
        public bool SupportsModifiedDateFilter { get; set; }
        public bool SupportsMaxReturned { get; set; }
        public bool SupportsIterator { get; set; }
        public string QueryType { get; set; }
    }

    /// <summary>
    /// Structured progress event for extraction
    /// </summary>
    public class ExtractionProgress
    {
        public string EntityType { get; set; }
        public int CurrentPage { get; set; }
        public int TotalRecordsExtracted { get; set; }
        public int RemainingRecords { get; set; }
        public TimeSpan Elapsed { get; set; }
        public TimeSpan? EstimatedRemaining { get; set; }
        public int CurrentBatchSize { get; set; }
        public long LastRequestTimeMs { get; set; }
    }

    /// <summary>
    /// Retry policy configuration
    /// </summary>
    public class RetryPolicy
    {
        public int MaxRetries { get; set; } = 3;
        public int BaseDelayMs { get; set; } = 1000;
        public int MaxDelayMs { get; set; } = 30000;
        public bool UseExponentialBackoff { get; set; } = true;
        public HashSet<int> RetryableStatusCodes { get; set; } = new HashSet<int> { -10, -11, 3180, 3100 };
    }

    /// <summary>
    /// ENTERPRISE-GRADE Iterator Helper (v4.3)
    /// 
    /// v4.3 IMPROVEMENTS:
    /// - RETRY POLICY: Configurable retry with exponential backoff
    /// - CANCELLATION: CancellationToken support for graceful abort
    /// - MAX DURATION: Per-entity extraction timeout
    /// - STRUCTURED PROGRESS: Event-based progress reporting
    /// - FAILURE BOUNDARY: Page context recorded for resume
    /// - INTERFACE-BASED: Uses IQBSessionManager for testing
    /// 
    /// Prior features:
    /// - Capability tracking, adaptive batching, timeout prevention
    /// - Progress heartbeat, robust cleanup, incremental sync
    /// </summary>
    public class QBIteratorHelper
    {
        private readonly IQBSessionManager _sessionManager;
        private readonly IRedactingLogger _logger;

        // Thread-safe random for jitter calculations
        private static readonly ThreadLocal<Random> _threadLocalRandom =
            new ThreadLocal<Random>(() => new Random(Guid.NewGuid().GetHashCode()));

        // Configuration
        public RetryPolicy RetryPolicy { get; set; } = new RetryPolicy();
        public TimeSpan? MaxDurationPerEntity { get; set; } = TimeSpan.FromMinutes(30);

        // Progress event
        public event Action<ExtractionProgress> OnProgress;

        // Adaptive batching parameters
        private const int MIN_BATCH_SIZE = 20;
        private const int MAX_BATCH_SIZE = 500;
        private const int DEFAULT_BATCH_SIZE = 100;
        private const int TARGET_REQUEST_TIME_MS = 5000; // Target 5 seconds per request

        // CRITICAL: Incremental sync support
        public DateTime? IncrementalFromDate { get; set; }

        // Track capability warnings for metadata
        public List<QueryCapabilityResult> CapabilityWarnings { get; private set; } = new List<QueryCapabilityResult>();

        // Known capabilities per query type
        private static readonly Dictionary<string, QueryCapabilities> KnownCapabilities = new Dictionary<string, QueryCapabilities>
        {
            ["AccountQuery"] = new QueryCapabilities 
            { 
                QueryType = "AccountQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["CustomerQuery"] = new QueryCapabilities 
            { 
                QueryType = "CustomerQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["VendorQuery"] = new QueryCapabilities 
            { 
                QueryType = "VendorQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["EmployeeQuery"] = new QueryCapabilities 
            { 
                QueryType = "EmployeeQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["ItemQuery"] = new QueryCapabilities 
            { 
                QueryType = "ItemQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["InvoiceQuery"] = new QueryCapabilities 
            { 
                QueryType = "InvoiceQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["BillQuery"] = new QueryCapabilities 
            { 
                QueryType = "BillQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            ["CheckQuery"] = new QueryCapabilities 
            { 
                QueryType = "CheckQuery",
                SupportsModifiedDateFilter = true,
                SupportsMaxReturned = true,
                SupportsIterator = true
            },
            // Queries with limited support
            ["CompanyQuery"] = new QueryCapabilities 
            { 
                QueryType = "CompanyQuery",
                SupportsModifiedDateFilter = false,  // Company info doesn't support date filters
                SupportsMaxReturned = false,
                SupportsIterator = false
            },
            ["PreferencesQuery"] = new QueryCapabilities 
            { 
                QueryType = "PreferencesQuery",
                SupportsModifiedDateFilter = false,
                SupportsMaxReturned = false,
                SupportsIterator = false
            }
        };

        // Iterator-supporting query types
        private static readonly HashSet<string> IteratorSupportedQueries = new HashSet<string>
        {
            "AccountQuery", "CustomerQuery", "VendorQuery", "EmployeeQuery", "ItemQuery",
            "InvoiceQuery", "BillQuery", "CheckQuery", "SalesReceiptQuery", "CreditMemoQuery",
            "PurchaseOrderQuery", "SalesOrderQuery", "EstimateQuery", "JournalEntryQuery",
            "DepositQuery", "ChargeQuery", "CreditCardChargeQuery", "CreditCardCreditQuery"
        };

        public QBIteratorHelper(IQBSessionManager sessionManager, IRedactingLogger logger = null)
        {
            _sessionManager = sessionManager ?? throw new ArgumentNullException(nameof(sessionManager));
            _logger = logger;
        }

        /// <summary>
        /// Legacy constructor for backwards compatibility
        /// </summary>
        public QBIteratorHelper(QBSessionManager sessionManager) 
            : this((IQBSessionManager)sessionManager, null) { }
        
        /// <summary>
        /// Set the date for incremental sync
        /// </summary>
        public void SetIncrementalSyncDate(DateTime? fromDate)
        {
            IncrementalFromDate = fromDate;
        }

        /// <summary>
        /// Execute a QBFC request with retry logic
        /// Uses exponential backoff for retryable errors
        /// </summary>
        private IMsgSetResponse DoRequestsWithRetry(IMsgSetRequest request, string context)
        {
            int attempt = 0;
            Exception lastException = null;

            while (attempt < RetryPolicy.MaxRetries)
            {
                try
                {
                    return _sessionManager.DoRequests(request);
                }
                catch (Exception ex)
                {
                    lastException = ex;
                    attempt++;

                    // Check if error is retryable
                    bool isRetryable = IsRetryableError(ex);
                    
                    if (!isRetryable || attempt >= RetryPolicy.MaxRetries)
                    {
                        _logger?.Log(LogLevel.Error, "{0}: Failed after {1} attempts: {2}", 
                            context, attempt, ex.Message);
                        throw;
                    }

                    // Calculate delay with exponential backoff
                    int delay = CalculateRetryDelay(attempt);
                    
                    _logger?.Log(LogLevel.Warning, "{0}: Attempt {1} failed, retrying in {2}ms: {3}", 
                        context, attempt, delay, ex.Message);
                    
                    System.Threading.Thread.Sleep(delay);
                }
            }

            throw lastException ?? new Exception($"{context}: Failed after {attempt} retries");
        }

        /// <summary>
        /// Check if an error is retryable
        /// </summary>
        private bool IsRetryableError(Exception ex)
        {
            // Check for QBFC status codes in exception message
            string msg = ex.Message.ToLowerInvariant();
            
            // Transient errors that should be retried
            if (msg.Contains("busy") || 
                msg.Contains("timeout") || 
                msg.Contains("connection") ||
                msg.Contains("session") ||
                msg.Contains("lock"))
            {
                return true;
            }

            // Check for known retryable status codes
            foreach (int code in RetryPolicy.RetryableStatusCodes)
            {
                if (msg.Contains($"code: {code}") || msg.Contains($"code:{code}"))
                {
                    return true;
                }
            }

            return false;
        }

        /// <summary>
        /// Calculate retry delay with exponential backoff and jitter
        /// Thread-safe with overflow protection
        /// </summary>
        private int CalculateRetryDelay(int attempt)
        {
            if (!RetryPolicy.UseExponentialBackoff)
            {
                return RetryPolicy.BaseDelayMs;
            }

            // Exponential backoff: baseDelay * 2^(attempt-1) with overflow protection
            // Cap exponent to prevent overflow (2^30 is max safe for int multiplication)
            int safeExponent = Math.Min(attempt - 1, 30);
            long delayLong = (long)RetryPolicy.BaseDelayMs * (1L << safeExponent);

            // Cap at max delay before converting to int
            delayLong = Math.Min(delayLong, RetryPolicy.MaxDelayMs);
            int delay = (int)delayLong;

            // Add jitter (10-30% random variation) using thread-safe Random
            double jitter = 1.0 + (_threadLocalRandom.Value.NextDouble() * 0.2);
            delay = (int)(delay * jitter);

            // Final cap at max delay
            return Math.Min(delay, RetryPolicy.MaxDelayMs);
        }


        /// <summary>
        /// Extract records using iterator pattern with ADAPTIVE batching
        /// Supports cancellation, retry policy, and max duration timeout
        /// </summary>
        public List<T> ExtractWithIterator<T>(
            Func<IMsgSetRequest, object> queryAppender,
            Func<object, int, T> recordParser,
            string recordTypeName,
            int initialBatchSize = DEFAULT_BATCH_SIZE,
            Action<List<T>, int> onBatchComplete = null,
            CancellationToken cancellationToken = default)
        {
            var allRecords = new List<T>();
            string iteratorID = null;
            int totalRecords = 0;
            int batchNumber = 0;
            int currentBatchSize = initialBatchSize;
            
            // Performance tracking for adaptive batching
            var stopwatch = new Stopwatch();

            try
            {
                // FIRST REQUEST - Start iterator
                IMsgSetRequest request = _sessionManager.CreateMsgSetRequest();
                object query = queryAppender(request);
                
                // CRITICAL: Add incremental sync filter if enabled
                if (IncrementalFromDate.HasValue)
                {
                    string queryType = GetQueryType(query);
                    if (KnownCapabilities.ContainsKey(queryType) && 
                        KnownCapabilities[queryType].SupportsModifiedDateFilter)
                    {
                        try
                        {
                            SetModifiedDateFilter(query, IncrementalFromDate.Value);
                            Console.WriteLine($"      Incremental sync: Only extracting {recordTypeName} modified since {IncrementalFromDate:yyyy-MM-dd}");
                        }
                        catch (Exception ex)
                        {
                            // FIXED: Track capability failure, don't silently swallow
                            var warning = new QueryCapabilityResult
                            {
                                Success = false,
                                FeatureName = "ModifiedDateFilter",
                                QueryType = queryType,
                                Reason = ex.Message
                            };
                            CapabilityWarnings.Add(warning);
                            Console.WriteLine($"⚠ {queryType} ModifiedDateFilter failed (first request): {ex.Message}");
                        }
                    }
                    else
                    {
                        Console.WriteLine($"  Note: {queryType} doesn't support ModifiedDateFilter (incremental sync disabled for this entity)");
                    }
                }
                
                // Set iterator to START with initial batch size
                SetIteratorProperty(query, "iterator", ENiteratorType.itStart);
                SetIteratorProperty(query, "iteratorID", "");
                SetMaxReturned(query, currentBatchSize);
                
                // Track request time
                stopwatch.Start();
                IMsgSetResponse response = DoRequestsWithRetry(request, $"{recordTypeName} initial request");
                stopwatch.Stop();
                long requestTimeMs = stopwatch.ElapsedMilliseconds;
                
                IResponse resp = response.ResponseList.GetAt(0);

                // Check for errors
                if (resp.StatusCode != 0)
                {
                    if (resp.StatusCode == 1) // No records found
                    {
                        Console.WriteLine($"  ℹ No {recordTypeName} found");
                        return allRecords;
                    }
                    
                    throw new Exception($"{recordTypeName} query failed: {resp.StatusMessage} (Code: {resp.StatusCode})");
                }

                // Get iterator metadata
                int remainingCount = resp.iteratorRemainingCount;
                iteratorID = resp.iteratorID;
                batchNumber++;

                // Process first batch
                List<T> batch = ProcessResponseBatch(resp, recordParser, recordTypeName);
                allRecords.AddRange(batch);
                totalRecords += batch.Count;
                
                Console.WriteLine($"  Batch {batchNumber}: {batch.Count} records (Remaining: {remainingCount}, Time: {requestTimeMs}ms, Size: {currentBatchSize})");
                onBatchComplete?.Invoke(batch, batchNumber);

                // ADAPTIVE BATCHING: Adjust batch size based on performance
                currentBatchSize = CalculateOptimalBatchSize(
                    currentBatchSize, 
                    requestTimeMs, 
                    batch.Count,
                    recordTypeName);

                // CONTINUE REQUESTS - Process remaining batches
                DateTime lastHeartbeat = DateTime.Now;
                var entityStopwatch = Stopwatch.StartNew();
                
                while (remainingCount > 0)
                {
                    // Check for cancellation
                    cancellationToken.ThrowIfCancellationRequested();
                    
                    // Check max duration
                    if (MaxDurationPerEntity.HasValue && entityStopwatch.Elapsed > MaxDurationPerEntity.Value)
                    {
                        _logger?.Log(LogLevel.Warning, "Max duration exceeded for {0}, stopping at {1} records", recordTypeName, totalRecords);
                        break;
                    }
                    
                    request = _sessionManager.CreateMsgSetRequest();
                    query = queryAppender(request);
                    
                    // CRITICAL: Add incremental sync filter to continuation requests
                    if (IncrementalFromDate.HasValue)
                    {
                        string queryType = GetQueryType(query);
                        if (KnownCapabilities.ContainsKey(queryType) && 
                            KnownCapabilities[queryType].SupportsModifiedDateFilter)
                        {
                            try
                            {
                                SetModifiedDateFilter(query, IncrementalFromDate.Value);
                            }
                            catch (Exception ex)
                            {
                                var warning = new QueryCapabilityResult
                                {
                                    Success = false,
                                    FeatureName = "ModifiedDateFilter",
                                    QueryType = queryType,
                                    Reason = ex.Message
                                };
                                CapabilityWarnings.Add(warning);
                                Console.WriteLine($"⚠ {queryType} ModifiedDateFilter failed: {ex.Message}");
                            }
                        }
                        else
                        {
                            Console.WriteLine($"  Note: {queryType} doesn't support ModifiedDateFilter (skipping)");
                        }
                    }
                    
                    // Set iterator to CONTINUE with adaptive batch size
                    SetIteratorProperty(query, "iterator", ENiteratorType.itContinue);
                    SetIteratorProperty(query, "iteratorID", iteratorID);
                    SetMaxReturned(query, currentBatchSize);

                    // Track request time
                    stopwatch.Restart();
                    response = DoRequestsWithRetry(request, $"{recordTypeName} batch {batchNumber + 1}");
                    stopwatch.Stop();
                    requestTimeMs = stopwatch.ElapsedMilliseconds;

                    resp = response.ResponseList.GetAt(0);

                    if (resp.StatusCode != 0)
                    {
                        throw new Exception($"{recordTypeName} iterator failed at record {totalRecords}: {resp.StatusMessage}");
                    }

                    remainingCount = resp.iteratorRemainingCount;
                    batchNumber++;

                    batch = ProcessResponseBatch(resp, recordParser, recordTypeName);
                    allRecords.AddRange(batch);
                    totalRecords += batch.Count;
                    
                    // Show progress
                    Console.WriteLine($"  Batch {batchNumber}: {batch.Count} records (Remaining: {remainingCount}, Time: {requestTimeMs}ms, Size: {currentBatchSize})");
                    onBatchComplete?.Invoke(batch, batchNumber);

                    // Adaptive batching adjustment
                    currentBatchSize = CalculateOptimalBatchSize(
                        currentBatchSize, 
                        requestTimeMs, 
                        batch.Count,
                        recordTypeName);

                    // Emit structured progress event
                    var progress = new ExtractionProgress
                    {
                        EntityType = recordTypeName,
                        CurrentPage = batchNumber,
                        TotalRecordsExtracted = totalRecords,
                        RemainingRecords = remainingCount,
                        Elapsed = entityStopwatch.Elapsed,
                        CurrentBatchSize = currentBatchSize,
                        LastRequestTimeMs = requestTimeMs
                    };
                    OnProgress?.Invoke(progress);

                    // HEARTBEAT: Show progress every 10 seconds to prove app hasn't frozen
                    if ((DateTime.Now - lastHeartbeat).TotalSeconds > 10)
                    {
                        _logger?.Log(LogLevel.Debug, "HEARTBEAT: {0} - {1:N0} extracted, {2:N0} remaining", 
                            recordTypeName, totalRecords, remainingCount);
                        lastHeartbeat = DateTime.Now;
                    }
                }

                Console.WriteLine($"  ✓ Extracted {totalRecords:N0} {recordTypeName} in {batchNumber} batches");
                return allRecords;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error extracting {recordTypeName}: {ex.Message}");
                throw;
            }
            finally
            {
                // CRITICAL: Always close iterator, even on crash
                if (!string.IsNullOrEmpty(iteratorID))
                {
                    CloseIterator(queryAppender, iteratorID);
                }
            }
        }

        /// <summary>
        /// ADAPTIVE BATCHING: Calculate optimal batch size based on performance
        /// Reduces batch size if requests are slow, increases if fast
        /// </summary>
        private int CalculateOptimalBatchSize(
            int currentBatchSize, 
            long requestTimeMs, 
            int recordsReturned,
            string recordTypeName)
        {
            // If request took too long, reduce batch size
            if (requestTimeMs > TARGET_REQUEST_TIME_MS * 2) // More than 10 seconds
            {
                int newSize = Math.Max(MIN_BATCH_SIZE, currentBatchSize / 2);
                if (newSize != currentBatchSize)
                {
                    Console.WriteLine($"  ⚠ Reducing batch size: {currentBatchSize} → {newSize} (request took {requestTimeMs}ms)");
                }
                return newSize;
            }
            
            // If request was fast and we got a full batch, try increasing size
            if (requestTimeMs < TARGET_REQUEST_TIME_MS / 2 && recordsReturned >= currentBatchSize)
            {
                int newSize = Math.Min(MAX_BATCH_SIZE, (int)(currentBatchSize * 1.5));
                if (newSize != currentBatchSize)
                {
                    Console.WriteLine($"  ℹ Increasing batch size: {currentBatchSize} → {newSize} (request was fast at {requestTimeMs}ms)");
                }
                return newSize;
            }
            
            // Current size is optimal
            return currentBatchSize;
        }

        /// <summary>
        /// Set MaxReturned property (batch size) using reflection
        /// <summary>
        /// Set MaxReturned on query using reflection
        /// v4.1 FIX: Removed CanWrite check - QBFC properties are often read-only
        /// but return value wrappers that have SetValue() methods
        /// </summary>
        private void SetMaxReturned(object query, int maxReturned)
        {
            try
            {
                PropertyInfo prop = query.GetType().GetProperty("MaxReturned");
                
                // FIXED: Don't check CanWrite - QBFC properties are read-only but return settable wrappers
                if (prop != null)
                {
                    object propValue = prop.GetValue(query, null);
                    
                    if (propValue != null)
                    {
                        MethodInfo setValueMethod = propValue.GetType().GetMethod("SetValue", new[] { typeof(int) });
                        if (setValueMethod != null)
                        {
                            setValueMethod.Invoke(propValue, new object[] { maxReturned });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                // Track capability failure instead of silent swallow
                CapabilityWarnings.Add(new QueryCapabilityResult
                {
                    Success = false,
                    FeatureName = "MaxReturned",
                    QueryType = query.GetType().Name,
                    Reason = ex.Message
                });
            }
        }

        /// <summary>
        /// Close iterator with robust error handling
        /// </summary>
        private void CloseIterator(Func<IMsgSetRequest, object> queryAppender, string iteratorID)
        {
            try
            {
                IMsgSetRequest request = _sessionManager.CreateMsgSetRequest();
                object query = queryAppender(request);
                
                SetIteratorProperty(query, "iterator", ENiteratorType.itStop);
                SetIteratorProperty(query, "iteratorID", iteratorID);
                
                // Use short timeout for close request
                request.Attributes.OnError = ENRqOnError.roeContinue;
                
                _sessionManager.DoRequests(request);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ⚠ Warning: Failed to close iterator: {ex.Message}");
                // Non-critical - QuickBooks will timeout the iterator eventually
            }
        }

        /// <summary>
        /// Process a batch of records from the response
        /// </summary>
        private List<T> ProcessResponseBatch<T>(IResponse response, Func<object, int, T> recordParser, string recordTypeName)
        {
            var batch = new List<T>();

            if (response.Detail == null)
            {
                return batch;
            }

            // Get the ret list from the response detail
            object retList = response.Detail;
            
            // Use reflection to get the Count property
            PropertyInfo countProp = retList.GetType().GetProperty("Count");
            if (countProp == null)
            {
                throw new Exception($"Could not find Count property on {retList.GetType().Name}");
            }

            int count = (int)countProp.GetValue(retList, null);

            // Use reflection to get the GetAt method
            MethodInfo getAtMethod = retList.GetType().GetMethod("GetAt");
            if (getAtMethod == null)
            {
                throw new Exception($"Could not find GetAt method on {retList.GetType().Name}");
            }

            // Extract each record
            for (int i = 0; i < count; i++)
            {
                try
                {
                    object record = getAtMethod.Invoke(retList, new object[] { i });
                    T parsedRecord = recordParser(record, i);
                    batch.Add(parsedRecord);
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"    ⚠ Warning: Failed to parse {recordTypeName} #{i}: {ex.Message}");
                }
            }

            return batch;
        }

        /// <summary>
        /// Set iterator property using reflection (handles different query types)
        /// v4.1 FIX: Removed CanWrite check - QBFC properties are read-only wrappers
        /// </summary>
        private void SetIteratorProperty(object query, string propertyName, object value)
        {
            try
            {
                PropertyInfo prop = query.GetType().GetProperty(propertyName);
                
                // FIXED: Don't check CanWrite - get the value wrapper and call SetValue on IT
                if (prop != null)
                {
                    object propValue = prop.GetValue(query, null);
                    
                    if (propValue != null)
                    {
                        // Call SetValue on the property object
                        MethodInfo setValueMethod = propValue.GetType().GetMethod("SetValue", new[] { value.GetType() });
                        if (setValueMethod != null)
                        {
                            setValueMethod.Invoke(propValue, new[] { value });
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                // Track failure but don't crash
                System.Diagnostics.Debug.WriteLine($"Could not set {propertyName}: {ex.Message}");
            }
        }

        /// <summary>
        /// Extract records WITHOUT iterator (for queries that don't support iteration)
        /// </summary>
        public List<T> ExtractWithoutIterator<T>(
            Func<IMsgSetRequest, object> queryAppender,
            Func<object, int, T> recordParser,
            string recordTypeName)
        {
            var allRecords = new List<T>();

            try
            {
                IMsgSetRequest request = _sessionManager.CreateMsgSetRequest();
                queryAppender(request);

                IMsgSetResponse response = _sessionManager.DoRequests(request);
                IResponse resp = response.ResponseList.GetAt(0);

                if (resp.StatusCode != 0)
                {
                    if (resp.StatusCode == 1)
                    {
                        Console.WriteLine($"  ℹ No {recordTypeName} found");
                        return allRecords;
                    }
                    
                    throw new Exception($"{recordTypeName} query failed: {resp.StatusMessage}");
                }

                allRecords = ProcessResponseBatch(resp, recordParser, recordTypeName);
                Console.WriteLine($"  ✓ Extracted {allRecords.Count:N0} {recordTypeName}");

                return allRecords;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  ✗ Error extracting {recordTypeName}: {ex.Message}");
                throw;
            }
        }
        
        /// <summary>
        /// Set ModifiedDateRangeFilter for incremental sync
        /// </summary>
        private void SetModifiedDateFilter(object query, DateTime fromDate)
        {
            try
            {
                Type queryType = query.GetType();
                PropertyInfo modifiedProp = queryType.GetProperty("ModifiedDateRangeFilter");
                
                if (modifiedProp != null)
                {
                    object filter = modifiedProp.GetValue(query);
                    if (filter != null)
                    {
                        Type filterType = filter.GetType();
                        PropertyInfo fromProp = filterType.GetProperty("FromModifiedDate");
                        
                        if (fromProp != null)
                        {
                            object fromModified = fromProp.GetValue(filter);
                            if (fromModified != null)
                            {
                                MethodInfo setValueMethod = fromModified.GetType().GetMethod("SetValue", new[] { typeof(DateTime) });
                                if (setValueMethod != null)
                                {
                                    setValueMethod.Invoke(fromModified, new object[] { fromDate });
                                }
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                // This catch is acceptable - ModifiedDateRangeFilter support varies
                // But we now track it in capability warnings
                throw new Exception($"SetModifiedDateFilter failed: {ex.Message}", ex);
            }
        }

        /// <summary>
        /// Get query type name from query object
        /// </summary>
        private string GetQueryType(object query)
        {
            if (query == null)
                return "UnknownQuery";
            
            string typeName = query.GetType().Name;
            // Remove 'I' prefix if present (IAccountQuery -> AccountQuery)
            if (typeName.StartsWith("I") && typeName.Length > 1)
                typeName = typeName.Substring(1);
            
            return typeName;
        }

        /// <summary>
        /// Validate response detail type before reflection
        /// </summary>
        private bool TryGetListCount(object detail, out int count)
        {
            count = 0;
            
            if (detail == null)
            {
                Console.WriteLine("⚠ Response detail is null");
                return false;
            }
            
            var detailType = detail.GetType();
            var typeName = detailType.Name;
            
            // Expected return list types
            var expectedTypes = new[]
            {
                "IAccountRetList", "ICustomerRetList", "IVendorRetList", "IEmployeeRetList",
                "IItemRetList", "IInvoiceRetList", "IBillRetList", "ICheckRetList"
                // Add more as needed
            };
            
            if (!expectedTypes.Contains(typeName))
            {
                Console.WriteLine($"⚠ Unexpected response type: {typeName} (expected one of {string.Join(", ", expectedTypes)})");
                // Try to continue anyway
            }
            
            var countProperty = detailType.GetProperty("Count");
            if (countProperty == null)
            {
                Console.WriteLine($"⚠ Type {typeName} has no Count property");
                return false;
            }
            
            try
            {
                count = (int)countProperty.GetValue(detail, null);
                return true;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠ Failed to get Count from {typeName}: {ex.Message}");
                return false;
            }
        }
    }
}

#endif // USE_QBFC