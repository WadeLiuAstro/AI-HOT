// 客户端数据层：快照 + 本站 API 代理 + 降级策略
// 优先级：/snapshot.json（构建产物）→ /api/*（服务端代理 aihot API）→ 空态
import type {
  AllFeedResponse,
  HotTopicsResponse,
  ItemsPage,
  NewsItem,
  Snapshot,
} from "./types";

async function fetchJSON<T>(url: string): Promise<T> {
  const r = await fetch(url, { headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`HTTP ${r.status} for ${url}`);
  return (await r.json()) as T;
}

/** 构建时生成的快照数据（精选流 / 日报周报索引的数据源） */
export async function loadSnapshot(): Promise<Snapshot | null> {
  try {
    return await fetchJSON<Snapshot>("/snapshot.json");
  } catch {
    return null;
  }
}

/** 热点榜（代理 /api/v1/hot-topics，60s 服务端缓存） */
export async function loadHot(): Promise<HotTopicsResponse | null> {
  try {
    return await fetchJSON<HotTopicsResponse>("/api/hot");
  } catch {
    return null;
  }
}

/** 精选条目流（代理 /api/public/items，仅 selected，服务端过滤分类/关键词） */
export async function loadFeatured(category?: string | null, q?: string): Promise<NewsItem[]> {
  const params = new URLSearchParams();
  if (category) params.set("category", category);
  if (q) params.set("q", q);
  const data = await fetchJSON<{ items: NewsItem[]; live: boolean }>(`/api/featured?${params}`);
  return data.items || [];
}

/** 全部 AI 动态（聚合条目 + 分类标签统计） */
export async function loadAll(): Promise<AllFeedResponse | null> {
  try {
    return await fetchJSON<AllFeedResponse>("/api/all");
  } catch {
    return null;
  }
}

/** 官方历史日报（/api/v1/dailies/{date} 代理），失败返回 null */
export async function loadOfficialDaily(date: string): Promise<unknown | null> {
  try {
    return await fetchJSON<unknown>(`/api/daily?date=${encodeURIComponent(date)}`);
  } catch {
    return null;
  }
}

/** 直连 items 分页（/api/items 代理透传 cursor） */
export async function fetchItemsPage(cursor?: string, limit = 50): Promise<ItemsPage | null> {
  try {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return await fetchJSON<ItemsPage>(`/api/items?${params}`);
  } catch {
    return null;
  }
}

/** 从快照 daily+weekly 合并出精选条目池（按 id 去重，publishedAt 降序） */
export function poolFromSnapshot(snap: Snapshot): NewsItem[] {
  const seen = new Set<string>();
  const pool: NewsItem[] = [];
  for (const view of [snap.daily, snap.weekly]) {
    for (const sec of view.sections || []) {
      for (const it of sec.items || []) {
        if (seen.has(it.id)) continue;
        seen.add(it.id);
        pool.push(it);
      }
    }
  }
  pool.sort((a, b) => new Date(b.publishedAt || 0).getTime() - new Date(a.publishedAt || 0).getTime());
  return pool;
}

/** 合并快照池与实时精选流：实时条目覆盖同 id 快照条目，其余追加 */
export function mergePools(snapshotPool: NewsItem[], liveItems: NewsItem[]): NewsItem[] {
  const map = new Map<string, NewsItem>();
  for (const it of snapshotPool) map.set(it.id, it);
  for (const it of liveItems) {
    const key = it.id.startsWith("aihot:") ? it.id : `aihot:${it.id}`;
    map.set(key, { ...it, id: key });
    if (map.has(it.id)) map.set(it.id, { ...it });
  }
  const out = [...map.values()];
  out.sort((a, b) => new Date(b.publishedAt || 0).getTime() - new Date(a.publishedAt || 0).getTime());
  return out;
}
