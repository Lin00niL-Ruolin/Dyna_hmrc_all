# bestman/dynahmrc/core/agent.py
"""
Robot Agent - Core agent class for heterogeneous robot collaboration
Adapted for BestMan platform APIs
"""

import time
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

class CollaborationPhase(Enum):
    SELF_DESCRIPTION = "self_description"
    TASK_ALLOCATION = "task_allocation"
    LEADER_ELECTION = "leader_election"
    EXECUTION = "execution"
    REFLECTION = "reflection"

class RobotAgent:
    """
    Heterogeneous Robot Agent with LLM-based decision making
    Compatible with BestMan unified simulation-hardware APIs
    """
    
    def __init__(
        self,
        name: str,
        robot_type: str,
        capabilities: List[str],
        llm_client: Any,
        bestman_robot: Any = None,  # BestMan robot instance
        config: Dict = None
    ):
        self.name = name
        self.robot_type = robot_type
        self.capabilities = capabilities
        self.llm_client = llm_client
        self.bestman_robot = bestman_robot  # Reference to BestMan robot controller
        self.config = config or {}
        
        # Collaboration state
        self.current_phase = CollaborationPhase.SELF_DESCRIPTION
        self.is_leader = False
        self.leader_name = None
        self.teammates = {}
        self.task_plan = {}
        
        # Execution state
        self.current_action = None
        self.action_history = []
        self.step_count = 0
        
        # Modules (initialized externally)
        self.observation = None
        self.memory = None
        self.planner = None
        self.reflection = None
        self.communication = None
        
    def initialize_modules(self, observation, memory, planner, reflection, communication):
        """Initialize functional modules"""
        self.observation = observation
        self.memory = memory
        self.planner = planner
        self.reflection = reflection
        self.communication = communication
        
    def self_describe(self, task_context: Dict) -> str:
        """
        Stage 1: Self-Description
        Generate introduction based on capabilities and task context
        """
        prompt = self._build_self_description_prompt(task_context)
        
        response = self.llm_client.generate(
            prompt,
            temperature=self.config.get('temperature', 0.5)
        )
        
        description = self._parse_response(response)
        self.memory.store_self_description(description)
        
        return description
    
    def propose_allocation(self, teammates_descriptions: Dict[str, str]) -> Tuple[Dict, str]:
        """
        Stage 2: Task Allocation and Leadership Bidding
        Propose task division and campaign speech
        """
        prompt = self._build_allocation_prompt(teammates_descriptions)
        
        response = self.llm_client.generate(prompt)
        plan, speech = self._parse_allocation_response(response)
        
        return plan, speech
    
    def vote_leader(self, proposals: Dict[str, Tuple[Dict, str]]) -> str:
        """
        Stage 3: Leader Election
        Vote for the most capable leader based on proposals
        """
        prompt = self._build_election_prompt(proposals)
        
        response = self.llm_client.generate(prompt)
        leader_name = self._parse_leader_response(response)
        
        self.is_leader = (leader_name == self.name)
        self.leader_name = leader_name
        
        return leader_name
    
    def execute_step(self, observation_data: Dict, leader_plan: Dict) -> Dict:
        """
        Stage 4: Closed-Loop Execution
        Execute one atomic action based on observation and plan
        """
        # Update observation from BestMan sensors
        if self.bestman_robot:
            observation_data = self._get_bestman_observation(observation_data)
        
        # Build prompt with history and feedback
        prompt = self._build_execution_prompt(observation_data, leader_plan)
        
        # Get LLM decision
        response = self.llm_client.generate(prompt)
        action = self._parse_action_response(response)
        
        # Validate action against capabilities
        if not self._validate_action(action):
            action = self._fallback_action()
        
        # Execute via BestMan APIs
        feedback = self._execute_action(action)
        
        # Update memory
        self.memory.store_action(action, feedback)
        self.step_count += 1
        
        return {
            'action': action,
            'feedback': feedback,
            'step': self.step_count
        }
    
    def reflect(self, team_history: Dict) -> Tuple[str, str]:
        """
        Reflection Stage: Summarize experience and plan future tasks
        """
        prompt = self._build_reflection_prompt(team_history)
        
        response = self.llm_client.generate(prompt)
        summary, future_plan = self._parse_reflection_response(response)
        
        return summary, future_plan
    
    def update_leader_plan(self, team_reflections: Dict[str, Tuple[str, str]]) -> Dict:
        """
        Leader integrates team reflections and updates plan
        """
        if not self.is_leader:
            return {}
        
        prompt = self._build_leader_update_prompt(team_reflections)
        
        response = self.llm_client.generate(prompt)
        new_plan = self._parse_plan_response(response)
        
        return new_plan
    
    # ============ BestMan Integration Methods ============
    
    def _get_bestman_observation(self, base_obs: Dict) -> Dict:
        """Get observation from BestMan robot sensors"""
        obs = base_obs.copy()
        
        if self.bestman_robot:
            # Get robot pose from BestMan
            if hasattr(self.bestman_robot, 'get_robot_pose'):
                obs['pose'] = self.bestman_robot.get_robot_pose()
            
            # Get gripper state for manipulation robots
            if 'pick' in self.capabilities and hasattr(self.bestman_robot, 'get_gripper_state'):
                obs['gripper_state'] = self.bestman_robot.get_gripper_state()
            
            # Get camera observations
            if hasattr(self.bestman_robot, 'get_camera_obs'):
                obs['visual'] = self.bestman_robot.get_camera_obs()
        
        return obs
    
    def _execute_action(self, action: Dict) -> Dict:
        """
        Execute action using BestMan unified APIs
        Returns detailed feedback for LLM
        """
        action_type = action.get('type')
        feedback = {
            'success': False,
            'message': '',
            'state_change': {}
        }
        
        try:
            if action_type == 'navigate':
                feedback = self._execute_navigate(action)
            elif action_type == 'pick':
                feedback = self._execute_pick(action)
            elif action_type == 'place':
                feedback = self._execute_place(action)
            elif action_type == 'open':
                feedback = self._execute_open(action)
            elif action_type == 'move':
                feedback = self._execute_move(action)
            elif action_type == 'communicate':
                feedback = self._execute_communicate(action)
            elif action_type == 'wait':
                feedback = self._execute_wait(action)
            else:
                feedback['message'] = f"Unknown action type: {action_type}"
                
        except Exception as e:
            feedback['message'] = f"Execution error: {str(e)}"
        
        return feedback
    
    def _execute_navigate(self, action: Dict) -> Dict:
        """Execute navigation using BestMan navigation APIs"""
        target = action.get('target')
        stand_pose = action.get('stand_pose', 0)
        
        if not self.bestman_robot:
            return {'success': True, 'message': f'Simulated navigation to {target}', 'type': 'navigate'}
        
        # Use BestMan's navigation module
        # Reference: BestMan navigation_basic.py examples
        try:
            # Check if target is valid in scene graph
            scene_graph = self.observation.get_scene_graph()
            if target not in scene_graph:
                return {
                    'success': False,
                    'message': f'Navigation failed: {target} not found in scene graph',
                    'type': 'navigate_failed'
                }
            
            # Execute navigation
            target_pos = scene_graph[target]['stand_poses'][stand_pose]
            
            # BestMan API: move_to_pose or similar navigation function
            if hasattr(self.bestman_robot, 'move_to_pose'):
                success = self.bestman_robot.move_to_pose(target_pos)
            elif hasattr(self.bestman_robot, 'navigate_to'):
                success = self.bestman_robot.navigate_to(target_pos)
            else:
                # Fallback to direct PyBullet control
                success = self._fallback_navigate(target_pos)
            
            if success:
                # Check for objects at target
                found_objects = self._scan_for_objects(target)
                return {
                    'success': True,
                    'message': f'Successfully navigated to {target}',
                    'found_objects': found_objects,
                    'type': 'navigate_success'
                }
            else:
                return {
                    'success': False,
                    'message': f'Navigation failed: could not reach {target}',
                    'type': 'navigate_failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Navigation error: {str(e)}',
                'type': 'navigate_failed'
            }
    
    def _execute_pick(self, action: Dict) -> Dict:
        """Execute pick using BestMan manipulation APIs"""
        target_obj = action.get('target_object')
        
        if not self.bestman_robot:
            return {'success': True, 'message': f'Simulated pick of {target_obj}', 'type': 'pick'}
        
        try:
            # Check if object is graspable
            if not self._is_object_reachable(target_obj):
                return {
                    'success': False,
                    'message': f'Pick failed: {target_obj} is out of reach',
                    'distance': self._get_object_distance(target_obj),
                    'type': 'pick_failed'
                }
            
            # BestMan grasp API
            if hasattr(self.bestman_robot, 'grasp'):
                success = self.bestman_robot.grasp(target_obj)
            elif hasattr(self.bestman_robot, 'pick_object'):
                success = self.bestman_robot.pick_object(target_obj)
            else:
                success = self._fallback_grasp(target_obj)
            
            if success:
                return {
                    'success': True,
                    'message': f'Successfully picked {target_obj}',
                    'grasped_object': target_obj,
                    'type': 'pick_success'
                }
            else:
                return {
                    'success': False,
                    'message': f'Pick failed: grasp unsuccessful',
                    'type': 'pick_failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Pick error: {str(e)}',
                'type': 'pick_failed'
            }
    
    def _execute_place(self, action: Dict) -> Dict:
        """Execute place using BestMan manipulation APIs"""
        target_obj = action.get('target_object')
        target_location = action.get('target_location')
        
        if not self.bestman_robot:
            return {'success': True, 'message': f'Simulated place of {target_obj} at {target_location}', 'type': 'place'}
        
        try:
            # Check if holding object
            if not self._is_holding_object(target_obj):
                return {
                    'success': False,
                    'message': f'Place failed: not holding {target_obj}',
                    'type': 'place_failed'
                }
            
            # BestMan place API
            if hasattr(self.bestman_robot, 'place'):
                success = self.bestman_robot.place(target_location)
            elif hasattr(self.bestman_robot, 'release'):
                success = self.bestman_robot.release(target_location)
            else:
                success = self._fallback_place(target_location)
            
            if success:
                return {
                    'success': True,
                    'message': f'Successfully placed {target_obj} at {target_location}',
                    'type': 'place_success'
                }
            else:
                return {
                    'success': False,
                    'message': f'Place failed: could not place at target',
                    'type': 'place_failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Place error: {str(e)}',
                'type': 'place_failed'
            }
    
    def _execute_open(self, action: Dict) -> Dict:
        """Execute open using BestMan manipulation APIs"""
        container = action.get('target_container')
        
        if not self.bestman_robot:
            return {'success': True, 'message': f'Simulated open of {container}', 'type': 'open'}
        
        try:
            # Check if container is reachable and closed
            if not self._is_object_reachable(container):
                return {
                    'success': False,
                    'message': f'Open failed: {container} is out of reach',
                    'type': 'open_failed'
                }
            
            # BestMan open API
            if hasattr(self.bestman_robot, 'open_container'):
                success = self.bestman_robot.open_container(container)
            else:
                success = self._fallback_open(container)
            
            if success:
                # Return contents after opening
                contents = self._get_container_contents(container)
                return {
                    'success': True,
                    'message': f'Successfully opened {container}',
                    'contents': contents,
                    'type': 'open_success'
                }
            else:
                return {
                    'success': False,
                    'message': f'Open failed: container already open or cannot be opened',
                    'type': 'open_failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Open error: {str(e)}',
                'type': 'open_failed'
            }
    
    def _execute_move(self, action: Dict) -> Dict:
        """Execute fine-grained base movement"""
        delta_x = action.get('delta_x', 0)
        delta_y = action.get('delta_y', 0)
        
        if not self.bestman_robot:
            return {'success': True, 'message': f'Simulated move ({delta_x}, {delta_y})', 'type': 'move'}
        
        try:
            # BestMan move API (fine positioning)
            if hasattr(self.bestman_robot, 'move_base'):
                success = self.bestman_robot.move_base(delta_x, delta_y)
            else:
                success = self._fallback_move(delta_x, delta_y)
            
            if success:
                return {
                    'success': True,
                    'message': f'Successfully moved ({delta_x}, {delta_y})',
                    'type': 'move_success'
                }
            else:
                return {
                    'success': False,
                    'message': f'Move failed: collision or out of bounds',
                    'type': 'move_failed'
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Move error: {str(e)}',
                'type': 'move_failed'
            }
    
    def _execute_communicate(self, action: Dict) -> Dict:
        """Send message to teammate"""
        content = action.get('content', '')
        target = action.get('target', 'all')
        
        if self.communication:
            self.communication.send_message(self.name, target, content)
        
        return {
            'success': True,
            'message': f'Message sent to {target}: {content}',
            'type': 'communicate'
        }
    
    def _execute_wait(self, action: Dict) -> Dict:
        """Wait for next step"""
        return {
            'success': True,
            'message': 'Waiting for next instruction',
            'type': 'wait'
        }
    
    # ============ Helper Methods ============
    
    def _validate_action(self, action: Dict) -> bool:
        """Validate if action is within robot capabilities"""
        action_type = action.get('type')
        return action_type in self.capabilities
    
    def _fallback_action(self) -> Dict:
        """Return safe fallback action"""
        return {'type': 'wait', 'reason': 'invalid_action'}
    
    def _is_object_reachable(self, obj_name: str) -> bool:
        """Check if object is within grasping range"""
        # Integration with BestMan's reachability analysis
        distance = self._get_object_distance(obj_name)
        return distance <= self.config.get('max_grasp_range', 0.8)
    
    def _get_object_distance(self, obj_name: str) -> float:
        """Calculate distance to object"""
        # Use BestMan's scene graph and robot pose
        scene_graph = self.observation.get_scene_graph()
        robot_pose = self.observation.get_robot_pose()
        
        if obj_name in scene_graph:
            obj_pos = scene_graph[obj_name].get('position', [0, 0, 0])
            # Calculate Euclidean distance in xy plane
            dist = ((robot_pose[0] - obj_pos[0])**2 + 
                   (robot_pose[1] - obj_pos[1])**2) ** 0.5
            return dist
        return float('inf')
    
    def _is_holding_object(self, obj_name: str) -> bool:
        """Check if robot is currently holding the object"""
        if self.bestman_robot and hasattr(self.bestman_robot, 'get_gripper_state'):
            gripper_state = self.bestman_robot.get_gripper_state()
            return gripper_state.get('grasped_object') == obj_name
        return False
    
    def _scan_for_objects(self, location: str) -> List[str]:
        """Scan location for objects (visual perception)"""
        # Integration with BestMan's perception module
        if self.bestman_robot and hasattr(self.bestman_robot, 'detect_objects'):
            return self.bestman_robot.detect_objects(location)
        return []
    
    def _get_container_contents(self, container: str) -> List[str]:
        """Get contents of a container after opening"""
        scene_graph = self.observation.get_scene_graph()
        if container in scene_graph:
            return scene_graph[container].get('contents', [])
        return []
    
    # ============ Fallback Methods for Pure Simulation ============
    
    def _fallback_navigate(self, target_pos: List[float]) -> bool:
        """Fallback navigation using direct PyBullet control"""
        # Simplified navigation for testing without full BestMan stack
        return True
    
    def _fallback_grasp(self, obj_name: str) -> bool:
        """Fallback grasp for testing"""
        return True
    
    def _fallback_place(self, location: str) -> bool:
        """Fallback place for testing"""
        return True
    
    def _fallback_open(self, container: str) -> bool:
        """Fallback open for testing"""
        return True
    
    def _fallback_move(self, delta_x: float, delta_y: float) -> bool:
        """Fallback move for testing"""
        return True
    
    # ============ Prompt Building Methods ============
    
    def _get_robot_role_and_skills(self) -> Tuple[str, str]:
        """Get differentiated Role and Skills description for each robot - detailed version"""
        name = self.name
        
        if name == "Alice":
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured with a wheeled chassis and a single manipulator arm.
2) You possess the ability to navigate across the ground and perform manipulation tasks, including transporting various objects and opening hinged objects."""
            skills = """# Skills:
