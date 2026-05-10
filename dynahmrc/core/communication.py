# bestman/dynahmrc/core/communication.py
"""
Communication Module - Inter-robot message passing
"""

from typing import Dict, List, Callable
import queue
import threading

class CommunicationModule:
    """
    Handles message passing between robots
    Supports unicast, multicast, and broadcast
    """
    
    def __init__(self, robot_name: str):
        self.robot_name = robot_name
        self.message_queue = queue.Queue()
        self.subscribers: List[Callable] = []
        self.connected_robots: List[str] = []
        
    def connect(self, robot_names: List[str]):
        """Establish connection with teammates"""
        self.connected_robots = [name for name in robot_names if name != self.robot_name]
    
    def send_message(self, from_robot: str, to_robot: str, content: str):
        """
        Send message to target robot(s)
        to_robot: 'all' for broadcast, or specific robot name
        """
        message = {
            'from': from_robot,
            'to': to_robot,
            'content': content,
            'timestamp': 0  # Will be set by receiver
        }
        
        # In simulation, directly deliver to target
        if to_robot == 'all':
            for robot in self.connected_robots:
                self._deliver_message(robot, message)
        else:
            self._deliver_message(to_robot, message)
    
    def _deliver_message(self, target_robot: str, message: Dict):
        """Deliver message to target robot's queue"""
        # This would be implemented via shared memory or network in distributed system
        # For simulation, we use a global message broker
        MessageBroker.deliver(target_robot, message)
    
    def receive_messages(self) -> List[Dict]:
        """Poll for new messages"""
        messages = []
        while not self.message_queue.empty():
            try:
                msg = self.message_queue.get_nowait()
                messages.append(msg)
            except queue.Empty:
                break
        return messages
    
    def on_message(self, callback: Callable):
        """Subscribe to message notifications"""
        self.subscribers.append(callback)
    
    def _notify_subscribers(self, message: Dict):
        """Notify all subscribers"""
        for callback in self.subscribers:
            callback(message)


class MessageBroker:
    """
    Global message broker for simulation
    In real deployment, this would be replaced by ROS2/DDS
    """
    _queues: Dict[str, queue.Queue] = {}
    
    @classmethod
    def register(cls, robot_name: str):
        """Register a robot"""
        if robot_name not in cls._queues:
            cls._queues[robot_name] = queue.Queue()
    
    @classmethod
    def deliver(cls, target_robot: str, message: Dict):
        """Deliver message to target"""
        if target_robot in cls._queues:
            cls._queues[target_robot].put(message)
    
    @classmethod
    def get_queue(cls, robot_name: str) -> queue.Queue:
        """Get robot's message queue"""
        return cls._queues.get(robot_name, queue.Queue())