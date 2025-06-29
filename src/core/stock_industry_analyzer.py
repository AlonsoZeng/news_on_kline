import sqlite3
import json
import logging
from typing import Optional, Dict, List
from datetime import datetime
import requests
import sqlite3
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class StockIndustryAnalyzer:
    """股票行业分析器"""
    
    def __init__(self, api_key: str, db_path: str):
        self.api_key = api_key
        self.db_path = db_path
        self.api_url = "https://api.siliconflow.cn/v1/chat/completions"
        self.init_database()
    
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
    

    
    def _determine_stock_type(self, stock_code: str, stock_name: str = "") -> str:
        """判断股票类型：普通股票、ETF、指数"""
        code_num = stock_code.split('.')[0]
        
        # 判断是否为指数
        index_patterns = [
            '000001.SH',  # 上证指数
            '000300.SH',  # 沪深300
            '399001.SZ',  # 深证成指
            '399006.SZ',  # 创业板指
            '000016.SH',  # 上证50
            '000905.SH',  # 中证500
            '000852.SH',  # 中证1000
        ]
        
        if stock_code in index_patterns:
            return "指数"
        
        # 判断是否为ETF（通常以5开头或1开头，且名称包含ETF相关关键词）
        if code_num.startswith('5') or code_num.startswith('1'):
            etf_keywords = ['ETF', 'etf', '基金', '指数基金']
            if stock_name and any(keyword in stock_name for keyword in etf_keywords):
                return "ETF"
            # 如果没有名称信息，根据代码模式判断
            if code_num.startswith('51') or code_num.startswith('15'):
                return "ETF"
        
        # 默认为普通股票
        return "股票"
    
    def init_database(self):
        """初始化股票行业映射表"""
        with self.get_db_connection() as conn:
            cursor = conn.cursor()
            
            # 创建股票行业映射表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stock_industry_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT UNIQUE NOT NULL,
                    stock_name TEXT,
                    industries TEXT NOT NULL,  -- JSON格式存储行业列表
                    analysis_summary TEXT,
                    confidence_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_code ON stock_industry_mapping(stock_code)')
            
            conn.commit()
            
        logger.info("股票行业映射表初始化完成")
    
    def get_stock_industries(self, stock_code: str) -> Optional[Dict]:
        """获取股票的行业信息"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT stock_name, industries, analysis_summary, confidence_score, updated_at
                    FROM stock_industry_mapping
                    WHERE stock_code = ?
                ''', (stock_code,))
                
                result = cursor.fetchone()
                if result:
                    stock_name, industries_json, summary, confidence, updated_at = result
                    industries = json.loads(industries_json) if industries_json else []
                    
                    return {
                        'stock_code': stock_code,
                        'stock_name': stock_name,
                        'industries': industries,
                        'analysis_summary': summary,
                        'confidence_score': confidence,
                        'updated_at': updated_at
                    }
        except Exception as e:
            logger.error(f"获取股票行业信息失败: {e}")
        
        return None
    
    def get_stock_detail_info(self, stock_code: str, stock_name: str = "") -> Optional[Dict]:
        """获取股票或ETF的详细信息"""
        try:
            # 尝试多个数据源获取股票详细信息
            detail_info = self._fetch_from_multiple_sources(stock_code, stock_name)
            if detail_info:
                logger.info(f"成功获取股票 {stock_code} 的详细信息")
                return detail_info
            else:
                logger.warning(f"无法获取股票 {stock_code} 的详细信息，将使用基础信息")
                return {
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'description': f"股票代码：{stock_code}，股票名称：{stock_name}",
                    'business_scope': '',
                    'main_business': '',
                    'industry_classification': ''
                }
        except Exception as e:
            logger.error(f"获取股票详细信息时发生异常: {e}")
            return None
    
    def _fetch_from_multiple_sources(self, stock_code: str, stock_name: str) -> Optional[Dict]:
        """从多个数据源获取股票信息"""
        result_info = {
            'stock_code': stock_code,
            'stock_name': stock_name,
            'description': '',
            'business_scope': '',
            'main_business': '',
            'industry_classification': ''
        }
        
        # 数据源1：尝试从东方财富获取基本信息和公司概况
        try:
            if stock_code.endswith('.SH'):
                market_code = '1'
                code = stock_code.replace('.SH', '')
            elif stock_code.endswith('.SZ'):
                market_code = '0'
                code = stock_code.replace('.SZ', '')
            else:
                market_code = '1'
                code = stock_code
            
            # 设置请求头和会话
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Connection': 'keep-alive'
            }
            
            # 获取基本信息（简化版，避免网络问题）
            try:
                basic_url = f"http://push2.eastmoney.com/api/qt/stock/get?secid={market_code}.{code}&fields=f57,f58"
                response = requests.get(basic_url, timeout=5, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data'):
                        stock_data = data['data']
                        result_info['stock_name'] = stock_name or stock_data.get('f58', '')
                        logger.info(f"成功获取股票 {stock_code} 的基本信息")
            except Exception as e:
                logger.warning(f"获取基本信息失败: {e}")
            
            # 暂时跳过复杂的公司概况获取，避免网络问题
            # 后续可以考虑使用本地数据库或其他稳定的数据源
            logger.info(f"跳过复杂网络请求，使用基础信息构建描述")
                    
        except Exception as e:
            logger.warning(f"从东方财富获取数据失败: {e}")
        
        # 数据源2：使用预定义的行业信息（避免网络请求问题）
        try:
            if not result_info.get('description') or not result_info.get('main_business'):
                # 使用一些已知的股票信息作为示例
                known_stocks = {
                    '600519.SH': {
                        'description': '贵州茅台酒股份有限公司主要从事茅台酒及系列酒的生产和销售，是中国白酒行业的龙头企业。',
                        'main_business': '白酒生产销售',
                        'business_scope': '白酒、食品、饮料的生产销售',
                        'industry_classification': '酒、饮料和精制茶制造业'
                    },
                    '000858.SZ': {
                        'description': '宜宾五粮液股份有限公司是以五粮液及其系列酒的生产经营为主的大型国有控股上市公司。',
                        'main_business': '白酒生产销售',
                        'business_scope': '白酒、食品的生产销售',
                        'industry_classification': '酒、饮料和精制茶制造业'
                    },
                    '512880.SH': {
                        'description': '证券ETF是跟踪中证全指证券公司指数的交易型开放式指数基金。',
                        'main_business': 'ETF基金投资',
                        'business_scope': '证券投资基金',
                        'industry_classification': '证券业'
                    },
                    '159915.SZ': {
                        'description': '创业板ETF是跟踪创业板指数的交易型开放式指数基金。',
                        'main_business': 'ETF基金投资',
                        'business_scope': '证券投资基金',
                        'industry_classification': '创业板综合'
                    }
                }
                
                if stock_code in known_stocks:
                    stock_info = known_stocks[stock_code]
                    result_info['description'] = stock_info['description']
                    result_info['main_business'] = stock_info['main_business']
                    result_info['business_scope'] = stock_info['business_scope']
                    result_info['industry_classification'] = stock_info['industry_classification']
                    logger.info(f"使用预定义信息填充股票 {stock_code} 的详细信息")
        except Exception as e:
            logger.warning(f"使用预定义信息失败: {e}")
        
        # 如果没有获取到详细信息，构建基础描述
        if not result_info['description']:
            stock_type = self._determine_stock_type(stock_code, stock_name)
            if stock_type == "ETF":
                result_info['description'] = f"ETF基金 {stock_code}（{result_info['stock_name']}），跟踪特定指数或行业板块的交易型开放式指数基金。"
            elif stock_type == "指数":
                result_info['description'] = f"股票指数 {stock_code}（{result_info['stock_name']}），反映特定市场或行业股票价格变动的指标。"
            else:
                result_info['description'] = f"上市公司 {stock_code}（{result_info['stock_name']}），在A股市场公开交易的股份有限公司。"
        
        return result_info
    
    def analyze_stock_industry(self, stock_code: str, stock_name: str = "") -> Optional[Dict]:
        """使用AI分析股票所属行业（基于详细信息）"""
        
        # 判断股票类型
        stock_type = self._determine_stock_type(stock_code, stock_name)
        
        # 获取股票详细信息
        detail_info = self.get_stock_detail_info(stock_code, stock_name)
        if not detail_info:
            logger.error(f"无法获取股票 {stock_code} 的详细信息，分析失败")
            return None
        
        # 构建包含详细信息的提示词
        detail_text = f"""
