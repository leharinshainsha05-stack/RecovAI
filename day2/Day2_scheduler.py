"""
RecovAI: Retry Scheduler & Grace Period Manager
Day 2: APScheduler background jobs for Block 2 salary window and Block 4 grace periods
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Day2_database import (
    RecoveryFlow, ScheduledRetry, RecoveryStateEnum,
    BlockTypeEnum, Base
)
from Day2_statemachine import RecoveryStateMachine, RecoveryFlowManager
from Day2_audit import AuditLedger


logger = logging.getLogger(__name__)


# ============================================================================
# SCHEDULER CONFIGURATION
# ============================================================================

class RecoveryScheduler:
    """
    Background job scheduler for RecovAI.
    
    Jobs:
    1. Salary Window Retry (10 AM on 1st/2nd of month) - BLOCK_2
    2. Grace Period Expiry Check (every 15 minutes) - BLOCK_4
    3. Retry Backoff Execution (scheduled retries) - BLOCK_1
    """
    
    def __init__(self, database_url: str):
        """
        Initialize scheduler.
        
        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        self.scheduler = BackgroundScheduler()
        self.state_machine = RecoveryStateMachine()
        self.flow_manager = RecoveryFlowManager(self.state_machine)
        self.audit_ledger = AuditLedger()
        
        logger.info("✓ RecoveryScheduler initialized")
    
    def start(self):
        """Start the scheduler"""
        if self.scheduler.running:
            logger.warning("⚠️  Scheduler already running")
            return
        
        # Register jobs
        self._register_salary_window_job()
        self._register_grace_period_job()
        self._register_retry_backoff_job()
        
        # Start scheduler
        self.scheduler.start()
        logger.info("✓ Scheduler started with 3 background jobs")
    
    def stop(self):
        """Stop the scheduler"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("✓ Scheduler stopped")
    
    # ========================================================================
    # JOB 1: SALARY WINDOW RETRY (Block 2)
    # ========================================================================
    
    def _register_salary_window_job(self):
        """
        Register job to execute Block 2 retries at 10 AM on 1st/2nd of month.
        
        Trigger: 10:00 AM IST every day
        Action: Execute pending salary window retries
        """
        self.scheduler.add_job(
            func=self._execute_salary_window_retries,
            trigger=CronTrigger(hour=10, minute=0, timezone='Asia/Kolkata'),
            id='salary_window_retry_daily',
            name='Salary Window Retry (Block 2)',
            misfire_grace_time=60,
            coalesce=True,
        )
        logger.info("✓ Salary window job registered (10 AM daily)")
    
    def _execute_salary_window_retries(self):
        """
        Execute pending salary window retries.
        
        Steps:
        1. Query flows in SALARY_WINDOW_SCHEDULED state
        2. For each invoice, attempt retry
        3. Update state based on result
        4. Log to audit trail
        """
        session = self.SessionLocal()
        
        try:
            # Find pending salary window retries
            pending = session.query(RecoveryFlow).filter(
                RecoveryFlow.current_state == RecoveryStateEnum.SALARY_WINDOW_SCHEDULED
            ).all()
            
            if not pending:
                logger.info("📅 No salary window retries pending")
                return
            
            logger.info(f"📅 Executing {len(pending)} salary window retries")
            
            for flow in pending:
                try:
                    # Simulate retry (in production, call Razorpay API)
                    logger.info(f"  Retrying invoice {flow.invoice_id}...")
                    
                    # For demo: randomly succeed/fail
                    import random
                    success = random.random() > 0.3  # 70% success rate
                    
                    if success:
                        # Mark as recovered
                        self.flow_manager.mark_recovered(flow)
                        
                        # Log success
                        self.audit_ledger.log_event(
                            session=session,
                            invoice_id=flow.invoice_id,
                            customer_id=flow.customer_id,
                            action="SALARY_RETRY_ATTEMPTED",
                            state_before=RecoveryStateEnum.SALARY_WINDOW_SCHEDULED,
                            state_after=RecoveryStateEnum.RECOVERED,
                            details={"result": "success"}
                        )
                        
                        logger.info(f"  ✓ Recovered: {flow.invoice_id}")
                    else:
                        # Escalate to Block 4
                        self.state_machine.transition(
                            flow,
                            RecoveryStateEnum.BLOCK_4_ESCALATED,
                            session
                        )
                        
                        # Log failure
                        self.audit_ledger.log_event(
                            session=session,
                            invoice_id=flow.invoice_id,
                            customer_id=flow.customer_id,
                            action="SALARY_RETRY_ATTEMPTED",
                            state_before=RecoveryStateEnum.SALARY_WINDOW_SCHEDULED,
                            state_after=RecoveryStateEnum.BLOCK_4_ESCALATED,
                            details={"result": "failed", "escalated": True}
                        )
                        
                        logger.info(f"  ✗ Escalated to Block 4: {flow.invoice_id}")
                
                except Exception as e:
                    logger.error(f"❌ Error retrying {flow.invoice_id}: {e}")
                    continue
            
            session.commit()
            
        except Exception as e:
            logger.error(f"❌ Salary window job failed: {e}")
            session.rollback()
        finally:
            session.close()
    
    # ========================================================================
    # JOB 2: GRACE PERIOD EXPIRY CHECK (Block 4)
    # ========================================================================
    
    def _register_grace_period_job(self):
        """
        Register job to check grace period expiry every 15 minutes.
        
        Trigger: Every 15 minutes
        Action: Check if grace periods have expired, handle accordingly
        """
        self.scheduler.add_job(
            func=self._check_grace_period_expiry,
            trigger=IntervalTrigger(minutes=15),
            id='grace_period_check',
            name='Grace Period Expiry Check (Block 4)',
            misfire_grace_time=60,
        )
        logger.info("✓ Grace period job registered (every 15 minutes)")
    
    def _check_grace_period_expiry(self):
        """
        Check for expired grace periods.
        
        Steps:
        1. Query flows in IN_GRACE_PERIOD state with grace_period_end <= NOW
        2. Check payment link status via Razorpay API
        3. If paid: Mark RECOVERED_VIA_FALLBACK
        4. If unpaid: Mark SUBSCRIPTION_PAUSED, suspend service
        5. Log to audit trail
        """
        session = self.SessionLocal()
        
        try:
            # Find expired grace periods
            now = datetime.utcnow()
            expired = session.query(RecoveryFlow).filter(
                RecoveryFlow.current_state == RecoveryStateEnum.IN_GRACE_PERIOD,
                RecoveryFlow.grace_period_end <= now
            ).all()
            
            if not expired:
                logger.debug("✓ No expired grace periods")
                return
            
            logger.info(f"⏰ Processing {len(expired)} expired grace periods")
            
            for flow in expired:
                try:
                    # Check payment link status (simulated)
                    logger.info(f"  Checking grace period for {flow.invoice_id}...")
                    
                    # In production: query Razorpay API
                    # link_status = razorpay_client.get_link_status(flow.fallback_link_id)
                    
                    # For demo: randomly paid/unpaid
                    import random
                    is_paid = random.random() > 0.4  # 60% paid
                    
                    if is_paid:
                        # Mark as recovered
                        self.flow_manager.mark_recovered(flow, via_fallback=True)
                        
                        # Log success
                        self.audit_ledger.log_event(
                            session=session,
                            invoice_id=flow.invoice_id,
                            customer_id=flow.customer_id,
                            action="GRACE_PERIOD_EXPIRED",
                            state_before=RecoveryStateEnum.IN_GRACE_PERIOD,
                            state_after=RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
                            details={"result": "paid_via_fallback"}
                        )
                        
                        logger.info(f"  ✓ Recovered via fallback: {flow.invoice_id}")
                    else:
                        # Mark as paused
                        self.flow_manager.mark_paused(flow)
                        
                        # Suspend service (would call subscription API in production)
                        # subscription_service.suspend(flow.invoice_id)
                        
                        # Log suspension
                        self.audit_ledger.log_event(
                            session=session,
                            invoice_id=flow.invoice_id,
                            customer_id=flow.customer_id,
                            action="GRACE_PERIOD_EXPIRED",
                            state_before=RecoveryStateEnum.IN_GRACE_PERIOD,
                            state_after=RecoveryStateEnum.SUBSCRIPTION_PAUSED,
                            details={"result": "not_paid", "service_suspended": True}
                        )
                        
                        logger.info(f"  ⏸ Service suspended: {flow.invoice_id}")
                
                except Exception as e:
                    logger.error(f"❌ Error processing grace period for {flow.invoice_id}: {e}")
                    continue
            
            session.commit()
            
        except Exception as e:
            logger.error(f"❌ Grace period job failed: {e}")
            session.rollback()
        finally:
            session.close()
    
    # ========================================================================
    # JOB 3: RETRY BACKOFF EXECUTION (Block 1)
    # ========================================================================
    
    def _register_retry_backoff_job(self):
        """
        Register job to execute scheduled retries every 5 minutes.
        
        Trigger: Every 5 minutes
        Action: Execute T+15m and T+2h retries for Block 1
        """
        self.scheduler.add_job(
            func=self._execute_scheduled_retries,
            trigger=IntervalTrigger(minutes=5),
            id='retry_backoff_execution',
            name='Retry Backoff Execution (Block 1)',
            misfire_grace_time=60,
        )
        logger.info("✓ Retry backoff job registered (every 5 minutes)")
    
    def _execute_scheduled_retries(self):
        """
        Execute scheduled retry jobs (T+15m and T+2h).
        
        Steps:
        1. Query ScheduledRetry records with scheduled_for <= NOW
        2. Execute each retry
        3. Update state based on result
        4. Log to audit trail
        """
        session = self.SessionLocal()
        
        try:
            now = datetime.utcnow()
            
            # Find pending scheduled retries
            pending = session.query(ScheduledRetry).filter(
                ScheduledRetry.is_executed == False,
                ScheduledRetry.is_cancelled == False,
                ScheduledRetry.scheduled_for <= now
            ).all()
            
            if not pending:
                logger.debug("✓ No scheduled retries pending")
                return
            
            logger.info(f"🔄 Executing {len(pending)} scheduled retries")
            
            for retry_job in pending:
                try:
                    flow = session.query(RecoveryFlow).filter(
                        RecoveryFlow.invoice_id == retry_job.invoice_id
                    ).first()
                    
                    if not flow:
                        logger.warning(f"⚠️  Flow not found for {retry_job.invoice_id}")
                        retry_job.is_cancelled = True
                        continue
                    
                    logger.info(f"  Retrying {retry_job.invoice_id} (type: {retry_job.retry_type})...")
                    
                    # Simulate retry (in production, call Razorpay API)
                    import random
                    success = random.random() > 0.4  # 60% success
                    
                    if success:
                        # Mark as recovered
                        self.flow_manager.mark_recovered(flow)
                        
                        # Log success
                        self.audit_ledger.log_event(
                            session=session,
                            invoice_id=flow.invoice_id,
                            customer_id=flow.customer_id,
                            action="RETRY_SCHEDULED",
                            state_before=flow.current_state,
                            state_after=RecoveryStateEnum.RECOVERED,
                            details={"retry_type": retry_job.retry_type, "result": "success"}
                        )
                        
                        logger.info(f"  ✓ Recovered: {retry_job.invoice_id}")
                    else:
                        logger.info(f"  ↻ Retry failed: {retry_job.invoice_id}")
                    
                    retry_job.is_executed = True
                    retry_job.executed_at = now
                
                except Exception as e:
                    logger.error(f"❌ Error executing retry for {retry_job.invoice_id}: {e}")
                    continue
            
            session.commit()
            
        except Exception as e:
            logger.error(f"❌ Retry backoff job failed: {e}")
            session.rollback()
        finally:
            session.close()
    
    def get_jobs_info(self) -> dict:
        """Get information about scheduled jobs"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        
        return {
            "running": self.scheduler.running,
            "jobs_count": len(jobs),
            "jobs": jobs
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Scheduler - Day 2 Test")
    print("="*80 + "\n")
    
    # Note: Requires PostgreSQL connection
    # Uncomment to test with real database
    
    # DATABASE_URL = "postgresql://user:password@localhost:5432/recovai"
    # 
    # scheduler = RecoveryScheduler(DATABASE_URL)
    # scheduler.start()
    # 
    # try:
    #     print("Scheduler running with these jobs:")
    #     for job in scheduler.scheduler.get_jobs():
    #         print(f"  • {job.name} (ID: {job.id})")
    #         print(f"    Next run: {job.next_run_time}")
    #     
    #     # Run for 60 seconds
    #     import time
    #     time.sleep(60)
    # 
    # finally:
    #     scheduler.stop()
    
    print("✓ Scheduler implementation complete")
    print("  Jobs: 3 (Salary Window, Grace Period, Retry Backoff)")
    print("  Requires PostgreSQL connection to run")
    print("="*80 + "\n")
