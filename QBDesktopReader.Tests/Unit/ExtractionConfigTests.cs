using System;
using System.IO;
using System.Runtime.InteropServices;
using FluentAssertions;
using Xunit;
using QBDesktopExtractor;

namespace QBDesktopReader.Tests.Unit
{
    public class ExtractionConfigTests : IDisposable
    {
        private readonly string _testDir;

        // P/Invoke for creating symlinks on .NET Framework 4.8 (Windows only)
        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        private static extern bool CreateSymbolicLink(string lpSymlinkFileName, string lpTargetFileName, int dwFlags);

        private const int SYMBOLIC_LINK_FLAG_FILE = 0x0;

        public ExtractionConfigTests()
        {
            _testDir = Path.Combine(Path.GetTempPath(), $"config_test_{Guid.NewGuid():N}");
            Directory.CreateDirectory(_testDir);
        }

        public void Dispose()
        {
            try
            {
                if (Directory.Exists(_testDir))
                    Directory.Delete(_testDir, recursive: true);
            }
            catch
            {
                // Best effort cleanup
            }
        }

        // ================================================================
        // MEDIUM-12 Fix: Path Traversal Detection
        // ================================================================

        [Fact]
        public void LoadFromFile_PathWithDotDot_ThrowsConfigurationException()
        {
            // This validates the MEDIUM-12 fix: paths containing ".." (path traversal)
            // must be rejected to prevent directory traversal attacks that could
            // read or write files outside the intended directory.

            // Arrange
            string maliciousPath = Path.Combine(_testDir, "..", "..", "etc", "passwd.json");

            // Act
            Action act = () => ExtractionConfig.LoadFromFile(maliciousPath);

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("Path traversal",
                    because: "paths with '..' must be rejected as potential traversal attacks");
        }

        [Fact]
        public void LoadFromFile_PathWithEmbeddedDotDot_ThrowsConfigurationException()
        {
            // Arrange - path traversal embedded in the middle
            string maliciousPath = Path.Combine(_testDir, "subdir", "..", "..", "secret.json");

            // Act
            Action act = () => ExtractionConfig.LoadFromFile(maliciousPath);

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("Path traversal");
        }

        // ================================================================
        // Symlink / Reparse Point Rejection
        // ================================================================

        [Fact]
        public void LoadFromFile_SymlinkReparsePoint_ThrowsConfigurationException()
        {
            // This test validates that symlink reparse points are detected and rejected.
            // We create a real symlink to test the reparse point detection.
            // Note: Symlink creation may require elevated privileges on Windows.

            // Arrange
            string realFile = Path.Combine(_testDir, "real_config.json");
            File.WriteAllText(realFile, "{\"serverUrl\": \"https://api.example.com\"}");

            string symlinkPath = Path.Combine(_testDir, "symlink_config.json");

            // Only run symlink test on Windows (requires kernel32)
            if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                return;

            try
            {
                // Try creating a symlink via P/Invoke (may fail without admin privileges)
                bool created = CreateSymbolicLink(symlinkPath, realFile, SYMBOLIC_LINK_FLAG_FILE);
                if (!created)
                {
                    // Symlink creation failed (likely no admin privileges); skip test
                    return;
                }
            }
            catch (Exception)
            {
                // Skip test if symlink creation is not supported
                return;
            }

            // Verify the symlink was actually created as a reparse point
            var linkInfo = new FileInfo(symlinkPath);
            if (!linkInfo.Exists || (linkInfo.Attributes & FileAttributes.ReparsePoint) == 0)
            {
                // Symlink was not created as a reparse point; skip
                return;
            }

            // Act
            Action act = () => ExtractionConfig.LoadFromFile(symlinkPath);

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("symbolic link",
                    because: "symlinks could redirect config loading to malicious files");
        }

        // ================================================================
        // Valid Paths Accepted
        // ================================================================

        [Fact]
        public void LoadFromFile_ValidPathToExistingConfig_LoadsSuccessfully()
        {
            // Arrange - create a valid config file
            string configPath = Path.Combine(_testDir, "valid_config.json");
            string configJson = @"{
                ""serverUrl"": ""https://api.example.com"",
                ""version"": ""4.2"",
                ""schemaVersion"": ""4.2""
            }";
            File.WriteAllText(configPath, configJson);

            // Act
            var config = ExtractionConfig.LoadFromFile(configPath);

            // Assert
            config.Should().NotBeNull();
            config.ServerUrl.Should().Be("https://api.example.com");
        }

        [Fact]
        public void LoadFromFile_ValidPathToMissingFile_ThrowsConfigurationException()
        {
            // Arrange
            string missingPath = Path.Combine(_testDir, "does_not_exist.json");

            // Act
            Action act = () => ExtractionConfig.LoadFromFile(missingPath);

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("not found");
        }

        // ================================================================
        // Validate Method
        // ================================================================

        [Fact]
        public void Validate_ValidConfig_DoesNotThrow()
        {
            // Arrange
            var config = ExtractionConfig.CreateDefault();

            // Act
            Action act = () => config.Validate();

            // Assert
            act.Should().NotThrow();
        }

        [Fact]
        public void Validate_MissingServerUrl_ThrowsConfigurationException()
        {
            // Arrange
            var config = new ExtractionConfig { ServerUrl = null };

            // Act
            Action act = () => config.Validate();

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("serverUrl");
        }

        [Fact]
        public void Validate_HttpUrlForNonLocalhost_ThrowsConfigurationException()
        {
            // Arrange
            var config = new ExtractionConfig
            {
                ServerUrl = "http://api.production.com",
                Advanced = new AdvancedSettings { AllowInsecureHttpForLocalhost = false }
            };

            // Act
            Action act = () => config.Validate();

            // Assert
            act.Should().Throw<ConfigurationException>()
                .Which.Message.Should().Contain("HTTPS");
        }

        [Fact]
        public void Validate_HttpsLocalhostUrl_DoesNotThrow()
        {
            // Arrange - localhost is allowed with HTTP
            var config = new ExtractionConfig
            {
                ServerUrl = "http://localhost:8080"
            };

            // Act
            Action act = () => config.Validate();

            // Assert
            act.Should().NotThrow(
                because: "localhost URLs are allowed to use HTTP for development");
        }

        [Fact]
        public void LoadFromFile_EmptyPath_ThrowsConfigurationException()
        {
            // Act
            Action act = () => ExtractionConfig.LoadFromFile("");

            // Assert
            act.Should().Throw<ConfigurationException>();
        }

        [Fact]
        public void LoadFromFile_WhitespacePath_ThrowsConfigurationException()
        {
            // Act
            Action act = () => ExtractionConfig.LoadFromFile("   ");

            // Assert
            act.Should().Throw<ConfigurationException>();
        }
    }
}
