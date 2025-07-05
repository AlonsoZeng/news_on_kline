"""
数据库操作模块

该模块负责处理所有与数据库相关的操作，包括：
- 数据库连接管理
- 事件数据的增删改查
- 股票K线数据的存储和查询
- 数据库初始化和迁移
- 更新日期的管理

作者: AI Assistant
创建时间: 2024
"""

import sqlite3
import pandas as pd
import os
import json
from datetime import date
from contextlib import contextmanager
from typing import Optional, List, Dict, Any


@contextmanager
def get_db_connection(db_file: Optional[str] = None):
    """
    数据库连接上下文管理器
    
    Args:
        db_file: 数据库文件路径，默认为 'data/events.db'
        
    Yields:
        sqlite3.Connection: 数据库连接对象
        
    Example:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events")
    """
    if db_file is None:
        db_file = 'data/events.db'
    
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()


def init_events_database(events_db_file: str) -> None:
    """
    初始化事件数据库，创建表结构
    
    Args:
        events_db_file: 事件数据库文件路径
        
    功能说明:
    - 创建events表：存储事件数据
    - 创建stock_kline表：存储股票K线数据
    - 创建必要的索引以提高查询性能
    """
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        # 创建事件表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            event_type TEXT DEFAULT 'custom',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建股票K线数据表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_kline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL NOT NULL,
            close REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            volume INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(stock_code, date)
        )
        ''')
        
        # 创建索引以提高查询性能
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_date ON stock_kline(stock_code, date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_updated ON stock_kline(stock_code, updated_at)')
        
        conn.commit()
    print(f"事件数据库已初始化: {events_db_file}")


def get_events_from_db(events_db_file: str) -> List[Dict[str, Any]]:
    """
    从数据库获取事件数据（优先使用政策数据表）
    
    Args:
        events_db_file: 事件数据库文件路径
        
    Returns:
        List[Dict]: 事件数据列表，每个事件包含date、title、event_type等字段
        
    功能说明:
    - 优先从policy_events表获取数据（新表）
    - 如果新表不存在，回退到events表（旧表）
    - 返回统一格式的事件数据
    """
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        # 首先尝试从新的政策数据表获取
        try:
            cursor.execute("""
                SELECT date, title, event_type, department, policy_level, impact_level 
                FROM policy_events 
                ORDER BY date DESC
            """)
            events = cursor.fetchall()
            
            if events:
                # 转换为字典格式
                events_list = []
                for event in events:
                    events_list.append({
                        'date': event[0],
                        'title': event[1],
                        'event_type': event[2],
                        'department': event[3] if len(event) > 3 else '',
                        'policy_level': event[4] if len(event) > 4 else '',
                        'impact_level': event[5] if len(event) > 5 else ''
                    })
                
                return events_list
        except sqlite3.OperationalError:
            # 如果政策数据表不存在，回退到旧表
            pass
        
        # 回退到旧的events表
        cursor.execute('SELECT date, title, event_type FROM events ORDER BY date')
        rows = cursor.fetchall()
        
        events = []
        for row in rows:
            events.append({
                'date': row[0],
                'title': row[1],
                'event_type': row[2],
                'department': '',
                'policy_level': '',
                'impact_level': ''
            })
        
        return events


def get_stock_kline_from_db(stock_code: str, events_db_file: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """
    从数据库获取股票K线数据
    
    Args:
        stock_code: 股票代码
        events_db_file: 事件数据库文件路径
        start_date: 开始日期，格式为'YYYY-MM-DD'，可选
        
    Returns:
        pd.DataFrame: K线数据，包含date、open、close、high、low、volume列
        
    功能说明:
    - 根据股票代码查询K线数据
    - 支持按开始日期过滤
    - 返回按日期排序的DataFrame
    """
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        if start_date:
            cursor.execute('''
                SELECT date, open, close, high, low, volume 
                FROM stock_kline 
                WHERE stock_code = ? AND date >= ? 
                ORDER BY date
            ''', (stock_code, start_date))
        else:
            cursor.execute('''
                SELECT date, open, close, high, low, volume 
                FROM stock_kline 
                WHERE stock_code = ? 
                ORDER BY date
            ''', (stock_code,))
        
        rows = cursor.fetchall()
        
        if not rows:
            return pd.DataFrame()
        
        # 转换为DataFrame
        df = pd.DataFrame(rows, columns=['date', 'open', 'close', 'high', 'low', 'volume'])
        df['date'] = pd.to_datetime(df['date'])
        return df


def get_latest_stock_date_from_db(stock_code: str, events_db_file: str) -> Optional[str]:
    """
    获取数据库中指定股票的最新日期
    
    Args:
        stock_code: 股票代码
        events_db_file: 事件数据库文件路径
        
    Returns:
        Optional[str]: 最新日期字符串，格式为'YYYY-MM-DD'，如果没有数据则返回None
    """
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT MAX(date) FROM stock_kline WHERE stock_code = ?
        ''', (stock_code,))
        
        result = cursor.fetchone()
        
        return result[0] if result and result[0] else None


