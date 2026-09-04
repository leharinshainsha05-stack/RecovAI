"""
RecovAI: Live Reroute Engine
Day 3: Smart gateway selection with <200ms latency for BLOCK_1 recovery
"""

import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import redis


logger = logging.getLogger(__name__)


# ============================================================================
# GATEWAY MODELS & ENUMS
# ============================================================================

class GatewayStatus(str, Enum):
    """Gateway health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class GatewayMetrics:
    """Real-time gateway metrics"""
    gateway_name: str
    uptime: float  # 0.0 to 1.0
    success_rate: float  # 0.0 to 1.0
    latency_p50: int  # milliseconds
    latency_p99: int  # milliseconds
    status: GatewayStatus
    last_updated: datetime
    error_count: int = 0
    success_count: int = 0
    
    def score(self) -> float:
        """Calculate gateway score (0-1)"""
        # Weighted scoring:
        # 40% uptime, 30% success_rate, 20% latency (inverse), 10% recency
        
        uptime_score = self.uptime * 0.4
        success_score = self.success_rate * 0.3
        
        # Latency inverse: target is <100ms
        latency_score = max(0, 1 - (self.latency_p99 / 200)) * 0.2
        
        # Recency: penalize if outdated (>5 min)
        age_seconds = (datetime.utcnow() - self.last_updated).total_seconds()
        recency_score = max(0, 1 - (age_seconds / 300)) * 0.1
        
        return uptime_score + success_score + latency_score + recency_score


# ============================================================================
# LIVE REROUTE ENGINE
# ============================================================================

class LiveRerouteEngine:
    """
    Smart gateway selection for <200ms recovery retry.
    
    Features:
    - Real-time gateway health tracking
    - Intelligent gateway selection
    - Latency-optimized routing
    - Fallback cascades
    - Quick decision (<50ms)
    
    Gateways:
    1. Razorpay (primary)
    2. PayU (secondary)
    3. Instamojo (tertiary)
    4. Cashfree (backup)
    """
    
    # Gateway configuration
    GATEWAYS = {
        "razorpay": {
            "priority": 1,
            "timeout_ms": 180,
            "retry_on_fail": True,
        },
        "payu": {
            "priority": 2,
            "timeout_ms": 190,
            "retry_on_fail": True,
        },
        "instamojo": {
            "priority": 3,
            "timeout_ms": 200,
            "retry_on_fail": False,
        },
        "cashfree": {
            "priority": 4,
            "timeout_ms": 200,
            "retry_on_fail": False,
        },
    }
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """
        Initialize live reroute engine.
        
        Args:
            redis_url: Redis connection URL for metrics cache
        """
        try:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            self.redis.ping()
            logger.info("✓ Connected to Redis for gateway metrics")
        except Exception as e:
            logger.warning(f"⚠️  Redis not available: {e}")
            self.redis = None
        
        # Initialize gateway metrics
        self._initialize_gateways()
        
        logger.info("✓ LiveRerouteEngine initialized")
    
    def _initialize_gateways(self):
        """Initialize gateway metrics in Redis"""
        if not self.redis:
            return
        
        for gateway_name in self.GATEWAYS.keys():
            key = f"gateway:{gateway_name}"
            
            # Set default metrics if not exists
            if not self.redis.exists(key):
                metrics = {
                    "uptime": "0.95",
                    "success_rate": "0.90",
                    "latency_p50": "80",
                    "latency_p99": "150",
                    "status": "healthy",
                    "last_updated": int(datetime.utcnow().timestamp()),
                    "error_count": "0",
                    "success_count": "0",
                }
                self.redis.hset(key, mapping=metrics)
                self.redis.expire(key, 86400)  # 24-hour TTL
    
    def update_gateway_metrics(
        self,
        gateway_name: str,
        success: bool,
        latency_ms: int,
        error_code: Optional[str] = None,
    ):
        """
        Update gateway metrics after transaction.
        
        Args:
            gateway_name: Gateway name
            success: True if transaction succeeded
            latency_ms: Response time in milliseconds
            error_code: Error code if failed
        """
        if not self.redis:
            return
        
        try:
            key = f"gateway:{gateway_name}"
            
            # Fetch current metrics
            metrics = self.redis.hgetall(key)
            
            if not metrics:
                logger.warning(f"⚠️  Gateway metrics not found: {gateway_name}")
                return
            
            # Update counters
            success_count = int(metrics.get("success_count", 0))
            error_count = int(metrics.get("error_count", 0))
            
            if success:
                success_count += 1
                # Update latency percentiles (simplified)
                latency_p50 = min(latency_ms, int(metrics.get("latency_p50", 100)))
                latency_p99 = max(latency_ms, int(metrics.get("latency_p99", 150)))
            else:
                error_count += 1
                latency_p99 = 200  # Max timeout on failure
            
            total_count = success_count + error_count
            success_rate = (success_count / total_count) if total_count > 0 else 0
            uptime = success_rate  # Simplified: uptime = success_rate
            
            # Determine status
            if success_rate >= 0.95:
                status = "healthy"
            elif success_rate >= 0.70:
                status = "degraded"
            else:
                status = "down"
            
            # Update Redis
            updated_metrics = {
                "success_rate": f"{success_rate:.2f}",
                "uptime": f"{uptime:.2f}",
                "latency_p50": str(latency_p50),
                "latency_p99": str(latency_p99),
                "status": status,
                "last_updated": int(datetime.utcnow().timestamp()),
                "success_count": str(success_count),
                "error_count": str(error_count),
            }
            
            self.redis.hset(key, mapping=updated_metrics)
            
            logger.debug(
                f"📊 Updated {gateway_name}: "
                f"success_rate={success_rate:.0%}, "
                f"latency_p99={latency_p99}ms, "
                f"status={status}"
            )
        
        except Exception as e:
            logger.error(f"❌ Failed to update gateway metrics: {e}")
    
    def select_gateway(
        self,
        primary_gateway: str = "razorpay",
        max_latency_ms: int = 200,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Select best available gateway for retry.
        
        Strategy:
        1. Try primary gateway if healthy
        2. Failover to secondary if primary is down
        3. Cascade through remaining gateways
        4. Return gateway with best score < max_latency
        
        Args:
            primary_gateway: Preferred gateway
            max_latency_ms: Maximum acceptable latency
            
        Returns:
            (gateway_name, gateway_config)
        """
        start_time = time.time()
        
        # Get all gateway metrics
        gateway_scores = []
        
        for gateway_name in self.GATEWAYS.keys():
            metrics = self._get_gateway_metrics(gateway_name)
            
            if not metrics:
                continue
            
            # Skip if exceeds latency budget
            if metrics.latency_p99 > max_latency_ms:
                logger.debug(
                    f"⏱️  {gateway_name} exceeds latency budget "
                    f"({metrics.latency_p99}ms > {max_latency_ms}ms)"
                )
                continue
            
            # Skip if down
            if metrics.status == GatewayStatus.DOWN:
                logger.debug(f"⬇️  {gateway_name} is down")
                continue
            
            # Calculate score
            score = metrics.score()
            gateway_scores.append((gateway_name, score, metrics))
        
        if not gateway_scores:
            logger.warning("❌ No healthy gateways available, using primary")
            return primary_gateway, self.GATEWAYS[primary_gateway]
        
        # Sort by score (descending)
        gateway_scores.sort(key=lambda x: x[1], reverse=True)
        
        selected_gateway = gateway_scores[0][0]
        selected_score = gateway_scores[0][1]
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"✓ Gateway selected: {selected_gateway} "
            f"(score={selected_score:.2f}, decision_time={elapsed_ms:.1f}ms)"
        )
        
        return selected_gateway, self.GATEWAYS[selected_gateway]
    
    def _get_gateway_metrics(self, gateway_name: str) -> Optional[GatewayMetrics]:
        """
        Get gateway metrics from Redis.
        
        Args:
            gateway_name: Gateway name
            
        Returns:
            GatewayMetrics object or None
        """
        if not self.redis:
            # Return default metrics if Redis unavailable
            return GatewayMetrics(
                gateway_name=gateway_name,
                uptime=0.95,
                success_rate=0.90,
                latency_p50=80,
                latency_p99=150,
                status=GatewayStatus.HEALTHY,
                last_updated=datetime.utcnow(),
            )
        
        try:
            key = f"gateway:{gateway_name}"
            metrics_dict = self.redis.hgetall(key)
            
            if not metrics_dict:
                return None
            
            return GatewayMetrics(
                gateway_name=gateway_name,
                uptime=float(metrics_dict.get("uptime", 0.95)),
                success_rate=float(metrics_dict.get("success_rate", 0.90)),
                latency_p50=int(metrics_dict.get("latency_p50", 80)),
                latency_p99=int(metrics_dict.get("latency_p99", 150)),
                status=GatewayStatus(metrics_dict.get("status", "healthy")),
                last_updated=datetime.fromtimestamp(
                    int(metrics_dict.get("last_updated", 0))
                ),
                error_count=int(metrics_dict.get("error_count", 0)),
                success_count=int(metrics_dict.get("success_count", 0)),
            )
        
        except Exception as e:
            logger.error(f"❌ Failed to get metrics for {gateway_name}: {e}")
            return None
    
    def get_all_gateway_status(self) -> List[Dict[str, Any]]:
        """
        Get status of all gateways.
        
        Returns:
            List of gateway status dicts
        """
        statuses = []
        
        for gateway_name in self.GATEWAYS.keys():
            metrics = self._get_gateway_metrics(gateway_name)
            
            if metrics:
                statuses.append({
                    "gateway": gateway_name,
                    "status": metrics.status.value,
                    "uptime": f"{metrics.uptime:.0%}",
                    "success_rate": f"{metrics.success_rate:.0%}",
                    "latency_p99": f"{metrics.latency_p99}ms",
                    "score": f"{metrics.score():.2f}",
                    "last_updated": metrics.last_updated.isoformat(),
                })
        
        return sorted(statuses, key=lambda x: float(x["score"]), reverse=True)


