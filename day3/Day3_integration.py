"""
RecovAI: Day 3 Complete Integration
Connects Razorpay API, live reroute, and notifications with Day 2 database
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from Day2_database import RecoveryFlow, ActionTypeEnum, RecoveryStateEnum
from Day2_audit import AuditLedger
from Day3_razorpay import RazorpayPaymentManager, PaymentMethod
from Day3_live_reroute import LiveRerouteEngine, RetryExecutor
from Day3_notifications import NotificationManager, NotificationType, NotificationChannel


logger = logging.getLogger(__name__)


# ============================================================================
# UNIFIED RECOVERY ENGINE (Day 2 + Day 3)
# ============================================================================

class UnifiedRecoveryEngine:
    """
    Unified recovery engine combining:
    - Day 2: State machine, audit trail, database
    - Day 3: Razorpay API, live reroute, notifications
    
    Features:
    - Payment link generation (BLOCK_4)
    - Live reroute retry (<200ms)
    - Smart notifications
    - Complete audit trail
    """
    
    def __init__(
        self,
        razorpay_key_id: str,
        razorpay_key_secret: str,
        redis_url: str = "redis://localhost:6379",
    ):
        """
        Initialize unified engine.
        
        Args:
            razorpay_key_id: Razorpay API Key ID
            razorpay_key_secret: Razorpay API Key Secret
            redis_url: Redis connection URL
        """
        # Day 3 components
        self.razorpay = RazorpayPaymentManager(razorpay_key_id, razorpay_key_secret)
        self.reroute = LiveRerouteEngine(redis_url)
        self.retry_executor = RetryExecutor(self.reroute, self.razorpay)
        self.notifications = NotificationManager(self.razorpay)
        
        # Day 2 components
        self.audit_ledger = AuditLedger()
        
        logger.info("✓ UnifiedRecoveryEngine initialized (Day 2 + Day 3)")
    
    # ========================================================================
    # BLOCK 1: LIVE REROUTE RETRY
    # ========================================================================
    
    def execute_block_1_retry(
        self,
        flow: RecoveryFlow,
        session,
    ) -> Dict[str, Any]:
        """
        Execute BLOCK_1 retry with live reroute (<200ms).
        
        Args:
            flow: RecoveryFlow entity
            session: Database session
            
        Returns:
            Result dict
        """
        try:
            logger.info(f"🔄 Executing BLOCK_1 live reroute retry: {flow.invoice_id}")
            
            # Execute retry via best gateway
            result = self.retry_executor.execute_retry(
                invoice_id=flow.invoice_id,
                customer_id=flow.customer_id,
                amount_paise=flow.invoice.amount_in_paise,
                token_id=flow.invoice.payment_method_token,  # Would be fetched
                timeout_ms=200,
            )
            
            # Log to audit trail
            self.audit_ledger.log_event(
                session=session,
                invoice_id=flow.invoice_id,
                customer_id=flow.customer_id,
                action=ActionTypeEnum.LIVE_REROUTE_TRIGGERED,
                details={
                    "gateway": result.get("gateway"),
                    "latency_ms": result.get("latency_ms"),
                    "success": result.get("status") == "success",
                }
            )
            
            return result
        
        except Exception as e:
            logger.error(f"❌ BLOCK_1 retry failed: {e}")
            return {"status": "error", "message": str(e)}
    
    # ========================================================================
    # BLOCK 4: FALLBACK UPI LINK
    # ========================================================================
    
    def generate_fallback_link(
        self,
        flow: RecoveryFlow,
        customer,
        session,
    ) -> Dict[str, Any]:
        """
        Generate fallback UPI payment link (BLOCK_4).
        
        Args:
            flow: RecoveryFlow entity
            customer: Customer entity
            session: Database session
            
        Returns:
            Link generation result
        """
        try:
            invoice = flow.invoice
            
            logger.info(f"🔗 Generating fallback UPI link: {invoice.id}")
            
            # Create payment link via Razorpay
            link_result = self.razorpay.create_payment_link(
                invoice_id=invoice.id,
                customer_id=customer.id,
                amount_paise=invoice.amount_in_paise,
                customer_name=customer.name or "Customer",
                customer_email=customer.email or "noemail@example.com",
                customer_phone=customer.phone or "0000000000",
                description="Payment recovery link",
                expire_minutes=int(flow.grace_period_hours * 60) if flow.grace_period_hours else 1440,
                upi_link=True,
                card_link=True,
                callback_url=None,  # Would be production callback URL
            )
            
            if link_result.get("status") != "success":
                logger.error(f"❌ Link generation failed: {link_result.get('message')}")
                return link_result
            
            # Store link info in recovery flow
            flow.fallback_link_id = link_result.get("link_id")
            flow.fallback_link_url = link_result.get("long_url")
            flow.fallback_link_short_url = link_result.get("short_url")
            
            # Log to audit trail
            self.audit_ledger.log_event(
                session=session,
                invoice_id=invoice.id,
                customer_id=customer.id,
                action=ActionTypeEnum.FALLBACK_LINK_SENT,
                details={
                    "link_id": link_result.get("link_id"),
                    "short_url": link_result.get("short_url"),
                    "grace_period_hours": flow.grace_period_hours,
                }
            )
            
            # Send notifications
            self._send_fallback_link_notification(
                customer=customer,
                invoice=invoice,
                link_result=link_result,
            )
            
            session.commit()
            
            logger.info(f"✓ Fallback link created: {invoice.id}")
            
            return link_result
        
        except Exception as e:
            logger.error(f"❌ Fallback link generation failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def check_fallback_link_payment(
        self,
        flow: RecoveryFlow,
        session,
    ) -> Dict[str, Any]:
        """
        Check if fallback link payment was made.
        
        Args:
            flow: RecoveryFlow entity
            session: Database session
            
        Returns:
            Payment status
        """
        try:
            if not flow.fallback_link_id:
                return {"status": "error", "message": "No fallback link"}
            
            # Check link status
            link_status = self.razorpay.get_payment_link_status(
                flow.fallback_link_id
            )
            
            if link_status.get("is_paid"):
                logger.info(f"✓ Fallback link payment confirmed: {flow.invoice_id}")
                
                # Log to audit trail
                self.audit_ledger.log_event(
                    session=session,
                    invoice_id=flow.invoice_id,
                    customer_id=flow.customer_id,
                    action=ActionTypeEnum.RECOVERED,
                    state_before=flow.current_state,
                    state_after=RecoveryStateEnum.RECOVERED_VIA_FALLBACK,
                    details={
                        "amount_paid": link_status.get("amount_paid"),
                        "link_id": flow.fallback_link_id,
                    }
                )
                
                session.commit()
            
            return link_status
        
        except Exception as e:
            logger.error(f"❌ Failed to check fallback link: {e}")
            return {"status": "error", "message": str(e)}
    
    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================
    
    def _send_fallback_link_notification(
        self,
        customer,
        invoice,
        link_result: Dict[str, Any],
    ):
        """
        Send payment link notification via SMS/WhatsApp.
        
        Args:
            customer: Customer entity
            invoice: Invoice entity
            link_result: Link generation result
        """
        try:
            if not customer.phone:
                logger.warning(f"⚠️  No phone number for customer {customer.id}")
                return
            
            # Prepare context
            context = {
                "customer_name": customer.name or "Customer",
                "amount": f"{invoice.amount_in_paise / 100:.0f}",
                "link": link_result.get("short_url", link_result.get("long_url")),
                "hours": str(invoice.grace_period_hours or 24),
            }
            
            # Send via SMS + WhatsApp
            result = self.notifications.send_notification(
                phone=customer.phone,
                email=customer.email or "noemail@example.com",
                customer_name=customer.name or "Customer",
                notification_type=NotificationType.PAYMENT_LINK_SENT,
                channels=[
                    NotificationChannel.SMS,
                    NotificationChannel.WHATSAPP,
                ],
                context=context,
            )
            
            logger.info(
                f"✓ Notification sent: {customer.phone} → "
                f"{result.get('channels', {}).get('sms', {}).get('status', 'unknown')}"
            )
        
        except Exception as e:
            logger.error(f"❌ Failed to send notification: {e}")
    
    def send_grace_period_reminder(
        self,
        customer,
        invoice,
        hours_remaining: int,
    ):
        """
        Send grace period expiry reminder.
        
        Args:
            customer: Customer entity
            invoice: Invoice entity
            hours_remaining: Hours until grace period expires
        """
        try:
            context = {
                "customer_name": customer.name or "Customer",
                "amount": f"{invoice.amount_in_paise / 100:.0f}",
                "hours": str(hours_remaining),
            }
            
            self.notifications.send_notification(
                phone=customer.phone,
                email=customer.email or "noemail@example.com",
                customer_name=customer.name or "Customer",
                notification_type=NotificationType.GRACE_PERIOD_EXPIRY,
                channels=[NotificationChannel.SMS, NotificationChannel.WHATSAPP],
                context=context,
            )
        
        except Exception as e:
            logger.error(f"❌ Reminder notification failed: {e}")
    
    def send_payment_success_notification(
        self,
        customer,
        invoice,
    ):
        """
        Send payment success confirmation.
        
        Args:
            customer: Customer entity
            invoice: Invoice entity
        """
        try:
            context = {
                "customer_name": customer.name or "Customer",
                "amount": f"{invoice.amount_in_paise / 100:.0f}",
            }
            
            self.notifications.send_notification(
                phone=customer.phone,
                email=customer.email or "noemail@example.com",
                customer_name=customer.name or "Customer",
                notification_type=NotificationType.PAYMENT_SUCCESS,
                channels=[
                    NotificationChannel.SMS,
                    NotificationChannel.EMAIL,
                ],
                context=context,
            )
        
        except Exception as e:
            logger.error(f"❌ Success notification failed: {e}")
    
    # ========================================================================
    # GATEWAY HEALTH MONITORING
    # ========================================================================
    
    def get_gateway_status(self) -> Dict[str, Any]:
        """
        Get real-time gateway health status.
        
        Returns:
            Gateway status dict
        """
        return {
            "gateways": self.reroute.get_all_gateway_status(),
            "timestamp": datetime.utcnow().isoformat(),
        }


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Unified Recovery Engine - Day 2 + Day 3")
    print("="*80 + "\n")
    
    print("Components:")
    print("  ✓ Day 2: State Machine + Database + Audit Ledger")
    print("  ✓ Day 3: Razorpay + Live Reroute + Notifications")
    print("\nFeatures:")
    print("  • BLOCK_1: Live reroute retry (<200ms)")
    print("  • BLOCK_4: Fallback UPI payment link")
    print("  • Gateway selection: Real-time health monitoring")
    print("  • Notifications: SMS, WhatsApp, Email")
    print("  • Audit trail: Complete transaction history")
    print("\n✓ Unified engine ready")
    print("\n" + "="*80 + "\n")
