import json
from datetime import datetime

class MigrationVerifier:
    def __init__(self, qbo_client):
        self.client = qbo_client
        self.report = {
            "migration_date": datetime.now().isoformat(),
            "summary": {},
            "details": {}
        }
    
    def verify_customers(self, expected_count):
        """Verify customer migration"""
        result = self.client.query("Customer")
        actual_count = len(result.get("QueryResponse", {}).get("Customer", []))
        
        self.report["summary"]["customers"] = {
            "expected": expected_count,
            "actual": actual_count,
            "success": actual_count == expected_count
        }
        
        print(f"  Customers: {actual_count}/{expected_count}")
        return actual_count == expected_count
    
    def verify_vendors(self, expected_count):
        """Verify vendor migration"""
        result = self.client.query("Vendor")
        actual_count = len(result.get("QueryResponse", {}).get("Vendor", []))
        
        self.report["summary"]["vendors"] = {
            "expected": expected_count,
            "actual": actual_count,
            "success": actual_count == expected_count
        }
        
        print(f"  Vendors: {actual_count}/{expected_count}")
        return actual_count == expected_count
    
    def verify_accounts(self, expected_count):
        """Verify account migration"""
        result = self.client.query("Account")
        actual_count = len(result.get("QueryResponse", {}).get("Account", []))
        
        # QBO has default accounts, so we check if actual >= expected
        success = actual_count >= expected_count
        
        self.report["summary"]["accounts"] = {
            "expected": expected_count,
            "actual": actual_count,
            "success": success
        }
        
        print(f"  Accounts: {actual_count} (expected at least {expected_count})")
        return success
    
    def verify_items(self, expected_count):
        """Verify item migration"""
        result = self.client.query("Item")
        actual_count = len(result.get("QueryResponse", {}).get("Item", []))
        
        self.report["summary"]["items"] = {
            "expected": expected_count,
            "actual": actual_count,
            "success": actual_count == expected_count
        }
        
        print(f"  Items: {actual_count}/{expected_count}")
        return actual_count == expected_count
    
    def verify_invoices(self, expected_count):
        """Verify invoice migration"""
        result = self.client.query("Invoice")
        actual_count = len(result.get("QueryResponse", {}).get("Invoice", []))
        
        self.report["summary"]["invoices"] = {
            "expected": expected_count,
            "actual": actual_count,
            "success": actual_count == expected_count
        }
        
        print(f"  Invoices: {actual_count}/{expected_count}")
        return actual_count == expected_count
    
    def save_report(self, filepath):
        """Save verification report to file"""
        with open(filepath, 'w') as f:
            json.dump(self.report, f, indent=2)
        
        print(f"\n✓ Verification report saved: {filepath}")