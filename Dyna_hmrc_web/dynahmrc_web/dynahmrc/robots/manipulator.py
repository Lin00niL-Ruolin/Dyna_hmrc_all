# bestman/dynahmrc/robots/manipulator.py
"""
Fixed Manipulation Robot - Desktop robotic arm
"""

from typing import Dict, List
from ..core.agent import RobotAgent

class ManipulatorRobot(RobotAgent):
    """
    Manipulation Robot (Ma) - Fixed base
    Capabilities: pick, place, communicate, wait
    """
    
    def __init__(self, name: str, llm_client, bestman_robot=None, config=None):
        super().__init__(
            name=name,
            robot_type="manipulation",
            capabilities=["pick", "place", "communicate", "wait"],
            llm_client=llm_client,
            bestman_robot=bestman_robot,
            config=config
        )
        
        self.workspace = config.get('workspace', 'desktop') if config else 'desktop'
        self.max_grasp_range = config.get('max_grasp_range', 0.5) if config else 0.5
    
    def get_principles(self) -> str:
        """Return robot-specific principles for prompt"""
        return """
1) Analyze tasks and scene graphs, prioritizing your work
2) Request help promptly for distant or missing objects
3) Notify collaborators of task progress timely
4) Track progress changes and adjust targets as needed
5) Respond promptly to collaborators' requests
6) Focus on task completion without unrelated actions
"""