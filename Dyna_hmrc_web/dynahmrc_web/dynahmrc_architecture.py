"""
DynaHMRC Architecture - Decentralized Multi-Robot Collaboration System aligned with Paper
Based on paper "DynaHMRC: Dynamic Heterogeneous Multi-Robot Collaboration" (TRO)

Core Design:
1. Decentralized: Each robot is an independent LLM Agent
2. Four-Stage Cycle: Self-Description -> Task Allocation -> Leader Election -> Closed-Loop Execution
3. Memory Module: feedback_history, received_message_history, action_history
4. Action Primitives: Differentiated action sets based on robot type
5. Leader Election: Voting mechanism
6. Reflection Mechanism: Periodic Reflection
"""

import json
import time
import sys
import os
import re
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
from enum import Enum

# Add dynahmrc path for importing scene simulator
sys.path.append(os.path.join(os.path.dirname(__file__), 'dynahmrc'))
from scene_simulator import SceneSimulator


class CollaborationPhase(Enum):
    """Four-stage collaboration process"""
    SELF_DESCRIPTION = "self_description"
    TASK_ALLOCATION = "task_allocation"
    LEADER_ELECTION = "leader_election"
    EXECUTION = "execution"
    REFLECTION = "reflection"


class MemoryModule:
    """
    Memory Module - Manages historical context
    Three independent FIFO queues (length limited to K)
    Enhanced version: Supports detailed feedback classification and task progress tracking
    """

    def __init__(self, max_history: int = 10, reflection_history: int = 50):
        self.max_history = max_history  # K
        self.reflection_history = reflection_history  # K̄ > K

        # Three independent queues
        self.feedback_history: deque = deque(maxlen=max_history)
        self.received_message_history: deque = deque(maxlen=max_history)
        self.action_history: deque = deque(maxlen=max_history)

        # Long history for Reflection
        self.long_feedback_history: deque = deque(maxlen=reflection_history)
        self.long_action_history: deque = deque(maxlen=reflection_history)

        # Persistent storage
        self.self_description = ""
        self.task_plan = {}

        # Task progress tracking
        self.task_progress = {
            'completed_objects': [],
            'remaining_objects': [],
            'failed_attempts': {},  # object_name -> failure_count
            'discovered_objects': []
        }

        # Execution statistics
        self.execution_stats = {
            'total_actions': 0,
            'success_count': 0,
            'failure_count': 0,
            'consecutive_failures': 0,
            'last_success_step': 0
        }

        # Failure type statistics
        self.failure_types = {
            'invalid_target': 0,
            'action_constraints': 0,
            'execution_conflict': 0,
            'error_measurement': 0,
            'api_invocation': 0
        }
    
    def store_feedback(self, feedback: Dict):
        """存储环境反馈 - 增强版支持详细反馈分类"""
        # 分类反馈类型
        feedback_type = self._classify_feedback(feedback)
        
        entry = {
            'step': len(self.action_history),
            'timestamp': time.time(),
            'feedback_type': feedback_type,
            **feedback
        }
        self.feedback_history.append(entry)
        self.long_feedback_history.append(entry)
        
        # 更新执行统计
        self._update_execution_stats(feedback, feedback_type)
    
    def _classify_feedback(self, feedback: Dict) -> str:
        """根据反馈内容分类反馈类型"""
        if feedback.get('success'):
            # Success Feedback 子类型
            if feedback.get('state_confirmation'):
                return 'state_confirmation'
            elif feedback.get('content_reporting'):
                return 'content_reporting'
            elif feedback.get('execution_validation'):
                return 'execution_validation'
            else:
                return 'success'
        else:
            # Failure Feedback 子类型
            error_type = feedback.get('error_type', '')
            if error_type == 'invalid_target':
                self.failure_types['invalid_target'] += 1
                return 'invalid_target'
            elif error_type == 'action_constraints':
                self.failure_types['action_constraints'] += 1
                return 'action_constraints'
            elif error_type == 'execution_conflict':
                self.failure_types['execution_conflict'] += 1
                return 'execution_conflict'
            elif error_type == 'error_measurement':
                self.failure_types['error_measurement'] += 1
                return 'error_measurement'
            elif error_type == 'api_invocation':
                self.failure_types['api_invocation'] += 1
                return 'api_invocation'
            else:
                return 'failure'
    
    def _update_execution_stats(self, feedback: Dict, feedback_type: str):
        """更新执行统计信息"""
        self.execution_stats['total_actions'] += 1
        
        if feedback.get('success'):
            self.execution_stats['success_count'] += 1
            self.execution_stats['consecutive_failures'] = 0
            self.execution_stats['last_success_step'] = self.execution_stats['total_actions']
            
            # 更新任务进度
            completed_obj = feedback.get('completed_object')
            if completed_obj and completed_obj not in self.task_progress['completed_objects']:
                self.task_progress['completed_objects'].append(completed_obj)
                if completed_obj in self.task_progress['remaining_objects']:
                    self.task_progress['remaining_objects'].remove(completed_obj)
        else:
            self.execution_stats['failure_count'] += 1
            self.execution_stats['consecutive_failures'] += 1
            
            # 记录失败尝试
            target_obj = feedback.get('target_object')
            if target_obj:
                if target_obj not in self.task_progress['failed_attempts']:
                    self.task_progress['failed_attempts'][target_obj] = 0
                self.task_progress['failed_attempts'][target_obj] += 1
    
    def store_action(self, action: Dict, feedback: Dict):
        """存储执行的动作及其反馈"""
        entry = {
            'step': len(self.action_history),
            'timestamp': time.time(),
            'action': action,
            'feedback': feedback
        }
        self.action_history.append(entry)
        self.long_action_history.append(entry)
        self.store_feedback(feedback)
    
    def update_task_progress(self, completed_objects: List[str] = None, 
                            remaining_objects: List[str] = None,
                            discovered_objects: List[str] = None):
        """更新任务进度"""
        if completed_objects:
            for obj in completed_objects:
                if obj not in self.task_progress['completed_objects']:
                    self.task_progress['completed_objects'].append(obj)
                if obj in self.task_progress['remaining_objects']:
                    self.task_progress['remaining_objects'].remove(obj)
        
        if remaining_objects:
            for obj in remaining_objects:
                if obj not in self.task_progress['remaining_objects']:
                    self.task_progress['remaining_objects'].append(obj)
        
        if discovered_objects:
            for obj in discovered_objects:
                if obj not in self.task_progress['discovered_objects']:
                    self.task_progress['discovered_objects'].append(obj)
    
    def should_trigger_reflection(self, step: int, regular_interval: int = 5) -> bool:
        """自适应反思触发判断"""
        # 1. 常规间隔触发
        if step > 0 and step % regular_interval == 0:
            return True
        
        # 2. 连续失败过多
        if self.execution_stats['consecutive_failures'] >= 3:
            return True
        
        # 3. 长时间无成功（任务可能停滞）
        steps_since_success = self.execution_stats['total_actions'] - self.execution_stats['last_success_step']
        if steps_since_success >= 5:
            return True
        
        # 4. 特定失败类型累计过多
        total_failures = sum(self.failure_types.values())
        if total_failures >= 3:
            return True
        
        return False
    
    def get_task_progress_summary(self) -> str:
        """获取任务进度摘要"""
        completed = len(self.task_progress['completed_objects'])
        remaining = len(self.task_progress['remaining_objects'])
        total = completed + remaining
        
        progress_pct = (completed / total * 100) if total > 0 else 0
        
        summary = f"Task Progress: {completed}/{total} ({progress_pct:.1f}%)\n"
        summary += f"  Completed: {', '.join(self.task_progress['completed_objects']) or 'None'}\n"
        summary += f"  Remaining: {', '.join(self.task_progress['remaining_objects']) or 'None'}\n"
        summary += f"  Discovered: {', '.join(self.task_progress['discovered_objects']) or 'None'}"
        
        return summary
    
    def get_execution_summary(self) -> str:
        """获取执行统计摘要"""
        stats = self.execution_stats
        total = stats['total_actions']
        if total == 0:
            return "No actions executed yet."
        
        success_rate = (stats['success_count'] / total * 100)
        
        summary = f"Execution Stats:\n"
        summary += f"  Total Actions: {total}\n"
        summary += f"  Success Rate: {success_rate:.1f}% ({stats['success_count']}/{total})\n"
        summary += f"  Consecutive Failures: {stats['consecutive_failures']}\n"
        summary += f"  Failure Breakdown:\n"
        for failure_type, count in self.failure_types.items():
            if count > 0:
                summary += f"    - {failure_type}: {count}\n"
        
        return summary
    
    def store_received_message(self, from_robot: str, content: str):
        """存储从其他机器人接收的消息"""
        self.received_message_history.append({
            'from': from_robot,
            'content': content,
            'step': len(self.action_history),
            'timestamp': time.time()
        })
    
    def store_self_description(self, description: str):
        """存储自我介绍"""
        self.self_description = description
    
    def store_task_plan(self, plan: Dict):
        """存储任务计划"""
        self.task_plan = plan
    
    def get_recent_history(self, k: int = None) -> List[Dict]:
        """获取最近k步的历史"""
        if k is None:
            k = self.max_history
        
        recent = []
        for i in range(min(k, len(self.action_history))):
            idx = len(self.action_history) - 1 - i
            recent.append({
                'action': list(self.action_history)[idx],
                'feedback': list(self.feedback_history)[idx] if idx < len(self.feedback_history) else None
            })
        return list(reversed(recent))
    
    def get_long_history(self) -> Tuple[List[Dict], List[Dict]]:
        """获取用于Reflection的长历史"""
        return list(self.long_action_history), list(self.long_feedback_history)
    
    def get_received_messages(self) -> List[Dict]:
        """获取接收到的消息历史"""
        return list(self.received_message_history)
    
    def format_history_for_prompt(self, k: int = 5) -> str:
        """将历史格式化为LLM prompt文本"""
        recent = self.get_recent_history(k)
        lines = ["Action and Feedback History:"]
        
        for item in recent:
            action = item['action']['action']
            feedback = item['feedback']
            step = item['action']['step']
            lines.append(f"  Step {step}: {action}")
            if feedback:
                status = "✓" if feedback.get('success') else "✗"
                msg = feedback.get('message', 'No feedback')
                lines.append(f"    -> {status} {msg}")
        
        return '\n'.join(lines)
    
    def format_messages_for_prompt(self) -> str:
        """将接收到的消息格式化为prompt文本"""
        messages = self.get_received_messages()
        if not messages:
            return "No messages received."
        
        lines = ["Received Messages:"]
        for msg in messages:
            lines.append(f"  From {msg['from']}: {msg['content']}")
        return '\n'.join(lines)


