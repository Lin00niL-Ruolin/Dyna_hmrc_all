#!/usr/bin/env python3
"""
测试解析逻辑的修复
"""

import sys
sys.path.append('dynahmrc_web')

from dynahmrc_architecture import RobotAgent
from dynahmrc.utils.llm_api import MockLLMClient

# 创建MockLLM客户端
llm_client = MockLLMClient()

# 创建测试机器人
robot = RobotAgent(
    name="TestRobot",
    robot_type="MobileManipulation",
    capabilities=["navigate", "open", "pick", "place", "move", "communicate", "wait"],
    llm_client=llm_client
)

task = "将桌子上的杯子移动到柜子里"

print("=== 测试自我描述阶段 ===")
thought, description = robot.self_describe(task)
print(f"Thought: {thought}")
print(f"Description: {description}")
print()

print("=== 测试任务分配阶段 ===")
teammates = {"Alice": "I'm Alice, a mobile manipulation robot"}
plan, thought, campaign = robot.propose_allocation(task, teammates)
print(f"Plan: {plan}")
print(f"Thought: {thought}")
print(f"Campaign: {campaign}")
print()

print("=== 测试领导选举阶段 ===")
proposals = {
    "Alice": ({"description": "Alice's plan"}, "Alice's thought", "Alice's campaign"),
    "Bob": ({"description": "Bob's plan"}, "Bob's thought", "Bob's campaign")
}
vote_for, thought, reasoning = robot.vote_leader(proposals)
print(f"Vote for: {vote_for}")
print(f"Thought: {thought}")
print(f"Reasoning: {reasoning}")
print()

print("测试完成！")
