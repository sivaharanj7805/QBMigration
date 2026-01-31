using System;
using System.Text.RegularExpressions;

namespace QBMigrationLauncher.Services
{
    public class ProgressEventArgs : EventArgs
    {
        public int Percentage { get; set; }
        public string StatusMessage { get; set; } = "";
    }

    public class LogParser
    {
        public event EventHandler<ProgressEventArgs>? ProgressChanged;
        public event EventHandler<string>? LogReceived;

        // FIX #24 & #25: Track current progress state
        private int _currentPercentage = 0;
        private bool _inSequentialMode = false;

        // FIX #12: Pre-compiled regex for better performance and to catch compile errors early
        private static readonly Regex ProgressPattern = new Regex(@"\[\s*(\d+)/(\d+)\]", RegexOptions.Compiled);

        public void ProcessLogLine(string? line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;

            // FIX #12: Wrap in try-catch to prevent log parsing from crashing the app
            try
            {
                LogReceived?.Invoke(this, line);

                // Parse progress based on log patterns
                // Example: "[ 9/25] Payment Methods" or "Extracting Accounts..."

                // FIX #24: Detect sequential mode transition (second phase of extraction)
                if (line.Contains("SEQUENTIAL MODE") || line.Contains("Writing") || line.Contains("Uploading"))
                {
                    _inSequentialMode = true;
                }

                if (line.Contains("[") && line.Contains("]"))
                {
                    // Try to parse entity counting [X/Y]
                    var match = ProgressPattern.Match(line);
                    if (match.Success)
                    {
                        if (int.TryParse(match.Groups[1].Value, out int current) &&
                            int.TryParse(match.Groups[2].Value, out int total) &&
                            total > 0)
                        {
                            // FIX #24: Calculate percentage properly
                            // List extraction phase = 0-50%, Writing/Upload phase = 50-100%
                            double phaseProgress = (double)current / total;
                            int percent;

                            if (_inSequentialMode)
                            {
                                // Second phase: 50% to 95%
                                percent = 50 + (int)(phaseProgress * 45);
                            }
                            else
                            {
                                // First phase: 0% to 50%
                                percent = (int)(phaseProgress * 50);
                            }

                            _currentPercentage = Math.Min(percent, 95); // Cap at 95% until SUCCESS
                            NotifyProgress(_currentPercentage, line);
                        }
                    }
                }
                else if (line.Contains("Extracting"))
                {
                    // FIX #25: Just update text, keep current percentage
                    NotifyProgress(_currentPercentage, line);
                }
                else if (line.Contains("SUCCESS") || line.Contains("Complete"))
                {
                    _currentPercentage = 100;
                    NotifyProgress(100, "Migration Complete");
                }
                else if (line.Contains("ERROR") || line.Contains("FAILED"))
                {
                    // Don't change percentage on error, just update message
                    NotifyProgress(_currentPercentage, line);
                }
            }
            catch (Exception ex)
            {
                // FIX #12: Log parsing errors should not crash the application
                System.Diagnostics.Debug.WriteLine($"[LogParser] Error parsing line: {ex.Message}");
            }
        }

        /// <summary>
        /// Reset parser state for a new extraction.
        /// </summary>
        public void Reset()
        {
            _currentPercentage = 0;
            _inSequentialMode = false;
        }

        private void NotifyProgress(int percent, string message)
        {
            ProgressChanged?.Invoke(this, new ProgressEventArgs
            {
                Percentage = percent,
                StatusMessage = message
            });
        }
    }
}
