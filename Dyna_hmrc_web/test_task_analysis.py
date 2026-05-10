#!/usr/bin/env python3
"""测试示例任务的分析结果"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dynahmrc_web'))

# 直接导入
from dynahmrc.task_analyzer import TaskAnalyzer, TASK_EXAMPLES

def safe_print(text):
    """安全打印，处理编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', 'ignore').decode('gbk'))

def test_examples():
    analyzer = TaskAnalyzer()
    
    safe_print("=" * 80)
    safe_print("测试示例任务分析")
    safe_print("=" * 80)
    
    for category_key, category in TASK_EXAMPLES.items():
        safe_print(f"\n{'='*60}")
        safe_print(f"任务类型: {category['name']}")
        safe_print(f"{'='*60}")
        
        for example in category['examples']:
            task = example['task']
            expected_level = example['level']
            expected_label = example['label']
            
            # 分析任务
            analysis = analyzer.analyze(task)
            
            # 提取位置信息用于调试
            locations = analyzer._extract_locations(task)
            
            # 检查是否匹配
            match = "OK" if analysis.complexity.value == expected_level else "FAIL"
            
            safe_print(f"\n[{match}] 任务: {task}")
            safe_print(f"   期望: {expected_level}")
            safe_print(f"   实际: {analysis.complexity.value}")
            safe_print(f"   D值: {analysis.D_value:.2f}")
            safe_print(f"   子任务数: {len(analysis.subtasks)}")
            safe_print(f"   L(位置): {analysis.location_factor:.2f}, N(数量): {analysis.quantity_factor:.2f}, Y(协作): {analysis.collaboration_factor:.2f}")
            safe_print(f"   提取位置: {locations}")

if __name__ == "__main__":
    test_examples()
