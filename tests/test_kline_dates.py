# -*- coding: utf-8 -*-
import sys
import os
import pandas as pd
from datetime import datetime

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import fetch_stock_kline_data, get_smart_events_for_stock

def test_kline_dates():
    """测试K线数据的日期范围"""
    stock_code = '600519'
    print(f"测试股票 {stock_code} 的K线数据日期范围")
    
    # 获取K线数据
    df_kline = fetch_stock_kline_data(stock_code)
    
    if df_kline.empty:
        print("未获取到K线数据")
        return
    
    print(f"\nK线数据总计: {len(df_kline)} 条")
    print(f"日期范围: {df_kline['date'].min()} 到 {df_kline['date'].max()}")
    
    # 检查是否包含事件日期
    event_date = '2024-03-13'
    print(f"\n检查是否包含事件日期 {event_date}:")
    
    # 转换为字符串格式进行比较
    df_kline['date_str'] = df_kline['date'].dt.strftime('%Y-%m-%d')
    
    if event_date in df_kline['date_str'].values:
        print(f"✓ K线数据包含日期 {event_date}")
        # 获取该日期的K线数据
        event_day_data = df_kline[df_kline['date_str'] == event_date]
        if not event_day_data.empty:
            row = event_day_data.iloc[0]
            print(f"  开盘: {row['open']}, 收盘: {row['close']}, 最高: {row['high']}, 最低: {row['low']}")
    else:
        print(f"✗ K线数据不包含日期 {event_date}")
        
        # 查找最接近的日期
        df_kline['date_diff'] = abs((df_kline['date'] - pd.to_datetime(event_date)).dt.days)
        closest_date = df_kline.loc[df_kline['date_diff'].idxmin()]
        print(f"  最接近的日期: {closest_date['date_str']} (相差 {closest_date['date_diff']} 天)")
    
    # 获取事件数据
    print(f"\n获取股票 600519.SH 的事件数据:")
    events = get_smart_events_for_stock('600519.SH')
    
    if events:
        print(f"找到 {len(events)} 条事件")
        for event in events:
            event_date = event.get('date')
            print(f"  事件日期: {event_date}")
            if event_date in df_kline['date_str'].values:
                print(f"    ✓ K线数据包含此日期")
            else:
                print(f"    ✗ K线数据不包含此日期")
    else:
        print("未找到事件数据")

if __name__ == '__main__':
    test_kline_dates()