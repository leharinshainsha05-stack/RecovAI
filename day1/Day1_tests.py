"""
RecovAI: Unit & Integration Tests
Day 1: Test diagnostic engine and API endpoints
"""

import pytest
import json
from datetime import datetime, time
from fastapi.testclient import TestClient

from Day1_models import (
    WebhookEvent, DiagnosticResult, BlockType, RootCauseType,
    SeverityLevel, RecoveryState
)
from Day1_diagnostic import DiagnosticEngine, create_test_webhook
from Day1_main import app, diagnostic_engine


# ============================================================================
# TEST CONFIGURATION
# ============================================================================

client = TestClient(app)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def diagnostic_engine_instance():
    """Provide a fresh diagnostic engine for each test"""
    return DiagnosticEngine()


# ============================================================================
# DIAGNOSTIC ENGINE TESTS
# ============================================================================

class TestDiagnosticEngine:
    """Test suite for DiagnosticEngine classification logic"""
    
    def test_gateway_timeout_classification(self, diagnostic_engine_instance):
        """Test BLOCK_1 classification for gateway timeout"""
        webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert result.block == BlockType.BLOCK_1
        assert result.root_cause == RootCauseType.GATEWAY_TIMEOUT
        assert result.severity == SeverityLevel.HIGH
        assert result.recovery_score > 0.80
    
    def test_insufficient_funds_classification(self, diagnostic_engine_instance):
        """Test BLOCK_2 classification for insufficient funds on month-end"""
        webhook = create_test_webhook(error_code="INSUFFICIENT_FUNDS")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert result.block == BlockType.BLOCK_2
        assert result.root_cause == RootCauseType.INSUFFICIENT_FUNDS
        assert result.severity == SeverityLevel.MEDIUM
        assert result.recovery_score > 0.70
    
    def test_card_expired_classification(self, diagnostic_engine_instance):
        """Test BLOCK_3 classification for expired card"""
        webhook = create_test_webhook(error_code="CARD_EXPIRED")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert result.block == BlockType.BLOCK_3
        assert result.root_cause == RootCauseType.CARD_EXPIRED
        assert result.severity == SeverityLevel.HIGH
        assert result.recovery_score == 0.0  # Hard decline
    
    def test_fraud_declined_classification(self, diagnostic_engine_instance):
        """Test CRITICAL severity for fraud"""
        webhook = create_test_webhook(error_code="FRAUD_DECLINED")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert result.block == BlockType.BLOCK_3
        assert result.root_cause == RootCauseType.FRAUD_DECLINED
        assert result.severity == SeverityLevel.CRITICAL
        assert result.recovery_score == 0.0
    
    def test_unknown_error_code_classification(self, diagnostic_engine_instance):
        """Test fallback for unknown error codes"""
        webhook = create_test_webhook(error_code="UNKNOWN_ERROR_XYZ")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert result.block == BlockType.BLOCK_4
        assert result.root_cause == RootCauseType.UNKNOWN
    
    def test_hard_decline_codes(self, diagnostic_engine_instance):
        """Test that all hard-decline codes result in 0.0 recovery score"""
        hard_declines = [
            "CARD_EXPIRED", "MANDATE_REVOKED", "CVV_MISMATCH",
            "INVALID_TOKEN", "FRAUD_DECLINED", "ISSUER_DECLINED"
        ]
        
        for error_code in hard_declines:
            webhook = create_test_webhook(error_code=error_code)
            result = diagnostic_engine_instance.classify(webhook)
            
            assert result.recovery_score == 0.0, f"{error_code} should have 0.0 recovery score"
            assert result.block == BlockType.BLOCK_3
    
    def test_soft_decline_codes(self, diagnostic_engine_instance):
        """Test that soft-decline codes are retryable"""
        soft_declines = [
            "GATEWAY_TIMEOUT", "NETWORK_ERROR", "REQUEST_TIMEOUT",
            "INSUFFICIENT_FUNDS"
        ]
        
        for error_code in soft_declines:
            webhook = create_test_webhook(error_code=error_code)
            result = diagnostic_engine_instance.classify(webhook)
            
            assert result.recovery_score > 0.0, f"{error_code} should be retryable"
    
    def test_batch_classification(self, diagnostic_engine_instance):
        """Test batch classification of multiple webhooks"""
        error_codes = ["GATEWAY_TIMEOUT", "INSUFFICIENT_FUNDS", "CARD_EXPIRED"]
        webhooks = [
            create_test_webhook(error_code=code, invoice_id=f"inv_{i}")
            for i, code in enumerate(error_codes)
        ]
        
        results = diagnostic_engine_instance.classify_batch(webhooks)
        
        assert len(results) == len(error_codes)
        assert results[0].block == BlockType.BLOCK_1
        assert results[1].block == BlockType.BLOCK_2
        assert results[2].block == BlockType.BLOCK_3
    
    def test_recovery_score_calculation(self, diagnostic_engine_instance):
        """Test recovery score calculations per block"""
        test_cases = [
            ("GATEWAY_TIMEOUT", 0.85, 0.95),      # BLOCK_1: 0.85-0.95
            ("INSUFFICIENT_FUNDS", 0.70, 0.85),  # BLOCK_2: 0.70-0.85
            ("CARD_EXPIRED", 0.0, 0.0),          # BLOCK_3: 0.0
        ]
        
        for error_code, min_score, max_score in test_cases:
            webhook = create_test_webhook(error_code=error_code)
            result = diagnostic_engine_instance.classify(webhook)
            
            assert min_score <= result.recovery_score <= max_score, \
                f"{error_code} score {result.recovery_score} not in range [{min_score}, {max_score}]"
    
    def test_diagnostic_result_structure(self, diagnostic_engine_instance):
        """Test that diagnostic result contains all required fields"""
        webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
        result = diagnostic_engine_instance.classify(webhook)
        
        assert isinstance(result, DiagnosticResult)
        assert result.invoice_id is not None
        assert result.block is not None
        assert result.root_cause is not None
        assert result.severity is not None
        assert 0.0 <= result.recovery_score <= 1.0
        assert result.next_action is not None
        assert result.details is not None
        assert result.classified_at is not None


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================

