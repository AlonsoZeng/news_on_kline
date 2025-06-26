#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量分析政策数据脚本
用于为相关行业(pa.industries)为空的数据行补齐数据
"""

import os
import sys
import sqlite3
import logging
from ai_policy_analyzer import AIPolicyAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_analysis.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_unanalyzed_count(db_path='events.db'):
    """获取未分析的政策数量"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*)
            FROM policy_events pe
            LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
            WHERE pa.policy_id IS NULL
        ''')
        
        count = cursor.fetchone()[0]
        return count
        
    except Exception as e:
        logger.error(f"获取未分析政策数量失败: {str(e)}")
        return 0
    finally:
        conn.close()

def get_analyzed_without_industries_count(db_path='events.db'):
    """获取已分析但未识别出行业的政策数量"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*)
            FROM policy_analysis pa
            WHERE pa.industries IS NULL OR pa.industries = '[]' OR pa.industries = ''
        ''')
        
        count = cursor.fetchone()[0]
        return count
        
    except Exception as e:
        logger.error(f"获取已分析但未识别出行业的政策数量失败: {str(e)}")
        return 0
    finally:
        conn.close()

def batch_analyze_all_policies(api_key: str, batch_size: int = 20, max_batches: int = None, use_async: bool = True, max_concurrent: int = 5) -> dict:
    """
    批量分析所有未处理的政策
    
    Args:
        api_key: SiliconFlow API密钥
        batch_size: 每批处理的政策数量
        max_batches: 最大批次数，None表示处理所有
        use_async: 是否使用异步处理（默认True）
        max_concurrent: 异步处理时的最大并发数
        
    Returns:
        包含统计信息的字典
    """
    if not api_key or api_key == 'YOUR_SILICONFLOW_API_KEY':
        logger.error("请设置有效的硅基流动API Key")
        return {'error': 'Invalid API key'}
    
    # 初始化AI分析器
    analyzer = AIPolicyAnalyzer(api_key)
    
    total_analyzed = 0
    batch_count = 0
    
    mode_text = "异步" if use_async else "同步"
    logger.info(f"开始批量分析政策（{mode_text}模式），每批处理 {batch_size} 条...")
    if use_async:
        logger.info(f"异步并发数: {max_concurrent}")
    
    while True:
        batch_count += 1
        logger.info(f"=== 第 {batch_count} 批次 ===")
        
        # 分析一批政策
        if use_async:
            import asyncio
            import time
            # Python 3.6兼容性处理
            if hasattr(asyncio, 'run'):
                analyzed_count = asyncio.run(
                    analyzer.analyze_unprocessed_policies_async(
                        limit=batch_size,
                        max_concurrent=max_concurrent
                    )
                )
            else:
                # Python 3.6兼容方式
                loop = asyncio.get_event_loop()
                analyzed_count = loop.run_until_complete(
                    analyzer.analyze_unprocessed_policies_async(
                        limit=batch_size,
                        max_concurrent=max_concurrent
                    )
                )
        else:
            analyzed_count = analyzer.analyze_unprocessed_policies(limit=batch_size)
        
        if analyzed_count == 0:
            logger.info("没有更多需要分析的政策")
            break
            
        total_analyzed += analyzed_count
        logger.info(f"本批次成功分析 {analyzed_count} 条政策（{mode_text}模式）")
        logger.info(f"累计已分析 {total_analyzed} 条政策")
        
        # 检查是否达到最大批次数
        if max_batches and batch_count >= max_batches:
            logger.info(f"已达到最大批次数 {max_batches}，停止分析")
            break
            
        # 检查用户是否要求中断
        try:
            # 短暂暂停，允许用户中断
            import time
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("用户中断分析")
            break
    
    # 最终统计
    final_unanalyzed = get_unprocessed_policies_count()
    final_without_industries = get_unidentified_industries_count()
    
    logger.info("=== 批量分析完成 ===")
    logger.info(f"总共处理了 {total_analyzed} 条政策")
    logger.info(f"剩余未分析: {final_unanalyzed} 条")
    logger.info(f"已分析但未识别出行业: {final_without_industries} 条")
    
    return {
        'total_analyzed': total_analyzed,
        'batch_count': batch_count,
        'unprocessed_count': final_unanalyzed,
        'unidentified_industries_count': final_without_industries,
        'mode': mode_text
    }