class ObservationModule:
    """
    观察模块 - 包含Scene Graph、Messages、Robot Info
    """
    
    def __init__(self, robot_agent):
        self.robot = robot_agent
        self.scene_graph = {}
        self.robot_info = {}
        
    def update_scene_graph(self, scene_data: Dict):
        """更新场景图 - 家具位置、朝向、开闭状态、物体位置"""
        self.scene_graph = scene_data
        
    def update_robot_info(self, pose: List[float], gripper_state: str = None, 
                         holding_object: str = None, max_grasp_range: float = 0.8):
        """更新机器人自身状态"""
        self.robot_info = {
            'robot_id': self.robot.name,
            'robot_type': self.robot.robot_type,
            'position': pose[:3] if pose else [0, 0, 0],
            'orientation': pose[3:] if pose and len(pose) > 3 else [0, 0, 0, 1],
            'gripper_state': gripper_state or 'unknown',
            'holding_object': holding_object,
            'max_grasp_range': max_grasp_range,
            'capabilities': self.robot.capabilities
        }
    
    def get_scene_graph_text(self) -> str:
        """将场景图格式化为文本"""
        if not self.scene_graph:
            return "Scene: No objects detected yet."
        
        lines = ["Scene Graph:"]
        for name, info in self.scene_graph.items():
            obj_type = info.get('type', 'object')
            pos = info.get('position', [0, 0, 0])
            state = info.get('state', '')
            state_str = f" ({state})" if state else ""
            lines.append(f"  - {name}: {obj_type} at ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}){state_str}")
        return '\n'.join(lines)
    
    def get_robot_info_text(self) -> str:
        """将机器人信息格式化为文本"""
        info = self.robot_info
        lines = [
            f"Robot: {info.get('robot_id')} ({info.get('robot_type')})",
            f"  Position: ({info['position'][0]:.2f}, {info['position'][1]:.2f}, {info['position'][2]:.2f})",
            f"  Gripper: {info.get('gripper_state', 'unknown')}",
        ]
        if info.get('holding_object'):
            lines.append(f"  Holding: {info['holding_object']}")
        lines.append(f"  Capabilities: {', '.join(info.get('capabilities', []))}")
        return '\n'.join(lines)


