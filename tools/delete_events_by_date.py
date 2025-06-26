#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除指定日期的事件数据
"""

import sqlite3
import os
from datetime import datetime

def delete_events_by_dates(db_path='events.db', dates_to_delete=None):
    """
    删除指定日期的事件数据
    
    Args:
        db_path: 数据库文件路径
        dates_to_delete: 要删除的日期列表，格式为 ['2025-06-23', '2025-06-24']
    """
    if dates_to_delete is None:
        dates_to_delete = ['2025-06-23', '2025-06-24']
    
    if not os.path.exists(db_path):
        print(f"错误：数据库文件 {db_path} 不存在")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        total_deleted_policy = 0
        total_deleted_events = 0
        
        for date in dates_to_delete:
            print(f"正在删除日期 {date} 的数据...")
            
            # 先查询要删除的记录数量
            cursor.execute("SELECT COUNT(*) FROM policy_events WHERE date = ?", (date,))
            policy_count = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM events WHERE date = ?", (date,))
            events_count = cursor.fetchone()[0]
            
            print(f"  policy_events表中找到 {policy_count} 条记录")
            print(f"  events表中找到 {events_count} 条记录")
            
            # 删除policy_events表中的数据
            cursor.execute("DELETE FROM policy_events WHERE date = ?", (date,))
            deleted_policy = cursor.rowcount
            
            # 删除events表中的数据
            cursor.execute("DELETE FROM events WHERE date = ?", (date,))
            deleted_events = cursor.rowcount
            
            total_deleted_policy += deleted_policy
            total_deleted_events += deleted_events
            
            print(f"  实际删除：policy_events表 {deleted_policy} 条，events表 {deleted_events} 条")
        
        # 提交事务
        conn.commit()
        
        print(f"\n删除完成！")
        print(f"总计删除：policy_events表 {total_deleted_policy} 条，events表 {total_deleted_events} 条")
        
        # 验证删除结果
        print("\n验证删除结果：")
        for date in dates_to_delete:
            cursor.execute("SELECT COUNT(*) FROM policy_events WHERE date = ?", (date,))
            remaining_policy = cursor.fetchone()[0]
            
            cursor.execute("SELECT COUNT(*) FROM events WHERE date = ?", (date,))
            remaining_events = cursor.fetchone()[0]
            
            print(f"  {date}: policy_events表剩余 {remaining_policy} 条，events表剩余 {remaining_events} 条")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"删除过程中发生错误：{str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def main():
    """
    主函数
    """
    print("开始删除events数据库中2025-06-23和2025-06-24的数据...")
    print("="*50)
    
    # 要删除的日期
    dates_to_delete = ['2025-06-23', '2025-06-24']
    
    # 执行删除
    success = delete_events_by_dates('events.db', dates_to_delete)
    
    if success:
        print("\n✅ 删除操作成功完成！")
    else:
        print("\n❌ 删除操作失败！")

if __name__ == '__main__':
    main()