#!/usr/bin/env python3
"""
Flomo 笔记同步到博客的脚本

从 Flomo 中获取指定标签的笔记，转换为 Markdown 格式，
并生成到博客的 content/posts 目录。

支持功能：
- 按标签过滤笔记
- 自动去重（已同步的笔记不重复生成）
- 图片上传到阿里云 OSS
- HTML 转 Markdown
"""

import os
import sys
import yaml
import json
import logging
import time
import uuid
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from urllib.parse import urlparse

import requests
import oss2
import html2text

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


class FlomoToBlogSync:
    """Flomo 到博客的同步器"""

    def __init__(self, config_path: str = ".flomo_sync_config.yaml"):
        """初始化同步器

        Args:
            config_path: 配置文件路径
        """
        self.config = self._load_config(config_path)
        self.posts_dir = Path(self.config['sync']['posts_dir'])
        self.api = self._init_flomo_api()
        self.oss_client = self._init_oss_client()

        logger.info("同步器初始化完成")

    def _load_config(self, config_path: str) -> dict:
        """加载配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            配置字典
        """
        logger.info(f"加载配置文件: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 验证必要的配置
        assert 'tags' in config, "配置中缺少 tags 字段"
        assert 'oss' in config, "配置中缺少 oss 字段"
        assert 'sync' in config, "配置中缺少 sync 字段"

        logger.info(f"要同步的标签: {config['tags']}")
        return config

    def _init_flomo_api(self) -> FlomoAPI:
        """初始化 Flomo API 客户端

        Returns:
            FlomoAPI 实例
        """
        token = os.environ.get('FLOMO_TOKEN')
        if not token:
            raise ValueError("环境变量 FLOMO_TOKEN 未设置")

        return FlomoAPI(token)

    def _init_oss_client(self) -> oss2.Auth:
        """初始化阿里云 OSS 客户端

        Returns:
            OSS Auth 对象
        """
        access_key_id = os.environ.get('OSS_ACCESS_KEY_ID')
        access_key_secret = os.environ.get('OSS_ACCESS_KEY_SECRET')

        if not access_key_id or not access_key_secret:
            raise ValueError("环境变量 OSS_ACCESS_KEY_ID 或 OSS_ACCESS_KEY_SECRET 未设置")

        return oss2.Auth(access_key_id, access_key_secret)

    def get_synced_slugs(self) -> Set[str]:
        """扫描 posts 目录，返回已同步的 slug 集合

        文件名格式: YYYY-MM-DD-{slug}.md

        Returns:
            已同步的 slug 集合
        """
        synced_slugs = set()

        if not self.posts_dir.exists():
            logger.warning(f"Posts 目录不存在: {self.posts_dir}")
            return synced_slugs

        for filepath in self.posts_dir.glob("*.md"):
            # 文件名格式: 2025-10-24-MjAxODc3MTg0.md
            # 提取 slug 部分（最后一个 '-' 之后，.md 之前）
            filename = filepath.name
            try:
                parts = filename.rsplit('-', 1)
                if len(parts) == 2:
                    slug = parts[1].replace('.md', '')
                    synced_slugs.add(slug)
                    logger.debug(f"已同步: {slug}")
            except Exception as e:
                logger.warning(f"解析文件名失败 {filename}: {e}")

        logger.info(f"发现 {len(synced_slugs)} 条已同步的笔记")
        return synced_slugs

    def get_new_memos(self, synced_slugs: Set[str]) -> List[Dict]:
        """获取需要同步的笔记

        Args:
            synced_slugs: 已同步的 slug 集合

        Returns:
            需要同步的笔记列表
        """
        logger.info("从 Flomo 获取笔记...")

        try:
            # 获取所有笔记
            all_memos = self.api.get_memo_list(limit="200")
            logger.info(f"获取到 {len(all_memos)} 条笔记")

            # 过滤
            new_memos = []
            for memo in all_memos:
                # 检查是否已同步
                if memo['slug'] in synced_slugs:
                    continue

                # 检查是否已删除
                if memo['deleted_at']:
                    continue

                # 检查标签是否匹配
                if self._tags_match(memo['tags']):
                    new_memos.append(memo)

            logger.info(f"需要同步的新笔记: {len(new_memos)} 条")
            return new_memos

        except AuthenticationError as e:
            logger.error(f"认证错误: {e}")
            raise
        except FlomoAPIError as e:
            logger.error(f"API 错误: {e}")
            raise

    def _tags_match(self, memo_tags: List[str]) -> bool:
        """检查笔记标签是否在配置中

        Args:
            memo_tags: 笔记的标签列表

        Returns:
            是否匹配
        """
        config_tags = set(self.config['tags'])
        memo_tags_set = set(memo_tags)
        return bool(config_tags & memo_tags_set)

    def _extract_title(self, content: str, max_length: int = 50) -> str:
        """从内容中提取标题

        Args:
            content: HTML 内容
            max_length: 最大长度

        Returns:
            提取的标题
        """
        # 转换为 Markdown
        md = html2text.html2text(content)

        # 提取第一行非空内容
        lines = [line.strip() for line in md.split('\n') if line.strip()]
        if lines:
            title = lines[0][:max_length]
            # 移除 Markdown 符号
            title = re.sub(r'^[#\s]+', '', title)
            if title:
                return title

        return '无标题笔记'

    def _generate_filename(self, memo: Dict) -> str:
        """生成文件名

        格式: YYYY-MM-DD-{slug}.md

        Args:
            memo: 笔记对象

        Returns:
            文件名
        """
        # 从 created_at 提取日期 (格式: "2025-10-24 18:45:35")
        date_str = memo['created_at'].split()[0]
        slug = memo['slug']
        return f"{date_str}-{slug}.md"

    def _convert_html_to_markdown(self, html_content: str) -> str:
        """将 HTML 转换为 Markdown

        Args:
            html_content: HTML 内容

        Returns:
            Markdown 内容
        """
        # 使用 html2text 转换
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False
        h.body_width = 0  # 不限制行宽

        markdown = h.handle(html_content)

        # 清理多余空行
        lines = markdown.split('\n')
        cleaned = []
        prev_empty = False
        for line in lines:
            if line.strip():
                cleaned.append(line)
                prev_empty = False
            elif not prev_empty:
                cleaned.append('')
                prev_empty = True

        return '\n'.join(cleaned).strip()

    def _process_images(self, memo: Dict) -> Tuple[str, List[str]]:
        """处理笔记中的图片

        从 files 字段和 content HTML 中提取图片，
        上传到 OSS，返回替换后的内容

        Args:
            memo: 笔记对象

        Returns:
            (处理后的内容, 上传的图片 URL 列表)
        """
        content = memo['content']
        uploaded_urls = []

        # 1. 处理 files 字段中的附件
        if memo.get('files'):
            logger.debug(f"发现 {len(memo['files'])} 个附件")
            for file in memo['files']:
                if file['type'] == 'image':
                    try:
                        url = self._upload_image_from_url(file['url'])
                        uploaded_urls.append(url)
                        # 在内容末尾添加图片
                        content += f'\n\n![{file["name"]}]({url})'
                        logger.debug(f"上传图片: {file['name']} -> {url}")
                    except Exception as e:
                        logger.warning(f"上传图片失败 {file['name']}: {e}")

        return content, uploaded_urls

    def _upload_image_from_url(self, image_url: str) -> str:
        """从 URL 下载图片并上传到 OSS

        Args:
            image_url: 图片 URL

        Returns:
            OSS 图片 URL
        """
        # 下载图片
        logger.debug(f"下载图片: {image_url}")
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()

        # 生成文件名
        ext = os.path.splitext(urlparse(image_url).path)[-1] or '.png'
        filename = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"

        # OSS 路径
        date_str = datetime.now().strftime('%Y-%m-%d')
        oss_config = self.config['oss']
        prefix = oss_config.get('prefix', 'flomo/')
        oss_path = f"{prefix}{date_str}/{filename}"

        # 上传到 OSS
        logger.debug(f"上传到 OSS: {oss_path}")
        bucket = oss2.Bucket(
            self.oss_client,
            oss_config['endpoint'],
            oss_config['bucket']
        )
        bucket.put_object(oss_path, response.content)

        # 返回 OSS URL
        url = f"https://{oss_config['bucket']}.{oss_config['endpoint']}/{oss_path}"
        return url

    def _generate_front_matter(self, memo: Dict) -> str:
        """生成 Front Matter

        使用 TOML 格式

        Args:
            memo: 笔记对象

        Returns:
            Front Matter 字符串
        """
        # 提取信息
        title = self._extract_title(memo['content'])
        date_str = memo['created_at']  # "2025-10-24 18:45:35"
        tags = memo['tags']
        slug = memo['slug']
        source = memo['source']

        # 转换日期格式为 ISO 8601
        # "2025-10-24 18:45:35" -> "2025-10-24T18:45:35+08:00"
        dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        iso_date = dt.strftime('%Y-%m-%dT%H:%M:%S') + '+08:00'

        # 生成 Front Matter（TOML 格式）
        front_matter = f'''+++
title = "{title}"
date = {iso_date}
draft = false
tags = {tags}
flomo_slug = "{slug}"
flomo_source = "{source}"
+++'''

        return front_matter

    def _generate_markdown_file(self, memo: Dict) -> Tuple[str, str]:
        """生成 Markdown 文件内容

        Args:
            memo: 笔记对象

        Returns:
            (文件名, 文件内容)
        """
        # 生成文件名
        filename = self._generate_filename(memo)

        # 处理图片
        content, _ = self._process_images(memo)

        # 转换为 Markdown
        md_content = self._convert_html_to_markdown(content)

        # 生成 Front Matter
        front_matter = self._generate_front_matter(memo)

        # 合并
        file_content = f"{front_matter}\n\n{md_content}"

        return filename, file_content

    def save_markdown_file(self, filename: str, content: str) -> bool:
        """保存 Markdown 文件

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            是否成功
        """
        # 确保目录存在
        self.posts_dir.mkdir(parents=True, exist_ok=True)

        filepath = self.posts_dir / filename

        # 避免覆盖现有文件
        if filepath.exists():
            logger.warning(f"文件已存在，跳过: {filename}")
            return False

        # 保存文件
        logger.info(f"保存笔记: {filename}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        return True

    def sync(self) -> Dict[str, int]:
        """执行同步

        Returns:
            同步统计 {'total': 总数, 'synced': 同步数, 'skipped': 跳过数, 'failed': 失败数}
        """
        logger.info("="*60)
        logger.info("开始同步 Flomo 笔记")
        logger.info("="*60)

        stats = {
            'total': 0,
            'synced': 0,
            'skipped': 0,
            'failed': 0
        }

        try:
            # 1. 获取已同步的笔记
            synced_slugs = self.get_synced_slugs()

            # 2. 获取需要同步的新笔记
            new_memos = self.get_new_memos(synced_slugs)
            stats['total'] = len(new_memos)

            if not new_memos:
                logger.info("没有新笔记需要同步")
                return stats

            # 3. 处理每条笔记
            for memo in new_memos:
                try:
                    logger.info(f"处理笔记: {memo['slug']}")
                    filename, content = self._generate_markdown_file(memo)

                    if self.save_markdown_file(filename, content):
                        stats['synced'] += 1
                        logger.info(f"✓ 同步成功: {filename}")
                    else:
                        stats['skipped'] += 1
                        logger.info(f"⊘ 跳过: {filename}")

                except Exception as e:
                    stats['failed'] += 1
                    logger.error(f"✗ 同步失败 {memo['slug']}: {e}", exc_info=True)

            # 4. 输出统计
            logger.info("="*60)
            logger.info("同步完成")
            logger.info(f"总计: {stats['total']}, 成功: {stats['synced']}, 跳过: {stats['skipped']}, 失败: {stats['failed']}")
            logger.info("="*60)

            return stats

        except Exception as e:
            logger.error(f"同步失败: {e}", exc_info=True)
            raise


def main():
    """主函数"""
    try:
        # 检查配置文件
        config_file = Path(".flomo_sync_config.yaml")
        if not config_file.exists():
            logger.error("配置文件不存在: .flomo_sync_config.yaml")
            return False

        # 创建同步器并执行
        syncer = FlomoToBlogSync()
        stats = syncer.sync()

        # 如果有同步的笔记，返回成功
        return stats['synced'] > 0 or stats['total'] == 0

    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
