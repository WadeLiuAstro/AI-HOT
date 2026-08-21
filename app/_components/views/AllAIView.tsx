// 全部 AI 动态视图：aihot 实时流 + 快照（含 Manus 公众号爬取）合并信息流
// 支持：AI 分类标签筛选 + 来源筛选（一手信源/资讯/推文/公众号）+ 按来源/标题/摘要搜索
"use client";

import { useEffect, useMemo, useState } from "react";
import type { NewsItem } from "../../_lib/types";
import { loadAll, loadSnapshot, mergePools, poolFromSnapshot } from "../../_lib/api";
import { bjDayKey, fmtMonthDay, fmtWeekday } from "../../_lib/format";
import { matchItem, sourceKindOf } from "../../_lib/source";
import { ArticleCard } from "../ArticleCard";
import { DateGroup } from "../DateGroup";
import { SearchToolbar, type SourceFilter } from "../SearchToolbar";

/** 跨导航切换保留筛选状态（模块级缓存） */
const persisted: { tag: string; q: string; src: SourceFilter } = { tag: "all", q: "", src: "all" };

export function AllAIView() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [tags, setTags] = useState<{ tag: string; count: number }[]>([]);
  const [tag, setTag] = useState(persisted.tag);
  const [q, setQ] = useState(persisted.q);
  const [src, setSrc] = useState<SourceFilter>(persisted.src);
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
      // 分类标签统计基于合并后条目重算（manus 中文版块与 aihot 归一化后同一空间）
      const counter = new Map<string, number>();
      for (const it of merged) {
        const key = it.category || "行业动态";
        counter.set(key, (counter.get(key) || 0) + 1);
      }
      setTags(
        [...counter.entries()]
          .map(([k, n]) => ({ tag: k, count: n }))
          .sort((a, b) => b.count - a.count),
      );
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () =>
      items.filter((it) => {
        if (tag !== "all" && it.category !== tag) return false;
        if (src !== "all" && sourceKindOf(it) !== src) return false;
        if (!matchItem(it, q)) return false;
        return true;
      }),
    [items, tag, q, src],
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

      {/* 标签筛选（AI 两级分类体系的一级标签） */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => {
            setTag("all");
            persisted.tag = "all";
          }}
          className={`rounded-full border px-3 py-1 text-[12.5px] transition-colors ${
            tag === "all"
              ? "border-brand bg-brand text-white"
              : "border-line bg-surface text-ink-2 hover:border-brand/50"
          }`}
        >
          全部 {items.length}
        </button>
        {tags.map((t) => (
          <button
            key={t.tag}
            type="button"
            onClick={() => {
              setTag(t.tag);
              persisted.tag = t.tag;
            }}
            className={`rounded-full border px-3 py-1 text-[12.5px] transition-colors ${
              tag === t.tag
                ? "border-brand bg-brand text-white"
                : "border-line bg-surface text-ink-2 hover:border-brand/50"
            }`}
          >
            {t.tag} {t.count}
          </button>
        ))}
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
          无匹配内容，试试切换标签、来源筛选或清空搜索词。
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
