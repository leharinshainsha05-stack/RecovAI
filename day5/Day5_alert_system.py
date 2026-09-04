"""
RecovAI: Alert System
Day 5: Monitor performance thresholds and generate alerts
"""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "ℹ️  INFO"
    WARNING = "⚠️  WARNING"
    CRITICAL = "🚨 CRITICAL"


@dataclass
class Alert:
    """Alert event"""
    timestamp: datetime
    severity: AlertSeverity
    title: str
    message: str
    metric: str
    threshold: float
    current_value: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "title": self.title,
            "message": self.message,
            "metric": self.metric,
            "threshold": self.threshold,
            "current_value": self.current_value,
        }


class AlertManager:
    """Manage performance alerts and thresholds"""
    
    # Alert thresholds
    THRESHOLDS = {
        "recovery_rate": 0.70,           # 70%
        "revenue_recovery": 0.70,        # 70%
        "block_1_rate": 0.80,           # 80%
        "block_2_rate": 0.60,           # 60%
        "block_3_rate": 0.25,           # 25%
        "block_4_rate": 0.30,           # 30%
        "gateway_latency_ms": 200,      # 200ms
        "gateway_success": 0.95,        # 95%
        "notification_delivery": 0.95,  # 95%
    }
    
    def __init__(self):
        """Initialize alert manager"""
        self.alerts: List[Alert] = []
        self.alert_count = {
            AlertSeverity.INFO: 0,
            AlertSeverity.WARNING: 0,
            AlertSeverity.CRITICAL: 0,
        }
        logger.info("✓ AlertManager initialized")
    
    def check_recovery_rate(self, current: float) -> List[Alert]:
        """Check recovery rate threshold"""
        alerts = []
        threshold = self.THRESHOLDS["recovery_rate"]
        
        if current < threshold * 0.9:  # Critical if 10% below
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.CRITICAL,
                title="Recovery Rate Critical",
                message=f"Recovery rate dropped to {current:.1%}, target is {threshold:.1%}",
                metric="recovery_rate",
                threshold=threshold,
                current_value=current,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.CRITICAL] += 1
        elif current < threshold:  # Warning if below
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.WARNING,
                title="Recovery Rate Below Target",
                message=f"Recovery rate is {current:.1%}, target is {threshold:.1%}",
                metric="recovery_rate",
                threshold=threshold,
                current_value=current,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.WARNING] += 1
        else:
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.INFO,
                title="Recovery Rate Healthy",
                message=f"Recovery rate is {current:.1%}, on target",
                metric="recovery_rate",
                threshold=threshold,
                current_value=current,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.INFO] += 1
        
        self.alerts.extend(alerts)
        return alerts
    
    def check_gateway_latency(self, current_ms: float) -> List[Alert]:
        """Check gateway latency"""
        alerts = []
        threshold = self.THRESHOLDS["gateway_latency_ms"]
        
        if current_ms > threshold:
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.WARNING,
                title="Gateway Latency High",
                message=f"Latency is {current_ms:.0f}ms, budget is {threshold:.0f}ms",
                metric="gateway_latency",
                threshold=threshold,
                current_value=current_ms,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.WARNING] += 1
        
        self.alerts.extend(alerts)
        return alerts
    
    def check_notification_delivery(self, delivery_rate: float) -> List[Alert]:
        """Check notification delivery rate"""
        alerts = []
        threshold = self.THRESHOLDS["notification_delivery"]
        
        if delivery_rate < threshold * 0.9:  # Critical
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.CRITICAL,
                title="Notification Delivery Critical",
                message=f"Delivery rate is {delivery_rate:.1%}, target is {threshold:.1%}",
                metric="notification_delivery",
                threshold=threshold,
                current_value=delivery_rate,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.CRITICAL] += 1
        elif delivery_rate < threshold:  # Warning
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.WARNING,
                title="Notification Delivery Low",
                message=f"Delivery rate is {delivery_rate:.1%}, target is {threshold:.1%}",
                metric="notification_delivery",
                threshold=threshold,
                current_value=delivery_rate,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.WARNING] += 1
        
        self.alerts.extend(alerts)
        return alerts
    
    def check_block_rate(self, block: str, current: float) -> List[Alert]:
        """Check block recovery rate"""
        alerts = []
        threshold_key = f"{block.lower()}_rate"
        threshold = self.THRESHOLDS.get(threshold_key, 0.5)
        
        if current < threshold:
            alert = Alert(
                timestamp=datetime.utcnow(),
                severity=AlertSeverity.WARNING,
                title=f"{block} Recovery Below Target",
                message=f"{block} recovery is {current:.1%}, target is {threshold:.1%}",
                metric=f"{block}_rate",
                threshold=threshold,
                current_value=current,
            )
            alerts.append(alert)
            self.alert_count[AlertSeverity.WARNING] += 1
        
        self.alerts.extend(alerts)
        return alerts
    
    def print_alerts(self, severity: AlertSeverity = None):
        """Print alerts"""
        if severity:
            alerts = [a for a in self.alerts if a.severity == severity]
        else:
            alerts = self.alerts
        
        if not alerts:
            print("No alerts")
            return
        
        print("\n" + "="*80)
        print("  ALERTS")
        print("="*80 + "\n")
        
        for alert in alerts[-10:]:  # Last 10 alerts
            print(f"{alert.severity} {alert.title}")
            print(f"   {alert.message}")
            print(f"   Metric: {alert.metric} | Current: {alert.current_value:.2f} | Threshold: {alert.threshold:.2f}")
            print()
        
        print("="*80 + "\n")
    
    def print_alert_summary(self):
        """Print alert summary"""
        print("\n" + "="*80)
        print("  ALERT SUMMARY")
        print("="*80 + "\n")
        
        print(f"ℹ️  INFO:              {self.alert_count[AlertSeverity.INFO]}")
        print(f"⚠️  WARNING:           {self.alert_count[AlertSeverity.WARNING]}")
        print(f"🚨 CRITICAL:          {self.alert_count[AlertSeverity.CRITICAL]}")
        print(f"\nTotal Alerts:         {sum(self.alert_count.values())}")
        
        print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    print("\n" + "="*80)
    print("RecovAI Alert System - Day 5")
    print("="*80 + "\n")
    
    # Create alert manager
    manager = AlertManager()
    
    # Check various metrics
    manager.check_recovery_rate(0.74)  # OK
    manager.check_recovery_rate(0.65)  # WARNING
    manager.check_recovery_rate(0.50)  # CRITICAL
    
    manager.check_gateway_latency(145)  # OK
    manager.check_gateway_latency(210)  # WARNING
    
    manager.check_notification_delivery(0.98)  # OK
    manager.check_notification_delivery(0.90)  # WARNING
    
    manager.check_block_rate("BLOCK_1", 0.95)  # OK
    manager.check_block_rate("BLOCK_3", 0.20)  # WARNING
    
    # Print alerts
    manager.print_alerts()
    manager.print_alert_summary()
    
    print("✓ Alert system working!")
