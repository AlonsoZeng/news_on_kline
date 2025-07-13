#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库操作模块
提供数据库连接管理和基础操作功能
"""

# 导入主要的数据库操作函数，方便外部直接使用
from .db_operations import (
    get_db_connection,
    init_events_database,
    get_events_from_db,
    get_stock_kline_from_db,
    get_latest_stock_date_from_db,
    insert_event_to_db,
    save_stock_kline_to_db,
    migrate_mock_events_to_db,
    get_last_update_date,
    set_last_update_date
)

__all__ = [
    'get_db_connection',
    'init_events_database', 
    'get_events_from_db',
    'get_stock_kline_from_db',
    'get_latest_stock_date_from_db',
    'insert_event_to_db',
    'save_stock_kline_to_db',
    'migrate_mock_events_to_db',
    'get_last_update_date',
    'set_last_update_date'
]