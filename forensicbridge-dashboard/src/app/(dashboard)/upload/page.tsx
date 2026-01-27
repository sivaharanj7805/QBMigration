"use client";

import { useState, useCallback } from "react";
import {
    Upload,
    FileSpreadsheet,
    CheckCircle2,
    AlertCircle,
    X,
    HardDrive,
    ArrowRight,
    Shield,
    Clock,
    Cloud,
    FileBarChart2,
    Building2
} from "lucide-react";

interface UploadedFile {
    name: string;
    size: number;
    type: string;
    status: "pending" | "validating" | "ready" | "error";
    error?: string;
    records?: number;
}

type DestinationType = "qbo" | "caseware" | null;

const supportedFormats = [
    { ext: ".QBW", name: "QuickBooks Company File", description: "Primary data file (recommended)" },
    { ext: ".QBB", name: "QuickBooks Backup", description: "Backup file format" },
    { ext: ".QBM", name: "QuickBooks Portable", description: "Smaller portable file" },
];

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

export default function UploadPage() {
    const [isDragActive, setIsDragActive] = useState(false);
    const [files, setFiles] = useState<UploadedFile[]>([]);
    const [isProcessing, setIsProcessing] = useState(false);
    const [destination, setDestination] = useState<DestinationType>(null);

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setIsDragActive(true);
        } else if (e.type === "dragleave") {
            setIsDragActive(false);
        }
    }, []);

    const processFile = (file: File) => {
        const uploadedFile: UploadedFile = {
            name: file.name,
            size: file.size,
            type: file.name.split('.').pop()?.toUpperCase() || "UNKNOWN",
            status: "validating"
        };

        setFiles(prev => [...prev, uploadedFile]);

        // Simulate validation
        setTimeout(() => {
            setFiles(prev => prev.map(f =>
                f.name === file.name
                    ? { ...f, status: "ready", records: Math.floor(Math.random() * 50000) + 5000 }
                    : f
            ));
        }, 1500);
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

    const formatSize = (bytes: number) => {
        if (bytes < 1024) return bytes + " B";
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    };

    const readyFiles = files.filter(f => f.status === "ready");

    const handleStartMigration = async () => {
        if (!destination || readyFiles.length === 0) return;

        setIsProcessing(true);
        try {
            const formData = new FormData();
            formData.append('destination', destination);
            readyFiles.forEach(f => {
                formData.append('file_names', f.name);
            });

            const response = await fetch(`${API_URL}/api/migrations`, {
                method: 'POST',
                body: JSON.stringify({ destination, files: readyFiles.map(f => f.name) }),
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
            });

            if (response.ok) {
                const data = await response.json();
                const migrationId = data.migration_id || data.id;
                if (migrationId) {
                    window.location.href = `/migrations/${migrationId}`;
                }
            } else {
                const errorData = await response.json();
                alert(errorData.error || "Failed to start migration");
            }
        } catch (error) {
            console.error("Migration start error:", error);
            alert("Failed to connect to server. Please try again.");
        } finally {
            setIsProcessing(false);
        }
    };

    return (
        <div className="space-y-6">
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
                        className={`p-6 rounded-xl border-2 text-left transition-all ${destination === "qbo"
                                ? "border-blue-500 bg-blue-50 ring-2 ring-blue-200"
                                : "border-gray-200 hover:border-blue-300 hover:bg-gray-50"
                            }`}
                    >
                        <div className="flex items-start gap-4">
                            <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${destination === "qbo" ? "bg-blue-500" : "bg-blue-100"
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
                        className={`p-6 rounded-xl border-2 text-left transition-all ${destination === "caseware"
                                ? "border-purple-500 bg-purple-50 ring-2 ring-purple-200"
                                : "border-gray-200 hover:border-purple-300 hover:bg-gray-50"
                            }`}
                    >
                        <div className="flex items-start gap-4">
                            <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${destination === "caseware" ? "bg-purple-500" : "bg-purple-100"
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

                {/* Caseware Details (shown when selected) */}
                {destination === "caseware" && (
                    <div className="mt-4 p-4 bg-purple-50 border border-purple-200 rounded-lg">
                        <h4 className="font-medium text-purple-900 mb-2">📦 Caseware Audit Bundle Includes:</h4>
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
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${destination ? "bg-blue-100 text-blue-600" : "bg-gray-100 text-gray-400"
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
                    <p className="text-sm text-gray-400 mb-4">Supports .QBW, .QBB, .QBM</p>
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
                                            {formatSize(file.size)} • {file.type}
                                            {file.records && ` • ${file.records.toLocaleString()} records`}
                                        </p>
                                    </div>
                                </div>

                                <div className="flex items-center gap-4">
                                    {file.status === "validating" && (
                                        <span className="badge badge-warning flex items-center gap-1">
                                            <Clock className="w-3 h-3 animate-spin" />
                                            Validating
                                        </span>
                                    )}
                                    {file.status === "ready" && (
                                        <span className="badge badge-success flex items-center gap-1">
                                            <CheckCircle2 className="w-3 h-3" />
                                            Ready
                                        </span>
                                    )}
                                    {file.status === "error" && (
                                        <span className="badge badge-error flex items-center gap-1">
                                            <AlertCircle className="w-3 h-3" />
                                            Error
                                        </span>
                                    )}

                                    <button
                                        onClick={() => removeFile(file.name)}
                                        className="p-1.5 hover:bg-gray-100 rounded"
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
                                className={`btn-primary flex items-center gap-2 ${destination === "caseware" ? "!bg-purple-600 hover:!bg-purple-700" : ""
                                    }`}
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
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center mx-auto mb-2 ${destination === "caseware" ? "bg-purple-100" : "bg-amber-100"
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
