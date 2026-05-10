# bestman/dynahmrc/tasks/make_sandwich.py
"""
Make Sandwich Task - Sequential stacking
"""

from typing import Dict, List
from .base_task import BaseTask

class MakeSandwichTask(BaseTask):
    """
    Assemble sandwich by stacking ingredients in specific order
    Tests sequential manipulation and ordering constraints
    """
    
    def __init__(self, task_id: str, config: Dict):
        super().__init__(task_id, config)
        self.ingredient_order = config.get('ingredient_order', [])  # ['bread', 'lettuce', 'tomato', 'bread']
        self.target_location = config.get('target_location', 'cutting_board')
        self.current_stack = []
        
    def get_goal_description(self) -> str:
        """Return task goal"""
        order_str = ' -> '.join(self.ingredient_order)
        return f"Make a sandwich by stacking ingredients in order on {self.target_location}: {order_str}"
    
    def check_completion(self, robot_states: Dict) -> bool:
        """Check if sandwich is correctly assembled"""
        # Get current stack state from target location
        location_contents = robot_states.get('location_contents', {}).get(self.target_location, [])
        self.current_stack = location_contents
        
        # Check if stack matches required order
        return self.current_stack == self.ingredient_order
    
    def get_partial_success(self) -> float:
        """Calculate partial success based on correct prefix"""
        if not self.ingredient_order:
            return 0.0
        
        correct_prefix = 0
        for i, ingredient in enumerate(self.ingredient_order):
            if i < len(self.current_stack) and self.current_stack[i] == ingredient:
                correct_prefix += 1
            else:
                break
        
        return correct_prefix / len(self.ingredient_order)
    
    def get_reward(self, robot_states: Dict) -> float:
        """Calculate reward"""
        # Higher reward for correct order, penalty for wrong order
        if self.current_stack != self.ingredient_order[:len(self.current_stack)]:
            return -0.1  # Wrong order penalty
        
        return self.get_partial_success() - self.current_step * 0.01
    
    def get_task_status(self) -> Dict:
        """Get detailed task status"""
        status = super().get_task_status()
        status.update({
            'required_order': self.ingredient_order,
            'current_stack': self.current_stack,
            'partial_success': self.get_partial_success(),
            'target_location': self.target_location
        })
        return status
    
    def inject_cto(self, new_order: List[str]):
        """Change Task Objective - modify ingredient order"""
        # Handle partial completion when goal changes
        self.ingredient_order = new_order
        self.pending_changes.append({
            'type': 'CTO',
            'description': f'Ingredient order changed to: {new_order}',
            'requires_rework': len(self.current_stack) > 0
        })