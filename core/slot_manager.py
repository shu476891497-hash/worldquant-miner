"""
Slot Manager for Concurrent Simulations
Manages 8 simulation slots with GLB taking 2 slots, others taking 1 slot
"""

import logging
import threading
import time
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class SlotStatus(Enum):
    """Slot status"""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Slot:
    """Represents a simulation slot"""
    slot_id: int
    status: SlotStatus = SlotStatus.IDLE
    template: Optional[str] = None
    region: Optional[str] = None
    progress_url: Optional[str] = None
    alpha_id: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    result: Optional[Dict] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
    log_buffer: deque = field(default_factory=lambda: deque(maxlen=200))  # Last 200 log lines (increased for full history)
    progress_percent: float = 0.0  # Progress percentage (0-100)
    progress_message: str = ""  # Current progress message
    api_status: str = ""  # Status from API (PENDING, RUNNING, COMPLETE, etc.)
    
    def add_log(self, message: str):
        """Add log message to buffer"""
        # Ensure message is a string, not a tuple
        if isinstance(message, (tuple, list)):
            message = ' '.join(str(m) for m in message) if message else ''
        elif message is None:
            message = ''
        else:
            message = str(message)
        timestamp = time.strftime("%H:%M:%S")
        self.log_buffer.append(f"[{timestamp}] {message}")
    
    def get_logs(self) -> List[str]:
        """Get all log messages"""
        return list(self.log_buffer)
    
    def update_progress(self, percent: float, message: str = "", api_status: str = ""):
        """Update progress information"""
        # Ensure percent is a float (handle string inputs from API)
        try:
            percent = float(percent)
        except (ValueError, TypeError):
            logger.warning(f"Invalid percent value: {percent}, using 0.0")
            percent = 0.0
        self.progress_percent = max(0.0, min(100.0, percent))
        if message:
            self.progress_message = message
        if api_status:
            self.api_status = api_status