def get_unprocessed_policies_count() -> int:
    """获取未分析的政策数量"""
    import sqlite3
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*)
            FROM policy_events pe
            LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
            WHERE pa.policy_id IS NULL
        ''')
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        print(f"获取未分析政策数量失败: {e}")
        return 0
    finally:
        conn.close()

def get_unidentified_industries_count() -> int:
    """获取已分析但未识别出行业的政策数量"""
    import sqlite3
    conn = sqlite3.connect('events.db')
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT COUNT(*)
            FROM policy_analysis
            WHERE industries IS NULL OR industries = '' OR industries = '[]'
        ''')
        count = cursor.fetchone()[0]
        return count
    except Exception as e:
        print(f"获取未识别行业政策数量失败: {e}")
        return 0
    finally:
        conn.close()

def main():
    """主函数"""
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='批量分析政策数据')
    parser.add_argument('--batch-size', type=int, default=20, help='每批处理的政策数量（默认20）')
    parser.add_argument('--max-batches', type=int, default=None, help='最大批次数（默认无限制）')
    parser.add_argument('--sync', action='store_true', help='使用同步模式（默认使用异步模式）')
    parser.add_argument('--max-concurrent', type=int, default=5, help='异步模式下的最大并发数（默认5）')
    
    args = parser.parse_args()
    
    # 初始化配置
    from config import init_config, Config
    
    if not init_config():
        print("错误: 配置初始化失败")
        print("请确保已正确设置 SILICONFLOW_API_KEY 环境变量")
        print("示例: set SILICONFLOW_API_KEY=your_api_key_here")
        print("或者创建 .env 文件并配置相关参数")
        return
    
    try:
        api_key = Config.get_api_key()
    except ValueError as e:
        print(f"错误: {e}")
        print("示例: set SILICONFLOW_API_KEY=your_api_key_here")
        return
    
    try:
        print("开始批量分析政策数据...")
        
        # 显示当前状态
        unprocessed = get_unprocessed_policies_count()
        unidentified = get_unidentified_industries_count()
        
        print(f"当前状态:")
        print(f"- 未分析的政策: {unprocessed} 条")
        print(f"- 已分析但未识别出行业的政策: {unidentified} 条")
        
        if unprocessed == 0:
            print("所有政策都已分析完成！")
            return
        
        # 显示配置信息
        use_async = not args.sync
        print(f"\n配置信息:")
        print(f"- 处理模式: {'异步' if use_async else '同步'}")
        print(f"- 批次大小: {args.batch_size}")
        print(f"- 最大批次数: {args.max_batches or '无限制'}")
        if use_async:
            print(f"- 最大并发数: {args.max_concurrent}")
        
        # 开始分析
        result = batch_analyze_all_policies(
            api_key=api_key,
            batch_size=args.batch_size,
            max_batches=args.max_batches,
            use_async=use_async,
            max_concurrent=args.max_concurrent
        )
        
        if 'error' in result:
            print(f"分析失败: {result['error']}")
            return
        
        print("\n=== 分析完成 ===")
        print(f"总共分析了 {result['total_analyzed']} 条政策")
        print(f"处理了 {result['batch_count']} 个批次")
        print(f"处理模式: {result['mode']}")
        print(f"剩余未分析: {result['unprocessed_count']} 条")
        print(f"已分析但未识别出行业: {result['unidentified_industries_count']} 条")
        
    except KeyboardInterrupt:
        print("\n用户中断了分析过程")
    except Exception as e:
        print(f"分析过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()