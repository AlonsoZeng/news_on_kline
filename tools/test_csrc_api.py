#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试证监会API抓取功能
"""

import requests
import json
from policy_data_fetcher import PolicyDataFetcher

def test_csrc_api():
    """测试证监会API"""
    base_url = "http://www.csrc.gov.cn/searchList/a1a078ee0bc54721ab6b148884c784a8"
    
    # 测试单页数据
    url = f"{base_url}?_isAgg=true&_isJson=true&_pageSize=18&_template=index&page=1"
    
    print(f"测试URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n返回数据结构:")
            print(f"- 顶层键: {list(data.keys())}")
            
            if 'data' in data:
                print(f"- data键内容: {list(data['data'].keys())}")
                
                if 'results' in data['data']:
                    results = data['data']['results']
                    print(f"- results数量: {len(results)}")
                    
                    if results:
                        print(f"\n第一条数据示例:")
                        first_item = results[0]
                        print(json.dumps(first_item, ensure_ascii=False, indent=2))
                        
                        # 测试数据解析
                        fetcher = PolicyDataFetcher()
                        
                        title = first_item.get('title', '').strip()
                        content = first_item.get('content', '').strip()
                        memo = first_item.get('memo', '').strip()
                        
                        print(f"\n解析结果:")
                        print(f"- 标题: {title}")
                        print(f"- 内容: {content[:100]}..." if content else "- 内容: 无")
                        print(f"- 备注: {memo[:100]}..." if memo else "- 备注: 无")
                        
                        # 测试日期提取
                        policy_date = fetcher._extract_date_from_csrc_item(first_item)
                        print(f"- 提取日期: {policy_date}")
                        
                        # 测试部门提取
                        department = fetcher._extract_department_from_csrc_item(first_item)
                        print(f"- 提取部门: {department}")
                        
                        # 测试URL提取
                        source_url = fetcher._extract_url_from_csrc_item(first_item)
                        print(f"- 提取URL: {source_url}")
                        
                        # 测试政策类型分类
                        event_type = fetcher._classify_csrc_policy_type(title, content)
                        print(f"- 政策类型: {event_type}")
                        
                else:
                    print("- 未找到results字段")
            else:
                print("- 未找到data字段")
                
        else:
            print(f"请求失败，状态码: {response.status_code}")
            
    except Exception as e:
        print(f"测试出错: {e}")

if __name__ == '__main__':
    test_csrc_api()