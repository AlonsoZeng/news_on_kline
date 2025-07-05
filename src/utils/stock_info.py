"""
股票信息工具模块

该模块提供股票名称获取和基本信息查询功能，包括：
- 股票名称获取（支持预定义映射、AI分析器、TuShare API）
- 股票信息辅助类
- 便捷的股票信息查询接口

作者: AI Assistant
创建时间: 2024
"""

import logging
from typing import Optional, Dict, Any

# 设置日志
logger = logging.getLogger(__name__)


class StockInfoHelper:
    """
    股票信息辅助类
    
    提供股票名称获取和基本信息查询功能
    """
    
    def __init__(self, tushare_token: str = None, stock_industry_analyzer=None):
        """
        初始化股票信息辅助类
        
        Args:
            tushare_token: TuShare API Token
            stock_industry_analyzer: 股票行业分析器实例
        """
        self.tushare_token = tushare_token
        self.stock_industry_analyzer = stock_industry_analyzer
        
        # 预定义的股票名称映射表（常见股票）
        self.stock_name_map = {
            '600519.SH': '贵州茅台',
            '600519': '贵州茅台',
            '000001.SZ': '平安银行',
            '000001': '平安银行',
            '000002.SZ': '万科A',
            '000002': '万科A',
            '600036.SH': '招商银行',
            '600036': '招商银行',
            '000858.SZ': '五粮液',
            '000858': '五粮液',
            '512880.SH': '证券ETF',
            '512880': '证券ETF',
            '159915.SZ': '创业板ETF',
            '159915': '创业板ETF',
            '510300.SH': '沪深300ETF',
            '510300': '沪深300ETF',
            '510500.SH': '中证500ETF',
            '510500': '中证500ETF',
            '000001.SH': '上证指数',
            '399001.SZ': '深证成指',
            '399006.SZ': '创业板指'
        }
    
    def get_stock_name(self, stock_code: str) -> Optional[str]:
        """
        获取股票名称
        
        Args:
            stock_code: 股票代码
            
        Returns:
            str: 股票名称，如果获取失败返回 None
            
        获取策略:
        1. 首先尝试从预定义映射表获取
        2. 尝试使用股票行业分析器获取详细信息
        3. 尝试TuShare API（如果Token有效）
        """
        # 首先尝试从预定义映射表获取
        if stock_code in self.stock_name_map:
            logger.info(f"从预定义映射表获取股票名称: {stock_code} -> {self.stock_name_map[stock_code]}")
            return self.stock_name_map[stock_code]
        
        # 尝试使用股票行业分析器获取详细信息
        if self.stock_industry_analyzer:
            try:
                detail_info = self.stock_industry_analyzer.get_stock_detail_info(stock_code)
                if detail_info and detail_info.get('stock_name'):
                    logger.info(f"从股票行业分析器获取股票名称: {stock_code} -> {detail_info['stock_name']}")
                    return detail_info['stock_name']
            except Exception as e:
                logger.warning(f"从股票行业分析器获取名称失败: {e}")
        
        # 尝试TuShare API（如果Token有效）
        if self.tushare_token:
            try:
                import tushare as ts
                pro = ts.pro_api(self.tushare_token)
                
                # 处理股票代码格式
                ts_code = self._format_tushare_code(stock_code)
                
                # 获取股票基本信息
                df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
                if not df.empty:
                    stock_name = df.iloc[0]['name']
                    logger.info(f"从TuShare API获取股票名称: {stock_code} -> {stock_name}")
                    return stock_name
                
                # 如果没找到，尝试ETF
                df_etf = pro.fund_basic(ts_code=ts_code, fields='ts_code,name')
                if not df_etf.empty:
                    etf_name = df_etf.iloc[0]['name']
                    logger.info(f"从TuShare API获取ETF名称: {stock_code} -> {etf_name}")
                    return etf_name
                    
            except Exception as e:
                logger.warning(f"TuShare获取股票名称失败: {e}")
        
        logger.warning(f"无法获取股票 {stock_code} 的名称")
        return None
    
    def _format_tushare_code(self, stock_code: str) -> str:
        """
        格式化股票代码为TuShare格式
        
        Args:
            stock_code: 原始股票代码
            
        Returns:
            str: TuShare格式的股票代码
        """
        if '.' in stock_code:
            return stock_code
        else:
            # 根据代码判断交易所
            if stock_code.startswith(('60', '68')):
                return f"{stock_code}.SH"
            elif stock_code.startswith(('00', '30')):
                return f"{stock_code}.SZ"
            else:
                return f"{stock_code}.SH"  # 默认上海
    
    def get_stock_info(self, stock_code: str) -> Dict[str, Any]:
        """
        获取股票的基本信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            Dict: 包含股票基本信息的字典
        """
        info = {
            'stock_code': stock_code,
            'stock_name': self.get_stock_name(stock_code),
            'formatted_code': self._format_tushare_code(stock_code)
        }
        
        # 如果有股票行业分析器，获取更多信息
        if self.stock_industry_analyzer:
            try:
                detail_info = self.stock_industry_analyzer.get_stock_detail_info(stock_code)
                if detail_info:
                    info.update({
                        'description': detail_info.get('description', ''),
                        'business_scope': detail_info.get('business_scope', ''),
                        'main_business': detail_info.get('main_business', ''),
                        'industry_classification': detail_info.get('industry_classification', '')
                    })
            except Exception as e:
                logger.warning(f"获取股票详细信息失败: {e}")
        
        return info


# 全局股票信息辅助实例（将在app.py中初始化）
_stock_info_helper: Optional[StockInfoHelper] = None


def init_stock_info_helper(tushare_token: str = None, stock_industry_analyzer=None):
    """
    初始化全局股票信息辅助实例
    
    Args:
        tushare_token: TuShare API Token
        stock_industry_analyzer: 股票行业分析器实例
    """
    global _stock_info_helper
    _stock_info_helper = StockInfoHelper(tushare_token, stock_industry_analyzer)
    logger.info("股票信息辅助模块初始化完成")


def get_stock_name(stock_code: str) -> Optional[str]:
    """
    便捷函数：获取股票名称
    
    Args:
        stock_code: 股票代码
        
    Returns:
        str: 股票名称，如果获取失败返回 None
    """
    if _stock_info_helper is None:
        logger.error("股票信息辅助模块未初始化，请先调用 init_stock_info_helper()")
        return None
    
    return _stock_info_helper.get_stock_name(stock_code)


def get_stock_info(stock_code: str) -> Dict[str, Any]:
    """
    便捷函数：获取股票基本信息
    
    Args:
        stock_code: 股票代码
        
    Returns:
        Dict: 包含股票基本信息的字典
    """
    if _stock_info_helper is None:
        logger.error("股票信息辅助模块未初始化，请先调用 init_stock_info_helper()")
        return {'stock_code': stock_code, 'stock_name': None}
    
    return _stock_info_helper.get_stock_info(stock_code)