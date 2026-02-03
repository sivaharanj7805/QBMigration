"use client";

import { useParams, useRouter } from "next/navigation";
import { useLiveStatus, useTrialBalance } from "@/lib/hooks/useLiveStatus";
import { useQuery } from "@tanstack/react-query";
import { PizzaTracker } from "@/components/dashboard/PizzaTracker";
import { ReconciliationShield } from "@/components/dashboard/ReconciliationShield";
import { AuditCertCard } from "@/components/dashboard/AuditCertCard";
import { CasewareBundleCard } from "@/components/dashboard/CasewareBundleCard";
import { ForensicIntegrityPulse } from "@/components/dashboard/ForensicIntegrityPulse";
import { DiscrepancyDoctor, Discrepancy } from "@/components/migrations/DiscrepancyDoctor";
import { ArrowLeft, Clock, CheckCircle, AlertCircle, Loader2, Cloud, FileBarChart2 } from "lucide-react";
import Link from "next/link";
import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { authFetch } from "@/lib/auth";
import { sanitize } from "@/lib/sanitize";
import { useLoadingGuard } from "@/lib/hooks/useSecurityHooks";

// API URL for authFetch calls (api client handles its own base URL internally)
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

// Destination type
type DestinationType = "qbo" | "caseware";

// FIX: Define proper types for API responses instead of using 'any'
interface LiveStatusResponse {
    migration_id: string;
    phase: string;
    phase_number: number;
    percentage: number;
    current_entity: string | null;
    status_message: string;
    status: string;
    alerts: string[];
    integrity_verified: boolean;
    phases: Array<{
        name: string;
        status: "pending" | "in_progress" | "completed";
        percentage: number;
        description: string;
    }>;
    company_name: string;
    started_at: string;
    elapsed_seconds: number;
    completed_at?: string;
    duration_seconds?: number;
    error?: string;
    destination?: DestinationType;
}

interface ApiDiscrepancy {
    account_name: string;
    account_type?: string;
    source_balance: number;
    destination_balance: number;
    difference: number;
    severity?: "critical" | "warning" | "info";
    possible_cause?: string;
}

