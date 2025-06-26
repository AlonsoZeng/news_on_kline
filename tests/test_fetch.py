import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# 导入必要的模块
import pandas as pd
import tushare as ts
import sqlite3
from datetime import datetime, date
import json
import os

# 从app.py导入相关函数
from app import (
    fetch_stock_kline_data, 
    get_stock_kline_from_db, 
    save_stock_kline_to_db,
    get_latest_stock_date_from_db
)

def test_fetch_function():
    print("=== 测试fetch_stock_kline_data函数 ===")
    
    try:
        # 测试获取茅台股票数据
        stock_code = '600519'
        print(f"\n正在测试获取 {stock_code} 的数据...")
        
        result = fetch_stock_kline_data(stock_code)
        
        if result is not None and not result.empty:
            print(f"✓ 成功获取到 {len(result)} 条数据")
            print("\n数据样例:")
            print(result.head())
            print("\n数据日期范围:")
            print(f"从 {result['date'].min()} 到 {result['date'].max()}")
        else:
            print("✗ 未获取到数据")
            
    except Exception as e:
        print(f"✗ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_fetch_function()