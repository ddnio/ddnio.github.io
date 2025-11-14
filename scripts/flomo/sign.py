"""Flomo API 参数签名生成"""

import hashlib
from typing import Any, Dict


def _ksort(params: Dict[str, Any]) -> Dict[str, Any]:
    """对字典按键进行字母排序。

    Args:
        params: 输入的参数字典

    Returns:
        排序后的字典
    """
    return dict(sorted(params.items()))


def get_sign(params: Dict[str, Any]) -> str:
    """生成 Flomo API 请求签名。

    签名算法：
    1. 对所有参数按键进行字母排序
    2. 将排序后的参数构造为查询字符串 (key1=value1&key2=value2&...)
       - 如果值是列表，展开为 key[]=value1&key[]=value2&...
    3. 追加密钥: dbbc3dd73364b4084c3a69346e0ce2b2
    4. 计算整个字符串的 MD5 哈希值

    Args:
        params: 请求参数字典，可能包含基本类型和列表

    Returns:
        32 位的 MD5 哈希值（十六进制字符串）

    Example:
        >>> params = {
        ...     "api_key": "flomo_web",
        ...     "timestamp": 1700000000,
        ...     "limit": "10"
        ... }
        >>> sign = get_sign(params)
        >>> len(sign)
        32
    """
    # 排序参数
    sorted_params = _ksort(params)

    # 构造签名字符串
    sign_str = ""
    for key, value in sorted_params.items():
        if value is not None and (value or value == 0):
            if isinstance(value, list):
                # 列表类型展开为 key[]=value1&key[]=value2
                for item in value:
                    sign_str += f"{key}[]={item}&"
            else:
                # 基本类型直接追加
                sign_str += f"{key}={value}&"

    # 移除末尾的 &
    if sign_str:
        sign_str = sign_str[:-1]

    # 追加密钥
    sign_str += "dbbc3dd73364b4084c3a69346e0ce2b2"

    # 计算 MD5
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest()
