"""
Locale-Aware Lead Sheet Code Mapper for Caseware
================================================

Provides lead sheet code mappings for different accounting standards:
- US GAAP (Generally Accepted Accounting Principles)
- Canadian GAAP (Canadian standards)
- IFRS (International Financial Reporting Standards)

ISSUE #33: Previously hardcoded for US GAAP only, causing auditor rejection
of Caseware files in Canadian/International jurisdictions.

Author: ForensicBridge Security Team
Version: 1.0.0
"""

import logging
from typing import Dict, Optional, Literal

logger = logging.getLogger(__name__)

AccountingStandard = Literal['US_GAAP', 'CANADIAN_GAAP', 'IFRS']


class LeadSheetMapper:
    """
    Detects accounting locale and provides appropriate lead sheet code mappings.
    """

    # US GAAP Lead Sheet Codes (US conventions)
    US_GAAP_CODES = {
        # Assets - General
        'Bank': 'A1',
        'Accounts Receivable': 'A2',
        'Other Current Assets': 'A3',
        'Fixed Assets': 'A4',
        'Other Assets': 'A5',
        'Inventory': 'A3.1',
        'Prepaid Expenses': 'A3.2',
        'Undeposited Funds': 'A1.1',

        # Assets - Agricultural (High-value sector)
        'Livestock': 'A6.1',
        'Crops': 'A6.2',
        'Agricultural Inventory': 'A6.3',
        'Farm Equipment': 'A6.4',
        'Agricultural Land': 'A6.5',
        'Breeding Stock': 'A6.6',
        'Growing Crops': 'A6.7',
        'Harvested Crops': 'A6.8',

        # Assets - Manufacturing (High-value sector)
        'Raw Materials': 'A7.1',
        'Work in Process': 'A7.2',
        'Finished Goods': 'A7.3',
        'Manufacturing Equipment': 'A7.4',
        'Factory Buildings': 'A7.5',
        'Tooling': 'A7.6',
        'Packaging Materials': 'A7.7',
        'Production Supplies': 'A7.8',

        # Assets - Other Industries
        'Construction in Progress': 'A8.1',
        'Software Development': 'A8.2',
        'Oil & Gas Equipment': 'A8.3',
        'Mining Assets': 'A8.4',
        'Real Estate Held for Sale': 'A8.5',

        # Liabilities
        'Accounts Payable': 'L1',
        'Credit Card': 'L2',
        'Other Current Liabilities': 'L3',
        'Long Term Liabilities': 'L4',
        'Sales Tax Payable': 'L3.1',
        'Payroll Liabilities': 'L3.2',
        'Accrued Liabilities': 'L3.3',
        'Deferred Revenue': 'L3.4',
        'Mortgage Payable': 'L4.1',
        'Equipment Loans': 'L4.2',

        # Equity
        'Equity': 'E1',
        'Retained Earnings': 'E2',
        'Opening Balance Equity': 'E3',
        'Shareholder Equity': 'E4',
        'Partner Capital': 'E5',

        # Income
        'Income': 'R1',
        'Other Income': 'R2',
        'Sales': 'R1.1',
        'Service Income': 'R1.2',
        'Agricultural Sales': 'R1.3',
        'Manufacturing Sales': 'R1.4',
        'Contract Revenue': 'R1.5',

        # Cost of Goods Sold
        'Cost of Goods Sold': 'C1',
        'Direct Labor': 'C2',
        'Manufacturing Overhead': 'C3',
        'Agricultural COGS': 'C4',

        # Expenses
        'Expense': 'X1',
        'Other Expense': 'X2',
        'Depreciation': 'X3',
        'Amortization': 'X4',
    }

    # Canadian GAAP Lead Sheet Codes (Canadian conventions)
    CANADIAN_GAAP_CODES = {
        # Assets - General (Canadian notation: CA, CB, etc.)
        'Bank': 'CA',
        'Accounts Receivable': 'CB',
        'Other Current Assets': 'OCA',  # CRITICAL FIX: Changed from 'CC' to avoid collision with Credit Card
        'Fixed Assets': 'FA',
        'Other Assets': 'OA',
        'Inventory': 'INV',
        'Prepaid Expenses': 'PRE',
        'Undeposited Funds': 'CA1',

        # Assets - Agricultural
        'Livestock': 'AG1',
        'Crops': 'AG2',
        'Agricultural Inventory': 'AG3',
        'Farm Equipment': 'AG4',
        'Agricultural Land': 'AG5',
        'Breeding Stock': 'AG6',
        'Growing Crops': 'AG7',
        'Harvested Crops': 'AG8',

        # Assets - Manufacturing
        'Raw Materials': 'MFG1',
        'Work in Process': 'WIP',
        'Finished Goods': 'FG',
        'Manufacturing Equipment': 'MFG4',
        'Factory Buildings': 'MFG5',
        'Tooling': 'MFG6',
        'Packaging Materials': 'MFG7',
        'Production Supplies': 'MFG8',

        # Assets - Other Industries
        'Construction in Progress': 'CIP',
        'Software Development': 'SD',
        'Oil & Gas Equipment': 'OG',
        'Mining Assets': 'MIN',
        'Real Estate Held for Sale': 'REHFS',  # CRITICAL FIX: Changed from 'RE' to avoid collision with Retained Earnings

        # Liabilities (Canadian notation: CL, LTL)
        'Accounts Payable': 'AP',
        'Credit Card': 'CC',
        'Other Current Liabilities': 'CL',
        'Long Term Liabilities': 'LTL',
        'Sales Tax Payable': 'GST',  # Canadian GST/HST
        'Payroll Liabilities': 'PAY',
        'Accrued Liabilities': 'ACR',
        'Deferred Revenue': 'DEF',
        'Mortgage Payable': 'MTG',
        'Equipment Loans': 'EQL',

        # Equity (Canadian notation)
        'Equity': 'EQ',
        'Retained Earnings': 'RE',
        'Opening Balance Equity': 'OBE',
        'Shareholder Equity': 'SE',
        'Partner Capital': 'PC',

        # Income (Canadian notation: REV)
        'Income': 'REV1',
        'Other Income': 'REV2',
        'Sales': 'SAL',
        'Service Income': 'SRV',
        'Agricultural Sales': 'AREV',
        'Manufacturing Sales': 'MREV',
        'Contract Revenue': 'CREV',

        # Cost of Goods Sold
        'Cost of Goods Sold': 'COGS',
        'Direct Labor': 'DL',
        'Manufacturing Overhead': 'OH',
        'Agricultural COGS': 'ACOGS',

        # Expenses
        'Expense': 'EXP',
        'Other Expense': 'OEXP',
        'Depreciation': 'DEP',
        'Amortization': 'AMO',
    }

    # IFRS Lead Sheet Codes (International standards - numbered sections)
    IFRS_CODES = {
        # Assets - IFRS uses numbered sections (1000-1999 for assets)
        'Bank': '1100',
        'Accounts Receivable': '1200',
        'Other Current Assets': '1300',
        'Fixed Assets': '1500',
        'Other Assets': '1900',
        'Inventory': '1400',
        'Prepaid Expenses': '1310',
        'Undeposited Funds': '1110',

        # Assets - Agricultural
        'Livestock': '1410',
        'Crops': '1420',
        'Agricultural Inventory': '1430',
        'Farm Equipment': '1540',
        'Agricultural Land': '1520',
        'Breeding Stock': '1411',
        'Growing Crops': '1421',
        'Harvested Crops': '1422',

        # Assets - Manufacturing
        'Raw Materials': '1440',
        'Work in Process': '1450',
        'Finished Goods': '1460',
        'Manufacturing Equipment': '1550',
        'Factory Buildings': '1560',
        'Tooling': '1551',
        'Packaging Materials': '1470',
        'Production Supplies': '1480',

        # Assets - Other Industries
        'Construction in Progress': '1570',
        'Software Development': '1710',
        'Oil & Gas Equipment': '1580',
        'Mining Assets': '1590',
        'Real Estate Held for Sale': '1350',

        # Liabilities - IFRS (2000-2999 for liabilities)
        'Accounts Payable': '2100',
        'Credit Card': '2110',
        'Other Current Liabilities': '2300',
        'Long Term Liabilities': '2500',
        'Sales Tax Payable': '2200',
        'Payroll Liabilities': '2210',
        'Accrued Liabilities': '2220',
        'Deferred Revenue': '2230',
        'Mortgage Payable': '2510',
        'Equipment Loans': '2520',

        # Equity - IFRS (3000-3999 for equity)
        'Equity': '3100',
        'Retained Earnings': '3200',
        'Opening Balance Equity': '3300',
        'Shareholder Equity': '3110',
        'Partner Capital': '3120',

        # Income - IFRS (4000-4999 for revenue)
        'Income': '4100',
        'Other Income': '4900',
        'Sales': '4110',
        'Service Income': '4120',
        'Agricultural Sales': '4130',
        'Manufacturing Sales': '4140',
        'Contract Revenue': '4150',

        # Cost of Goods Sold - IFRS (5000-5999 for COGS)
        'Cost of Goods Sold': '5100',
        'Direct Labor': '5200',
        'Manufacturing Overhead': '5300',
        'Agricultural COGS': '5400',

        # Expenses - IFRS (6000-6999 for expenses)
        'Expense': '6100',
        'Other Expense': '6900',
        'Depreciation': '6500',
        'Amortization': '6510',
    }

    def __init__(self):
        """Initialize LeadSheetMapper."""
        self.detected_standard: Optional[AccountingStandard] = None

    def detect_accounting_standard(self, company_data: Dict) -> AccountingStandard:
        """
        Detect the accounting standard from QuickBooks company data.

        Detection logic:
        1. Check company country/region
        2. Check currency (CAD = Canadian, others = check country)
        3. Check company preferences if available
        4. Default to US GAAP if uncertain

        Args:
            company_data: QB company information dictionary

        Returns:
            Detected accounting standard
        """
        if not company_data:
            logger.warning("No company data provided, defaulting to US_GAAP")
            self.detected_standard = 'US_GAAP'
            return self.detected_standard

        # Check country field (case-insensitive)
        country = (company_data.get('country') or
                   company_data.get('Country') or
                   company_data.get('companyCountry') or '').strip().upper()

        # Check currency
        currency = (company_data.get('currency') or
                    company_data.get('Currency') or
                    company_data.get('homeCurrency') or '').strip().upper()

        # Check address for country indicators
        address = (company_data.get('address') or
                   company_data.get('Address') or
                   company_data.get('companyAddress') or '').upper()

        # Detection: Canadian GAAP
        if (country in ['CA', 'CAN', 'CANADA'] or
            currency == 'CAD' or
            'CANADA' in address):
            logger.info("Detected Canadian GAAP from company data")
            self.detected_standard = 'CANADIAN_GAAP'
            return self.detected_standard

        # Detection: IFRS (International countries)
        # IFRS is used in 140+ countries including UK, EU, Australia, etc.
        ifrs_countries = {
            'GB', 'UK', 'UNITED KINGDOM', 'ENGLAND', 'SCOTLAND', 'WALES',
            'AU', 'AUS', 'AUSTRALIA',
            'NZ', 'NEW ZEALAND',
            'IN', 'IND', 'INDIA',
            'SG', 'SINGAPORE',
            'HK', 'HONG KONG',
            'MY', 'MALAYSIA',
            'ZA', 'SOUTH AFRICA',
            # EU countries
            'DE', 'GERMANY', 'FR', 'FRANCE', 'IT', 'ITALY', 'ES', 'SPAIN',
            'NL', 'NETHERLANDS', 'BE', 'BELGIUM', 'SE', 'SWEDEN', 'DK', 'DENMARK',
            'NO', 'NORWAY', 'FI', 'FINLAND', 'IE', 'IRELAND', 'AT', 'AUSTRIA',
            'PL', 'POLAND', 'PT', 'PORTUGAL', 'GR', 'GREECE', 'CZ', 'CZECH',
        }

        if country in ifrs_countries or currency in ['GBP', 'EUR', 'AUD', 'NZD', 'INR']:
            logger.info(f"Detected IFRS from company data (Country: {country}, Currency: {currency})")
            self.detected_standard = 'IFRS'
            return self.detected_standard

        # Default: US GAAP
        logger.info(f"Defaulting to US_GAAP (Country: {country or 'unknown'}, Currency: {currency or 'USD'})")
        self.detected_standard = 'US_GAAP'
        return self.detected_standard

    def get_lead_sheet_codes(self, accounting_standard: Optional[AccountingStandard] = None) -> Dict[str, str]:
        """
        Get lead sheet code mapping for the specified accounting standard.

        Args:
            accounting_standard: Accounting standard to use (uses detected if None)

        Returns:
            Dictionary mapping account types to lead sheet codes
        """
        standard = accounting_standard or self.detected_standard or 'US_GAAP'

        if standard == 'CANADIAN_GAAP':
            return self.CANADIAN_GAAP_CODES.copy()
        elif standard == 'IFRS':
            return self.IFRS_CODES.copy()
        else:
            return self.US_GAAP_CODES.copy()

    def get_lead_sheet_code(self, account_type: str,
                             accounting_standard: Optional[AccountingStandard] = None) -> str:
        """
        Get lead sheet code for a specific account type.

        Args:
            account_type: QB account type (e.g., 'Bank', 'Accounts Receivable')
            accounting_standard: Accounting standard to use (uses detected if None)

        Returns:
            Lead sheet code string (defaults to 'X9'/'OTH'/'9999' if not found)
        """
        standard = accounting_standard or self.detected_standard or 'US_GAAP'
        codes = self.get_lead_sheet_codes(standard)

        # Get default "Other" code based on standard
        if standard == 'CANADIAN_GAAP':
            default_code = 'OTH'
        elif standard == 'IFRS':
            default_code = '9999'
        else:
            default_code = 'X9'

        return codes.get(account_type, default_code)

    def get_type_code(self, account_type: str) -> str:
        """
        Get single-letter type code for account type (universal across all standards).

        Args:
            account_type: QB account type

        Returns:
            Single letter: A (Asset), L (Liability), E (Equity), R (Revenue), C (COGS), X (Expense)
        """
        type_map = {
            'Bank': 'A', 'Accounts Receivable': 'A', 'Other Current Assets': 'A',
            'Fixed Assets': 'A', 'Other Assets': 'A', 'Inventory': 'A',
            'Undeposited Funds': 'A', 'Prepaid Expenses': 'A',
            # Agricultural
            'Livestock': 'A', 'Crops': 'A', 'Agricultural Inventory': 'A',
            'Farm Equipment': 'A', 'Agricultural Land': 'A', 'Breeding Stock': 'A',
            'Growing Crops': 'A', 'Harvested Crops': 'A',
            # Manufacturing
            'Raw Materials': 'A', 'Work in Process': 'A', 'Finished Goods': 'A',
            'Manufacturing Equipment': 'A', 'Factory Buildings': 'A', 'Tooling': 'A',
            'Packaging Materials': 'A', 'Production Supplies': 'A',
            # Other assets
            'Construction in Progress': 'A', 'Software Development': 'A',
            'Oil & Gas Equipment': 'A', 'Mining Assets': 'A', 'Real Estate Held for Sale': 'A',
            # Liabilities
            'Accounts Payable': 'L', 'Credit Card': 'L', 'Other Current Liabilities': 'L',
            'Long Term Liabilities': 'L', 'Sales Tax Payable': 'L', 'Payroll Liabilities': 'L',
            'Accrued Liabilities': 'L', 'Deferred Revenue': 'L', 'Mortgage Payable': 'L',
            'Equipment Loans': 'L',
            # Equity
            'Equity': 'E', 'Retained Earnings': 'E', 'Opening Balance Equity': 'E',
            'Shareholder Equity': 'E', 'Partner Capital': 'E',
            # Revenue
            'Income': 'R', 'Other Income': 'R', 'Sales': 'R', 'Service Income': 'R',
            'Agricultural Sales': 'R', 'Manufacturing Sales': 'R', 'Contract Revenue': 'R',
            # COGS
            'Cost of Goods Sold': 'C', 'Direct Labor': 'C', 'Manufacturing Overhead': 'C',
            'Agricultural COGS': 'C',
            # Expenses
            'Expense': 'X', 'Other Expense': 'X', 'Depreciation': 'X', 'Amortization': 'X',
        }

        code = type_map.get(account_type)
        if code is None:
            logger.warning(f"Unmapped account type: {account_type}, defaulting to X")
            return 'X'
        return code


# CRITICAL FIX: Thread-safe singleton pattern
import threading
_mapper_instance: Optional[LeadSheetMapper] = None
_mapper_lock = threading.Lock()


def get_mapper() -> LeadSheetMapper:
    """
    Get singleton LeadSheetMapper instance (thread-safe).

    Returns:
        Global LeadSheetMapper instance
    """
    global _mapper_instance
    if _mapper_instance is None:
        with _mapper_lock:
            # Double-checked locking pattern
            if _mapper_instance is None:
                _mapper_instance = LeadSheetMapper()
    return _mapper_instance


def detect_and_configure(company_data: Dict) -> AccountingStandard:
    """
    Convenience function to detect accounting standard and configure global mapper.

    Args:
        company_data: QB company information

    Returns:
        Detected accounting standard
    """
    mapper = get_mapper()
    return mapper.detect_accounting_standard(company_data)
