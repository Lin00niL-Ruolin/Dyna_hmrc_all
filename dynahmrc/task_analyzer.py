"""
Task Analyzer - Analyzes task complexity and determines if multi-robot collaboration is needed
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class TaskComplexity(Enum):
    """Task complexity levels"""
    SIMPLE = "simple"           # Simple task, single robot can complete
    MODERATE = "moderate"       # Moderate task, single robot can complete but slower
    COMPLEX = "complex"         # Complex task, requires multi-robot collaboration
    VERY_COMPLEX = "very_complex"  # Very complex, must have multi-robot


class CollaborationType(Enum):
    """Collaboration types"""
    SEQUENTIAL = "sequential"   # Sequential collaboration (one after another)
    PARALLEL = "parallel"       # Parallel collaboration (simultaneous)
    HETEROGENEOUS = "heterogeneous"  # Heterogeneous collaboration (different robot types)
    HYBRID = "hybrid"           # Hybrid collaboration


class TaskType(Enum):
    """Three basic task types"""
    PACK_OBJECT = "pack_object"      # Packing task
    SORT_SOLID = "sort_solid"        # Sorting task
    MAKE_SANDWICH = "make_sandwich"  # Assembly/stacking task
    UNKNOWN = "unknown"


@dataclass
class Furniture:
    """
    Furniture item in Scene Graph (DynaHMRC paper)
    - position: [x, y, z] coordinates
    - orientation: [qx, qy, qz, qw] quaternion
    - stand_pose: [x, y, theta] navigation target for robot
    - state: open/close for containers
    - contents: items inside (initially hidden)
    """
    name: str
    position: List[float]
    orientation: List[float]
    stand_pose: List[float]
    state: str = "open"  # "open" or "close"
    contents: List[str] = None  # Items inside (hidden until explored)
    surface_items: List[str] = None  # Items on surface (visible)
    
    def __post_init__(self):
        if self.contents is None:
            self.contents = []
        if self.surface_items is None:
            self.surface_items = []


@dataclass
class SceneGraph:
    """
    Scene Graph representation (DynaHMRC paper)
    Contains all furniture and their relationships in the environment
    """
    name: str
    description: str
    furniture: Dict[str, Furniture]
    objects: Dict[str, str]  # object_name -> furniture_name mapping
    
    def get_visible_objects(self) -> List[str]:
        """Get all visible objects (on surfaces)"""
        visible = []
        for furn in self.furniture.values():
            visible.extend(furn.surface_items)
        return visible
    
    def get_hidden_objects(self) -> List[str]:
        """Get all hidden objects (inside closed containers)"""
        hidden = []
        for furn in self.furniture.values():
            if furn.state == "close":
                hidden.extend(furn.contents)
        return hidden
    
    def get_all_locations(self) -> List[str]:
        """Get all furniture names as locations"""
        return list(self.furniture.keys())
    
    def find_object_location(self, obj_name: str) -> Optional[str]:
        """Find which furniture contains the object"""
        for furn_name, furn in self.furniture.items():
            if obj_name in furn.surface_items or obj_name in furn.contents:
                return furn_name
        return None


@dataclass
class TaskAnalysis:
    """Task analysis result"""
    task: str
    task_type: TaskType
    complexity: TaskComplexity
    D_value: float  # DynaHMRC complexity score [0, 1]
    collaboration_needed: bool
    min_robots: int
    recommended_robots: int
    required_capabilities: List[str]
    collaboration_type: CollaborationType
    estimated_steps: int
    reasoning: str
    subtasks: List[Dict]
    location_factor: float  # L value
    quantity_factor: float  # N value
    collaboration_factor: float  # Y value
    dynamic_complexity: List[str] = None  # Dynamic changes: CTO, IRZ, ANC, REC


class TaskAnalyzer:
    """
    Task Analyzer
    
    Analyzes task characteristics:
    1. Object count and distribution
    2. Operation type diversity
    3. Spatial distribution (single point vs multi-point)
    4. Time constraints
    5. Capability requirements
    """
    
    def __init__(self):
        # Capability keyword mapping (English + Chinese)
        self.capability_keywords = {
            'navigation': ['move', 'go to', 'walk to', 'navigate', 'enter', 'cross', 'room', 
                          '移动', '导航', '行走', '进入', '穿过', '房间', '客厅', '厨房', '卧室'],
            'manipulation': ['take', 'get', 'put', 'pick up', 'move', 'place', 'organize', 'tidy', 'pick',
                            '拿', '取', '放', '拾取', '放置', '移动', '整理', '收拾', '收集', '打包'],
            'aerial': ['fly', 'air', 'top', 'above', 'high', 'drone',
                      '飞', '空中', '顶部', '上方', '高处', '无人机', '俯视'],
            'precision': ['precision', 'delicate', 'careful', 'gentle',
                         '精确', '精细', '小心', '轻柔', '精密'],
            'heavy_lifting': ['heavy', 'weight', 'heavy object', 'carry', 'lift',
                             '重', '重物', '搬运', '举起', '携带'],
            'exploration': ['search', 'find', 'explore', 'discover', 'unknown',
                           '搜索', '寻找', '探索', '发现', '未知', '散落', '分布'],
            'perception': ['inspect', 'observe', 'monitor', 'check',
                          '检查', '观察', '监控', '查看', '识别', '定位'],
            'communication': ['notify', 'report', 'coordinate', 'tell', 'inform',
                             '通知', '报告', '协调', '告诉', '沟通', '协作', '配合'],
        }
        
        # Spatial distribution keywords (English + Chinese)
        self.location_keywords = ['room', 'location', 'place', 'area', 'zone',
                                 '房间', '位置', '地方', '区域', '桌面', '书架', '台面', '柜台', '抽屉', '橱柜']
        self.multi_location_indicators = [
            'all', 'every', 'each', 'different', 'multi', 'multiple', 'between', 'and', 'with', 'as well as', 'rooms',
            '所有', '每个', '各个', '不同', '多', '多个', '分散', '散落', '和', '与', '以及', '还有', '之间'
        ]
        
        # Time constraint keywords (English + Chinese)
        self.time_constraints = [
            'minute', 'second', 'hour', 'within', 'asap', 'immediately', 'simultaneously', 'at the same time',
            '分钟', '秒', '小时', '之内', '尽快', '立即', '同时', '紧急', '限时'
        ]
        
        # Collaboration keywords (English + Chinese)
        self.collaboration_keywords = [
            'cooperate', 'collaborate', 'together', 'jointly', 'simultaneously', 'mutually', 'assist', 'help', 'support',
            '合作', '协作', '一起', '共同', '同时', '互相', '协助', '帮助', '支持', '配合', '协调', '多个机器人'
        ]
        
        # Dynamic complexity factors (CTO, IRZ, ANC, REC)
        self.dynamic_complexity_factors = {
            'CTO': ['change target', 'modify', 'add object', 'remove object', 
                   '变更目标', '修改任务', '增加物品', '减少物品', '中途变更'],
            'IRZ': ['restricted zone', 'forbidden area', 'no entry', 'cannot enter',
                   '禁区', '禁止区域', '限制区域', '不能进入'],
            'ANC': ['new member', 'add robot', 'join team', 'new teammate',
                   '新成员', '增加机器人', '加入团队', '新队友'],
            'REC': ['robot failure', 'member removed', 'leave team', 'broken',
                   '机器人故障', '成员移除', '离开团队', '离队', '损坏']
        }
        
        # Predefined Scene Graphs (Real environments)
        self.scenes = self._init_scenes()
        self.current_scene = None
        
        # Three basic task type keywords (English and Chinese)
        self.task_type_keywords = {
            TaskType.PACK_OBJECT: ['pack', '打包', '装箱', '收集', '整理', '放入', '装进', 'box', 'tidy', 'put in', 'collect', 'put to', 'pack into'],
            TaskType.SORT_SOLID: ['sort', '分类', '分拣', '按颜色', '按类型', '归类', 'sort to', 'put to', 'match', 'by color', 'by type', 'separately put'],
            TaskType.MAKE_SANDWICH: ['assemble', 'stack', '制作', '堆叠', '组装', '搭建', '三明治', '汉堡', 'stack up', 'build', 'make', 'in order', 'sandwich', 'burger']
        }
    
    def _init_scenes(self) -> Dict[str, SceneGraph]:
        """Initialize predefined scene graphs - 3 scenes (A, B, C) with bathroom + living room + kitchen"""
        scenes = {}
        
        # ==================== 场景A: 一字排开布局 ====================
        scene_a = {
            # 厨房区域 (x:0-4, y:0-4)
            'kitchen_table': Furniture(
                name='kitchen_table',
                position=[2.0, 1.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[2.0, 0.5, 0.0],
                state='open',
                surface_items=['tray', 'bowl', 'plate', 'fork', 'apple']
            ),
            'refrigerator': Furniture(
                name='refrigerator',
                position=[0.5, 3.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[0.5, 2.0, 1.57],
                state='close',
                contents=['cheese', 'tomato', 'lettuce', 'meat']
            ),
            'kitchen_cabinet': Furniture(
                name='kitchen_cabinet',
                position=[3.5, 3.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[3.5, 2.0, -1.57],
                state='close',
                contents=['spoon', 'knife', 'cup', 'spice']
            ),
            'countertop': Furniture(
                name='countertop',
                position=[2.0, 3.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[2.0, 2.0, 0.0],
                state='open',
                surface_items=['tray', 'cutting_board', 'bread']
            ),
            # 客厅区域 (x:5-9, y:0-4)
            'coffee_table': Furniture(
                name='coffee_table',
                position=[7.0, 2.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[7.0, 1.0, 0.0],
                state='open',
                surface_items=['tray', 'remote', 'cup', 'magazine']
            ),
            'sofa': Furniture(
                name='sofa',
                position=[9.0, 2.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[9.0, 1.0, 0.0],
                state='open',
                surface_items=['pillow', 'blanket', 'phone']
            ),
            'tv_cabinet': Furniture(
                name='tv_cabinet',
                position=[6.0, 3.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[6.0, 2.5, 1.57],
                state='close',
                contents=['dvd', 'cable', 'game']
            ),
            'bookshelf': Furniture(
                name='bookshelf',
                position=[8.5, 0.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[8.5, -0.5, 0.0],
                state='open',
                surface_items=['book', 'decoration'],
                contents=['photo_frame', 'toy']
            ),
            # 浴室区域 (x:0-4, y:5-9)
            'washbasin': Furniture(
                name='washbasin',
                position=[1.0, 6.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.0, 5.0, 0.0],
                state='open',
                surface_items=['tray', 'toothbrush', 'cup', 'soap']
            ),
            'bathroom_cabinet': Furniture(
                name='bathroom_cabinet',
                position=[3.5, 6.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[3.5, 5.0, 0.0],
                state='close',
                contents=['towel', 'shampoo', 'toothpaste', 'perfume']
            ),
            'shelf': Furniture(
                name='shelf',
                position=[2.0, 8.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[2.0, 7.0, 0.0],
                state='open',
                surface_items=['tray', 'lotion']
            )
        }
        scenes['scene_a'] = self._create_scene_graph('scene_a',
            '场景A',
            '厨房、客厅、浴室一字排开布局，物品分散摆放。',
            scene_a)
        
        # ==================== 场景B: L型布局 ====================
        scene_b = {
            # 厨房区域 - 位置不同 (x:0-4, y:0-4)
            'kitchen_table': Furniture(
                name='kitchen_table',
                position=[1.0, 2.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.0, 1.0, 0.0],
                state='open',
                surface_items=['tray', 'bowl', 'plate', 'fork', 'knife']
            ),
            'refrigerator': Furniture(
                name='refrigerator',
                position=[3.5, 1.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[3.5, 0.0, -1.57],
                state='close',
                contents=['cheese', 'apple', 'cup', 'spice']
            ),
            'kitchen_cabinet': Furniture(
                name='kitchen_cabinet',
                position=[0.5, 3.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[0.5, 2.5, 1.57],
                state='close',
                contents=['spoon', 'tomato', 'lettuce']
            ),
            'countertop': Furniture(
                name='countertop',
                position=[3.0, 3.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[3.0, 2.0, 0.0],
                state='open',
                surface_items=['tray', 'cutting_board', 'bread', 'meat']
            ),
            # 客厅区域 - 位置不同 (x:5-9, y:0-4)
            'coffee_table': Furniture(
                name='coffee_table',
                position=[6.5, 2.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[6.5, 1.5, 0.0],
                state='open',
                surface_items=['tray', 'remote', 'keys', 'phone', 'cup']
            ),
            'sofa': Furniture(
                name='sofa',
                position=[8.5, 1.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[8.5, 0.0, 0.0],
                state='open',
                surface_items=['pillow', 'blanket', 'book']
            ),
            'tv_cabinet': Furniture(
                name='tv_cabinet',
                position=[9.0, 3.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[9.0, 2.5, -1.57],
                state='close',
                contents=['dvd', 'magazine']
            ),
            'bookshelf': Furniture(
                name='bookshelf',
                position=[6.0, 0.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[6.0, -0.5, 0.0],
                state='open',
                surface_items=['book', 'decoration', 'photo_frame', 'toy']
            ),
            # 浴室区域 - 位置不同 (x:5-9, y:5-9) L型转角
            'washbasin': Furniture(
                name='washbasin',
                position=[6.0, 6.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[6.0, 5.0, 0.0],
                state='open',
                surface_items=['tray', 'toothbrush', 'soap', 'towel']
            ),
            'bathroom_cabinet': Furniture(
                name='bathroom_cabinet',
                position=[8.5, 6.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[8.5, 5.0, 0.0],
                state='close',
                contents=['shampoo', 'toothpaste']
            ),
            'shelf': Furniture(
                name='shelf',
                position=[7.0, 8.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[7.0, 7.0, 0.0],
                state='open',
                surface_items=['tray', 'perfume', 'lotion', 'cup']
            )
        }
        scenes['scene_b'] = self._create_scene_graph('scene_b',
            '场景B',
            '客厅与厨房在一侧，浴室在另一侧呈L型布局。',
            scene_b)
        
        # ==================== 场景C: 紧凑布局 ====================
        scene_c = {
            # 厨房区域 - 紧凑 (x:0-3, y:0-3)
            'kitchen_table': Furniture(
                name='kitchen_table',
                position=[1.5, 1.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.5, 0.0, 0.0],
                state='open',
                surface_items=['tray', 'bowl', 'cup', 'apple']
            ),
            'refrigerator': Furniture(
                name='refrigerator',
                position=[0.5, 2.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[0.5, 1.5, 1.57],
                state='close',
                contents=['cheese', 'tomato', 'bread', 'tray']
            ),
            'kitchen_cabinet': Furniture(
                name='kitchen_cabinet',
                position=[2.5, 2.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[2.5, 1.5, -1.57],
                state='close',
                contents=['plate', 'fork', 'knife', 'spoon', 'spice']
            ),
            'countertop': Furniture(
                name='countertop',
                position=[1.5, 2.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.5, 1.0, 0.0],
                state='open',
                surface_items=['tray', 'cutting_board']
            ),
            # 客厅区域 - 紧凑 (x:4-7, y:0-3)
            'coffee_table': Furniture(
                name='coffee_table',
                position=[5.5, 1.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[5.5, 0.5, 0.0],
                state='open',
                surface_items=['tray', 'remote', 'cup', 'magazine']
            ),
            'sofa': Furniture(
                name='sofa',
                position=[7.0, 1.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[7.0, 0.5, 0.0],
                state='open',
                surface_items=['pillow', 'phone', 'book']
            ),
            'tv_cabinet': Furniture(
                name='tv_cabinet',
                position=[4.5, 2.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[4.5, 1.5, 1.57],
                state='close',
                contents=['dvd', 'decoration', 'tray']
            ),
            'bookshelf': Furniture(
                name='bookshelf',
                position=[6.5, 0.3, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[6.5, -0.7, 0.0],
                state='open',
                surface_items=['book', 'photo_frame'],
                contents=['toy']
            ),
            # 浴室区域 - 紧凑 (x:0-3, y:4-7)
            'washbasin': Furniture(
                name='washbasin',
                position=[1.0, 5.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.0, 4.0, 0.0],
                state='open',
                surface_items=['tray', 'toothbrush', 'soap']
            ),
            'bathroom_cabinet': Furniture(
                name='bathroom_cabinet',
                position=[2.5, 5.0, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[2.5, 4.0, 0.0],
                state='close',
                contents=['towel', 'shampoo', 'toothpaste', 'perfume', 'lotion']
            ),
            'shelf': Furniture(
                name='shelf',
                position=[1.5, 6.5, 0.0],
                orientation=[0.0, 0.0, 0.0, 1.0],
                stand_pose=[1.5, 5.5, 0.0],
                state='open',
                surface_items=['tray']
            )
        }
        scenes['scene_c'] = self._create_scene_graph('scene_c',
            '场景C',
            '紧凑家居环境，三个房间紧密相连，家具间距较小。',
            scene_c)
        
        return scenes
    
    def _create_scene_graph(self, name: str, display_name: str, description: str, 
                           furniture: Dict[str, Furniture]) -> SceneGraph:
        """Helper method to create SceneGraph from furniture dict"""
        objects = {}
        for furn in furniture.values():
            for item in furn.surface_items:
                objects[item] = furn.name
            for item in furn.contents:
                objects[item] = furn.name
        
        return SceneGraph(
            name=name,
            description=display_name + '\n' + description,
            furniture=furniture,
            objects=objects
        )
    
    def get_scene(self, scene_name: str) -> Optional[SceneGraph]:
        """Get a scene by name"""
        return self.scenes.get(scene_name)
    
    def set_scene(self, scene_name: str):
        """Set current scene for analysis"""
        if scene_name in self.scenes:
            self.current_scene = self.scenes[scene_name]
    
    def get_all_scenes(self) -> Dict[str, SceneGraph]:
        """Get all available scenes"""
        return self.scenes
    
    def identify_task_type(self, task: str) -> TaskType:
        """Identify which basic task type this is"""
        task_lower = task.lower()
        
        # Check explicit prefixes (English and Chinese)
        # Pack/Packing/装箱 tasks
        if (task.startswith('Pack:') or task.startswith('Pack：') or 
            task.startswith('Packing:') or task.startswith('Packing：') or
            task.startswith('装箱') or task.startswith('打包') or 
            task.startswith('pack')):
            return TaskType.PACK_OBJECT
        
        # Sort/Sorting/分类 tasks
        if (task.startswith('Sort:') or task.startswith('Sort：') or
            task.startswith('Sorting:') or task.startswith('Sorting：') or
            task.startswith('分类') or task.startswith('sort')):
            return TaskType.SORT_SOLID
        
        # Assemble/Make Sandwich/制作/堆叠 tasks
        if (task.startswith('Assemble:') or task.startswith('Assemble：') or
            task.startswith('Make Sandwich:') or task.startswith('Make Sandwich：') or
            task.startswith('制作') or task.startswith('堆叠') or 
            task.startswith('assemble') or task.startswith('stack')):
            return TaskType.MAKE_SANDWICH
        
        # Match by keywords
        scores = {}
        for task_type, keywords in self.task_type_keywords.items():
            score = sum(1 for kw in keywords if kw in task_lower)
            if score > 0:
                scores[task_type] = score
        
        if scores:
            return max(scores, key=scores.get)
        
        return TaskType.UNKNOWN
    
    def analyze(self, task: str) -> TaskAnalysis:
        """
        Analyze task
        
        Args:
            task: Task description
            
        Returns:
            TaskAnalysis: Analysis result
        """
        task_lower = task.lower()
        
        # 0. Identify task type
        task_type = self.identify_task_type(task)
        
        # 1. Extract objects
        objects = self._extract_objects(task)
        
        # 2. Extract locations
        locations = self._extract_locations(task)
        
        # 3. Identify required capabilities
        required_capabilities = self._identify_capabilities(task)
        
        # 4. Determine spatial distribution
        is_multi_location = self._check_multi_location(task, locations, len(objects))
        
        # 5. Check time constraints
        has_time_constraint = self._check_time_constraints(task)
        
        # 6. Check collaboration keywords
        collaboration_indicated = self._check_collaboration_keywords(task)
        
        # 7. Calculate complexity factors (DynaHMRC formula)
        # D = αL + βN + γY
        L = self._calculate_location_factor(task, locations, len(objects))  # 位置难度因子
        N = self._calculate_object_quantity_factor(len(objects))  # 物体数量因子
        Y = self._calculate_collaboration_intensity(task, locations, required_capabilities, len(objects), task_type)  # 协作强度因子
        
        # 权重系数
        alpha, beta, gamma = 0.4, 0.2, 0.4
        D = alpha * L + beta * N + gamma * Y
        
        # 8. Determine complexity level based on D value
        complexity = self._determine_complexity(D, collaboration_indicated)
        
        # 9. Determine if collaboration is needed
        collaboration_needed = self._determine_collaboration_need(
            complexity, is_multi_location, collaboration_indicated, task_type
        )
        
        # 10. Determine collaboration type
        collaboration_type = self._determine_collaboration_type(
            required_capabilities, is_multi_location
        )
        
        # 11. Calculate recommended robot count
        min_robots, recommended_robots = self._calculate_robot_count(
            complexity, locations, required_capabilities, collaboration_type
        )
        
        # 12. Estimate steps
        estimated_steps = self._estimate_steps(objects, locations, task_type)
        
        # 13. Break down subtasks
        subtasks = self._breakdown_subtasks(task, task_type, objects, locations)
        
        # 14. Detect dynamic complexity factors (CTO, IRZ, ANC, REC)
        dynamic_factors = self._detect_dynamic_complexity(task)
        
        # 15. Generate reasoning
        reasoning = self._generate_reasoning_with_dvalue(
            task_type, complexity, D, L, N, Y, collaboration_needed, objects, locations,
            required_capabilities, collaboration_type
        )
        
        return TaskAnalysis(
            task=task,
            task_type=task_type,
            complexity=complexity,
            D_value=D,
            collaboration_needed=collaboration_needed,
            min_robots=min_robots,
            recommended_robots=recommended_robots,
            required_capabilities=required_capabilities,
            collaboration_type=collaboration_type,
            estimated_steps=estimated_steps,
            reasoning=reasoning,
            subtasks=subtasks,
            location_factor=L,
            quantity_factor=N,
            collaboration_factor=Y,
            dynamic_complexity=dynamic_factors
        )
    
    def _extract_objects(self, task: str) -> List[str]:
        """Extract objects mentioned in task (English and Chinese)"""
        # Common object list (English and Chinese) - exclude destination containers like tray
        common_objects = [
            # English - Basic objects
            'apple', 'book', 'cup', 'bottle', 'box', 'toy', 'phone', 'keys',
            'block', 'plate', 'fork', 'knife', 'spoon', 'pen', 'bag', 'remote',
            'fruit', 'vegetable', 'tool', 'material', 'waste', 'instrument',
            'bowl', 'dish', 'glass', 'container',
            # English - New objects from examples (packing tasks)
            'toothbrush', 'tableware', 'toiletry', 'toiletries',
            # English - Sandwich ingredients
            'bread', 'cheese', 'lettuce', 'tomato', 'patty', 'egg', 'cucumber',
            # Chinese
            '苹果', '书', '杯子', '瓶子', '盒子', '玩具', '手机', '钥匙',
            '积木', '盘子', '叉子', '刀', '勺子', '笔', '包', '遥控器',
            '水果', '蔬菜', '工具', '材料', '垃圾', '器具',
            '碗', '碟', '玻璃杯', '容器'
        ]
        
        found_objects = []
        task_lower = task.lower()
        
        for obj in common_objects:
            if obj in task_lower:
                found_objects.append(obj)
        
        return found_objects
    
    def _extract_locations(self, task: str) -> List[str]:
        """Extract locations mentioned in task (English and Chinese)"""
        # Furniture patterns only (exclude room names)
        # Use word boundaries to avoid partial matches (e.g., "table" in "tableware")
        furniture_patterns = [
            r'\bcoffee[_\s]*table\b',
            r'\bkitchen[_\s]*table\b',
            r'\bdining[_\s]*table\b',
            r'\btable\s*(\d*)\b',
            r'\bshelf\s*(\d*)\b',
            r'\bbox\s*(\d*)\b',
            r'\bdrawer\s*(\d*)\b',
            r'\bcabinets?\s*(\d*)\b',
            r'\bcountertop\b',
            r'\bwashbasin\b',
            r'\bsofa\b',
            r'\bbookshelf\b',
            r'\brefrigerator\b',
            # Chinese furniture patterns
            r'茶几',
            r'餐桌',
            r'桌子\s*(\d*)',
            r'架子\s*(\d*)',
            r'箱子\s*(\d*)',
            r'抽屉\s*(\d*)',
            r'橱柜\s*(\d*)',
            r'柜子\s*(\d*)',
            r'洗手台',
            r'沙发',
            r'书架',
            r'冰箱',
            r'操作台',
            r'台面',
            r'托盘'
        ]
        
        locations = []
        task_lower = task.lower()
        
        for pattern in furniture_patterns:
            matches = re.finditer(pattern, task_lower)
            for match in matches:
                locations.append(match.group(0))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_locations = []
        for loc in locations:
            if loc not in seen:
                seen.add(loc)
                unique_locations.append(loc)
        
        return unique_locations
    
    def _identify_capabilities(self, task: str) -> List[str]:
        """Identify required capabilities"""
        required = []
        task_lower = task.lower()
        
        for capability, keywords in self.capability_keywords.items():
            if any(kw in task_lower for kw in keywords):
                required.append(capability)
        
        # Remove duplicates and return
        return list(set(required))
    
    def _check_multi_location(self, task: str, locations: List[str], object_count: int = 0) -> bool:
        """Check if task involves multiple locations (English and Chinese)"""
        # Check if multiple location keywords appear
        if len(locations) >= 2:
            return True
        
        # Multiple objects typically mean multiple source locations for collection tasks
        if object_count >= 2:
            return True
        
        # Check for multi-location indicators (English and Chinese)
        task_lower = task.lower()
        multi_location_indicators = [
            'all', 'every', 'each', 'different', 'multi', 'multiple',
            'between', 'and', 'with', 'as well as', 'rooms',
            # Chinese indicators
            '所有', '每个', '各个', '不同', '多', '分散', '散落',
            '和', '与', '以及', '还有', '之间', '以及'
        ]
        location_keywords = [
            'room', 'table', 'area', 'place', 'location',
            # Chinese
            '房间', '桌子', '桌面', '书架', '台面', '地方', '位置'
        ]
        
        for indicator in multi_location_indicators:
            if indicator in task_lower:
                # Check if it indeed indicates multiple locations
                if any(loc in task_lower for loc in location_keywords):
                    return True
        
        return False
    
    def _check_time_constraints(self, task: str) -> bool:
        """Check if task has time constraints"""
        task_lower = task.lower()
        return any(tc in task_lower for tc in self.time_constraints)
    
    def _check_collaboration_keywords(self, task: str) -> bool:
        """Check if task explicitly mentions collaboration"""
        task_lower = task.lower()
        return any(ck in task_lower for ck in self.collaboration_keywords)
    
    def _calculate_location_difficulty(self, task: str, location: str) -> int:
        """
        计算位置难度 l_i (DynaHMRC论文)
        l_i = 0: 物体在桌面上且在操作机器人范围内
        l_i = 1: 物体在桌面上但在操作范围外，需要协作搬运
        l_i = 2: 物体不在桌面上（如在柜子里），需要额外的探索和运输
        """
        task_lower = task.lower()
        location_lower = location.lower()
        
        # 桌面范围内 (最简单)
        table_in_range = ['table', '桌面', '台面', 'countertop']
        if any(kw in location_lower for kw in table_in_range):
            # 检查是否提到"范围内"或没有提到"外"
            if '范围内' in task_lower or '外' not in task_lower:
                return 0
            return 1  # 桌面但在范围外
        
        # 不在桌面上（需要探索）
        non_table_locations = ['cabinet', 'drawer', 'shelf', 'box', 'locker', 'safe',
                              '橱柜', '抽屉', '架子', '箱子', '锁柜', '保险箱', '柜子', '高处']
        if any(kw in location_lower for kw in non_table_locations):
            return 2
        
        # 默认中等难度
        return 1
    
    def _calculate_location_factor(self, task: str, locations: List[str], object_count: int = 0) -> float:
        """
        计算位置难度因子 L (DynaHMRC论文)
        L = 0.8 * max(l_i) + 0.2 * mean(l_i)
        """
        # 过滤掉目标位置（如 tray），只保留源位置
        source_locations = []
        destination_keywords = ['tray', 'box', 'container', 'destination', 'target',
                               '托盘', '盒子', '容器', '目标']
        for loc in locations:
            if not any(dk in loc.lower() for dk in destination_keywords):
                source_locations.append(loc)
        
        # 如果没有提取到源位置（或只有目标位置），根据任务描述和物体数量估算默认位置难度
        if not source_locations:
            # 根据物品数量调整默认位置难度
            # 物品越多，意味着可能分散在更多位置
            if object_count <= 2:
                return 0.25  # 简单任务，1-2个物品，可能在同一位置
            elif object_count == 3:
                return 0.50  # 中等任务，3个物品，可能需要探索2个位置
            elif object_count == 4:
                return 0.65  # 较复杂任务，4个物品，可能需要探索多个位置
            elif object_count == 5:
                return 0.80  # 复杂任务，5个物品，分散在多个位置
            else:
                return 0.90  # 极复杂任务，6+个物品，分散在多个位置，可能包含隐藏区域
        
        # 计算每个位置的难度
        difficulties = [self._calculate_location_difficulty(task, loc) for loc in source_locations]
        
        max_difficulty = max(difficulties)
        mean_difficulty = sum(difficulties) / len(difficulties)
        
        # L = 0.8 * max(l_i) + 0.2 * mean(l_i)
        L = 0.8 * max_difficulty + 0.2 * mean_difficulty
        
        # 归一化到 [0, 1]
        return min(L / 2.0, 1.0)
    
    def _calculate_object_quantity_factor(self, object_count: int) -> float:
        """
        计算物体数量因子 N (DynaHMRC论文)
        N = (J - J_min) / (J_max - J_min)
        其中 J 在 1 到 5 之间，J_min = 1, J_max = 5
        """
        J = max(1, min(object_count, 5))  # 限制在 1-5 范围
        J_min = 1
        J_max = 5
        
        if J_max == J_min:
            return 0.0
        
        N = (J - J_min) / (J_max - J_min)
        return N
    
    def _calculate_collaboration_intensity(self, task: str, locations: List[str], 
                                          capabilities: List[str],
                                          object_count: int = 0,
                                          task_type: TaskType = None) -> float:
        """
        计算协作强度因子 Y (DynaHMRC论文)
        Y = y / Y_max
        其中 y 是额外需要的机器人数量 (0-2)，Y_max = 2
        """
        y = 0  # 基础操作机器人外需要增加的助手数量
        
        task_lower = task.lower()
        
        # 需要无人机 (空中能力)
        aerial_keywords = ['drone', 'fly', 'aerial', 'high', 'above', 'top',
                          '无人机', '飞', '空中', '顶部', '上方', '高处']
        if any(kw in task_lower for kw in aerial_keywords):
            y += 1
        
        # 需要移动机器人 (导航/探索) - 物品数量多时需要协作
        # 简单任务：1-2个物品，不需要额外协作
        # 中等任务：3-4个物品，可能需要协作
        # 复杂任务：5+个物品，需要协作
        if len(locations) >= 3 or 'explore' in task_lower or '探索' in task_lower:
            y += 1
        elif len(locations) >= 2 and object_count >= 4:
            # 2个位置但物品较多（4个及以上），可能需要协作
            y += 1
        
        # 根据物品数量和任务类型增加协作需求
        if object_count >= 7:
            # 7个及以上物品（极复杂任务），需要大量协作
            y += 2
        elif object_count >= 6:
            # 6个物品的分类任务需要高协作
            if task_type == TaskType.SORT_SOLID:
                y += 2
            else:
                y += 1
        elif object_count >= 5:
            # 5个物品的装箱任务需要高协作
            if task_type == TaskType.PACK_OBJECT:
                y += 2
            else:
                y += 1
        elif object_count >= 4 and task_type == TaskType.MAKE_SANDWICH:
            # 4个物品的堆叠任务需要协作（顺序要求高）
            y += 1
        elif object_count >= 3 and task_type == TaskType.PACK_OBJECT:
            # 3个物品的装箱任务需要协作
            y += 1
        
        # 根据位置难度增加协作需求
        if any('cabinet' in loc.lower() for loc in locations):
            # 涉及橱柜/柜子的任务需要协作（需要开关柜门）
            y += 1
        
        # 需要额外协作机器人 - 只有明确提到协作关键词时才触发
        collaboration_keywords = ['coordinate', 'cooperate', 'collaborate', 'multiple robots',
                                 '协调', '配合', '多个机器人', '合作']
        if any(kw in task_lower for kw in collaboration_keywords):
            y = max(y, 1)  # 至少需要一个助手
        
        # Y_max = 2，归一化到 [0, 1]
        Y_max = 2
        return min(y / Y_max, 1.0)
    
    def _calculate_complexity_score(self, objects: List[str], locations: List[str],
                                   capabilities: List[str], is_multi_location: bool,
                                   has_time_constraint: bool, collaboration_indicated: bool,
                                   task: str, task_type: TaskType) -> float:
        """
        计算任务复杂度 D (DynaHMRC论文公式)
        D = αL + βN + γY
        其中: α=0.4 (位置权重), β=0.2 (数量权重), γ=0.4 (协作权重)
        
        Returns: D 值在 [0, 1] 范围
        """
        # 权重系数
        alpha = 0.4  # 位置权重
        beta = 0.2   # 数量权重
        gamma = 0.4  # 协作权重
        
        # 计算三个维度
        L = self._calculate_location_factor(task, locations)  # 位置难度因子
        N = self._calculate_object_quantity_factor(len(objects))  # 物体数量因子
        Y = self._calculate_collaboration_intensity(task, locations, capabilities, len(objects), task_type)  # 协作强度因子
        
        # 核心公式: D = αL + βN + γY
        D = alpha * L + beta * N + gamma * Y
        
        return min(D, 1.0)  # 确保在 [0, 1] 范围内
    
    def _determine_complexity(self, D: float, collaboration_indicated: bool) -> TaskComplexity:
        """
        根据 DynaHMRC 论文确定复杂度等级
        D 值范围 [0, 1]:
        - 简单 (Easy): [0, 0.3] - 物体数量少，大多在可触及范围内，几乎不需要复杂协作
        - 中等 (Medium): (0.3, 0.6] - 物体分布较散，需要一定的探索和基础协作
        - 困难 (Hard): (0.6, 1.0] - 物体多且隐藏在受限区域，必须通过多机紧密配合
        """
        if D <= 0.3:
            return TaskComplexity.SIMPLE
        elif D <= 0.6:
            return TaskComplexity.MODERATE
        elif D <= 0.85:
            return TaskComplexity.COMPLEX
        else:
            return TaskComplexity.VERY_COMPLEX
    
    def _determine_collaboration_need(self, complexity: TaskComplexity,
                                     is_multi_location: bool,
                                     collaboration_indicated: bool,
                                     task_type: TaskType) -> bool:
        """Determine if collaboration is needed"""
        # If explicitly requires collaboration, definitely need collaboration
        if collaboration_indicated:
            return True
        
        # If complexity is very high, definitely need collaboration
        if complexity == TaskComplexity.VERY_COMPLEX:
            return True
        
        # Complex or very complex tasks need collaboration
        if complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
            return True
        
        # Multi-location tasks require collaboration (moderate or above)
        if is_multi_location and complexity in [TaskComplexity.MODERATE, TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]:
            return True
        
        # Assembly tasks usually benefit from collaboration
        if task_type == TaskType.MAKE_SANDWICH:
            return True
        
        # Packing tasks always need collaboration (mobile robot picks up, fixed arm places)
        if task_type == TaskType.PACK_OBJECT:
            return True
        
        return False
    
    def _determine_collaboration_type(self, capabilities: List[str],
                                     is_multi_location: bool) -> CollaborationType:
        """Determine collaboration type"""
        # If diverse capabilities are needed
        if len(capabilities) >= 3:
            return CollaborationType.HETEROGENEOUS
        
        # If multiple locations
        if is_multi_location:
            return CollaborationType.PARALLEL
        
        # Default to sequential
        return CollaborationType.SEQUENTIAL
    
    def _calculate_robot_count(self, complexity: TaskComplexity, locations: List[str],
                              capabilities: List[str],
                              collaboration_type: CollaborationType) -> Tuple[int, int]:
        """Calculate minimum and recommended robot count"""
        base_count = 1
        
        # Adjust based on complexity
        if complexity == TaskComplexity.SIMPLE:
            base_count = 1
        elif complexity == TaskComplexity.MODERATE:
            base_count = 1
        elif complexity == TaskComplexity.COMPLEX:
            base_count = 2
        else:  # VERY_COMPLEX
            base_count = 3
        
        # Adjust based on location count
        loc_count = len(locations)
        if loc_count >= 4:
            base_count = max(base_count, 3)
        elif loc_count >= 2:
            base_count = max(base_count, 2)
        
        # Adjust based on capability diversity
        cap_count = len(capabilities)
        if cap_count >= 4:
            base_count = max(base_count, 3)
        elif cap_count >= 2:
            base_count = max(base_count, 2)
        
        min_robots = base_count
        recommended_robots = min(base_count + 1, 4)  # Max 4 robots
        
        return min_robots, recommended_robots
    
    def _estimate_steps(self, objects: List[str], locations: List[str],
                       task_type: TaskType) -> int:
        """Estimate required steps"""
        obj_count = len(objects) if objects else 1
        loc_count = len(locations) if locations else 1
        
        if task_type == TaskType.PACK_OBJECT:
            return obj_count * loc_count
        elif task_type == TaskType.SORT_SOLID:
            return obj_count * 2  # Pick + place
        elif task_type == TaskType.MAKE_SANDWICH:
            return obj_count * 3  # More complex assembly
        else:
            return obj_count
    
    def _breakdown_subtasks(self, task: str, task_type: TaskType,
                           objects: List[str], locations: List[str]) -> List[Dict]:
        """Break down task into subtasks (Chinese)"""
        subtasks = []
        
        if task_type == TaskType.PACK_OBJECT:
            for obj in objects:
                subtasks.append({
                    'type': 'pick_and_place',
                    'target': obj,
                    'description': f'打包{obj}'
                })
        
        elif task_type == TaskType.SORT_SOLID:
            for obj in objects:
                subtasks.append({
                    'type': 'sort',
                    'target': obj,
                    'description': f'分类{obj}'
                })
        
        elif task_type == TaskType.MAKE_SANDWICH:
            for i, obj in enumerate(objects):
                subtasks.append({
                    'type': 'assemble',
                    'target': obj,
                    'description': f'堆叠第{i+1}层: {obj}'
                })
        
        return subtasks
    
    def _generate_reasoning(self, task_type: TaskComplexity, complexity: TaskComplexity,
                           collaboration_needed: bool, objects: List[str],
                           locations: List[str], capabilities: List[str],
                           collaboration_type: CollaborationType) -> str:
        """Generate reasoning explanation (Chinese)"""
        reasons = []
        
        # Complexity explanation (Chinese)
        if complexity == TaskComplexity.SIMPLE:
            reasons.append("这是一个简单任务")
        elif complexity == TaskComplexity.MODERATE:
            reasons.append("这是一个中等复杂度任务")
        elif complexity == TaskComplexity.COMPLEX:
            reasons.append("这是一个复杂任务")
        else:
            reasons.append("这是一个非常复杂任务")
        
        # Object count (Chinese)
        if objects:
            reasons.append(f"涉及{len(objects)}种物品")
        
        # Location distribution (Chinese)
        if len(locations) > 1:
            reasons.append(f"分布在{len(locations)}个位置")
        
        # Capability requirements (Chinese)
        if capabilities:
            reasons.append(f"需要{len(capabilities)}种能力")
        
        # Collaboration explanation (Chinese)
        collaboration_type_labels = {
            CollaborationType.SEQUENTIAL: "顺序",
            CollaborationType.PARALLEL: "并行",
            CollaborationType.HETEROGENEOUS: "异构",
            CollaborationType.HYBRID: "混合"
        }
        if collaboration_needed:
            collab_label = collaboration_type_labels.get(collaboration_type, collaboration_type.value)
            reasons.append(f"需要{collab_label}协作才能高效完成")
        else:
            reasons.append("单个机器人即可高效完成")
        
        return "。".join(reasons) + "。"
    
    def _detect_dynamic_complexity(self, task: str) -> List[str]:
        """
        检测动态复杂度因子 (CTO, IRZ, ANC, REC)
        - CTO: Change Target (目标变更)
        - IRZ: Introduce Restricted Zone (禁区引入)
        - ANC: Add New member (新成员加入)
        - REC: Remove member (成员移除)
        """
        dynamic_factors = []
        task_lower = task.lower()
        
        for factor, keywords in self.dynamic_complexity_factors.items():
            if any(kw in task_lower for kw in keywords):
                dynamic_factors.append(factor)
        
        return dynamic_factors
    
    def _generate_reasoning_with_dvalue(self, task_type: TaskType, complexity: TaskComplexity,
                                        D: float, L: float, N: float, Y: float,
                                        collaboration_needed: bool, objects: List[str],
                                        locations: List[str], capabilities: List[str],
                                        collaboration_type: CollaborationType) -> str:
        """Generate reasoning with D-value explanation (DynaHMRC)"""
        reasons = []
        
        # Complexity level based on D value
        if complexity == TaskComplexity.SIMPLE:
            reasons.append("这是一个简单任务")
        elif complexity == TaskComplexity.MODERATE:
            reasons.append("这是一个中等复杂度任务")
        elif complexity == TaskComplexity.COMPLEX:
            reasons.append("这是一个复杂任务")
        else:
            reasons.append("这是一个非常困难的任务")
        
        # Add DynaHMRC formula explanation
        reasons.append(f"复杂度评分 D={D:.2f} (位置因子L={L:.2f}, 数量因子N={N:.2f}, 协作因子Y={Y:.2f})")
        
        # Object count
        if objects:
            reasons.append(f"涉及{len(objects)}种物品")
        
        # Location distribution
        if len(locations) > 1:
            reasons.append(f"分布在{len(locations)}个位置")
        
        # Capability requirements
        if capabilities:
            reasons.append(f"需要{len(capabilities)}种能力")
        
        # Collaboration explanation
        collaboration_type_labels = {
            CollaborationType.SEQUENTIAL: "顺序",
            CollaborationType.PARALLEL: "并行",
            CollaborationType.HETEROGENEOUS: "异构",
            CollaborationType.HYBRID: "混合"
        }
        if collaboration_needed:
            collab_label = collaboration_type_labels.get(collaboration_type, "协作")
            reasons.append(f"需要{collab_label}协作才能高效完成")
        else:
            reasons.append("单个机器人即可高效完成")
        
        return "。".join(reasons) + "。"
    
    def format_analysis(self, analysis: TaskAnalysis) -> str:
        """Format analysis result as readable text (Chinese)"""
        # Task type label (Chinese)
        task_type_labels = {
            TaskType.PACK_OBJECT: "📦 打包任务",
            TaskType.SORT_SOLID: "🎨 分类任务",
            TaskType.MAKE_SANDWICH: "🥪 堆叠任务",
            TaskType.UNKNOWN: "❓ 未知类型"
        }
        task_type_label = task_type_labels.get(analysis.task_type, "未知")
        
        # Complexity labels (Chinese)
        complexity_labels = {
            TaskComplexity.SIMPLE: "⭐ 简单",
            TaskComplexity.MODERATE: "⭐⭐ 中等",
            TaskComplexity.COMPLEX: "⭐⭐⭐ 复杂",
            TaskComplexity.VERY_COMPLEX: "⭐⭐⭐⭐ 极复杂"
        }
        complexity_label = complexity_labels.get(analysis.complexity, "未知")
        
        # Collaboration type labels (Chinese)
        collab_type_labels = {
            CollaborationType.SEQUENTIAL: "顺序协作",
            CollaborationType.PARALLEL: "并行协作",
            CollaborationType.HETEROGENEOUS: "异构协作",
            CollaborationType.HYBRID: "混合协作"
        }
        collab_type_label = collab_type_labels.get(analysis.collaboration_type, analysis.collaboration_type.value)
        
        lines = []
        lines.append(f"📋 任务类型: {task_type_label}")
        lines.append(f"📊 复杂度: {complexity_label}")
        lines.append(f"🤝 多机器人协作: {'✅ 需要' if analysis.collaboration_needed else '❌ 不需要（单个机器人可完成）'}")
        
        if analysis.collaboration_needed:
            lines.append(f"   推荐机器人数: {analysis.recommended_robots}个")
            lines.append(f"   协作类型: {collab_type_label}")
        
        if analysis.objects:
            lines.append(f"📦 物品: {', '.join(analysis.objects)}")
        
        if analysis.locations:
            lines.append(f"📍 位置: {', '.join(analysis.locations)}")
        
        if analysis.required_capabilities:
            lines.append(f"🔧 需要能力: {', '.join(analysis.required_capabilities)}")
        
        lines.append(f"📈 估计步骤: {analysis.estimated_steps}步")
        lines.append(f"💡 分析: {analysis.reasoning}")
        
        return "\n".join(lines)
    
    def _get_collab_type_label(self, collab_type: CollaborationType) -> str:
        """Get collaboration type label (Chinese)"""
        labels = {
            CollaborationType.SEQUENTIAL: "顺序协作",
            CollaborationType.PARALLEL: "并行协作",
            CollaborationType.HETEROGENEOUS: "异构协作",
            CollaborationType.HYBRID: "混合协作"
        }
        return labels.get(collab_type, "未知")
    
    def get_recommendation(self, analysis: TaskAnalysis) -> str:
        """Generate recommendation based on analysis (Chinese)"""
        if not analysis.collaboration_needed:
            complexity_labels = {
                TaskComplexity.SIMPLE: "简单",
                TaskComplexity.MODERATE: "中等",
                TaskComplexity.COMPLEX: "复杂",
                TaskComplexity.VERY_COMPLEX: "极复杂"
            }
            complexity_label = complexity_labels.get(analysis.complexity, analysis.complexity.value)
            return f"单个机器人可高效完成这个{complexity_label}任务。"
        
        robot_names = ['Alice', 'Bob', 'David', 'Lucy']
        recommended = robot_names[:analysis.recommended_robots]
        
        collab_type_labels = {
            CollaborationType.SEQUENTIAL: "顺序",
            CollaborationType.PARALLEL: "并行",
            CollaborationType.HETEROGENEOUS: "异构",
            CollaborationType.HYBRID: "混合"
        }
        collab_label = collab_type_labels.get(analysis.collaboration_type, analysis.collaboration_type.value)
        
        return f"推荐使用{analysis.recommended_robots}个机器人（{', '.join(recommended)}）进行{collab_label}协作。"
    
    def _get_complexity_label(self, complexity: TaskComplexity) -> str:
        """Get complexity label (Chinese) - 与前端示例任务弹窗保持一致"""
        labels = {
            TaskComplexity.SIMPLE: "⭐ 简单",
            TaskComplexity.MODERATE: "⭐⭐ 中等",
            TaskComplexity.COMPLEX: "⭐⭐⭐ 复杂",
            TaskComplexity.VERY_COMPLEX: "⭐⭐⭐⭐ 极复杂"
        }
        return labels.get(complexity, "未知")
    
    def get_task_examples(self) -> Dict:
        """Get example tasks organized by type"""
        return TASK_EXAMPLES


# Example task database - organized by three basic task types
# 与前端 chat.html 中的 taskExamples 保持一致
TASK_EXAMPLES = {
    # ========== Pack Objects (Packing) ==========
    # 基本任务：评估机器人的拾取放置能力
    # 目标：从环境中拾取分散的物品并放入指定托盘
    # 挑战：未知环境需要探索；无法到达的区域需要多机器人协作
    'pack_object': {
        'name': '📦 装箱任务',
        'description': '拾取放置：将物品拾取并放入指定的托盘/容器',
        'details': '评估多机器人在拾取放置任务上的协作能力。系统中包含固定机械臂和移动机器人，通过四阶段模型实现自主任务分配与协调。',
        'color': '#4ecdc4',
        'examples': [
            # 简单 - 单一位置，少量物品
            {"task": "装箱：Put \"cup\" and \"toothbrush\" into tray.", "level": "simple", "label": "⭐ 简单"},
            # 中等 - 多个物品，可能需要打开抽屉
            {"task": "装箱：Put \"cup\", \"remote\" and \"tableware\" into tray.", "level": "moderate", "label": "⭐⭐ 中等"},
            # 复杂 - 多位置，需要协作
            {"task": "装箱：Put \"cup\", \"tableware\", \"toiletry\" and \"book\" into tray.", "level": "complex", "label": "⭐⭐⭐ 复杂"},
            # 极复杂
            {"task": "装箱：Put \"cup\", \"tableware\", \"toiletry\", \"book\" and \"fruit\" into tray.", "level": "very_complex", "label": "⭐⭐⭐⭐ 极复杂"}
        ]
    },
    
    # ========== Sort Solids (Sorting) ==========
    # 在基本拾取放置基础上增加颜色分类要求
    # 目标：识别纯色并放置到对应颜色的面板上
    # 挑战：视觉系统必须提取颜色属性并匹配物体到目标位置
    'sort_solid': {
        'name': '🎨 分类任务',
        'description': '分类：按类别将物品分类并放置到指定区域',
        'details': '评估多机器人在分类任务上的协作能力。系统中包含固定机械臂和移动机器人，通过四阶段模型实现自主任务分配与协调。',
        'color': '#95e1d3',
        'examples': [
            # 简单 - 单一位置，少量物品
            {"task": "分类：Sort \"tableware\" and \"cup\" into different trays by category.", "level": "simple", "label": "⭐ 简单"},
            # 中等 - 多个物品，可能需要打开抽屉
            {"task": "分类：Sort \"tableware\", \"cup\", \"fruit\" and \"remote\" into corresponding trays by category.", "level": "moderate", "label": "⭐⭐ 中等"},
            # 复杂 - 多位置，需要协作
            {"task": "分类：Sort \"tableware\", \"book\", \"toiletry\" and \"cup\" into corresponding trays and cabinets by category.", "level": "complex", "label": "⭐⭐⭐ 复杂"},
            # 极复杂
            {"task": "分类：Sort \"cup\", \"tableware\", \"book\", \"toiletry\", \"fruit\" and \"remote\" into designated storage locations by category.", "level": "very_complex", "label": "⭐⭐⭐⭐ 极复杂"}
        ]
    },
    
    # ========== Make Sandwich (Make Sandwich) ==========
    # 最复杂任务：评估顺序堆叠能力
    # 目标：按照食谱在砧板上严格按垂直顺序堆叠食材
    # 挑战：强因果关系、长操作链、食材分布在不同家具中
    'make_sandwich': {
        'name': '🥪 堆叠任务',
        'description': '顺序堆叠：按顺序堆叠食材（从下到上）',
        'details': '评估多机器人在顺序堆叠任务上的协作能力。系统中包含固定机械臂和移动机器人，通过四阶段模型实现自主任务分配与协调。',
        'color': '#ff6b9d',
        'examples': [
            # 简单 - 少量层次，所有物品可见
            {"task": "制作三明治：Stack \"bread\" and \"cheese\" onto the tray in order.", "level": "simple", "label": "⭐ 简单"},
            # 中等 - 更多层次，部分物品在橱柜中
            {"task": "制作三明治：Stack \"bread\", \"lettuce\" and \"cheese\" into sandwich on the countertop.", "level": "moderate", "label": "⭐⭐ 中等"},
            # 复杂 - 多种食材分布在不同位置，需要协调
            {"task": "制作三明治：Stack \"bread\", \"lettuce\", \"tomato\", \"patty\" and \"cheese\" into hamburger on the countertop.", "level": "complex", "label": "⭐⭐⭐ 复杂"},
            # 极复杂
            {"task": "制作三明治：Build multi-layer sandwich tower with \"bread\", \"lettuce\", \"tomato\", \"patty\", \"cheese\", \"egg\" and \"cucumber\".", "level": "very_complex", "label": "⭐⭐⭐⭐ 极复杂"}
        ]
    }
}


# Global analyzer instance
analyzer = TaskAnalyzer()


def analyze_task(task: str) -> TaskAnalysis:
    """Convenience function to analyze a task"""
    return analyzer.analyze(task)


if __name__ == "__main__":
    # Test examples
    test_tasks = [
        "Pack: Put apples from table into box",
        "Sort: Put red blocks to red plate, blue blocks to blue plate",
        "Assemble: Build a bridge, requires stabilizer, assembler, and material handler"
    ]
    
    for task in test_tasks:
        print(f"\n{'='*50}")
        print(f"Task: {task}")
        print('='*50)
        result = analyze_task(task)
        print(analyzer.format_analysis(result))
