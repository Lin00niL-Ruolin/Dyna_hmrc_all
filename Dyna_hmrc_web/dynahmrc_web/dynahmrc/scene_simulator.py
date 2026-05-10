"""
场景模拟器 - 提供真实的物理环境模拟
用于 DynaHMRC 多机器人协作系统的仿真
"""

import random
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class Object:
    """场景中的物体"""
    name: str
    obj_type: str  # 'object', 'furniture', 'container'
    position: List[float]  # [x, y, z]
    state: str = 'available'  # 'available', 'held', 'in_container'
    holder: Optional[str] = None  # 持有者的名字


@dataclass
class RobotState:
    """机器人状态"""
    name: str
    robot_type: str
    position: List[float]  # [x, y, z]
    orientation: float = 0.0  # 朝向角度（弧度）
    holding_object: Optional[str] = None
    max_speed: float = 0.5  # 最大移动速度 m/s
    max_range: float = 1.0  # 最大操作范围 m


class SceneSimulator:
    """
    场景模拟器
    - 管理物体和机器人的位置
    - 计算距离和可达性
    - 模拟动作执行
    """
    
    def __init__(self, room_size: Tuple[float, float] = (10.0, 10.0)):
        """
        初始化场景
        
        Args:
            room_size: 房间尺寸 (width, depth)，单位米
        """
        self.room_width, self.room_depth = room_size
        self.objects: Dict[str, Object] = {}
        self.robots: Dict[str, RobotState] = {}
        self.furniture: Dict[str, Object] = {}
        
    def add_robot(self, name: str, robot_type: str, 
                  position: List[float] = None,
                  max_speed: float = 0.5,
                  max_range: float = 1.0):
        """添加机器人"""
        if position is None:
            position = self._random_position()
        
        self.robots[name] = RobotState(
            name=name,
            robot_type=robot_type,
            position=position,
            max_speed=max_speed,
            max_range=max_range
        )
    
    def add_object(self, name: str, obj_type: str = 'object',
                   position: List[float] = None,
                   on_furniture: str = None):
        """
        添加物体到场景
        
        Args:
            name: 物体名称
            obj_type: 物体类型
            position: 位置，如果为None则随机生成
            on_furniture: 放置在某个家具上
        """
        if on_furniture and on_furniture in self.furniture:
            # 放在家具上（高度+0.5m）
            furniture_pos = self.furniture[on_furniture].position
            position = [
                furniture_pos[0] + random.uniform(-0.3, 0.3),
                furniture_pos[1] + random.uniform(-0.3, 0.3),
                furniture_pos[2] + 0.5
            ]
        elif position is None:
            position = self._random_position()
        
        self.objects[name] = Object(
            name=name,
            obj_type=obj_type,
            position=position
        )
    
    def add_furniture(self, name: str, position: List[float] = None,
                      size: List[float] = None):
        """添加家具"""
        if position is None:
            position = self._random_position()
        
        self.furniture[name] = Object(
            name=name,
            obj_type='furniture',
            position=position
        )
    
    def _random_position(self) -> List[float]:
        """生成随机位置"""
        return [
            random.uniform(-self.room_width/2, self.room_width/2),
            random.uniform(-self.room_depth/2, self.room_depth/2),
            random.uniform(0.5, 1.5)  # 高度
        ]
    
    def get_distance(self, pos1: List[float], pos2: List[float]) -> float:
        """计算两点之间的距离（xy平面）"""
        return math.sqrt(
            (pos1[0] - pos2[0])**2 +
            (pos1[1] - pos2[1])**2
        )
    
    def is_reachable(self, robot_name: str, target_pos: List[float]) -> Tuple[bool, float]:
        """
        检查目标是否在机器人可达范围内
        
        Returns:
            (是否可达, 距离)
        """
        if robot_name not in self.robots:
            return False, float('inf')
        
        robot = self.robots[robot_name]
        distance = self.get_distance(robot.position, target_pos)
        
        return distance <= robot.max_range, distance
    
    def navigate(self, robot_name: str, target_pos: List[float], 
                 step_size: float = 0.5) -> Dict:
        """
        模拟导航动作
        
        Returns:
            {
                'success': bool,
                'message': str,
                'distance_moved': float,
                'found_objects': List[str]
            }
        """
        if robot_name not in self.robots:
            return {
                'success': False,
                'message': f'Robot {robot_name} not found',
                'distance_moved': 0.0,
                'found_objects': []
            }
        
        robot = self.robots[robot_name]
        current_pos = robot.position
        
        # 计算到目标的距离
        distance = self.get_distance(current_pos, target_pos)
        
        if distance <= step_size:
            # 可以直接到达
            robot.position = target_pos.copy()
            distance_moved = distance
        else:
            # 向目标移动一步
            dx = target_pos[0] - current_pos[0]
            dy = target_pos[1] - current_pos[1]
            
            robot.position[0] += (dx / distance) * step_size
            robot.position[1] += (dy / distance) * step_size
            distance_moved = step_size
        
        # 检查新位置附近发现了什么物体（感知范围2米）
        found_objects = []
        perception_range = 2.0
        
        for obj_name, obj in self.objects.items():
            if obj.state == 'available':
                dist = self.get_distance(robot.position, obj.position)
                if dist <= perception_range:
                    found_objects.append(obj_name)
        
        for furn_name, furn in self.furniture.items():
            dist = self.get_distance(robot.position, furn.position)
            if dist <= perception_range:
                found_objects.append(furn_name)
        
        return {
            'success': True,
            'message': f'Navigation Success: Moved {distance_moved:.2f}m towards target',
            'distance_moved': distance_moved,
            'found_objects': found_objects,
            'remaining_distance': self.get_distance(robot.position, target_pos)
        }
    
    def pick(self, robot_name: str, object_name: str) -> Dict:
        """
        模拟拾取动作
        
        Returns:
            {
                'success': bool,
                'message': str,
                'grasped_object': str
            }
        """
        if robot_name not in self.robots:
            return {
                'success': False,
                'message': f'Robot {robot_name} not found'
            }
        
        if object_name not in self.objects:
            return {
                'success': False,
                'message': f'Object {object_name} not found'
            }
        
        robot = self.robots[robot_name]
        obj = self.objects[object_name]
        
        # 检查是否已经有物体
        if robot.holding_object:
            return {
                'success': False,
                'message': f'Already holding {robot.holding_object}'
            }
        
        # 检查物体是否可用
        if obj.state != 'available':
            return {
                'success': False,
                'message': f'Object {object_name} is not available (state: {obj.state})'
            }
        
        # 检查距离
        reachable, distance = self.is_reachable(robot_name, obj.position)
        if not reachable:
            return {
                'success': False,
                'message': f'Pick Failed: Distance {distance:.2f}m exceeds max range {robot.max_range}m',
                'distance': distance
            }
        
        # 拾取成功
        robot.holding_object = object_name
        obj.state = 'held'
        obj.holder = robot_name
        
        return {
            'success': True,
            'message': f'Pick Success: Grasped {object_name}',
            'grasped_object': object_name
        }
    
    def place(self, robot_name: str, location: str = None) -> Dict:
        """
        模拟放置动作
        
        Args:
            location: 放置位置或容器名称
        
        Returns:
            {
                'success': bool,
                'message': str
            }
        """
        if robot_name not in self.robots:
            return {
                'success': False,
                'message': f'Robot {robot_name} not found'
            }
        
        robot = self.robots[robot_name]
        
        # 检查是否持有物体
        if not robot.holding_object:
            return {
                'success': False,
                'message': 'Not holding any object'
            }
        
        object_name = robot.holding_object
        obj = self.objects[object_name]
        
        # 更新物体位置到机器人当前位置
        obj.position = robot.position.copy()
        obj.state = 'available'
        obj.holder = None
        
        # 更新机器人状态
        robot.holding_object = None
        
        location_str = f' at {location}' if location else ''
        return {
            'success': True,
            'message': f'Place Success: Placed {object_name}{location_str}'
        }
    
    def get_scene_graph(self) -> Dict:
        """获取当前场景图（用于传递给LLM）"""
        scene = {}
        
        # 添加物体
        for name, obj in self.objects.items():
            scene[name] = {
                'type': obj.obj_type,
                'position': obj.position.copy(),
                'state': obj.state
            }
        
        # 添加家具
        for name, furn in self.furniture.items():
            scene[name] = {
                'type': 'furniture',
                'position': furn.position.copy()
            }
        
        return scene
    
    def get_robot_pose(self, robot_name: str) -> Optional[List[float]]:
        """获取机器人位姿"""
        if robot_name not in self.robots:
            return None
        robot = self.robots[robot_name]
        return robot.position.copy() + [robot.orientation]
    
    def get_all_robot_states(self) -> Dict:
        """获取所有机器人状态"""
        states = {}
        for name, robot in self.robots.items():
            states[name] = {
                'position': robot.position.copy(),
                'holding': robot.holding_object,
                'type': robot.robot_type
            }
        return states
    
    def initialize_default_scene(self, object_names: List[str] = None):
        """初始化默认场景"""
        # 添加家具
        self.add_furniture('table', position=[2.0, 1.0, 0.8])
        self.add_furniture('chair', position=[3.0, 2.0, 0.5])
        self.add_furniture('cabinet', position=[-2.0, 1.0, 1.0])
        self.add_furniture('sink', position=[-1.0, -2.0, 0.9])
        
        # 添加物体
        if object_names is None:
            object_names = ['apple', 'book', 'cup', 'remote']
        
        for obj_name in object_names:
            # 随机放在家具上或地上
            if random.random() > 0.3:
                furniture = random.choice(list(self.furniture.keys()))
                self.add_object(obj_name, on_furniture=furniture)
            else:
                self.add_object(obj_name)
    
    def print_scene(self):
        """打印场景状态（用于调试）"""
        print("\n=== Scene Status ===")
        print("\nRobots:")
        for name, robot in self.robots.items():
            print(f"  {name} ({robot.robot_type}): pos={robot.position}, holding={robot.holding_object}")
        
        print("\nFurniture:")
        for name, furn in self.furniture.items():
            print(f"  {name}: pos={furn.position}")
        
        print("\nObjects:")
        for name, obj in self.objects.items():
            print(f"  {name}: pos={obj.position}, state={obj.state}")
