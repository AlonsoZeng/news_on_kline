#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_industry_analyzer import StockIndustryAnalyzer

def test_etf_industry_recognition():
    """测试ETF行业识别功能"""
    
    # 初始化分析器
    API_KEY = os.getenv('SILICONFLOW_API_KEY', 'sk-rtfxnalfnpfrucbjvzzizgsltocaywdtfvvcmloznshsqzfo')
    DB_PATH = 'events.db'
    
    analyzer = StockIndustryAnalyzer(API_KEY, DB_PATH)
    
    # 测试ETF列表
    test_etfs = [
        ('512800.SH', '银行ETF'),
        ('512000.SH', '券商ETF'),
        ('512010.SH', '医药ETF'),
        ('515000.SH', '科技ETF'),
        ('159928.SZ', '消费ETF'),
        ('512660.SH', '军工ETF'),
        ('516160.SH', '新能源ETF'),
        ('516110.SH', '汽车ETF'),
        ('000001.SH', '上证指数（非ETF）'),
        ('600519.SH', '贵州茅台（个股）')
    ]
    
    print("=== ETF行业识别功能测试 ===")
    print()
    
    for stock_code, name in test_etfs:
        print(f"测试: {stock_code} ({name})")
        
        # 检查股票类型
        stock_type = analyzer.get_stock_type(stock_code)
        print(f"  股票类型: {stock_type}")
        
        # 使用AI分析获取行业信息
        industry_info = analyzer.get_or_analyze_stock_industry(stock_code)
        if industry_info and industry_info.get('industries'):
            etf_industries = industry_info['industries']
            print(f"  ETF行业: {etf_industries}")
            
            # 获取相关政策
            related_policies = analyzer.get_related_policies(etf_industries, limit=5)
            print(f"  相关政策数量: {len(related_policies)}")
            
            if related_policies:
                print("  前3条相关政策:")
                for i, policy in enumerate(related_policies[:3], 1):
                    print(f"    {i}. {policy['date']}: {policy['title'][:50]}...")
        else:
            # 检查是否为其他指数股票
            is_index = analyzer.is_index_stock(stock_code)
            print(f"  是否为指数股票: {is_index}")
            
            if not is_index:
                print(f"  这是个股，需要AI分析行业")
        
        print()

if __name__ == "__main__":
    test_etf_industry_recognition()