class TestAPIEndpoints:
    """Test suite for FastAPI endpoints"""
    
    def test_health_check(self):
        """Test /health endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "recovai-engine"
        assert "timestamp" in data
    
    def test_readiness_check(self):
        """Test /ready endpoint"""
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert data["ready"] == True
        assert "diagnostic_engine" in data
    
    def test_root_endpoint(self):
        """Test root / endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "endpoints" in data
    
    def test_error_codes_reference(self):
        """Test /api/v1/errors/codes endpoint"""
        response = client.get("/api/v1/errors/codes")
        
        assert response.status_code == 200
        data = response.json()
        assert "total_codes" in data
        assert "error_codes" in data
        assert data["total_codes"] > 0
        
        # Check sample error codes
        assert "GATEWAY_TIMEOUT" in data["error_codes"]
        assert "CARD_EXPIRED" in data["error_codes"]
    
    def test_hard_declines_reference(self):
        """Test /api/v1/errors/hard-declines endpoint"""
        response = client.get("/api/v1/errors/hard-declines")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "codes" in data
        assert "CARD_EXPIRED" in data["codes"]
        assert "FRAUD_DECLINED" in data["codes"]
    
    def test_soft_declines_reference(self):
        """Test /api/v1/errors/soft-declines endpoint"""
        response = client.get("/api/v1/errors/soft-declines")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "codes" in data
        assert "GATEWAY_TIMEOUT" in data["codes"]
        assert "INSUFFICIENT_FUNDS" in data["codes"]


# ============================================================================
# WEBHOOK ENDPOINT TESTS
# ============================================================================

class TestWebhookEndpoint:
    """Test suite for /webhooks/payment-failure endpoint"""
    
    def test_webhook_accept_valid_payload(self):
        """Test webhook accepts valid Razorpay payload"""
        webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
        
        response = client.post(
            "/webhooks/payment-failure",
            json=webhook.dict(),
            headers={"X-Razorpay-Signature": "test_signature"}
        )
        
        # In debug mode, signature is not verified
        assert response.status_code == 202  # Accepted
        data = response.json()
        assert data["status"] == "accepted"
        assert "event_id" in data
        assert "processing_timestamp" in data
    
    def test_webhook_rejects_invalid_json(self):
        """Test webhook rejects invalid JSON"""
        response = client.post(
            "/webhooks/payment-failure",
            data="invalid json",
            headers={"X-Razorpay-Signature": "test_signature"}
        )
        
        assert response.status_code == 400
    
    def test_webhook_rejects_missing_required_fields(self):
        """Test webhook rejects payload with missing required fields"""
        invalid_payload = {
            "id": "evt_test",
            # Missing event, created_at, data
        }
        
        response = client.post(
            "/webhooks/payment-failure",
            json=invalid_payload,
            headers={"X-Razorpay-Signature": "test_signature"}
        )
        
        assert response.status_code == 400


# ============================================================================
# DIAGNOSTIC API TESTS
# ============================================================================

