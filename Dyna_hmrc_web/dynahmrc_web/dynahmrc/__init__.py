# bestman/dynahmrc/__init__.py
"""
DynaHMRC: Decentralized Heterogeneous Multi-Robot Collaboration
"""
'''
__version__ = "0.1.0"
__author__ = "Based on DynaHMRC paper (TRO 2025)"

from .core import RobotAgent, CollaborationPhase
from .robots import MobileManipulatorRobot, ManipulatorRobot, MobileRobot, DroneRobot
from .tasks import PackObjectsTask, SortSolidsTask, MakeSandwichTask
from .coordinator import DynaHMRC_Coordinator

__all__ = [
    'RobotAgent',
    'CollaborationPhase',
    'MobileManipulatorRobot',
    'ManipulatorRobot',
    'MobileRobot',
    'DroneRobot',
    'PackObjectsTask',
    'SortSolidsTask',
    'MakeSandwichTask',
    'DynaHMRC_Coordinator'
]
'''

# dynahmrc/__init__.py
"""
DynaHMRC - 基于大语言模型的异构多机器人动态协作框架
"""

from .coordinator import DynaHMRC_Coordinator, BaseRobot, RobotState, ExecutionStatus, ExecutionResult
from .utils.llm_api import create_llm_client, BaseLLMClient, KimiLLMClient, MockLLMClient
from .core import CollaborationPhase, CollaborationManager, TaskAllocator, Task, TaskStatus

__all__ = [
    'DynaHMRC_Coordinator',
    'BaseRobot',
    'RobotState',
    'ExecutionStatus',
    'ExecutionResult',
    'create_llm_client',
    'BaseLLMClient',
    'KimiLLMClient',
    'MockLLMClient',
    'CollaborationPhase',
    'CollaborationManager',
    'TaskAllocator',
    'Task',
    'TaskStatus'
]