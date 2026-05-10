# bestman/dynahmrc/robots/mobile_robot.py
"""
Mobile Robot - Pure navigation
"""

from typing import Dict, List
from ..core.agent import RobotAgent

class MobileRobot(RobotAgent):
    """
    Mobile Robot (Mo) - Wheeled base only
    Capabilities: navigate, communicate, wait
    """
    
    def __init__(self, name: str, llm_client, bestman_robot=None, config=None):
        super().__init__(
            name=name,
            robot_type="mobile",
            capabilities=["navigate", "communicate", "wait"],
            llm_client=llm_client,
            bestman_robot=bestman_robot,
            config=config
        )
        
        self.navigation_speed = config.get('navigation_speed', 1.2) if config else 1.2
    
    def get_principles(self) -> str:
        """Return robot-specific principles for prompt"""
        return """
1) Efficiently explore and navigate all locations in the scene graph without repetition
2) Notify collaborators of task items and request mobile teammates for transport
3) Notify capable assistants to explore inaccessible areas
4) Request collaborators to open objects for exploration
5) Track task progress and adjust targets timely
6) Respond promptly to assistants' messages
7) Focus on completing the task without unrelated actions
"""