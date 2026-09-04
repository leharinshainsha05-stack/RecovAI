"""
RecovAI: Pydantic Models for Data Validation
Day 1: Core data models for webhooks, invoices, and recovery flows
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field, validator


# ============================================================================
# ENUMS
# ============================================================================

class BlockType(str, Enum):
    """Recovery block classification"""
    BLOCK_1 = "BLOCK_1"  # Gateway & Network Downtime
    BLOCK_2 = "BLOCK_2"  # Liquidity Lag & Salary Cycle
    BLOCK_3 = "BLOCK_3"  # Dead Mandates & Instruments
    BLOCK_4 = "BLOCK_4"  # Alternative Fallback Instrument
    BLOCK_5 = "BLOCK_5"  # Guardrails & Audit
    BLOCK_6 = "BLOCK_6"  # Benchmark & Evaluation


class RootCauseType(str, Enum):
    """Root cause classifications"""
    GATEWAY_TIMEOUT = "GATEWAY_TIMEOUT"
    GATEWAY_ERROR_5XX = "GATEWAY_ERROR_5XX"
    NETWORK_ERROR = "NETWORK_ERROR"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    LOW_BALANCE = "LOW_BALANCE"
    CARD_EXPIRED = "CARD_EXPIRED"
    MANDATE_REVOKED = "MANDATE_REVOKED"
    CVV_MISMATCH = "CVV_MISMATCH"
    INVALID_TOKEN = "INVALID_TOKEN"
    FRAUD_DECLINED = "FRAUD_DECLINED"
    ISSUER_DECLINED = "ISSUER_DECLINED"
    UNKNOWN = "UNKNOWN"


class SeverityLevel(str, Enum):
    """Failure severity"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecoveryState(str, Enum):
    """State machine states"""
    INITIAL = "INITIAL"
    GATEWAY_FAILURE = "GATEWAY_FAILURE"
    SCHEDULED_RETRY_1 = "SCHEDULED_RETRY_1"
    SCHEDULED_RETRY_2 = "SCHEDULED_RETRY_2"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    SALARY_WINDOW_SCHEDULED = "SALARY_WINDOW_SCHEDULED"
    SALARY_RETRY_ATTEMPTED = "SALARY_RETRY_ATTEMPTED"
    INSTRUMENT_INVALID = "INSTRUMENT_INVALID"
    BLOCK_4_ESCALATED = "BLOCK_4_ESCALATED"
    FALLBACK_LINK_SENT = "FALLBACK_LINK_SENT"
    IN_GRACE_PERIOD = "IN_GRACE_PERIOD"
    RECOVERED = "RECOVERED"
    RECOVERED_VIA_FALLBACK = "RECOVERED_VIA_FALLBACK"
    SUBSCRIPTION_PAUSED = "SUBSCRIPTION_PAUSED"
    DND_ABORTED = "DND_ABORTED"


class LTVTier(str, Enum):
    """Customer LTV tiers for grace period"""
    TIER_1 = "TIER_1"  # Standard B2C (72 hours)
    TIER_2 = "TIER_2"  # High-LTV / B2B (7 days)


class ActionType(str, Enum):
    """Audit log action types"""
    WEBHOOK_RECEIVED = "WEBHOOK_RECEIVED"
    DIAGNOSED = "DIAGNOSED"
    LIVE_REROUTE_TRIGGERED = "LIVE_REROUTE_TRIGGERED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    INSTRUMENT_VALIDATED = "INSTRUMENT_VALIDATED"
    FALLBACK_LINK_SENT = "FALLBACK_LINK_SENT"
    GRACE_PERIOD_STARTED = "GRACE_PERIOD_STARTED"
    GRACE_PERIOD_EXPIRED = "GRACE_PERIOD_EXPIRED"
    RECOVERED = "RECOVERED"
    PAUSED = "PAUSED"
    DND_ABORT = "DND_ABORT"
    AUDIT_LOG_WRITTEN = "AUDIT_LOG_WRITTEN"