- [navigate] to <stand_pose_id> of <object>: Move to a predefined pose near the target object/furniture
- [open] <container>: Open a hinged container (drawer, cabinet, fridge, etc.)
- [pick] up <object>: Grasp an object using the manipulator arm
- [place] <object> on/into <platform>: Place the held object onto or into a target platform/container
- [move] <delta_x> and <delta_y>: Adjust base position by relative x,y offsets for better reach
- [communicate] <content> to <role>: Send a message to a specific teammate or broadcast to all
- [wait]: Pause and wait for further instructions or teammate actions

# Unique Strengths:
- Can both navigate and manipulate, making me the most versatile team member
- Can transport objects from distant locations to manipulation robots
- Can open containers to access objects inside
- Can adjust my base position to improve grasping success rate"""
        elif name == "Bob":
            role = f"""# Role:
1) You are an intelligent robot named {name}, and your configuration is a single robotic arm fixed on a desktop.
2) You are capable of manipulating within a limited range around your fixed base position."""
            skills = """# Skills:
- [pick] up <object>: Grasp an object within your operational range
- [place] <object> on/into <platform>: Place the held object onto or into a target platform/container
- [communicate] <content> to <role>: Send a message to a specific teammate or broadcast to all
- [wait]: Pause and wait for objects to be brought within your reach

