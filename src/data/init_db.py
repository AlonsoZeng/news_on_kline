#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动初始化数据库
"""

from ..core.policy_data_fetcher import PolicyDataFetcher

if __name__ == "__main__":
    print("开始初始化数据库...")
    fetcher = PolicyDataFetcher()
    fetcher.init_database()
    print("数据库初始化完成")