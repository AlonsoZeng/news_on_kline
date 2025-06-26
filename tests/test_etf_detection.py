# -*- coding: utf-8 -*-
import sys
import os

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_industry_analyzer import StockIndustryAnalyzer
from app import get_smart_events_for_stock

def test_etf_detection():
    """测试ETF股票的检测和事件获取"""
    stock_code = '512800.SH'
    print(f"测试股票 {stock_code} (银行ETF) 的检测和事件获取")
    
    # 初始化分析器
    API_KEY = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # 使用占位符
    analyzer = StockIndustryAnalyzer(API_KEY, 'events.db')
    
    # 测试是否被识别为指数股票
    is_index = analyzer.is_index_stock(stock_code)
    print(f"\n1. 是否被识别为指数股票: {is_index}")
    
    # 测试股票代码的模式匹配
    code_num = stock_code.split('.')[0]
    print(f"   股票代码数字部分: {code_num}")
    print(f"   是否以5开头: {code_num.startswith('5')}")
    print(f"   是否以1开头: {code_num.startswith('1')}")
    
    # 获取智能筛选的事件
    print(f"\n2. 获取智能筛选的事件:")
    events = get_smart_events_for_stock(stock_code)
    print(f"   获取到 {len(events)} 条事件")
    
    # 如果被识别为指数股票，应该返回全量数据
    if is_index:
        print("   ✓ 作为指数股票，返回全量政策数据是正确的")
    else:
        print("   ✗ 未被识别为指数股票，应该进行行业分析")
        
        # 尝试获取行业信息
        try:
            industry_info = analyzer.get_or_analyze_stock_industry(stock_code)
            if industry_info:
                print(f"   行业信息: {industry_info}")
            else:
                print("   无法获取行业信息")
        except Exception as e:
            print(f"   获取行业信息时出错: {e}")
    
    # 显示前几条事件
    if events:
        print(f"\n3. 前5条事件:")
        for i, event in enumerate(events[:5], 1):
            print(f"   {i}. {event.get('date', 'N/A')} - {event.get('title', 'N/A')[:50]}...")

if __name__ == '__main__':
    test_etf_detection()