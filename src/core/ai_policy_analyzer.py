# 建议整理导入
from typing import Dict, List, Optional
import asyncio
import json
import logging
import random
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

import aiohttp
import openai
import requests
from bs4 import BeautifulSoup

# 配置常量
class Config:
    # API配置
    DEFAULT_API_BASE_URL = "https://api.siliconflow.cn"
    DEFAULT_MODEL = "Qwen/Qwen2.5-7B-Instruct"
    
    # 重试配置
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_BASE_DELAY = 1
    DEFAULT_MAX_DELAY = 60
    
    # 速率限制配置
    DEFAULT_MAX_CALLS = 10
    DEFAULT_TIME_WINDOW = 60
    
    # 内容抓取配置
    REQUEST_TIMEOUT = 10
    MIN_CONTENT_LENGTH = 200
    FULL_CONTENT_THRESHOLD = 500
    PARTIAL_CONTENT_THRESHOLD = 100
    MAX_CONTENT_LENGTH = 3000
    BATCH_DELAY = 0.8  # 批量处理间隔延迟（秒）
    
    # 请求头配置
    DEFAULT_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    # 内容选择器
    CONTENT_SELECTORS = [
        '.content', '.article-content', '.policy-content', '.main-content',
        '#content', '#article-content', '#policy-content', '#main-content',
        '.text', '.article-text', '.policy-text',
        'article', '.article', '.post-content',
        '.TRS_Editor', '.Custom_UnionStyle',  # 政府网站常用的编辑器类名
        '[class*="content"]', '[class*="article"]', '[class*="text"]'
    ]
    
    # 过滤关键词
    FILTER_KEYWORDS = ['导航', '菜单', '首页', '返回', '上一页', '下一页', '版权', '联系我们', 'Copyright']

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_with_backoff(max_retries=Config.DEFAULT_MAX_RETRIES, 
                      base_delay=Config.DEFAULT_BASE_DELAY, 
                      max_delay=Config.DEFAULT_MAX_DELAY):
    """重试装饰器，带指数退避和随机抖动"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.Timeout, 
                       requests.exceptions.ConnectionError,
                       requests.exceptions.RequestException,
                       openai.error.RateLimitError,
                       openai.error.APIError) as e:
                    last_exception = e
                    if attempt == max_retries - 1:
                        logger.error(f"API调用失败，已重试{max_retries}次: {str(e)}")
                        break
                    
                    # 指数退避 + 随机抖动
                    delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
                    logger.warning(f"API调用失败，{delay:.2f}秒后重试 (第{attempt+1}次): {str(e)}")
                    time.sleep(delay)
                except Exception as e:
                    logger.error(f"API调用发生未预期异常: {str(e)}")
                    return None
            
            # 如果所有重试都失败，记录最后一个异常
            if last_exception:
                logger.error(f"重试失败，最后异常: {str(last_exception)}")
            return None
        return wrapper
    return decorator

class RateLimiter:
    """API速率限制器"""
    def __init__(self, max_calls=Config.DEFAULT_MAX_CALLS, time_window=Config.DEFAULT_TIME_WINDOW):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
        self._lock = asyncio.Lock() if hasattr(asyncio, 'current_task') else None
    
    async def wait_if_needed(self):
        """检查是否需要等待以满足速率限制"""
        if self._lock:
            async with self._lock:
                await self._check_and_wait()
        else:
            self._check_and_wait_sync()
    
    def _check_and_wait_sync(self):
        """同步版本的速率检查"""
        now = time.time()
        # 移除时间窗口外的调用记录
        self.calls = [call_time for call_time in self.calls if call_time > now - self.time_window]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.time_window - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(f"达到速率限制，等待 {sleep_time:.2f} 秒")
                time.sleep(sleep_time)
        
        self.calls.append(now)
    
    async def _check_and_wait(self):
        """异步版本的速率检查"""
        now = time.time()
        # 移除时间窗口外的调用记录
        self.calls = [call_time for call_time in self.calls if call_time > now - self.time_window]
        
        if len(self.calls) >= self.max_calls:
            sleep_time = self.time_window - (now - self.calls[0])
            if sleep_time > 0:
                logger.info(f"达到速率限制，等待 {sleep_time:.2f} 秒")
                await asyncio.sleep(sleep_time)
        
        self.calls.append(now)

class AIPolicyAnalyzer:
    """AI政策分析器，使用硅基流动API分析政策新闻的相关行业、板块、个股"""
    
    def __init__(self, api_key: str, db_path: str = 'events.db', model: str = None):
        self.api_key = api_key
        self.api_base_url = Config.DEFAULT_API_BASE_URL
        self.model = model or Config.DEFAULT_MODEL
        self.db_path = db_path
        self.rate_limiter = RateLimiter()
        
        # 设置openai配置（适用于0.8.0版本）
        openai.api_key = self.api_key
        openai.api_base = self.api_base_url
        
        self.init_analysis_table()
    
    def _create_failed_response(self, reason: str, content_quality: str = "title_only", 
                               full_content: str = "") -> Dict:
        """创建标准的分析失败响应"""
        return {
            'industries': ["分析失败"],
            'analysis_summary': reason,
            'confidence_score': 0.0,
            'content_quality': content_quality,
            'full_content': full_content,
            'analysis_status': 'failed'
        }
    
    def _parse_api_response(self, ai_response: str) -> Optional[Dict]:
        """解析AI API响应的JSON内容"""
        try:
            # 尝试解析JSON
            # 有时AI会在JSON前后添加说明文字，需要提取JSON部分
            start_idx = ai_response.find('{')
            
            if start_idx == -1:
                logger.error("AI返回结果中未找到JSON开始标记")
                return None
            
            # 使用括号计数来找到完整的JSON对象
            brace_count = 0
            end_idx = start_idx
            
            for i in range(start_idx, len(ai_response)):
                if ai_response[i] == '{':
                    brace_count += 1
                elif ai_response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if brace_count != 0:
                logger.error("AI返回结果中JSON格式不完整，括号不匹配")
                return None
            
            json_str = ai_response[start_idx:end_idx]
            logger.debug(f"提取的JSON字符串: {json_str[:200]}...")
            
            result = json.loads(json_str)
            
            # 验证必要字段
            required_fields = ['industries', 'analysis_summary', 'confidence_score']
            for field in required_fields:
                if field not in result:
                    logger.warning(f"AI返回结果缺少必要字段: {field}")
                    return None
            
            # 数据类型验证和清理
            if not isinstance(result['industries'], list):
                result['industries'] = [str(result['industries'])]
            
            if not isinstance(result['confidence_score'], (int, float)):
                try:
                    result['confidence_score'] = float(result['confidence_score'])
                except (ValueError, TypeError):
                    result['confidence_score'] = 0.5
            
            # 确保置信度在合理范围内
            result['confidence_score'] = max(0.0, min(1.0, result['confidence_score']))
            
            return result
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {str(e)}")
            logger.error(f"原始AI响应: {ai_response[:500]}...")
            return None
        except Exception as e:
            logger.error(f"解析AI返回结果时发生异常: {str(e)}")
            return None
    
    def _build_analysis_prompt(self, title: str, content: str, event_type: str, 
                              source_url: str = "", has_full_content: bool = False) -> str:
        """构建分析prompt模板"""
        base_analysis_request = """