股票基本信息：
- 股票代码：{detail_info.get('stock_code', stock_code)}
- 股票名称：{detail_info.get('stock_name', stock_name)}
- 公司描述：{detail_info.get('description', '')}
- 经营范围：{detail_info.get('business_scope', '')}
- 主营业务：{detail_info.get('main_business', '')}
- 行业分类：{detail_info.get('industry_classification', '')}
"""
        
        # 根据股票类型构建不同的提示词
        if stock_type == "ETF":
            prompt = f"""
请基于以下ETF基金的详细信息，分析其所跟踪的行业板块：

{detail_text}

分析要求：
1. 基于ETF的名称、描述和相关信息，识别其主要投资的行业领域
2. 分析该ETF覆盖的细分行业
3. 考虑A股市场的行业分类标准
4. 提供详细的分析说明，说明判断依据
5. 给出分析的置信度评分(0-1之间)

请以JSON格式返回结果：
{{
    "industries": ["主要行业1", "细分行业1", "相关行业1"],
    "analysis_summary": "基于ETF详细信息的分析说明，包括判断依据",
    "confidence_score": 0.85
}}

注意：
- industries数组应包含3-5个相关行业关键词
- 行业名称要准确、具体
- 分析说明要详细，包含判断依据
- 置信度要基于信息完整度客观评估
"""
        elif stock_type == "指数":
            prompt = f"""
