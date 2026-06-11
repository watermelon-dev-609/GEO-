"""统一错误码定义"""

from __future__ import annotations

ERROR_CODES: dict[str, dict] = {
    # 网络/连接类
    "GEO_001": {
        "message": "网络连接失败",
        "suggestion": "请检查网络连接，确认是否能访问外部API。如使用代理，请检查代理设置。",
        "severity": "high",
    },
    "GEO_002": {
        "message": "API请求超时",
        "suggestion": "AI平台响应较慢，已自动重试。如持续超时，请检查API平台状态或切换其他平台。",
        "severity": "medium",
    },
    "GEO_003": {
        "message": "API连接被拒绝",
        "suggestion": "目标API服务不可用，请检查API地址是否正确，或检查防火墙是否放行443端口。",
        "severity": "high",
    },

    # 认证/配额类
    "GEO_010": {
        "message": "API Key无效或已过期",
        "suggestion": "请在「配置API Key」中重新输入有效的API Key。确认API Key未过期、未用完额度。",
        "severity": "high",
    },
    "GEO_011": {
        "message": "API调用配额已用尽",
        "suggestion": "当月API调用次数已达上限。请等待下月重置，或在设置中提高限额。",
        "severity": "high",
    },
    "GEO_012": {
        "message": "API调用频率过高",
        "suggestion": "请求过于频繁，已被限流。系统将自动等待后重试。请减少并发操作。",
        "severity": "medium",
    },
    "GEO_013": {
        "message": "API账户余额不足",
        "suggestion": "请在对应AI平台的充值中心充值。推荐DeepSeek（性价比最高）。",
        "severity": "high",
    },

    # 内容类
    "GEO_020": {
        "message": "文本内容过短",
        "suggestion": "输入文本需≥50字符。请提供更完整的企业介绍、产品说明或服务描述。",
        "severity": "low",
    },
    "GEO_021": {
        "message": "文本包含不支持的字符",
        "suggestion": "文本中包含无法解析的特殊字符。请移除emoji、乱码或非中文内容后重试。",
        "severity": "low",
    },
    "GEO_022": {
        "message": "内容合规检测未通过",
        "suggestion": "文案中包含广告法禁词。请根据检测结果修改后重新提交。",
        "severity": "medium",
    },

    # 生成/评测类
    "GEO_030": {
        "message": "AI生成内容为空",
        "suggestion": "AI平台返回了空内容。请尝试切换其他AI平台，或调整文案后重试。",
        "severity": "high",
    },
    "GEO_031": {
        "message": "AI生成质量不达标",
        "suggestion": "生成内容可能包含幻觉或格式异常。请尝试重新生成，或提供更详细的五维信息。",
        "severity": "medium",
    },
    "GEO_032": {
        "message": "评测数据不足",
        "suggestion": "评测需要≥50字符的文案。请先完成GEO优化后再评测。",
        "severity": "low",
    },
    "GEO_033": {
        "message": "信源一致性过低",
        "suggestion": "AI生成内容与原文案严重偏离（可能产生了幻觉）。请重新优化，确保五维信息完整。",
        "severity": "high",
    },

    # 系统类
    "GEO_040": {
        "message": "模型未加载",
        "suggestion": "向量模型加载失败。请检查网络是否能访问HuggingFace镜像，或手动下载模型。",
        "severity": "high",
    },
    "GEO_041": {
        "message": "文件读写失败",
        "suggestion": "数据目录权限不足或磁盘空间满。请检查data目录的读写权限。",
        "severity": "high",
    },
    "GEO_042": {
        "message": "配置加载失败",
        "suggestion": "配置文件格式错误。请检查settings.yaml和api_keys.yaml的YAML格式。",
        "severity": "high",
    },

    # 批量处理类
    "GEO_050": {
        "message": "批量任务部分失败",
        "suggestion": "部分文案处理失败。请检查失败项的文案内容是否符合要求（≥50字符，中文内容）。",
        "severity": "medium",
    },
    "GEO_051": {
        "message": "批量任务已取消",
        "suggestion": "任务已被手动取消。可重新发起批量处理。",
        "severity": "low",
    },
}


def get_error_info(code: str) -> dict:
    """获取错误码对应的信息"""
    info = ERROR_CODES.get(code)
    if info:
        return dict(info)
    return {
        "message": f"未知错误 ({code})",
        "suggestion": "请截图此错误信息并联系技术支持。",
        "severity": "medium",
    }


def get_error_code_by_category(category: str) -> str:
    """根据异常类别返回对应错误码"""
    mapping = {
        "network": "GEO_001",
        "timeout": "GEO_002",
        "connection": "GEO_003",
        "auth": "GEO_010",
        "quota": "GEO_011",
        "rate_limit": "GEO_012",
        "content_short": "GEO_020",
        "compliance": "GEO_022",
        "empty_response": "GEO_030",
        "low_quality": "GEO_031",
        "source_mismatch": "GEO_033",
        "system": "GEO_040",
    }
    return mapping.get(category, "GEO_001")
