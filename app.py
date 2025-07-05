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
# 删除第27行的重复导入
# # 将注释掉的导入语句修改为正确的路径
from src.utils.stock_info import init_stock_info_helper, get_stock_name

# 导入新的数据库操作模块
from src.database.db_operations import (
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

# 导入图表生成模块
# 更简洁的导入方式
from src.charts import (
    create_kline_chart,
    fill_non_trading_days,
    check_and_fill_missing_non_trading_days
)

# 导入数据统计分析模块
from src.analytics import get_data_statistics, get_events_with_details

# --- 配置管理 --- #
# AppConfig类已移至config/app_config.py模块

# --- 配置初始化 --- #
config = AppConfig()
TUSHARE_TOKEN = config.TUSHARE_TOKEN
DB_FILE = config.DB_FILE
EVENTS_DB_FILE = config.EVENTS_DB_FILE
SILICONFLOW_API_KEY = config.SILICONFLOW_API_KEY

# --- Flask 应用初始化 --- #
# 在 Flask 应用初始化后添加 AI 分析器初始化
app = Flask(__name__)
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 初始化AI政策分析器和股票行业分析器
ai_analyzer = None
stock_industry_analyzer = None

if SILICONFLOW_API_KEY and SILICONFLOW_API_KEY != 'your_api_key_here':
    try:
        ai_analyzer = AIPolicyAnalyzer(SILICONFLOW_API_KEY, EVENTS_DB_FILE)
        stock_industry_analyzer = StockIndustryAnalyzer(SILICONFLOW_API_KEY, EVENTS_DB_FILE)
        print("AI分析器初始化成功")
        
        # 初始化股票信息辅助模块
        init_stock_info_helper(TUSHARE_TOKEN, stock_industry_analyzer)
        print("股票信息辅助模块初始化成功")
    except Exception as e:
        print(f"AI分析器初始化失败: {e}")
else:
    print("SILICONFLOW_API_KEY 未配置，AI分析功能将不可用")

# --- 数据库初始化 --- #
# 使用新模块的函数进行初始化
init_events_database(EVENTS_DB_FILE)

# --- 数据获取与处理 --- #


def fetch_stock_kline_data(stock_code_tushare):
    """获取股票K线数据，优先从数据库读取，必要时从TuShare API获取"""
    today = datetime.now().date()
    start_date = '2019-08-18'  # 数据起始日期
    
    print(f"开始获取 {stock_code_tushare} 的K线数据...")
    
    # 1. 首先从数据库获取现有数据
    db_data = get_stock_kline_from_db(stock_code_tushare, EVENTS_DB_FILE, start_date)
    
    # 2. 检查是否需要从API获取新数据
    need_api_fetch = False
    api_start_date = start_date
    
    if db_data.empty:
        print(f"数据库中没有 {stock_code_tushare} 的数据，需要从API获取全部数据")
        need_api_fetch = True
    else:
        # 获取数据库中最新的日期
        latest_date_str = get_latest_stock_date_from_db(stock_code_tushare, EVENTS_DB_FILE)
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
                save_stock_kline_to_db(stock_code_tushare, df_api_processed, EVENTS_DB_FILE, include_non_trading_days=True)
                
                # 更新最后获取时间记录
                set_last_update_date(stock_code_tushare, today, DB_FILE)
                
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
    check_and_fill_missing_non_trading_days(stock_code_tushare, EVENTS_DB_FILE)
    
    # 5. 重新从数据库获取完整数据（包含补全的非交易日）
    final_data = get_stock_kline_from_db(stock_code_tushare, EVENTS_DB_FILE, start_date)
    
    # 6. 填充非交易日的占位蜡烛（确保最新数据也包含非交易日）
    if not final_data.empty:
        final_data = fill_non_trading_days(final_data)
        print(f"填充非交易日后，总计 {len(final_data)} 条数据")
    
    return final_data


# 保留 get_smart_events_for_stock 函数（第364-439行）
def get_smart_events_for_stock(stock_code: str):
    """智能获取股票相关的事件数据"""
    if not stock_industry_analyzer:
        # 如果股票行业分析器未初始化，返回全量数据
        print("股票行业分析器未初始化，返回全量政策数据")
        return get_events_from_db(EVENTS_DB_FILE)
    
    # 大盘指数列表 - 这些指数默认显示所有政策数据
    major_indices = [
        '000001.SH',  # 上证指数
        '399001.SZ',  # 深证成指
        '399006.SZ'   # 创业板指数
    ]
    
    # 检查是否为大盘指数
    if stock_code in major_indices:
        print(f"检测到大盘指数 {stock_code}，返回全量政策数据")
        return get_events_from_db(EVENTS_DB_FILE)
    
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
                    return get_events_from_db(EVENTS_DB_FILE)
            else:
                print(f"无法获取{stock_type} {stock_code} 的行业信息，返回全量数据")
                return get_events_from_db(EVENTS_DB_FILE)
        except Exception as e:
            print(f"分析{stock_type} {stock_code} 时发生错误: {e}，返回全量数据")
            return get_events_from_db(EVENTS_DB_FILE)
    
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
                return get_events_from_db(EVENTS_DB_FILE)
        else:
            print(f"无法获取股票 {stock_code} 的行业信息，返回全量数据")
            return get_events_from_db(EVENTS_DB_FILE)
            
    except Exception as e:
        print(f"智能事件筛选失败: {e}，返回全量数据")
        return get_events_from_db(EVENTS_DB_FILE)



# 保留 get_smart_events_for_stock 函数（第200-276行）
def get_smart_events_for_stock(stock_code: str):
    """智能获取股票相关的事件数据"""
    if not stock_industry_analyzer:
        # 如果股票行业分析器未初始化，返回全量数据
        print("股票行业分析器未初始化，返回全量政策数据")
        return get_events_from_db(EVENTS_DB_FILE)
    
    # 大盘指数列表 - 这些指数默认显示所有政策数据
    major_indices = [
        '000001.SH',  # 上证指数
        '399001.SZ',  # 深证成指
        '399006.SZ'   # 创业板指数
    ]
    
    # 检查是否为大盘指数
    if stock_code in major_indices:
        print(f"检测到大盘指数 {stock_code}，返回全量政策数据")
        return get_events_from_db(EVENTS_DB_FILE)
    
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
                    return get_events_from_db(EVENTS_DB_FILE)
            else:
                print(f"无法获取{stock_type} {stock_code} 的行业信息，返回全量数据")
                return get_events_from_db(EVENTS_DB_FILE)
        except Exception as e:
            print(f"分析{stock_type} {stock_code} 时发生错误: {e}，返回全量数据")
            return get_events_from_db(EVENTS_DB_FILE)
    
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
                return get_events_from_db(EVENTS_DB_FILE)
        else:
            print(f"无法获取股票 {stock_code} 的行业信息，返回全量数据")
            return get_events_from_db(EVENTS_DB_FILE)
            
    except Exception as e:
        print(f"智能事件筛选失败: {e}，返回全量数据")
        return get_events_from_db(EVENTS_DB_FILE)



# --- Flask 路由 --- #
@app.route('/data-viewer')
def data_viewer():
    # 现在将正确使用从 analytics 模块导入的函数
    stats = get_data_statistics(EVENTS_DB_FILE)
    events = get_events_with_details(EVENTS_DB_FILE)  # 这里会调用正确的函数
    
    return render_template('data_viewer.html', 
                         total_events=stats['total_events'],
                         event_types_count=stats['event_types_count'],
                         date_range_days=stats['date_range_days'],
                         latest_event_date=stats['latest_event_date'],
                         event_type_stats=stats['event_type_stats'],
                         data_quality=stats['data_quality'],
                         events=events)

# 保留第374-382行的路由定义
@app.route('/api/policy-stats')
def get_policy_stats():
    try:
        statistics = get_data_statistics(EVENTS_DB_FILE)
        return jsonify(statistics)
    except Exception as e:
        return jsonify({
            'error': f'获取统计数据时出错: {str(e)}'
        }), 500

# 删除第402-410行的重复定义：
# @app.route('/api/policy-stats')
# def get_policy_stats():
#     # 修复：使用导入的函数并传入参数
#     try:
#         statistics = get_data_statistics(EVENTS_DB_FILE)
#         return jsonify(statistics)
#     except Exception as e:
#         return jsonify({
#             'error': f'获取统计数据时出错: {str(e)}'
#         }), 500

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

@app.route('/api/events')
def get_events_api():
    """获取事件数据API - 支持按股票代码筛选"""
    try:
        stock_code = request.args.get('stock_code')
        
        if stock_code:
            # 如果提供了股票代码，使用智能筛选
            events = get_smart_events_for_stock(stock_code)
            print(f"为股票 {stock_code} 获取到 {len(events) if events else 0} 条事件")
        else:
            # 如果没有提供股票代码，返回全量数据
            events = get_events_from_db(EVENTS_DB_FILE)
            print(f"获取全量事件数据，共 {len(events) if events else 0} 条")
        
        # 按日期倒序排列
        if events:
            events.sort(key=lambda x: x.get('date', ''), reverse=True)
        
        return jsonify({
            'success': True,
            'events': events or [],
            'count': len(events) if events else 0,
            'stock_code': stock_code
        })
        
    except Exception as e:
        print(f"获取事件数据时出错: {e}")
        return jsonify({
            'success': False,
            'message': f'获取事件数据时出错: {str(e)}',
            'events': [],
            'count': 0
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
    init_events_database(EVENTS_DB_FILE)
    
    # 获取端口配置
    port = int(os.environ.get('FLASK_PORT', 8080))
    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    
    # 启动应用
    app.run(host=host, port=port, debug=False)