# ============================================================================
# RAZORPAY WEBHOOK MODELS
# ============================================================================

class PaymentError(BaseModel):
    """Payment error details"""
    code: str
    message: str
    source: Optional[str] = None


class Card(BaseModel):
    """Card payment method"""
    id: str
    entity: str = "card"
    name: Optional[str] = None
    last4: Optional[str] = None
    network: Optional[str] = None
    type: Optional[str] = None
    issuer: Optional[str] = None
    international: Optional[bool] = None
    emi: Optional[bool] = None
    recurring: Optional[bool] = None


class PaymentMethod(BaseModel):
    """Payment method details"""
    type: str  # card, upi, nach, bnpl, wallet, etc.
    card: Optional[Card] = None


class ChargeData(BaseModel):
    """Charge/Transaction data"""
    entity: str = "charge"
    id: str
    invoice_id: Optional[str] = None
    payment_id: Optional[str] = None
    order_id: Optional[str] = None
    customer_id: Optional[str] = None
    amount: int  # Amount in paise
    currency: str = "INR"
    error: PaymentError
    payment_method: PaymentMethod
    status: str = "failed"
    created_at: int  # Unix timestamp


class WebhookEvent(BaseModel):
    """Razorpay webhook event"""
    id: str
    entity: str = "event"
    event: str  # e.g., "charge.failed"
    created_at: int  # Unix timestamp
    data: ChargeData

    @validator('event')
    def validate_event(cls, v):
        allowed_events = ['charge.failed', 'payment.failed', 'mandate.failed']
        if v not in allowed_events:
            raise ValueError(f"Event must be one of {allowed_events}")
        return v


# ============================================================================
# DIAGNOSTIC / CLASSIFIER MODELS
# ============================================================================

class DiagnosticResult(BaseModel):
    """Output of diagnostic classifier"""
    invoice_id: str
    block: BlockType
    root_cause: RootCauseType
    severity: SeverityLevel
    recovery_score: float = Field(ge=0.0, le=1.0)  # 0.0 to 1.0
    retry_count: int = 0
    next_action: str
    details: Optional[Dict[str, Any]] = None
    classified_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# INVOICE MODELS
# ============================================================================

class Invoice(BaseModel):
    """Invoice entity"""
    id: str
    customer_id: str
    subscription_id: Optional[str] = None
    amount_in_paise: int
    currency: str = "INR"
    status: RecoveryState
    original_payment_method: Optional[str] = None
    failed_at: Optional[datetime] = None
    recovered_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceCreate(BaseModel):
    """Create invoice request"""
    customer_id: str
    subscription_id: Optional[str] = None
    amount_in_paise: int
    currency: str = "INR"
    original_payment_method: str


# ============================================================================
# RECOVERY FLOW MODELS
# ============================================================================

class RecoveryFlow(BaseModel):
    """Recovery flow state machine"""
    id: str
    invoice_id: str
    current_block: BlockType
    current_state: RecoveryState
    
    block_1_retries_done: int = 0
    block_2_retry_scheduled: bool = False
    block_3_instrument_dead: bool = False
    
    fallback_link_id: Optional[str] = None
    grace_period_tier: Optional[LTVTier] = None
    grace_period_start: Optional[datetime] = None
    grace_period_end: Optional[datetime] = None
    
    final_state: Optional[RecoveryState] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RecoveryFlowCreate(BaseModel):
    """Create recovery flow"""
    invoice_id: str
    current_block: BlockType
    current_state: RecoveryState


# ============================================================================
# AUDIT LOG MODELS
# ============================================================================

