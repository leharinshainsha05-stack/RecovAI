# 💰 RecovAI: Autonomous Payment Recovery Engine

> **Empirical AI Buildathon Capstone**  
> An intelligent, multi-rail recovery pipeline for recurring payments, transforming involuntary customer churn into recovered ARR through automated diagnostics, real-time routing, and cryptographic auditability.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Executive Summary

Failed recurring card debits and subscription mandates cost modern SaaS and digital businesses up to 10% of their annual recurring revenue (ARR) in involuntary customer churn. Standard recovery mechanisms rely on naive, scheduled retry spam that triggers customer fatigue, wastes merchant gateway transaction fees, and runs afoul of regulatory limits.

**RecovAI** is an autonomous payment recovery orchestrator built specifically for the Indian and global payments ecosystem. Operating through a 6-block intelligent state machine, it performs synchronous gateway diagnostics in under 50ms, respects customer salary liquidity cycles, suppresses fatal instrument retries, issues dynamic fallback payment rails, and tracks every state transition inside a tamper-evident SHA-256 cryptographic ledger.

Incoming Webhook Failure
│
▼
┌────────────────────────────────────────────────────────┐
│  Day 1: Diagnostic Engine & Failure Classifier         │
│  Classifies 12 error codes across 4 operational blocks │
└───────────────────────┬────────────────────────────────┘
                        │
┌───────────────────────┴────────────────────────┐
▼                                                ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ Block 1: Network Auto-Retry  │ │ Block 2: Payday Cycle Retry  │
│ Live Reroute (<200ms budget) │ │ 10:00 AM IST Salary Window   │
└──────────────┬───────────────┘ └──────────────┬───────────────┘
               │                                │
               └────────────────┬───────────────┘
                                │ (On Failure / Hard Decline)
                                ▼
┌────────────────────────────────────────────────────────┐
│ Block 3: Dead Instrument Suppression                   │
│ Suppresses retries on expired cards/revoked mandates   │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Block 4: Dynamic 1-Click Fallback Links                │
│ Razorpay UPI/Card links + LTV-tiered grace periods     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Block 5: Compliance Guardrails & SHA-256 Ledger        │
│ Hard 2-retry cap, 6h cooldown, DND, chained hashes     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Block 6: Pre-Emptive Account Aggregator (Roadmap)      │
│ Pre-flight balance check via RBI AA (T-24h window)     │
└────────────────────────────────────────────────────────┘
---

## 📊 Benchmark & Empirical Performance

Verified across a standardized 50-transaction synthetic test suite modeling real-world payment distributions:

| Evaluation Metric | Production Target | RecovAI Result | Assessment |
| :--- | :---: | :---: | :---: |
| **Invoice Recovery Rate** | $\ge 70.0\%$ | **74.0%** (37 / 50) | ✅ **PASS** |
| **Gross Revenue Recovery** | $\ge 70.0\%$ | **79.9%** (₹64,229 / ₹80,351) | ✅ **PASS** |
| **Block 1 (Network) Recovery** | $\ge 80.0\%$ | **95.0%** (19 / 20) | ✅ **PASS** |
| **Block 2 (Liquidity) Recovery** | $\ge 60.0\%$ | **83.3%** (10 / 12) | ✅ **PASS** |
| **Block 3 (Dead Card) Suppression** | Baseline Filter | **100%** Retries Blocked | ✅ **PASS** |
| **Block 4 (Fallback Link) Conversion** | $\ge 30.0\%$ | **50.0%** Converted | ✅ **PASS** |
| **Live Reroute Budget** | $< 200\text{ ms}$ | **145 ms (P99)** | ✅ **PASS** |
| **Audit Trail Cryptographic Coverage**| $100\%$ | **100% Verified Chain** | ✅ **PASS** |

---

## 🛠️ The 6-Day Engineering Progression

### Day 1: Core Backend & Diagnostic Classification Engine
* **FastAPI Application:** Built a modular, asynchronous API framework handling ingested webhook notifications (`POST /webhooks/payment-failure`).
* **Pydantic Validation Schemas:** Developed 11 core data models covering webhook envelopes, transaction payloads, gateway errors, and diagnostic outcomes.
* **Intelligent Diagnostic Engine:** Implemented error classification mapping 12 discrete gateway error codes (e.g., `GATEWAY_TIMEOUT`, `INSUFFICIENT_FUNDS`, `CARD_EXPIRED`, `FRAUD_DECLINED`) to 4 functional recovery blocks.
* **Context-Aware Scoring:** Calculates recovery probability scores ($0.0$ to $1.0$) based on error severity, historical gateway uptime, and calendar dates.

