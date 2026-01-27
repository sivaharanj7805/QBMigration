using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;

namespace QBMigrationLauncher.Services
{
    public class ExtractorRunner
    {
        private readonly LogParser _parser;

        public ExtractorRunner(LogParser parser)
        {
            _parser = parser;
        }

        public async Task RunExtractionAsync(string? companyFile, string sessionCode, string outputDir)
        {
            // Resolve QBExtractor.exe path with production-first priority:
            // 1. Next to the launcher (production deployment)
            // 2. Standard install path
            // 3. Development fallback
            string exePath = ResolveExtractorPath();

            var startInfo = new ProcessStartInfo
            {
                FileName = exePath,
                Arguments = $"--company-file \"{companyFile}\" --session \"{sessionCode}\" --no-pause --auto-incremental --output-dir \"{outputDir}\"",
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                WorkingDirectory = Path.GetDirectoryName(exePath)
            };

            using var process = new Process { StartInfo = startInfo };
            
            process.OutputDataReceived += (s, e) => _parser.ProcessLogLine(e.Data);
            process.ErrorDataReceived += (s, e) => _parser.ProcessLogLine($"ERROR: {e.Data}");

            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            await Task.Run(() => process.WaitForExit());

            if (process.ExitCode != 0)
            {
                throw new Exception($"Migration engine failed with code {process.ExitCode}");
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
