#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
专门用于抓取2025年6月政策数据的脚本
"""

from policy_data_fetcher import PolicyDataFetcher
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    """抓取2025年6月的政策数据"""
    logger.info("开始抓取2025年6月政策数据")
    
    # 创建数据抓取器实例
    fetcher = PolicyDataFetcher()
    
    # 运行数据收集，指定目标月份为2025年6月
    target_month = "2025-06"
    saved_count = fetcher.run_data_collection(target_month=target_month)
    
    logger.info(f"2025年6月政策数据抓取完成，共保存 {saved_count} 条数据")
    
    return saved_count

if __name__ == "__main__":
    main()