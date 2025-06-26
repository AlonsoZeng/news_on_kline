#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接查看fetch_log表内容
"""

import sqlite3
import os

def check_fetch_log_table():
    """检查fetch_log表内容"""
    db_path = "policy_data.db"
    
    if not os.path.exists(db_path):
        print(f"数据库文件 {db_path} 不存在")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fetch_log'")
        table_exists = cursor.fetchone()
        
        if not table_exists:
            print("fetch_log表不存在")
            conn.close()
            return
        
        print("fetch_log表存在")
        
        # 查看表结构
        cursor.execute("PRAGMA table_info(fetch_log)")
        columns = cursor.fetchall()
        print("\n=== fetch_log表结构 ===")
        for col in columns:
            print(f"  {col[1]} {col[2]} {'NOT NULL' if col[3] else ''} {'PRIMARY KEY' if col[5] else ''}")
        
        # 查看所有记录
        cursor.execute("SELECT * FROM fetch_log ORDER BY last_fetch_time DESC")
        records = cursor.fetchall()
        
        print(f"\n=== fetch_log表内容 (共{len(records)}条记录) ===")
        if records:
            # 打印列名
            column_names = [desc[0] for desc in cursor.description]
            print(f"列名: {column_names}")
            print()
            
            for record in records:
                print(f"记录: {record}")
        else:
            print("表中无数据")
        
        conn.close()
        
    except Exception as e:
        print(f"检查fetch_log表时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_fetch_log_table()