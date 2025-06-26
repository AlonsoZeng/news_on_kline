# -*- coding: utf-8 -*-
"""
事件管理模块
提供事件的单个创建、批量导入、删除等功能
"""

import sqlite3
import csv
import io
import json
from datetime import datetime
from flask import jsonify, request
from werkzeug.utils import secure_filename
import os

class EventManager:
    def __init__(self, db_path='events.db'):
        self.db_path = db_path
    
    def get_db_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_single_event(self, event_data):
        """创建单个事件"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # 插入到policy_events表
            cursor.execute("""
                INSERT INTO policy_events (
                    date, title, content_type, event_type, department, 
                    policy_level, impact_level, industries, content, 
                    ai_analysis, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_data['date'],
                event_data['title'],
                event_data.get('content_type', ''),
                event_data.get('event_type', ''),
                event_data.get('department', ''),
                event_data.get('policy_level', ''),
                event_data.get('impact_level', ''),
                event_data.get('industries', ''),
                event_data.get('content', ''),
                event_data.get('ai_analysis', ''),
                event_data.get('source_url', ''),
                datetime.now().isoformat()
            ))
            
            # 插入到events表（用于K线图显示）
            cursor.execute("""
                INSERT INTO events (date, title, event_type, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                event_data['date'],
                event_data['title'],
                event_data.get('event_type', ''),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': '事件创建成功'}
            
        except Exception as e:
            return {'success': False, 'message': f'创建事件失败: {str(e)}'}
    
    def import_events_from_csv(self, csv_content):
        """从CSV内容批量导入事件"""
        try:
            # 解析CSV内容
            csv_reader = csv.DictReader(io.StringIO(csv_content))
            
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            success_count = 0
            error_count = 0
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):  # 从第2行开始（第1行是标题）
                try:
                    # 验证必填字段
                    if not row.get('date') or not row.get('title'):
                        errors.append(f'第{row_num}行: 日期和标题为必填字段')
                        error_count += 1
                        continue
                    
                    # 插入到policy_events表
                    cursor.execute("""
                        INSERT INTO policy_events (
                            date, title, content_type, event_type, department, 
                            policy_level, impact_level, industries, content, 
                            ai_analysis, source_url, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        row['date'],
                        row['title'],
                        row.get('content_type', ''),
                        row.get('event_type', ''),
                        row.get('department', ''),
                        row.get('policy_level', ''),
                        row.get('impact_level', ''),
                        row.get('industries', ''),
                        row.get('content', ''),
                        row.get('ai_analysis', ''),
                        row.get('source_url', ''),
                        datetime.now().isoformat()
                    ))
                    
                    # 插入到events表
                    cursor.execute("""
                        INSERT INTO events (date, title, event_type, created_at)
                        VALUES (?, ?, ?, ?)
                    """, (
                        row['date'],
                        row['title'],
                        row.get('event_type', ''),
                        datetime.now().isoformat()
                    ))
                    
                    success_count += 1
                    
                except Exception as e:
                    errors.append(f'第{row_num}行: {str(e)}')
                    error_count += 1
            
            conn.commit()
            conn.close()
            
            return {
                'success': True,
                'message': f'导入完成: 成功{success_count}条，失败{error_count}条',
                'success_count': success_count,
                'error_count': error_count,
                'errors': errors
            }
            
        except Exception as e:
            return {'success': False, 'message': f'导入失败: {str(e)}'}
    
    def delete_event(self, event_id):
        """删除事件"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            # 从policy_events表删除
            cursor.execute("DELETE FROM policy_events WHERE id = ?", (event_id,))
            
            # 从events表删除（通过标题匹配）
            cursor.execute("""
                DELETE FROM events WHERE title IN (
                    SELECT title FROM policy_events WHERE id = ?
                )
            """, (event_id,))
            
            conn.commit()
            conn.close()
            
            return {'success': True, 'message': '事件删除成功'}
            
        except Exception as e:
            return {'success': False, 'message': f'删除事件失败: {str(e)}'}
    
    def get_csv_template(self):
        """获取CSV导入模板"""
        template_headers = [
            'date',           # 日期 (必填, 格式: YYYY-MM-DD)
            'title',          # 标题 (必填)
            'source_url',     # 原文链接 (可选)
            'content_type',   # 内容类型
            'event_type',     # 事件类型
            'department',     # 发布部门
            'policy_level',   # 政策级别
            'impact_level',   # 影响级别
            'industries',     # 相关行业 (多个行业用逗号分隔)
            'content',        # 内容
            'ai_analysis'     # AI分析
        ]
        
        # 创建示例数据
        example_data = [
            {
                'date': '2024-01-15',
                'title': '示例政策事件',
                'source_url': 'https://example.com/policy-document',
                'content_type': '政策文件',
                'event_type': '货币政策',
                'department': '央行',
                'policy_level': '国家级',
                'impact_level': '重大',
                'industries': '银行,保险',
                'content': '这是一个示例政策内容',
                'ai_analysis': '这是AI分析结果'
            }
        ]
        
        # 生成CSV内容
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=template_headers)
        writer.writeheader()
        writer.writerows(example_data)
        
        return output.getvalue()

# 创建全局实例
event_manager = EventManager()

def register_event_routes(app):
    """注册事件管理相关的路由"""
    
    @app.route('/api/create-event', methods=['POST'])
    def create_event():
        """创建单个事件API"""
        try:
            event_data = request.get_json()
            result = event_manager.create_single_event(event_data)
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'message': f'请求处理失败: {str(e)}'}), 500
    
    @app.route('/api/import-events', methods=['POST'])
    def import_events():
        """批量导入事件API"""
        try:
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': '未找到上传文件'}), 400
            
            file = request.files['file']
            if file.filename == '':
                return jsonify({'success': False, 'message': '未选择文件'}), 400
            
            if not file.filename.lower().endswith('.csv'):
                return jsonify({'success': False, 'message': '只支持CSV文件'}), 400
            
            # 读取文件内容
            csv_content = file.read().decode('utf-8-sig')  # 支持带BOM的UTF-8
            
            result = event_manager.import_events_from_csv(csv_content)
            return jsonify(result)
            
        except Exception as e:
            return jsonify({'success': False, 'message': f'导入失败: {str(e)}'}), 500
    
    @app.route('/api/delete-event/<int:event_id>', methods=['DELETE'])
    def delete_event_api(event_id):
        """删除事件API"""
        try:
            result = event_manager.delete_event(event_id)
            return jsonify(result)
        except Exception as e:
            return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500
    
    @app.route('/api/download-template')
    def download_template():
        """下载CSV模板"""
        try:
            template_content = event_manager.get_csv_template()
            
            from flask import Response
            return Response(
                template_content,
                mimetype='text/csv',
                headers={
                    'Content-Disposition': 'attachment; filename=event_import_template.csv',
                    'Content-Type': 'text/csv; charset=utf-8'
                }
            )
        except Exception as e:
            return jsonify({'success': False, 'message': f'模板下载失败: {str(e)}'}), 500