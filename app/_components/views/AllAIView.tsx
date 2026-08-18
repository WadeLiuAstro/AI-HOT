// 全部 AI 动态视图（优先级最低模块）：全量信息流 + AI 分类标签筛选
// 标签来自上游分类归一化；LLM 深度打标接入后此视图直接复用同一数据结构
"use client";

import { useEffect, useMemo, useState } from "react";
import type { NewsItem } from "../../_lib/types";
import { loadAll } from "../../_lib/api";
import { bjDayKey, fmtMonthDay, fmtWeekday } from "../../_lib/format";
import { ArticleCard } from "../ArticleCard";
import { DateGroup } from "../DateGroup";

export function AllAIView() {
  const [items, setItems] = useState<NewsItem[]>([]);
  const [tags, setTags] = useState<{ tag: string; count: number }[]>([]);
  const [tag, setTag] = useState("all");
  const [loading, setLoading] = useState(true);
  const [live, setLive] = useState(true);

  useEffect(() => {
    let cancelled = false;
    loadAll().then((r) => {
      if (cancelled) return;
      if (r) {
        setItems(r.items);
        setTags(r.tags);
        setLive(r.live);
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const filtered = useMemo(
    () => (tag === "all" ? items : items.filter((it) => it.category === tag)),
    [items, tag],
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
      <header className="mb-6">
        <h1 className="text-[26px] font-extrabold text-ink">全部 AI 动态</h1>
        <p className="mt-1 text-[13px] text-mut">AI 相关资讯全量信息流 · 自动分类与打标签</p>
      </header>

      {/* 标签筛选（AI 两级分类体系的一级标签） */}
      <div className="mb-5 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setTag("all")}
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
            onClick={() => setTag(t.tag)}
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
        分类与标签由 AI 自动打标（两级分类体系 · 定稿后批量写入）；LLM 深度标签接入中。
        {!live && " 实时接口暂不可用，当前无数据。"}
      </p>

      {loading ? (
        <div className="flex flex-col gap-3.5">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="ah-card h-[110px] animate-pulse bg-surface-2" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <p className="ah-card p-8 text-center text-[13px] text-mut">暂无动态数据。</p>
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
