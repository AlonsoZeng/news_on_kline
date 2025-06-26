#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
政策数据自动抓取脚本 - 抓取最近30页内容并增量更新
支持每天自动运行，只抓取新增内容
"""

from policy_data_fetcher import PolicyDataFetcher
import logging
import schedule
import time
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('policy_fetch.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def fetch_latest_policies():
    """抓取最新政策数据（30页）"""
    logger.info("="*50)
    logger.info("开始执行政策数据抓取任务")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 创建数据抓取器实例
        fetcher = PolicyDataFetcher()
        
        # 运行数据收集，抓取最近30页
        # 不指定target_month，抓取所有最新数据
        saved_count = fetcher.run_data_collection(target_month=None, max_pages=30)
        
        logger.info(f"政策数据抓取完成，新增保存 {saved_count} 条数据")
        logger.info("="*50)
        
        return saved_count
        
    except Exception as e:
        logger.error(f"抓取政策数据时出错: {e}")
        logger.info("="*50)
        return 0

def fetch_specific_month_policies(target_month):
    """抓取指定月份的政策数据（30页）
    
    Args:
        target_month: 目标月份，格式为'2025-06'
    """
    logger.info("="*50)
    logger.info(f"开始执行 {target_month} 月份政策数据抓取任务")
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 创建数据抓取器实例
        fetcher = PolicyDataFetcher()
        
        # 运行数据收集，抓取指定月份的30页数据
        saved_count = fetcher.run_data_collection(target_month=target_month, max_pages=30)
        
        logger.info(f"{target_month} 月份政策数据抓取完成，新增保存 {saved_count} 条数据")
        logger.info("="*50)
        
        return saved_count
        
    except Exception as e:
        logger.error(f"抓取 {target_month} 月份政策数据时出错: {e}")
        logger.info("="*50)
        return 0

def setup_daily_schedule():
    """设置每天自动抓取任务"""
    # 每天早上8点执行
    schedule.every().day.at("08:00").do(fetch_latest_policies)
    
    # 每天下午2点执行
    schedule.every().day.at("14:00").do(fetch_latest_policies)
    
    # 每天晚上8点执行
    schedule.every().day.at("20:00").do(fetch_latest_policies)
    
    logger.info("已设置每日自动抓取任务：")
    logger.info("- 每天 08:00 执行政策数据抓取")
    logger.info("- 每天 14:00 执行政策数据抓取")
    logger.info("- 每天 20:00 执行政策数据抓取")

def run_scheduler():
    """运行调度器"""
    logger.info("政策数据自动抓取服务启动")
    
    # 先执行一次立即抓取
    logger.info("执行初始抓取...")
    fetch_latest_policies()
    
    # 设置定时任务
    setup_daily_schedule()
    
    # 持续运行调度器
    logger.info("开始监听定时任务...")
    while True:
        schedule.run_pending()
        time.sleep(60)  # 每分钟检查一次

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "once":
            # 执行一次抓取
            logger.info("执行单次政策数据抓取")
            fetch_latest_policies()
            
        elif command == "month" and len(sys.argv) > 2:
            # 抓取指定月份
            target_month = sys.argv[2]
            logger.info(f"执行 {target_month} 月份政策数据抓取")
            fetch_specific_month_policies(target_month)
            
        elif command == "schedule":
            # 启动定时任务
            run_scheduler()
            
        else:
            print("使用方法:")
            print("  python fetch_latest_policies.py once          # 执行一次抓取")
            print("  python fetch_latest_policies.py month 2025-06 # 抓取指定月份")
            print("  python fetch_latest_policies.py schedule      # 启动定时任务")
    else:
        # 默认执行一次抓取
        logger.info("执行默认单次政策数据抓取")
        fetch_latest_policies()

if __name__ == "__main__":
    main()