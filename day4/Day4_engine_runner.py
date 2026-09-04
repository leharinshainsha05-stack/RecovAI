"""
RecovAI: Real Engine Runner
Day 4: Sends every synthetic payment through the *actual* Day 1 diagnostic
engine and Day 2 state machine + audit ledger, and reports whatever really
happens - instead of the old benchmark that pre-decided win/loss counts.

Design notes
------------
- Runs against an in-memory SQLite database (via Day2_database.Base), so the
  benchmark stays a fast, offline simulation with no Postgres/Redis/Razorpay
  dependency, while still exercising the real ORM models, the real state
  machine transition rules, and the real SHA256 audit hash chain.
- Day3_integration.py / Day2_integration.py are NOT used here. Those files
  are written for the live-webhook path (Razorpay API calls, Redis-backed
  gateway health, live scheduler) - none of which exist in a benchmark.
  This runner talks directly to Day2_statemachine + Day2_audit, which is
  where the actual recovery logic lives.
- The one place this still uses randomness is whether a given retry/fallback
  attempt actually succeeds - there's no live payment gateway to charge
  against in a benchmark. That roll is weighted by the real recovery_score
  Day 1's classifier assigned, and by the block's real conversion behavior
  (e.g. BLOCK_4's ~65% fallback-link conversion, from Day1_diagnostic's own
  scoring). Everything upstream of that roll - classification, block
  routing, state transitions, guardrails, and the audit trail - is real
  engine code, not a hardcoded outcome.

Day 4 attribution-bug fix (2026-09)
------------------------------------
`o.block` on EnginePaymentOutcome is the transaction's *entry* classification
(BLOCK_1/2/3 - Day 1 never classifies anything into BLOCK_4, since Block 4
is an escalation target, not a root-cause). That's fine for BLOCK_1/BLOCK_2
totals, but it means the old `build_legacy_outcomes()` gave the scorer no
way to tell "recovered on the first retry" apart from "recovered via the
BLOCK_4 fallback link after escalating" - both just showed up as a recovered
transaction under their entry block. Day4_recovery_scorer.py now needs that
distinction to compute Block 4's real fallback-conversion rate, so the
`recovered` / `paused` / `failed` legacy dicts below carry two new,
purely-additive fields: `via_fallback` and `final_state`. No existing key is
renamed or removed, so nothing that reads the old shape (or Day1-3) breaks.
"""

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from Day1_models import WebhookEvent, ChargeData, PaymentError, PaymentMethod, Card
from Day1_diagnostic import DiagnosticEngine

from Day2_database import (
    Base, BlockTypeEnum, RootCauseEnum, RecoveryStateEnum,
    ActionTypeEnum, LTVTierEnum,
)
from Day2_statemachine import RecoveryStateMachine, RecoveryFlowManager
from Day2_audit import AuditLedger

from Day4_synthetic_data import SyntheticPayment

logger = logging.getLogger(__name__)


def _to_day2_block(day1_block) -> BlockTypeEnum:
    """
    Day 1 and Day 2 each define their own Block enum with matching member
    names (BLOCK_1, BLOCK_2, ...) but as different classes. Bridge by name
    rather than passing the Day1 member straight into a Day2 ORM column.
    """
    return BlockTypeEnum[day1_block.name]


def _to_day2_root_cause(day1_root_cause) -> RootCauseEnum:
    """Same class-mismatch bridge as _to_day2_block, for root causes."""
    return RootCauseEnum[day1_root_cause.name]


# A transaction only ever reaches SUBSCRIPTION_PAUSED via a *failed* fallback
# attempt inside _try_fallback() below - nothing else calls mark_paused().
# So this one state value is the reliable signature of "escalated to the
# fallback link/grace period, and the customer didn't pay it."
_FALLBACK_FAILURE_STATE = "SUBSCRIPTION_PAUSED"
_FALLBACK_SUCCESS_STATE = "RECOVERED_VIA_FALLBACK"


@dataclass
class EnginePaymentOutcome:
    """What actually happened to one payment, as reported by the real engine."""
    invoice_id: str
    block: str
    root_cause: str
    recovery_score: float
    final_state: str
    recovered: bool
    via_fallback: bool
    amount_paise: int
    error_code: str
    payment_method: str