# Limitations:
- Cannot move or navigate; base is fixed at a single location
- Cannot open containers or explore the environment
- Dependent on other robots to transport objects to your operational range

# Unique Strengths:
- High-precision manipulation with stable base
- Can quickly pick and place multiple objects once they are within reach
- Ideal for final assembly and precise placement tasks"""
        elif name == "David":
            role = f"""# Role:
1) You are an intelligent robot named {name}, and your configuration is a wheeled chassis.
2) You can navigate and move on the ground, cannot manipulate any objects and cannot open any hinged objects."""
            skills = """# Skills:
- [navigate] to <stand_pose_id> of <object>: Move to a predefined pose near the target object/furniture
- [communicate] <content> to <role>: Send a message to specific teammates or broadcast discoveries
- [wait]: Pause and wait for further instructions

# Limitations:
- No manipulation capabilities; cannot pick, place, or open anything
- Can only observe and report object locations

# Unique Strengths:
- Fastest exploration of the environment
- Can navigate to all reachable locations in the scene
- Can report object locations and environmental states to teammates
- Can request other robots to open containers for inspection"""
        elif name == "Lucy":
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured as a quadrotor drone with a fixed suction gripper.
2) You are capable of aerial navigation and manipulation in elevated or hard-to-reach areas."""
            skills = """# Skills:
- [navigate] to <stand_pose_id> of <object>: Fly to a predefined pose near the target object/furniture
- [pick] up <object>: Grasp a lightweight object using the suction gripper
- [place] <object> on/into <platform>: Place the held object onto or into a target platform
- [communicate] <content> to <role>: Send a message to specific teammates or broadcast discoveries
- [wait]: Hover and wait for further instructions

# Limitations:
- Limited payload capacity (lightweight objects only)
- Cannot open hinged containers
- Suction gripper less reliable than manipulator arms for heavy objects

# Unique Strengths:
- Can access elevated areas and hard-to-reach locations (top of cabinets, high shelves)
- Can explore from aerial perspective
- Can transport small objects over obstacles
- Can locate objects in areas inaccessible to ground robots"""
        else:
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured as a {self.robot_type}.
2) You are capable of various tasks based on your configuration."""
            skills = f"""# Skills:
{chr(10).join(['- ' + cap for cap in self.capabilities]) if self.capabilities else '- perform various tasks'}"""
        
        return role, skills
    
    def _build_self_description_prompt(self, task_context: Dict) -> str:
        """Build prompt for self-description stage - detailed format"""
        teammates_str = ', '.join(task_context.get('teammates', [])) or "other robots"
        task = task_context.get('goal', 'Unknown')
        
        # Get robot-specific role and skills
        role_desc, skills_desc = self._get_robot_role_and_skills()
        
        prompt = f"""==== System Prompt ====