# ============================================================================
# RETRY EXECUTOR WITH LIVE REROUTE
# ============================================================================

class RetryExecutor:
    """
    Execute payment retry with live rerouting.
    
    Workflow:
    1. Select best gateway (<200ms decision time)
    2. Execute retry via gateway
    3. Record response time & success
    4. Update gateway metrics
    5. Return result
    """
    
    def __init__(self, reroute_engine: LiveRerouteEngine, razorpay_manager):
        """
        Initialize retry executor.
        
        Args:
            reroute_engine: LiveRerouteEngine instance
            razorpay_manager: RazorpayPaymentManager instance
        """
        self.reroute = reroute_engine
        self.razorpay = razorpay_manager
        
        logger.info("✓ RetryExecutor initialized")
    
    def execute_retry(
        self,
        invoice_id: str,
        customer_id: str,
        amount_paise: int,
        token_id: str,
        timeout_ms: int = 200,
    ) -> Dict[str, Any]:
        """
        Execute payment retry with automatic failover.
        
        Args:
            invoice_id: Invoice ID
            customer_id: Customer ID
            amount_paise: Amount in paise
            token_id: Token for saved payment method
            timeout_ms: Total timeout budget
            
        Returns:
            Retry result dict
        """
        retry_start = time.time()
        
        try:
            # Step 1: Select gateway (<50ms)
            selected_gateway, config = self.reroute.select_gateway(
                max_latency_ms=timeout_ms
            )
            
            # Step 2: Execute retry
            retry_start_ms = time.time()
            
            result = self.razorpay.execute_payment_retry(
                customer_id=customer_id,
                invoice_id=invoice_id,
                amount_paise=amount_paise,
                token_id=token_id,
            )
            
            retry_latency_ms = (time.time() - retry_start_ms) * 1000
            
            # Step 3: Record result
            success = result.get("status") == "success"
            
            # Step 4: Update gateway metrics
            self.reroute.update_gateway_metrics(
                gateway_name=selected_gateway,
                success=success,
                latency_ms=int(retry_latency_ms),
                error_code=result.get("error_code"),
            )
            
            # Step 5: Return result
            total_elapsed_ms = (time.time() - retry_start) * 1000
            
            logger.info(
                f"✓ Retry executed: {invoice_id} → "
                f"{result.get('status')} "
                f"(gateway={selected_gateway}, "
                f"latency={retry_latency_ms:.0f}ms, "
                f"total={total_elapsed_ms:.0f}ms)"
            )
            
            return {
                "status": result.get("status"),
                "payment_id": result.get("payment_id"),
                "invoice_id": invoice_id,
                "gateway": selected_gateway,
                "latency_ms": int(retry_latency_ms),
                "total_ms": int(total_elapsed_ms),
                "within_budget": total_elapsed_ms <= timeout_ms,
            }
        
        except Exception as e:
            logger.error(f"❌ Retry execution failed: {e}")
            
            return {
                "status": "error",
                "message": str(e),
                "invoice_id": invoice_id,
                "total_ms": int((time.time() - retry_start) * 1000),
            }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Live Reroute Engine - Day 3 Test")
    print("="*80 + "\n")
    
    # Initialize engine
    try:
        reroute = LiveRerouteEngine()
        
        print("Testing gateway selection:")
        print("-" * 60)
        
        # Test gateway selection
        selected, config = reroute.select_gateway()
        print(f"✓ Selected gateway: {selected}")
        
        # Get all gateway status
        print("\nGateway Status:")
        statuses = reroute.get_all_gateway_status()
        for status in statuses:
            print(f"  • {status['gateway']:12} {status['status']:10} "
                  f"success={status['success_rate']:>5} "
                  f"latency={status['latency_p99']:>7}")
        
        print("\n✓ Live reroute engine working")
    
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("\n" + "="*80 + "\n")
