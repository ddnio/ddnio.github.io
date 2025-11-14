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
    level=logging.DEBUG,
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

    def get_synced_memo_info(self) -> Dict[str, str]:
        """扫描 posts 目录，返回已同步的笔记信息

        文件名格式: YYYY-MM-DD-{slug}.md
        使用正则表达式严格验证格式，避免误匹配

        返回字典格式: {slug: updated_at}
        用于检测笔记是否已更新

        Returns:
            已同步笔记信息字典 {slug: updated_at}
        """
        synced_info = {}

        if not self.posts_dir.exists():
            logger.warning(f"Posts 目录不存在: {self.posts_dir}")
            return synced_info

        # 匹配格式: YYYY-MM-DD-{slug}.md
        # 例如: 2025-10-24-MjAxODc3MTg0.md
        filename_pattern = r'^(\d{4})-(\d{2})-(\d{2})-(.+)\.md$'
        # 从 front matter 提取 flomo_updated_at
        updated_at_pattern = r'flomo_updated_at\s*=\s*"(.+?)"'

        for filepath in self.posts_dir.glob("*.md"):
            filename = filepath.name
            try:
                match = re.match(filename_pattern, filename)
                if not match:
                    logger.debug(f"文件名不符合预期格式，跳过: {filename}")
                    continue

                # 第 4 组是 slug
                slug = match.group(4)

                # 读取文件并解析 front matter 中的 updated_at
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 提取 flomo_updated_at 字段
                updated_match = re.search(updated_at_pattern, content)
                if updated_match:
                    updated_at = updated_match.group(1)
                    synced_info[slug] = updated_at
                    logger.debug(f"已同步: {slug} (updated_at: {updated_at})")
                else:
                    # 兼容旧文件（没有 updated_at 字段）
                    # 使用一个很早的时间戳，确保会被更新
                    synced_info[slug] = "1970-01-01 00:00:00"
                    logger.debug(f"已同步（无 updated_at）: {slug}")

            except Exception as e:
                logger.warning(f"解析文件失败 {filename}: {e}")

        logger.info(f"发现 {len(synced_info)} 条已同步的笔记")
        return synced_info


    def get_memos_to_sync(self, synced_info: Dict[str, str]) -> List[Dict]:
        """获取需要同步的笔记（新笔记 + 已更新的笔记）

        Args:
            synced_info: 已同步笔记信息 {slug: updated_at}

        Returns:
            需要同步的笔记列表
        """
        logger.info("从 Flomo 获取笔记...")

        try:
            # 计算 N 天前的时间戳
            days_to_sync = self.config['sync'].get('days_to_sync', 30)
            timestamp = int(time.time()) - (days_to_sync * 24 * 3600)
            logger.info(f"查询前 {days_to_sync} 天的笔记")

            # 获取最近的笔记
            all_memos = self.api.get_memo_list(latest_updated_at=str(timestamp), limit="200")
            logger.info(f"获取到 {len(all_memos)} 条笔记")

            # 过滤和分类
            memos_to_sync = []
            for memo in all_memos:
                # 检查是否已删除
                if memo['deleted_at']:
                    logger.debug(f"笔记已删除，跳过: {memo['slug']}")
                    continue

                # 检查标签是否匹配
                if not self._tags_match(memo['tags']):
                    logger.debug(f"标签不匹配，跳过: {memo['slug']}")
                    continue

                slug = memo['slug']
                api_updated_at = memo['updated_at']

                # 判断是新笔记还是已更新笔记
                if slug not in synced_info:
                    # 新笔记
                    logger.info(f"发现新笔记: {slug}")
                    memos_to_sync.append(memo)
                elif api_updated_at > synced_info[slug]:
                    # 已更新笔记
                    logger.info(
                        f"检测到笔记更新: {slug} "
                        f"({synced_info[slug]} -> {api_updated_at})"
                    )
                    memos_to_sync.append(memo)
                else:
                    # 无变化
                    logger.debug(f"笔记无变化，跳过: {slug}")

            logger.info(f"需要同步的笔记: {len(memos_to_sync)} 条")
            return memos_to_sync

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
        """从内容中提取标题，跳过标签行

        Args:
            content: HTML 内容
            max_length: 最大长度

        Returns:
            提取的标题
        """
        # 转换为 Markdown
        md = html2text.html2text(content)

        # 逐行处理，跳过标签行
        for line in md.split('\n'):
            line = line.strip()

            # 跳过空行
            if not line:
                continue

            # 跳过标签行（以 # 开头）
            if line.startswith('#'):
                continue

            # 找到第一个有实际内容的行
            title = line[:max_length]
            # 移除 Markdown 符号
            title = re.sub(r'^[\*\-_\s]+', '', title)
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

        # 清理多余空行和标签行
        lines = markdown.split('\n')
        cleaned = []
        prev_empty = False
        for line in lines:
            stripped = line.strip()

            # 跳过标签行（以 # 开头）
            if stripped.startswith('#'):
                prev_empty = True
                continue

            # 处理非空行
            if stripped:
                cleaned.append(line)
                prev_empty = False
            # 处理空行（最多保留一个连续空行）
            elif not prev_empty:
                cleaned.append('')
                prev_empty = True

        return '\n'.join(cleaned).strip()

    def _process_images(self, memo: Dict) -> Tuple[str, List[str]]:
        """处理笔记中的图片

        从 files 字段中提取图片，上传到 OSS，
        生成 Hugo shortcode 格式，返回替换后的内容

        Args:
            memo: 笔记对象

        Returns:
            (处理后的内容, 上传的图片 URL 列表)
        """
        content = memo['content']
        uploaded_urls = []

        # 1. 处理 files 字段中的附件
        if memo.get('files'):
            image_files = [f for f in memo['files'] if f['type'] == 'image']

            if image_files:
                logger.debug(f"发现 {len(image_files)} 个图片附件")

                for file in image_files:
                    try:
                        url = self._upload_image_from_url(file['url'])
                        uploaded_urls.append(url)
                        logger.debug(f"上传图片: {file['name']} -> {url}")
                    except Exception as e:
                        logger.warning(f"上传图片失败 {file['name']}: {e}")

                # 生成 Hugo shortcode，用 | 分隔多个图片 URL
                if uploaded_urls:
                    images_str = '|'.join(uploaded_urls)
                    shortcode = f'{{{{< flomo images="{images_str}" >}}}}'
                    content += f'\n\n{shortcode}\n'

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
        updated_at = memo['updated_at']  # "2025-10-24 18:45:35"
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
flomo_updated_at = "{updated_at}"
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

        # 提取标题（用于去重）
        title = self._extract_title(memo['content'])

        # 处理图片
        content, _ = self._process_images(memo)

        # 转换为 Markdown
        md_content = self._convert_html_to_markdown(content)

        # 删除正文开头与 front matter 标题重复的行
        lines = md_content.split('\n')
        cleaned_lines = []
        title_removed = False

        for line in lines:
            # 如果第一行与标题相同，跳过
            if not title_removed and line.strip() == title:
                title_removed = True
                continue
            cleaned_lines.append(line)

        md_content = '\n'.join(cleaned_lines).strip()

        # 生成 Front Matter
        front_matter = self._generate_front_matter(memo)

        # 合并
        file_content = f"{front_matter}\n\n{md_content}"

        return filename, file_content

    def save_markdown_file(self, filename: str, content: str) -> bool:
        """保存 Markdown 文件

        支持新建和覆盖（用于更新已同步的笔记）

        Args:
            filename: 文件名
            content: 文件内容

        Returns:
            是否成功
        """
        # 确保目录存在
        self.posts_dir.mkdir(parents=True, exist_ok=True)

        filepath = self.posts_dir / filename

        # 保存文件（新建或覆盖）
        logger.info(f"保存笔记: {filename}")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        except Exception as e:
            logger.error(f"保存文件失败 {filename}: {e}")
            return False

    def sync(self) -> Dict[str, int]:
        """执行同步

        Returns:
            同步统计 {'total': 总数, 'new': 新增数, 'updated': 更新数, 'failed': 失败数}
        """
        logger.info("="*60)
        logger.info("开始同步 Flomo 笔记")
        logger.info("="*60)

        stats = {
            'total': 0,
            'new': 0,
            'updated': 0,
            'failed': 0
        }

        try:
            # 1. 获取已同步的笔记信息
            synced_info = self.get_synced_memo_info()

            # 2. 获取需要同步的笔记（新笔记 + 已更新笔记）
            memos_to_sync = self.get_memos_to_sync(synced_info)
            stats['total'] = len(memos_to_sync)

            if not memos_to_sync:
                logger.info("没有笔记需要同步")
                return stats

            # 3. 处理每条笔记
            for memo in memos_to_sync:
                try:
                    slug = memo['slug']
                    is_update = slug in synced_info

                    logger.info(f"处理笔记: {slug} ({'更新' if is_update else '新增'})")
                    filename, content = self._generate_markdown_file(memo)

                    if self.save_markdown_file(filename, content):
                        if is_update:
                            stats['updated'] += 1
                            logger.info(f"✓ 更新成功: {filename}")
                        else:
                            stats['new'] += 1
                            logger.info(f"✓ 新增成功: {filename}")
                    else:
                        stats['failed'] += 1
                        logger.error(f"✗ 保存失败: {filename}")

                except Exception as e:
                    stats['failed'] += 1
                    logger.error(f"✗ 同步失败 {memo['slug']}: {e}", exc_info=True)

            # 4. 输出统计
            logger.info("="*60)
            logger.info("同步完成")
            logger.info(
                f"总计: {stats['total']}, "
                f"新增: {stats['new']}, "
                f"更新: {stats['updated']}, "
                f"失败: {stats['failed']}"
            )
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

        # 如果有新增或更新的笔记，返回成功
        return (stats['new'] + stats['updated']) > 0 or stats['total'] == 0

    except Exception as e:
        logger.error(f"错误: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
