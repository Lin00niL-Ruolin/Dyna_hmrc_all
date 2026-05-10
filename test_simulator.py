#!/usr/bin/env python
"""
测试场景模拟器
"""

from dynahmrc.scene_simulator import SceneSimulator

def test_simulator():
    """测试场景模拟器的各种功能"""
    
    print("=" * 60)
    print("场景模拟器测试")
    print("=" * 60)
    
    # 创建模拟器
    sim = SceneSimulator(room_size=(10.0, 10.0))
    
    # 添加机器人
    sim.add_robot("Alice", "MobileManipulation", max_range=1.0, max_speed=0.5)
    sim.add_robot("Bob", "Manipulator", max_range=0.8, max_speed=0.0)
    sim.add_robot("David", "Mobile", max_range=1.0, max_speed=0.8)
    
    print("\n1. 初始化机器人")
    for name, robot in sim.robots.items():
        print(f"   {name}: 位置={robot.position}, 最大速度={robot.max_speed}m/s, 操作范围={robot.max_range}m")
    
    # 初始化默认场景
    print("\n2. 初始化场景")
    sim.initialize_default_scene(object_names=['apple', 'book', 'cup', 'keys'])
    
    print("\n   家具:")
    for name, furn in sim.furniture.items():
        print(f"      {name}: 位置={furn.position}")
    
    print("\n   物体:")
    for name, obj in sim.objects.items():
        print(f"      {name}: 位置={obj.position}, 状态={obj.state}")
    
    # 测试导航
    print("\n3. 测试导航")
    target_obj = 'apple'
    if target_obj in sim.objects:
        target_pos = sim.objects[target_obj].position
        print(f"\n   Alice 导航到 {target_obj} ({target_pos})")
        result = sim.navigate('Alice', target_pos)
        print(f"      结果: {result['message']}")
        print(f"      移动距离: {result.get('distance_moved', 0):.2f}m")
        print(f"      发现物体: {result.get('found_objects', [])}")
        print(f"      剩余距离: {result.get('remaining_distance', 0):.2f}m")
    
    # 测试距离计算
    print("\n4. 测试距离计算")
    alice_pos = sim.robots['Alice'].position
    apple_pos = sim.objects['apple'].position
    distance = sim.get_distance(alice_pos, apple_pos)
    print(f"   Alice 到 apple 的距离: {distance:.2f}m")
    
    reachable, dist = sim.is_reachable('Alice', apple_pos)
    print(f"   是否可达: {reachable}, 距离: {dist:.2f}m")
    
    # 继续导航直到到达
    print("\n5. 继续导航直到到达目标")
    step = 1
    while result.get('remaining_distance', 0) > 0.5 and step < 10:
        result = sim.navigate('Alice', target_pos)
        print(f"   步骤 {step}: 移动 {result.get('distance_moved', 0):.2f}m, 剩余 {result.get('remaining_distance', 0):.2f}m")
        step += 1
    
    # 测试拾取
    print("\n6. 测试拾取")
    result = sim.pick('Alice', 'apple')
    print(f"   结果: {result['message']}")
    print(f"   成功: {result.get('success', False)}")
    
    if result.get('success'):
        print(f"   Alice 持有的物体: {sim.robots['Alice'].holding_object}")
        print(f"   apple 状态: {sim.objects['apple'].state}")
    
    # 测试放置
    print("\n7. 测试放置")
    result = sim.place('Alice', 'table')
    print(f"   结果: {result['message']}")
    print(f"   成功: {result.get('success', False)}")
    
    if result.get('success'):
        print(f"   Alice 持有的物体: {sim.robots['Alice'].holding_object}")
        print(f"   apple 新位置: {sim.objects['apple'].position}")
        print(f"   apple 状态: {sim.objects['apple'].state}")
    
    # 获取场景图
    print("\n8. 获取场景图（用于LLM）")
    scene_graph = sim.get_scene_graph()
    for name, info in scene_graph.items():
        print(f"   {name}: {info}")
    
    # 获取机器人状态
    print("\n9. 获取机器人状态")
    robot_states = sim.get_all_robot_states()
    for name, state in robot_states.items():
        print(f"   {name}: 位置={state['position']}, 持有={state['holding']}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)

if __name__ == '__main__':
    test_simulator()