# Contexts:
1) You are an intelligent robot capable of human-like reasoning and decision-making.
2) You must collaborate with heterogeneous robots to accomplish complex tasks.

Phase: Initial stage, where each robot introduces itself.

CoT: Let's think step by step!

==== User Prompt ====
==== Common Components Shared by All Robots ====
Each robot introduces itself according to its configuration, capabilities, and understanding of the shared task.

Task Objective and Context:
1) The overall collaborative goal is {task}.
2) Objects are scattered in an unknown indoor environment, requiring exploration and organization.
3) You should introduce yourself to help teammates {teammates_str} understand your role and abilities.

==== Distinct Components Specific to Each Robot ====
{role_desc}

{skills_desc}

# Output Response Format:
1) Thoughts: step-by-step reasoning about your capabilities and how they contribute to the team;
2) Contents: concise self-introduction for teammates (1-2 sentences highlighting your unique strengths)."""
        
        return prompt
    
    def _build_allocation_prompt(self, teammates_descriptions: Dict[str, str], task: str = "") -> str:
        """Build prompt for task allocation stage - detailed format"""
        descriptions_text = '\n'.join([
            f"- {name}: {desc}" for name, desc in teammates_descriptions.items()
        ])
        all_robots = [self.name] + list(teammates_descriptions.keys())
        teammates_str = ", ".join(all_robots)
        
        prompt = f"""==== System Prompt ====
