"""应用配置管理模块"""
import os


class AppConfig:
    """应用配置管理类"""
    
    def __init__(self):
        # 先加载.env文件
        self._load_env_file()
        
        self.TUSHARE_TOKEN = self._get_tushare_token()
        self.DB_FILE = 'data/stock_updates.json'
        self.EVENTS_DB_FILE = 'data/events.db'
        # self.EODHD_API_TOKEN = self._get_eodhd_token()
        self.SILICONFLOW_API_KEY = self._get_siliconflow_key()
    
    def _load_env_file(self):
        """加载.env文件到环境变量"""
        try:
            # 获取项目根目录（当前文件的上级目录）
            project_root = os.path.dirname(os.path.dirname(__file__))
            env_file = os.path.join(project_root, '.env')
            
            if os.path.exists(env_file):
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            # 只有当环境变量不存在时才设置（避免覆盖系统环境变量）
                            if key.strip() not in os.environ:
                                os.environ[key.strip()] = value.strip()
                print(f"已加载配置文件: {env_file}")
            else:
                print(f"警告：未找到.env文件: {env_file}")
        except Exception as e:
            print(f"加载.env文件时出错: {e}")
        
    def _get_tushare_token(self):
        """获取TuShare Token"""
        token = os.getenv('TUSHARE_TOKEN')
        if token == 'YOUR_TUSHARE_TOKEN' or not token:
            print("警告：请设置您的TuShare Token (环境变量 TUSHARE_TOKEN)，否则无法获取数据。")
        return token
    
    # def _get_eodhd_token(self):
    #     """获取EODHD API Token"""
    #     token = os.getenv('EODHD_API_TOKEN', 'demo')
    #     if token == 'YOUR_EODHD_API_TOKEN' or not token:
    #         print("警告：请设置您的EODHD API Token (环境变量 EODHD_API_TOKEN)，否则可能无法获取宏观事件数据。")
    #     return token
    
    def _get_siliconflow_key(self):
        """获取硅基流动 AI API Key"""
        # 直接从环境变量获取，因为我们已经在_load_env_file中加载了
        api_key = os.getenv('SILICONFLOW_API_KEY')
        if not api_key:
            print("警告：硅基流动 API Key 未正确配置，AI政策分析功能将不可用。")
            print("请设置 SILICONFLOW_API_KEY 环境变量或在 .env 文件中配置。")
            return None
        return api_key