"""
RecovAI: State Machine Engine
Day 2: 15-state recovery workflow management
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
from enum import Enum
import uuid

from sqlalchemy.orm import Session

from Day2_database import (
    RecoveryFlow, RecoveryStateEnum, BlockTypeEnum, 
    RootCauseEnum, LTVTierEnum, Customer
)


logger = logging.getLogger(__name__)


# ============================================================================
# STATE MACHINE TRANSITIONS
# ============================================================================

class RecoveryStateMachine:
    """
    15-state machine for payment recovery workflows.
    
    States:
    1. INITIAL - New invoice, no failure yet
    2. GATEWAY_FAILURE - Network/gateway error (BLOCK_1)
    3. SCHEDULED_RETRY_1 - First retry scheduled
    4. SCHEDULED_RETRY_2 - Second retry scheduled
    5. INSUFFICIENT_FUNDS - Low balance detected (BLOCK_2)
    6. SALARY_WINDOW_SCHEDULED - Waiting for salary window
    7. SALARY_RETRY_ATTEMPTED - Salary window retry executed
    8. INSTRUMENT_INVALID - Dead card/mandate (BLOCK_3)
    9. BLOCK_4_ESCALATED - Escalated to fallback
    10. FALLBACK_LINK_SENT - 1-click UPI link sent
    11. IN_GRACE_PERIOD - Waiting for link payment (BLOCK_4)
    12. RECOVERED - Payment successful ✅
    13. RECOVERED_VIA_FALLBACK - Fallback link paid ✅
    14. SUBSCRIPTION_PAUSED - Service suspended ❌
    15. DND_ABORTED - User opted out ❌
    """
    
   # Valid state transitions
    TRANSITIONS = {
        RecoveryStateEnum.INITIAL: [
            RecoveryStateEnum.GATEWAY_FAILURE,
            RecoveryStateEnum.INSUFFICIENT_FUNDS,
            RecoveryStateEnum.INSTRUMENT_INVALID,
        ],
        RecoveryStateEnum.GATEWAY_FAILURE: [
            RecoveryStateEnum.SCHEDULED_RETRY_1,
            RecoveryStateEnum.BLOCK_4_ESCALATED,
            RecoveryStateEnum.DND_ABORTED,
            RecoveryStateEnum.RECOVERED,
        ],
        RecoveryStateEnum.SCHEDULED_RETRY_1: [
            RecoveryStateEnum.SCHEDULED_RETRY_2,
            RecoveryStateEnum.BLOCK_4_ESCALATED,
            RecoveryStateEnum.RECOVERED,
        ],
        RecoveryStateEnum.SCHEDULED_RETRY_2: [
            RecoveryStateEnum.BLOCK_4_ESCALATED,
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.DND_ABORTED,
        ],
        RecoveryStateEnum.INSUFFICIENT_FUNDS: [
            RecoveryStateEnum.SALARY_WINDOW_SCHEDULED,
            RecoveryStateEnum.BLOCK_4_ESCALATED,
            RecoveryStateEnum.DND_ABORTED,
        ],
        RecoveryStateEnum.SALARY_WINDOW_SCHEDULED: [
            RecoveryStateEnum.SALARY_RETRY_ATTEMPTED,
            RecoveryStateEnum.DND_ABORTED,
        ],
        RecoveryStateEnum.SALARY_RETRY_ATTEMPTED: [
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.BLOCK_4_ESCALATED,
        ],
        RecoveryStateEnum.INSTRUMENT_INVALID: [
            RecoveryStateEnum.BLOCK_4_ESCALATED,
            RecoveryStateEnum.FALLBACK_LINK_SENT,
            RecoveryStateEnum.IN_GRACE_PERIOD,
        ],
        RecoveryStateEnum.BLOCK_4_ESCALATED: [
            RecoveryStateEnum.FALLBACK_LINK_SENT,
            RecoveryStateEnum.IN_GRACE_PERIOD,
            RecoveryStateEnum.DND_ABORTED,
        ],
        RecoveryStateEnum.FALLBACK_LINK_SENT: [
            RecoveryStateEnum.IN_GRACE_PERIOD,
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
            RecoveryStateEnum.SUBSCRIPTION_PAUSED,
            RecoveryStateEnum.DND_ABORTED,
        ],
        RecoveryStateEnum.IN_GRACE_PERIOD: [
            RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
            RecoveryStateEnum.SUBSCRIPTION_PAUSED,
            RecoveryStateEnum.DND_ABORTED,
        ],
        # Terminal states (no transitions)
        RecoveryStateEnum.RECOVERED: [],
        RecoveryStateEnum.RECOVERED_VIA_FALLBACK: [],
        RecoveryStateEnum.SUBSCRIPTION_PAUSED: [],
        RecoveryStateEnum.DND_ABORTED: [],
    }
    
    def __init__(self):
        """Initialize state machine"""
        logger.info("✓ RecoveryStateMachine initialized")
    
    def can_transition(
        self,
        from_state: RecoveryStateEnum,
        to_state: RecoveryStateEnum
    ) -> bool:
        """
        Check if transition is valid.
        
        Args:
            from_state: Current state
            to_state: Desired next state
            
        Returns:
            True if transition is allowed, False otherwise
        """
        allowed_states = self.TRANSITIONS.get(from_state, [])
        return to_state in allowed_states
    
    def transition(
        self,
        flow: RecoveryFlow,
        new_state: RecoveryStateEnum,
        session: Session
    ) -> bool:
        """
        Execute state transition.
        
        Args:
            flow: RecoveryFlow entity
            new_state: Desired state
            session: SQLAlchemy session
            
        Returns:
            True if successful, False if invalid
        """
        current = flow.current_state
        
        # Validate transition
        if not self.can_transition(current, new_state):
            logger.warning(
                f"❌ Invalid transition: {current} → {new_state}"
            )
            return False
        
        # Check guardrails before transition
        if not self._check_guardrails(flow, new_state):
            logger.warning(f"❌ Guardrails check failed for {new_state}")
            return False
        
        # Execute transition
        old_state = flow.current_state
        flow.current_state = new_state
        flow.updated_at = datetime.utcnow()
        
        # Mark as terminal state if applicable
        if new_state in [
            RecoveryStateEnum.RECOVERED,
            RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
            RecoveryStateEnum.SUBSCRIPTION_PAUSED,
            RecoveryStateEnum.DND_ABORTED,
        ]:
            flow.final_state = new_state
            flow.final_state_reached_at = datetime.utcnow()
        
        session.add(flow)
        
        logger.info(f"✓ State transition: {old_state} → {new_state}")
        return True
    
    def _check_guardrails(
        self,
        flow: RecoveryFlow,
        new_state: RecoveryStateEnum
    ) -> bool:
        """
        Apply Block 5 guardrails before state transition.
        
        Checks:
        - Max retry attempts
        - Cooldown between retries
        - DND status
        - Subscription status
        
        Args:
            flow: RecoveryFlow entity
            new_state: Desired state
            
        Returns:
            True if guardrails pass, False otherwise
        """
        # Rule 1: Max 2 retries
        if new_state == RecoveryStateEnum.SCHEDULED_RETRY_1:
            if (flow.block_1_retries_done or 0) >= 2:
                logger.warning("❌ Max retries (2) reached")
                return False
        
        # Rule 2: Min 6-hour cooldown between notifications
        if flow.last_notification_at:
            time_since_last = datetime.utcnow() - flow.last_notification_at
            if time_since_last < timedelta(hours=6):
                logger.warning(
                    f"❌ Cooldown period not elapsed: {time_since_last.total_seconds()/3600:.1f}h"
                )
                return False
        
        # Rule 3: DND check (would be checked before calling this)
        # Implemented in main.py webhook handler
        
        return True


# ============================================================================
# RECOVERY FLOW MANAGER
# ============================================================================

class RecoveryFlowManager:
    """
    Manages recovery flows from creation to completion.
    
    Responsibilities:
    - Create recovery flows
    - Execute state transitions
    - Manage retry schedules
    - Track grace periods
    - Enforce guardrails
    """
    
    def __init__(self, state_machine: RecoveryStateMachine):
        """Initialize with state machine"""
        self.state_machine = state_machine
        logger.info("✓ RecoveryFlowManager initialized")
    
    def create_flow(
        self,
        invoice_id: str,
        customer_id: str,
        block: BlockTypeEnum,
        root_cause: RootCauseEnum,
        recovery_score: float,
        session: Session
    ) -> RecoveryFlow:
        """
        Create new recovery flow from diagnostic result.
        
        Args:
            invoice_id: Invoice ID
            customer_id: Customer ID
            block: Assigned recovery block
            root_cause: Root cause classification
            recovery_score: Recovery probability
            session: SQLAlchemy session
            
        Returns:
            RecoveryFlow entity
        """
        flow_id = f"rflow_{uuid.uuid4().hex[:12]}"
        
        # Determine initial state based on block
        initial_state = self._get_initial_state(block)
        
        flow = RecoveryFlow(
            id=flow_id,
            invoice_id=invoice_id,
            customer_id=customer_id,
            current_block=block,
            current_state=initial_state,
            root_cause=root_cause,
            recovery_score=recovery_score,
        )
        
        session.add(flow)
        logger.info(f"✓ Created recovery flow {flow_id} → {initial_state}")
        
        return flow
    
    def _get_initial_state(self, block: BlockTypeEnum) -> RecoveryStateEnum:
        """Map block to initial state"""
        state_map = {
            BlockTypeEnum.BLOCK_1: RecoveryStateEnum.GATEWAY_FAILURE,
            BlockTypeEnum.BLOCK_2: RecoveryStateEnum.INSUFFICIENT_FUNDS,
            BlockTypeEnum.BLOCK_3: RecoveryStateEnum.INSTRUMENT_INVALID,
            BlockTypeEnum.BLOCK_4: RecoveryStateEnum.BLOCK_4_ESCALATED,
        }
        return state_map.get(block, RecoveryStateEnum.INITIAL)
    
    def schedule_retry_1(
        self,
        flow: RecoveryFlow,
        session: Session
    ) -> bool:
        """
        Schedule first retry (T+15 minutes for BLOCK_1).
        
        Args:
            flow: RecoveryFlow entity
            session: SQLAlchemy session
            
        Returns:
            True if scheduled successfully
        """
        if not self.state_machine.transition(
            flow,
            RecoveryStateEnum.SCHEDULED_RETRY_1,
            session
        ):
            return False
        
        flow.block_1_retries_done = 1
        flow.last_retry_at = datetime.utcnow() + timedelta(minutes=15)
        
        logger.info(f"✓ Retry 1 scheduled for {flow.last_retry_at}")
        return True
    
    def schedule_retry_2(
        self,
        flow: RecoveryFlow,
        session: Session
    ) -> bool:
        """
        Schedule second retry (T+2 hours for BLOCK_1).
        
        Args:
            flow: RecoveryFlow entity
            session: SQLAlchemy session
            
        Returns:
            True if scheduled successfully
        """
        if not self.state_machine.transition(
            flow,
            RecoveryStateEnum.SCHEDULED_RETRY_2,
            session
        ):
            return False
        
        flow.block_1_retries_done = 2
        flow.last_retry_at = datetime.utcnow() + timedelta(hours=2)
        
        logger.info(f"✓ Retry 2 scheduled for {flow.last_retry_at}")
        return True
    
    def schedule_salary_window_retry(
        self,
        flow: RecoveryFlow,
        session: Session
    ) -> bool:
        """
        Schedule retry at salary window (10 AM on 1st/2nd of month).
        
        Args:
            flow: RecoveryFlow entity
            session: SQLAlchemy session
            
        Returns:
            True if scheduled successfully
        """
        if not self.state_machine.transition(
            flow,
            RecoveryStateEnum.SALARY_WINDOW_SCHEDULED,
            session
        ):
            return False
        
        flow.block_2_retry_scheduled = True
        
        # Calculate next salary window (10 AM on 1st or 2nd)
        today = datetime.utcnow()
        if today.day <= 2:
            # This month's salary window
            salary_date = today.replace(day=1, hour=10, minute=0, second=0)
        else:
            # Next month's salary window
            if today.month == 12:
                salary_date = today.replace(year=today.year+1, month=1, day=1, hour=10, minute=0, second=0)
            else:
                salary_date = today.replace(month=today.month+1, day=1, hour=10, minute=0, second=0)
        
        flow.last_retry_at = salary_date
        logger.info(f"✓ Salary window retry scheduled for {salary_date}")
        return True
    
    def setup_grace_period(
        self,
        flow: RecoveryFlow,
        customer: Customer,
        session: Session
    ) -> bool:
        """
        Setup grace period for fallback link (Block 4).
        
        Args:
            flow: RecoveryFlow entity
            customer: Customer entity
            session: SQLAlchemy session
            
        Returns:
            True if grace period setup successfully
        """
        # Transition to fallback
        if not self.state_machine.transition(
            flow,
            RecoveryStateEnum.FALLBACK_LINK_SENT,
            session
        ):
            return False
        
        # Determine grace period based on LTV
        grace_hours = 72 if customer.ltv_tier == LTVTierEnum.TIER_1 else 168
        
        flow.grace_period_tier = customer.ltv_tier
        flow.grace_period_hours = grace_hours
        flow.grace_period_start = datetime.utcnow()
        flow.grace_period_end = datetime.utcnow() + timedelta(hours=grace_hours)
        
        # Transition to grace period
        if not self.state_machine.transition(
            flow,
            RecoveryStateEnum.IN_GRACE_PERIOD,
            session
        ):
            return False
        
        logger.info(
            f"✓ Grace period setup: {grace_hours}h "
            f"(ends: {flow.grace_period_end})"
        )
        return True
    
    def mark_recovered(
        self,
        flow: RecoveryFlow,
        via_fallback: bool = False,
        session: Optional[Session] = None
    ) -> bool:
        """
        Mark flow as recovered.
        
        Args:
            flow: RecoveryFlow entity
            via_fallback: True if recovered via fallback link
            session: SQLAlchemy session
            
        Returns:
            True if marked successfully
        """
        if via_fallback:
            target_state = RecoveryStateEnum.RECOVERED_VIA_FALLBACK
        else:
            target_state = RecoveryStateEnum.RECOVERED
        
        if session and not self.state_machine.transition(flow, target_state, session):
            return False
        else:
            flow.current_state = target_state
            flow.final_state = target_state
            flow.final_state_reached_at = datetime.utcnow()
        
        logger.info(f"✓ Marked as {target_state}")
        return True
    
    def mark_paused(
        self,
        flow: RecoveryFlow,
        session: Optional[Session] = None
    ) -> bool:
        """
        Mark flow as subscription paused (grace period expired).
        
        Args:
            flow: RecoveryFlow entity
            session: SQLAlchemy session
            
        Returns:
            True if marked successfully
        """
        if session and not self.state_machine.transition(
            flow,
            RecoveryStateEnum.SUBSCRIPTION_PAUSED,
            session
        ):
            return False
        else:
            flow.current_state = RecoveryStateEnum.SUBSCRIPTION_PAUSED
            flow.final_state = RecoveryStateEnum.SUBSCRIPTION_PAUSED
            flow.final_state_reached_at = datetime.utcnow()
        
        logger.info("✓ Marked as SUBSCRIPTION_PAUSED")
        return True
    
    def abort_dnd(
        self,
        flow: RecoveryFlow,
        session: Optional[Session] = None
    ) -> bool:
        """
        Abort recovery due to DND (Do Not Disturb).
        
        Args:
            flow: RecoveryFlow entity
            session: SQLAlchemy session
            
        Returns:
            True if aborted successfully
        """
        if session and not self.state_machine.transition(
            flow,
            RecoveryStateEnum.DND_ABORTED,
            session
        ):
            return False
        else:
            flow.current_state = RecoveryStateEnum.DND_ABORTED
            flow.final_state = RecoveryStateEnum.DND_ABORTED
            flow.final_state_reached_at = datetime.utcnow()
        
        logger.info("✓ Recovery aborted (DND)")
        return True


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI State Machine - Day 2 Test")
    print("="*80 + "\n")
    
    # Initialize state machine
    sm = RecoveryStateMachine()
    manager = RecoveryFlowManager(sm)
    
    # Test valid transitions
    print("Testing State Transitions:")
    print("-" * 60)
    
    transitions = [
        (RecoveryStateEnum.INITIAL, RecoveryStateEnum.GATEWAY_FAILURE, True),
        (RecoveryStateEnum.GATEWAY_FAILURE, RecoveryStateEnum.SCHEDULED_RETRY_1, True),
        (RecoveryStateEnum.SCHEDULED_RETRY_1, RecoveryStateEnum.SCHEDULED_RETRY_2, True),
        (RecoveryStateEnum.SCHEDULED_RETRY_2, RecoveryStateEnum.RECOVERED, True),
        (RecoveryStateEnum.RECOVERED, RecoveryStateEnum.GATEWAY_FAILURE, False),  # Invalid
        (RecoveryStateEnum.INSUFFICIENT_FUNDS, RecoveryStateEnum.SALARY_WINDOW_SCHEDULED, True),
        (RecoveryStateEnum.INSTRUMENT_INVALID, RecoveryStateEnum.BLOCK_4_ESCALATED, True),
        (RecoveryStateEnum.FALLBACK_LINK_SENT, RecoveryStateEnum.IN_GRACE_PERIOD, True),
        (RecoveryStateEnum.IN_GRACE_PERIOD, RecoveryStateEnum.RECOVERED_VIA_FALLBACK, True),
    ]
    
    for from_state, to_state, expected_valid in transitions:
        is_valid = sm.can_transition(from_state, to_state)
        status = "✓" if is_valid == expected_valid else "✗"
        print(f"{status} {from_state} → {to_state}: {is_valid}")
    
    print("\n" + "="*80)
    print("✓ State Machine tests completed!")
    print("="*80 + "\n")
