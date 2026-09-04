# RecovAI - Day 1: Core Backend & Data Models

**Status:** ✅ Ready to Start  
**Focus:** FastAPI Backend Setup + Diagnostic Classifier + Test Suite  
**Deliverable:** Working webhook endpoint + error classification engine  

---

## 📋 Day 1 Overview

### Goal
Set up the core FastAPI backend with Pydantic schemas and implement the diagnostic classifier that routes payment failures to 6 recovery blocks.

### What You'll Build
1. **FastAPI Application** - Production-ready API framework
2. **Pydantic Models** - Data validation for all entities (invoices, webhooks, audit logs, etc.)
3. **Diagnostic Engine** - Classifier that maps error codes → recovery blocks
4. **Webhook Receiver** - Razorpay webhook ingestion with signature validation
5. **Test Suite** - Comprehensive unit & integration tests

### Deliverables
- ✅ `Day1_models.py` - All data models
- ✅ `Day1_diagnostic.py` - Diagnostic classifier + test cases
- ✅ `Day1_main.py` - FastAPI application
- ✅ `Day1_tests.py` - Complete test suite
- ✅ `Day1_requirements.txt` - Python dependencies

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -r Day1_requirements.txt
```

### 2. Run the FastAPI Server

```bash
# Option A: Direct Python execution (hot reload)
python Day1_main.py

# Option B: Uvicorn (recommended)
uvicorn Day1_main:app --reload --host 0.0.0.0 --port 8000

# Option C: Uvicorn with custom settings
uvicorn Day1_main:app --reload --port 8000 --log-level info
```

**Expected Output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 3. Visit API Documentation

Once server is running, open in browser:
- **Swagger UI (Interactive):** http://localhost:8000/docs
- **ReDoc (Pretty):** http://localhost:8000/redoc

---

## 🧪 Testing the Diagnostic Engine

### Method 1: CLI Test (Standalone)

Run the diagnostic engine tests directly:

```bash
python Day1_diagnostic.py
```

**Output:**
```
================================================================================
RecovAI Diagnostic Engine - Day 1 Test Run
================================================================================

Test 1: Gateway Timeout (BLOCK_1)
------------------------------------------------------------
Block: BLOCK_1
Root Cause: GATEWAY_TIMEOUT
Severity: HIGH
Recovery Score: 0.88
Next Action: LIVE_REROUTE_OR_SCHEDULED_RETRY
```

### Method 2: FastAPI Test Endpoints

Use these endpoints to test classification:

#### A. Test Single Error Code

```bash
# Test gateway timeout
curl http://localhost:8000/api/v1/diagnostic/test-webhook/GATEWAY_TIMEOUT

# Test expired card
curl http://localhost:8000/api/v1/diagnostic/test-webhook/CARD_EXPIRED

# Test insufficient funds
curl http://localhost:8000/api/v1/diagnostic/test-webhook/INSUFFICIENT_FUNDS
```

#### B. Direct Classification Endpoint

```bash
# POST with webhook payload
curl -X POST http://localhost:8000/api/v1/diagnostic/classify \
  -H "Content-Type: application/json" \
  -d '{
    "id": "evt_test_001",
    "event": "charge.failed",
    "created_at": 1693500000,
    "data": {
      "id": "ch_test_001",
      "invoice_id": "inv_test_001",
      "customer_id": "cust_test_001",
      "amount": 99900,
      "currency": "INR",
      "error": {
        "code": "GATEWAY_TIMEOUT",
        "message": "Request timeout from issuer gateway"
      },
      "payment_method": {
        "type": "card",
        "card": {"id": "card_test_001"}
      },
      "status": "failed",
      "created_at": 1693500000
    }
  }'
```

#### C. Reference Endpoints

```bash
# Get all supported error codes
curl http://localhost:8000/api/v1/errors/codes

# Get hard-decline codes (0% recovery)
curl http://localhost:8000/api/v1/errors/hard-declines