class RobotAgent:
    """
    机器人Agent - 去中心化的独立LLM Agent
    每个机器人有自己的Memory、Observation、Planning模块
    """
    
    # 不同机器人类型的动作集（Table II）
    # 支持中英文两种键名
    ACTION_SETS = {
        # English keys for robot types
        'MobileManipulation': ['navigate', 'open', 'pick', 'place', 'move', 'communicate', 'wait'],
        'Manipulator': ['pick', 'place', 'communicate', 'wait'],  # no navigate
        'Mobile': ['navigate', 'communicate', 'wait'],  # no pick/place
        'Drone': ['navigate', 'pick', 'place', 'communicate', 'wait']
    }
    
    def __init__(
        self,
        name: str,
        robot_type: str,  # MobileManipulation, Manipulator, Mobile, Drone
        capabilities: List[str],
        llm_client: Any,
        avatar: str = "🤖",
        max_history: int = 10
    ):
        self.name = name
        self.robot_type = robot_type
        self.capabilities = capabilities
        self.llm_client = llm_client
        self.avatar = avatar
        
        # 动作集
        self.available_actions = self.ACTION_SETS.get(robot_type, ['communicate', 'wait'])
        
        # 协作状态
        self.is_leader = False
        self.leader_name = None
        self.teammates = {}  # {name: description}
        self.current_phase = CollaborationPhase.SELF_DESCRIPTION
        
        # 执行状态
        self.step_count = 0
        self.current_action = None
        
        # 模块
        self.memory = MemoryModule(max_history=max_history)
        self.observation = ObservationModule(self)
        
        # 通信回调
        self.send_message_callback = None
        
    def set_message_callback(self, callback):
        """设置发送消息的回调函数"""
        self.send_message_callback = callback
    
    # ========== Stage 1: Self-Description ==========
    def self_describe(self, task: str) -> Tuple[str, str]:
        """
        Stage 1: Self-Description
        生成自我介绍，包括能力和对任务的理解
        
        Returns: (thought, description)
        """
        print(f"\n{'='*60}")
        print(f"[SELF-DESCRIPTION] Robot: {self.name} ({self.robot_type})")
        print(f"[SELF-DESCRIPTION] Task: {task[:80]}...")
        print(f"{'='*60}")
        
        prompt = self._build_self_description_prompt(task)
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt, temperature=0.9, max_tokens=1000)
                
                # 打印原响应用于调试
                print(f"[SELF-DESCRIPTION] Attempt {attempt+1}/{max_retries}")
                print(f"[SELF-DESCRIPTION] Raw response:\n{response[:200]}...")
                
                # 解析响应
                thought, description = self._parse_self_description_response(response)
                
                # 检查响应是否合规
                if description and len(description) >= 20:
                    print(f"[SELF-DESCRIPTION] ✓ Success! Parsed description ({len(description)} chars)")
                    print(f"[SELF-DESCRIPTION] Cleaned: {description[:100]}...")
                    
                    self.memory.store_self_description(description)
                    self.current_phase = CollaborationPhase.TASK_ALLOCATION
                    return thought if thought else "", description
                else:
                    print(f"[SELF-DESCRIPTION] ✗ Invalid response (too short or empty), retrying...")
                    
            except Exception as e:
                print(f"[SELF-DESCRIPTION] ✗ Error during generation: {str(e)}")
                continue
        
        # 如果多次尝试后仍然失败，使用默认自我介绍
        print(f"[SELF-DESCRIPTION] ⚠ All attempts failed, using default self-description")
        default_description = self._generate_default_self_description(task)
        self.memory.store_self_description(default_description)
        self.current_phase = CollaborationPhase.TASK_ALLOCATION
        return "", default_description
    
    def _generate_default_self_description(self, task: str) -> str:
        """Generate default self-description - used when LLM call fails"""
        robot_type_desc = {
            'Alice': 'mobile manipulation robot with wheeled chassis and robotic arm',
            'Bob': 'fixed manipulator',
            'David': 'mobile robot with wheeled chassis',
            'Lucy': 'drone with aerial operation capabilities'
        }
        
        desc = robot_type_desc.get(self.name, f'{self.robot_type} robot')
        caps = ', '.join(self.capabilities[:4]) if self.capabilities else 'perform various tasks'
        
        return f"Hi everyone! I'm {self.name}, a {desc}. I can {caps}. I'm ready to help the team complete this task."
    
    def _get_self_description_role(self) -> str:
        """Get role description for Self-Description stage - simplified in English"""
        robot_type_lower = self.robot_type.lower()
        
        if "mobile_manipulation" in robot_type_lower or "mobile manipulation" in robot_type_lower or self.name == "Alice":
            return f"Mobile manipulation robot. Configuration: wheeled chassis + single robotic arm. Capabilities: ground navigation, object manipulation (pick/place), transporting items, opening/closing articulated objects."
        
        elif ("manipulator" in robot_type_lower and "mobile" not in robot_type_lower) or "fixed manipulator" in robot_type_lower or self.name == "Bob":
            return f"Desktop manipulator. Configuration: fixed single robotic arm. Capabilities: precise manipulation within limited range, picking, placing."
        
        elif ("mobile" in robot_type_lower and "manipulation" not in robot_type_lower) or self.robot_type == "Mobile Robot" or self.name == "David":
            return f"Mobile robot. Configuration: wheeled chassis. Capabilities: ground navigation, movement, environment exploration. Limitations: cannot manipulate objects."
        
        elif "drone" in robot_type_lower or "aerial" in robot_type_lower or self.name == "Lucy":
            return f"Drone. Configuration: quadcopter + suction gripper. Capabilities: aerial navigation, aerial manipulation, global monitoring."
        
        else:
            caps = ', '.join(self.capabilities) if self.capabilities else 'perform various tasks'
            return f"{self.robot_type} robot. Capabilities: {caps}."
    
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
    
    def _build_self_description_prompt(self, task: str) -> str:
        """Build prompt for Self-Description stage - detailed format"""
        
        # Get teammates list
        teammates_str = ", ".join(self.teammates) if hasattr(self, 'teammates') and self.teammates else "other robots"
        
        # Get robot-specific role and skills
        role_desc, skills_desc = self._get_robot_role_and_skills()
        
        return f"""==== System Prompt ====
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
    
    def _parse_self_description_response(self, response: str) -> Tuple[str, str]:
        """Parse Self-Description response - parse Thoughts and Contents format"""
        original_response = response.strip()
        
        # If response is empty, return empty values
        if not original_response:
            print(f"[WARN] Empty response in self-description")
            return "", ""
        
        thought = ""
        content = ""
        
        # Try to parse standard format: "Thoughts: ... Contents: ..."
        lines = original_response.split('\n')
        in_thoughts = False
        in_contents = False
        thoughts_lines = []
        contents_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            line_lower = line_stripped.lower()
            
            # Detect "Thoughts:" section
            if line_lower.startswith('thoughts:') or line_lower.startswith('1) thoughts:'):
                in_thoughts = True
                in_contents = False
                # Extract content after colon
                if ':' in line_stripped:
                    thought_text = line_stripped.split(':', 1)[1].strip()
                    if thought_text:
                        thoughts_lines.append(thought_text)
                continue
            
            # Detect "Contents:" section
            if line_lower.startswith('contents:') or line_lower.startswith('2) contents:'):
                in_thoughts = False
                in_contents = True
                # Extract content after colon
                if ':' in line_stripped:
                    content_text = line_stripped.split(':', 1)[1].strip()
                    if content_text:
                        contents_lines.append(content_text)
                continue
            
            # Collect lines for current section
            if in_thoughts:
                thoughts_lines.append(line_stripped)
            elif in_contents:
                contents_lines.append(line_stripped)
        
        # Join collected lines
        if thoughts_lines:
            thought = ' '.join(thoughts_lines).strip()
        if contents_lines:
            content = ' '.join(contents_lines).strip()
        
        # Fallback: if no structured format found, treat entire response as content
        if not content and not thought:
            # Remove common markers
            cleaned = original_response
            for marker in ['Thoughts:', 'Contents:', 'thoughts:', 'contents:']:
                cleaned = cleaned.replace(marker, '').strip()
            content = cleaned
        
        # If only thought was found but no content, use thought as content
        if thought and not content:
            content = thought
            thought = ""
        
        # Clean content
        prefixes_to_remove = [
            'Contents:', 'Content:', 'Introduction:', 'Self-introduction:',
            'Response:', 'Answer:', 'Output:', 'Result:', 'Description:'
        ]
        for prefix in prefixes_to_remove:
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
        
        # Final validation
        if len(content) < 10:
            print(f"[WARN] Self-description content too short: {content}")
            # Fallback to default
            content = f"Hi everyone! I'm {self.name}, a {self.robot_type} robot ready to help with the task."
        
        return thought, content
    
    # ========== Stage 2: Task Allocation + Leadership Bidding ==========
    def propose_allocation(self, task: str, teammates_descriptions: Dict[str, str]) -> Tuple[Dict, str, str]:
        """
        Stage 2: Task Allocation and Leadership Bidding
        Propose task allocation plan and campaign speech
        
        Returns: (plan, thought, campaign_speech)
        """
        self.teammates = teammates_descriptions
        
        prompt = self._build_allocation_prompt(task, teammates_descriptions)
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=800)
                
                # 打印原响应用于调试
                print(f"\n{'='*60}")
                print(f"[TASK ALLOCATION] Robot: {self.name} (Attempt {attempt+1}/{max_retries})")
                print(f"{'='*60}")
                print(f"[RAW RESPONSE]\n{response}\n")
                
                plan, thought, campaign_speech = self._parse_allocation_response(response)
                
                # Print parsed results
                print(f"[PARSED] Thought length: {len(thought) if thought else 0}")
                print(f"[PARSED] Plan: {plan}")
                print(f"[PARSED] Campaign length: {len(campaign_speech) if campaign_speech else 0}")
                
                # Detect if response is in self-description format (wrong response)
                is_self_description = False
                check_text = (thought or "") + " " + (plan.get('description', '') if plan else "") + " " + (campaign_speech or "")
                if ("I am" in check_text and "robot" in check_text.lower() and "collaborate" not in check_text.lower()):
                    print(f"[WARNING] Detected self-description content in Task Allocation response!")
                    print(f"[WARNING] Content preview: {check_text[:100]}")
                    is_self_description = True
                
                # Success if any content exists and is not self-description format
                if (plan or thought or campaign_speech) and not is_self_description:
                    # Ensure plan is in dictionary format
                    if not plan:
                        plan = {'description': campaign_speech if campaign_speech else thought if thought else f'{self.name} will contribute to the task.'}
                    if not thought:
                        thought = "I will collaborate with my teammates effectively."
                    if not campaign_speech:
                        caps = ', '.join(self.capabilities)
                        campaign_speech = f"Vote for me! I have {caps} capabilities."
                    
                    self.memory.store_task_plan(plan)
                    self.current_phase = CollaborationPhase.LEADER_ELECTION
                    print(f"[SUCCESS] Task allocation completed for {self.name}")
                    return plan, thought, campaign_speech
                
                print(f"[RETRY] Empty response, retrying...")
                
            except Exception as e:
                print(f"[ERROR] API call failed for {self.name} (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1.0)  # Wait before retry
                    continue
                else:
                    break
        
        # If all attempts fail, return default values (Task Allocation format)
        print(f"[FAILED] All attempts failed for {self.name}, using defaults")
        caps = ', '.join(self.capabilities)
        
        # Build default response in Teamwork Plan format
        teammates_list = list(self.teammates.keys()) if hasattr(self, 'teammates') and self.teammates else ['teammates']
        plan_lines = [f"{self.name}: Coordinate task execution using my capabilities"]
        for teammate in teammates_list:
            plan_lines.append(f"{teammate}: Support task execution with their capabilities")
        
        default_plan = {
            'description': f"Team Collaboration Plan:\n" + ";\n".join(plan_lines)
        }
        default_thought = f"As {self.name}, I need to analyze this task and propose a collaboration strategy for our team. Given my capabilities ({caps}), I can contribute effectively to this mission."
        default_campaign = f"Hi team, I'm {self.name}. With my capabilities in {caps}, I'm ready to coordinate our efforts and lead this team to successfully complete the task. Vote for me to ensure efficient collaboration and task completion!"
        
        return default_plan, default_thought, default_campaign
    
    def _clean_allocation_content(self, content: str) -> str:
        """Clean prompt phrases and template repetition from task allocation response"""
        if not content:
            return content
        
        # Prompt phrases to remove
        prompt_phrases = [
            r'The user wants.*?\n',
            r'Robots available:',
            r'\d+\.\s*\w+\s*\(me\):.*?\n',
            r'Description: I am ready to help.*?\n',
            r'create a collaboration plan.*?\n',
            r'leadership campaign.*?\n',
        ]
        
        for phrase in prompt_phrases:
            content = re.sub(phrase, '', content, flags=re.IGNORECASE)
        
        # Clean up robot capability list repetition (if appears in thought/plan)
        content = re.sub(r'\d+\.\s*\w+:\s*.*?\(.*?\).*?\n', '', content)
        
        # Clean up extra empty lines
        content = '\n'.join([line for line in content.split('\n') if line.strip()])
        
        return content.strip()
    
    def _build_allocation_prompt(self, task: str, teammates: Dict[str, str]) -> str:
        """Build prompt for Task Allocation stage - detailed format"""
        # Format teammates' self-introductions
        teammates_info = "\n".join([f"- {name}: {desc}" for name, desc in teammates.items()])
        all_robots = [self.name] + list(teammates.keys())
        teammates_str = ", ".join(all_robots)
        
        return f"""==== System Prompt ====
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
{teammates_info}

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
    
    def _parse_allocation_response(self, response: str) -> Tuple[Dict, str, str]:
        """Parse Task Allocation response - supports new format with Thoughts and Contents"""
        plan = {}
        thought = ""
        campaign = ""
        
        response = response.strip()
        
        if not response:
            return plan, thought, campaign
        
        # First try to parse the expected format from MockLLMClient
        # Format: "Thoughts: ... Collaboration Plan: ... Campaign Speech: ..."
        
        # Extract Thought (everything after "Thoughts:" until "Collaboration Plan:")
        thought_match = re.search(r'Thoughts:\s*(.*?)(?=Collaboration Plan:|Campaign Speech:|$)', response, re.DOTALL | re.IGNORECASE)
        if thought_match:
            thought = thought_match.group(1).strip()
        
        # Extract Collaboration Plan (everything after "Collaboration Plan:" until "Campaign Speech:")
        plan_match = re.search(r'Collaboration Plan:\s*(.*?)(?=Campaign Speech:|$)', response, re.DOTALL | re.IGNORECASE)
        if plan_match:
            plan_text = plan_match.group(1).strip()
            if plan_text:
                plan = {'description': plan_text}
        
        # Extract Campaign Speech (everything after "Campaign Speech:")
        campaign_match = re.search(r'Campaign Speech:\s*(.+)', response, re.DOTALL | re.IGNORECASE)
        if campaign_match:
            campaign = campaign_match.group(1).strip()
        
        # If the above didn't work, try the old parsing method
        if not thought and not plan and not campaign:
            return self._parse_allocation_response_old_format(response)
        
        # Clean up
        if thought:
            thought = self._clean_allocation_content(thought)
        if campaign:
            campaign = self._clean_allocation_content(campaign)
        
        # Ensure plan has content
        plan_desc = plan.get('description', '') if plan else ''
        if not plan_desc or len(plan_desc) < 30:
            plan = {'description': f"As {self.name}, I will collaborate with teammates to divide the task efficiently. Each robot will handle subtasks matching their capabilities, working in parallel to complete the mission."}
        
        # Ensure thought has content
        if not thought or len(thought) < 30:
            thought = f"Analyzing the task requirements and team capabilities. We need to divide work based on each robot's strengths and coordinate effectively for parallel execution."
        
        # Ensure campaign has content
        if not campaign or len(campaign) < 30:
            campaign = f"Hi team, I'm {self.name}. With my capabilities and leadership skills, I will coordinate our efforts to complete this task efficiently. Vote for me to ensure smooth collaboration and successful mission completion!"
        
        return plan, thought, campaign
    
    def _parse_allocation_response_old_format(self, response: str) -> Tuple[Dict, str, str]:
        """Fallback parsing for old format (Thought/Plan/Campaign Speech)"""
        plan = {}
        thought = ""
        campaign = ""
        
        # Simple format markers
        thought_markers = ['Thought:', 'Thought：', 'thought:', 'THOUGHT:']
        plan_markers = ['Plan:', 'Plan：', 'plan:', 'PLAN:', 'Collaboration Plan:']
        campaign_markers = ['Campaign Speech:', 'Campaign:', 'Campaign：', 'campaign:', 'CAMPAIGN:', 'Speech:']
        
        def find_marker_pos(text, markers):
            for marker in markers:
                pos = text.find(marker)
                if pos != -1:
                    return pos, marker
            return -1, None
        
        thought_pos, thought_marker = find_marker_pos(response, thought_markers)
        plan_pos, plan_marker = find_marker_pos(response, plan_markers)
        campaign_pos, campaign_marker = find_marker_pos(response, campaign_markers)
        
        # Extract based on positions
        positions = []
        if thought_pos != -1:
            positions.append((thought_pos, 'thought', thought_marker))
        if plan_pos != -1:
            positions.append((plan_pos, 'plan', plan_marker))
        if campaign_pos != -1:
            positions.append((campaign_pos, 'campaign', campaign_marker))
        
        positions.sort()
        
        for i, (pos, part_type, marker) in enumerate(positions):
            start = pos + len(marker)
            end = positions[i+1][0] if i+1 < len(positions) else len(response)
            content = response[start:end].strip()
            
            if part_type == 'thought':
                thought = content
            elif part_type == 'plan':
                plan = {'description': content}
            elif part_type == 'campaign':
                campaign = content
        
        return plan, thought, campaign
    
    # ========== Stage 3: Leader Election ==========
    def vote_leader(self, proposals: Dict[str, Tuple[Dict, str, str]]) -> Tuple[str, str, str]:
        """
        Stage 3: Leader Election
        分析所有提案并投票
        
        proposals: {robot_name: (plan, thought, campaign_speech)}
        Returns: (vote_for, thought, reasoning)
        """
        prompt = self._build_election_prompt(proposals)
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=1000)
                
                # 打印原响应用于调试
                print(f"[DEBUG] Leader Election Response (attempt {attempt+1}): {response}")
                
                vote_for, thought, reasoning = self._parse_election_response(response, list(proposals.keys()))
                
                # 检查响应是否合规
                if thought and reasoning:
                    # 更新领导者状态
                    self.leader_name = vote_for
                    self.is_leader = (vote_for == self.name)
                    self.current_phase = CollaborationPhase.EXECUTION
                    return vote_for, thought, reasoning
                
                print(f"[DEBUG] Invalid response, retrying...")
                
            except Exception as e:
                print(f"[ERROR] API call failed for {self.name} in vote_leader (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1.0)  # 等待后重试
                    continue
                else:
                    break
        
        # 如果多次尝试后仍然失败，返回默认值
        print(f"[FAILED] vote_leader failed for {self.name}, using defaults")
        default_vote = list(proposals.keys())[0] if proposals else self.name
        return default_vote, f"I vote for {default_vote}.", f"{default_vote} seems capable of leading the team."
    
    def _build_election_prompt(self, proposals: Dict[str, Tuple[Dict, str, str]]) -> str:
        """Build prompt for Leader Election stage - detailed format"""
        # Format proposals
        if not proposals:
            proposals_text = "\nNo proposals available."
        else:
            proposals_text = ""
            for name, (plan, thought, campaign) in proposals.items():
                proposals_text += f"\n=== {name}'s Proposal ===\n"
                if isinstance(plan, dict):
                    plan_desc = plan.get('description', 'No plan')
                else:
                    plan_desc = str(plan) if plan else 'No plan'
                proposals_text += f"Collaboration Plan: {plan_desc}\n"
                proposals_text += f"Campaign Speech: {campaign}\n"
        
        return f"""==== System Prompt ====
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
    
    def _parse_election_response(self, response: str, candidates: List[str]) -> Tuple[str, str, str]:
        """Parse Leader Election response - new format: Thoughts/Reasons/Leader"""
        thought = ""
        vote = candidates[0] if candidates else self.name
        reasoning = ""
        
        response = response.strip()
        
        if not response:
            return vote, thought, reasoning
        
        # Handle markdown code blocks
        if "```" in response:
            code_blocks = re.findall(r'```(?:\w+)?\n?(.*?)```', response, re.DOTALL)
            if code_blocks:
                response = code_blocks[0].strip()
        
        # New format markers
        thought_markers = ['Thoughts:', 'Thoughts：', '1) Thoughts:', 'thoughts:']
        reasons_markers = ['Reasons:', 'Reasons：', '2) Reasons:', 'reasons:']
        leader_markers = ['Leader:', 'Leader：', '3) Leader:', 'leader:']
        
        # Fallback markers for old format
        thought_markers_old = ['Thought:', 'Thought：', 'thought:']
        vote_markers_old = ['Vote:', 'Vote：', 'vote:']
        reasoning_markers_old = ['Reasoning:', 'Reasoning：', 'reasoning:']
        
        def find_marker_pos(text, markers):
            for marker in markers:
                pos = text.find(marker)
                if pos != -1:
                    return pos, marker
            return -1, None
        
        # Try new format first
        thought_pos, thought_marker = find_marker_pos(response, thought_markers)
        reasons_pos, reasons_marker = find_marker_pos(response, reasons_markers)
        leader_pos, leader_marker = find_marker_pos(response, leader_markers)
        
        # If new format not found, try old format
        if thought_pos == -1 and reasons_pos == -1 and leader_pos == -1:
            thought_pos, thought_marker = find_marker_pos(response, thought_markers_old)
            leader_pos, leader_marker = find_marker_pos(response, vote_markers_old)
            reasons_pos, reasons_marker = find_marker_pos(response, reasoning_markers_old)
        
        # Extract sections
        positions = []
        if thought_pos != -1:
            positions.append((thought_pos, 'thought', thought_marker))
        if reasons_pos != -1:
            positions.append((reasons_pos, 'reasoning', reasons_marker))
        if leader_pos != -1:
            positions.append((leader_pos, 'leader', leader_marker))
        
        positions.sort()
        
        for i, (pos, part_type, marker) in enumerate(positions):
            start = pos + len(marker)
            end = positions[i+1][0] if i+1 < len(positions) else len(response)
            content = response[start:end].strip()
            
            if part_type == 'thought':
                thought = content
            elif part_type == 'reasoning':
                reasoning = content
            elif part_type == 'leader':
                # Find matching candidate
                for candidate in candidates:
                    if candidate.lower() in content.lower():
                        vote = candidate
                        break
                # If no match, try searching entire response
                if vote == candidates[0]:
                    for candidate in candidates:
                        if candidate in response:
                            vote = candidate
                            break
        
        # Fallback: if nothing extracted, use entire response
        if not thought and not reasoning and response:
            thought = response
        
        return vote, thought, reasoning
    
    # ========== Stage 4: Closed-Loop Execution ==========
    def plan_next_action(self, task: str, leader_plan: Dict, scene_graph: Dict, 
                        robot_pose: List[float]) -> Tuple[Dict, str]:
        """
        Stage 4: Closed-Loop Execution - Next Action Prediction
        基于观察和历史规划下一个原子动作
        
        Returns: (action_dict, thought)
        """
        # 更新观察
        self.observation.update_scene_graph(scene_graph)
        self.observation.update_robot_info(robot_pose)
        
        prompt = self._build_execution_prompt(task, leader_plan)
        
        response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=1000)
        
        action, thought = self._parse_execution_response(response)
        
        # 验证动作是否在能力范围内
        if action.get('type') not in self.available_actions:
            action = {'type': 'wait', 'reason': f"Action {action.get('type')} not available for {self.robot_type}"}
        
        self.current_action = action
        
        return action, thought
    
    def _get_execution_principles(self) -> str:
        """获取Execution阶段特定原则 - 基于论文Tab. VII，增强协作通信"""
        robot_type_lower = self.robot_type.lower()
        
        if "mobile_manipulation" in robot_type_lower or self.name == "Alice":
            return """1) Efficiently explore and navigate all locations in the scene graph without repetition.
