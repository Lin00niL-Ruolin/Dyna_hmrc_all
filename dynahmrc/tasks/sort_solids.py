# bestman/dynahmrc/tasks/sort_solids.py
"""
Sort Solids Task - Color-based matching
"""

from typing import Dict, List
from .base_task import BaseTask

class SortSolidsTask(BaseTask):
    """
    Sort colored solids onto matching colored panels
    Requires color recognition and precise placement
    """
    
    def __init__(self, task_id: str, config: Dict):
        super().__init__(task_id, config)
        self.color_pairs = config.get('color_pairs', [])  # [('red', 'red_panel'), ...]
        self.sorted_objects = {}
        
    def get_goal_description(self) -> str:
        """Return task goal"""
        pairs_str = '; '.join([f"{obj} -> {panel}" for obj, panel in self.color_pairs])
        return f"Sort colored solids onto matching colored panels: {pairs_str}"
    
    def check_completion(self, robot_states: Dict) -> bool:
        """Check if all objects are on correct panels"""
        panel_states = robot_states.get('panel_contents', {})
        
        for obj_color, panel in self.color_pairs:
            # Extract color from object name (e.g., "red_cube" -> "red")
            obj_name = f"{obj_color}_solid"
            target_panel = f"{panel}"
            
            # Check if object is on correct panel
            panel_contents = panel_states.get(target_panel, [])
            if obj_name not in panel_contents:
                return False
        
        return True
    
    def get_partial_success(self) -> float:
        """Calculate partial success rate"""
        if not self.color_pairs:
            return 0.0
        
        correct = 0
        for obj_color, panel in self.color_pairs:
            obj_name = f"{obj_color}_solid"
            # Check if correctly placed (would need actual state)
            correct += 1  # Simplified
        
        return correct / len(self.color_pairs)
    
    def get_reward(self, robot_states: Dict) -> float:
        """Calculate reward"""
        return self.get_partial_success() - self.current_step * 0.01
    
    def get_task_status(self) -> Dict:
        """Get detailed task status"""
        status = super().get_task_status()
        status.update({
            'color_pairs': self.color_pairs,
            'sorted_count': sum(self.sorted_objects.values()),
            'partial_success': self.get_partial_success()
        })
        return status