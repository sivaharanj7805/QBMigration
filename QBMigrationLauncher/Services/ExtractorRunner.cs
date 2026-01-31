using System;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace QBMigrationLauncher.Services
{
    public class ExtractorRunner
    {
        private readonly LogParser _parser;

        // FIX #4: Pattern to detect potentially dangerous characters in arguments
        private static readonly Regex UnsafePathChars = new Regex(@"[""<>|&;`$]", RegexOptions.Compiled);

        // FIX #4: Process timeout for large company files
        // FIX LOW: Use constant from centralized location
        private static readonly TimeSpan ProcessTimeout = Constants.Timeouts.ProcessExecution;

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

            // FIX #1: Define event handlers as named delegates for proper unsubscription
            DataReceivedEventHandler outputHandler = (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    _parser.ProcessLogLine(e.Data);
            };
            DataReceivedEventHandler errorHandler = (s, e) =>
            {
                if (!string.IsNullOrEmpty(e.Data))
                    _parser.ProcessLogLine($"ERROR: {e.Data}");
            };

            try
            {
                process.OutputDataReceived += outputHandler;
                process.ErrorDataReceived += errorHandler;

                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();

                // FIX #4: Add timeout to WaitForExit with process.Kill() on timeout
                bool exited = await Task.Run(() => process.WaitForExit((int)ProcessTimeout.TotalMilliseconds));

                if (!exited)
                {
                    // Process timed out - kill it
                    try
                    {
                        process.Kill(entireProcessTree: true);
                    }
                    catch (InvalidOperationException)
                    {
                        // Process already exited
                    }
                    throw new TimeoutException(
                        $"Migration engine timed out after {ProcessTimeout.TotalMinutes} minutes and was terminated");
                }

                if (process.ExitCode != 0)
                {
                    throw new Exception($"Migration engine failed with code {process.ExitCode}");
                }

                // FIX MEDIUM: Verify extraction output files after completion
                VerifyExtractionOutput(outputDir);
            }
            finally
            {
                // FIX #1: Unsubscribe event handlers before disposing to prevent resource leak
                process.OutputDataReceived -= outputHandler;
                process.ErrorDataReceived -= errorHandler;
            }
        }

        /// <summary>
        /// FIX MEDIUM: Verify that extraction produced expected output files.
        /// This helps catch silent failures where the process exits successfully
        /// but doesn't produce the expected output.
        /// </summary>
        private void VerifyExtractionOutput(string outputDir)
        {
            if (string.IsNullOrEmpty(outputDir))
                return;

            var extractedDir = Path.Combine(outputDir, Constants.Migration.ExtractedDirectoryName);

            // Check if extracted directory exists
            if (!Directory.Exists(extractedDir))
            {
                _parser.ProcessLogLine("[WARN] Extraction completed but 'extracted' directory not found. Files may be in root output directory.");
                return;
            }

            // Check for expected output files
            // FIX LOW: Use constants for file patterns
            var ndjsonFiles = Directory.GetFiles(extractedDir, $"*{Constants.FileOps.NdjsonExtension}");
            var manifestFile = Path.Combine(extractedDir, Constants.Migration.ManifestFileName);

            if (ndjsonFiles.Length == 0)
            {
                _parser.ProcessLogLine("[WARN] No NDJSON data files found in extraction output.");
            }
            else
            {
                _parser.ProcessLogLine($"[INFO] Verified extraction output: {ndjsonFiles.Length} data file(s) found.");
            }

            // Check for manifest file
            if (File.Exists(manifestFile))
            {
                try
                {
                    var manifestInfo = new FileInfo(manifestFile);
                    if (manifestInfo.Length > 0)
                    {
                        _parser.ProcessLogLine("[INFO] Extraction manifest verified.");
                    }
                    else
                    {
                        _parser.ProcessLogLine("[WARN] Extraction manifest file is empty.");
                    }
                }
                catch (Exception ex)
                {
                    _parser.ProcessLogLine($"[WARN] Could not verify manifest file: {ex.Message}");
                }
            }
            else
            {
                _parser.ProcessLogLine("[WARN] Extraction manifest (run_manifest.json) not found.");
            }

            // Check for errors file
            // FIX LOW: Use constant for errors file name
            var errorsFile = Path.Combine(extractedDir, Constants.Migration.ErrorsFileName);
            if (File.Exists(errorsFile))
            {
                try
                {
                    var errorLines = File.ReadAllLines(errorsFile);
                    if (errorLines.Length > 0)
                    {
                        _parser.ProcessLogLine($"[WARN] Extraction completed with {errorLines.Length} error(s). Check errors.ndjson for details.");
                    }
                }
                catch (Exception ex)
                {
                    _parser.ProcessLogLine($"[WARN] Could not read errors file: {ex.Message}");
                }
            }
        }

        /// <summary>
        /// FIX #4: Safely build command line arguments with proper escaping.
        /// FIX #3: Use proper Windows escaping - double quotes are escaped by doubling them.
        /// </summary>
        private static string BuildArguments(string? companyFile, string sessionCode, string outputDir)
        {
            // FIX #3: Escape embedded quotes by doubling them (correct Windows convention)
            // Windows cmd.exe uses "" to escape quotes inside quoted strings
            string EscapeArg(string? arg) =>
                (arg ?? "").Replace("\"", "\"\"");

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

        /// <summary>
        /// FIX #18: Removed development fallback path for production security.
        /// Only searches production deployment locations.
        /// </summary>
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

            // FIX #18: Removed development fallback path - only production paths allowed
            throw new FileNotFoundException(
                $"Could not find migration engine ({exeName}). Searched:\n" +
                $"  Production: {productionPath}\n" +
                $"  Install: {installPath}");
        }
    }
}
