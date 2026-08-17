"""llm_common.py — OpenAI-compatible /chat/completions 调用与 JSON 输出解析（稳定函数）。

从 tag_news.py 抽取的公共能力，供打标签（tag_news）与正文加工（enrich_news）复用。
纯标准库实现。
"""
import json
import os
import re
import urllib.request


def call_llm(tx: dict, system: str, user: str, timeout_seconds: int | None = None) -> str:
    """OpenAI 兼容 /chat/completions，返回原始文本。缺 key/网络错误抛异常由上层处理。

    timeout_seconds 缺省沿用 taxonomy model 配置；长正文加工可传入更大值。
    """
    m = tx["model"]
    api_key = os.environ.get(m["api_key_env"], "")
    if not api_key:
        raise RuntimeError(f"环境变量 {m['api_key_env']} 未配置")
    base = os.environ.get(m["api_base_env"], "") or m["default_base"]
    body = {
        "model": m["model"],
        "temperature": m.get("temperature", 0),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds or m.get("timeout_seconds", 20)) as resp:
        d = json.loads(resp.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"] or ""


def parse_output(text: str) -> dict | None:
    """json_object 模式输出 → 裸 JSON → markdown 围栏剥离；失败返回 None。"""
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return d if isinstance(d, dict) else None
