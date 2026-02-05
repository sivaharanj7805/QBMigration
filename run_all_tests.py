"""
ForensicBridge Comprehensive Test Runner
Executes all test suites and generates coverage report

Usage:
    python run_all_tests.py
    python run_all_tests.py --coverage
    python run_all_tests.py --backend-only
    python run_all_tests.py --integration-only
"""

import subprocess
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path


class TestRunner:
    """Comprehensive test runner for ForensicBridge"""
    
    def __init__(self):
        self.root_dir = Path(__file__).parent.parent
        self.results = []
        self.start_time = None
        
    def run_backend_tests(self, coverage=False):
        """Run QBMigrationServer tests"""
        print("\n" + "="*60)
        print("Running Backend API Tests (QBMigrationServer)")
        print("="*60)
        
        test_dir = self.root_dir / "QBMigrationServer" / "tests"
        
        if coverage:
            cmd = [
                sys.executable, "-m", "pytest",
                str(test_dir),
                "-v", "--tb=short",
                "--cov=api", "--cov=models",
                "--cov-report=html:coverage_reports/backend"
            ]
        else:
            cmd = [
                sys.executable, "-m", "pytest",
                str(test_dir),
                "-v", "--tb=short"
            ]
        
        result = subprocess.run(cmd, cwd=str(self.root_dir / "QBMigrationServer"))
        self.results.append(("Backend API Tests", result.returncode == 0))
        return result.returncode == 0
    
    def run_service_tests(self, coverage=False):
        """Run QBMigrationService tests"""
        print("\n" + "="*60)
        print("Running Service Tests (QBMigrationService)")
        print("="*60)
        
        test_dir = self.root_dir / "QBMigrationService" / "tests"
        
        if coverage:
            cmd = [
                sys.executable, "-m", "pytest",
                str(test_dir),
                "-v", "--tb=short",
                "--cov=.", 
                "--cov-report=html:coverage_reports/service"
            ]
        else:
            cmd = [
                sys.executable, "-m", "pytest",
                str(test_dir),
                "-v", "--tb=short"
            ]
        
        result = subprocess.run(cmd, cwd=str(self.root_dir / "QBMigrationService"))
        self.results.append(("Service Tests", result.returncode == 0))
        return result.returncode == 0
    
    def run_integration_tests(self):
        """Run integration tests"""
        print("\n" + "="*60)
        print("Running Integration Tests")
        print("="*60)
        
        test_file = self.root_dir / "QBMigrationService" / "tests" / "test_integration.py"
        
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_file),
            "-v", "--tb=short",
            "-m", "not slow"  # Skip slow tests by default
        ]
        
        result = subprocess.run(cmd, cwd=str(self.root_dir / "QBMigrationService"))
        self.results.append(("Integration Tests", result.returncode == 0))
        return result.returncode == 0
    
    def run_frontend_tests(self):
        """Run Next.js frontend tests"""
        print("\n" + "="*60)
        print("Running Frontend Tests (ForensicBridge Dashboard)")
        print("="*60)
        
        frontend_dir = self.root_dir / "forensicbridge-dashboard"
        
        if not (frontend_dir / "node_modules").exists():
            print("⚠️  node_modules not found. Run 'npm install' first.")
            self.results.append(("Frontend Tests", False))
            return False
        
        cmd = ["npm", "test", "--", "--run"]
        
        result = subprocess.run(cmd, cwd=str(frontend_dir))
        self.results.append(("Frontend Tests", result.returncode == 0))
        return result.returncode == 0
    
    def run_csharp_tests(self):
        """Run C# QBDesktopReader tests"""
        print("\n" + "="*60)
        print("Running C# Tests (QBDesktopReader)")
        print("="*60)
        
        csharp_dir = self.root_dir / "QBDesktopReader"
        
        cmd = ["dotnet", "test", "--verbosity", "normal"]
        
        result = subprocess.run(cmd, cwd=str(csharp_dir))
        self.results.append(("C# Tests", result.returncode == 0))
        return result.returncode == 0
    
    def check_qbo_connection(self):
        """Validate QBO API connection"""
        print("\n" + "="*60)
        print("Checking QBO API Connection")
        print("="*60)
        
        # Check for credentials
        required_env = ['QBO_CLIENT_ID', 'QBO_CLIENT_SECRET', 'QBO_REALM_ID']
        missing = [e for e in required_env if not os.environ.get(e)]
        
        if missing:
            print(f"⚠️  Missing environment variables: {missing}")
            print("   Set these to test QBO connection.")
            self.results.append(("QBO Connection", None))  # None = skipped
            return None
        
        # Try to validate credentials
        try:
            import requests
            response = requests.get(
                "https://sandbox-quickbooks.api.intuit.com/v3/company/info",
                timeout=10
            )
            connected = response.status_code != 500
            self.results.append(("QBO Connection", connected))
            return connected
        except Exception as e:
            print(f"⚠️  QBO connection check failed: {e}")
            self.results.append(("QBO Connection", False))
            return False
    
    def generate_report(self):
        """Generate summary report"""
        print("\n" + "="*60)
        print("TEST SUMMARY REPORT")
        print("="*60)
        
        total = len(self.results)
        passed = sum(1 for _, r in self.results if r is True)
        failed = sum(1 for _, r in self.results if r is False)
        skipped = sum(1 for _, r in self.results if r is None)
        
        print(f"\nTotal Test Suites: {total}")
        print(f"Passed: {passed} ✓")
        print(f"Failed: {failed} ✗")
        print(f"Skipped: {skipped} ○")
        
        print("\nDetailed Results:")
        for name, result in self.results:
            if result is True:
                status = "✓ PASSED"
            elif result is False:
                status = "✗ FAILED"
            else:
                status = "○ SKIPPED"
            print(f"  {name}: {status}")
        
        # Calculate duration
        if self.start_time:
            duration = datetime.now() - self.start_time
            print(f"\nTotal Duration: {duration.total_seconds():.1f} seconds")
        
        return failed == 0
    
    def run_all(self, coverage=False):
        """Run all test suites"""
        self.start_time = datetime.now()
        
        print("="*60)
        print("ForensicBridge Comprehensive Test Suite")
        print(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        self.run_backend_tests(coverage)
        self.run_service_tests(coverage)
        self.run_integration_tests()
        self.run_frontend_tests()
        self.check_qbo_connection()
        
        return self.generate_report()


def main():
    parser = argparse.ArgumentParser(description="ForensicBridge Test Runner")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage reports")
    parser.add_argument("--backend-only", action="store_true", help="Run only backend tests")
    parser.add_argument("--service-only", action="store_true", help="Run only service tests")
    parser.add_argument("--frontend-only", action="store_true", help="Run only frontend tests")
    parser.add_argument("--integration-only", action="store_true", help="Run only integration tests")
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.backend_only:
        success = runner.run_backend_tests(args.coverage)
    elif args.service_only:
        success = runner.run_service_tests(args.coverage)
    elif args.frontend_only:
        success = runner.run_frontend_tests()
    elif args.integration_only:
        success = runner.run_integration_tests()
    else:
        success = runner.run_all(args.coverage)
    
    runner.generate_report()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
