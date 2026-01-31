using System;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading.Tasks;

namespace QBMigrationLauncher.Services
{
    public class ExtractorRunner
    {
        private readonly LogParser _parser;

        // FIX #4: Pattern to detect potentially dangerous characters in arguments
        private static readonly Regex UnsafePathChars = new Regex(@"[""<>|&;`$]", RegexOptions.Compiled);

        public ExtractorRunner(LogParser parser)
        {
            _parser = parser;
        }

        /// <summary>
        /// Run extraction with all required parameters.
        /// </summary>
        public async Task RunExtractionAsync(string? companyFile, string sessionCode, string outputDir)
        {
            // FIX #4: Validate and sanitize inputs to prevent command injection
            ValidateArgument(companyFile, nameof(companyFile));
            ValidateArgument(sessionCode, nameof(sessionCode));
            ValidateArgument(outputDir, nameof(outputDir));

            // Resolve QBExtractor.exe path with production-first priority:
            // 1. Next to the launcher (production deployment)
            // 2. Standard install path
            // 3. Development fallback
            string exePath = ResolveExtractorPath();

            // FIX #35: Ensure working directory is not null
            string? workingDir = Path.GetDirectoryName(exePath);
            if (string.IsNullOrEmpty(workingDir))
            {
                workingDir = AppDomain.CurrentDomain.BaseDirectory;
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = exePath,
                Arguments = BuildArguments(companyFile, sessionCode, outputDir),
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                WorkingDirectory = workingDir
            };

            using var process = new Process { StartInfo = startInfo };

            process.OutputDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    _parser.ProcessLogLine(e.Data);
            };
            process.ErrorDataReceived += (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    _parser.ProcessLogLine($"ERROR: {e.Data}");
            };

            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            await Task.Run(() => process.WaitForExit());

            if (process.ExitCode != 0)
            {
                throw new Exception($"Migration engine failed with code {process.ExitCode}");
            }
        }

        /// <summary>
        /// FIX #4: Safely build command line arguments with proper escaping.
        /// </summary>
        private static string BuildArguments(string? companyFile, string sessionCode, string outputDir)
        {
            // Escape embedded quotes by doubling them (Windows convention)
            string EscapeArg(string? arg) =>
                (arg ?? "").Replace("\"", "\\\"");

            return $"--company-file \"{EscapeArg(companyFile)}\" " +
                   $"--session \"{EscapeArg(sessionCode)}\" " +
                   $"--no-pause --auto-incremental " +
                   $"--output-dir \"{EscapeArg(outputDir)}\"";
        }

        /// <summary>
        /// FIX #4: Validate argument doesn't contain dangerous characters.
        /// </summary>
        private static void ValidateArgument(string? value, string paramName)
        {
            if (string.IsNullOrEmpty(value))
                return; // Null/empty is handled elsewhere

            if (UnsafePathChars.IsMatch(value))
            {
                throw new ArgumentException(
                    $"Parameter '{paramName}' contains invalid characters. " +
                    $"Path cannot contain: \" < > | & ; ` $", paramName);
            }
        }

        private static string ResolveExtractorPath()
        {
            const string exeName = "QBExtractor.exe";

            // 1. Production: next to the launcher executable
            string productionPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, exeName);
            if (File.Exists(productionPath))
            {
                return Path.GetFullPath(productionPath);
            }

            // 2. Standard install path
            string installPath = Path.Combine(@"C:\Program Files\ForensicBridge", exeName);
            if (File.Exists(installPath))
            {
                return installPath;
            }

            // 3. Development fallback
            string devPath = Path.GetFullPath(Path.Combine(
                AppDomain.CurrentDomain.BaseDirectory,
                @"..\..\..\..\QBDesktopReader\bin\Debug\net48",
                exeName));
            if (File.Exists(devPath))
            {
                return devPath;
            }

            throw new FileNotFoundException(
                $"Could not find migration engine ({exeName}). Searched:\n" +
                $"  Production: {productionPath}\n" +
                $"  Install: {installPath}\n" +
                $"  Dev: {devPath}");
        }
    }
}