### Day 2: State Machine, Background Scheduling & SHA-256 Audit Ledger
* **15-State Workflow Machine:** Implemented state transition logic enforcing strict recovery pathways across 25+ guarded transitions.
* **SQLAlchemy Database Architecture:** Configured relational storage for customers, invoices, active recovery flows, scheduled jobs, and audit events.
* **Cryptographic SHA-256 Audit Chain:** Built an append-only audit ledger where every state transition's hash is chained to its previous event hash ($H_n = \text{SHA-256}(D_n + H_{n-1})$), ensuring mathematical tamper-evidence.
* **Background Scheduler (APScheduler):** Configured 3 asynchronous jobs:
  1. *Salary Window Retry:* 10:00 AM daily check for liquidity windows.
  2. *Grace Period Monitor:* 15-minute polling for link payment or service suspension.
  3. *Exponential Backoff Runner:* Automated T+15m and T+2h network retry triggers.

### Day 3: Razorpay Integration, Sub-200ms Live Rerouting & Notifications
* **Razorpay Payment Manager:** Automated payment link generation, recurring e-mandates, and tokenized auto-debits via official Razorpay SDK APIs.
* **Sub-200ms Live Reroute Engine:** Implemented real-time gateway selection evaluating latency, uptime, and success rates across multiple rails (Razorpay, PayU, Instamojo, Cashfree) within a 50ms decision budget.
* **Multi-Channel Notification Dispatcher:** Integrated SMS, WhatsApp, and email dispatch with strict Do-Not-Disturb (DND) suppression logic.
* **HMAC Signature Security:** Implemented cryptographic payload verification using `X-Razorpay-Signature` validation.

### Day 4: Benchmark Harness, Empirical Proof & Financial Modeling
* **Synthetic Transaction Generator:** Synthesized 50 transaction payloads simulating real payment mixtures (40% network, 25% balance, 20% dead cards, 15% manual).
* **Multi-Tier Financial Engine:** Modeled net revenue impact accounting for direct recovery amounts, 2% processing fees, Customer Acquisition Cost (CAC) churn defense, and Lifetime Value (LTV) customer retention.
* **Automated Benchmark Runner:** Built a headless test orchestrator producing structured JSON telemetry (`benchmark_report.json`) and pass/fail criterion checks.

### Day 5: Real-Time Monitoring Dashboard & Block 6 Production Roadmap
* **Streamlit Operational Dashboard:** Visualized key operational KPIs, status distributions, block-by-block performance bars, and financial waterfall flows.
* **Dynamic SHA-256 Ledger Viewer:** Interactive tabular audit viewer displaying unique cryptographic digests for each state transition.
* **Production Roadmap Architecture (Block 6):** Structured a strategic 6-step proposal detailing proactive payment failure interception using the Reserve Bank of India (RBI) Account Aggregator framework.

### Day 6: Capstone Packaging, Documentation & Submission
* Finalized packaging, dependency management, and production documentation.

---

## 🏗️ 6-Block Production Architecture
┌────────────────────────────────────────────────────────────────────────┐
│ Block 1: Network & Gateway Auto-Retry                                  │
│ • Targets: Transient 5xx errors, timeouts, and gateway connection drops│
│ • Strategy: Live reroute (<200ms) or exponential backoff (T+15m, T+2h) │
│ • Guardrail: Hard ceiling of 2 retries per invoice                     │
└────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Block 2: Payday & Salary Window Recovery                               │
│ • Targets: INSUFFICIENT_FUNDS and low customer liquidity lag           │
│ • Strategy: Schedules single retry at 10:00 AM on 1st/2nd of month     │
│ • Guardrail: Zero immediate retries to prevent customer bank penalties │
└────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Block 3: Dead Instrument Retry Suppression                             │
│ • Targets: CARD_EXPIRED, MANDATE_REVOKED, CVV_MISMATCH, FRAUD_DECLINED │
│ • Strategy: Instant retry suppression; routes straight to fallback     │
│ • Benefit: Eliminates wasted gateway retry fees                        │
└────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Block 4: Dynamic 1-Click Fallback Links                                │
│ • Targets: Hard declines and exhausted retry workflows                 │
│ • Strategy: Dispatches dynamic Razorpay UPI/Card links with grace time │
│ • Customer Tiers: Tier 1 = 72-hour grace; Tier 2 (High LTV) = 7 days   │
└────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Block 5: Compliance Guardrails & SHA-256 Audit Ledger                  │
│ • Enforces 2-retry hard caps, 6-hour communication cooldowns, and DND  │
│ • Implements cryptographic SHA-256 hash chains for all transitions     │
└────────────────────────────────────────────────────────────────────────┘
                                    │
┌───────────────────────────────────▼────────────────────────────────────┐
│ Block 6: Pre-Emptive Account Aggregator Roadmap                        │
│ • Future Vision: Proactive failure interception via consented bank data│
│ • Leverages RBI DEPA/Sahamati framework at T-24 hours before debits    │
└────────────────────────────────────────────────────────────────────────┘
---

## 🚀 Quickstart & Installation

