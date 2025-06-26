#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强制抓取测试，验证时间控制功能
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from policy_data_fetcher import PolicyDataFetcher

def force_fetch_test():
    """强制抓取测试"""
    print("=== 强制抓取测试 ===")
    
    fetcher = PolicyDataFetcher()
    
    # 手动记录一些抓取状态来模拟之前的抓取
    print("\n1. 手动记录抓取状态...")
    fetcher.record_fetch_status("gov_cn", 'success', 150)
    fetcher.record_fetch_status("mof", 'success', 80)
    fetcher.record_fetch_status("ndrc", 'success', 45)
    fetcher.record_fetch_status("csrc", 'success', 120)
    
    print("已记录所有数据源的成功抓取状态")
    
    # 检查抓取日志
    print("\n2. 检查抓取日志...")
    import sqlite3
    conn = sqlite3.connect("policy_data.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT source_name, last_fetch_time, fetch_status, records_fetched
        FROM fetch_log 
        ORDER BY last_fetch_time DESC
    ''')
    
    results = cursor.fetchall()
    for source_name, last_time, status, records in results:
        print(f"  {source_name}: {last_time} - {status} - {records}条记录")
    
    conn.close()
    
    # 测试跳过逻辑
    print("\n3. 测试跳过逻辑...")
    sources = ["gov_cn", "mof", "ndrc", "csrc"]
    
    for source in sources:
        should_skip = fetcher.should_skip_fetch(source, min_interval_hours=1)
        print(f"  {source}: {'跳过' if should_skip else '可以抓取'}")
    
    # 测试不同时间间隔
    print("\n4. 测试不同时间间隔...")
    for hours in [0.5, 1, 2]:
        print(f"\n  {hours}小时间隔:")
        for source in sources:
            should_skip = fetcher.should_skip_fetch(source, min_interval_hours=hours)
            print(f"    {source}: {'跳过' if should_skip else '可以抓取'}")
    
    # 模拟运行数据收集
    print("\n5. 模拟运行数据收集...")
    try:
        # 这应该会跳过所有数据源
        policies = fetcher.fetch_all_policies(max_pages=1)
        print(f"抓取结果: {len(policies)}条政策")
    except Exception as e:
        print(f"抓取过程出错: {e}")
    
    print("\n测试完成！")

if __name__ == "__main__":
    force_fetch_test()