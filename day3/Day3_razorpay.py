"""
RecovAI: Razorpay SDK Integration
Day 3: Payment link generation, mandate management, and payment retry execution
"""

import logging
import hashlib
import hmac
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum

import razorpay

logger = logging.getLogger(__name__)


# ============================================================================
# RAZORPAY CONFIGURATION & ENUMS
# ============================================================================

class PaymentMethod(str, Enum):
    """Payment methods supported"""
    CARD = "card"
    UPI = "upi"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMANDATE = "emandate"


class LinkStatus(str, Enum):
    """Payment link statuses"""
    CREATED = "created"
    ACCEPTED = "accepted"
    PROCESSED = "processed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class MandateStatus(str, Enum):
    """E-mandate statuses"""
    CREATED = "created"
    PAUSED = "paused"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


# ============================================================================
# RAZORPAY PAYMENT MANAGER
# ============================================================================

class RazorpayPaymentManager:
    """
    Wrapper around Razorpay Python SDK.
    
    Features:
    - Payment link generation (UPI + Card)
    - E-mandate creation & management
    - Payment status checking
    - Refund management
    - Webhook signature verification
    - Batch operations
    """
    
    def __init__(self, key_id: str, key_secret: str):
        """
        Initialize Razorpay client.
        
        Args:
            key_id: Razorpay API Key ID
            key_secret: Razorpay API Key Secret
        """
        self.key_id = key_id
        self.key_secret = key_secret
        
        # Initialize Razorpay client
        self.client = razorpay.Client(auth=(key_id, key_secret))
        
        logger.info(f"✓ Razorpay client initialized (Key: {key_id[:10]}...)")
    
    # ========================================================================
    # PAYMENT LINK OPERATIONS
    # ========================================================================
    
    def create_payment_link(
        self,
        invoice_id: str,
        customer_id: str,
        amount_paise: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        description: str = "Payment recovery link",
        expire_minutes: int = 1440,  # 24 hours default
        upi_link: bool = True,
        card_link: bool = True,
        callback_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a payment link (short URL for payment).
        """
        try:
            expire_timestamp = int((datetime.utcnow() + timedelta(minutes=expire_minutes)).timestamp())
            
            link_data = {
                "amount": amount_paise,
                "currency": "INR",
                "accept_partial": False,
                "description": description,
                "customer": {
                    "name": customer_name,
                    "email": customer_email,
                    "contact": customer_phone,
                },
                "notify": {
                    "sms": True,
                    "email": True,
                },
                "reminder_enable": True,
                "notes": {
                    "invoice_id": invoice_id,
                    "customer_id": customer_id,
                    "recovery_type": "fallback_upi_link",
                },
                "expire_by": expire_timestamp,
            }
            
            if callback_url:
                link_data["callback_url"] = callback_url
                link_data["callback_method"] = "get"

            # Use payment_link API endpoint instead of invoice
            response = self.client.payment_link.create(link_data)
            
            logger.info(
                f"✓ Payment link created: {invoice_id} → {response.get('short_url')}"
            )
            
            return {
                "status": "success",
                "link_id": response.get("id"),
                "short_url": response.get("short_url"),
                "long_url": response.get("short_url"),
                "amount": response.get("amount"),
                "expire_by": response.get("expire_by"),
                "customer_id": customer_id,
                "invoice_id": invoice_id,
            }
        
        except Exception as e:
            logger.error(f"❌ Payment link creation failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "invoice_id": invoice_id,
            }
    
    def get_payment_link_status(self, link_id: str) -> Dict[str, Any]:
        """
        Check payment link status.
        
        Args:
            link_id: Payment link ID (e.g. plink_xxx)
            
        Returns:
            Link status dict
        """
        try:
            # Fetch using payment_link API endpoint
            response = self.client.payment_link.fetch(link_id)
            
            amount_paid = response.get("amount_paid", 0) or 0
            link_status = response.get("status")
            
            return {
                "status": link_status,
                "link_id": link_id,
                "amount": response.get("amount"),
                "amount_paid": amount_paid,
                "short_url": response.get("short_url"),
                "expire_by": response.get("expire_by"),
                "is_paid": amount_paid > 0 or link_status == "paid",
                "created_at": response.get("created_at"),
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch link status: {e}")
            return {"status": "error", "message": str(e)}
    
    # ========================================================================
    # E-MANDATE OPERATIONS
    # ========================================================================
    
    def create_emandate(
        self,
        customer_id: str,
        invoice_id: str,
        amount_paise: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        max_amount_paise: Optional[int] = None,
        expire_months: int = 12,
    ) -> Dict[str, Any]:
        """
        Create an e-mandate for recurring payments.
        
        Args:
            customer_id: Customer ID
            invoice_id: Invoice ID
            amount_paise: Amount for first debit
            customer_name: Customer name
            customer_email: Customer email
            customer_phone: Customer phone
            max_amount_paise: Max amount allowed (default 2x amount)
            expire_months: Mandate validity period
            
        Returns:
            E-mandate response dict
        """
        try:
            if not max_amount_paise:
                max_amount_paise = amount_paise * 2  # Default 2x
            
            mandate_data = {
                "customer_notify": 1,
                "type": "emandate",
                "currency": "INR",
                "amount": amount_paise,
                "description": f"E-mandate for {invoice_id}",
                "customer_id": customer_id,
                "token": None,  # Will be created
                "recurring": "1y",
                "email": customer_email,
                "phone": customer_phone,
                "notes": {
                    "invoice_id": invoice_id,
                    "max_amount": max_amount_paise,
                },
            }
            
            response = self.client.emandate.create(mandate_data)
            
            logger.info(f"✓ E-mandate created: {invoice_id} → {response.get('id')}")
            
            return {
                "status": "success",
                "mandate_id": response.get("id"),
                "token_id": response.get("token_id"),
                "amount": response.get("amount"),
                "max_amount": max_amount_paise,
                "status": response.get("status"),
                "short_url": response.get("short_url"),
                "invoice_id": invoice_id,
            }
        
        except Exception as e:
            logger.error(f"❌ E-mandate creation failed: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_mandate_status(self, mandate_id: str) -> Dict[str, Any]:
        """
        Get e-mandate status.
        
        Args:
            mandate_id: Mandate ID
            
        Returns:
            Mandate status dict
        """
        try:
            response = self.client.emandate.fetch(mandate_id)
            
            return {
                "mandate_id": mandate_id,
                "status": response.get("status"),
                "amount": response.get("amount"),
                "token_id": response.get("token_id"),
                "used_count": response.get("used_count", 0),
                "created_at": response.get("created_at"),
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch mandate status: {e}")
            return {"status": "error", "message": str(e)}
    
    def pause_mandate(self, mandate_id: str) -> Dict[str, Any]:
        """
        Pause an e-mandate.
        
        Args:
            mandate_id: Mandate ID
            
        Returns:
            Result dict
        """
        try:
            response = self.client.emandate.pause(mandate_id)
            
            logger.info(f"✓ Mandate paused: {mandate_id}")
            
            return {
                "status": "success",
                "mandate_id": mandate_id,
                "new_status": response.get("status"),
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to pause mandate: {e}")
            return {"status": "error", "message": str(e)}
    
    # ========================================================================
    # PAYMENT RETRY OPERATIONS
        # ========================================================================
    
    def execute_payment_retry(
        self,
        customer_id: str,
        invoice_id: str,
        amount_paise: int,
        token_id: str,
        description: str = "Payment retry",
    ) -> Dict[str, Any]:
        """
        Execute payment retry using saved token.
        
        Used for:
        - BLOCK_1: Silent T+15m, T+2h retries
        - BLOCK_2: Salary window retries
        
        Args:
            customer_id: Customer ID
            invoice_id: Invoice ID
            amount_paise: Amount in paise
            token_id: Token for saved payment method
            description: Payment description
            
        Returns:
            Payment result dict
        """
        try:
            payment_data = {
                "email": None,  # Would be fetched from customer record
                "contact": None,  # Would be fetched from customer record
                "amount": amount_paise,
                "currency": "INR",
                "customer_id": customer_id,
                "token": token_id,
                "recurring": "0",  # Not recurring
                "description": description,
                "notes": {
                    "invoice_id": invoice_id,
                    "retry_type": "auto_retry",
                },
            }
            
            response = self.client.payment.create(payment_data)
            
            logger.info(
                f"✓ Payment retry executed: {invoice_id} → {response.get('id')}"
            )
            
            return {
                "status": "success",
                "payment_id": response.get("id"),
                "amount": response.get("amount"),
                "status": response.get("status"),
                "invoice_id": invoice_id,
            }
        
        except Exception as e:
            logger.error(f"❌ Payment retry failed: {e}")
            return {
                "status": "error",
                "message": str(e),
                "invoice_id": invoice_id,
            }
    
    # ========================================================================
    # PAYMENT STATUS & DETAILS
    # ========================================================================
    
    def get_payment_status(self, payment_id: str) -> Dict[str, Any]:
        """
        Get payment status.
        
        Args:
            payment_id: Payment ID
            
        Returns:
            Payment status dict
        """
        try:
            response = self.client.payment.fetch(payment_id)
            
            return {
                "payment_id": payment_id,
                "amount": response.get("amount"),
                "status": response.get("status"),
                "method": response.get("method"),
                "description": response.get("description"),
                "invoice_id": response.get("notes", {}).get("invoice_id"),
                "created_at": response.get("created_at"),
                "error_code": response.get("error_code"),
                "error_description": response.get("error_description"),
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch payment status: {e}")
            return {"status": "error", "message": str(e)}
    
    def refund_payment(
        self,
        payment_id: str,
        amount_paise: Optional[int] = None,
        notes: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Refund a payment (full or partial).
        
        Args:
            payment_id: Payment ID
            amount_paise: Amount to refund (None = full)
            notes: Refund notes
            
        Returns:
            Refund result dict
        """
        try:
            refund_data = {
                "notes": notes or {"reason": "customer_request"},
            }
            
            if amount_paise:
                refund_data["amount"] = amount_paise
            
            response = self.client.payment.refund(payment_id, refund_data)
            
            logger.info(f"✓ Refund created: {payment_id} → {response.get('id')}")
            
            return {
                "status": "success",
                "refund_id": response.get("id"),
                "amount": response.get("amount"),
                "payment_id": payment_id,
            }
        
        except Exception as e:
            logger.error(f"❌ Refund failed: {e}")
            return {"status": "error", "message": str(e)}
    
    # ========================================================================
    # WEBHOOK SIGNATURE VERIFICATION
    # ========================================================================
    
    def verify_webhook_signature(
        self,
        webhook_body: str,
        webhook_signature: str,
    ) -> bool:
        """
        Verify Razorpay webhook signature (HMAC-SHA256).
        
        Args:
            webhook_body: Webhook payload as string
            webhook_signature: X-Razorpay-Signature header value
            
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Calculate expected signature
            expected_signature = hmac.new(
                self.key_secret.encode(),
                webhook_body.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            is_valid = hmac.compare_digest(expected_signature, webhook_signature)
            
            if is_valid:
                logger.info("✓ Webhook signature verified")
            else:
                logger.warning("❌ Webhook signature verification failed")
            
            return is_valid
        
        except Exception as e:
            logger.error(f"❌ Signature verification error: {e}")
            return False
    
    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    
    def get_payments_batch(
        self,
        limit: int = 50,
        skip: int = 0,
        from_date: Optional[int] = None,
        to_date: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch batch of payments.
        
        Args:
            limit: Number of payments to fetch
            skip: Offset
            from_date: Unix timestamp (from)
            to_date: Unix timestamp (to)
            
        Returns:
            List of payment dicts
        """
        try:
            params = {"count": limit, "skip": skip}
            
            if from_date:
                params["from"] = from_date
            if to_date:
                params["to"] = to_date
            
            response = self.client.payment.all(params)
            
            return response.get("items", [])
        
        except Exception as e:
            logger.error(f"❌ Failed to fetch payments: {e}")
            return []
    
    def get_customer_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """
        Search for customer by phone.
        
        Args:
            phone: Phone number
            
        Returns:
            Customer dict or None
        """
        try:
            response = self.client.customer.all({"phone": phone})
            
            if response.get("count", 0) > 0:
                return response["items"][0]
            
            return None
        
        except Exception as e:
            logger.error(f"❌ Customer search failed: {e}")
            return None


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Razorpay Integration - Day 3 Test")
    print("="*80 + "\n")
    
    # Note: Requires actual Razorpay API keys
    # Get from https://dashboard.razorpay.com/app/keys
    
    KEY_ID = "YOUR_KEY_ID"
    KEY_SECRET = "YOUR_KEY_SECRET"
    
    if KEY_ID == "YOUR_KEY_ID":
        print("⚠️  Razorpay API keys not configured")
        print("\nTo test:")
        print("1. Go to https://dashboard.razorpay.com/app/keys")
        print("2. Copy Key ID and Key Secret")
        print("3. Replace KEY_ID and KEY_SECRET in this file")
        print("4. Run: python Day3_razorpay.py")
    else:
        manager = RazorpayPaymentManager(KEY_ID, KEY_SECRET)
        
        print("✓ Razorpay integration ready")
        print("\nMethods available:")
        print("  • create_payment_link() - Create UPI/Card payment link")
        print("  • create_emandate() - Create e-mandate")
        print("  • execute_payment_retry() - Execute auto-retry")
        print("  • get_payment_status() - Check payment status")
        print("  • verify_webhook_signature() - Verify webhook")
    
    print("\n" + "="*80 + "\n")
