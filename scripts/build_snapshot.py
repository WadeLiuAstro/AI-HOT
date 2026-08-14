#!/usr/bin/env python3
"""build_snapshot.py — 抓取 aihot 公开 API，生成 AI HOT 仪表盘静态快照（单文件 HTML）。

用法:
    python3 scripts/build_snapshot.py [--out public/index.html]
        [--template templates/index.template.html]
        [--api-base https://aihot.virxact.com]
        [--wechat-json wechat_items.json]
        [--days 7]

流程:
    1. 分页抓取 /api/public/items（扁平条目流，天然去重）
    2. 合并公众号抓取结果（wechat_items.json，可选）：URL 归一化去重 + 关键词分类
    3. 日报 = 昨天 00:00 至今（以真实今天为基准，不再跟随最新数据日期）；周报 = 最新数据日期前 N 天
    4. 按六版块分组、全局连续编号、北京时间人话时间
    5. 用模板渲染出单文件 HTML（DATA 内嵌）

纯标准库实现，Windows / Linux / macOS 均可运行。
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

# 六版块固定顺序（与前端 SECTION_COLORS 对应）
SECTIONS = ["模型发布/更新", "产品发布/更新", "AI泛娱乐新闻", "行业动态", "论文研究", "技巧与观点"]

# API category -> 六版块
CATEGORY_MAP = {
    "ai-models": "模型发布/更新",
    "ai-products": "产品发布/更新",
    "industry": "行业动态",
    "paper": "论文研究",
    "tip": "技巧与观点",
}

BJ = timezone(timedelta(hours=8), name="Asia/Shanghai")
WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

MAX_PAGES = 20  # 分页上限（每页 50 条），防止死循环

# 公众号文章六版块分类规则（按顺序匹配，命中即归入；兜底「行业动态」）
WECHAT_CATEGORY_RULES = [
    ("模型发布/更新", ["模型", "开源", "权重", "参数", "benchmark", "评测", "GPT", "Qwen", "Kimi", "Claude", "Gemini", "DeepSeek", "GLM", "大模型", "多模态", "tokenizer"]),
    ("论文研究", ["论文", "paper", "arxiv", "SOTA", "研究", "基准测试"]),
    ("AI泛娱乐新闻", ["娱乐", "游戏", "影视", "视频生成", "音乐", "虚拟人", "数字人"]),
    ("产品发布/更新", ["功能", "App", "Agent", "agent", "工具", "平台", "上线", "API", "接入", "助手", "Copilot", "升级", "插件", "组件"]),
    ("行业动态", ["融资", "投资", "估值", "市场", "监管", "政策", "诉讼", "IPO", "营收", "财报", "合作", "战略"]),
]


def classify_wechat(item: dict) -> str:
    """公众号文章按关键词规则归入六版块。"""
    text = ((item.get("title") or "") + " " + (item.get("summary") or "")).lower()
    for label, kws in WECHAT_CATEGORY_RULES:
        if any(k.lower() in text for k in kws):
            return label
    return "技巧与观点"


def norm_url(url: str) -> str:
    """URL 归一化（去 query 参数），用于跨源去重。

    例外：mp.weixin.qq.com 链接不剥 query —— 微信文章的唯一标识在 query 里
    （__biz/mid/sn 或 signature），剥掉后所有文章都变成 "mp.weixin.qq.com/s"，
    任意一条微信链接存在就会误伤拦截全部公众号文章（实测 bug）。
    """
    url = (url or "").rstrip("/").lower()
    if "mp.weixin.qq.com" in url:
        return url
    return url.split("?")[0]


def load_wechat(path: str) -> list[dict]:
    """读取 fetch_wechat.py 的产出（可缺省），返回已分类的公众号条目。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not data.get("ok"):
        return []
    out = []
    for it in data.get("items") or []:
        if not it.get("title") or not it.get("publishedAt"):
            continue
        it = dict(it)
        it["category"] = classify_wechat(it)
        it["sourceType"] = "wechat"
        it["mpName"] = (it.get("source") or "").replace("公众号：", "") or None
        out.append(it)
    return out


