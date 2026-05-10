# dynahmrc/utils/llm_api.py
import os
import time
import json
import logging
from typing import List, Dict, Optional, Any, Callable
from abc import ABC, abstractmethod
from openai import OpenAI, RateLimitError, APIError, AuthenticationError, APITimeoutError
import httpx

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """LLM 客户端抽象基类"""
    
    @abstractmethod
    def complete(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """发送对话请求并获取回复"""
        pass
    
    @abstractmethod
    def stream_complete(self, messages: List[Dict[str, str]], **kwargs):
        """流式获取回复"""
        pass


class KimiLLMClient(BaseLLMClient):
    """
    Kimi (Moonshot AI) API 客户端
    使用 OpenAI 兼容接口调用 Kimi 模型
    """
    
    # 支持的模型列表
    AVAILABLE_MODELS = {
        "deepseek-v4-pro": "deepseek-v4-pro",           # 最新旗舰模型，支持超长上下文
        "kimi-k2": "kimi-k2-0711-preview",  # K2 预览版
        "kimi-128k": "moonshot-v1-128k",    # 128K 上下文
        "kimi-32k": "moonshot-v1-32k",      # 32K 上下文
        "kimi-8k": "moonshot-v1-8k",        # 8K 上下文
    }
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "deepseek-v4-pro",
        base_url: str = "https://api.deepseek.com",
        temperature: float = 0.3,
        max_tokens: int = 10000,
        system_prompt: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 60.0
    ):
        """
        初始化 Kimi 客户端
        
        Args:
            api_key: Moonshot API Key，默认从环境变量 MOONSHOT_API_KEY 读取
            model: 模型名称，支持 "kimi-k2.5", "kimi-k2", "kimi-128k", "kimi-32k", "kimi-8k"
            base_url: API 基础地址
            temperature: 采样温度 (0-1)，越低越确定，越高越随机
            max_tokens: 最大生成 token 数
            system_prompt: 系统提示词
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            timeout: API 调用超时时间（秒）
        """
        self.api_key = api_key or os.getenv("MOONSHOT_API_KEY")
        if not self.api_key:
            raise ValueError("必须提供 api_key 或设置 MOONSHOT_API_KEY 环境变量")
        
        # 解析模型名称
        self.model = self.AVAILABLE_MODELS.get(model, model)
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or self._default_system_prompt()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        
        # 初始化 OpenAI 客户端，设置超时
        http_client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=http_client
        )
        
        # 对话历史（用于多轮对话）
        self.conversation_history: List[Dict[str, str]] = []
        

    
    def _default_system_prompt(self) -> str:
        """Default system prompt (optimized for robot task planning)"""
        return """You are an expert in heterogeneous multi-robot collaborative task planning.

Your responsibilities:
1. Analyze complex tasks and decompose them into subtasks
2. Assign appropriate subtasks to each robot
3. Plan task execution order and collaboration strategies
4. Handle exceptions and conflicts during execution

You need to consider:
- Heterogeneous robot capabilities (mobility, manipulation, perception, etc.)
- Task priorities and dependencies
- Path planning and collision avoidance
- Communication and synchronization mechanisms

Please provide structured, executable planning solutions."""
    
    def complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        发送对话请求并获取完整回复
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}, ...]
            temperature: 覆盖默认温度
            max_tokens: 覆盖默认最大 token 数
            tools: 工具函数定义（用于 Function Calling）
            tool_choice: 工具选择策略
        
        Returns:
            模型生成的文本回复
        """
        # 构建完整消息列表
        full_messages = [{"role": "system", "content": self.system_prompt}]
        full_messages.extend(messages)
        
        # 合并参数
        params = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            **kwargs
        }
        
        # 添加工具相关参数
        if tools:
            params["tools"] = tools
        if tool_choice:
            params["tool_choice"] = tool_choice
        
        # 记录API调用请求
        logger.info(f"[KIMI API CALL] Model: {self.model}, Messages: {len(full_messages)}, Attempt: 1/{self.max_retries}")
        logger.debug(f"[KIMI API REQUEST] Params: {json.dumps(params, ensure_ascii=False, indent=2)[:500]}...")
        
        # 重试机制
        for attempt in range(self.max_retries):
            try:
                logger.info(f"[KIMI API ATTEMPT {attempt + 1}/{self.max_retries}] Sending request...")
                start_time = time.time()
                
                response = self.client.chat.completions.create(**params)
                
                elapsed_time = time.time() - start_time
                logger.info(f"[KIMI API SUCCESS] Response received in {elapsed_time:.2f}s")
                
                # 检查是否有工具调用
                if response.choices[0].message.tool_calls:
                    logger.info(f"[KIMI API] Tool calls detected: {len(response.choices[0].message.tool_calls)} calls")
                    return self._handle_tool_calls(response, messages, **kwargs)
                
                message = response.choices[0].message
                finish_reason = response.choices[0].finish_reason
                content = message.content or ""
                
                logger.info(f"[KIMI API RESPONSE] Finish reason: {finish_reason}, Content length: {len(content)}")
                
                # 如果 content 为空或被截断，尝试获取 reasoning_content
                if hasattr(message, 'reasoning_content') and message.reasoning_content:
                    if not content or finish_reason == 'length':
                        logger.info(f"[KIMI API] Content empty or truncated, extracting from reasoning_content")
                        # 从 reasoning_content 中提取 Thought 和 Description
                        content = self._extract_from_reasoning(message.reasoning_content, content)
                
                logger.info(f"[KIMI API COMPLETE] Returning content ({len(content)} chars)")
                return content
                
            except RateLimitError as e:
                logger.warning(f"[KIMI API RATE LIMIT] Attempt {attempt + 1}: {str(e)}")
                time.sleep(self.retry_delay * (attempt + 1))
                continue
                
            except AuthenticationError as e:
                logger.error(f"[KIMI API AUTH ERROR] Invalid API key or authentication failed: {str(e)}")
                raise
            
            except APITimeoutError as e:
                logger.error(f"[KIMI API TIMEOUT] Attempt {attempt + 1}: Request timed out after {self.timeout}s")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise Exception(f"API 调用超时 ({self.timeout}秒)，请检查网络连接或稍后重试")
                
            except APIError as e:
                logger.error(f"[KIMI API ERROR] Attempt {attempt + 1}: {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                raise
            except Exception as e:
                logger.error(f"[KIMI API UNEXPECTED ERROR] Attempt {attempt + 1}: {type(e).__name__}: {str(e)}")
                raise
        
        logger.error("[KIMI API FAILED] 达到最大重试次数，请求失败")
        raise Exception("达到最大重试次数，请求失败")
    
    def _extract_from_reasoning(self, reasoning: str, partial_content: str = "") -> str:
        """从 reasoning_content 中提取格式化的响应"""
        # 尝试从 reasoning 中提取 Thought 和 Description
        # 通常 reasoning 包含模型的思考过程，我们需要格式化它
        
        lines = reasoning.strip().split('\n')
        
        # 查找包含 "Thought:" 和 "Description:" 的部分
        thought_start = -1
        description_start = -1
        
        for i, line in enumerate(lines):
            if 'Thought:' in line or 'thought:' in line.lower():
                thought_start = i
            if 'Description:' in line or 'description:' in line.lower():
                description_start = i
        
        # 如果找到了标记，提取相应部分
        if thought_start >= 0 and description_start > thought_start:
            thought_lines = []
            description_lines = []
            
            for i in range(thought_start, description_start):
                thought_lines.append(lines[i])
            
            for i in range(description_start, len(lines)):
                description_lines.append(lines[i])
            
            return '\n'.join(thought_lines + description_lines)
        
        # 如果没有找到标记，但有 partial_content，尝试结合两者
        if partial_content and 'Thought:' in partial_content:
            # 从 reasoning 中提取描述
            # 查找 "Description:" 或最后几句话作为描述
            desc = "I am ready to help with this task."
            for line in lines:
                if 'description' in line.lower() or 'introduce' in line.lower():
                    desc = line.strip()
                    break
            return f"{partial_content}\nDescription: {desc}"
        
        # 如果没有找到标记，返回整个 reasoning 作为 Thought
        return f"Thought: {reasoning[:500]}...\nDescription: I am ready to help with this task."
    
    def _handle_tool_calls(
        self,
        response,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """处理工具调用（Function Calling）"""
        message = response.choices[0].message
        tool_calls = message.tool_calls
        
        # 构建包含工具调用的消息
        messages.append({
            "role": "assistant",
            "content": message.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                } for tc in tool_calls
            ]
        })
        
        # 这里应该执行实际的工具函数
        # 简化处理：返回工具调用信息
        tool_results = []
        for tc in tool_calls:
            tool_results.append(f"工具调用: {tc.function.name}({tc.function.arguments})")
        
        return f"需要执行工具:\n" + "\n".join(tool_results)
    
    def stream_complete(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        流式获取回复（逐字返回）
        
        Yields:
            每个 chunk 的内容片段
        """
        full_messages = [{"role": "system", "content": self.system_prompt}]
        full_messages.extend(messages)
        
        params = {
            "model": self.model,
            "messages": full_messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": True,
            **kwargs
        }
        
        try:
            stream = self.client.chat.completions.create(**params)
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:

            raise
    
    def chat(self, user_message: str, keep_history: bool = True) -> str:
        """
        简单的单轮/多轮对话接口
        
        Args:
            user_message: 用户输入
            keep_history: 是否保留对话历史
        
        Returns:
            模型回复
        """
        messages = [{"role": "user", "content": user_message}]
        
        if keep_history and self.conversation_history:
            messages = self.conversation_history + messages
        
        response = self.complete(messages)
        
        if keep_history:
            self.conversation_history.extend([
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response}
            ])
        
        return response
    
    def clear_history(self):
        """清空对话历史"""
        self.conversation_history = []

    
    def set_system_prompt(self, prompt: str):
        """动态修改系统提示词"""
        self.system_prompt = prompt

    
    def generate(self, prompt: str, **kwargs) -> str:
        """
        兼容 SimpleQA 的接口（与 MockLLMClient 保持一致）
        
        Args:
            prompt: 输入提示
            **kwargs: 其他参数
        
        Returns:
            生成的文本
        """
        messages = [{"role": "user", "content": prompt}]
        return self.complete(messages, **kwargs)
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """获取使用统计（如果有）"""
        # Kimi API 目前不直接返回 usage 统计，这里预留接口
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }


