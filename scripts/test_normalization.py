#!/usr/bin/env python3
"""
测试数据规范化逻辑
验证 _normalize_memo 是否正确处理实际的 API 返回数据
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flomo import FlomoAPI

# 实际的 API 返回数据示例（从你的测试输出中提取）
sample_memo = {
    'content': '<p>#每日一记 </p><p>我是怎么充值ChatGPT Plus</p>',
    'creator_id': 324482,
    'source': 'web',
    'tags': ['#每日一记'],
    'pin': 0,
    'created_at': '2025-10-24 18:45:35',
    'updated_at': '2025-10-24 18:55:21',
    'deleted_at': None,
    'slug': 'MjAxODc3MTg0',
    'linked_count': 0,
    'files': [
        {
            'id': 43811488,
            'creator_id': 324482,
            'type': 'image',
            'name': '1761299665504.png',
            'path': 'file/2025-10-24/324482/f0ae9c640c13aa99f0a41920f98548e7.png',
            'size': 185275,
            'seconds': None,
            'content': None,
            'url': 'https://static.flomoapp.com/file/2025-10-24/324482/f0ae9c640c13aa99f0a41920f98548e7.png?OSSAccessKeyId=xxx',
            'thumbnail_url': 'https://static.flomoapp.com/file/2025-10-24/324482/f0ae9c640c13aa99f0a41920f98548e7.png/thumbnailwebp?OSSAccessKeyId=xxx'
        }
    ]
}

print("=" * 60)
print("测试数据规范化")
print("=" * 60)

print("\n1️⃣  原始数据:")
print(json.dumps(sample_memo, ensure_ascii=False, indent=2)[:500] + "...")

print("\n2️⃣  标准化数据:")
normalized = FlomoAPI._normalize_memo(sample_memo)
print(json.dumps(normalized, ensure_ascii=False, indent=2, default=str)[:800] + "...")

print("\n3️⃣  验证字段:")
required_fields = [
    'content', 'creator_id', 'source', 'tags', 'pin',
    'created_at', 'updated_at', 'deleted_at', 'slug',
    'linked_count', 'files'
]

all_present = True
for field in required_fields:
    present = field in normalized
    status = "✓" if present else "✗"
    print(f"  {status} {field}: {type(normalized.get(field)).__name__}")
    if not present:
        all_present = False

print("\n4️⃣  标签处理:")
print(f"  原始标签: {sample_memo['tags']}")
print(f"  标准化后: {normalized['tags']}")
print(f"  ✓ # 符号已移除" if all(not tag.startswith('#') for tag in normalized['tags']) else "  ✗ # 符号未移除")

print("\n5️⃣  文件信息:")
print(f"  文件数: {len(normalized['files'])}")
if normalized['files']:
    file_fields = ['id', 'type', 'name', 'size', 'url', 'thumbnail_url']
    for i, file in enumerate(normalized['files'][:1], 1):
        print(f"  附件 {i}: {file.get('name')}")
        for field in file_fields:
            present = field in file
            status = "✓" if present else "✗"
            print(f"    {status} {field}")

print("\n" + "=" * 60)
if all_present:
    print("✓ 所有必需字段都存在!")
else:
    print("✗ 某些字段缺失!")
print("=" * 60)