def fetch_items(api_base: str, since_bj: datetime) -> list[dict]:
    """分页抓取 items，直到覆盖 since_bj 之前的条目或翻完为止。

    注意：API 的翻页参数是 cursor（实测 nextCursor 会重复返回第一页）。
    """
    items: list[dict] = []
    cursor = None
    for _ in range(MAX_PAGES):
        params = {"limit": "50"}
        if cursor:
            params["cursor"] = cursor
        url = f"{api_base}/api/public/items?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        batch = data.get("items") or []
        items.extend(batch)
        if not data.get("hasNext") or not data.get("nextCursor"):
            break
        cursor = data["nextCursor"]
        # 本页最旧条目已早于窗口起点，无需继续翻页
        oldest = min((i.get("publishedAt") or "" for i in batch), default="")
        if oldest and to_bj(oldest) < since_bj:
            break
    return items


def to_bj(iso: str) -> datetime:
    """ISO8601 -> 北京时间 datetime（无法解析时返回遥远的过去）。"""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone(BJ)
    except (ValueError, AttributeError):
        return datetime(2000, 1, 1, tzinfo=BJ)


def fmt_date(d: datetime) -> str:
    return f"{d.year}年{d.month}月{d.day}日 {WEEKDAYS[d.weekday()]}"


def fmt_time_text(dt: datetime, today: datetime) -> str:
    """北京时间人话：今天 HH:MM / 昨天 HH:MM / M/D HH:MM"""
    day_diff = (today.date() - dt.date()).days
    hm = dt.strftime("%H:%M")
    if day_diff == 0:
        return f"今天 {hm}"
    if day_diff == 1:
        return f"昨天 {hm}"
    return f"{dt.month}/{dt.day} {hm}"


def build_item(raw: dict, num: int, today: datetime) -> dict:
    """API item -> 模板 item 结构。category 已是中文六版块时直通。"""
    published = to_bj(raw.get("publishedAt") or "")
    cat = raw.get("category") or ""
    category = cat if cat in SECTIONS else CATEGORY_MAP.get(cat, "行业动态")
    url = raw.get("url") or raw.get("permalink") or ""
    source = raw.get("source") or raw.get("attribution", {}).get("source") or "AI HOT"
    # 修复历史 bug：aihot 数据里 source 以「公众号：」开头的条目应标记为 wechat，
    # 否则前端「仅看公众号」筛选（sourceType===wechat）永远为空
    source_type = raw.get("sourceType") or ("wechat" if str(source).startswith("公众号：") else "aihot")
    return {
        "id": f"aihot:{raw.get('id')}" if not str(raw.get("id") or "").startswith("wechat:") else raw.get("id"),
        "title": raw.get("title") or "",
        "summary": raw.get("summary") or "",
        "url": url,
        "source": source,
        "sourceType": source_type,
        "category": category,
        "publishedAt": raw.get("publishedAt") or "",
        "score": raw.get("score") if isinstance(raw.get("score"), (int, float)) else None,
        "mpName": raw.get("mpName") if "mpName" in raw else None,
        "num": num,
        "timeText": fmt_time_text(published, today),
    }


def group_sections(items: list[dict]) -> list[dict]:
    """按六版块固定顺序分组。"""
    grouped = {s: [] for s in SECTIONS}
    for it in items:
        grouped.setdefault(it["category"], []).append(it)
    return [
        {"label": s, "count": len(grouped[s]), "items": grouped[s]}
        for s in SECTIONS
    ]


