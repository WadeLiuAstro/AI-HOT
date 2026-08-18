// 精选流聚合：GET /api/featured?category=&q=
// 聚合 /api/public/items 前 3 页，仅保留 selected 精选，归一化分类后按分类/关键词过滤
import { NextResponse } from "next/server";
import { normalizeCategory } from "../../_lib/format";
import type { ItemsPage, NewsItem } from "../../_lib/types";
import { upstreamJSON } from "../../_lib/upstream";

const MAX_PAGES = 3;

async function fetchSelectedPool(): Promise<NewsItem[] | null> {
  const pool: NewsItem[] = [];
  let cursor: string | undefined;
  for (let i = 0; i < MAX_PAGES; i++) {
    const params = new URLSearchParams({ limit: "50" });
    if (cursor) params.set("cursor", cursor);
    const res = await upstreamJSON(`/api/public/items?${params}`);
    if (!res.ok) return i > 0 ? pool : null; // 翻页中途失败时保留已抓部分
    const page = res.data as ItemsPage;
    pool.push(...(page.items || []));
    if (!page.hasNext || !page.nextCursor) break;
    cursor = page.nextCursor;
  }
  return pool;
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const category = url.searchParams.get("category") || "";
  const q = (url.searchParams.get("q") || "").trim().toLowerCase();

  const pool = await fetchSelectedPool();
  if (!pool) {
    return NextResponse.json({ items: [], live: false }, { status: 200 });
  }

  let items: NewsItem[] = pool.filter((it) => it.selected !== false);
  items = items.map((it) => ({
    ...it,
    id: `aihot:${it.id}`,
    sourceType: String(it.source || "").startsWith("公众号：") ? "wechat" : "aihot",
    category: normalizeCategory(it.category),
  }));
  if (category) items = items.filter((it) => it.category === category);
  if (q) {
    items = items.filter(
      (it) =>
        (it.title || "").toLowerCase().includes(q) ||
        (it.summary || "").toLowerCase().includes(q),
    );
  }
  items.sort(
    (a, b) => new Date(b.publishedAt || 0).getTime() - new Date(a.publishedAt || 0).getTime(),
  );

  return NextResponse.json(
    { items, live: true },
    { headers: { "Cache-Control": "s-maxage=60, stale-while-revalidate=300" } },
  );
}
