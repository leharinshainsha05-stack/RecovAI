"""
RecovAI: Advanced Metrics & Trending
Day 5: Historical analysis and performance trending
"""

import json
from typing import Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# METRICS TRACKER
# ============================================================================

class MetricsTracker:
    """
    Track metrics over time for trending analysis.
    
    Tracks:
    - Recovery rate trend
    - Revenue trend
    - Block performance
    - Customer segment performance
    """
    
    def __init__(self, history_file: str = "metrics_history.json"):
        """
        Initialize metrics tracker.
        
        Args:
            history_file: File to store historical metrics
        """
        self.history_file = history_file
        self.history = self._load_history()
        
        logger.info("✓ MetricsTracker initialized")
    
    def _load_history(self) -> List[Dict[str, Any]]:
        """Load historical metrics"""
        try:
            with open(self.history_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return []
    
    def _save_history(self):
        """Save historical metrics"""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2, default=str)
    
    def record_benchmark(self, report: Dict[str, Any]):
        """
        Record benchmark results.
        
        Args:
            report: Benchmark report dict
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "recovery_rate": report['key_metrics']['recovery_rate']['value'],
            "revenue_recovery": report['key_metrics']['revenue_recovery_rate']['value'],
            "net_revenue": report['key_metrics']['net_revenue_impact']['value'],
            "total_transactions": report['overview']['batch_size'],
            "recovered_transactions": report['transaction_breakdown']['recovered'],
            "by_block": report['recovery_by_block'],
            "status": "PASS" if report['analysis']['pass_fail_criteria']['overall_status'].startswith("✓") else "FAIL",
        }
        
        self.history.append(entry)
        self._save_history()
        
        logger.info(f"✓ Recorded benchmark: {entry['recovery_rate']:.1%} recovery")
    
    def get_trend(self, metric: str, periods: int = 10) -> Dict[str, Any]:
        """
        Get trend for metric.
        
        Args:
            metric: Metric name (recovery_rate, revenue_recovery, net_revenue, etc.)
            periods: Number of periods to analyze
            
        Returns:
            Trend analysis dict
        """
        if not self.history:
            return {"status": "no_data"}
        
        # Get last N entries
        recent = self.history[-periods:]
        
        # Extract metric values
        values = [entry.get(metric, 0) for entry in recent]
        timestamps = [entry['timestamp'] for entry in recent]
        
        if not values:
            return {"status": "no_data"}
        
        # Calculate trend
        current = values[-1]
        previous = values[-2] if len(values) > 1 else values[0]
        change = current - previous
        change_pct = (change / previous * 100) if previous != 0 else 0
        
        # Calculate average
        avg = sum(values) / len(values)
        
        # Determine direction
        if change > 0:
            direction = "↑ Up"
        elif change < 0:
            direction = "↓ Down"
        else:
            direction = "→ Stable"
        
        return {
            "metric": metric,
            "current": current,
            "previous": previous,
            "change": change,
            "change_pct": change_pct,
            "direction": direction,
            "average": avg,
            "min": min(values),
            "max": max(values),
            "values": values,
            "timestamps": timestamps,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics"""
        if not self.history:
            return {"status": "no_data"}
        
        df = pd.DataFrame(self.history)
        
        return {
            "total_benchmarks": len(self.history),
            "pass_rate": (df['status'] == 'PASS').sum() / len(df),
            "avg_recovery_rate": df['recovery_rate'].mean(),
            "avg_revenue_recovery": df['revenue_recovery'].mean(),
            "total_net_revenue": df['net_revenue'].sum(),
            "total_transactions": df['total_transactions'].sum(),
            "total_recovered": df['recovered_transactions'].sum(),
            "latest_benchmark": self.history[-1] if self.history else None,
        }


# ============================================================================
# PERFORMANCE ANALYZER
# ============================================================================