def build_view(view: str, items: list[dict], day: datetime, days: int, generated_at: datetime, mp_status: dict,
               time_ref: datetime | None = None, end: datetime | None = None) -> dict:
    """组装 daily / weekly 视图。items 需已按 publishedAt 降序。

    day: 视图锚点日（当天 00:00 北京时间）；窗口起点 = day - (days-1) 天
    end: 窗口右边界，默认 day+1 天（完整自然日）；日报传生成时刻实现「昨天 00:00 至今」
    time_ref: 「今天/昨天」标签参照时刻，默认锚点日；传生成时刻让标签相对真实今天
    """
    start = day - timedelta(days=days - 1)
    end = end or (day + timedelta(days=1))
    ref = time_ref or day
    raw = [i for i in items if start <= to_bj(i.get("publishedAt") or "") < end]
    raw.sort(key=lambda i: to_bj(i.get("publishedAt") or ""), reverse=True)
    converted = [build_item(it, idx + 1, ref) for idx, it in enumerate(raw)]
    sections = group_sections(converted)
    # 今日头条：日报取评分最高的一条（公众号文章无评分，不参与竞争）
    scored = [it for it in converted if isinstance(it.get("score"), (int, float))]
    lead = max(scored, key=lambda it: it["score"])["title"] if view == "daily" and scored else None
    return {
        "view": view,
        "range": {
            "start": start.date().isoformat(),
            "end": day.date().isoformat(),
            "label": f"{fmt_date(start)} 至 {fmt_date(day)}" if start.date() != day.date() else fmt_date(day),
        },
        "total": len(converted),
        "lead": lead,
        "sections": sections,
        "stats": [{"label": s["label"], "count": s["count"]} for s in sections],
        "mpStatus": mp_status,
        "generatedAt": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def render(template_path: str, out_path: str, data: dict) -> None:
    """读模板，替换 DATA 占位符，输出快照 HTML。"""
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()
    json_str = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    # 注意：不能用 re.sub 替换，替换串里的 \n 会被 re 解释成换行；用 str.replace 最安全
    placeholder = "const DATA = __DATA__;"
    if placeholder not in html:
        raise RuntimeError(f"模板中未找到 DATA 占位符（{template_path}）")
    new_html = html.replace(placeholder, f"const DATA = {json_str};", 1)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    print(f"已生成 {out_path}（{len(new_html)} 字节）")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 AI HOT 仪表盘静态快照")
    parser.add_argument("--out", default="public/index.html")
    parser.add_argument("--template", default="templates/index.template.html")
    parser.add_argument("--api-base", default="https://aihot.virxact.com")
    parser.add_argument("--wechat-json", default="wechat_items.json",
                        help="fetch_wechat.py 的产出（不存在时自动跳过）")
    parser.add_argument("--days", type=int, default=7, help="周报窗口天数（默认 7）")
    args = parser.parse_args()

    now_bj = datetime.now(BJ)
    try:
        items = fetch_items(args.api_base, now_bj - timedelta(days=args.days + 2))
    except Exception as exc:  # noqa: BLE001 - 抓取失败给出可读错误
        print(f"抓取失败: {exc}", file=sys.stderr)
        return 1
    if not items:
        print("抓取结果为空，放弃生成", file=sys.stderr)
        return 1

    # 按 publishedAt 降序，去重（同 id 保留最新）
    items.sort(key=lambda i: to_bj(i.get("publishedAt") or ""), reverse=True)
    seen: set[str] = set()
    deduped = []
    for i in items:
        key = i.get("id") or i.get("permalink") or ""
        if key in seen:
            continue
        seen.add(key)
        deduped.append(i)
    items = deduped

    # 合并公众号抓取结果：URL 归一化 + 标题去重，避免与 aihot 已有公众号内容重复
    wechat_items = load_wechat(args.wechat_json)
    if wechat_items:
        seen_urls = {norm_url(i.get("url") or i.get("permalink") or "") for i in items}
        seen_titles = {(i.get("title") or "").strip().lower() for i in items}
        merged = 0
        for w in wechat_items:
            if norm_url(w.get("url") or "") in seen_urls:
                continue
            if (w.get("title") or "").strip().lower() in seen_titles:
                continue
            items.append(w)
            merged += 1
        items.sort(key=lambda i: to_bj(i.get("publishedAt") or ""), reverse=True)
        print(f"公众号源：获取 {len(wechat_items)} 条，去重后合并 {merged} 条")
        mp_status = {"connected": True,
                     "note": f"已接入公众号追踪源（GitHub Actions 搜狗抓取，本次合并 {merged} 条新文章）"}
    else:
        mp_status = {"connected": False,
                     "note": "公众号追踪源本次未返回数据（搜狗抓取失败或无新文章），仅显示 aihot 数据"}

    latest_day = to_bj(items[0].get("publishedAt") or "").date()
    generated_at = datetime.now(timezone.utc)
    today_start = datetime.combine(now_bj.date(), datetime.min.time(), tzinfo=BJ)
    data = {
        # 日报：昨天 00:00 至今（今天没新文章时自然退化为昨日视图，标签相对真实今天）
        "daily": build_view("daily", items, today_start, 2, generated_at, mp_status,
                             time_ref=now_bj, end=now_bj),
        # 周报：窗口仍以最新数据日期为锚点（保持不变），标签相对真实今天
        "weekly": build_view("weekly", items, datetime.combine(latest_day, datetime.min.time(), tzinfo=BJ),
                              args.days, generated_at, mp_status, time_ref=now_bj),
    }
    render(args.template, args.out, data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
