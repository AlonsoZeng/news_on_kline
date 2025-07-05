"""数据统计分析功能模块

提供数据库统计信息和事件数据查询功能
"""

import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager


@contextmanager
def get_db_connection(db_file):
    """数据库连接上下文管理器
    
    Args:
        db_file (str): 数据库文件路径
        
    Yields:
        sqlite3.Connection: 数据库连接对象
    """
    conn = sqlite3.connect(db_file)
    try:
        yield conn
    finally:
        conn.close()


def get_data_statistics(events_db_file):
    """获取数据库统计信息（优先使用政策数据表）
    
    Args:
        events_db_file (str): 事件数据库文件路径
        
    Returns:
        dict: 包含统计信息的字典
    """
    with get_db_connection(events_db_file) as conn:
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
                        'economic': '经济',
                        'regulation': '法规',
                        'notice': '通知',
                        'announcement': '公告'
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


def get_events_with_details(events_db_file):
    """获取带有AI分析详情的事件数据（优先使用政策数据表）
    
    Args:
        events_db_file (str): 事件数据库文件路径
        
    Returns:
        list: 包含事件详情的列表
    """
    with get_db_connection(events_db_file) as conn:
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