# Contexts:
1) You are an intelligent robot that can think and make decisions like a human.
2) You need to cooperate with other robots of various configurations to complete complex and long-term tasks.

Phase: Now second step of collaboration

Tasks:
1) You need to propose a follow-up division of labor plan.
2) You need to propose a campaign speech to run for leader.

CoT: Let's think step by step!

==== User Prompt ====
# Identity and Information:
1) You are an intelligent robot named {self.name}.
2) Below are the self-introductions from yourself and your collaborators:
{descriptions_text}

# Task Information:
Overall task: {task}
Team members: {teammates_str}

# Plan Proposal and Leadership Campaign:
1) Please analyze the self-introductions carefully and thoroughly to develop your collaboration plan.
2) Reflect on your strengths from multiple perspectives and write a campaign speech to run for the leader role.

# Principles for Plan Design:
1) The plan enables robots to work in parallel to maximize efficiency.
2) Utilize shared capabilities among heterogeneous robots, e.g., navigation robots jointly explore the environment.
3) Leverage unique abilities efficiently, e.g., flying robots explore high areas, manipulation robots handle precise placement.
4) Minimize dependencies and waiting time between robots.
5) Assign tasks based on each robot's capabilities and limitations.
6) Consider the spatial distribution of objects and the optimal task sequence.

# Principles for Leadership Campaign:
1) Highlight your unique capabilities that make you suitable for coordination.
2) Emphasize your understanding of the overall task and team dynamics.
3) Demonstrate your ability to integrate information from all teammates.
4) Show your track record of successful task completion (if any prior experience).

# Output Response Format:
1) Thoughts: think step by step to analyze the team capabilities, task requirements, and optimal division of labor;
2) Contents: Include two parts:
   - Collaboration Plan: Detailed task allocation for each robot including specific subtasks and sequence
   - Campaign Speech: 2-3 sentences arguing why you should be the leader"""
        
        return prompt
    
    def _build_election_prompt(self, proposals: Dict) -> str:
        """Build prompt for leader election - detailed format"""
        proposals_text = '\n\n'.join([
            f"=== {name}'s Proposal ===\nCollaboration Plan: {prop[0]}\nCampaign Speech: {prop[1]}"
            for name, prop in proposals.items()
        ])
        
        prompt = f"""==== System Prompt ====
# Contexts:
1) You are an intelligent robot capable of human-like thinking and decision-making.
2) You need to collaborate with other robots of various configurations to accomplish complex, long-term tasks.

Phase: Now it's the third step of collaboration.

Tasks:
1) Carefully analyze the collaboration plans and leadership proposals from all participants.
2) Objectively elect a leader (self-nomination allowed).

CoT: Let's think step by step!

==== User Prompt ====
# Identity and Information:
1) You are an intelligent robot named {self.name}.
2) Below are the collaboration plans and campaign speeches from yourself and other collaborators:
{proposals_text}

# Leader Election Instructions:
Please analyze and judge fairly, justly, and objectively to elect a qualified leader.

# Evaluation Criteria for Leader Selection:
1) Capability alignment: Does the candidate have the right skills to coordinate this specific task?
2) Plan quality: Is the proposed collaboration plan efficient, feasible, and comprehensive?
3) Communication ability: Does the candidate demonstrate clear thinking and communication skills?
4) Neutrality: Can the candidate fairly allocate tasks without favoring themselves?
5) Experience: Does the candidate show understanding of potential failure modes and contingency plans?

