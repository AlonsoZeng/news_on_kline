import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_policy_analyzer import AIPolicyAnalyzer
import json

def test_ai_analyzer():
    """测试AI政策分析器功能"""
    print("=== AI政策分析器测试 ===")
    
    # 配置
    API_KEY = "sk-rtfxnalfnpfrucbjvzzizgsltocaywdtfvvcmloznshsqzfo"
    DB_PATH = "events.db"
    
    try:
        # 初始化分析器
        print("1. 初始化AI分析器...")
        analyzer = AIPolicyAnalyzer(API_KEY, DB_PATH)
        print("✓ AI分析器初始化成功")
        
        # 测试单个政策分析
        print("\n2. 测试单个政策分析...")
        test_title = "国务院发布新能源汽车产业发展规划"
        test_content = "为推动新能源汽车产业高质量发展，国务院发布了新能源汽车产业发展规划，明确了未来发展目标和重点任务，支持新能源汽车技术创新和产业升级。"
        
        result = analyzer.analyze_policy(test_title, test_content, "政策发布")
        
        if result:
            print("✓ 政策分析成功")
            print("分析结果:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("✗ 政策分析失败")
        
        # 测试批量分析未处理的政策
        print("\n3. 测试批量分析未处理政策...")
        processed_count = analyzer.analyze_unprocessed_policies(limit=3)
        print(f"✓ 成功分析 {processed_count} 条政策")
        
        # 测试根据股票代码查询相关政策
        print("\n4. 测试根据股票代码查询相关政策...")
        stock_policies = analyzer.get_policies_by_stock("600519")
        print(f"✓ 找到 {len(stock_policies)} 条与股票600519相关的政策")
        
        if stock_policies:
            print("相关政策示例:")
            for policy in stock_policies[:2]:  # 只显示前2条
                print(f"- {policy['title']} ({policy['date']})")
        
        print("\n=== 测试完成 ===")
        
    except Exception as e:
        print(f"✗ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_analyzer()