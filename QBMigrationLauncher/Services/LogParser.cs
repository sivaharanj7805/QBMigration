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

        public void ProcessLogLine(string line)
        {
            if (string.IsNullOrWhiteSpace(line)) return;

            LogReceived?.Invoke(this, line);

            // Parse progress based on log patterns i observed in code
            // Example: "[ 9/25] Payment Methods" or "Extracting Accounts..."
            
            if (line.Contains("[") && line.Contains("]"))
            {
                // Try to parse entity counting [X/Y]
                var match = Regex.Match(line, @"\[\s*(\d+)/(\d+)\]");
                if (match.Success)
                {
                    if (int.TryParse(match.Groups[1].Value, out int current) && 
                        int.TryParse(match.Groups[2].Value, out int total))
                    {
                        // Calculate percentage
                        // List phase is roughly 50% of work
                        int percent = (int)((double)current / total * 50); 
                        if (line.Contains("SEQUENTIAL MODE")) percent += 50; // Use offset?
                        
                        // Heuristic progress
                        NotifyProgress(percent, line);
                    }
                }
            }
            else if (line.Contains("Extracting"))
            {
                NotifyProgress(-1, line); // Just update text
            }
            else if (line.Contains("SUCCESS"))
            {
                NotifyProgress(100, "Migration Complete");
            }
        }

        private void NotifyProgress(int percent, string message)
        {
             ProgressChanged?.Invoke(this, new ProgressEventArgs 
             { 
                 Percentage = percent >= 0 ? percent : 0, // Keep previous if -1? simplified for MVP
                 StatusMessage = message
             });
        }
    }
}
