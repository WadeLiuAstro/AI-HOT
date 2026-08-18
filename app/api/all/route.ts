// 全部 AI 动态聚合：GET /api/all
// 聚合 /api/public/items 前 3 页全量条目，归一化分类并统计标签，供前端标签筛选
import { NextResponse } from "next/server";
import { normalizeCategory } from "../../_lib/format";
import type { ItemsPage, NewsItem } from "../../_lib/types";
import { upstreamJSON } from "../../_lib/upstream";

const MAX_PAGES = 3;

export async function GET() {
  const pool: NewsItem[] = [];
  let cursor: string | undefined;
  let live = false;
  for (let i = 0; i < MAX_PAGES; i++) {
    const params = new URLSearchParams({ limit: "50" });
    if (cursor) params.set("cursor", cursor);
    const res = await upstreamJSON(`/api/public/items?${params}`);
    if (!res.ok) break;
    live = true;
    const page = res.data as ItemsPage;
    pool.push(...(page.items || []));
    if (!page.hasNext || !page.nextCursor) break;
    cursor = page.nextCursor;
  }

  const items: NewsItem[] = pool.map((it) => ({
    ...it,
    id: `aihot:${it.id}`,
    sourceType: String(it.source || "").startsWith("公众号：") ? "wechat" : "aihot",
    category: normalizeCategory(it.category),
  }));
  items.sort(
    (a, b) => new Date(b.publishedAt || 0).getTime() - new Date(a.publishedAt || 0).getTime(),
  );

  const counter = new Map<string, number>();
  for (const it of items) counter.set(it.category || "行业动态", (counter.get(it.category || "行业动态") || 0) + 1);
  const tags = [...counter.entries()]
    .map(([tag, count]) => ({ tag, count }))
    .sort((a, b) => b.count - a.count);

  return NextResponse.json(
    { items, tags, live },
    { headers: { "Cache-Control": "s-maxage=60, stale-while-revalidate=300" } },
  );
}