class TestDiagnosticAPI:
    """Test suite for diagnostic API endpoints"""
    
    def test_classify_endpoint_gateway_timeout(self):
        """Test POST /api/v1/diagnostic/classify with gateway timeout"""
        webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
        
        response = client.post(
            "/api/v1/diagnostic/classify",
            json=webhook.dict()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["block"] == "BLOCK_1"
        assert data["root_cause"] == "GATEWAY_TIMEOUT"
        assert data["recovery_score"] > 0.80
    
    def test_classify_endpoint_expired_card(self):
        """Test POST /api/v1/diagnostic/classify with expired card"""
        webhook = create_test_webhook(error_code="CARD_EXPIRED")
        
        response = client.post(
            "/api/v1/diagnostic/classify",
            json=webhook.dict()
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["block"] == "BLOCK_3"
        assert data["recovery_score"] == 0.0
    
    def test_test_webhook_endpoint_all_codes(self):
        """Test GET /api/v1/diagnostic/test-webhook/{error_code} for various codes"""
        test_codes = [
            "GATEWAY_TIMEOUT",
            "INSUFFICIENT_FUNDS",
            "CARD_EXPIRED",
            "FRAUD_DECLINED",
            "NETWORK_ERROR"
        ]
        
        for code in test_codes:
            response = client.get(
                f"/api/v1/diagnostic/test-webhook/{code}"
            )
            
            assert response.status_code == 200, f"Failed for code {code}"
            data = response.json()
            assert data["root_cause"] == code
            assert data["block"] is not None
    
    def test_batch_classification_endpoint(self):
        """Test POST /api/v1/diagnostic/batch"""
        webhooks = [
            create_test_webhook(error_code="GATEWAY_TIMEOUT", invoice_id="inv_1"),
            create_test_webhook(error_code="CARD_EXPIRED", invoice_id="inv_2"),
            create_test_webhook(error_code="INSUFFICIENT_FUNDS", invoice_id="inv_3")
        ]
        
        response = client.post(
            "/api/v1/diagnostic/batch",
            json=[w.dict() for w in webhooks]
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["results"]) == 3


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """End-to-end integration tests"""
    
    def test_full_webhook_to_classification_flow(self):
        """Test complete flow: webhook receipt → classification → response"""
        webhook = create_test_webhook(
            error_code="GATEWAY_TIMEOUT",
            invoice_id="inv_integration_test",
            customer_id="cust_integration_test",
            amount=50000
        )
        
        # Step 1: Send webhook
        response = client.post(
            "/webhooks/payment-failure",
            json=webhook.dict(),
            headers={"X-Razorpay-Signature": "test"}
        )
        
        assert response.status_code == 202
        webhook_ack = response.json()
        assert webhook_ack["status"] == "accepted"
        
        # Step 2: Classify same payload via diagnostic endpoint
        response = client.post(
            "/api/v1/diagnostic/classify",
            json=webhook.dict()
        )
        
        assert response.status_code == 200
        classification = response.json()
        
        # Verify classification
        assert classification["invoice_id"] == "inv_integration_test"
        assert classification["block"] == "BLOCK_1"
        assert classification["recovery_score"] > 0.85
    
    def test_diverse_error_scenarios(self):
        """Test diverse error scenarios across all blocks"""
        scenarios = [
            ("GATEWAY_TIMEOUT", BlockType.BLOCK_1),
            ("INSUFFICIENT_FUNDS", BlockType.BLOCK_2),
            ("CARD_EXPIRED", BlockType.BLOCK_3),
            ("FRAUD_DECLINED", BlockType.BLOCK_3),
        ]
        
        for error_code, expected_block in scenarios:
            response = client.get(
                f"/api/v1/diagnostic/test-webhook/{error_code}"
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["block"] == expected_block.value, \
                f"{error_code} should route to {expected_block.value}"


# ============================================================================
# PERFORMANCE/LOAD TESTS
# ============================================================================

class TestPerformance:
    """Performance and load tests"""
    
    def test_diagnostic_classification_speed(self, diagnostic_engine_instance):
        """Test that classification completes in < 100ms"""
        import time
        
        webhook = create_test_webhook(error_code="GATEWAY_TIMEOUT")
        
        start = time.time()
        result = diagnostic_engine_instance.classify(webhook)
        end = time.time()
        
        elapsed_ms = (end - start) * 1000
        assert elapsed_ms < 100, f"Classification took {elapsed_ms:.2f}ms"
    
    @pytest.mark.skip(reason="Performance test - timing varies by system")
    def test_batch_throughput(self, diagnostic_engine_instance):
        """Test batch classification throughput (50+ payloads)"""
        pass

# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    # Run all tests with: pytest Day1_tests.py -v
    # Or: pytest Day1_tests.py -v --tb=short
    
    print("\n" + "="*80)
    print("RecovAI - Day 1 Test Suite")
    print("="*80 + "\n")
    
    pytest.main([__file__, "-v", "--tb=short"])
