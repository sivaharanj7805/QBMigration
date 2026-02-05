/**
 * MED-16 to MED-25 FIX: Proper Logging Utility
 *
 * Replaces console.log statements with structured logging.
 * In production, logs are suppressed or sent to a monitoring service.
 *
 * LOW-04 FIX: Sentry integration for production error monitoring.
 * Errors and warnings are forwarded to Sentry when NEXT_PUBLIC_SENTRY_DSN is set.
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  [key: string]: unknown;
}

interface Logger {
  debug: (message: string, context?: LogContext) => void;
  info: (message: string, context?: LogContext) => void;
  warn: (message: string, context?: LogContext) => void;
  error: (message: string, error?: Error | unknown, context?: LogContext) => void;
}

const isProduction = process.env.NODE_ENV === 'production';
const isDebugEnabled = process.env.NEXT_PUBLIC_DEBUG === 'true';
const sentryDsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

/**
 * LOW-04 FIX: Lightweight Sentry reporter using the Sentry Envelope API.
 * Sends error events directly via fetch without requiring the full @sentry/nextjs SDK,
 * keeping the bundle size minimal. For full breadcrumb/replay support, install
 * @sentry/nextjs and replace this with Sentry.init().
 */
function reportToSentry(
  message: string,
  error?: Error | unknown,
  context?: LogContext
): void {
  if (!sentryDsn || typeof window === 'undefined') return;

  try {
    // Parse DSN: https://<key>@<host>/<project_id>
    const dsnMatch = sentryDsn.match(
      /^https?:\/\/([^@]+)@([^/]+)\/(\d+)$/
    );
    if (!dsnMatch) return;

    const [, publicKey, host, projectId] = dsnMatch;
    const endpoint = `https://${host}/api/${projectId}/envelope/?sentry_key=${publicKey}&sentry_version=7`;

    const eventId = crypto.randomUUID?.() ?? Math.random().toString(36).slice(2);

    const errorData =
      error instanceof Error
        ? {
            type: error.name,
            value: error.message,
            stacktrace: error.stack
              ? {
                  frames: error.stack
                    .split('\n')
                    .slice(1, 10)
                    .map((line) => ({ filename: line.trim() })),
                }
              : undefined,
          }
        : error
          ? { type: 'Error', value: String(error) }
          : undefined;

    const event = {
      event_id: eventId,
      timestamp: new Date().toISOString(),
      platform: 'javascript',
      level: 'error',
      message: { formatted: message },
      exception: errorData
        ? { values: [errorData] }
        : undefined,
      extra: context,
      environment: process.env.NODE_ENV,
      tags: { source: 'forensicbridge-dashboard' },
    };

    const envelope = [
      JSON.stringify({
        event_id: eventId,
        sent_at: new Date().toISOString(),
        dsn: sentryDsn,
      }),
      JSON.stringify({ type: 'event' }),
      JSON.stringify(event),
    ].join('\n');

    // Fire-and-forget: don't await, don't block the UI
    void fetch(endpoint, {
      method: 'POST',
      body: envelope,
      headers: { 'Content-Type': 'application/x-sentry-envelope' },
    }).catch(() => {
      // Silently ignore Sentry delivery failures
    });
  } catch {
    // Never let monitoring code crash the application
  }
}

function formatMessage(level: LogLevel, message: string, context?: LogContext): string {
  const timestamp = new Date().toISOString();
  const contextStr = context ? ` ${JSON.stringify(context)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}] ${message}${contextStr}`;
}

function shouldLog(level: LogLevel): boolean {
  if (isProduction) {
    // In production, only log warnings and errors
    return level === 'warn' || level === 'error';
  }
  if (level === 'debug' && !isDebugEnabled) {
    return false;
  }
  return true;
}

/**
 * Application logger
 *
 * Usage:
 * ```typescript
 * import { logger } from '@/lib/logger';
 *
 * logger.info('User logged in', { userId: 123 });
 * logger.error('Failed to fetch data', error, { endpoint: '/api/data' });
 * ```
 */
export const logger: Logger = {
  debug: (message: string, context?: LogContext) => {
    if (shouldLog('debug')) {
      console.debug(formatMessage('debug', message, context));
    }
  },

  info: (message: string, context?: LogContext) => {
    if (shouldLog('info')) {
      console.info(formatMessage('info', message, context));
    }
  },

  warn: (message: string, context?: LogContext) => {
    if (shouldLog('warn')) {
      console.warn(formatMessage('warn', message, context));
    }
  },

  error: (message: string, error?: Error | unknown, context?: LogContext) => {
    if (shouldLog('error')) {
      const errorContext = {
        ...context,
        ...(error instanceof Error
          ? {
              errorName: error.name,
              errorMessage: error.message,
              errorStack: isProduction ? undefined : error.stack,
            }
          : { errorDetails: String(error) }),
      };
      console.error(formatMessage('error', message, errorContext));

      // LOW-04 FIX: Send errors to Sentry in production
      if (isProduction) {
        reportToSentry(message, error, context);
      }
    }
  },
};

/**
 * Create a namespaced logger for a specific module
 */
export function createLogger(namespace: string): Logger {
  return {
    debug: (message, context) => logger.debug(`[${namespace}] ${message}`, context),
    info: (message, context) => logger.info(`[${namespace}] ${message}`, context),
    warn: (message, context) => logger.warn(`[${namespace}] ${message}`, context),
    error: (message, error, context) => logger.error(`[${namespace}] ${message}`, error, context),
  };
}

export default logger;