# 保留 MockLLMClient 用于测试
class MockLLMClient(BaseLLMClient):
    """模拟 LLM 客户端（用于无网络/API Key 时的测试）"""
    
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self._cache = {}  # 缓存每个机器人的自我介绍，确保一致性
    
    def _extract_robot_name(self, content: str) -> str:
        """从 prompt 中提取机器人名字"""
        import re
        # 匹配 "named Alice" 或 "robot named Alice"
        name_match = re.search(r'named\s+(\w+)', content, re.IGNORECASE)
        if name_match:
            return name_match.group(1)
        # 备选1：匹配 "You are Alice"（但不是 "You are an"）
        name_match = re.search(r'You are\s+([A-Z][a-z]+)\b(?!\s+(?:an?|the|in|on|at|to))', content)
        if name_match:
            return name_match.group(1)
        # 备选2：匹配 "Robot Alice" 或 "robot Alice"
        name_match = re.search(r'[Rr]obot\s+(\w+)\b', content)
        if name_match:
            return name_match.group(1)
        # 备选3：匹配 "I am Alice" 或 "I'm Alice"
        name_match = re.search(r"I(?:'m| am)\s+(\w+)\b", content, re.IGNORECASE)
        if name_match:
            return name_match.group(1)
        # 备选4：直接查找已知机器人名字（Alice, Bob, David, Lucy）
        known_names = ['Alice', 'Bob', 'David', 'Lucy']
        for name in known_names:
            if re.search(r'\b' + name + r'\b', content):
                return name
        return "Robot"
    
    def _get_cached_or_new(self, key: str, generator_func) -> str:
        """获取缓存内容或生成新内容"""
        if key not in self._cache:
            self._cache[key] = generator_func()
        return self._cache[key]
    
    def complete(self, messages: List[Dict[str, str]], **kwargs) -> str:
        time.sleep(self.delay)
        
        # 获取 prompt 内容
        content = messages[-1].get("content", "") if messages else ""
        content_lower = content.lower()
        
        # 调试输出 - 打印前200个字符用于诊断
        print(f"[MOCK DEBUG] Content preview: {content[:200]}...")
        print(f"[MOCK DEBUG] Lowercase preview: {content_lower[:200]}...")
        
        # 提取机器人名字（用于所有阶段）
        name = self._extract_robot_name(content)
        print(f"[MOCK DEBUG] Extracted name: {name}")
        
        # ===== Stage 1: Self-Description =====
        if "introduce yourself" in content_lower:
            # 根据机器人类型生成不同的自我介绍
            robot_type = "Mobile Manipulation Robot" if name == "Alice" else \
                        "Manipulation Robot" if name == "Bob" else \
                        "Mobile Robot" if name == "David" else \
                        "Drone Robot" if name == "Lucy" else "Robot"
            
            unique_strength = "navigate and manipulate objects" if name == "Alice" else \
                             "perform precise manipulation" if name == "Bob" else \
                             "explore the environment quickly" if name == "David" else \
                             "access elevated areas from the air" if name == "Lucy" else "assist the team"
            
            return f"""Thoughts: I need to analyze my capabilities and how they contribute to the team. As a {robot_type}, my unique strengths include the ability to {unique_strength}. This will help the team complete the task efficiently.

Contents: Hello team! I'm {name}, a {robot_type}. I can {unique_strength} and I'm ready to contribute my unique capabilities to help us succeed."""
        
        # ===== Stage 2: Task Allocation (优先级高，先于 Reflection) =====
        # Prompt 中使用的是 "second step of collaboration" 和 "Campaign Speech"
        has_second_step = "second step" in content_lower
        has_task_allocation = "task allocation" in content_lower
        has_campaign = "campaign" in content_lower
        print(f"[MOCK DEBUG] Stage 2 check: second_step={has_second_step}, task_allocation={has_task_allocation}, campaign={has_campaign}")
        if (has_second_step or has_task_allocation) and has_campaign:
            # 根据机器人名字生成不同的计划（单行格式，便于解析）
            if name == "Alice":
                plan_text = "My Role: Lead the task coordination and execute primary operations. Navigate to furniture locations and open containers. Pick up objects and transport them to Bob. Coordinate with David for object discovery. Support Lucy if ground access to high areas is needed."
                strengths = "I can both navigate and manipulate, making me the most versatile team member for this task"
            elif name == "Bob":
                plan_text = "My Role: Handle final placement operations. Wait for Alice to transport objects within my reach. Pick up objects and place them precisely into the tray. Communicate when I need specific objects or assistance. Support quality control for proper placement."
                strengths = "My stable base and high-precision manipulation make me ideal for the critical final placement task"
            elif name == "David":
                plan_text = "My Role: Lead environmental exploration. Systematically visit all furniture locations. Report object locations and container states to the team. Request Alice to open containers for inspection. Maintain an updated map of discovered objects."
                strengths = "My mobility and speed make me the best choice for rapid environmental exploration and object discovery"
            elif name == "Lucy":
                plan_text = "My Role: Access elevated and hard-to-reach areas. Fly to check high shelves, cabinet tops, and elevated surfaces. Transport lightweight objects from high areas. Provide aerial overview of the environment. Support David in locating objects from above."
                strengths = "My aerial capabilities allow me to access areas completely inaccessible to ground robots"
            else:
                plan_text = "My Role: Support the team with my capabilities. Execute tasks as assigned by the leader. Communicate progress and issues promptly."
                strengths = "I'm ready to contribute my unique capabilities to the team"
            
            return f"""Thoughts: I need to analyze the team capabilities, task requirements, and optimal division of labor. Looking at the self-introductions, we have diverse capabilities: Alice can navigate and manipulate, Bob is good at precise manipulation, David can explore, and Lucy can access high areas. The task requires finding objects and placing them in the tray, which requires a coordinated effort.

Collaboration Plan: {plan_text}

Campaign Speech: Hi team, I'm {name}. {strengths}. I can effectively coordinate our efforts to work in parallel, minimize dependencies, and complete this task efficiently. Vote for me!"""
        
        # ===== Stage 3: Leader Election =====
        # 注意：Prompt 中使用的是 "third step of collaboration" 和 "elect a leader"
        if "third step" in content_lower or "elect a leader" in content_lower or "leader election instructions" in content_lower:
            return f"""Thoughts: I need to analyze each candidate's plan, speech, and suitability for leadership. Looking at the proposals, Alice has demonstrated a comprehensive understanding of the task requirements and proposed an efficient collaboration plan that leverages each robot's unique capabilities. Her plan enables parallel work and minimizes dependencies.

Reasons: Based on the evaluation criteria, Alice shows strong capability alignment for coordination, high-quality plan design, clear communication, and fair task allocation. Her plan considers the spatial distribution of objects and assigns tasks based on each robot's strengths.

Leader: Alice

Confidence: High - Alice's plan is well-structured, comprehensive, and considers all team members' capabilities effectively."""
        
        # ===== Stage 4: Execution =====
        if "next action" in content_lower or "execute" in content_lower or "current situation" in content_lower:
            # 根据机器人类型返回不同的默认动作
            if name == "Alice":
                return f"""Thoughts: Based on the current scene graph and task status, I need to navigate to potential object locations. The tray is at position [0.5,0.5,0.8] and table_0 has stand poses available. I should start by navigating to explore locations where objects might be found.

Contents: [navigate](table_0, stand_pose_0)"""
            elif name == "Bob":
                return f"""Thoughts: I'm waiting for Alice to transport objects to me. Since my base is fixed, I should wait until objects are within my reach before attempting to pick and place them.

Contents: [wait]()"""
            elif name == "David":
                return f"""Thoughts: I should systematically explore the environment to locate target objects. The cabinet is at [2.0,0.5,0.0] and might contain objects. I'll navigate there to check.

Contents: [navigate](cabinet, stand_pose_0)"""
            elif name == "Lucy":
                return f"""Thoughts: I should check elevated areas that ground robots cannot access. I'll fly to get an aerial view of the room to locate any objects on high shelves or cabinets.

Contents: [navigate](cabinet, stand_pose_0)"""
            else:
                return f"""Thoughts: Based on the current task status and my capabilities, I should wait for further instructions.

Contents: [wait]()"""
        
        # ===== Stage 5: Reflection (放在最后，避免与其他阶段冲突) =====
        if "reflection" in content_lower or ("group discussion" in content_lower) or ("summary" in content_lower and "plan" in content_lower):
            return f"""Thoughts: Let me analyze what has been accomplished so far, what successful strategies were used, what failures occurred, and what obstacles remain. We've started the task with initial navigation actions. No major failures yet, but we need to improve coordination to avoid redundant exploration.

Summaries:
- Successes: Team successfully initialized and began exploration. Each robot understood their role. Communication channels are open.
- Failures: No significant failures yet, but exploration could be more coordinated to avoid overlap.
- Coordination Assessment: Initial coordination is good, but we need better task allocation to prevent multiple robots checking the same locations.

Plans:
- My proposed next subtasks: Continue systematic exploration, focusing on assigned areas
- Suggested team strategy: Assign specific furniture locations to each robot to avoid redundant exploration
- Requests: None at this time"""
        
        # 默认响应
        return f"Thought: Processing task requirements.\nDescription: {name} is ready to assist."
    
    def stream_complete(self, messages: List[Dict[str, str]], **kwargs):
        """模拟流式输出"""
        response = self.complete(messages, **kwargs)
        for char in response:
            time.sleep(0.01)
            yield char
    
    def generate(self, prompt: str, **kwargs) -> str:
        """兼容接口 - 复用 complete 方法的逻辑"""
        # 将 prompt 包装成 messages 格式，调用 complete 方法
        messages = [{"role": "user", "content": prompt}]
        return self.complete(messages, **kwargs)


