using System;
using System.Linq;
using System.Management;
using System.Net.NetworkInformation;
using System.Security.Cryptography;
using System.Text;

namespace QBDesktopExtractor
{
    /// <summary>
    /// Hardware Fingerprint Generator
    /// Creates a unique machine identifier for license binding
    ///
    /// Uses combination of:
    /// - CPU ID
    /// - Disk Serial Number
    /// - Primary MAC Address
    /// - Windows Product ID
    /// </summary>
    public static class HardwareFingerprint
    {
        // Cache the fingerprint to avoid expensive WMI calls
        // FIX CRIT-05: Add volatile keyword for proper double-check locking pattern
        private static volatile string _cachedFingerprint;
        private static readonly object _cacheLock = new object();

        // VM adapter indicators (case-insensitive)
        private static readonly string[] VirtualAdapterKeywords = new[]
        {
            "virtual", "vmware", "hyper-v", "virtualbox", "vbox",
            "xen", "qemu", "kvm", "docker", "parallels", "vpc"
        };

        /// <summary>
        /// Generate a unique hardware fingerprint for this machine.
        /// Results are cached for performance.
        /// </summary>
        /// <returns>Base64-encoded SHA256 hash of hardware identifiers</returns>
        public static string Generate()
        {
            // Return cached value if available
            if (_cachedFingerprint != null)
            {
                return _cachedFingerprint;
            }

            lock (_cacheLock)
            {
                // Double-check after acquiring lock
                if (_cachedFingerprint != null)
                {
                    return _cachedFingerprint;
                }

                _cachedFingerprint = GenerateInternal();
                return _cachedFingerprint;
            }
        }

        /// <summary>
        /// Force regeneration of fingerprint (clears cache)
        /// </summary>
        public static string Regenerate()
        {
            lock (_cacheLock)
            {
                _cachedFingerprint = null;
            }
            return Generate();
        }

        private static string GenerateInternal()
        {
            var components = new StringBuilder();
            
            try
            {
                // CPU ID
                components.Append(GetCpuId());
            }
            catch (Exception)
            {
                components.Append("CPU_UNKNOWN");
            }
            
            try
            {
                // Disk Serial (first fixed disk)
                components.Append(GetDiskSerial());
            }
            catch (Exception)
            {
                components.Append("DISK_UNKNOWN");
            }
            
            try
            {
                // Primary MAC Address
                components.Append(GetPrimaryMacAddress());
            }
            catch (Exception)
            {
                components.Append("MAC_UNKNOWN");
            }
            
            try
            {
                // Windows Product ID
                components.Append(GetWindowsProductId());
            }
            catch (Exception)
            {
                components.Append("WIN_UNKNOWN");
            }
            
            // Hash the combined string
            using (var sha256 = SHA256.Create())
            {
                var hashBytes = sha256.ComputeHash(Encoding.UTF8.GetBytes(components.ToString()));
                return Convert.ToBase64String(hashBytes);
            }
        }
        
        /// <summary>
        /// Get CPU Processor ID via WMI
        /// </summary>
        private static string GetCpuId()
        {
            using (var searcher = new ManagementObjectSearcher("SELECT ProcessorId FROM Win32_Processor"))
            {
                // SECURITY FIX: Properly dispose ManagementObject instances to prevent WMI resource leaks
                foreach (ManagementObject obj in searcher.Get())
                {
                    using (obj)
                    {
                        var processorId = obj["ProcessorId"]?.ToString();
                        if (!string.IsNullOrEmpty(processorId))
                        {
                            return processorId;
                        }
                    }
                }
            }
            return "CPU_FALLBACK";
        }
        
        /// <summary>
        /// Get primary disk serial number via WMI
        /// </summary>
        private static string GetDiskSerial()
        {
            using (var searcher = new ManagementObjectSearcher("SELECT SerialNumber FROM Win32_DiskDrive WHERE Index = 0"))
            {
                // SECURITY FIX: Properly dispose ManagementObject instances to prevent WMI resource leaks
                foreach (ManagementObject obj in searcher.Get())
                {
                    using (obj)
                    {
                        var serial = obj["SerialNumber"]?.ToString()?.Trim();
                        if (!string.IsNullOrEmpty(serial))
                        {
                            return serial;
                        }
                    }
                }
            }
            return "DISK_FALLBACK";
        }
        
        /// <summary>
        /// Get primary network adapter MAC address
        /// Filters out virtual/VM adapters for more stable fingerprinting
        /// </summary>
        private static string GetPrimaryMacAddress()
        {
            var allInterfaces = NetworkInterface.GetAllNetworkInterfaces()
                .Where(nic => nic.OperationalStatus == OperationalStatus.Up
                           && nic.NetworkInterfaceType != NetworkInterfaceType.Loopback
                           && nic.NetworkInterfaceType != NetworkInterfaceType.Tunnel)
                .ToList();

            // Filter function to check if adapter is virtual
            bool IsVirtualAdapter(NetworkInterface nic)
            {
                string descLower = nic.Description.ToLowerInvariant();
                return VirtualAdapterKeywords.Any(keyword => descLower.Contains(keyword));
            }

            // First try to find a non-virtual adapter
            var physicalInterface = allInterfaces
                .Where(nic => !IsVirtualAdapter(nic))
                .OrderByDescending(nic => nic.Speed)
                .FirstOrDefault();

            // If all adapters are virtual (VM environment), use the fastest one
            // This ensures VMs still get a fingerprint, just based on virtual adapter
            if (physicalInterface == null)
            {
                physicalInterface = allInterfaces
                    .OrderByDescending(nic => nic.Speed)
                    .FirstOrDefault();
            }

            if (physicalInterface != null)
            {
                var macBytes = physicalInterface.GetPhysicalAddress().GetAddressBytes();
                if (macBytes.Length > 0)
                {
                    return BitConverter.ToString(macBytes).Replace("-", "");
                }
            }

            return "MAC_FALLBACK";
        }
        
        /// <summary>
        /// Get Windows Product ID from registry
        /// </summary>
        private static string GetWindowsProductId()
        {
            try
            {
                using (var key = Microsoft.Win32.Registry.LocalMachine.OpenSubKey(
                    @"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
                {
                    var productId = key?.GetValue("ProductId")?.ToString();
                    if (!string.IsNullOrEmpty(productId))
                    {
                        return productId;
                    }
                }
            }
            catch (System.Security.SecurityException)
            {
                // Registry access may fail
            }
            catch (UnauthorizedAccessException)
            {
                // Registry access denied
            }

            return "WIN_FALLBACK";
        }
        
        /// <summary>
        /// Get a truncated fingerprint for display purposes
        /// </summary>
        public static string GetDisplayFingerprint()
        {
            var full = Generate();
            if (full.Length > 12)
            {
                return full.Substring(0, 12) + "...";
            }
            return full;
        }
    }
}
