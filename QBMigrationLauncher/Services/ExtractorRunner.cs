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

        public async Task RunExtractionAsync(string? companyFile)
        {
            // Find exe (Assuming strictly relative path for now)
            // In dev: ..\..\..\QBDesktopReader\bin\Debug\net48\QBExtractor.exe
            // In prod: .\QBExtractor.exe
            
            string exePath = "QBExtractor.exe";
            if (!File.Exists(exePath))
            {
                // Fallback for dev environment
                exePath = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"..\..\..\..\QBDesktopReader\bin\Debug\net48\QBExtractor.exe"));
            }

            if (!File.Exists(exePath))
            {
                 // Try one more common spot
                 exePath = Path.GetFullPath(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"QBExtractor.exe"));
            }

            // If still not found, search? For MVP, fail.
            if (!File.Exists(exePath))
            {
                throw new FileNotFoundException($"Could not find migration engine at: {exePath}");
            }

            var startInfo = new ProcessStartInfo
            {
                FileName = exePath,
                Arguments = "--no-pause --auto-incremental", // Auto-run flags
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
    }
}
