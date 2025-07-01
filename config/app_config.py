"""应用配置管理模块"""
import os


class AppConfig:
    """应用配置管理类"""
    
    def __init__(self):
        self.TUSHARE_TOKEN = self._get_tushare_token()
        self.DB_FILE = 'data/stock_updates.json'
        self.EVENTS_DB_FILE = 'data/events.db'
        self.EODHD_API_TOKEN = self._get_eodhd_token()
        self.SILICONFLOW_API_KEY = self._get_siliconflow_key()
        
    def _get_tushare_token(self):
        """获取TuShare Token"""
        token = os.getenv('TUSHARE_TOKEN')
        if token == 'YOUR_TUSHARE_TOKEN' or not token:
            print("警告：请设置您的TuShare Token (环境变量 TUSHARE_TOKEN)，否则无法获取数据。")
        return token
    
    def _get_eodhd_token(self):
        """获取EODHD API Token"""
        token = os.getenv('EODHD_API_TOKEN', 'demo')
        if token == 'YOUR_EODHD_API_TOKEN' or not token:
            print("警告：请设置您的EODHD API Token (环境变量 EODHD_API_TOKEN)，否则可能无法获取宏观事件数据。")
        return token
    
    def _get_siliconflow_key(self):
        """获取硅基流动 AI API Key"""
        from src.utils.config import init_config, Config
        
        config_initialized = init_config()
        if config_initialized:
            try:
                return Config.get_api_key()
            except ValueError:
                print("警告：硅基流动 API Key 未正确配置，AI政策分析功能将不可用。")
                print("请设置 SILICONFLOW_API_KEY 环境变量或创建 .env 文件。")
        else:
            print("警告：配置初始化失败，AI分析功能将不可用。")
        return None