"""
RecovAI: SQLAlchemy Database Models
Day 2: PostgreSQL schema definition with ORM models
"""

from datetime import datetime, timedelta
import os;
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, 
    Enum, JSON, ForeignKey, Index, UniqueConstraint, Text, text
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import relationship

import enum

# Create base class for all models
Base = declarative_base()


# ============================================================================
# ENUM DEFINITIONS (Mirror Day1_models.py)
# ============================================================================

class BlockTypeEnum(str, enum.Enum):
    BLOCK_1 = "BLOCK_1"
    BLOCK_2 = "BLOCK_2"
    BLOCK_3 = "BLOCK_3"
    BLOCK_4 = "BLOCK_4"
    BLOCK_5 = "BLOCK_5"
    BLOCK_6 = "BLOCK_6"


class RootCauseEnum(str, enum.Enum):
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


class SeverityEnum(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RecoveryStateEnum(str, enum.Enum):
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


class LTVTierEnum(str, enum.Enum):
    TIER_1 = "TIER_1"  # 72 hours
    TIER_2 = "TIER_2"  # 7 days


class ActionTypeEnum(str, enum.Enum):
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
# CUSTOMER MODEL
# ============================================================================

class Customer(Base):
    """Customer entity with LTV tracking"""
    __tablename__ = "customers"
    
    id = Column(String(50), primary_key=True)
    email = Column(String(255), unique=True, index=True)
    phone = Column(String(20), index=True)
    
    # Lifetime value metrics
    lifetime_value_in_paise = Column(Integer, default=0)
    subscription_count = Column(Integer, default=0)
    avg_transaction_value = Column(Integer, default=0)
    
    # LTV tier
    ltv_tier = Column(Enum(LTVTierEnum), default=LTVTierEnum.TIER_1)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoices = relationship("Invoice", back_populates="customer")
    recovery_flows = relationship("RecoveryFlow", back_populates="customer")
    audit_logs = relationship("AuditLog", back_populates="customer")
    
    __table_args__ = (
        Index('idx_ltv_tier', 'ltv_tier'),
        Index('idx_lifetime_value', 'lifetime_value_in_paise'),
    )


# ============================================================================
# INVOICE MODEL
# ============================================================================

class Invoice(Base):
    """Payment invoice with status tracking"""
    __tablename__ = "invoices"
    
    id = Column(String(50), primary_key=True)
    customer_id = Column(String(50), ForeignKey('customers.id'), index=True)
    subscription_id = Column(String(50), index=True)
    
    # Payment details
    amount_in_paise = Column(Integer, nullable=False)
    currency = Column(String(3), default='INR')
    
    # Status tracking
    status = Column(Enum(RecoveryStateEnum), default=RecoveryStateEnum.INITIAL, index=True)
    original_payment_method = Column(String(50))
    
    # Timeline
    failed_at = Column(DateTime, index=True)
    recovered_at = Column(DateTime)
    paused_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    customer = relationship("Customer", back_populates="invoices")
    recovery_flow = relationship("RecoveryFlow", back_populates="invoice", uselist=False)
    audit_logs = relationship("AuditLog", back_populates="invoice")
    
    __table_args__ = (
        Index('idx_customer_status', 'customer_id', 'status'),
        Index('idx_failed_recovered', 'failed_at', 'recovered_at'),
    )


# ============================================================================
# RECOVERY FLOW MODEL (State Machine)
# ============================================================================

class RecoveryFlow(Base):
    """Recovery workflow state machine"""
    __tablename__ = "recovery_flows"
    
    id = Column(String(50), primary_key=True)
    invoice_id = Column(String(50), ForeignKey('invoices.id'), unique=True, index=True)
    customer_id = Column(String(50), ForeignKey('customers.id'), index=True)
    
    # State machine tracking
    current_block = Column(Enum(BlockTypeEnum), nullable=False)
    current_state = Column(Enum(RecoveryStateEnum), nullable=False, index=True)
    
    # Block-specific counters
    block_1_retries_done = Column(Integer, default=0)
    block_2_retry_scheduled = Column(Boolean, default=False)
    block_3_instrument_dead = Column(Boolean, default=False)
    
    # Last retry timestamps (for cooldown enforcement)
    last_retry_at = Column(DateTime)
    last_notification_at = Column(DateTime)
    
    # Fallback link management (Block 4)
    fallback_link_id = Column(String(255))
    fallback_link_url = Column(String(500))
    fallback_link_short_url = Column(String(50))
    
    # Grace period management (LTV-tiered)
    grace_period_tier = Column(Enum(LTVTierEnum))
    grace_period_hours = Column(Integer)
    grace_period_start = Column(DateTime)
    grace_period_end = Column(DateTime, index=True)
    
    # Final state
    final_state = Column(Enum(RecoveryStateEnum))
    final_state_reached_at = Column(DateTime)
    
    # Metadata
    root_cause = Column(Enum(RootCauseEnum))
    recovery_score = Column(Float, default=0.0)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    invoice = relationship("Invoice", back_populates="recovery_flow")
    customer = relationship("Customer", back_populates="recovery_flows")
    
    __table_args__ = (
        Index('idx_current_state', 'current_state'),
        Index('idx_grace_period_end', 'grace_period_end'),
        Index('idx_block_retry_status', 'current_block', 'block_1_retries_done'),
    )


# ============================================================================
# AUDIT LOG MODEL (Immutable)
# ============================================================================

class AuditLog(Base):
    """Immutable audit trail with cryptographic hash chain"""
    __tablename__ = "audit_log"
    
    # Auto-incrementing ID (for ordering)
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Event tracking
    event_id = Column(String(50), unique=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Foreign keys
    invoice_id = Column(String(50), ForeignKey('invoices.id'), index=True)
    customer_id = Column(String(50), ForeignKey('customers.id'), index=True)
    transaction_id = Column(String(50))
    
    # Event details
    block = Column(Enum(BlockTypeEnum))
    action = Column(Enum(ActionTypeEnum), nullable=False, index=True)
    root_cause = Column(Enum(RootCauseEnum))
    error_code = Column(String(100))
    
    # State transitions
    state_before = Column(Enum(RecoveryStateEnum))
    state_after = Column(Enum(RecoveryStateEnum))
    
    # Event metadata (JSON for extensibility)
    details = Column(JSON, default={})
    
    # Cryptographic hash chain (for immutability verification)
    audit_hash = Column(String(255), index=True)  # SHA256 of current event
    prev_audit_hash = Column(String(255), index=True)  # SHA256 of previous event
    
    # Relationships
    invoice = relationship("Invoice", back_populates="audit_logs")
    customer = relationship("Customer", back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_invoice_timestamp', 'invoice_id', 'timestamp'),
        Index('idx_customer_action', 'customer_id', 'action'),
        Index('idx_hash_chain', 'audit_hash', 'prev_audit_hash'),
    )


# ============================================================================
# SCHEDULED RETRY MODEL
# ============================================================================

class ScheduledRetry(Base):
    """Scheduled retry jobs (salary window, grace period expiry, etc.)"""
    __tablename__ = "scheduled_retries"
    
    id = Column(String(50), primary_key=True)
    invoice_id = Column(String(50), ForeignKey('invoices.id'), index=True)
    
    # Retry type
    retry_type = Column(String(50), nullable=False)  # salary_window, grace_period_check, etc.
    
    # Scheduling
    scheduled_for = Column(DateTime, nullable=False, index=True)
    executed_at = Column(DateTime)
    
    # Status
    is_executed = Column(Boolean, default=False, index=True)
    is_cancelled = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_scheduled_for', 'scheduled_for'),
        Index('idx_execution_status', 'is_executed', 'is_cancelled'),
    )


# ============================================================================
# GATEWAY HEALTH MODEL (Real-time monitoring)
# ============================================================================

class GatewayHealth(Base):
    """Real-time gateway health metrics (mirrors Redis cache)"""
    __tablename__ = "gateway_health"
    
    gateway_name = Column(String(50), primary_key=True)
    
    # Metrics
    uptime = Column(Float, default=1.0)  # 0.0 to 1.0
    success_rate = Column(Float, default=1.0)  # 0.0 to 1.0
    latency_p50 = Column(Integer)  # milliseconds
    latency_p99 = Column(Integer)  # milliseconds
    
    # Status
    status = Column(String(50))  # healthy, degraded, down
    
    # Timestamp
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_status', 'status'),
    )


