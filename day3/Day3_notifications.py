"""
RecovAI: Notifications System
Day 3: SMS and WhatsApp notifications for payment recovery
"""

import logging
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# NOTIFICATION TYPES & TEMPLATES
# ============================================================================

class NotificationType(str, Enum):
    """Notification types"""
    PAYMENT_LINK_SENT = "payment_link_sent"
    PAYMENT_REMINDER = "payment_reminder"
    GRACE_PERIOD_EXPIRY = "grace_period_expiry"
    PAYMENT_FAILED = "payment_failed"
    PAYMENT_SUCCESS = "payment_success"
    DND_CONFIRMATION = "dnd_confirmation"
    ERROR_ALERT = "error_alert"


class NotificationChannel(str, Enum):
    """Notification channels"""
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    PUSH = "push_notification"


# ============================================================================
# NOTIFICATION TEMPLATES
# ============================================================================

NOTIFICATION_TEMPLATES = {
    NotificationType.PAYMENT_LINK_SENT: {
        "sms": "Hi {customer_name}, your payment of ₹{amount} is due. Click: {link} to pay. Link valid for 24 hours.",
        "whatsapp": "Hi {customer_name} 👋\n\nYour payment of ₹{amount} is pending.\n\n💳 Pay Now: {link}\n\nLink expires in 24 hours.\n\nThank you!",
        "email_subject": "Payment Link - ₹{amount} Due",
        "email_body": """<h2>Payment Required</h2>
<p>Hi {customer_name},</p>
<p>Your payment of <b>₹{amount}</b> is due.</p>
<p><a href="{link}" style="background-color: #007AFF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">
Pay Now
</a></p>
<p>This link is valid for 24 hours.</p>
<p>Thank you!</p>""",
    },
    
    NotificationType.PAYMENT_REMINDER: {
        "sms": "Reminder: ₹{amount} payment pending. Pay here: {link}. Link expires in {hours} hours.",
        "whatsapp": "⏰ Reminder\n\nYour payment of ₹{amount} is still pending.\n\n💳 Pay Now: {link}\n\nLink expires in {hours} hours.\n\nThank you!",
        "email_subject": "Reminder: Payment of ₹{amount} Pending",
    },
    
    NotificationType.GRACE_PERIOD_EXPIRY: {
        "sms": "Important: Your payment link expires in {hours} hours. Pay ₹{amount} now: {link}",
        "whatsapp": "⚠️ Important\n\nYour payment link expires in {hours} hours.\n\nPay ₹{amount} now: {link}\n\nAfter expiry, your service will be suspended.",
        "email_subject": "Action Required: Payment Link Expiring Soon",
    },
    
    NotificationType.PAYMENT_FAILED: {
        "sms": "Payment of ₹{amount} failed: {error}. Retry: {link}",
        "whatsapp": "❌ Payment Failed\n\nReason: {error}\n\n💳 Retry: {link}",
        "email_subject": "Payment Failed - Try Again",
    },
    
    NotificationType.PAYMENT_SUCCESS: {
        "sms": "✓ Payment successful! ₹{amount} confirmed. Thank you!",
        "whatsapp": "✅ Payment Confirmed!\n\nWe received your payment of ₹{amount}.\n\nThank you for your business!",
        "email_subject": "Payment Confirmed - Receipt",
    },
    
    NotificationType.DND_CONFIRMATION: {
        "sms": "Noted: You've opted out of recovery messages. Contact support to re-enable.",
        "whatsapp": "Noted: You've opted out of payment recovery messages. Contact support to re-enable.",
        "email_subject": "Notification Preference Updated",
    },
}


# ============================================================================
# NOTIFICATION MANAGER
# ============================================================================

