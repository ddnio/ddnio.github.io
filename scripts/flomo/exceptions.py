"""Flomo API 异常定义"""


class FlomoError(Exception):
    """Flomo 相关错误的基类。

    所有 Flomo 相关的异常都继承自此类，便于统一捕获。
    """

    pass


class AuthenticationError(FlomoError):
    """认证失败错误。

    当 Bearer Token 无效、过期或权限不足时抛出此异常。
    """

    pass


class FlomoAPIError(FlomoError):
    """Flomo API 业务错误。

    当 Flomo API 返回业务错误（code != 0）时抛出此异常。
    包含原始的错误信息。
    """

    def __init__(self, message: str, code: int = -1) -> None:
        """初始化 API 错误。

        Args:
            message: 错误信息
            code: 错误代码（默认 -1）
        """
        super().__init__(message)
        self.message = message
        self.code = code

    def __str__(self) -> str:
        """返回字符串表示。

        Returns:
            格式化的错误消息
        """
        return f"FlomoAPIError({self.code}): {self.message}"
