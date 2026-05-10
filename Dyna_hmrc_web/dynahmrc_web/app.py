# app.py
# -*- coding: utf-8 -*-
import sys
import io
# 设置标准输出编码为utf-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from flask import Flask, render_template, request, jsonify, Response, stream_with_context, redirect
from flask_cors import CORS
from typing import Dict, List, Any, Optional
import json
import time
import os
import re
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加 dynahmrc 路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'dynahmrc'))

# 导入新的DynaHMRC架构
from dynahmrc_architecture import DynaHMRC_Coordinator, RobotAgent, CollaborationPhase
from dynahmrc.utils.llm_api import create_llm_client, MockLLMClient, KimiLLMClient
from dynahmrc.task_analyzer import TaskAnalyzer, TASK_EXAMPLES

# 导入评估指标模块
from dynahmrc.metrics import get_metrics_collector, reset_metrics_collector, MetricsCollector

app = Flask(__name__)
CORS(app)

# 全局协调器实例
coordinator = None
llm_client = None


def init_coordinator(api_key: str = None, use_mock: bool = False):
    """初始化协调器 - 使用新的DynaHMRC架构"""
    global coordinator, llm_client
    
    # 创建 LLM 客户端
    if use_mock or not api_key:
        llm_client = MockLLMClient()

    else:
        llm_client = KimiLLMClient(api_key=api_key)

    
    # 创建机器人智能体 - 符合论文的去中心化设计
    # 严格按照 Table II 的原子动作集定义
    
    # Alice: 移动操作机器人 - 轮式底盘 + 单机械臂
    # Atomic actions: [navigate, open, pick, place, move, communicate, wait]
    alice = RobotAgent(
        name="Alice",
        robot_type="MobileManipulation",
        capabilities=["navigate", "open", "pick", "place", "move", "communicate", "wait"],
        llm_client=llm_client,
        avatar="🚗",
        max_history=10
    )
    
    # Bob: Fixed Manipulator - Desktop fixed single arm, cannot move
    # Atomic actions: [pick, place, communicate, wait] (no navigate)
    bob = RobotAgent(
        name="Bob",
        robot_type="Manipulator",
        capabilities=["pick", "place", "communicate", "wait"],
        llm_client=llm_client,
        avatar="🦾",
        max_history=10
    )
    
    # David: Mobile Robot - Pure wheeled chassis, cannot manipulate objects
    # Atomic actions: [navigate, communicate, wait] (no pick/place/open/move)
    david = RobotAgent(
        name="David",
        robot_type="Mobile",
        capabilities=["navigate", "communicate", "wait"],
        llm_client=llm_client,
        avatar="🤖",
        max_history=10
    )
    
    # Lucy: Drone - Quadrotor + suction gripper
    # Atomic actions: [navigate, pick, place, communicate, wait] (no open/move)
    lucy = RobotAgent(
        name="Lucy",
        robot_type="Drone",
        capabilities=["navigate", "pick", "place", "communicate", "wait"],
        llm_client=llm_client,
        avatar="🚁",
        max_history=10
    )
    
    robots = [alice, bob, david, lucy]
    
    # 创建协调器 - 管理协作流程（不是中央控制器）
    coordinator = DynaHMRC_Coordinator(
        robots=robots,
        reflection_interval=5,  # Δt = 5步
        max_steps=20,  # H = 20
        use_simulator=True  # 启用场景模拟器
    )
    
    # 初始化场景（添加物体和家具）
    coordinator.initialize_scene(objects=['apple', 'book', 'cup', 'remote', 'keys'])
    
    # 将真实场景图传递给协调器
    coordinator.scene_graph = coordinator.simulator.get_scene_graph()

    return coordinator


@app.route('/')
def index():
    """主页面 - 重定向到聊天界面"""
    return redirect('/chat')


@app.route('/chat')
def chat():
    """聊天式UI页面"""
    return render_template('chat.html')


