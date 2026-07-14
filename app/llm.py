from __future__ import annotations

import os

from .config import load_project_environment


load_project_environment()


SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_SILICONFLOW_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
# worker 在后台执行，允许模型获得更合理的响应窗口，但不会阻塞入站 API。
SILICONFLOW_TIMEOUT_SECONDS = 90.0


class SiliconFlowProviderError(RuntimeError):
    """硅基流动调用失败时使用的脱敏异常类型。"""


def call_siliconflow_json(system_prompt: str, user_prompt: str) -> str:
    """通过 OpenAI 兼容接口请求 JSON Mode，密钥只从环境变量读取。"""

    api_key = os.getenv("SILICONFLOW_API_KEY")
    if not api_key:
        raise SiliconFlowProviderError("SILICONFLOW_API_KEY is not configured")

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=SILICONFLOW_BASE_URL,
            timeout=SILICONFLOW_TIMEOUT_SECONDS,
            max_retries=0,
        )
        model = os.getenv("SILICONFLOW_MODEL", DEFAULT_SILICONFLOW_MODEL)
        request_params = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 512,
        }
        if model == DEFAULT_SILICONFLOW_MODEL:
            # V4 Flash 的 low/medium 会被 Provider 映射为 high，故显式使用最低有效档。
            request_params["reasoning_effort"] = "high"
        elif model in {"deepseek-ai/DeepSeek-V3.2", "Pro/deepseek-ai/DeepSeek-V3.2"}:
            # V3.2 支持关闭思考；业务仅需结构化草稿，优先降低排队和生成耗时。
            request_params["extra_body"] = {"enable_thinking": False}
        response = client.chat.completions.create(**request_params)
        content = response.choices[0].message.content
    except Exception as exc:
        # 不保留 Provider 原始异常，避免响应体或配置意外出现在 run 留痕中。
        raise SiliconFlowProviderError("siliconflow request failed") from exc

    if not isinstance(content, str) or not content.strip():
        raise SiliconFlowProviderError("siliconflow returned empty content")
    return content
