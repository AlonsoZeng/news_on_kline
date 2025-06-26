#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import get_smart_events_for_stock, stock_industry_analyzer

def test_bank_etf_events():
    """测试银行ETF事件获取"""
    
    stock_code = '512800.SH'
    print(f"=== 测试银行ETF ({stock_code}) 事件获取 ===")
    print()
    
    if not stock_industry_analyzer:
        print("错误: 股票行业分析器未初始化")
        return
    
    # 检查股票类型
    stock_type = stock_industry_analyzer.get_stock_type(stock_code)
    print(f"股票类型: {stock_type}")
    
    # 使用AI分析获取行业信息
    industry_info = stock_industry_analyzer.get_or_analyze_stock_industry(stock_code)
    if industry_info and industry_info.get('industries'):
        etf_industries = industry_info['industries']
        print(f"ETF行业: {etf_industries}")
    
    # 检查是否为指数股票
    is_index = stock_industry_analyzer.is_index_stock(stock_code)
    print(f"是否为指数股票: {is_index}")
    print()
    
    # 获取智能事件
    print("获取智能事件...")
    events = get_smart_events_for_stock(stock_code)
    
    print(f"获取到 {len(events)} 条事件")
    print()
    
    if events:
        print("前10条事件:")
        for i, event in enumerate(events[:10], 1):
            print(f"{i:2d}. {event['date']}: {event['title'][:60]}...")
            if event.get('ai_industries'):
                print(f"     AI行业: {event['ai_industries']}")
            print()
    else:
        print("未获取到任何事件")

def test_comparison():
    """对比测试：银行ETF vs 贵州茅台"""
    print("\n=== 对比测试 ===")
    
    test_stocks = [
        ('512800.SH', '银行ETF'),
        ('600519.SH', '贵州茅台')
    ]
    
    for stock_code, name in test_stocks:
        print(f"\n--- {name} ({stock_code}) ---")
        
        if stock_industry_analyzer:
            stock_type = stock_industry_analyzer.get_stock_type(stock_code)
            is_etf = stock_industry_analyzer.is_etf(stock_code)
            is_index = stock_industry_analyzer.is_index(stock_code)
            
            print(f"股票类型: {stock_type}, ETF: {is_etf}, 指数: {is_index}")
            
            # 使用AI分析获取行业信息
            industry_info = stock_industry_analyzer.get_or_analyze_stock_industry(stock_code)
            if industry_info and industry_info.get('industries'):
                industries = industry_info['industries']
                print(f"行业: {industries}")
        
        events = get_smart_events_for_stock(stock_code)
        print(f"事件数量: {len(events)}")

if __name__ == "__main__":
    test_bank_etf_events()
    test_comparison()