@app.route('/api/init', methods=['POST'])
def api_init():
    """初始化 API"""
    data = request.json or {}
    api_key = data.get('api_key')
    use_mock = data.get('use_mock', False)
    
    try:
        init_coordinator(api_key=api_key, use_mock=use_mock)
        return jsonify({
            "success": True,
            "message": "协调器初始化成功",
            "llm_type": "Mock" if use_mock else "Kimi",
            "robots": [r.name for r in coordinator.robots.values()]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/robots')
def api_robots():
    """获取机器人状态"""
    if not coordinator:
        return jsonify({"error": "协调器未初始化"}), 400
    
    robots_info = []
    for name, robot in coordinator.robots.items():
        info = {
            "id": name,
            "type": robot.robot_type,
            "capabilities": robot.capabilities,
            "is_leader": robot.is_leader,
            "leader_name": robot.leader_name,
            "step_count": robot.step_count,
            "avatar": robot.avatar
        }
        robots_info.append(info)
    
    return jsonify({"robots": robots_info})


@app.route('/api/analyze_task', methods=['POST'])
def api_analyze_task():
    """
    分析任务复杂度
    判断是否需要多机器人协作
    """
    data = request.json or {}
    task = data.get('task', '')
    
    if not task:
        return jsonify({"error": "任务描述不能为空"}), 400
    
    try:
        analyzer = TaskAnalyzer()
        analysis = analyzer.analyze(task)
        
        # Task type label mapping (Chinese)
        task_type_labels = {
            'pack_object': '📦 打包任务 (拾取放置)',
            'sort_solid': '🎨 分类任务 (颜色匹配)',
            'make_sandwich': '🥪 堆叠任务 (顺序堆叠)',
            'unknown': '❓ 未知类型'
        }
        
        return jsonify({
            "success": True,
            "task": task,
            "task_type": analysis.task_type.value,
            "task_type_label": task_type_labels.get(analysis.task_type.value, '❓ 未知类型'),
            "complexity": analysis.complexity.value,
            "complexity_label": analyzer._get_complexity_label(analysis.complexity),
            "D_value": round(analysis.D_value, 2),
            "location_factor": round(analysis.location_factor, 2),
            "quantity_factor": round(analysis.quantity_factor, 2),
            "collaboration_factor": round(analysis.collaboration_factor, 2),
            "dynamic_complexity": analysis.dynamic_complexity,
            "collaboration_needed": analysis.collaboration_needed,
            "min_robots": analysis.min_robots,
            "recommended_robots": analysis.recommended_robots,
            "collaboration_type": analysis.collaboration_type.value,
            "collaboration_type_label": analyzer._get_collab_type_label(analysis.collaboration_type),
            "required_capabilities": analysis.required_capabilities,
            "estimated_steps": analysis.estimated_steps,
            "reasoning": analysis.reasoning,
            "subtasks": analysis.subtasks,
            "recommendation": analyzer.get_recommendation(analysis)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/example_tasks')
def api_example_tasks():
    """获取示例任务列表"""
    return jsonify({
        "success": True,
        "examples": TASK_EXAMPLES
    })


@app.route('/api/scenes')
def api_scenes():
    """获取所有预定义场景"""
    try:
        analyzer = TaskAnalyzer()
        scenes = analyzer.get_all_scenes()
        
        scene_list = []
        for name, scene in scenes.items():
            scene_list.append({
                "name": name,
                "description": scene.description,
                "furniture_count": len(scene.furniture),
                "object_count": len(scene.objects),
                "visible_objects": scene.get_visible_objects(),
                "hidden_objects": scene.get_hidden_objects()
            })
        
        return jsonify({
            "success": True,
            "scenes": scene_list
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/scene/<scene_name>')
def api_scene_detail(scene_name):
    """获取特定场景的详细信息"""
    try:
        analyzer = TaskAnalyzer()
        scene = analyzer.get_scene(scene_name)
        
        if not scene:
            return jsonify({"success": False, "error": "场景不存在"}), 404
        
        # Build furniture details
        furniture_list = []
        for furn_name, furn in scene.furniture.items():
            furniture_list.append({
                "name": furn_name,
                "position": furn.position,
                "stand_pose": furn.stand_pose,
                "state": furn.state,
                "surface_items": furn.surface_items,
                "contents": furn.contents if furn.state == "close" else []
            })
        
        return jsonify({
            "success": True,
            "scene": {
                "name": scene.name,
                "description": scene.description,
                "furniture": furniture_list,
                "visible_objects": scene.get_visible_objects(),
                "hidden_objects": scene.get_hidden_objects()
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/execute', methods=['POST'])
def api_execute():
    """执行任务（非流式）- 使用新的DynaHMRC架构"""
    if not coordinator:
        return jsonify({"error": "协调器未初始化"}), 400
    
    data = request.json or {}
    task = data.get('task', '')
    
    if not task:
        return jsonify({"error": "任务描述不能为空"}), 400
    
    # 简化的非流式执行
    try:
        # 执行Self-Description
        descriptions = {}
        for name, robot in coordinator.robots.items():
            _, description = robot.self_describe(task)
            descriptions[name] = description
        
        # 执行Task Allocation
        proposals = {}
        for name, robot in coordinator.robots.items():
            teammates = {n: d for n, d in descriptions.items() if n != name}
            plan, _, _ = robot.propose_allocation(task, teammates)
            proposals[name] = plan
        
        # 执行Leader Election
        votes = {}
        for name, robot in coordinator.robots.items():
            vote_for, _, _ = robot.vote_leader(proposals)
            votes[name] = vote_for
        
        vote_counts = {}
        for vote in votes.values():
            vote_counts[vote] = vote_counts.get(vote, 0) + 1
        leader_name = max(vote_counts, key=vote_counts.get)
        
        return jsonify({
            "success": True,
            "message": f"任务执行完成。领导者: {leader_name}",
            "leader": leader_name,
            "votes": vote_counts,
            "descriptions": descriptions
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def extract_objects_from_task(task: str) -> list:
    """从任务描述中提取物体列表"""
    # 常见的物体关键词
    common_objects = ['apple', 'book', 'cup', 'pen', 'fork', 'knife', 'spoon', 
                      'plate', 'bottle', 'box', 'bag', 'toy', 'phone', 'keys',
                      '苹果', '书', '杯子', '笔', '叉子', '刀', '勺子', 
                      '盘子', '瓶子', '盒子', '包', '玩具', '手机', '钥匙']
    
    objects = []
    task_lower = task.lower()
    
    for obj in common_objects:
        if obj in task_lower or obj in task:
            objects.append(obj)
    
    # 如果没有找到物体，使用默认值
    if not objects:
        objects = ['apple', 'book', 'cup']
    
    return objects


# ========== 闭环执行辅助函数 ==========

def _validate_execution(action: Dict, feedback: Dict, scene_graph: Dict) -> Dict:
    """
    执行验证层 - 验证动作执行结果
    检查状态确认、内容报告、执行验证
    """
    validation = {
        'state_confirmed': False,
        'content_reported': False,
        'execution_validated': False,
        'pre_state': {},
        'post_state': {},
        'discrepancies': []
    }
    
    action_type = action.get('type', 'wait')
    
    if feedback.get('success'):
        # Success Feedback 验证
        
        # 1. State Confirmation & Update
        if action_type == 'pick' and feedback.get('holding_object'):
            validation['state_confirmed'] = True
            validation['post_state']['holding'] = feedback.get('holding_object')
        elif action_type == 'place' and not feedback.get('holding_object'):
            validation['state_confirmed'] = True
            validation['post_state']['holding'] = None
        elif action_type == 'open' and feedback.get('container_opened'):
            validation['state_confirmed'] = True
            validation['post_state']['container_state'] = 'open'
        
        # 2. Content Reporting
        if feedback.get('found_objects') or feedback.get('message'):
            validation['content_reported'] = True
        
        # 3. Execution Validation
        if feedback.get('position_changed') or feedback.get('object_moved'):
            validation['execution_validated'] = True
        
        # 如果没有明确的验证标记，默认通过
        if not any([validation['state_confirmed'], validation['content_reported'], validation['execution_validated']]):
            validation['execution_validated'] = True  # 默认验证通过
    else:
        # Failure Feedback 分类
        error_msg = feedback.get('message', '').lower()
        
        if 'not found' in error_msg or 'invalid' in error_msg or 'target' in error_msg:
            feedback['error_type'] = 'invalid_target'
        elif 'constraint' in error_msg or 'cannot' in error_msg or 'unable' in error_msg:
            feedback['error_type'] = 'action_constraints'
        elif 'conflict' in error_msg or 'collision' in error_msg:
            feedback['error_type'] = 'execution_conflict'
        elif 'measurement' in error_msg or 'position' in error_msg or 'distance' in error_msg:
            feedback['error_type'] = 'error_measurement'
        elif 'api' in error_msg or 'invocation' in error_msg:
            feedback['error_type'] = 'api_invocation'
        else:
            feedback['error_type'] = 'unknown'
    
    return validation


def _enhance_feedback(action: Dict, feedback: Dict, validation: Dict) -> Dict:
    """增强反馈信息，添加详细分类"""
    enhanced = feedback.copy()
    action_type = action.get('type', 'wait')
    
    if feedback.get('success'):
        # Success Feedback 分类
        if validation.get('state_confirmed'):
            enhanced['feedback_type'] = 'state_confirmation'
            enhanced['state_confirmation'] = True
        elif validation.get('content_reported'):
            enhanced['feedback_type'] = 'content_reporting'
            enhanced['content_reporting'] = True
        elif validation.get('execution_validated'):
            enhanced['feedback_type'] = 'execution_validation'
            enhanced['execution_validation'] = True
        else:
            enhanced['feedback_type'] = 'success'
    else:
        # Failure Feedback 已在验证层分类
        enhanced['feedback_type'] = feedback.get('error_type', 'failure')
    
    # 添加动作元数据
    enhanced['action_type'] = action_type
    enhanced['action_params'] = {k: v for k, v in action.items() if k != 'type'}
    
    # 提取目标物体
    if action_type in ['pick', 'place']:
        target = action.get('object') or action.get('target')
        if target:
            enhanced['target_object'] = target
    
    # 提取完成物体
    if feedback.get('success') and action_type == 'place':
        placed_obj = action.get('object') or action.get('target')
        if placed_obj:
            enhanced['completed_object'] = placed_obj
    
    return enhanced


def _update_task_progress_from_feedback(robot, feedback: Dict):
    """根据反馈更新任务进度"""
    # 更新发现的物体
    if feedback.get('found_objects'):
        robot.memory.update_task_progress(
            discovered_objects=feedback['found_objects']
        )
    
    # 更新完成的物体
    if feedback.get('completed_object'):
        robot.memory.update_task_progress(
            completed_objects=[feedback['completed_object']]
        )


def _format_feedback_message(feedback: Dict) -> str:
    """格式化反馈信息为可读文本"""
    feedback_type = feedback.get('feedback_type', 'unknown')
    message = feedback.get('message', '')
    
    # 添加反馈类型前缀
    type_labels = {
        'state_confirmation': '✓ State Confirmed:',
        'content_reporting': '📢 Content Report:',
        'execution_validation': '✓ Execution Validated:',
        'success': '✓ Success:',
        'invalid_target': '✗ Invalid Target:',
        'action_constraints': '✗ Action Constraints:',
        'execution_conflict': '✗ Execution Conflict:',
        'error_measurement': '✗ Error Measurement:',
        'api_invocation': '✗ API Error:',
        'failure': '✗ Failed:'
    }
    
    prefix = type_labels.get(feedback_type, f'[{feedback_type}]')
    
    # 添加发现物体信息
    if feedback.get('found_objects'):
        message += f" | Discovered: {', '.join(feedback['found_objects'])}"
    
    # 添加持有物体信息
    if feedback.get('holding_object'):
        message += f" | Holding: {feedback['holding_object']}"
    
    return f"{prefix} {message}"


def _should_update_leader_plan(leader, team_reflections: Dict, previous_plan: str) -> bool:
    """
    判断是否需要更新Leader Plan
    基于团队反思的差异度和执行状态
    """
    # 1. 首次执行，必须更新
    if previous_plan is None:
        return True
    
    # 2. 检查执行统计数据
    total_failures = sum(leader.memory.failure_types.values())
    consecutive_failures = leader.memory.execution_stats['consecutive_failures']
    
    # 连续失败过多，需要更新
    if consecutive_failures >= 2:
        return True
    
    # 3. 检查团队反思中的关键信号
    significant_issues = 0
    for name, (thought, summary, future) in team_reflections.items():
        # 检查反思中是否提到关键问题
        summary_lower = summary.lower()
        if any(keyword in summary_lower for keyword in ['fail', 'error', 'cannot', 'unable', 'stuck', 'blocked']):
            significant_issues += 1
        if any(keyword in summary_lower for keyword in ['discovered', 'found', 'new']):
            significant_issues += 1
    
    # 多个机器人报告问题，需要更新
    if significant_issues >= 2:
        return True
    
    # 4. 任务进度显著变化
    completed = len(leader.memory.task_progress['completed_objects'])
    remaining = len(leader.memory.task_progress['remaining_objects'])
    total = completed + remaining
    
    if total > 0:
        progress_pct = completed / total
        # 每完成25%的任务，更新一次计划
        if progress_pct > 0 and progress_pct % 0.25 < 0.05:
            return True
    
    # 默认：不需要更新
    return False


@app.route('/api/execute/stream', methods=['POST'])
def api_execute_stream():
    """
    执行任务（流式输出 - 聊天式UI格式）
    使用符合论文的DynaHMRC架构：
    - 去中心化：每个机器人是独立的LLM Agent
    - 四阶段循环：Self-Description -> Task Allocation -> Leader Election -> Closed-Loop Execution
    - 投票机制选举领导者
    - 周期性Reflection
    """
    if not coordinator:
        return jsonify({"error": "协调器未初始化"}), 400
    
    data = request.json or {}
    task = data.get('task', '')
    
    if not task:
        return jsonify({"error": "任务描述不能为空"}), 400
    
    def generate_stream():
        """生成流式输出 - 使用真正的DynaHMRC架构"""
        try:
            # 开始
            yield _format_sse("start", {
                "message": f"开始执行任务: {task}",
                "timestamp": time.strftime("%H:%M:%S")
            })
            
            # 定义回调函数来接收协调器的事件
            events = []
            def event_callback(event_type, data):
                events.append((event_type, data))
            
            # 运行协作流程
            # 注意：这会阻塞直到完成，我们需要在循环中yield事件
            # 由于协调器是同步的，我们先收集所有事件再yield
            
            # 手动执行各阶段以支持流式输出
            # 修复：阶段切换事件在当前阶段所有消息发送完成后才发送
            
            # ========== Stage 1: Self-Description ==========
            # 首先发送第一阶段事件
            yield _format_sse("phase", {"phase": "self-description"})
            time.sleep(0.1)  # 给前端时间处理阶段切换
            
            descriptions = {}
            self_description_results = []  # 收集所有自我介绍结果
            
            for name, robot in coordinator.robots.items():
                try:
                    thought, description = robot.self_describe(task)
                    descriptions[name] = description
                    
                    # 先收集结果，暂不发送
                    # 只发送 description，与模拟演示格式一致
                    self_description_results.append({
                        "robot_id": name,
                        "robot_type": robot.robot_type,
                        "avatar": robot.avatar,
                        "thought": description,  # 使用 description 作为 thought 显示
                        "phase": "self-description",
                        "is_leader": False,
                        "action": None,
                        "action_status": None,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    logger.error(f"[ERROR] Self-Description failed for {name}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 使用默认描述
                    descriptions[name] = f"I am {name}, ready to help."
                    self_description_results.append({
                        "robot_id": name,
                        "robot_type": robot.robot_type,
                        "avatar": robot.avatar,
                        "thought": descriptions[name],
                        "phase": "self-description",
                        "is_leader": False,
                        "action": None,
                        "action_status": None,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
            
            # 所有自我介绍完成后，统一发送消息
            for msg_data in self_description_results:
                yield _format_sse("robot_message", msg_data)
                time.sleep(0.1)
            
            # 第一阶段所有消息发送完成后，再发送第二阶段事件
            logger.info("[STAGE 2] Starting Task Allocation phase")
            time.sleep(0.2)  # 确保第一阶段消息已处理完成
            yield _format_sse("phase", {"phase": "task-allocation"})
            time.sleep(0.1)  # 给前端时间处理阶段切换
            
            proposals = {}
            collaboration_plan_results = []  # 收集 Collaboration Plan 结果
            campaign_speech_results = []  # 收集 Campaign Speech 结果
            
            for name, robot in coordinator.robots.items():
                # 初始化变量，避免作用域问题
                plan = None
                thought = None
                campaign = None
                
                try:
                    logger.info(f"[STAGE 2] Processing Task Allocation for {name}")
                    teammates = {n: d for n, d in descriptions.items() if n != name}
                    
                    # 添加超时保护 - 增加到60秒
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(robot.propose_allocation, task, teammates)
                        try:
                            plan, thought, campaign = future.result(timeout=60)  # 60秒超时
                            logger.info(f"[STAGE 2] {name} propose_allocation returned successfully")
                        except concurrent.futures.TimeoutError:
                            logger.error(f"[ERROR] Task Allocation timeout for {name}")
                            # 超时时使用默认值而不是抛出异常
                            caps = ', '.join(robot.capabilities)
                            plan = {'description': f'{name}: Lead task execution; Others: Support operations'}
                            thought = f"As {name}, I will propose a collaboration plan for our team."
                            campaign = f"Hi team, I'm {name}. Vote for me to lead this mission!"
                            logger.warning(f"[FALLBACK] Using default values for {name} due to timeout")
                    
                    # 验证返回的内容，确保不是自我介绍格式
                    if thought and ("大家好" in thought or "I am" in thought[:20] and "robot" in thought.lower()):
                        logger.error(f"[ERROR] {name} returned self-description content in Task Allocation!")
                        logger.error(f"[ERROR] Content: {thought[:100]}")
                        # 强制使用默认值
                        caps = ', '.join(robot.capabilities)
                        plan = {'description': f'{name}: Lead task execution; Others: Support operations'}
                        thought = f"As {name}, I will propose a collaboration plan for our team."
                        campaign = f"Hi team, I'm {name}. Vote for me to lead this mission!"
                    
                    # 如果解析失败，提供默认值
                    if not plan or not plan.get('description'):
                        plan = {'description': f'{name} proposes to collaborate with teammates to complete the task.'}
                    if not thought:
                        thought = f"I will work with my teammates to accomplish this task efficiently."
                    if not campaign:
                        campaign = f"I believe I can be a good leader because I have {', '.join(robot.capabilities)} capabilities."
                    
                    proposals[name] = (plan, thought, campaign)
                    
                    # 打印调试信息
                    logger.info(f"[DEBUG] Task Allocation - Robot: {name}")
                    logger.info(f"[DEBUG] Thought: {thought[:100]}...")
                    logger.info(f"[DEBUG] Plan: {plan}")
                    logger.info(f"[DEBUG] Campaign: {campaign[:100]}...")
                    
                    # 收集 Collaboration Plan 结果
                    collaboration_plan_results.append({
                        "robot_id": name,
                        "thought": plan.get('description', thought),  # 使用 plan description
                        "phase": "task-allocation",
                        "is_leader": False,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                    
                    # 收集 Campaign Speech 结果
                    campaign_speech_results.append({
                        "robot_id": name,
                        "thought": campaign,  # 使用 campaign speech
                        "phase": "task-allocation",
                        "is_leader": False,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                except Exception as e:
                    logger.error(f"[ERROR] Task Allocation failed for {name}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 发送错误信息到前端
                    yield _format_sse("system", {
                        "message": f"⚠️ {name} 任务分配出错，使用默认方案"
                    })
                    # 提供默认提案
                    default_plan = {'description': f'{name} will contribute using capabilities: {", ".join(robot.capabilities)}'}
                    default_thought = "Let me collaborate with my teammates."
                    default_campaign = f"Vote for me! I have {', '.join(robot.capabilities)}."
                    proposals[name] = (default_plan, default_thought, default_campaign)
                    
                    # 收集 Collaboration Plan 结果
                    collaboration_plan_results.append({
                        "robot_id": name,
                        "thought": default_plan['description'],
                        "phase": "task-allocation",
                        "is_leader": False,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                    
                    # 收集 Campaign Speech 结果
                    campaign_speech_results.append({
                        "robot_id": name,
                        "thought": default_campaign,
                        "phase": "task-allocation",
                        "is_leader": False,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
            
            # 先发送 Collaboration Plan（所有机器人）
            for msg_data in collaboration_plan_results:
                yield _format_sse("robot_message", msg_data)
                time.sleep(0.2)
            
            # 再发送 Campaign Speech（所有机器人）
            for msg_data in campaign_speech_results:
                yield _format_sse("robot_message", msg_data)
                time.sleep(0.2)
            
            # 第二阶段所有消息发送完成后，再发送第三阶段事件
            time.sleep(0.2)  # 确保第二阶段消息已处理完成
            
            # ========== Stage 3: Voting (投票选举) ==========
            # 检查proposals是否为空，如果为空则使用默认领导者
            if not proposals:
                yield _format_sse("system", {
                    "message": "⚠️ 没有任务分配提案，使用默认领导者"
                })
                # 选择第一个机器人作为默认领导者
                default_leader = list(coordinator.robots.keys())[0] if coordinator.robots else "Alice"
                leader_name = default_leader
                
                # 更新所有机器人的领导者状态
                for name, robot in coordinator.robots.items():
                    robot.leader_name = leader_name
                    robot.is_leader = (name == leader_name)
                
                coordinator.leader_name = leader_name
                
                yield _format_sse("phase", {"phase": "voting"})
                time.sleep(0.1)
                yield _format_sse("system", {
                    "message": f"🗳️ 默认领导者: {leader_name} (无投票阶段)"
                })
            else:
                votes = {}
                voting_results = []  # 收集所有投票结果
                
                for name, robot in coordinator.robots.items():
                    try:
                        vote_for, thought, reasoning = robot.vote_leader(proposals)
                        
                        # 确保有合理的值
                        if not vote_for or vote_for not in proposals:
                            vote_for = list(proposals.keys())[0] if proposals else "Alice"
                        if not thought:
                            thought = f"I vote for {vote_for} as the leader."
                        if not reasoning:
                            reasoning = f"{vote_for} has demonstrated good leadership qualities."
                        
                        votes[name] = vote_for
                        
                        # 先收集结果，暂不发送
                        voting_results.append({
                            "robot_id": name,
                            "vote_for": vote_for,
                            "thought": thought,
                            "reasoning": reasoning,
                            "phase": "voting",
                            "is_leader": False,
                            "timestamp": time.strftime("%H:%M:%S")
                        })
                    except Exception as e:
                        print(f"[ERROR] Voting failed for {name}: {str(e)}")
                        # 默认投票给第一个候选人
                        default_vote = list(proposals.keys())[0] if proposals else "Alice"
                        votes[name] = default_vote
                        
                        # 先收集结果，暂不发送
                        voting_results.append({
                            "robot_id": name,
                            "vote_for": default_vote,
                            "thought": f"I vote for {default_vote} as the leader.",
                            "reasoning": f"{default_vote} has demonstrated good leadership qualities.",
                            "phase": "voting",
                            "is_leader": False,
                            "timestamp": time.strftime("%H:%M:%S")
                        })
                
                # 统计投票结果
                vote_counts = {}
                for vote in votes.values():
                    vote_counts[vote] = vote_counts.get(vote, 0) + 1
                
                # 确保有投票结果，如果没有则默认选第一个机器人
                if not vote_counts:
                    default_leader = list(coordinator.robots.keys())[0] if coordinator.robots else "Alice"
                    vote_counts[default_leader] = 1
                
                leader_name = max(vote_counts, key=vote_counts.get)
                
                # 更新所有机器人的领导者状态
                for name, robot in coordinator.robots.items():
                    robot.leader_name = leader_name
                    robot.is_leader = (name == leader_name)
                
                coordinator.leader_name = leader_name
                
                # 发送阶段切换事件 - 进入第三阶段：投票选举
                yield _format_sse("phase", {"phase": "voting"})
                time.sleep(0.1)
                
                # 发送投票消息，显示完整的 Leader Election 分析
                for msg_data in voting_results:
                    # 构建投票消息格式，包含完整的分析内容
                    voting_msg = {
                        "robot_id": msg_data["robot_id"],
                        "thought": msg_data.get("thought", f"I vote for {msg_data['vote_for']}."),
                        "reasoning": msg_data.get("reasoning", ""),
                        "vote_for": msg_data["vote_for"],
                        "is_leader": msg_data["robot_id"] == leader_name,
                        "timestamp": msg_data["timestamp"]
                    }
                    yield _format_sse("robot_message", voting_msg)
                    time.sleep(0.15)
                
                yield _format_sse("system", {
                    "message": f"🗳️ 投票结果: {leader_name} 当选为领导者 ({vote_counts[leader_name]}/{len(coordinator.robots)} 票)"
                })
                time.sleep(0.2)
            
            # 第三阶段所有消息发送完成后，再发送第四阶段事件
            time.sleep(0.2)  # 确保第三阶段消息已处理完成
            
            # ========== Stage 4: Closed-Loop Execution with Enhanced Feedback ==========
            yield _format_sse("phase", {"phase": "execution"})
            time.sleep(0.1)
            
            leader_plan = proposals[leader_name][0] if leader_name in proposals else {}
            
            # 执行多个步骤
            max_steps = 10  # 简化演示
            previous_leader_plan = None
            reflection_triggered = False
            
            for step in range(max_steps):
                # 自适应反思触发判断
                should_reflect = False
                trigger_reason = ""
                
                for name, robot in coordinator.robots.items():
                    if robot.memory.should_trigger_reflection(step, regular_interval=5):
                        should_reflect = True
                        # 获取触发原因
                        if robot.memory.execution_stats['consecutive_failures'] >= 3:
                            trigger_reason = f"{name} 连续失败 {robot.memory.execution_stats['consecutive_failures']} 次"
                        elif step > 0 and step % 5 == 0:
                            trigger_reason = "定期反思间隔 (Δt=5)"
                        elif robot.memory.execution_stats['total_actions'] - robot.memory.execution_stats['last_success_step'] >= 5:
                            trigger_reason = f"{robot.memory.execution_stats['total_actions'] - robot.memory.execution_stats['last_success_step']} 步未成功"
                        break
                
                # 执行反思阶段
                if should_reflect and step > 0:
                    reflection_triggered = True
                    yield _format_sse("phase", {"phase": "reflection"})
                    time.sleep(0.1)
                    yield _format_sse("system", {
                        "message": f"🔄 反思触发: {trigger_reason}"
                    })
                    
                    # 所有机器人反思（Self-Reflection）
                    team_reflections = {}
                    for name, robot in coordinator.robots.items():
                        thought, summary, future = robot.reflect(task)
                        team_reflections[name] = (thought, summary, future)
                        
                        # 发送个人反思结果
                        yield _format_sse("robot_message", {
                            "robot_id": name,
                            "thought": thought,
                            "summary": summary,
                            "future_plan": future,
                            "phase": "reflection",
                            "is_leader": robot.is_leader,
                            "is_reflection": True,
                            "action": None,
                            "action_status": None,
                            "timestamp": time.strftime("%H:%M:%S")
                        })
                        time.sleep(0.15)
                    
                    # Leader整合团队反思并更新计划（Leader-Plan）
                    if leader_name:
                        leader = coordinator.robots[leader_name]
                        
                        # 检查是否有必要更新计划
                        should_update_plan = _should_update_leader_plan(
                            leader, team_reflections, previous_leader_plan
                        )
                        
                        if should_update_plan:
                            thought, updated_plan = leader.update_leader_plan(team_reflections)
                            
                            # 验证计划变化
                            plan_changed = (previous_leader_plan != updated_plan)
                            
                            yield _format_sse("robot_message", {
                                "robot_id": leader_name,
                                "thought": thought,
                                "updated_plan": updated_plan,
                                "phase": "reflection",
                                "is_leader": True,
                                "plan_changed": plan_changed,
                                "action": None,
                                "action_status": None,
                                "timestamp": time.strftime("%H:%M:%S")
                            })
                            
                            # 更新leader plan
                            previous_leader_plan = updated_plan
                            leader_plan = {'description': updated_plan}
                            
                            yield _format_sse("system", {
                                "message": f"📋 领导者更新了协作计划" + 
                                          (" (检测到重大变更)" if plan_changed else " (小幅调整)")
                            })
                        else:
                            yield _format_sse("system", {
                                "message": "📋 当前计划仍然是最优的，无需更新"
                            })
                    
                    # 反思阶段所有消息发送完成后，再返回执行阶段
                    time.sleep(0.2)  # 确保反思阶段消息已处理完成
                    
                    # 返回执行阶段
                    yield _format_sse("phase", {"phase": "execution"})
                    time.sleep(0.1)
                
                # 更新场景图（从模拟器获取真实位置）
                if coordinator.simulator:
                    coordinator.scene_graph = coordinator.simulator.get_scene_graph()
                
                # 每个机器人执行一步
                for name, robot in coordinator.robots.items():
                    # 获取机器人当前真实位置
                    robot_pose = [0, 0, 0]
                    if coordinator.simulator:
                        robot_pose = coordinator.simulator.get_robot_pose(name) or [0, 0, 0]
                        robot.observation.update_robot_info(robot_pose)
                    
                    # 规划动作（Planning Module）
                    action, thought = robot.plan_next_action(
                        task,
                        leader_plan,
                        coordinator.scene_graph,
                        robot_pose
                    )
                    
                    # 执行动作（Close-Loop Execution）
                    if coordinator.simulator:
                        feedback = coordinator._execute_action_with_simulator(name, action)
                    else:
                        feedback = robot.execute_action(action)
                    
                    # 执行验证层 - 验证动作执行结果
                    validation_result = _validate_execution(action, feedback, coordinator.scene_graph)
                    feedback['validation'] = validation_result
                    
                    # 增强反馈信息
                    enhanced_feedback = _enhance_feedback(action, feedback, validation_result)
                    
                    # 存储结果到Memory
                    robot.store_execution_result(action, enhanced_feedback)
                    
                    # 更新任务进度
                    _update_task_progress_from_feedback(robot, enhanced_feedback)
                    
                    # 执行后更新场景图
                    if coordinator.simulator:
                        coordinator.scene_graph = coordinator.simulator.get_scene_graph()
                    
                    # 格式化动作字符串
                    action_str = f"{action.get('type', 'wait')}({', '.join([f'{k}={v}' for k, v in action.items() if k != 'type'])})" if action else None
                    
                    # 格式化反馈信息（包含详细反馈类型）
                    feedback_msg = _format_feedback_message(enhanced_feedback)
                    
                    yield _format_sse("robot_message", {
                        "robot_id": name,
                        "thought": thought,
                        "action": action_str,
                        "action_status": "success" if enhanced_feedback.get('success') else "failed",
                        "feedback": feedback_msg,
                        "feedback_type": enhanced_feedback.get('feedback_type', 'unknown'),
                        "robot_position": robot_pose[:3],
                        "phase": "execution",
                        "is_leader": robot.is_leader,
                        "step": step,
                        "timestamp": time.strftime("%H:%M:%S")
                    })
                    time.sleep(0.3)
                
                # 检查是否完成任务
                if step >= max_steps - 1:
                    break
            
            # ========== Final Reflection ==========
            
            for name, robot in coordinator.robots.items():
                thought, summary, future = robot.reflect(task)
                
                yield _format_sse("robot_message", {
                    "robot_id": name,
                    "thought": thought,
                    "summary": summary,
                    "future_plan": future,
                    "phase": "reflection",
                    "is_leader": robot.is_leader,
                    "is_reflection": True,
                    "action": None,
                    "action_status": None,
                    "timestamp": time.strftime("%H:%M:%S")
                })
                time.sleep(0.15)
            
            # 完成
            yield _format_sse("complete", {
                "message": f"任务执行完成！",
                "total_steps": max_steps,
                "timestamp": time.strftime("%H:%M:%S")
            })
            
            # 重置领导者状态
            yield _format_sse("system", {
                "message": "--- 任务结束，领导者状态已重置 ---",
                "reset_leader": True
            })
            
        except Exception as e:
            import traceback
            error_msg = f"{str(e)}\n{traceback.format_exc()}"

            yield _format_sse("error", {"error": str(e), "message": "执行过程中发生错误"})
    
    return Response(
        stream_with_context(generate_stream()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/chat/stream', methods=['POST'])
def api_chat_stream():
    """与 Kimi 对话（流式）"""
    if not coordinator or not coordinator.llm_client:
        return jsonify({"error": "协调器未初始化"}), 400
    
    data = request.json or {}
    message = data.get('message', '')
    
    if not message:
        return jsonify({"error": "消息不能为空"}), 400
    
    def generate_chat():
        """生成流式对话"""
        try:
            # 检查是否是 Kimi 客户端
            from dynahmrc.utils.llm_api import KimiLLMClient
            if isinstance(coordinator.llm_client, KimiLLMClient):
                # 使用真实的 Kimi 流式 API
                full_messages = [{"role": "user", "content": message}]
                
                yield _format_sse("start", {"message": "开始生成回复..."})
                
                accumulated = ""
                for chunk in coordinator.llm_client.stream_complete(full_messages):
                    accumulated += chunk
                    yield _format_sse("token", {"content": chunk, "accumulated": accumulated})
                
                yield _format_sse("complete", {
                    "full_response": accumulated,
                    "message": "回复生成完成"
                })
            else:
                # Mock 模式：模拟流式输出
                response = coordinator.llm_client.generate(message)
                
                yield _format_sse("start", {"message": "开始生成回复...(Mock模式)"})
                
                # 逐字输出
                for char in response:
                    yield _format_sse("token", {"content": char, "accumulated": response[:response.index(char)+1] if char in response else response})
                    time.sleep(0.01)
                
                yield _format_sse("complete", {
                    "full_response": response,
                    "message": "回复生成完成"
                })
                
        except Exception as e:
            yield _format_sse("error", {"error": str(e)})
    
    return Response(
        stream_with_context(generate_chat()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


@app.route('/api/status')
def api_status():
    """获取协调器状态"""
    if not coordinator:
        return jsonify({"initialized": False})
    
    return jsonify({
        "initialized": True,
        "llm_type": type(coordinator.llm_client).__name__,
        "robots_count": len(coordinator.robots),
        "execution_status": coordinator.get_execution_status() if hasattr(coordinator, 'get_execution_status') else "unknown"
    })


def _format_sse(event_type: str, data: dict) -> str:
    """格式化 Server-Sent Events 消息"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ========== 评估指标 API ==========

@app.route('/api/metrics/start', methods=['POST'])
def api_start_metrics():
    """开始记录新任务的评估指标"""
    data = request.json or {}
    task_id = data.get('task_id', f"task_{int(time.time())}")
    task_description = data.get('task_description', '')
    total_subtasks = data.get('total_subtasks', 0)
    
    try:
        collector = get_metrics_collector()
        metrics = collector.start_task(task_id, task_description, total_subtasks)
        return jsonify({
            "success": True,
            "message": f"开始记录任务 {task_id} 的指标",
            "task_id": task_id,
            "metrics": metrics.to_dict()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/end', methods=['POST'])
def api_end_metrics():
    """结束当前任务的评估指标记录"""
    data = request.json or {}
    task_id = data.get('task_id')
    
    try:
        collector = get_metrics_collector()
        metrics = collector.end_task(task_id)
        if metrics:
            return jsonify({
                "success": True,
                "message": f"任务 {metrics.task_id} 指标记录已结束",
                "task_summary": {
                    "task_id": metrics.task_id,
                    "is_completed": metrics.is_completed,
                    "is_partial_success": metrics.is_partial_success,
                    "completion_rate": metrics.completion_rate,
                    "total_steps": metrics.total_steps,
                    "active_steps": metrics.active_steps,
                    "communication_count": metrics.communication_count,
                    "duration": metrics.duration
                }
            })
        return jsonify({"success": False, "error": "没有正在记录的任务"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/record_step', methods=['POST'])
def api_record_step():
    """记录执行步骤"""
    data = request.json or {}
    action_type = data.get('action_type', '')
    robot_name = data.get('robot_name')
    is_wait = data.get('is_wait', False)
    
    try:
        collector = get_metrics_collector()
        collector.record_step(action_type, robot_name, is_wait)
        return jsonify({
            "success": True,
            "message": "步骤已记录"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/record_communication', methods=['POST'])
def api_record_communication():
    """记录机器人间的通信"""
    data = request.json or {}
    from_robot = data.get('from_robot', '')
    to_robot = data.get('to_robot', '')
    is_broadcast = data.get('is_broadcast', False)
    
    try:
        collector = get_metrics_collector()
        collector.record_communication(from_robot, to_robot, is_broadcast)
        return jsonify({
            "success": True,
            "message": "通信已记录"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/update_progress', methods=['POST'])
def api_update_progress():
    """更新任务进度"""
    data = request.json or {}
    completed = data.get('completed', 0)
    total = data.get('total', 0)
    
    try:
        collector = get_metrics_collector()
        collector.update_progress(completed, total)
        return jsonify({
            "success": True,
            "message": f"进度已更新: {completed}/{total}"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/summary')
def api_get_summary():
    """获取核心评估指标 (SUCC, PS, TS, AS, CC)"""
    try:
        collector = get_metrics_collector()
        summary = collector.get_summary_metrics()
        return jsonify({
            "success": True,
            "summary": summary,
            "description": {
                "SUCC": "任务全做完的比例 (Success Rate)",
                "PS": "任务做了一半以上的比例 (Partial Success)",
                "TS": "总共花了多少步 (Total Steps)",
                "AS": "实际干了多少活 (Active Steps, 不算发呆/等待)",
                "CC": "互相喊话了多少次 (Communication Count)"
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/current')
def api_get_current_metrics():
    """获取当前任务的详细指标"""
    try:
        collector = get_metrics_collector()
        metrics = collector.get_current_task_metrics()
        if metrics:
            return jsonify({
                "success": True,
                "metrics": metrics
            })
        return jsonify({"success": False, "error": "没有正在记录的任务"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/report')
def api_get_full_report():
    """获取完整的评估报告"""
    try:
        collector = get_metrics_collector()
        report = collector.get_full_report()
        return jsonify({
            "success": True,
            "report": report
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/metrics/reset', methods=['POST'])
def api_reset_metrics():
    """重置所有评估指标"""
    try:
        reset_metrics_collector()
        return jsonify({
            "success": True,
            "message": "所有评估指标已重置"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == '__main__':
    # 初始化默认协调器（Mock 模式）
    init_coordinator(use_mock=True)

    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