请从以下几个方面进行分析：
1. 相关行业：列出可能受到影响的主要行业（最多5个）
2. 影响程度：评估对股市的整体影响程度（正面/负面/中性）
3. 分析摘要：{summary_instruction}
4. 置信度：对分析结果的置信度评分（0-1之间{confidence_note}）

请以JSON格式返回结果：
{{
    "industries": ["行业1", "行业2", ...],
    "impact_type": "正面/负面/中性",
    "analysis_summary": "分析摘要",
    "confidence_score": {default_confidence}
}}
"""
        
        if has_full_content:
            truncated_content = content[:Config.MAX_CONTENT_LENGTH]
            truncation_note = '...(内容过长已截断)' if len(content) > Config.MAX_CONTENT_LENGTH else ''
            
            return f"""
请分析以下政策对中国股市的影响：

标题：{title}
事件类型：{event_type if event_type else '未知'}

完整内容：
{truncated_content}{truncation_note}

{base_analysis_request.format(
    summary_instruction="基于完整政策内容，详细说明政策的主要影响点和逻辑",
    confidence_note="",
    default_confidence="0.8"
)}
"""
        else:
            return f"""
请分析以下政策对中国股市的影响：

标题：{title}
内容：{content if content else '无详细内容'}
事件类型：{event_type if event_type else '未知'}
原文链接：{source_url if source_url else '无'}

注意：由于缺乏详细政策内容，请基于标题进行初步分析，并在置信度评分中体现这一限制。

