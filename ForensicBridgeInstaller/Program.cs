using System;
using System.Windows.Forms;

namespace ForensicBridgeInstaller
{
    static class Program
    {
        /// <summary>
        /// The main entry point for the application.
        /// </summary>
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            // Parse command line arguments
            string sessionCode = null;
            bool autoStart = false;

            for (int i = 0; i < args.Length; i++)
            {
                if ((args[i] == "--session" || args[i] == "-s") && i + 1 < args.Length)
                {
                    sessionCode = args[i + 1];
                    i++;
                }
                else if (args[i] == "--auto")
                {
                    autoStart = true;
                }
            }

            Application.Run(new MainForm(sessionCode, autoStart));
        }
    }
}
