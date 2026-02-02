# M&A Security & Compliance Complete Checklist

## Executive Summary

**Your Timeline:** 4 months (by June 2, 2026)
**Reality Check:** SOC 2 Type II takes 6-18 months. You need a "Minimum Viable Security Posture" strategy.

---

## WHAT YOU NEED vs WHAT YOU CAN SKIP

| Requirement | Must Have | Can Defer | Notes |
|-------------|-----------|-----------|-------|
| Security Policies | YES | - | 2-3 weeks to create |
| Penetration Test | YES | - | $7-20K, 2 weeks |
| Vulnerability Scan | YES | - | $2-5K, 1-2 days |
| SOC 2 Type I | Ideal | YES | Can accept holdback |
| SOC 2 Type II | - | YES | 6-18 months, post-close |
| ISO 27001 | - | YES | 6-12 months |
| IP Assignment Audit | YES | - | Critical for any deal |
| Open Source Audit | YES | - | SBOM required |
| Data Mapping | YES | - | 2-4 weeks |
| HIPAA | - | YES | Not healthcare |
| PCI DSS | - | YES | Using Stripe |
| PIPEDA Compliance | YES | - | Canadian data |

---

## PHASE 1: IMMEDIATE (Week 1-2) - Cost: ~$5,000

### 1.1 Security Gap Assessment
- [ ] Run automated security scan (free tools available)
- [ ] Document current security posture
- [ ] Identify critical gaps

### 1.2 Generate Software Bill of Materials (SBOM)
```bash
# Python dependencies
pip install pip-audit
pip-audit --format=json > sbom_python.json

# .NET dependencies
dotnet list package --format=json > sbom_dotnet.json

# JavaScript dependencies
npm audit --json > sbom_npm.json
```

### 1.3 IP Assignment Inventory
- [ ] List all contributors (employees, contractors)
- [ ] Check if each has signed IP assignment agreement
- [ ] Identify any gaps

### 1.4 Document Architecture
- [ ] Network diagram
- [ ] Data flow diagram
- [ ] Cloud infrastructure diagram

---

## PHASE 2: SHORT-TERM (Days 15-30) - Cost: ~$25,000-50,000

### 2.1 Security Policies (CREATE THESE)

**MUST HAVE (10 Core Policies):**

| Policy | Status | Owner | Due Date |
|--------|--------|-------|----------|
| 1. Information Security Policy | [ ] | | |
| 2. Acceptable Use Policy | [ ] | | |
| 3. Access Control Policy | [ ] | | |
| 4. Data Classification Policy | [ ] | | |
| 5. Incident Response Policy | [ ] | | |
| 6. Password/Authentication Policy | [ ] | | |
| 7. Change Management Policy | [ ] | | |
| 8. Vendor Management Policy | [ ] | | |
| 9. Data Retention Policy | [ ] | | |
| 10. Encryption Policy | [ ] | | |

### 2.2 External Penetration Test
- [ ] Hire pentest firm ($7,000-20,000)
- [ ] Scope: External network + web application
- [ ] Timeline: 1-2 weeks
- [ ] Remediate critical/high findings immediately

**Recommended Firms:**
- Bishop Fox
- Rapid7
- Coalfire
- NCC Group
- Or any CREST-certified firm

### 2.3 Vulnerability Scanning
- [ ] Run Nessus/Qualys/OpenVAS scan
- [ ] Document all findings
- [ ] Remediate critical vulnerabilities
- [ ] Create remediation plan for others

### 2.4 MFA Implementation
- [ ] MFA on all admin accounts
- [ ] MFA on all cloud consoles (AWS, Azure, GCP)
- [ ] MFA on code repositories
- [ ] MFA on production database access
- [ ] Document MFA coverage

### 2.5 Open Source License Audit
```bash
# Use FOSSA, Snyk, or WhiteSource
# Or manual review:
pip-licenses --format=csv > python_licenses.csv
```

**License Risk Assessment:**

| License Type | Risk | Action Required |
|--------------|------|-----------------|
| MIT, Apache 2.0, BSD | Low | Attribution only |
| LGPL | Medium | Document compliance |
| GPL, AGPL | HIGH | Legal review needed |

---

## PHASE 3: MEDIUM-TERM (Days 30-60) - Cost: ~$15,000-30,000

### 3.1 Data Inventory & Mapping

| Data Category | Source | Storage | Encryption | Retention | Legal Basis |
|--------------|--------|---------|------------|-----------|-------------|
| QuickBooks data | User upload | AWS S3 ca-central-1 | AES-256 | Per customer | Contract |
| User accounts | Registration | PostgreSQL | bcrypt | Account life | Contract |
| Payment info | Stripe | Stripe (PCI) | Stripe managed | Per Stripe | Contract |
| Audit logs | System | CloudWatch | At rest | 12 months | Legitimate interest |

### 3.2 Vendor Risk Assessment

