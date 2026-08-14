#!/usr/bin/env python3
"""fetch_weread.py — 基于微信读书的公众号订阅式抓取（主信源，替代搜狗的完整性/及时性短板）。

原理:
    借用 wewe-rss 开源项目的中转服务协议（weread.111965.xyz）：用备用微信读书账号
    的 token 调「公众号文章列表」接口，按账号拉时间线——该号每篇文章都能拿到，
    无搜狗式的索引滞后与相关度排序问题。

用法:
    # CI 抓取（token 由环境变量 WEREAD_TOKEN 注入）
    python3 scripts/fetch_weread.py --mapping weread_mps.json --out wechat_items.json

    # 本地：把公众号文章分享链接解析成 mpId 并写入映射表（需 token）
    python3 scripts/fetch_weread.py --resolve "https://mp.weixin.qq.com/s/xxxx"

    # 干跑：只解析映射表不发请求
    python3 scripts/fetch_weread.py --dry-run

错误语义:
    401 = token 失效（写 state 的 weread_token_expired，workflow 告警提示重新扫码）
    429 = 频控小黑屋（当日跳过该号）

纯标准库实现，Windows / Linux / macOS 均可运行。
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

PLATFORM_URL = "https://weread.111965.xyz"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


class WeReadError(Exception):
    """中转服务返回的错误，status 携带 HTTP 状态码（网络异常时为 0）。"""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


def http_json(url: str, token: str = "", vid: str = "", method: str = "GET",
              body: dict | None = None, timeout: int = 30) -> dict | list:
    headers = {"User-Agent": UA, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if vid:
        headers["xid"] = str(vid)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # 401/429 等需要区分状态码
        raise WeReadError(f"HTTP {exc.code}: {exc.reason}", status=exc.code) from exc
    except Exception as exc:  # noqa: BLE001 - 网络层异常统一包装
        raise WeReadError(str(exc)) from exc


def load_mapping(path: str) -> list[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [a for a in data.get("accounts") or [] if a.get("name") and a.get("mpId")]
    except (OSError, json.JSONDecodeError):
        return []


def resolve_url(base: str, token: str, vid: str, url: str) -> list[dict]:
    """公众号文章分享链接 -> 公众号信息（id/name/intro/cover）。"""
    return http_json(f"{base}/api/v2/platform/wxs2mp", token=token, vid=vid,
                     method="POST", body={"url": url.strip()})


def fetch_articles(base: str, token: str, vid: str, mp_id: str, page: int = 1) -> list[dict]:
    """公众号文章列表（时间倒序），返回 [{id, title, picUrl, publishTime}]。"""
    result = http_json(f"{base}/api/v2/platform/mps/{mp_id}/articles",
                       token=token, vid=vid, method="GET")
    # 接口按 query 传 page；GET 无 query 时服务端默认第一页
    _ = page  # 预留分页参数（当前窗口 7 天一页足够）
    return result if isinstance(result, list) else []


def build_item(raw: dict, mp_name: str) -> dict:
    """中转服务文章 -> wechat_items.json 兼容 schema（与 fetch_wechat.py 产出对齐）。"""
    url = f"https://mp.weixin.qq.com/s/{raw['id']}"
    ts = int(raw.get("publishTime") or 0)
    published_iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z") if ts else ""
    return {
        "title": raw.get("title") or "",
        "summary": "",  # 接口无摘要字段；不逐篇抓正文，避免放大请求量
        "source": f"公众号：{mp_name}",
        "publishedAt": published_iso,
        "url": url,
        "id": "wechat:" + hashlib.md5(url.encode("utf-8")).hexdigest()[:12],
    }


def merge_items(new_items: list[dict], out_path: str, since_ts: int) -> list[dict]:
    """与上次抓取结果（可能含搜狗路线条目）做窗口内增量合并。

    去重键 = （账号，标题）；超过时间窗口的旧条目自然淘汰。
    逻辑与 fetch_wechat.py 保持一致（独立复制，避免 CI 中的跨文件导入依赖）。
    """
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            old = json.load(f).get("items") or []
    except (OSError, json.JSONDecodeError):
        old = []

    def published_ts(it: dict) -> float:
        try:
            return datetime.fromisoformat((it.get("publishedAt") or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    key = lambda it: ((it.get("source") or ""), (it.get("title") or "").strip())
    result: dict[tuple, dict] = {key(it): it for it in old if published_ts(it) >= since_ts}
    for it in new_items:
        result.setdefault(key(it), it)
    kept = len([1 for it in old if published_ts(it) >= since_ts])
    print(f"增量合并：旧窗口内 {kept} 条 + 本次微信读书 {len(new_items)} 条 → 共 {len(result)} 条")
    return list(result.values())


def cmd_resolve(args) -> int:
    """解析公众号文章链接并把结果写入映射表。"""
    token = args.token or os.environ.get("WEREAD_TOKEN", "")
    if not token:
        print("缺少 token：请设置环境变量 WEREAD_TOKEN 或传 --token", file=sys.stderr)
        return 1
    base = args.platform.rstrip("/")
    try:
        mps = resolve_url(base, token, "", args.resolve)
    except WeReadError as exc:
        print(f"解析失败: {exc}", file=sys.stderr)
        return 1
    if not mps:
        print("未解析到公众号（链接无效或微信读书未收录）", file=sys.stderr)
        return 1

    try:
        with open(args.mapping, "r", encoding="utf-8") as f:
            mapping = json.load(f)
    except (OSError, json.JSONDecodeError):
        mapping = {"accounts": []}
    existing = {a.get("name"): a for a in mapping.get("accounts") or []}

    for mp in mps:
        name, mp_id = mp.get("name") or "", mp.get("id") or ""
        if not name or not mp_id:
            continue
        if name in existing:
            existing[name]["mpId"] = mp_id
            print(f"更新: {name} -> {mp_id}")
        else:
            entry = {"name": name, "mpId": mp_id}
            mapping.setdefault("accounts", []).append(entry)
            existing[name] = entry
            print(f"新增: {name} -> {mp_id}")

    with open(args.mapping, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=1)
    print(f"已写入 {args.mapping}（当前 {len(mapping.get('accounts') or [])} 个账号）")
    return 0


def cmd_fetch(args) -> int:
    mapping = load_mapping(args.mapping)
    if args.dry_run:
        print(f"[dry-run] 映射表 {args.mapping}: {len(mapping)} 个已映射账号")
        for a in mapping:
            print(f"  - {a['name']} ({a['mpId']})")
        return 0
    if not mapping:
        print(f"映射表为空或不可读（{args.mapping}），跳过微信读书抓取（搜狗路线兜底）")
        _write_covered(args.covered_out, [])
        return 0

    token = args.token or os.environ.get("WEREAD_TOKEN", "")
    state_patch = {"weread_token_expired": False, "weread_ok_accounts": 0,
                   "weread_fail_accounts": 0, "weread_items": 0}
    if not token:
        print("缺少 WEREAD_TOKEN，跳过微信读书抓取（搜狗路线兜底）")
        _patch_state(args.state, state_patch)
        _write_covered(args.covered_out, [])
        return 0

    base = args.platform.rstrip("/")
    since_ts = int(time.time()) - args.days * 86400
    items: list[dict] = []
    covered: list[str] = []  # 本次实际拉到文章的账号，搜狗兜底只跳过这些
    for acc in mapping:
        name, mp_id = acc["name"], acc["mpId"]
        try:
            articles = fetch_articles(base, token, "", mp_id)
            picked = 0
            for raw in articles:
                if int(raw.get("publishTime") or 0) < since_ts:
                    continue  # 时间倒序，早于窗口即可停止
                if picked >= args.per_account:
                    break
                items.append(build_item(raw, name))
                picked += 1
            state_patch["weread_ok_accounts"] += 1
            if picked > 0:
                covered.append(name)
            print(f"  [OK] {name}: {picked} 篇")
        except WeReadError as exc:
            if exc.status == 401:
                print("token 已失效（401），终止本次微信读书抓取，请重新扫码更新 WEREAD_TOKEN", file=sys.stderr)
                state_patch["weread_token_expired"] = True
                break
            if exc.status == 429:
                print(f"  [SKIP] {name}: 频控小黑屋（429），今日跳过", file=sys.stderr)
            else:
                print(f"  [FAIL] {name}: {exc}", file=sys.stderr)
            state_patch["weread_fail_accounts"] += 1
        time.sleep(1.5)

    state_patch["weread_items"] = len(items)
    merged = merge_items(items, args.out, since_ts) if items else _keep_old(args.out, since_ts)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"fetchedAt": now, "ok": len(merged) > 0, "items": merged},
                  f, ensure_ascii=False, indent=1)
    _patch_state(args.state, state_patch)
    _write_covered(args.covered_out, covered)
    print(f"微信读书源完成：成功 {state_patch['weread_ok_accounts']}/{len(mapping)} 账号，"
          f"抓取 {len(items)} 篇，合并后共 {len(merged)} 条")
    return 0


def _write_covered(path: str, names: list[str]) -> None:
    """写入本次实际覆盖的账号名列表（搜狗兜底只跳过这些账号，防两头落空）。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"accounts": names}, f, ensure_ascii=False, indent=1)
    except OSError as exc:
        print(f"覆盖清单写入失败（不影响抓取）: {exc}", file=sys.stderr)