# 工厂函数
def create_llm_client(
    client_type: str = "deepseek",
    api_key: Optional[str] = None,
    model: str = "deepseek-v4-pro",
    **kwargs
) -> BaseLLMClient:
    """
    创建 LLM 客户端的工厂函数
    
    Args:
        client_type: "deepseek" 或 "mock"
        api_key: API Key（Deepseek 需要）
        model: 模型名称
        **kwargs: 其他配置参数
    
    Returns:
        LLM 客户端实例
    """
    if client_type == "kimi":
        return KimiLLMClient(api_key=api_key, model=model, **kwargs)
    elif client_type == "mock":
        return MockLLMClient(**kwargs)
    else:
        raise ValueError(f"不支持的客户端类型: {client_type}")


# 使用示例
if __name__ == "__main__":
    # 测试 Kimi 客户端
    try:
        client = KimiLLMClient(
            api_key=os.getenv("MOONSHOT_API_KEY"),
            model="deepseek-v4-pro",
            temperature=1.0
        )
        
        # 简单对话测试
        response = client.chat("你好，请介绍一下自己")

        
        # Task planning test
        task_prompt = """
Current scene has two robots:
- robot1: Mobile robot, good at navigation
- robot2: Manipulator robot, good at grasping

Task: Move the cup from the table to the cabinet.
Please provide a collaboration plan.
"""
        plan = client.chat(task_prompt)

        
    except Exception as e:

        
        mock_client = MockLLMClient()
        response = mock_client.chat("测试消息")
