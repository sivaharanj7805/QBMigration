"use client";

import { useState, useRef } from "react";
import {
    Upload,
    Eye,
    Save,
    RefreshCw,
    Shield,
    CheckCircle,
    Zap,
    Building2
} from "lucide-react";

interface WhitelabelConfig {
    company_name: string;
    logo_url: string | null;
    primary_color: string;
    secondary_color: string;
    accent_color: string;
    support_email: string;
    support_phone: string;
    website_url: string;
}

interface WhitelabelPreviewProps {
    initialConfig?: Partial<WhitelabelConfig>;
    onSave?: (config: WhitelabelConfig) => void;
    isEnterprise?: boolean;
}

const DEFAULT_CONFIG: WhitelabelConfig = {
    company_name: "ForensicBridge",
    logo_url: "/new-logo.png",
    primary_color: "#3B82F6",
    secondary_color: "#0F172A",
    accent_color: "#B8860B",
    support_email: "support@forensicbridge.ca",
    support_phone: "",
    website_url: "https://forensicbridge.ca"
};

export function WhitelabelPreview({
    initialConfig,
    onSave,
    isEnterprise = true
}: WhitelabelPreviewProps) {
    const [config, setConfig] = useState<WhitelabelConfig>({
        ...DEFAULT_CONFIG,
        ...initialConfig
    });
    const [previewLogo, setPreviewLogo] = useState<string | null>(config.logo_url);
    const [isPreviewMode, setIsPreviewMode] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                const dataUrl = event.target?.result as string;
                setPreviewLogo(dataUrl);
                setConfig(prev => ({ ...prev, logo_url: dataUrl }));
            };
            reader.readAsDataURL(file);
        }
    };

    const handleReset = () => {
        setConfig(DEFAULT_CONFIG);
        setPreviewLogo(null);
    };

    const handleSave = () => {
        onSave?.(config);
    };

    // Generate CSS variables from config
    const previewStyles = {
        "--preview-primary": config.primary_color,
        "--preview-secondary": config.secondary_color,
        "--preview-accent": config.accent_color,
    } as React.CSSProperties;

    if (!isEnterprise) {
        return (
            <div className="card-forensic p-8 text-center">
                <Building2 className="w-16 h-16 mx-auto text-gray-300 mb-4" />
                <h2 className="text-xl font-semibold mb-2">Enterprise Feature</h2>
                <p className="text-gray-500 mb-4">
                    White-labeling is available on Enterprise and Reseller plans.
                </p>
                <button className="px-6 py-3 bg-gradient-to-r from-[#F59E0B] to-[#D97706] text-white font-medium rounded-lg">
                    Upgrade to Enterprise
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-xl font-semibold">Brand Customization</h2>
                    <p className="text-sm text-gray-500">
                        Preview how ForensicBridge will appear with your branding
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setIsPreviewMode(!isPreviewMode)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg border transition-colors ${isPreviewMode
                            ? "bg-[var(--bridge-blue)] text-white border-[var(--bridge-blue)]"
                            : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
                            }`}
                    >
                        <Eye className="w-4 h-4" />
                        {isPreviewMode ? "Exit Preview" : "Preview"}
                    </button>
                    <button
                        onClick={handleReset}
                        className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50"
                    >
                        <RefreshCw className="w-4 h-4" />
                        Reset
                    </button>
                    <button
                        onClick={handleSave}
                        className="flex items-center gap-2 px-4 py-2 bg-[var(--bridge-blue)] text-white rounded-lg hover:bg-[var(--bridge-blue)]/90"
                    >
                        <Save className="w-4 h-4" />
                        Save Changes
                    </button>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Configuration Panel */}
                <div className="card-forensic p-6 space-y-6">
                    <h3 className="font-semibold text-lg">Configuration</h3>

                    {/* Logo Upload */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Company Logo
                        </label>
                        <div className="flex items-center gap-4">
                            <div
                                className="w-20 h-20 rounded-lg border-2 border-dashed border-gray-300 flex items-center justify-center bg-gray-50 cursor-pointer hover:border-[var(--bridge-blue)] transition-colors"
                                onClick={() => fileInputRef.current?.click()}
                            >
                                {previewLogo ? (
                                    <img
                                        src={previewLogo}
                                        alt="Logo"
                                        className="w-full h-full object-contain rounded-lg"
                                    />
                                ) : (
                                    <Upload className="w-6 h-6 text-gray-400" />
                                )}
                            </div>
                            <div>
                                <button
                                    onClick={() => fileInputRef.current?.click()}
                                    className="text-sm text-[var(--bridge-blue)] hover:underline"
                                >
                                    Upload Logo
                                </button>
                                <p className="text-xs text-gray-500 mt-1">
                                    PNG, JPG up to 2MB. Recommended: 200x200px
                                </p>
                            </div>
                            <input
                                ref={fileInputRef}
                                type="file"
                                accept="image/*"
                                onChange={handleLogoUpload}
                                className="hidden"
                            />
                        </div>
                    </div>

                    {/* Company Name */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Company Name
                        </label>
                        <input
                            type="text"
                            value={config.company_name}
                            onChange={(e) => setConfig(prev => ({ ...prev, company_name: e.target.value }))}
                            className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                            placeholder="Your Company Name"
                        />
                    </div>

                    {/* Colors */}
                    <div className="grid grid-cols-3 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Primary Color
                            </label>
                            <div className="flex items-center gap-2">
                                <input
                                    type="color"
                                    value={config.primary_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, primary_color: e.target.value }))}
                                    className="w-10 h-10 rounded cursor-pointer"
                                />
                                <input
                                    type="text"
                                    value={config.primary_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, primary_color: e.target.value }))}
                                    className="flex-1 px-2 py-1 border border-gray-200 rounded text-sm font-mono"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Secondary Color
                            </label>
                            <div className="flex items-center gap-2">
                                <input
                                    type="color"
                                    value={config.secondary_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, secondary_color: e.target.value }))}
                                    className="w-10 h-10 rounded cursor-pointer"
                                />
                                <input
                                    type="text"
                                    value={config.secondary_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, secondary_color: e.target.value }))}
                                    className="flex-1 px-2 py-1 border border-gray-200 rounded text-sm font-mono"
                                />
                            </div>
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Accent Color
                            </label>
                            <div className="flex items-center gap-2">
                                <input
                                    type="color"
                                    value={config.accent_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, accent_color: e.target.value }))}
                                    className="w-10 h-10 rounded cursor-pointer"
                                />
                                <input
                                    type="text"
                                    value={config.accent_color}
                                    onChange={(e) => setConfig(prev => ({ ...prev, accent_color: e.target.value }))}
                                    className="flex-1 px-2 py-1 border border-gray-200 rounded text-sm font-mono"
                                />
                            </div>
                        </div>
                    </div>

                    {/* Contact Info */}
                    <div className="grid grid-cols-2 gap-4">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Support Email
                            </label>
                            <input
                                type="email"
                                value={config.support_email}
                                onChange={(e) => setConfig(prev => ({ ...prev, support_email: e.target.value }))}
                                className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                                placeholder="support@yourfirm.com"
                            />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">
                                Support Phone
                            </label>
                            <input
                                type="tel"
                                value={config.support_phone}
                                onChange={(e) => setConfig(prev => ({ ...prev, support_phone: e.target.value }))}
                                className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--bridge-blue)]"
                                placeholder="1-800-555-0123"
                            />
                        </div>
                    </div>
                </div>

                {/* Live Preview Panel */}
                <div className="card-forensic overflow-hidden" style={previewStyles}>
                    <div
                        className="p-4 text-white"
                        style={{ backgroundColor: config.secondary_color }}
                    >
                        <div className="flex items-center gap-3">
                            {previewLogo ? (
                                <img src={previewLogo} alt="Logo" className="w-8 h-8 object-contain" />
                            ) : (
                                <Shield className="w-8 h-8" style={{ color: config.accent_color }} />
                            )}
                            <span className="font-semibold">{config.company_name} Migration Suite</span>
                        </div>
                    </div>

                    <div className="p-6 space-y-4">
                        {/* Preview Stat Cards */}
                        <div className="grid grid-cols-2 gap-3">
                            <div
                                className="p-4 rounded-lg text-white"
                                style={{ backgroundColor: config.primary_color }}
                            >
                                <p className="text-2xl font-bold">127</p>
                                <p className="text-sm opacity-80">Migrations</p>
                            </div>
                            <div
                                className="p-4 rounded-lg text-white"
                                style={{ backgroundColor: config.accent_color }}
                            >
                                <p className="text-2xl font-bold">98.5%</p>
                                <p className="text-sm opacity-80">Success Rate</p>
                            </div>
                        </div>

                        {/* Preview Shield */}
                        <div
                            className="p-4 rounded-lg border-2"
                            style={{ borderColor: config.accent_color }}
                        >
                            <div className="flex items-center justify-between mb-3">
                                <span className="font-medium">Reconciliation Shield</span>
                                <span
                                    className="px-3 py-1 rounded-full text-xs font-bold text-white"
                                    style={{ backgroundColor: config.accent_color }}
                                >
                                    ✓ VERIFIED
                                </span>
                            </div>
                            <div className="flex justify-between text-sm">
                                <div>
                                    <p className="text-gray-500">Source</p>
                                    <p className="font-bold">$1,450,220</p>
                                </div>
                                <div className="text-center">
                                    <CheckCircle
                                        className="w-6 h-6 mx-auto"
                                        style={{ color: config.primary_color }}
                                    />
                                </div>
                                <div className="text-right">
                                    <p className="text-gray-500">Destination</p>
                                    <p className="font-bold">$1,450,220</p>
                                </div>
                            </div>
                        </div>

                        {/* Preview Button */}
                        <button
                            className="w-full py-3 rounded-lg text-white font-medium flex items-center justify-center gap-2"
                            style={{ backgroundColor: config.primary_color }}
                        >
                            <Zap className="w-4 h-4" />
                            Start New Migration
                        </button>

                        {/* Preview Footer */}
                        <div className="text-center text-xs text-gray-500 pt-2 border-t">
                            Powered by {config.company_name} | {config.support_email}
                        </div>
                    </div>
                </div>
            </div>

            {/* Generated CSS */}
            <div className="card-forensic p-4">
                <h3 className="font-medium mb-2">Generated CSS Variables</h3>
                <pre className="text-xs bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto">
                    {`:root {
  --brand-primary: ${config.primary_color};
  --brand-secondary: ${config.secondary_color};
  --brand-accent: ${config.accent_color};
  --brand-name: "${config.company_name}";
}`}
                </pre>
            </div>
        </div>
    );
}
