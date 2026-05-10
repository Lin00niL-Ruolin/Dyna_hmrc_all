# dynahmrc/coordinator.py
"""
DynaHMRC - 异构多机器人协作协调器
基于大语言模型的动态任务规划与执行
"""

import json
import time
import math
from typing import List, Dict, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque

from .core.collaboration import CollaborationPhase, CollaborationManager
from .core.task_allocation import TaskAllocator, Task
from .utils.llm_api import create_llm_client, BaseLLMClient, KimiLLMClient, MockLLMClient


class ExecutionStatus(Enum):
    """执行状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"


@dataclass
class RobotState:
    """机器人状态数据类"""
    robot_id: str
    robot_type: str
    position: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    battery_level: float = 100.0
    is_busy: bool = False
    current_task: Optional[str] = None
    error_status: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "robot_id": self.robot_id,
            "robot_type": self.robot_type,
            "position": self.position,
            "orientation": self.orientation,
            "battery_level": self.battery_level,
            "is_busy": self.is_busy,
            "current_task": self.current_task,
            "error_status": self.error_status,
            "capabilities": self.capabilities
        }


@dataclass
class ExecutionResult:
    """执行结果数据类"""
    success: bool
    message: str
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    execution_time: float = 0.0
    replan_count: int = 0


class BaseRobot:
    """机器人基类"""
    
    def __init__(self, robot_id: str, robot_type: str, capabilities: List[str]):
        self.robot_id = robot_id
        self.robot_type = robot_type
        self.capabilities = capabilities
        self.state = RobotState(
            robot_id=robot_id,
            robot_type=robot_type,
            capabilities=capabilities
        )
    
    def execute_task(self, task_plan: Dict[str, Any]) -> bool:
        """执行任务（子类需要重写）"""
        raise NotImplementedError
    
    def get_state(self) -> RobotState:
        """获取当前状态"""
        return self.state
    
    def update_state(self, **kwargs):
        """更新状态"""
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
    
    def emergency_stop(self) -> bool:
        """紧急停止"""
        self.state.is_busy = False
        self.state.current_task = None
        return True
    
    def recover(self) -> bool:
        """从错误中恢复"""
        self.state.error_status = None
        return True


class DynaHMRC_Coordinator:
    """
    DynaHMRC 主协调器
    负责多机器人协作的任务规划、分配、执行监控和异常处理
    """
    
    def __init__(
        self,
        robots: List[BaseRobot],
        llm_client: Optional[BaseLLMClient] = None,
        enable_replanning: bool = True,
        max_replan_attempts: int = 3,
        execution_interval: float = 0.1
    ):
        """
        初始化协调器
        
        Args:
            robots: 机器人列表
            llm_client: LLM 客户端（默认使用 Mock）
            enable_replanning: 是否启用动态重规划
            max_replan_attempts: 最大重规划次数
            execution_interval: 执行循环间隔（秒）
        """
        self.robots: Dict[str, BaseRobot] = {r.robot_id: r for r in robots}
        self.llm_client = llm_client or MockLLMClient()
        self.enable_replanning = enable_replanning
        self.max_replan_attempts = max_replan_attempts
        self.execution_interval = execution_interval
        
        # 核心组件
        self.collab_manager = CollaborationManager()
        self.task_allocator = TaskAllocator(list(self.robots.values()))
        
        # 执行状态
        self.status = ExecutionStatus.PENDING
        self.current_plan: Optional[Dict[str, Any]] = None
        self.task_queue: deque = deque()
        self.execution_history: List[Dict] = []
        self.active_tasks: Dict[str, Task] = {}
        self.failed_tasks: List[str] = []
        
        # 场景相关（新增）
        self.scene_loader = None
        self.scene_objects: Dict[str, Any] = {}
        self.task_config: Dict[str, Any] = {}
        
        # 统计信息
        self.start_time: Optional[float] = None
        self.replan_count = 0
        

    
    # ==================== 机器人管理 ====================
    
    def add_robot(self, robot: BaseRobot):
        """添加机器人"""
        self.robots[robot.robot_id] = robot
        self.task_allocator.update_robots(list(self.robots.values()))

    
    def remove_robot(self, robot_id: str):
        """移除机器人"""
        if robot_id in self.robots:
            del self.robots[robot_id]
            self.task_allocator.update_robots(list(self.robots.values()))

    
    def get_robot_state(self, robot_id: str) -> Optional[RobotState]:
        """获取指定机器人状态"""
        robot = self.robots.get(robot_id)
        return robot.get_state() if robot else None
    
    def get_all_robot_states(self) -> Dict[str, RobotState]:
        """获取所有机器人状态"""
        return {rid: r.get_state() for rid, r in self.robots.items()}
    
    def broadcast_command(self, command: str, params: Optional[Dict] = None):
        """向所有机器人广播命令"""

        for robot in self.robots.values():
            # 这里可以实现具体的命令下发逻辑
            pass
    
    def emergency_stop_all(self):
        """紧急停止所有机器人"""

        for robot in self.robots.values():
            robot.emergency_stop()
        self.status = ExecutionStatus.PAUSED
    
    # ==================== 场景加载（新增） ====================
    
    def load_scene_from_json(self, json_path: str) -> Dict[str, Any]:
        """
        从 JSON 文件加载场景
        
        Args:
            json_path: 场景配置文件路径
        
        Returns:
            场景数据字典
        """
        from .scene_loader import SceneLoader
        
        self.scene_loader = SceneLoader()
        scene_data = self.scene_loader.load_scene_from_json(json_path)
        
        self.scene_objects = scene_data.get('objects', {})
        self.task_config = scene_data.get('task_config', {})
        
        # 根据场景配置初始化机器人
        robot_configs = scene_data.get('robot_configs', [])
        self._init_robots_from_scene(robot_configs)
        

        return scene_data
    
    def _init_robots_from_scene(self, robot_configs: List[Dict]):
        """根据场景配置初始化机器人"""
        for config in robot_configs:
            robot = self._create_robot_from_config(config)
            if robot and robot.robot_id not in self.robots:
                self.add_robot(robot)
    
    def _create_robot_from_config(self, config: Dict) -> Optional[BaseRobot]:
        """根据配置创建机器人（需要根据实际情况实现）"""
        # 这里应该根据实际机器人 API 创建具体实例
        # 示例实现：
        try:
            robot_id = config.get('name', 'unknown_robot')
            robot_type = config.get('type', 'generic')
            capabilities = config.get('config', {}).get('capabilities', ['navigation'])
            
            # 创建基础机器人（实际项目中应该导入具体的机器人类）
            robot = BaseRobot(robot_id, robot_type, capabilities)
            
            # 设置初始位姿
            position = config.get('position', [0, 0, 0])
            orientation = config.get('orientation', [0, 0, 0, 1])
            robot.update_state(position=position, orientation=orientation)
            
            return robot
            
        except Exception as e:

            return None
    
    def get_scene_object_info(self) -> Dict[str, Any]:
        """获取场景物体信息（用于 LLM 规划）"""
        if not self.scene_loader:
            return {}
        
        object_info = {}
        for name, obj_data in self.scene_objects.items():
            pos = self.scene_loader.get_object_position(name)
            orn = self.scene_loader.get_object_orientation(name)
            object_info[name] = {
                'position': pos,
                'orientation': orn,
                'type': obj_data.get('type', 'unknown'),
                'config': obj_data.get('config', {})
            }
        return object_info
    
    def get_task_goals(self) -> List[Dict]:
        """获取任务目标配置"""
        return self.task_config.get('task_goals', [])
    
    # ==================== 任务规划（使用 Kimi） ====================
    
    def generate_task_plan(self, high_level_task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        使用 LLM 生成任务规划
        
        Args:
            high_level_task: 高层任务描述
            context: 额外的上下文信息
        
        Returns:
            结构化任务规划
        """
        # 构建场景描述
        scene_info = self._build_scene_description()
        
        # 构建机器人能力描述
        robot_info = self._build_robot_description()
        
        # 构建提示词
        prompt = self._build_planning_prompt(high_level_task, scene_info, robot_info, context)
        
        # 调用 LLM
        try:
            response = self.llm_client.generate(prompt, temperature=1.0, max_tokens=4096)
            plan = self._parse_plan_response(response)
            return plan
            
        except Exception as e:

            return self._create_fallback_plan(high_level_task)
    
    def _build_scene_description(self) -> str:
        """构建场景描述"""
        objects = self.get_scene_object_info()
        if not objects:
            return "场景暂无特定物体。"
        
        desc_parts = ["场景中的物体："]
        for name, info in objects.items():
            pos = info.get('position', [0, 0, 0])
            desc_parts.append(f"- {name}: 位置({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")
        
        return "\n".join(desc_parts)
    
    def _build_robot_description(self) -> str:
        """构建机器人能力描述"""
        desc_parts = ["可用机器人："]
        for rid, robot in self.robots.items():
            state = robot.get_state()
            caps = ", ".join(state.capabilities)
            busy = "忙碌" if state.is_busy else "空闲"
            desc_parts.append(f"- {rid}({state.robot_type}): 能力[{caps}], 状态[{busy}]")
        return "\n".join(desc_parts)
    
    def _build_planning_prompt(
        self,
        task: str,
        scene_info: str,
        robot_info: str,
        context: Optional[Dict]
    ) -> str:
        """Build planning prompt"""
        
        prompt = f"""You are an expert in heterogeneous multi-robot collaborative planning. Please analyze the following task and provide a detailed collaborative planning solution.

## Task Description
{task}

## Current Environment
{scene_info}

## Available Robots
{robot_info}
"""

        if context:
            prompt += f"\n## Additional Context\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"

        prompt += """
## Output Requirements
Please output a planning solution in JSON format, containing the following fields:
- "task_decomposition": Task decomposition list, each subtask includes id, description, required_capabilities, estimated_duration
- "robot_assignment": Robot assignment plan, specifying which robot is assigned to each subtask
- "execution_sequence": Execution sequence, indicating parallel and serial relationships
- "collaboration_points": Collaboration synchronization points, explaining which steps require collaboration
- "contingency_plans": Contingency plans for exceptions

Please ensure the output is valid JSON format without markdown code block markers.
"""
        return prompt
    
    def _parse_plan_response(self, response: str) -> Dict[str, Any]:
        """解析 LLM 返回的规划"""
        try:
            # 尝试直接解析 JSON
            plan = json.loads(response)
            return plan
        except json.JSONDecodeError:
            # 尝试从 markdown 代码块中提取
            try:
                if "```json" in response:
                    json_str = response.split("```json")[1].split("```")[0].strip()
                elif "```" in response:
                    json_str = response.split("```")[1].split("```")[0].strip()
                else:
                    # 尝试找到 JSON 的开始和结束
                    start = response.find("{")
                    end = response.rfind("}") + 1
                    json_str = response[start:end]
                
                plan = json.loads(json_str)
                return plan
            except Exception as e:

                return self._create_fallback_plan("解析失败")
    
    def _create_fallback_plan(self, task: str) -> Dict[str, Any]:
        """Create fallback plan (used when LLM fails)"""
        # Simple round-robin assignment strategy
        subtasks = []
        assignments = {}
        
        robots = list(self.robots.keys())
        if not robots:
            return {"error": "No robots available"}
        
        # Simple task decomposition
        subtasks.append({
            "id": "task_1",
            "description": f"Execute task: {task}",
            "required_capabilities": ["navigation", "manipulation"],
            "estimated_duration": 60
        })
        assignments["task_1"] = robots[0]
        
        return {
            "task_decomposition": subtasks,
            "robot_assignment": assignments,
            "execution_sequence": ["task_1"],
            "collaboration_points": [],
            "contingency_plans": {"default": "Replan"}
        }
    
    # ==================== Task Execution ====================
    
    def execute_collaborative_task(self, high_level_task: str) -> ExecutionResult:
        """
        Execute collaborative task (main entry)
        
        Args:
            high_level_task: High-level task description
        
        Returns:
            Execution result
        """

        
        self.start_time = time.time()
        self.status = ExecutionStatus.RUNNING
        self.replan_count = 0
        
        # 阶段 1: 任务规划
        plan = self.generate_task_plan(high_level_task)
        self.current_plan = plan
        
        if "error" in plan:
            return ExecutionResult(
                success=False,
                message=f"规划失败: {plan['error']}",
                execution_time=time.time() - self.start_time
            )
        
        # 阶段 2: 任务分配
        allocation_success = self._allocate_tasks(plan)
        if not allocation_success:
            return ExecutionResult(
                success=False,
                message="任务分配失败",
                execution_time=time.time() - self.start_time
            )
        
        # 阶段 3: 执行监控
        execution_success = self._run_execution_loop()
        
        # 汇总结果
        total_time = time.time() - self.start_time
        self.status = ExecutionStatus.COMPLETED if execution_success else ExecutionStatus.FAILED
        
        result = ExecutionResult(
            success=execution_success,
            message="任务完成" if execution_success else "任务失败",
            completed_tasks=list(self.active_tasks.keys()),
            failed_tasks=self.failed_tasks,
            execution_time=total_time,
            replan_count=self.replan_count
        )
        
        self._print_execution_summary(result)
        return result
    
    def _allocate_tasks(self, plan: Dict[str, Any]) -> bool:
        """分配任务给机器人"""
        decomposition = plan.get("task_decomposition", [])
        assignment = plan.get("robot_assignment", {})
        
        for task_info in decomposition:
            task_id = task_info.get("id")
            robot_id = assignment.get(task_id)
            
            if not robot_id or robot_id not in self.robots:

                continue
            
            task = Task(
                task_id=task_id,
                description=task_info.get("description", ""),
                assigned_robot=robot_id,
                required_capabilities=task_info.get("required_capabilities", []),
                estimated_duration=task_info.get("estimated_duration", 60)
            )
            
            self.task_queue.append(task)
            self.active_tasks[task_id] = task

        
        return len(self.active_tasks) > 0
    
    def _run_execution_loop(self) -> bool:
        """执行主循环"""
        while self.task_queue and self.status == ExecutionStatus.RUNNING:
            # 获取下一个任务
            current_task = self.task_queue.popleft()
            
            # 检查是否需要重规划
            if self.enable_replanning and self._should_replan():
                if self.replan_count < self.max_replan_attempts:

                    if self._dynamic_replan():
                        self.replan_count += 1
                        continue
                    else:
                        pass

                else:
                    pass

            
            # 执行任务
            success = self._execute_single_task(current_task)
            
            if success:
                current_task.status = "completed"

            else:
                current_task.status = "failed"
                self.failed_tasks.append(current_task.task_id)

                
                # 尝试恢复或调整
                if not self._handle_task_failure(current_task):

                    return False
            
            # 记录执行历史
            self.execution_history.append({
                "timestamp": time.time(),
                "task_id": current_task.task_id,
                "success": success,
                "robot_states": self.get_all_robot_states()
            })
            
            # 执行间隔
            time.sleep(self.execution_interval)
        
        # 检查是否所有任务完成
        pending = [t for t in self.active_tasks.values() if t.status != "completed"]
        return len(pending) == 0 and len(self.failed_tasks) == 0
    
    def _execute_single_task(self, task: Task) -> bool:
        """执行单个任务"""
        robot = self.robots.get(task.assigned_robot)
        if not robot:

            return False
        
        # 构建任务计划（确保是字典格式）
        task_plan = {
            "task_id": task.task_id,
            "description": task.description,
            "steps": self._decompose_task_steps(task)
        }
        
        # 更新机器人状态
        robot.update_state(is_busy=True, current_task=task.task_id)
        
        try:
            # 调用机器人执行
            success = robot.execute_task(task_plan)
            
            # 更新状态
            robot.update_state(is_busy=False, current_task=None)
            return success
            
        except Exception as e:

            robot.update_state(is_busy=False, error_status=str(e))
            return False
    
    def _decompose_task_steps(self, task: Task) -> List[Dict]:
        """将任务分解为执行步骤"""
        # 这里可以根据任务类型进行更智能的分解
        return [
            {"type": "navigate", "params": {}},
            {"type": "manipulate", "params": {"action": "execute", "target": task.description}},
            {"type": "verify", "params": {}}
        ]
    
    def _should_replan(self) -> bool:
        """检查是否需要重规划"""
        # 检查是否有机器人异常
        for robot in self.robots.values():
            state = robot.get_state()
            if state.error_status or state.battery_level < 20:
                return True
        
        # 检查是否有任务失败
        if self.failed_tasks:
            return True
        
        # 检查场景变化（如果有场景加载器）
        # 这里可以添加场景变化检测逻辑
        
        return False
    
    def _dynamic_replan(self) -> bool:
        """动态重规划"""

        
        # 获取当前状态
        current_states = self.get_all_robot_states()
        
        # 构建重规划上下文
        context = {
            "current_states": {rid: s.to_dict() for rid, s in current_states.items()},
            "completed_tasks": [t for t in self.active_tasks if self.active_tasks[t].status == "completed"],
            "failed_tasks": self.failed_tasks,
            "remaining_tasks": [t.task_id for t in self.task_queue]
        }
        
        # 生成新规划
        new_plan = self.generate_task_plan("继续完成剩余任务", context)
        
        if "error" not in new_plan:
            # 更新任务队列
            self.task_queue.clear()
            self._allocate_tasks(new_plan)

            return True
        
        return False
    
    def _handle_task_failure(self, task: Task) -> bool:
        """处理任务失败"""

        
        # 尝试分配给其他机器人
        available_robots = [
            rid for rid, r in self.robots.items()
            if rid != task.assigned_robot and not r.get_state().is_busy
        ]
        
        if available_robots:
            new_robot = available_robots[0]

            task.assigned_robot = new_robot
            task.status = "pending"
            self.task_queue.appendleft(task)
            return True
        
        # 尝试让原机器人恢复
        robot = self.robots.get(task.assigned_robot)
        if robot and robot.recover():

            task.status = "pending"
            self.task_queue.appendleft(task)
            return True
        
        return False
    
    def _print_execution_summary(self, result: ExecutionResult):
        """打印执行摘要"""
        pass
    
    # ==================== 工具方法 ====================
    
    def pause_execution(self):
        """暂停执行"""
        if self.status == ExecutionStatus.RUNNING:
            self.status = ExecutionStatus.PAUSED

    
    def resume_execution(self):
        """恢复执行"""
        if self.status == ExecutionStatus.PAUSED:
            self.status = ExecutionStatus.RUNNING

    
    def get_execution_status(self) -> Dict[str, Any]:
        """获取当前执行状态"""
        return {
            "status": self.status.value,
            "active_tasks": len(self.active_tasks),
            "pending_tasks": len(self.task_queue),
            "failed_tasks": len(self.failed_tasks),
            "replan_count": self.replan_count,
            "elapsed_time": time.time() - self.start_time if self.start_time else 0
        }
    
    def export_execution_log(self, filepath: str):
        """导出执行日志"""
        log_data = {
            "execution_history": self.execution_history,
            "final_plan": self.current_plan,
            "robot_states": {rid: r.get_state().to_dict() for rid, r in self.robots.items()},
            "failed_tasks": self.failed_tasks
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)
        



# 简单的任务数据类（如果 task_allocation.py 中没有定义）
class Task:
    """任务类"""
    def __init__(
        self,
        task_id: str,
        description: str,
        assigned_robot: str,
        required_capabilities: List[str],
        estimated_duration: float = 60
    ):
        self.task_id = task_id
        self.description = description
        self.assigned_robot = assigned_robot
        self.required_capabilities = required_capabilities
        self.estimated_duration = estimated_duration
        self.status = "pending"  # pending, running, completed, failed