from flask import Flask, render_template, request, redirect, url_for, jsonify
import tushare as ts
from pyecharts.charts import Kline, Line, Bar
from pyecharts import options as opts
from pyecharts.globals import ThemeType
import pandas as pd
import os
from datetime import datetime, date, timedelta
import sqlite3
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from contextlib import contextmanager
import json

# 为 pandas 2.0+ 添加 append 方法兼容性
if not hasattr(pd.DataFrame, 'append'):
    def append_compat(self, other, ignore_index=False, **kwargs):
        return pd.concat([self, other], ignore_index=ignore_index, **kwargs)
    pd.DataFrame.append = append_compat

from src.core.policy_data_fetcher import PolicyDataFetcher
from src.core.ai_policy_analyzer import AIPolicyAnalyzer
from src.core.stock_industry_analyzer import StockIndustryAnalyzer
from src.core.event_manager import register_event_routes
from config.app_config import AppConfig

# --- 数据库上下文管理器 --- #
@contextmanager
def get_db_connection(db_file=None):
    """数据库连接上下文管理器"""
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

# --- 配置管理 --- #
# AppConfig类已移至config/app_config.py模块

# --- 配置初始化 --- #
config = AppConfig()
TUSHARE_TOKEN = config.TUSHARE_TOKEN
DB_FILE = config.DB_FILE
EVENTS_DB_FILE = config.EVENTS_DB_FILE
SILICONFLOW_API_KEY = config.SILICONFLOW_API_KEY

# --- Flask 应用初始化 --- #
app = Flask(__name__)
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 初始化AI政策分析器
ai_analyzer = None
stock_industry_analyzer = None
if SILICONFLOW_API_KEY:
    try:
        ai_analyzer = AIPolicyAnalyzer(SILICONFLOW_API_KEY, EVENTS_DB_FILE)
        stock_industry_analyzer = StockIndustryAnalyzer(SILICONFLOW_API_KEY, EVENTS_DB_FILE)
        print("AI政策分析器和股票行业分析器初始化成功")
    except Exception as e:
        print(f"AI分析器初始化失败: {e}")
else:
    print("未配置AI API Key，AI分析功能不可用")

# --- 数据库初始化 --- #
def init_events_database():
    """初始化事件数据库，创建表结构"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
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
    print(f"事件数据库已初始化: {EVENTS_DB_FILE}")

def get_events_from_db():
    """从数据库获取事件数据（优先使用政策数据表）"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
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