{base_analysis_request.format(
    summary_instruction="简要说明政策的主要影响点和逻辑",
    confidence_note="，由于缺乏详细内容应适当降低",
    default_confidence="0.5"
)}
"""
    
    async def check_api_health(self):
        """检查API健康状态"""
        try:
            # 使用旧版本openai API进行健康检查
            response = openai.Completion.create(
                model=self.model,
                prompt="test",
                max_tokens=10,
                temperature=0.1
            )
            
            if response and response.get('choices'):
                logger.info("API健康检查通过")
                return True
            else:
                logger.warning("API健康检查失败：响应格式异常")
                return False
                
        except Exception as e:
            logger.error(f"API健康检查异常: {e}")
            return False
    
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
    
    def init_analysis_table(self):
        """初始化分析结果表"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 创建政策分析结果表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS policy_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_id INTEGER NOT NULL,
                    industries TEXT,  -- JSON格式存储相关行业
                    analysis_summary TEXT,  -- 分析摘要
                    confidence_score REAL,  -- 置信度分数
                    content_quality TEXT DEFAULT 'title_only',  -- 分析时使用的内容质量: full/partial/title_only
                    full_content TEXT,  -- 存储政策原文完整内容
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (policy_id) REFERENCES policy_events (id)
                )
            ''')
            
            # 检查并添加新字段（兼容旧数据库）
            cursor.execute("PRAGMA table_info(policy_analysis)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'content_quality' not in columns:
                cursor.execute('ALTER TABLE policy_analysis ADD COLUMN content_quality TEXT DEFAULT "title_only"')
                logger.info("已添加content_quality字段到policy_analysis表")
                
            if 'full_content' not in columns:
                cursor.execute('ALTER TABLE policy_analysis ADD COLUMN full_content TEXT')
                logger.info("已添加full_content字段到policy_analysis表")        
            
            conn.commit()
        logger.info("AI分析结果表初始化完成")
    
    @retry_with_backoff(max_retries=3, base_delay=2, max_delay=30)
    def call_ai_api(self, prompt: str) -> Optional[Dict]:
        """调用硅基流动API（带重试机制）"""
        # 应用速率限制
        self.rate_limiter._check_and_wait_sync()
        
        try:
            # 使用旧版本openai API调用
            full_prompt = "你是一个专业的金融政策分析师，擅长分析政策新闻对股票市场的影响。请根据政策内容分析相关的行业、板块和个股。\n\n" + prompt
            response = openai.Completion.create(
                model=self.model,
                prompt=full_prompt,
                temperature=0.3,
                max_tokens=2000
            )
            
            return response
            
        except Exception as e:
            logger.error(f"API调用失败: {str(e)}")
            raise Exception(str(e))
    
    def fetch_policy_content(self, source_url: str) -> str:
        """从政策原文链接抓取完整内容"""
        if not source_url or not source_url.strip():
            return ""
            
        try:
            logger.info(f"正在抓取政策原文: {source_url}")
            
            # 使用配置的请求头
            response = requests.get(source_url, headers=Config.DEFAULT_HEADERS, timeout=Config.REQUEST_TIMEOUT)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.warning(f"HTTP状态码异常: {response.status_code}")
                return ""
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 使用配置的内容选择器
            content_selectors = Config.CONTENT_SELECTORS
            
            content_text = ""
            for selector in content_selectors:
                try:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        content_text = content_elem.get_text(separator='\n', strip=True)
                        if len(content_text) > Config.MIN_CONTENT_LENGTH:  # 确保抓取到足够的内容
                            logger.info(f"成功抓取内容，长度: {len(content_text)}字符")
                            return content_text
                except Exception as e:
                    continue
            
            # 如果没有找到特定容器，尝试从body提取
            body = soup.find('body')
            if body:
                content_text = body.get_text(separator='\n', strip=True)
                # 过滤掉导航、菜单等无关内容
                lines = content_text.split('\n')
                filtered_lines = []
                for line in lines:
                    line = line.strip()
                    if len(line) > 10 and not any(keyword in line for keyword in Config.FILTER_KEYWORDS):
                        filtered_lines.append(line)
                
                content_text = '\n'.join(filtered_lines)
                
            if len(content_text) > Config.MIN_CONTENT_LENGTH:
                logger.info(f"从body提取内容，长度: {len(content_text)}字符")
                return content_text
            else:
                logger.warning(f"抓取的内容过短: {len(content_text)}字符")
                return ""
                
        except requests.exceptions.Timeout:
            logger.error(f"请求超时: {source_url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {source_url}, 错误: {str(e)}")
        except Exception as e:
            logger.error(f"抓取政策内容失败 {source_url}: {str(e)}")
        
        return ""
    
    def analyze_policy(self, title: str, content: str = "", event_type: str = "", source_url: str = "") -> Optional[Dict]:
        """分析单个政策的相关行业、板块、个股（兼容旧接口）"""
        return self.analyze_policy_with_full_content(
            policy_id=0, title=title, source_url=source_url, content=content, event_type=event_type
        )
    
    def analyze_policy_with_full_content(self, policy_id: int, title: str, 
                                        source_url: str = "", content: str = "", 
                                        event_type: str = "") -> Optional[Dict]:
        """
        使用AI分析政策对股市的影响（完整版本）
        
        Args:
            policy_id: 政策ID
            title: 政策标题
            source_url: 政策原文链接
            content: 政策内容（可选）
            event_type: 事件类型
            
        Returns:
            分析结果字典
        """
        try:
            # 尝试从原文链接获取完整内容
            full_content = content
            content_quality = "title_only"
            
            if source_url and not content:
                logger.info(f"尝试从原文链接获取政策内容: {source_url}")
                full_content = self.fetch_policy_content(source_url)
                if full_content:
                    if len(full_content) > Config.FULL_CONTENT_THRESHOLD:
                        content_quality = "full"
                    elif len(full_content) > Config.PARTIAL_CONTENT_THRESHOLD:
                        content_quality = "partial"
                    else:
                        content_quality = "title_only"
            elif content:
                # 判断现有内容的质量
                if len(content) > Config.FULL_CONTENT_THRESHOLD:
                    content_quality = "full"
                elif len(content) > Config.PARTIAL_CONTENT_THRESHOLD:
                    content_quality = "partial"
                else:
                    content_quality = "title_only"
            
            # 构建分析prompt
            has_full_content = full_content and len(full_content) > 50
            prompt = self._build_analysis_prompt(
                title=title,
                content=full_content if has_full_content else content,
                event_type=event_type,
                source_url=source_url,
                has_full_content=has_full_content
            )
        
            # 调用AI API
            api_result = self.call_ai_api(prompt)
            
            if not api_result:
                # API调用失败，返回分析失败标识
                return self._create_failed_response(
                    reason="API调用失败，无法进行分析",
                    content_quality=content_quality,
                    full_content=full_content or ''
                )
                
            # 提取AI回复内容
            ai_response = api_result['choices'][0]['text']
            
            # 解析AI返回的结果
            result = self._parse_api_response(ai_response)
            
            if result:
                # 处理分析结果中的行业信息
                industries = result.get('industries', [])
                
                # 如果分析结果中没有行业或行业为空，标记为"分析后无相关行业"
                if not industries or (isinstance(industries, list) and len(industries) == 0):
                    industries = ["分析后无相关行业"]
                
                # 添加内容质量信息和完整内容
                result['industries'] = industries
                result['content_quality'] = content_quality
                result['full_content'] = full_content or ''
                result['analysis_status'] = 'success'
                logger.info(f"政策分析完成: {title[:50]}..., 内容质量: {content_quality}, 相关行业: {industries}")
                return result
            else:
                 # 解析失败，返回分析失败标识
                 return self._create_failed_response(
                     reason="AI返回结果解析失败",
                     content_quality=content_quality,
                     full_content=full_content or ''
                 )
                
        except Exception as e:
            logger.error(f"处理AI回复时发生异常: {str(e)}")
            # 返回分析失败标识
            return self._create_failed_response(
                reason=f"分析过程异常: {str(e)}",
                content_quality=content_quality,
                full_content=full_content or ''
            )
    
    def get_stored_policy_content(self, policy_id: int) -> Optional[str]:
        """从数据库获取已存储的政策原文内容"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT full_content FROM policy_analysis WHERE policy_id = ?', (policy_id,))
                result = cursor.fetchone()
                
                if result and result[0]:
                    logger.info(f"从数据库获取到政策ID {policy_id} 的原文内容，长度: {len(result[0])}字符")
                    return result[0]
                else:
                    logger.info(f"政策ID {policy_id} 没有存储的原文内容")
                return None
                
        except Exception as e:
            logger.error(f"获取存储的政策内容失败: {str(e)}")
            return None
    
    def reanalyze_policy_from_stored_content(self, policy_id: int, title: str, event_type: str = "") -> Optional[Dict]:
        """使用已存储的政策原文内容重新分析政策"""
        try:
            # 从数据库获取已存储的原文内容
            stored_content = self.get_stored_policy_content(policy_id)
            
            if not stored_content:
                logger.warning(f"政策ID {policy_id} 没有存储的原文内容，无法进行重新分析")
                return None
            
            logger.info(f"开始使用存储内容重新分析政策: {title[:50]}...")
            
            # 使用存储的内容进行分析
            return self.analyze_policy_with_full_content(
                policy_id=policy_id,
                title=title,
                source_url="",  # 不需要重新抓取
                content=stored_content,
                event_type=event_type
            )
            
        except Exception as e:
            logger.error(f"重新分析政策失败: {str(e)}")
            return None
    
    def batch_reanalyze_policies_with_stored_content(self, limit: int = 10) -> int:
        """批量重新分析有存储内容的政策"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 获取有存储内容的政策
                cursor.execute('''
                    SELECT pa.policy_id, pe.title, pe.event_type
                    FROM policy_analysis pa
                    JOIN policy_events pe ON pa.policy_id = pe.id
                    WHERE pa.full_content IS NOT NULL AND pa.full_content != ''
                    ORDER BY pe.date DESC
                    LIMIT ?
                ''', (limit,))
                
                policies = cursor.fetchall()
            
            if not policies:
                logger.info("没有找到有存储内容的政策")
                return 0
            
            success_count = 0
            
            for policy_id, title, event_type in policies:
                logger.info(f"重新分析政策: {title[:50]}...")
                
                analysis_result = self.reanalyze_policy_from_stored_content(
                    policy_id=policy_id,
                    title=title,
                    event_type=event_type or ""
                )
                
                if analysis_result:
                    # 保存重新分析的结果
                    self.save_analysis_result(policy_id, analysis_result)
                    success_count += 1
                    logger.info(f"政策重新分析完成: {title[:50]}...")
                else:
                    logger.warning(f"政策重新分析失败: {title[:50]}...")
                
                # 减少延迟时间
                time.sleep(0.5)
            
            logger.info(f"批量重新分析完成，成功处理 {success_count}/{len(policies)} 条政策")
            return success_count
            
        except Exception as e:
            logger.error(f"批量重新分析政策时发生错误: {str(e)}")
            return 0
    
    def save_analysis_result(self, policy_id: int, analysis_result: Dict) -> bool:
        """保存分析结果到数据库"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 检查是否已存在分析结果
                cursor.execute('SELECT id FROM policy_analysis WHERE policy_id = ?', (policy_id,))
                existing = cursor.fetchone()
                
                if existing:
                    # 更新现有记录
                    cursor.execute('''
                        UPDATE policy_analysis 
                        SET industries = ?, analysis_summary = ?, confidence_score = ?, content_quality = ?, full_content = ?,
                            created_at = CURRENT_TIMESTAMP
                        WHERE policy_id = ?
                    ''', (
                        json.dumps(analysis_result['industries'], ensure_ascii=False),
                        analysis_result['analysis_summary'],
                        analysis_result['confidence_score'],
                        analysis_result.get('content_quality', 'title_only'),
                        analysis_result.get('full_content', ''),
                        policy_id
                    ))
                    logger.info(f"更新政策ID {policy_id} 的分析结果")
                else:
                    # 插入新记录
                    cursor.execute('''
                        INSERT INTO policy_analysis 
                        (policy_id, industries, analysis_summary, confidence_score, content_quality, full_content)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        policy_id,
                        json.dumps(analysis_result['industries'], ensure_ascii=False),
                        analysis_result['analysis_summary'],
                        analysis_result['confidence_score'],
                        analysis_result.get('content_quality', 'title_only'),
                        analysis_result.get('full_content', '')
                    ))
                    logger.info(f"保存政策ID {policy_id} 的分析结果")
                
                conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"保存分析结果失败: {str(e)}")
            return False
    
    def analyze_unprocessed_policies(self, limit: int = 10) -> int:
        """
        批量分析未处理的政策（同步版本，保持向后兼容）
        
        Args:
            limit: 每次处理的政策数量限制
            
        Returns:
            成功分析的政策数量
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 获取未分析的政策（包括source_url）
                cursor.execute('''
                    SELECT pe.id, pe.title, pe.content, pe.event_type, pe.source_url
                    FROM policy_events pe
                    LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
                    WHERE pa.policy_id IS NULL
                    ORDER BY pe.date DESC
                    LIMIT ?
                ''', (limit,))
                
                policies = cursor.fetchall()
            
            success_count = 0
            
            for policy in policies:
                policy_id, title, content, event_type, source_url = policy
                
                logger.info(f"开始分析政策: {title[:50]}...")
                
                # 使用完整版本的分析方法
                analysis_result = self.analyze_policy_with_full_content(
                    policy_id=policy_id,
                    title=title,
                    source_url=source_url or "",
                    content=content or "",
                    event_type=event_type or ""
                )
                
                if analysis_result:
                    # 保存分析结果
                    self.save_analysis_result(policy_id, analysis_result)
                    success_count += 1
                    logger.info(f"政策分析完成: {title[:50]}..., 内容质量: {analysis_result.get('content_quality', 'unknown')}")
                else:
                    logger.warning(f"政策分析失败: {title[:50]}...")
                
                # 批量处理间隔延迟
                time.sleep(Config.BATCH_DELAY)
            
            return success_count
            
        except Exception as e:
            logger.error(f"批量分析政策时发生错误: {str(e)}")
            return 0
    
    def analyze_failed_and_empty_policies(self, limit: int = 10) -> int:
        """
        批量重新分析失败的政策和无相关行业的政策
        
        Args:
            limit: 每次处理的政策数量限制
            
        Returns:
            成功分析的政策数量
        """
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 获取需要重新分析的政策：分析失败或无相关行业的
                cursor.execute('''
                    SELECT pe.id, pe.title, pe.content, pe.event_type, pe.source_url, pa.industries
                    FROM policy_events pe
                    JOIN policy_analysis pa ON pe.id = pa.policy_id
                    WHERE pa.industries LIKE '%分析失败%' OR pa.industries LIKE '%分析后无相关行业%'
                    ORDER BY pe.date DESC
                    LIMIT ?
                ''', (limit,))
                
                policies = cursor.fetchall()
            
            if not policies:
                logger.info("没有需要重新分析的政策")
                return 0
            
            success_count = 0
            
            for policy in policies:
                policy_id, title, content, event_type, source_url, old_industries = policy
                
                logger.info(f"重新分析政策: {title[:50]}... (原分析结果: {old_industries})")
                
                # 使用完整版本的分析方法
                analysis_result = self.analyze_policy_with_full_content(
                    policy_id=policy_id,
                    title=title,
                    source_url=source_url or "",
                    content=content or "",
                    event_type=event_type or ""
                )
                
                if analysis_result:
                    # 检查新的分析结果是否有改善
                    new_industries = analysis_result.get('industries', [])
                    if (new_industries and 
                        "分析失败" not in str(new_industries) and 
                        "分析后无相关行业" not in str(new_industries)):
                        # 保存改善的分析结果
                        self.save_analysis_result(policy_id, analysis_result)
                        success_count += 1
                        logger.info(f"政策重新分析成功: {title[:50]}..., 新行业: {new_industries}")
                    else:
                        # 保存结果，即使仍然是失败或无相关行业
                        self.save_analysis_result(policy_id, analysis_result)
                        logger.info(f"政策重新分析完成但结果未改善: {title[:50]}..., 结果: {new_industries}")
                else:
                    logger.warning(f"政策重新分析失败: {title[:50]}...")
                
                # 减少延迟时间
                time.sleep(0.8)
            
            logger.info(f"重新分析完成，处理了 {len(policies)} 条政策，其中 {success_count} 条有改善")
            return success_count
            
        except Exception as e:
            logger.error(f"批量重新分析政策时发生错误: {str(e)}")
            return 0
    
    async def analyze_unprocessed_policies_async(self, limit: int = 20, max_concurrent: int = 5) -> int:
        """
        异步批量分析未处理的政策（优化版本）
        
        Args:
            limit: 每次处理的政策数量限制
            max_concurrent: 最大并发数
            
        Returns:
            成功分析的政策数量
        """
        # 获取未分析的政策
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT pe.id, pe.title, pe.content, pe.event_type, pe.source_url
                    FROM policy_events pe
                    LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
                    WHERE pa.policy_id IS NULL
                    ORDER BY pe.date DESC
                    LIMIT ?
                ''', (limit,))
                
                policies = cursor.fetchall()
            
            if not policies:
                logger.info("没有需要分析的政策")
                return 0
            
            logger.info(f"开始异步分析 {len(policies)} 条政策...")
            
            # 创建信号量限制并发数
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def analyze_single_policy_async(policy_data):
                async with semaphore:
                    policy_id, title, content, event_type, source_url = policy_data
                    
                    try:
                        # 异步获取完整内容
                        full_content = content or ""
                        content_quality = "title_only"
                        
                        if source_url and not content:
                            logger.info(f"尝试获取政策完整内容: {title[:50]}...")
                            full_content = await self.fetch_policy_content_async(source_url)
                            if full_content:
                                if len(full_content) > 500:
                                    content_quality = "full"
                                elif len(full_content) > 100:
                                    content_quality = "partial"
                        elif content:
                            if len(content) > 500:
                                content_quality = "full"
                            elif len(content) > 100:
                                content_quality = "partial"
                        
                        # 构建分析prompt
                        if full_content and len(full_content) > 50:
                            prompt = f"""