请基于以下指数的详细信息，分析其所覆盖的行业板块：

{detail_text}

分析要求：
1. 基于指数的名称、描述和相关信息，识别其主要覆盖的行业领域
2. 分析该指数包含的主要行业构成
3. 考虑A股市场的行业分类标准
4. 提供详细的分析说明，说明判断依据
5. 给出分析的置信度评分(0-1之间)

请以JSON格式返回结果：
{{
    "industries": ["主要行业1", "细分行业1", "相关行业1"],
    "analysis_summary": "基于指数详细信息的分析说明，包括判断依据",
    "confidence_score": 0.85
}}

注意：
- industries数组应包含3-5个相关行业关键词
- 行业名称要准确、具体
- 分析说明要详细，包含判断依据
- 置信度要基于信息完整度客观评估
"""
        else:  # 普通股票
            prompt = f"""
请基于以下上市公司的详细信息，分析其所属的行业分类：

{detail_text}

分析要求：
1. 基于公司的名称、描述、经营范围、主营业务等信息，识别其主营业务所属的行业
2. 分析该公司涉及的细分行业领域
3. 考虑A股市场的行业分类标准
4. 提供详细的分析说明，说明判断依据
5. 给出分析的置信度评分(0-1之间)

请以JSON格式返回结果：
{{
    "industries": ["主要行业1", "细分行业1", "相关行业1"],
    "analysis_summary": "基于公司详细信息的分析说明，包括判断依据",
    "confidence_score": 0.85
}}

