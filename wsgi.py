#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PythonAnywhere WSGI 配置文件
"""

import sys
import os
from pathlib import Path

# 添加项目路径到 Python 路径
project_home = '/home/zencold/news_on_kline'  # 替换为你的用户名
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 设置环境变量
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_DEBUG'] = 'False'

# 导入 Flask 应用
from app import app as application

if __name__ == "__main__":
    application.run()