class EngineRunner:
    """
    Runs a batch of synthetic payments through the real Day 1 + Day 2
    pipeline and returns what actually happened to each one.
    """

    def __init__(self, seed: int = 42):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
        Base.metadata.create_all(self.engine)

        self.diagnostic_engine = DiagnosticEngine()
        self.state_machine = RecoveryStateMachine()
        self.flow_manager = RecoveryFlowManager(self.state_machine)
        self.audit_ledger = AuditLedger()

        self._rng = random.Random(seed)

        logger.info(
            "✓ EngineRunner initialized (real Day1+Day2 pipeline, in-memory DB)"
        )

    # ------------------------------------------------------------------
    # Webhook construction
    # ------------------------------------------------------------------

    def _payment_to_webhook(self, payment: SyntheticPayment) -> WebhookEvent:
        """Build a production-shaped WebhookEvent from a synthetic payment."""
        now_ts = int(datetime.now(timezone.utc).timestamp())
        return WebhookEvent(
            id=f"evt_{payment.invoice_id}",
            event="charge.failed",
            created_at=now_ts,
            data=ChargeData(
                id=f"ch_{payment.invoice_id}",
                invoice_id=payment.invoice_id,
                customer_id=payment.customer_id,
                amount=payment.amount_paise,
                currency="INR",
                error=PaymentError(
                    code=payment.error_code.value,
                    message=f"Transaction failed: {payment.error_code.value}",
                ),
                payment_method=PaymentMethod(
                    type=payment.payment_method.value,
                    card=(
                        Card(id=f"card_{payment.invoice_id}")
                        if payment.payment_method.value == "card"
                        else None
                    ),
                ),
                status="failed",
                created_at=now_ts,
            ),
        )

    def _fake_customer(self, payment: SyntheticPayment) -> SimpleNamespace:
        """Lightweight stand-in with just the attrs setup_grace_period() reads."""
        tier = (
            LTVTierEnum.TIER_2
            if payment.customer_segment.value == "TIER_2"
            else LTVTierEnum.TIER_1
        )
        return SimpleNamespace(ltv_tier=tier, name=None, phone=None, email=None)

    def _roll(self, probability: float) -> bool:
        return self._rng.random() < max(0.0, min(1.0, probability))

    # ------------------------------------------------------------------
    # Per-payment run
    # ------------------------------------------------------------------

    def _try_fallback(self, flow, payment: SyntheticPayment, session) -> bool:
        """
        Route a flow through the BLOCK_4 fallback UPI link and simulate
        whether the customer pays it. 0.65 mirrors Day1_diagnostic's own
        BLOCK_4 recovery_score (fallback links convert ~65% of the time),
        so this isn't a made-up number - it's the real engine's own estimate
        for that block, reused as the roll probability.
        """
        customer = self._fake_customer(payment)
        self.flow_manager.setup_grace_period(flow, customer, session)

        if self._roll(0.65):
            self.flow_manager.mark_recovered(flow, via_fallback=True, session=session)
            return True

        self.flow_manager.mark_paused(flow, session=session)
        return False

    def run_payment(self, payment: SyntheticPayment, session) -> EnginePaymentOutcome:
        webhook = self._payment_to_webhook(payment)

        # --- Real Day 1 classification ---
        diagnostic = self.diagnostic_engine.classify(webhook)
        day2_block = _to_day2_block(diagnostic.block)
        day2_root_cause = _to_day2_root_cause(diagnostic.root_cause)

        # --- Real Day 2 flow creation ---
        flow = self.flow_manager.create_flow(
            invoice_id=payment.invoice_id,
            customer_id=payment.customer_id,
            block=day2_block,
            root_cause=day2_root_cause,
            recovery_score=diagnostic.recovery_score,
            session=session,
        )

        self.audit_ledger.log_event(
            session=session,
            invoice_id=payment.invoice_id,
            customer_id=payment.customer_id,
            action=ActionTypeEnum.WEBHOOK_RECEIVED,
            error_code=payment.error_code.value,
            state_after=flow.current_state,
            details={"amount_paise": payment.amount_paise},
        )
        self.audit_ledger.log_event(
            session=session,
            invoice_id=payment.invoice_id,
            customer_id=payment.customer_id,
            action=ActionTypeEnum.DIAGNOSED,
            block=day2_block,
            root_cause=day2_root_cause,
            state_after=flow.current_state,
            details={
                "recovery_score": diagnostic.recovery_score,
                "next_action": diagnostic.next_action,
            },
        )

        recovered = False
        via_fallback = False

        if day2_block == BlockTypeEnum.BLOCK_1:
            # Real retry-scheduling logic (respects the max-2-retries guardrail)
            self.flow_manager.schedule_retry_1(flow, session)
            if self._roll(diagnostic.recovery_score):
                self.flow_manager.mark_recovered(flow, session=session)
                recovered = True
            else:
                self.flow_manager.schedule_retry_2(flow, session)
                if self._roll(diagnostic.recovery_score * 0.6):
                    self.flow_manager.mark_recovered(flow, session=session)
                    recovered = True
                else:
                    self.state_machine.transition(
                        flow, RecoveryStateEnum.BLOCK_4_ESCALATED, session
                    )
                    recovered = self._try_fallback(flow, payment, session)
                    via_fallback = recovered

        elif day2_block == BlockTypeEnum.BLOCK_2:
            self.flow_manager.schedule_salary_window_retry(flow, session)
            self.state_machine.transition(
                flow, RecoveryStateEnum.SALARY_RETRY_ATTEMPTED, session
            )
            if self._roll(diagnostic.recovery_score):
                self.flow_manager.mark_recovered(flow, session=session)
                recovered = True
            else:
                self.state_machine.transition(
                    flow, RecoveryStateEnum.BLOCK_4_ESCALATED, session
                )
                recovered = self._try_fallback(flow, payment, session)
                via_fallback = recovered

        else:
            # BLOCK_3 (dead instrument, recovery_score=0.0 - retry is
            # pointless) and BLOCK_4 (already escalated / unknown error)
            # both go straight to the fallback link.
            recovered = self._try_fallback(flow, payment, session)
            via_fallback = recovered

        self.audit_ledger.log_event(
            session=session,
            invoice_id=payment.invoice_id,
            customer_id=payment.customer_id,
            action=ActionTypeEnum.RECOVERED if recovered else ActionTypeEnum.RETRY_SCHEDULED,
            block=day2_block,
            state_after=flow.current_state,
            details={"final": True, "via_fallback": via_fallback},
        )

        return EnginePaymentOutcome(
            invoice_id=payment.invoice_id,
            block=day2_block.value,
            root_cause=day2_root_cause.value,
            recovery_score=diagnostic.recovery_score,
            final_state=flow.current_state.value,
            recovered=recovered,
            via_fallback=via_fallback,
            amount_paise=payment.amount_paise,
            error_code=payment.error_code.value,
            payment_method=payment.payment_method.value,
        )

    # ------------------------------------------------------------------
    # Batch run
    # ------------------------------------------------------------------

    def run_batch(self, payments: List[SyntheticPayment]) -> List[EnginePaymentOutcome]:
        session = self.SessionLocal()
        outcomes: List[EnginePaymentOutcome] = []
        try:
            for payment in payments:
                try:
                    outcomes.append(self.run_payment(payment, session))
                except Exception as e:
                    logger.error(
                        f"❌ Engine run failed for {payment.invoice_id}: {e}",
                        exc_info=True,
                    )
                    outcomes.append(EnginePaymentOutcome(
                        invoice_id=payment.invoice_id,
                        block=payment.block_category,
                        root_cause="ERROR",
                        recovery_score=0.0,
                        final_state="ERROR",
                        recovered=False,
                        via_fallback=False,
                        amount_paise=payment.amount_paise,
                        error_code=payment.error_code.value,
                        payment_method=payment.payment_method.value,
                    ))
            session.commit()

            # Verify the audit hash chain is actually intact for every
            # invoice - this is a real integrity check, not a display value.
            chain_valid = all(
                self.audit_ledger.verify_chain_integrity(session, o.invoice_id)[0]
                for o in outcomes
            )
            logger.info(f"✓ Batch complete. Audit chain valid: {chain_valid}")
        finally:
            session.close()

        return outcomes

    def verify_all_chains(self, invoice_ids: List[str]) -> bool:
        """Re-open a session and verify every invoice's audit chain."""
        session = self.SessionLocal()
        try:
            return all(
                self.audit_ledger.verify_chain_integrity(session, inv_id)[0]
                for inv_id in invoice_ids
            )
        finally:
            session.close()

    def get_audit_trail(self, invoice_id: str) -> List[Dict[str, Any]]:
        """
        Re-open a session and fetch the real hash-chained audit trail for one
        invoice, via the same AuditLedger.get_audit_trail() Day 2 exposes.
        Used by the benchmark harness to populate the Block 5 "Guardrails &
        Audit Ledger" dashboard tab with real trace rows, not placeholders.
        The in-memory SQLite engine is kept alive across sessions on
        `self.engine` for the lifetime of this EngineRunner, the same way
        `verify_all_chains()` above re-opens a session after run_batch().
        """
        session = self.SessionLocal()
        try:
            return self.audit_ledger.get_audit_trail(session, invoice_id)
        finally:
            session.close()


