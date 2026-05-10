# bestman/dynahmrc/core/observation.py
"""
Observation Module - Scene graph and robot state perception
Integrated with BestMan perception APIs
"""

from typing import Dict, List, Any, Optional
import numpy as np

class ObservationModule:
    """
    Manages robot observations including scene graph, robot states, and messages
    Compatible with BestMan perception component
    """
    
    def __init__(self, robot_agent):
        self.robot = robot_agent
        self.scene_graph = {}
        self.robot_states = {}
        self.message_buffer = []
        
    def update_scene_graph(self, env_data: Dict):
        """Update scene graph from environment data"""
        self.scene_graph = {
            'furniture': env_data.get('furniture', {}),
            'objects': env_data.get('objects', {}),
            'containers': env_data.get('containers', {})
        }
        
        # Add stand poses for navigation targets
        for obj_name, obj_data in self.scene_graph['furniture'].items():
            if 'position' in obj_data:
                # Calculate stand poses around furniture
                obj_data['stand_poses'] = self._calculate_stand_poses(obj_data['position'])
    
    def _calculate_stand_poses(self, position: List[float]) -> List[List[float]]:
        """Calculate navigation target poses around an object"""
        # Generate poses at 0.8m distance in 4 directions
        poses = []
        distance = 0.8
        for angle in [0, 90, 180, 270]:
            rad = np.radians(angle)
            x = position[0] + distance * np.cos(rad)
            y = position[1] + distance * np.sin(rad)
            # Orientation facing the object
            yaw = angle + 180  # Face toward object
            poses.append([x, y, 0, 0, 0, np.radians(yaw)])
        return poses
    
    def get_scene_graph(self) -> Dict:
        """Get current scene graph"""
        return self.scene_graph
    
    def get_robot_pose(self) -> List[float]:
        """Get current robot pose from BestMan"""
        if self.robot.bestman_robot and hasattr(self.robot.bestman_robot, 'get_robot_pose'):
            return self.robot.bestman_robot.get_robot_pose()
        return [0, 0, 0, 0, 0, 0]
    
    def get_observation_for_llm(self) -> Dict:
        """Format observation for LLM prompt"""
        return {
            'scene_graph': self._format_scene_graph(),
            'robot_status': self._format_robot_status(),
            'messages': self.message_buffer[-3:]  # Last 3 messages
        }
    
    def _format_scene_graph(self) -> str:
        """Format scene graph as text for LLM"""
        lines = []
        for category, items in self.scene_graph.items():
            lines.append(f"{category.upper()}:")
            for name, data in items.items():
                status = data.get('state', 'unknown')
                pos = data.get('position', [])
                lines.append(f"  - {name}: pos={pos}, state={status}")
        return '\n'.join(lines)
    
    def _format_robot_status(self) -> str:
        """Format robot status as text"""
        pose = self.get_robot_pose()
        status = {
            'position': pose[:3],
            'orientation': pose[3:],
            'capabilities': self.robot.capabilities
        }
        
        if 'pick' in self.robot.capabilities:
            status['gripper'] = self._get_gripper_status()
        
        return str(status)
    
    def _get_gripper_status(self) -> Dict:
        """Get gripper state from BestMan"""
        if self.robot.bestman_robot and hasattr(self.robot.bestman_robot, 'get_gripper_state'):
            return self.robot.bestman_robot.get_gripper_state()
        return {'open': True, 'grasped_object': None}
    
    def receive_message(self, from_robot: str, content: str):
        """Receive message from another robot"""
        self.message_buffer.append({
            'from': from_robot,
            'content': content,
            'timestamp': len(self.message_buffer)
        })