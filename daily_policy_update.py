#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
每日政策数据自动更新脚本
简化版本，专门用于每日定时抓取
"""

from policy_data_fetcher import PolicyDataFetcher
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('daily_policy_update.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def daily_policy_update():
    """每日政策数据更新"""
    logger.info("="*60)
    logger.info("开始执行每日政策数据更新任务")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 创建数据抓取器实例
        fetcher = PolicyDataFetcher()
        
        # 运行数据收集，抓取最近30页
        # 不指定target_month，抓取所有最新数据
        saved_count = fetcher.run_data_collection(target_month=None, max_pages=30)
        
        logger.info(f"每日政策数据更新完成，新增保存 {saved_count} 条数据")
        logger.info("="*60)
        
        return saved_count
        
    except Exception as e:
        logger.error(f"每日政策数据更新时出错: {e}")
        logger.exception("详细错误信息:")
        logger.info("="*60)
        return 0

if __name__ == "__main__":
    daily_policy_update()