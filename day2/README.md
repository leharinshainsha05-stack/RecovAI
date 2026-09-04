# RecovAI - Day 2: State Machine & Guardrails

**Status:** ✅ Ready to Implement  
**Focus:** Database + State Machine + Audit Ledger + Scheduling  
**Duration:** 3-5 hours  
**Deliverable:** Persistent recovery workflows with audit trail  

---

## 🎯 Day 2 Overview

### Goals
1. ✅ Set up PostgreSQL database with ORM
2. ✅ Implement 15-state machine for recovery workflows
3. ✅ Build immutable audit ledger with SHA256 hash chain
4. ✅ Create background job scheduler (APScheduler)
5. ✅ Integrate with Day 1 API backend

### What You'll Build
- **SQLAlchemy Models** (6 tables + relationships)
- **State Machine** (15 states, 25+ transitions)
- **Audit Ledger** (cryptographic hash chain)
- **Background Scheduler** (3 scheduled jobs)
- **Integration Layer** (connects to Day 1)

---

## 📁 Day 2 Files

### Core Python Files (1,200+ lines)

| File | Lines | Purpose |
|------|-------|---------|
| `Day2_database.py` | 350 | SQLAlchemy ORM models |
| `Day2_statemachine.py` | 400 | State transitions & workflows |
| `Day2_audit.py` | 300 | Immutable ledger & hash chain |
| `Day2_scheduler.py` | 350 | APScheduler job definitions |
| `Day2_integration.py` | 200 | Integration with Day 1 |
| `Day2_tests.py` | 300 | Test suite (25+ tests) |

### Documentation
- `Day2_README.md` (this file)
- `Day2_SUMMARY.md` (overview & metrics)

---

## 🗄️ Database Schema

### Tables (6)

#### 1. **customers** - Customer lifecycle management
```sql
CREATE TABLE customers (
  id VARCHAR(50) PRIMARY KEY,
  email VARCHAR(255) UNIQUE,
  phone VARCHAR(20),
  lifetime_value_in_paise INTEGER,
  subscription_count INTEGER,
  ltv_tier ENUM('TIER_1', 'TIER_2'),
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);
```

**Columns:**
- `id` - Customer ID (from Razorpay)
- `lifetime_value_in_paise` - LTV for grace period calculation
- `ltv_tier` - Tier 1 (72h) or Tier 2 (7d)
- Indexes: ltv_tier, lifetime_value_in_paise

#### 2. **invoices** - Payment invoices with status
```sql
CREATE TABLE invoices (
  id VARCHAR(50) PRIMARY KEY,
  customer_id VARCHAR(50) FOREIGN KEY,
  subscription_id VARCHAR(50),
  amount_in_paise INTEGER,
  status ENUM('INITIAL', 'GATEWAY_FAILURE', ..., 'RECOVERED'),
  failed_at TIMESTAMP,
  recovered_at TIMESTAMP,
  paused_at TIMESTAMP,
  created_at TIMESTAMP
);
```

**Columns:**
- `status` - 15 recovery states
- `failed_at` - When payment first failed
- `recovered_at` - When successfully recovered
- `paused_at` - When service was suspended
- Indexes: customer_id, status, failed_at

#### 3. **recovery_flows** - State machine entities
```sql
CREATE TABLE recovery_flows (
  id VARCHAR(50) PRIMARY KEY,
  invoice_id VARCHAR(50) FOREIGN KEY,
  customer_id VARCHAR(50) FOREIGN KEY,
  current_block ENUM('BLOCK_1', ..., 'BLOCK_6'),
  current_state ENUM('INITIAL', ..., 'DND_ABORTED'),
  
  block_1_retries_done INTEGER,
  block_2_retry_scheduled BOOLEAN,
  block_3_instrument_dead BOOLEAN,
  
  grace_period_tier ENUM('TIER_1', 'TIER_2'),
  grace_period_start TIMESTAMP,
  grace_period_end TIMESTAMP,
  
  fallback_link_id VARCHAR(255),
  fallback_link_url VARCHAR(500),
  
  final_state ENUM(...),
  final_state_reached_at TIMESTAMP,
  
  created_at TIMESTAMP
);
```

