"""数据统计分析模块

提供数据统计和分析功能，包括：
- 数据库统计信息获取
- 事件数据详情查询
- 数据质量分析
"""

from .data_statistics import get_data_statistics, get_events_with_details

__all__ = ['get_data_statistics', 'get_events_with_details']