// AI 日报视图：仅日报 / 周报两种粒度（无月报）
// 日报按月份组织当月所有日期；周报按月份组织当月每一周；正文未生成前展示占位结构
"use client";

import { useEffect, useMemo, useState } from "react";
import type { HistoryEntry, Snapshot, WeeklyNavEntry } from "../../_lib/types";
import { loadOfficialDaily, loadSnapshot } from "../../_lib/api";
import { fmtCnDate, fmtWeekday } from "../../_lib/format";
import { ArrowRightIcon } from "../icons";

type Tab = "daily" | "weekly";

/** 从官方历史日报响应中防御性提取版块结构（结构未知时返回 null） */
function parseOfficialSections(data: unknown): { label: string; count: number; topTitle: string }[] | null {
  if (!data || typeof data !== "object") return null;
  const obj = data as Record<string, unknown>;
  const candidate = (obj.sections ?? obj.flashes ?? obj.items) as unknown;
  if (!Array.isArray(candidate) || candidate.length === 0) return null;
  const out: { label: string; count: number; topTitle: string }[] = [];
  for (const sec of candidate) {
    if (!sec || typeof sec !== "object") continue;
    const s = sec as Record<string, unknown>;
    const items = Array.isArray(s.items) ? (s.items as Record<string, unknown>[]) : [];
    const label = typeof s.label === "string" ? s.label : typeof s.title === "string" ? s.title : "";
    if (!label) continue;
    out.push({
      label,
      count: items.length,
      topTitle: items.length ? String(items[0].title || "") : "",
    });
  }
  return out.length ? out : null;
}

