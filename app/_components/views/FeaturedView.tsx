// 精选视图：按时间戳倒序的精选新闻流 + 分类 Tab 筛选 + 搜索 + 当前热点入口
"use client";

import { useEffect, useMemo, useState } from "react";
import type { HotTopic, NewsItem } from "../../_lib/types";
import { loadFeatured, loadHot, loadSnapshot, mergePools, poolFromSnapshot } from "../../_lib/api";
import {
  bjDayKey,
  fmtFullDay,
  fmtMonthDay,
  fmtWeekday,
  heatOf,
  SECTIONS,
  SECTION_SHORT,
} from "../../_lib/format";
import { useApp } from "../providers/AppDataProvider";
import { ArticleCard } from "../ArticleCard";
import { CategoryTabs, type TabOption } from "../CategoryTabs";
import { DateGroup } from "../DateGroup";
import { ArrowRightIcon } from "../icons";
import { SearchToolbar, type SourceFilter } from "../SearchToolbar";
import { matchItem, sourceKindOf } from "../../_lib/source";

/** 跨导航切换保留筛选状态（模块级缓存） */
const persisted: { cat: string; q: string; src: SourceFilter } = { cat: "all", q: "", src: "all" };

export function FeaturedView() {
  const { setView } = useApp();
  const [pool, setPool] = useState<NewsItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [liveOk, setLiveOk] = useState(true);
  const [hotTop, setHotTop] = useState<HotTopic[]>([]);
  const [cat, setCat] = useState(persisted.cat);
  const [q, setQ] = useState(persisted.q);
  const [src, setSrc] = useState<SourceFilter>(persisted.src);
  const [today, setToday] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setToday(fmtFullDay(new Date().toISOString()));
      const snap = await loadSnapshot();
      const base = snap ? poolFromSnapshot(snap) : [];
      if (cancelled) return;
      if (base.length) {
        setPool(base);
        setLoading(false);
      }
      try {
        const live = await loadFeatured();
        if (cancelled) return;
        if (live.length) setPool(base.length ? mergePools(base, live) : live);
        setLiveOk(true);
      } catch {
        setLiveOk(false);
      }
      setLoading(false);
    })();
    loadHot().then((r) => {
      if (!cancelled && r) setHotTop(r.items.slice(0, 3));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /** 分类 Tab：全部 + 数据中实际出现的版块（固定顺序、短名） */
  const tabOptions = useMemo<TabOption[]>(() => {
    const counter = new Map<string, number>();
    for (const it of pool) counter.set(it.category || "行业动态", (counter.get(it.category || "行业动态") || 0) + 1);
    const opts: TabOption[] = [{ key: "all", label: "全部", count: pool.length }];
    for (const s of SECTIONS) {
      const n = counter.get(s);
      if (n) opts.push({ key: s, label: SECTION_SHORT[s] || s, count: n });
    }
    return opts;
  }, [pool]);

  /** 过滤 + 按北京日期分组（时间戳倒序） */
  const groups = useMemo(() => {
    const filtered = pool.filter((it) => {
      if (cat !== "all" && it.category !== cat) return false;
      if (src !== "all" && sourceKindOf(it) !== src) return false;
      if (!matchItem(it, q)) return false;
      return true;
    });
    const map = new Map<string, NewsItem[]>();
    for (const it of filtered) {
      const key = bjDayKey(it.publishedAt) || "unknown";
      const arr = map.get(key);
      if (arr) arr.push(it);
      else map.set(key, [it]);
    }
    return [...map.entries()];
  }, [pool, cat, q, src]);

  const totalShown = groups.reduce((n, [, items]) => n + items.length, 0);

  return (
    <div>
      {/* 页头：标题 + 搜索 */}
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold text-ink">精选</h1>
          <p className="mt-1 text-[13px] text-mut">{today} · AI 筛选的今日重点</p>
        </div>
        <div className="flex w-full max-w-[340px] items-center gap-2 sm:w-auto">
          <SearchToolbar
            q={q}
            onQChange={(v) => {
              setQ(v);
              persisted.q = v;
            }}
            src={src}
            onSrcChange={(v) => {
              setSrc(v);
              persisted.src = v;
            }}
          />
        </div>
      </header>

      {/* 当前热点（前 3 条，入口跳转热点榜） */}
      {hotTop.length > 0 && (
        <div className="ah-card mb-6 p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[15px] font-bold text-ink">当前热点</h2>
            <button
              type="button"
              onClick={() => setView("hot")}
              className="inline-flex items-center gap-1 text-[12.5px] font-medium text-brand hover:text-brand-strong"
            >
              完整榜单 <ArrowRightIcon />
            </button>
          </div>
          <ol className="flex flex-col divide-y divide-line-2">
            {hotTop.map((t) => (
              <li key={t.id} className="flex items-center gap-3 py-2.5">
                <span className="w-5 text-center text-[15px] font-extrabold text-heat-red">{t.rank}</span>
                <a
                  href={t.links.original}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-ink-2 hover:text-brand"
                  title={t.title}
                >
                  {t.title}
                </a>
                <span className="text-[12px] font-bold whitespace-nowrap text-ink">{heatOf(t)} 热度</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* 分类 Tab */}
      <div className="mb-6">
        <CategoryTabs
          options={tabOptions}
          active={cat}
          onChange={(key) => {
            setCat(key);
            persisted.cat = key;
          }}
        />
      </div>

      {/* 内容区 */}
      {loading ? (
        <div className="flex flex-col gap-3.5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="ah-card h-[120px] animate-pulse bg-surface-2" />
          ))}
        </div>
      ) : totalShown === 0 ? (
        <p className="ah-card p-8 text-center text-[13px] text-mut">
          无匹配内容{!liveOk && "（实时接口不可用，且快照为空）"}，试试切换分类、来源筛选或清空搜索词。
        </p>
      ) : (
        groups.map(([dayKey, items]) => (
          <DateGroup
            key={dayKey}
            monthDay={dayKey === "unknown" ? "时间未知" : fmtMonthDay(items[0].publishedAt)}
            weekday={dayKey === "unknown" ? "" : fmtWeekday(items[0].publishedAt)}
            count={items.length}
          >
            {items.map((it) => (
              <ArticleCard key={it.id} item={it} />
            ))}
          </DateGroup>
        ))
      )}

      <footer className="mt-10 border-t border-line pt-5 text-center text-[12px] text-mut-2">
        共 {totalShown} 条精选 · 数据来源：AI HOT 开放 API · 时间为北京时间 · 摘要由 AI 生成，点击标题核对原文
      </footer>
    </div>
  );
}
