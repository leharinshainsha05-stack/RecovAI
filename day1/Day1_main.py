"""
RecovAI: FastAPI Application
Day 1: Core API setup with webhook receiver and diagnostic classifier
"""

import os
import logging
import json
import hmac
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from Day1_models import (
    WebhookEvent, WebhookAckResponse, DiagnosticResult,
    PaymentError, Card, PaymentMethod, ChargeData
)
from Day1_diagnostic import DiagnosticEngine, create_test_webhook


# ============================================================================
# LOGGING SETUP
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="RecovAI",
    description="Autonomous Revenue Defense Engine - Day 1: Core Backend",
    version="0.1.0"
)

# Add CORS middleware (for future frontend integration)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global diagnostic engine instance
diagnostic_engine = DiagnosticEngine()

# Configuration (from environment or defaults)
RAZORPAY_WEBHOOK_SECRET = os.getenv(
    "RAZORPAY_WEBHOOK_SECRET",
    "test_webhook_secret_day1"  # TODO: Replace with actual secret
)

DEBUG_MODE = os.getenv("DEBUG_MODE", "true").lower() == "true"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def verify_razorpay_signature(
    body: str,
    signature_header: str
) -> bool:
    """
    Verify Razorpay webhook signature using HMAC-SHA256.
    
    Args:
        body: Raw request body
        signature_header: X-Razorpay-Signature header value
        
    Returns:
        True if signature is valid, False otherwise
    """
    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(signature_header, expected_signature)


def log_diagnostic_result(result: DiagnosticResult):
    """Log diagnostic result in structured format"""
    logger.info(f"📊 Diagnostic Classification:")
    logger.info(f"   Invoice: {result.invoice_id}")
    logger.info(f"   Block: {result.block.value}")
    logger.info(f"   Root Cause: {result.root_cause.value}")
    logger.info(f"   Severity: {result.severity.value}")
    logger.info(f"   Recovery Score: {result.recovery_score:.2f}")
    logger.info(f"   Next Action: {result.next_action}")


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for orchestration
    """
    return {
        "status": "healthy",
        "service": "recovai-engine",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness probe - check if dependencies are ready
    """
    # TODO: In production, check database, Redis, Razorpay API connectivity
    return {
        "ready": True,
        "diagnostic_engine": "initialized",
        "database": "pending",  # Will implement in Day 2
        "redis": "pending"      # Will implement in Day 2/3
    }


# ============================================================================
# WEBHOOK ENDPOINTS
# ============================================================================

@app.post(
    "/webhooks/payment-failure",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["Webhooks"]
)
async def receive_payment_failure_webhook(request: Request):
    """
    Main webhook endpoint for payment failure events.
    
    Receives Razorpay charge.failed events, validates signature,
    parses payload, and routes to diagnostic engine.
    
    Returns:
        202 Accepted with event_id for async processing
    """
    
    try:
        # Get raw body and signature
        body = await request.body()
        body_str = body.decode('utf-8')
        signature_header = request.headers.get('X-Razorpay-Signature', '')
        
        logger.info(f"🔔 Webhook received | Signature: {signature_header[:20]}...")
        
        # Verify signature (skip in debug mode)
        if not DEBUG_MODE:
            if not signature_header:
                logger.warning("⚠️  Missing Razorpay signature header")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing X-Razorpay-Signature header"
                )
            
            if not verify_razorpay_signature(body_str, signature_header):
                logger.error("❌ Invalid webhook signature")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
            
            logger.info("✓ Signature verified")
        else:
            logger.info("⚠️  DEBUG_MODE=true: Skipping signature verification")
        
        # Parse JSON payload
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON payload: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid JSON payload"
            )
        
        logger.info(f"📥 Raw payload: {json.dumps(payload, indent=2)[:200]}...")
        
        # Validate and parse webhook event
        try:
            webhook_event = WebhookEvent(**payload)
            logger.info(f"✓ Webhook validated | Event: {webhook_event.event}")
        except ValueError as e:
            logger.error(f"❌ Webhook validation failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid webhook format: {str(e)}"
            )
        
        # Classify using diagnostic engine
        logger.info("🔍 Running diagnostic classifier...")
        diagnostic_result = diagnostic_engine.classify(webhook_event)
        log_diagnostic_result(diagnostic_result)
        
        # TODO (Day 2): Store diagnostic result to database
        # TODO (Day 2): Enqueue async recovery workflow
        # TODO (Day 2): Create audit log entry
        
        # Return acknowledgment
        response = WebhookAckResponse(
            status="accepted",
            event_id=webhook_event.id,
            processing_timestamp=datetime.now(timezone.utc)
        )
        
        logger.info(f"✓ Webhook processed successfully | Returning 202")
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Unexpected error processing webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error processing webhook"
        )


