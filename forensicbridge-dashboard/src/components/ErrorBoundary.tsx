/**
 * MED-01 to MED-15 FIX: React Error Boundary Component
 *
 * Provides error boundaries for React components to prevent
 * entire application crashes from component errors.
 */
'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
  resetKey: number;  // MED-06 FIX: Counter to force children re-mount on retry
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, resetKey: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // AUDIT FIX P13-M1: Integrate with Sentry for production error reporting
    if (typeof window !== 'undefined' && (window as Record<string, unknown>).Sentry) {
      const Sentry = (window as Record<string, unknown>).Sentry as {
        captureException: (err: Error, ctx?: Record<string, unknown>) => void;
      };
      Sentry.captureException(error, {
        extra: { componentStack: errorInfo.componentStack },
      });
    }

    if (process.env.NODE_ENV === 'development') {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return (
        <div className="min-h-[200px] flex items-center justify-center p-4">
          <div className="text-center">
            <div className="text-red-500 mb-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-12 w-12 mx-auto"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">
              Something went wrong
            </h2>
            <p className="text-sm text-gray-600 mb-4">
              We&apos;re sorry, but something unexpected happened.
            </p>
            <button
              onClick={() => this.setState(prev => ({ hasError: false, error: null, resetKey: prev.resetKey + 1 }))}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
              type="button"
            >
              Try Again
            </button>
          </div>
        </div>
      );
    }

    // MED-06 FIX: Use key to force re-mount of children when "Try Again" is clicked.
    // Without this, React reuses the existing component tree which stays in error state.
    return <React.Fragment key={this.state.resetKey}>{this.props.children}</React.Fragment>;
  }
}

/**
 * Higher-order component to wrap components with error boundary
 */
export function withErrorBoundary<P extends object>(
  WrappedComponent: React.ComponentType<P>,
  fallback?: ReactNode
): React.FC<P> {
  const displayName = WrappedComponent.displayName || WrappedComponent.name || 'Component';

  const ComponentWithErrorBoundary: React.FC<P> = (props) => (
    <ErrorBoundary fallback={fallback}>
      <WrappedComponent {...props} />
    </ErrorBoundary>
  );

  ComponentWithErrorBoundary.displayName = `withErrorBoundary(${displayName})`;

  return ComponentWithErrorBoundary;
}

export default ErrorBoundary;
