# bestman/dynahmrc/examples/demo_multi_robot.py
"""
Demo: Multi-Robot Collaboration with DynaHMRC
Compatible with BestMan simulation environment
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dynahmrc.coordinator import DynaHMRC_Coordinator
from dynahmrc.robots import MobileManipulatorRobot, ManipulatorRobot, MobileRobot, DroneRobot
from dynahmrc.tasks import PackObjectsTask
from dynahmrc.utils.llm_api import MockLLMClient, LLMClient
from dynahmrc.core.observation import ObservationModule
from dynahmrc.core.memory import MemoryModule
from dynahmrc.core.planner import PlanningModule
from dynahmrc.core.reflection import ReflectionModule
from dynahmrc.core.communication import CommunicationModule

def create_robot_with_modules(name, robot_type, llm_client, config):
    """Helper to create robot with all modules initialized"""
    
    # Create robot based on type
    if robot_type == "mobile_manipulation":
        robot = MobileManipulatorRobot(name, llm_client, config=config)
    elif robot_type == "manipulation":
        robot = ManipulatorRobot(name, llm_client, config=config)
    elif robot_type == "mobile":
        robot = MobileRobot(name, llm_client, config=config)
    elif robot_type == "drone":
        robot = DroneRobot(name, llm_client, config=config)
    else:
        raise ValueError(f"Unknown robot type: {robot_type}")
    
    # Initialize modules
    observation = ObservationModule(robot)
    memory = MemoryModule(max_history=10)
    planner = PlanningModule(llm_client, {})
    reflection = ReflectionModule(reflection_interval=10)
    communication = CommunicationModule(name)
    
    robot.initialize_modules(observation, memory, planner, reflection, communication)
    
    return robot

def demo_pack_objects():
    """Demo: Pack Objects task with 4 heterogeneous robots"""
    

    
    # Configuration
    config = {
        'max_steps': 50,
        'reflection_interval': 10,
        'temperature': 0.5
    }
    
    # Create LLM client (use Mock for demo without API key)
    # llm_client = LLMClient(provider="openai", model="gpt-4o")
    llm_client = MockLLMClient(scenario="pack_objects")
    
    # Create coordinator
    coordinator = DynaHMRC_Coordinator(config)
    
    # Create heterogeneous robot team (Ma-MoMa-Mo-UAV configuration)
    robots_config = [
        ("Alice", "mobile_manipulation"),
        ("Bob", "manipulation"),
        ("David", "mobile"),
        ("Lucy", "drone")
    ]
    
    for name, rtype in robots_config:
        robot = create_robot_with_modules(name, rtype, llm_client, config)
        coordinator.register_robot(robot)

    
    # Create task
    task = PackObjectsTask("pack_001", {
        'target_objects': ['apple', 'banana', 'book'],
        'target_container': 'tray',
        'max_steps': 50
    })
    coordinator.set_task(task)
    
    # Run collaboration
    result = coordinator.run_collaboration()
    
    # Print results
    print("\n" + "="*70)
    print("Collaboration Results")
    print("="*70)
    print(f"Success: {result['success']}")
    print(f"Total Actions: {result['metrics']['total_actions']}")
    print(f"Reflections: {result['metrics']['reflection_count']}")
    print(f"Steps: {coordinator.step_count}")

def demo_with_bestman_integration():
    """
    Demo with actual BestMan simulation
    This requires BestMan to be installed and running
    """
    try:
        # Import BestMan modules
        from bestman import BestMan
        from bestman.simulator import Simulator
        
        print("Initializing BestMan simulation...")
        
        # Create simulator (headless or GUI)
        sim = Simulator(
            render=True,
            background_color=[1.0, 1.0, 1.0],
            image_width=1280,
            image_height=720
        )
        
        # Create BestMan robots
        # Note: This is pseudo-code, actual BestMan API may differ
        bestman_alice = BestMan(
            sim,
            robot_name="Alice",
            robot_type="mobile_manipulation",
            base_pos=[0.5, 0.5, 0.0]
        )
        
        bestman_bob = BestMan(
            sim,
            robot_name="Bob",
            robot_type="manipulation",
            base_pos=[1.0, 1.0, 0.0]
        )
        
        # Create DynaHMRC agents with BestMan controllers
        llm_client = MockLLMClient()
        
        alice = MobileManipulatorRobot(
            "Alice", 
            llm_client, 
            bestman_robot=bestman_alice,
            config={'max_grasp_range': 0.8}
        )
        
        bob = ManipulatorRobot(
            "Bob",
            llm_client,
            bestman_robot=bestman_bob,
            config={'max_grasp_range': 0.5}
        )
        
        # Initialize modules and run...
        print("BestMan integration demo - to be implemented")
        
    except ImportError:
        print("BestMan not installed. Running pure simulation demo instead.")
        demo_pack_objects()

if __name__ == "__main__":
    # Run demo
    demo_pack_objects()
    
    # Uncomment to try BestMan integration (requires BestMan installed)
    # demo_with_bestman_integration()