# ============================================================================
# DIAGNOSTIC ENDPOINTS (DEBUG/TESTING)
# ============================================================================

@app.post(
    "/api/v1/diagnostic/classify",
    response_model=DiagnosticResult,
    tags=["Diagnostic (Debug)"]
)
async def classify_payment_failure(webhook: WebhookEvent):
    """
    Direct diagnostic endpoint for testing.
    
    Accepts a payment failure webhook and returns classification result.
    Useful for testing error scenarios without Razorpay signature validation.
    
    Example request body:
    ```json
    {
      "id": "evt_test_001",
      "event": "charge.failed",
      "created_at": 1693500000,
      "data": {
        "id": "ch_test_001",
        "invoice_id": "inv_test_001",
        "customer_id": "cust_test_001",
        "amount": 99900,
        "currency": "INR",
        "error": {
          "code": "GATEWAY_TIMEOUT",
          "message": "Request timeout from issuer gateway"
        },
        "payment_method": {
          "type": "card",
          "card": {"id": "card_test_001"}
        },
        "status": "failed",
        "created_at": 1693500000
      }
    }
    ```
    """
    logger.info(f"🧪 Direct diagnostic request for invoice {webhook.data.invoice_id}")
    result = diagnostic_engine.classify(webhook)
    log_diagnostic_result(result)
    return result


@app.post(
    "/api/v1/diagnostic/batch",
    tags=["Diagnostic (Debug)"],
    response_model=Dict[str, Any]  
)   
async def classify_batch(payloads: List[dict]):
    """
    Batch diagnostic classification for testing.
    
    Useful for running 50-payload benchmark tests.
    """
    logger.info(f" Batch classification request for {len(payloads)} payloads")
    
    if not payloads:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payloads list cannot be empty"
        )
    
    results = []
    for i, payload in enumerate(payloads):
        try:
            webhook = WebhookEvent(**payload)
            result = diagnostic_engine.classify(webhook)
            results.append(result.model_dump())
        except Exception as e:
            logger.error(f"❌ Error processing batch item {i}: {e}")
            results.append({
                "error": str(e),
                "index": i
            })
    
    logger.info(f"✓ Batch classification complete: {len(results)} results")
    return {
        "total": len(results),
        "success": len([r for r in results if "error" not in r]),
        "results": results
    }


@app.get(
    "/api/v1/diagnostic/test-webhook/{error_code}",
    response_model=DiagnosticResult,
    tags=["Diagnostic (Debug)"]
)
async def test_webhook_by_error_code(
    error_code: str,
    invoice_id: str = "inv_test_001",
    customer_id: str = "cust_test_001",
    amount: int = 99900
):
    """
    Generate and classify a test webhook with specific error code.
    
    Useful for quickly testing different failure scenarios.
    
    Example: GET /api/v1/diagnostic/test-webhook/GATEWAY_TIMEOUT
    """
    logger.info(f"🧪 Generating test webhook for error code: {error_code}")
    
    webhook = create_test_webhook(
        error_code=error_code,
        invoice_id=invoice_id,
        customer_id=customer_id,
        amount=amount
    )
    
    result = diagnostic_engine.classify(webhook)
    log_diagnostic_result(result)
    return result


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/api/v1/errors/codes", tags=["Reference"])
async def get_error_code_reference():
    """
    Get reference of all supported error codes and their classifications.
    """
    from Day1_diagnostic import DiagnosticEngine
    
    codes = {}
    for error_code, (root_cause, block, severity) in DiagnosticEngine.ERROR_CODE_MAPPING.items():
        codes[error_code] = {
            "root_cause": root_cause.value,
            "block": block.value,
            "severity": severity.value
        }
    
    return {
        "total_codes": len(codes),
        "error_codes": codes
    }


