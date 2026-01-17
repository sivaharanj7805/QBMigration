using System;
using System.Collections.Generic;

namespace QBDesktopExtractor.Tests
{
    /// <summary>
    /// Test suite for RecursiveTransactionLinker
    /// Validates payment-invoice link reconstruction
    /// </summary>
    class TestTransactionLinking
    {
        static int _passed = 0;
        static int _failed = 0;

        static void Main()
        {
            Console.WriteLine("Testing RecursiveTransactionLinker");
            Console.WriteLine("====================================\n");

            TestBasicLinking();
            TestPartialPayment();
            TestMultiInvoicePayment();
            TestOrphanPaymentDetection();
            TestLinkVerification();
            TestCreditMemoLinking();

            Console.WriteLine("\n====================================");
            Console.WriteLine($"Results: {_passed} passed, {_failed} failed");
            Console.WriteLine("====================================");

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

        static void TestBasicLinking()
        {
            Console.WriteLine("Test: Basic Payment-to-Invoice Linking");
            
            var linker = new RecursiveTransactionLinker();
            
            var data = new QBExtractedData
            {
                Invoices = new List<QBInvoice>
                {
                    new QBInvoice
                    {
                        TxnID = "INV-001",
                        RefNumber = "1001",
                        Subtotal = 1000.00m,
                        SalesTaxTotal = 80.00m,
                        AppliedAmount = 1080.00m,
                        BalanceRemaining = 0
                    }
                },
                ReceivePayments = new List<QBReceivePayment>
                {
                    new QBReceivePayment
                    {
                        TxnID = "PMT-001",
                        RefNumber = "PAY001",
                        TotalAmount = 1080.00m
                    }
                },
                Bills = new List<QBBill>(),
                BillPayments = new List<QBBillPaymentCheck>(),
                CreditMemos = new List<QBCreditMemo>()
            };
            
            var result = linker.ProcessLinks(data);
            
            if (result.Success && result.TotalLinksProcessed > 0)
            {
                Console.WriteLine($"  ✓ Processed {result.TotalLinksProcessed} link(s)");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Linking failed: {result.Error}");
                _failed++;
            }
        }

        static void TestPartialPayment()
        {
            Console.WriteLine("\nTest: Partial Payment Handling");
            
            var linker = new RecursiveTransactionLinker();
            
            var data = new QBExtractedData
            {
                Invoices = new List<QBInvoice>
                {
                    new QBInvoice
                    {
                        TxnID = "INV-002",
                        RefNumber = "1002",
                        Subtotal = 2000.00m,
                        SalesTaxTotal = 160.00m,
                        AppliedAmount = 500.00m,
                        BalanceRemaining = 1660.00m
                    }
                },
                ReceivePayments = new List<QBReceivePayment>
                {
                    new QBReceivePayment
                    {
                        TxnID = "PMT-002",
                        RefNumber = "PAY002",
                        TotalAmount = 500.00m
                    }
                },
                Bills = new List<QBBill>(),
                BillPayments = new List<QBBillPaymentCheck>(),
                CreditMemos = new List<QBCreditMemo>()
            };
            
            var result = linker.ProcessLinks(data);
            
            if (result.Success)
            {
                Console.WriteLine("  ✓ Partial payment processed correctly");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Partial payment handling failed");
                _failed++;
            }
        }

        static void TestMultiInvoicePayment()
        {
            Console.WriteLine("\nTest: Multi-Invoice Payment");
            
            var linker = new RecursiveTransactionLinker();
            
            var data = new QBExtractedData
            {
                Invoices = new List<QBInvoice>
                {
                    new QBInvoice { TxnID = "INV-003A", Subtotal = 500.00m, BalanceRemaining = 0 },
                    new QBInvoice { TxnID = "INV-003B", Subtotal = 500.00m, BalanceRemaining = 0 }
                },
                ReceivePayments = new List<QBReceivePayment>
                {
                    new QBReceivePayment
                    {
                        TxnID = "PMT-003",
                        TotalAmount = 1000.00m
                    }
                },
                Bills = new List<QBBill>(),
                BillPayments = new List<QBBillPaymentCheck>(),
                CreditMemos = new List<QBCreditMemo>()
            };
            
            var result = linker.ProcessLinks(data);
            
            if (result.Success)
            {
                Console.WriteLine("  ✓ Multi-invoice payment processed");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Multi-invoice payment failed");
                _failed++;
            }
        }

        static void TestOrphanPaymentDetection()
        {
            Console.WriteLine("\nTest: Orphan Payment Detection");
            
            var linker = new RecursiveTransactionLinker();
            
            var data = new QBExtractedData
            {
                Invoices = new List<QBInvoice>(), // No invoices
                ReceivePayments = new List<QBReceivePayment>
                {
                    new QBReceivePayment
                    {
                        TxnID = "PMT-ORPHAN",
                        TotalAmount = 100.00m
                    }
                },
                Bills = new List<QBBill>(),
                BillPayments = new List<QBBillPaymentCheck>(),
                CreditMemos = new List<QBCreditMemo>()
            };
            
            var result = linker.ProcessLinks(data);
            
            // For this basic implementation, we just verify it doesn't crash
            if (result.Success)
            {
                Console.WriteLine("  ✓ Orphan payment handled without crash");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Orphan payment handling failed");
                _failed++;
            }
        }

        static void TestLinkVerification()
        {
            Console.WriteLine("\nTest: Invoice Link Verification");
            
            var linker = new RecursiveTransactionLinker();
            
            // Test valid invoice (balanced)
            var validInvoice = new QBInvoice
            {
                TxnID = "INV-VALID",
                Subtotal = 1000.00m,
                SalesTaxTotal = 80.00m,
                AppliedAmount = 580.00m,
                BalanceRemaining = 500.00m
            };
            
            var validResult = linker.VerifyInvoiceLinks(validInvoice);
            
            if (validResult.IsValid)
            {
                Console.WriteLine("  ✓ Valid invoice verified correctly");
                _passed++;
            }
            else
            {
                Console.WriteLine($"  ✗ Valid invoice flagged as invalid: {validResult.Error}");
                _failed++;
            }
            
            // Test invalid invoice (unbalanced)
            var invalidInvoice = new QBInvoice
            {
                TxnID = "INV-INVALID",
                Subtotal = 1000.00m,
                SalesTaxTotal = 80.00m,
                AppliedAmount = 100.00m,
                BalanceRemaining = 100.00m // Should be 980
            };
            
            var invalidResult = linker.VerifyInvoiceLinks(invalidInvoice);
            
            if (!invalidResult.IsValid)
            {
                Console.WriteLine("  ✓ Invalid invoice detected correctly");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Invalid invoice passed verification incorrectly");
                _failed++;
            }
        }

        static void TestCreditMemoLinking()
        {
            Console.WriteLine("\nTest: Credit Memo Linking");
            
            var linker = new RecursiveTransactionLinker();
            
            var data = new QBExtractedData
            {
                Invoices = new List<QBInvoice>
                {
                    new QBInvoice { TxnID = "INV-CM", Subtotal = 500.00m }
                },
                CreditMemos = new List<QBCreditMemo>
                {
                    new QBCreditMemo
                    {
                        TxnID = "CM-001",
                        RefNumber = "CM001",
                        TotalAmount = 100.00m
                    }
                },
                ReceivePayments = new List<QBReceivePayment>(),
                Bills = new List<QBBill>(),
                BillPayments = new List<QBBillPaymentCheck>()
            };
            
            var result = linker.ProcessLinks(data);
            
            if (result.Success && result.TotalLinksProcessed >= 1)
            {
                Console.WriteLine("  ✓ Credit memo link processed");
                _passed++;
            }
            else
            {
                Console.WriteLine("  ✗ Credit memo linking failed");
                _failed++;
            }
        }
    }
}
