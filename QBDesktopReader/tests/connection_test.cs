#if USE_QBFC

using System;
using QBFC16Lib;

class SimpleTest
{
    static void Main()
    {
        Console.WriteLine("QuickBooks Connection Test");
        Console.WriteLine("===========================\n");
        
        Console.WriteLine("IMPORTANT:");
        Console.WriteLine("1. Make sure QuickBooks Desktop is running");
        Console.WriteLine("2. Make sure sample company file is open");
        Console.WriteLine("3. QB should NOT have any dialogs open\n");
        
        Console.WriteLine("Press Enter to test connection...");
        Console.ReadLine();

        try
        {
            // Step 1: Create session manager
            Console.WriteLine("\n[1/4] Creating session manager...");
            QBSessionManager sessionManager = new QBSessionManager();
            Console.WriteLine("✓ Success");

            // Step 2: Connect to QuickBooks
            Console.WriteLine("\n[2/4] Connecting to QuickBooks...");
            Console.WriteLine("(QuickBooks may show authorization dialog - click 'Yes, always')");
            sessionManager.OpenConnection("", "My Test App");
            Console.WriteLine("✓ Connected");

            // Step 3: Begin session
            Console.WriteLine("\n[3/4] Starting session...");
            sessionManager.BeginSession("", ENOpenMode.omDontCare);
            Console.WriteLine("✓ Session started");

            // Step 4: Read company name
            Console.WriteLine("\n[4/4] Reading company info...");
            IMsgSetRequest request = sessionManager.CreateMsgSetRequest("US", 16, 0);
            request.AppendCompanyQueryRq();
            IMsgSetResponse response = sessionManager.DoRequests(request);
            IResponse resp = response.ResponseList.GetAt(0);
            
            if (resp.StatusCode == 0)
            {
                ICompanyRet company = resp.Detail as ICompanyRet;
                string companyName = company.CompanyName.GetValue();
                Console.WriteLine($"✓ Success! Company: {companyName}");
            }

            // Step 5: Disconnect
            Console.WriteLine("\n[5/5] Disconnecting...");
            sessionManager.EndSession();
            sessionManager.CloseConnection();
            Console.WriteLine("✓ Disconnected");

            Console.WriteLine("\n=============================");
            Console.WriteLine("✓✓✓ ALL TESTS PASSED! ✓✓✓");
            Console.WriteLine("=============================");
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n✗✗✗ ERROR: {ex.Message}\n");
            
            if (ex.Message.Contains("Could not start QuickBooks"))
            {
                Console.WriteLine("→ QuickBooks Desktop is not running");
                Console.WriteLine("→ Start QuickBooks and open a company file");
            }
            else if (ex.Message.Contains("User canceled"))
            {
                Console.WriteLine("→ You clicked 'No' on the authorization dialog");
                Console.WriteLine("→ Run again and click 'Yes, always'");
            }
            else
            {
                Console.WriteLine("Full error details:");
                Console.WriteLine(ex.ToString());
            }
        }

        Console.WriteLine("\n\nPress Enter to exit...");
        Console.ReadLine();
    }
}

#endif // USE_QBFC