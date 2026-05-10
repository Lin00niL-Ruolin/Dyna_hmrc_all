#!/usr/bin/env python3
"""测试协作类型判断"""

import sys
import os

# 添加路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dynahmrc_web'))

from dynahmrc.task_analyzer import TaskAnalyzer, TASK_EXAMPLES

def safe_print(text):
    """安全打印，处理编码问题"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', 'ignore').decode('gbk'))

def test_collab_type():
    analyzer = TaskAnalyzer()
    
    test_tasks = [
        '装箱：Put "cup" and "toothbrush" into tray.',
        '装箱：Put "cup", "remote" and "tableware" into tray.',
        '分类：Sort "tableware" and "cup" into different trays by category.',
        '制作三明治：Stack "bread" and "cheese" onto the tray in order.',
    ]
    
    safe_print("=" * 80)
    safe_print("测试协作类型判断")
    safe_print("=" * 80)
    
    for task in test_tasks:
        analysis = analyzer.analyze(task)
        
        safe_print(f"\n任务: {task}")
        safe_print(f"  物品数: {len(analysis.subtasks)}")
        safe_print(f"  多位置: 是" if len(analysis.subtasks) >= 2 else "  多位置: 否")
        safe_print(f"  协作类型: {analysis.collaboration_type.value}")
        safe_print(f"  协作类型(中文): {analyzer._get_collab_type_label(analysis.collaboration_type)}")
        safe_print(f"  需要协作: {'是' if analysis.collaboration_needed else '否'}")

if __name__ == "__main__":
    test_collab_type()