2) Transport task-related items promptly.
3) When facing inaccessible areas, proactively COMMUNICATE with capable assistants.
4) Track task progress and adjust targets timely.
5) Respond promptly to collaborators' requests and messages.
6) If grasp fails, try other stand poses or adjust base position.
7) PROACTIVELY use COMMUNICATE action to coordinate with teammates when needed.
8) Focus on completing the task without unrelated actions.

COMMUNICATION GUIDELINES:
- Use COMMUNICATE action to request help, share discoveries, or coordinate with teammates
- Choose appropriate target: specific robot name for unicast, 'all' for broadcast
- Example: COMMUNICATE: Please help transport the cup to the kitchen"""
        
        elif "manipulator" in robot_type_lower and "mobile" not in robot_type_lower or self.name == "Bob":
            return """1) Analyze tasks and scene graphs, prioritizing your work.
2) CRITICAL: Since you are FIXED and cannot move, you MUST use COMMUNICATE action to request mobile robots to deliver distant objects.
3) Notify collaborators of task progress timely.
4) Track progress changes and adjust targets as needed.
5) Respond promptly to collaborators' requests.
6) PROACTIVELY communicate your limitations and request help from mobile teammates.
7) Focus on task completion without unrelated actions.

COMMUNICATION GUIDELINES:
- Use COMMUNICATE action FREQUENTLY to request mobile robots to deliver objects
- Example: "Alice, please bring the cup from the kitchen to me"
- You cannot navigate, so you MUST rely on communication for collaboration"""
        
        elif "mobile" in robot_type_lower and "manipulation" not in robot_type_lower or self.name == "David":
            return """1) Efficiently explore and navigate all locations in the scene graph without repetition.
2) Notify collaborators of task items and request manipulation-capable teammates for pickup.
3) Notify capable assistants to explore inaccessible areas.
4) Request collaborators to open objects for exploration.
5) Track task progress and adjust targets timely.
6) Respond promptly to assistants' messages.
7) Use COMMUNICATE to share discovered objects with teammates.
8) Focus on completing the task without unrelated actions.

COMMUNICATION GUIDELINES:
- Use COMMUNICATE action to inform teammates about discovered objects
- Request manipulation-capable robots (like Alice or Bob) to pick up items you find
- Example: I found a cup at the kitchen table, Alice please pick it up
"""
        
        elif "drone" in robot_type_lower or self.name == "Lucy":
            return """1) Efficiently explore and navigate all locations in the scene graph without repetition.
2) Transport task-related items promptly.
3) Request collaborators to open objects for exploration.
4) Track task progress and adjust targets timely.
5) Respond promptly to collaborators' requests.
6) Use COMMUNICATE to share aerial observations with ground robots.
7) Focus on task completion without unrelated actions.

COMMUNICATION GUIDELINES:
- Use COMMUNICATE action to share aerial view information
- Inform ground robots about high locations or objects they cannot see
- Example: I spotted an object on top of the cabinet"""
        
        else:
            return """1) Follow the task plan and execute actions efficiently.
2) Track task progress and adjust targets timely.
3) Respond promptly to collaborators' requests.
4) Use COMMUNICATE action when coordination is needed.
5) Focus on completing the task without unrelated actions."""
    
    def _get_execution_role_and_skills(self) -> Tuple[str, str, str]:
        """Get robot-specific Role, Skills and Principles for Execution stage - detailed format"""
        name = self.name
        
        if name == "Alice":
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured with a wheeled chassis and a single manipulator arm.
2) You possess the ability to navigate across the ground and perform manipulation tasks."""
            skills = """# Skills (Atomic Action Set):
1) [navigate] to <stand_pose_id> of <object>: Move to predefined pose near target
2) [open] <container>: Open hinged container to access contents
3) [pick] up <object>: Grasp object with manipulator arm
4) [place] <object> on/into <platform>: Place held object at target location
5) [move] <delta_x> and <delta_y>: Adjust base position for better reach (requires local costmap)
6) [communicate] <content> to <role>: Send message to teammate(s)
7) [wait]: Pause execution"""
            principles = """# Principles:
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
            role = f"""# Role:
