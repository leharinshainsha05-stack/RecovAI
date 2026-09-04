"""
RecovAI: Immutable Audit Ledger
Day 2: Cryptographic hash chain for audit trail integrity
"""

import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import logging
import uuid

from sqlalchemy.orm import Session

from Day2_database import (
    AuditLog, ActionTypeEnum, BlockTypeEnum, 
    RootCauseEnum, RecoveryStateEnum
)


logger = logging.getLogger(__name__)


# ============================================================================
# AUDIT LEDGER WITH HASH CHAIN
# ============================================================================

class AuditLedger:
    """
    Immutable audit ledger with cryptographic SHA256 hash chain.
    
    Every event is logged with a hash of the current event and previous event hash.
    This creates an unbreakable chain - tampering with any event breaks the chain.
    
    Hash Chain Example:
    Event 1: hash = SHA256(json_serialize(event1))
    Event 2: hash = SHA256(json_serialize(event2) + event1_hash)
    Event 3: hash = SHA256(json_serialize(event3) + event2_hash)
    
    If Event 2 is modified, Event 2's hash changes, breaking the chain for Event 3.
    """
    
    def __init__(self):
        """Initialize audit ledger"""
        logger.info("✓ AuditLedger initialized")
    
    @staticmethod
    def _serialize_event(event_dict: Dict[str, Any]) -> str:
        """
        Serialize event to canonical JSON for hashing.
        
        Args:
            event_dict: Event data
            
        Returns:
            JSON string (sorted keys for consistency)
        """
        # Remove hash fields before serialization (not part of event data)
        serializable = {k: v for k, v in event_dict.items() 
                       if k not in ['audit_hash', 'prev_audit_hash', 'id']}
        
        # Sort keys for deterministic JSON
        return json.dumps(serializable, sort_keys=True, default=str)
    
    @staticmethod
    def _calculate_hash(
        event_json: str,
        prev_hash: Optional[str] = None
    ) -> str:
        """
        Calculate SHA256 hash of event.
        
        Args:
            event_json: Serialized event JSON
            prev_hash: Previous event's hash (for chain linkage)
            
        Returns:
            SHA256 hex digest (64 characters)
        """
        # Combine current event with previous hash
        data_to_hash = event_json
        if prev_hash:
            data_to_hash += prev_hash
        
        # Calculate SHA256
        hash_obj = hashlib.sha256(data_to_hash.encode())
        return hash_obj.hexdigest()
    
    def log_event(
        self,
        session: Session,
        invoice_id: str,
        customer_id: str,
        action: ActionTypeEnum,
        block: Optional[BlockTypeEnum] = None,
        root_cause: Optional[RootCauseEnum] = None,
        error_code: Optional[str] = None,
        state_before: Optional[RecoveryStateEnum] = None,
        state_after: Optional[RecoveryStateEnum] = None,
        transaction_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        """
        Log an audit event with cryptographic hash.
        """
        # Generate event ID and single timestamp source of truth
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        now_iso = now.isoformat()
        
        # Prepare event data
        event_data = {
            "event_id": event_id,
            "timestamp": now_iso,
            "invoice_id": invoice_id,
            "customer_id": customer_id,
            "action": action.value if hasattr(action, "value") else str(action),
            "block": block.value if hasattr(block, "value") and block else None,
            "root_cause": root_cause.value if hasattr(root_cause, "value") and root_cause else None,
            "error_code": error_code,
            "state_before": state_before.value if hasattr(state_before, "value") and state_before else None,
            "state_after": state_after.value if hasattr(state_after, "value") and state_after else None,
            "transaction_id": transaction_id,
            "details": details or {},
        }
        
        # Serialize event
        event_json = self._serialize_event(event_data)
        
        # Get previous event's hash (for chain linkage)
        prev_log = session.query(AuditLog).filter(
            AuditLog.invoice_id == invoice_id
        ).order_by(AuditLog.id.desc()).first()
        
        prev_hash = prev_log.audit_hash if prev_log else None
        
        # Calculate hash
        current_hash = self._calculate_hash(event_json, prev_hash)
        
        # Create audit log entry using the exact same 'now' timestamp
        log_entry = AuditLog(
            event_id=event_id,
            timestamp=now,
            invoice_id=invoice_id,
            customer_id=customer_id,
            transaction_id=transaction_id,
            action=action,
            block=block,
            root_cause=root_cause,
            error_code=error_code,
            state_before=state_before,
            state_after=state_after,
            details=details or {},
            audit_hash=current_hash,
            prev_audit_hash=prev_hash,
        )
        
        session.add(log_entry)
        
        logger.info(
            f"✓ Audit event logged: {event_id} "
            f"({action.value if hasattr(action, 'value') else action}) "
            f"[hash: {current_hash[:16]}...]"
        )
        
        return log_entry
    
    def verify_chain_integrity(
        self,
        session: Session,
        invoice_id: str
    ) -> tuple[bool, str]:
        """
        Verify the integrity of the entire audit chain for an invoice.
        
        Steps:
        1. Fetch all audit logs for invoice
        2. Recalculate hash for each event
        3. Verify each hash matches stored hash
        4. Verify prev_hash references are correct
        
        Args:
            session: SQLAlchemy session
            invoice_id: Invoice ID
            
        Returns:
            (is_valid: bool, message: str)
        """
        # Fetch all logs for invoice (ordered by ID)
        logs = session.query(AuditLog).filter(
            AuditLog.invoice_id == invoice_id
        ).order_by(AuditLog.id.asc()).all()
        
        if not logs:
            return True, "No audit logs to verify"
        
        logger.info(f"🔍 Verifying audit chain for {invoice_id} ({len(logs)} events)")
        
        # Verify each event
        for i, log in enumerate(logs):
            # Prepare event data for re-hashing
            event_data = {
                "event_id": log.event_id,
                "timestamp": log.timestamp.isoformat() if hasattr(log.timestamp, "isoformat") else str(log.timestamp),
                "invoice_id": log.invoice_id,
                "customer_id": log.customer_id,
                "action": log.action.value if hasattr(log.action, "value") else str(log.action),
                "block": log.block.value if hasattr(log.block, "value") and log.block else None,
                "root_cause": log.root_cause.value if hasattr(log.root_cause, "value") and log.root_cause else None,
                "error_code": log.error_code,
                "state_before": log.state_before.value if hasattr(log.state_before, "value") and log.state_before else None,
                "state_after": log.state_after.value if hasattr(log.state_after, "value") and log.state_after else None,
                "transaction_id": log.transaction_id,
                "details": log.details or {},
            }
            
            # Serialize
            event_json = self._serialize_event(event_data)
            
            # Get previous hash
            prev_hash = logs[i-1].audit_hash if i > 0 else None
            
            # Recalculate hash
            expected_hash = self._calculate_hash(event_json, prev_hash)
            
            # Verify hash matches
            if expected_hash != log.audit_hash:
                msg = (
                    f"❌ Hash mismatch at event {i+1} ({log.event_id}): "
                    f"expected {expected_hash[:16]}... "
                    f"got {log.audit_hash[:16]}..."
                )
                logger.error(msg)
                return False, msg
            
            # Verify prev_hash reference
            if i > 0:
                if log.prev_audit_hash != logs[i-1].audit_hash:
                    msg = (
                        f"❌ Chain link broken at event {i+1} ({log.event_id}): "
                        f"prev_hash mismatch"
                    )
                    logger.error(msg)
                    return False, msg
            else:
                if log.prev_audit_hash is not None:
                    msg = (
                        f"❌ First event has prev_hash set "
                        f"({log.event_id})"
                    )
                    logger.error(msg)
                    return False, msg
        
        msg = f"✓ Audit chain verified successfully ({len(logs)} events)"
        logger.info(msg)
        return True, msg
    
    def get_audit_trail(
        self,
        session: Session,
        invoice_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve audit trail for an invoice.
        
        Args:
            session: SQLAlchemy session
            invoice_id: Invoice ID
            limit: Max number of events to return
            
        Returns:
            List of audit events as dicts
        """
        query = session.query(AuditLog).filter(
            AuditLog.invoice_id == invoice_id
        ).order_by(AuditLog.id.asc())
        
        if limit:
            query = query.limit(limit)
        
        logs = query.all()
        
        return [
            {
                "event_id": log.event_id,
                "timestamp": log.timestamp.isoformat() if hasattr(log.timestamp, "isoformat") else str(log.timestamp),
                "action": log.action.value if hasattr(log.action, "value") and log.action else None,
                "block": log.block.value if hasattr(log.block, "value") and log.block else None,
                "root_cause": log.root_cause.value if hasattr(log.root_cause, "value") and log.root_cause else None,
                "state_before": log.state_before.value if hasattr(log.state_before, "value") and log.state_before else None,
                "state_after": log.state_after.value if hasattr(log.state_after, "value") and log.state_after else None,
                "details": log.details,
                "hash": log.audit_hash[:16] + "...",
            }
            for log in logs
        ]


# ============================================================================
# EXAMPLE USAGE & TESTING
# ============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("RecovAI Audit Ledger - Day 2 Test")
    print("="*80 + "\n")
    
    ledger = AuditLedger()
    
    # Test hash calculation
    print("Testing Hash Calculation:")
    print("-" * 60)
    
    event1 = {
        "event_id": "evt_001",
        "action": "WEBHOOK_RECEIVED",
        "invoice_id": "inv_001",
    }
    
    event1_json = ledger._serialize_event(event1)
    event1_hash = ledger._calculate_hash(event1_json)
    
    print(f"Event 1 JSON: {event1_json}")
    print(f"Event 1 Hash: {event1_hash}")
    print()
    
    event2 = {
        "event_id": "evt_002",
        "action": "DIAGNOSED",
        "invoice_id": "inv_001",
    }
    
    event2_json = ledger._serialize_event(event2)
    event2_hash = ledger._calculate_hash(event2_json, event1_hash)
    
    print(f"Event 2 JSON: {event2_json}")
    print(f"Event 2 Hash (with chain): {event2_hash}")
    print()
    
    # Test chain integrity
    print("Testing Chain Integrity:")
    print("-" * 60)
    
    # Create 3 events
    events = []
    for i in range(3):
        event_data = {
            "event_id": f"evt_{i+1:03d}",
            "action": "TEST_ACTION",
            "invoice_id": "inv_001",
        }
        event_json = ledger._serialize_event(event_data)
        
        prev_hash = events[i-1]['hash'] if i > 0 else None
        current_hash = ledger._calculate_hash(event_json, prev_hash)
        
        events.append({
            'id': i+1,
            'event_id': event_data['event_id'],
            'hash': current_hash,
            'prev_hash': prev_hash,
            'data': event_data
        })
        
        print(f"Event {i+1}: {current_hash[:20]}... (prev: {prev_hash[:20] if prev_hash else 'None'}...)")
    
    print("\n✓ Hash chain created successfully")
    print("="*80 + "\n")
