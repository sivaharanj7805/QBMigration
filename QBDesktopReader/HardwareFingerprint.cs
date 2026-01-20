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
        /// <summary>
        /// Generate a unique hardware fingerprint for this machine
        /// </summary>
        /// <returns>Base64-encoded SHA256 hash of hardware identifiers</returns>
        public static string Generate()
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
                foreach (ManagementObject obj in searcher.Get())
                {
                    var processorId = obj["ProcessorId"]?.ToString();
                    if (!string.IsNullOrEmpty(processorId))
                    {
                        return processorId;
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
                foreach (ManagementObject obj in searcher.Get())
                {
                    var serial = obj["SerialNumber"]?.ToString()?.Trim();
                    if (!string.IsNullOrEmpty(serial))
                    {
                        return serial;
                    }
                }
            }
            return "DISK_FALLBACK";
        }
        
        /// <summary>
        /// Get primary network adapter MAC address
        /// </summary>
        private static string GetPrimaryMacAddress()
        {
            var networkInterface = NetworkInterface.GetAllNetworkInterfaces()
                .Where(nic => nic.OperationalStatus == OperationalStatus.Up 
                           && nic.NetworkInterfaceType != NetworkInterfaceType.Loopback
                           && nic.NetworkInterfaceType != NetworkInterfaceType.Tunnel
                           && !nic.Description.ToLower().Contains("virtual")
                           && !nic.Description.ToLower().Contains("vmware")
                           && !nic.Description.ToLower().Contains("hyper-v"))
                .OrderByDescending(nic => nic.Speed)
                .FirstOrDefault();
            
            if (networkInterface != null)
            {
                var macBytes = networkInterface.GetPhysicalAddress().GetAddressBytes();
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
            catch
            {
                // Registry access may fail
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