export function DailyReportView() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<Tab>("daily");
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [selectedWeek, setSelectedWeek] = useState<string>(""); // weekly url 作为键
  const [official, setOfficial] = useState<{ label: string; count: number; topTitle: string }[] | null>(null);

  useEffect(() => {
    loadSnapshot().then((s) => {
      setSnap(s);
      if (s?.history?.length) setSelectedDate(s.history[0].date);
      if (s?.weeklyNav?.length) setSelectedWeek(s.weeklyNav[0].url);
    });
  }, []);

  /** 日报按月份分组（新到旧） */
  const dailyMonths = useMemo(() => {
    const map = new Map<string, HistoryEntry[]>();
    for (const h of snap?.history || []) {
      const key = h.date.slice(0, 7); // YYYY-MM
      const arr = map.get(key);
      if (arr) arr.push(h);
      else map.set(key, [h]);
    }
    return [...map.entries()];
  }, [snap]);

  /** 周报按月份分组：从 url 中解析周起始日期 */
  const weeklyMonths = useMemo(() => {
    const map = new Map<string, (WeeklyNavEntry & { weekStart: string })[]>();
    for (const w of snap?.weeklyNav || []) {
      const m = w.url.match(/weekly\/(\d{4}-\d{2}-\d{2})/);
      const weekStart = m ? m[1] : "";
      const key = weekStart.slice(0, 7) || "unknown";
      const arr = map.get(key);
      if (arr) arr.push({ ...w, weekStart });
      else map.set(key, [{ ...w, weekStart }]);
    }
    return [...map.entries()];
  }, [snap]);

  const currentDaily = (snap?.history || []).find((h) => h.date === selectedDate) || null;
  const currentWeekly = (snap?.weeklyNav || []).find((w) => w.url === selectedWeek) || null;

  /** 选中日期变化时拉取官方历史日报，用于「今日看点」版块结构 */
  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setOfficial(null);
    loadOfficialDaily(selectedDate).then((data) => {
      if (!cancelled) setOfficial(parseOfficialSections(data));
    });
    return () => {
      cancelled = true;
    };
  }, [selectedDate]);

  const monthLabel = (key: string) => {
    if (key === "unknown") return "未知月份";
    const [y, m] = key.split("-");
    return `${y} 年 ${Number(m)} 月`;
  };

  const tabBtn = (t: Tab, label: string) => (
    <button
      key={t}
      type="button"
      onClick={() => setTab(t)}
      className={`rounded-lg px-5 py-1.5 text-[13px] font-semibold transition-colors ${
        tab === t ? "bg-surface-2 text-ink shadow-sm ring-1 ring-line" : "text-mut hover:text-ink"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      {/* 页头 + 粒度切换（仅日报 / 周报，无月报） */}
      <header className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-extrabold text-ink">AI 日报</h1>
          <p className="mt-1 text-[13px] text-mut">每日晨报与每周综述 · 按月份归档组织</p>
        </div>
        <div className="flex gap-1 rounded-xl border border-line bg-surface p-1">
          {tabBtn("daily", "日报")}
          {tabBtn("weekly", "周报")}
        </div>
      </header>

      {!snap ? (
        <div className="ah-card h-[220px] animate-pulse bg-surface-2" />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
          {/* 左列：月份归档索引 */}
          <aside className="ah-card ah-scroll h-fit max-h-[calc(100vh-180px)] overflow-y-auto p-4 lg:sticky lg:top-6">
            {tab === "daily" ? (
              dailyMonths.length === 0 ? (
                <p className="p-2 text-[12px] text-mut">归档积累中…</p>
              ) : (
                dailyMonths.map(([key, days]) => (
                  <div key={key} className="mb-4">
                    <div className="mb-2 flex items-baseline justify-between px-1">
                      <span className="text-[13px] font-bold text-ink">{monthLabel(key)}</span>
                      <span className="text-[11.5px] text-mut-2">{days.length}</span>
                    </div>
                    <ul className="flex flex-col gap-0.5">
                      {days.map((h) => (
                        <li key={h.date}>
                          <button
                            type="button"
                            onClick={() => setSelectedDate(h.date)}
                            className={`flex w-full items-center justify-between rounded-md px-2.5 py-1.5 text-left text-[12.5px] transition-colors ${
                              selectedDate === h.date
                                ? "bg-brand-soft font-semibold text-brand-strong"
                                : "text-ink-2 hover:bg-surface-2"
                            }`}
                          >
                            <span>{h.label.replace(/\s.*$/, "")}</span>
                            <span className="text-[11px] text-mut-2">{h.total}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              )
            ) : weeklyMonths.length === 0 ? (
              <p className="p-2 text-[12px] text-mut">首个完结自然周后产出…</p>
            ) : (
              weeklyMonths.map(([key, weeks]) => (
                <div key={key} className="mb-4">
                  <div className="mb-2 px-1 text-[13px] font-bold text-ink">{monthLabel(key)}</div>
                  <ul className="flex flex-col gap-0.5">
                    {weeks.map((w) => (
                      <li key={w.url}>
                        <button
                          type="button"
                          onClick={() => setSelectedWeek(w.url)}
                          className={`w-full rounded-md px-2.5 py-2 text-left transition-colors ${
                            selectedWeek === w.url ? "bg-brand-soft" : "hover:bg-surface-2"
                          }`}
                        >
                          <span className={`block text-[12.5px] ${selectedWeek === w.url ? "font-semibold text-brand-strong" : "text-ink-2"}`}>
                            {w.label}
                          </span>
                          <span className="mt-0.5 block text-[11px] text-mut-2">
                            {w.range} · {w.total} 条
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))
            )}
          </aside>

          {/* 右列：期刊内容（正文未生成时展示占位结构） */}
          <main>
            {tab === "daily" ? (
              currentDaily ? (
                <DailyDetail entry={currentDaily} official={official} />
              ) : (
                <EmptyPanel text="暂无日报归档" />
              )
            ) : currentWeekly ? (
              <WeeklyDetail entry={currentWeekly} />
            ) : (
              <EmptyPanel text="暂无周报归档" />
            )}
          </main>
        </div>
      )}
    </div>
  );
}

/** 日报详情：VOL 期刊头 + 今日看点（版块结构 / 头条占位） */
function DailyDetail({
  entry,
  official,
}: {
  entry: HistoryEntry;
  official: { label: string; count: number; topTitle: string }[] | null;
}) {
  const dateIso = `${entry.date}T00:00:00Z`;
  return (
    <div>
      <div className="text-[12px] tracking-[0.2em] text-mut uppercase">
        VOL.{entry.date.replaceAll("-", ".")} · {entry.total} STORIES · AI HOT DAILY
      </div>
      <h2 className="mt-2 text-[30px] font-extrabold">
        <span className="text-brand">AI HOT</span> <span className="text-ink">日报</span>
      </h2>
      <p className="mt-1 text-[12.5px] text-mut">
        {fmtCnDate(dateIso)} {fmtWeekday(dateIso)} · DAILY · 每早八时
        {entry.finalized ? " · 已定稿" : " · 更新中"}
      </p>

      <div className="ah-card mt-6 overflow-hidden">
        <div className="flex items-center justify-between border-b border-line bg-surface-2 px-5 py-3">
          <h3 className="text-[14px] font-bold text-ink">今日看点</h3>
          <span className="text-[12px] text-mut">{entry.total} 篇报道</span>
        </div>
        {official ? (
          <ol className="divide-y divide-line-2">
            {official.map((s, i) => (
              <li key={s.label} className="flex items-start gap-4 px-5 py-4">
                <span className="pt-0.5 text-[14px] font-extrabold text-brand">{String(i + 1).padStart(2, "0")}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-bold text-ink">{s.label}</div>
                  {s.topTitle && <div className="mt-1 truncate text-[12.5px] text-mut">{s.topTitle}</div>}
                </div>
                <span className="text-[13px] font-bold text-mut">{s.count}</span>
              </li>
            ))}
          </ol>
        ) : (
          <div className="px-5 py-4">
            <div className="flex items-start gap-4">
              <span className="pt-0.5 text-[14px] font-extrabold text-brand">01</span>
              <div className="min-w-0 flex-1">
                <div className="text-[13.5px] font-bold text-ink">当日头条</div>
                <div className="mt-1 text-[12.5px] leading-relaxed text-mut">{entry.title || "暂无头条数据"}</div>
              </div>
              <span className="text-[13px] font-bold text-mut">{entry.total}</span>
            </div>
          </div>
        )}
      </div>

      {/* 正文占位：AI 生成的日报叙事内容产出后替换此区块 */}
      <div className="ah-card mt-4 border-dashed p-6 text-center">
        <p className="text-[13px] text-mut">日报正文（AI 生成的叙事综述）尚未产出，生成后将在此展示。</p>
        <a
          href={entry.url}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-brand px-4 py-2 text-[13px] font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
        >
          查看当日完整归档 <ArrowRightIcon />
        </a>
      </div>
    </div>
  );
}

/** 周报详情：VOL 期刊头 + 本期主线占位 */
function WeeklyDetail({ entry }: { entry: WeeklyNavEntry }) {
  const m = entry.url.match(/weekly\/(\d{4})-(\d{2})-(\d{2})/);
  const year = m ? m[1] : "";
  const startIso = m ? `${m[1]}-${m[2]}-${m[3]}T00:00:00Z` : "";
  return (
    <div>
      <div className="text-[12px] tracking-[0.2em] text-mut uppercase">
        VOL.{year} · {entry.label} · WEEKLY
      </div>
      <h2 className="mt-2 text-[30px] font-extrabold text-ink">{entry.label}</h2>
      <p className="mt-1 text-[12.5px] text-mut">
        {entry.range} · WEEKLY · 编辑系统自动综合 · {entry.total} 条
      </p>

      <div className="ah-card mt-6 overflow-hidden">
        <div className="border-b border-line bg-surface-2 px-5 py-3">
          <h3 className="text-[14px] font-bold text-ink">本期主线</h3>
        </div>
        <div className="px-5 py-5">
          <p className="text-[13px] leading-relaxed text-mut">
            {startIso ? `${fmtCnDate(startIso)} 起的自然周综述` : "本周期刊"}共收录 {entry.total} 条 AI 动态，
            周报正文（主线梳理与深度综述）尚未产出。
          </p>
        </div>
      </div>

      <div className="ah-card mt-4 border-dashed p-6 text-center">
        <p className="text-[13px] text-mut">周报正文待生成，产出后将在此展示。</p>
        <a
          href={entry.url}
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-brand px-4 py-2 text-[13px] font-semibold text-brand transition-colors hover:bg-brand hover:text-white"
        >
          查看本期周期刊 <ArrowRightIcon />
        </a>
      </div>
    </div>
  );
}

function EmptyPanel({ text }: { text: string }) {
  return <div className="ah-card p-10 text-center text-[13px] text-mut">{text}</div>;
}
