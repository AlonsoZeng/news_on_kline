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
import time

# 从app.py导入相关函数
from app import (
    fetch_stock_kline_data, 
    get_stock_kline_from_db, 
    get_latest_stock_date_from_db
)

def test_cache_logic():
    print("=== 测试数据库缓存逻辑 ===")
    
    stock_code = '600519'
    
    # 第一次调用 - 应该从数据库读取（因为已有数据）
    print("\n--- 第一次调用 fetch_stock_kline_data ---")
    start_time = time.time()
    result1 = fetch_stock_kline_data(stock_code)
    end_time = time.time()
    print(f"第一次调用耗时: {end_time - start_time:.2f} 秒")
    print(f"获取到 {len(result1) if result1 is not None and not result1.empty else 0} 条数据")
    
    # 检查数据库中的最新日期
    latest_date = get_latest_stock_date_from_db(stock_code)
    print(f"数据库中最新日期: {latest_date}")
    
    # 第二次调用 - 应该直接从数据库读取，速度更快
    print("\n--- 第二次调用 fetch_stock_kline_data ---")
    start_time = time.time()
    result2 = fetch_stock_kline_data(stock_code)
    end_time = time.time()
    print(f"第二次调用耗时: {end_time - start_time:.2f} 秒")
    print(f"获取到 {len(result2) if result2 is not None and not result2.empty else 0} 条数据")
    
    # 比较两次结果
    if result1 is not None and result2 is not None and not result1.empty and not result2.empty:
        if len(result1) == len(result2):
            print("✓ 两次调用返回的数据条数一致")
        else:
            print(f"⚠ 两次调用返回的数据条数不一致: {len(result1)} vs {len(result2)}")
    
    # 直接从数据库读取进行对比
    print("\n--- 直接从数据库读取数据 ---")
    start_time = time.time()
    db_result = get_stock_kline_from_db(stock_code, '2023-01-01')
    end_time = time.time()
    print(f"直接数据库读取耗时: {end_time - start_time:.2f} 秒")
    print(f"数据库中共有 {len(db_result) if not db_result.empty else 0} 条数据")
    
    print("\n=== 缓存逻辑测试完成 ===")

if __name__ == '__main__':
    test_cache_logic()