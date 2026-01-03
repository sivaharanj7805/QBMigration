import requests
import time
import json
from config import *

class QBOClient:
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        self.request_count = 0
        self.start_time = time.time()
    
    def _rate_limit(self):
        """Enforce rate limiting"""
        self.request_count += 1
        time.sleep(RATE_LIMIT_DELAY)
        
        # If we've made 450 requests in less than 60 seconds, wait
        elapsed = time.time() - self.start_time
        if self.request_count >= 450 and elapsed < 60:
            wait_time = 60 - elapsed
            print(f"  Rate limit: Waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            self.request_count = 0
            self.start_time = time.time()
    
    def _make_request(self, method, endpoint, data=None, retries=0):
        """Make HTTP request with retry logic"""
        self._rate_limit()
        
        url = f"{BASE_URL}/{endpoint}"
        
        try:
            if method == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method == "GET":
                response = requests.get(url, headers=self.headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            if response.status_code == 429:  # Rate limit
                if retries < MAX_RETRIES:
                    wait_time = 2 ** retries
                    print(f"  Rate limited. Retry {retries+1}/{MAX_RETRIES} in {wait_time}s...")
                    time.sleep(wait_time)
                    return self._make_request(method, endpoint, data, retries + 1)
                else:
                    raise Exception("Max retries exceeded for rate limit")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            if retries < MAX_RETRIES:
                wait_time = 2 ** retries
                print(f"  Error. Retry {retries+1}/{MAX_RETRIES} in {wait_time}s...")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, data, retries + 1)
            else:
                raise e
    
    def create_customer(self, customer_data):
        """Create a customer in QBO"""
        return self._make_request("POST", "customer", customer_data)
    
    def create_vendor(self, vendor_data):
        """Create a vendor in QBO"""
        return self._make_request("POST", "vendor", vendor_data)
    
    def create_account(self, account_data):
        """Create an account in QBO"""
        return self._make_request("POST", "account", account_data)
    
    def create_item(self, item_data):
        """Create an item in QBO"""
        return self._make_request("POST", "item", item_data)
    
    def create_invoice(self, invoice_data):
        """Create an invoice in QBO"""
        return self._make_request("POST", "invoice", invoice_data)
    
    def query(self, entity_type, query_string=""):
        """Run a query against QBO"""
        if query_string:
            endpoint = f"query?query={query_string}"
        else:
            endpoint = f"query?query=SELECT * FROM {entity_type}"
        
        return self._make_request("GET", endpoint)
    
    def batch_create(self, operations):
        """Create multiple entities in one batch request"""
        batch_data = {
            "BatchItemRequest": []
        }
        
        for i, op in enumerate(operations):
            batch_data["BatchItemRequest"].append({
                "bId": f"bid_{i}",
                op["entity_type"]: op["data"]
            })
        
        return self._make_request("POST", "batch", batch_data)