@app.get("/api/v1/errors/hard-declines", tags=["Reference"])
async def get_hard_decline_codes():
    """
    Get list of hard-decline error codes (no retry possible).
    """
    from Day1_diagnostic import DiagnosticEngine
    
    return {
        "total": len(DiagnosticEngine.HARD_DECLINE_CODES),
        "codes": sorted(list(DiagnosticEngine.HARD_DECLINE_CODES)),
        "description": "Error codes that result in 0% recovery score"
    }


@app.get("/api/v1/errors/soft-declines", tags=["Reference"])
async def get_soft_decline_codes():
    """
    Get list of soft/transient error codes (retryable).
    """
    from Day1_diagnostic import DiagnosticEngine
    
    return {
        "total": len(DiagnosticEngine.SOFT_DECLINE_CODES),
        "codes": sorted(list(DiagnosticEngine.SOFT_DECLINE_CODES)),
        "description": "Error codes that are retryable"
    }


# ============================================================================
# APPLICATION STARTUP/SHUTDOWN
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize on application startup"""
    logger.info("="*80)
    logger.info("RecovAI Engine - Day 1: Core Backend & Data Models")
    logger.info("="*80)
    logger.info(f"✓ FastAPI application started")
    logger.info(f"✓ Diagnostic engine initialized")
    logger.info(f"✓ Debug mode: {DEBUG_MODE}")
    logger.info(f"✓ Webhook secret configured: {bool(RAZORPAY_WEBHOOK_SECRET)}")
    logger.info("="*80 + "\n")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info("\n" + "="*80)
    logger.info("RecovAI Engine - Shutting down")
    logger.info("="*80)
    logger.info("✓ Gracefully shut down")


# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/", tags=["Info"])
async def root():
    """
    Root endpoint with API documentation links.
    """
    return {
        "service": "RecovAI - Autonomous Revenue Defense Engine",
        "version": "0.1.0",
        "day": "Day 1: Core Backend & Data Models",
        "status": "🟢 Running",
        "endpoints": {
            "health": "/health",
            "readiness": "/ready",
            "webhook": "/webhooks/payment-failure",
            "docs": "/docs",
            "openapi": "/openapi.json"
        },
        "test_endpoints": {
            "classify": "POST /api/v1/diagnostic/classify",
            "batch": "POST /api/v1/diagnostic/batch",
            "test_webhook": "GET /api/v1/diagnostic/test-webhook/{error_code}",
            "error_codes": "GET /api/v1/errors/codes",
            "hard_declines": "GET /api/v1/errors/hard-declines",
            "soft_declines": "GET /api/v1/errors/soft-declines"
        }
    }


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Run with: python Day1_main.py
    # Or: uvicorn Day1_main:app --reload --host 0.0.0.0 --port 8000
    
    print("\n" + "="*80)
    print("RecovAI - Day 1 FastAPI Server")
    print("="*80)
    print("\nStarting server...")
    print("📚 API Docs: http://localhost:8000/docs")
    print("📚 ReDoc: http://localhost:8000/redoc")
    print("\nTest webhook endpoint:")
    print("POST http://localhost:8000/webhooks/payment-failure")
    print("\nTest diagnostic endpoint:")
    print("GET http://localhost:8000/api/v1/diagnostic/test-webhook/GATEWAY_TIMEOUT")
    print("="*80 + "\n")
    
    uvicorn.run(
        "Day1_main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