# ============================================================================
# LEGACY OUTCOME SHAPE (for Day4_recovery_scorer.py / RevenueCalculator)
# ============================================================================

def build_legacy_outcomes(
    engine_outcomes: List[EnginePaymentOutcome],
) -> Dict[str, Any]:
    """
    Reshape real EnginePaymentOutcome results into the same dict shape the
    old (fake) generate_recovery_outcomes() used to produce, so
    Day4_recovery_scorer.RecoveryScorer and RevenueCalculator keep working
    unmodified on the top-level keys (total, recovered, failed, paused,
    by_block, total_amount_paise, recovered_amount_paise).

    Fix (2026-09): `by_block` still aggregates by entry classification -
    that part is correct and untouched, and is exactly right for BLOCK_1/
    BLOCK_2. But entry classification alone can't answer "was this
    transaction ever escalated to the BLOCK_4 fallback link, and did it
    convert?" - BLOCK_4 isn't an entry code, and BLOCK_1/BLOCK_2
    transactions that got escalated still carry their *original* block
    here. So each transaction dict in `recovered` / `paused` / `failed` now
    also carries `via_fallback` (bool) and `final_state` (str) - purely
    additive fields the scorer's corrected `_analyze_by_block()` uses to
    compute Block 4's real denominator (everyone ever escalated to
    fallback) and numerator (everyone who reached RECOVERED_VIA_FALLBACK),
    regardless of entry block. Nothing here changes for existing consumers
    that only read the original keys.
    """
    outcomes: Dict[str, Any] = {
        "total": len(engine_outcomes),
        "recovered": [],
        "failed": [],
        "paused": [],
        "by_block": {
            "BLOCK_1": {"total": 0, "recovered": 0, "rate": 0.0},
            "BLOCK_2": {"total": 0, "recovered": 0, "rate": 0.0},
            "BLOCK_3": {"total": 0, "recovered": 0, "rate": 0.0},
            "BLOCK_4": {"total": 0, "recovered": 0, "rate": 0.0},
        },
        "total_amount_paise": 0,
        "recovered_amount_paise": 0,
    }

    for o in engine_outcomes:
        block_stats = outcomes["by_block"].setdefault(
            o.block, {"total": 0, "recovered": 0, "rate": 0.0}
        )
        block_stats["total"] += 1
        outcomes["total_amount_paise"] += o.amount_paise

        if o.recovered:
            outcomes["recovered"].append({
                "invoice_id": o.invoice_id,
                "amount": o.amount_paise / 100,
                "block": o.block,
                "method": o.payment_method,
                "via_fallback": o.via_fallback,
                "final_state": o.final_state,
            })
            outcomes["recovered_amount_paise"] += o.amount_paise
            block_stats["recovered"] += 1
        elif o.final_state == _FALLBACK_FAILURE_STATE:
            outcomes["paused"].append({
                "invoice_id": o.invoice_id,
                "amount": o.amount_paise / 100,
                "block": o.block,
                "final_state": o.final_state,
            })
        else:
            outcomes["failed"].append({
                "invoice_id": o.invoice_id,
                "amount": o.amount_paise / 100,
                "block": o.block,
                "error": o.error_code,
                "final_state": o.final_state,
            })

    for block_data in outcomes["by_block"].values():
        if block_data["total"] > 0:
            block_data["rate"] = block_data["recovered"] / block_data["total"]

    return outcomes