### 1. Prerequisites
* Python 3.10+
* Git
* *(Optional)* Redis & PostgreSQL for persistent live mode

### 2. Clone & Environment Setup
```bash
# Clone the repository
git clone [https://github.com/your-username/recovai.git](https://github.com/your-username/recovai.git)
cd recovai

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate       # On Windows: venv\Scripts\activate

# Install all dependencies
pip install -r requirements.txt



```

### 3. Environment Configuration

Create a `.env` file in the root directory:

```env
RAZORPAY_KEY_ID=rzp_test_your_test_key_here
RAZORPAY_KEY_SECRET=your_test_secret_here
DEBUG_MODE=true
HOST=0.0.0.0
PORT=8000

```

### 4. Run the Full Benchmark Suite

Execute the synthetic generation and benchmark evaluation engine:


python day4/Day4_benchmark_harness.py



*Generates `benchmark_report.json` with recovery metrics, financial ROI, and cryptographic audit traces.*

### 5. Launch the Streamlit Interactive Dashboard


streamlit run day5/Day5_dashboard.py



Open [http://localhost:8501](http://localhost:8501) in your browser.



## 🧪 Testing

Run the automated test suites covering classification, state machines, and integrations:


# Run all unit and integration tests
pytest day1/Day1_tests.py day2/Day2_tests.py day3/Day3_tests.py -v

# Run performance benchmark tests (<200ms live reroute)
pytest day3/Day3_tests.py::TestPerformance -v



---

## 📁 Repository Structure

```text
recovai/
├── .gitignore                      # Git exclusion rules
├── requirements.txt                # Unified production dependencies
├── README.md                       # Master capstone documentation
├── benchmark_report.json           # Active benchmark empirical results
├── create_db.py                    # Database bootstrapping utility
│
├── day1/                           # Day 1: Core API & Diagnostic Engine
│   ├── Day1_diagnostic.py          # Error classification logic & scoring
│   ├── Day1_main.py                # FastAPI endpoints & webhook handler
│   ├── Day1_models.py              # Pydantic data schemas
│   ├── Day1_tests.py               # Classification unit tests
│   └── README.md                   # Day 1 technical notes
│
├── day2/                           # Day 2: State Machine & Audit Ledger
│   ├── Day2_audit.py               # SHA-256 cryptographic hash chain
│   ├── Day2_database.py            # SQLAlchemy database models
│   ├── Day2_integration.py         # Day 1 + Day 2 bridge
│   ├── Day2_scheduler.py           # APScheduler background tasks
│   ├── Day2_statemachine.py        # 15-state recovery workflow engine
│   ├── Day2_tests.py               # State transition & audit tests
│   └── README.md                   # Day 2 technical notes
│
├── day3/                           # Day 3: Razorpay SDK & Live Rerouting
│   ├── Day3_integration.py         # Unified engine orchestrator
│   ├── Day3_live_reroute.py        # Real-time (<200ms) gateway selector
│   ├── Day3_notifications.py      # SMS/WhatsApp DND-safe notifier
│   ├── Day3_razorpay.py            # Razorpay API client wrapper
│   └── README.md                   # Day 3 technical notes
│
├── day4/                           # Day 4: Benchmarking & Proof
│   ├── Day4_benchmark_harness.py   # Test suite runner & orchestrator
│   ├── Day4_engine_runner.py       # Recovery execution simulator
│   ├── Day4_recovery_scorer.py     # Multi-factor financial & rate scorer
│   ├── Day4_synthetic_data.py      # 50-transaction synthetic generator
│   └── README.md                   # Day 4 technical notes
│
└── day5/                           # Day 5: Monitoring UI & Architecture
    ├── Day5_advanced_metrics.py    # Analytics aggregators
    ├── Day5_alert_system.py        # Anomaly detection & alerting
    ├── Day5_dashboard.py           # Streamlit executive UI
    ├── Day5_metrics_dashboard.py   # Terminal console dashboard
    ├── Day5_transaction_history.py # Transaction explorer & filter
    └── README.md                   # Day 5 technical notes

```

---

## 📜 Regulatory Compliance & Design Guardrails

* **RBI Mandate Adherence:** Complies with RBI recurring payment directives. Silent, non-spamming retry intervals prevent cardholder penalty charges.
* **DND Opt-Out Compliance:** Instant suppression of all transactional notifications and recovery links upon receiving customer unsubscribe/opt-out signals.
* **Cryptographic Auditability:** Every action taken by RecovAI is recorded with an immutable SHA-256 fingerprint chained to the previous transition, providing compliance teams and auditors with tamper-evident operational logs.
* **Scoped Data Isolation:** Account Aggregator architectural flows (Block 6) use scoped, one-time consent tokens dedicated strictly to pre-flight balance sufficiency verification.

---

## 📄 License

This project is open-source software licensed under the **MIT License**.

```

---
```

