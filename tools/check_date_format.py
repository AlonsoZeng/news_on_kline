#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查数据库中的日期格式问题
"""

import sqlite3
from datetime import datetime

def check_date_formats():
    """检查数据库中的日期格式"""
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()
    
    # 检查policy_events表
    try:
        cursor.execute('SELECT date, title, source_url FROM policy_events LIMIT 20')
        rows = cursor.fetchall()
        
        print("=== 政策事件表中的日期样例 ===")
        print(f"总共检查 {len(rows)} 条记录")
        print()
        
        date_formats = {}
        
        for i, (date_str, title, url) in enumerate(rows, 1):
            print(f"{i:2d}. 日期: {date_str:12s} | 标题: {title[:40]}...")
            
            # 统计日期格式
            if date_str in date_formats:
                date_formats[date_str] += 1
            else:
                date_formats[date_str] = 1
        
        print("\n=== 日期格式统计 ===")
        for date_str, count in sorted(date_formats.items()):
            print(f"{date_str:12s}: {count} 条记录")
            
        # 检查所有记录的日期格式分布
        cursor.execute('SELECT date, COUNT(*) as count FROM policy_events GROUP BY date ORDER BY count DESC LIMIT 10')
        date_stats = cursor.fetchall()
        
        print("\n=== 最常见的日期值 (前10个) ===")
        for date_str, count in date_stats:
            print(f"{date_str:12s}: {count:4d} 条记录")
            
    except sqlite3.OperationalError as e:
        print(f"查询policy_events表失败: {e}")
        
        # 尝试查询events表
        try:
            cursor.execute('SELECT date, title FROM events LIMIT 10')
            rows = cursor.fetchall()
            
            print("\n=== events表中的日期样例 ===")
            for i, (date_str, title) in enumerate(rows, 1):
                print(f"{i:2d}. 日期: {date_str:12s} | 标题: {title[:40]}...")
                
        except sqlite3.OperationalError as e2:
            print(f"查询events表也失败: {e2}")
    
    conn.close()

if __name__ == "__main__":
    check_date_formats()