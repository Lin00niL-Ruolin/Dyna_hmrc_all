# DynaHMRC 聊天式UI API 文档

## 概述

本文档描述了 DynaHMRC 多机器人协作系统的聊天式UI与后端的接口规范。

## 页面访问

- 原UI: `http://localhost:5000/`
- 新聊天式UI: `http://localhost:5000/chat`

## WebSocket / SSE 事件格式

### 连接方式

使用 Server-Sent Events (SSE) 进行流式通信：

```javascript
const response = await fetch('/api/execute/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task: "任务描述" })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const text = decoder.decode(value);
    // 解析 SSE 事件
}
```

### SSE 事件格式

```
event: <event_type>
data: <json_data>

```

## 事件类型

### 1. start - 任务开始

```json
{
    "event": "start",
    "data": {
        "message": "开始执行任务: Pack Objects",
        "timestamp": "10:23:00"
    }
}
```

### 2. phase - 阶段切换

```json
{
    "event": "phase",
    "data": {
        "phase": "self-description",
        "message": "机器人自我介绍..."
    }
}
```

阶段值：
- `self-description` - 自我介绍阶段
- `task-allocation` - 任务分配阶段
- `leader-election` - 领导者选举阶段
- `execution` - 执行阶段
- `reflection` - 反思阶段

### 3. robot_message - 机器人消息

这是核心事件类型，包含机器人的思考、动作和状态。

```json
{
    "event": "robot_message",
    "data": {
        "robot_id": "Alice",
        "robot_type": "MobileManipulation",
        "avatar": "🚗",
        "thought": "Hi team! I'm Alice...",
        "action": "navigate(table_0, stand_pose_0)",
        "action_status": "success",
        "is_leader": true,
        "is_reflection": false,
        "reply_to": "Bob",
        "reply_text": "I'll help you",
        "full_prompt": "...",
        "full_response": "...",
        "timestamp": "10:23:15",
        "thinking_time": 1.2
    }
}
```

字段说明：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| robot_id | string | 是 | 机器人ID: Alice/Bob/Lucy |
| robot_type | string | 否 | 机器人类型 |
| avatar | string | 否 | 头像emoji |
| thought | string | 否 | 思考内容(CoT) |
| action | string | 否 | 执行的动作 |
| action_status | string | 否 | 动作状态: pending/success/error |
| is_leader | boolean | 否 | 是否为领导者 |
| is_reflection | boolean | 否 | 是否为反思阶段消息 |
| reply_to | string | 否 | 回复给哪个机器人 |
| reply_text | string | 否 | 回复引用的内容 |
| full_prompt | string | 否 | 完整LLM Prompt |
| full_response | string | 否 | 完整LLM Response |
| timestamp | string | 否 | 时间戳 |
| thinking_time | number | 否 | 思考耗时(秒) |

### 4. task_progress - 任务进度

```json
{
    "event": "task_progress",
    "data": {
        "completed_objects": ["apple", "book"],
        "remaining_objects": ["fork", "cup", "pen"]
    }
}
```

### 5. complete - 任务完成

```json
{
    "event": "complete",
    "data": {
        "message": "所有任务执行完成",
        "total_tasks": 5,
        "timestamp": "10:25:30"
    }
}
```

### 6. error - 错误

```json
{
    "event": "error",
    "data": {
        "error": "详细错误信息",
        "message": "执行过程中发生错误"
    }
}
```

## 机器人配置

### 机器人信息

```javascript
const ROBOTS = {
    Alice: {
        name: 'Alice',
        type: 'MobileManipulation',
        avatar: '🚗',
        color: 'alice',
        capabilities: ['navigation', 'manipulation']
    },
    Bob: {
        name: 'Bob',
        type: 'Manipulator',
        avatar: '🦾',
        color: 'bob',
        capabilities: ['manipulation', 'precision']
    },
    Lucy: {
        name: 'Lucy',
        type: 'Drone',
        avatar: '🚁',
        color: 'lucy',
        capabilities: ['aerial', 'exploration']
    }
};
```

## 与现有Python后端集成

### 1. 修改 coordinator.py

在 `DynaHMRC_Coordinator` 类中添加消息发送钩子：

```python
class DynaHMRC_Coordinator:
    def __init__(self, ...):
        # ... 现有代码 ...
        self.message_callback = None  # 添加消息回调
    
    def set_message_callback(self, callback: Callable):
        """设置消息回调函数"""
        self.message_callback = callback
    
    def send_robot_message(self, robot_id: str, thought: str, 
                          action: str = None, **kwargs):
        """发送机器人消息"""
        if self.message_callback:
            self.message_callback({
                "event": "robot_message",
                "data": {
                    "robot_id": robot_id,
                    "thought": thought,
                    "action": action,
                    **kwargs
                }
            })
```

