// AI HOT 前端数据类型定义（与 build_snapshot.py / aihot API 对齐）

export type ViewKey = "featured" | "hot" | "all" | "daily";

/** AI 两级分类（tag_news 打标签产物，展示结构） */
export interface Classification {
  cat: string;
  catLabel: string;
  dims?: { key: string; value: string }[];
}

/** 新闻条目（快照与 aihot API 合并后的统一结构） */
export interface NewsItem {
  id: string;
  title: string;
  summary?: string;
  url?: string;
  permalink?: string;
  source?: string;
  sourceType?: "aihot" | "wechat";
  /** 中文六版块；API 原始英文分类经 API_CATEGORY_MAP 归一化 */
  category?: string;
  publishedAt?: string;
  discoveredAt?: string;
  score?: number | null;
  selected?: boolean;
  mpName?: string | null;
  classification?: Classification | null;
  num?: number;
  timeText?: string;
}

export interface DigestSection {
  label: string;
  count: number;
  items: NewsItem[];
}

/** 日报 / 周报视图（快照 DATA.daily / DATA.weekly 结构） */
export interface DigestView {
  view: string;
  range: { start: string; end: string; label: string; cnLabel?: string };
  total: number;
  lead?: string | null;
  sections: DigestSection[];
  stats: { label: string; count: number }[];
  mpStatus?: { connected: boolean; note?: string };
  generatedAt: string;
  vol?: string;
}

/** 主页历史归档日期导航条目 */
export interface HistoryEntry {
  date: string;
  label: string;
  title: string;
  total: number;
  finalized: boolean;
  url: string;
}

/** 自然周期刊导航条目 */
export interface WeeklyNavEntry {
  url: string;
  label: string;
  range: string;
  total: number;
}

/** build_snapshot.py 输出的 snapshot.json 根结构 */
export interface Snapshot {
  daily: DigestView;
  weekly: DigestView;
  history: HistoryEntry[];
  weeklyNav: WeeklyNavEntry[];
}

/** /api/v1/hot-topics 单条热点事件（实测结构） */
export interface HotTopic {
  rank: number;
  id: string;
  title: string;
  source: { name: string };
  links: { aihot: string; original: string; story: string };
  sourceCount: number;
  signalCount: number;
  sourceNames: string[];
  latestAt: string;
}

export interface HotTopicsResponse {
  schemaVersion: number;
  count: number;
  items: HotTopic[];
}

/** /api/public/items 分页响应 */
export interface ItemsPage {
  count: number;
  hasNext: boolean;
  nextCursor?: string;
  items: NewsItem[];
}

/** /api/all 聚合响应（条目 + 分类标签统计） */
export interface AllFeedResponse {
  items: NewsItem[];
  tags: { tag: string; count: number }[];
  live: boolean;
}
