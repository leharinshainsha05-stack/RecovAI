"""
RecovAI: Day 1 & Day 2 Integration
Connects FastAPI endpoints with database persistence and state machine
"""
import sys
from pathlib import Path

# Add project root ('rax') and 'day1' to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))
sys.path.append(str(BASE_DIR / "day1"))

import logging
from typing import Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Day1_models import (
    DiagnosticResult, ActionType as Day1ActionTypeEnum,
    BlockType as Day1BlockType, RootCauseType as Day1RootCauseType,
)
from Day1_diagnostic import DiagnosticEngine

from Day2_database import (
    Base, Customer, Invoice, RecoveryFlow,
    RecoveryStateEnum, ActionTypeEnum, BlockTypeEnum, RootCauseEnum
)
from Day2_statemachine import RecoveryStateMachine, RecoveryFlowManager
from Day2_audit import AuditLedger
from Day2_scheduler import RecoveryScheduler


logger = logging.getLogger(__name__)


def _to_day2_block(day1_block: Day1BlockType) -> BlockTypeEnum:
    """
    Day 1 and Day 2 each define their own Block enum with matching member
    names (BLOCK_1, BLOCK_2, ...) but as different classes. SQLAlchemy's
    enum column checks the concrete class, not just the value, so passing
    a Day1_models.BlockType straight into a Day2 model crashes. Bridge by
    name instead.
    """
    return BlockTypeEnum[day1_block.name]


def _to_day2_root_cause(day1_root_cause: Day1RootCauseType) -> RootCauseEnum:
    """Same class-mismatch bridge as _to_day2_block, for root causes."""
    return RootCauseEnum[day1_root_cause.name]


# ============================================================================
# INTEGRATED RECOVERY ENGINE
# ============================================================================

