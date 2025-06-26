#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查数据库表结构
"""

import sqlite3

def check_table_schema(db_path='events.db'):
    """检查policy_events表结构"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取表结构
        cursor.execute("PRAGMA table_info(policy_events)")
        columns = cursor.fetchall()
        
        print("policy_events表结构:")
        print("列名\t\t类型\t\t非空\t\t默认值\t\t主键")
        print("-" * 60)
        
        for col in columns:
            cid, name, type_, notnull, default, pk = col
            print(f"{name:<15}\t{type_:<10}\t{notnull}\t\t{default}\t\t{pk}")
        
        # 检查是否有industries字段
        column_names = [col[1] for col in columns]
        if 'industries' in column_names:
            print("\n✓ industries字段存在")
        else:
            print("\n✗ industries字段不存在")
            print("\n需要添加industries字段到表中")
        
        conn.close()
        
    except Exception as e:
        print(f"检查表结构时出错: {e}")

if __name__ == '__main__':
    check_table_schema()