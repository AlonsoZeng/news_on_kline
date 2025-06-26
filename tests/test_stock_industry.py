#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import json
import time

# 测试配置
BASE_URL = "http://192.168.2.10:5001"
test_stocks = [
    "000858",  # 五粮液
    "000001",  # 平安银行
    "000002",  # 万科A
    "600519",  # 贵州茅台
    "000300"   # 沪深300指数
]

def test_stock_industry_analysis():
    """测试股票行业分析功能"""
    base_url = "http://192.168.2.10:5001"
    
    # 测试股票代码列表
    test_stocks = [
        "000858",  # 五粮液 - 白酒行业
        "000001",  # 平安银行 - 银行业
        "000002",  # 万科A - 房地产
        "600519",  # 贵州茅台 - 白酒行业
        "000300"   # 沪深300指数
    ]
    
    print("=== 测试股票行业分析功能 ===")
    
    for stock_code in test_stocks:
        print(f"\n测试股票: {stock_code}")
        
        # 1. 获取股票行业信息
        try:
            response = requests.get(f"{base_url}/api/stock-industry/{stock_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    industry_info = data.get('data', {})
                    print(f"  行业信息: {industry_info.get('industry', '未知')}")
                    print(f"  是否为指数: {industry_info.get('is_index', False)}")
                    print(f"  数据来源: {industry_info.get('source', '未知')}")
                else:
                    print(f"  获取行业信息失败: {data.get('message')}")
            else:
                print(f"  请求失败: {response.status_code}")
        except Exception as e:
            print(f"  请求异常: {e}")
        
        # 等待一下避免请求过快
        time.sleep(1)
    
    print("\n=== 测试手动触发行业分析 ===")
    
    # 2. 测试手动触发行业分析
    try:
        response = requests.post(f"{base_url}/api/stock-industry-analysis", 
                               json={"limit": 5})
        if response.status_code == 200:
            data = response.json()
            print(f"分析结果: {data}")
        else:
            print(f"请求失败: {response.status_code}")
    except Exception as e:
        print(f"请求异常: {e}")

if __name__ == "__main__":
    test_stock_industry_analysis()