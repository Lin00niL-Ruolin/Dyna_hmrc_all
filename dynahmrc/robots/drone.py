# bestman/dynahmrc/robots/drone.py
"""
Drone Robot - Aerial manipulation
"""

from typing import Dict, List
from ..core.agent import RobotAgent

class DroneRobot(RobotAgent):
    """
    Drone Robot (UAV) - Aerial navigation and manipulation
    Capabilities: navigate, pick, place, communicate, wait
    Can access high areas and hard-to-reach locations
    """
    
    def __init__(self, name: str, llm_client, bestman_robot=None, config=None):
        super().__init__(
            name=name,
            robot_type="drone",
            capabilities=["navigate", "pick", "place", "communicate", "wait"],
            llm_client=llm_client,
            bestman_robot=bestman_robot,
            config=config
        )
        
        self.max_grasp_range = config.get('max_grasp_range', 0.3) if config else 0.3
        self.can_access = config.get('can_access', ["high_areas", "hard_to_reach"]) if config else ["high_areas", "hard_to_reach"]
    
    def get_principles(self) -> str:
        """Return robot-specific principles for prompt"""
        return """
1) Efficiently explore and navigate all locations, especially high or hard-to-reach areas
2) Transport task-related items promptly from aerial positions
3) Request collaborators to open objects for exploration when needed
4) Track task progress and adjust targets timely
5) Respond promptly to collaborators' requests
6) Focus on task completion without unrelated actions
"""
    
    def _is_object_reachable(self, obj_name: str) -> bool:
        """Drone can reach high areas that other robots cannot"""
        # Check if object is in high area
        scene_graph = self.observation.get_scene_graph()
        if obj_name in scene_graph.get('objects', {}):
            obj_data = scene_graph['objects'][obj_name]
            height = obj_data.get('position', [0, 0, 0])[2]
            # Drone can reach objects above 1.5m (on top of furniture)
            if height > 1.5:
                return True
        
        # For normal height objects, use standard reachability check
        return super()._is_object_reachable(obj_name)