1) You are an intelligent robot named {name}, configuration is a single robotic arm fixed on a desktop.
2) You are capable of manipulating within a limited range around your fixed base."""
            skills = """# Skills (Atomic Action Set):
1) [pick] up <object>: Grasp object within your operational range
2) [place] <object> on/into <platform>: Place held object at target location
3) [communicate] <content> to <role>: Send message to teammate(s)
4) [wait]: Pause execution"""
            principles = """# Principles:
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
            role = f"""# Role:
1) You are an intelligent robot named {name}, configuration is a wheeled chassis.
2) You can navigate and move on the ground, cannot manipulate any objects and cannot open any hinged objects."""
            skills = """# Skills (Atomic Action Set):
1) [navigate] to <stand_pose_id> of <object>: Move to predefined pose near target
2) [communicate] <content> to <role>: Send message to teammate(s)
3) [wait]: Pause execution"""
            principles = """# Principles:
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
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured as a quadrotor drone with a fixed suction gripper.
2) You are capable of aerial navigation and manipulation in elevated areas."""
            skills = """# Skills (Atomic Action Set):
1) [navigate] to <stand_pose_id> of <object>: Fly to predefined pose near target
2) [pick] up <object>: Grasp lightweight object with suction gripper
3) [place] <object> on/into <platform>: Place held object at target location
4) [communicate] <content> to <role>: Send message to teammate(s)
5) [wait]: Hover and wait"""
            principles = """# Principles:
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
            role = f"""# Role:
1) You are an intelligent robot named {name}, configured as a {self.robot_type}.
2) You are capable of various tasks based on your configuration."""
            skills = f"""# Skills (Atomic Action Set):
{chr(10).join([f'{i+1}) [{action}]' for i, action in enumerate(self.available_actions)])}"""
            principles = """# Principles:
1) Follow the task plan and execute actions efficiently.
2) Track task progress and adjust targets timely.
3) Respond promptly to collaborators' requests.
4) Use COMMUNICATE action when coordination is needed.
5) Focus on completing the task without unrelated or redundant actions."""
        
        return role, skills, principles
    
    def _build_execution_prompt(self, task: str, leader_plan: Dict) -> str:
        """Build prompt for Execution stage - detailed format"""
        # Get history
        history_text = self.memory.format_history_for_prompt(k=5)
        messages_text = self.memory.format_messages_for_prompt()
        scene_text = self.observation.get_scene_graph_text()
        robot_text = self.observation.get_robot_info_text()
        
        # Task progress
        completed = len([a for a in self.memory.action_history if a['feedback'].get('success')])
        total = len(self.memory.action_history) + 1
        
        # Get robot-specific role, skills, and principles
        role_desc, skills_desc, principles_desc = self._get_execution_role_and_skills()
        
        # Teammates info
        teammates_str = ", ".join(self.teammates) if hasattr(self, 'teammates') and self.teammates else "other robots"
        
        # Leader requirement
        leader_req = f"Follow {self.leader_name}'s guidance and collaborate with teammates." if not self.is_leader else "You are the leader. Coordinate the team effectively."
        
        return f"""==== System Prompt ====
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
4) {self.leader_name} is the elected leader and proposed the collaboration plan: {leader_plan.get('description', 'Execute task step by step')}. Thus, all robots should follow this plan while adapting to real-time feedback.

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
Latest Task Progress Status: {completed}/{total} steps completed.

# Scene Graph:
{scene_text}

# Robot Status:
Current robot states: {robot_text}

# Feedback History:
The historical feedbacks, from oldest to newest, are as follows:
{history_text}

# Action History:
The historical actions, from oldest to newest, are as follows:
{self.memory.format_history_for_prompt(k=5)}

# Receive Message History:
The historical receive messages, from oldest to newest, are as follows:
{messages_text}

# Available Actions:
Choose and execute ONLY ONE action from your robot's action set below.

# Output Response Format:
1) Thoughts: think step by step to analyze the current situation, task progress, and optimal next action;
2) Contents: output exactly ONE action in the format: [action_name](arguments)"""
    
    def _parse_execution_response(self, response: str) -> Tuple[Dict, str]:
        """Parse Execution response - new format: Thoughts/Contents"""
        thought = ""
        action = {'type': 'wait'}
        
        if not response:
            return action, thought
        
        response = response.strip()
        
        # Handle markdown code blocks
        if "```" in response:
            code_blocks = re.findall(r'```(?:\w+)?\n?(.*?)```', response, re.DOTALL)
            if code_blocks:
                response = code_blocks[0].strip()
        
        # Try new format first: "Thoughts:" and "Contents:"
        thoughts_markers = ['Thoughts:', 'Thoughts：', '1) Thoughts:', 'thoughts:']
        contents_markers = ['Contents:', 'Contents：', '2) Contents:', 'contents:']
        
        # Find Thoughts section
        thoughts_start = -1
        thoughts_marker_len = 0
        for marker in thoughts_markers:
            pos = response.lower().find(marker.lower())
            if pos != -1:
                thoughts_start = pos + len(marker)
                thoughts_marker_len = len(marker)
                break
        
        # Find Contents section
        contents_start = -1
        contents_marker_len = 0
        for marker in contents_markers:
            pos = response.lower().find(marker.lower())
            if pos != -1:
                contents_start = pos + len(marker)
                contents_marker_len = len(marker)
                break
        
        # Extract thought
        if thoughts_start != -1:
            if contents_start != -1 and contents_start > thoughts_start:
                thought = response[thoughts_start:contents_start - contents_marker_len].strip()
            else:
                # Thoughts goes to end or until next section
                thought = response[thoughts_start:].strip()
                # Limit thought length if Contents is not found
                lines = thought.split('\n')
                if len(lines) > 1:
                    thought = lines[0].strip()
        
        # Extract action from Contents
        if contents_start != -1:
            contents_text = response[contents_start:].strip()
            # Parse action from contents
            action = self._parse_action_from_text(contents_text)
        
        # Fallback to old format if new format not found
        if not thought and action['type'] == 'wait':
            return self._parse_execution_response_old_format(response)
        
        return action, thought
    
    def _parse_action_from_text(self, text: str) -> Dict:
        """Parse action from text content"""
        action = {'type': 'wait'}
        text_lower = text.lower().strip()
        
        # Look for action patterns like [navigate], navigate, etc.
        action_patterns = [
            (r'\[?navigate\]?.*?(?:to|location)?[:\s]+(\w+)', 'navigate'),
            (r'\[?pick\]?.*?(?:up)?[:\s]+(\w+)', 'pick'),
            (r'\[?place\]?[:\s]+(\w+)', 'place'),
            (r'\[?open\]?[:\s]+(\w+)', 'open'),
            (r'\[?move\]?[:\s]+([\d\s,]+)', 'move'),
            (r'\[?communicate\]?[:\s]+(.+?)(?:\s+to\s+(\w+)|$)', 'communicate'),
            (r'\[?wait\]?', 'wait'),
        ]
        
        for pattern, action_type in action_patterns:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                action = {'type': action_type}
                groups = match.groups()
                if action_type == 'navigate' and groups[0]:
                    action['location'] = groups[0].strip()
                elif action_type == 'pick' and groups[0]:
                    action['object'] = groups[0].strip()
                elif action_type == 'place' and groups[0]:
                    action['object'] = groups[0].strip()
                elif action_type == 'open' and groups[0]:
                    action['object'] = groups[0].strip()
                elif action_type == 'move' and groups[0]:
                    coords = groups[0].replace(',', ' ').split()
                    if len(coords) >= 2:
                        action['delta_x'] = coords[0]
                        action['delta_y'] = coords[1]
                elif action_type == 'communicate':
                    if groups[0]:
                        action['content'] = groups[0].strip()
                    if len(groups) > 1 and groups[1]:
                        action['target'] = groups[1].strip()
                    else:
                        action['target'] = 'all'
                break
        
        # If no specific pattern matched, check for simple action name
        if action['type'] == 'wait':
            available_actions = ['navigate', 'pick', 'place', 'open', 'move', 'communicate', 'wait']
            for act in available_actions:
                if act in text_lower:
                    action = {'type': act}
                    break
        
        return action
    
    def _parse_execution_response_old_format(self, response: str) -> Tuple[Dict, str]:
        """Fallback parsing for old format (Thought/Action/Parameters)"""
        thought = ""
        action = {'type': 'wait'}
        
        if "Thought:" in response:
            thought_part = response.split("Thought:")[1]
            if "Action:" in thought_part:
                thought = thought_part.split("Action:")[0].strip()
            else:
                thought = thought_part.strip()
        
        if "Action:" in response:
            action_part = response.split("Action:")[1]
            if "Parameters:" in action_part:
                action_text = action_part.split("Parameters:")[0].strip()
                params_text = action_part.split("Parameters:")[1].strip()
            else:
                action_text = action_part.strip()
                params_text = ""
            
            action_type = action_text.split()[0].lower() if action_text else 'wait'
            
            # Parse parameters
            params = {}
            if params_text:
                try:
                    params = json.loads(params_text)
                except:
                    params = {'raw': params_text}
            
            action = {'type': action_type, **params}
        
        return action, thought
    
    def execute_action(self, action: Dict) -> Dict:
        """
        执行动作并返回详细反馈
        符合Table I的反馈类型
        """
        action_type = action.get('type')
        
        # 模拟执行（实际应调用BestMan API）
        if action_type == 'navigate':
            return self._simulate_navigate(action)
        elif action_type == 'pick':
            return self._simulate_pick(action)
        elif action_type == 'place':
            return self._simulate_place(action)
        elif action_type == 'open':
            return self._simulate_open(action)
        elif action_type == 'move':
            return self._simulate_move(action)
        elif action_type == 'communicate':
            return self._simulate_communicate(action)
        elif action_type == 'wait':
            return {'success': True, 'message': '等待下一步指令', 'type': 'wait'}
        else:
            return {'success': False, 'message': f'未知动作类型: {action_type}', 'type': 'action_failed'}
    
    def _simulate_navigate(self, action: Dict) -> Dict:
        """模拟导航动作"""
        target = action.get('target', 'unknown')
        # 模拟成功率
        import random
        success = random.random() > 0.1  # 90%成功率
        
        if success:
            # 更新场景图（可能发现新物体）
            return {
                'success': True,
                'message': f'导航成功: 成功导航到 {target}',
                'type': 'navigate_success',
                'found_objects': [f'object_at_{target}']
            }
        else:
            return {
                'success': False,
                'message': f'导航失败: 到 {target} 的路径被阻塞',
                'type': 'navigate_failed'
            }
    
    def _simulate_pick(self, action: Dict) -> Dict:
        """模拟拾取动作"""
        target = action.get('target_object', 'unknown')
        import random
        
        # 检查是否在范围内（模拟）
        in_range = random.random() > 0.2
        
        if not in_range:
            return {
                'success': False,
                'message': f'拾取失败: 夹爪与 {target} 的距离超过阈值',
                'type': 'pick_failed',
                'reason': 'out_of_range'
            }
        
        success = random.random() > 0.1
        if success:
            return {
                'success': True,
                'message': f'拾取成功: 成功抓取 {target}',
                'type': 'pick_success',
                'grasped_object': target
            }
        else:
            return {
                'success': False,
                'message': f'拾取失败: 抓取姿态发生碰撞或无法到达',
                'type': 'pick_failed',
                'reason': 'collision'
            }
    
    def _simulate_place(self, action: Dict) -> Dict:
        """模拟放置动作"""
        target = action.get('target_object', 'unknown')
        location = action.get('target_location', 'unknown')
        
        import random
        success = random.random() > 0.1
        
        if success:
            return {
                'success': True,
                'message': f'放置成功: 成功将 {target} 放置在 {location}',
                'type': 'place_success'
            }
        else:
            return {
                'success': False,
                'message': f'放置失败: 目标位置已被占用或无法到达',
                'type': 'place_failed'
            }
    
    def _simulate_open(self, action: Dict) -> Dict:
        """模拟打开动作"""
        container = action.get('target_container', 'unknown')
        
        return {
            'success': True,
            'message': f'打开成功: 成功打开 {container}',
            'type': 'open_success',
            'contents': []
        }
    
    def _simulate_move(self, action: Dict) -> Dict:
        """模拟微调移动动作"""
        delta_x = action.get('delta_x', 0)
        delta_y = action.get('delta_y', 0)
        
        return {
            'success': True,
            'message': f'移动成功: 成功移动 ({delta_x}, {delta_y})',
            'type': 'move_success'
        }
    
    def _simulate_communicate(self, action: Dict) -> Dict:
        """模拟通信动作"""
        content = action.get('content', '')
        target = action.get('target', 'all')
        
        # 调用回调发送消息
        if self.send_message_callback:
            self.send_message_callback(self.name, target, content)
        
        return {
            'success': True,
            'message': f'通信: 消息已发送给 {target}',
            'type': 'communicate',
            'content': content
        }
    
    def store_execution_result(self, action: Dict, feedback: Dict):
        """存储执行结果到记忆"""
        self.memory.store_action(action, feedback)
        self.step_count += 1
    
    # ========== Stage 4b: Reflection ==========
    def reflect(self, task: str, team_reflections: Dict[str, str] = None) -> Tuple[str, str, str]:
        """
        Reflection Stage - 基于论文Tab. VIII-IX
        总结执行经验，提出未来计划
        
        Args:
            task: 任务描述
            team_reflections: 其他机器人的反思结果（仅leader需要）
        
        Returns: (thought, summary, future_plan)
        """
        # 获取长历史
        long_actions, long_feedbacks = self.memory.get_long_history()
        
        prompt = self._build_reflection_prompt(task, long_actions, long_feedbacks, team_reflections)
        
        response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=500)
        
        thought, summary, future_plan = self._parse_reflection_response(response)
        
        self.current_phase = CollaborationPhase.EXECUTION
        
        return thought, summary, future_plan
    
    def _build_reflection_prompt(self, task: str, actions: List[Dict], feedbacks: List[Dict], team_reflections: Dict[str, str] = None) -> str:
        """Build prompt for Reflection stage - detailed format"""
        # Statistics
        successes = sum(1 for f in feedbacks if f.get('success'))
        failures = len(feedbacks) - successes
        
        # Recent actions
        recent_actions = actions[-10:] if len(actions) > 10 else actions
        actions_text = "\n".join([f"  Step {a['step']}: {a['action']} -> {a['feedback'].get('message', '')}" 
                                  for a in recent_actions])
        
        # Format team reflections for leader
        team_reflections_text = ""
        if team_reflections:
            for name, reflection in team_reflections.items():
                team_reflections_text += f"\n=== {name} ===\n{reflection}\n"
        
        # Choose prompt based on leader status
        if self.is_leader:
            # Leader Reflection Prompt
            return f"""==== Leader System Prompt ====
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

