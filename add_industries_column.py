#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据库迁移脚本：添加industries字段到policy_events表
"""

import sqlite3

def add_industries_column(db_path='events.db'):
    """添加industries字段到policy_events表"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查industries字段是否已存在
        cursor.execute("PRAGMA table_info(policy_events)")
        columns = cursor.fetchall()
        column_names = [col[1] for col in columns]
        
        if 'industries' in column_names:
            print("industries字段已存在，无需添加")
            return
        
        print("正在添加industries字段...")
        
        # 添加industries字段
        cursor.execute("""
            ALTER TABLE policy_events 
            ADD COLUMN industries TEXT DEFAULT ''
        """)
        
        # 同时添加content和ai_analysis字段（如果不存在）
        if 'content' not in column_names:
            print("正在添加content字段...")
            cursor.execute("""
                ALTER TABLE policy_events 
                ADD COLUMN content TEXT DEFAULT ''
            """)
        
        if 'ai_analysis' not in column_names:
            print("正在添加ai_analysis字段...")
            cursor.execute("""
                ALTER TABLE policy_events 
                ADD COLUMN ai_analysis TEXT DEFAULT ''
            """)
        
        conn.commit()
        print("✓ 字段添加成功")
        
        # 验证添加结果
        cursor.execute("PRAGMA table_info(policy_events)")
        columns = cursor.fetchall()
        print("\n更新后的表结构:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        conn.close()
        
    except Exception as e:
        print(f"添加字段时出错: {e}")
        if conn:
            conn.rollback()
            conn.close()

if __name__ == '__main__':
    add_industries_column()