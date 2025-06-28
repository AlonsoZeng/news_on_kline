#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置管理模块
集中管理应用配置和环境变量
"""

import os
import logging
from typing import Optional

class Config:
    """应用配置类"""
    
    # API配置
    SILICONFLOW_API_KEY: Optional[str] = None
    API_BASE_URL: str = "https://api.siliconflow.cn/v1"
    API_MODEL: str = "deepseek-ai/DeepSeek-V2.5"
    API_TIMEOUT: int = 60
    MAX_CONCURRENT_REQUESTS: int = 5
    API_RETRY_ATTEMPTS: int = 3
    
    # 数据库配置
    DATABASE_PATH: str = "events.db"
    
    # Flask应用配置
    FLASK_ENV: str = "development"
    FLASK_DEBUG: bool = True
    FLASK_HOST: str = "127.0.0.1"
    FLASK_PORT: int = 5000
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "batch_analysis.log"
    
    @classmethod
    def load_from_env(cls):
        """从环境变量加载配置"""
        # API配置
        cls.SILICONFLOW_API_KEY = os.getenv('SILICONFLOW_API_KEY')
        cls.API_BASE_URL = os.getenv('API_BASE_URL', cls.API_BASE_URL)
        cls.API_MODEL = os.getenv('API_MODEL', cls.API_MODEL)
        cls.API_TIMEOUT = int(os.getenv('API_TIMEOUT', cls.API_TIMEOUT))
        cls.MAX_CONCURRENT_REQUESTS = int(os.getenv('MAX_CONCURRENT_REQUESTS', cls.MAX_CONCURRENT_REQUESTS))
        cls.API_RETRY_ATTEMPTS = int(os.getenv('API_RETRY_ATTEMPTS', cls.API_RETRY_ATTEMPTS))
        
        # 数据库配置
        cls.DATABASE_PATH = os.getenv('DATABASE_PATH', cls.DATABASE_PATH)
        
        # Flask应用配置
        cls.FLASK_ENV = os.getenv('FLASK_ENV', cls.FLASK_ENV)
        cls.FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
        cls.FLASK_HOST = os.getenv('FLASK_HOST', cls.FLASK_HOST)
        cls.FLASK_PORT = int(os.getenv('FLASK_PORT', cls.FLASK_PORT))
        
        # 日志配置
        cls.LOG_LEVEL = os.getenv('LOG_LEVEL', cls.LOG_LEVEL)
        cls.LOG_FILE = os.getenv('LOG_FILE', cls.LOG_FILE)
    
    @classmethod
    def validate(cls) -> bool:
        """验证必需的配置项"""
        errors = []
        
        # 验证API密钥
        if not cls.SILICONFLOW_API_KEY:
            errors.append("SILICONFLOW_API_KEY 环境变量未设置")
        elif cls.SILICONFLOW_API_KEY == 'your_api_key_here':
            errors.append("SILICONFLOW_API_KEY 仍为默认值，请设置真实的API密钥")
        elif not cls.SILICONFLOW_API_KEY.startswith('sk-'):
            errors.append("SILICONFLOW_API_KEY 格式不正确，应以 'sk-' 开头")
        
        # 验证数据库路径
        if not cls.DATABASE_PATH:
            errors.append("DATABASE_PATH 不能为空")
        
        # 验证端口号
        if not (1 <= cls.FLASK_PORT <= 65535):
            errors.append(f"FLASK_PORT {cls.FLASK_PORT} 不在有效范围内 (1-65535)")
        
        # 验证并发数
        if cls.MAX_CONCURRENT_REQUESTS <= 0:
            errors.append("MAX_CONCURRENT_REQUESTS 必须大于0")
        
        if errors:
            for error in errors:
                logging.error(f"配置验证失败: {error}")
            return False
        
        return True
    
    @classmethod
    def get_api_key(cls) -> str:
        """安全地获取API密钥"""
        if not cls.SILICONFLOW_API_KEY:
            raise ValueError("API密钥未配置，请设置 SILICONFLOW_API_KEY 环境变量")
        return cls.SILICONFLOW_API_KEY
    
    @classmethod
    def print_config_status(cls):
        """打印配置状态（隐藏敏感信息）"""
        print("=== 配置状态 ===")
        print(f"API密钥: {'已设置' if cls.SILICONFLOW_API_KEY else '未设置'}")
        print(f"API模型: {cls.API_MODEL}")
        print(f"数据库路径: {cls.DATABASE_PATH}")
        print(f"Flask端口: {cls.FLASK_PORT}")
        print(f"最大并发数: {cls.MAX_CONCURRENT_REQUESTS}")
        print(f"日志级别: {cls.LOG_LEVEL}")
        print("=================")
    
    @classmethod
    def setup_logging(cls):
        """设置日志配置"""
        log_level = getattr(logging, cls.LOG_LEVEL.upper(), logging.INFO)
        
        # 配置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        
        # 文件处理器
        file_handler = logging.FileHandler(cls.LOG_FILE, encoding='utf-8')
        file_handler.setFormatter(formatter)
        
        # 配置根日志器
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)


def init_config() -> bool:
    """初始化配置"""
    try:
        # 尝试加载 .env 文件
        env_file = os.path.join(os.path.dirname(__file__), '.env')
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
        
        # 从环境变量加载配置
        Config.load_from_env()
        
        # 设置日志
        Config.setup_logging()
        
        # 验证配置
        if not Config.validate():
            print("\n配置验证失败！请检查以下内容:")
            print("1. 确保已设置 SILICONFLOW_API_KEY 环境变量")
            print("2. 或者创建 .env 文件并配置相关参数")
            print("3. 参考 .env.example 文件了解配置格式")
            return False
        
        return True
        
    except Exception as e:
        print(f"配置初始化失败: {e}")
        return False


if __name__ == "__main__":
    # 测试配置模块
    if init_config():
        Config.print_config_status()
        print("配置初始化成功！")
    else:
        print("配置初始化失败！")