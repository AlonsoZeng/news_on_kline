#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试数据库初始化问题
"""

import sqlite3
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_database_init():
    """调试数据库初始化"""
    db_path = "policy_data.db"
    
    print(f"当前工作目录: {os.getcwd()}")
    print(f"数据库路径: {os.path.abspath(db_path)}")
    
    # 删除现有数据库文件（如果存在）
    if os.path.exists(db_path):
        print(f"删除现有数据库文件: {db_path}")
        os.remove(db_path)
    
    try:
        print("开始创建数据库连接...")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("创建policy_events表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS policy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                event_type TEXT NOT NULL,
                content TEXT,
                source_url TEXT,
                department TEXT,
                policy_level TEXT,
                impact_level TEXT,
                content_type TEXT DEFAULT '政策',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("policy_events表创建完成")
        
        print("创建fetch_log表...")
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL UNIQUE,
                last_fetch_time TIMESTAMP NOT NULL,
                fetch_status TEXT NOT NULL DEFAULT 'success',
                error_message TEXT,
                records_fetched INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("fetch_log表创建完成")
        
        print("创建索引...")
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_log_source 
            ON fetch_log(source_name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_log_time 
            ON fetch_log(last_fetch_time)
        ''')
        print("索引创建完成")
        
        print("提交事务...")
        conn.commit()
        
        print("检查创建的表...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"数据库中的表: {[t[0] for t in tables]}")
        
        print("关闭数据库连接...")
        conn.close()
        
        print("数据库初始化完成！")
        
        # 再次验证
        print("\n=== 验证数据库 ===")
        conn2 = sqlite3.connect(db_path)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables2 = cursor2.fetchall()
        print(f"验证 - 数据库中的表: {[t[0] for t in tables2]}")
        conn2.close()
        
    except Exception as e:
        print(f"数据库初始化失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_database_init()