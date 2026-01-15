"use client";

import { FileText, Download, Calendar, Building2 } from "lucide-react";

interface AuditCertCardProps {
    migrationId: string;
    companyName: string;
    completedAt: string | null;
    isAvailable: boolean;
    onDownload: () => void;
    isDownloading?: boolean;
}

export function AuditCertCard({
    migrationId,
    companyName,
    completedAt,
    isAvailable,
    onDownload,
    isDownloading = false,
}: AuditCertCardProps) {
    const formatDate = (ts: string | null) => {
        if (!ts) return "—";
        return new Date(ts).toLocaleDateString("en-US", {
            month: "long",
            day: "numeric",
            year: "numeric",
        });
    };

    return (
        <div className="card-forensic-gold overflow-hidden">
            {/* Gold Header */}
            <div className="bg-gradient-to-r from-[var(--forensic-gold)] to-[var(--forensic-gold-light)] px-6 py-4">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <div className="w-12 h-12 bg-white/20 rounded-lg flex items-center justify-center">
                            <FileText className="w-6 h-6 text-white" />
                        </div>
                        <div>
                            <h3 className="text-lg font-bold text-white">CPA Audit Certificate</h3>
                            <p className="text-sm text-white/80">Migration Verification Document</p>
                        </div>
                    </div>
                    {isAvailable && (
                        <div className="px-3 py-1 bg-white/20 rounded-full text-xs font-medium text-white">
                            Ready for Download
                        </div>
                    )}
                </div>
            </div>

            {/* Document Preview */}
            <div className="p-6">
                <div className="bg-gray-50 rounded-lg p-4 mb-4 border-2 border-dashed border-gray-200">
                    {/* PDF Preview Mockup */}
                    <div className="aspect-[8.5/11] max-h-48 bg-white rounded shadow-sm flex flex-col items-center justify-center text-gray-400 mx-auto w-full max-w-[200px]">
                        <FileText className="w-12 h-12 mb-2" />
                        <p className="text-xs font-medium">PDF Preview</p>
                        <p className="text-xs mt-1">{migrationId}</p>
                    </div>
                </div>

                {/* Document Info */}
                <div className="space-y-3">
                    <div className="flex items-center gap-3 text-sm">
                        <Building2 className="w-4 h-4 text-gray-400" />
                        <span className="text-gray-500">Company:</span>
                        <span className="font-medium text-gray-900">{companyName}</span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                        <Calendar className="w-4 h-4 text-gray-400" />
                        <span className="text-gray-500">Completed:</span>
                        <span className="font-medium text-gray-900">{formatDate(completedAt)}</span>
                    </div>
                    <div className="flex items-center gap-3 text-sm">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <span className="text-gray-500">Session ID:</span>
                        <code className="font-mono text-xs text-[var(--bridge-blue)]">{migrationId}</code>
                    </div>
                </div>

                {/* Download Button */}
                <button
                    onClick={onDownload}
                    disabled={!isAvailable || isDownloading}
                    className={`w-full mt-6 flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-medium transition-all ${isAvailable
                            ? "bg-[var(--forensic-gold)] text-white hover:bg-[var(--forensic-gold)]/90 shadow-lg shadow-[var(--forensic-gold)]/30"
                            : "bg-gray-100 text-gray-400 cursor-not-allowed"
                        }`}
                >
                    {isDownloading ? (
                        <>
                            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                            Preparing Download...
                        </>
                    ) : (
                        <>
                            <Download className="w-5 h-5" />
                            Download Institutional Audit Pack
                        </>
                    )}
                </button>

                {!isAvailable && (
                    <p className="text-xs text-gray-500 text-center mt-3">
                        Certificate will be available after migration completes
                    </p>
                )}
            </div>
        </div>
    );
}