### 2. 在各阶段添加消息发送

#### Self-Description 阶段

```python
def self_description_phase(self):
    for robot_id, robot in self.robots.items():
        description = robot.generate_self_description()
        self.send_robot_message(
            robot_id=robot_id,
            thought=description,
            robot_type=robot.robot_type,
            avatar=robot.avatar
        )
```

#### Task Allocation 阶段

```python
def allocate_tasks(self, task_plan):
    for task_id, robot_id in task_plan.assignments.items():
        self.send_robot_message(
            robot_id=robot_id,
            thought=f"I'll handle {task_id}",
            action=f"allocate_task: {task_id}",
            action_status="success"
        )
```

#### Leader Election 阶段

```python
def elect_leader(self):
    # 选举过程
    leader_id = self._vote_for_leader()
    
    for robot_id in self.robots:
        is_leader = (robot_id == leader_id)
        thought = "I propose myself as leader" if is_leader else f"I vote for {leader_id}"
        
        self.send_robot_message(
            robot_id=robot_id,
            thought=thought,
            action="nominate_leader" if is_leader else "vote",
            is_leader=is_leader,
            reply_to=None if is_leader else leader_id
        )
```

#### Execution 阶段

```python
def execute_step(self, robot_id, action):
    # 发送思考
    self.send_robot_message(
        robot_id=robot_id,
        thought=f"Executing: {action}",
        action=action,
        action_status="pending"
    )
    
    # 执行动作
    result = self.robots[robot_id].execute(action)
    
    # 发送结果
    self.send_robot_message(
        robot_id=robot_id,
        thought=f"Action completed: {action}",
        action=action,
        action_status="success" if result else "error"
    )
```

### 3. Flask 流式响应集成

```python
@app.route('/api/execute/stream', methods=['POST'])
def api_execute_stream():
    def generate():
        queue = Queue()
        
        def on_message(msg):
            queue.put(msg)
        
        coordinator.set_message_callback(on_message)
        
        # 启动任务
        thread = Thread(target=coordinator.execute_collaborative_task, 
                       args=(task,))
        thread.start()
        
        # 流式输出
        while thread.is_alive() or not queue.empty():
            try:
                msg = queue.get(timeout=0.1)
                yield _format_sse(msg["event"], msg["data"])
            except Empty:
                continue
    
    return Response(stream_with_context(generate()), 
                   mimetype='text/event-stream')
```

## UI 组件说明

### 1. 消息气泡组件

- 不同机器人使用不同颜色
- Leader 显示 👑 皇冠标记
- 消息支持展开查看详情
- 打字机效果显示思考过程

### 2. 阶段指示器

- 顶部显示当前阶段
- 已完成阶段标记为 ✓
- 当前阶段有脉冲动画

### 3. 机器人状态面板

- 显示每个机器人的当前状态
- 思考中/执行中/空闲
- Leader 特殊高亮

### 4. 任务进度

- 显示已完成/剩余对象
- 进度条可视化
- 已完成对象标签展示

## 前端事件处理

```javascript
function handleServerEvent(event, data) {
    switch (event) {
        case 'start':
            addTimeDivider(data.timestamp);
            addSystemMessage(data.message);
            break;
            
        case 'phase':
            setPhase(data.phase);
            break;
            
        case 'robot_message':
            messageQueue.add({
                robot_id: data.robot_id,
                thought: data.thought,
                action: data.action,
                action_status: data.action_status,
                is_leader: data.is_leader,
                reply_to: data.reply_to,
                timestamp: data.timestamp
            });
            break;
            
        case 'task_progress':
            updateTaskProgress(
                data.completed_objects, 
                data.remaining_objects
            );
            break;
            
        case 'complete':
            addSystemMessage(`✅ ${data.message}`);
            break;
            
        case 'error':
            addSystemMessage(`❌ ${data.message}`);
            break;
    }
}
```

## 样式变量

```css
:root {
    --alice-color: #ff6b9d;  /* Alice - 粉色 */
    --bob-color: #4ecdc4;    /* Bob - 青色 */
    --lucy-color: #95e1d3;   /* Lucy - 绿色 */
    --accent-primary: #e94560;
    --success: #00d9ff;
    --warning: #ffd700;
}
```

## 注意事项

1. **消息队列**: 前端使用消息队列管理消息显示，支持播放/暂停控制
2. **倍速播放**: 支持 0.5x/1x/2x 倍速，影响打字机效果和消息间隔
3. **过滤功能**: 可以按机器人筛选显示的消息
4. **响应式设计**: 支持桌面和移动端适配
