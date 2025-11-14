"""Flomo Web API 客户端封装"""

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from . import sign
from .exceptions import AuthenticationError, FlomoAPIError

# 日志记录器
logger = logging.getLogger(__name__)

# Flomo API 配置
FLOMO_DOMAIN = "https://flomoapp.com"
MEMO_LIST_URL = FLOMO_DOMAIN + "/api/v1/memo/updated/"

# 标准请求头
DEFAULT_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "origin": "https://v.flomoapp.com",
    "priority": "u=1, i",
    "referer": "https://v.flomoapp.com/",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}

# 请求超时（秒）
DEFAULT_TIMEOUT = 10


class FlomoAPI:
    """Flomo Web API 客户端。

    提供与 Flomo Web API 交互的接口，包括：
    - 使用 Bearer Token 进行身份验证
    - 自动参数签名（MD5）
    - 分页获取笔记列表
    - 数据格式标准化
    - 完整的错误处理和日志记录

    Attributes:
        token: Flomo 认证 Token
        session: HTTP 会话对象
    """

    def __init__(self, token: str) -> None:
        """初始化 Flomo API 客户端。

        Args:
            token: Flomo Bearer Token（从浏览器 DevTools 获取）

        Raises:
            ValueError: 如果 token 为空或无效
            AuthenticationError: 如果 token 无效（API 调用时）
        """
        if not token or not isinstance(token, str) or not token.strip():
            raise ValueError("Bearer Token 不能为空")

        self.token = token.strip()
        self.session = requests.Session()

        logger.debug("FlomoAPI 客户端已初始化")

    def get_memo_list(
        self, latest_updated_at: str = "0", limit: str = "200"
    ) -> List[Dict[str, Any]]:
        """获取笔记列表。

        支持增量获取（通过 latest_updated_at 游标），每次最多返回 200 条笔记。

        Args:
            latest_updated_at: 最后更新时间戳（UNIX 时间戳，秒数）
                             用作分页游标，获取该时间戳之后更新的笔记
                             默认 "0" 表示获取所有笔记
            limit: 每次获取的最大笔记数（默认 200，API 限制）

        Returns:
            标准化的笔记列表，每条笔记包含：
            - content: 笔记内容（HTML 格式，可能为空字符串）
            - creator_id: 创建者ID
            - source: 笔记来源（web, ios, android 等）
            - tags: 标签列表（已去除 # 符号）
            - pin: 置顶状态（0/1）
            - created_at: 创建时间（格式：YYYY-MM-DD HH:MM:SS）
            - updated_at: 更新时间（格式：YYYY-MM-DD HH:MM:SS）
            - deleted_at: 删除时间（格式：YYYY-MM-DD HH:MM:SS，如果未删除则为 None）
            - slug: 唯一标识符（base64 编码）
            - linked_count: 链接计数（整数）
            - files: 附件列表，每个文件包含：
                - id: 文件ID
                - type: 文件类型（image, file 等）
                - name: 文件名称
                - size: 文件大小（字节）
                - url: 文件 URL（包含过期时间的签名 URL）
                - thumbnail_url: 缩略图 URL（如果支持）
                - path: 文件路径
                - seconds: 音频/视频时长（秒，可能为 None）
                - content: 文件内容（可能为 None）

        Raises:
            AuthenticationError: Token 无效或过期
            FlomoAPIError: Flomo API 返回业务错误
            requests.Timeout: 请求超时
            requests.RequestException: 其他网络错误
        """
        logger.debug(
            "获取笔记列表",
            extra={"latest_updated_at": latest_updated_at, "limit": limit},
        )

        try:
            # 构造请求
            headers = self._build_headers()
            params = self._build_params(
                limit=limit, latest_updated_at=latest_updated_at
            )

            logger.debug("发送 Flomo API 请求", extra={"url": MEMO_LIST_URL})

            # 发送请求
            response = requests.get(
                MEMO_LIST_URL,
                headers=headers,
                params=params,
                timeout=DEFAULT_TIMEOUT,
            )

            logger.debug(f"收到响应，状态码: {response.status_code}")

            # 检查 HTTP 状态
            if response.status_code != 200:
                logger.error(
                    f"HTTP 错误: {response.status_code}",
                    extra={"response": response.text[:200]},
                )
                raise FlomoAPIError(
                    f"HTTP {response.status_code}: {response.text}",
                    code=response.status_code,
                )

            # 解析响应
            memos = self._parse_response(response)

            logger.info(f"成功获取 {len(memos)} 条笔记")

            return memos

        except requests.exceptions.Timeout as e:
            logger.error("请求超时", exc_info=True)
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"网络错误: {str(e)}", exc_info=True)
            raise
        except (FlomoAPIError, AuthenticationError):
            raise
        except Exception as e:
            logger.error(f"未知错误: {str(e)}", exc_info=True)
            raise

    def _build_headers(self) -> Dict[str, str]:
        """构造 HTTP 请求头。

        Returns:
            包含认证信息和标准请求头的字典
        """
        headers = DEFAULT_HEADERS.copy()
        headers["authorization"] = f"Bearer {self.token}"
        return headers

    def _build_params(self, **kwargs: Any) -> Dict[str, Any]:
        """构造请求参数并生成签名。

        自动添加以下参数：
        - timestamp: 当前 UNIX 时间戳
        - sign: 参数签名（MD5）
        - api_key, app_version, platform, webp: Flomo 固定参数
        - tz: 时区（默认 8:0 表示 UTC+8）

        Args:
            **kwargs: 其他参数（如 limit, latest_updated_at）

        Returns:
            包含签名的完整参数字典
        """
        # 基础参数
        params = {
            "api_key": "flomo_web",
            "app_version": "4.0",
            "platform": "web",
            "webp": "1",
            "tz": "8:0",
            "timestamp": int(time.time()),
        }

        # 合并用户参数
        params.update(kwargs)

        # 生成签名
        params["sign"] = sign.get_sign(params)

        return params

    def _parse_response(self, response: requests.Response) -> List[Dict[str, Any]]:
        """解析 API 响应并标准化数据。

        Args:
            response: requests.Response 对象

        Returns:
            标准化的笔记列表

        Raises:
            FlomoAPIError: 如果 API 返回错误或数据格式不正确
            AuthenticationError: 如果认证失败
        """
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"JSON 解析失败: {str(e)}")
            raise FlomoAPIError("API 返回无效的 JSON 格式") from e
        print(data)
        # 检查 API 业务状态码
        code = data.get("code")
        if code != 0:
            message = data.get("message", "未知错误")

            # 认证错误特殊处理
            if code in [401, 403] or "auth" in message.lower():
                logger.error(f"认证失败: {message}")
                raise AuthenticationError(f"认证失败: {message}")

            logger.error(f"API 业务错误: code={code}, message={message}")
            raise FlomoAPIError(message, code=code)

        # 提取笔记列表
        memos = data.get("data", [])

        if not isinstance(memos, list):
            logger.error(f"数据格式错误: 期望 list，实际 {type(memos)}")
            raise FlomoAPIError("API 返回的数据格式不正确")

        # 标准化笔记数据
        normalized_memos = []
        for memo in memos:
            try:
                normalized = self._normalize_memo(memo)
                normalized_memos.append(normalized)
            except Exception as e:
                logger.warning(f"笔记标准化失败: {str(e)}")
                # 继续处理其他笔记，不中断流程

        logger.debug(f"标准化了 {len(normalized_memos)}/{len(memos)} 条笔记")

        return normalized_memos

    @staticmethod
    def _normalize_memo(raw_memo: Dict[str, Any]) -> Dict[str, Any]:
        """标准化单条笔记数据。

        从 Flomo API 返回的原始数据转换为标准格式。

        Args:
            raw_memo: API 返回的原始笔记数据

        Returns:
            标准化的笔记对象
        """
        # 提取标签（去掉 # 符号）
        tags = raw_memo.get("tags", [])
        if tags and isinstance(tags, list):
            tags = [tag.lstrip("#") if isinstance(tag, str) else str(tag) for tag in tags]
        else:
            tags = []

        # 提取文件列表（保持原样，不修改）
        files = raw_memo.get("files", [])

        return {
            "content": raw_memo.get("content", ""),
            "creator_id": raw_memo.get("creator_id"),
            "source": raw_memo.get("source", ""),
            "tags": tags,
            "pin": raw_memo.get("pin", 0),
            "created_at": raw_memo.get("created_at", ""),
            "updated_at": raw_memo.get("updated_at", ""),
            "deleted_at": raw_memo.get("deleted_at"),
            "slug": raw_memo.get("slug", ""),
            "linked_count": raw_memo.get("linked_count", 0),
            "files": files,
        }
