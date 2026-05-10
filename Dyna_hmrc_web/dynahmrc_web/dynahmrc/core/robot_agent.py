# dynahmrc/core/robot_agent.py
"""
机器人代理模块
封装单个机器人的决策和通信能力
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import time


@dataclass
class AgentMessage:
    """代理间消息"""
    sender_id: str
    receiver_id: Optional[str]  # None 表示广播
    message_type: str
    content: Dict[str, Any]
    timestamp: float = 0.0
    
    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class RobotAgent:
    """
    机器人代理
    负责单个机器人的局部决策和与其他代理的协调
    """
    
    def __init__(self, robot_id: str, robot_instance: Any, llm_client: Optional[Any] = None):
        self.robot_id = robot_id
        self.robot = robot_instance
        self.llm_client = llm_client
        self.message_queue: List[AgentMessage] = []
        self.neighbors: Dict[str, 'RobotAgent'] = {}  # 邻居代理
        self.local_plan: Optional[Dict] = None
        self.beliefs: Dict[str, Any] = {}  # 对环境的信念
        self.intentions: List[str] = []  # 当前意图
        self.message_handlers: Dict[str, Callable] = {}
        
        # 注册默认消息处理器
        self._register_default_handlers()
    
    def _register_default_handlers(self):
        """注册默认消息处理器"""
        self.message_handlers['task_proposal'] = self._handle_task_proposal
        self.message_handlers['task_accept'] = self._handle_task_accept
        self.message_handlers['task_reject'] = self._handle_task_reject
        self.message_handlers['help_request'] = self._handle_help_request
        self.message_handlers['status_update'] = self._handle_status_update
        self.message_handlers['plan_update'] = self._handle_plan_update
    
    def perceive(self, environment_state: Dict[str, Any]):
        """感知环境更新信念"""
        self.beliefs.update(environment_state)
        
        # 更新自身状态
        if self.robot:
            robot_state = self.robot.get_state()
            self.beliefs['self'] = {
                'position': robot_state.position,
                'battery': robot_state.battery_level,
                'is_busy': robot_state.is_busy,
                'capabilities': robot_state.capabilities
            }
    
    def deliberate(self) -> List[str]:
        """
        决策过程 (BDI模型)
        根据信念生成意图
        """
        new_intentions = []
        
        # 检查是否需要充电
        if self.beliefs.get('self', {}).get('battery', 100) < 20:
            new_intentions.append('recharge')
        
        # 检查是否有新任务
        pending_tasks = self.beliefs.get('pending_tasks', [])
        if pending_tasks and not self.beliefs.get('self', {}).get('is_busy'):
            # 评估是否接受任务
            best_task = self._evaluate_tasks(pending_tasks)
            if best_task:
                new_intentions.append(f'execute_task:{best_task}')
        
        self.intentions = new_intentions
        return new_intentions
    
    def plan(self) -> Optional[Dict]:
        """
        为当前意图生成执行计划
        可以使用 LLM 进行规划
        """
        if not self.intentions:
            return None
        
        intention = self.intentions[0]
        
        # 使用 LLM 生成计划
        if self.llm_client and 'execute_task' in intention:
            task_id = intention.split(':')[1]
            prompt = self._build_planning_prompt(task_id)
            try:
                response = self.llm_client.generate(prompt)
                self.local_plan = self._parse_plan(response)
                return self.local_plan
            except Exception as e:
                print(f"[RobotAgent {self.robot_id}] 规划失败: {e}")
                return self._create_default_plan(intention)
        
        return self._create_default_plan(intention)
    
    def execute(self) -> bool:
        """执行当前计划"""
        if not self.local_plan or not self.robot:
            return False
        
        steps = self.local_plan.get('steps', [])
        for step in steps:
            success = self._execute_step(step)
            if not success:
                return False
        
        return True
    
    def send_message(self, receiver_id: Optional[str], msg_type: str, content: Dict):
        """发送消息给其他代理"""
        msg = AgentMessage(
            sender_id=self.robot_id,
            receiver_id=receiver_id,
            message_type=msg_type,
            content=content
        )
        
        if receiver_id is None:
            # 广播
            for agent in self.neighbors.values():
                agent.receive_message(msg)
        else:
            # 单播
            if receiver_id in self.neighbors:
                self.neighbors[receiver_id].receive_message(msg)
    
    def receive_message(self, message: AgentMessage):
        """接收消息"""
        self.message_queue.append(message)
        
        # 立即处理或加入待处理队列
        handler = self.message_handlers.get(message.message_type)
        if handler:
            handler(message)
    
    def process_messages(self):
        """处理所有待处理消息"""
        while self.message_queue:
            msg = self.message_queue.pop(0)
            handler = self.message_handlers.get(msg.message_type)
            if handler:
                handler(msg)
    
    def negotiate_task(self, task: Dict, candidates: List[str]) -> Optional[str]:
        """
        协商任务分配 (合同网协议 Contract Net Protocol)
        
        Returns:
            选中的机器人ID
        """
        if not candidates:
            return None
        
        # 广播任务提议
        self.send_message(None, 'task_proposal', {
            'task': task,
            'sender': self.robot_id
        })
        
        # 收集投标（简化版，实际应该等待响应）
        bids = []
        for candidate_id in candidates:
            if candidate_id == self.robot_id:
                bid = self._evaluate_task_bid(task)
                bids.append((candidate_id, bid))
            elif candidate_id in self.neighbors:
                # 请求邻居投标
                pass  # 实际实现需要异步等待
        
        # 选择最优投标
        if bids:
            best = max(bids, key=lambda x: x[1])
            return best[0]
        
        return None
    
    def _evaluate_tasks(self, tasks: List[Dict]) -> Optional[str]:
        """评估任务，返回最优任务ID"""
        best_task = None
        best_score = -float('inf')
        
        for task in tasks:
            score = self._calculate_task_score(task)
            if score > best_score:
                best_score = score
                best_task = task.get('task_id')
        
        return best_task
    
    def _calculate_task_score(self, task: Dict) -> float:
        """计算任务评分"""
        score = 100.0
        
        # 能力匹配
        required_caps = set(task.get('required_capabilities', []))
        my_caps = set(self.beliefs.get('self', {}).get('capabilities', []))
        match_ratio = len(required_caps & my_caps) / len(required_caps) if required_caps else 0
        score += match_ratio * 100
        
        # 距离惩罚
        task_pos = task.get('position')
        my_pos = self.beliefs.get('self', {}).get('position')
        if task_pos and my_pos:
            distance = ((task_pos[0] - my_pos[0])**2 + 
                       (task_pos[1] - my_pos[1])**2)**0.5
            score -= distance * 10
        
        # 当前负载
        if self.beliefs.get('self', {}).get('is_busy'):
            score -= 50
        
        return score
    
    def _evaluate_task_bid(self, task: Dict) -> float:
        """评估任务投标价（越低越好）"""
        return -self._calculate_task_score(task)  # 取反，因为投标价越低越好
    
    def _build_planning_prompt(self, task_id: str) -> str:
        """构建规划提示词"""
        return f"""机器人 {self.robot_id} 需要执行任务 {task_id}。