class AuditLogEvent(BaseModel):
    """Single audit log event"""
    event_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    invoice_id: str
    customer_id: str
    transaction_id: Optional[str] = None
    
    block: Optional[BlockType] = None
    action: ActionType
    root_cause: Optional[RootCauseType] = None
    error_code: Optional[str] = None
    
    state_before: Optional[RecoveryState] = None
    state_after: Optional[RecoveryState] = None
    
    details: Optional[Dict[str, Any]] = None
    audit_hash: Optional[str] = None
    prev_audit_hash: Optional[str] = None


# ============================================================================
# GATEWAY HEALTH MODELS
# ============================================================================

class GatewayHealthMetric(BaseModel):
    """Single gateway health metric"""
    uptime: float = Field(ge=0.0, le=1.0)
    success_rate: float = Field(ge=0.0, le=1.0)
    latency_p50: int  # milliseconds
    latency_p99: int  # milliseconds
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    status: str  # "healthy", "degraded", "down"


class GatewayHealth(BaseModel):
    """Overall gateway health index"""
    hdfc: Optional[GatewayHealthMetric] = None
    sbi: Optional[GatewayHealthMetric] = None
    icici: Optional[GatewayHealthMetric] = None
    upi: Optional[GatewayHealthMetric] = None
    card: Optional[GatewayHealthMetric] = None
    bnpl: Optional[GatewayHealthMetric] = None


# ============================================================================
# API RESPONSE MODELS
# ============================================================================

class WebhookAckResponse(BaseModel):
    """Acknowledgment for webhook receipt"""
    status: str = "accepted"
    event_id: str
    processing_timestamp: datetime


class LiveRerouteRequest(BaseModel):
    """Request for live reroute decision"""
    invoice_id: str
    payment_method: str
    amount: int
    customer_id: str


class LiveRerouteResponse(BaseModel):
    """Response with reroute recommendation"""
    status: str  # "reroute_available" or "no_healthy_channel"
    recommended_channel: Optional[str] = None
    action: str  # "redirect_to_upi_intent" or "escalate_to_async"
    url: Optional[str] = None
    ttl_seconds: Optional[int] = None
    recovery_attempt_id: str
    escalation_block: Optional[str] = None
    message: Optional[str] = None


class GracePeriodStatusResponse(BaseModel):
    """Grace period status query response"""
    invoice_id: str
    status: str  # "in_grace_period", "expired", "paid"
    fallback_link: Optional[Dict[str, Any]] = None
    grace_period: Optional[Dict[str, Any]] = None


class AuditTrailQueryResponse(BaseModel):
    """Audit trail query response"""
    invoice_id: str
    total_events: int
    events: List[AuditLogEvent]
    chain_valid: bool


# ============================================================================
# CUSTOMER LTV MODELS
# ============================================================================

class CustomerLTV(BaseModel):
    """Customer lifetime value segment"""
    customer_id: str
    lifetime_value_in_paise: int
    subscription_count: int
    avg_transaction_value: int
    tier: LTVTier
    grace_period_hours: int
    last_calculated: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# BENCHMARK TEST MODELS
# ============================================================================

class BenchmarkTestPayload(BaseModel):
    """Single test payload for benchmark"""
    test_id: str
    invoice_id: str
    customer_id: str
    amount: int
    failure_scenario: str  # e.g., "NETWORK_TIMEOUT", "LOW_BALANCE", "EXPIRED_CARD"
    error_code: str
    webhook_event: WebhookEvent


class BenchmarkResult(BaseModel):
    """Result of single benchmark test"""
    test_id: str
    invoice_id: str
    status: RecoveryState
    amount_recovered: int
    audit_complete: bool
    recovery_success: bool


class BenchmarkScorecard(BaseModel):
    """Overall benchmark evaluation scorecard"""
    gross_revenue_at_risk: int
    net_revenue_recovered: int
    recovery_conversion_rate: float = Field(ge=0.0, le=1.0)
    target_met: bool  # True if >= 70%
    audit_log_coverage: float = Field(ge=0.0, le=1.0)
    benchmark_passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
