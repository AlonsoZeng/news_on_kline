#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
异步批量分析政策数据脚本
采用异步并发处理优化，显著提高分析速度
用于为相关行业(pa.industries)为空的数据行补齐数据
"""

import os
import sys
import sqlite3
import logging
import asyncio
import aiohttp
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional, Tuple
from ai_policy_analyzer import AIPolicyAnalyzer

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_analysis_async.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class AsyncPolicyAnalyzer:
    """异步政策分析器"""
    
    def __init__(self, api_key: str, db_path: str = 'events.db', max_concurrent: int = 5):
        self.api_key = api_key
        self.db_path = db_path
        self.max_concurrent = max_concurrent
        self.session = None
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        # 创建线程池用于数据库操作
        self.thread_pool = ThreadPoolExecutor(max_workers=3)
        
        # 初始化分析表
        self._init_analysis_table()
    
    def _init_analysis_table(self):
        """初始化分析结果表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS policy_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id INTEGER UNIQUE NOT NULL,
                industries TEXT,
                analysis_summary TEXT,
                confidence_score REAL,
                content_quality TEXT DEFAULT 'unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (policy_id) REFERENCES policy_events (id)
            )
        ''')
        
        # 检查并添加content_quality字段（兼容旧数据库）
        try:
            cursor.execute('ALTER TABLE policy_analysis ADD COLUMN content_quality TEXT DEFAULT "unknown"')
        except sqlite3.OperationalError:
            pass  # 字段已存在
        
        conn.commit()
        conn.close()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
            connector=aiohttp.TCPConnector(limit=self.max_concurrent)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
        self.thread_pool.shutdown(wait=True)
    
    async def get_unanalyzed_policies(self, limit: int = 50) -> List[Tuple]:
        """异步获取未分析的政策列表"""
        loop = asyncio.get_event_loop()
        
        def _get_policies():
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
                return policies
            except Exception as e:
                logger.error(f"获取未分析政策失败: {str(e)}")
                return []
            finally:
                conn.close()
        
        return await loop.run_in_executor(self.thread_pool, _get_policies)
    
    async def fetch_policy_content(self, source_url: str) -> Optional[str]:
        """异步获取政策完整内容"""
        if not source_url or not self.session:
            return None
        
        try:
            async with self.session.get(source_url, ssl=False) as response:
                if response.status == 200:
                    content = await response.text()
                    # 简单的内容提取（实际应用中可能需要更复杂的解析）
                    if len(content) > 100:
                        return content[:3000]  # 限制内容长度
                return None
        except Exception as e:
            logger.warning(f"获取政策内容失败 {source_url}: {str(e)}")
            return None
    
    async def call_ai_api(self, prompt: str) -> Optional[Dict]:
        """异步调用AI API"""
        if not self.session:
            return None
        
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
            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    return result
                else:
                    logger.error(f"AI API调用失败，状态码: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"AI API调用异常: {str(e)}")
            return None
    
    async def analyze_single_policy(self, policy_data: Tuple) -> Optional[Dict]:
        """异步分析单个政策"""
        async with self.semaphore:  # 限制并发数
            policy_id, title, content, event_type, source_url = policy_data
            
            try:
                # 尝试获取完整内容
                full_content = content or ""
                content_quality = "title_only"
                
                if source_url and not content:
                    logger.info(f"尝试获取政策完整内容: {title[:50]}...")
                    fetched_content = await self.fetch_policy_content(source_url)
                    if fetched_content:
                        full_content = fetched_content
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
                
                # 调用AI API
                api_result = await self.call_ai_api(prompt)
                
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
                        'policy_id': policy_id,
                        'industries': result.get('industries', []),
                        'impact_type': result.get('impact_type', '中性'),
                        'analysis_summary': result.get('analysis_summary', ''),
                        'confidence_score': float(result.get('confidence_score', 0.5)),
                        'content_quality': content_quality
                    }
                    
                    logger.info(f"政策分析完成: {title[:50]}..., 内容质量: {content_quality}")
                    return analysis_result
                    
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.error(f"解析AI回复失败 {title[:50]}...: {str(e)}")
                    return None
                    
            except Exception as e:
                logger.error(f"分析政策失败 {title[:50]}...: {str(e)}")
                return None
    
    async def save_analysis_result(self, analysis_result: Dict) -> bool:
        """异步保存分析结果"""
        loop = asyncio.get_event_loop()
        
        def _save_result():
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                # 检查是否已存在
                cursor.execute('SELECT id FROM policy_analysis WHERE policy_id = ?', 
                             (analysis_result['policy_id'],))
                existing = cursor.fetchone()
                
                industries_json = json.dumps(analysis_result['industries'], ensure_ascii=False)
                
                if existing:
                    # 更新现有记录
                    cursor.execute('''
                        UPDATE policy_analysis 
                        SET industries = ?, analysis_summary = ?, confidence_score = ?, 
                            content_quality = ?, created_at = CURRENT_TIMESTAMP
                        WHERE policy_id = ?
                    ''', (
                        industries_json,
                        analysis_result['analysis_summary'],
                        analysis_result['confidence_score'],
                        analysis_result['content_quality'],
                        analysis_result['policy_id']
                    ))
                else:
                    # 插入新记录
                    cursor.execute('''
                        INSERT INTO policy_analysis 
                        (policy_id, industries, analysis_summary, confidence_score, content_quality)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        analysis_result['policy_id'],
                        industries_json,
                        analysis_result['analysis_summary'],
                        analysis_result['confidence_score'],
                        analysis_result['content_quality']
                    ))
                
                conn.commit()
                return True
                
            except Exception as e:
                logger.error(f"保存分析结果失败: {str(e)}")
                return False
            finally:
                conn.close()
        
        return await loop.run_in_executor(self.thread_pool, _save_result)
    
    async def batch_analyze_policies(self, batch_size: int = 20) -> int:
        """异步批量分析政策"""
        policies = await self.get_unanalyzed_policies(batch_size)
        
        if not policies:
            logger.info("没有需要分析的政策")
            return 0
        
        logger.info(f"开始异步分析 {len(policies)} 条政策...")
        
        # 创建分析任务
        tasks = [self.analyze_single_policy(policy) for policy in policies]
        
        # 并发执行分析任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 保存成功的分析结果
        success_count = 0
        save_tasks = []
        
        for result in results:
            if isinstance(result, dict) and result is not None:
                save_tasks.append(self.save_analysis_result(result))
        
        # 并发保存结果
        if save_tasks:
            save_results = await asyncio.gather(*save_tasks, return_exceptions=True)
            success_count = sum(1 for r in save_results if r is True)
        
        logger.info(f"批次分析完成，成功分析并保存 {success_count} 条政策")
        return success_count

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

