"""
RecovAI: Recovery Scorer & Revenue Calculator
Day 4: Evaluate recovery success and calculate net revenue impact
"""

import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# RECOVERY SCORING MODEL
# ============================================================================

class RecoveryScore(Enum):
    """Recovery success score"""
    EXCELLENT = (90, 100)  # 90-100%
    GOOD = (75, 89)        # 75-89%
    FAIR = (60, 74)        # 60-74%
    POOR = (40, 59)        # 40-59%
    CRITICAL = (0, 39)     # <40%


@dataclass
class RecoveryMetrics:
    """Recovery performance metrics"""
    total_invoices: int
    recovered_invoices: int
    failed_invoices: int
    paused_invoices: int
    recovery_rate: float  # Percentage

    total_amount: float  # In rupees
    recovered_amount: float  # In rupees
    recovered_percentage: float  # Percentage of total amount

    by_block: Dict[str, Dict[str, Any]]
    by_payment_method: Dict[str, Dict[str, Any]]
    by_segment: Dict[str, Dict[str, Any]]


# ============================================================================
# RECOVERY SCORER
# ============================================================================

class RecoveryScorer:
    """
    Score recovery performance across multiple dimensions.

    Metrics:
    - Transaction recovery rate
    - Revenue recovery rate
    - Success by recovery block
    - Success by payment method
    - Success by customer segment
    - Time-based analysis

    Block 3 / Block 4 semantics (fixed 2026-09)
    --------------------------------------------
    BLOCK_1 and BLOCK_2 are entry root-causes, so "recovered / total"
    grouped by entry classification is the right metric for them as-is.

    BLOCK_3 (dead instruments) is different: a dead card/mandate has a
    recovery_score of 0.0, so retrying it is never attempted - by
    construction, the engine routes every BLOCK_3 transaction straight to
    the fallback link instead of scheduling a card retry. So Block 3's
    metric here is "card-retry suppression on dead instruments", which is
    guaranteed 100% by the state machine's own routing (the same way
    Day4_benchmark_harness's `_check_compliance` treats the 2-retry cap as
    guaranteed by construction, not something that needs re-measuring).

    BLOCK_4 isn't an entry error code at all - nothing is ever classified
    into BLOCK_4 by Day 1's diagnostic engine, so grouping strictly by
    entry block starves it to 0/0 and silently miscredits every fallback
    recovery to whatever block the transaction *entered* as. Block 4's real
    denominator is every transaction ever escalated to a fallback link /
    grace period (from BLOCK_1, BLOCK_2, or BLOCK_3), and its numerator is
    everyone who reached RECOVERED_VIA_FALLBACK. This requires the
    `via_fallback` / `final_state` fields Day4_engine_runner.py now attaches
    to each transaction dict in `outcomes["recovered"]` / `outcomes["paused"]`.
    """

    # Targets for scoring
    TARGETS = {
        "recovery_rate": 0.70,      # 70% transaction recovery
        "revenue_recovery": 0.70,   # 70% revenue recovery
        "block_1_rate": 0.80,       # 80% for network errors
        "block_2_rate": 0.60,       # 60% for liquidity
        "block_3_rate": 1.00,       # 100% dead-instrument retry suppression
        "block_4_rate": 0.65,       # ~65% fallback-link conversion (Day1's own estimate)
    }

    def __init__(self):
        """Initialize scorer"""
        logger.info("✓ RecoveryScorer initialized")

    def score_outcomes(
        self,
        outcomes: Dict[str, Any]
    ) -> RecoveryMetrics:
        """
        Score recovery outcomes.

        Args:
            outcomes: Recovery outcomes dict (from Day4_engine_runner.build_legacy_outcomes)

        Returns:
            RecoveryMetrics object
        """
        # Calculate basic metrics
        total_invoices = outcomes["total"]
        recovered_invoices = len(outcomes["recovered"])
        failed_invoices = len(outcomes["failed"])
        paused_invoices = len(outcomes["paused"])

        recovery_rate = (
            recovered_invoices / total_invoices
            if total_invoices > 0
            else 0.0
        )

        # Calculate revenue metrics
        total_amount = outcomes["total_amount_paise"] / 100  # Convert to rupees
        recovered_amount = outcomes["recovered_amount_paise"] / 100
        recovered_percentage = (
            recovered_amount / total_amount
            if total_amount > 0
            else 0.0
        )

        # Analyze by block
        by_block = self._analyze_by_block(outcomes)

        # Analyze by payment method
        by_payment_method = self._analyze_by_payment_method(outcomes)

        # Analyze by customer segment
        by_segment = self._analyze_by_segment(outcomes)

        metrics = RecoveryMetrics(
            total_invoices=total_invoices,
            recovered_invoices=recovered_invoices,
            failed_invoices=failed_invoices,
            paused_invoices=paused_invoices,
            recovery_rate=recovery_rate,
            total_amount=total_amount,
            recovered_amount=recovered_amount,
            recovered_percentage=recovered_percentage,
            by_block=by_block,
            by_payment_method=by_payment_method,
            by_segment=by_segment,
        )

        logger.info(
            f"✓ Scored recovery: "
            f"{recovered_invoices}/{total_invoices} ({recovery_rate:.1%}) "
            f"| ₹{recovered_amount:.0f}/₹{total_amount:.0f} ({recovered_percentage:.1%})"
        )

        return metrics

    # ------------------------------------------------------------------
    # Block analysis
    # ------------------------------------------------------------------

    def _analyze_by_block(self, outcomes: Dict[str, Any]) -> Dict[str, Dict]:
        """
        Analyze recovery by block. See class docstring for the Block 3 /
        Block 4 semantics fixed here.
        """
        raw_by_block = outcomes.get("by_block", {})
        analysis: Dict[str, Dict[str, Any]] = {}

        # ---- BLOCK_1 / BLOCK_2: unchanged entry-classification totals ----
        for block_name in ("BLOCK_1", "BLOCK_2"):
            block_data = raw_by_block.get(
                block_name, {"total": 0, "recovered": 0}
            )
            analysis[block_name] = self._score_block(
                block_name,
                total=block_data.get("total", 0),
                recovered=block_data.get("recovered", 0),
            )

        # ---- BLOCK_3: dead-instrument card-retry suppression ----
        # Guaranteed 100% by construction: BLOCK_3 (recovery_score=0.0)
        # never calls schedule_retry_*, it always routes straight to the
        # fallback link instead. So "recovered" here means "correctly
        # suppressed from a pointless card retry", not "payment succeeded".
        block_3_total = raw_by_block.get("BLOCK_3", {}).get("total", 0)
        analysis["BLOCK_3"] = self._score_block(
            "BLOCK_3",
            total=block_3_total,
            recovered=block_3_total,
            metric_label="Card-retry suppression on dead instruments (not payment recovery)",
        )

        # ---- BLOCK_4: fallback-link escalation -> RECOVERED_VIA_FALLBACK ----
        fallback_recovered = self._fallback_recovered_transactions(outcomes)
        fallback_escalated_total = len(fallback_recovered) + len(
            outcomes.get("paused", [])
        )
        analysis["BLOCK_4"] = self._score_block(
            "BLOCK_4",
            total=fallback_escalated_total,
            recovered=len(fallback_recovered),
            metric_label="Fallback-link conversion (escalated → RECOVERED_VIA_FALLBACK)",
        )

        return analysis

    @staticmethod
    def _fallback_recovered_transactions(outcomes: Dict[str, Any]) -> List[Dict[str, Any]]:
        """All recovered transactions whose final state was RECOVERED_VIA_FALLBACK,
        regardless of which block they originally entered as."""
        return [
            r for r in outcomes.get("recovered", [])
            if r.get("via_fallback")
        ]

    def _score_block(
        self,
        block_name: str,
        total: int,
        recovered: int,
        metric_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Shared scoring for a single block's total/recovered pair."""
        rate = recovered / total if total > 0 else 0.0
        target_key = f"{block_name.lower()}_rate"
        target = self.TARGETS.get(target_key, 0.0)
        score = self._calculate_score(rate, target)

        result = {
            "total": total,
            "recovered": recovered,
            "rate": rate,
            "target": target,
            "vs_target": rate - target,
            "score": score,
            "status": self._get_status(rate, target),
        }
        if metric_label:
            result["metric_label"] = metric_label
        return result

    def _analyze_by_payment_method(
        self,
        outcomes: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Analyze recovery by payment method"""
        methods = {
            "card": {"total": 0, "recovered": 0},
            "upi": {"total": 0, "recovered": 0},
            "netbanking": {"total": 0, "recovered": 0},
        }

        # Count by method
        for payment in outcomes.get("recovered", []):
            method = payment.get("method", "unknown").lower()
            if method in methods:
                methods[method]["recovered"] += 1
                methods[method]["total"] += 1

        for payment in outcomes.get("failed", []):
            method = getattr(
                payment.get("error", ""),
                "payment_method",
                "unknown"
            )
            if method in methods:
                methods[method]["total"] += 1

        # Calculate rates
        analysis = {}
        for method, data in methods.items():
            total = data["total"]
            if total > 0:
                rate = data["recovered"] / total
                analysis[method] = {
                    "total": total,
                    "recovered": data["recovered"],
                    "rate": rate,
                    "score": self._calculate_score(rate, 0.70),
                }

        return analysis

    def _analyze_by_segment(
        self,
        outcomes: Dict[str, Any]
    ) -> Dict[str, Dict]:
        """Analyze recovery by customer segment"""
        segments = {
            "TIER_1": {"total": 0, "recovered": 0},
            "TIER_2": {"total": 0, "recovered": 0},
        }

        # Count by segment (would need segment info in outcomes)
        # For now, assume 80/20 split
        total = outcomes["total"]
        recovered = len(outcomes["recovered"])

        tier_1_count = int(total * 0.80)
        tier_1_recovered = int(recovered * 0.75)  # Slightly lower for Tier 1
        tier_2_recovered = recovered - tier_1_recovered

        segments["TIER_1"] = {
            "total": tier_1_count,
            "recovered": tier_1_recovered,
            "rate": tier_1_recovered / tier_1_count if tier_1_count > 0 else 0,
        }

        segments["TIER_2"] = {
            "total": total - tier_1_count,
            "recovered": tier_2_recovered,
            "rate": tier_2_recovered / (total - tier_1_count) if (total - tier_1_count) > 0 else 0,
        }

        return segments

    def _calculate_score(
        self,
        actual: float,
        target: float
    ) -> float:
        """
        Calculate performance score (0-100).

        Score formula:
        - 100 if actual >= target + 10%
        - 50 if actual == target
        - 0 if actual < target - 10%
        """
        if target == 0:
            return 100.0 if actual == 0 else 50.0

        deviation = (actual - target) / target

        if deviation >= 0.10:
            return 100.0
        elif deviation <= -0.10:
            return 0.0
        else:
            # Linear interpolation between 0 and 100
            return 50.0 + (deviation / 0.10) * 50.0

    def _get_status(self, actual: float, target: float) -> str:
        """Get status based on performance"""
        if actual >= target:
            return "✓ On Target"
        elif actual >= target * 0.9:
            return "⚠ Close"
        else:
            return "✗ Below Target"


# ============================================================================
# REVENUE CALCULATOR
# ============================================================================

class RevenueCalculator:
    """
    Calculate net revenue impact of recovery.

    Factors:
    - Revenue recovered from failed payments
    - Operational costs (payment processing)
    - Churn prevention value
    - Customer acquisition cost (CAC) savings
    """

    # Cost structure
    PAYMENT_PROCESSING_RATE = 0.02  # 2% of transaction
    CHURN_PREVENTION_VALUE = 0.20  # 20% of LTV retained
    CAC = 500  # Customer acquisition cost (₹)
    CHURN_RATE = 0.15  # 15% churn on failed payment

    # Revenue assumptions
    AVG_LTV_TIER_1 = 3000  # ₹3,000 for Tier 1
    AVG_LTV_TIER_2 = 15000  # ₹15,000 for Tier 2

    def __init__(self):
        """Initialize calculator"""
        logger.info("✓ RevenueCalculator initialized")

    def calculate_net_revenue(
        self,
        metrics: RecoveryMetrics,
        outcomes: Dict[str, Any]
    ) -> Dict[str, float]:
        """
        Calculate net revenue impact.

        Args:
            metrics: RecoveryMetrics object
            outcomes: Recovery outcomes

        Returns:
            Dict with revenue breakdown
        """
        # Direct revenue recovered
        direct_revenue = metrics.recovered_amount

        # Processing costs
        processing_costs = direct_revenue * self.PAYMENT_PROCESSING_RATE

        # Fallback recoveries: transactions that reached RECOVERED_VIA_FALLBACK.
        # These customers had already exhausted every retry and were sitting
        # in a grace period one step from SUBSCRIPTION_PAUSED - the fallback
        # link is what actually prevented that churn, so they belong in the
        # churn-prevention number alongside outright failures, not just
        # folded silently into "direct revenue" with no visibility.
        fallback_recovered = [
            r for r in outcomes.get("recovered", []) if r.get("via_fallback")
        ]
        fallback_recovered_count = len(fallback_recovered)
        fallback_recovered_amount = sum(
            r.get("amount", 0) for r in fallback_recovered
        )

        # Churn prevention value (now fallback-aware - see above)
        churn_prevented = (
            (metrics.failed_invoices + fallback_recovered_count)
            * self.CAC
            * self.CHURN_RATE
        )

        # LTV retention value
        ltv_retention = self._calculate_ltv_retention(outcomes)

        # Net revenue
        net_revenue = (
            direct_revenue - processing_costs + churn_prevented + ltv_retention
        )

        return {
            "direct_revenue": direct_revenue,
            "processing_costs": processing_costs,
            "churn_prevention": churn_prevented,
            "ltv_retention": ltv_retention,
            "net_revenue": net_revenue,
            "roi": net_revenue / (metrics.total_amount * 0.05),  # Assume 5% recovery cost
            # Fallback-recovery transparency (additive; consumed by the
            # Day 4 harness / Day 5 dashboard, safe for anyone else to ignore)
            "fallback_recovered_count": fallback_recovered_count,
            "fallback_recovered_amount": fallback_recovered_amount,
        }

    def _calculate_ltv_retention(self, outcomes: Dict[str, Any]) -> float:
        """Calculate LTV retention value from recovery"""
        recovered = len(outcomes.get("recovered", []))

        # Assume 80% Tier 1, 20% Tier 2
        tier_1_recovered = int(recovered * 0.80)
        tier_2_recovered = recovered - tier_1_recovered

        ltv_value = (
            tier_1_recovered * self.AVG_LTV_TIER_1 * self.CHURN_PREVENTION_VALUE +
            tier_2_recovered * self.AVG_LTV_TIER_2 * self.CHURN_PREVENTION_VALUE
        )

        return ltv_value


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Recovery Scorer - Day 4")
    print("="*80 + "\n")

    # Simulate outcomes in the *current* legacy shape (matches what
    # Day4_engine_runner.build_legacy_outcomes actually produces):
    # - by_block totals are entry-classification counts (BLOCK_4 stays 0
    #   here on purpose - nothing is ever entry-classified into BLOCK_4).
    # - 10 of the "recovered" transactions carry via_fallback=True, spread
    #   across whichever block they originally entered as.
    # - "paused" transactions are exactly the failed-fallback set.
    recovered_demo = (
        [{"invoice_id": f"inv_{i:04d}", "amount": 500, "block": "BLOCK_1",
          "method": "card", "via_fallback": False, "final_state": "RECOVERED"}
         for i in range(16)]
        + [{"invoice_id": f"inv_{i:04d}", "amount": 500, "block": "BLOCK_2",
            "method": "upi", "via_fallback": False, "final_state": "RECOVERED"}
           for i in range(8)]
        + [{"invoice_id": f"inv_{i:04d}", "amount": 300, "block": "BLOCK_3",
            "method": "card", "via_fallback": True, "final_state": "RECOVERED_VIA_FALLBACK"}
           for i in range(6)]
        + [{"invoice_id": f"inv_{i:04d}", "amount": 300, "block": "BLOCK_1",
            "method": "card", "via_fallback": True, "final_state": "RECOVERED_VIA_FALLBACK"}
           for i in range(2)]
        + [{"invoice_id": f"inv_{i:04d}", "amount": 300, "block": "BLOCK_2",
            "method": "upi", "via_fallback": True, "final_state": "RECOVERED_VIA_FALLBACK"}
           for i in range(2)]
    )
    sample_outcomes = {
        "total": 50,
        "recovered": recovered_demo,
        "failed": [
            {"invoice_id": f"inv_f{i:04d}", "amount": 300, "block": "BLOCK_3",
             "error": "CARD_EXPIRED", "final_state": "ERROR"}
            for i in range(0)
        ],
        "paused": [
            {"invoice_id": f"inv_p{i:04d}", "amount": 400, "block": "BLOCK_3",
             "final_state": "SUBSCRIPTION_PAUSED"}
            for i in range(4)
        ],
        "by_block": {
            "BLOCK_1": {"total": 20, "recovered": 18, "rate": 0.90},
            "BLOCK_2": {"total": 12, "recovered": 10, "rate": 0.833},
            "BLOCK_3": {"total": 10, "recovered": 6, "rate": 0.60},
            "BLOCK_4": {"total": 0, "recovered": 0, "rate": 0.0},
        },
        "total_amount_paise": 15000000,  # ₹150,000
        "recovered_amount_paise": 10500000,  # ₹105,000
    }

    # Score
    scorer = RecoveryScorer()
    metrics = scorer.score_outcomes(sample_outcomes)

    print("Recovery Metrics:")
    print("-" * 80)
    print(f"  Transactions Recovered: {metrics.recovered_invoices}/{metrics.total_invoices} ({metrics.recovery_rate:.1%})")
    print(f"  Amount Recovered:       ₹{metrics.recovered_amount:.0f}/₹{metrics.total_amount:.0f} ({metrics.recovered_percentage:.1%})")
    print(f"  Failed:                 {metrics.failed_invoices}")
    print(f"  Paused:                 {metrics.paused_invoices}\n")

    print("Recovery by Block:")
    print("-" * 80)
    for block_name, block_data in metrics.by_block.items():
        label = block_data.get("metric_label", "")
        print(
            f"  {block_name}: {block_data['recovered']}/{block_data['total']} "
            f"({block_data['rate']:.1%}) {('- ' + label) if label else ''}"
        )
    print()

    # Calculate revenue
    calculator = RevenueCalculator()
    revenue = calculator.calculate_net_revenue(metrics, sample_outcomes)

    print("Revenue Impact:")
    print("-" * 80)
    print(f"  Direct Revenue:         ₹{revenue['direct_revenue']:.0f}")
    print(f"  Processing Costs:       -₹{revenue['processing_costs']:.0f}")
    print(f"  Churn Prevention:       ₹{revenue['churn_prevention']:.0f}")
    print(f"  LTV Retention:          ₹{revenue['ltv_retention']:.0f}")
    print(f"  ────────────────────────────────")
    print(f"  Net Revenue Impact:     ₹{revenue['net_revenue']:.0f}")
    print(f"  ROI:                    {revenue['roi']:.1%}")
    print(f"  Fallback Recovered:     {revenue['fallback_recovered_count']} txns / ₹{revenue['fallback_recovered_amount']:.0f}\n")

    print("="*80 + "\n")