# Get soft-decline codes (retryable)
curl http://localhost:8000/api/v1/errors/soft-declines
```

### Method 3: Pytest (Full Suite)

Run the complete test suite:

```bash
# Install pytest (if not already installed)
pip install pytest pytest-asyncio

# Run all tests
pytest Day1_tests.py -v

# Run specific test class
pytest Day1_tests.py::TestDiagnosticEngine -v

# Run with coverage
pytest Day1_tests.py --cov=Day1_diagnostic --cov=Day1_main --cov-report=html
```

**Expected Output:**
```
test_gateway_timeout_classification PASSED                     [ 5%]
test_insufficient_funds_classification PASSED                  [ 10%]
test_card_expired_classification PASSED                        [ 15%]
test_fraud_declined_classification PASSED                      [ 20%]
test_health_check PASSED                                       [ 25%]
...
======================== 30 passed in 2.34s ==========================
```

---

## 📊 Classification Examples

### Block 1: Gateway & Network Downtime
**Error Codes:** `GATEWAY_TIMEOUT`, `REQUEST_TIMEOUT`, `NETWORK_ERROR`  
**Recovery Score:** 0.85-0.95  
**Next Action:** Live reroute (<200ms) or scheduled retry

```json
{
  "error_code": "GATEWAY_TIMEOUT",
  "block": "BLOCK_1",
  "root_cause": "GATEWAY_TIMEOUT",
  "severity": "HIGH",
  "recovery_score": 0.88
}
```

### Block 2: Liquidity Lag & Salary Cycle
**Error Codes:** `INSUFFICIENT_FUNDS`, `LOW_BALANCE`  
**Recovery Score:** 0.75-0.85  
**Next Action:** Schedule retry at 10:00 AM on 1st/2nd of month

```json
{
  "error_code": "INSUFFICIENT_FUNDS",
  "block": "BLOCK_2",
  "root_cause": "INSUFFICIENT_FUNDS",
  "severity": "MEDIUM",
  "recovery_score": 0.78
}
```

### Block 3: Dead Mandates & Instruments
**Error Codes:** `CARD_EXPIRED`, `MANDATE_REVOKED`, `CVV_MISMATCH`, `FRAUD_DECLINED`  
**Recovery Score:** 0.0 (Hard decline, no direct retry possible)  
**Next Action:** Skip to Block 4 (Fallback UPI link)

```json
{
  "error_code": "CARD_EXPIRED",
  "block": "BLOCK_3",
  "root_cause": "CARD_EXPIRED",
  "severity": "HIGH",
  "recovery_score": 0.0
}
```

### Block 4: Alternative Fallback Instrument
**Error Codes:** Any after retry exhaustion or hard decline  
**Recovery Score:** 0.60-0.70  
**Next Action:** Generate 1-click UPI payment link

```json
{
  "error_code": "CARD_EXPIRED",
  "block": "BLOCK_4",
  "root_cause": "CARD_EXPIRED",
  "next_action": "GENERATE_1_CLICK_UPI_LINK"
}
```

---

## 📁 Project Structure

```
Day1/
├── Day1_models.py              # Pydantic models (11 classes)
├── Day1_diagnostic.py          # Diagnostic engine (core logic)
├── Day1_main.py                # FastAPI application
├── Day1_tests.py               # Complete test suite
├── Day1_requirements.txt        # Python dependencies
└── Day1_README.md              # This file
```

### File Descriptions

#### `Day1_models.py`
Contains Pydantic models for data validation:
- **Enums:** BlockType, RootCauseType, SeverityLevel, RecoveryState, LTVTier, ActionType
- **Webhook Models:** WebhookEvent, ChargeData, PaymentError, PaymentMethod
- **Entity Models:** Invoice, RecoveryFlow, AuditLogEvent, CustomerLTV
- **API Response Models:** WebhookAckResponse, LiveRerouteResponse, etc.

**Usage:**
```python
from Day1_models import WebhookEvent, DiagnosticResult, BlockType