**Key Columns:**
- `current_block` - Current recovery block (1-6)
- `current_state` - Current state machine state (1-15)
- `block_*` - Block-specific counters/flags
- `grace_period_*` - LTV-tiered grace period tracking
- `final_state_*` - Terminal state tracking
- Indexes: current_state, grace_period_end

#### 4. **audit_log** - Immutable audit trail (append-only)
```sql
CREATE TABLE audit_log (
  id BIGSERIAL PRIMARY KEY,
  event_id VARCHAR(50) UNIQUE,
  timestamp TIMESTAMP,
  
  invoice_id VARCHAR(50) FOREIGN KEY,
  customer_id VARCHAR(50) FOREIGN KEY,
  
  action ENUM('WEBHOOK_RECEIVED', ..., 'AUDIT_LOG_WRITTEN'),
  block ENUM('BLOCK_1', ..., 'BLOCK_6'),
  root_cause ENUM('GATEWAY_TIMEOUT', ..., 'UNKNOWN'),
  
  state_before ENUM(...),
  state_after ENUM(...),
  
  details JSONB,
  
  audit_hash VARCHAR(255),  -- SHA256 of current event
  prev_audit_hash VARCHAR(255),  -- SHA256 of previous event
  
  created_at TIMESTAMP
);
```

**Key Columns:**
- `audit_hash` - SHA256 of current event (+ prev hash)
- `prev_audit_hash` - Previous event's hash (chain linkage)
- `details` - JSON metadata
- Indexes: invoice_id, hash, timestamp
- **APPEND-ONLY** - Never update, only insert

#### 5. **scheduled_retries** - Scheduled retry jobs
```sql
CREATE TABLE scheduled_retries (
  id VARCHAR(50) PRIMARY KEY,
  invoice_id VARCHAR(50) FOREIGN KEY,
  
  retry_type VARCHAR(50),  -- 'salary_window', 'grace_period_check', etc.
  scheduled_for TIMESTAMP,
  executed_at TIMESTAMP,
  
  is_executed BOOLEAN,
  is_cancelled BOOLEAN,
  
  created_at TIMESTAMP
);
```

#### 6. **gateway_health** - Real-time gateway metrics
```sql
CREATE TABLE gateway_health (
  gateway_name VARCHAR(50) PRIMARY KEY,
  
  uptime FLOAT,  -- 0.0-1.0
  success_rate FLOAT,  -- 0.0-1.0
  latency_p50 INTEGER,  -- milliseconds
  latency_p99 INTEGER,  -- milliseconds
  
  status VARCHAR(50),  -- 'healthy', 'degraded', 'down'
  last_updated TIMESTAMP
);
```

---

## 🔄 State Machine (15 States)

### State Diagram

```
INITIAL
  ├─→ GATEWAY_FAILURE (BLOCK_1)
  │     ├─→ SCHEDULED_RETRY_1
  │     │     ├─→ SCHEDULED_RETRY_2
  │     │     │     ├─→ RECOVERED ✅
  │     │     │     └─→ BLOCK_4_ESCALATED
  │     │     └─→ RECOVERED ✅
  │     ├─→ RECOVERED ✅
  │     └─→ DND_ABORTED ❌
  │
  ├─→ INSUFFICIENT_FUNDS (BLOCK_2)
  │     ├─→ SALARY_WINDOW_SCHEDULED
  │     │     ├─→ SALARY_RETRY_ATTEMPTED
  │     │     │     ├─→ RECOVERED ✅
  │     │     │     └─→ BLOCK_4_ESCALATED
  │     │     └─→ DND_ABORTED ❌
  │     ├─→ BLOCK_4_ESCALATED
  │     └─→ DND_ABORTED ❌
  │
  ├─→ INSTRUMENT_INVALID (BLOCK_3)
  │     └─→ BLOCK_4_ESCALATED
  │           ├─→ FALLBACK_LINK_SENT
  │           │     ├─→ IN_GRACE_PERIOD
  │           │     │     ├─→ RECOVERED_VIA_FALLBACK ✅
  │           │     │     ├─→ SUBSCRIPTION_PAUSED ❌
  │           │     │     └─→ DND_ABORTED ❌
  │           │     └─→ DND_ABORTED ❌
  │           └─→ DND_ABORTED ❌
```

