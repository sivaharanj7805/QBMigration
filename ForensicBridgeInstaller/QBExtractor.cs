using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace ForensicBridgeInstaller
{
    /// <summary>
    /// QuickBooks Desktop Extractor using late binding (COM interop).
    /// Compiles without QBFC16 installed, uses it at runtime if available.
    /// </summary>
    public class QBExtractor : IDisposable
    {
        private dynamic? _sessionManager;
        private bool _sessionOpen;
        private readonly Action<string> _logCallback;
        private readonly Action<int> _progressCallback;

        public Dictionary<string, int> EntityCounts { get; private set; } = new Dictionary<string, int>();
        public string CompanyName { get; private set; } = "";
        public string QBVersion { get; private set; } = "";

        public QBExtractor(Action<string>? logCallback = null, Action<int>? progressCallback = null)
        {
            _logCallback = logCallback ?? (msg => { });
            _progressCallback = progressCallback ?? (pct => { });
        }

        /// <summary>
        /// Check if QuickBooks SDK (QBFC16) is installed
        /// </summary>
        public static bool IsQBFCInstalled()
        {
            try
            {
                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                return qbType != null;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Check if QuickBooks Desktop is running
        /// </summary>
        public static bool IsQuickBooksRunning()
        {
            try
            {
                var processes = System.Diagnostics.Process.GetProcessesByName("QBW32");
                return processes.Length > 0;
            }
            catch
            {
                return false;
            }
        }

        /// <summary>
        /// Initialize connection to QuickBooks
        /// </summary>
        public bool Initialize()
        {
            try
            {
                _logCallback("Initializing QBFC16 session manager...");

                var qbType = Type.GetTypeFromProgID("QBFC16.QBSessionManager");
                if (qbType == null)
                {
                    _logCallback("ERROR: QBFC16 not found. Please install the QuickBooks SDK.");
                    return false;
                }

                _sessionManager = Activator.CreateInstance(qbType);
                _logCallback("Session manager created successfully.");

                return true;
            }
            catch (COMException ex)
            {
                _logCallback($"COM Error initializing QBFC: {ex.Message}");
                return false;
            }
            catch (Exception ex)
            {
                _logCallback($"Error initializing QBFC: {ex.Message}");
                return false;
            }
        }

        /// <summary>
        /// Open a session to QuickBooks
        /// </summary>
        public bool OpenSession()
        {
            try
            {
                _logCallback("Opening connection to QuickBooks...");
                _logCallback("Please authorize ForensicBridge in QuickBooks if prompted.");

                // OpenConnection2: appID="", appName="ForensicBridge", connType=1 (localQBD)
                _sessionManager!.OpenConnection2("", "ForensicBridge", 1);

                // BeginSession: companyFile="" (use currently open), openMode=2 (omDontCare)
                _sessionManager.BeginSession("", 2);

                _sessionOpen = true;
                _logCallback("Connected to QuickBooks successfully!");

                GetCompanyInfo();

                return true;
            }
            catch (COMException ex)
            {
                var hrString = $"0x{ex.ErrorCode:X8}";
                _logCallback($"QuickBooks connection error ({hrString}): {ex.Message}");

                if (ex.ErrorCode == unchecked((int)0x80040408))
                {
                    _logCallback("The QuickBooks company file is not open. Please open QuickBooks first.");
                }
                else if (ex.ErrorCode == unchecked((int)0x80040401))
                {
                    _logCallback("Access denied. Please authorize ForensicBridge in QuickBooks.");
                }

                return false;
            }
            catch (Exception ex)
            {
                _logCallback($"Failed to connect: {ex.Message}");
                return false;
            }
        }

        private void GetCompanyInfo()
        {
            try
            {
                var msgSetRequest = _sessionManager!.CreateMsgSetRequest("US", 16, 0);
                msgSetRequest.Attributes.OnError = 1; // rocContinue

                msgSetRequest.AppendCompanyQueryRq();

                var msgSetResponse = _sessionManager.DoRequests(msgSetRequest);
                var responseList = msgSetResponse.ResponseList;

                if (responseList.Count > 0)
                {
                    var response = responseList.GetAt(0);
                    if (response.StatusCode == 0)
                    {
                        var companyRet = response.Detail;
                        if (companyRet != null)
                        {
                            CompanyName = companyRet.CompanyName?.GetValue() ?? "Unknown Company";
                            _logCallback($"Company: {CompanyName}");
                        }
                    }
                }

                try
                {
                    var hostQuery = _sessionManager.CreateMsgSetRequest("US", 16, 0);
                    hostQuery.AppendHostQueryRq();
                    var hostResponse = _sessionManager.DoRequests(hostQuery);

                    if (hostResponse.ResponseList.Count > 0)
                    {
                        var hostRet = hostResponse.ResponseList.GetAt(0).Detail;
                        if (hostRet != null)
                        {
                            var versionList = hostRet.SupportedQBXMLVersionList;
                            if (versionList != null && versionList.Count > 0)
                            {
                                QBVersion = versionList.GetAt(versionList.Count - 1);
                                _logCallback($"QuickBooks QBXML Version: {QBVersion}");
                            }
                        }
                    }
                }
                catch { }
            }
            catch (Exception ex)
            {
                _logCallback($"Warning: Could not get company info: {ex.Message}");
            }
        }

        /// <summary>
        /// Extract all data from QuickBooks
        /// </summary>
        public ExtractionResult ExtractAll()
        {
            var result = new ExtractionResult
            {
                Success = false,
                CompanyName = CompanyName,
                QBVersion = QBVersion,
                ExtractedAt = DateTime.UtcNow
            };

            if (!_sessionOpen)
            {
                result.Error = "Session not open";
                return result;
            }

            try
            {
                _logCallback("Starting data extraction...");
                _progressCallback(5);

                var allData = new Dictionary<string, object>();

                var entityTypes = new (string Name, string Query, int Progress)[]
                {
                    ("Customers", "CustomerQueryRq", 15),
                    ("Vendors", "VendorQueryRq", 25),
                    ("Accounts", "AccountQueryRq", 35),
                    ("Items", "ItemQueryRq", 45),
                    ("Invoices", "InvoiceQueryRq", 55),
                    ("Bills", "BillQueryRq", 65),
                    ("Payments", "ReceivePaymentQueryRq", 72),
                    ("Checks", "CheckQueryRq", 78),
                    ("JournalEntries", "JournalEntryQueryRq", 82),
                    ("Classes", "ClassQueryRq", 84)
                };

                foreach (var (entityName, queryType, progress) in entityTypes)
                {
                    try
                    {
                        _logCallback($"Extracting {entityName}...");
                        var entities = ExtractEntity(queryType);
                        allData[entityName] = entities;
                        EntityCounts[entityName] = entities.Count;
                        _logCallback($"  Found {entities.Count} {entityName}");
                        _progressCallback(progress);
                    }
                    catch (Exception ex)
                    {
                        _logCallback($"  Warning: Could not extract {entityName}: {ex.Message}");
                        allData[entityName] = new List<Dictionary<string, object>>();
                        EntityCounts[entityName] = 0;
                    }
                }

                _logCallback("Serializing extracted data...");
                result.JsonData = JsonSerializer.Serialize(allData, new JsonSerializerOptions
                {
                    WriteIndented = false,
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase
                });

                result.TotalRecords = 0;
                foreach (var count in EntityCounts.Values)
                {
                    result.TotalRecords += count;
                }

                result.EntityCounts = new Dictionary<string, int>(EntityCounts);
                result.Success = true;

                _progressCallback(84);
                _logCallback($"Extraction complete! Total records: {result.TotalRecords}");

                return result;
            }
            catch (Exception ex)
            {
                result.Error = ex.Message;
                _logCallback($"Extraction failed: {ex.Message}");
                return result;
            }
        }

        private List<Dictionary<string, object>> ExtractEntity(string queryRequestType)
        {
            var results = new List<Dictionary<string, object>>();

            try
            {
                var msgSetRequest = _sessionManager!.CreateMsgSetRequest("US", 16, 0);
                msgSetRequest.Attributes.OnError = 1; // rocContinue

                // Use dynamic invocation to call Append<QueryType>
                var msgType = ((object)msgSetRequest).GetType();
                var appendMethod = msgType.GetMethod($"Append{queryRequestType}");

                if (appendMethod != null)
                {
                    appendMethod.Invoke(msgSetRequest, null);
                }
                else
                {
                    throw new Exception($"Query method Append{queryRequestType} not found");
                }

                var msgSetResponse = _sessionManager.DoRequests(msgSetRequest);
                var responseList = msgSetResponse.ResponseList;

                for (int i = 0; i < responseList.Count; i++)
                {
                    var response = responseList.GetAt(i);
                    if (response.StatusCode == 0 && response.Detail != null)
                    {
                        results.AddRange(ParseResponseDetail(response.Detail));
                    }
                }
            }
            catch (Exception ex)
            {
                throw new Exception($"Query {queryRequestType} failed: {ex.Message}");
            }

            return results;
        }

        private List<Dictionary<string, object>> ParseResponseDetail(dynamic detail)
        {
            var results = new List<Dictionary<string, object>>();

            try
            {
                if (HasProperty(detail, "Count"))
                {
                    int count = detail.Count;
                    for (int i = 0; i < count; i++)
                    {
                        var item = detail.GetAt(i);
                        var dict = ExtractProperties(item);
                        if (dict.Count > 0)
                        {
                            results.Add(dict);
                        }
                    }
                }
                else
                {
                    var dict = ExtractProperties(detail);
                    if (dict.Count > 0)
                    {
                        results.Add(dict);
                    }
                }
            }
            catch { }

            return results;
        }

        private Dictionary<string, object> ExtractProperties(dynamic obj)
        {
            var dict = new Dictionary<string, object>();

            if (obj == null) return dict;

            try
            {
                var fields = new[]
                {
                    "ListID", "TxnID", "TimeCreated", "TimeModified",
                    "Name", "FullName", "CompanyName", "FirstName", "LastName",
                    "Email", "Phone", "AltPhone", "Fax",
                    "Balance", "TotalBalance", "Amount", "Rate",
                    "IsActive", "Sublevel",
                    "AccountType", "AccountNumber", "BankNumber",
                    "RefNumber", "TxnNumber", "PONumber",
                    "TxnDate", "DueDate", "ShipDate",
                    "Memo", "Desc", "Description",
                    "Quantity", "QuantityOnHand", "QuantityOnOrder",
                    "Price", "Cost", "SalesPrice", "PurchaseCost",
                    "ItemType", "ClassRef", "ParentRef", "TermsRef"
                };

                foreach (var field in fields)
                {
                    try
                    {
                        if (HasProperty(obj, field))
                        {
                            var prop = ((object)obj).GetType().GetProperty(field);
                            if (prop != null)
                            {
                                var value = prop.GetValue(obj);
                                if (value != null)
                                {
                                    if (HasMethod(value, "GetValue"))
                                    {
                                        var v = value.GetValue();
                                        if (v != null) dict[field] = v;
                                    }
                                    else if (HasProperty(value, "FullName"))
                                    {
                                        var refName = value.FullName;
                                        if (refName != null && HasMethod(refName, "GetValue"))
                                        {
                                            var v = refName.GetValue();
                                            if (v != null) dict[field] = v.ToString();
                                        }
                                    }
                                    else
                                    {
                                        dict[field] = value.ToString();
                                    }
                                }
                            }
                        }
                    }
                    catch { }
                }

                TryExtractAddress(obj, "BillAddress", dict);
                TryExtractAddress(obj, "ShipAddress", dict);
            }
            catch { }

            return dict;
        }

        private void TryExtractAddress(dynamic obj, string addressField, Dictionary<string, object> dict)
        {
            try
            {
                if (HasProperty(obj, addressField))
                {
                    var addr = ((object)obj).GetType().GetProperty(addressField)?.GetValue(obj);
                    if (addr != null)
                    {
                        var addrDict = new Dictionary<string, string>();
                        var addrFields = new[] { "Addr1", "Addr2", "Addr3", "City", "State", "PostalCode", "Country" };

                        foreach (var f in addrFields)
                        {
                            try
                            {
                                if (HasProperty(addr, f))
                                {
                                    var val = ((object)addr).GetType().GetProperty(f)?.GetValue(addr);
                                    if (val != null && HasMethod(val, "GetValue"))
                                    {
                                        var strVal = val.GetValue()?.ToString();
                                        if (!string.IsNullOrEmpty(strVal))
                                        {
                                            addrDict[f] = strVal;
                                        }
                                    }
                                }
                            }
                            catch { }
                        }

                        if (addrDict.Count > 0)
                        {
                            dict[addressField] = addrDict;
                        }
                    }
                }
            }
            catch { }
        }

        private bool HasProperty(object obj, string propertyName)
        {
            if (obj == null) return false;
            try { return obj.GetType().GetProperty(propertyName) != null; }
            catch { return false; }
        }

        private bool HasMethod(object obj, string methodName)
        {
            if (obj == null) return false;
            try { return obj.GetType().GetMethod(methodName) != null; }
            catch { return false; }
        }

        /// <summary>
        /// Close the QuickBooks session
        /// </summary>
        public void CloseSession()
        {
            try
            {
                if (_sessionOpen)
                {
                    _sessionManager!.EndSession();
                    _sessionOpen = false;
                    _logCallback("Session closed.");
                }

                if (_sessionManager != null)
                {
                    _sessionManager.CloseConnection();
                    _logCallback("Connection closed.");
                }
            }
            catch (Exception ex)
            {
                _logCallback($"Warning during close: {ex.Message}");
            }
        }

        public void Dispose()
        {
            CloseSession();

            if (_sessionManager != null)
            {
                try
                {
                    Marshal.ReleaseComObject(_sessionManager);
                }
                catch { }

                _sessionManager = null;
            }
        }
    }

    /// <summary>
    /// Result of an extraction operation
    /// </summary>
    public class ExtractionResult
    {
        public bool Success { get; set; }
        public string? Error { get; set; }
        public string JsonData { get; set; } = "";
        public string CompanyName { get; set; } = "";
        public string QBVersion { get; set; } = "";
        public DateTime ExtractedAt { get; set; }
        public int TotalRecords { get; set; }
        public Dictionary<string, int> EntityCounts { get; set; } = new Dictionary<string, int>();
    }
}
