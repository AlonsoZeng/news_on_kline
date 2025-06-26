#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sqlite3
import os

def check_and_clean_database():
    """检查并清理数据库中的模拟数据"""
    db_path = 'events.db'
    
    if not os.path.exists(db_path):
        print("数据库文件不存在")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查events表
        print("=== 检查events表 ===")
        cursor.execute('SELECT COUNT(*) FROM events')
        events_count = cursor.fetchone()[0]
        print(f'events表总数: {events_count}')
        
        if events_count > 0:
            cursor.execute('SELECT date, title, event_type FROM events ORDER BY date LIMIT 10')
            print('events表前10条:')
            for row in cursor.fetchall():
                print(f'  {row[0]}: {row[1]} ({row[2]})')
        
        # 检查policy_events表
        print("\n=== 检查policy_events表 ===")
        try:
            cursor.execute('SELECT COUNT(*) FROM policy_events')
            policy_count = cursor.fetchone()[0]
            print(f'policy_events表总数: {policy_count}')
            
            if policy_count > 0:
                cursor.execute('SELECT date, title, event_type, source_url FROM policy_events ORDER BY date LIMIT 10')
                print('policy_events表前10条:')
                for row in cursor.fetchall():
                    source = row[3] if row[3] else "无来源"
                    print(f'  {row[0]}: {row[1]} ({row[2]}) - {source}')
        except sqlite3.OperationalError:
            print('policy_events表不存在')
            policy_count = 0
        
        # 分析数据来源
        print("\n=== 数据来源分析 ===")
        
        # 检查events表中的模拟数据特征
        if events_count > 0:
            cursor.execute("SELECT COUNT(*) FROM events WHERE title LIKE '%测试%' OR title LIKE '%模拟%' OR title LIKE '%示例%'")
            mock_events = cursor.fetchone()[0]
            print(f'events表中疑似模拟数据: {mock_events}条')
            
            # 显示疑似模拟数据
            if mock_events > 0:
                cursor.execute("SELECT date, title, event_type FROM events WHERE title LIKE '%测试%' OR title LIKE '%模拟%' OR title LIKE '%示例%' LIMIT 5")
                print('疑似模拟数据示例:')
                for row in cursor.fetchall():
                    print(f'  {row[0]}: {row[1]} ({row[2]})')
        
        # 检查policy_events表中的真实数据
        if policy_count > 0:
            cursor.execute("SELECT COUNT(*) FROM policy_events WHERE source_url IS NOT NULL AND source_url != ''")
            real_policy_data = cursor.fetchone()[0]
            print(f'policy_events表中有来源URL的真实数据: {real_policy_data}条')
        
        # 询问是否删除模拟数据
        print("\n=== 清理建议 ===")
        if events_count > 0:
            print("建议操作:")
            print("1. 保留policy_events表中的真实政策数据")
            print("2. 清空events表中的模拟数据")
            
            confirm = input("\n是否执行清理操作？(y/N): ")
            if confirm.lower() == 'y':
                # 清空events表
                cursor.execute('DELETE FROM events')
                conn.commit()
                print("已清空events表中的模拟数据")
                
                # 重新检查
                cursor.execute('SELECT COUNT(*) FROM events')
                remaining_events = cursor.fetchone()[0]
                print(f'清理后events表剩余数据: {remaining_events}条')
            else:
                print("取消清理操作")
        else:
            print("events表已为空，无需清理")
            
    except Exception as e:
        print(f"操作出错: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    check_and_clean_database()