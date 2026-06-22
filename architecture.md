# AI Firewall / DLP — Architecture

## Overview

ระบบ Transparent Proxy ที่คอย intercept HTTPS traffic จาก corporate network ไปยัง LLM platforms
โดย redact PII ออกก่อนส่ง และ de-anonymize response ที่กลับมา โดยไม่กระทบ workflow ของ user

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Corporate Network                      │
│                                                         │
│   [User Devices]                                        │
│   Browser / App                                         │
│        │                                                │
│        ▼                                                │
│   [Load Balancer]  ←─── health check                   │
│        │                                                │
│   ┌────┴────┐                                           │
│   ▼         ▼                                           │
│ [Proxy 1] [Proxy 2]   ← mitmproxy (HA, 2 nodes)        │
│   └────┬────┘                                           │
│        │  SSL Inspection                                │
│        ▼                                                │
│   [DLP Orchestrator]                                    │
│        │                                                │
│   ┌────┼────────┐                                       │
│   ▼    ▼        ▼                                       │
│ [Text] [File]  [OCR]   ← Workers (scale อิสระ)         │
│ Worker Worker  Worker                                   │
│   └────┼────────┘                                       │
│        │                                                │
│        ▼                                                │
│   [Redis]  ← session mapping store (TTL 1hr)            │
│        │                                                │
│        ▼                                                │
│   [Audit Logger]  → log store (90 days)                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
        │
        ▼ (redacted request)
┌───────────────────┐
│   Internet        │
│  ChatGPT / Gemini │
│  Grok / etc.      │
└───────────────────┘
        │
        ▼ (response)
   [DLP Orchestrator]
        │
   De-anonymize (exact → fuzzy th.90 → log)
        │
        ▼
   [User]
```

---

## Request Flow (Detailed)

### Outbound (User → LLM)

```
1. User ส่ง request ไป chatgpt.com
2. Load Balancer รับ → forward ไป Proxy node
3. Proxy ทำ SSL Inspection (MITM)
4. ตรวจ domain ว่าอยู่ใน LLM whitelist ไหม
   - ไม่ใช่ → forward ผ่านปกติ
   - ใช่ → ส่งไป DLP Orchestrator
5. Orchestrator ตรวจ content-type
   - text/plain    → Text Worker
   - PDF/DOCX      → File Worker
   - image/*       → OCR Worker
6. Worker redact PII → บันทึก mapping ใน Redis
   session:{id}:PERSON_001 = "สมชาย"
7. ส่ง redacted request ออกไปยัง LLM
```

### Inbound (LLM → User)

```
1. Response กลับมาจาก LLM
2. Proxy ดักจับ
3. ส่งไป De-anonymizer
4. ดึง mapping จาก Redis ตาม session_id
5. Exact match → replace token กลับ
   ไม่เจอ → Fuzzy match (threshold 90)
   ไม่เจอ → Log warning + ส่งกลับ as-is
6. Re-pack file (ถ้า response เป็น DOCX/PDF)
7. ส่ง response กลับหา User
```

### Fail Safe (DLP Crash)

```
DLP Orchestrator crash
        ↓
Block เฉพาะ LLM domains
        ↓
Internet ปกติยังใช้ได้
        ↓
User เห็น error page "AI tools unavailable, contact IT"
        ↓
Alert ไปหา Admin ทันที (email / Slack)
```

---

## Component Breakdown

| Component | Technology | หน้าที่ |
|---|---|---|
| Load Balancer | HAProxy / Nginx | กระจาย traffic ระหว่าง 2 proxy nodes |
| Proxy | mitmproxy | SSL inspection, intercept HTTPS |
| DLP Orchestrator | Python (FastAPI) | รับงาน แจกให้ worker ที่เหมาะสม |
| Text Worker | Microsoft Presidio + PyThaiNLP | Detect + redact PII ใน plain text |
| File Worker | python-docx, pdfplumber, reportlab | Parse และ re-pack DOCX/PDF |
| OCR Worker | EasyOCR | Extract text จาก image + bounding box redact |
| Mapping Store | Redis | เก็บ session mapping (TTL 1hr) |
| Audit Logger | Python → PostgreSQL | บันทึกทุก redaction event |
| Admin Dashboard | React + FastAPI | stats, whitelist management, audit log |
| Domain Updater | Cron job (Python) | Auto-update LLM domain whitelist |
| MDM | Jamf / Microsoft Intune | บังคับ CA cert + mobile policy |

---

## PII Entity Types

| Entity | ตัวอย่าง | Token รูปแบบ |
|---|---|---|
| ชื่อ-นามสกุล | สมชาย ใจดี | `<<P001>>` |
| เบอร์โทร | 0812345678 | `<<PH001>>` |
| อีเมล | somchai@company.com | `<<EM001>>` |
| เลขบัตรประชาชน | 1234567890123 | `<<ID001>>` |
| ที่อยู่ | 123 ถ.สุขุมวิท กรุงเทพ | `<<AD001>>` |
| ชื่อบริษัท/โปรเจกต์ | Project Phoenix | `<<ORG001>>` |
| รูปภาพ | (OCR แล้ว redact) | overlay สีดำทับ |

---

## Scalability

- Text Worker: scale ได้ตาม CPU load
- OCR Worker: scale ได้อิสระ (หนัก GPU/CPU)
- File Worker: scale ได้ตาม memory
- Redis: Cluster mode สำหรับ 1,000 concurrent sessions
- Proxy: 2 nodes เป็น minimum, เพิ่มได้ถ้า traffic สูง

---

## Security Considerations

- CA Certificate deploy ผ่าน MDM (Jamf/Intune) ไปทุกเครื่อง
- Redis encrypt at rest + TLS in transit
- Mapping data ไม่เก็บใน log — log เก็บแค่ token ไม่เก็บ original value
- Admin Dashboard ต้องผ่าน MFA

---

## Out of Scope (v1)

- Mobile hotspot / VPN ส่วนตัว (แก้ด้วย MDM policy)
- LLM on-premise
- Real-time de-anonymization สำหรับ streaming response (v2)
