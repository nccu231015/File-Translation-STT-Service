'use client';

/**
 * ChartBlock.tsx
 *
 * Renders a chart from a `chart_config` object returned by the backend API.
 * Supports three chart types:
 *   - 'bar_line_combo' : dual-Y-axis (Bar = quantity, Line = defect rate) for Q5
 *   - 'multi_line'    : multiple lines, one per model/line  for Q7
 *   - 'heatmap'       : fault reason × equipment occurrence matrix  for EQ-G
 *
 * This component is intentionally *backend-agnostic*:
 * it only depends on the ChartConfig interface, not on how the data was fetched.
 * When the backend migrates to n8n the chart_config JSON structure stays the same.
 */

import {
    ComposedChart,
    LineChart,
    Bar,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
} from 'recharts';
import { ChartConfig } from '@/lib/api/factory';

// ── Colour palette ────────────────────────────────────────────────────────────
const PALETTE = [
    '#6366f1', // indigo-500
    '#f59e0b', // amber-500
    '#10b981', // emerald-500
    '#ef4444', // red-500
    '#3b82f6', // blue-500
    '#8b5cf6', // violet-500
    '#ec4899', // pink-500
    '#14b8a6', // teal-500
    '#f97316', // orange-500
    '#84cc16', // lime-500
];

function colour(i: number) {
    return PALETTE[i % PALETTE.length];
}

// ── Convert datasets array → recharts row-based format ────────────────────────
function toRows(labels: string[], datasets: ChartConfig['datasets']) {
    return labels.map((label, i) => {
        const row: Record<string, string | number | null> = { label };
        datasets.forEach(ds => {
            row[ds.label] = ds.data[i] ?? null;
        });
        return row;
    });
}

// ── Custom Tooltip ────────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }: any) {
    if (!active || !payload?.length) return null;
    return (
        <div className="bg-white border border-slate-200 rounded-xl shadow-lg px-4 py-3 text-xs space-y-1">
            <p className="font-semibold text-slate-600 mb-1">{label}</p>
            {payload.map((p: any) => (
                <div key={p.name} className="flex items-center gap-2">
                    <span className="size-2.5 rounded-full flex-shrink-0" style={{ background: p.color }} />
                    <span className="text-slate-500">{p.name}：</span>
                    <span className="font-bold text-slate-800">
                        {p.value == null ? '—' : typeof p.value === 'number' && p.value < 5 && p.name.includes('%')
                            ? `${p.value.toFixed(4)}%`
                            : p.value.toLocaleString()}
                    </span>
                </div>
            ))}
        </div>
    );
}

// ── Heat map colour helpers ───────────────────────────────────────────────────
/** Interpolate white (#f8fafc) → deep-red (#b91c1c) based on normalised t ∈ [0,1] */
function heatColor(value: number, maxVal: number): string {
    if (maxVal === 0 || value === 0) return 'rgb(248,250,252)';
    const t = Math.min(value / maxVal, 1);
    // 0 → white, 0.5 → orange-ish, 1 → crimson
    const r = Math.round(248 + t * (185 - 248));  // 248 → 185
    const g = Math.round(250 + t * (28  - 250));  // 250 → 28
    const b = Math.round(252 + t * (28  - 252));  // 252 → 28
    return `rgb(${r},${g},${b})`;
}
function textOnHeat(value: number, maxVal: number): string {
    if (maxVal === 0) return '#94a3b8';
    return value / maxVal > 0.45 ? '#ffffff' : '#1e293b';
}