class IntegratedRecoveryEngine:
    """
    Unified recovery engine combining Day 1 (diagnosis) and Day 2 (execution).
    
    Flow:
    1. Webhook received (Day 1)
    2. Diagnostic classification (Day 1)
    3. Database persistence (Day 2)
    4. State machine transition (Day 2)
    5. Audit trail logging (Day 2)
    6. Background scheduler (Day 2)
    """
    
    def __init__(self, database_url: str):
        """
        Initialize integrated engine.
        
        Args:
            database_url: PostgreSQL connection URL
        """
        # Database
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)
        
        # Day 1 components
        self.diagnostic_engine = DiagnosticEngine()
        
        # Day 2 components
        self.state_machine = RecoveryStateMachine()
        self.flow_manager = RecoveryFlowManager(self.state_machine)
        self.audit_ledger = AuditLedger()
        self.scheduler = RecoveryScheduler(database_url)
        
        logger.info("✓ IntegratedRecoveryEngine initialized")
    
    def start(self):
        """Start background scheduler"""
        self.scheduler.start()
        logger.info("✓ Background scheduler started")
    
    def stop(self):
        """Stop background scheduler"""
        self.scheduler.stop()
        logger.info("✓ Background scheduler stopped")
    
    def process_webhook(self, webhook_event) -> dict:
        """
        End-to-end webhook processing.
        
        Steps:
        1. Classify error (Day 1)
        2. Get or create customer
        3. Create invoice record
        4. Create recovery flow
        5. Log initial audit event
        6. Return result
        
        Args:
            webhook_event: Razorpay webhook event
            
        Returns:
            Processing result dict
        """
        session = self.SessionLocal()
        
        try:
            # Step 1: Classify error (Day 1 diagnostic)
            logger.info(f"🔍 Classifying webhook: {webhook_event.data.invoice_id}")
            diagnostic_result = self.diagnostic_engine.classify(webhook_event)
            
            # Step 2: Get or create customer
            customer_id = webhook_event.data.customer_id
            customer = session.query(Customer).filter(
                Customer.id == customer_id
            ).first()
            
            if not customer:
                logger.info(f"👤 Creating customer: {customer_id}")
                customer = Customer(
                    id=customer_id,
                    email=None,  # Would come from Razorpay API call
                    phone=None,
                    lifetime_value_in_paise=0,
                    subscription_count=0,
                )
                session.add(customer)
                session.flush()
            
            # Step 3: Create or update invoice
            invoice_id = webhook_event.data.invoice_id
            invoice = session.query(Invoice).filter(
                Invoice.id == invoice_id
            ).first()
            
            if not invoice:
                logger.info(f"📋 Creating invoice: {invoice_id}")
                invoice = Invoice(
                    id=invoice_id,
                    customer_id=customer_id,
                    subscription_id=None,
                    amount_in_paise=webhook_event.data.amount,
                    currency=webhook_event.data.currency,
                    status=RecoveryStateEnum.INITIAL,
                    original_payment_method=webhook_event.data.payment_method.type,
                    failed_at=datetime.utcnow(),
                )
                session.add(invoice)
                session.flush()
            
            # Step 4: Create recovery flow
            logger.info(f"🔄 Creating recovery flow for {invoice_id}")
            day2_block = _to_day2_block(diagnostic_result.block)
            day2_root_cause = _to_day2_root_cause(diagnostic_result.root_cause)
            recovery_flow = self.flow_manager.create_flow(
                invoice_id=invoice_id,
                customer_id=customer_id,
                block=day2_block,
                root_cause=day2_root_cause,
                recovery_score=diagnostic_result.recovery_score,
                session=session,
            )
            
            # Step 5: Log initial audit event
            logger.info(f"📝 Logging initial audit event")
            self.audit_ledger.log_event(
                session=session,
                invoice_id=invoice_id,
                customer_id=customer_id,
                action=ActionTypeEnum.WEBHOOK_RECEIVED,
                error_code=webhook_event.data.error.code,
                state_after=recovery_flow.current_state,
                details={
                    "error_message": webhook_event.data.error.message,
                    "payment_method": webhook_event.data.payment_method.type,
                },
            )
            
            # Log diagnostic result
            self.audit_ledger.log_event(
                session=session,
                invoice_id=invoice_id,
                customer_id=customer_id,
                action=ActionTypeEnum.DIAGNOSED,
                block=day2_block,
                root_cause=day2_root_cause,
                state_after=recovery_flow.current_state,
                details={
                    "recovery_score": diagnostic_result.recovery_score,
                    "severity": diagnostic_result.severity.value,
                    "next_action": diagnostic_result.next_action,
                },
            )
            
            # Commit all changes
            session.commit()
            
            logger.info(f"✓ Webhook processed: {invoice_id} → {recovery_flow.current_state}")
            
            return {
                "status": "processed",
                "invoice_id": invoice_id,
                "flow_id": recovery_flow.id,
                "block": diagnostic_result.block.value,
                "recovery_score": diagnostic_result.recovery_score,
                "next_action": diagnostic_result.next_action,
            }
        
        except Exception as e:
            logger.error(f"❌ Error processing webhook: {e}", exc_info=True)
            session.rollback()
            raise
        
        finally:
            session.close()
    
    def execute_recovery_action(
        self,
        invoice_id: str,
        action: str
    ) -> dict:
        """
        Execute recovery action based on current state.
        
        Actions:
        - retry_1: Execute first retry (BLOCK_1)
        - retry_2: Execute second retry (BLOCK_1)
        - salary_window: Execute salary window retry (BLOCK_2)
        - fallback_link: Generate & send UPI link (BLOCK_4)
        
        Args:
            invoice_id: Invoice ID
            action: Action to execute
            
        Returns:
            Result dict
        """
        session = self.SessionLocal()
        
        try:
            # Get recovery flow
            flow = session.query(RecoveryFlow).filter(
                RecoveryFlow.invoice_id == invoice_id
            ).first()
            
            if not flow:
                return {"status": "error", "message": f"Flow not found for {invoice_id}"}
            
            logger.info(f"⚡ Executing action: {action} for {invoice_id}")
            
            # Execute action
            if action == "retry_1":
                success = self.flow_manager.schedule_retry_1(flow, session)
                next_state = RecoveryStateEnum.SCHEDULED_RETRY_1
            
            elif action == "retry_2":
                success = self.flow_manager.schedule_retry_2(flow, session)
                next_state = RecoveryStateEnum.SCHEDULED_RETRY_2
            
            elif action == "salary_window":
                success = self.flow_manager.schedule_salary_window_retry(flow, session)
                next_state = RecoveryStateEnum.SALARY_WINDOW_SCHEDULED
            
            elif action == "fallback_link":
                customer = session.query(Customer).filter(
                    Customer.id == flow.customer_id
                ).first()
                success = self.flow_manager.setup_grace_period(flow, customer, session)
                next_state = RecoveryStateEnum.IN_GRACE_PERIOD
            
            else:
                return {"status": "error", "message": f"Unknown action: {action}"}
            
            if success:
                # Log action
                self.audit_ledger.log_event(
                    session=session,
                    invoice_id=invoice_id,
                    customer_id=flow.customer_id,
                    action=ActionTypeEnum.RETRY_SCHEDULED,
                    block=flow.current_block,
                    state_before=flow.current_state,
                    state_after=next_state,
                    details={"action": action},
                )
                
                session.commit()
                
                logger.info(f"✓ Action executed: {action} → {next_state}")
                
                return {
                    "status": "success",
                    "invoice_id": invoice_id,
                    "action": action,
                    "new_state": next_state.value,
                }
            else:
                return {"status": "failed", "message": "Action execution failed"}
        
        except Exception as e:
            logger.error(f"❌ Error executing action: {e}", exc_info=True)
            session.rollback()
            return {"status": "error", "message": str(e)}
        
        finally:
            session.close()
    
    def get_recovery_status(self, invoice_id: str) -> dict:
        """
        Get current recovery status for an invoice.
        
        Args:
            invoice_id: Invoice ID
            
        Returns:
            Status dict with flow and audit trail
        """
        session = self.SessionLocal()
        
        try:
            flow = session.query(RecoveryFlow).filter(
                RecoveryFlow.invoice_id == invoice_id
            ).first()
            
            if not flow:
                return {"status": "not_found"}
            
            # Get audit trail
            audit_trail = self.audit_ledger.get_audit_trail(session, invoice_id)
            
            # Verify audit chain
            is_valid, message = self.audit_ledger.verify_chain_integrity(session, invoice_id)
            
            return {
                "invoice_id": invoice_id,
                "current_block": flow.current_block.value,
                "current_state": flow.current_state.value,
                "recovery_score": flow.recovery_score,
                "grace_period_end": flow.grace_period_end.isoformat() if flow.grace_period_end else None,
                "audit_events": len(audit_trail),
                "audit_valid": is_valid,
                "audit_trail": audit_trail[-10:],  # Last 10 events
            }
        
        except Exception as e:
            logger.error(f"❌ Error getting status: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            session.close()


# ============================================================================
# FASTAPI INTEGRATION (Example)
# ============================================================================

# This shows how to integrate with Day1_main.py

def integrate_with_fastapi():
    """
    Example of how to integrate Day 2 with Day 1 FastAPI app.
    
    Add this to Day1_main.py after FastAPI initialization:
    """
    
    code = """
from Day2_integration import IntegratedRecoveryEngine

# Initialize integrated engine
DATABASE_URL = "postgresql://user:pass@localhost/recovai"
recovery_engine = IntegratedRecoveryEngine(DATABASE_URL)
recovery_engine.start()

@app.on_event("startup")
async def startup():
    recovery_engine.start()

@app.on_event("shutdown")
async def shutdown():
    recovery_engine.stop()

@app.post("/webhooks/payment-failure")
async def receive_payment_failure_webhook(request: Request):
    body = await request.body()
    body_str = body.decode('utf-8')
    
    # Verify signature...
    
    payload = json.loads(body_str)
    webhook_event = WebhookEvent(**payload)
    
    # Process webhook with integrated engine
    result = recovery_engine.process_webhook(webhook_event)
    
    return WebhookAckResponse(
        status="accepted",
        event_id=webhook_event.id,
        processing_timestamp=datetime.utcnow()
    )

@app.get("/api/v1/recovery/status/{invoice_id}")
async def get_recovery_status(invoice_id: str):
    return recovery_engine.get_recovery_status(invoice_id)
    """
    
    print(code)


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Day 1 + Day 2 Integration - Test")
    print("="*80 + "\n")
    
    print("Integration Pattern:")
    print("-" * 60)
    print("""
1. FastAPI receives webhook (Day 1)
2. Diagnostic classifier runs (Day 1)
3. RecoveryFlowManager creates flow (Day 2)
4. State machine transitions state (Day 2)
5. AuditLedger logs event (Day 2)
6. RecoveryScheduler executes jobs (Day 2)
7. Database persists everything (Day 2)
    """)
    
    print("\nFastAPI Integration Example:")
    print("-" * 60)
    integrate_with_fastapi()
    
    print("\n" + "="*80)
    print("✓ Integration layer ready")
    print("="*80 + "\n")
