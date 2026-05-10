#!/usr/bin/env python3
"""
测试动态重规划功能
验证重规划触发条件和重新分配任务逻辑
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynahmrc_architecture import RobotAgent, DynaHMRC_Coordinator, MemoryModule
from dynahmrc.utils.llm_api import MockLLMClient


def test_should_trigger_replanning():
    """测试重规划触发条件判断"""
    print("=" * 60)
    print("测试 1: 重规划触发条件")
    print("=" * 60)
    
    # 创建模拟LLM客户端
    llm_client = MockLLMClient()
    
    # 创建机器人代理
    robot = RobotAgent(
        name="Alice",
        robot_type="MobileManipulator",
        capabilities=["navigate", "pick", "place", "open"],
        llm_client=llm_client
    )
    
    # 测试1: 初始状态不应触发
    should_trigger, reason = robot.should_trigger_replanning()
    print(f"初始状态 - 触发: {should_trigger}, 原因: {reason}")
    assert not should_trigger, "初始状态不应触发重规划"
    
    # 测试2: 连续失败3次应触发
    for i in range(3):
        robot.memory.execution_stats['total_actions'] += 1
        robot.memory.execution_stats['failure_count'] += 1
        robot.memory.execution_stats['consecutive_failures'] += 1
    
    should_trigger, reason = robot.should_trigger_replanning()
    print(f"连续3次失败 - 触发: {should_trigger}, 原因: {reason}")
    assert should_trigger and reason == "consecutive_failures", "连续失败应触发重规划"
    
    # 重置
    robot.memory.execution_stats['consecutive_failures'] = 0
    
    # 测试3: 特定对象失败3次应触发
    robot.memory.task_progress['failed_attempts']['cup'] = 3
    should_trigger, reason = robot.should_trigger_replanning()
    print(f"对象'cup'失败3次 - 触发: {should_trigger}, 原因: {reason}")
    assert should_trigger and "object_failure" in reason, "对象多次失败应触发重规划"
    
    # 重置
    robot.memory.task_progress['failed_attempts'] = {}
    
    # 测试4: 长时间无进展应触发
    robot.memory.execution_stats['total_actions'] = 10
    robot.memory.execution_stats['last_success_step'] = 2  # 8步无成功
    
    should_trigger, reason = robot.should_trigger_replanning()
    print(f"8步无进展 - 触发: {should_trigger}, 原因: {reason}")
    assert should_trigger and reason == "stalled_progress", "长时间无进展应触发重规划"
    
    # 重置
    robot.memory.execution_stats['last_success_step'] = 10
    
    # 测试5: 效率过低应触发
    robot.memory.execution_stats['total_actions'] = 15
    robot.memory.execution_stats['success_count'] = 3  # 20%成功率
    
    should_trigger, reason = robot.should_trigger_replanning()
    print(f"低效率(3/15=20%) - 触发: {should_trigger}, 原因: {reason}")
    assert should_trigger and reason == "low_efficiency", "低效率应触发重规划"
    
    print("[PASS] 测试1通过: 重规划触发条件判断正确")
    print()


def test_reallocate_tasks():
    """测试重新任务分配功能"""
    print("=" * 60)
    print("测试 2: 重新任务分配")
    print("=" * 60)
    
    llm_client = MockLLMClient()
    
    robot = RobotAgent(
        name="Alice",
        robot_type="MobileManipulator",
        capabilities=["navigate", "pick", "place", "open"],
        llm_client=llm_client
    )
    
    # 存储自我介绍
    robot.memory.self_description = "Alice is a mobile manipulator with navigation and manipulation capabilities."
    
    # 准备测试数据
    task = "Put cup and toothbrush into tray"
    teammates = {
        "Bob": "Bob is a fixed manipulator with precise manipulation skills.",
        "David": "David is a mobile robot with navigation and exploration capabilities."
    }
    completed_objects = ["cup"]
    failed_objects = ["toothbrush"]
    execution_history = "Alice: 2/5 successful, 3 failures, 2 consecutive failures\nBob: 3/4 successful, 1 failure, 0 consecutive failures"
    
    # 调用重新分配方法
    plan, thought, campaign = robot.reallocate_tasks(
        task, teammates, completed_objects, failed_objects, execution_history
    )
    
    print(f"新计划: {plan}")
    print(f"思考过程: {thought[:100]}...")
    print(f"竞选演讲: {campaign[:100]}...")
    
    assert plan is not None, "应返回新计划"
    assert 'description' in plan, "计划应包含description字段"
    assert len(thought) > 0, "应有思考过程"
    assert len(campaign) > 0, "应有竞选演讲"
    
    print("[PASS] 测试2通过: 重新任务分配功能正常")
    print()


def test_memory_stats_update():
    """测试记忆模块统计更新"""
    print("=" * 60)
    print("测试 3: 记忆模块统计更新")
    print("=" * 60)
    
    memory = MemoryModule(max_history=10)
    
    # 模拟成功动作
    success_feedback = {
        'success': True,
        'message': 'Picked up cup successfully',
        'completed_object': 'cup'
    }
    memory.store_feedback(success_feedback)
    
    print(f"成功后的统计: {memory.execution_stats}")
    assert memory.execution_stats['success_count'] == 1
    assert memory.execution_stats['consecutive_failures'] == 0
    
    # 模拟失败动作
    failure_feedback = {
        'success': False,
        'message': 'Failed to pick toothbrush',
        'target_object': 'toothbrush',
        'error_type': 'invalid_target'
    }
    memory.store_feedback(failure_feedback)
    
    print(f"失败后的统计: {memory.execution_stats}")
    assert memory.execution_stats['failure_count'] == 1
    assert memory.execution_stats['consecutive_failures'] == 1
    assert memory.task_progress['failed_attempts']['toothbrush'] == 1
    
    # 多次失败同一对象
    memory.store_feedback(failure_feedback)
    memory.store_feedback(failure_feedback)
    
    print(f"3次失败后的统计: {memory.execution_stats}")
    assert memory.task_progress['failed_attempts']['toothbrush'] == 3
    
    print("[PASS] 测试3通过: 记忆模块统计更新正确")
    print()


def test_coordinator_replanning_trigger():
    """测试协调器中的重规划触发逻辑"""
    print("=" * 60)
    print("测试 4: 协调器重规划触发")
    print("=" * 60)
    
    llm_client = MockLLMClient()
    
    # 创建多个机器人
    robots = [
        RobotAgent("Alice", "MobileManipulator", ["navigate", "pick", "place"], llm_client),
        RobotAgent("Bob", "FixedManipulator", ["pick", "place"], llm_client),
        RobotAgent("David", "MobileRobot", ["navigate", "explore"], llm_client)
    ]
    
    # 存储自我介绍
    for robot in robots:
        robot.memory.self_description = f"{robot.name} is ready to help."
    
    # 创建协调器
    coordinator = DynaHMRC_Coordinator(robots, reflection_interval=5, max_steps=20, use_simulator=False)
    
    # 模拟执行历史 - 让Alice触发重规划条件
    alice = coordinator.robots['Alice']
    for i in range(4):
        alice.memory.execution_stats['total_actions'] += 1
        alice.memory.execution_stats['failure_count'] += 1
        alice.memory.execution_stats['consecutive_failures'] += 1
    
    print(f"Alice的执行统计: {alice.memory.execution_stats}")
    
    # 检查是否触发重规划
    need_replanning = False
    replanning_reason = ""
    
    for name, robot in coordinator.robots.items():
        should_trigger, reason = robot.should_trigger_replanning()
        if should_trigger:
            need_replanning = True
            replanning_reason = reason
            print(f"[REPLANNING TRIGGERED] Robot {name} suggests replanning: {reason}")
            break
    
    assert need_replanning, "应触发重规划"
    assert replanning_reason == "consecutive_failures", "触发原因应为连续失败"
    
    print("[PASS] 测试4通过: 协调器重规划触发逻辑正确")
    print()


def test_replanning_integration():
    """测试完整的重规划集成流程"""
    print("=" * 60)
    print("测试 5: 完整重规划集成流程")
    print("=" * 60)
    
    llm_client = MockLLMClient()
    
    robots = [
        RobotAgent("Alice", "MobileManipulator", ["navigate", "pick", "place"], llm_client),
        RobotAgent("Bob", "FixedManipulator", ["pick", "place"], llm_client),
    ]
    
    for robot in robots:
        robot.memory.self_description = f"{robot.name} is a capable robot."
    
    coordinator = DynaHMRC_Coordinator(robots, reflection_interval=5, max_steps=10, use_simulator=False)
    
    # 收集执行历史信息（模拟重规划流程中的数据收集）
    alice = coordinator.robots['Alice']
    bob = coordinator.robots['Bob']
    
    # 模拟一些执行历史
    alice.memory.task_progress['completed_objects'] = ['cup']
    alice.memory.task_progress['failed_attempts']['toothbrush'] = 3
    alice.memory.execution_stats = {
        'total_actions': 8,
        'success_count': 2,
        'failure_count': 6,
        'consecutive_failures': 3,
        'last_success_step': 5
    }
    
    bob.memory.execution_stats = {
        'total_actions': 5,
        'success_count': 4,
        'failure_count': 1,
        'consecutive_failures': 0,
        'last_success_step': 5
    }
    
    # 收集数据
    completed_objects = []
    failed_objects = []
    execution_history = ""
    
    for name, robot in coordinator.robots.items():
        completed_objects.extend(robot.memory.task_progress['completed_objects'])
        failed_objects.extend(robot.memory.task_progress['failed_attempts'].keys())
        
        stats = robot.memory.execution_stats
        history = f"{name}: {stats['success_count']}/{stats['total_actions']} successful, "
        history += f"{stats['failure_count']} failures, "
        history += f"{stats['consecutive_failures']} consecutive failures"
        execution_history += history + "\n"
    
    # 去重
    completed_objects = list(set(completed_objects))
    failed_objects = list(set(failed_objects))
    
    print(f"已完成对象: {completed_objects}")
    print(f"失败对象: {failed_objects}")
    print(f"执行历史:\n{execution_history}")
    
    # 验证数据收集正确
    assert 'cup' in completed_objects, "应包含已完成对象"
    assert 'toothbrush' in failed_objects, "应包含失败对象"
    assert 'Alice' in execution_history, "应包含Alice的执行历史"
    
    print("[PASS] 测试5通过: 完整重规划集成流程数据收集正确")
    print()


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("动态重规划功能测试套件")
    print("=" * 60 + "\n")
    
    try:
        test_should_trigger_replanning()
        test_reallocate_tasks()
        test_memory_stats_update()
        test_coordinator_replanning_trigger()
        test_replanning_integration()
        
        print("=" * 60)
        print("[PASS] 所有测试通过!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"[FAIL] 测试失败: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
