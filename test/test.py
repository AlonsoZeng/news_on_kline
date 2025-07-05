import tushare as ts
import pandas as pd
import os
from datetime import datetime

def get_stock_data_free():
    """
    使用tushare免费接口获取股票数据
    注意：免费接口对ETF支持有限，建议使用个股代码测试
    """
    
    try:
        print("开始使用免费接口获取股票数据...")
        
        # 使用免费接口，无需token
        # 注意：512800是ETF，免费接口可能无法获取，建议先用个股测试
        stock_code = '000001'  # 先用平安银行测试
        # stock_code = '512800'  # ETF可能无法获取
        
        df = ts.get_k_data(
            code=stock_code,
            start='2023-01-01',
            end='2025-07-03'
        )
        
        if df is None or df.empty:
            print("免费接口未获取到数据，可能原因：")
            print("1. ETF数据免费接口不支持")
            print("2. 网络连接问题")
            print("3. 股票代码格式问题")
            return None
        
        print(f"成功获取到 {len(df)} 条数据")
        
        # 数据预处理
        df = df.sort_values('date')
        df = df.reset_index(drop=True)
        
        # 重命名列
        df_result = df.copy()
        df_result.columns = ['交易日期', '开盘价', '收盘价', '最高价', '最低价', '成交量']
        
        # 计算价格变动和涨跌幅
        df_result['价格变动'] = df_result['收盘价'] - df_result['收盘价'].shift(1)
        df_result['涨跌幅(%)'] = (df_result['价格变动'] / df_result['收盘价'].shift(1) * 100).round(2)
        
        # 重新排列列顺序
        df_result = df_result[['交易日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '价格变动', '涨跌幅(%)']]
        
        # 保存为CSV
        output_file = f'stock_{stock_code}_free_data.csv'
        df_result.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print(f"数据已保存到: {output_file}")
        print("\n数据预览:")
        print(df_result.head())
        
        return df_result
        
    except Exception as e:
        print(f"获取数据失败: {str(e)}")
        return None

def get_stock_data_pro():
    """
    使用tushare Pro接口获取股票数据（需要正确的token和积分）
    """
    
    # 使用正确的token格式
    token = 'f6a8c4b66eaeb4e9ff4fdcd8575e1f7acf8c268079e132247f1af168'  # 从.env文件复制的正确token
    ts.set_token(token)
    pro = ts.pro_api()
    
    try:
        print("开始使用Pro接口获取股票数据...")
        
        # 获取股票日线数据
        df = pro.daily(
            ts_code='512800.SH',
            start_date='20230101',
            end_date='20250703'
        )
        
        if df.empty:
            print("Pro接口未获取到数据，可能原因：")
            print("1. 积分不足")
            print("2. Token无效")
            print("3. 股票代码错误")
            return None
        
        print(f"成功获取到 {len(df)} 条数据")
        
        # 数据处理（与原代码相同）
        df = df.sort_values('trade_date')
        df = df.reset_index(drop=True)
        
        result_df = df[[
            'trade_date', 'open', 'high', 'low', 'close', 'vol', 'change', 'pct_chg'
        ]].copy()
        
        result_df.columns = [
            '交易日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '价格变动', '涨跌幅(%)'
        ]
        
        result_df['交易日期'] = pd.to_datetime(result_df['交易日期'], format='%Y%m%d').dt.strftime('%Y-%m-%d')
        
        output_file = 'stock_512800_SH_pro_data.csv'
        result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        
        print(f"数据已保存到: {output_file}")
        print("\n数据预览:")
        print(result_df.head())
        
        return result_df
        
    except Exception as e:
        print(f"Pro接口获取数据失败: {str(e)}")
        return None

def get_stock_data_like_web():
    """
    方案3：完全模拟web服务的数据获取方式
    使用与app.py中fetch_stock_kline_data函数相同的逻辑
    """
    
    # 使用与web服务相同的token配置
    token = 'f6a8c4b66eaeb4e9ff4fdcd8575e1f7acf8c268079e132247f1af168'
    ts.set_token(token)
    
    try:
        print("=== 方案3：模拟web服务的数据获取方式 ===")
        print("使用与app.py完全相同的配置和调用方式")
        
        # 目标股票代码（先测试个股，再测试ETF）
        test_stocks = [
            # {'code': '000001', 'name': '平安银行', 'type': '个股'},
            {'code': '512800', 'name': '中证银行ETF', 'type': 'ETF'}
        ]
        
        results = {}
        
        for stock in test_stocks:
            stock_code = stock['code']
            stock_name = stock['name']
            stock_type = stock['type']
            
            print(f"\n--- 正在获取 {stock_name}({stock_code}) 的数据 ---")
            print(f"股票类型: {stock_type}")
            
            try:
                # 使用与web服务相同的免费接口调用方式
                print(f"正在从TuShare免费接口获取 {stock_code} 的数据...")
                
                # 完全模拟app.py中的调用方式
                df_api = ts.get_k_data(
                    code=stock_code,
                    start='2023-01-01',
                    end='2025-07-03'
                )
                
                if df_api is not None and not df_api.empty:
                    print(f"✅ 成功获取到 {len(df_api)} 条数据")
                    
                    # 处理API返回的数据（模拟app.py的处理逻辑）
                    df_processed = pd.DataFrame({
                        'date': pd.to_datetime(df_api['date']),
                        'open': df_api['open'],
                        'close': df_api['close'],
                        'low': df_api['low'],
                        'high': df_api['high'],
                        'volume': df_api['volume']
                    })
                    df_processed = df_processed.sort_values(by='date')
                    
                    # 计算价格变动和涨跌幅
                    df_processed['change'] = df_processed['close'] - df_processed['close'].shift(1)
                    df_processed['pct_chg'] = (df_processed['change'] / df_processed['close'].shift(1) * 100).round(2)
                    
                    # 重命名列为中文（与原需求一致）
                    df_result = df_processed[[
                        'date', 'open', 'high', 'low', 'close', 'volume', 'change', 'pct_chg'
                    ]].copy()
                    
                    df_result.columns = [
                        '交易日期', '开盘价', '最高价', '最低价', '收盘价', '成交量', '价格变动', '涨跌幅(%)'
                    ]
                    
                    # 格式化日期
                    df_result['交易日期'] = df_result['交易日期'].dt.strftime('%Y-%m-%d')
                    
                    # 保存文件
                    output_file = f'stock_{stock_code}_{stock_name}_web_style_data.csv'
                    df_result.to_csv(output_file, index=False, encoding='utf-8-sig')
                    
                    print(f"📁 数据已保存到: {output_file}")
                    print(f"📊 数据统计:")
                    print(f"   - 数据时间范围: {df_result['交易日期'].min()} 到 {df_result['交易日期'].max()}")
                    print(f"   - 总交易日数: {len(df_result)} 天")
                    print(f"   - 期间最高价: {df_result['最高价'].max():.2f}")
                    print(f"   - 期间最低价: {df_result['最低价'].min():.2f}")
                    
                    # 显示前几行数据
                    print(f"\n📋 数据预览（前5行）:")
                    print(df_result.head())
                    
                    results[stock_code] = {
                        'success': True,
                        'data': df_result,
                        'file': output_file,
                        'count': len(df_result)
                    }
                    
                else:
                    print(f"❌ 未获取到 {stock_code} 的数据")
                    print(f"   可能原因: {stock_type}数据在免费接口中不可用")
                    results[stock_code] = {
                        'success': False,
                        'reason': f'{stock_type}数据免费接口不支持'
                    }
                    
            except Exception as e:
                print(f"❌ 获取 {stock_code} 数据时出错: {str(e)}")
                results[stock_code] = {
                    'success': False,
                    'reason': str(e)
                }
        
        # 总结报告
        print("\n" + "="*60)
        print("📈 方案3执行总结报告")
        print("="*60)
        
        success_count = sum(1 for r in results.values() if r.get('success', False))
        total_count = len(results)
        
        print(f"✅ 成功获取: {success_count}/{total_count} 个股票")
        
        for stock_code, result in results.items():
            stock_info = next(s for s in test_stocks if s['code'] == stock_code)
            if result.get('success', False):
                print(f"   ✅ {stock_info['name']}({stock_code}): {result['count']}条数据 -> {result['file']}")
            else:
                print(f"   ❌ {stock_info['name']}({stock_code}): {result.get('reason', '未知错误')}")
        
        print("\n🎯 结论:")
        if success_count > 0:
            print("   方案3成功！与web服务使用相同的免费接口可以获取数据")
            print("   建议：对于ETF数据，可能需要使用Pro API或其他数据源")
        else:
            print("   方案3失败，可能需要检查网络连接或tushare服务状态")
        
        return results
        
    except Exception as e:
        print(f"❌ 方案3执行失败: {str(e)}")
        return None

if __name__ == "__main__":
    print("=== TuShare数据获取测试 ===")
    
    print("\n方法1: 使用免费接口（推荐先测试）")
    result_free = get_stock_data_free()
    
    print("\n" + "="*50)
    print("\n方法2: 使用Pro接口（需要积分）")
    result_pro = get_stock_data_pro()
    
    print("\n" + "="*50)
    print("\n方法3: 完全模拟web服务方式（推荐）")
    result_web = get_stock_data_like_web()
    
    print("\n" + "="*50)
    print("\n=== 最终总结 ===")
    
    methods_status = [
        ("免费接口", result_free is not None),
        ("Pro接口", result_pro is not None),
        ("Web服务模拟", result_web is not None and any(r.get('success', False) for r in result_web.values()) if result_web else False)
    ]
    
    for method_name, success in methods_status:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{method_name}: {status}")
    
    print("\n🎯 推荐使用方案3，因为它与web服务使用完全相同的配置和调用方式！")