export default function MigrationDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = typeof params?.id === 'string' ? params.id : '';

    // Real API hooks
    const { data: liveStatus, isLoading: statusLoading } = useLiveStatus(id);
    const { data: trialBalance } = useTrialBalance(id, liveStatus?.status === "completed");

    // Fetch discrepancies from API
    // SECURITY: Using authFetch instead of localStorage.getItem('token')
    const { data: discrepancyData } = useQuery({
        queryKey: ["discrepancies", id],
        queryFn: async ({ signal }) => {
            const response = await authFetch(`${API_URL}/api/migrations/${id}/discrepancies`, {
                signal,
            });
            if (!response.ok) return { discrepancies: [], total_discrepancy: 0 };
            return response.json();
        },
        enabled: !!id && liveStatus?.status === "completed",
    });

    // Fetch record count from API
    // SECURITY: Using authFetch instead of localStorage.getItem('token')
    const { data: recordCountData } = useQuery({
        queryKey: ["recordCount", id],
        queryFn: async ({ signal }) => {
            const response = await authFetch(`${API_URL}/api/migrations/${id}/record-count`, {
                signal,
            });
            if (!response.ok) return { record_count: 0 };
            return response.json();
        },
        enabled: !!id,
    });

    // FIX: Remove 'any' cast - use typed response
    // The liveStatus is typed from useLiveStatus hook, destination is optional
    const destination: DestinationType = (liveStatus as LiveStatusResponse | undefined)?.destination || "qbo";

    const [isCancelling, setIsCancelling] = useState(false);
    const [showDiscrepancyDoctor, setShowDiscrepancyDoctor] = useState(true);
    // FIX: Add state for concurrent request throttling
    const [isExportingReport, setIsExportingReport] = useState(false);
    // FIX: Add error states to replace alert() calls
    const [exportError, setExportError] = useState<string | null>(null);
    const [cancelError, setCancelError] = useState<string | null>(null);
    const [certificateError, setCertificateError] = useState<string | null>(null);

    // FIX: Auto-dismiss errors after 5 seconds
    useEffect(() => {
        if (exportError) {
            const timer = setTimeout(() => setExportError(null), 5000);
            return () => clearTimeout(timer);
        }
    }, [exportError]);

    useEffect(() => {
        if (cancelError) {
            const timer = setTimeout(() => setCancelError(null), 5000);
            return () => clearTimeout(timer);
        }
    }, [cancelError]);

    useEffect(() => {
        if (certificateError) {
            const timer = setTimeout(() => setCertificateError(null), 5000);
            return () => clearTimeout(timer);
        }
    }, [certificateError]);

    // FIX: Improved error messages with specific details
    // SECURITY: Using authFetch instead of localStorage.getItem('token')
    const handleExportDiscrepancyReport = async () => {
        // FIX: Prevent concurrent requests
        if (isExportingReport) return;
        setIsExportingReport(true);
        try {
            const response = await authFetch(`${API_URL}/api/migrations/${id}/discrepancy-report`);
            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Discrepancy_Report_${id}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                // FIX: Provide specific error details based on HTTP status
                let errorMessage = "Failed to export discrepancy report.";
                if (response.status === 401) {
                    errorMessage += " Your session may have expired. Please log in again.";
                } else if (response.status === 404) {
                    errorMessage += " The report was not found for this migration.";
                } else if (response.status === 403) {
                    errorMessage += " You don't have permission to access this report.";
                } else if (response.status >= 500) {
                    errorMessage += ` Server error (${response.status}). Please try again later.`;
                } else {
                    try {
                        const errorData = await response.json();
                        if (errorData.error) {
                            // SECURITY FIX: Sanitize error messages from API to prevent XSS
                            // API errors could be user-influenced or from compromised server
                            errorMessage = sanitize.text(String(errorData.error));
                        }
                    } catch {
                        // Response wasn't JSON
                    }
                }
                // FIX: Replace alert() with state-based error toast
                setExportError(errorMessage);
            }
        } catch (error) {
            // FIX: Only log errors in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error("Export error:", error);
            }
            // FIX: Differentiate between network errors and other errors - replace alert() with state
            if (error instanceof TypeError && error.message.includes('fetch')) {
                setExportError("Network error: Unable to connect to the server. Please check your internet connection.");
            } else {
                setExportError("Failed to export report. Please try again.");
            }
        } finally {
            // FIX: Always reset loading state
            setIsExportingReport(false);
        }
    };

    const handleReviewResolve = () => {
        // Navigate to reports page where discrepancies can be reviewed
        router.push('/reports');
    };

    const handleCancelMigration = async () => {
        if (!confirm("Are you sure you want to cancel this migration?")) return;
        setIsCancelling(true);
        setCancelError(null); // Clear previous errors
        try {
            const result = await api.cancelMigration(id);
            if (result.success) {
                router.refresh();
            } else {
                // FIX: Replace alert() with state-based error toast
                setCancelError(result.error || "Failed to cancel migration");
            }
        } catch (error) {
            // FIX: Only log errors in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error("Cancel error:", error);
            }
            // FIX: Replace alert() with state-based error toast
            setCancelError("Failed to cancel migration. Please try again.");
        } finally {
            setIsCancelling(false);
        }
    };

    // Certificate download handler
    const [isDownloading, setIsDownloading] = useState(false);
    const handleDownloadCertificate = async () => {
        setIsDownloading(true);
        setCertificateError(null); // Clear previous errors
        try {
            const blob = await api.downloadAuditCertificate(id);
            if (blob) {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `Audit_Certificate_${id}.pdf`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            } else {
                // FIX: Replace alert() with state-based error toast
                setCertificateError("Certificate download failed. The file may not be available yet.");
            }
        } catch (e) {
            // FIX: Only log errors in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error("Certificate download error:", e);
            }
            // FIX: Replace alert() with state-based error toast
            setCertificateError("Error downloading certificate. Please try again.");
        } finally {
            setIsDownloading(false);
        }
    };

    const getStatusIcon = () => {
        switch (liveStatus?.status) {
            case "completed":
                return <CheckCircle className="w-5 h-5 text-[var(--success)]" />;
            case "failed":
                return <AlertCircle className="w-5 h-5 text-[var(--error)]" />;
            case "processing":
                return <Loader2 className="w-5 h-5 text-[var(--bridge-blue)] animate-spin" />;
            default:
                return <Clock className="w-5 h-5 text-gray-400" />;
        }
    };

    const getDestinationBadge = () => {
        if (destination === "caseware") {
            return (
                <span className="flex items-center gap-1 px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                    <FileBarChart2 className="w-4 h-4" />
                    Caseware
                </span>
            );
        }
        return (
            <span className="flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
                <Cloud className="w-4 h-4" />
                QuickBooks Online
            </span>
        );
    };

    if (!id) {
        return <div className="p-8 text-center text-gray-500">Invalid migration ID</div>;
    }

    if (statusLoading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-[var(--bridge-blue)]" />
            </div>
        );
    }

    const isCompleted = liveStatus?.status === "completed";
    const isProcessing = liveStatus?.status === "processing";
    const isCaseware = destination === "caseware";

    return (
        <div className="space-y-6">
            {/* FIX: Error Toast UI - replaces alert() calls */}
            {(exportError || cancelError || certificateError) && (
                <div className="fixed top-4 right-4 z-50 space-y-2">
                    {exportError && (
                        <div className="bg-red-500 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 max-w-md animate-in slide-in-from-right">
                            <AlertCircle className="w-5 h-5 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-sm">Export Error</p>
                                <p className="text-sm opacity-90">{exportError}</p>
                            </div>
                            <button
                                onClick={() => setExportError(null)}
                                className="text-white/80 hover:text-white"
                                aria-label="Dismiss error"
                            >
                                ×
                            </button>
                        </div>
                    )}
                    {cancelError && (
                        <div className="bg-red-500 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 max-w-md animate-in slide-in-from-right">
                            <AlertCircle className="w-5 h-5 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-sm">Cancel Error</p>
                                <p className="text-sm opacity-90">{cancelError}</p>
                            </div>
                            <button
                                onClick={() => setCancelError(null)}
                                className="text-white/80 hover:text-white"
                                aria-label="Dismiss error"
                            >
                                ×
                            </button>
                        </div>
                    )}
                    {certificateError && (
                        <div className="bg-red-500 text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 max-w-md animate-in slide-in-from-right">
                            <AlertCircle className="w-5 h-5 flex-shrink-0" />
                            <div className="flex-1">
                                <p className="font-medium text-sm">Download Error</p>
                                <p className="text-sm opacity-90">{certificateError}</p>
                            </div>
                            <button
                                onClick={() => setCertificateError(null)}
                                className="text-white/80 hover:text-white"
                                aria-label="Dismiss error"
                            >
                                ×
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Link
                        href="/migrations"
                        className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        <ArrowLeft className="w-5 h-5 text-gray-500" />
                    </Link>
                    <div>
                        <div className="flex items-center gap-3">
                            {getStatusIcon()}
                            <h1 className="text-2xl font-bold text-gray-900">
                                {sanitize.text(liveStatus?.company_name || "Migration Details")}
                            </h1>
                            {getDestinationBadge()}
                        </div>
                        <p className="text-sm text-gray-500 mt-1">
                            Session ID: <code className="text-[var(--bridge-blue)]">{id}</code>
                            {isCaseware && <span className="ml-2 text-purple-600">• Caseware Audit Bundle Mode</span>}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {isProcessing && (
                        <button
                            className="flex items-center gap-2 px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                            onClick={handleCancelMigration}
                            disabled={isCancelling}
                        >
                            {isCancelling ? "Cancelling..." : "Cancel Migration"}
                        </button>
                    )}
                </div>
            </div>

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #1: FORENSIC TRUST CHAIN (PIZZA TRACKER)
                5-phase visual progress bar - ALWAYS VISIBLE at top
            ═══════════════════════════════════════════════════════════════ */}
            <PizzaTracker
                phases={liveStatus?.phases || []}
                currentPhase={liveStatus?.phase_number || 1}
                overallPercentage={liveStatus?.percentage || 0}
                currentEntity={liveStatus?.current_entity}
                statusMessage={liveStatus?.status_message}
                companyName={liveStatus?.company_name}
                elapsedSeconds={liveStatus?.elapsed_seconds || 0}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #2: RECONCILIATION SHIELD
                Large green ✓ or red ⚠ - THE MOST IMPORTANT DATA POINT
            ═══════════════════════════════════════════════════════════════ */}
            <ReconciliationShield
                sourceBalance={trialBalance?.source_trial_balance ?? undefined}
                destinationBalance={trialBalance?.destination_trial_balance ?? undefined}
                discrepancy={trialBalance?.discrepancy ?? 0}
                isBalanced={trialBalance?.is_balanced ?? false}
                forensicStatus={
                    (trialBalance?.forensic_status as "VERIFIED" | "PENDING" | "DISCREPANCY_DETECTED" | "NOT_AVAILABLE") ||
                    (isCompleted && trialBalance ? "VERIFIED" : "PENDING")
                }
                verificationTimestamp={trialBalance?.verification_timestamp ?? undefined}
                sourceHash={trialBalance?.source_hash ?? undefined}
                destinationHash={trialBalance?.destination_hash ?? undefined}
                hashMatch={trialBalance?.hash_match ?? undefined}
                migrationId={id}
                isLoading={!isCompleted && statusLoading}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #3 & #5: CASEWARE BUNDLE + AUDIT CERTIFICATE
                Side-by-side download cards - THE USP
            ═══════════════════════════════════════════════════════════════ */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <CasewareBundleCard
                    migrationId={id}
                    companyName={liveStatus?.company_name || "Company"}
                    isAvailable={isCompleted}
                    recordCount={recordCountData?.record_count || 0}
                />

                <AuditCertCard
                    migrationId={id}
                    companyName={liveStatus?.company_name || "Unknown"}
                    completedAt={liveStatus?.completed_at || null}
                    isAvailable={isCompleted}
                    onDownload={handleDownloadCertificate}
                    isDownloading={isDownloading}
                />
            </div>

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #4: FORENSIC INTEGRITY PULSE
                Terminal-style rolling log - Chain of Custody visualization
            ═══════════════════════════════════════════════════════════════ */}
            <ForensicIntegrityPulse
                isLive={isProcessing}
                migrationId={id}
            />

            {/* ═══════════════════════════════════════════════════════════════
                HIGH PRIORITY #6: DISCREPANCY DOCTOR
                Interactive drill-down - only shown if there are variances
            ═══════════════════════════════════════════════════════════════ */}
            {(discrepancyData?.has_discrepancies && showDiscrepancyDoctor) ? (
                <DiscrepancyDoctor
                    discrepancies={discrepancyData.discrepancies.map((d: ApiDiscrepancy) => ({
                        account_name: d.account_name,
                        account_type: d.account_type || "Unknown",
                        source_balance: d.source_balance,
                        destination_balance: d.destination_balance,
                        difference: d.difference,
                        severity: d.severity || "warning",
                        possible_cause: d.possible_cause,
                    }))}
                    totalDiscrepancy={discrepancyData.total_discrepancy}
                    onDismiss={() => setShowDiscrepancyDoctor(false)}
                    onExportReport={handleExportDiscrepancyReport}
                    onReviewResolve={handleReviewResolve}
                />
            ) : isCompleted ? (
                <div className="card-forensic bg-green-50 border-green-200 p-6">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 bg-green-100 rounded-full flex items-center justify-center">
                            <CheckCircle className="w-6 h-6 text-green-600" />
                        </div>
                        <div>
                            <h3 className="font-bold text-green-900 text-lg">Penny-Perfect Migration</h3>
                            <p className="text-green-700">
                                All accounts balanced. No discrepancies detected. Ready for CPA sign-off.
                            </p>
                        </div>
                    </div>
                </div>
            ) : null}
        </div>
    );
}