### 15 States Explained

| State | Block | Terminal | Description |
|-------|-------|----------|-------------|
| `INITIAL` | - | No | New invoice, no failure |
| `GATEWAY_FAILURE` | 1 | No | Network/gateway error detected |
| `SCHEDULED_RETRY_1` | 1 | No | First retry scheduled (T+15m) |
| `SCHEDULED_RETRY_2` | 1 | No | Second retry scheduled (T+2h) |
| `INSUFFICIENT_FUNDS` | 2 | No | Low balance detected |
| `SALARY_WINDOW_SCHEDULED` | 2 | No | Waiting for salary window (10 AM) |
| `SALARY_RETRY_ATTEMPTED` | 2 | No | Salary window retry executed |
| `INSTRUMENT_INVALID` | 3 | No | Dead card/mandate detected |
| `BLOCK_4_ESCALATED` | 4 | No | Escalated to fallback |
| `FALLBACK_LINK_SENT` | 4 | No | 1-click UPI link dispatched |
| `IN_GRACE_PERIOD` | 4 | No | Waiting for link payment (72h/7d) |
| `RECOVERED` | - | **Yes** ✅ | Payment successful |
| `RECOVERED_VIA_FALLBACK` | 4 | **Yes** ✅ | Fallback link paid |
| `SUBSCRIPTION_PAUSED` | - | **Yes** ❌ | Service suspended |
| `DND_ABORTED` | - | **Yes** ❌ | User opted out |

---

## 🔐 Audit Ledger with Hash Chain

### How It Works

Every audit event creates an immutable ledger entry:

```
Event 1: SHA256({event1_data})
  → hash_1 = "a1b2c3d4..."

Event 2: SHA256({event2_data} + hash_1)
  → hash_2 = "e5f6g7h8..."

Event 3: SHA256({event3_data} + hash_2)
  → hash_3 = "i9j0k1l2..."
```

### Integrity Verification

If someone tampersEvent 2:
- Event 2's hash changes
- Event 3 still references old Event 2 hash
- Chain is **broken** → Tampering detected! 🚨

### Example Audit Trail

```json
[
  {
    "event_id": "evt_001",
    "timestamp": "2025-01-01T10:30:00Z",
    "action": "WEBHOOK_RECEIVED",
    "invoice_id": "inv_001",
    "error_code": "GATEWAY_TIMEOUT",
    "state_after": "GATEWAY_FAILURE",
    "audit_hash": "a1b2c3d4e5f6g7h8...",
    "prev_audit_hash": null
  },
  {
    "event_id": "evt_002",
    "timestamp": "2025-01-01T10:30:15Z",
    "action": "RETRY_SCHEDULED",
    "state_before": "GATEWAY_FAILURE",
    "state_after": "SCHEDULED_RETRY_1",
    "audit_hash": "e5f6g7h8i9j0k1l2...",
    "prev_audit_hash": "a1b2c3d4e5f6g7h8..."
  },
  ...
]
```

---

## ⏰ Background Scheduler (3 Jobs)

### Job 1: Salary Window Retry (Block 2)

**Trigger:** 10:00 AM IST daily  
**Cron:** `0 10 * * *`  
**Action:**
1. Find flows in `SALARY_WINDOW_SCHEDULED` state
2. Retry via Razorpay auto-debit API
3. If success: → `RECOVERED`
4. If fail: → `BLOCK_4_ESCALATED`

**RBI Compliance:**
- ✅ Single retry per salary window
- ✅ Prevents bank penalty bounce fees
- ✅ Respects customer balance cycles

