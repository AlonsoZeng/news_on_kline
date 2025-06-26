import sqlite3
import json
import logging
import time
import requests
import asyncio
import aiohttp
from typing import Dict, List, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import time
import re

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AIPolicyAnalyzer:
    """AI政策分析器，使用硅基流动API分析政策新闻的相关行业、板块、个股"""
    
    def __init__(self, api_key: str, db_path: str = 'events.db'):
        self.api_key = api_key
        self.api_base_url = "https://api.siliconflow.cn/v1"
        self.model = "Qwen/Qwen3-8B"
        self.db_path = db_path
        self.init_analysis_table()
    
    def init_analysis_table(self):
        """初始化分析结果表"""
        conn = sqlite3.connect(self.db_path)
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (policy_id) REFERENCES policy_events (id)
            )
        ''')
        
        # 检查并添加content_quality字段（兼容旧数据库）
        cursor.execute("PRAGMA table_info(policy_analysis)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'content_quality' not in columns:
            cursor.execute('ALTER TABLE policy_analysis ADD COLUMN content_quality TEXT DEFAULT "title_only"')
            logger.info("已添加content_quality字段到policy_analysis表")        
        
        conn.commit()
        conn.close()
        logger.info("AI分析结果表初始化完成")
    
    def call_ai_api(self, prompt: str) -> Optional[Dict]:
        """调用硅基流动API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的金融政策分析师，擅长分析政策新闻对股票市场的影响。请根据政策内容分析相关的行业、板块和个股。"
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(
                f"{self.api_base_url}/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                return result
            else:
                logger.error(f"API调用失败，状态码: {response.status_code}, 响应: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"API调用异常: {str(e)}")
            return None
    
    def fetch_policy_content(self, source_url: str) -> str:
        """从政策原文链接抓取完整内容"""
        if not source_url or not source_url.strip():
            return ""
            
        try:
            logger.info(f"正在抓取政策原文: {source_url}")
            
            # 设置请求头，模拟浏览器访问
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            response = requests.get(source_url, headers=headers, timeout=30)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                logger.warning(f"HTTP状态码异常: {response.status_code}")
                return ""
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除脚本和样式标签
            for script in soup(["script", "style"]):
                script.decompose()
            
            # 尝试多种内容选择器，适配不同政府网站
            content_selectors = [
                '.content', '.article-content', '.policy-content', '.main-content',
                '#content', '#article-content', '#policy-content', '#main-content',
                '.text', '.article-text', '.policy-text',
                'article', '.article', '.post-content',
                '.TRS_Editor', '.Custom_UnionStyle',  # 政府网站常用的编辑器类名
                '[class*="content"]', '[class*="article"]', '[class*="text"]'
            ]
            
            content_text = ""
            for selector in content_selectors:
                try:
                    content_elem = soup.select_one(selector)
                    if content_elem:
                        content_text = content_elem.get_text(separator='\n', strip=True)
                        if len(content_text) > 200:  # 确保抓取到足够的内容
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
                    if len(line) > 10 and not any(keyword in line for keyword in 
                        ['导航', '菜单', '首页', '返回', '上一页', '下一页', '版权', '联系我们', 'Copyright']):
                        filtered_lines.append(line)
                
                content_text = '\n'.join(filtered_lines)
                
            if len(content_text) > 100:
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
                    if len(full_content) > 500:
                        content_quality = "full"
                    elif len(full_content) > 100:
                        content_quality = "partial"
                    else:
                        content_quality = "title_only"
            elif content:
                # 判断现有内容的质量
                if len(content) > 500:
                    content_quality = "full"
                elif len(content) > 100:
                    content_quality = "partial"
                else:
                    content_quality = "title_only"
            
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
        
            # 调用AI API
            api_result = self.call_ai_api(prompt)
            
            if not api_result:
                return None
                
            # 提取AI回复内容
            ai_response = api_result['choices'][0]['message']['content']
            
            # 解析AI返回的结果
            try:
                # 尝试解析JSON
                # 有时AI会在JSON前后添加说明文字，需要提取JSON部分
                start_idx = ai_response.find('{')
                end_idx = ai_response.rfind('}') + 1
                
                if start_idx != -1 and end_idx != -1:
                    json_str = ai_response[start_idx:end_idx]
                    result = json.loads(json_str)
                else:
                    result = json.loads(ai_response)
                
                # 确保返回结果包含所需字段
                if all(key in result for key in ['industries', 'analysis_summary', 'confidence_score']):
                    # 添加内容质量信息
                    result['content_quality'] = content_quality
                    logger.info(f"政策分析完成: {title[:50]}..., 内容质量: {content_quality}")
                    return result
                else:
                    logger.error(f"AI返回结果缺少必要字段: {result}")
                    return None
            except json.JSONDecodeError as e:
                logger.error(f"解析AI返回结果失败: {e}, 原始响应: {ai_response}")
                return None
                
        except Exception as e:
            logger.error(f"处理AI回复时发生异常: {str(e)}")
            return None
    
    def save_analysis_result(self, policy_id: int, analysis_result: Dict) -> bool:
        """保存分析结果到数据库"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 检查是否已存在分析结果
            cursor.execute('SELECT id FROM policy_analysis WHERE policy_id = ?', (policy_id,))
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute('''
                    UPDATE policy_analysis 
                    SET industries = ?, analysis_summary = ?, confidence_score = ?, content_quality = ?,
                        created_at = CURRENT_TIMESTAMP
                    WHERE policy_id = ?
                ''', (
                    json.dumps(analysis_result['industries'], ensure_ascii=False),
                    analysis_result['analysis_summary'],
                    analysis_result['confidence_score'],
                    analysis_result.get('content_quality', 'title_only'),
                    policy_id
                ))
                logger.info(f"更新政策ID {policy_id} 的分析结果")
            else:
                # 插入新记录
                cursor.execute('''
                    INSERT INTO policy_analysis 
                    (policy_id, industries, analysis_summary, confidence_score, content_quality)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    policy_id,
                    json.dumps(analysis_result['industries'], ensure_ascii=False),
                    analysis_result['analysis_summary'],
                    analysis_result['confidence_score'],
                    analysis_result.get('content_quality', 'title_only')
                ))
                logger.info(f"保存政策ID {policy_id} 的分析结果")
            
            conn.commit()
            conn.close()
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
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
                
                # 减少延迟时间，从2秒优化到0.8秒
                time.sleep(0.8)
            
            return success_count
            
        except Exception as e:
            logger.error(f"批量分析政策时发生错误: {str(e)}")
            return 0
        finally:
            conn.close()
    
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
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
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
                        ai_response = api_result['choices'][0]['message']['content']
                        
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
        finally:
            conn.close()
    
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
            timeout = aiohttp.ClientTimeout(total=30)
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
    
    async def call_ai_api_async(self, prompt: str) -> Optional[Dict]:
        """
        异步调用AI API
        
        Args:
            prompt: 分析提示词
            
        Returns:
            API响应结果或None
        """
        url = "https://api.siliconflow.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": "deepseek-ai/DeepSeek-V2.5",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        logger.error(f"异步AI API调用失败，状态码: {response.status}")
                        return None
        except Exception as e:
            logger.error(f"异步AI API调用异常: {str(e)}")
            return None
    
    def get_analysis_result(self, policy_id: int) -> Optional[Dict]:
        """获取指定政策的分析结果"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
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
        finally:
            conn.close()
    
    def get_policies_by_stock(self, stock_code: str) -> List[Dict]:
        """根据股票代码查找相关政策"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
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
        finally:
            conn.close()


if __name__ == "__main__":
    # 测试代码
    from config import init_config, Config
    
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