def get_stock_kline_from_db(stock_code, start_date=None):
    """从数据库获取股票K线数据"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
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

def get_latest_stock_date_from_db(stock_code):
    """获取数据库中指定股票的最新日期"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT MAX(date) FROM stock_kline WHERE stock_code = ?
        ''', (stock_code,))
        
        result = cursor.fetchone()
        
        return result[0] if result and result[0] else None

def insert_event_to_db(date, title, event_type='custom'):
    """向数据库插入单个事件"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        
        cursor.execute('INSERT INTO events (date, title, event_type) VALUES (?, ?, ?)', 
                       (date, title, event_type))
        
        conn.commit()

def save_stock_kline_to_db(stock_code, df_kline, include_non_trading_days=False):
    """将股票K线数据保存到数据库"""
    if df_kline.empty:
        return
    
    # 如果需要包含非交易日，先填充数据
    if include_non_trading_days:
        df_kline = fill_non_trading_days(df_kline)
    
    with get_db_connection(EVENTS_DB_FILE) as conn:
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

def migrate_mock_events_to_db():
    """将模拟事件数据迁移到数据库（仅在首次运行时执行）"""
    # 检查数据库中是否已有数据
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM events')
        count = cursor.fetchone()[0]
    
    if count > 0:
        print(f"数据库中已有 {count} 条事件记录，跳过迁移")
        return
    
    print("数据库为空，但模拟事件生成函数已移除。请手动添加事件数据或从外部数据源导入。")

# 初始化数据库
init_events_database()

# --- 数据库相关函数 --- #
def get_last_update_date(stock_code):
    """从JSON文件获取指定股票的最后更新日期"""
    if not os.path.exists(DB_FILE):
        return None
    try:
        with open(DB_FILE, 'r') as f:
            data = json.load(f)
            date_str = data.get(stock_code)
            if date_str:
                return date.fromisoformat(date_str)
    except (FileNotFoundError, json.JSONDecodeError, Exception) as e:
        print(f"读取 {stock_code} 最后更新日期失败: {e}")
    return None

def set_last_update_date(stock_code, today_date):
    """将指定股票今天的日期写入JSON文件作为最后更新日期"""
    data = {}
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                data = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f"读取 stock_updates.json 失败，将创建新文件: {e}")
            data = {}

    data[stock_code] = today_date.isoformat()
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"写入 {stock_code} 最后更新日期失败: {e}")

# --- 数据获取与处理 --- #


def fetch_stock_kline_data(stock_code_tushare):
    """获取股票K线数据，优先从数据库读取，必要时从TuShare API获取"""
    today = datetime.now().date()
    start_date = '2019-08-18'  # 数据起始日期
    
    print(f"开始获取 {stock_code_tushare} 的K线数据...")
    
    # 1. 首先从数据库获取现有数据
    db_data = get_stock_kline_from_db(stock_code_tushare, start_date)
    
    # 2. 检查是否需要从API获取新数据
    need_api_fetch = False
    api_start_date = start_date
    
    if db_data.empty:
        print(f"数据库中没有 {stock_code_tushare} 的数据，需要从API获取全部数据")
        need_api_fetch = True
    else:
        # 获取数据库中最新的日期
        latest_date_str = get_latest_stock_date_from_db(stock_code_tushare)
        if latest_date_str:
            latest_date = datetime.strptime(latest_date_str, '%Y-%m-%d').date()
            print(f"数据库中 {stock_code_tushare} 最新数据日期: {latest_date}")
            
            # 如果最新数据不是今天，且不是周末，则需要获取增量数据
            days_diff = (today - latest_date).days
            if days_diff > 0:
                # 从最新日期的下一天开始获取
                next_date = latest_date + pd.Timedelta(days=1)
                api_start_date = next_date.strftime('%Y-%m-%d')
                need_api_fetch = True
                print(f"需要获取 {api_start_date} 到今天的增量数据")
            else:
                print(f"数据库中的数据已是最新，无需从API获取")
        else:
            need_api_fetch = True
    
    # 3. 如果需要，从API获取数据
    final_data = pd.DataFrame()
    if need_api_fetch:
        try:
            print(f"正在从TuShare API获取 {stock_code_tushare} 从 {api_start_date} 开始的数据...")
            df_api = ts.get_k_data(stock_code_tushare, start=api_start_date)
            
            if df_api is not None and not df_api.empty:
                # 处理API返回的数据
                df_api_processed = pd.DataFrame({
                    'date': pd.to_datetime(df_api['date']),
                    'open': df_api['open'],
                    'close': df_api['close'],
                    'low': df_api['low'],
                    'high': df_api['high'],
                    'volume': df_api['volume']
                })
                df_api_processed = df_api_processed.sort_values(by='date')
                
                # 保存到数据库（包含非交易日占位数据）
                save_stock_kline_to_db(stock_code_tushare, df_api_processed, include_non_trading_days=True)
                
                # 更新最后获取时间记录
                set_last_update_date(stock_code_tushare, today)
                
                # 合并数据库数据和新获取的数据
                if not db_data.empty:
                    # 确保没有重复数据
                    final_data = pd.concat([db_data, df_api_processed]).drop_duplicates(subset=['date']).sort_values(by='date')
                    print(f"合并数据：数据库 {len(db_data)} 条 + API {len(df_api_processed)} 条 = 总计 {len(final_data)} 条")
                else:
                    final_data = df_api_processed
                    print(f"从API获取到 {len(df_api_processed)} 条新数据")
            else:
                print(f"TuShare API 未返回 {stock_code_tushare} 的数据")
                if not db_data.empty:
                    final_data = db_data
                    print(f"返回数据库中的现有数据 ({len(db_data)} 条)")
                else:
                    return pd.DataFrame()
                    
        except Exception as e:
            print(f"从TuShare API获取 {stock_code_tushare} 数据时出错: {e}")
            if not db_data.empty:
                final_data = db_data
                print(f"API获取失败，返回数据库中的现有数据 ({len(db_data)} 条)")
            else:
                return pd.DataFrame()
    else:
         # 不需要API获取，直接返回数据库数据
         final_data = db_data
         print(f"从数据库返回 {len(db_data)} 条数据")
    
    # 4. 检查并补全历史数据中缺失的非交易日
    check_and_fill_missing_non_trading_days(stock_code_tushare)
    
    # 5. 重新从数据库获取完整数据（包含补全的非交易日）
    final_data = get_stock_kline_from_db(stock_code_tushare, start_date)
    
    # 6. 填充非交易日的占位蜡烛（确保最新数据也包含非交易日）
    if not final_data.empty:
        final_data = fill_non_trading_days(final_data)
        print(f"填充非交易日后，总计 {len(final_data)} 条数据")
    
    return final_data

def fill_non_trading_days(df_kline):
    """为非交易日填充占位蜡烛，使用上一个交易日的收盘价作为开高低收价格"""
    if df_kline.empty:
        return df_kline
    
    # 确保数据按日期排序
    df_kline = df_kline.sort_values(by='date').reset_index(drop=True)
    
    # 获取日期范围
    start_date = df_kline['date'].min()
    end_date = df_kline['date'].max()
    
    # 创建完整的日期范围（包括周末和节假日）
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # 创建一个包含所有日期的DataFrame
    full_df = pd.DataFrame({'date': date_range})
    
    # 合并原始数据
    merged_df = pd.merge(full_df, df_kline, on='date', how='left')
    
    # 填充缺失的数据
    filled_rows = []
    last_close_price = None
    
    for i, row in merged_df.iterrows():
        if pd.isna(row['open']):  # 如果是非交易日（缺失数据）
            if last_close_price is not None:
                # 使用上一个交易日的收盘价作为开高低收价格
                filled_row = {
                    'date': row['date'],
                    'open': last_close_price,
                    'close': last_close_price,
                    'high': last_close_price,
                    'low': last_close_price,
                    'volume': 0  # 非交易日成交量为0
                }
                filled_rows.append(filled_row)
                # print(f"为非交易日 {row['date'].strftime('%Y-%m-%d')} 创建占位蜡烛，价格: {last_close_price}")
        else:
            # 交易日，保留原始数据并更新最后收盘价
            filled_rows.append({
                'date': row['date'],
                'open': row['open'],
                'close': row['close'],
                'high': row['high'],
                'low': row['low'],
                'volume': row['volume']
            })
            last_close_price = row['close']
    
    # 创建新的DataFrame
    result_df = pd.DataFrame(filled_rows)
    
    # 确保数据类型正确
    result_df['date'] = pd.to_datetime(result_df['date'])
    result_df['open'] = pd.to_numeric(result_df['open'])
    result_df['close'] = pd.to_numeric(result_df['close'])
    result_df['high'] = pd.to_numeric(result_df['high'])
    result_df['low'] = pd.to_numeric(result_df['low'])
    result_df['volume'] = pd.to_numeric(result_df['volume'])
    
    return result_df

def check_and_fill_missing_non_trading_days(stock_code):
    """检查并补全指定股票缺失的非交易日占位蜡烛"""
    print(f"检查 {stock_code} 是否存在未占位的非交易日...")
    
    # 从数据库获取现有数据
    existing_data = get_stock_kline_from_db(stock_code)
    
    if existing_data.empty:
        print(f"{stock_code} 数据库中无数据，跳过检查")
        return
    
    # 获取日期范围
    start_date = existing_data['date'].min()
    end_date = existing_data['date'].max()
    
    # 创建完整的日期范围
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    existing_dates = set(existing_data['date'].dt.date)
    
    # 找出缺失的日期
    missing_dates = []
    for date in date_range:
        if date.date() not in existing_dates:
            missing_dates.append(date)
    
    if not missing_dates:
        print(f"{stock_code} 无缺失的非交易日，无需补全")
        return
    
    print(f"{stock_code} 发现 {len(missing_dates)} 个缺失的非交易日，开始补全...")
    
    # 填充缺失的非交易日
    filled_data = fill_non_trading_days(existing_data)
    
    # 保存补全后的数据到数据库
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 只保存新增的非交易日数据
        for date in missing_dates:
            # 找到该日期对应的数据
            date_data = filled_data[filled_data['date'].dt.date == date.date()]
            if not date_data.empty:
                row = date_data.iloc[0]
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
    print(f"已为 {stock_code} 补全 {len(missing_dates)} 个非交易日的占位蜡烛")

# --- Mock Event Data Generation (for testing) --- #
# 注释：模拟事件生成函数已移除，现在所有事件数据都从数据库获取

# --- 图表生成 --- #
def create_kline_chart(df_kline, stock_display_name, economic_events=None, custom_mock_events=None): # Added custom_mock_events
    """使用pyecharts生成K线图"""
    if df_kline.empty:
        return "<p>无法加载K线数据，请稍后再试或检查后台日志。</p>"

    dates = df_kline['date'].dt.strftime('%Y-%m-%d').tolist()
    # 数据格式: [open, close, low, high]
    k_values = df_kline[['open', 'close', 'low', 'high']].values.tolist()

    kline = (
        Kline()
        .add_xaxis(xaxis_data=dates)
        .add_yaxis(
            series_name=f"{stock_display_name} 日K",
            y_axis=k_values,
            itemstyle_opts=opts.ItemStyleOpts(
                color="#ec0000",  # 阳线颜色
                color0="#00da3c", # 阴线颜色
                border_color="#8A0000",
                border_color0="#008F28",
            ),
            # markpoint_opts=opts.MarkPointOpts(
            #     data=[
            #         opts.MarkPointItem(type_="max", name="最大值"),
            #         opts.MarkPointItem(type_="min", name="最小值"),
            #     ]
            # ),
            markline_opts=opts.MarkLineOpts(
                data=[
                    opts.MarkLineItem(type_="average", name="平均值")
                ]
            )
        )
        .set_global_opts(
            xaxis_opts=opts.AxisOpts(is_scale=True, axislabel_opts=opts.LabelOpts(rotate=30)),
            yaxis_opts=opts.AxisOpts(
                is_scale=True,
                splitarea_opts=opts.SplitAreaOpts(
                    is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                ),
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            datazoom_opts=[
                opts.DataZoomOpts(type_="inside", xaxis_index=[0], range_start=80, range_end=100),
                opts.DataZoomOpts(type_="slider", xaxis_index=[0], range_start=80, range_end=100, pos_bottom="0%"),
            ],
            title_opts=opts.TitleOpts(title=f"{stock_display_name} 日K线图", subtitle=f"数据截止: {dates[-1] if dates else 'N/A'}"),
        )
    )

    # 处理经济事件标记
    if economic_events and not df_kline.empty:
        event_mark_points_data = []
        for event in economic_events:
            event_date_str = event.get('date') # 格式应为 'YYYY-MM-DD'
            event_title = event.get('title', '经济事件')
            if event_date_str in dates: # 确保事件日期在K线图的日期范围内
                try:
                    idx = dates.index(event_date_str)
                    event_mark_points_data.append(
                        opts.MarkPointItem(
                            coord=[event_date_str, k_values[idx][3]], # [日期, 当日最高价]
                            name=event_title,
                            value=event_title, 
                            symbol='path://M8,0 L10.472,5.236 L16,6.18 L11.764,9.818 L13.056,15 L8,12.273 L2.944,15 L4.236,9.818 L0,6.18 L5.528,5.236 Z', 
                            symbol_size=15,
                            itemstyle_opts=opts.ItemStyleOpts(color='gold') 
                        )
                    )
                except (ValueError, IndexError) as e:
                    print(f"为事件 '{event_title}' 在日期 {event_date_str} 添加标记点时出错: {e}")
                    pass 
        
        # 将事件标记点添加到图表
        # 检查是否已有 'max'/'min' 标记点，并追加
        current_mark_point_opts = kline.options['series'][0].get('markPoint', opts.MarkPointOpts().opts)
        if 'data' not in current_mark_point_opts or not current_mark_point_opts['data']:
            current_mark_point_opts['data'] = [] # 初始化data列表
        current_mark_point_opts['data'].extend(event_mark_points_data)
        kline.options['series'][0]['markPoint'] = current_mark_point_opts

    # --- 处理自定义模拟事件标记 (黄星星) ---
    if custom_mock_events and not df_kline.empty:
        custom_event_mark_points_data = []
        # Group events by date for stacking
        events_by_date = {}
        for event in custom_mock_events:
            event_date_str = event.get('date') # 格式应为 'YYYY-MM-DD'
            if event_date_str not in events_by_date:
                events_by_date[event_date_str] = []
            events_by_date[event_date_str].append(event)

        for event_date_str, daily_events in events_by_date.items():
            if event_date_str in dates:
                try:
                    idx = dates.index(event_date_str)
                    candle_high = k_values[idx][3] # 当日最高价
                    # Define a base y-offset for the first star and increment for stacking
                    # The y-value in pyecharts for markPoint is the actual data value on the y-axis.
                    # We need to place the star above the candle's high.
                    # Let's calculate a small percentage of the price range or a fixed offset.
                    price_range = df_kline['high'].max() - df_kline['low'].min()
                    vertical_offset_increment = price_range * 0.01 # 1% of price range as offset, adjust as needed
                    if vertical_offset_increment == 0: # Handle flat lines or single data point
                        vertical_offset_increment = candle_high * 0.01 if candle_high > 0 else 0.1

                    for i, event in enumerate(daily_events):
                        event_title = event.get('title', '自定义事件')
                        # Stack stars vertically by increasing y-coordinate
                        star_y_coord = candle_high + (vertical_offset_increment * (i + 1))
                        # Create unique identifier for each event that matches template format
                        # Prioritize using actual event id if available, otherwise use composite format
                        if event.get('id'):
                            unique_event_id = str(event['id'])
                        else:
                            # Use the same format as in template: {date}_{position_in_date}_{title}
                            unique_event_id = f"{event_date_str}_{i}_{event_title}"

                        custom_event_mark_points_data.append(
                            opts.MarkPointItem(
                                name=unique_event_id,  # Use unique ID as name for precise matching
                                coord=[event_date_str, star_y_coord],
                                # value=event_title, # Value displayed on hover, REMOVED to hide text on chart
                                symbol='path://M8,0 L10.472,5.236 L16,6.18 L11.764,9.818 L13.056,15 L8,12.273 L2.944,15 L4.236,9.818 L0,6.18 L5.528,5.236 Z', # SVG path for a star
                                symbol_size=15,
                                itemstyle_opts=opts.ItemStyleOpts(color='gold') # Yellow star
                            )
                        )
                except (ValueError, IndexError) as e:
                    print(f"为自定义事件 '{event_title}' 在日期 {event_date_str} 添加标记点时出错: {e}")
                    pass

        # Add custom event mark points to the chart
        mark_point_opt = kline.options['series'][0].get('markPoint')

        if not mark_point_opt:
            # If 'markPoint' doesn't exist, create it as a dictionary with a data list
            kline.options['series'][0]['markPoint'] = {'data': custom_event_mark_points_data}
        elif isinstance(mark_point_opt, dict):
            # If 'markPoint' is already a dictionary
            if 'data' not in mark_point_opt or not mark_point_opt['data']:
                mark_point_opt['data'] = [] # Initialize data list if empty or not present
            mark_point_opt['data'].extend(custom_event_mark_points_data)
        elif hasattr(mark_point_opt, 'opts') and isinstance(mark_point_opt.opts, dict): 
            # If 'markPoint' is an object like MarkPointOpts, access its .opts dictionary
            if 'data' not in mark_point_opt.opts or not mark_point_opt.opts['data']:
                mark_point_opt.opts['data'] = [] # Initialize data list
            mark_point_opt.opts['data'].extend(custom_event_mark_points_data)
            # Ensure the main kline options are updated if we modified .opts of an object
            kline.options['series'][0]['markPoint'] = mark_point_opt.opts
        else:
            # Fallback or error handling if structure is unexpected
            print(f"Unexpected markPoint structure: {type(mark_point_opt)}. Could not add custom event markers.")
            # As a safe fallback, re-initialize if unsure
            kline.options['series'][0]['markPoint'] = {'data': custom_event_mark_points_data}

    return kline.render_embed()

# --- 数据分析函数 --- #
def get_data_statistics():
    """获取数据库统计信息（优先使用政策数据表）"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 首先尝试从新的政策数据表获取统计
        try:
            cursor.execute('SELECT COUNT(*) FROM policy_events')
            total_events = cursor.fetchone()[0]
            
            if total_events > 0:
                cursor.execute('SELECT COUNT(DISTINCT event_type) FROM policy_events')
                event_types_count = cursor.fetchone()[0]
                
                cursor.execute('SELECT MIN(date), MAX(date) FROM policy_events')
                date_range = cursor.fetchone()
                
                # 计算日期跨度
                date_range_days = 0
                latest_event_date = '无数据'
                if date_range[0] and date_range[1]:
                    from datetime import datetime
                    start_date = datetime.strptime(date_range[0], '%Y-%m-%d')
                    end_date = datetime.strptime(date_range[1], '%Y-%m-%d')
                    date_range_days = (end_date - start_date).days
                    latest_event_date = date_range[1]
                
                # 事件类型统计
                cursor.execute('SELECT event_type, COUNT(*) as count FROM policy_events GROUP BY event_type ORDER BY count DESC')
                type_stats_raw = cursor.fetchall()
                
                event_type_stats = []
                for event_type, count in type_stats_raw:
                    cursor.execute('SELECT MAX(date) FROM policy_events WHERE event_type = ?', (event_type,))
                    latest_date = cursor.fetchone()[0]
                    
                    type_display = {
                        'custom': '自定义',
                        'policy': '政策',
                        'economic': '经济'
                    }.get(event_type, event_type)
                    
                    event_type_stats.append({
                        'type': event_type,
                        'type_display': type_display,
                        'count': count,
                        'percentage': (count / total_events * 100) if total_events > 0 else 0,
                        'latest_date': latest_date or '无'
                    })
                
                # 数据质量分析
                cursor.execute('SELECT COUNT(DISTINCT date) FROM policy_events')
                unique_dates = cursor.fetchone()[0]
                
                cursor.execute('SELECT date, COUNT(*) as daily_count FROM policy_events GROUP BY date ORDER BY daily_count DESC LIMIT 1')
                max_events_result = cursor.fetchone()
                max_events_per_day = max_events_result[1] if max_events_result else 0
                
                # 计算月均事件数
                if date_range[0] and date_range[1]:
                    months_span = max(1, date_range_days / 30)
                    avg_events_per_month = round(total_events / months_span, 1)
                else:
                    avg_events_per_month = 0
                
                # 统计pa.industries为空的事件数量
                cursor.execute('''
                    SELECT COUNT(*) FROM policy_events pe 
                    LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id 
                    WHERE pa.industries IS NULL OR pa.industries = '' OR pa.industries = '[]'
                ''')
                empty_industries_count = cursor.fetchone()[0]
                
                data_quality = {
                    'completeness': 100 if total_events > 0 else 0,  # 简化的完整性指标
                    'avg_events_per_month': avg_events_per_month,
                    'unique_dates': unique_dates,
                    'max_events_per_day': max_events_per_day,
                    'empty_industries_count': empty_industries_count
                }
                
                return {
                    'total_events': total_events,
                    'event_types_count': event_types_count,
                    'date_range_days': date_range_days,
                    'latest_event_date': latest_event_date,
                    'event_type_stats': event_type_stats,
                    'data_quality': data_quality
                }
        except sqlite3.OperationalError:
            # 如果政策数据表不存在，回退到旧表
            pass
        
        # 回退到旧的events表统计
        cursor.execute('SELECT COUNT(*) FROM events')
        total_events = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT event_type) FROM events')
        event_types_count = cursor.fetchone()[0]
         
        cursor.execute('SELECT MIN(date), MAX(date) FROM events')
        date_range = cursor.fetchone()
        
        # 计算日期跨度
        date_range_days = 0
        latest_event_date = '无数据'
        if date_range[0] and date_range[1]:
            from datetime import datetime
            start_date = datetime.strptime(date_range[0], '%Y-%m-%d')
            end_date = datetime.strptime(date_range[1], '%Y-%m-%d')
            date_range_days = (end_date - start_date).days
            latest_event_date = date_range[1]
        
        # 事件类型统计
        cursor.execute('SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type ORDER BY count DESC')
        type_stats_raw = cursor.fetchall()
        
        event_type_stats = []
        for event_type, count in type_stats_raw:
            cursor.execute('SELECT MAX(date) FROM events WHERE event_type = ?', (event_type,))
            latest_date = cursor.fetchone()[0]
            
            type_display = {
                'custom': '自定义',
                'policy': '政策',
                'economic': '经济'
            }.get(event_type, event_type)
            
            event_type_stats.append({
                'type': event_type,
                'type_display': type_display,
                'count': count,
                'percentage': (count / total_events * 100) if total_events > 0 else 0,
                'latest_date': latest_date or '无'
            })
        
        # 数据质量分析
        cursor.execute('SELECT COUNT(DISTINCT date) FROM events')
        unique_dates = cursor.fetchone()[0]
        
        cursor.execute('SELECT date, COUNT(*) as daily_count FROM events GROUP BY date ORDER BY daily_count DESC LIMIT 1')
        max_events_result = cursor.fetchone()
        max_events_per_day = max_events_result[1] if max_events_result else 0
        
        # 计算月均事件数
        if date_range[0] and date_range[1]:
            months_span = max(1, date_range_days / 30)
            avg_events_per_month = round(total_events / months_span, 1)
        else:
            avg_events_per_month = 0
        
        data_quality = {
            'completeness': 100 if total_events > 0 else 0,  # 简化的完整性指标
            'avg_events_per_month': avg_events_per_month,
            'unique_dates': unique_dates,
            'max_events_per_day': max_events_per_day
        }
        
        return {
            'total_events': total_events,
            'event_types_count': event_types_count,
            'date_range_days': date_range_days,
            'latest_event_date': latest_event_date,
            'event_type_stats': event_type_stats,
            'data_quality': data_quality
        }

def get_smart_events_for_stock(stock_code: str):
    """智能获取股票相关的事件数据"""
    if not stock_industry_analyzer:
        # 如果股票行业分析器未初始化，返回全量数据
        print("股票行业分析器未初始化，返回全量政策数据")
        return get_events_from_db()
    
    # 大盘指数列表 - 这些指数默认显示所有政策数据
    major_indices = [
        '000001.SH',  # 上证指数
        '399001.SZ',  # 深证成指
        '399006.SZ'   # 创业板指数
    ]
    
    # 检查是否为大盘指数
    if stock_code in major_indices:
        print(f"检测到大盘指数 {stock_code}，返回全量政策数据")
        return get_events_from_db()
    
    # 检查股票类型并获取行业信息
    stock_type = stock_industry_analyzer.get_stock_type(stock_code)
    print(f"检测到股票类型: {stock_type}")
    
    # 对于ETF和指数，也使用AI分析获取行业信息
    if stock_type in ["ETF", "指数"]:
        try:
            # 获取或分析行业信息
            industry_info = stock_industry_analyzer.get_or_analyze_stock_industry(stock_code)
            
            if industry_info and industry_info.get('industries'):
                industries = industry_info['industries']
                print(f"{stock_type} {stock_code} 所属行业: {industries}")
                
                # 获取相关政策事件
                related_events = stock_industry_analyzer.get_related_policies(industries, limit=100)
                
                if related_events:
                    print(f"为{stock_type} {stock_code} 找到 {len(related_events)} 条相关政策")
                    return related_events
                else:
                    print(f"未找到{stock_type} {stock_code} 的相关政策，返回全量数据")
                    return get_events_from_db()
            else:
                print(f"无法获取{stock_type} {stock_code} 的行业信息，返回全量数据")
                return get_events_from_db()
        except Exception as e:
            print(f"分析{stock_type} {stock_code} 时发生错误: {e}，返回全量数据")
            return get_events_from_db()
    
    # 对于普通股票，也使用相同的AI分析流程
    try:
        # 获取或分析股票行业信息
        industry_info = stock_industry_analyzer.get_or_analyze_stock_industry(stock_code)
        
        if industry_info and industry_info.get('industries'):
            industries = industry_info['industries']
            print(f"股票 {stock_code} 所属行业: {industries}")
            
            # 获取相关政策事件
            related_events = stock_industry_analyzer.get_related_policies(industries, limit=100)
            
            if related_events:
                print(f"为股票 {stock_code} 找到 {len(related_events)} 条相关政策")
                return related_events
            else:
                print(f"未找到股票 {stock_code} 的相关政策，返回全量数据")
                return get_events_from_db()
        else:
            print(f"无法获取股票 {stock_code} 的行业信息，返回全量数据")
            return get_events_from_db()
            
    except Exception as e:
        print(f"智能事件筛选失败: {e}，返回全量数据")
        return get_events_from_db()

def get_events_with_details():
    """获取带有AI分析详情的事件数据（优先使用政策数据表）"""
    with get_db_connection(EVENTS_DB_FILE) as conn:
        cursor = conn.cursor()
        
        # 首先尝试从新的政策数据表获取
        try:
            cursor.execute("""
                SELECT pe.id, pe.date, pe.title, pe.event_type, pe.department, pe.policy_level, pe.impact_level, 
                       pe.source_url, pe.created_at, pe.content_type,
                       pa.industries, pa.analysis_summary, pa.confidence_score
                FROM policy_events pe
                LEFT JOIN policy_analysis pa ON pe.id = pa.policy_id
                ORDER BY pe.date DESC
            """)
            events = cursor.fetchall()
            
            if events:
                events_list = []
                for event in events:
                    # 解析AI分析结果的JSON数据
                    industries = json.loads(event[10]) if event[10] else []
                    
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
                        'ai_industries': industries,
                        'ai_summary': event[11] if event[11] else '',
                        'ai_confidence': event[12] if event[12] else None
                    })
                
                return events_list
        except sqlite3.OperationalError:
            # 如果政策数据表不存在，回退到旧表
            pass
        
        # 回退到旧的events表
        cursor.execute('SELECT date, title, event_type, created_at FROM events ORDER BY date DESC')
        rows = cursor.fetchall()
        
        events = []
        for row in rows:
            events.append({
                'date': row[0],
                'title': row[1],
                'event_type': row[2],
                'department': '',
                'policy_level': '',
                'impact_level': '',
                'source_url': '',
                'created_at': row[3],
                'ai_industries': [],
                'ai_sectors': [],
                'ai_stocks': [],
                'ai_summary': '',
                'ai_confidence': None
            })
        
        return events

# --- Flask 路由 --- #
@app.route('/data-viewer')
def data_viewer():
    """数据查看器页面"""
    stats = get_data_statistics()
    events = get_events_with_details()
    
    return render_template('data_viewer.html', 
                         total_events=stats['total_events'],
                         event_types_count=stats['event_types_count'],
                         date_range_days=stats['date_range_days'],
                         latest_event_date=stats['latest_event_date'],
                         event_type_stats=stats['event_type_stats'],
                         data_quality=stats['data_quality'],
                         events=events)

@app.route('/fetch-policy-data', methods=['POST'])
def fetch_policy_data():
    """手动触发政策数据获取"""
    try:
        fetcher = PolicyDataFetcher(EVENTS_DB_FILE)
        saved_count = fetcher.run_data_collection()
        
        return jsonify({
            'success': True,
            'message': f'成功获取并保存了 {saved_count} 条政策数据',
            'saved_count': saved_count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取政策数据时出错: {str(e)}'
        }), 500

@app.route('/api/policy-stats')
def get_policy_stats():
    """获取政策数据统计API"""
    try:
        statistics = get_data_statistics()
        return jsonify(statistics)
    except Exception as e:
        return jsonify({
            'error': f'获取统计数据时出错: {str(e)}'
        }), 500

@app.route('/ai-analysis', methods=['POST'])
def trigger_ai_analysis():
    """手动触发AI政策分析"""
    if not ai_analyzer:
        return jsonify({
            'success': False,
            'message': 'AI分析器未初始化，请检查API Key配置'
        }), 500
    
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 10)  # 默认分析10条
        use_async = data.get('async', False)  # 是否使用异步处理
        max_concurrent = data.get('max_concurrent', 5)  # 最大并发数
        
        if use_async:
            # 使用异步处理
            import asyncio
            processed_count = asyncio.run(
                ai_analyzer.analyze_unprocessed_policies_async(
                    limit=limit, 
                    max_concurrent=max_concurrent
                )
            )
        else:
            # 使用同步处理（保持向后兼容）
            processed_count = ai_analyzer.analyze_unprocessed_policies(limit=limit)
        
        return jsonify({
            'success': True,
            'message': f'成功分析了 {processed_count} 条政策（{"异步" if use_async else "同步"}模式）',
            'processed_count': processed_count,
            'mode': 'async' if use_async else 'sync'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'AI分析时出错: {str(e)}'
        }), 500

@app.route('/api/policy-analysis/<int:policy_id>')
def get_policy_analysis(policy_id):
    """获取指定政策的AI分析结果"""
    if not ai_analyzer:
        return jsonify({
            'error': 'AI分析器未初始化'
        }), 500
    
    try:
        analysis_result = ai_analyzer.get_analysis_result(policy_id)
        
        if analysis_result:
            return jsonify(analysis_result)
        else:
            return jsonify({
                'error': '未找到分析结果'
            }), 404
    except Exception as e:
        return jsonify({
            'error': f'获取分析结果时出错: {str(e)}'
        }), 500

# 删除重复的路由，使用新的股票行业分析功能

@app.route('/api/policies-by-stock/<stock_code>')
def get_policies_by_stock(stock_code):
    """根据股票代码获取相关政策"""
    if not ai_analyzer:
        return jsonify({
            'success': False,
            'message': 'AI分析器未初始化，请检查API Key配置'
        }), 500
    
    try:
        policies = ai_analyzer.get_policies_by_stock(stock_code)
        
        return jsonify({
            'success': True,
            'data': policies,
            'count': len(policies)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取相关政策时出错: {str(e)}'
        }), 500

@app.route('/api/stock-industry-analysis', methods=['POST'])
def analyze_stock_industry():
    """分析股票所属行业"""
    if not stock_industry_analyzer:
        return jsonify({
            'success': False,
            'message': '股票行业分析器未初始化，请检查API Key配置'
        }), 500
    
    try:
        data = request.get_json() or {}
        stock_code = data.get('stock_code')
        stock_name = data.get('stock_name', '')
        force_refresh = data.get('force_refresh', False)
        
        if not stock_code:
            return jsonify({
                'success': False,
                'message': '请提供股票代码'
            }), 400
        
        # 如果强制刷新，先删除现有数据
        if force_refresh:
            with get_db_connection(EVENTS_DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM stock_industry_mapping WHERE stock_code = ?', (stock_code,))
                conn.commit()
        
        # 获取或分析股票行业信息
        result = stock_industry_analyzer.get_or_analyze_stock_industry(stock_code, stock_name)
        
        if result:
            # 获取相关政策数量
            related_policies_count = len(stock_industry_analyzer.get_related_policies(result['industries'], limit=1000))
            result['related_policies_count'] = related_policies_count
            
            return jsonify({
                'success': True,
                'data': result,
                'message': f'成功分析股票 {stock_code} 的行业信息'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'分析股票 {stock_code} 的行业信息失败'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'分析股票行业时出错: {str(e)}'
        }), 500

@app.route('/api/stock-industry/<stock_code>')
def get_stock_industry(stock_code):
    """获取股票行业信息"""
    if not stock_industry_analyzer:
        return jsonify({
            'success': False,
            'message': '股票行业分析器未初始化'
        }), 500
    
    try:
        result = stock_industry_analyzer.get_stock_industries(stock_code)
        
        if result:
            # 获取相关政策数量
            related_policies_count = len(stock_industry_analyzer.get_related_policies(result['industries'], limit=1000))
            result['related_policies_count'] = related_policies_count
            
            return jsonify({
                'success': True,
                'data': result
            })
        else:
            return jsonify({
                'success': False,
                'message': f'未找到股票 {stock_code} 的行业信息'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'获取股票行业信息时出错: {str(e)}'
        }), 500

@app.route('/delete-event', methods=['POST'])
def delete_event():
    """删除事件数据"""
    try:
        data = request.get_json()
        event_title = data.get('title')
        
        if not event_title:
            return jsonify({
                'success': False,
                'message': '缺少事件标题参数'
            }), 400
        
        with get_db_connection(EVENTS_DB_FILE) as conn:
            cursor = conn.cursor()
            
            # 先检查policy_events表是否存在并尝试删除
            try:
                cursor.execute('SELECT COUNT(*) FROM policy_events WHERE title = ?', (event_title,))
                policy_count = cursor.fetchone()[0]
                if policy_count > 0:
                    cursor.execute('DELETE FROM policy_events WHERE title = ?', (event_title,))
                    deleted_count = cursor.rowcount
                else:
                    deleted_count = 0
            except sqlite3.OperationalError:
                # policy_events表不存在
                deleted_count = 0
            
            # 检查并删除events表中的数据
            cursor.execute('SELECT COUNT(*) FROM events WHERE title = ?', (event_title,))
            events_count = cursor.fetchone()[0]
            if events_count > 0:
                cursor.execute('DELETE FROM events WHERE title = ?', (event_title,))
                deleted_count += cursor.rowcount
            
            conn.commit()
        
        if deleted_count > 0:
            return jsonify({
                'success': True,
                'message': f'成功删除了 {deleted_count} 条相关数据'
            })
        else:
            return jsonify({
                'success': False,
                'message': '未找到匹配的事件数据'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'删除事件时出错: {str(e)}'
        }), 500

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        stock_input = request.form.get('stock_code')
        if stock_input:
            # 用户可能输入 600519, 600519.SH, 茅台等
            # 我们将原始输入传递给下一个路由，让它处理代码转换和显示
            return redirect(url_for('show_kline_chart', stock_code_input=stock_input.strip()))
        else:
            return render_template('kline.html', error_message="请输入股票代码或名称。", kline_chart_html="", events=[])
    return render_template('kline.html', kline_chart_html="", events=[]) # GET请求显示表单，不带图表

def get_stock_name(stock_code):
    """获取股票名称"""
    # 预定义的股票名称映射表（常见股票）
    stock_name_map = {
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
    
    # 首先尝试从预定义映射表获取
    if stock_code in stock_name_map:
        return stock_name_map[stock_code]
    
    # 尝试使用股票行业分析器获取详细信息
    try:
        if stock_industry_analyzer:
            detail_info = stock_industry_analyzer.get_stock_detail_info(stock_code)
            if detail_info and detail_info.get('stock_name'):
                return detail_info['stock_name']
    except Exception as e:
        print(f"从股票行业分析器获取名称失败: {e}")
    
    # 尝试TuShare API（如果Token有效）
    try:
        import tushare as ts
        pro = ts.pro_api(TUSHARE_TOKEN)
        
        # 处理股票代码格式
        if '.' in stock_code:
            ts_code = stock_code
        else:
            # 根据代码判断交易所
            if stock_code.startswith(('60', '68')):
                ts_code = f"{stock_code}.SH"
            elif stock_code.startswith(('00', '30')):
                ts_code = f"{stock_code}.SZ"
            else:
                ts_code = f"{stock_code}.SH"  # 默认上海
        
        # 获取股票基本信息
        df = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
        if not df.empty:
            return df.iloc[0]['name']
        
        # 如果没找到，尝试ETF
        df_etf = pro.fund_basic(ts_code=ts_code, fields='ts_code,name')
        if not df_etf.empty:
            return df_etf.iloc[0]['name']
            
    except Exception as e:
        print(f"TuShare获取股票名称失败: {e}")
    
    return None

@app.route('/kline/<stock_code_input>')
def show_kline_chart(stock_code_input):
    # 获取K线数据的日期范围，以便获取对应范围的经济事件
    # 假设K线数据从 '2019-08-18' 开始，到今天
    date_from_str = '2019-08-18' # 与 fetch_stock_kline_data 中的一致或动态获取
    date_to_str = datetime.now().strftime('%Y-%m-%d')

    stock_code_for_tushare = stock_code_input.split('.')[0]
    stock_display_name = stock_code_input.upper()

    if TUSHARE_TOKEN == 'YOUR_TUSHARE_TOKEN' or not TUSHARE_TOKEN:
        kline_html = "<p>错误：TuShare Token 未配置。请在 app.py 中或通过环境变量设置 TUSHARE_TOKEN。</p>"
        return render_template('kline.html', kline_chart_html=kline_html, stock_code=stock_code_input, error_message="TuShare Token 未配置", current_year=datetime.now().year)

    # 获取股票名称
    stock_name = get_stock_name(stock_code_input)
    print(f"获取到的股票名称: {stock_name} (股票代码: {stock_code_input})")
    
    # 如果获取不到股票名称，设置默认值
    if not stock_name:
        stock_name = f"股票代码: {stock_code_input}"
    
    # 智能获取相关事件数据
    db_events = get_smart_events_for_stock(stock_code_input)

    df_stock = fetch_stock_kline_data(stock_code_for_tushare)
    kline_html = ""

    if not df_stock.empty:
        kline_html = create_kline_chart(df_stock, stock_display_name, economic_events=None, custom_mock_events=db_events) # 使用智能筛选的事件数据
    else:
        kline_html = f"<p>获取 {stock_display_name} ({stock_code_for_tushare}) 股票数据失败。原因可能：<br>1. 股票代码无效或TuShare不支持。<br>2. TuShare Token无效或已过期。<br>3. 网络连接问题。<br>4. TuShare接口当日调用次数已达上限。</p>"

    # 按日期倒序排列事件列表
    if db_events:
        db_events.sort(key=lambda x: x.get('date'), reverse=True)
    return render_template('kline.html', kline_chart_html=kline_html, current_stock_code=stock_code_input, stock_name=stock_name, current_year=datetime.now().year, events=db_events)

# --- 注册事件管理路由 --- #
register_event_routes(app)

# --- 主程序入口 --- #
if __name__ == '__main__':
    # 初始化数据库
    init_events_database()
    
    # 获取端口配置
    port = int(os.environ.get('FLASK_PORT', 8080))
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    
    # 启动应用
    app.run(host=host, port=port, debug=False)