# ============================================================================
# DATABASE INITIALIZATION & UTILITY FUNCTIONS
# ============================================================================

def create_all_tables(engine):
    """Create all tables in the database"""
    Base.metadata.create_all(engine)
    print("✓ All tables created successfully")


def drop_all_tables(engine):
    """Drop all tables (careful - for testing/reset only!)"""
    Base.metadata.drop_all(engine)
    print("✓ All tables dropped")


def get_session_maker(database_url):
    """Create a session maker for the given database"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_engine(database_url, echo=False)
    return sessionmaker(bind=engine), engine

# ============================================================================
# EXECUTION & VERIFICATION RUNNER
# ============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/recovai"
)

if __name__ == "__main__":
    SessionMaker, engine = get_session_maker(DATABASE_URL)

    print("🔨 Creating database tables...")
    Base.metadata.create_all(engine)
    print("✓ Database tables created successfully!")

    # 1. Test PostgreSQL Connection
    print("1️⃣  Testing PostgreSQL connection...")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        print("   ✓ Connected to recovai database\n")

    # 2. Creating tables confirmation
    print("2️⃣  Creating database tables...")
    print("   ✓ Tables created\n")

    # 3. Testing record creation
    print("3️⃣  Testing record creation...")
    session = SessionMaker()
    try:
        # Create Customer
        cust = session.get(Customer, "cust_test_001")
        if not cust:
            cust = Customer(
                id="cust_test_001",
                email="test_cust@example.com",
                phone="+919876543210",
                lifetime_value_in_paise=99900,
                subscription_count=1,
                avg_transaction_value=99900,
                ltv_tier=LTVTierEnum.TIER_1
            )
            session.add(cust)
            session.commit()

        # Create Invoice
        inv = session.get(Invoice, "inv_test_001")
        if not inv:
            inv = Invoice(
                id="inv_test_001",
                customer_id="cust_test_001",
                subscription_id="sub_test_001",
                amount_in_paise=99900,
                currency="INR",
                status=RecoveryStateEnum.INITIAL,
                original_payment_method="card"
            )
            session.add(inv)
            session.commit()
        print("   ✓ Created invoice: inv_test_001")

        # Create Recovery Flow
        rf = session.get(RecoveryFlow, "rf_test_001")
        if not rf:
            rf = RecoveryFlow(
                id="rf_test_001",
                invoice_id="inv_test_001",
                customer_id="cust_test_001",
                current_block=BlockTypeEnum.BLOCK_1,
                current_state=RecoveryStateEnum.INITIAL,
                root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
                recovery_score=0.88
            )
            session.add(rf)
            session.commit()
        print("   ✓ Created recovery flow: rf_test_001")

        # Create Audit Log
        audit = session.query(AuditLog).filter_by(event_id="evt_test_001").first()
        if not audit:
            audit = AuditLog(
                event_id="evt_test_001",
                invoice_id="inv_test_001",
                customer_id="cust_test_001",
                block=BlockTypeEnum.BLOCK_1,
                action=ActionTypeEnum.WEBHOOK_RECEIVED,
                root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
                error_code="GATEWAY_TIMEOUT",
                state_before=RecoveryStateEnum.INITIAL,
                state_after=RecoveryStateEnum.INITIAL,
                audit_hash="0" * 64,
                prev_audit_hash="0" * 64
            )
            session.add(audit)
            session.commit()
        print("   ✓ Created audit log entry\n")

    finally:
        session.close()

    print("=" * 80)
    print("✓ Day 2 Database Setup Complete!")
    print("=" * 80)