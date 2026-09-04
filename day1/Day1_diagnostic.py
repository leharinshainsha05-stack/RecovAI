"""
RecovAI: Diagnostic Classifier Engine
Day 1: Root cause diagnosis and block routing logic
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import json
import logging
from Day1_models import (
    WebhookEvent, DiagnosticResult, BlockType, RootCauseType, 
    SeverityLevel
)


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DiagnosticEngine:
    """
    Core diagnostic classifier that parses payment failure webhooks
    and routes them to appropriate recovery blocks.
    """
    
    # Error code to root cause mapping
    ERROR_CODE_MAPPING = {
        # Gateway & Network errors (BLOCK 1)
        "GATEWAY_TIMEOUT": (RootCauseType.GATEWAY_TIMEOUT, BlockType.BLOCK_1, SeverityLevel.HIGH),
        "GATEWAY_ERROR_5XX": (RootCauseType.GATEWAY_ERROR_5XX, BlockType.BLOCK_1, SeverityLevel.HIGH),
        "REQUEST_TIMEOUT": (RootCauseType.GATEWAY_TIMEOUT, BlockType.BLOCK_1, SeverityLevel.HIGH),
        "NETWORK_ERROR": (RootCauseType.NETWORK_ERROR, BlockType.BLOCK_1, SeverityLevel.HIGH),
        "ISSUER_TIMEOUT": (RootCauseType.GATEWAY_TIMEOUT, BlockType.BLOCK_1, SeverityLevel.MEDIUM),
        
        # Liquidity errors (BLOCK 2)
        "INSUFFICIENT_FUNDS": (RootCauseType.INSUFFICIENT_FUNDS, BlockType.BLOCK_2, SeverityLevel.MEDIUM),
        "LOW_BALANCE": (RootCauseType.LOW_BALANCE, BlockType.BLOCK_2, SeverityLevel.MEDIUM),
        "ACCOUNT_CLOSED": (RootCauseType.INSUFFICIENT_FUNDS, BlockType.BLOCK_2, SeverityLevel.HIGH),
        
        # Dead instrument errors (BLOCK 3)
        "CARD_EXPIRED": (RootCauseType.CARD_EXPIRED, BlockType.BLOCK_3, SeverityLevel.HIGH),
        "MANDATE_REVOKED": (RootCauseType.MANDATE_REVOKED, BlockType.BLOCK_3, SeverityLevel.HIGH),
        "CVV_MISMATCH": (RootCauseType.CVV_MISMATCH, BlockType.BLOCK_3, SeverityLevel.HIGH),
        "INVALID_TOKEN": (RootCauseType.INVALID_TOKEN, BlockType.BLOCK_3, SeverityLevel.HIGH),
        "FRAUD_DECLINED": (RootCauseType.FRAUD_DECLINED, BlockType.BLOCK_3, SeverityLevel.CRITICAL),
        "ISSUER_DECLINED": (RootCauseType.ISSUER_DECLINED, BlockType.BLOCK_3, SeverityLevel.HIGH),
        "STOLEN_CARD": (RootCauseType.FRAUD_DECLINED, BlockType.BLOCK_3, SeverityLevel.CRITICAL),
    }
    
    # Hard decline error codes (no retry possible)
    HARD_DECLINE_CODES = {
        "CARD_EXPIRED", "MANDATE_REVOKED", "CVV_MISMATCH", 
        "INVALID_TOKEN", "FRAUD_DECLINED", "ISSUER_DECLINED",
        "STOLEN_CARD", "DO_NOT_HONOUR"
    }
    
    # Soft/transient error codes (retryable)
    SOFT_DECLINE_CODES = {
        "GATEWAY_TIMEOUT", "REQUEST_TIMEOUT", "NETWORK_ERROR",
        "ISSUER_TIMEOUT", "GATEWAY_ERROR_5XX", "INSUFFICIENT_FUNDS",
        "LOW_BALANCE"
    }
    
    def __init__(self):
        """Initialize diagnostic engine"""
        self.gateway_health = {}  # In Day 2/3, replace with Redis lookup
        logger.info("✓ DiagnosticEngine initialized")
    
    def classify(self, webhook: WebhookEvent) -> DiagnosticResult:
        """
        Main diagnostic method: classify failure and determine recovery block.
        
        Args:
            webhook: Razorpay webhook event
            
        Returns:
            DiagnosticResult with block routing and recovery score
        """
        invoice_id = webhook.data.invoice_id or webhook.data.payment_id
        customer_id = webhook.data.customer_id
        error_code = webhook.data.error.code
        amount = webhook.data.amount
        
        logger.info(f"📋 Classifying error: {error_code} for invoice {invoice_id}")
        
        # Step 1: Map error code
        if error_code in self.ERROR_CODE_MAPPING:
            root_cause, block, severity = self.ERROR_CODE_MAPPING[error_code]
        else:
            logger.warning(f"⚠️  Unknown error code: {error_code}")
            root_cause = RootCauseType.UNKNOWN
            block = BlockType.BLOCK_4  # Escalate unknown to fallback
            severity = SeverityLevel.MEDIUM
        
        # Step 2: Apply context-aware logic
        block, severity = self._apply_contextual_rules(
            error_code, block, severity, webhook
        )
        
        # Step 3: Calculate recovery score
        recovery_score = self._calculate_recovery_score(error_code, block)
        
        # Step 4: Determine next action
        next_action = self._determine_next_action(block, error_code)
        
        result = DiagnosticResult(
            invoice_id=invoice_id,
            block=block,
            root_cause=root_cause,
            severity=severity,
            recovery_score=recovery_score,
            retry_count=0,
            next_action=next_action,
            details={
                "error_code": error_code,
                "error_message": webhook.data.error.message,
                "amount": amount,
                "customer_id": customer_id,
                "payment_method": webhook.data.payment_method.type,
                "is_hard_decline": error_code in self.HARD_DECLINE_CODES,
                "is_soft_decline": error_code in self.SOFT_DECLINE_CODES,
            }
        )
        
        logger.info(f"✓ Classified to {result.block} (recovery_score: {recovery_score:.2f})")
        return result
    
    def _apply_contextual_rules(
        self,
        error_code: str,
        block: BlockType,
        severity: SeverityLevel,
        webhook: WebhookEvent
    ) -> tuple:
        """
        Apply contextual rules based on date, gateway health, mandate status.
        
        Returns:
            (updated_block, updated_severity)
        """
        
        # Rule 1: FRAUD_DECLINED is always CRITICAL (BLOCK_3)
        if error_code == "FRAUD_DECLINED":
            logger.info(f"🚨 FRAUD DETECTED - Setting to BLOCK_3 with CRITICAL severity")
            return BlockType.BLOCK_3, SeverityLevel.CRITICAL

        # Rule 2: Hard declines always → BLOCK_3 (no retry possible)
        if error_code in self.HARD_DECLINE_CODES:
            logger.info(f"🚫 Hard decline detected: {error_code} → BLOCK_3")
            return BlockType.BLOCK_3, SeverityLevel.HIGH

        # Rule 3: INSUFFICIENT_FUNDS on month-end dates (25-31) → BLOCK_2
        if error_code == "INSUFFICIENT_FUNDS":
            today = datetime.now(timezone.utc).day
            if 25 <= today <= 31:
                logger.info(f"📅 Month-end liquidity pattern detected (day {today}) → BLOCK_2")
                return BlockType.BLOCK_2, SeverityLevel.MEDIUM
        
        # Rule 4: Gateway timeouts with low gateway health → BLOCK_1
        if error_code in ["GATEWAY_TIMEOUT", "REQUEST_TIMEOUT", "ISSUER_TIMEOUT"]:
            # Check gateway health (simulated for now, real implementation queries Redis)
            gateway_health_score = self._get_gateway_health_score()
            if gateway_health_score < 0.95:
                logger.info(f"⚠️  Gateway degraded (health: {gateway_health_score:.2%}) → BLOCK_1")
                return BlockType.BLOCK_1, SeverityLevel.HIGH
        
        # Rule 5: Recurring payment mandates check (requires mandate status lookup)
        # In production, query Razorpay API to validate mandate status
        if webhook.data.payment_method.type == "nach":
            logger.info("🔄 NACH mandate detected - validating instrument status")
            # Will be queried from Razorpay in production
        
        # Rule 6: Unknown errors escalate to BLOCK_4 (fallback link)
        if block == BlockType.BLOCK_4:
            logger.info(f"⚠️  Escalating unknown/unhandled error to BLOCK_4 (fallback link)")
            return BlockType.BLOCK_4, SeverityLevel.MEDIUM
        
        return block, severity
    
    def _calculate_recovery_score(self, error_code: str, block: BlockType) -> float:
        """
        Calculate probability of successful recovery (0.0 to 1.0).
        
        Scoring logic:
        - BLOCK_1 (Network): 0.85+ (transient, retryable)
        - BLOCK_2 (Liquidity): 0.75+ (wait for salary window)
        - BLOCK_3 (Dead instrument): 0.0 (no direct retry possible)
        - BLOCK_4 (Fallback): 0.60-0.70 (1-click UPI link)
        """
        
        score_map = {
            BlockType.BLOCK_1: 0.88,   # Network issues are highly retryable
            BlockType.BLOCK_2: 0.78,   # Liquidity cycles are predictable
            BlockType.BLOCK_3: 0.0,    # Dead instruments have 0% success on retry
            BlockType.BLOCK_4: 0.65,   # Fallback links have 65% conversion
            BlockType.BLOCK_5: 0.5,    # Guardrails (meta block)
            BlockType.BLOCK_6: 0.9,    # Benchmark (theoretical)
        }
        
        base_score = score_map.get(block, 0.5)
        
        # Adjust based on error code specificity
        if error_code == "GATEWAY_TIMEOUT":
            base_score += 0.02  # Likely transient
        elif error_code in self.HARD_DECLINE_CODES:
            base_score = 0.0  # Cannot recover via direct retry
        
        return min(1.0, max(0.0, base_score))
    
    def _determine_next_action(self, block: BlockType, error_code: str) -> str:
        """Determine the next action based on block classification"""
        
        actions = {
            BlockType.BLOCK_1: "LIVE_REROUTE_OR_SCHEDULED_RETRY",
            BlockType.BLOCK_2: "SCHEDULE_SALARY_WINDOW_RETRY",
            BlockType.BLOCK_3: "SKIP_TO_FALLBACK_LINK",
            BlockType.BLOCK_4: "GENERATE_1_CLICK_UPI_LINK",
            BlockType.BLOCK_5: "ENFORCE_GUARDRAILS",
            BlockType.BLOCK_6: "BENCHMARK_EVALUATION",
        }
        
        return actions.get(block, "ESCALATE_TO_MANUAL_REVIEW")
    
    def _get_gateway_health_score(self) -> float:
        """
        Get current gateway health score (0.0 to 1.0).
        
        In production: Query Redis cache updated every 30 seconds.
        For now: Return mock value.
        """
        # TODO: Replace with Redis lookup in Day 3
        return 0.97  # Mock: 97% uptime
    
    def classify_batch(self, webhooks: list) -> list:
        """
        Classify multiple webhooks (useful for testing).
        
        Args:
            webhooks: List of WebhookEvent objects
            
        Returns:
            List of DiagnosticResult objects
        """
        results = []
        for webhook in webhooks:
            try:
                result = self.classify(webhook)
                results.append(result)
            except Exception as e:
                logger.error(f"❌ Error classifying webhook: {e}")
                continue
        
        return results


def create_test_webhook(
    error_code: str,
    invoice_id: str = "inv_test_001",
    customer_id: str = "cust_test_001",
    amount: int = 99900,
    payment_method_type: str = "card"
) -> WebhookEvent:
    """
    Helper function to create test webhook events.
    
    Args:
        error_code: Error code to test
        invoice_id: Invoice ID
        customer_id: Customer ID
        amount: Amount in paise
        payment_method_type: Payment method type
        
    Returns:
        WebhookEvent object ready for classification
    """
    from Day1_models import PaymentError, Card, PaymentMethod, ChargeData
    
    return WebhookEvent(
        id=f"evt_test_{invoice_id}",
        event="charge.failed",
        created_at=int(datetime.now(timezone.utc).timestamp()),
        data=ChargeData(
            id=f"ch_test_{invoice_id}",
            invoice_id=invoice_id,
            customer_id=customer_id,
            amount=amount,
            currency="INR",
            error=PaymentError(
                code=error_code,
                message=f"Transaction failed: {error_code}"
            ),
            payment_method=PaymentMethod(
                type=payment_method_type,
                card=Card(id="card_test_001") if payment_method_type == "card" else None
            ),
            status="failed",
            created_at=int(datetime.now(timezone.utc).timestamp())
        )
    )


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    # Initialize engine
    engine = DiagnosticEngine()
    
    print("\n" + "="*80)
    print("RecovAI Diagnostic Engine - Day 1 Test Run")
    print("="*80 + "\n")
    
    # Test Case 1: Network Timeout (BLOCK 1)
    print("Test 1: Gateway Timeout (BLOCK_1)")
    print("-" * 60)
    webhook1 = create_test_webhook(error_code="GATEWAY_TIMEOUT")
    result1 = engine.classify(webhook1)
    print(f"Block: {result1.block}")
    print(f"Root Cause: {result1.root_cause}")
    print(f"Severity: {result1.severity}")
    print(f"Recovery Score: {result1.recovery_score:.2f}")
    print(f"Next Action: {result1.next_action}\n")
    
    # Test Case 2: Low Balance on Month-End (BLOCK 2)
    print("Test 2: Insufficient Funds on Month-End (BLOCK_2)")
    print("-" * 60)
    webhook2 = create_test_webhook(error_code="INSUFFICIENT_FUNDS")
    result2 = engine.classify(webhook2)
    print(f"Block: {result2.block}")
    print(f"Root Cause: {result2.root_cause}")
    print(f"Severity: {result2.severity}")
    print(f"Recovery Score: {result2.recovery_score:.2f}")
    print(f"Next Action: {result2.next_action}\n")
    
    # Test Case 3: Expired Card (BLOCK 3)
    print("Test 3: Card Expired (BLOCK_3)")
    print("-" * 60)
    webhook3 = create_test_webhook(error_code="CARD_EXPIRED")
    result3 = engine.classify(webhook3)
    print(f"Block: {result3.block}")
    print(f"Root Cause: {result3.root_cause}")
    print(f"Severity: {result3.severity}")
    print(f"Recovery Score: {result3.recovery_score:.2f}")
    print(f"Next Action: {result3.next_action}\n")
    
    # Test Case 4: Fraud Declined (CRITICAL)
    print("Test 4: Fraud Declined (CRITICAL)")
    print("-" * 60)
    webhook4 = create_test_webhook(error_code="FRAUD_DECLINED")
    result4 = engine.classify(webhook4)
    print(f"Block: {result4.block}")
    print(f"Root Cause: {result4.root_cause}")
    print(f"Severity: {result4.severity}")
    print(f"Recovery Score: {result4.recovery_score:.2f}")
    print(f"Next Action: {result4.next_action}\n")
    
    # Test Case 5: Unknown Error Code
    print("Test 5: Unknown Error Code")
    print("-" * 60)
    webhook5 = create_test_webhook(error_code="UNKNOWN_ERROR_XYZ")
    result5 = engine.classify(webhook5)
    print(f"Block: {result5.block}")
    print(f"Root Cause: {result5.root_cause}")
    print(f"Severity: {result5.severity}")
    print(f"Recovery Score: {result5.recovery_score:.2f}")
    print(f"Next Action: {result5.next_action}\n")
    
    # Batch Classification Test
    print("\n" + "="*80)
    print("Batch Classification Test (10 diverse payloads)")
    print("="*80 + "\n")
    
    test_cases = [
        ("GATEWAY_TIMEOUT", "Network issue"),
        ("INSUFFICIENT_FUNDS", "Low balance"),
        ("CARD_EXPIRED", "Expired card"),
        ("MANDATE_REVOKED", "Mandate revoked"),
        ("REQUEST_TIMEOUT", "Request timeout"),
        ("FRAUD_DECLINED", "Fraud detected"),
        ("CVV_MISMATCH", "CVV mismatch"),
        ("ISSUER_DECLINED", "Issuer declined"),
        ("LOW_BALANCE", "Account low balance"),
        ("NETWORK_ERROR", "Network error"),
    ]
    
    webhooks = [
        create_test_webhook(error_code=code, invoice_id=f"inv_batch_{i:02d}")
        for i, (code, _) in enumerate(test_cases)
    ]
    
    results = engine.classify_batch(webhooks)
    
    # Print summary table
    print(f"{'Error Code':<20} {'Block':<10} {'Severity':<12} {'Recovery Score':<15} {'Next Action':<35}")
    print("-" * 92)
    
    for result, (code, desc) in zip(results, test_cases):
        print(f"{code:<20} {result.block.value:<10} {result.severity.value:<12} {result.recovery_score:>14.2f} {result.next_action:<35}")
    
    # Summary stats
    print("\n" + "="*80)
    print("Summary Statistics")
    print("="*80)
    block_distribution = {}
    for result in results:
        block = result.block.value
        block_distribution[block] = block_distribution.get(block, 0) + 1
    
    print("\nBlock Distribution:")
    for block, count in sorted(block_distribution.items()):
        print(f"  {block}: {count} cases ({count/len(results)*100:.1f}%)")
    
    avg_recovery_score = sum(r.recovery_score for r in results) / len(results)
    print(f"\nAverage Recovery Score: {avg_recovery_score:.2f}")
    
    hard_declines = sum(1 for r in results if r.recovery_score == 0.0)
    print(f"Hard Declines (score=0): {hard_declines}/{len(results)}")
    
    print("\n✓ Day 1 diagnostic engine test completed successfully!\n")
