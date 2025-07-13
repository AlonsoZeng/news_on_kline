#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
政策数据获取和处理模块
用于获取中国政府政策数据并存储到数据库
"""

import requests
import sqlite3
import json
import time
from datetime import datetime, timedelta
import re
from bs4 import BeautifulSoup
import logging
from contextlib import contextmanager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class PolicyDataFetcher:
    def __init__(self, db_path='events.db'):
        self.db_path = db_path
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
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
        
    def init_database(self):
        """初始化数据库表结构"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 创建政策数据表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS policy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    title TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    content TEXT,
                    source_url TEXT,
                    department TEXT,
                    policy_level TEXT,
                    impact_level TEXT,
                    content_type TEXT DEFAULT '政策',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建数据源抓取日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS fetch_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL UNIQUE,
                    last_fetch_time TIMESTAMP NOT NULL,
                    fetch_status TEXT NOT NULL DEFAULT 'success',
                    error_message TEXT,
                    records_fetched INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_fetch_log_source 
                ON fetch_log(source_name)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_fetch_log_time 
                ON fetch_log(last_fetch_time)
            ''')
            
            # 检查并添加content_type字段（为已存在的表添加新字段）
            try:
                cursor.execute("ALTER TABLE policy_events ADD COLUMN content_type TEXT DEFAULT '政策'")
                logger.info("已为policy_events表添加content_type字段")
            except sqlite3.OperationalError:
                # 字段已存在，忽略错误
                pass
            
            conn.commit()
        logger.info("数据库初始化完成")
    
    def should_skip_fetch(self, source_name, min_interval_hours=1):
        """检查是否应该跳过抓取
        
        Args:
            source_name: 数据源名称
            min_interval_hours: 最小抓取间隔（小时）
            
        Returns:
            bool: True表示应该跳过，False表示可以抓取
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 查询上次抓取记录
                cursor.execute('''
                    SELECT last_fetch_time, fetch_status, error_message
                    FROM fetch_log 
                    WHERE source_name = ?
                    ORDER BY last_fetch_time DESC 
                    LIMIT 1
                ''', (source_name,))
                
                result = cursor.fetchone()
            
            if not result:
                # 没有抓取记录，可以抓取
                return False
            
            last_fetch_time_str, last_status, error_message = result
            
            # 解析上次抓取时间
            try:
                last_fetch_time = datetime.strptime(last_fetch_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # 时间格式解析失败，允许抓取
                logger.warning(f"无法解析{source_name}的上次抓取时间: {last_fetch_time_str}")
                return False
            
            # 计算时间间隔
            time_diff = datetime.now() - last_fetch_time
            # hours_diff = time_diff.total_seconds() / 3600
            hours_diff = time_diff.total_seconds() / 1
            
            # 检查时间间隔和上次抓取状态
            if hours_diff < min_interval_hours:
                if last_status == 'success':
                    logger.info(f"跳过{source_name}抓取：距离上次成功抓取仅{hours_diff:.1f}小时（< {min_interval_hours}小时）")
                    return True
                elif last_status == 'error' and error_message:
                    logger.info(f"跳过{source_name}抓取：距离上次失败抓取仅{hours_diff:.1f}小时，错误: {error_message[:100]}")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查{source_name}抓取状态时出错: {e}")
            return False
    
    def record_fetch_status(self, source_name, status, records_count=0, error_message=None):
        """记录抓取状态
        
        Args:
            source_name: 数据源名称
            status: 抓取状态 ('success' 或 'error')
            records_count: 抓取到的记录数
            error_message: 错误信息（如果有）
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                # 使用REPLACE INTO来插入或更新记录
                cursor.execute('''
                    REPLACE INTO fetch_log 
                    (source_name, last_fetch_time, fetch_status, error_message, records_fetched, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (source_name, current_time, status, error_message, records_count, current_time))
                
                conn.commit()
            
            if status == 'success':
                logger.info(f"记录{source_name}抓取成功: {records_count}条记录")
            else:
                logger.warning(f"记录{source_name}抓取失败: {error_message}")
                
        except Exception as e:
            logger.error(f"记录{source_name}抓取状态时出错: {e}")
    
    def fetch_gov_cn_policies(self, days_back=30, target_month=None, max_pages=10):
        """从中国政府网获取政策数据
        
        Args:
            days_back: 获取最近多少天的数据
            target_month: 目标月份，格式为'2025-06'，如果指定则优先抓取该月份数据
            max_pages: 最大抓取分页数，默认10页
        """
        source_name = "gov_cn"
        
        # 检查是否应该跳过抓取
        if self.should_skip_fetch(source_name):
            return []
        
        policies = []
        base_url = "http://www.gov.cn"
        
        try:
            # 获取政策发布页面的基础URL模板
            policy_url_templates = [
                {"url": "https://www.gov.cn/zhengce/zuixin/home_{}.htm", "content_type": "政策"},
            ]
            
            for template_info in policy_url_templates:
                url_template = template_info["url"]
                content_type = template_info["content_type"]
                logger.info(f"开始抓取{content_type}数据")
                
                # 遍历多个分页
                for page in range(max_pages):
                    url = url_template.format(page)
                    logger.info(f"正在获取{content_type}第{page+1}页: {url}")
                    
                    try:
                        response = self.session.get(url, timeout=10)
                        response.encoding = 'utf-8'
                        
                        if response.status_code == 200:
                            soup = BeautifulSoup(response.text, 'html.parser')
                            
                            # 查找政策链接
                            links = soup.find_all('a', href=True)
                            page_policies = 0
                            
                            for link in links:
                                href = link.get('href')
                                title = link.get_text(strip=True)
                                
                                # 过滤备案号和无效内容
                                if self._should_skip_content(title):
                                    continue
                                
                                if href and title and len(title) > 10:
                                    # 构建完整URL
                                    if href.startswith('/'):
                                        full_url = base_url + href
                                    elif href.startswith('http'):
                                        full_url = href
                                    else:
                                        continue
                                    
                                    # 提取日期信息 - 优先从父元素中查找
                                    policy_date = None
                                    
                                    # 首先尝试从URL和标题中提取日期
                                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', href + title)
                                    if date_match:
                                        policy_date = date_match.group(1).replace('/', '-')
                                    
                                    # 如果没找到，从父元素中查找日期
                                    if not policy_date:
                                        parent = link.parent
                                        while parent and not policy_date:
                                            parent_text = parent.get_text()
                                            parent_date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parent_text)
                                            if parent_date_match:
                                                policy_date = parent_date_match.group(1)
                                                break
                                            parent = parent.parent
                                    
                                    # 如果仍然没找到日期，使用当前日期（这种情况应该很少）
                                    if not policy_date:
                                        policy_date = datetime.now().strftime('%Y-%m-%d')
                                        logger.warning(f"无法提取日期信息，使用当前日期: {title[:50]}")
                                    
                                    # 如果指定了目标月份，只抓取该月份的数据
                                    if target_month:
                                        if not policy_date.startswith(target_month):
                                            continue
                                    
                                    # 判断政策类型
                                    event_type = self._classify_policy_type(title, full_url)
                                    
                                    policies.append({
                                        'date': policy_date,
                                        'title': title,
                                        'event_type': event_type,
                                        'source_url': full_url,
                                        'department': self._extract_department(title, full_url),
                                        'policy_level': self._determine_policy_level(title, full_url),
                                        'impact_level': self._assess_impact_level(title),
                                        'content_type': content_type
                                    })
                                    page_policies += 1
                            
                            logger.info(f"{content_type}第{page+1}页获取到 {page_policies} 条数据")
                            
                            # 如果当前页面没有获取到数据，可能已经到达最后一页
                            if page_policies == 0:
                                logger.info(f"{content_type}第{page+1}页无新内容，停止抓取该类型数据")
                                break
                                
                        else:
                            logger.warning(f"{content_type}第{page+1}页请求失败，状态码: {response.status_code}")
                            
                    except Exception as e:
                        logger.error(f"获取{content_type}第{page+1}页时出错: {e}")
                        continue
                    
                    time.sleep(1)  # 避免请求过快
                
        except Exception as e:
            logger.error(f"获取政策数据时出错: {e}")
            # 记录抓取失败状态
            self.record_fetch_status(source_name, 'error', 0, str(e))
            return []
        
        logger.info(f"gov.cn 总共获取到 {len(policies)} 条数据（包含政策和新闻）")
        # 记录抓取成功状态
        self.record_fetch_status(source_name, 'success', len(policies))
        return policies
    
    def fetch_mof_policies(self, target_month=None, max_pages=10):
        """从财政部获取政策数据
        
        Args:
            target_month: 目标月份，格式为'2025-06'，如果指定则优先抓取该月份数据
            max_pages: 最大抓取分页数，默认10页
        """
        source_name = "mof"
        
        # 检查是否应该跳过抓取
        if self.should_skip_fetch(source_name):
            return []
        
        policies = []
        base_url = "https://www.mof.gov.cn"
        
        try:
            logger.info("开始抓取财政部政策数据")
            
            # 遍历多个分页
            for page in range(max_pages):
                # 构建URL：首页是index.htm，后续页面是index_1.htm, index_2.htm等
                if page == 0:
                    url = "https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/index.htm"
                else:
                    url = f"https://www.mof.gov.cn/zhengwuxinxi/zhengcefabu/index_{page}.htm"
                
                logger.info(f"正在获取财政部第{page+1}页: {url}")
                
                try:
                    response = self.session.get(url, timeout=10)
                    response.encoding = 'utf-8'
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 查找政策链接 - 财政部网站通常使用特定的选择器
                        links = soup.find_all('a', href=True)
                        page_policies = 0
                        
                        for link in links:
                            href = link.get('href')
                            title = link.get_text(strip=True)
                            
                            # 过滤备案号和无效内容
                            if self._should_skip_content(title):
                                continue
                            
                            if href and title and len(title) > 10:
                                # 构建完整URL
                                if href.startswith('/'):
                                    full_url = base_url + href
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    continue
                                
                                # 提取日期信息
                                policy_date = None
                                
                                # 首先尝试从URL和标题中提取日期
                                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', href + title)
                                if date_match:
                                    policy_date = date_match.group(1).replace('/', '-')
                                
                                # 如果没找到，从父元素中查找日期
                                if not policy_date:
                                    parent = link.parent
                                    while parent and not policy_date:
                                        parent_text = parent.get_text()
                                        parent_date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parent_text)
                                        if parent_date_match:
                                            policy_date = parent_date_match.group(1)
                                            break
                                        parent = parent.parent
                                
                                # 如果仍然没找到日期，尝试从详情页获取
                                if not policy_date:
                                    policy_date = self._extract_date_from_detail_page(full_url)
                                
                                # 如果还是没找到日期，使用当前日期
                                if not policy_date:
                                    policy_date = datetime.now().strftime('%Y-%m-%d')
                                    logger.warning(f"无法提取日期信息，使用当前日期: {title[:50]}")
                                
                                # 如果指定了目标月份，只抓取该月份的数据
                                if target_month:
                                    if not policy_date.startswith(target_month):
                                        continue
                                
                                # 判断是否为财政政策相关内容
                                if self._is_mof_policy_content(title, full_url):
                                    policies.append({
                                        'date': policy_date,
                                        'title': title,
                                        'event_type': '财政政策',
                                        'source_url': full_url,
                                        'department': '财政部',
                                        'policy_level': '国家级',
                                        'impact_level': self._assess_impact_level(title),
                                        'content_type': '政策'
                                    })
                                    page_policies += 1
                        
                        logger.info(f"财政部第{page+1}页获取到 {page_policies} 条政策")
                        
                        # 如果当前页面没有获取到数据，可能已经到达最后一页
                        if page_policies == 0:
                            logger.info(f"财政部第{page+1}页无新内容，停止抓取")
                            break
                            
                    else:
                        logger.warning(f"财政部第{page+1}页请求失败，状态码: {response.status_code}")
                        # 如果是404等错误，可能已经超出分页范围
                        if response.status_code == 404:
                            logger.info(f"财政部第{page+1}页不存在，停止抓取")
                            break
                        
                except Exception as e:
                    logger.error(f"获取财政部第{page+1}页时出错: {e}")
                    continue
                
                time.sleep(1)  # 避免请求过快
                
        except Exception as e:
            logger.error(f"获取财政部政策数据时出错: {e}")
            # 记录抓取失败状态
            self.record_fetch_status(source_name, 'error', 0, str(e))
            return []
        
        logger.info(f"财政部总共获取到 {len(policies)} 条政策数据")
        # 记录抓取成功状态
        self.record_fetch_status(source_name, 'success', len(policies))
        return policies
    
    def fetch_ndrc_policies(self, target_month=None, max_pages=10):
        """从国家发改委获取政策数据
        
        Args:
            target_month: 目标月份，格式为'2025-06'，如果指定则优先抓取该月份数据
            max_pages: 最大抓取分页数，默认10页
        """
        source_name = "ndrc"
        
        # 检查是否应该跳过抓取
        if self.should_skip_fetch(source_name):
            return []
        
        policies = []
        base_url = "https://www.ndrc.gov.cn"
        
        try:
            # 发改委政策页面模板（发改委令页面）
            url_templates = [
                "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/index_{}.html"  # 发改委令分页
            ]
            
            # 首先尝试主页面
            main_urls = [
                "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/index.html"  # 发改委令首页
            ]
            
            for url in main_urls:
                logger.info(f"正在获取发改委主页: {url}")
                try:
                    response = self.session.get(url, timeout=10)
                    response.encoding = 'utf-8'
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 查找政策链接
                        links = soup.find_all('a', href=True)
                        page_policies = 0
                        
                        for link in links:
                            href = link.get('href')
                            title = link.get_text(strip=True)
                            
                            # 过滤备案号和无效内容
                            if self._should_skip_content(title):
                                continue
                            
                            if href and title and len(title) > 10:
                                if href.startswith('/'):
                                    full_url = base_url + href
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    continue
                                
                                # 提取日期
                                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', href + title)
                                if date_match:
                                    policy_date = date_match.group(1).replace('/', '-')
                                else:
                                    policy_date = datetime.now().strftime('%Y-%m-%d')
                                
                                # 如果指定了目标月份，只抓取该月份的数据
                                if target_month:
                                    if not policy_date.startswith(target_month):
                                        continue
                                
                                policies.append({
                                    'date': policy_date,
                                    'title': title,
                                    'event_type': '发改委政策',
                                    'source_url': full_url,
                                    'department': '国家发改委',
                                    'policy_level': '国家级',
                                    'impact_level': self._assess_impact_level(title)
                                })
                                page_policies += 1
                        
                        logger.info(f"发改委主页获取到 {page_policies} 条政策")
                        
                except Exception as e:
                    logger.error(f"获取发改委主页时出错: {e}")
                    continue
                
                time.sleep(1)
            
            # 尝试分页抓取（发改委令分页格式：第一页index.html，第二页index_1.html，第三页index_2.html...）
            base_page_url = "https://www.ndrc.gov.cn/xxgk/zcfb/fzggwl/index"
            for page in range(1, min(max_pages + 1, 11)):  # 限制在10页内
                if page == 1:
                    url = f"{base_page_url}.html"  # 第一页
                else:
                    url = f"{base_page_url}_{page-1}.html"  # 第二页是index_1.html，第三页是index_2.html
                logger.info(f"正在尝试发改委第{page}页: {url}")
                
                try:
                    response = self.session.get(url, timeout=10)
                    response.encoding = 'utf-8'
                    
                    if response.status_code == 200:
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # 查找政策链接
                        links = soup.find_all('a', href=True)
                        page_policies = 0
                        
                        for link in links:
                            href = link.get('href')
                            title = link.get_text(strip=True)
                            
                            if href and title and len(title) > 10:
                                if href.startswith('/'):
                                    full_url = base_url + href
                                elif href.startswith('http'):
                                    full_url = href
                                else:
                                    continue
                                
                                # 提取日期
                                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', href + title)
                                if date_match:
                                    policy_date = date_match.group(1).replace('/', '-')
                                else:
                                    policy_date = datetime.now().strftime('%Y-%m-%d')
                                
                                # 如果指定了目标月份，只抓取该月份的数据
                                if target_month:
                                    if not policy_date.startswith(target_month):
                                        continue
                                
                                policies.append({
                                    'date': policy_date,
                                    'title': title,
                                    'event_type': '发改委政策',
                                    'source_url': full_url,
                                    'department': '国家发改委',
                                    'policy_level': '国家级',
                                    'impact_level': self._assess_impact_level(title)
                                })
                                page_policies += 1
                        
                        logger.info(f"发改委第{page}页获取到 {page_policies} 条政策")
                        
                        # 如果当前页面没有获取到政策，可能已经到达最后一页
                        if page_policies == 0:
                            logger.info(f"发改委第{page}页无新内容，停止抓取")
                            break
                            
                    else:
                        logger.warning(f"发改委第{page}页请求失败，状态码: {response.status_code}")
                        if response.status_code == 404:
                            break  # 404说明页面不存在，停止抓取
                            
                except Exception as e:
                    logger.error(f"获取发改委第{page}页时出错: {e}")
                    continue
                
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"获取发改委数据时出错: {e}")
            # 记录抓取失败状态
            self.record_fetch_status(source_name, 'error', 0, str(e))
            return []
        
        logger.info(f"发改委总共获取到 {len(policies)} 条政策")
        # 记录抓取成功状态
        self.record_fetch_status(source_name, 'success', len(policies))
        return policies
    
    def _classify_policy_type(self, title, url):
        """根据标题和URL分类政策类型"""
        title_lower = title.lower()
        url_lower = url.lower()
        
        if any(keyword in title for keyword in ['货币', '央行', '利率', '准备金', '流动性']):
            return '货币政策'
        elif any(keyword in title for keyword in ['财政', '税收', '减税', '财政部', '预算']):
            return '财政政策'
        elif any(keyword in title for keyword in ['房地产', '楼市', '住房', '房价']):
            return '房地产政策'
        elif any(keyword in title for keyword in ['股市', '证券', '上市', 'IPO', '证监会']):
            return '证券政策'
        elif any(keyword in title for keyword in ['经济', '发展', '改革', '开放']):
            return '经济政策'
        elif any(keyword in title for keyword in ['环保', '环境', '碳', '绿色']):
            return '环保政策'
        elif any(keyword in title for keyword in ['科技', '创新', '研发', '技术']):
            return '科技政策'
        else:
            return '其他政策'
    
    def _extract_department(self, title, url):
        """提取发布部门"""
        departments = {
            '国务院': ['国务院', 'guowuyuan'],
            '央行': ['央行', '人民银行', 'pbc'],
            '财政部': ['财政部', 'mof'],
            '发改委': ['发改委', 'ndrc'],
            '证监会': ['证监会', 'csrc'],
            '银保监会': ['银保监会', 'cbirc'],
            '商务部': ['商务部', 'mofcom']
        }
        
        for dept, keywords in departments.items():
            if any(keyword in title or keyword in url.lower() for keyword in keywords):
                return dept
        
        return '未知部门'
    
    def _determine_policy_level(self, title, url):
        """判断政策级别"""
        if any(keyword in title for keyword in ['国务院', '中央', '全国']):
            return '国家级'
        elif any(keyword in title for keyword in ['省', '市', '地方']):
            return '地方级'
        else:
            return '部委级'
    
    def _assess_impact_level(self, title):
        """评估影响级别"""
        high_impact_keywords = ['重大', '重要', '关键', '核心', '全面', '深化', '改革']
        medium_impact_keywords = ['推进', '加强', '完善', '优化', '提升']
        
        if any(keyword in title for keyword in high_impact_keywords):
            return '高'
        elif any(keyword in title for keyword in medium_impact_keywords):
            return '中'
        else:
            return '低'
    
    def _should_skip_content(self, title):
        """判断是否应该跳过该内容（过滤备案号等无效信息）"""
        if not title or len(title.strip()) == 0:
            return True
        
        title_lower = title.lower().strip()
        
        # 过滤备案号
        icp_patterns = [
            r'京icp备\d+号',
            r'icp备案号',
            r'京公网安备\d+号',
            r'公安备案号',
            r'网站备案',
            r'备案号',
            r'icp证',
            r'许可证号'
        ]
        
        for pattern in icp_patterns:
            if re.search(pattern, title_lower):
                return True
        
        # 过滤其他无效内容
        skip_keywords = [
            '版权所有',
            'copyright',
            '联系我们',
            '网站地图',
            '免责声明',
            '隐私政策',
            '使用条款',
            '技术支持',
            '网站维护',
            '更多',
            '查看更多',
            '点击查看',
            '详情',
            '返回',
            '首页',
            '上一页',
            '下一页',
            '分享',
            '打印',
            '收藏',
            '关闭',
            '确定',
            '取消'
        ]
        
        for keyword in skip_keywords:
            if keyword in title_lower:
                return True
        
        # 过滤过短的标题（可能是导航链接）
        if len(title.strip()) < 8:
            return True
        
        # 过滤纯数字或日期格式的标题
        if re.match(r'^\d{4}[-/]\d{1,2}[-/]\d{1,2}$', title.strip()):
            return True
        
        return False
    
    def _extract_date_from_detail_page(self, url):
        """从详情页提取发布日期"""
        try:
            response = self.session.get(url, timeout=10)
            response.encoding = 'utf-8'
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 尝试多种日期提取方式
                date_patterns = [
                    r'发布时间[：:]\s*(\d{4}-\d{2}-\d{2})',
                    r'发文日期[：:]\s*(\d{4}-\d{2}-\d{2})',
                    r'时间[：:]\s*(\d{4}-\d{2}-\d{2})',
                    r'日期[：:]\s*(\d{4}-\d{2}-\d{2})',
                    r'(\d{4}年\d{1,2}月\d{1,2}日)',
                    r'(\d{4}-\d{2}-\d{2})'
                ]
                
                page_text = soup.get_text()
                for pattern in date_patterns:
                    match = re.search(pattern, page_text)
                    if match:
                        date_str = match.group(1)
                        # 处理中文日期格式
                        if '年' in date_str:
                            date_str = re.sub(r'(\d{4})年(\d{1,2})月(\d{1,2})日', r'\1-\2-\3', date_str)
                            # 补齐月份和日期的零
                            parts = date_str.split('-')
                            if len(parts) == 3:
                                date_str = f"{parts[0]}-{parts[1].zfill(2)}-{parts[2].zfill(2)}"
                        return date_str
                        
        except Exception as e:
            logger.warning(f"从详情页提取日期失败 {url}: {e}")
        
        return None
    
    def _is_mof_policy_content(self, title, url):
        """判断是否为财政部政策相关内容"""
        # 财政政策相关关键词
        policy_keywords = [
            '通知', '公告', '办法', '规定', '意见', '方案', '政策', '措施',
            '财政', '税收', '预算', '资金', '补贴', '奖励', '支持', '管理',
            '实施', '暂行', '试行', '修订', '废止', '解释', '细则'
        ]
        
        # 排除的内容类型
        exclude_keywords = [
            '招聘', '采购', '中标', '公示', '会议', '新闻', '动态',
            '领导', '机构', '简介', '职能', '联系', '地址'
        ]
        
        title_lower = title.lower()
        
        # 检查是否包含排除关键词
        for keyword in exclude_keywords:
            if keyword in title:
                return False
        
        # 检查是否包含政策关键词
        for keyword in policy_keywords:
            if keyword in title:
                return True
        
        # 检查URL是否包含政策相关路径
        policy_url_patterns = [
            'zhengcefabu',  # 政策发布
            'policy',
            'notice',
            'announcement'
        ]
        
        for pattern in policy_url_patterns:
            if pattern in url.lower():
                return True
        
        return False
    
    def save_policies_to_db(self, policies):
        """保存政策数据到数据库"""
        if not policies:
            logger.info("没有新的政策数据需要保存")
            return 0
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            saved_count = 0
            
            for policy in policies:
                try:
                    # 检查是否已存在相同的政策
                    cursor.execute(
                        "SELECT id FROM policy_events WHERE title = ? AND date = ?",
                        (policy['title'], policy['date'])
                    )
                    
                    if cursor.fetchone() is None:
                        cursor.execute(
                            """
                            INSERT INTO policy_events 
                            (date, title, event_type, source_url, department, policy_level, impact_level, content_type)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                policy['date'],
                                policy['title'],
                                policy['event_type'],
                                policy.get('source_url', ''),
                                policy.get('department', ''),
                                policy.get('policy_level', ''),
                                policy.get('impact_level', ''),
                                policy.get('content_type', '政策')
                            )
                        )
                        saved_count += 1
                        
                except Exception as e:
                    logger.error(f"保存政策数据时出错: {e}")
                    continue
            
            conn.commit()
        
        logger.info(f"成功保存 {saved_count} 条政策数据")
        return saved_count
    
    def migrate_old_events(self):
        """将旧的events表数据迁移到新的policy_events表"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # 检查旧表是否存在
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
                if cursor.fetchone():
                    # 获取旧数据
                    cursor.execute("SELECT date, title, event_type FROM events")
                    old_events = cursor.fetchall()
                    
                    migrated_count = 0
                    for event in old_events:
                        date, title, event_type = event
                        
                        # 检查新表中是否已存在
                        cursor.execute(
                            "SELECT id FROM policy_events WHERE title = ? AND date = ?",
                            (title, date)
                        )
                        
                        if cursor.fetchone() is None:
                            cursor.execute(
                                """
                                INSERT INTO policy_events 
                                (date, title, event_type, department, policy_level, impact_level, content_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (date, title, event_type, '模拟数据', '测试级', '低', '政策')
                            )
                            migrated_count += 1
                    
                    conn.commit()
                    logger.info(f"成功迁移 {migrated_count} 条历史数据")
                    
            except Exception as e:
                logger.error(f"数据迁移时出错: {e}")
    
    def fetch_csrc_policies(self, max_pages=50):
        """从证监会API获取政策数据
        
        Args:
            max_pages: 最大抓取分页数，默认50页
        """
        source_name = "csrc"
        
        # 检查是否应该跳过抓取
        if self.should_skip_fetch(source_name):
            return []
        
        policies = []
        base_url = "http://www.csrc.gov.cn/searchList/a1a078ee0bc54721ab6b148884c784a8"
        
        try:
            logger.info(f"开始抓取证监会政策数据，最多抓取 {max_pages} 页")
            
            for page in range(1, max_pages + 1):
                url = f"{base_url}?_isAgg=true&_isJson=true&_pageSize=18&_template=index&page={page}"
                logger.info(f"正在获取证监会第{page}页: {url}")
                
                try:
                    response = self.session.get(url, timeout=10)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # 检查返回数据结构
                            if 'data' in data and 'results' in data['data']:
                                results = data['data']['results']
                                page_policies = 0
                                
                                for item in results:
                                    try:
                                        # 提取基本信息，添加空值检查
                                        title = (item.get('title') or '').strip()
                                        content = (item.get('content') or '').strip()
                                        memo = (item.get('memo') or '').strip()
                                        
                                        # 跳过无效数据
                                        if not title or len(title) < 5:
                                            continue
                                        
                                        # 过滤备案号和无效内容
                                        if self._should_skip_content(title):
                                            continue
                                        
                                        # 提取日期信息
                                        policy_date = self._extract_date_from_csrc_item(item)
                                        
                                        # 提取部门信息
                                        department = self._extract_department_from_csrc_item(item)
                                        
                                        # 构建详情页URL（如果有的话）
                                        source_url = self._extract_url_from_csrc_item(item)
                                        
                                        # 判断政策类型
                                        event_type = self._classify_csrc_policy_type(title, content)
                                        
                                        # 评估影响级别
                                        impact_level = self._assess_impact_level(title)
                                        
                                        policies.append({
                                            'date': policy_date,
                                            'title': title,
                                            'event_type': event_type,
                                            'content': content or memo,
                                            'source_url': source_url,
                                            'department': department,
                                            'policy_level': '国家级',
                                            'impact_level': impact_level,
                                            'content_type': '政策'
                                        })
                                        page_policies += 1
                                        
                                    except Exception as e:
                                        logger.warning(f"解析证监会数据项时出错: {e}")
                                        continue
                                
                                logger.info(f"证监会第{page}页获取到 {page_policies} 条政策")
                                
                                # 如果当前页面没有获取到数据，可能已经到达最后一页
                                if page_policies == 0:
                                    logger.info(f"证监会第{page}页无新内容，停止抓取")
                                    break
                                    
                            else:
                                logger.warning(f"证监会第{page}页返回数据格式异常")
                                
                        except json.JSONDecodeError as e:
                            logger.error(f"证监会第{page}页JSON解析失败: {e}")
                            continue
                            
                    else:
                        logger.warning(f"证监会第{page}页请求失败，状态码: {response.status_code}")
                        # 如果是404等错误，可能已经超出分页范围
                        if response.status_code == 404:
                            logger.info(f"证监会第{page}页不存在，停止抓取")
                            break
                        
                except Exception as e:
                    logger.error(f"获取证监会第{page}页时出错: {e}")
                    continue
                
                time.sleep(0.5)  # 避免请求过快
                
        except Exception as e:
            logger.error(f"获取证监会政策数据时出错: {e}")
            # 记录抓取失败状态
            self.record_fetch_status(source_name, 'error', 0, str(e))
            return []
        
        logger.info(f"证监会总共获取到 {len(policies)} 条政策数据")
        # 记录抓取成功状态
        self.record_fetch_status(source_name, 'success', len(policies))
        return policies
    
    def _extract_date_from_csrc_item(self, item):
        """从证监会数据项中提取日期"""
        # 优先使用publishedTimeStr字段
        if 'publishedTimeStr' in item and item['publishedTimeStr']:
            published_time_str = str(item['publishedTimeStr']).strip()
            # 从yyyy-mm-dd hh:mm:ss格式提取yyyy-mm-dd部分
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', published_time_str)
            if date_match:
                return date_match.group(1)
        
        # 备用方案：尝试从其他字段中提取日期
        date_fields = ['publishTime', 'createTime', 'updateTime']
        
        for field in date_fields:
            if field in item and item[field]:
                date_str = str(item[field])
                # 尝试解析日期格式
                date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', date_str)
                if date_match:
                    return date_match.group(1).replace('/', '-')
        
        # 如果没找到日期，使用当前日期
        return datetime.now().strftime('%Y-%m-%d')
    
    def _extract_department_from_csrc_item(self, item):
        """从证监会数据项中提取部门信息"""
        # 尝试从domainMetaList中提取部门信息
        if 'domainMetaList' in item:
            for domain in item['domainMetaList']:
                if 'resultList' in domain:
                    for result in domain['resultList']:
                        if result.get('key') == 'section' or result.get('name') == '部门':
                            dept = (result.get('value') or '').strip()
                            if dept:
                                return dept
        
        # 默认返回证监会
        return '证监会'
    
    def _extract_url_from_csrc_item(self, item):
        """从证监会数据项中提取详情页URL"""
        # 尝试从item中提取URL信息
        if 'url' in item and item['url']:
            url = item['url']
            if url.startswith('/'):
                return f"http://www.csrc.gov.cn{url}"
            elif url.startswith('http'):
                return url
        
        # 如果没有具体URL，返回证监会主页
        return "http://www.csrc.gov.cn"
    
    def _classify_csrc_policy_type(self, title, content):
        """分类证监会政策类型"""
        title_lower = title.lower()
        content_lower = content.lower() if content else ''
        
        # 证监会特有的政策类型关键词
        if any(keyword in title_lower for keyword in ['上市', '发行', 'ipo', '股票']):
            return '上市监管'
        elif any(keyword in title_lower for keyword in ['基金', '资管', '理财']):
            return '基金监管'
        elif any(keyword in title_lower for keyword in ['期货', '衍生品', '期权']):
            return '期货监管'
        elif any(keyword in title_lower for keyword in ['债券', '公司债', '企业债']):
            return '债券监管'
        elif any(keyword in title_lower for keyword in ['违法', '处罚', '罚款', '警告']):
            return '执法监管'
        elif any(keyword in title_lower for keyword in ['规则', '办法', '规定', '指引']):
            return '制度建设'
        else:
            return '证券监管'
    
    def fetch_all_policies(self, target_month=None, max_pages=10):
        """获取所有来源的政策数据
        
        Args:
            target_month: 目标月份，格式为'2025-06'，如果指定则优先抓取该月份数据
            max_pages: 最大抓取分页数，默认10页
        """
        if target_month:
            logger.info(f"开始获取 {target_month} 月份的政策数据，最多抓取 {max_pages} 页...")
        else:
            logger.info(f"开始获取政策数据，最多抓取 {max_pages} 页...")
        
        all_policies = []
        
        # 从各个来源获取数据
        gov_policies = self.fetch_gov_cn_policies(target_month=target_month, max_pages=max_pages)
        ndrc_policies = self.fetch_ndrc_policies(target_month=target_month, max_pages=max_pages)
        mof_policies = self.fetch_mof_policies(target_month=target_month, max_pages=max_pages)
        csrc_policies = self.fetch_csrc_policies(max_pages=50)  # 证监会抓取50页
        
        all_policies.extend(gov_policies)
        all_policies.extend(ndrc_policies)
        all_policies.extend(mof_policies)
        all_policies.extend(csrc_policies)
        
        # 增强去重逻辑：基于标题和URL进行去重
        unique_policies = []
        seen_items = set()  # 存储 (title, url) 元组
        
        for policy in all_policies:
            # 创建去重标识：标题 + URL
            dedup_key = (policy['title'].strip(), policy['source_url'])
            
            if dedup_key not in seen_items:
                unique_policies.append(policy)
                seen_items.add(dedup_key)
            else:
                logger.debug(f"发现重复政策，已跳过: {policy['title'][:50]}...")
        
        logger.info(f"原始数据 {len(all_policies)} 条，去重后 {len(unique_policies)} 条唯一政策数据")
        return unique_policies
    
    def run_data_collection(self, target_month=None, max_pages=10):
        """运行数据收集流程
        
        Args:
            target_month: 目标月份，格式为'2025-06'，如果指定则优先抓取该月份数据
            max_pages: 最大抓取分页数，默认10页
        """
        if target_month:
            logger.info(f"开始收集 {target_month} 月份的政策数据，最多抓取 {max_pages} 页")
        else:
            logger.info(f"开始收集政策数据，最多抓取 {max_pages} 页")
        
        # 初始化数据库
        self.init_database()
        
        # 迁移旧数据
        self.migrate_old_events()
        
        # 获取新数据
        policies = self.fetch_all_policies(target_month=target_month, max_pages=max_pages)
        
        # 增量更新：过滤掉数据库中已存在的政策
        new_policies = self._filter_new_policies(policies)
        
        # 保存到数据库
        saved_count = self.save_policies_to_db(new_policies)
        
        logger.info(f"数据收集完成，抓取 {len(policies)} 条，过滤后 {len(new_policies)} 条新数据，实际保存 {saved_count} 条")
        
        # 如果有新数据，尝试触发AI分析
        if saved_count > 0:
            try:
                from .ai_policy_analyzer import AIPolicyAnalyzer
                import os
                import sys
                
                # 获取AI API Key
                api_key = os.getenv('SILICONFLOW_API_KEY', 'sk-rtfxnalfnpfrucbjvzzizgsltocaywdtfvvcmloznshsqzfo')
                
                if api_key and api_key != 'YOUR_SILICONFLOW_API_KEY':
                    analyzer = AIPolicyAnalyzer(api_key, self.db_path)
                    
                    # 优先使用异步分析（如果数据量较大）
                    if saved_count >= 5:
                        import asyncio
                        
                        # Python 3.7+ 兼容性处理
                        if sys.version_info >= (3, 7):
                            analyzed_count = asyncio.run(
                                analyzer.analyze_unprocessed_policies_async(
                                    limit=saved_count + 5,
                                    max_concurrent=3  # 数据抓取时使用较小的并发数
                                )
                            )
                        else:
                            # Python 3.6 及以下版本的兼容性处理
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                analyzed_count = loop.run_until_complete(
                                    analyzer.analyze_unprocessed_policies_async(
                                        limit=saved_count + 5,
                                        max_concurrent=3
                                    )
                                )
                            finally:
                                loop.close()
                        
                        logger.info(f"AI异步分析完成，成功分析 {analyzed_count} 条新政策")
                    else:
                        # 数据量较小时使用同步分析
                        analyzed_count = analyzer.analyze_unprocessed_policies(limit=saved_count)
                        logger.info(f"AI同步分析完成，成功分析 {analyzed_count} 条新政策")
                else:
                    logger.warning("未配置AI API Key，跳过自动AI分析")
            except Exception as e:
                logger.error(f"自动AI分析失败: {str(e)}")
        
        return saved_count
    
    def _filter_new_policies(self, policies):
        """过滤出数据库中不存在的新政策
        
        Args:
            policies: 政策列表
            
        Returns:
            list: 新政策列表
        """
        if not policies:
            return []
        
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            new_policies = []
            
            try:
                for policy in policies:
                    # 检查数据库中是否已存在相同标题和URL的政策
                    cursor.execute(
                        "SELECT id FROM policy_events WHERE title = ? AND source_url = ?",
                        (policy['title'], policy['source_url'])
                    )
                    
                    if cursor.fetchone() is None:
                        new_policies.append(policy)
                    else:
                        logger.debug(f"数据库中已存在政策，跳过: {policy['title'][:50]}...")
                        
            except Exception as e:
                logger.error(f"过滤新政策时出错: {e}")
                # 如果出错，返回所有政策（让save_policies_to_db处理重复）
                new_policies = policies
        
        logger.info(f"过滤完成：原有 {len(policies)} 条，新增 {len(new_policies)} 条")
        return new_policies

def main():
    """主函数"""
    fetcher = PolicyDataFetcher()
    fetcher.run_data_collection()

if __name__ == "__main__":
    main()