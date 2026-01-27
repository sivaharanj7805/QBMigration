using System;
using System.Threading;
using System.Threading.Tasks;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Utility class for retry operations with exponential backoff
    /// </summary>
    public static class RetryHelper
    {
        /// <summary>
        /// Execute an action with retry logic and exponential backoff
        /// </summary>
        public static async Task<T> ExecuteWithRetryAsync<T>(
            Func<Task<T>> operation,
            int maxRetries = 3,
            int baseDelayMs = 1000,
            IRedactingLogger logger = null,
            string operationName = "operation",
            CancellationToken ct = default)
        {
            Exception lastException = null;

            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                try
                {
                    ct.ThrowIfCancellationRequested();
                    return await operation();
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    lastException = ex;

                    if (attempt < maxRetries)
                    {
                        int delay = baseDelayMs * (int)Math.Pow(2, attempt - 1);
                        logger?.Log(LogLevel.Warning,
                            "{0} failed (attempt {1}/{2}): {3}. Retrying in {4}ms...",
                            operationName, attempt, maxRetries, ex.Message, delay);

                        await Task.Delay(delay, ct);
                    }
                    else
                    {
                        logger?.Log(LogLevel.Error,
                            "{0} failed after {1} attempts: {2}",
                            operationName, maxRetries, ex.Message);
                    }
                }
            }

            throw new RetryExhaustedException(
                $"{operationName} failed after {maxRetries} attempts",
                lastException);
        }

        /// <summary>
        /// Execute a synchronous action with retry logic
        /// </summary>
        public static T ExecuteWithRetry<T>(
            Func<T> operation,
            int maxRetries = 3,
            int baseDelayMs = 1000,
            IRedactingLogger logger = null,
            string operationName = "operation")
        {
            Exception lastException = null;

            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                try
                {
                    return operation();
                }
                catch (Exception ex)
                {
                    lastException = ex;

                    if (attempt < maxRetries)
                    {
                        int delay = baseDelayMs * (int)Math.Pow(2, attempt - 1);
                        logger?.Log(LogLevel.Warning,
                            "{0} failed (attempt {1}/{2}): {3}. Retrying in {4}ms...",
                            operationName, attempt, maxRetries, ex.Message, delay);

                        Thread.Sleep(delay);
                    }
                    else
                    {
                        logger?.Log(LogLevel.Error,
                            "{0} failed after {1} attempts: {2}",
                            operationName, maxRetries, ex.Message);
                    }
                }
            }

            throw new RetryExhaustedException(
                $"{operationName} failed after {maxRetries} attempts",
                lastException);
        }

        /// <summary>
        /// Execute an action with retry (no return value)
        /// </summary>
        public static async Task ExecuteWithRetryAsync(
            Func<Task> operation,
            int maxRetries = 3,
            int baseDelayMs = 1000,
            IRedactingLogger logger = null,
            string operationName = "operation",
            CancellationToken ct = default)
        {
            await ExecuteWithRetryAsync(async () =>
            {
                await operation();
                return true;
            }, maxRetries, baseDelayMs, logger, operationName, ct);
        }
    }

    /// <summary>
    /// Exception thrown when all retry attempts are exhausted
    /// </summary>
    public class RetryExhaustedException : Exception
    {
        public RetryExhaustedException(string message, Exception innerException)
            : base(message, innerException)
        {
        }
    }
}
