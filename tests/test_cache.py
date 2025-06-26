import sqlite3
import pandas as pd
from datetime import datetime

# 测试数据库缓存功能
def test_stock_cache():
    print("=== 测试股票数据库缓存功能 ===")
    
    # 连接数据库
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()
    
    # 检查stock_kline表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stock_kline'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        print("✓ stock_kline表已创建")
        
        # 检查表结构
        cursor.execute("PRAGMA table_info(stock_kline)")
        columns = cursor.fetchall()
        print("\n表结构:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
        
        # 检查数据
        cursor.execute("SELECT COUNT(*) FROM stock_kline")
        count = cursor.fetchone()[0]
        print(f"\n当前数据条数: {count}")
        
        if count > 0:
            # 显示最新的几条数据
            cursor.execute("""
                SELECT stock_code, date, open, close, high, low, volume 
                FROM stock_kline 
                ORDER BY stock_code, date DESC 
                LIMIT 5
            """)
            recent_data = cursor.fetchall()
            print("\n最新数据样例:")
            for row in recent_data:
                print(f"  {row[0]} | {row[1]} | O:{row[2]} C:{row[3]} H:{row[4]} L:{row[5]} V:{row[6]}")
            
            # 检查各股票的数据情况
            cursor.execute("""
                SELECT stock_code, COUNT(*) as count, MIN(date) as start_date, MAX(date) as end_date
                FROM stock_kline 
                GROUP BY stock_code
            """)
            stock_summary = cursor.fetchall()
            print("\n各股票数据汇总:")
            for row in stock_summary:
                print(f"  {row[0]}: {row[1]}条数据, 从{row[2]}到{row[3]}")
        else:
            print("数据库中暂无股票数据")
    else:
        print("✗ stock_kline表不存在")
    
    conn.close()
    print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_stock_cache()