{team_reflections_text}

# Format of Team Input:
Each entry contains:
- Robot: <name>
- Type: <robot_type>
- Successes: <list>
- Failures: <list>
- Proposed Next Tasks: <list>
- Requests: <list>

# Current Global State:
Overall task progress: {successes}/{len(feedbacks)} successful steps
Total Steps: {len(actions)}
Successes: {successes}
Failures: {failures}

Recent Actions:
{actions_text}

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
        else:
            # Participant Reflection Prompt
            return f"""==== Participants System Prompt ====
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
Target task: {task}
Current progress: {successes}/{len(feedbacks)} successful steps
Remaining subtasks: to be determined based on scene exploration

# Your Extended History (last {len(actions)} steps):
## Your Action History:
{actions_text}

## Your Feedback History:
Recent feedbacks from oldest to newest:
{chr(10).join([f"- Step {f.get('step', i)}: {f.get('message', 'No message')}" for i, f in enumerate(feedbacks[-10:])])}

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
    
    def _parse_reflection_response(self, response: str) -> Tuple[str, str, str]:
        """解析Reflection响应 - 支持Participant和Leader两种格式"""
        thought = ""
        summary = ""
        future_plan = ""
        
        response = response.strip()
        
        # 解析Thought (两种格式都有)
        if "Thought:" in response:
            thought_part = response.split("Thought:")[1]
            # 检查是否有Summaries (Participant格式) 或 Contents (Leader格式)
            if "Summaries:" in thought_part:
                thought = thought_part.split("Summaries:")[0].strip()
            elif "Plans:" in thought_part:
                thought = thought_part.split("Plans:")[0].strip()
            elif "Contents:" in thought_part:
                thought = thought_part.split("Contents:")[0].strip()
            else:
                thought = thought_part.strip()
        
        # Participant格式: Summaries 和 Plans
        if "Summaries:" in response:
            summaries_part = response.split("Summaries:")[1]
            if "Plans:" in summaries_part:
                summary = summaries_part.split("Plans:")[0].strip()
            else:
                summary = summaries_part.strip()
        
        if "Plans:" in response:
            plans_part = response.split("Plans:")[1]
            future_plan = plans_part.strip()
        
        # Leader格式: Contents (包含最终计划)
        if "Contents:" in response:
            contents_part = response.split("Contents:")[1].strip()
            # Leader的输出作为summary
            if not summary:
                summary = "Leader's consolidated plan"
            if not future_plan:
                future_plan = contents_part
        
        # 兼容旧格式: Summary 和 Future Plan
        if not summary and "Summary:" in response:
            summary_part = response.split("Summary:")[1]
            if "Future Plan:" in summary_part:
                summary = summary_part.split("Future Plan:")[0].strip()
            else:
                summary = summary_part.strip()
        
        if not future_plan and "Future Plan:" in response:
            future_plan = response.split("Future Plan:")[1].strip()
        
        return thought, summary, future_plan
    
    def update_leader_plan(self, team_reflections: Dict[str, Tuple[str, str, str]]) -> Tuple[str, str]:
        """
        Leader整合团队反思并更新计划
        
        team_reflections: {robot_name: (thought, summary, future_plan)}
        Returns: (thought, updated_plan)
        """
        if not self.is_leader:
            return "", ""
        
        # 整合所有反思
        reflections_text = ""
        for name, (thought, summary, future) in team_reflections.items():
            reflections_text += f"\n=== {name} ===\nSummary: {summary}\nFuture Plan: {future}\n"
        
        prompt = f"""You are {self.name}, the leader of the team.

## Team Reflections
{reflections_text}

## Instructions
As the leader, integrate the team's reflections and propose an updated plan for continuing or future tasks.