def insert_event_to_db(date: str, title: str, events_db_file: str, event_type: str = 'custom') -> None:
    """
    向数据库插入单个事件
    
    Args:
        date: 事件日期，格式为'YYYY-MM-DD'
        title: 事件标题
        events_db_file: 事件数据库文件路径
        event_type: 事件类型，默认为'custom'
        
    功能说明:
    - 向events表插入新的事件记录
    - 自动设置创建时间
    """
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO events (date, title, event_type) VALUES (?, ?, ?)', 
                       (date, title, event_type))
        
        conn.commit()


def save_stock_kline_to_db(stock_code: str, df_kline: pd.DataFrame, events_db_file: str, 
                          include_non_trading_days: bool = False) -> None:
    """
    将股票K线数据保存到数据库
    
    Args:
        stock_code: 股票代码
        df_kline: K线数据DataFrame
        events_db_file: 事件数据库文件路径
        include_non_trading_days: 是否包含非交易日数据
        
    功能说明:
    - 将K线数据批量保存到数据库
    - 使用INSERT OR REPLACE处理重复数据
    - 自动更新updated_at字段
    
    注意:
    - 如果include_non_trading_days为True，需要先调用fill_non_trading_days函数
    """
    if df_kline.empty:
        return
    
    # 注意：这里暂时注释掉fill_non_trading_days的调用，因为该函数还在app.py中
    # 后续需要将该函数也迁移到合适的模块
    # if include_non_trading_days:
    #     df_kline = fill_non_trading_days(df_kline)
    
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        
        # 使用INSERT OR REPLACE来处理重复数据
        for _, row in df_kline.iterrows():
            cursor.execute('''
                INSERT OR REPLACE INTO stock_kline 
                (stock_code, date, open, close, high, low, volume, updated_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                stock_code,
                row['date'].strftime('%Y-%m-%d'),
                float(row['open']),
                float(row['close']),
                float(row['high']),
                float(row['low']),
                int(row['volume'])
            ))
        
        conn.commit()
    print(f"已保存 {len(df_kline)} 条 {stock_code} 的K线数据到数据库")


def migrate_mock_events_to_db(events_db_file: str) -> None:
    """
    将模拟事件数据迁移到数据库（仅在首次运行时执行）
    
    Args:
        events_db_file: 事件数据库文件路径
        
    功能说明:
    - 检查数据库中是否已有数据
    - 如果没有数据，提示用户手动添加或从外部导入
    """
    # 检查数据库中是否已有数据
    with get_db_connection(events_db_file) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM events')
        count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"数据库中已有 {count} 条事件记录，跳过迁移")
        return
    
    print("数据库为空，但模拟事件生成函数已移除。请手动添加事件数据或从外部数据源导入。")


def get_last_update_date(stock_code: str, db_file: str) -> Optional[date]:
    """
    从JSON文件获取指定股票的最后更新日期
    
    Args:
        stock_code: 股票代码
        db_file: JSON文件路径
        
    Returns:
        Optional[date]: 最后更新日期，如果没有记录则返回None
        
    功能说明:
    - 从stock_updates.json文件读取股票的最后更新时间
    - 用于判断是否需要从API获取新数据
    """
    if not os.path.exists(db_file):
        return None
    try:
        with open(db_file, 'r') as f:
            data = json.load(f)
            date_str = data.get(stock_code)
            if date_str:
                return date.fromisoformat(date_str)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"读取 {stock_code} 最后更新日期失败: {e}")
    return None


def set_last_update_date(stock_code: str, today_date: date, db_file: str) -> None:
    """
    将指定股票今天的日期写入JSON文件作为最后更新日期
    
    Args:
        stock_code: 股票代码
        today_date: 今天的日期
        db_file: JSON文件路径
        
    功能说明:
    - 更新stock_updates.json文件中的股票更新时间记录
    - 如果文件不存在会自动创建
    """
    data = {}
    if os.path.exists(db_file):
        try:
            with open(db_file, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"读取 stock_updates.json 失败，将创建新文件: {e}")
            data = {}

    data[stock_code] = today_date.isoformat()
    try:
        with open(db_file, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"写入 {stock_code} 最后更新日期失败: {e}")