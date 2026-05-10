#!/usr/bin/env python3
"""详细测试示例任务分析结果"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dynahmrc_web'))

from dynahmrc.task_analyzer import TaskAnalyzer, TASK_EXAMPLES

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', 'ignore').decode('gbk'))

def test_examples():
    analyzer = TaskAnalyzer()
    
    safe_print("=" * 100)
    safe_print("详细测试示例任务分析")
    safe_print("=" * 100)
    
    all_passed = True
    
    for category_key, category in TASK_EXAMPLES.items():
        safe_print(f"\n{'='*80}")
        safe_print(f"任务类型: {category['name']} ({category_key})")
        safe_print(f"{'='*80}")
        
        for example in category['examples']:
            task = example['task']
            expected_level = example['level']
            expected_label = example['label']
            
            analysis = analyzer.analyze(task)
            
            match = analysis.complexity.value == expected_level
            status = "✓ PASS" if match else "✗ FAIL"
            
            if not match:
                all_passed = False
            
            safe_print(f"\n{status} | 任务: {task}")
            safe_print(f"  期望复杂度: {expected_label} ({expected_level})")
            safe_print(f"  实际复杂度: {analyzer._get_complexity_label(analysis.complexity)} ({analysis.complexity.value})")
            safe_print(f"  D值: {analysis.D_value:.2f} (阈值: simple≤0.3, moderate≤0.6, complex≤0.85, very_complex>0.85)")
            safe_print(f"  三因子: L={analysis.location_factor:.2f}, N={analysis.quantity_factor:.2f}, Y={analysis.collaboration_factor:.2f}")
            safe_print(f"  协作需要: {analysis.collaboration_needed}, 推荐机器人: {analysis.recommended_robots}")
            safe_print(f"  子任务数: {len(analysis.subtasks)}")
            safe_print(f"  任务类型: {analysis.task_type.value}")
    
    safe_print(f"\n{'='*100}")
    if all_passed:
        safe_print("✓ 所有测试通过！")
    else:
        safe_print("✗ 存在不匹配的测试项")
    safe_print("=" * 100)

if __name__ == "__main__":
    test_examples()