请分析以下政策对中国股市的影响：

标题：{title}
事件类型：{event_type if event_type else '未知'}

完整内容：
{full_content[:3000]}{'...(内容过长已截断)' if len(full_content) > 3000 else ''}

请从以下几个方面进行分析：
1. 相关行业：列出可能受到影响的主要行业（最多5个）
2. 影响程度：评估对股市的整体影响程度（正面/负面/中性）
3. 分析摘要：基于完整政策内容，详细说明政策的主要影响点和逻辑
4. 置信度：对分析结果的置信度评分（0-1之间）

请以JSON格式返回结果：
{{
    "industries": ["行业1", "行业2", ...],
    "impact_type": "正面/负面/中性",
    "analysis_summary": "分析摘要",
    "confidence_score": 0.8
}}
"""
                        else:
                            prompt = f"""
请分析以下政策对中国股市的影响：

标题：{title}
内容：{content if content else '无详细内容'}
事件类型：{event_type if event_type else '未知'}
原文链接：{source_url if source_url else '无'}

注意：由于缺乏详细政策内容，请基于标题进行初步分析，并在置信度评分中体现这一限制。

请从以下几个方面进行分析：
1. 相关行业：列出可能受到影响的主要行业（最多5个）
2. 影响程度：评估对股市的整体影响程度（正面/负面/中性）
3. 分析摘要：简要说明政策的主要影响点和逻辑
4. 置信度：对分析结果的置信度评分（0-1之间，由于缺乏详细内容应适当降低）

