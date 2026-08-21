// 全部 AI 动态视图：aihot 实时流 + 快照（含 Manus 公众号爬取）合并信息流
// 支持：新 6 类分类 Tab + 维度标签筛选 + 来源筛选（一手信源/资讯/推文/公众号）+ 按来源/标题/摘要搜索
"use client";

import { useEffect, useMemo, useState } from "react";
import type { NewsItem } from "../../_lib/types";
import { loadAll, loadSnapshot, mergePools, poolFromSnapshot } from "../../_lib/api";
import { bjDayKey, fmtMonthDay, fmtWeekday } from "../../_lib/format";
import { categoryOf, matchDims, TAXONOMY_CATEGORIES } from "../../_lib/taxonomy";
import { matchItem, sourceKindOf } from "../../_lib/source";
import { ArticleCard } from "../ArticleCard";
import { CategoryTabs, type TabOption } from "../CategoryTabs";
import { DateGroup } from "../DateGroup";
import { SearchToolbar, type SourceFilter } from "../SearchToolbar";
import { TagFilterBar, type DimSelection } from "../TagFilterBar";

/** 跨导航切换保留筛选状态（模块级缓存） */
const persisted: { tag: string; q: string; src: SourceFilter; dimSel: DimSelection } = {
  tag: "all",
  q: "",
  src: "all",
  dimSel: {},
};

export function AllAIView() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [tag, setTag] = useState(persisted.tag);
  const [q, setQ] = useState(persisted.q);
  const [src, setSrc] = useState<SourceFilter>(persisted.src);
  const [dimSel, setDimSel] = useState<DimSelection>(persisted.dimSel);
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      // 快照池（含 Manus 公众号条目）+ aihot 实时流合并
      const snap = await loadSnapshot();
      const base = snap ? poolFromSnapshot(snap) : [];
      const all = await loadAll();
      if (cancelled) return;
      let merged: NewsItem[] = base;
      if (all && all.items.length) {
        merged = base.length ? mergePools(base, all.items) : all.items;
        setLive(all.live);
      }
      if (cancelled) return;
      setItems(merged);
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  /** 分类 Tab：全部 + 新 6 类（固定顺序，计数基于 categoryOf） */
  const tabOptions = useMemo<TabOption[]>(() => {
    const counter = new Map<string, number>();
    for (const it of items) {
      const key = categoryOf(it);
      counter.set(key, (counter.get(key) || 0) + 1);
    }
    const opts: TabOption[] = [{ key: "all", label: "全部", count: items.length }];
    for (const c of TAXONOMY_CATEGORIES) {
      const n = counter.get(c.id);
      if (n) opts.push({ key: c.id, label: c.label, count: n });
    }
    return opts;
  }, [items]);

  /** 当前类别的维度标签筛选（「全部」或无维度类别不显示） */
  const activeDims = useMemo(() => {
    if (tag === "all") return [];
    return TAXONOMY_CATEGORIES.find((c) => c.id === tag)?.dims ?? [];
  }, [tag]);

  const filtered = useMemo(
    () =>
      items.filter((it) => {
        if (tag !== "all" && categoryOf(it) !== tag) return false;
        if (!matchDims(it, dimSel)) return false;
        if (src !== "all" && sourceKindOf(it) !== src) return false;
        if (!matchItem(it, q)) return false;
        return true;
      }),
    [items, tag, q, src, dimSel],
  );

  const groups = useMemo(() => {
    const map = new Map<string, NewsItem[]>();
    for (const it of filtered) {
      const key = bjDayKey(it.publishedAt) || "unknown";
      const arr = map.get(key);
      if (arr) arr.push(it);
      else map.set(key, [it]);
    }
    return [...map.entries()];
  }, [filtered]);

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold text-ink">全部 AI 动态</h1>
          <p className="mt-1 text-[13px] text-mut">AI 相关资讯全量信息流 · 自动分类与打标签</p>
        </div>
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
      </header>

      {/* 分类 Tab + 维度标签筛选 */}
      <div className="mb-6">
        <CategoryTabs
          options={tabOptions}
          active={tag}
          onChange={(key) => {
            setTag(key);
            persisted.tag = key;
            // 切换类别时清空上一类别的维度筛选（维度语义随类别变化）
            setDimSel({});
            persisted.dimSel = {};
          }}
        />
        {activeDims.length > 0 && (
          <div className="mt-3">
            <TagFilterBar
              dims={activeDims}
              selection={dimSel}
              onChange={(next) => {
                setDimSel(next);
                persisted.dimSel = next;
              }}
            />
          </div>
        )}
      </div>

      <p className="mb-5 text-[12px] text-mut-2">
        数据来源：AI HOT 开放 API + Manus 公众号爬取 · 时间为北京时间 · 摘要由 AI 生成，点击标题核对原文。
        {!live && " 实时接口暂不可用，当前仅展示快照数据。"}
      </p>

      {loading ? (
        <div className="flex flex-col gap-3.5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="ah-card h-[110px] animate-pulse bg-surface-2" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <p className="ah-card p-8 text-center text-[13px] text-mut">
          无匹配内容，试试切换分类、标签、来源筛选或清空搜索词。
        </p>
      ) : (
        groups.map(([dayKey, list]) => (
          <DateGroup
            key={dayKey}
            monthDay={dayKey === "unknown" ? "时间未知" : fmtMonthDay(list[0].publishedAt)}
            weekday={dayKey === "unknown" ? "" : fmtWeekday(list[0].publishedAt)}
            count={list.length}
          >
            {list.map((it) => (
              <ArticleCard key={it.id} item={it} />
            ))}
          </DateGroup>
        ))
      )}
    </div>
  );
}