| Vendor | Service | Data Access | SOC 2? | Risk Tier |
|--------|---------|-------------|--------|-----------|
| AWS | Cloud hosting | All data | Yes | Critical |
| Stripe | Payments | Payment info | Yes | Critical |
| SendGrid/SES | Email | Email addresses | Yes | High |
| Sentry | Error tracking | Error logs | Yes | Medium |

### 3.3 Incident Response Plan

**Required Sections:**
- [ ] Incident classification (P1-P4)
- [ ] Response team roles
- [ ] Detection procedures
- [ ] Containment procedures
- [ ] Communication templates
- [ ] Regulatory notification requirements
- [ ] Post-incident review process

**Notification Timelines:**
| Regulation | Notification Deadline |
|------------|----------------------|
| GDPR | 72 hours |
| PIPEDA | "As soon as feasible" |
| CCPA | "Most expedient time possible" |
| State breach laws | Varies (typically 30-60 days) |

### 3.4 Business Continuity / Disaster Recovery

- [ ] Recovery Time Objective (RTO): ___ hours
- [ ] Recovery Point Objective (RPO): ___ hours
- [ ] Backup verification (test restore)
- [ ] Documented recovery procedures
- [ ] Contact escalation list

### 3.5 Centralized Logging Setup
- [ ] All authentication events logged
- [ ] All admin actions logged
- [ ] All data access logged
- [ ] Log retention: 12 months minimum
- [ ] Alerting configured

---

## PHASE 4: PRE-DUE DILIGENCE (Days 60-90) - Cost: ~$20,000-40,000

### 4.1 SOC 2 Type I Readiness (Optional but Recommended)

**Fast-Track Option:** Use compliance automation platform
- Vanta: ~$10,000/year
- Drata: ~$12,000/year
- Secureframe: ~$10,000/year

**SOC 2 Type I Timeline:**
- Week 1-4: Implement controls with platform
- Week 5-8: Pre-audit assessment
- Week 9-10: Audit
- **Total: 2.5 months**

**Cost Breakdown:**
| Item | Cost |
|------|------|
| Compliance platform | $10,000-15,000 |
| Auditor (Type I) | $10,000-25,000 |
| **Total** | **$20,000-40,000** |

### 4.2 IP Documentation Package

**Required Documents:**
- [ ] IP Assignment Agreement (employee template)
- [ ] IP Assignment Agreement (contractor template)
- [ ] Signed agreements for all contributors
- [ ] Open source license compliance report
- [ ] SBOM (Software Bill of Materials)
- [ ] Trade secret protection documentation

**Missing IP Assignments - Fix Options:**
1. Get retroactive assignment (preferred)
2. Get license grant
3. Document in disclosure schedule with remediation plan

### 4.3 Technical Due Diligence Prep

**Code Quality Evidence:**
- [ ] Static analysis scan results (SonarQube, Semgrep)
- [ ] Code coverage report
- [ ] Technical debt assessment
- [ ] Architecture documentation

**Infrastructure Evidence:**
- [ ] Cloud configuration review
- [ ] Infrastructure-as-code (Terraform, CloudFormation)
- [ ] Security group / firewall rules
- [ ] WAF configuration

---

## VIRTUAL DATA ROOM CONTENTS

### Folder Structure

```
/DataRoom
├── /1_Corporate
│   ├── Certificate of Incorporation
│   ├── Bylaws
│   ├── Cap table
│   └── Board resolutions
├── /2_Financial
│   ├── Financial statements (3 years)
│   ├── Tax returns (3 years)
│   ├── Revenue breakdown
│   └── Customer concentration analysis
├── /3_Legal
│   ├── Material contracts
│   ├── Customer agreements (template)
│   ├── Vendor agreements
│   └── Litigation history
├── /4_IP
│   ├── IP assignment register
│   ├── Employee IP agreements
│   ├── Contractor IP agreements
│   ├── Open source audit report
│   ├── SBOM
│   └── Patent filings (if any)
├── /5_Security
│   ├── Security policies
│   ├── Penetration test report
│   ├── Vulnerability scan results
│   ├── SOC 2 report (if available)
│   ├── Incident response plan
│   ├── BCP/DR plan
│   └── Data flow diagrams
├── /6_Technology
│   ├── Architecture documentation
│   ├── API documentation
│   ├── Infrastructure diagrams
│   ├── Technical debt assessment
│   └── Code quality reports
├── /7_Privacy
│   ├── Privacy policy
│   ├── Data processing agreements
│   ├── Data inventory
│   ├── PIPEDA compliance documentation
│   └── Cookie consent implementation
├── /8_HR
│   ├── Org chart
│   ├── Key employee agreements
│   ├── Non-compete agreements
│   └── Employee handbook
└── /9_Product
    ├── Product roadmap
    ├── Customer list (anonymized)
    ├── Feature documentation
    └── Demo access instructions
```

---

## COMPLIANCE COST SUMMARY

### What You Can Do in 4 Months

