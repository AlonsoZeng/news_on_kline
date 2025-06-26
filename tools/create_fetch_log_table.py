#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
创建数据源抓取日志表
"""

import sqlite3
from datetime import datetime

def create_fetch_log_table(db_path='events.db'):
    """创建数据源抓取日志表"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 创建数据源抓取日志表
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
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_log_source 
            ON fetch_log(source_name)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fetch_log_time 
            ON fetch_log(last_fetch_time)
        ''')
        
        conn.commit()
        conn.close()
        
        print("数据源抓取日志表创建成功")
        
    except Exception as e:
        print(f"创建表时出错: {e}")

if __name__ == '__main__':
    create_fetch_log_table()