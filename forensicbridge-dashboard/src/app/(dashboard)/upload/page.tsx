"use client";

import { useState, useCallback } from "react";
import {
    Upload,
    FileSpreadsheet,
    CheckCircle2,
    AlertCircle,
    X,
    HardDrive,
    Shield,
    Clock,
    Cloud,
    FileBarChart2,
    Building2
} from "lucide-react";
import { authFetch } from "@/lib/auth";
import { sanitize } from "@/lib/sanitize";
import { useLoadingGuard } from "@/lib/hooks/useSecurityHooks";

// Types
interface UploadedFile {
    name: string;
    size: number;
    type: string;
    status: "pending" | "validating" | "ready" | "error";
    error?: string;
    records?: number;
}

type DestinationType = "qbo" | "caseware" | null;

// Constants
const SUPPORTED_FORMATS = [
    { ext: ".QBW", name: "QuickBooks Company File", description: "Primary data file (recommended)" },
    { ext: ".QBB", name: "QuickBooks Backup", description: "Backup file format" },
    { ext: ".QBM", name: "QuickBooks Portable", description: "Smaller portable file" },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024; // 5GB

/**
 * Validate QuickBooks file extension
 * SECURITY: Prevents double-extension attacks
 */
function isValidQBFile(fileName: string): { valid: boolean; error?: string } {
    const normalizedName = fileName.trim().toLowerCase();
    const validExtensions = ['.qbw', '.qbb', '.qbm'];

    // Check for valid extension
    const hasValidExtension = validExtensions.some(ext => normalizedName.endsWith(ext));
    if (!hasValidExtension) {
        return { valid: false, error: 'Invalid file type. Please upload a .QBW, .QBB, or .QBM file.' };
    }

    // Reject files with multiple extensions (common attack vector)
    const extensionCount = (normalizedName.match(/\.[a-z0-9]+/g) || []).length;
    if (extensionCount > 1) {
        return { valid: false, error: 'Files with multiple extensions are not allowed for security reasons.' };
    }

    return { valid: true };
}

/**
 * Format file size for display
 */
function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

/**
 * File Status Badge Component
 */
function FileStatusBadge({ status, error }: { status: string; error?: string }) {
    switch (status) {
        case "validating":
            return (
                <span className="badge badge-warning flex items-center gap-1">
                    <Clock className="w-3 h-3 animate-spin" />
                    Validating
                </span>
            );
        case "ready":
            return (
                <span className="badge badge-success flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    Ready
                </span>
            );
        case "error":
            return (
                <span className="badge badge-error flex items-center gap-1" title={error}>
                    <AlertCircle className="w-3 h-3" />
                    Error
                </span>
            );
        default:
            return null;
    }
}

/**
 * Destination Card Component
 */
function DestinationCard({
    type,
    title,
    description,
    tags,
    selected,
    onSelect,
    color,
    icon: Icon,
}: {
    type: DestinationType;
    title: string;
    description: string;
    tags: { label: string; color: string }[];
    selected: boolean;
    onSelect: () => void;
    color: string;
    icon: React.ComponentType<{ className?: string }>;
}) {
    const borderColor = selected ? `border-${color}-500` : 'border-gray-200';
    const bgColor = selected ? `bg-${color}-50` : '';
    const ringColor = selected ? `ring-2 ring-${color}-200` : '';
    const iconBgColor = selected ? `bg-${color}-500` : `bg-${color}-100`;
    const iconTextColor = selected ? 'text-white' : `text-${color}-600`;

    return (
        <button
            onClick={onSelect}
            className={`p-6 rounded-xl border-2 text-left transition-all ${borderColor} ${bgColor} ${ringColor} hover:border-${color}-300 hover:bg-gray-50`}
        >
            <div className="flex items-start gap-4">
                <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${iconBgColor}`}>
                    <Icon className={`w-7 h-7 ${iconTextColor}`} />
                </div>
                <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 text-lg">{title}</h3>
                    <p className="text-sm text-gray-600 mt-1">{description}</p>
                    <div className="flex flex-wrap gap-2 mt-3">
                        {tags.map((tag) => (
                            <span key={tag.label} className={`text-xs ${tag.color} px-2 py-1 rounded`}>
                                {tag.label}
                            </span>
                        ))}
                    </div>
                </div>
                {selected && (
                    <CheckCircle2 className={`w-6 h-6 text-${color}-500`} />
                )}
            </div>
        </button>
    );
}

export default function UploadPage() {
    const [isDragActive, setIsDragActive] = useState(false);
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const [destination, setDestination] = useState<DestinationType>(null);
    const [migrationError, setMigrationError] = useState<string | null>(null);

    // Loading guard to prevent double-clicks
    const { isLoading: isProcessing, execute } = useLoadingGuard();

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsDragActive(true);
        } else if (e.type === "dragleave") {
            setIsDragActive(false);
        }
    }, []);

    const processFile = async (file: File) => {
        // Validate file
        const validation = isValidQBFile(file.name);
        if (!validation.valid) {
            const uploadedFile: UploadedFile = {
                name: sanitize.filename(file.name),
                size: file.size,
                type: file.name.split('.').pop()?.toUpperCase() || "UNKNOWN",
                status: "error",
                error: validation.error,
            };
            setFiles(prev => [...prev, uploadedFile]);
            return;
        }

        // Check file size
        if (file.size > MAX_FILE_SIZE) {
            const uploadedFile: UploadedFile = {
                name: sanitize.filename(file.name),
                size: file.size,
                type: file.name.split('.').pop()?.toUpperCase() || "UNKNOWN",
                status: "error",
                error: "File too large. Maximum size is 5GB.",
            };
            setFiles(prev => [...prev, uploadedFile]);
            return;
        }

        const uploadedFile: UploadedFile = {
            name: sanitize.filename(file.name),
            size: file.size,
            type: file.name.split('.').pop()?.toUpperCase() || "UNKNOWN",
            status: "validating"
        };

        setFiles(prev => [...prev, uploadedFile]);

        // Validate with server
        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await authFetch(`${API_URL}/api/upload/validate`, {
                method: 'POST',
                body: formData,
                headers: {}, // Don't set Content-Type for FormData
            });

            if (response.ok) {
                const data = await response.json();
                setFiles(prev => prev.map(f =>
                    f.name === uploadedFile.name
                        ? { ...f, status: "ready", records: data.record_count || data.records || 0 }
                        : f
                ));
            } else {
                const errorData = await response.json().catch(() => ({ error: 'Validation failed' }));
                setFiles(prev => prev.map(f =>
                    f.name === uploadedFile.name
                        ? { ...f, status: "error", error: errorData.error || 'Validation failed' }
                        : f
                ));
            }
        } catch {
            setFiles(prev => prev.map(f =>
                f.name === uploadedFile.name
                    ? { ...f, status: "error", error: 'Failed to connect to validation server' }
                    : f
            ));
        }
    };

    const handleDrop = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsDragActive(false);

        const droppedFiles = Array.from(e.dataTransfer.files);
        droppedFiles.forEach(processFile);
    }, []);

    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        const selectedFiles = Array.from(e.target.files || []);
        selectedFiles.forEach(processFile);
    };

    const removeFile = (name: string) => {
        setFiles(prev => prev.filter(f => f.name !== name));
    };

    const readyFiles = files.filter(f => f.status === "ready");

    const handleStartMigration = async () => {
        if (!destination || readyFiles.length === 0) return;

        setMigrationError(null);

        const result = await execute(async () => {
            const response = await authFetch(`${API_URL}/api/migrations`, {
                method: 'POST',
                body: JSON.stringify({
                    destination,
                    files: readyFiles.map(f => f.name)
                }),
            });

            if (response.ok) {
                const data = await response.json();
                const migrationId = data.migration_id || data.id;
                if (migrationId) {
                    window.location.href = `/migrations/${migrationId}`;
                }
                return { success: true };
            } else {
                const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
                return { success: false, error: errorData.error || "Failed to start migration" };
            }
        });

        if (result && !result.success) {
            setMigrationError(result.error || "Failed to start migration. Please try again.");
        }
    };

    return (
        <div className="space-y-6">
            {/* Error toast for migration errors */}
            {migrationError && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center justify-between">
                    <div className="flex items-center gap-2 text-red-700">
                        <AlertCircle className="w-5 h-5" />
                        {migrationError}
                    </div>
                    <button
                        onClick={() => setMigrationError(null)}
                        className="text-red-500 hover:text-red-700 text-sm"
                    >
                        Dismiss
                    </button>
                </div>
            )}

            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Upload Files</h1>
                <p className="text-gray-500 mt-1">Upload QuickBooks Desktop files for migration</p>
            </div>

            {/* STEP 1: Choose Destination */}
            <div className="card-forensic p-6">
                <div className="flex items-center gap-3 mb-6">
                    <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold">
                        1
                    </div>
                    <h2 className="text-lg font-semibold text-gray-900">Choose Your Destination</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* QuickBooks Online Option */}
                    <button
                        onClick={() => setDestination("qbo")}
                        className={`p-6 rounded-xl border-2 text-left transition-all ${
                            destination === "qbo"
                                ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                                : "border-gray-200 hover:border-blue-300 hover:bg-gray-50"
                        }`}
                    >
                        <div className="flex items-start gap-4">
                            <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
                                destination === "qbo" ? "bg-blue-500" : "bg-blue-100"
                            }`}>
                                <Cloud className={`w-7 h-7 ${destination === "qbo" ? "text-white" : "text-blue-600"}`} />
                            </div>
                            <div className="flex-1">
                                <h3 className="font-semibold text-gray-900 text-lg">QuickBooks Online</h3>
                                <p className="text-sm text-gray-600 mt-1">
                                    Migrate your data directly to QuickBooks Online (Intuit cloud)
                                </p>
                                <div className="flex flex-wrap gap-2 mt-3">
                                    <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded">Live Migration</span>
                                    <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">OAuth Secure</span>
                                </div>
                            </div>
                            {destination === "qbo" && (
                                <CheckCircle2 className="w-6 h-6 text-blue-500" />
                            )}
                        </div>
                    </button>

                    {/* Caseware Option */}
                    <button
                        onClick={() => setDestination("caseware")}
                        className={`p-6 rounded-xl border-2 text-left transition-all ${
                            destination === "caseware"
                                ? "border-purple-500 bg-purple-50 ring-2 ring-purple-200"
                                : "border-gray-200 hover:border-purple-300 hover:bg-gray-50"
                        }`}
                    >
                        <div className="flex items-start gap-4">
                            <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${
                                destination === "caseware" ? "bg-purple-500" : "bg-purple-100"
                            }`}>
                                <FileBarChart2 className={`w-7 h-7 ${destination === "caseware" ? "text-white" : "text-purple-600"}`} />
                            </div>
                            <div className="flex-1">
                                <h3 className="font-semibold text-gray-900 text-lg">Caseware Working Papers</h3>
                                <p className="text-sm text-gray-600 mt-1">
                                    Export audit-ready files for Caseware or OnPoint DAS
                                </p>
                                <div className="flex flex-wrap gap-2 mt-3">
                                    <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">Audit Bundle</span>
                                    <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded">58 Lead Sheets</span>
                                </div>
                            </div>
                            {destination === "caseware" && (
                                <CheckCircle2 className="w-6 h-6 text-purple-500" />
                            )}
                        </div>
                    </button>
                </div>

                {/* Caseware Details */}
                {destination === "caseware" && (
                    <div className="mt-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                        <h4 className="font-medium text-purple-900 mb-2">Caseware Audit Bundle Includes:</h4>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
                            <div className="flex items-center gap-2 text-purple-700">
                                <CheckCircle2 className="w-4 h-4" />
                                <span><code>Audit_TB.csv</code> - Trial Balance</span>
                            </div>
                            <div className="flex items-center gap-2 text-purple-700">
                                <CheckCircle2 className="w-4 h-4" />
                                <span><code>Audit_GL.csv</code> - General Ledger</span>
                            </div>
                            <div className="flex items-center gap-2 text-purple-700">
                                <CheckCircle2 className="w-4 h-4" />
                                <span><code>Audit_Mapping.cvw</code> - Column Config</span>
                            </div>
                        </div>
                        <p className="text-xs text-purple-600 mt-3">
                            All files include SHA-256 forensic integrity hashes and pre-mapped Lead Sheet codes.
                        </p>
                    </div>
                )}
            </div>

            {/* STEP 2: Upload Files */}
            <div className={`card-forensic p-6 transition-opacity ${!destination ? "opacity-50 pointer-events-none" : ""}`}>
                <div className="flex items-center gap-3 mb-6">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${
                        destination ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-400"
                    }`}>
                        2
                    </div>
                    <h2 className="text-lg font-semibold text-gray-900">Upload QuickBooks Desktop File</h2>
                </div>

                {/* Drag & Drop Zone */}
                <div
                    className={`drop-zone ${isDragActive ? "active" : ""}`}
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                >
                    <div className="w-16 h-16 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4">
                        <Upload className="w-8 h-8 text-[var(--bridge-blue)]" />
                    </div>
                    <p className="text-lg font-medium text-gray-700 mb-1">
                        Drag & Drop your QuickBooks file here
                    </p>
                    <p className="text-sm text-gray-400 mb-4">Supports .QBW, .QBB, .QBM (max 5GB)</p>
                    <label className="btn-primary cursor-pointer">
                        Select File
                        <input
                            type="file"
                            accept=".qbw,.qbb,.qbm"
                            className="hidden"
                            onChange={handleFileSelect}
                        />
                    </label>
                </div>
            </div>

            {/* Uploaded Files */}
            {files.length > 0 && (
                <div className="card-forensic">
                    <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
                        <h2 className="font-semibold text-gray-900">Uploaded Files</h2>
                        <span className="text-sm text-gray-500">{files.length} file(s)</span>
                    </div>

                    <div className="divide-y divide-gray-100">
                        {files.map((file) => (
                            <div key={file.name} className="p-4 flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center">
                                        <FileSpreadsheet className="w-5 h-5 text-[var(--bridge-blue)]" />
                                    </div>
                                    <div>
                                        <p className="font-medium text-gray-900">{file.name}</p>
                                        <p className="text-sm text-gray-500">
                                            {formatSize(file.size)} {file.type}
                                            {file.records && ` - ${file.records.toLocaleString()} records`}
                                        </p>
                                        {file.error && (
                                            <p className="text-xs text-red-500 mt-1">{file.error}</p>
                                        )}
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    <FileStatusBadge status={file.status} error={file.error} />
                                    <button
                                        onClick={() => removeFile(file.name)}
                                        className="p-1.5 hover:bg-gray-100 rounded"
                                        aria-label={`Remove ${file.name}`}
                                    >
                                        <X className="w-4 h-4 text-gray-400" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>

                    {readyFiles.length > 0 && destination && (
                        <div className="px-6 py-4 border-t border-gray-100 flex items-center justify-between bg-gray-50">
                            <div>
                                <p className="text-sm text-gray-600">
                                    {readyFiles.length} file(s) ready
                                </p>
                                <p className="text-xs text-gray-500">
                                    Destination: <span className="font-medium">
                                        {destination === "qbo" ? "QuickBooks Online" : "Caseware Working Papers"}
                                    </span>
                                </p>
                            </div>
                            <button
                                onClick={handleStartMigration}
                                disabled={isProcessing}
                                className={`btn-primary flex items-center gap-2 ${
                                    destination === "caseware" ? "!bg-purple-600 hover:!bg-purple-700" : ""
                                } disabled:opacity-50 disabled:cursor-not-allowed`}
                            >
                                {isProcessing ? (
                                    <>
                                        <Clock className="w-4 h-4 animate-spin" />
                                        Processing...
                                    </>
                                ) : destination === "qbo" ? (
                                    <>
                                        Migrate to QBO <Cloud className="w-4 h-4" />
                                    </>
                                ) : (
                                    <>
                                        Generate Caseware Bundle <FileBarChart2 className="w-4 h-4" />
                                    </>
                                )}
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* How It Works */}
            <div className="card-forensic p-6">
                <h3 className="font-semibold text-gray-900 mb-4 flex items-center gap-2">
                    <Building2 className="w-5 h-5" />
                    How It Works: QuickBooks Desktop → {destination === "caseware" ? "Caseware" : "Your Destination"}
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-2">
                            <span className="font-bold text-blue-600">1</span>
                        </div>
                        <p className="font-medium text-sm">Extract</p>
                        <p className="text-xs text-gray-500">QBDesktopReader extracts 55 entity types from .QBW file</p>
                    </div>
                    <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-2">
                            <span className="font-bold text-green-600">2</span>
                        </div>
                        <p className="font-medium text-sm">Hash & Encrypt</p>
                        <p className="text-xs text-gray-500">SHA-256 forensic hash per record, AES-256 encryption</p>
                    </div>
                    <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center mx-auto mb-2">
                            <span className="font-bold text-purple-600">3</span>
                        </div>
                        <p className="font-medium text-sm">Transform</p>
                        <p className="text-xs text-gray-500">Server decrypts, verifies hashes, transforms data</p>
                    </div>
                    <div className="text-center p-4 bg-gray-50 rounded-lg">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 ${
                            destination === "caseware" ? "bg-purple-100" : "bg-amber-100"
                        }`}>
                            <span className={`font-bold ${destination === "caseware" ? "text-purple-600" : "text-amber-600"}`}>4</span>
                        </div>
                        <p className="font-medium text-sm">
                            {destination === "caseware" ? "Export Bundle" : "Push to QBO"}
                        </p>
                        <p className="text-xs text-gray-500">
                            {destination === "caseware"
                                ? "Generate Audit_TB.csv, Audit_GL.csv with Lead Sheets"
                                : "Push to QuickBooks Online via OAuth API"
                            }
                        </p>
                    </div>
                </div>
            </div>

            {/* Security Info */}
            <div className="card-forensic p-6 bg-green-50 border-green-200">
                <div className="flex items-start gap-4">
                    <div className="w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <Shield className="w-5 h-5 text-green-600" />
                    </div>
                    <div>
                        <h3 className="font-semibold text-green-900">Forensic Data Integrity</h3>
                        <p className="text-sm text-green-700 mt-1">
                            Every record is SHA-256 hashed at extraction time. These hashes are verified after decryption
                            to ensure <strong>zero data modification</strong> during transfer.
                            {destination === "caseware" && " All hashes are included in your Caseware bundle."}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
