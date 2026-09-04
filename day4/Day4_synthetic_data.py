"""
RecovAI: Synthetic Data Generator
Day 4: Generate 50 payment transactions for benchmarking
"""

import random
import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


# ============================================================================
# DATA MODELS
# ============================================================================

class PaymentMethod(str, Enum):
    """Payment methods"""
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    WALLET = "wallet"


class ErrorCode(str, Enum):
    """Error codes that cause failures"""
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


class CustomerSegment(str, Enum):
    """Customer LTV segments"""
    TIER_1 = "TIER_1"  # B2C, LTV ₹0-5,000
    TIER_2 = "TIER_2"  # High-LTV/B2B, ₹5,000+


@dataclass
class SyntheticPayment:
    """Synthetic payment transaction"""
    invoice_id: str
    customer_id: str
    customer_name: str
    customer_email: str
    customer_phone: str
    customer_segment: CustomerSegment
    amount_paise: int  # in paise
    payment_method: PaymentMethod
    error_code: ErrorCode
    timestamp: str
    subscription_id: str
    block_category: str = "BLOCK_1"  
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return asdict(self)


# ============================================================================
# SYNTHETIC DATA GENERATOR
# ============================================================================

class SyntheticDataGenerator:
    """
    Generate realistic payment failure data for benchmarking.
    
    Distribution:
    - BLOCK_1 (Network errors): 40%
    - BLOCK_2 (Liquidity): 25%
    - BLOCK_3 (Dead instruments): 20%
    - BLOCK_4 (Others): 15%
    """
    
    # Customer name pool
    FIRST_NAMES = [
        "Aarav", "Vivaan", "Arjun", "Rohan", "Priya",
        "Ananya", "Neha", "Deepak", "Sameer", "Rajesh",
        "Suresh", "Vikram", "Aditya", "Sanjay", "Harsha",
        "Divya", "Pooja", "Shreya", "Akshay", "Rahul"
    ]
    
    LAST_NAMES = [
        "Kumar", "Singh", "Patel", "Shah", "Gupta",
        "Sharma", "Verma", "Rao", "Nair", "Menon",
        "Desai", "Joshi", "Kulkarni", "Reddy", "Iyer"
    ]
    
    # Amount distribution (in rupees)
    AMOUNT_RANGES = [
        (100, 500),      # Small transactions
        (500, 2000),     # Regular transactions
        (2000, 5000),    # Large transactions
        (5000, 10000),   # Very large transactions
    ]
    
    # Error code distribution by recovery block
    BLOCK_1_ERRORS = [
        ErrorCode.GATEWAY_TIMEOUT,
        ErrorCode.GATEWAY_ERROR_5XX,
        ErrorCode.NETWORK_ERROR,
    ]
    
    BLOCK_2_ERRORS = [
        ErrorCode.INSUFFICIENT_FUNDS,
        ErrorCode.LOW_BALANCE,
    ]
    
    BLOCK_3_ERRORS = [
        ErrorCode.CARD_EXPIRED,
        ErrorCode.MANDATE_REVOKED,
        ErrorCode.CVV_MISMATCH,
        ErrorCode.INVALID_TOKEN,
        ErrorCode.FRAUD_DECLINED,
        ErrorCode.ISSUER_DECLINED,
    ]
    
    def __init__(self, seed: int = 42):
        """
        Initialize generator.
        
        Args:
            seed: Random seed for reproducibility
        """
        random.seed(seed)
        logger.info("✓ SyntheticDataGenerator initialized")
    
    def generate_batch(self, count: int = 50) -> List[SyntheticPayment]:
        """
        Generate batch of synthetic payments.
        
        Distribution:
        - BLOCK_1: 40% (20 transactions)
        - BLOCK_2: 25% (12-13 transactions)
        - BLOCK_3: 20% (10 transactions)
        - BLOCK_4: 15% (7-8 transactions)
        
        Args:
            count: Number of transactions to generate
            
        Returns:
            List of SyntheticPayment objects
        """
        payments = []
        
        # Calculate distribution
        block_1_count = int(count * 0.40)  # 40%
        block_2_count = int(count * 0.25)  # 25%
        block_3_count = int(count * 0.20)  # 20%
        block_4_count = count - block_1_count - block_2_count - block_3_count  # Remainder
        
        logger.info(
            f"Generating {count} synthetic payments: "
            f"BLOCK_1={block_1_count}, BLOCK_2={block_2_count}, "
            f"BLOCK_3={block_3_count}, BLOCK_4={block_4_count}"
        )
        
        # Generate BLOCK_1 payments (network errors)
        for i in range(block_1_count):
            payment = self._generate_payment(
                index=i,
                error_category="BLOCK_1"
            )
            payments.append(payment)
        
        # Generate BLOCK_2 payments (liquidity)
        for i in range(block_2_count):
            payment = self._generate_payment(
                index=block_1_count + i,
                error_category="BLOCK_2"
            )
            payments.append(payment)
        
        # Generate BLOCK_3 payments (dead instruments)
        for i in range(block_3_count):
            payment = self._generate_payment(
                index=block_1_count + block_2_count + i,
                error_category="BLOCK_3"
            )
            payments.append(payment)
        
        # Generate BLOCK_4 payments (others)
        for i in range(block_4_count):
            payment = self._generate_payment(
                index=block_1_count + block_2_count + block_3_count + i,
                error_category="BLOCK_4"
            )
            payments.append(payment)
        
        logger.info(f"✓ Generated {len(payments)} synthetic payments")
        
        return payments
    
    def _generate_payment(
        self,
        index: int,
        error_category: str
    ) -> SyntheticPayment:
        """
        Generate single synthetic payment.
        
        Args:
            index: Payment index in batch
            error_category: Error category (BLOCK_1, 2, 3, or 4)
            
        Returns:
            SyntheticPayment object
        """
        # Customer details
        customer_id = f"cust_{index+1:04d}"
        first_name = random.choice(self.FIRST_NAMES)
        last_name = random.choice(self.LAST_NAMES)
        customer_name = f"{first_name} {last_name}"
        customer_email = f"{first_name.lower()}.{last_name.lower()}@example.com"
        customer_phone = f"98{random.randint(10000000, 99999999)}"
        
        # Determine segment (80% Tier 1, 20% Tier 2)
        segment = (
            CustomerSegment.TIER_2
            if random.random() < 0.20
            else CustomerSegment.TIER_1
        )
        
        # Amount (weighted towards smaller amounts)
        amount_range = random.choices(
            self.AMOUNT_RANGES,
            weights=[50, 30, 15, 5],  # Bias towards smaller amounts
            k=1
        )[0]
        amount_rupees = random.randint(*amount_range)
        amount_paise = amount_rupees * 100
        
        # Payment method (70% card, 20% UPI, 10% others)
        method = random.choices(
            [PaymentMethod.CARD, PaymentMethod.UPI, PaymentMethod.NETBANKING],
            weights=[70, 20, 10],
            k=1
        )[0]
        
        # Select error code based on category
        if error_category == "BLOCK_1":
            error_code = random.choice(self.BLOCK_1_ERRORS)
        elif error_category == "BLOCK_2":
            error_code = random.choice(self.BLOCK_2_ERRORS)
        elif error_category == "BLOCK_3":
            error_code = random.choice(self.BLOCK_3_ERRORS)
        else:  # BLOCK_4
            # Mix of all error codes
            all_errors = (
                self.BLOCK_1_ERRORS +
                self.BLOCK_2_ERRORS +
                self.BLOCK_3_ERRORS
            )
            error_code = random.choice(all_errors)
        
        # Invoice details
        invoice_id = f"inv_{index+1:04d}"
        subscription_id = f"sub_{(index//5)+1:03d}"  # Group into subscription batches
        
        # Timestamp (distributed over past 24 hours)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        timestamp = (
            datetime.utcnow() - timedelta(hours=hours_ago, minutes=minutes_ago)
        ).isoformat()
        
        return SyntheticPayment(
            invoice_id=invoice_id,
            customer_id=customer_id,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_phone=customer_phone,
            customer_segment=segment,
            amount_paise=amount_paise,
            payment_method=method,
            error_code=error_code,
            timestamp=timestamp,
            subscription_id=subscription_id,
            block_category=error_category,  
        )
    
    # NOTE: The old generate_recovery_outcomes() method used to live here.
    # It pre-decided a fixed win/loss count per block (e.g. "19 of 20
    # BLOCK_1 payments succeed") instead of actually running payments
    # through the recovery engine. Real outcomes now come from
    # Day4_engine_runner.EngineRunner, which sends each payment through
    # the actual Day1_diagnostic + Day2_statemachine code path.


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Synthetic Data Generator - Day 4")
    print("="*80 + "\n")
    
    # Initialize generator
    generator = SyntheticDataGenerator(seed=42)
    
    # Generate 50-transaction batch
    payments = generator.generate_batch(count=50)
    
    print(f"Generated {len(payments)} synthetic payments\n")
    
    # Show sample
    print("Sample Transactions:")
    print("-" * 80)
    for payment in payments[:5]:
        print(
            f"  {payment.invoice_id}: "
            f"₹{payment.amount_paise/100:.0f} | "
            f"{payment.payment_method.value} | "
            f"{payment.error_code.value} | "
            f"{payment.customer_segment.value}"
        )
    print(f"  ... ({len(payments) - 5} more)\n")
    
    # Simulate recovery
    outcomes = generator.generate_recovery_outcomes(payments)
    
    print("Simulated Recovery Results:")
    print("-" * 80)
    print(f"  Total Invoices:       {outcomes['total']}")
    print(f"  Total Amount:         ₹{outcomes['total_amount_paise']/100:.0f}")
    print(f"  Recovered:            {len(outcomes['recovered'])}")
    print(f"  Recovered Amount:     ₹{outcomes['recovered_amount_paise']/100:.0f}")
    print(f"  Recovery Rate:        {len(outcomes['recovered'])/outcomes['total']:.1%}")
    print(f"  Failed:               {len(outcomes['failed'])}")
    print(f"  Paused:               {len(outcomes['paused'])}\n")
    
    print("Recovery by Block:")
    print("-" * 80)
    for block_name, block_data in outcomes["by_block"].items():
        print(
            f"  {block_name}: "
            f"{block_data['total']} total, "
            f"{block_data['recovered']} recovered, "
            f"{block_data['rate']:.1%} rate"
        )
    
    print("\n" + "="*80 + "\n")