# Output Response Format:
1) Thoughts: think step by step to analyze each candidate's plan, speech, and suitability for leadership;
2) Reasons: state the specific reason for your choice, referencing the evaluation criteria;
3) Leader: directly give the name of the selected leader (format: "Leader: [name]");
4) Confidence: rate your confidence in this choice (High/Medium/Low) and explain why."""
        
        return prompt
    
    def _build_execution_prompt(self, observation: Dict, leader_plan: Dict) -> str:
        """Build prompt for action execution - detailed format"""
        # Get robot-specific role, skills, and principles
        role_desc, skills_desc = self._get_robot_role_and_skills()
        principles_desc = self._get_execution_principles_for_agent()
        
        history = self.memory.get_recent_history(k=5)
        teammates = leader_plan.get('teammates', [])
        teammates_str = ', '.join(teammates) if teammates else 'other robots'
        leader_name = leader_plan.get('leader', 'Unknown')
        plan_desc = leader_plan.get('description', 'Execute task step by step')
        task = leader_plan.get('goal', 'Unknown')
        
        # Get robot-specific observation info
        scene_graph = observation.get('scene_graph', {})
        robot_status = observation.get('status', {})
        
        # Get message history
        message_history = self.memory.get_received_messages(k=5)
        
        prompt = f"""==== System Prompt ====
# Contexts:
1) You are an intelligent robot capable of human-like reasoning and decision-making.
2) You must collaborate with heterogeneous robots to accomplish complex tasks.

Phase: Execution stage, where robots perform actions based on plans.

CoT: Let's think step by step!

==== Common Components Shared by All Robots ====
# Task Objective and Context:
1) The overall team task is: {task}.
2) Ingredients/objects are scattered in an unknown indoor environment. The scene graph shows furniture locations but not their contents.
3) Collaborate with teammates {teammates_str}, who have different capabilities, to complete the task.
4) {leader_name} is the elected leader and proposed the collaboration plan: {plan_desc}. Thus, all robots should follow this plan while adapting to real-time feedback.

# Communication Protocol:
- Use [communicate] action to share discoveries, request help, or report progress
- Keep messages concise and information-dense
- Avoid redundant communication
- Use broadcast for general discoveries, unicast for specific requests

# General Principles:
1) Always verify current state before acting to avoid redundant actions
2) If an action fails, analyze the failure reason and try alternative approaches
3) Monitor task progress and avoid working on already-completed subgoals
4) Respond promptly to teammates' requests for assistance
5) Use [wait] strategically when teammates are completing critical steps
6) Focus on completing the task without unrelated or redundant actions

==== Distinct Components Specific to {self.robot_type} ({self.name}) ====
{role_desc}

{skills_desc}

{principles_desc}

==== User Prompt ====
==== Common Components Shared by All Robots ====

# Task Status:
Latest Task Progress Status: {len(self.memory.get_action_history())} steps completed.

# Scene Graph:
{scene_graph}

# Robot Status:
Current robot states: {robot_status}

# Feedback History:
The historical feedbacks, from oldest to newest, are as follows:
{history}

# Action History:
The historical actions, from oldest to newest, are as follows:
{history}

# Receive Message History:
The historical receive messages, from oldest to newest, are as follows:
{message_history}

# Available Actions:
Choose and execute ONLY ONE action from your robot's action set below.

# Output Response Format:
1) Thoughts: think step by step to analyze the current situation, task progress, and optimal next action;
2) Contents: output exactly ONE action in the format: [action_name](arguments)"""
        
        return prompt
    
    def _get_execution_principles_for_agent(self) -> str:
        """Get execution principles for agent - detailed format"""
        name = self.name
        
        if name == "Alice":
            return """# Principles:
1) Efficiently explore and navigate all locations in the scene graph without repetition.
2) Transport task-related items promptly to teammates who need them.
3) When facing inaccessible areas, notify capable assistants (e.g., drone for high areas).
4) Track task progress and adjust targets timely when objects are found/moved.
5) Respond promptly to collaborators' requests for transport or assistance.
6) If grasp fails, try other stand poses or use [move] to adjust base position.
7) When using [move], analyze the local costmap to select optimal position near target.
8) Open containers before attempting to pick objects inside.
9) Focus on completing the task without unrelated or redundant actions.

# Move Action Special Protocol:
When executing [move], you will receive a local costmap showing:
- X_free: Navigable areas
- X_obs: Obstacle regions
- X_goal: Target object location
- X_base: Your current position
Select (delta_x, delta_y) to minimize distance to X_goal while staying in X_free."""
        elif name == "Bob":
            return """# Principles:
1) Analyze tasks and scene graphs, prioritizing objects already within your reach.
2) Request help promptly for distant or missing objects (ask mobile robots to transport).
3) Notify collaborators of task progress and what objects you still need.
4) Track progress changes and adjust targets as needed.
5) Respond promptly to collaborators' requests and incoming objects.
6) If object is slightly out of reach, request mobile robot to reposition it.
7) Cannot open containers; request mobile manipulation robot to open and retrieve.
8) Focus on completing the task without unrelated or redundant actions.

# Operational Constraints:
- Base is FIXED; cannot navigate or move
- Can only manipulate objects within arm reach
- Cannot open any containers
- Dependent on teammates for object delivery"""
        elif name == "David":
            return """# Principles:
1) Efficiently explore and navigate all locations in the scene graph without repetition.
2) Notify collaborators of task items found and request mobile teammates for transport.
3) Notify capable assistants to explore inaccessible areas (e.g., drone for high shelves).
4) Request collaborators to open objects for exploration (drawers, cabinets, fridge).
5) Track task progress and adjust exploration targets timely.
6) Respond promptly to assistants' messages and requests.
7) If target object is found, immediately report location and contents to team.
8) Focus on completing the task without unrelated or redundant actions.

# Exploration Strategy:
- Systematically visit all furniture locations in scene graph
- Check containers by requesting others to open them
- Report all discoveries via [communicate]
- Prioritize locations likely to contain target objects

# Operational Constraints:
- Cannot manipulate or pick any objects
- Cannot open containers
- Can only navigate and communicate"""
        elif name == "Lucy":
            return """# Principles:
1) Efficiently explore and navigate all locations, especially elevated and hard-to-reach areas.
2) Transport task-related items promptly when they are in accessible aerial locations.
3) Request collaborators to open objects for exploration if contents are not visible from air.
4) Track task progress and adjust targets timely.
5) Respond promptly to collaborators' requests.
6) Be aware of payload limits; only pick lightweight objects.
7) If suction grasp fails, report failure and request ground robot assistance.
8) Focus on completing the task without unrelated or redundant actions.

# Aerial Advantages:
- Can access top of cabinets, high shelves, ceiling areas
- Can fly over obstacles that block ground robots
- Can survey room from above for object location
- Can deliver small items to high platforms

# Operational Constraints:
- Limited payload capacity (lightweight objects only)
- Cannot open hinged containers
- Suction gripper less reliable than manipulator arms for heavy objects
- Can access elevated areas and hard-to-reach locations"""
        else:
            return """# Principles:
1) Follow the task plan and execute actions efficiently.
2) Track task progress and adjust targets timely.
3) Respond promptly to collaborators' requests.
4) Use COMMUNICATE action when coordination is needed.
5) Focus on completing the task without unrelated or redundant actions."""
    
    def _build_reflection_prompt(self, team_history: Dict) -> str:
        """Build prompt for reflection stage - detailed format"""
        
        actions = self.memory.get_action_history()
        successes = sum(1 for a in actions if a.get('feedback', {}).get('success', False))
        failures = len(actions) - successes
        
        # Format action history
        actions_text = "\n".join([f"  Step {i+1}: {a.get('action', 'Unknown')}" for i, a in enumerate(actions[-10:])])
        
        # Format feedback history
        feedbacks = [a.get('feedback', {}) for a in actions]
        feedbacks_text = "\n".join([f"  Step {i+1}: {f.get('message', 'No message')}" for i, f in enumerate(feedbacks[-10:])])
        
        prompt = f"""==== Participants System Prompt ====
# Contexts:
1) You are an intelligent robot capable of human-like reasoning and decision-making.
2) You need to collaborate with other robots of various configurations to accomplish complex, long-term tasks.

Phase: Now it is the group discussion session of the heterogeneous robot collaboration.

# Principles:
1) Compare the differences between the current task status and the target task status.
2) Analyze the current scene graph content, historical feedback, action and message sequences.
3) Summarize successful experiences: what strategies worked well?
4) Identify failure patterns: what went wrong and why?
5) Assess team coordination efficiency: were there communication gaps or redundant actions?
6) Evaluate individual performance: did each robot utilize their capabilities effectively?
7) Identify remaining challenges and obstacles to task completion.

CoT: Let's think step by step!

==== Participants User Prompt ====

# Your Identity:
You are {self.name}, a {self.robot_type} in the team.

# Current Task State:
Current progress: {successes}/{len(actions)} successful steps
Remaining subtasks: to be determined based on scene exploration

# Your Extended History (last {len(actions)} steps):
## Your Action History:
{actions_text}

## Your Feedback History:
Recent feedbacks from oldest to newest:
{feedbacks_text}

## Execution Statistics:
Total Steps: {len(actions)}
Successes: {successes}
Failures: {failures}

# Output Response Format:
1) Thoughts: think step by step to analyze:
   - What has been accomplished so far?
   - What successful strategies were used?
   - What failures or inefficiencies occurred?
   - What are the main obstacles remaining?
   
2) Summaries:
   - Successes: List key successes and why they worked
   - Failures: List key failures, root causes, and lessons learned
   - Coordination Assessment: Evaluate team communication and collaboration efficiency
   
3) Plans:
   - Your proposed next subtasks (specific and actionable)
   - Suggested adjustments to overall team strategy
   - Any requests for assistance or role changes"""
        
        return prompt
    
    def _build_leader_update_prompt(self, team_reflections: Dict) -> str:
        """Build prompt for leader to update plan - detailed format"""
        
        actions = self.memory.get_action_history()
        successes = sum(1 for a in actions if a.get('feedback', {}).get('success', False))
        failures = len(actions) - successes
        
        reflections_text = '\n'.join([
            f"=== {name} ===\nThoughts: {ref[0]}\nSummaries: {ref[1]}\nPlans: {ref[2] if len(ref) > 2 else 'N/A'}"
            for name, ref in team_reflections.items()
        ])
        
        prompt = f"""==== Leader System Prompt ====