请以JSON格式返回结果：
{{
    "industries": ["行业1", "行业2", ...],
    "impact_type": "正面/负面/中性",
    "analysis_summary": "分析摘要",
    "confidence_score": 0.5
}}
"""
                        
                        # 异步调用AI API
                        api_result = await self.call_ai_api_async(prompt)
                        
                        if not api_result:
                            return None
                        
                        # 解析AI回复
                        ai_response = api_result['choices'][0]['text']
                        
                        try:
                            # 提取JSON部分
                            start_idx = ai_response.find('{')
                            end_idx = ai_response.rfind('}') + 1
                            
                            if start_idx != -1 and end_idx != -1:
                                json_str = ai_response[start_idx:end_idx]
                                result = json.loads(json_str)
                            else:
                                result = json.loads(ai_response)
                            
                            # 确保返回结果包含所需字段
                            analysis_result = {
                                'industries': result.get('industries', []),
                                'impact_type': result.get('impact_type', '中性'),
                                'analysis_summary': result.get('analysis_summary', ''),
                                'confidence_score': float(result.get('confidence_score', 0.5)),
                                'content_quality': content_quality
                            }
                            
                            logger.info(f"政策分析完成: {title[:50]}..., 内容质量: {content_quality}")
                            return (policy_id, analysis_result)
                            
                        except (json.JSONDecodeError, KeyError, ValueError) as e:
                            logger.error(f"解析AI回复失败 {title[:50]}...: {str(e)}")
                            return None
                            
                    except Exception as e:
                        logger.error(f"分析政策失败 {title[:50]}...: {str(e)}")
                        return None
            
            # 创建分析任务
            tasks = [analyze_single_policy_async(policy) for policy in policies]
            
            # 并发执行分析任务
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 保存成功的分析结果
            success_count = 0
            
            for result in results:
                if isinstance(result, tuple) and result is not None:
                    policy_id, analysis_result = result
                    if self.save_analysis_result(policy_id, analysis_result):
                        success_count += 1
            
            logger.info(f"异步批次分析完成，成功分析并保存 {success_count} 条政策")
            return success_count
            
        except Exception as e:
            logger.error(f"异步批量分析政策时发生错误: {str(e)}")
            return 0
    
    async def fetch_policy_content_async(self, source_url: str) -> Optional[str]:
        """
        异步获取政策完整内容
        
        Args:
            source_url: 政策原文链接
            
        Returns:
            政策完整内容或None
        """
        if not source_url:
            return None
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(source_url, ssl=False) as response:
                    if response.status == 200:
                        content = await response.text()
                        # 简单的内容提取（实际应用中可能需要更复杂的解析）
                        if len(content) > 100:
                            return content[:3000]  # 限制内容长度
                    return None
        except Exception as e:
            logger.warning(f"异步获取政策内容失败 {source_url}: {str(e)}")
            return None
    
    async def call_ai_api_async(self, prompt: str, max_retries: int = 3) -> Optional[Dict]:
        """
        异步调用AI API（带重试机制）
        
        Args:
            prompt: 分析提示词
            max_retries: 最大重试次数
            
        Returns:
            API响应结果或None
        """
        # 应用速率限制
        await self.rate_limiter.wait_if_needed()
        
        url = "https://api.siliconflow.cn/v1/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 合并系统提示和用户提示
        full_prompt = "你是一个专业的金融政策分析师，擅长分析政策新闻对股票市场的影响。请根据政策内容分析相关的行业、板块和个股。\n\n" + prompt
        
        data = {
            "model": self.model,
            "prompt": full_prompt,
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        for attempt in range(max_retries):
            try:
                # 增加超时配置
                timeout = aiohttp.ClientTimeout(
                    total=120,  # 总超时时间
                    connect=10,  # 连接超时
                    sock_read=90  # 读取超时
                )
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            return result
                        else:
                            error_text = await response.text()
                            error_msg = f"HTTP {response.status}: {error_text[:200]}"
                            logger.error(f"异步API调用失败，状态码: {response.status}, 响应: {error_text[:200]}")
                            
                            if attempt == max_retries - 1:
                                return None
                            
                            # 对于5xx错误进行重试
                            if 500 <= response.status < 600:
                                delay = Config.BASE_DELAY ** attempt + random.uniform(0, 1)
                                logger.warning(f"服务器错误，{delay:.2f}秒后重试 (第{attempt+1}次)")
                                await asyncio.sleep(delay)
                                continue
                            else:
                                return None
                                
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"异步API调用失败，已重试{max_retries}次: {str(e)}")
                    return None
                
                # 指数退避
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                logger.warning(f"异步API调用异常，{delay:.2f}秒后重试 (第{attempt+1}次): {str(e)}")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"异步API调用发生未预期异常: {str(e)}")
                return None
                
        return None
    
    def get_analysis_result(self, policy_id: int) -> Optional[Dict]:
        """获取指定政策的分析结果"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT industries, analysis_summary, confidence_score, content_quality, created_at
                    FROM policy_analysis
                    WHERE policy_id = ?
                ''', (policy_id,))
                
                result = cursor.fetchone()
                
                if result:
                    return {
                        'industries': json.loads(result[0]) if result[0] else [],
                        'analysis_summary': result[1],
                        'confidence_score': result[2],
                        'content_quality': result[3] if result[3] else 'title_only',
                        'created_at': result[4]
                    }
                else:
                    return None
                    
        except Exception as e:
            logger.error(f"获取分析结果失败: {str(e)}")
            return None
    
    def get_policies_by_stock(self, stock_code: str) -> List[Dict]:
        """根据股票代码查找相关政策"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT pe.id, pe.title, pe.date, pe.event_type, pa.industries, pa.analysis_summary
                    FROM policy_events pe
                    JOIN policy_analysis pa ON pe.id = pa.policy_id
                    WHERE pa.industries LIKE ?
                    ORDER BY pe.date DESC
                ''', (f'%{stock_code}%',))
                
                results = cursor.fetchall()
                policies = []
                
                for result in results:
                    try:
                        industries = json.loads(result[4]) if result[4] else []
                        # 检查是否包含相关行业
                        if any(stock_code in str(industry) for industry in industries):
                            policies.append({
                                'id': result[0],
                                'title': result[1],
                                'date': result[2],
                                'event_type': result[3],
                                'industries': industries,
                                'analysis_summary': result[5]
                            })
                    except json.JSONDecodeError:
                        continue
                
                return policies
                
        except Exception as e:
            logger.error(f"查询股票相关政策失败: {str(e)}")
            return []
    
    def get_analysis_statistics(self) -> Dict:
        """获取分析状态统计信息"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 统计总政策数
                cursor.execute('SELECT COUNT(*) FROM policy_events')
                total_policies = cursor.fetchone()[0]
                
                # 统计已分析政策数
                cursor.execute('SELECT COUNT(*) FROM policy_analysis')
                analyzed_policies = cursor.fetchone()[0]
                
                # 统计分析失败的政策数
                cursor.execute("SELECT COUNT(*) FROM policy_analysis WHERE industries LIKE '%分析失败%'")
                failed_analysis = cursor.fetchone()[0]
                
                # 统计无相关行业的政策数
                cursor.execute("SELECT COUNT(*) FROM policy_analysis WHERE industries LIKE '%分析后无相关行业%'")
                no_industry_analysis = cursor.fetchone()[0]
                
                # 统计成功分析且有相关行业的政策数
                cursor.execute("""
                    SELECT COUNT(*) FROM policy_analysis 
                    WHERE industries NOT LIKE '%分析失败%' 
                    AND industries NOT LIKE '%分析后无相关行业%'
                    AND industries != '[]'
                """)
                successful_analysis = cursor.fetchone()[0]
                
                # 统计未分析的政策数
                unanalyzed_policies = total_policies - analyzed_policies
                
                # 统计需要重新分析的政策数
                need_reanalysis = failed_analysis + no_industry_analysis
                
                return {
                    'total_policies': total_policies,
                    'analyzed_policies': analyzed_policies,
                    'unanalyzed_policies': unanalyzed_policies,
                    'successful_analysis': successful_analysis,
                    'failed_analysis': failed_analysis,
                    'no_industry_analysis': no_industry_analysis,
                    'need_reanalysis': need_reanalysis,
                    'analysis_rate': round(analyzed_policies / total_policies * 100, 2) if total_policies > 0 else 0,
                    'success_rate': round(successful_analysis / analyzed_policies * 100, 2) if analyzed_policies > 0 else 0
                }
                
        except Exception as e:
            logger.error(f"获取分析统计信息失败: {str(e)}")
            return {}
    
    def print_analysis_statistics(self):
        """打印分析状态统计信息"""
        stats = self.get_analysis_statistics()
        if stats:
            print("\n=== 政策分析统计信息 ===")
            print(f"总政策数: {stats['total_policies']}")
            print(f"已分析政策数: {stats['analyzed_policies']}")
            print(f"未分析政策数: {stats['unanalyzed_policies']}")
            print(f"成功分析且有相关行业: {stats['successful_analysis']}")
            print(f"分析失败: {stats['failed_analysis']}")
            print(f"分析后无相关行业: {stats['no_industry_analysis']}")
            print(f"需要重新分析: {stats['need_reanalysis']}")
            print(f"分析覆盖率: {stats['analysis_rate']}%")
            print(f"分析成功率: {stats['success_rate']}%")
            print("========================\n")
        else:
            print("无法获取统计信息")


if __name__ == "__main__":
    # 测试代码
    from ..utils.config import init_config, Config
    
    if not init_config():
        print("错误：配置初始化失败")
        print("请设置 SILICONFLOW_API_KEY 环境变量")
        exit(1)
    
    try:
        API_KEY = Config.get_api_key()
        analyzer = AIPolicyAnalyzer(API_KEY)
    except ValueError as e:
        print(f"错误：{e}")
        exit(1)
    
    # 测试分析功能
    test_title = "国务院发布新能源汽车产业发展规划"
    test_content = "为推动新能源汽车产业高质量发展，国务院发布了新能源汽车产业发展规划，明确了未来发展目标和重点任务。"
    
    print("正在测试AI分析功能...")
    result = analyzer.analyze_policy(test_title, test_content, "政策发布")
    
    if result:
        print("分析结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("分析失败")
    
    # 分析未处理的政策
    print("\n正在分析未处理的政策...")
    processed = analyzer.analyze_unprocessed_policies(limit=5)
    print(f"处理了 {processed} 条政策")