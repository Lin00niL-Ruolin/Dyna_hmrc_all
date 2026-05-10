# bestman/dynahmrc/core/memory.py
"""
Memory Module - Historical context management for LLM reasoning
"""

from typing import Dict, List, Any, Deque
from collections import deque

class MemoryModule:
    """
    Manages feedback history, message history, and action history
    Maintains sliding window of recent interactions
    """
    
    def __init__(self, max_history: int = 10):
        self.max_history = max_history
        
        # Circular buffers for history
        self.feedback_history: Deque[Dict] = deque(maxlen=max_history)
        self.message_history: Deque[Dict] = deque(maxlen=max_history)
        self.action_history: Deque[Dict] = deque(maxlen=max_history)
        
        # Persistent storage
        self.self_description = ""
        self.task_plan = {}
        self.reflection_summaries = []
        
    def store_feedback(self, feedback: Dict):
        """Store environment feedback"""
        self.feedback_history.append({
            'step': len(self.action_history),
            **feedback
        })
    
    def store_action(self, action: Dict, feedback: Dict):
        """Store executed action and its feedback"""
        self.action_history.append({
            'step': len(self.action_history),
            'action': action,
            'feedback': feedback
        })
        self.store_feedback(feedback)
    
    def store_message(self, from_robot: str, content: str):
        """Store received message"""
        self.message_history.append({
            'from': from_robot,
            'content': content,
            'timestamp': len(self.action_history)
        })
    
    def store_self_description(self, description: str):
        """Store self-introduction"""
        self.self_description = description
    
    def store_task_plan(self, plan: Dict):
        """Store assigned task plan"""
        self.task_plan = plan
    
    def get_recent_history(self, k: int = 5) -> List[Dict]:
        """Get recent k steps of history"""
        recent = []
        for i in range(min(k, len(self.action_history))):
            idx = len(self.action_history) - 1 - i
            recent.append({
                'action': list(self.action_history)[idx],
                'feedback': list(self.feedback_history)[idx] if idx < len(self.feedback_history) else None
            })
        return list(reversed(recent))
    
    def get_action_history(self) -> List[Dict]:
        """Get full action history"""
        return list(self.action_history)
    
    def get_message_history(self) -> List[Dict]:
        """Get message history"""
        return list(self.message_history)
    
    def format_history_for_prompt(self, k: int = 5) -> str:
        """Format history as text for LLM prompt"""
        recent = self.get_recent_history(k)
        lines = ["Recent Actions:"]
        
        for item in recent:
            action = item['action']['action']
            feedback = item['feedback']
            lines.append(f"  Step {item['action']['step']}: {action}")
            if feedback:
                lines.append(f"    -> {feedback.get('message', 'No feedback')}")
        
        return '\n'.join(lines)