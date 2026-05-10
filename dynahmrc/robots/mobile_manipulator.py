# bestman/dynahmrc/robots/mobile_manipulator.py
"""
Mobile Manipulation Robot - Wheeled base + robotic arm
Example: BestMan mobile manipulator
"""

from typing import Dict, List
from ..core.agent import RobotAgent

class MobileManipulatorRobot(RobotAgent):
    """
    Mobile Manipulation Robot (MoMa)
    Capabilities: navigate, pick, place, open, move, communicate, wait
    """
    
    def __init__(self, name: str, llm_client, bestman_robot=None, config=None):
        super().__init__(
            name=name,
            robot_type="mobile_manipulation",
            capabilities=["navigate", "pick", "place", "open", "move", "communicate", "wait"],
            llm_client=llm_client,
            bestman_robot=bestman_robot,
            config=config
        )
        
        # Mobile manipulation specific config
        self.max_grasp_range = config.get('max_grasp_range', 0.8) if config else 0.8
        self.navigation_speed = config.get('navigation_speed', 1.0) if config else 1.0
    
    def get_principles(self) -> str:
        """Return robot-specific principles for prompt"""
        return """
1) Efficiently explore and navigate all locations in the scene graph without repetition
2) Transport task-related items promptly
3) When facing inaccessible areas, notify capable assistants
4) Track task progress and adjust targets timely
5) Respond promptly to collaborators' requests
6) If grasp fails, try other stand poses or adjust base position using 'move'
7) Focus on completing the task without unrelated actions
"""