# dynahmrc/core/task_allocation.py
"""
任务分配模块
负责任务的分解、分配和调度
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
import heapq


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"
    ASSIGNED = "assigned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """任务数据类"""
    task_id: str
    description: str
    assigned_robot: Optional[str] = None
    required_capabilities: List[str] = field(default_factory=list)
    estimated_duration: float = 60.0  # 秒
    priority: int = 1  # 数字越小优先级越高
    dependencies: List[str] = field(default_factory=list)  # 依赖的其他任务ID
    status: str = "pending"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "assigned_robot": self.assigned_robot,
            "required_capabilities": self.required_capabilities,
            "estimated_duration": self.estimated_duration,
            "priority": self.priority,
            "dependencies": self.dependencies,
            "status": self.status
        }


class TaskAllocator:
    """任务分配器"""
    
    def __init__(self, robots: List[Any]):
        self.robots = robots
        self.tasks: Dict[str, Task] = {}
        self.assignment_history: List[Dict] = []
        self.allocation_strategy = "capability_match"  # 分配策略
        
    def update_robots(self, robots: List[Any]):
        """更新机器人列表"""
        self.robots = robots
    
    def add_task(self, task: Task) -> bool:
        """添加任务"""
        self.tasks[task.task_id] = task
        return True
    
    def remove_task(self, task_id: str) -> bool:
        """移除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False
    
    def allocate_task(self, task: Task, robot_id: Optional[str] = None) -> Optional[str]:
        """
        分配任务给机器人
        
        Args:
            task: 任务对象
            robot_id: 指定机器人ID，None则自动选择
        
        Returns:
            分配的机器人ID，失败返回None
        """
        if robot_id:
            # 检查指定机器人是否可用
            robot = self._get_robot_by_id(robot_id)
            if robot and self._can_execute(robot, task):
                task.assigned_robot = robot_id
                task.status = "assigned"
                self._record_assignment(task, robot_id)
                return robot_id
            return None
        
        # 自动选择最佳机器人
        best_robot = self._select_best_robot(task)
        if best_robot:
            task.assigned_robot = best_robot
            task.status = "assigned"
            self._record_assignment(task, best_robot)
            return best_robot
        
        return None
    
    def allocate_tasks_batch(self, tasks: List[Task]) -> Dict[str, Optional[str]]:
        """
        批量分配任务
        
        Returns:
            任务ID到机器人ID的映射
        """
        allocations = {}
        
        # 按优先级排序
        sorted_tasks = sorted(tasks, key=lambda t: t.priority)
        
        for task in sorted_tasks:
            robot_id = self.allocate_task(task)
            allocations[task.task_id] = robot_id
        
        return allocations
    
    def reallocate_task(self, task_id: str, new_robot_id: Optional[str] = None) -> bool:
        """重新分配任务"""
        if task_id not in self.tasks:
            return False
        
        task = self.tasks[task_id]
        old_robot = task.assigned_robot
        
        # 重置任务状态
        task.status = "pending"
        task.assigned_robot = None
        
        # 重新分配
        new_robot = self.allocate_task(task, new_robot_id)
        
        if new_robot:
            print(f"[TaskAllocator] 任务 {task_id} 重新分配: {old_robot} -> {new_robot}")
            return True
        
        # 恢复原分配
        task.assigned_robot = old_robot
        task.status = "assigned"
        return False
    
    def _get_robot_by_id(self, robot_id: str) -> Optional[Any]:
        """根据ID获取机器人"""
        for robot in self.robots:
            if getattr(robot, 'robot_id', None) == robot_id:
                return robot
        return None
    
    def _can_execute(self, robot: Any, task: Task) -> bool:
        """检查机器人是否能执行任务"""
        robot_caps = getattr(robot, 'capabilities', [])
        return all(cap in robot_caps for cap in task.required_capabilities)
    
    def _select_best_robot(self, task: Task) -> Optional[str]:
        """
        选择最佳机器人
        
        策略：
        1. 能力匹配
        2. 当前负载最低
        3. 预估执行时间最短
        """
        candidates = []
        
        for robot in self.robots:
            robot_id = getattr(robot, 'robot_id', None)
            robot_state = getattr(robot, 'state', None)
            
            # 检查能力匹配
            if not self._can_execute(robot, task):
                continue
            
            # 检查是否忙碌
            if robot_state and getattr(robot_state, 'is_busy', False):
                continue
            
            # 计算评分（负载越低越好）
            score = self._calculate_robot_score(robot, task)
            candidates.append((score, robot_id))
        
        if not candidates:
            return None
        
        # 选择评分最高的（heapq是最小堆，所以用负分）
        best = max(candidates, key=lambda x: x[0])
        return best[1]
    
    def _calculate_robot_score(self, robot: Any, task: Task) -> float:
        """计算机器人评分"""
        score = 100.0
        
        # 根据能力匹配度加分
        robot_caps = set(getattr(robot, 'capabilities', []))
        required_caps = set(task.required_capabilities)
        match_ratio = len(robot_caps & required_caps) / len(required_caps)
        score += match_ratio * 50
        
        # 根据当前负载减分
        robot_state = getattr(robot, 'state', None)
        if robot_state:
            if getattr(robot_state, 'is_busy', False):
                score -= 50
            # 电池电量影响
            battery = getattr(robot_state, 'battery_level', 100)
            score += battery * 0.1
        
        return score
    
    def _record_assignment(self, task: Task, robot_id: str):
        """记录分配历史"""
        self.assignment_history.append({
            "timestamp": time.time(),
            "task_id": task.task_id,
            "robot_id": robot_id,
            "strategy": self.allocation_strategy
        })
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """获取任务状态"""
        task = self.tasks.get(task_id)
        return task.status if task else None
    
    def get_robot_workload(self, robot_id: str) -> int:
        """获取机器人当前任务数"""
        count = 0
        for task in self.tasks.values():
            if task.assigned_robot == robot_id and task.status in ["assigned", "executing"]:
                count += 1
        return count
    
    def get_allocation_summary(self) -> Dict[str, Any]:
        """获取分配摘要"""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == "completed")
        failed = sum(1 for t in self.tasks.values() if t.status == "failed")
        executing = sum(1 for t in self.tasks.values() if t.status == "executing")
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "executing": executing,
            "pending": total - completed - failed - executing,
            "assignments": {
                rid: self.get_robot_workload(rid) 
                for rid in [getattr(r, 'robot_id', None) for r in self.robots]
            }
        }
    
    def optimize_allocations(self) -> List[Tuple[str, str, str]]:
        """
        优化现有分配
        
        Returns:
            优化建议列表 [(task_id, from_robot, to_robot), ...]
        """
        suggestions = []
        
        # 检查负载不均衡
        workloads = {
            getattr(r, 'robot_id', None): self.get_robot_workload(getattr(r, 'robot_id', None))
            for r in self.robots
        }
        
        avg_load = sum(workloads.values()) / len(workloads) if workloads else 0
        
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            
            current_robot = task.assigned_robot
            current_load = workloads.get(current_robot, 0)
            
            # 如果当前机器人负载过高，尝试找负载低的
            if current_load > avg_load + 1:
                better_robot = self._select_best_robot(task)
                if better_robot and workloads.get(better_robot, 0) < current_load - 1:
                    suggestions.append((task.task_id, current_robot, better_robot))
        
        return suggestions