# bestman/dynahmrc/tasks/pack_objects.py
"""
Pack Objects Task - Fundamental picking and placing
"""

from typing import Dict, List
from .base_task import BaseTask

class PackObjectsTask(BaseTask):
    """
    Pack objects into a designated tray
    Evaluates basic manipulation capabilities
    """
    
    def __init__(self, task_id: str, config: Dict):
        super().__init__(task_id, config)
        self.target_objects = config.get('target_objects', [])
        self.target_container = config.get('target_container', 'tray')
        self.placed_objects = []
        
    def get_goal_description(self) -> str:
        """Return task goal"""
        objects_str = ', '.join(self.target_objects)
        return f"Pack the following objects into the {self.target_container}: {objects_str}"
    
    def check_completion(self, robot_states: Dict) -> bool:
        """Check if all objects are in tray"""
        # Check container contents from scene graph
        container_contents = robot_states.get('container_contents', {}).get(self.target_container, [])
        self.placed_objects = container_contents
        
        # Check if all target objects are placed
        return all(obj in container_contents for obj in self.target_objects)
    
    def get_partial_success(self) -> float:
        """Calculate partial success rate"""
        if not self.target_objects:
            return 0.0
        placed = sum(1 for obj in self.target_objects if obj in self.placed_objects)
        return placed / len(self.target_objects)
    
    def get_reward(self, robot_states: Dict) -> float:
        """Calculate reward based on progress"""
        completion = self.get_partial_success()
        step_penalty = self.current_step * 0.01
        return completion - step_penalty
    
    def get_task_status(self) -> Dict:
        """Get detailed task status"""
        status = super().get_task_status()
        status.update({
            'target_objects': self.target_objects,
            'placed_objects': self.placed_objects,
            'target_container': self.target_container,
            'partial_success': self.get_partial_success()
        })
        return status
    
    def inject_cto(self, new_objects: List[str]):
        """Change Task Objective - modify target objects"""
        self.target_objects = new_objects
        self.pending_changes.append({
            'type': 'CTO',
            'description': f'Target objects changed to: {new_objects}'
        })