webhook = WebhookEvent(**payload_dict)
assert isinstance(webhook, WebhookEvent)
```

#### `Day1_diagnostic.py`
Core diagnostic engine:
- **DiagnosticEngine** class with error code mapping
- **Error classification logic** (error_code → block)
- **Recovery score calculation**
- **Context-aware rules** (month-end, gateway health, etc.)
- **Test helper functions**

**Usage:**
```python
from Day1_diagnostic import DiagnosticEngine, create_test_webhook

engine = DiagnosticEngine()
webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
result = engine.classify(webhook)
```

#### `Day1_main.py`
FastAPI application with endpoints:
- **Webhook receiver:** `POST /webhooks/payment-failure`
- **Diagnostic endpoints:** `POST /api/v1/diagnostic/classify`
- **Test endpoints:** `GET /api/v1/diagnostic/test-webhook/{error_code}`
- **Reference endpoints:** `/api/v1/errors/codes`, etc.

**Endpoints:**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhooks/payment-failure` | Receive Razorpay webhook |
| POST | `/api/v1/diagnostic/classify` | Classify single webhook |
| POST | `/api/v1/diagnostic/batch` | Classify batch of webhooks |
| GET | `/api/v1/diagnostic/test-webhook/{code}` | Test specific error code |
| GET | `/api/v1/errors/codes` | Reference: all error codes |
| GET | `/api/v1/errors/hard-declines` | Reference: non-retryable codes |
| GET | `/api/v1/errors/soft-declines` | Reference: retryable codes |
| GET | `/health` | Health check |
| GET | `/ready` | Readiness probe |

#### `Day1_tests.py`
Comprehensive test suite with 30+ tests:
- **Unit Tests:** DiagnosticEngine classification logic
- **API Tests:** Endpoint responses and behavior
- **Integration Tests:** End-to-end flows
- **Performance Tests:** Speed and throughput

**Test Coverage:**
- All 12 error codes tested
- All 4 blocks (BLOCK_1-4) tested
- Hard decline vs soft decline classification
- Batch processing
- API response validation
- Performance benchmarks (<100ms per classification)

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file (optional):

```bash
# Razorpay webhook secret (for production signature verification)
RAZORPAY_WEBHOOK_SECRET=your_secret_key_here

# Debug mode (skip signature verification)
DEBUG_MODE=true

# FastAPI settings
HOST=0.0.0.0
PORT=8000
```

### Load Environment

```python
from dotenv import load_dotenv

load_dotenv()  # Loads from .env file
```

---

## 🔍 Understanding the Diagnostic Classifier

### Error Code Mapping

The classifier uses a hardcoded error code mapping:

```python
ERROR_CODE_MAPPING = {
    "GATEWAY_TIMEOUT": (GATEWAY_TIMEOUT, BLOCK_1, HIGH),
    "INSUFFICIENT_FUNDS": (INSUFFICIENT_FUNDS, BLOCK_2, MEDIUM),
    "CARD_EXPIRED": (CARD_EXPIRED, BLOCK_3, HIGH),
    ...
}
```

### Classification Flow

```
1. Parse error_code from webhook
2. Look up in ERROR_CODE_MAPPING
   ├─ If found → Get (root_cause, block, severity)
   └─ If not found → Default to BLOCK_4, UNKNOWN
3. Apply contextual rules
   ├─ INSUFFICIENT_FUNDS + day in [25-31] → force BLOCK_2
   ├─ Hard decline error → force BLOCK_3
   └─ Low gateway health → stay in BLOCK_1
4. Calculate recovery_score per block
   ├─ BLOCK_1: 0.85-0.95 (transient)
   ├─ BLOCK_2: 0.75-0.85 (liquidity cycle)
   ├─ BLOCK_3: 0.0 (hard decline)
   └─ BLOCK_4: 0.60-0.70 (fallback)
5. Determine next_action
6. Return DiagnosticResult
```

### Recovery Score Interpretation

| Score | Meaning | Action |
|-------|---------|--------|
| 0.0 | Cannot recover via direct retry | Escalate to Block 4 (fallback) |
| 0.1-0.5 | Low probability | Fallback link recommended |
| 0.5-0.8 | Medium probability | Scheduled retry recommended |
| 0.8-1.0 | High probability | Live reroute or immediate retry |

