"""
RecovAI: Real-Time Metrics Dashboard
Day 5: Live recovery metrics, trends, and performance monitoring
"""

import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class DashboardMetrics:
    """Real-time dashboard metrics"""
    timestamp: datetime
    total_invoices: int = 0
    recovered_invoices: int = 0
    failed_invoices: int = 0
    paused_invoices: int = 0
    total_amount_rupees: float = 0.0
    recovered_amount_rupees: float = 0.0
    recovery_rate: float = 0.0
    revenue_recovery_rate: float = 0.0
    block_1_rate: float = 0.0
    block_2_rate: float = 0.0
    block_3_rate: float = 0.0
    block_4_rate: float = 0.0
    avg_gateway_latency_ms: float = 0.0
    gateway_success_rate: float = 0.0
    notifications_sent: int = 0
    notifications_delivered: int = 0
    notification_delivery_rate: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "transactions": {
                "total": self.total_invoices,
                "recovered": self.recovered_invoices,
                "failed": self.failed_invoices,
                "paused": self.paused_invoices,
            },
            "revenue": {
                "total": self.total_amount_rupees,
                "recovered": self.recovered_amount_rupees,
                "recovery_rate": self.revenue_recovery_rate,
            },
            "rates": {
                "recovery_rate": self.recovery_rate,
                "block_1": self.block_1_rate,
                "block_2": self.block_2_rate,
                "block_3": self.block_3_rate,
                "block_4": self.block_4_rate,
            },
            "gateway": {
                "avg_latency_ms": self.avg_gateway_latency_ms,
                "success_rate": self.gateway_success_rate,
            },
            "notifications": {
                "sent": self.notifications_sent,
                "delivered": self.notifications_delivered,
                "delivery_rate": self.notification_delivery_rate,
            }
        }


class MetricsCollector:
    """Collect and aggregate real-time metrics"""
    
    MAX_HISTORY_POINTS = 1440  # 24 hours
    
    def __init__(self):
        """Initialize metrics collector"""
        self.current_metrics = DashboardMetrics(timestamp=datetime.utcnow())
        self.history: deque = deque(maxlen=self.MAX_HISTORY_POINTS)
        logger.info("✓ MetricsCollector initialized")
    
    def update_transaction_metrics(self, total: int, recovered: int, failed: int, paused: int):
        """Update transaction metrics"""
        self.current_metrics.total_invoices = total
        self.current_metrics.recovered_invoices = recovered
        self.current_metrics.failed_invoices = failed
        self.current_metrics.paused_invoices = paused
        if total > 0:
            self.current_metrics.recovery_rate = recovered / total
    
    def update_revenue_metrics(self, total_amount: float, recovered_amount: float):
        """Update revenue metrics"""
        self.current_metrics.total_amount_rupees = total_amount
        self.current_metrics.recovered_amount_rupees = recovered_amount
        if total_amount > 0:
            self.current_metrics.revenue_recovery_rate = recovered_amount / total_amount
    
    def update_block_metrics(self, b1: float, b2: float, b3: float, b4: float):
        """Update block rates"""
        self.current_metrics.block_1_rate = b1
        self.current_metrics.block_2_rate = b2
        self.current_metrics.block_3_rate = b3
        self.current_metrics.block_4_rate = b4
    
    def update_gateway_metrics(self, latency_ms: float, success_rate: float):
        """Update gateway metrics"""
        self.current_metrics.avg_gateway_latency_ms = latency_ms
        self.current_metrics.gateway_success_rate = success_rate
    
    def update_notification_metrics(self, sent: int, delivered: int):
        """Update notification metrics"""
        self.current_metrics.notifications_sent = sent
        self.current_metrics.notifications_delivered = delivered
        if sent > 0:
            self.current_metrics.notification_delivery_rate = delivered / sent
    
    def snapshot(self) -> DashboardMetrics:
        """Get current metrics snapshot"""
        self.current_metrics.timestamp = datetime.utcnow()
        self.history.append(self.current_metrics.to_dict())
        return self.current_metrics