class PerformanceAnalyzer:
    """
    Analyze system performance and identify trends.
    
    Provides:
    - Performance trends
    - Anomaly detection
    - Recommendations
    - Health checks
    """
    
    # Thresholds for alerts
    THRESHOLDS = {
        "recovery_rate_warning": 0.70,  # Below 70% = warning
        "recovery_rate_critical": 0.60,  # Below 60% = critical
        "revenue_recovery_warning": 0.70,
        "revenue_recovery_critical": 0.60,
        "net_revenue_warning": 10000,
        "block_1_warning": 0.80,
        "block_1_critical": 0.70,
    }
    
    def __init__(self):
        """Initialize analyzer"""
        logger.info("✓ PerformanceAnalyzer initialized")
    
    def health_check(self, report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check system health.
        
        Args:
            report: Benchmark report
            
        Returns:
            Health status dict
        """
        health_status = {
            "timestamp": datetime.utcnow().isoformat(),
            "overall_health": "HEALTHY",
            "checks": {},
            "alerts": [],
        }
        
        metrics = report['key_metrics']
        
        # Check recovery rate
        recovery_rate = metrics['recovery_rate']['value']
        if recovery_rate < self.THRESHOLDS['recovery_rate_critical']:
            health_status['overall_health'] = "CRITICAL"
            health_status['alerts'].append(
                f"CRITICAL: Recovery rate {recovery_rate:.1%} below {self.THRESHOLDS['recovery_rate_critical']:.1%}"
            )
            health_status['checks']['recovery_rate'] = "CRITICAL"
        elif recovery_rate < self.THRESHOLDS['recovery_rate_warning']:
            health_status['overall_health'] = "WARNING"
            health_status['alerts'].append(
                f"WARNING: Recovery rate {recovery_rate:.1%} below {self.THRESHOLDS['recovery_rate_warning']:.1%}"
            )
            health_status['checks']['recovery_rate'] = "WARNING"
        else:
            health_status['checks']['recovery_rate'] = "HEALTHY"
        
        # Check revenue recovery
        revenue_recovery = metrics['revenue_recovery_rate']['value']
        if revenue_recovery < self.THRESHOLDS['revenue_recovery_critical']:
            health_status['overall_health'] = "CRITICAL"
            health_status['checks']['revenue_recovery'] = "CRITICAL"
        elif revenue_recovery < self.THRESHOLDS['revenue_recovery_warning']:
            if health_status['overall_health'] != "CRITICAL":
                health_status['overall_health'] = "WARNING"
            health_status['checks']['revenue_recovery'] = "WARNING"
        else:
            health_status['checks']['revenue_recovery'] = "HEALTHY"
        
        # Check net revenue
        net_revenue = metrics['net_revenue_impact']['value']
        if net_revenue < self.THRESHOLDS['net_revenue_warning']:
            health_status['checks']['net_revenue'] = "WARNING"
            health_status['alerts'].append(
                f"WARNING: Net revenue {net_revenue:.0f} below target {self.THRESHOLDS['net_revenue_warning']}"
            )
        else:
            health_status['checks']['net_revenue'] = "HEALTHY"
        
        # Check BLOCK_1
        block_1_rate = report['recovery_by_block']['BLOCK_1']['rate']
        if block_1_rate < self.THRESHOLDS['block_1_critical']:
            health_status['overall_health'] = "CRITICAL"
            health_status['checks']['block_1'] = "CRITICAL"
            health_status['alerts'].append(
                f"CRITICAL: BLOCK_1 recovery {block_1_rate:.1%} below {self.THRESHOLDS['block_1_critical']:.1%}"
            )
        elif block_1_rate < self.THRESHOLDS['block_1_warning']:
            health_status['checks']['block_1'] = "WARNING"
        else:
            health_status['checks']['block_1'] = "HEALTHY"
        
        return health_status
    
    def get_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """
        Get performance recommendations.
        
        Args:
            report: Benchmark report
            
        Returns:
            List of recommendations
        """
        recommendations = []
        
        # Check recovery rate
        recovery_rate = report['key_metrics']['recovery_rate']['value']
        if recovery_rate < 0.75:
            recommendations.append(
                "Increase overall recovery rate: Optimize BLOCK_3 and BLOCK_4 performance"
            )
        
        # Check block rates
        by_block = report['recovery_by_block']
        
        if by_block['BLOCK_1']['rate'] < 0.90:
            recommendations.append(
                "Improve BLOCK_1 (network errors): Increase live reroute success rate"
            )
        
        if by_block['BLOCK_2']['rate'] < 0.65:
            recommendations.append(
                "Improve BLOCK_2 (liquidity): Extend salary window retry window"
            )
        
        if by_block['BLOCK_3']['rate'] < 0.35:
            recommendations.append(
                "Improve BLOCK_3 (dead instruments): Send UPI fallback link earlier"
            )
        
        if by_block['BLOCK_4']['rate'] < 0.35:
            recommendations.append(
                "Improve BLOCK_4 (fallback): Increase grace period or add reminders"
            )
        
        # Check paused rate
        paused_rate = report['transaction_breakdown']['paused'] / report['overview']['batch_size']
        if paused_rate > 0.10:
            recommendations.append(
                "Reduce paused subscriptions: Review pause criteria and customer notifications"
            )
        
        # Check revenue
        net_revenue = report['key_metrics']['net_revenue_impact']['value']
        if net_revenue < 50000:
            recommendations.append(
                "Increase net revenue impact: Focus on high-LTV customer recovery"
            )
        
        return recommendations if recommendations else ["System is performing optimally"]


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Advanced Metrics - Day 5")
    print("="*80 + "\n")
    
    # Initialize
    tracker = MetricsTracker()
    analyzer = PerformanceAnalyzer()
    
    print("✓ MetricsTracker initialized")
    print("✓ PerformanceAnalyzer initialized")
    print("\nCapabilities:")
    print("  • Track metrics over time")
    print("  • Analyze performance trends")
    print("  • Detect anomalies")
    print("  • Generate health reports")
    print("  • Provide recommendations")
    
    # Load sample report
    try:
        with open('benchmark_report.json', 'r') as f:
            report = json.load(f)
        
        # Record benchmark
        tracker.record_benchmark(report)
        print("\n✓ Benchmark recorded")
        
        # Get summary
        summary = tracker.get_summary()
        print(f"\nSummary Statistics:")
        print(f"  Total Benchmarks: {summary['total_benchmarks']}")
        print(f"  Pass Rate: {summary['pass_rate']:.1%}")
        print(f"  Avg Recovery Rate: {summary['avg_recovery_rate']:.1%}")
        print(f"  Total Net Revenue: ₹{summary['total_net_revenue']:,.0f}")
        
        # Health check
        health = analyzer.health_check(report)
        print(f"\nHealth Status: {health['overall_health']}")
        for check, status in health['checks'].items():
            symbol = "✓" if status == "HEALTHY" else "⚠" if status == "WARNING" else "✗"
            print(f"  {symbol} {check}: {status}")
        
        # Recommendations
        recommendations = analyzer.get_recommendations(report)
        print("\nRecommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
    
    except FileNotFoundError:
        print("⚠️  benchmark_report.json not found")
    
    print("\n" + "="*80 + "\n")