### Job 2: Grace Period Expiry Check (Block 4)

**Trigger:** Every 15 minutes  
**Action:**
1. Find flows in `IN_GRACE_PERIOD` with `grace_period_end <= NOW`
2. Check payment link status via Razorpay API
3. If paid: → `RECOVERED_VIA_FALLBACK`
4. If unpaid: → `SUBSCRIPTION_PAUSED` + suspend service

**RBI Compliance:**
- ✅ Service only suspended after grace period expires
- ✅ LTV-tiered grace periods (72h/7d)
- ✅ Zero messaging after expiry

### Job 3: Retry Backoff Execution (Block 1)

**Trigger:** Every 5 minutes  
**Action:**
1. Find `ScheduledRetry` records with `scheduled_for <= NOW`
2. Execute T+15m and T+2h retries
3. Update state based on result
4. Mark as executed

**Guardrails:**
- ✅ Max 2 retries per invoice
- ✅ Exponential backoff (15m, 2h)
- ✅ Silent execution (no notifications)

---

## 🚀 Quick Start (Day 2)

### Prerequisites
- PostgreSQL 14+ running
- Python 3.8+
- Day 1 files from previous session

### Step 1: Install Additional Dependencies

```bash
# Install Day 2 specific packages
pip install -r Day2_requirements.txt

# Or add to existing Day 1 environment
pip install sqlalchemy psycopg2-binary apscheduler redis asyncpg
```

### Step 2: Set Up PostgreSQL Database

```bash
# Create database
createdb recovai

# Or using psql:
psql -c "CREATE DATABASE recovai;"
```

### Step 3: Initialize Database Schema

```bash
python
>>> from Day2_database import create_all_tables, get_session_maker
>>> SessionLocal, engine = get_session_maker('postgresql://user:pass@localhost/recovai')
>>> create_all_tables(engine)
# Output: ✓ All tables created successfully
```

### Step 4: Test State Machine

```bash
python Day2_statemachine.py
```

### Step 5: Test Audit Ledger

```bash
python Day2_audit.py
```

### Step 6: Test Scheduler

```bash
python Day2_scheduler.py
```

---

## 📊 Database Configuration

### PostgreSQL Connection String

```python
# .env file
DATABASE_URL=postgresql://user:password@localhost:5432/recovai
```

### SQLAlchemy Configuration

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://user:password@localhost:5432/recovai"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine)
```

### With Environment Variables

```python
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
```

---

## 🔗 Integration with Day 1

### Architecture

```
Day 1: FastAPI API
    ↓ (webhook received)
Day 2: Diagnostic Engine
    ↓ (classifies error)
Day 2: RecoveryFlowManager
    ↓ (creates flow + transitions state)
Day 2: AuditLedger
    ↓ (logs to audit trail)
Day 2: RecoveryScheduler
    ↓ (schedules background jobs)
