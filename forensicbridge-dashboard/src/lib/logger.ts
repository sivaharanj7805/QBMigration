/**
 * MED-16 to MED-25 FIX: Proper Logging Utility
 *
 * Replaces console.log statements with structured logging.
 * In production, logs are suppressed or sent to a monitoring service.
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

      // In production, send to monitoring service
      if (isProduction && typeof window !== 'undefined') {
        // TODO: Integrate with Sentry or other monitoring service
        // Sentry.captureException(error, { extra: context });
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
