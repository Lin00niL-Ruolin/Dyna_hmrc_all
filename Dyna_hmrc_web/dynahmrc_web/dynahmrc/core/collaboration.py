# dynahmrc/core/collaboration.py
"""
协作管理模块
管理多机器人协作的阶段和同步
"""

from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import time


class CollaborationPhase(Enum):
    """协作阶段枚举"""
    IDLE = "idle"
    PLANNING = "planning"
    NEGOTIATING = "negotiating"
    SYNCHRONIZING = "synchronizing"
    EXECUTING = "executing"
    MONITORING = "monitoring"
    RECOVERING = "recovering"
    COMPLETED = "completed"


@dataclass
class CollaborationPoint:
    """协作同步点"""
    point_id: str
    description: str
    required_robots: List[str]
    synchronized_robots: List[str] = field(default_factory=list)
    is_reached: bool = False
    timestamp: Optional[float] = None
    
    def mark_reached(self, robot_id: str) -> bool:
        """标记机器人到达同步点"""
        if robot_id not in self.synchronized_robots:
            self.synchronized_robots.append(robot_id)
        
        # 检查是否所有机器人都已到达
        if set(self.synchronized_robots) >= set(self.required_robots):
            self.is_reached = True
            self.timestamp = time.time()
            return True
        return False
    
    def reset(self):
        """重置同步点"""
        self.synchronized_robots.clear()
        self.is_reached = False
        self.timestamp = None


class CollaborationManager:
    """协作管理器"""
    
    def __init__(self):
        self.current_phase = CollaborationPhase.IDLE
        self.collaboration_points: Dict[str, CollaborationPoint] = {}
        self.phase_handlers: Dict[CollaborationPhase, Callable] = {}
        self.execution_history: List[Dict] = []
        self.active_sync_points: set = set()
        
    def register_phase_handler(self, phase: CollaborationPhase, handler: Callable):
        """注册阶段处理器"""
        self.phase_handlers[phase] = handler
    
    def transition_to(self, phase: CollaborationPhase, context: Optional[Dict] = None):
        """转换到指定阶段"""
        old_phase = self.current_phase
        self.current_phase = phase
        
        # 记录历史
        self.execution_history.append({
            "timestamp": time.time(),
            "from": old_phase.value,
            "to": phase.value,
            "context": context or {}
        })
        
        # 调用处理器
        if phase in self.phase_handlers:
            self.phase_handlers[phase](context)
        
        print(f"[Collaboration] 阶段转换: {old_phase.value} -> {phase.value}")
    
    def add_collaboration_point(self, point_id: str, description: str, required_robots: List[str]):
        """添加协作同步点"""
        point = CollaborationPoint(
            point_id=point_id,
            description=description,
            required_robots=required_robots
        )
        self.collaboration_points[point_id] = point
        self.active_sync_points.add(point_id)
        print(f"[Collaboration] 添加同步点: {point_id} ({description})")
    
    def reach_collaboration_point(self, point_id: str, robot_id: str) -> bool:
        """机器人到达协作点"""
        if point_id not in self.collaboration_points:
            print(f"[Collaboration] 警告: 未知的同步点 {point_id}")
            return False
        
        point = self.collaboration_points[point_id]
        all_reached = point.mark_reached(robot_id)
        
        progress = f"{len(point.synchronized_robots)}/{len(point.required_robots)}"
        print(f"[Collaboration] 机器人 {robot_id} 到达同步点 {point_id} ({progress})")
        
        if all_reached:
            print(f"[Collaboration] 同步点 {point_id} 达成！所有机器人已同步")
            self.active_sync_points.discard(point_id)
        
        return all_reached
    
    def wait_for_collaboration_point(self, point_id: str, timeout: float = 30.0) -> bool:
        """等待协作点达成（阻塞）"""
        if point_id not in self.collaboration_points:
            return False
        
        start_time = time.time()
        point = self.collaboration_points[point_id]
        
        while not point.is_reached:
            if time.time() - start_time > timeout:
                print(f"[Collaboration] 等待同步点 {point_id} 超时")
                return False
            time.sleep(0.1)
        
        return True
    
    def reset_collaboration_point(self, point_id: str):
        """重置协作点"""
        if point_id in self.collaboration_points:
            self.collaboration_points[point_id].reset()
            self.active_sync_points.add(point_id)
    
    def get_current_phase(self) -> CollaborationPhase:
        """获取当前阶段"""
        return self.current_phase
    
    def is_phase(self, phase: CollaborationPhase) -> bool:
        """检查是否处于指定阶段"""
        return self.current_phase == phase
    
    def get_collaboration_status(self) -> Dict[str, Any]:
        """获取协作状态"""
        return {
            "current_phase": self.current_phase.value,
            "active_sync_points": list(self.active_sync_points),
            "sync_points_status": {
                pid: {
                    "reached": p.is_reached,
                    "progress": f"{len(p.synchronized_robots)}/{len(p.required_robots)}"
                }
                for pid, p in self.collaboration_points.items()
            }
        }
    
    def clear(self):
        """清除所有状态"""
        self.current_phase = CollaborationPhase.IDLE
        self.collaboration_points.clear()
        self.active_sync_points.clear()
        self.execution_history.clear()