| Item | Cost | Time | Priority |
|------|------|------|----------|
| Security policies | $5,000-15,000 | 3-4 weeks | P1 |
| Penetration test | $7,000-20,000 | 2 weeks | P1 |
| Vulnerability scan | $2,000-5,000 | 2 days | P1 |
| SBOM generation | $5,000-15,000 | 2 weeks | P1 |
| IP audit | $10,000-25,000 | 3 weeks | P1 |
| Data mapping | $10,000-25,000 | 3 weeks | P1 |
| Incident response plan | $5,000-10,000 | 2 weeks | P1 |
| SOC 2 Type I | $20,000-40,000 | 10 weeks | P2 |
| Compliance platform | $10,000-15,000/yr | Ongoing | P2 |
| **TOTAL** | **$74,000-170,000** | | |

### What to Defer (Accept Holdback/Escrow)

| Item | Typical Holdback | Post-Close Timeline |
|------|------------------|---------------------|
| SOC 2 Type II | 5-10% of deal | 6-12 months |
| ISO 27001 | 5-10% of deal | 12 months |
| Full policy maturity | 2-5% of deal | 6 months |

---

## DEAL IMPACT OF SECURITY GAPS

### What Kills Deals (73% walk-away rate)

- Undisclosed data breach history
- Significant IP ownership disputes
- GPL/AGPL code contamination
- Unpatched critical vulnerabilities
- No security controls whatsoever

### What Reduces Valuation (5-15%)

- No SOC 2 certification
- Incomplete IP assignments
- Open source license issues
- Missing security policies
- No penetration test history

### What's Acceptable with Plan

- SOC 2 Type I in progress
- Minor policy gaps
- Recent pentest scheduled
- Some IP assignments missing (if remediation clear)

---

## YOUR SPECIFIC ACTION ITEMS

### Week 1 (Feb 3-9)
- [ ] Run vulnerability scan on all systems
- [ ] Generate SBOM for all components
- [ ] List all code contributors
- [ ] Start drafting security policies

### Week 2 (Feb 10-16)
- [ ] Engage penetration testing firm
- [ ] Complete IP assignment inventory
- [ ] Begin data mapping exercise
- [ ] Document current architecture

### Week 3-4 (Feb 17 - Mar 2)
- [ ] Complete 10 core security policies
- [ ] Receive penetration test results
- [ ] Remediate critical vulnerabilities
- [ ] Create incident response plan

### Week 5-8 (Mar 3-30)
- [ ] Complete data inventory
- [ ] Vendor risk assessments
- [ ] Fix any IP assignment gaps
- [ ] Set up centralized logging
- [ ] Consider SOC 2 Type I kickoff

### Week 9-12 (Mar 31 - Apr 27)
- [ ] Virtual data room complete
- [ ] All documentation finalized
- [ ] Remediation evidence compiled
- [ ] Ready for due diligence

### Week 13-16 (Apr 28 - May 25)
- [ ] Support due diligence requests
- [ ] Address buyer questions
- [ ] Negotiate remediation terms
- [ ] Close deal

---

## QUICK REFERENCE: REGULATORY REQUIREMENTS

### PIPEDA (Canada) - REQUIRED
- [ ] Privacy policy published
- [ ] Consent mechanisms documented
- [ ] Data breach notification procedures
- [ ] Cross-border transfer documentation
- [ ] Individual access request procedures

### GDPR (If EU customers) - IF APPLICABLE
- [ ] Lawful basis documented for each processing
- [ ] Data subject rights procedures
- [ ] DPA with all processors
- [ ] Privacy impact assessments
- [ ] 72-hour breach notification capability

### CCPA/CPRA (California) - IF APPLICABLE
- [ ] "Do Not Sell" mechanism
- [ ] Privacy policy with CCPA disclosures
- [ ] Consumer request procedures
- [ ] Vendor contracts updated

---

## TEMPLATES TO CREATE

1. **Information Security Policy** - 10-15 pages
2. **Acceptable Use Policy** - 3-5 pages
3. **Access Control Policy** - 5-8 pages
4. **Incident Response Plan** - 15-20 pages
5. **Data Classification Standard** - 3-5 pages
6. **Vendor Security Questionnaire** - 50-100 questions
7. **Employee IP Assignment Agreement** - 2-3 pages
8. **Contractor IP Assignment Agreement** - 3-4 pages
9. **Data Processing Agreement** - 5-8 pages
10. **Privacy Policy** - 5-10 pages

---

## TOOLS & VENDORS

### Compliance Automation
- Vanta ($10K/yr) - Fastest SOC 2 path
- Drata ($12K/yr) - Good for multi-framework
- Secureframe ($10K/yr) - Developer-friendly

### Penetration Testing
- Bishop Fox
- NCC Group
- Rapid7
- Coalfire

### Vulnerability Scanning
- Nessus (Tenable)
- Qualys
- OpenVAS (free)

### Code Scanning
- Snyk (SCA + SAST)
- SonarQube (Code quality)
- Semgrep (SAST)
- FOSSA (License compliance)

### Data Mapping
- OneTrust
- BigID
- Transcend

---

*Document Version: 1.0*
*Created: February 2, 2026*
*For: ForensicBridge M&A Readiness*
