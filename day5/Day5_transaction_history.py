"""
RecovAI: Transaction History Viewer
Day 5: Display detailed transaction recovery information
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TransactionRecord:
    """Single transaction record"""
    invoice_id: str
    customer_id: str
    customer_name: str
    amount_rupees: float
    error_code: str
    recovery_block: str
    recovery_status: str  # recovered, failed, paused
    timestamp: str
    latency_ms: int
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return {
            "invoice_id": self.invoice_id,
            "customer_id": self.customer_id,
            "customer_name": self.customer_name,
            "amount": self.amount_rupees,
            "error": self.error_code,
            "block": self.recovery_block,
            "status": self.recovery_status,
            "timestamp": self.timestamp,
            "latency_ms": self.latency_ms,
        }


class TransactionHistoryViewer:
    """View transaction history with filtering and sorting"""
    
    def __init__(self):
        """Initialize viewer"""
        self.transactions: List[TransactionRecord] = []
        logger.info("✓ TransactionHistoryViewer initialized")
    
    def add_transaction(self, record: TransactionRecord):
        """Add transaction record"""
        self.transactions.append(record)
    
    def add_batch(self, records: List[TransactionRecord]):
        """Add batch of transactions"""
        self.transactions.extend(records)
        logger.info(f"✓ Added {len(records)} transactions to history")
    
    def filter_by_status(self, status: str) -> List[TransactionRecord]:
        """Filter by recovery status"""
        return [t for t in self.transactions if t.recovery_status == status]
    
    def filter_by_block(self, block: str) -> List[TransactionRecord]:
        """Filter by recovery block"""
        return [t for t in self.transactions if t.recovery_block == block]
    
    def sort_by_amount(self, descending: bool = True) -> List[TransactionRecord]:
        """Sort by amount"""
        return sorted(self.transactions, key=lambda t: t.amount_rupees, reverse=descending)
    
    def get_top_recovered(self, count: int = 10) -> List[TransactionRecord]:
        """Get top recovered transactions by amount"""
        recovered = self.filter_by_status("recovered")
        return self.sort_by_amount(descending=True)[:count]
    
    def get_failed_transactions(self) -> List[TransactionRecord]:
        """Get all failed transactions"""
        return self.filter_by_status("failed")
    
    def print_transaction_history(self, records: List[TransactionRecord] = None, limit: int = 20):
        """Print formatted transaction history"""
        if records is None:
            records = self.transactions
        
        if not records:
            print("No transactions found")
            return
        
        print("\n" + "="*120)
        print("  TRANSACTION HISTORY")
        print("="*120 + "\n")
        
        print(f"{'Invoice':<12} {'Customer':<20} {'Amount':>10} {'Block':<10} {'Status':<12} {'Error':<20} {'Latency':<10}")
        print("─"*120)
        
        for transaction in records[:limit]:
            status_icon = {
                "recovered": "✓",
                "failed": "✗",
                "paused": "⏸",
            }.get(transaction.recovery_status, "?")
            
            print(
                f"{transaction.invoice_id:<12} "
                f"{transaction.customer_name:<20} "
                f"₹{transaction.amount_rupees:>8,.0f} "
                f"{transaction.recovery_block:<10} "
                f"{status_icon} {transaction.recovery_status:<10} "
                f"{transaction.error_code:<20} "
                f"{transaction.latency_ms:>7}ms"
            )
        
        if len(records) > limit:
            print(f"\n... and {len(records) - limit} more transactions")
        
        print("\n" + "="*120 + "\n")
    
    def print_summary(self):
        """Print transaction summary"""
        if not self.transactions:
            print("No transactions in history")
            return
        
        recovered = self.filter_by_status("recovered")
        failed = self.filter_by_status("failed")
        paused = self.filter_by_status("paused")
        
        total_amount = sum(t.amount_rupees for t in self.transactions)
        recovered_amount = sum(t.amount_rupees for t in recovered)
        
        print("\n" + "="*80)
        print("  TRANSACTION SUMMARY")
        print("="*80 + "\n")
        
        print(f"Total Transactions:    {len(self.transactions)}")
        print(f"  ✓ Recovered:         {len(recovered)} ({len(recovered)/len(self.transactions):.1%})")
        print(f"  ✗ Failed:            {len(failed)} ({len(failed)/len(self.transactions):.1%})")
        print(f"  ⏸ Paused:            {len(paused)} ({len(paused)/len(self.transactions):.1%})")
        
        print(f"\nTotal Amount:          ₹{total_amount:>12,.0f}")
        print(f"Recovered Amount:      ₹{recovered_amount:>12,.0f} ({recovered_amount/total_amount:.1%})")
        
        # Average latency
        if self.transactions:
            avg_latency = sum(t.latency_ms for t in self.transactions) / len(self.transactions)
            print(f"Avg Latency:           {avg_latency:>12.0f}ms")
        
        # Top recovered customers
        print("\nTop Recovered Invoices:")
        print("─" * 80)
        for i, record in enumerate(self.get_top_recovered(5), 1):
            print(f"  {i}. {record.invoice_id}: ₹{record.amount_rupees:,.0f} ({record.recovery_block})")
        
        print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    print("\n" + "="*80)
    print("RecovAI Transaction History Viewer - Day 5")
    print("="*80 + "\n")
    
    # Create viewer
    viewer = TransactionHistoryViewer()
    
    # Add sample transactions
    sample_transactions = [
        TransactionRecord(
            invoice_id="inv_0001",
            customer_id="cust_001",
            customer_name="Rajesh Kumar",
            amount_rupees=5000,
            error_code="GATEWAY_TIMEOUT",
            recovery_block="BLOCK_1",
            recovery_status="recovered",
            timestamp="2026-09-01T10:30:00",
            latency_ms=145,
        ),
        TransactionRecord(
            invoice_id="inv_0002",
            customer_id="cust_002",
            customer_name="Priya Singh",
            amount_rupees=2500,
            error_code="INSUFFICIENT_FUNDS",
            recovery_block="BLOCK_2",
            recovery_status="recovered",
            timestamp="2026-09-01T10:31:00",
            latency_ms=1200,
        ),
        TransactionRecord(
            invoice_id="inv_0003",
            customer_id="cust_003",
            customer_name="Arjun Patel",
            amount_rupees=1500,
            error_code="CARD_EXPIRED",
            recovery_block="BLOCK_3",
            recovery_status="failed",
            timestamp="2026-09-01T10:32:00",
            latency_ms=50,
        ),
        TransactionRecord(
            invoice_id="inv_0004",
            customer_id="cust_004",
            customer_name="Divya Sharma",
            amount_rupees=3000,
            error_code="NETWORK_ERROR",
            recovery_block="BLOCK_1",
            recovery_status="recovered",
            timestamp="2026-09-01T10:33:00",
            latency_ms=160,
        ),
        TransactionRecord(
            invoice_id="inv_0005",
            customer_id="cust_005",
            customer_name="Vikram Desai",
            amount_rupees=2000,
            error_code="LOW_BALANCE",
            recovery_block="BLOCK_2",
            recovery_status="paused",
            timestamp="2026-09-01T10:34:00",
            latency_ms=2000,
        ),
    ]
    
    viewer.add_batch(sample_transactions)
    
    # Print history
    viewer.print_transaction_history()
    
    # Print summary
    viewer.print_summary()
    
    # Filter by status
    print("Recovered Transactions Only:")
    print("─" * 80)
    recovered = viewer.filter_by_status("recovered")
    viewer.print_transaction_history(recovered)
    
    print("✓ Transaction history viewer working!")
