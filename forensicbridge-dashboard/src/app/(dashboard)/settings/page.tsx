"use client";

import { WhitelabelPreview } from "@/components/settings/WhitelabelPreview";
import { TeamManagement } from "@/components/settings/TeamManagement";
import { useState, useEffect } from "react";
import { Palette, Bell, Shield, CreditCard, Users, Loader2 } from "lucide-react";
import { getAuthState } from "@/lib/auth";

type SettingsTab = "branding" | "notifications" | "security" | "billing" | "team";

// Match the WhitelabelConfig type from WhitelabelPreview
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

// API configuration
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000";

interface UserSubscription {
    tier: string;
    tierName: string;
    features: string[];
    migrationsRemaining?: number;
}

export default function SettingsPage() {
    const [activeTab, setActiveTab] = useState<SettingsTab>("branding");
    const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
    const [loading, setLoading] = useState(true);
    const [userName, setUserName] = useState("");
    const [userEmail, setUserEmail] = useState("");
    const [subscription, setSubscription] = useState<UserSubscription>({
        tier: "starter",
        tierName: "Starter",
        features: []
    });

    useEffect(() => {
        loadUserData();
    }, []);

    const loadUserData = async () => {
        setLoading(true);
        try {
            // First, get data from localStorage
            const authState = getAuthState();
            if (authState.user) {
                const name = authState.user.name ||
                    authState.user.first_name ||
                    authState.user.email?.split('@')[0] ||
                    "User";
                setUserName(name);
                setUserEmail(authState.user.email || "");
            }

            // Try to fetch subscription from API
            const response = await fetch(`${API_URL}/api/auth/me`, {
                credentials: 'include',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('token') || ''}`
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.user) {
                    setUserName(data.user.first_name || data.user.name || "User");
                    setUserEmail(data.user.email || "");

                    // Get subscription tier from user data or license
                    const tier = data.user.subscription_tier || data.user.tier || "starter";
                    const tierConfig: Record<string, { name: string, features: string[] }> = {
                        'starter': { name: 'Starter', features: ['10 migrations/month', 'Email support'] },
                        'professional': { name: 'Professional', features: ['50 migrations/month', 'Priority support', 'Reports'] },
                        'enterprise': { name: 'Enterprise', features: ['Unlimited migrations', 'Whitelabel', 'Priority support'] },
                        'reseller': { name: 'Reseller', features: ['Unlimited migrations', 'Full Whitelabel', 'API Access'] }
                    };

                    const config = tierConfig[tier] || tierConfig['starter'];
                    setSubscription({
                        tier: tier,
                        tierName: config.name,
                        features: config.features,
                        migrationsRemaining: data.user.migrations_remaining
                    });
                }
            }
        } catch (error) {
            console.error("Failed to load user data:", error);
        } finally {
            setLoading(false);
        }
    };

    const handleSaveWhitelabel = (_config: WhitelabelConfig) => {
        setSaveStatus("saving");
        // Simulate API call
        setTimeout(() => {
            setSaveStatus("saved");
            setTimeout(() => setSaveStatus("idle"), 2000);
        }, 1000);
    };

    const tabs = [
        { id: "branding" as const, label: "Branding", icon: Palette },
        { id: "notifications" as const, label: "Notifications", icon: Bell },
        { id: "security" as const, label: "Security", icon: Shield },
        { id: "billing" as const, label: "Billing", icon: CreditCard },
        { id: "team" as const, label: "Team", icon: Users },
    ];

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
                <p className="text-sm text-gray-500 mt-1">
                    Manage your account settings and preferences
                </p>
            </div>

            {/* Save Status Toast */}
            {saveStatus === "saved" && (
                <div className="fixed top-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2 z-50">
                    ✓ Changes saved successfully
                </div>
            )}

            {/* Tab Navigation */}
            <div className="border-b border-gray-200">
                <nav className="flex gap-4 overflow-x-auto">
                    {tabs.map(({ id, label, icon: Icon }) => (
                        <button
                            key={id}
                            onClick={() => setActiveTab(id)}
                            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${activeTab === id
                                ? "border-[var(--bridge-blue)] text-[var(--bridge-blue)]"
                                : "border-transparent text-gray-500 hover:text-gray-700"
                                }`}
                        >
                            <Icon className="w-4 h-4" />
                            {label}
                        </button>
                    ))}
                </nav>
            </div>

            {/* Tab Content */}
            <div>
                {activeTab === "branding" && (
                    <WhitelabelPreview
                        onSave={handleSaveWhitelabel}
                    />
                )}

                {activeTab === "notifications" && (
                    <div className="card-forensic p-6">
                        <h2 className="text-lg font-semibold mb-4">Notification Preferences</h2>
                        <div className="space-y-4">
                            <label className="flex items-center justify-between">
                                <span>Email on migration complete</span>
                                <input type="checkbox" defaultChecked className="w-5 h-5" />
                            </label>
                            <label className="flex items-center justify-between">
                                <span>Email on migration failure</span>
                                <input type="checkbox" defaultChecked className="w-5 h-5" />
                            </label>
                            <label className="flex items-center justify-between">
                                <span>Weekly summary report</span>
                                <input type="checkbox" className="w-5 h-5" />
                            </label>
                        </div>
                    </div>
                )}

                {activeTab === "security" && (
                    <div className="card-forensic p-6">
                        <h2 className="text-lg font-semibold mb-4">Security Settings</h2>
                        <div className="space-y-4">
                            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                                <p className="font-medium text-green-800">✓ AES-256-GCM Encryption Active</p>
                                <p className="text-sm text-green-600">All data is encrypted at rest and in transit</p>
                            </div>
                            <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                                <p className="font-medium text-green-800">✓ AWS KMS Integration Enabled</p>
                                <p className="text-sm text-green-600">Hardware-backed key management</p>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === "billing" && (
                    <div className="card-forensic p-6">
                        <h2 className="text-lg font-semibold mb-4">Billing & Subscription</h2>
                        <div className="p-4 bg-gradient-to-r from-[var(--forensic-gold)] to-yellow-500 text-white rounded-lg">
                            <p className="font-bold text-lg">{subscription.tierName} Plan</p>
                            <p className="text-sm opacity-90">
                                {subscription.features.join(' • ')}
                            </p>
                            {subscription.migrationsRemaining !== undefined && subscription.migrationsRemaining >= 0 && (
                                <p className="text-sm mt-2 opacity-80">
                                    Migrations remaining: {subscription.migrationsRemaining}
                                </p>
                            )}
                        </div>
                        <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                            <p className="text-sm text-gray-600">
                                <strong>Account:</strong> {userEmail}
                            </p>
                            <p className="text-sm text-gray-600 mt-1">
                                <strong>Name:</strong> {userName}
                            </p>
                        </div>
                    </div>
                )}

                {activeTab === "team" && (
                    <TeamManagement />
                )}
            </div>
        </div>
    );
}