class DashboardRenderer:
    """Render real-time metrics dashboard"""
    
    @staticmethod
    def render_console(metrics: DashboardMetrics):
        """Render dashboard to console"""
        print("\n" + "="*80)
        print("  RecovAI LIVE DASHBOARD - Real-Time Metrics")
        print("="*80 + "\n")
        print(f"Last Updated: {metrics.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC\n")
        
        # Transaction metrics
        print("┌" + "─"*78 + "┐")
        print("│ TRANSACTION METRICS" + " "*59 + "│")
        print("├" + "─"*78 + "┤")
        print(f"│  Total:        {metrics.total_invoices:>4} invoices" + " "*51 + "│")
        bar = "█" * int(metrics.recovery_rate * 20)
        print(f"│  ✓ Recovered:  {metrics.recovered_invoices:>4} ({metrics.recovery_rate:>6.1%}) {bar:<20}  │")
        print(f"│  ✗ Failed:     {metrics.failed_invoices:>4}" + " "*62 + "│")
        print(f"│  ⏸ Paused:     {metrics.paused_invoices:>4}" + " "*62 + "│")
        print("└" + "─"*78 + "┘\n")
        
        # Revenue metrics
        print("┌" + "─"*78 + "┐")
        print("│ REVENUE METRICS" + " "*63 + "│")
        print("├" + "─"*78 + "┤")
        print(f"│  Total:        ₹{metrics.total_amount_rupees:>12,.0f}" + " "*50 + "│")
        print(f"│  ✓ Recovered:  ₹{metrics.recovered_amount_rupees:>12,.0f} ({metrics.revenue_recovery_rate:>6.1%})" + " "*30 + "│")
        print("└" + "─"*78 + "┘\n")
        
        # Block rates
        print("┌" + "─"*78 + "┐")
        print("│ RECOVERY RATES BY BLOCK" + " "*54 + "│")
        print("├" + "─"*78 + "┤")
        blocks = [("BLOCK_1", metrics.block_1_rate, 0.80),
                  ("BLOCK_2", metrics.block_2_rate, 0.60),
                  ("BLOCK_3", metrics.block_3_rate, 0.25),
                  ("BLOCK_4", metrics.block_4_rate, 0.30)]
        for name, rate, target in blocks:
            status = "✓" if rate >= target else "⚠"
            bar = "█" * int(rate * 20) + "░" * (20 - int(rate * 20))
            print(f"│  {status} {name:10} {rate:>6.1%} (target: {target:>5.1%}) [{bar}] │")
        print("└" + "─"*78 + "┘\n")
        
        # Gateway metrics
        print("┌" + "─"*78 + "┐")
        print("│ GATEWAY PERFORMANCE" + " "*59 + "│")
        print("├" + "─"*78 + "┤")
        print(f"│  Avg Latency:  {metrics.avg_gateway_latency_ms:>6.0f} ms (Budget: 200ms)" + " "*37 + "│")
        bar = "█" * int(metrics.gateway_success_rate * 20)
        print(f"│  Success Rate: {metrics.gateway_success_rate:>6.1%} {bar:<20}  │")
        print("└" + "─"*78 + "┘\n")
        
        # Notification metrics
        print("┌" + "─"*78 + "┐")
        print("│ NOTIFICATION DELIVERY" + " "*56 + "│")
        print("├" + "─"*78 + "┤")
        print(f"│  Sent:         {metrics.notifications_sent:>6} messages" + " "*57 + "│")
        print(f"│  Delivered:    {metrics.notifications_delivered:>6} ({metrics.notification_delivery_rate:>6.1%})" + " "*48 + "│")
        print("└" + "─"*78 + "┘\n")
        
        # Health status
        status = DashboardRenderer._get_health_status(metrics)
        print("┌" + "─"*78 + "┐")
        print("│ SYSTEM HEALTH" + " "*64 + "│")
        print("├" + "─"*78 + "┤")
        print(f"│  Status: {status['status']} {status['message']:<60}  │")
        print("└" + "─"*78 + "┘\n")
        print("="*80 + "\n")
    
    @staticmethod
    def _get_health_status(metrics: DashboardMetrics) -> Dict[str, str]:
        """Get health status"""
        if (metrics.recovery_rate >= 0.70 and 
            metrics.revenue_recovery_rate >= 0.70 and
            metrics.block_1_rate >= 0.80):
            return {"status": "🟢", "message": "Healthy - All targets met"}
        elif (metrics.recovery_rate >= 0.60):
            return {"status": "🟡", "message": "Degraded - Some targets below"}
        else:
            return {"status": "🔴", "message": "Critical - Multiple issues"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    collector = MetricsCollector()
    collector.update_transaction_metrics(50, 37, 9, 4)
    collector.update_revenue_metrics(80351, 64229)
    collector.update_block_metrics(0.95, 0.833, 0.40, 0.50)
    collector.update_gateway_metrics(145, 0.98)
    collector.update_notification_metrics(50, 49)
    
    metrics = collector.snapshot()
    DashboardRenderer.render_console(metrics)
    print("✓ Dashboard rendered successfully!")
