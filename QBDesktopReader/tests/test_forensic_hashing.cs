using System;
using System.Security.Cryptography;
using System.Text;

namespace QBDesktopExtractor.Tests
{
    /// <summary>
    /// Test suite for ForensicHashingService
    /// Validates hash determinism, uniqueness, and correctness
    /// </summary>
    class TestForensicHashing
    {
        static int _passed = 0;
        static int _failed = 0;

        static void Main()
        {
            Console.WriteLine("Testing ForensicHashingService");
            Console.WriteLine("================================\n");

            TestHashDeterminism();
            TestHashUniqueness();
            TestNullHandling();
            TestInvoiceHashing();
            TestBillHashing();
            TestPaymentHashing();

            Console.WriteLine("\n================================");
            Console.WriteLine($"Results: {_passed} passed, {_failed} failed");
            Console.WriteLine("================================");

            if (_failed > 0)
            {
                Console.WriteLine("\n✗ SOME TESTS FAILED");
                Environment.Exit(1);
            }
            else
            {
                Console.WriteLine("\n✓ ALL TESTS PASSED");
            }
        }

        static void TestHashDeterminism()
        {
            Console.WriteLine("Test: Hash Determinism (same input = same hash)");
            
            var invoice1 = CreateTestInvoice("INV-001", 1000.00m);
            var invoice2 = CreateTestInvoice("INV-001", 1000.00m);
            
            var hash1 = ForensicHashingService.ComputeInvoiceHash(invoice1);
            var hash2 = ForensicHashingService.ComputeInvoiceHash(invoice2);
            
            if (hash1 == hash2)
            {
                Console.WriteLine("  ✓ Same invoice data produces identical hashes");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Hashes differ: {hash1} vs {hash2}");
                _failed++;
            }
        }

        static void TestHashUniqueness()
        {
            Console.WriteLine("\nTest: Hash Uniqueness (different input = different hash)");
            
            var invoice1 = CreateTestInvoice("INV-001", 1000.00m);
            var invoice2 = CreateTestInvoice("INV-002", 1000.00m);
            var invoice3 = CreateTestInvoice("INV-001", 1001.00m);
            
            var hash1 = ForensicHashingService.ComputeInvoiceHash(invoice1);
            var hash2 = ForensicHashingService.ComputeInvoiceHash(invoice2);
            var hash3 = ForensicHashingService.ComputeInvoiceHash(invoice3);
            
            if (hash1 != hash2 && hash1 != hash3 && hash2 != hash3)
            {
                Console.WriteLine("  ✓ Different invoices produce different hashes");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Hash collision detected!");
                _failed++;
            }
        }

        static void TestNullHandling()
        {
            Console.WriteLine("\nTest: Null Handling");
            
            var nullHash = ForensicHashingService.ComputeInvoiceHash(null);
            
            if (nullHash == null)
            {
                Console.WriteLine("  ✓ Null input returns null hash");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Expected null, got: {nullHash}");
                _failed++;
            }
        }

        static void TestInvoiceHashing()
        {
            Console.WriteLine("\nTest: Invoice Hashing");
            
            var invoice = CreateTestInvoice("INV-TEST", 500.00m);
            var hash = ForensicHashingService.ComputeInvoiceHash(invoice);
            
            if (!string.IsNullOrEmpty(hash) && hash.Length == 64) // SHA256 = 64 hex chars
            {
                Console.WriteLine($"  ✓ Invoice hash generated: {hash.Substring(0, 16)}...");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Invalid hash: {hash}");
                _failed++;
            }
        }

        static void TestBillHashing()
        {
            Console.WriteLine("\nTest: Bill Hashing");
            
            var bill = new QBBill
            {
                TxnID = "TXN-BILL-001",
                RefNumber = "BILL-001",
                TxnDate = new DateTime(2025, 1, 15),
                VendorRefListID = "VENDOR-001",
                AmountDue = 750.50m,
                IsPaid = false,
                EditSequence = "12345"
            };
            
            var hash = ForensicHashingService.ComputeBillHash(bill);
            
            if (!string.IsNullOrEmpty(hash) && hash.Length == 64)
            {
                Console.WriteLine($"  ✓ Bill hash generated: {hash.Substring(0, 16)}...");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Invalid hash: {hash}");
                _failed++;
            }
        }

        static void TestPaymentHashing()
        {
            Console.WriteLine("\nTest: Payment Hashing");
            
            var payment = new QBReceivePayment
            {
                TxnID = "TXN-PMT-001",
                RefNumber = "PMT-001",
                TxnDate = new DateTime(2025, 1, 16),
                CustomerRefListID = "CUST-001",
                TotalAmount = 500.00m,
                PaymentMethodRefListID = "CC",
                DepositToAccountRefListID = "ACCT-001",
                EditSequence = "12346"
            };
            
            var hash = ForensicHashingService.ComputeReceivePaymentHash(payment);
            
            if (!string.IsNullOrEmpty(hash) && hash.Length == 64)
            {
                Console.WriteLine($"  ✓ Payment hash generated: {hash.Substring(0, 16)}...");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Invalid hash: {hash}");
                _failed++;
            }
        }

        static QBInvoice CreateTestInvoice(string refNumber, decimal subtotal)
        {
            return new QBInvoice
            {
                TxnID = $"TXN-{refNumber}",
                RefNumber = refNumber,
                TxnDate = new DateTime(2025, 1, 15),
                CustomerRefListID = "CUST-001",
                Subtotal = subtotal,
                SalesTaxTotal = subtotal * 0.08m,
                AppliedAmount = 0,
                BalanceRemaining = subtotal * 1.08m,
                IsPaid = false,
                EditSequence = "12345"
            };
        }
    }
}