def _keep_old(out_path: str, since_ts: int) -> list[dict]:
    """本次无新文章时保留旧文件窗口内条目（不丢数据）。"""
    try:
        with open(out_path, "r", encoding="utf-8") as f:
            old = json.load(f).get("items") or []
    except (OSError, json.JSONDecodeError):
        return []

    def published_ts(it: dict) -> float:
        try:
            return datetime.fromisoformat((it.get("publishedAt") or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    return [it for it in old if published_ts(it) >= since_ts]


def _patch_state(state_path: str, patch: dict) -> None:
    state = {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    state.update(patch)
    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=1)
    except OSError as exc:
        print(f"状态写入失败（不影响抓取）: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="基于微信读书的公众号订阅式抓取")
    parser.add_argument("--token", default="", help="微信读书 token（默认读环境变量 WEREAD_TOKEN）")
    parser.add_argument("--mapping", default="weread_mps.json", help="账号名→mpId 映射表")
    parser.add_argument("--out", default="wechat_items.json")
    parser.add_argument("--state", default="wechat_state.json")
    parser.add_argument("--days", type=int, default=7, help="只保留近 N 天文章（默认 7）")
    parser.add_argument("--per-account", type=int, default=10, help="每账号最多保留篇数（默认 10）")
    parser.add_argument("--platform", default=PLATFORM_URL, help="中转服务基地址")
    parser.add_argument("--covered-out", default="weread_covered.json",
                        help="本次实际覆盖账号清单输出路径（搜狗兜底只跳过这些账号）")
    parser.add_argument("--resolve", default="", help="解析公众号文章分享链接并写入映射表（本地用）")
    parser.add_argument("--dry-run", action="store_true", help="只解析映射表不发请求")
    args = parser.parse_args()

    if args.resolve:
        return cmd_resolve(args)
    return cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())
