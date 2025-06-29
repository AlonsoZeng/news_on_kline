#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修正所有政策数据的日期字段
支持断点续传和进度保存
"""

import sqlite3
import json
import os
import time
from datetime import datetime
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'tools'))
from fix_policy_dates import PolicyDateFixer
import logging
import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
from contextlib import contextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_fix_dates.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BatchPolicyDateFixer(PolicyDateFixer):
    def __init__(self, db_path='events.db', progress_file='date_fix_progress.json'):
        super().__init__(db_path)
        self.progress_file = progress_file
        self.progress = self.load_progress()
    
    @contextmanager
    def get_db_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            raise e
        finally:
            if conn:
                conn.close()
    
    def load_progress(self):
        """加载进度信息"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载进度文件失败: {e}")
        
        return {
            'last_processed_id': 0,
            'total_updated': 0,
            'total_skipped': 0,
            'total_errors': 0,
            'start_time': None,
            'last_update_time': None
        }
    
    def save_progress(self):
        """保存进度信息"""
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存进度文件失败: {e}")
    
    def get_total_records(self):
        """获取总记录数"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT COUNT(*) 
                FROM policy_events 
                WHERE source_url IS NOT NULL AND source_url != ''
            ''')
            
            total = cursor.fetchone()[0]
            return total
    
    def fix_all_policy_dates_with_resume(self, batch_size=50, max_errors=10):
        """批量修正所有政策日期，支持断点续传
        
        Args:
            batch_size: 批处理大小
            max_errors: 最大连续错误数，超过则停止
        """
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            try:
            # 获取总记录数
            total_records = self.get_total_records()
            
            # 设置开始时间
            if not self.progress['start_time']:
                self.progress['start_time'] = datetime.now().isoformat()
            
            logger.info(f"开始批量修正政策日期")
            logger.info(f"总记录数: {total_records}")
            logger.info(f"上次处理到ID: {self.progress['last_processed_id']}")
            logger.info(f"已更新: {self.progress['total_updated']} 条")
            logger.info(f"已跳过: {self.progress['total_skipped']} 条")
            logger.info(f"错误数: {self.progress['total_errors']} 条")
            
            # 获取需要处理的记录（从上次停止的地方继续）
            cursor.execute('''
                SELECT id, title, source_url, date 
                FROM policy_events 
                WHERE source_url IS NOT NULL AND source_url != ''
                AND id > ?
                ORDER BY id
            ''', (self.progress['last_processed_id'],))
            
            records = cursor.fetchall()
            remaining_records = len(records)
            
            logger.info(f"剩余待处理: {remaining_records} 条")
            
            if remaining_records == 0:
                logger.info("所有记录已处理完成！")
                return
            
            consecutive_errors = 0
            
            for i, (record_id, title, source_url, current_date) in enumerate(records, 1):
                try:
                    processed_count = self.progress['total_updated'] + self.progress['total_skipped'] + i
                    logger.info(f"处理第 {processed_count}/{total_records} 条 (ID:{record_id}): {title[:50]}...")
                    
                    # 提取真实发布日期
                    real_date = self.extract_publish_date_from_url(source_url, title)
                    
                    if real_date and real_date != current_date:
                        # 更新数据库
                        cursor.execute('''
                            UPDATE policy_events 
                            SET date = ? 
                            WHERE id = ?
                        ''', (real_date, record_id))
                        
                        logger.info(f"  ✓ 更新日期: {current_date} -> {real_date}")
                        self.updated_count += 1
                        self.progress['total_updated'] += 1
                        
                    elif real_date:
                        logger.debug(f"  - 日期无需更新: {current_date}")
                        self.skipped_count += 1
                        self.progress['total_skipped'] += 1
                        
                    else:
                        logger.warning(f"  ✗ 无法提取日期，跳过: {source_url}")
                        self.skipped_count += 1
                        self.progress['total_skipped'] += 1
                    
                    # 更新进度
                    self.progress['last_processed_id'] = record_id
                    self.progress['last_update_time'] = datetime.now().isoformat()
                    
                    # 重置连续错误计数
                    consecutive_errors = 0
                    
                    # 批量提交和保存进度
                    if i % batch_size == 0:
                        conn.commit()
                        self.save_progress()
                        logger.info(f"已处理 {processed_count} 条记录，已更新 {self.progress['total_updated']} 条")
                    
                    # 避免请求过快
                    time.sleep(0.3)
                    
                except Exception as e:
                    logger.error(f"处理记录 {record_id} 时出错: {e}")
                    self.error_count += 1
                    self.progress['total_errors'] += 1
                    consecutive_errors += 1
                    
                    # 如果连续错误过多，停止处理
                    if consecutive_errors >= max_errors:
                        logger.error(f"连续错误达到 {max_errors} 次，停止处理")
                        break
                    
                    continue
            
            # 最终提交和保存进度
            conn.commit()
            self.save_progress()
            
            logger.info(f"批量日期修正完成！")
            logger.info(f"本次处理: {remaining_records} 条")
            logger.info(f"总计更新: {self.progress['total_updated']} 条")
            logger.info(f"总计跳过: {self.progress['total_skipped']} 条")
            logger.info(f"总计错误: {self.progress['total_errors']} 条")
            
            # 检查是否全部完成
            remaining = self.get_total_records() - (self.progress['total_updated'] + self.progress['total_skipped'])
            if remaining <= 0:
                logger.info("🎉 所有政策日期修正完成！")
                # 可以选择删除进度文件
                # os.remove(self.progress_file)
            else:
                logger.info(f"还有 {remaining} 条记录待处理，可以重新运行脚本继续")
            
            except Exception as e:
                logger.error(f"批量修正日期时出错: {e}")
                conn.rollback()
                raise
    
    def reset_progress(self):
        """重置进度，从头开始"""
        if os.path.exists(self.progress_file):
            os.remove(self.progress_file)
        self.progress = self.load_progress()
        logger.info("进度已重置")
    
    def show_progress(self):
        """显示当前进度"""
        total_records = self.get_total_records()
        processed = self.progress['total_updated'] + self.progress['total_skipped']
        
        print(f"\n=== 日期修正进度 ===")
        print(f"总记录数: {total_records}")
        print(f"已处理: {processed} ({processed/total_records*100:.1f}%)")
        print(f"已更新: {self.progress['total_updated']}")
        print(f"已跳过: {self.progress['total_skipped']}")
        print(f"错误数: {self.progress['total_errors']}")
        print(f"上次处理ID: {self.progress['last_processed_id']}")
        
        if self.progress['start_time']:
            print(f"开始时间: {self.progress['start_time']}")
        if self.progress['last_update_time']:
            print(f"最后更新: {self.progress['last_update_time']}")
        
        remaining = total_records - processed
        if remaining > 0:
            print(f"剩余: {remaining} 条")
        else:
            print("✅ 全部完成！")
        print()

def main():
    """主函数"""
    import sys
    import time
    
    fixer = BatchPolicyDateFixer()
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "status":
            # 显示进度
            fixer.show_progress()
            
        elif command == "reset":
            # 重置进度
            fixer.reset_progress()
            print("进度已重置，可以重新开始处理")
            
        elif command == "continue" or command == "start":
            # 开始或继续处理
            fixer.fix_all_policy_dates_with_resume()
            
        else:
            print("使用方法:")
            print("  python batch_fix_dates.py start     # 开始处理")
            print("  python batch_fix_dates.py continue  # 继续处理")
            print("  python batch_fix_dates.py status    # 查看进度")
            print("  python batch_fix_dates.py reset     # 重置进度")
    else:
        # 默认显示进度
        fixer.show_progress()
        
        # 询问是否开始处理
        response = input("是否开始/继续处理？(y/N): ")
        if response.lower() in ['y', 'yes', '是']:
            fixer.fix_all_policy_dates_with_resume()

if __name__ == "__main__":
    main()