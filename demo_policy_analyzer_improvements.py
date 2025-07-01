#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
政策分析器改进功能演示脚本

本脚本演示如何使用改进后的政策分析器功能：
1. 区分分析失败和无相关行业的情况
2. 重新分析失败或无相关行业的政策
3. 查看分析统计信息
"""

import sys
import os
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.ai_policy_analyzer import AIPolicyAnalyzer
from config.app_config import AppConfig

def main():
    """主函数"""
    print("=== 政策分析器改进功能演示 ===")
    
    try:
        # 初始化配置和分析器
        config = AppConfig()
        analyzer = AIPolicyAnalyzer(config.EVENTS_DB_FILE)
        
        print("\n1. 查看当前分析统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n2. 分析未处理的政策（包含失败处理逻辑）")
        print("正在分析未处理的政策...")
        results = analyzer.analyze_unprocessed_policies(max_policies=5)
        print(f"分析完成，处理了 {len(results)} 条政策")
        
        print("\n3. 查看分析后的统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n4. 重新分析失败和无相关行业的政策")
        print("正在重新分析失败和无相关行业的政策...")
        reanalysis_results = analyzer.analyze_failed_and_empty_policies(max_policies=3)
        print(f"重新分析完成，处理了 {len(reanalysis_results)} 条政策")
        
        print("\n5. 查看最终统计信息")
        analyzer.print_analysis_statistics()
        
        print("\n=== 演示完成 ===")
        print("\n改进功能说明：")
        print("- 分析失败时会标记为'分析失败'")
        print("- 分析成功但无相关行业时会标记为'分析后无相关行业'")
        print("- 可以专门重新分析失败和无相关行业的政策")
        print("- 提供详细的分析统计信息")
        
    except Exception as e:
        print(f"演示过程中发生错误: {e}")
        print("请确保：")
        print("1. 已设置SILICONFLOW_API_KEY环境变量")
        print("2. 数据库文件存在且包含政策数据")
        print("3. 网络连接正常")

if __name__ == "__main__":
    main()