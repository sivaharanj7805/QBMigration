# Intuit Developer App Registration

> **Application:** ForensicBridge  
> **Prepared:** 2026-01-18  
> **Status:** ⚠️ REQUIRES YOUR INPUT ON SEVERAL FIELDS

---

## Legal URLs

| Field | Value | Status |
|:------|:------|:-------|
| **End-user license agreement URL** | `https://forensicbridge.ca/legal/eula` | ⚠️ NEED TO CONFIRM |
| **Privacy policy URL** | `https://forensicbridge.ca/legal/privacy` | ⚠️ NEED TO CONFIRM |

> **❓ Questions for you:**
> 1. Do you have these pages published? If not, what URLs do you want to use?

---

## OAuth Configuration URLs

| Field | Value | Status |
|:------|:------|:-------|
| **Host domain** | `app.forensicbridge.ca` | ⚠️ NEED TO CONFIRM |
| **Launch URL** | `https://app.forensicbridge.ca/dashboard` | ⚠️ NEED TO CONFIRM |
| **Disconnect URL** | `https://app.forensicbridge.ca/disconnect` | ⚠️ NEED TO CONFIRM |

> **❓ Questions for you:**
> 1. What is your production domain? (e.g., `app.forensicbridge.ca` or `forensicbridge.ca`)
> 2. What URL should users land on after OAuth authentication?
> 3. What URL handles disconnection from QuickBooks?

---

## Regulated Industries

Based on ForensicBridge functionality (data migration, no lending/payments/insurance):

| Industry | Applicable? | Reason |
|:---------|:------------|:-------|
| **Insurance** | ❌ No | ForensicBridge does not offer insurance |
| **Investment / financial planning** | ❌ No | ForensicBridge does not advise on securities or retirement plans |
| **Lending** | ❌ No | ForensicBridge does not provide or facilitate lending |
| **Payments / money movement** | ❌ No | ForensicBridge does not process payments or move money |

> **✅ Recommended:** None of the regulated industries apply to ForensicBridge.

---

## App Categories (Select up to 4)

Based on ForensicBridge functionality, recommended categories:

| Category | Selected | Reason |
|:---------|:---------|:-------|
| **Data Management** | ✅ | Core function: migrating and transforming QB data |
| **Accounting** | ✅ | Integrates with QuickBooks accounting software |
| **Document Management** | ✅ | Generates audit certificates, export bundles |
| **Legal and Regulatory Compliance** | ✅ | Forensic audit trails, SHA-256 verification |

> **❓ Question:** Are these 4 categories acceptable, or would you prefer different ones?

---

## IP Whitelisting

| Field | Value | Status |
|:------|:------|:-------|
| **Country** | Canada | ⚠️ NEED TO CONFIRM |
| **IP Address Type** | Single IP or Range? | ⚠️ NEED TO CONFIRM |
| **IP Address(es)** | `?` | ⚠️ NEED YOUR AWS/SERVER IPs |

> **❓ Questions for you:**
> 1. What AWS region are you deploying to? (Currently configured for `ca-central-1`)
> 2. Do you have static Elastic IPs assigned to your EC2/load balancer?
> 3. If using NAT Gateway, what is the outbound IP?

---

## Summary of Information Needed From You

1. **Legal URLs:**
   - EULA URL: `https://____________________`
   - Privacy Policy URL: `https://____________________`

2. **OAuth URLs:**
   - Host domain (no https): `____________________`
   - Launch URL: `https://____________________`
   - Disconnect URL: `https://____________________`

3. **Categories:** Confirm the 4 categories above or specify different ones

4. **IP Whitelisting:**
   - Country: `____________________`
   - IP Address(es): `____________________`

---

*Once you provide this information, I'll update this document with the final values ready for submission.*
