# bestman/dynahmrc/tasks/base_task.py
"""
Base Task Class - Common interface for all tasks
"""

from typing import Dict, List, Any
from abc import ABC, abstractmethod

class BaseTask(ABC):
    """
    Base class for collaborative tasks
    """
    
    def __init__(self, task_id: str, config: Dict):
        self.task_id = task_id
        self.config = config
        self.max_steps = config.get('max_steps', 100)
        self.reflection_interval = config.get('reflection_interval', 10)
        
        # Task state
        self.current_step = 0
        self.completed = False
        self.success_rate = 0.0
        
        # Dynamic variations
        self.variations = []
        self.pending_changes = []
    
    @abstractmethod
    def get_goal_description(self) -> str:
        """Return task goal description for LLM"""
        pass
    
    @abstractmethod
    def check_completion(self, robot_states: Dict) -> bool:
        """Check if task is completed"""
        pass
    
    @abstractmethod
    def get_reward(self, robot_states: Dict) -> float:
        """Calculate task reward"""
        pass
    
    def inject_variation(self, variation_type: str, params: Dict):
        """
        Inject dynamic task variation
        Types: CTO, IRZ, ANC, REC
        """
        self.pending_changes.append({
            'type': variation_type,
            'params': params,
            'step': self.current_step
        })
    
    def apply_pending_changes(self) -> List[Dict]:
        """Apply and return pending dynamic changes"""
        changes = self.pending_changes.copy()
        self.pending_changes = []
        self.variations.extend(changes)
        return changes
    
    def get_task_status(self) -> Dict:
        """Get current task status for feedback"""
        return {
            'task_id': self.task_id,
            'step': self.current_step,
            'max_steps': self.max_steps,
            'completed': self.completed,
            'variations_applied': len(self.variations)
        }
    
    def step(self):
        """Increment step counter"""
        self.current_step += 1
        return self.current_step < self.max_steps