当前状态: {self.beliefs.get('self', {})}
请生成详细的执行步骤。"""
    
    def _parse_plan(self, response: str) -> Dict:
        """解析 LLM 返回的计划"""
        # 简化实现
        return {
            'steps': [
                {'type': 'navigate', 'target': 'task_location'},
                {'type': 'execute', 'action': 'perform_task'},
                {'type': 'verify', 'condition': 'task_complete'}
            ]
        }
    
    def _create_default_plan(self, intention: str) -> Dict:
        """创建默认计划"""
        return {
            'steps': [{'type': 'execute', 'action': intention}]
        }
    
    def _execute_step(self, step: Dict) -> bool:
        """执行单个步骤"""
        step_type = step.get('type')
        
        if step_type == 'navigate':
            # 模拟导航
            time.sleep(0.5)
            return True
        elif step_type == 'execute':
            # 实际执行
            if self.robot:
                return self.robot.execute_task(step)
            return True
        elif step_type == 'verify':
            # 验证结果
            return True
        
        return False
    
    # 消息处理器
    def _handle_task_proposal(self, msg: AgentMessage):
        """处理任务提议"""
        task = msg.content.get('task')
        if task:
            score = self._calculate_task_score(task)
            # 发送投标
            self.send_message(msg.sender_id, 'task_bid', {
                'task_id': task.get('task_id'),
                'bid_score': score
            })
    
    def _handle_task_accept(self, msg: AgentMessage):
        """处理任务接受确认"""
        print(f"[RobotAgent {self.robot_id}] 任务被接受")
    
    def _handle_task_reject(self, msg: AgentMessage):
        """处理任务拒绝"""
        print(f"[RobotAgent {self.robot_id}] 任务被拒绝")
    
    def _handle_help_request(self, msg: AgentMessage):
        """处理求助请求"""
        # 评估是否提供帮助
        if not self.beliefs.get('self', {}).get('is_busy'):
            self.send_message(msg.sender_id, 'help_offer', {
                'helper_id': self.robot_id
            })
    
    def _handle_status_update(self, msg: AgentMessage):
        """处理状态更新"""
        # 更新对邻居的信念
        neighbor_id = msg.sender_id
        self.beliefs[f'agent_{neighbor_id}'] = msg.content
    
    def _handle_plan_update(self, msg: AgentMessage):
        """处理计划更新"""
        # 协调局部计划
        pass
    
    def add_neighbor(self, agent: 'RobotAgent'):
        """添加邻居代理"""
        self.neighbors[agent.robot_id] = agent
    
    def get_status(self) -> Dict[str, Any]:
        """获取代理状态"""
        return {
            'robot_id': self.robot_id,
            'intentions': self.intentions,
            'beliefs_summary': list(self.beliefs.keys()),
            'message_queue_size': len(self.message_queue),
            'neighbors': list(self.neighbors.keys()),
            'has_plan': self.local_plan is not None
        }