---

## 🐛 Debugging

### Enable Verbose Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Day1_diagnostic")
```

### Test with Debug Endpoint

```bash
# Get detailed classification for any error code
curl http://localhost:8000/api/v1/diagnostic/test-webhook/GATEWAY_TIMEOUT | jq .
```

### Inspect Webhook Payload

```bash
# Log raw payload in FastAPI
@app.post("/webhooks/payment-failure")
async def receive_webhook(request: Request):
    body = await request.body()
    print(f"Raw payload: {body.decode()}")  # Debug output
    ...
```

---

## ✅ Day 1 Checklist

Before moving to Day 2, complete these:

- [ ] All dependencies installed (`pip install -r Day1_requirements.txt`)
- [ ] FastAPI server starts without errors
- [ ] Swagger UI accessible at http://localhost:8000/docs
- [ ] Diagnostic engine tests pass (`python Day1_diagnostic.py`)
- [ ] Full pytest suite passes (`pytest Day1_tests.py -v`)
- [ ] All 5 error codes classify correctly:
  - [ ] GATEWAY_TIMEOUT → BLOCK_1
  - [ ] INSUFFICIENT_FUNDS → BLOCK_2
  - [ ] CARD_EXPIRED → BLOCK_3
  - [ ] FRAUD_DECLINED → BLOCK_3
  - [ ] Unknown error → BLOCK_4
- [ ] Recovery scores are correct per block
- [ ] API endpoints respond with 200/202 status codes
- [ ] Test webhook endpoint works: `/api/v1/diagnostic/test-webhook/GATEWAY_TIMEOUT`

---

## 🎯 What You've Built Today

✅ **Production-ready FastAPI backend**
- Async request handling
- Built-in OpenAPI documentation
- CORS support for future frontend

✅ **Robust data validation**
- Pydantic models for all entities
- Type hints for IDE autocomplete
- Automatic JSON schema generation

✅ **Intelligent error classifier**
- 12 error codes mapped to 4 blocks
- Context-aware classification rules
- Recovery probability scoring

✅ **Comprehensive test suite**
- 30+ unit and integration tests
- Performance benchmarks
- Edge case coverage

✅ **Production-ready webhook handler**
- Razorpay signature verification
- Error handling and logging
- Async processing support

---

## 📝 Next Steps (Day 2)

After Day 1 is complete, Day 2 will add:
- **PostgreSQL database** for persistent storage
- **State machine engine** for recovery workflows
- **Retry scheduling** with APScheduler
- **Immutable audit ledger** with cryptographic hashing
- **Database models** (invoices, recovery_flows, audit_log)

---

## 🆘 Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'fastapi'"
**Solution:** Install dependencies: `pip install -r Day1_requirements.txt`

### Issue: Port 8000 already in use
**Solution:** Use different port: `uvicorn Day1_main:app --port 8001`

### Issue: Tests fail with "assert recovery_score == 0.0"
**Solution:** Verify hard_decline codes are mapped correctly in `ERROR_CODE_MAPPING`

### Issue: Webhook signature verification fails
**Solution:** Enable DEBUG_MODE: `export DEBUG_MODE=true` or set in code

---

## 📚 References

- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **Pydantic Docs:** https://docs.pydantic.dev/
- **Razorpay Webhooks:** https://razorpay.com/docs/webhooks/
- **Pytest Docs:** https://docs.pytest.org/

---

## 🎉 Conclusion

You now have a production-ready backend that can:
1. ✅ Receive payment failure webhooks from Razorpay
2. ✅ Validate and parse webhook payloads
3. ✅ Classify failures into 6 recovery blocks
4. ✅ Calculate recovery probability scores
5. ✅ Respond with proper HTTP status codes
6. ✅ Log all operations for debugging

**Ready for Day 2? Let's build the state machine! 🚀**

---

**Questions?** Refer to the architecture document or review the inline code comments.

**Last Updated:** August 29, 2026  
**Status:** ✅ Ready to Code
