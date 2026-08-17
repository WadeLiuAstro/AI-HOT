#!/usr/bin/env python3
"""test_manus_pipeline.py — 阶段 B 正文采集编排离线单测（不发真实 Manus 请求）。

运行：python -m unittest tests.test_manus_pipeline -v
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from manus_source import contracts  # noqa: E402
from manus_source.pipeline import ContentPipeline, plan_batches  # noqa: E402

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "manus")
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "prompts", "manus_content.md")
TARGET_DATE = "2026-08-16"


def load_fixture(name: str) -> dict:
    with open(os.path.join(FIXTURE_DIR, name), "r", encoding="utf-8") as f:
        return json.load(f)


def all_discoveries() -> dict:
    return {
        "group_a": load_fixture("discovery-group-a.json"),
        "group_b": load_fixture("discovery-group-b.json"),
        "group_c": load_fixture("discovery-group-c.json"),
    }


class FakeContentClient:
    """按请求清单（从 task brief 解析 URL）从正文夹具中回填结果。"""

    def __init__(self, fixture: dict, target_date: str):
        self.by_url = {a["article_url"]: a for a in fixture["articles"]}
        self.target_date = target_date
        self.created = []
        self._pending_urls: list[str] = []

    def create_crawl_task(self, prompt_text, source_group, target_date, title, task_brief,
                          output_schema=None):
        urls = re.findall(r"article_url：(\S+)", task_brief)
        self.created.append(urls)
        self._pending_urls = urls

        class _Task:
            task_id = f"fake-{len(self.created)}"
            task_url = f"https://manus.app/task/fake-{len(self.created)}"
        return _Task()

    def wait_for_structured_result(self, task_id):
        articles = [dict(self.by_url[u]) for u in self._pending_urls if u in self.by_url]
        return {"target_date": self.target_date, "articles": articles}


class AssertNotCalledClient:
    def create_crawl_task(self, **kw):
        raise AssertionError("断点续跑不应再创建 Manus 任务")

    def wait_for_structured_result(self, task_id):
        raise AssertionError("断点续跑不应再轮询 Manus 任务")


class TestPlanBatches(unittest.TestCase):
    def test_dedup_and_chunking(self):
        batches, dropped = plan_batches(all_discoveries(), batch_size=4)
        self.assertEqual(dropped, 1)  # ZPotential 与 FounderPark 同 URL
        urls = [a["article_url"] for b in batches for a in b]
        self.assertEqual(len(urls), 11)
        self.assertEqual(len(set(urls)), 11)
        self.assertEqual([len(b) for b in batches], [4, 4, 3])


class TestContentPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="manus-pipeline-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.prompt_text = open(PROMPT_PATH, encoding="utf-8").read()

    def make_pipeline(self, client):
        return ContentPipeline(client, self.prompt_text, TARGET_DATE, self.tmp,
                               batch_size=4, max_content_chars=20000, min_content_chars=100)

    def test_full_run_end_to_end(self):
        client = FakeContentClient(load_fixture("content-batch.json"), TARGET_DATE)
        result = self.make_pipeline(client).run(all_discoveries())
        self.assertEqual(result.duplicates_dropped, 1)
        self.assertEqual(result.batches_run, 3)
        self.assertEqual(result.batches_resumed, 0)
        self.assertEqual(len(result.ok_articles), 9)
        self.assertEqual(len(result.failed), 2)
        reasons = {f["article_url"]: f["reason"] for f in result.failed}
        self.assertIn("风控", reasons["https://news.qq.com/rain/a/20260816A01GEEK000"])
        self.assertIn("不一致", reasons["https://news.qq.com/rain/a/20260816A01VC00000"])
        # ok 文章均带合法正文
        for art in result.ok_articles:
            self.assertGreaterEqual(len(art["content_text"]), 100)
        # 原始与诊断文件都已落盘
        raw_dir = os.path.join(self.tmp, TARGET_DATE, "raw")
        diag_dir = os.path.join(self.tmp, "diagnostics", TARGET_DATE)
        self.assertEqual(sorted(os.listdir(raw_dir))[:3],
                         ["content-batch-01.json", "content-batch-02.json", "content-batch-03.json"])
        diag_text = open(os.path.join(diag_dir, "content-batch-01.json"), encoding="utf-8").read()
        self.assertNotIn("content_text", diag_text)  # 诊断不含正文
        summary = json.load(open(os.path.join(diag_dir, "summary.json"), encoding="utf-8"))
        self.assertEqual(summary["ok_count"], 9)

    def test_full_resume_avoids_all_manus_calls(self):
        fixture = load_fixture("content-batch.json")
        self.make_pipeline(FakeContentClient(fixture, TARGET_DATE)).run(all_discoveries())
        result = self.make_pipeline(AssertNotCalledClient()).run(all_discoveries())
        self.assertEqual(result.batches_resumed, 3)
        self.assertEqual(result.batches_run, 0)
        self.assertEqual(len(result.ok_articles), 9)

    def test_partial_resume_only_reruns_missing_batch(self):
        fixture = load_fixture("content-batch.json")
        self.make_pipeline(FakeContentClient(fixture, TARGET_DATE)).run(all_discoveries())
        os.remove(os.path.join(self.tmp, TARGET_DATE, "raw", "content-batch-02.json"))
        client = FakeContentClient(fixture, TARGET_DATE)
        result = self.make_pipeline(client).run(all_discoveries())
        self.assertEqual(result.batches_resumed, 2)
        self.assertEqual(result.batches_run, 1)
        self.assertEqual(len(result.ok_articles), 9)

    def test_corrupted_batch_file_is_ignored(self):
        fixture = load_fixture("content-batch.json")
        self.make_pipeline(FakeContentClient(fixture, TARGET_DATE)).run(all_discoveries())
        bad_path = os.path.join(self.tmp, TARGET_DATE, "raw", "content-batch-99.json")
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write("{这不是合法 JSON")
        result = self.make_pipeline(AssertNotCalledClient()).run(all_discoveries())
        self.assertEqual(result.batches_resumed, 3)  # 损坏文件不影响合法批次复用

    def test_batch_result_url_mismatch_raises(self):
        class DroppingClient(FakeContentClient):
            def wait_for_structured_result(self, task_id):
                payload = super().wait_for_structured_result(task_id)
                payload["articles"] = payload["articles"][:-1]  # 故意漏一篇
                return payload

        client = DroppingClient(load_fixture("content-batch.json"), TARGET_DATE)
        with self.assertRaises(contracts.ContractError):
            self.make_pipeline(client).run(all_discoveries())

    def test_prompt_renders_max_chars(self):
        pipeline = self.make_pipeline(AssertNotCalledClient())
        self.assertIn("20000", pipeline.prompt_text)
        self.assertNotIn("{{MAX_CONTENT_CHARS}}", pipeline.prompt_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
