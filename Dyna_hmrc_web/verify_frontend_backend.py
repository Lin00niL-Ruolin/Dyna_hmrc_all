#!/usr/bin/env python3
"""验证前端和后端示例任务定义是否一致"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dynahmrc_web'))

from dynahmrc.task_analyzer import TASK_EXAMPLES

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', 'ignore').decode('gbk'))

def main():
    safe_print("=" * 100)
    safe_print("后端 TASK_EXAMPLES 定义")
    safe_print("=" * 100)
    
    for category_key, category in TASK_EXAMPLES.items():
        safe_print(f"\n【{category['name']}】({category_key})")
        safe_print("-" * 80)
        
        for i, example in enumerate(category['examples'], 1):
            safe_print(f"\n  {i}. 任务: {example['task']}")
            safe_print(f"     level: {example['level']}")
            safe_print(f"     label: {example['label']}")
    
    safe_print("\n" + "=" * 100)
    safe_print("请与前端 chat.html 中的 taskExamples 定义对比")
    safe_print("=" * 100)

if __name__ == "__main__":
    main()