## Output Format
Thought: <Your integration reasoning>
Updated Plan: <The new plan based on team feedback>"""
        
        response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=1000)
        
        # 解析反思响应
        thought = ""
        updated_plan = ""
        
        if "Thought:" in response:
            thought = response.split("Thought:")[1].split("Updated Plan:")[0].strip() if "Updated Plan:" in response else ""
        
        if "Updated Plan:" in response:
            updated_plan = response.split("Updated Plan:")[1].strip()
        
        return thought, updated_plan
    
    # ========== Dynamic Replanning ==========
    def should_trigger_replanning(self) -> Tuple[bool, str]:
        """
        判断是否触发动态重规划
        Returns: (should_trigger, reason)
        """
        # 条件1: 连续失败过多（机器人故障或任务困难）
        if self.memory.execution_stats['consecutive_failures'] >= 3:
            return True, "consecutive_failures"
        
        # 条件2: 特定任务对象失败次数过多
        for obj, count in self.memory.task_progress['failed_attempts'].items():
            if count >= 3:
                return True, f"object_failure:{obj}"
        
        # 条件3: 长时间无进展
        steps_since_success = (self.memory.execution_stats['total_actions'] - 
                              self.memory.execution_stats['last_success_step'])
        if steps_since_success >= 8:
            return True, "stalled_progress"
        
        # 条件4: 任务完成度低但步数已过半
        total_actions = self.memory.execution_stats['total_actions']
        success_count = self.memory.execution_stats['success_count']
        if total_actions > 10 and success_count / total_actions < 0.3:
            return True, "low_efficiency"
        
        return False, ""
    
    def reallocate_tasks(self, task: str, teammates: Dict[str, str], 
                        completed_objects: List[str], failed_objects: List[str],
                        execution_history: str) -> Tuple[Dict, str, str]:
        """
        动态重规划 - 重新分配任务
        
        Args:
            task: 原始任务
            teammates: 队友描述
            completed_objects: 已完成的对象
            failed_objects: 失败的对象列表
            execution_history: 执行历史摘要
        
        Returns: (new_plan, thought, campaign_speech)
        """
        self.teammates = teammates
        
        prompt = self._build_reallocation_prompt(
            task, teammates, completed_objects, failed_objects, execution_history
        )
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=800)
                
                print(f"\n{'='*60}")
                print(f"[REALLOCATION] Robot: {self.name} (Attempt {attempt+1}/{max_retries})")
                print(f"{'='*60}")
                print(f"[RAW RESPONSE]\n{response}\n")
                
                # 使用相同的解析方法
                plan, thought, campaign_speech = self._parse_allocation_response(response)
                
                print(f"[PARSED] Thought length: {len(thought) if thought else 0}")
                print(f"[PARSED] Plan: {plan}")
                print(f"[PARSED] Campaign length: {len(campaign_speech) if campaign_speech else 0}")
                
                # 成功解析
                if plan or thought or campaign_speech:
                    if not plan:
                        plan = {'description': campaign_speech if campaign_speech else thought if thought else f'{self.name} will adapt the task plan.'}
                    if not thought:
                        thought = "Analyzing execution failures and proposing a revised collaboration strategy."
                    if not campaign_speech:
                        caps = ', '.join(self.capabilities)
                        campaign_speech = f"Based on our execution experience, I propose a revised plan. Vote for me to lead with {caps} capabilities!"
                    
                    # 存储新计划
                    self.memory.store_task_plan(plan)
                    print(f"[SUCCESS] Task reallocation completed for {self.name}")
                    return plan, thought, campaign_speech
                
                print(f"[RETRY] Empty response, retrying...")
                
            except Exception as e:
                print(f"[ERROR] Reallocation failed for {self.name} (attempt {attempt+1}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(1.0)
                    continue
                else:
                    break
        
        # 失败后返回默认重规划结果
        print(f"[FAILED] Reallocation failed for {self.name}, using defaults")
        caps = ', '.join(self.capabilities)
        
        # 构建默认重规划计划
        remaining = [obj for obj in failed_objects if obj not in completed_objects]
        remaining_str = ", ".join(remaining) if remaining else "remaining subtasks"
        
        default_plan = {
            'description': f"Revised Plan: Based on execution experience, {self.name} will handle {remaining_str} with adjusted strategy. Other robots support based on their capabilities."
        }
        default_thought = f"Due to execution challenges, we need to reallocate tasks. I will focus on {remaining_str} with improved approach."
        default_campaign = f"Vote for me to lead the revised plan. With {caps}, I'll ensure we overcome previous challenges."
        
        return default_plan, default_thought, default_campaign
    
    def _build_reallocation_prompt(self, task: str, teammates: Dict[str, str],
                                   completed_objects: List[str], failed_objects: List[str],
                                   execution_history: str) -> str:
        """构建动态重规划提示词"""
        teammates_info = "\n".join([f"- {name}: {desc}" for name, desc in teammates.items()])
        all_robots = [self.name] + list(teammates.keys())
        teammates_str = ", ".join(all_robots)
        
        completed_str = ", ".join(completed_objects) if completed_objects else "None yet"
        failed_str = ", ".join(failed_objects) if failed_objects else "None identified"
        
        return f"""==== System Prompt ====
# Contexts:
1) You are an intelligent robot that can think and make decisions like a human.
2) You need to cooperate with other robots of various configurations to complete complex and long-term tasks.
3) The team has encountered difficulties executing the original plan and needs DYNAMIC REPLANNING.

Phase: Now second step of collaboration - TASK REALLOCATION due to execution challenges

Tasks:
1) Analyze execution failures and propose a REVISED division of labor plan.
2) Propose a campaign speech to run for leader of the new plan.

CoT: Let's think step by step! Analyze what went wrong and how to fix it.

==== User Prompt ====
# Identity and Information:
1) You are an intelligent robot named {self.name}.
2) Below are the self-introductions from yourself and your collaborators:
{teammates_info}

# Task Information:
Overall task: {task}
Team members: {teammates_str}

# Execution History and Current Status:
## Completed Objects:
{completed_str}

## Objects with Repeated Failures:
{failed_str}

## Execution Summary:
{execution_history}

# Replanning Requirements:
1) Identify why previous attempts failed (object unreachable? wrong robot assigned? coordination issue?)
2) Propose alternative strategies for failed objects (different robot? different approach? sequential vs parallel?)
3) Adjust task allocation to maximize success probability
4) Consider robot-specific strengths for challenging subtasks

# Principles for Revised Plan:
1) Learn from failures: don't repeat the same assignments that failed
2) Redistribute failed tasks to robots with better-suited capabilities
3) Consider sequential execution for difficult objects instead of parallel
4) Add coordination points where robots should communicate/wait
5) Include contingency plans for potential new failure modes
6) Prioritize completing partially-finished tasks before starting new ones