Database: PostgreSQL
```

### Integration Steps

1. **On Webhook Receipt (Day 1):**
   ```python
   # Day1_main.py
   from Day2_database import create_session
   from Day2_statemachine import RecoveryFlowManager
   
   session = create_session()
   manager = RecoveryFlowManager(state_machine)
   flow = manager.create_flow(
       invoice_id=webhook.data.invoice_id,
       customer_id=webhook.data.customer_id,
       block=diagnostic_result.block,
       root_cause=diagnostic_result.root_cause,
       recovery_score=diagnostic_result.recovery_score,
       session=session
   )
   ```

2. **On State Transitions:**
   ```python
   # When marking as recovered
   manager.mark_recovered(flow, via_fallback=False, session=session)
   ```

3. **Log to Audit Trail:**
   ```python
   # Every state transition
   audit_ledger.log_event(
       session=session,
       invoice_id=flow.invoice_id,
       customer_id=flow.customer_id,
       action=ActionTypeEnum.RECOVERED,
       state_before=old_state,
       state_after=new_state
   )
   ```

---

## 🧪 Testing Day 2

### Run Tests

```bash
pytest Day2_tests.py -v
```

### Expected Output

```
test_database_connection PASSED
test_customer_creation PASSED
test_invoice_creation PASSED
test_recovery_flow_creation PASSED
test_state_transitions PASSED
...
======================== 25+ passed in 3.21s ==========================
```

### Test Coverage

- ✅ Database models (CRUD operations)
- ✅ State machine (all transitions)
- ✅ State machine guardrails (max retries, cooldown)
- ✅ Audit ledger (hash chain, integrity)
- ✅ Recovery flow manager (all workflows)
- ✅ Scheduler job registration
- ✅ Grace period calculations

---

## 📈 Performance Targets (Day 2)

| Metric | Target | Notes |
|--------|--------|-------|
| State Transition | <10ms | In-memory operation |
| Audit Log Write | <50ms | Database insert |
| Hash Chain Verify | <100ms | 50 events |
| Scheduler Startup | <5s | Job registration |
| Database Query | <100ms | With indexes |

---

## 🎯 Day 2 Checklist

Before moving to Day 3:

- [ ] PostgreSQL installed and running
- [ ] Day2_database.py creates all tables
- [ ] Customer, Invoice, RecoveryFlow created
- [ ] 15-state machine working
- [ ] All state transitions valid
- [ ] State machine transitions tested
- [ ] Audit ledger writing events
- [ ] Hash chain calculated correctly
- [ ] Audit trail verified (chain integrity)
- [ ] Scheduler jobs registered
- [ ] Database schema validated
- [ ] Tests passing (25+)
- [ ] Integration with Day 1 API ready

---

## 🚨 Common Issues & Solutions

### Issue: "psycopg2.OperationalError: could not connect to server"
```bash
# Ensure PostgreSQL is running
brew services start postgresql  # macOS
sudo systemctl start postgresql  # Linux

# Test connection
psql -c "SELECT version();"
```

### Issue: "ModuleNotFoundError: No module named 'sqlalchemy'"
```bash
pip install sqlalchemy psycopg2-binary
```

### Issue: "Audit hash mismatch" during verification
- Check if audit logs were modified
- Recalculate hashes to verify integrity
- Review audit_hash and prev_audit_hash columns

### Issue: Scheduler jobs not executing
- Verify RecoveryScheduler is started: `scheduler.start()`
- Check job logs in terminal
- Verify database connection is working
- Check cron trigger times (timezone-aware)

---

## 📚 File Structure

```
Day2/
├── Day2_database.py          ← SQLAlchemy models (6 tables)
├── Day2_statemachine.py      ← State machine (15 states)
├── Day2_audit.py             ← Audit ledger (hash chain)
├── Day2_scheduler.py         ← Background jobs (APScheduler)
├── Day2_integration.py       ← Integration with Day 1
├── Day2_tests.py             ← Test suite (25+ tests)
├── Day2_requirements.txt      ← Additional dependencies
├── Day2_README.md            ← This file
└── Day2_SUMMARY.md           ← Metrics & overview
```

---

## ✅ Success Criteria

**Day 2 is complete when:**

✅ All 6 database tables created  
✅ 15-state machine working  
✅ All state transitions valid  
✅ Audit ledger logging events  
✅ Hash chain integrity verified  
✅ 3 background jobs scheduled  
✅ 25+ tests passing  
✅ Integration with Day 1 ready  

---

## 🎉 Next Steps (Day 3)

After Day 2 is complete, Day 3 adds:
- Razorpay SDK integration
- Payment link generation
- Live health router
- SMS/WhatsApp notifications
- Real-time gateway monitoring

---

## 📞 Support

See Day 2_SUMMARY.md for:
- Architecture diagrams
- Performance metrics
- Quality benchmarks
- Production roadmap

---

**Status:** Ready to Implement ✅  
**Duration:** 3-5 hours  
**Complexity:** Medium  
**Prerequisites:** Day 1 complete + PostgreSQL installed  