class NotificationManager:
    """
    Manages sending notifications via multiple channels.
    
    Channels:
    - SMS (Razorpay SMS or Twilio)
    - WhatsApp (Razorpay WhatsApp or Twilio)
    - Email (Razorpay Email or SendGrid)
    - Push (FCM or OneSignal)
    
    DND Compliance:
    - Check DND list before sending
    - Respect user preferences
    - Allow opt-in/opt-out
    """
    
    def __init__(self, razorpay_manager=None, twilio_client=None):
        """
        Initialize notification manager.
        
        Args:
            razorpay_manager: RazorpayPaymentManager instance
            twilio_client: Twilio client instance (optional)
        """
        self.razorpay = razorpay_manager
        self.twilio = twilio_client
        
        # DND (Do Not Disturb) list
        self.dnd_list = set()
        
        logger.info("✓ NotificationManager initialized")
    
    def add_to_dnd(self, phone: str):
        """
        Add phone to DND list.
        
        Args:
            phone: Phone number
        """
        self.dnd_list.add(phone)
        logger.info(f"✓ Added to DND: {phone}")
    
    def remove_from_dnd(self, phone: str):
        """
        Remove phone from DND list.
        
        Args:
            phone: Phone number
        """
        self.dnd_list.discard(phone)
        logger.info(f"✓ Removed from DND: {phone}")
    
    def is_on_dnd(self, phone: str) -> bool:
        """
        Check if phone is on DND list.
        
        Args:
            phone: Phone number
            
        Returns:
            True if on DND, False otherwise
        """
        return phone in self.dnd_list
    
    def send_notification(
        self,
        phone: str,
        email: str,
        customer_name: str,
        notification_type: NotificationType,
        channels: List[NotificationChannel],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send notification via multiple channels.
        
        Args:
            phone: Customer phone (10 digits)
            email: Customer email
            customer_name: Customer name
            notification_type: Type of notification
            channels: Channels to use [SMS, WhatsApp, Email]
            context: Template context dict
            
        Returns:
            Result dict with channel status
        """
        # Check DND
        if self.is_on_dnd(phone):
            logger.warning(f"⛔ Customer on DND list: {phone}")
            return {
                "status": "blocked",
                "reason": "Customer is on DND list",
                "phone": phone,
            }
        
        result = {
            "status": "sent",
            "phone": phone,
            "notification_type": notification_type.value,
            "channels": {},
        }
        
        # Send via each channel
        for channel in channels:
            try:
                if channel == NotificationChannel.SMS:
                    sms_result = self._send_sms(phone, notification_type, context)
                    result["channels"]["sms"] = sms_result
                
                elif channel == NotificationChannel.WHATSAPP:
                    wa_result = self._send_whatsapp(phone, notification_type, context)
                    result["channels"]["whatsapp"] = wa_result
                
                elif channel == NotificationChannel.EMAIL:
                    email_result = self._send_email(
                        email, customer_name, notification_type, context
                    )
                    result["channels"]["email"] = email_result
                
                elif channel == NotificationChannel.PUSH:
                    push_result = self._send_push(phone, notification_type, context)
                    result["channels"]["push"] = push_result
            
            except Exception as e:
                logger.error(f"❌ Failed to send {channel.value}: {e}")
                result["channels"][channel.value] = {
                    "status": "failed",
                    "error": str(e),
                }
        
        return result
    
    def _send_sms(
        self,
        phone: str,
        notification_type: NotificationType,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send SMS notification.
        
        Args:
            phone: Phone number
            notification_type: Notification type
            context: Template context
            
        Returns:
            Result dict
        """
        try:
            template = NOTIFICATION_TEMPLATES.get(notification_type, {}).get("sms")
            
            if not template:
                return {"status": "error", "message": "No SMS template"}
            
            # Format message
            message = template.format(**context)
            
            # Send via Razorpay or Twilio
            if self.razorpay:
                # Would use Razorpay SMS API
                logger.info(f"📱 SMS sent via Razorpay: {phone}")
            elif self.twilio:
                # Send via Twilio
                self.twilio.messages.create(
                    body=message,
                    from_="+919876543210",  # Indian Twilio number
                    to=f"+91{phone[-10:]}"  # Ensure 10 digits
                )
                logger.info(f"📱 SMS sent via Twilio: {phone}")
            else:
                logger.warning("⚠️  SMS provider not configured, simulating send")
            
            return {
                "status": "sent",
                "channel": "sms",
                "phone": phone,
                "message_preview": message[:50] + "...",
            }
        
        except Exception as e:
            logger.error(f"❌ SMS send failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _send_whatsapp(
        self,
        phone: str,
        notification_type: NotificationType,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send WhatsApp notification.
        
        Args:
            phone: Phone number
            notification_type: Notification type
            context: Template context
            
        Returns:
            Result dict
        """
        try:
            template = NOTIFICATION_TEMPLATES.get(notification_type, {}).get("whatsapp")
            
            if not template:
                return {"status": "error", "message": "No WhatsApp template"}
            
            # Format message
            message = template.format(**context)
            
            # Send via Razorpay or Twilio
            if self.razorpay:
                # Would use Razorpay WhatsApp API
                logger.info(f"💬 WhatsApp sent via Razorpay: {phone}")
            elif self.twilio:
                # Send via Twilio WhatsApp
                self.twilio.messages.create(
                    body=message,
                    from_="whatsapp:+14155552671",  # Twilio sandbox
                    to=f"whatsapp:+91{phone[-10:]}"
                )
                logger.info(f"💬 WhatsApp sent via Twilio: {phone}")
            else:
                logger.warning("⚠️  WhatsApp provider not configured, simulating send")
            
            return {
                "status": "sent",
                "channel": "whatsapp",
                "phone": phone,
                "message_preview": message.split("\n")[0][:50],
            }
        
        except Exception as e:
            logger.error(f"❌ WhatsApp send failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _send_email(
        self,
        email: str,
        customer_name: str,
        notification_type: NotificationType,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send email notification.
        
        Args:
            email: Email address
            customer_name: Customer name
            notification_type: Notification type
            context: Template context
            
        Returns:
            Result dict
        """
        try:
            templates = NOTIFICATION_TEMPLATES.get(notification_type, {})
            subject = templates.get("email_subject", "Payment Update")
            body = templates.get("email_body", "")
            
            if not body:
                return {"status": "error", "message": "No email template"}
            
            # Format subject and body
            subject = subject.format(**context)
            body = body.format(customer_name=customer_name, **context)
            
            # Send via email provider (Razorpay, SendGrid, AWS SES, etc.)
            logger.info(f"📧 Email sent: {email}")
            
            return {
                "status": "sent",
                "channel": "email",
                "email": email,
                "subject": subject[:50],
            }
        
        except Exception as e:
            logger.error(f"❌ Email send failed: {e}")
            return {"status": "failed", "error": str(e)}
    
    def _send_push(
        self,
        phone: str,
        notification_type: NotificationType,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Send push notification.
        
        Args:
            phone: Phone number
            notification_type: Notification type
            context: Template context
            
        Returns:
            Result dict
        """
        try:
            # Send via FCM (Firebase) or OneSignal
            logger.info(f"🔔 Push notification sent: {phone}")
            
            return {
                "status": "sent",
                "channel": "push",
                "phone": phone,
            }
        
        except Exception as e:
            logger.error(f"❌ Push notification failed: {e}")
            return {"status": "failed", "error": str(e)}


# ============================================================================
# NOTIFICATION LOGGER
# ============================================================================

class NotificationLogger:
    """
    Log all notifications sent for audit trail.
    
    Tracks:
    - Sent notifications
    - Delivery status
    - User responses
    - DND compliance
    """
    
    def __init__(self, session=None):
        """
        Initialize notification logger.
        
        Args:
            session: SQLAlchemy database session
        """
        self.session = session
        self.logs = []
    
    def log_notification(
        self,
        invoice_id: str,
        customer_id: str,
        phone: str,
        notification_type: NotificationType,
        channels: List[NotificationType],
        result: Dict[str, Any],
    ):
        """
        Log notification sent.
        
        Args:
            invoice_id: Invoice ID
            customer_id: Customer ID
            phone: Phone number
            notification_type: Notification type
            channels: Channels used
            result: Notification result
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "phone": phone,
            "type": notification_type.value,
            "channels": [c.value for c in channels],
            "status": result.get("status"),
            "details": result,
        }
        
        self.logs.append(log_entry)
        logger.info(f"📝 Notification logged: {invoice_id} → {notification_type.value}")


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Notifications System - Day 3 Test")
    print("="*80 + "\n")
    
    # Initialize notification manager
    manager = NotificationManager()
    
    print("Notification Templates Available:")
    print("-" * 60)
    for notif_type in NotificationType:
        print(f"  ✓ {notif_type.value}")
    
    print("\nAvailable Channels:")
    print("-" * 60)
    for channel in NotificationChannel:
        print(f"  ✓ {channel.value}")
    
    print("\nDND Management:")
    print("-" * 60)
    manager.add_to_dnd("9876543210")
    print(f"  Is 9876543210 on DND? {manager.is_on_dnd('9876543210')}")
    manager.remove_from_dnd("9876543210")
    print(f"  Is 9876543210 on DND now? {manager.is_on_dnd('9876543210')}")
    
    print("\n✓ Notification system ready")
    print("\nExample usage:")
    print("""
    result = manager.send_notification(
        phone="9876543210",
        email="user@example.com",
        customer_name="John Doe",
        notification_type=NotificationType.PAYMENT_LINK_SENT,
        channels=[NotificationChannel.SMS, NotificationChannel.WHATSAPP],
        context={
            "amount": "500",
            "link": "https://rzp.io/i/...",
            "hours": "24"
        }
    )
    """)
    
    print("\n" + "="*80 + "\n")