class SlotManager:
    """
    Manages 8 concurrent simulation slots
    
    Rules:
    - GLB region takes 2 slots
    - Other regions take 1 slot
    - Maximum 8 slots total
    """
    
    def __init__(self, max_slots: int = 8):
        """
        Initialize slot manager
        
        Args:
            max_slots: Maximum number of slots (default: 8)
        """
        self.max_slots = max_slots
        self.slots: List[Slot] = [Slot(slot_id=i) for i in range(max_slots)]
        self.lock = threading.Lock()
        self.slot_assignments: Dict[int, int] = {}  # {template_index: slot_id}
        
    def get_slots_required(self, region: str) -> int:
        """
        Get number of slots required for a region
        
        Args:
            region: Region code
            
        Returns:
            Number of slots required (1 for most, 2 for GLB)
        """
        return 2 if region == "GLB" else 1
    
    def find_available_slots(self, num_slots: int) -> Optional[List[int]]:
        """
        Find available consecutive slots
        
        Args:
            num_slots: Number of slots needed
            
        Returns:
            List of available slot IDs or None if not available
        """
        with self.lock:
            # Try to find consecutive available slots
            for start in range(self.max_slots - num_slots + 1):
                if all(self.slots[start + i].status == SlotStatus.IDLE for i in range(num_slots)):
                    return list(range(start, start + num_slots))
            return None
    
    def assign_slot(self, template: str, region: str, template_index: int) -> Optional[List[int]]:
        """
        Assign slot(s) to a simulation
        
        Args:
            template: Template expression
            region: Region code
            template_index: Index of template in queue
            
        Returns:
            List of assigned slot IDs or None if no slots available
        """
        num_slots = self.get_slots_required(region)
        slot_ids = self.find_available_slots(num_slots)
        
        if not slot_ids:
            return None
        
        with self.lock:
            for slot_id in slot_ids:
                slot = self.slots[slot_id]
                slot.status = SlotStatus.RUNNING
                slot.template = template
                slot.region = region
                slot.start_time = time.time()
                slot.add_log(f"🚀 Starting simulation: {template[:50]}...")
                slot.add_log(f"Region: {region}, Slots: {num_slots}")
            
            self.slot_assignments[template_index] = slot_ids[0]  # Store primary slot
        
        return slot_ids
    
    def release_slot(self, slot_id: int, success: bool = True, result: Optional[Dict] = None, error: Optional[str] = None):
        """
        Release a slot after simulation completes
        
        Args:
            slot_id: Slot ID to release
            success: Whether simulation succeeded
            result: Simulation result if successful
            error: Error message if failed
        """
        with self.lock:
            slot = self.slots[slot_id]
            slot.end_time = time.time()
            slot.status = SlotStatus.COMPLETED if success else SlotStatus.FAILED
            slot.result = result
            slot.error = error
            
            if success and result:
                alpha_id = result.get('alpha_id', '') if isinstance(result, dict) else ''
                # Ensure alpha_id is a string, not a tuple or list
                if isinstance(alpha_id, (tuple, list)):
                    alpha_id = str(alpha_id[0]) if alpha_id and len(alpha_id) > 0 else ''
                elif alpha_id is None:
                    alpha_id = ''
                else:
                    alpha_id = str(alpha_id)
                # Final safety check - ensure alpha_id is always a string
                if isinstance(alpha_id, (tuple, list)):
                    alpha_id = str(alpha_id[0]) if alpha_id and len(alpha_id) > 0 else ''
                elif alpha_id is None:
                    alpha_id = ''
                else:
                    alpha_id = str(alpha_id)
                slot.alpha_id = alpha_id
                # Ensure message is a string before logging
                alpha_id_str = str(slot.alpha_id) if slot.alpha_id else ''
                slot.add_log(f"✅ SUCCESS - Alpha ID: {alpha_id_str}")
                if isinstance(result, dict) and 'returns' in result:
                    slot.add_log(f"   Returns: {result['returns']:.4f}, Sharpe: {result.get('sharpe', 0):.4f}")
            elif error:
                slot.add_log(f"❌ FAILED: {error}")
            
            # Reset slot after a delay (to show results)
            def reset_slot():
                time.sleep(2)  # Show result for 2 seconds
                with self.lock:
                    slot.status = SlotStatus.IDLE
                    slot.template = None
                    slot.region = None
                    slot.progress_url = None
                    slot.alpha_id = None
                    slot.start_time = None
                    slot.end_time = None
                    slot.result = None
                    slot.error = None
                    slot.thread = None
                    slot.log_buffer.clear()
            
            threading.Thread(target=reset_slot, daemon=True).start()
    
    def release_slots(self, slot_ids: List[int], success: bool = True, result: Optional[Dict] = None, error: Optional[str] = None):
        """Release multiple slots (for GLB which uses 2 slots)"""
        for slot_id in slot_ids:
            self.release_slot(slot_id, success, result, error)
    
    def update_slot_progress(self, slot_id: int, progress_url: str = None, percent: float = None, message: str = "", api_status: str = ""):
        """
        Update slot with progress information
        
        Args:
            slot_id: Slot ID
            progress_url: Optional progress URL from submission
            percent: Optional progress percentage (0-100)
            message: Optional progress message
            api_status: Optional API status (PENDING, RUNNING, COMPLETE, etc.)
        """
        with self.lock:
            slot = self.slots[slot_id]
            if progress_url:
                slot.progress_url = progress_url
            if percent is not None:
                slot.update_progress(percent, message, api_status)
            if message:
                slot.add_log(message)
            elif progress_url:
                slot.add_log(f"✅ Submitted: {progress_url}")
    
    def get_slot_status(self, slot_id: int) -> Slot:
        """Get current status of a slot"""
        with self.lock:
            return self.slots[slot_id]
    
    def get_all_slots_status(self) -> List[Slot]:
        """Get status of all slots"""
        with self.lock:
            return [slot for slot in self.slots]
    
    def get_active_slots_count(self) -> int:
        """Get number of active (running) slots"""
        with self.lock:
            return sum(1 for slot in self.slots if slot.status == SlotStatus.RUNNING)
    
    def get_available_slots_count(self) -> int:
        """Get number of available slots (considering GLB takes 2)"""
        # This is a simplified calculation - actual availability depends on slot layout
        with self.lock:
            idle_count = sum(1 for slot in self.slots if slot.status == SlotStatus.IDLE)
            # Can fit at least idle_count single-slot simulations
            # Or idle_count // 2 GLB simulations
            return idle_count
