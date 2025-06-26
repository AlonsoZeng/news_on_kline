#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试政策数据抓取时间控制功能
"""

import sqlite3
import sys
import os
from datetime import datetime, timedelta

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from policy_data_fetcher import PolicyDataFetcher

def check_fetch_log():
    """检查抓取日志表"""
    db_path = "policy_data.db"
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询所有抓取记录
        cursor.execute('''
            SELECT source_name, last_fetch_time, fetch_status, 
                   error_message, records_fetched
            FROM fetch_log 
            ORDER BY last_fetch_time DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        print("=== 数据源抓取日志 ===")
        if not results:
            print("暂无抓取记录")
        else:
            for source_name, last_time, status, error_msg, records in results:
                print(f"数据源: {source_name}")
                print(f"  最后抓取时间: {last_time}")
                print(f"  抓取状态: {status}")
                print(f"  记录数量: {records}")
                if error_msg:
                    print(f"  错误信息: {error_msg[:100]}...")
                print()
                
    except Exception as e:
        print(f"查询抓取日志时出错: {e}")

def test_fetch_control():
    """测试抓取时间控制功能"""
    print("=== 测试抓取时间控制功能 ===")
    
    fetcher = PolicyDataFetcher()
    
    # 测试各个数据源的抓取控制
    sources = [
        ("gov_cn", "中国政府网"),
        ("mof", "财政部"),
        ("ndrc", "国家发改委"),
        ("csrc", "证监会")
    ]
    
    for source_name, source_desc in sources:
        print(f"\n--- 测试 {source_desc} ({source_name}) ---")
        
        # 检查是否应该跳过抓取
        should_skip = fetcher.should_skip_fetch(source_name, min_interval_hours=1)
        
        if should_skip:
            print(f"✓ {source_desc} 抓取被跳过（时间间隔不足1小时）")
        else:
            print(f"✓ {source_desc} 可以进行抓取")
            
            # 模拟记录抓取状态
            fetcher.record_fetch_status(source_name, 'success', 100)
            print(f"✓ 已记录 {source_desc} 抓取成功状态")

def simulate_fetch_scenarios():
    """模拟不同的抓取场景"""
    print("\n=== 模拟抓取场景 ===")
    
    fetcher = PolicyDataFetcher()
    
    # 场景1：模拟成功抓取
    print("\n场景1：模拟成功抓取")
    fetcher.record_fetch_status("test_source", 'success', 50)
    
    # 立即检查是否应该跳过
    should_skip = fetcher.should_skip_fetch("test_source", min_interval_hours=1)
    print(f"立即再次抓取是否跳过: {should_skip}")
    
    # 场景2：模拟失败抓取
    print("\n场景2：模拟失败抓取")
    fetcher.record_fetch_status("test_source_error", 'error', 0, "网络连接超时")
    
    # 立即检查是否应该跳过
    should_skip = fetcher.should_skip_fetch("test_source_error", min_interval_hours=1)
    print(f"失败后立即再次抓取是否跳过: {should_skip}")
    
    # 场景3：测试不同的时间间隔
    print("\n场景3：测试不同时间间隔")
    should_skip_30min = fetcher.should_skip_fetch("test_source", min_interval_hours=0.5)
    should_skip_2hour = fetcher.should_skip_fetch("test_source", min_interval_hours=2)
    print(f"30分钟间隔是否跳过: {should_skip_30min}")
    print(f"2小时间隔是否跳过: {should_skip_2hour}")

if __name__ == "__main__":
    print("政策数据抓取时间控制功能测试")
    print("=" * 50)
    
    # 检查现有抓取日志
    check_fetch_log()
    
    # 测试抓取控制功能
    test_fetch_control()
    
    # 模拟不同抓取场景
    simulate_fetch_scenarios()
    
    # 再次检查抓取日志
    print("\n=== 测试后的抓取日志 ===")
    check_fetch_log()
    
    print("\n测试完成！")