// ── Heat map sub-component ────────────────────────────────────────────────────
function HeatMapBlock({ config }: { config: ChartConfig }) {
    const maxVal = config.max_value ?? Math.max(...config.datasets.flatMap(ds => ds.data as number[]), 1);
    const equipNames = config.labels;          // X-axis = equipment (columns)
    const notes      = config.datasets;        // Y-axis rows = fault reasons

    return (
        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-3">{config.title}</p>

            {/* Scrollable wrapper so many columns don't break layout */}
            <div className="overflow-x-auto">
                <table className="text-[11px] border-separate border-spacing-[2px] min-w-max">
                    <thead>
                        <tr>
                            {/* Row-label header */}
                            <th className="sticky left-0 z-10 bg-slate-100 text-slate-500 font-medium px-2 py-1 rounded text-left whitespace-nowrap min-w-[140px]">
                                故障原因 \ 設備
                            </th>
                            {equipNames.map(eq => (
                                <th
                                    key={eq}
                                    className="bg-slate-100 text-slate-500 font-medium px-2 py-1 rounded text-center whitespace-nowrap"
                                >
                                    {eq}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {notes.map(ds => (
                            <tr key={ds.label}>
                                {/* Fault reason label – sticky */}
                                <td className="sticky left-0 z-10 bg-white border border-slate-100 text-slate-600 font-medium px-2 py-1 rounded whitespace-nowrap">
                                    <span className="block truncate max-w-[200px]" title={ds.label}>
                                        {ds.label}
                                    </span>
                                    {ds.cate && (
                                        <span className="text-[9px] text-slate-400 ml-0.5">[{ds.cate}]</span>
                                    )}
                                </td>
                                {(ds.data as number[]).map((val, ci) => (
                                    <td
                                        key={ci}
                                        className="text-center rounded px-1 py-1 font-semibold transition-all"
                                        style={{
                                            backgroundColor: heatColor(val, maxVal),
                                            color: textOnHeat(val, maxVal),
                                            minWidth: 40,
                                        }}
                                        title={`${ds.label} × ${equipNames[ci]}：${val} 次`}
                                    >
                                        {val > 0 ? val : ''}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-2 mt-3">
                <span className="text-[10px] text-slate-400">低頻</span>
                <div className="flex h-3 w-32 rounded overflow-hidden">
                    {Array.from({ length: 20 }, (_, i) => (
                        <div key={i} className="flex-1" style={{ backgroundColor: heatColor(i + 1, 20) }} />
                    ))}
                </div>
                <span className="text-[10px] text-slate-400">高頻</span>
                <span className="ml-auto text-[10px] text-slate-400">資料由 AI 助手即時查詢，僅供參考</span>
            </div>
        </div>
    );
}

// ── Main component ────────────────────────────────────────────────────────────
interface ChartBlockProps {
    config: ChartConfig;
}

export function ChartBlock({ config }: ChartBlockProps) {
    // ── Heat map: render its own pure-CSS component ───────────────────────────
    if (config.chart_type === 'heatmap') {
        return <HeatMapBlock config={config} />;
    }

    const rows = toRows(config.labels, config.datasets);

    // Detect which datasets are bars vs lines for ComposedChart
    const barDatasets  = config.datasets.filter(ds => ds.type === 'bar');
    const lineDatasets = config.datasets.filter(ds => ds.type === 'line');

    // Left Y-axis key (quantity), right Y-axis key (defect rate)
    const leftAxisId  = barDatasets[0]?.yAxisID  ?? 'y_quantity';
    const rightAxisId = lineDatasets[0]?.yAxisID ?? 'y_defect_rate';

    return (
        <div className="mt-4 rounded-2xl border border-slate-100 bg-slate-50/60 p-4 shadow-sm">
            <p className="text-sm font-semibold text-slate-700 mb-3">{config.title}</p>

            <ResponsiveContainer width="100%" height={300}>
                {config.chart_type === 'bar_line_combo' ? (
                    /* ── Q5: Bar (quantity) + Line (defect rate), dual Y-axis ── */
                    <ComposedChart data={rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis
                            dataKey="label"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={{ stroke: '#e2e8f0' }}
                            tickLine={false}
                        />
                        {/* Left Y – quantity */}
                        <YAxis
                            yAxisId={leftAxisId}
                            orientation="left"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                            label={{
                                value: config.yAxes?.[leftAxisId]?.label ?? '產量',
                                angle: -90, position: 'insideLeft',
                                style: { fontSize: 10, fill: '#94a3b8' },
                            }}
                        />
                        {/* Right Y – defect rate */}
                        <YAxis
                            yAxisId={rightAxisId}
                            orientation="right"
                            tickFormatter={(v: number) => `${v.toFixed(2)}%`}
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                            label={{
                                value: config.yAxes?.[rightAxisId]?.label ?? '不良率',
                                angle: 90, position: 'insideRight',
                                style: { fontSize: 10, fill: '#94a3b8' },
                            }}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        {barDatasets.map((ds, i) => (
                            <Bar
                                key={ds.label}
                                dataKey={ds.label}
                                yAxisId={ds.yAxisID ?? leftAxisId}
                                fill={ds.backgroundColor ?? colour(i)}
                                radius={[4, 4, 0, 0]}
                                maxBarSize={40}
                                hide={(ds as any).hide}
                                legendType={(ds as any).hideInLegend ? 'none' : 'rect'}
                            />
                        ))}
                        {lineDatasets.map((ds, i) => (
                            <Line
                                key={ds.label}
                                type="monotone"
                                dataKey={ds.label}
                                yAxisId={ds.yAxisID ?? rightAxisId}
                                stroke={ds.borderColor ?? colour(barDatasets.length + i)}
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                activeDot={{ r: 5 }}
                                connectNulls
                                legendType={(ds as any).hideInLegend ? 'none' : 'line'}
                            />
                        ))}
                    </ComposedChart>
                ) : (
                    /* ── Q7: Multi-line (one per model / production line) ── */
                    <LineChart data={rows} margin={{ top: 8, right: 24, left: 0, bottom: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                        <XAxis
                            dataKey="label"
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={{ stroke: '#e2e8f0' }}
                            tickLine={false}
                        />
                        <YAxis
                            tickFormatter={(v: number) => `${v.toFixed(2)}%`}
                            tick={{ fontSize: 11, fill: '#94a3b8' }}
                            axisLine={false}
                            tickLine={false}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Legend wrapperStyle={{ fontSize: 12 }} />
                        {config.datasets.map((ds, i) => (
                            <Line
                                key={ds.label}
                                type="monotone"
                                dataKey={ds.label}
                                stroke={ds.borderColor ?? colour(i)}
                                strokeWidth={2}
                                dot={{ r: 3 }}
                                activeDot={{ r: 5 }}
                                connectNulls
                            />
                        ))}
                    </LineChart>
                )}
            </ResponsiveContainer>

            <p className="text-[10px] text-slate-400 text-right mt-2">
                資料由 AI 助手即時查詢，僅供參考
            </p>
        </div>
    );
}
