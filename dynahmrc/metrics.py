"""
任务评估指标模块 - Task Evaluation Metrics

评估指标:
- SUCC: 任务全做完的比例 (Success Rate)
- PS: 任务做了一半以上的比例 (Partial Success)
- TS: 总共花了多少步 (Total Steps)
- AS: 实际干了多少活 (Active Steps, 不算发呆/等待)
- CC: 互相喊话了多少次 (Communication Count)
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class TaskMetrics:
    """单个任务的评估指标"""
    task_id: str
    task_description: str = ""
    
    # 任务完成度
    total_subtasks: int = 0
    completed_subtasks: int = 0
    partial_threshold: float = 0.5  # 50%以上为部分成功
    
    # 步骤统计
    total_steps: int = 0
    active_steps: int = 0  # 不包括等待/发呆
    wait_steps: int = 0
    
    # 通信统计
    communication_count: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    
    # 时间统计
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # 机器人参与情况
    robot_participation: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    # 动作统计
    action_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    def start(self):
        """开始记录任务"""
        self.start_time = time.time()
    
    def end(self):
        """结束记录任务"""
        self.end_time = time.time()
    
    @property
    def is_completed(self) -> bool:
        """任务是否全部完成"""
        if self.total_subtasks == 0:
            return False
        return self.completed_subtasks >= self.total_subtasks
    
    @property
    def is_partial_success(self) -> bool:
        """任务是否部分成功(超过阈值)"""
        if self.total_subtasks == 0:
            return False
        completion_rate = self.completed_subtasks / self.total_subtasks
        return completion_rate >= self.partial_threshold
    
    @property
    def completion_rate(self) -> float:
        """任务完成比例"""
        if self.total_subtasks == 0:
            return 0.0
        return self.completed_subtasks / self.total_subtasks
    
    @property
    def duration(self) -> float:
        """任务持续时间(秒)"""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time
    
    def record_step(self, action_type: str, is_wait: bool = False):
        """记录执行步骤"""
        self.total_steps += 1
        self.action_counts[action_type] += 1
        
        if is_wait or action_type in ['等待', 'wait']:
            self.wait_steps += 1
        else:
            self.active_steps += 1
    
    def record_communication(self, from_robot: str, to_robot: str, is_broadcast: bool = False):
        """记录通信"""
        self.communication_count += 1
        self.messages_sent += 1
        
        if is_broadcast:
            # 广播消息算多次通信
            self.communication_count += 1
    
    def record_message_received(self, robot_name: str):
        """记录收到消息"""
        self.messages_received += 1
    
    def record_robot_action(self, robot_name: str, action_type: str):
        """记录机器人动作"""
        if robot_name not in self.robot_participation:
            self.robot_participation[robot_name] = {
                'actions': 0,
                'communications': 0,
                'action_types': defaultdict(int)
            }
        
        self.robot_participation[robot_name]['actions'] += 1
        self.robot_participation[robot_name]['action_types'][action_type] += 1
    
    def update_progress(self, completed: int, total: int):
        """更新任务进度"""
        self.completed_subtasks = completed
        self.total_subtasks = total
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'task_id': self.task_id,
            'task_description': self.task_description,
            'completion': {
                'completed_subtasks': self.completed_subtasks,
                'total_subtasks': self.total_subtasks,
                'completion_rate': round(self.completion_rate, 3),
                'is_completed': self.is_completed,
                'is_partial_success': self.is_partial_success
            },
            'steps': {
                'total_steps': self.total_steps,
                'active_steps': self.active_steps,
                'wait_steps': self.wait_steps,
                'active_ratio': round(self.active_steps / self.total_steps, 3) if self.total_steps > 0 else 0
            },
            'communication': {
                'total_communications': self.communication_count,
                'messages_sent': self.messages_sent,
                'messages_received': self.messages_received
            },
            'time': {
                'start_time': self.start_time,
                'end_time': self.end_time,
                'duration_seconds': round(self.duration, 2)
            },
            'robot_participation': {
                name: {
                    'actions': data['actions'],
                    'communications': data['communications'],
                    'action_breakdown': dict(data['action_types'])
                }
                for name, data in self.robot_participation.items()
            },
            'action_breakdown': dict(self.action_counts)
        }


class MetricsCollector:
    """指标收集器 - 管理所有任务的评估指标"""
    
    def __init__(self):
        self.tasks: Dict[str, TaskMetrics] = {}
        self.current_task_id: Optional[str] = None
        self.overall_stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'partial_success_tasks': 0,
            'total_communications': 0,
            'total_steps': 0,
            'total_active_steps': 0
        }
    
    def start_task(self, task_id: str, task_description: str = "", total_subtasks: int = 0) -> TaskMetrics:
        """开始记录新任务"""
        metrics = TaskMetrics(
            task_id=task_id,
            task_description=task_description,
            total_subtasks=total_subtasks
        )
        metrics.start()
        
        self.tasks[task_id] = metrics
        self.current_task_id = task_id
        self.overall_stats['total_tasks'] += 1
        
        return metrics
    
    def end_task(self, task_id: str = None) -> TaskMetrics:
        """结束任务记录"""
        tid = task_id or self.current_task_id
        if tid and tid in self.tasks:
            self.tasks[tid].end()
            self._update_overall_stats(tid)
            return self.tasks[tid]
        return None
    
    def get_current_task(self) -> Optional[TaskMetrics]:
        """获取当前任务的指标"""
        if self.current_task_id and self.current_task_id in self.tasks:
            return self.tasks[self.current_task_id]
        return None
    
    def record_step(self, action_type: str, robot_name: str = None, is_wait: bool = False):
        """记录执行步骤"""
        task = self.get_current_task()
        if task:
            task.record_step(action_type, is_wait)
            if robot_name:
                task.record_robot_action(robot_name, action_type)
    
    def record_communication(self, from_robot: str, to_robot: str, is_broadcast: bool = False):
        """记录通信"""
        task = self.get_current_task()
        if task:
            task.record_communication(from_robot, to_robot, is_broadcast)
            self.overall_stats['total_communications'] += 1
    
    def record_message_received(self, robot_name: str):
        """记录收到消息"""
        task = self.get_current_task()
        if task:
            task.record_message_received(robot_name)
    
    def update_progress(self, completed: int, total: int):
        """更新任务进度"""
        task = self.get_current_task()
        if task:
            task.update_progress(completed, total)
    
    def _update_overall_stats(self, task_id: str):
        """更新总体统计"""
        task = self.tasks[task_id]
        if task.is_completed:
            self.overall_stats['completed_tasks'] += 1
        if task.is_partial_success:
            self.overall_stats['partial_success_tasks'] += 1
        self.overall_stats['total_steps'] += task.total_steps
        self.overall_stats['total_active_steps'] += task.active_steps
    
    def get_summary_metrics(self) -> Dict[str, Any]:
        """获取汇总指标 (SUCC, PS, TS, AS, CC)"""
        total = self.overall_stats['total_tasks']
        if total == 0:
            return {
                'SUCC': 0.0,
                'PS': 0.0,
                'TS': 0,
                'AS': 0,
                'CC': 0
            }
        
        return {
            'SUCC': round(self.overall_stats['completed_tasks'] / total, 3),
            'PS': round(self.overall_stats['partial_success_tasks'] / total, 3),
            'TS': self.overall_stats['total_steps'],
            'AS': self.overall_stats['total_active_steps'],
            'CC': self.overall_stats['total_communications']
        }
    
    def get_full_report(self) -> Dict[str, Any]:
        """获取完整报告"""
        return {
            'summary_metrics': self.get_summary_metrics(),
            'overall_stats': self.overall_stats,
            'tasks': {
                tid: metrics.to_dict()
                for tid, metrics in self.tasks.items()
            }
        }
    
    def get_current_task_metrics(self) -> Optional[Dict[str, Any]]:
        """获取当前任务的指标字典"""
        task = self.get_current_task()
        if task:
            return task.to_dict()
        return None
    
    def reset(self):
        """重置所有指标"""
        self.tasks.clear()
        self.current_task_id = None
        self.overall_stats = {
            'total_tasks': 0,
            'completed_tasks': 0,
            'partial_success_tasks': 0,
            'total_communications': 0,
            'total_steps': 0,
            'total_active_steps': 0
        }


# 全局指标收集器实例
_metrics_collector = None


def get_metrics_collector() -> MetricsCollector:
    """获取全局指标收集器实例"""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector


def reset_metrics_collector():
    """重置全局指标收集器"""
    global _metrics_collector
    _metrics_collector = MetricsCollector()
