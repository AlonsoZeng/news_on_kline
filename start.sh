#!/bin/bash

# 启动脚本
echo "正在启动股票分析应用..."

# 检查环境变量
if [ -z "$TUSHARE_TOKEN" ]; then
    echo "警告: TUSHARE_TOKEN 环境变量未设置"
fi

if [ -z "$SILICONFLOW_API_KEY" ]; then
    echo "警告: SILICONFLOW_API_KEY 环境变量未设置"
fi

# 创建必要目录
mkdir -p data logs

# 启动应用
echo "启动Flask应用..."
python app.py