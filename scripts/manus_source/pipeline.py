"""pipeline.py — Manus 两阶段采集的阶段 B：按批提取正文（离线可测，纯标准库）。

职责：
  - 从三组发现结果汇总 complete 文章，跨镜像 URL 去重（保留 provenance 最完整者）
  - 按 batch_size 分批；已有合法原始批次的 URL 直接复用（断点续跑）
  - 调 ManusClient 提交正文任务，contracts 本地门槛校验
  - 原始正文只写运行时 work 目录；诊断文件剥离 content_text
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import contracts

CONTENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "target_date": {"type": "string"},
        "articles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "account_name": {"type": "string"},
                    "article_url": {"type": "string"},
                    "title": {"type": "string"},
                    "published_date": {"type": "string"},
                    "content_text": {"type": "string"},
                    "content_status": {"type": "string", "enum": ["complete", "failed"]},
                    "content_truncated": {"type": "boolean"},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["account_name", "article_url", "title", "published_date",
                             "content_text", "content_status", "content_truncated", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["target_date", "articles"],
    "additionalProperties": False,
}

CONTENT_BRIEF_TEMPLATE = ("本批共 {count} 篇文章；逐篇打开并提取正文，"
                          "严格遵守附件 prompt 的二次核对与失败判定规则。\n\n文章清单：\n{listing}")


@dataclass
class ContentResult:
    ok_articles: list[dict] = field(default_factory=list)     # 通过本地门槛、可进入模型加工
    failed: list[dict] = field(default_factory=list)          # [{article_url, account_name, reason}]
    batches_run: int = 0
    batches_resumed: int = 0
    duplicates_dropped: int = 0


def plan_batches(discoveries: dict[str, dict], batch_size: int) -> tuple[list[list[dict]], int]:
    """汇总各组 complete 文章 → 跨镜像 URL 去重 → 分批。返回 (批次, 被去重丢弃数)。"""
    all_complete: list[dict] = []
    for group in sorted(discoveries):  # 固定顺序，保证批次划分可重复
        all_complete.extend(a for a in discoveries[group]["articles"]
                            if a.get("extraction_status") == "complete")
    seen: dict[str, dict] = {}
    dropped = 0
    for art in all_complete:
        url = art["article_url"]
        if url in seen:
            dropped += 1  # 先来者优先（组序固定）；跨镜像保留 provenance 完整的第一条
            continue
        seen[url] = art
    unique = list(seen.values())
    batches = [unique[i:i + batch_size] for i in range(0, len(unique), batch_size)]
    return batches, dropped


def render_content_prompt(template_text: str, max_content_chars: int) -> str:
    if "{{MAX_CONTENT_CHARS}}" not in template_text:
        raise RuntimeError("正文 prompt 缺少 {{MAX_CONTENT_CHARS}} 占位符")
    return template_text.replace("{{MAX_CONTENT_CHARS}}", str(max_content_chars))


def render_batch_listing(batch: list[dict]) -> str:
    lines = []
    for i, a in enumerate(batch, 1):
        lines.append(f"{i}. account_name：{a['account_name']}")
        lines.append(f"   - article_url：{a['article_url']}")
        lines.append(f"   - title：{a['title']}")
        lines.append(f"   - published_date：{a['published_date']}")
    return "\n".join(lines)


def _raw_batch_paths(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.glob("content-batch-*.json"))


def load_resumed_records(raw_dir: Path, target_date: str, expected_titles: dict[str, str],
                         min_content_chars: int) -> dict[str, dict]:
    """断点续跑：读取同一日期已有原始批次，返回可复用的 {url: 文章记录}。

    整个批次文件必须通过契约校验才可复用；任何损坏都放弃该文件（重跑该批）。
    """
    resumed: dict[str, dict] = {}
    for path in _raw_batch_paths(raw_dir):
        try:
            with open(path, "r", encoding="utf-8") as f:
                batch = json.load(f)
            ok, _failed = contracts.validate_content_batch(batch, target_date, expected_titles,
                                                           min_content_chars)
        except (OSError, json.JSONDecodeError, contracts.ContractError):
            continue
        for art in batch.get("articles", []):
            resumed[art["article_url"]] = art
    return resumed


def strip_content_for_diagnostics(batch: dict) -> dict:
    """生成不含正文的诊断记录：URL、状态、长度、哈希、原因。"""
    entries = []
    for a in batch.get("articles", []):
        text = a.get("content_text") or ""
        entries.append({
            "account_name": a.get("account_name"),
            "article_url": a.get("article_url"),
            "title": a.get("title"),
            "content_status": a.get("content_status"),
            "content_truncated": a.get("content_truncated"),
            "content_chars": len(text),
            "content_sha256": contracts.content_sha256(text) if text else None,
            "note": a.get("note"),
        })
    return {"target_date": batch.get("target_date"), "articles": entries}


def _next_batch_index(raw_dir: Path) -> int:
    indexes = []
    for path in _raw_batch_paths(raw_dir):
        m = re.search(r"content-batch-(\d+)\.json$", path.name)
        if m:
            indexes.append(int(m.group(1)))
    return (max(indexes) + 1) if indexes else 1


class ContentPipeline:
    """阶段 B 编排器。client 仅需实现 create_crawl_task / wait_for_structured_result。"""

    def __init__(self, client, prompt_template_text: str, target_date: str, work_dir: Path,
                 batch_size: int = 4, max_content_chars: int = 20000,
                 min_content_chars: int = 100):
        self.client = client
        self.prompt_text = render_content_prompt(prompt_template_text, max_content_chars)
        self.target_date = target_date
        self.raw_dir = Path(work_dir) / target_date / "raw"
        self.diag_dir = Path(work_dir) / "diagnostics" / target_date
        self.batch_size = batch_size
        self.min_content_chars = min_content_chars

    def run(self, discoveries: dict[str, dict]) -> ContentResult:
        result = ContentResult()
        batches, result.duplicates_dropped = plan_batches(discoveries, self.batch_size)
        expected_titles = {a["article_url"]: a["title"]
                           for batch in batches for a in batch}
        resumed = load_resumed_records(self.raw_dir, self.target_date,
                                       expected_titles, self.min_content_chars)

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.diag_dir.mkdir(parents=True, exist_ok=True)
        batch_index = _next_batch_index(self.raw_dir)

        for batch in batches:
            urls = [a["article_url"] for a in batch]
            if all(u in resumed for u in urls):
                # 断点续跑：该批所有 URL 已有合法记录，直接复用
                result.batches_resumed += 1
                batch_articles = [resumed[u] for u in urls]
            else:
                listing = render_batch_listing(batch)
                brief = CONTENT_BRIEF_TEMPLATE.format(count=len(batch), listing=listing)
                task = self.client.create_crawl_task(
                    prompt_text=self.prompt_text,
                    source_group="content",
                    target_date=self.target_date,
                    title=f"AI 新闻正文提取 {self.target_date} · batch{batch_index:02d}",
                    task_brief=brief,
                    output_schema=CONTENT_OUTPUT_SCHEMA,
                )
                print(f"[content] batch{batch_index:02d} Manus task created: {task.task_url}",
                      flush=True)
                payload = self.client.wait_for_structured_result(task.task_id)
                if not isinstance(payload.get("articles"), list):
                    raise contracts.ContractError(f"batch{batch_index:02d} 正文结果缺少 articles")
                # 批次结果必须与请求清单 URL 一一对应（不漏不增）
                got_urls = {a.get("article_url") for a in payload["articles"]}
                if got_urls != set(urls):
                    raise contracts.ContractError(
                        f"batch{batch_index:02d} 正文结果 URL 集合与请求清单不一致："
                        f"缺少 {sorted(set(urls) - got_urls)} 多出 {sorted(got_urls - set(urls))}")
                raw_path = self.raw_dir / f"content-batch-{batch_index:02d}.json"
                raw_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                (self.diag_dir / f"content-batch-{batch_index:02d}.json").write_text(
                    json.dumps(strip_content_for_diagnostics(payload), ensure_ascii=False, indent=2),
                    encoding="utf-8")
                result.batches_run += 1
                batch_index += 1
                batch_articles = payload["articles"]

            batch_obj = {"target_date": self.target_date, "articles": batch_articles}
            ok, failed = contracts.validate_content_batch(batch_obj, self.target_date,
                                                          expected_titles, self.min_content_chars)
            result.ok_articles.extend(ok)
            result.failed.extend(failed)

        # 诊断汇总（无正文）
        summary = {
            "target_date": self.target_date,
            "batches_run": result.batches_run,
            "batches_resumed": result.batches_resumed,
            "duplicates_dropped": result.duplicates_dropped,
            "ok_count": len(result.ok_articles),
            "failed": result.failed,
        }
        (self.diag_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return result
