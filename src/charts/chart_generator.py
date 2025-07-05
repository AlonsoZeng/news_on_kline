"""
图表生成模块
负责K线图的生成和相关数据处理功能
"""

import pandas as pd
from pyecharts.charts import Kline
from pyecharts import options as opts
from src.database.db_operations import get_db_connection, get_stock_kline_from_db


def create_kline_chart(df_kline, stock_display_name, economic_events=None, custom_mock_events=None):
    """
    使用pyecharts生成K线图
    
    Args:
        df_kline: K线数据DataFrame
        stock_display_name: 股票显示名称
        economic_events: 经济事件列表
        custom_mock_events: 自定义事件列表
    
    Returns:
        str: 渲染后的HTML图表代码
    """
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
        current_mark_point_opts = kline.options['series'][0].get('markPoint', opts.MarkPointOpts().opts)
        if 'data' not in current_mark_point_opts or not current_mark_point_opts['data']:
            current_mark_point_opts['data'] = [] # 初始化data列表
        current_mark_point_opts['data'].extend(event_mark_points_data)
        kline.options['series'][0]['markPoint'] = current_mark_point_opts

    # 处理自定义模拟事件标记 (黄星星)
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
                    price_range = df_kline['high'].max() - df_kline['low'].min()
                    vertical_offset_increment = price_range * 0.01 # 1% of price range as offset
                    if vertical_offset_increment == 0: # Handle flat lines or single data point
                        vertical_offset_increment = candle_high * 0.01 if candle_high > 0 else 0.1

                    for i, event in enumerate(daily_events):
                        event_title = event.get('title', '自定义事件')
                        # Stack stars vertically by increasing y-coordinate
                        star_y_coord = candle_high + (vertical_offset_increment * (i + 1))
                        # Create unique identifier for each event
                        if event.get('id'):
                            unique_event_id = str(event['id'])
                        else:
                            unique_event_id = f"{event_date_str}_{i}_{event_title}"

                        custom_event_mark_points_data.append(
                            opts.MarkPointItem(
                                name=unique_event_id,  # Use unique ID as name for precise matching
                                coord=[event_date_str, star_y_coord],
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
            kline.options['series'][0]['markPoint'] = {'data': custom_event_mark_points_data}
        elif isinstance(mark_point_opt, dict):
            if 'data' not in mark_point_opt or not mark_point_opt['data']:
                mark_point_opt['data'] = []
            mark_point_opt['data'].extend(custom_event_mark_points_data)
        elif hasattr(mark_point_opt, 'opts') and isinstance(mark_point_opt.opts, dict): 
            if 'data' not in mark_point_opt.opts or not mark_point_opt.opts['data']:
                mark_point_opt.opts['data'] = []
            mark_point_opt.opts['data'].extend(custom_event_mark_points_data)
            kline.options['series'][0]['markPoint'] = mark_point_opt.opts
        else:
            print(f"Unexpected markPoint structure: {type(mark_point_opt)}. Could not add custom event markers.")
            kline.options['series'][0]['markPoint'] = {'data': custom_event_mark_points_data}

    return kline.render_embed()


def fill_non_trading_days(df_kline):
    """
    为非交易日填充占位蜡烛，使用上一个交易日的收盘价作为开高低收价格
    
    Args:
        df_kline: K线数据DataFrame
    
    Returns:
        pd.DataFrame: 填充后的K线数据
    """
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


def check_and_fill_missing_non_trading_days(stock_code, events_db_file):
    """
    检查并补全指定股票缺失的非交易日占位蜡烛
    
    Args:
        stock_code: 股票代码
        events_db_file: 事件数据库文件路径
    """
    print(f"检查 {stock_code} 是否存在未占位的非交易日...")
    
    # 从数据库获取现有数据
    existing_data = get_stock_kline_from_db(stock_code, events_db_file)
    
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
    with get_db_connection(events_db_file) as conn:
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