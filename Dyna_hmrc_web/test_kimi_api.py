#!/usr/bin/env python3
"""
Kimi API 测试脚本
用于验证API连接和调用是否正常
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dynahmrc_web.dynahmrc.utils.llm_api import KimiLLMClient

def test_api_connection():
    """测试API连接"""
    print("=" * 60)
    print("🧪 Testing Kimi API Connection")
    print("=" * 60)
    
    # 获取API Key
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        print("❌ Error: MOONSHOT_API_KEY environment variable not set")
        print("   Please set it with: export MOONSHOT_API_KEY='your-api-key'")
        return False
    
    print(f"✓ API Key found: {api_key[:8]}...{api_key[-4:]}")
    
    try:
        # 初始化客户端
        print("\n[1] Initializing KimiLLMClient...")
        client = KimiLLMClient(
            api_key=api_key,
            model="kimi-k2.5",
            temperature=0.3,
            max_tokens=500
        )
        print("✓ Client initialized successfully")
        
        # 测试简单对话
        print("\n[2] Testing simple completion...")
        messages = [
            {"role": "user", "content": "Hello! Please respond with 'API test successful' if you receive this message."}
        ]
        
        response = client.complete(messages)
        print(f"✓ Response received: {response[:100]}...")
        
        # 测试复杂对话（机器人场景）
        print("\n[3] Testing robot collaboration scenario...")
        task_prompt = """You are Alice, a Mobile Manipulation Robot.
Task: Collect cups from the living room and kitchen.
Available actions: navigate, open, pick, place, move, communicate, wait.

What is your next action? Please respond in JSON format:
{
    "thought": "your reasoning",
    "action": {"type": "action_name", "target": "target_name"}
}"""
        
        messages = [{"role": "user", "content": task_prompt}]
        response = client.complete(messages)
        print(f"✓ Robot scenario response: {response[:200]}...")
        
        # 测试流式输出
        print("\n[4] Testing streaming completion...")
        messages = [{"role": "user", "content": "Count from 1 to 5"}]
        
        print("   Streaming response: ", end="", flush=True)
        for chunk in client.stream_complete(messages):
            print(chunk, end="", flush=True)
        print(" ✓")
        
        print("\n" + "=" * 60)
        print("✅ All tests passed! Kimi API is working correctly.")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_with_app():
    """测试应用中的API调用"""
    print("\n" + "=" * 60)
    print("🧪 Testing API Integration in Application")
    print("=" * 60)
    
    try:
        # 导入应用模块
        print("\n[1] Importing application modules...")
        from dynahmrc_web.dynahmrc_architecture import RobotAgent, DynaHMRC_Coordinator
        print("✓ Modules imported")
        
        # 获取API Key
        api_key = os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            print("❌ MOONSHOT_API_KEY not set")
            return False
        
        # 创建LLM客户端
        print("\n[2] Creating LLM client...")
        client = KimiLLMClient(api_key=api_key)
        print("✓ LLM client created")
        
        # 创建一个机器人进行测试
        print("\n[3] Creating test robot agent...")
        robot = RobotAgent(
            name="TestAlice",
            robot_type="MobileManipulation",
            capabilities=["navigate", "open", "pick", "place", "move", "communicate", "wait"],
            llm_client=client,
            avatar="🚗"
        )
        print("✓ Robot agent created")
        
        # 测试自我介绍阶段
        print("\n[4] Testing self-description phase...")
        description = robot.self_describe()
        print(f"✓ Self-description: {description[:150]}...")
        
        # 测试观察
        print("\n[5] Testing observation...")
        scene_graph = {
            "kitchen_table": {"type": "furniture", "contains": ["cup"]},
            "sofa": {"type": "furniture", "contains": ["remote"]}
        }
        observation = robot.observe(scene_graph)
        print(f"✓ Observation: {str(observation)[:150]}...")
        
        print("\n" + "=" * 60)
        print("✅ Application integration test passed!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    # 设置日志级别
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("\n" + "🚀 " * 20)
    print("Kimi API Testing Suite")
    print("🚀 " * 20 + "\n")
    
    # 运行测试
    success1 = test_api_connection()
    success2 = test_with_app()
    
    print("\n" + "=" * 60)
    if success1 and success2:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("⚠️  SOME TESTS FAILED")
        if not success1:
            print("   - API connection test failed")
        if not success2:
            print("   - Application integration test failed")
    print("=" * 60)
