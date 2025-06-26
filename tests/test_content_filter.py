#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试内容过滤功能
验证备案号和无效内容的过滤是否正常工作
"""

from policy_data_fetcher import PolicyDataFetcher

def test_content_filter():
    """测试内容过滤功能"""
    fetcher = PolicyDataFetcher()
    
    # 测试用例：应该被过滤的内容
    should_skip = [
        "京ICP备05070218号",
        "京公网安备11010202000001号",
        "ICP备案号：京ICP备12345678号",
        "网站备案信息",
        "版权所有",
        "联系我们",
        "网站地图",
        "更多",
        "查看更多",
        "首页",
        "返回",
        "2024-06-17",  # 纯日期
        "123",  # 过短
        "",  # 空字符串
        "   ",  # 空白字符
    ]
    
    # 测试用例：不应该被过滤的内容
    should_keep = [
        "国务院关于印发《政府工作报告》重点工作分工的意见",
        "财政部关于进一步加强政府采购需求管理的指导意见",
        "中国人民银行关于金融支持全面推进乡村振兴的意见",
        "国家发展改革委关于促进服务业领域困难行业恢复发展的若干政策",
        "证监会发布《关于加强证券公司和公募基金监管加强投资者保护的若干规定》",
        "工业和信息化部关于印发《""十四五""信息化和工业化深度融合发展规划》的通知",
    ]
    
    print("=== 测试内容过滤功能 ===")
    print()
    
    print("测试应该被过滤的内容：")
    failed_skip = []
    for content in should_skip:
        result = fetcher._should_skip_content(content)
        status = "✓ 正确过滤" if result else "✗ 未被过滤"
        print(f"  {status}: '{content}'")
        if not result:
            failed_skip.append(content)
    
    print()
    print("测试不应该被过滤的内容：")
    failed_keep = []
    for content in should_keep:
        result = fetcher._should_skip_content(content)
        status = "✓ 正确保留" if not result else "✗ 被错误过滤"
        print(f"  {status}: '{content[:50]}{'...' if len(content) > 50 else ''}'")
        if result:
            failed_keep.append(content)
    
    print()
    print("=== 测试结果汇总 ===")
    print(f"应该过滤的内容: {len(should_skip)} 个，成功过滤: {len(should_skip) - len(failed_skip)} 个")
    print(f"应该保留的内容: {len(should_keep)} 个，成功保留: {len(should_keep) - len(failed_keep)} 个")
    
    if failed_skip:
        print(f"\n⚠️  以下内容应该被过滤但未被过滤:")
        for content in failed_skip:
            print(f"  - '{content}'")
    
    if failed_keep:
        print(f"\n⚠️  以下内容不应该被过滤但被过滤了:")
        for content in failed_keep:
            print(f"  - '{content[:50]}{'...' if len(content) > 50 else ''}'")
    
    if not failed_skip and not failed_keep:
        print("\n🎉 所有测试通过！过滤功能工作正常。")
    else:
        print(f"\n❌ 测试失败: {len(failed_skip + failed_keep)} 个用例未通过")
    
    return len(failed_skip + failed_keep) == 0

if __name__ == "__main__":
    test_content_filter()