# Output Response Format:
1) Thoughts: analyze the execution failures, identify root causes, and propose strategic adjustments;
2) Contents: Include two parts:
   - Collaboration Plan: REVISED detailed task allocation considering execution experience
   - Campaign Speech: 2-3 sentences arguing why you should lead the new plan"""
    
    # ========== Communication ==========
    def receive_message(self, from_robot: str, content: str):
        """接收来自其他机器人的消息"""
        self.memory.store_received_message(from_robot, content)
    
    def communicate(self, content: str, target: str = 'all') -> Tuple[Dict, str]:
        """
        主动通信
        Returns: (action, thought)
        """
        action = {
            'type': 'communicate',
            'content': content,
            'target': target
        }
        
        thought = f"I need to inform {target} about: {content}"
        
        return action, thought


class DynaHMRC_Coordinator:
    """
    DynaHMRC协调器 - 管理多机器人协作流程
    注意：这是协调流程，不是中央控制器
    每个机器人仍然是独立的LLM Agent
    """
    
    def __init__(
        self,
        robots: List[RobotAgent],
        reflection_interval: int = 10,  # Δt
        max_steps: int = 100,  # H
        use_simulator: bool = True
    ):
        self.robots = {r.name: r for r in robots}
        self.reflection_interval = reflection_interval
        self.max_steps = max_steps
        self.use_simulator = use_simulator
        
        # 全局状态
        self.current_step = 0
        self.leader_name = None
        self.task = ""
        self.scene_graph = {}
        
        # 场景模拟器
        self.simulator: Optional[SceneSimulator] = None
        if use_simulator:
            self.simulator = SceneSimulator(room_size=(10.0, 10.0))
            # 为每个机器人添加初始位置
            for robot in robots:
                max_range = 1.0 if 'Mobile' in robot.robot_type else 0.8
                max_speed = 0.5 if 'Mobile' in robot.robot_type else 0.0
                self.simulator.add_robot(
                    robot.name,
                    robot.robot_type,
                    max_range=max_range,
                    max_speed=max_speed
                )
        
        # 设置消息回调
        for robot in robots:
            robot.set_message_callback(self._relay_message)
        
        # 消息队列（用于UI显示）
        self.message_queue = []
        
    def _relay_message(self, from_robot: str, target: str, content: str):
        """转发消息给目标机器人"""
        self.message_queue.append({
            'from': from_robot,
            'target': target,
            'content': content,
            'step': self.current_step
        })
        
        if target == 'all':
            # 广播给所有其他机器人
            for name, robot in self.robots.items():
                if name != from_robot:
                    robot.receive_message(from_robot, content)
        else:
            # 单播
            if target in self.robots:
                self.robots[target].receive_message(from_robot, content)
    
    def run_collaboration(self, task: str, callback=None):
        """
        运行完整的协作流程
        callback: 用于流式输出到UI的回调函数
        """
        self.task = task
        
        # Stage 1: Self-Description
        if callback:
            callback('phase', {'phase': 'self-description', 'message': '机器人正在自我介绍...'})
        
        descriptions = {}
        for name, robot in self.robots.items():
            thought, description = robot.self_describe(task)
            descriptions[name] = description
            
            if callback:
                callback('robot_message', {
                    'robot_id': name,
                    'thought': thought,
                    'description': description,
                    'phase': 'self-description'
                })
        
        # Stage 2: Task Allocation + Leadership Bidding
        if callback:
            callback('phase', {'phase': 'task-allocation', 'message': '任务分配和领导者竞选...'})
        
        proposals = {}
        for name, robot in self.robots.items():
            # 其他机器人的描述（不包括自己）
            teammates = {n: d for n, d in descriptions.items() if n != name}
            plan, thought, campaign = robot.propose_allocation(task, teammates)
            proposals[name] = (plan, thought, campaign)
            
            if callback:
                callback('robot_message', {
                    'robot_id': name,
                    'thought': thought,
                    'plan': plan.get('description', ''),
                    'campaign': campaign,
                    'phase': 'task-allocation'
                })
        
        # Stage 3: Leader Election
        if callback:
            callback('phase', {'phase': 'leader-election', 'message': '正在为领导者投票...'})
        
        votes = {}
        for name, robot in self.robots.items():
            vote_for, thought, reasoning = robot.vote_leader(proposals)
            votes[name] = vote_for
            
            if callback:
                callback('robot_message', {
                    'robot_id': name,
                    'thought': thought,
                    'vote_for': vote_for,
                    'reasoning': reasoning,
                    'phase': 'leader-election'
                })
        
        # 统计投票结果
        vote_counts = {}
        for vote in votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1
        
        self.leader_name = max(vote_counts, key=vote_counts.get)
        
        # 更新所有机器人的领导者状态
        for name, robot in self.robots.items():
            robot.leader_name = self.leader_name
            robot.is_leader = (name == self.leader_name)
        
        if callback:
            callback('system', {'message': f'{self.leader_name} is elected as leader with {vote_counts[self.leader_name]} votes'})
        
        # Stage 4: Closed-Loop Execution
        leader_plan = proposals[self.leader_name][0] if self.leader_name in proposals else {}
        
        for step in range(self.max_steps):
            self.current_step = step
            
            # 检查是否需要Reflection
            if step > 0 and step % self.reflection_interval == 0:
                if callback:
                    callback('phase', {'phase': 'reflection', 'message': f'第 {step} 步进行反思...'})
                
                # 所有机器人进行反思
                reflections = {}
                for name, robot in self.robots.items():
                    thought, summary, future = robot.reflect(task)
                    reflections[name] = (thought, summary, future)
                    
                    if callback:
                        callback('robot_message', {
                            'robot_id': name,
                            'thought': thought,
                            'summary': summary,
                            'future_plan': future,
                            'phase': 'reflection'
                        })
                
                # Leader整合反思并更新计划
                if self.leader_name:
                    leader = self.robots[self.leader_name]
                    thought, updated_plan = leader.update_leader_plan(reflections)
                    leader_plan = {'description': updated_plan}
                    
                    if callback:
                        callback('robot_message', {
                            'robot_id': self.leader_name,
                            'thought': thought,
                            'updated_plan': updated_plan,
                            'phase': 'reflection',
                            'is_leader': True
                        })
                
                # ========== 动态重规划检查 ==========
                need_replanning = False
                replanning_reason = ""
                
                # 检查每个机器人是否需要重规划
                for name, robot in self.robots.items():
                    should_trigger, reason = robot.should_trigger_replanning()
                    if should_trigger:
                        need_replanning = True
                        replanning_reason = reason
                        print(f"[REPLANNING TRIGGERED] Robot {name} suggests replanning: {reason}")
                        break
                
                # 如果触发了重规划，重新进行任务分配和领导选举
                if need_replanning:
                    if callback:
                        callback('phase', {'phase': 'replanning', 'message': f'检测到执行困难({replanning_reason})，启动动态重规划...'})
                        callback('system', {'message': f'执行效率低下，正在进行任务重新分配...'})
                    
                    print(f"\n{'='*60}")
                    print(f"[DYNAMIC REPLANNING] Triggered by: {replanning_reason}")
                    print(f"{'='*60}")
                    
                    # 收集执行历史信息
                    completed_objects = []
                    failed_objects = []
                    execution_history = ""
                    
                    for name, robot in self.robots.items():
                        completed_objects.extend(robot.memory.task_progress['completed_objects'])
                        failed_objects.extend(robot.memory.task_progress['failed_attempts'].keys())
                        
                        # 构建执行历史摘要
                        stats = robot.memory.execution_stats
                        history = f"{name}: {stats['success_count']}/{stats['total_actions']} successful, "
                        history += f"{stats['failure_count']} failures, "
                        history += f"{stats['consecutive_failures']} consecutive failures"
                        execution_history += history + "\n"
                    
                    # 去重
                    completed_objects = list(set(completed_objects))
                    failed_objects = list(set(failed_objects))
                    
                    # Stage 2b: 重新任务分配
                    if callback:
                        callback('phase', {'phase': 'task-reallocation', 'message': '基于执行经验重新分配任务...'})
                    
                    # 重新获取所有机器人的描述
                    descriptions = {}
                    for name, robot in self.robots.items():
                        descriptions[name] = robot.memory.self_description
                    
                    new_proposals = {}
                    for name, robot in self.robots.items():
                        teammates = {n: d for n, d in descriptions.items() if n != name}
                        plan, thought, campaign = robot.reallocate_tasks(
                            task, teammates, completed_objects, failed_objects, execution_history
                        )
                        new_proposals[name] = (plan, thought, campaign)
                        
                        if callback:
                            callback('robot_message', {
                                'robot_id': name,
                                'thought': thought,
                                'plan': plan.get('description', ''),
                                'campaign': campaign,
                                'phase': 'task-reallocation'
                            })
                    
                    # Stage 3b: 重新领导选举
                    if callback:
                        callback('phase', {'phase': 'leader-re-election', 'message': '重新选举领导者...'})
                    
                    new_votes = {}
                    for name, robot in self.robots.items():
                        vote_for, thought, reasoning = robot.vote_leader(new_proposals)
                        new_votes[name] = vote_for
                        
                        if callback:
                            callback('robot_message', {
                                'robot_id': name,
                                'thought': thought,
                                'vote_for': vote_for,
                                'reasoning': reasoning,
                                'phase': 'leader-re-election'
                            })
                    
                    # 统计新投票结果
                    new_vote_counts = {}
                    for vote in new_votes.values():
                        new_vote_counts[vote] = new_vote_counts.get(vote, 0) + 1
                    
                    self.leader_name = max(new_vote_counts, key=new_vote_counts.get)
                    
                    # 更新领导者状态
                    for name, robot in self.robots.items():
                        robot.leader_name = self.leader_name
                        robot.is_leader = (name == self.leader_name)
                    
                    if callback:
                        callback('system', {'message': f'{self.leader_name} 被重新选举为领导者（{new_vote_counts[self.leader_name]} 票）'})
                    
                    # 使用新计划
                    leader_plan = new_proposals[self.leader_name][0] if self.leader_name in new_proposals else leader_plan
                    proposals = new_proposals  # 更新全局proposals
                    
                    # 重置失败计数（给新计划一个机会）
                    for name, robot in self.robots.items():
                        robot.memory.execution_stats['consecutive_failures'] = 0
                    
                    print(f"[REPLANNING COMPLETE] New leader: {self.leader_name}")
                    print(f"{'='*60}\n")
            
            if callback:
                callback('phase', {'phase': 'execution', 'message': f'执行第 {step} 步...'})
            
            # 更新场景图（从模拟器获取真实位置）
            if self.simulator:
                self.scene_graph = self.simulator.get_scene_graph()
            
            # 每个机器人执行一步
            for name, robot in self.robots.items():
                # 获取机器人当前真实位置
                robot_pose = [0, 0, 0]
                if self.simulator:
                    robot_pose = self.simulator.get_robot_pose(name) or [0, 0, 0]
                    # 更新机器人观察模块中的位置
                    robot.observation.update_robot_info(robot_pose)
                
                # 规划动作
                action, thought = robot.plan_next_action(
                    task, 
                    leader_plan, 
                    self.scene_graph,
                    robot_pose
                )
                
                # 使用模拟器执行动作
                if self.simulator:
                    feedback = self._execute_action_with_simulator(name, action)
                else:
                    feedback = robot.execute_action(action)
                
                # 处理通信动作 - 将消息传递给目标机器人
                if action.get('type') == 'communicate':
                    content = action.get('content', '')
                    target = action.get('target', 'all')
                    
                    if target == 'all':
                        # 广播给所有其他机器人
                        for other_name, other_robot in self.robots.items():
                            if other_name != name:
                                other_robot.receive_message(name, content)
                        feedback['message'] = f"Broadcast message sent: '{content}'"
                    elif target in self.robots:
                        # 单播给特定机器人
                        self.robots[target].receive_message(name, content)
                        feedback['message'] = f"Message sent to {target}: '{content}'"
                    else:
                        feedback['message'] = f"Message could not be delivered - unknown target: {target}"
                
                # 存储结果
                robot.store_execution_result(action, feedback)
                
                # 执行后更新场景图
                if self.simulator:
                    self.scene_graph = self.simulator.get_scene_graph()
                
                if callback:
                    callback('robot_message', {
                        'robot_id': name,
                        'thought': thought,
                        'action': action,
                        'feedback': feedback,
                        'phase': 'execution',
                        'is_leader': robot.is_leader
                    })
                
                # 检查是否完成任务
                if step >= self.max_steps:
                    break
        
        # 最终Reflection
        if callback:
            callback('phase', {'phase': 'reflection', 'message': '最终反思...'})
        
        reflections = {}
        for name, robot in self.robots.items():
            thought, summary, future = robot.reflect(task)
            reflections[name] = (thought, summary, future)
            
            if callback:
                callback('robot_message', {
                    'robot_id': name,
                    'thought': thought,
                    'summary': summary,
                    'future_plan': future,
                    'phase': 'reflection',
                    'is_reflection': True
                })
        
        if callback:
            callback('complete', {'message': '任务成功完成'})
    
    def _execute_action_with_simulator(self, robot_name: str, action: Dict) -> Dict:
        """
        使用场景模拟器执行动作
        
        Returns:
            动作执行反馈
        """
        if not self.simulator:
            return {'success': False, 'message': '模拟器不可用'}
        
        action_type = action.get('type', 'wait')
        
        if action_type == 'navigate':
            target = action.get('target', '')
            # 获取目标位置
            target_pos = None
            if target in self.simulator.objects:
                target_pos = self.simulator.objects[target].position
            elif target in self.simulator.furniture:
                target_pos = self.simulator.furniture[target].position
            else:
                # 默认位置
                target_pos = [0, 0, 0]
            
            result = self.simulator.navigate(robot_name, target_pos)
            return result
        
        elif action_type == 'pick':
            target_object = action.get('target_object', '')
            result = self.simulator.pick(robot_name, target_object)
            return result
        
        elif action_type == 'place':
            location = action.get('location', '')
            result = self.simulator.place(robot_name, location)
            return result
        
        elif action_type == 'explore':
            # 随机探索到一个新位置
            target_pos = self.simulator._random_position()
            result = self.simulator.navigate(robot_name, target_pos)
            result['message'] = f'Explore: {result["message"]}'
            return result
        
        elif action_type == 'communicate':
            return {
                'success': True,
                'message': f'通信消息已发送给 {action.get("to", "all")}',
                'type': 'communicate_success'
            }
        
        elif action_type == 'wait':
            return {
                'success': True,
                'message': '等待下一步指令',
                'type': 'wait'
            }
        
        else:
            return {
                'success': False,
                'message': f'未知动作类型: {action_type}',
                'type': 'action_failed'
            }
    
    def initialize_scene(self, objects: List[str] = None):
        """
        初始化场景
        
        Args:
            objects: 要添加的物体列表，如果为None则使用默认物体
        """
        if not self.simulator:
            print("[DynaHMRC] Simulator not enabled")
            return
        
        # 初始化默认场景
        self.simulator.initialize_default_scene(objects)
        
        # 更新场景图
        self.scene_graph = self.simulator.get_scene_graph()
        
        print(f"[DynaHMRC] Scene initialized with {len(self.simulator.objects)} objects")
        print(f"[DynaHMRC] Robots: {list(self.simulator.robots.keys())}")
        print(f"[DynaHMRC] Furniture: {list(self.simulator.furniture.keys())}")
        
        # 打印场景状态
        self.simulator.print_scene()
