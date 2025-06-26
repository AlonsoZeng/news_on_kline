#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查证监会数据抓取结果
"""

import sqlite3
from datetime import datetime

def check_csrc_data(db_path='events.db'):
    """检查证监会数据抓取结果"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 查询证监会相关数据
        cursor.execute("""
            SELECT COUNT(*) as total_count 
            FROM policy_events 
            WHERE department = '证监会'
        """)
        total_count = cursor.fetchone()[0]
        
        print(f"证监会政策数据总数: {total_count} 条")
        
        # 按事件类型统计
        cursor.execute("""
            SELECT event_type, COUNT(*) as count 
            FROM policy_events 
            WHERE department = '证监会'
            GROUP BY event_type
            ORDER BY count DESC
        """)
        
        print("\n按事件类型统计:")
        print("-" * 40)
        for row in cursor.fetchall():
            event_type, count = row
            print(f"{event_type:<20}: {count} 条")
        
        # 查看最新的10条数据
        cursor.execute("""
            SELECT date, title, event_type, department
            FROM policy_events 
            WHERE department = '证监会'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        
        print("\n最新的10条证监会数据:")
        print("-" * 80)
        for row in cursor.fetchall():
            date, title, event_type, department = row
            print(f"{date} | {event_type:<12} | {title[:50]}...")
        
        # 按日期统计最近的数据
        cursor.execute("""
            SELECT date, COUNT(*) as count 
            FROM policy_events 
            WHERE department = '证监会'
            GROUP BY date
            ORDER BY date DESC
            LIMIT 10
        """)
        
        print("\n按日期统计(最近10天):")
        print("-" * 30)
        for row in cursor.fetchall():
            date, count = row
            print(f"{date}: {count} 条")
        
        conn.close()
        
    except Exception as e:
        print(f"检查数据时出错: {e}")

if __name__ == '__main__':
    check_csrc_data()