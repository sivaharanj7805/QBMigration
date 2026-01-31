"use client";

import { Download, FileSpreadsheet, Package, CheckCircle2, Loader2, AlertCircle } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";

interface CasewareBundleCardProps {
    migrationId: string;
    companyName: string;
    isAvailable: boolean;
    recordCount?: number;
}

export function CasewareBundleCard({
    migrationId,
    companyName,
    isAvailable,
    recordCount = 0
}: CasewareBundleCardProps) {
    const [isDownloading, setIsDownloading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [status, setStatus] = useState<string>("");

    const handleDownload = async () => {
        setIsDownloading(true);
        setError(null);
        setStatus("Generating Caseware bundle...");

        try {
            // Step 1: Generate the Caseware bundle on the server
            const exportResult = await api.exportCasewareBundle(migrationId);

            if (!exportResult.success || exportResult.error) {
                throw new Error(exportResult.error || "Failed to generate Caseware bundle");
            }

            setStatus("Downloading bundle...");

            // Step 2: Download the generated bundle
            const blob = await api.downloadCasewareBundle(migrationId);

            if (!blob) {
                throw new Error("Failed to download Caseware bundle");
            }

            // Step 3: Trigger browser download
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${companyName}_CasewareBundle.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            setStatus("Download complete!");
        } catch (err) {
            const message = err instanceof Error ? err.message : "Unknown error occurred";
            setError(message);
            // FIX: Only log in development mode
            if (process.env.NODE_ENV === 'development') {
                console.error("Caseware download error:", err);
            }
        } finally {
            setIsDownloading(false);
            // Clear status after 3 seconds
            setTimeout(() => setStatus(""), 3000);
        }
    };

    return (
        <div className="card-forensic overflow-hidden border-2 border-[var(--bridge-blue)]">
            {/* Blue Header - HIGH CONTRAST */}
            <div className="bg-[var(--bridge-blue)] px-6 py-4">
                <div className="flex items-center gap-3">
                    <div className="w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
                        <Package className="w-6 h-6 text-white" />
                    </div>
                    <div>
                        <h3 className="text-lg font-bold text-white">Caseware Audit Bundle</h3>
                        <p className="text-sm text-white/80">Ready for Caseware Working Papers</p>
                    </div>
                </div>
            </div>

            {/* Bundle Contents */}
            <div className="p-6 bg-blue-50">
                <p className="text-sm text-gray-600 mb-4">Bundle contains:</p>

                <div className="space-y-2">
                    <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-blue-100">
                        <FileSpreadsheet className="w-5 h-5 text-blue-600" />
                        <div className="flex-1">
                            <p className="font-medium text-gray-900">Audit_TB.csv</p>
                            <p className="text-xs text-gray-500">Trial Balance with 58 Lead Sheet Codes</p>
                        </div>
                        <CheckCircle2 className="w-5 h-5 text-green-500" />
                    </div>

                    <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-blue-100">
                        <FileSpreadsheet className="w-5 h-5 text-blue-600" />
                        <div className="flex-1">
                            <p className="font-medium text-gray-900">Audit_GL.csv</p>
                            <p className="text-xs text-gray-500">General Ledger with SHA-256 Hashes</p>
                        </div>
                        <CheckCircle2 className="w-5 h-5 text-green-500" />
                    </div>

                    <div className="flex items-center gap-3 p-3 bg-white rounded-lg border border-blue-100">
                        <FileSpreadsheet className="w-5 h-5 text-blue-600" />
                        <div className="flex-1">
                            <p className="font-medium text-gray-900">Audit_Mapping.cvw</p>
                            <p className="text-xs text-gray-500">Caseware Column Configuration</p>
                        </div>
                        <CheckCircle2 className="w-5 h-5 text-green-500" />
                    </div>
                </div>

                {/* Stats */}
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-blue-200">
                    <div className="text-sm text-gray-600">
                        <span className="font-bold text-gray-900">{recordCount.toLocaleString()}</span> records
                    </div>
                    <div className="text-sm text-gray-600">
                        Session: <code className="text-[var(--bridge-blue)]">{migrationId}</code>
                    </div>
                </div>
            </div>

            {/* Error Display */}
            {error && (
                <div className="px-6 py-3 bg-red-50 border-t border-red-200">
                    <div className="flex items-center gap-2 text-red-700">
                        <AlertCircle className="w-4 h-4" />
                        <span className="text-sm">{error}</span>
                    </div>
                </div>
            )}

            {/* Status Display */}
            {status && !error && (
                <div className="px-6 py-2 bg-blue-100 border-t border-blue-200">
                    <p className="text-sm text-blue-700 text-center">{status}</p>
                </div>
            )}

            {/* BIG DOWNLOAD BUTTON */}
            <div className="p-6 bg-white border-t">
                <button
                    onClick={handleDownload}
                    disabled={!isAvailable || isDownloading}
                    className={`w-full flex items-center justify-center gap-3 px-8 py-4 rounded-xl font-bold text-lg transition-all ${isAvailable
                        ? "bg-[var(--bridge-blue)] text-white hover:bg-[var(--bridge-blue-dark)] shadow-lg shadow-blue-500/30 hover:shadow-xl hover:scale-[1.02]"
                        : "bg-gray-100 text-gray-400 cursor-not-allowed"
                        }`}
                >
                    {isDownloading ? (
                        <>
                            <Loader2 className="w-6 h-6 animate-spin" />
                            Preparing Bundle...
                        </>
                    ) : (
                        <>
                            <Download className="w-6 h-6" />
                            Download Audit Bundle
                        </>
                    )}
                </button>

                {isAvailable && (
                    <p className="text-xs text-center text-gray-500 mt-3">
                        ↓ Direct import into Caseware Working Papers
                    </p>
                )}
            </div>
        </div>
    );
}