# Contexts:
1) You are an intelligent robot capable of human-like reasoning, collaborating with others on complex tasks.
2) As the leader, you must synthesize all team members' experiences and update the global collaboration plan.

Phase: It is the leadership summary stage of group discussion.

# Principles:
1) Assign specific, measurable tasks to each robot including yourself.
2) Ensure plan reflects current environment and object states (not outdated information).
3) Prioritize critical path: identify which subtasks block others and schedule first.
4) Balance workload: avoid overloading one robot while others are idle.
5) Incorporate lessons learned from failures to avoid repeated mistakes.
6) Maintain flexibility: plan should adapt to unexpected discoveries or failures.
7) Minimize communication overhead: assign tasks that reduce need for coordination.

CoT: Let's think step by step!

==== Leader User Prompt ====
1) You are a smart robot named {self.name}, you are the elected leader.
2) The historical summaries and future plans of each team member are as follows:

{reflections_text}

# Format of Team Input:
Each entry contains:
- Robot: <name>
- Type: <robot_type>
- Successes: <list>
- Failures: <list>
- Proposed Next Tasks: <list>
- Requests: <list>

# Current Global State:
Overall task progress: {successes}/{len(actions)} successful steps
Total Steps: {len(actions)}
Successes: {successes}
Failures: {failures}

# Output Response Format:
1) Thoughts: think step by step to analyze:
   - Aggregate all team members' findings and experiences
   - Identify conflicts or redundancies in proposed plans
   - Determine optimal task allocation based on current state
   
2) Contents: output the updated heterogeneous robots collaboration plan including:
   - For each robot (<name>):
     * Assigned subtasks (specific, ordered)
     * Expected outcomes
     * Coordination points (when to communicate/wait for others)
   - Global task sequence and dependencies
   - Contingency plans for likely failure scenarios
   - Updated task priorities based on current progress"""
        
        return prompt
    
    # ============ Response Parsing Methods ============
    
    def _parse_response(self, response: str) -> str:
        """Parse LLM response to extract content"""
        # Return cleaned response directly
        response = response.strip()
        
        # If contains thinking process markers, try to extract actual content
        if 'Contents:' in response:
            lines = response.split('\n')
            content_started = False
            contents = []
            for line in lines:
                if 'Contents:' in line or 'content:' in line.lower():
                    content_started = True
                    continue
                if content_started and line.strip():
                    contents.append(line)
            return '\n'.join(contents) if contents else response
        
        # Remove possible English prompt residue
        if 'The user wants me to act as' in response or 'Key constraints:' in response:
            # Try to find actual content (usually in the last paragraph)
            paragraphs = [p.strip() for p in response.split('\n\n') if p.strip()]
            if paragraphs:
                # Return the last paragraph, usually the most concise introduction
                return paragraphs[-1]
        
        return response
    
    def _parse_allocation_response(self, response: str) -> Tuple[Dict, str]:
        """Parse task allocation response"""
        # Extract plan and speech from response
        plan = {}
        speech = ""
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            if 'Plan:' in line:
                current_section = 'plan'
                continue
            elif 'Speech:' in line:
                current_section = 'speech'
                continue
            
            if current_section == 'plan':
                # Parse plan assignments
                if ':' in line:
                    robot, task = line.split(':', 1)
                    plan[robot.strip()] = task.strip()
            elif current_section == 'speech':
                speech += line + '\n'
        
        return plan, speech.strip()
    
    def _parse_action_response(self, response: str) -> Dict:
        """Parse action from LLM response"""
        try:
            import json
            # Try to find JSON in response
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                action_json = response[start:end]
                return json.loads(action_json)
        except:
            pass
        
        # Fallback: parse text format
        for line in response.split('\n'):
            if 'Action:' in line:
                # Simple text parsing
                action_type = line.split(':')[-1].strip().lower()
                return {'type': action_type}
        
        return {'type': 'wait'}
    
    def _parse_leader_response(self, response: str) -> str:
        """Parse leader election response"""
        for line in response.split('\n'):
            if 'Leader:' in line:
                return line.split(':')[-1].strip()
        return list(self.teammates.keys())[0] if self.teammates else self.name
    
    def _parse_reflection_response(self, response: str) -> Tuple[str, str]:
        """Parse reflection response"""
        summary = ""
        plan = ""
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            if 'Summary:' in line:
                current_section = 'summary'
                continue
            elif 'Plan:' in line or 'Future' in line:
                current_section = 'plan'
                continue
            
            if current_section == 'summary':
                summary += line + '\n'
            elif current_section == 'plan':
                plan += line + '\n'
        
        return summary.strip(), plan.strip()
    
    def _parse_plan_response(self, response: str) -> Dict:
        """Parse updated plan response"""
        plan = {}
        current_robot = None
        
        for line in response.split('\n'):
            if ':' in line and not line.startswith(' '):
                robot, task = line.split(':', 1)
                plan[robot.strip()] = task.strip()
        
        return plan