async def batch_analyze_all_policies_async(api_key, db_path='events.db', batch_size=20, max_concurrent=5):
    """
    异步批量分析所有未处理的政策
    
    Args:
        api_key: 硅基流动API密钥
        db_path: 数据库路径
        batch_size: 每批处理的数量
        max_concurrent: 最大并发数
    """
    if not api_key or api_key == 'YOUR_SILICONFLOW_API_KEY':
        logger.error("请设置有效的硅基流动API Key")
        return False
    
    # 获取未分析的政策总数
    total_unanalyzed = get_unanalyzed_count(db_path)
    logger.info(f"发现 {total_unanalyzed} 条未分析的政策")
    
    if total_unanalyzed == 0:
        logger.info("所有政策都已分析完成")
        return True
    
    # 使用异步分析器
    async with AsyncPolicyAnalyzer(api_key, db_path, max_concurrent) as analyzer:
        total_processed = 0
        batch_num = 1
        
        while total_processed < total_unanalyzed:
            logger.info(f"开始处理第 {batch_num} 批，每批 {batch_size} 条")
            
            start_time = time.time()
            
            # 异步分析一批政策
            processed_count = await analyzer.batch_analyze_policies(batch_size)
            
            end_time = time.time()
            batch_time = end_time - start_time
            
            if processed_count == 0:
                logger.warning("本批次没有成功处理任何政策，可能遇到问题")
                break
            
            total_processed += processed_count
            logger.info(f"第 {batch_num} 批完成，处理了 {processed_count} 条政策，耗时 {batch_time:.2f} 秒")
            logger.info(f"总进度: {total_processed}/{total_unanalyzed} ({total_processed/total_unanalyzed*100:.1f}%)")
            
            batch_num += 1
            
            # 检查是否还有未处理的政策
            remaining = get_unanalyzed_count(db_path)
            if remaining == 0:
                logger.info("所有政策分析完成！")
                break
            
            # 短暂延迟避免API限制
            await asyncio.sleep(0.5)
    
    # 最终统计
    final_unanalyzed = get_unanalyzed_count(db_path)
    final_without_industries = get_analyzed_without_industries_count(db_path)
    
    logger.info("=== 异步批量分析完成 ===")
    logger.info(f"总共处理了 {total_processed} 条政策")
    logger.info(f"剩余未分析: {final_unanalyzed} 条")
    logger.info(f"已分析但未识别出行业: {final_without_industries} 条")
    
    return True

def main():
    """主函数"""
    # 初始化配置
    from config import init_config, Config
    
    if not init_config():
        print("错误：配置初始化失败")
        print("请确保已正确设置 SILICONFLOW_API_KEY 环境变量")
        print("示例：set SILICONFLOW_API_KEY=your_api_key_here")
        print("或者创建 .env 文件并配置相关参数")
        return
    
    try:
        api_key = Config.get_api_key()
    except ValueError as e:
        print(f"错误：{e}")
        print("示例：set SILICONFLOW_API_KEY=your_api_key_here")
        return
    
    print("开始异步批量分析政策数据...")
    print("采用异步并发处理，速度显著提升")
    print("详细日志将保存到 batch_analysis_async.log 文件中")
    
    try:
        # 运行异步分析
        success = asyncio.run(batch_analyze_all_policies_async(
            api_key, 
            batch_size=20,  # 每批20条
            max_concurrent=5  # 最大并发5个
        ))
        
        if success:
            print("\n异步批量分析完成！请查看日志了解详细结果。")
        else:
            print("\n异步批量分析过程中遇到问题，请查看日志了解详情。")
            
    except KeyboardInterrupt:
        print("\n用户中断了分析过程")
    except Exception as e:
        logger.error(f"异步批量分析过程中发生错误: {str(e)}")
        print(f"\n发生错误: {str(e)}")

if __name__ == "__main__":
    main()