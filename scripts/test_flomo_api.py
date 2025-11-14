#!/usr/bin/env python3
"""
Flomo API 集成测试脚本

实际调用 Flomo API 获取笔记数据并打印结果
"""

import os
import sys
import json
import logging

# 添加 scripts 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flomo import FlomoAPI
from flomo.exceptions import AuthenticationError, FlomoAPIError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """主函数"""

    # 从环境变量获取 token
    token = os.environ.get('FLOMO_TOKEN')

    if not token:
        print("❌ 错误: 请设置 FLOMO_TOKEN 环境变量")
        print("\n使用方法:")
        print("  export FLOMO_TOKEN='your_token_here'")
        print("  python3 scripts/test_flomo_api.py")
        return False

    print("=" * 60)
    print("Flomo API 集成测试")
    print("=" * 60)

    try:
        # 初始化 API 客户端
        print("\n1️⃣  初始化 Flomo API 客户端...")
        api = FlomoAPI(token)
        print("✓ 客户端初始化成功")

        # 获取笔记列表
        print("\n2️⃣  获取笔记列表...")
        memos = api.get_memo_list(latest_updated_at="1761302730", limit="3")
        print(f"✓ 成功获取 {len(memos)} 条笔记\n")
        print(memos)
        # 打印笔记数据
        if memos:
            print("=" * 60)
            print("笔记数据:")
            print("=" * 60)
            for i, memo in enumerate(memos, 1):
                print(f"\n📝 笔记 {i}:")
                print(f"  Slug: {memo['slug']}")
                print(f"  创建者ID: {memo['creator_id']}")

                # 内容预览
                content = memo['content']
                if content:
                    # 去除 HTML 标签预览
                    preview = content[:100].replace('<p>', '').replace('</p>', '').replace('<ol>', '').replace('</ol>', '').replace('<li>', '').replace('</li>', '')
                    print(f"  内容: {preview}..." if len(content) > 100 else f"  内容: {preview}")
                else:
                    print(f"  内容: [空]")

                print(f"  标签: {', '.join(memo['tags']) if memo['tags'] else '无'}")
                print(f"  创建时间: {memo['created_at']}")
                print(f"  更新时间: {memo['updated_at']}")
                if memo['deleted_at']:
                    print(f"  删除时间: {memo['deleted_at']}")
                print(f"  置顶: {'是' if memo['pin'] else '否'}")
                print(f"  来源: {memo['source']}")
                print(f"  链接计数: {memo['linked_count']}")

                # 附件信息
                if memo['files']:
                    print(f"  附件数: {len(memo['files'])}")
                    for j, file in enumerate(memo['files'], 1):
                        print(f"    - 附件 {j}: {file['name']} ({file['type']}, {file['size']} 字节)")

            # 打印 JSON 格式
            print("\n" + "=" * 60)
            print("JSON 格式:")
            print("=" * 60)
            print(json.dumps(memos[:3], ensure_ascii=False, indent=2))  # 只打印前 3 条
            if len(memos) > 3:
                print(f"... 还有 {len(memos) - 3} 条笔记")
        else:
            print("⚠️  没有获取到任何笔记")

        print("\n" + "=" * 60)
        print("✓ 测试成功完成")
        print("=" * 60)
        return True

    except AuthenticationError as e:
        print(f"\n❌ 认证错误: {e}")
        print("请检查你的 FLOMO_TOKEN 是否正确")
        return False
    except FlomoAPIError as e:
        print(f"\n❌ API 错误: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
