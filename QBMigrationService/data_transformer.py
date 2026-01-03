import re

class DataTransformer:
    def __init__(self):
        self.id_mapping = {
            'customers': {},
            'vendors': {},
            'accounts': {},
            'items': {}
        }
    
    def transform_customer(self, qbd_customer):
        """Transform QB Desktop customer to QBO format"""
        qbo_customer = {
            "DisplayName": qbd_customer["Name"],
            "Active": True
        }
        
        if qbd_customer.get("CompanyName"):
            qbo_customer["CompanyName"] = qbd_customer["CompanyName"]
        
        # Split full name into first/last if available
        name_parts = qbd_customer["Name"].split(" ", 1)
        if len(name_parts) == 2:
            qbo_customer["GivenName"] = name_parts[0]
            qbo_customer["FamilyName"] = name_parts[1]
        else:
            qbo_customer["GivenName"] = qbd_customer["Name"]
        
        if qbd_customer.get("Phone"):
            qbo_customer["PrimaryPhone"] = {
                "FreeFormNumber": qbd_customer["Phone"]
            }
        
        if qbd_customer.get("Email"):
            qbo_customer["PrimaryEmailAddr"] = {
                "Address": qbd_customer["Email"]
            }
        
        # Address
        if any([qbd_customer.get("Addr1"), qbd_customer.get("City")]):
            qbo_customer["BillAddr"] = {}
            
            if qbd_customer.get("Addr1"):
                qbo_customer["BillAddr"]["Line1"] = qbd_customer["Addr1"]
            if qbd_customer.get("Addr2"):
                qbo_customer["BillAddr"]["Line2"] = qbd_customer["Addr2"]
            if qbd_customer.get("City"):
                qbo_customer["BillAddr"]["City"] = qbd_customer["City"]
            if qbd_customer.get("State"):
                qbo_customer["BillAddr"]["CountrySubDivisionCode"] = qbd_customer["State"]
            if qbd_customer.get("PostalCode"):
                qbo_customer["BillAddr"]["PostalCode"] = qbd_customer["PostalCode"]
            if qbd_customer.get("Country"):
                qbo_customer["BillAddr"]["Country"] = qbd_customer["Country"]
        
        return qbo_customer
    
    def transform_vendor(self, qbd_vendor):
        """Transform QB Desktop vendor to QBO format"""
        qbo_vendor = {
            "DisplayName": qbd_vendor["Name"],
            "Active": True
        }
        
        if qbd_vendor.get("CompanyName"):
            qbo_vendor["CompanyName"] = qbd_vendor["CompanyName"]
        
        if qbd_vendor.get("Phone"):
            qbo_vendor["PrimaryPhone"] = {
                "FreeFormNumber": qbd_vendor["Phone"]
            }
        
        if qbd_vendor.get("Email"):
            qbo_vendor["PrimaryEmailAddr"] = {
                "Address": qbd_vendor["Email"]
            }
        
        # Address
        if any([qbd_vendor.get("Addr1"), qbd_vendor.get("City")]):
            qbo_vendor["BillAddr"] = {}
            
            if qbd_vendor.get("Addr1"):
                qbo_vendor["BillAddr"]["Line1"] = qbd_vendor["Addr1"]
            if qbd_vendor.get("City"):
                qbo_vendor["BillAddr"]["City"] = qbd_vendor["City"]
            if qbd_vendor.get("State"):
                qbo_vendor["BillAddr"]["CountrySubDivisionCode"] = qbd_vendor["State"]
            if qbd_vendor.get("PostalCode"):
                qbo_vendor["BillAddr"]["PostalCode"] = qbd_vendor["PostalCode"]
        
        return qbo_vendor
    
    def transform_account(self, qbd_account):
        """Transform QB Desktop account to QBO format"""
        # Map Desktop account types to Online account types
        type_mapping = {
            "Bank": "Bank",
            "AccountsReceivable": "Accounts Receivable",
            "OtherCurrentAsset": "Other Current Asset",
            "FixedAsset": "Fixed Asset",
            "OtherAsset": "Other Asset",
            "AccountsPayable": "Accounts Payable",
            "CreditCard": "Credit Card",
            "OtherCurrentLiability": "Other Current Liability",
            "LongTermLiability": "Long Term Liability",
            "Equity": "Equity",
            "Income": "Income",
            "CostOfGoodsSold": "Cost of Goods Sold",
            "Expense": "Expense",
            "OtherIncome": "Other Income",
            "OtherExpense": "Other Expense"
        }
        
        account_type = type_mapping.get(qbd_account["AccountType"], "Expense")
        
        qbo_account = {
            "Name": qbd_account["Name"],
            "AccountType": account_type,
            "Active": qbd_account.get("IsActive", True)
        }
        
        if qbd_account.get("AccountNumber"):
            qbo_account["AcctNum"] = qbd_account["AccountNumber"]
        
        if qbd_account.get("Description"):
            qbo_account["Description"] = qbd_account["Description"]
        
        return qbo_account
    
    def transform_item(self, qbd_item, income_account_id=None):
        """Transform QB Desktop item to QBO format"""
        qbo_item = {
            "Name": qbd_item["Name"],
            "Type": "Service",
            "Active": qbd_item.get("IsActive", True)
        }
        
        if qbd_item.get("Description"):
            qbo_item["Description"] = qbd_item["Description"]
        
        if qbd_item.get("SalesPrice"):
            qbo_item["UnitPrice"] = qbd_item["SalesPrice"]
        
        # Income account reference
        if income_account_id:
            qbo_item["IncomeAccountRef"] = {
                "value": income_account_id
            }
        
        return qbo_item
    
    def transform_invoice(self, qbd_invoice, customer_id_map, item_id_map):
        """Transform QB Desktop invoice to QBO format"""
        # Map customer
        qbd_customer_id = qbd_invoice["CustomerRef"]
        qbo_customer_id = customer_id_map.get(qbd_customer_id)
        
        if not qbo_customer_id:
            raise ValueError(f"Customer mapping not found for {qbd_customer_id}")
        
        qbo_invoice = {
            "CustomerRef": {
                "value": qbo_customer_id
            },
            "TxnDate": qbd_invoice["TxnDate"][:10],  # Format: YYYY-MM-DD
            "Line": []
        }
        
        if qbd_invoice.get("RefNumber"):
            qbo_invoice["DocNumber"] = qbd_invoice["RefNumber"]
        
        # Transform line items
        for line in qbd_invoice.get("Lines", []):
            qbd_item_id = line["ItemRef"]
            qbo_item_id = item_id_map.get(qbd_item_id)
            
            if not qbo_item_id:
                print(f"  Warning: Item mapping not found for {qbd_item_id}, skipping line")
                continue
            
            qbo_line = {
                "DetailType": "SalesItemLineDetail",
                "Amount": line["Amount"],
                "SalesItemLineDetail": {
                    "ItemRef": {
                        "value": qbo_item_id
                    },
                    "Qty": line["Quantity"],
                    "UnitPrice": line["Rate"]
                }
            }
            
            if line.get("Description"):
                qbo_line["Description"] = line["Description"]
            
            qbo_invoice["Line"].append(qbo_line)
        
        return qbo_invoice