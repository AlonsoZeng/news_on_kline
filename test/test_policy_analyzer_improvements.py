#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试政策分析器的改进功能
- 测试分析失败和无相关行业的区分
- 测试重新分析功能
- 测试统计信息功能
"""

import sys
import os
import json
import sqlite3
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.ai_policy_analyzer import AIPolicyAnalyzer
from config.app_config import AppConfig

def setup_test_data():
    """设置测试数据"""
    test_db_path = 'test_events.db'
    
    # 删除已存在的测试数据库
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    # 创建测试数据库和表
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()
    
    # 创建policy_events表
    cursor.execute('''
        CREATE TABLE policy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT,
            date TEXT,
            event_type TEXT,
            source_url TEXT
        )
    ''')
    
    # 插入测试数据
    test_policies = [
        {
            'title': '国务院发布新能源汽车产业发展规划',
            'content': '为推动新能源汽车产业高质量发展，国务院发布了新能源汽车产业发展规划，明确了未来发展目标和重点任务。重点支持动力电池、电机、电控等关键技术研发。',
            'date': '2024-01-15',
            'event_type': '政策发布',
            'source_url': 'https://example.com/policy1'
        },
        {
            'title': '央行调整存款准备金率',
            'content': '中国人民银行决定下调金融机构存款准备金率0.5个百分点，释放长期资金约1万亿元。',
            'date': '2024-01-16',
            'event_type': '货币政策',
            'source_url': 'https://example.com/policy2'
        },
        {
            'title': '某地区举办文化节活动',
            'content': '为丰富群众文化生活，某地区将举办为期一周的文化节活动，包括文艺演出、书画展览等。',
            'date': '2024-01-17',
            'event_type': '文化活动',
            'source_url': 'https://example.com/policy3'
        }
    ]
    
    for policy in test_policies:
        cursor.execute('''
            INSERT INTO policy_events (title, content, date, event_type, source_url)
            VALUES (?, ?, ?, ?, ?)
        ''', (policy['title'], policy['content'], policy['date'], policy['event_type'], policy['source_url']))
    
    conn.commit()
    conn.close()
    
    return test_db_path

def test_analysis_improvements():
    """测试分析功能的改进"""
    print("=== 测试政策分析器改进功能 ===")
    
    # 设置测试数据
    test_db_path = setup_test_data()
    
    try:
        # 获取API密钥
        config = AppConfig()
        api_key = config.SILICONFLOW_API_KEY
        if not api_key:
            print("错误：未找到API密钥，请设置SILICONFLOW_API_KEY环境变量")
            return
        
        # 创建分析器实例
        analyzer = AIPolicyAnalyzer(api_key, db_path=test_db_path)
        
        print("\n1. 查看初始统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n2. 分析未处理的政策")
        processed = analyzer.analyze_unprocessed_policies(limit=3)
        print(f"处理了 {processed} 条政策")
        
        print("\n3. 查看分析后的统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n4. 查看具体分析结果")
        with analyzer.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pe.title, pa.industries, pa.analysis_summary, pa.confidence_score
                FROM policy_events pe
                JOIN policy_analysis pa ON pe.id = pa.policy_id
                ORDER BY pe.id
            ''')
            
            results = cursor.fetchall()
            for i, (title, industries, summary, confidence) in enumerate(results, 1):
                print(f"\n政策 {i}: {title[:50]}...")
                print(f"相关行业: {industries}")
                print(f"分析摘要: {summary[:100]}...")
                print(f"置信度: {confidence}")
        
        print("\n5. 测试重新分析功能")
        # 模拟一些分析失败的情况
        with analyzer.get_db_connection() as conn:
            cursor = conn.cursor()
            # 手动设置一条记录为分析失败
            cursor.execute('''
                UPDATE policy_analysis 
                SET industries = '["分析失败"]', analysis_summary = '测试分析失败情况'
                WHERE policy_id = 1
            ''')
            # 手动设置一条记录为无相关行业
            cursor.execute('''
                UPDATE policy_analysis 
                SET industries = '["分析后无相关行业"]', analysis_summary = '测试无相关行业情况'
                WHERE policy_id = 2
            ''')
            conn.commit()
        
        print("\n6. 查看设置失败状态后的统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n7. 执行重新分析")
        reanalyzed = analyzer.analyze_failed_and_empty_policies(limit=5)
        print(f"重新分析了 {reanalyzed} 条政策")
        
        print("\n8. 查看重新分析后的统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n9. 查看重新分析后的结果")
        with analyzer.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pe.title, pa.industries, pa.analysis_summary
                FROM policy_events pe
                JOIN policy_analysis pa ON pe.id = pa.policy_id
                WHERE pe.id IN (1, 2)
                ORDER BY pe.id
            ''')
            
            results = cursor.fetchall()
            for title, industries, summary in results:
                print(f"\n政策: {title[:50]}...")
                print(f"相关行业: {industries}")
                print(f"分析摘要: {summary[:100]}...")
        
        print("\n=== 测试完成 ===")
        
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理测试数据
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
            print(f"\n已清理测试数据库: {test_db_path}")

def test_mock_analysis():
    """测试模拟分析功能（不调用真实API）"""
    print("\n=== 测试模拟分析功能 ===")
    
    test_db_path = setup_test_data()
    
    try:
        # 创建一个模拟的分析器
        class MockAIPolicyAnalyzer(AIPolicyAnalyzer):
            def __init__(self, db_path):
                self.db_path = db_path
                self.init_analysis_table()
            
            def call_ai_api(self, prompt):
                """模拟API调用"""
                # 根据prompt内容返回不同的模拟结果
                if "新能源汽车" in prompt:
                    return {
                        'choices': [{
                            'message': {
                                'content': json.dumps({
                                    'industries': ['新能源汽车', '动力电池', '汽车制造'],
                                    'impact_type': '正面',
                                    'analysis_summary': '政策支持新能源汽车产业发展，利好相关行业',
                                    'confidence_score': 0.8
                                }, ensure_ascii=False)
                            }
                        }]
                    }
                elif "存款准备金" in prompt:
                    return {
                        'choices': [{
                            'message': {
                                'content': json.dumps({
                                    'industries': ['银行', '金融'],
                                    'impact_type': '正面',
                                    'analysis_summary': '降准释放流动性，利好银行和金融行业',
                                    'confidence_score': 0.9
                                }, ensure_ascii=False)
                            }
                        }]
                    }
                elif "文化节" in prompt:
                    return {
                        'choices': [{
                            'message': {
                                'content': json.dumps({
                                    'industries': [],
                                    'impact_type': '中性',
                                    'analysis_summary': '文化活动对股市影响较小',
                                    'confidence_score': 0.3
                                }, ensure_ascii=False)
                            }
                        }]
                    }
                else:
                    # 模拟API调用失败
                    return None
        
        analyzer = MockAIPolicyAnalyzer(test_db_path)
        
        print("\n1. 模拟分析未处理的政策")
        processed = analyzer.analyze_unprocessed_policies(limit=3)
        print(f"处理了 {processed} 条政策")
        
        print("\n2. 查看模拟分析结果")
        analyzer.print_analysis_statistics()
        
        print("\n3. 查看具体分析结果")
        with analyzer.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT pe.title, pa.industries, pa.analysis_summary
                FROM policy_events pe
                JOIN policy_analysis pa ON pe.id = pa.policy_id
                ORDER BY pe.id
            ''')
            
            results = cursor.fetchall()
            for title, industries, summary in results:
                print(f"\n政策: {title[:50]}...")
                print(f"相关行业: {industries}")
                print(f"分析摘要: {summary[:100]}...")
        
        print("\n=== 模拟测试完成 ===")
        
    except Exception as e:
        print(f"模拟测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        if os.path.exists(test_db_path):
            os.remove(test_db_path)

if __name__ == "__main__":
    # 首先运行模拟测试
    test_mock_analysis()
    
    # 询问是否运行真实API测试
    print("\n是否要运行真实API测试？这将消耗API调用次数。(y/N): ", end="")
    choice = input().strip().lower()
    
    if choice in ['y', 'yes']:
        test_analysis_improvements()
    else:
        print("跳过真实API测试")