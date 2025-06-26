#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修正政策数据库中的日期字段
从政策链接页面提取真实的发布日期
"""

import sqlite3
import requests
import re
import time
from datetime import datetime
from bs4 import BeautifulSoup
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PolicyDateFixer:
    def __init__(self, db_path='events.db'):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.updated_count = 0
        self.skipped_count = 0
        self.error_count = 0
    
    def extract_publish_date_from_url(self, url, title):
        """从政策页面URL提取发布日期
        
        Args:
            url: 政策页面URL
            title: 政策标题
            
        Returns:
            str: 格式化的日期字符串 (YYYY-MM-DD) 或 None
        """
        try:
            logger.debug(f"正在提取日期: {url}")
            
            # 首先尝试从URL中提取日期
            url_date_patterns = [
                r'/(\d{4})/(\d{1,2})/(\d{1,2})/',  # /2024/06/15/
                r'/(\d{4})-(\d{1,2})-(\d{1,2})',   # /2024-06-15
                r'/(\d{4})(\d{2})(\d{2})/',        # /20240615/
                r't(\d{8})',                       # t20240615
                r'content_(\d{4})_(\d{2})(\d{2})', # content_2024_0615
            ]
            
            for pattern in url_date_patterns:
                match = re.search(pattern, url)
                if match:
                    if len(match.groups()) == 3:
                        year, month, day = match.groups()
                        try:
                            # 验证日期有效性
                            date_obj = datetime(int(year), int(month), int(day))
                            return date_obj.strftime('%Y-%m-%d')
                        except ValueError:
                            continue
                    elif len(match.groups()) == 1 and len(match.group(1)) == 8:
                        # 处理 YYYYMMDD 格式
                        date_str = match.group(1)
                        try:
                            year = int(date_str[:4])
                            month = int(date_str[4:6])
                            day = int(date_str[6:8])
                            date_obj = datetime(year, month, day)
                            return date_obj.strftime('%Y-%m-%d')
                        except ValueError:
                            continue
            
            # 如果URL中没有找到日期，尝试访问页面内容
            try:
                response = self.session.get(url, timeout=10)
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # 常见的发布日期模式
                    date_patterns = [
                        # 中文日期格式
                        r'发布时间[：:](\d{4})[年-](\d{1,2})[月-](\d{1,2})[日号]',
                        r'发布日期[：:](\d{4})[年-](\d{1,2})[月-](\d{1,2})[日号]',
                        r'时间[：:](\d{4})[年-](\d{1,2})[月-](\d{1,2})[日号]',
                        r'日期[：:](\d{4})[年-](\d{1,2})[月-](\d{1,2})[日号]',
                        r'(\d{4})[年-](\d{1,2})[月-](\d{1,2})[日号]',
                        
                        # 标准日期格式
                        r'发布时间[：:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
                        r'发布日期[：:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
                        r'时间[：:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
                        r'日期[：:]\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
                        
                        # 通用日期格式
                        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})\s*\d{2}:\d{2}',
                        r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})',
                    ]
                    
                    page_text = soup.get_text()
                    
                    for pattern in date_patterns:
                        matches = re.findall(pattern, page_text)
                        for match in matches:
                            try:
                                if len(match) == 3:
                                    year, month, day = match
                                    date_obj = datetime(int(year), int(month), int(day))
                                    # 验证日期合理性（不能是未来日期，不能太久远）
                                    if 2000 <= date_obj.year <= datetime.now().year:
                                        if date_obj <= datetime.now():
                                            return date_obj.strftime('%Y-%m-%d')
                            except (ValueError, TypeError):
                                continue
                    
                    # 尝试查找特定的HTML元素
                    date_selectors = [
                        '.time', '.date', '.publish-time', '.publish-date',
                        '#time', '#date', '#publish-time', '#publish-date',
                        '[class*="time"]', '[class*="date"]',
                        '.article-time', '.article-date', '.news-time', '.news-date'
                    ]
                    
                    for selector in date_selectors:
                        elements = soup.select(selector)
                        for element in elements:
                            text = element.get_text(strip=True)
                            for pattern in date_patterns:
                                match = re.search(pattern, text)
                                if match:
                                    try:
                                        if len(match.groups()) == 3:
                                            year, month, day = match.groups()
                                            date_obj = datetime(int(year), int(month), int(day))
                                            if 2000 <= date_obj.year <= datetime.now().year:
                                                if date_obj <= datetime.now():
                                                    return date_obj.strftime('%Y-%m-%d')
                                    except (ValueError, TypeError):
                                        continue
                
            except Exception as e:
                logger.debug(f"访问页面失败 {url}: {e}")
                
        except Exception as e:
            logger.error(f"提取日期时出错 {url}: {e}")
        
        return None
    
    def fix_all_policy_dates(self, limit=None, batch_size=50):
        """修正所有政策的日期
        
        Args:
            limit: 限制处理的记录数，None表示处理所有
            batch_size: 批处理大小
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # 获取需要修正的记录
            if limit:
                cursor.execute('''
                    SELECT id, title, source_url, date 
                    FROM policy_events 
                    WHERE source_url IS NOT NULL AND source_url != ''
                    ORDER BY id
                    LIMIT ?
                ''', (limit,))
            else:
                cursor.execute('''
                    SELECT id, title, source_url, date 
                    FROM policy_events 
                    WHERE source_url IS NOT NULL AND source_url != ''
                    ORDER BY id
                ''')
            
            records = cursor.fetchall()
            total_records = len(records)
            
            logger.info(f"开始修正 {total_records} 条政策记录的日期")
            
            for i, (record_id, title, source_url, current_date) in enumerate(records, 1):
                logger.info(f"处理第 {i}/{total_records} 条: {title[:50]}...")
                
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
                    
                elif real_date:
                    logger.debug(f"  - 日期无需更新: {current_date}")
                    self.skipped_count += 1
                    
                else:
                    logger.warning(f"  ✗ 无法提取日期，跳过: {source_url}")
                    self.skipped_count += 1
                
                # 批量提交
                if i % batch_size == 0:
                    conn.commit()
                    logger.info(f"已处理 {i} 条记录，已更新 {self.updated_count} 条")
                
                # 避免请求过快
                time.sleep(0.5)
            
            # 最终提交
            conn.commit()
            
            logger.info(f"日期修正完成！")
            logger.info(f"总处理: {total_records} 条")
            logger.info(f"已更新: {self.updated_count} 条")
            logger.info(f"已跳过: {self.skipped_count} 条")
            logger.info(f"错误数: {self.error_count} 条")
            
        except Exception as e:
            logger.error(f"修正日期时出错: {e}")
            conn.rollback()
        finally:
            conn.close()

def main():
    """主函数"""
    import sys
    
    # 解析命令行参数
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            logger.info(f"限制处理 {limit} 条记录")
        except ValueError:
            logger.error("参数必须是数字")
            return
    
    fixer = PolicyDateFixer()
    fixer.fix_all_policy_dates(limit=limit)

if __name__ == "__main__":
    main()