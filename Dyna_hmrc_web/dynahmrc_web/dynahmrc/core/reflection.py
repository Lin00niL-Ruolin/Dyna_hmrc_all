# bestman/dynahmrc/core/reflection.py
"""
Reflection Module - Periodic team discussion and plan adjustment
"""

from typing import Dict, List, Tuple, Any

class ReflectionModule:
    """
    Manages periodic reflection and group discussion
    Triggered at fixed intervals during task execution
    """
    
    def __init__(self, reflection_interval: int = 10):
        self.interval = reflection_interval
        self.reflection_count = 0
        
    def should_reflect(self, step_count: int) -> bool:
        """Check if reflection should be triggered"""
        return step_count > 0 and step_count % self.interval == 0
    
    def conduct_reflection(self, robot_agents: List[Any]) -> Dict[str, Tuple[str, str]]:
        """
        Conduct group reflection among all robots
        Returns each robot's summary and future plan
        """
        reflections = {}
        
        # Each robot generates reflection
        for agent in robot_agents:
            team_history = self._aggregate_team_history(robot_agents)
            summary, future_plan = agent.reflect(team_history)
            reflections[agent.name] = (summary, future_plan)
        
        self.reflection_count += 1
        return reflections
    
    def _aggregate_team_history(self, robot_agents: List[Any]) -> Dict:
        """Aggregate history from all team members"""
        history = {
            'total_steps': max([a.step_count for a in robot_agents]),
            'robot_states': {},
            'messages_exchanged': []
        }
        
        for agent in robot_agents:
            history['robot_states'][agent.name] = {
                'actions': len(agent.memory.get_action_history()),
                'current_task': agent.task_plan
            }
        
        return history
    
    def update_team_plan(self, leader_agent: Any, reflections: Dict) -> Dict:
        """
        Leader integrates reflections and updates team plan
        """
        if not leader_agent.is_leader:
            return {}
        
        return leader_agent.update_leader_plan(reflections)