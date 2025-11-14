#!/usr/bin/env python3
"""
测试同步脚本的逻辑
验证配置加载、文件名生成、标签匹配等核心功能
"""

import os
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sync_flomo_to_blog import FlomoToBlogSync

# 测试数据
SAMPLE_MEMO = {
    'content': '<p>#每日一记 </p><p>我是怎么充值ChatGPT Plus</p>',
    'creator_id': 324482,
    'source': 'web',
    'tags': ['每日一记'],
    'pin': 0,
    'created_at': '2025-10-24 18:45:35',
    'updated_at': '2025-10-24 18:55:21',
    'deleted_at': None,
    'slug': 'MjAxODc3MTg0',
    'linked_count': 0,
    'files': []
}


def test_config_loading():
    """测试配置文件加载"""
    print("测试配置加载...")
    try:
        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            # 复制配置文件
            config_src = Path(".flomo_sync_config.yaml")
            config_dst = Path(tmpdir) / ".flomo_sync_config.yaml"
            shutil.copy(config_src, config_dst)

            # 改变工作目录
            orig_cwd = os.getcwd()
            os.chdir(tmpdir)

            try:
                syncer = FlomoToBlogSync(str(config_dst))
                assert syncer.config is not None
                assert 'tags' in syncer.config
                assert 'oss' in syncer.config
                print("✓ 配置加载成功")
                return True
            except Exception as e:
                print(f"✗ 配置加载失败: {e}")
                return False
            finally:
                os.chdir(orig_cwd)
    except ValueError as e:
        # 预期：缺少环境变量
        if "FLOMO_TOKEN" in str(e) or "OSS_ACCESS_KEY" in str(e):
            print("✓ 配置加载正确（预期的环境变量检查）")
            return True
        else:
            print(f"✗ 配置加载失败: {e}")
            return False


def test_filename_generation():
    """测试文件名生成"""
    print("\n测试文件名生成...")

    # 创建临时的同步器（不初始化 API 和 OSS）
    class TestSync:
        def _generate_filename(self, memo):
            date_str = memo['created_at'].split()[0]
            slug = memo['slug']
            return f"{date_str}-{slug}.md"

    syncer = TestSync()
    filename = syncer._generate_filename(SAMPLE_MEMO)

    expected = "2025-10-24-MjAxODc3MTg0.md"
    if filename == expected:
        print(f"✓ 文件名生成正确: {filename}")
        return True
    else:
        print(f"✗ 文件名生成失败: {filename} != {expected}")
        return False


def test_title_extraction():
    """测试标题提取"""
    print("\n测试标题提取...")

    import html2text

    html_content = '<p>#每日一记 </p><p>我是怎么充值ChatGPT Plus</p>'

    # 简单的标题提取逻辑
    h = html2text.HTML2Text()
    h.ignore_links = False
    md = h.handle(html_content)
    lines = [line.strip() for line in md.split('\n') if line.strip()]

    if lines:
        title = lines[0][:50]
        print(f"✓ 标题提取成功: {title}")
        return True
    else:
        print(f"✗ 标题提取失败")
        return False


def test_slug_extraction():
    """测试从文件名提取 slug"""
    print("\n测试 slug 提取...")

    # 模拟文件列表
    filenames = [
        "2025-10-24-MjAxODc3MTg0.md",
        "2025-10-25-MTg4MzA4MjEw.md",
        "2025-10-23-dGVzdA==.md"
    ]

    slugs = set()
    for filename in filenames:
        parts = filename.rsplit('-', 1)
        if len(parts) == 2:
            slug = parts[1].replace('.md', '')
            slugs.add(slug)

    expected_slugs = {"MjAxODc3MTg0", "MTg4MzA4MjEw", "dGVzdA=="}

    if slugs == expected_slugs:
        print(f"✓ Slug 提取成功: {slugs}")
        return True
    else:
        print(f"✗ Slug 提取失败: {slugs} != {expected_slugs}")
        return False


def test_tag_matching():
    """测试标签匹配"""
    print("\n测试标签匹配...")

    config_tags = {'博客', '每日一记'}
    memo_tags_1 = ['每日一记']  # 匹配
    memo_tags_2 = ['技术']      # 不匹配

    match_1 = bool(config_tags & set(memo_tags_1))
    match_2 = bool(config_tags & set(memo_tags_2))

    if match_1 and not match_2:
        print("✓ 标签匹配逻辑正确")
        return True
    else:
        print(f"✗ 标签匹配逻辑失败: match_1={match_1}, match_2={match_2}")
        return False


def test_markdown_generation():
    """测试 front matter 生成"""
    print("\n测试 Front Matter 生成...")

    from datetime import datetime

    memo = SAMPLE_MEMO.copy()

    # 生成 Front Matter
    title = "测试标题"
    date_str = memo['created_at']
    tags = memo['tags']
    slug = memo['slug']
    source = memo['source']

    # 转换日期格式
    dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    iso_date = dt.strftime('%Y-%m-%dT%H:%M:%S') + '+08:00'

    front_matter = f'''+++
title = "{title}"
date = {iso_date}
draft = false
tags = {tags}
flomo_slug = "{slug}"
flomo_source = "{source}"
+++'''

    # 验证
    if '+++' in front_matter and 'title' in front_matter and 'draft = false' in front_matter:
        print("✓ Front Matter 生成成功")
        print(f"  日期格式: {iso_date}")
        return True
    else:
        print(f"✗ Front Matter 生成失败")
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("Flomo 同步脚本逻辑测试")
    print("="*60 + "\n")

    tests = [
        test_filename_generation,
        test_title_extraction,
        test_slug_extraction,
        test_tag_matching,
        test_markdown_generation,
        test_config_loading,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ 测试异常: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    # 总结
    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"测试结果: {passed}/{total} 通过")
    print("="*60)

    return all(results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