注意：
- industries数组应包含3-5个相关行业关键词
- 行业名称要准确、具体
- 分析说明要详细，包含判断依据
- 置信度要基于信息完整度客观评估
"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 根据股票类型调整系统提示词
        if stock_type == "ETF":
            system_content = "你是一个专业的ETF基金分析师，擅长分析A股市场的ETF基金行业分类。请基于ETF的详细信息（包括名称、描述、投资范围等），准确识别其跟踪的行业板块。你需要仔细分析提供的所有信息，给出详细的判断依据。"
        elif stock_type == "指数":
            system_content = "你是一个专业的指数分析师，擅长分析A股市场的指数构成。请基于指数的详细信息（包括名称、描述、成分股特征等），准确识别其覆盖的主要行业领域。你需要仔细分析提供的所有信息，给出详细的判断依据。"
        else:
            system_content = "你是一个专业的股票行业分析师，擅长分析A股市场的上市公司行业分类。请基于公司的详细信息（包括名称、描述、经营范围、主营业务等），准确识别其主营业务所属行业。你需要仔细分析提供的所有信息，给出详细的判断依据。"
        
        data = {
            "model": "deepseek-ai/DeepSeek-V2.5",
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(self.api_url, headers=headers, json=data, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            content = result['choices'][0]['message']['content']
            
            # 尝试解析JSON
            try:
                # 提取JSON部分
                start_idx = content.find('{')
                end_idx = content.rfind('}') + 1
                if start_idx != -1 and end_idx != 0:
                    json_str = content[start_idx:end_idx]
                    analysis_result = json.loads(json_str)
                    
                    # 验证必要字段
                    if 'industries' in analysis_result and 'analysis_summary' in analysis_result:
                        logger.info(f"成功分析股票 {stock_code} 的行业信息")
                        return analysis_result
                    else:
                        logger.warning(f"AI返回结果缺少必要字段: {analysis_result}")
                else:
                    logger.warning(f"无法从AI响应中提取JSON: {content}")
            except json.JSONDecodeError as e:
                logger.error(f"解析AI返回的JSON失败: {e}, 内容: {content}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"调用AI API失败: {e}")
        except Exception as e:
            logger.error(f"分析股票行业时发生异常: {e}")
        
        return None
    
    def save_stock_industry(self, stock_code: str, stock_name: str, analysis_result: Dict) -> bool:
        """保存股票行业分析结果"""
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                industries_json = json.dumps(analysis_result.get('industries', []), ensure_ascii=False)
                
                # 使用REPLACE语句，如果存在则更新，不存在则插入
                cursor.execute('''
                    REPLACE INTO stock_industry_mapping 
                    (stock_code, stock_name, industries, analysis_summary, confidence_score, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    stock_name,
                    industries_json,
                    analysis_result.get('analysis_summary', ''),
                    analysis_result.get('confidence_score', 0.0),
                    datetime.now().isoformat()
                ))
                
                conn.commit()
                logger.info(f"成功保存股票 {stock_code} 的行业信息")
                return True
                
        except Exception as e:
            logger.error(f"保存股票行业信息失败: {e}")
            return False
    
    def get_or_analyze_stock_industry(self, stock_code: str, stock_name: str = "") -> Optional[Dict]:
        """获取或分析股票行业信息（优先从数据库获取）"""
        # 首先尝试从数据库获取
        existing_data = self.get_stock_industries(stock_code)
        if existing_data:
            logger.info(f"从数据库获取到股票 {stock_code} 的行业信息")
            return existing_data
        
        # 数据库中没有，使用AI分析
        logger.info(f"数据库中没有股票 {stock_code} 的行业信息，开始AI分析")
        analysis_result = self.analyze_stock_industry(stock_code, stock_name)
        
        if analysis_result:
            # 保存分析结果
            if self.save_stock_industry(stock_code, stock_name, analysis_result):
                return {
                    'stock_code': stock_code,
                    'stock_name': stock_name,
                    'industries': analysis_result.get('industries', []),
                    'analysis_summary': analysis_result.get('analysis_summary', ''),
                    'confidence_score': analysis_result.get('confidence_score', 0.0),
                    'updated_at': datetime.now().isoformat()
                }
        
        return None
    
    def get_related_policies(self, industries: List[str], limit: int = 50) -> List[Dict]:
        """根据行业获取相关政策事件"""
        if not industries:
            return []
        
        try:
            with self.get_db_connection() as conn:
                cursor = conn.cursor()
                
                # 构建查询条件，匹配任一行业关键词
                industry_conditions = []
                params = []
                
                for industry in industries:
                    industry_conditions.append("(pe.title LIKE ? OR pa.industries LIKE ?)")
                    params.extend([f"%{industry}%", f"%{industry}%"])
                
                where_clause = " OR ".join(industry_conditions)
                
                query = f"""
                    SELECT DISTINCT pe.id, pe.date, pe.title, pe.event_type, pe.department, 
                           pe.policy_level, pe.impact_level, pe.source_url, pe.created_at, 
                           pe.content_type, pa.industries, pa.analysis_summary, pa.confidence_score
                    FROM policy_events pe
                    LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
                    WHERE {where_clause}
                    ORDER BY pe.date DESC
                    LIMIT ?
                """
                
                params.append(limit)
                cursor.execute(query, params)
                events = cursor.fetchall()
                
                events_list = []
                for event in events:
                    # 解析AI分析结果的JSON数据
                    ai_industries = json.loads(event[10]) if event[10] else []
                    
                    events_list.append({
                        'id': event[0],
                        'date': event[1],
                        'title': event[2],
                        'event_type': event[3],
                        'department': event[4] if event[4] else '',
                        'policy_level': event[5] if event[5] else '',
                        'impact_level': event[6] if event[6] else '',
                        'source_url': event[7] if event[7] else '',
                        'created_at': event[8] if event[8] else '',
                        'content_type': event[9] if event[9] else '政策',
                        'ai_industries': ai_industries,
                        'ai_summary': event[11] if event[11] else '',
                        'ai_confidence': event[12] if event[12] else None
                    })
                
                logger.info(f"根据行业 {industries} 找到 {len(events_list)} 条相关政策")
                return events_list
                
        except Exception as e:
            logger.error(f"获取相关政策失败: {e}")
            return []
    
    def get_stock_type(self, stock_code: str, stock_name: str = "") -> str:
        """获取股票类型"""
        return self._determine_stock_type(stock_code, stock_name)
    
    def is_etf(self, stock_code: str, stock_name: str = "") -> bool:
        """判断是否为ETF"""
        return self._determine_stock_type(stock_code, stock_name) == "ETF"
    
    def is_index(self, stock_code: str, stock_name: str = "") -> bool:
        """判断是否为指数"""
        return self._determine_stock_type(stock_code, stock_name) == "指数"
    
    def is_stock(self, stock_code: str, stock_name: str = "") -> bool:
        """判断是否为普通股票"""
        return self._determine_stock_type(stock_code, stock_name) == "股票"

# 测试代码
if __name__ == "__main__":
    import os
    
    API_KEY = os.getenv('SILICONFLOW_API_KEY', 'sk-rtfxnalfnpfrucbjvzzizgsltocaywdtfvvcmloznshsqzfo')
    DB_PATH = 'events.db'
    
    analyzer = StockIndustryAnalyzer(API_KEY, DB_PATH)
    
    # 测试分析茅台股票
    result = analyzer.get_or_analyze_stock_industry('600519', '贵州茅台')
    if result:
        print(f"股票行业分析结果: {result}")
        
        # 获取相关政策
        policies = analyzer.get_related_policies(result['industries'], limit=10)
        print(f"相关政策数量: {len(policies)}")
        for policy in policies[:3]:
            print(f"- {policy['date']}: {policy['title']}")
    else:
        print("分析失败")