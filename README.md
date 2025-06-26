# 茅台K线应用项目结构说明

## 目录结构

```
maotai_kline_app/
├── app.py                    # 主应用程序（Flask Web服务）
├── policy_data_fetcher.py    # 政策数据抓取核心模块
├── daily_policy_update.py    # 每日政策更新脚本
├── fetch_latest_policies.py  # 最新政策抓取脚本
├── requirements.txt          # 项目依赖
├── setup_daily_task.bat     # Windows定时任务设置
├── events.db                # SQLite数据库文件
├── stock_updates.json       # 股票更新记录
├── templates/               # HTML模板文件
│   ├── kline.html
│   └── data_viewer.html
├── static/                  # 静态文件
├── tests/                   # 测试代码目录
│   ├── test_fetch.py        # 股票数据获取测试
│   ├── test_cache.py        # 数据库缓存测试
│   ├── test_cache_logic.py  # 缓存逻辑测试
│   └── test_content_filter.py # 内容过滤测试
├── tools/                   # 工具脚本目录
│   ├── check_db.py          # 数据库检查工具
│   ├── check_date_format.py # 日期格式检查工具
│   ├── clean_mock_data.py   # 清理模拟数据工具
│   └── fix_policy_dates.py  # 政策日期修正工具
└── scripts/                 # 一次性执行脚本目录
    ├── batch_fix_dates.py   # 批量日期修正脚本
    └── fetch_june_2025_data.py # 特定月份数据抓取脚本
```

## 使用说明

### 运行主应用
```bash
python app.py
```

### 运行测试
```bash
# 测试股票数据获取
python tests/test_fetch.py

# 测试数据库缓存
python tests/test_cache.py

# 测试缓存逻辑
python tests/test_cache_logic.py

# 测试内容过滤
python tests/test_content_filter.py
```

### 使用工具
```bash
# 检查数据库
python tools/check_db.py

# 检查日期格式
python tools/check_date_format.py

# 清理模拟数据
python tools/clean_mock_data.py
```

### 执行脚本
```bash
# 批量修正日期
python scripts/batch_fix_dates.py

# 抓取特定月份数据
python scripts/fetch_june_2025_data.py
```

## 目录说明

- **根目录**: 包含主要的生产代码和配置文件
- **tests/**: 所有测试相关的代码，用于验证功能正确性
- **tools/**: 开发和维护工具，用于数据库检查、数据清理等
- **scripts/**: 一次性执行的脚本，通常用于数据迁移、批量处理等任务
- **templates/**: HTML模板文件
- **static/**: 静态资源文件

## 注意事项

1. 测试代码和工具代码已从主目录分离，保持代码结构清晰
2. 所有移动的文件已更新导入路径，确保正常运行
3. 主应用程序保持在根目录，便于部署和运行
4. 各目录都有对应的 `__init__.py` 文件，支持作为Python包导入