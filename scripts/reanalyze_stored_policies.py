#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
重新分析已存储政策内容的脚本

该脚本用于重新分析数据库中已存储原文内容的政策，
适用于以下场景：
1. 新的行业出现后，需要重新分析政策影响
2. AI模型升级后，需要重新分析以获得更准确的结果
3. 分析逻辑优化后，需要重新处理历史数据
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.ai_policy_analyzer import AIPolicyAnalyzer
from src.utils.config import init_config, Config
import logging
import sqlite3
from contextlib import contextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@contextmanager
def get_db_connection(db_path):
    """数据库连接上下文管理器"""
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()

def check_stored_content_stats(db_path: str):
    """检查数据库中存储内容的统计信息"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            
            # 统计总政策数量
            cursor.execute('SELECT COUNT(*) FROM policy_events')
            total_policies = cursor.fetchone()[0]
            
            # 统计已分析的政策数量
            cursor.execute('SELECT COUNT(*) FROM policy_analysis')
            analyzed_policies = cursor.fetchone()[0]
            
            # 统计有存储内容的政策数量
            cursor.execute('''
                SELECT COUNT(*) FROM policy_analysis 
                WHERE full_content IS NOT NULL AND full_content != ''
            ''')
            stored_content_policies = cursor.fetchone()[0]
            
            # 统计不同内容质量的政策数量
            cursor.execute('''
                SELECT content_quality, COUNT(*) 
                FROM policy_analysis 
                GROUP BY content_quality
            ''')
            quality_stats = cursor.fetchall()
        
        logger.info(f"=== 政策内容存储统计 ===")
        logger.info(f"总政策数量: {total_policies}")
        logger.info(f"已分析政策数量: {analyzed_policies}")
        logger.info(f"有存储内容的政策数量: {stored_content_policies}")
        logger.info(f"内容质量分布:")
        for quality, count in quality_stats:
            logger.info(f"  {quality}: {count}")
        
        return stored_content_policies
        
    except Exception as e:
        logger.error(f"检查存储内容统计失败: {str(e)}")
        return 0

def main():
    """主函数"""
    logger.info("开始重新分析已存储的政策内容...")
    
    # 初始化配置
    if not init_config():
        logger.error("配置初始化失败")
        return
    
    try:
        api_key = Config.get_api_key()
    except ValueError as e:
        logger.error(f"获取API密钥失败: {e}")
        return
    
    # 数据库路径
    db_path = 'data/events.db'
    
    # 检查存储内容统计
    stored_count = check_stored_content_stats(db_path)
    
    if stored_count == 0:
        logger.info("没有找到已存储内容的政策，无需重新分析")
        return
    
    # 初始化AI分析器
    analyzer = AIPolicyAnalyzer(api_key, db_path)
    
    # 询问用户是否继续
    print(f"\n发现 {stored_count} 条有存储内容的政策可以重新分析。")
    print("重新分析将使用最新的AI模型和分析逻辑。")
    
    choice = input("是否继续进行重新分析？(y/N): ").strip().lower()
    
    if choice not in ['y', 'yes', '是']:
        logger.info("用户取消操作")
        return
    
    # 询问处理数量
    try:
        limit = int(input(f"请输入要处理的政策数量 (最多 {stored_count}，默认 10): ") or "10")
        limit = min(limit, stored_count)
    except ValueError:
        limit = 10
        logger.info("使用默认处理数量: 10")
    
    logger.info(f"开始重新分析 {limit} 条政策...")
    
    # 执行批量重新分析
    success_count = analyzer.batch_reanalyze_policies_with_stored_content(limit)
    
    logger.info(f"重新分析完成！成功处理 {success_count}/{limit} 条政策")
    
    if success_count > 0:
        logger.info("建议检查分析结果，确认新的行业分类是否符合预期")

if __name__ == "__main__":
    main()