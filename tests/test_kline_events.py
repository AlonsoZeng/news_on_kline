# -*- coding: utf-8 -*-
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import get_smart_events_for_stock

def test_kline_events():
    """测试K线图事件获取"""
    stock_code = '600519.SH'
    print(f"测试股票 {stock_code} 的K线事件获取")
    
    # 获取智能筛选的事件
    events = get_smart_events_for_stock(stock_code)
    
    print(f"\n获取到 {len(events)} 条事件:")
    
    if events:
        for i, event in enumerate(events[:10], 1):  # 只显示前10条
            print(f"  {i}. 日期: {event.get('date', 'N/A')}")
            print(f"     标题: {event.get('title', 'N/A')[:50]}...")
            print(f"     类型: {event.get('event_type', 'N/A')}")
            print(f"     AI行业: {event.get('ai_industries', [])}")
            print()
    else:
        print("未获取到任何事件")
    
    # 检查事件日期格式
    print("\n检查事件日期格式:")
    date_formats = set()
    for event in events[:5]:  # 检查前5条事件的日期格式
        date_str = event.get('date', '')
        if date_str:
            date_formats.add(type(date_str).__name__ + ': ' + str(date_str))
    
    for date_format in date_formats:
        print(f"  {date_format}")

if __name__ == '__main__':
    test_kline_events()