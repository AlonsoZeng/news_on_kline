# 茅台K线应用项目结构说明

## 目录结构

```
news_on_kline/
├── app.py                    # 主应用程序（Flask Web服务）
├── requirements.txt          # 项目依赖
├── .env                      # 环境变量配置
├── .env.example              # 环境变量配置示例
├── README.md                 # 项目说明文档
├── data/                     # 数据存储目录
│   ├── events.db             # 事件数据库
│   ├── policy_data.db        # 政策数据库
│   └── stock_updates.json    # 股票更新记录
├── src/                      # 源代码目录
│   ├── core/                 # 核心业务模块
│   │   ├── ai_policy_analyzer.py      # AI政策分析器
│   │   ├── event_manager.py           # 事件管理器
│   │   ├── policy_data_fetcher.py     # 政策数据抓取器
│   │   └── stock_industry_analyzer.py # 股票行业分析器
│   ├── data/                 # 数据处理模块
│   │   ├── daily_policy_update.py     # 每日政策更新
│   │   ├── fetch_latest_policies.py   # 最新政策抓取
│   │   └── init_db.py                 # 数据库初始化
│   └── utils/                # 工具模块
│       └── config.py                  # 配置管理
├── templates/                # HTML模板文件
│   ├── kline.html            # K线图页面
│   └── data_viewer.html      # 数据查看页面
├── static/                   # 静态文件
│   └── images/               # 图片资源
├── scripts/                  # 脚本目录
│   ├── batch_fix_dates.py    # 批量日期修正
│   └── fetch_june_2025_data.py # 特定数据抓取
└── docs/                     # 文档目录
    ├── 政策数据抓取使用说明.md
    └── 日期修正工具使用说明.md
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