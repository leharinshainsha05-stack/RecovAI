"""
RecovAI: Day 2 Test Suite
Database, State Machine, Audit Ledger, and Scheduler tests
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Day2_database import (
    Base, Customer, Invoice, RecoveryFlow, AuditLog,
    ScheduledRetry, GatewayHealth,
    RecoveryStateEnum, BlockTypeEnum, RootCauseEnum,
    LTVTierEnum, ActionTypeEnum
)
from Day2_statemachine import RecoveryStateMachine, RecoveryFlowManager
from Day2_audit import AuditLedger
from Day2_scheduler import RecoveryScheduler


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Use in-memory SQLite for tests (no PostgreSQL needed)
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture
def db_session():
    """Create test database session"""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    yield session
    
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def state_machine():
    """Create state machine"""
    return RecoveryStateMachine()


@pytest.fixture
def flow_manager(state_machine):
    """Create recovery flow manager"""
    return RecoveryFlowManager(state_machine)


@pytest.fixture
def audit_ledger():
    """Create audit ledger"""
    return AuditLedger()


# ============================================================================
# DATABASE MODEL TESTS
# ============================================================================

class TestDatabaseModels:
    """Test SQLAlchemy ORM models"""
    
    def test_create_customer(self, db_session):
        """Test customer creation"""
        customer = Customer(
            id="cust_test_001",
            email="test@example.com",
            phone="9876543210",
            lifetime_value_in_paise=100000,
            ltv_tier=LTVTierEnum.TIER_1
        )
        
        db_session.add(customer)
        db_session.commit()
        
        result = db_session.query(Customer).filter_by(id="cust_test_001").first()
        assert result is not None
        assert result.email == "test@example.com"
        assert result.ltv_tier == LTVTierEnum.TIER_1
    
    def test_create_invoice(self, db_session):
        """Test invoice creation"""
        # Create customer first
        customer = Customer(id="cust_001")
        db_session.add(customer)
        db_session.flush()
        
        invoice = Invoice(
            id="inv_test_001",
            customer_id="cust_001",
            amount_in_paise=50000,
            status=RecoveryStateEnum.INITIAL,
            original_payment_method="card"
        )
        
        db_session.add(invoice)
        db_session.commit()
        
        result = db_session.query(Invoice).filter_by(id="inv_test_001").first()
        assert result is not None
        assert result.amount_in_paise == 50000
    
    def test_create_recovery_flow(self, db_session):
        """Test recovery flow creation"""
        # Create customer and invoice
        customer = Customer(id="cust_001")
        db_session.add(customer)
        db_session.flush()
        
        invoice = Invoice(
            id="inv_001",
            customer_id="cust_001",
            amount_in_paise=50000
        )
        db_session.add(invoice)
        db_session.flush()
        
        flow = RecoveryFlow(
            id="flow_001",
            invoice_id="inv_001",
            customer_id="cust_001",
            current_block=BlockTypeEnum.BLOCK_1,
            current_state=RecoveryStateEnum.GATEWAY_FAILURE,
            root_cause=RootCauseEnum.GATEWAY_TIMEOUT
        )
        
        db_session.add(flow)
        db_session.commit()
        
        result = db_session.query(RecoveryFlow).filter_by(id="flow_001").first()
        assert result is not None
        assert result.current_block == BlockTypeEnum.BLOCK_1
    
    def test_audit_log_creation(self, db_session):
        """Test audit log entry creation"""
        log = AuditLog(
            event_id="evt_001",
            timestamp=datetime.utcnow(),
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.WEBHOOK_RECEIVED,
            audit_hash="abc123",
            prev_audit_hash=None
        )
        
        db_session.add(log)
        db_session.commit()
        
        result = db_session.query(AuditLog).filter_by(event_id="evt_001").first()
        assert result is not None
        assert result.action == ActionTypeEnum.WEBHOOK_RECEIVED


# ============================================================================
# STATE MACHINE TESTS
# ============================================================================

class TestStateMachine:
    """Test state machine transitions"""
    
    def test_valid_transition(self, state_machine):
        """Test valid state transition"""
        is_valid = state_machine.can_transition(
            RecoveryStateEnum.INITIAL,
            RecoveryStateEnum.GATEWAY_FAILURE
        )
        assert is_valid is True
    
    def test_invalid_transition(self, state_machine):
        """Test invalid state transition"""
        is_valid = state_machine.can_transition(
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.GATEWAY_FAILURE
        )
        assert is_valid is False
    
    def test_all_valid_transitions(self, state_machine):
        """Test all valid transitions exist"""
        transitions = [
            (RecoveryStateEnum.INITIAL, RecoveryStateEnum.GATEWAY_FAILURE),
            (RecoveryStateEnum.GATEWAY_FAILURE, RecoveryStateEnum.SCHEDULED_RETRY_1),
            (RecoveryStateEnum.SCHEDULED_RETRY_1, RecoveryStateEnum.SCHEDULED_RETRY_2),
            (RecoveryStateEnum.INSUFFICIENT_FUNDS, RecoveryStateEnum.SALARY_WINDOW_SCHEDULED),
            (RecoveryStateEnum.INSTRUMENT_INVALID, RecoveryStateEnum.BLOCK_4_ESCALATED),
            (RecoveryStateEnum.FALLBACK_LINK_SENT, RecoveryStateEnum.IN_GRACE_PERIOD),
        ]
        
        for from_state, to_state in transitions:
            assert state_machine.can_transition(from_state, to_state) is True
    
    def test_terminal_states(self, state_machine):
        """Test terminal states have no transitions"""
        terminal_states = [
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
            RecoveryStateEnum.SUBSCRIPTION_PAUSED,
            RecoveryStateEnum.DND_ABORTED,
        ]
        
        for terminal_state in terminal_states:
            transitions = state_machine.TRANSITIONS.get(terminal_state, [])
            assert len(transitions) == 0


# ============================================================================
# RECOVERY FLOW MANAGER TESTS
# ============================================================================

class TestRecoveryFlowManager:
    """Test recovery flow management"""
    
    def test_create_flow_block_1(self, flow_manager, db_session):
        """Test flow creation for BLOCK_1"""
        flow = flow_manager.create_flow(
            invoice_id="inv_001",
            customer_id="cust_001",
            block=BlockTypeEnum.BLOCK_1,
            root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
            recovery_score=0.88,
            session=db_session
        )
        
        assert flow.current_state == RecoveryStateEnum.GATEWAY_FAILURE
        assert flow.current_block == BlockTypeEnum.BLOCK_1
    
    def test_create_flow_block_2(self, flow_manager, db_session):
        """Test flow creation for BLOCK_2"""
        flow = flow_manager.create_flow(
            invoice_id="inv_002",
            customer_id="cust_002",
            block=BlockTypeEnum.BLOCK_2,
            root_cause=RootCauseEnum.INSUFFICIENT_FUNDS,
            recovery_score=0.78,
            session=db_session
        )
        
        assert flow.current_state == RecoveryStateEnum.INSUFFICIENT_FUNDS
        assert flow.current_block == BlockTypeEnum.BLOCK_2
    
    def test_schedule_retry_1(self, flow_manager, db_session, state_machine):
        """Test scheduling first retry"""
        flow = flow_manager.create_flow(
            invoice_id="inv_001",
            customer_id="cust_001",
            block=BlockTypeEnum.BLOCK_1,
            root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
            recovery_score=0.88,
            session=db_session
        )
        
        success = flow_manager.schedule_retry_1(flow, db_session)
        
        assert success is True
        assert flow.current_state == RecoveryStateEnum.SCHEDULED_RETRY_1
        assert flow.block_1_retries_done == 1
    
    def test_schedule_salary_window_retry(self, flow_manager, db_session):
        """Test scheduling salary window retry"""
        flow = flow_manager.create_flow(
            invoice_id="inv_002",
            customer_id="cust_002",
            block=BlockTypeEnum.BLOCK_2,
            root_cause=RootCauseEnum.INSUFFICIENT_FUNDS,
            recovery_score=0.78,
            session=db_session
        )
        
        success = flow_manager.schedule_salary_window_retry(flow, db_session)
        
        assert success is True
        assert flow.current_state == RecoveryStateEnum.SALARY_WINDOW_SCHEDULED
        assert flow.block_2_retry_scheduled is True
    
    def test_mark_recovered(self, flow_manager, db_session):
        """Test marking flow as recovered"""
        flow = flow_manager.create_flow(
            invoice_id="inv_001",
            customer_id="cust_001",
            block=BlockTypeEnum.BLOCK_1,
            root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
            recovery_score=0.88,
            session=db_session
        )
        
        success = flow_manager.mark_recovered(flow)
        
        assert success is True
        assert flow.current_state == RecoveryStateEnum.RECOVERED
        assert flow.final_state == RecoveryStateEnum.RECOVERED


# ============================================================================
# AUDIT LEDGER TESTS
# ============================================================================

class TestAuditLedger:
    """Test audit ledger and hash chain"""
    
    def test_log_event(self, audit_ledger, db_session):
        """Test logging an event"""
        log = audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.WEBHOOK_RECEIVED,
            error_code="GATEWAY_TIMEOUT"
        )
        
        assert log.event_id is not None
        assert log.audit_hash is not None
        assert len(log.audit_hash) == 64  # SHA256 is 64 hex characters
    
    def test_hash_chain(self, audit_ledger, db_session):
        """Test hash chain linkage"""
        # Create two events
        log1 = audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.WEBHOOK_RECEIVED
        )
        
        log2 = audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.DIAGNOSED
        )
        
        # Verify chain linkage
        assert log1.audit_hash is not None
        assert log2.prev_audit_hash == log1.audit_hash
    
    def test_hash_consistency(self, audit_ledger):
        """Test hash calculation is deterministic"""
        event = {
            "event_id": "evt_001",
            "action": "TEST",
            "invoice_id": "inv_001"
        }
        
        event_json = audit_ledger._serialize_event(event)
        hash1 = audit_ledger._calculate_hash(event_json)
        hash2 = audit_ledger._calculate_hash(event_json)
        
        assert hash1 == hash2  # Same input = same hash
    
    def test_chain_integrity_verification(self, audit_ledger, db_session):
        """Test audit chain integrity verification"""
        # Create chain of events
        for i in range(3):
            audit_ledger.log_event(
                session=db_session,
                invoice_id="inv_001",
                customer_id="cust_001",
                action=ActionTypeEnum.WEBHOOK_RECEIVED if i == 0 else ActionTypeEnum.RETRY_SCHEDULED
            )
        
        db_session.commit()
        
        # Verify chain
        is_valid, message = audit_ledger.verify_chain_integrity(db_session, "inv_001")
        assert is_valid is True


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """End-to-end integration tests"""
    
    def test_block_1_workflow(self, db_session, flow_manager, audit_ledger, state_machine):
        """Test complete Block 1 (network) workflow"""
        # Create flow
        flow = flow_manager.create_flow(
            invoice_id="inv_001",
            customer_id="cust_001",
            block=BlockTypeEnum.BLOCK_1,
            root_cause=RootCauseEnum.GATEWAY_TIMEOUT,
            recovery_score=0.88,
            session=db_session
        )
        
        # Log initial event
        audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.WEBHOOK_RECEIVED,
            state_after=flow.current_state
        )
        
        # Schedule retry 1
        flow_manager.schedule_retry_1(flow, db_session)
        
        # Log retry event
        audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.RETRY_SCHEDULED,
            state_before=RecoveryStateEnum.GATEWAY_FAILURE,
            state_after=RecoveryStateEnum.SCHEDULED_RETRY_1
        )
        
        # Mark as recovered
        flow_manager.mark_recovered(flow)
        
        # Log recovery event
        audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_001",
            customer_id="cust_001",
            action=ActionTypeEnum.RECOVERED,
            state_before=RecoveryStateEnum.SCHEDULED_RETRY_1,
            state_after=RecoveryStateEnum.RECOVERED
        )
        
        db_session.commit()
        
        # Verify final state
        assert flow.current_state == RecoveryStateEnum.RECOVERED
        
        # Verify audit trail
        is_valid, _ = audit_ledger.verify_chain_integrity(db_session, "inv_001")
        assert is_valid is True
    
    def test_block_2_workflow(self, db_session, flow_manager, audit_ledger):
        """Test complete Block 2 (liquidity) workflow"""
        flow = flow_manager.create_flow(
            invoice_id="inv_002",
            customer_id="cust_002",
            block=BlockTypeEnum.BLOCK_2,
            root_cause=RootCauseEnum.INSUFFICIENT_FUNDS,
            recovery_score=0.78,
            session=db_session
        )
        
        flow_manager.schedule_salary_window_retry(flow, db_session)
        
        audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_002",
            customer_id="cust_002",
            action=ActionTypeEnum.RETRY_SCHEDULED,
            state_after=RecoveryStateEnum.SALARY_WINDOW_SCHEDULED
        )
        
        db_session.commit()
        
        assert flow.current_state == RecoveryStateEnum.SALARY_WINDOW_SCHEDULED
        assert flow.block_2_retry_scheduled is True
    
    def test_block_3_to_block_4_workflow(self, db_session, flow_manager, audit_ledger):
        """Test Block 3 escalation to Block 4"""
        # Create customer for grace period
        customer = Customer(
            id="cust_003",
            ltv_tier=LTVTierEnum.TIER_1
        )
        db_session.add(customer)
        db_session.flush()
        
        flow = flow_manager.create_flow(
            invoice_id="inv_003",
            customer_id="cust_003",
            block=BlockTypeEnum.BLOCK_3,
            root_cause=RootCauseEnum.CARD_EXPIRED,
            recovery_score=0.0,
            session=db_session
        )
        
        # Setup grace period (escalate to Block 4)
        flow_manager.setup_grace_period(flow, customer, db_session)
        
        db_session.commit()
        
        assert flow.current_state == RecoveryStateEnum.IN_GRACE_PERIOD
        assert flow.grace_period_tier == LTVTierEnum.TIER_1
        assert flow.grace_period_hours == 72


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestPerformance:
    """Performance and load tests"""
    
    def test_state_transition_speed(self, state_machine, db_session):
        """Test state transition is fast (<10ms)"""
        import time
        
        flow = RecoveryFlow(
            id="perf_flow_001",
            invoice_id="inv_perf_001",
            customer_id="cust_perf_001",
            current_block=BlockTypeEnum.BLOCK_1,
            current_state=RecoveryStateEnum.GATEWAY_FAILURE
        )
        
        db_session.add(flow)
        db_session.flush()
        
        start = time.time()
        state_machine.transition(
            flow,
            RecoveryStateEnum.SCHEDULED_RETRY_1,
            db_session
        )
        elapsed = (time.time() - start) * 1000
        
        assert elapsed < 10, f"Transition took {elapsed:.2f}ms"
    
    def test_audit_logging_speed(self, audit_ledger, db_session):
        """Test audit logging is fast (<50ms)"""
        import time
        
        start = time.time()
        for i in range(10):
            audit_ledger.log_event(
                session=db_session,
                invoice_id="inv_perf_001",
                customer_id="cust_perf_001",
                action=ActionTypeEnum.WEBHOOK_RECEIVED
            )
        elapsed = (time.time() - start) * 1000 / 10
        
        assert elapsed < 50, f"Logging took {elapsed:.2f}ms per event"
# ============================================================================
# ADDITIONAL DAY 2 COMPLIANCE & EDGE-CASE TESTS (25+ TARGET)
# ============================================================================

class TestAdditionalGuardrailsAndLedger:
    """Additional compliance, security, and edge-case verification tests"""

    def test_tamper_detection_breaks_hash_chain(self, audit_ledger, db_session):
        """Security: Modifying any historical record invalidates the audit chain"""
        # 1. Log 3 authentic events
        for i in range(3):
            audit_ledger.log_event(
                session=db_session,
                invoice_id="inv_tamper_001",
                customer_id="cust_tamper_001",
                action=ActionTypeEnum.WEBHOOK_RECEIVED if i == 0 else ActionTypeEnum.RETRY_SCHEDULED,
                details={"step": i}
            )
        db_session.commit()

        # 2. Tamper with the 2nd record directly in the database
        tampered_record = db_session.query(AuditLog).filter_by(invoice_id="inv_tamper_001").all()[1]
        tampered_record.details = {"step": 999, "hacked": True}
        db_session.commit()

        # 3. Chain verification must detect the modification and fail
        is_valid, _ = audit_ledger.verify_chain_integrity(db_session, "inv_tamper_001")
        assert is_valid is False

    def test_scheduled_retry_model_creation(self, db_session):
        """Database: Verify scheduled retry table storage and index logic"""
        retry_job = ScheduledRetry(
            id="retry_job_001",
            invoice_id="inv_test_001",
            retry_type="SALARY_WINDOW",
            scheduled_for=datetime.utcnow() + timedelta(days=3),
            is_executed=False
        )
        db_session.add(retry_job)
        db_session.commit()

        result = db_session.query(ScheduledRetry).filter_by(id="retry_job_001").first()
        assert result is not None
        assert result.retry_type == "SALARY_WINDOW"
        assert result.is_executed is False

    def test_gateway_health_model_creation(self, db_session):
        """Database: Verify telemetry storage for live gateway health"""
        gw = GatewayHealth(
            gateway_name="RAZORPAY_PRIMARY",
            uptime=0.9995,
            success_rate=0.985,
            latency_p50=120,
            latency_p99=450,
            status="healthy"
        )
        db_session.add(gw)
        db_session.commit()

        result = db_session.query(GatewayHealth).filter_by(gateway_name="RAZORPAY_PRIMARY").first()
        assert result is not None
        assert result.success_rate == 0.985
        assert result.status == "healthy"

    def test_tier_2_high_ltv_grace_period(self, flow_manager, db_session):
        """Block 4: Verify Tier 2 (High LTV) customers receive 7-day (168h) grace period"""
        vip_customer = Customer(
            id="cust_vip_001",
            ltv_tier=LTVTierEnum.TIER_2,
            lifetime_value_in_paise=5000000
        )
        db_session.add(vip_customer)
        db_session.flush()

        flow = flow_manager.create_flow(
            invoice_id="inv_vip_001",
            customer_id="cust_vip_001",
            block=BlockTypeEnum.BLOCK_3,
            root_cause=RootCauseEnum.CARD_EXPIRED,
            recovery_score=0.0,
            session=db_session
        )

        flow_manager.setup_grace_period(flow, vip_customer, db_session)
        db_session.commit()

        assert flow.current_state == RecoveryStateEnum.IN_GRACE_PERIOD
        assert flow.grace_period_tier == LTVTierEnum.TIER_2
        assert flow.grace_period_hours == 168

    def test_get_audit_trail_export(self, audit_ledger, db_session):
        """Audit API: Verify structured audit trail export formatting"""
        audit_ledger.log_event(
            session=db_session,
            invoice_id="inv_export_001",
            customer_id="cust_001",
            action=ActionTypeEnum.WEBHOOK_RECEIVED,
            error_code="GATEWAY_TIMEOUT"
        )
        db_session.commit()

        trail = audit_ledger.get_audit_trail(db_session, "inv_export_001")
        assert len(trail) == 1
        assert trail[0]["action"] == "WEBHOOK_RECEIVED"
        assert "hash" in trail[0]


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
