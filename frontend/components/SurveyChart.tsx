"use client";

import { useEffect, useRef, useState } from "react";
import { toPng } from "html-to-image";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Funnel,
  FunnelChart,
  Legend,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Pie,
  PieChart,
  Radar,
  RadarChart,
  RadialBar,
  RadialBarChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import type { ChartConfig, ChartPoint } from "@/lib/api";

interface Props {
  config: ChartConfig;
}

const fallbackColors = [
  "#6366f1",
  "#8b5cf6",
  "#ec4899",
  "#f59e0b",
  "#10b981",
  "#3b82f6",
  "#f43f5e",
  "#14b8a6",
  "#64748b",
  "#0ea5e9",
];

export default function SurveyChart({ config }: Props) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [downloading, setDownloading] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  const colors = config.colors?.length ? config.colors : fallbackColors;

  useEffect(() => {
    const update = () => setIsMobile(window.innerWidth < 640);
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const handleDownload = async () => {
    if (!chartRef.current || downloading) return;
    setDownloading(true);
    setIsExporting(true);

    try {
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

      const exportWidth = Math.max(chartRef.current.scrollWidth, chartRef.current.clientWidth);
      const exportHeight = Math.max(chartRef.current.scrollHeight, chartRef.current.clientHeight);

      const dataUrl = await toPng(chartRef.current, {
        quality: 1,
        backgroundColor: "#ffffff",
        pixelRatio: isMobile ? 3 : 2,
        cacheBust: true,
        canvasWidth: exportWidth,
        canvasHeight: exportHeight,
        style: {
          overflow: "visible",
        },
      });

      const safeTitle = (config.title || "survey-chart")
        .replace(/[^a-z0-9\s]/gi, "")
        .trim()
        .replace(/\s+/g, "-")
        .toLowerCase();

      const link = document.createElement("a");
      link.download = `${safeTitle || "survey-chart"}_${Date.now()}.png`;
      link.href = dataUrl;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (error) {
      console.error("Chart export failed", error);
      alert("Failed to download chart. Please try again.");
    } finally {
      setIsExporting(false);
      setDownloading(false);
    }
  };

  if (config.error) {
    return (
      <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-100 dark:border-yellow-700">
        <p className="font-medium">{config.error}</p>
        {config.suggestion && <p className="text-sm mt-1">Try: {config.suggestion}</p>}
      </div>
    );
  }

  const data = Array.isArray(config.data) ? config.data : [];
  const chartHeight = isMobile ? 270 : 320;
  const tickColor = "#64748b";
  const axisFontSize = isMobile ? 10 : 12;
  const truncateCategory = (value: string) => {
    const max = isMobile ? 14 : 24;
    return value.length > max ? `${value.slice(0, max - 1)}…` : value;
  };
  const needsWideCanvas = [
    "bar",
    "clustered_column",
    "horizontal_bar",
    "clustered_bar",
    "line",
    "area",
    "stacked_bar",
    "comparison",
    "waterfall",
    "gantt",
    "histogram",
    "diverging_bar",
  ].includes(
    config.chart_type || ""
  ) && data.length > 6;
  const minCanvasWidth = isMobile && needsWideCanvas ? Math.max(360, data.length * 56) : 0;

  const barSeriesByCategory = data.reduce<Record<string, Record<string, string | number>>>(
    (acc, row) => {
      const category = String(row.category ?? "Unknown");
      const series = String(row.series ?? "Series");
      const value = Number(row.value ?? 0);
      if (!acc[category]) {
        acc[category] = { category };
      }
      acc[category][series] = value;
      return acc;
    },
    {}
  );

  const stackedData = Object.values(barSeriesByCategory);
  const stackedSeriesKeys = Array.from(
    new Set(data.map((d) => d.series).filter((v): v is string => typeof v === "string" && v.trim().length > 0))
  );
  const groupedData = stackedSeriesKeys.length > 0 ? stackedData : data;
  const groupedSeriesKeys = stackedSeriesKeys;

  const waterfallData = data.reduce<
    Array<{
      category: string;
      base: number;
      delta: number;
      deltaAbs: number;
      end: number;
      color_index?: number;
      positive: boolean;
    }>
  >((acc, row) => {
    const prevEnd = acc.length > 0 ? acc[acc.length - 1].end : 0;
    const delta = Number(row.value || 0);
    const end = prevEnd + delta;
    const base = Math.min(prevEnd, end);
    acc.push({
      category: String(row.category || "Stage"),
      base,
      delta,
      deltaAbs: Math.abs(delta),
      end,
      color_index: row.color_index,
      positive: delta >= 0,
    });
    return acc;
  }, []);

  const ganttData = data.map((row, index) => {
    const parsedStart = Number(row.start);
    const fallbackStart = Number.isFinite(parsedStart) ? parsedStart : index * 10;
    const parsedEnd = Number(row.end);
    const fallbackEnd = Number.isFinite(parsedEnd) ? parsedEnd : fallbackStart + Number(row.value || 1);
    return {
      category: String(row.category || row.label || `Task ${index + 1}`),
      startValue: fallbackStart,
      duration: Math.max(0.5, fallbackEnd - fallbackStart),
      color_index: row.color_index,
    };
  });

  const heatmapXLabels = Array.from(new Set(data.map((row, idx) => String(row.x ?? row.category ?? `X${idx + 1}`))));
  const heatmapYLabels = Array.from(new Set(data.map((row, idx) => String(row.y ?? row.series ?? `Y${idx + 1}`))));
  const heatmapCells = data.map((row, idx) => {
    const x = String(row.x ?? row.category ?? `X${idx + 1}`);
    const y = String(row.y ?? row.series ?? `Y${idx + 1}`);
    return {
      x,
      y,
      value: Number(row.value || 0),
      colorIndex: row.color_index ?? idx,
    };
  });
  const heatmapMax = Math.max(1, ...heatmapCells.map((c) => Math.abs(c.value)));

  const gaugeSource = data[0];
  const gaugeMin = Number(gaugeSource?.min ?? 0);
  const gaugeMax = Number(gaugeSource?.max ?? 100);
  const gaugeRaw = Number(gaugeSource?.value ?? 0);
  const gaugePct = Math.max(0, Math.min(100, ((gaugeRaw - gaugeMin) / Math.max(1, gaugeMax - gaugeMin)) * 100));

  const bulletMax = Math.max(
    1,
    ...data.map((d) => Number(d.max ?? d.target ?? d.value ?? 0)),
    ...data.map((d) => Number(d.value ?? 0))
  );

  const vennValues = {
    a: Number(data[0]?.value ?? 0),
    b: Number(data[1]?.value ?? 0),
    overlap: Number(data[2]?.value ?? 0),
    aLabel: String(data[0]?.category || "Set A"),
    bLabel: String(data[1]?.category || "Set B"),
  };

  const shouldShowLegend =
    (Boolean(config.show_legend) || (isExporting && ["pie", "donut"].includes(config.chart_type || ""))) &&
    [
      "pie",
      "donut",
      "stacked_bar",
      "clustered_column",
      "clustered_bar",
      "comparison",
      "radar",
      "bubble",
      "scatter",
      "waterfall",
      "diverging_bar",
    ].includes(config.chart_type || "");
  const pieTotal = data.reduce((sum, item) => sum + Number(item.value || 0), 0);
  const truncateLegendLabel = (value: string) => {
    const max = isMobile ? 28 : 44;
    return value.length > max ? `${value.slice(0, max - 1)}...` : value;
  };

  const renderBars = (points: ChartPoint[]) =>
    points.map((entry, index) => (
      <Cell key={`cell-${index}`} fill={colors[(entry.color_index ?? index) % colors.length]} />
    ));

  const renderChart = () => {
    switch (config.chart_type) {
      case "bar":
      case "horizontal_bar": {
        const isHorizontal = config.chart_type === "horizontal_bar";
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart
              data={data}
              layout={isHorizontal ? "vertical" : "horizontal"}
              margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 20, left: isMobile ? 8 : 18 }}
            >
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              {isHorizontal ? (
                <>
                  <XAxis type="number" tick={{ fontSize: axisFontSize, fill: tickColor }} />
                  <YAxis type="category" dataKey="category" width={isMobile ? 95 : 135} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
                </>
              ) : (
                <>
                  <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 48} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
                  <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
                </>
              )}
              <Tooltip
                contentStyle={{
                  borderRadius: "10px",
                  border: "1px solid #e2e8f0",
                  boxShadow: "0 8px 24px rgba(15,23,42,0.14)",
                  fontSize: "12px",
                }}
                formatter={(value: number | string) => [String(value), config.legend_title || "Value"]}
              />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {renderBars(data)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
      }
      case "clustered_column":
      case "comparison": {
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={groupedData} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              {groupedSeriesKeys.map((series, idx) => (
                <Bar key={series} dataKey={series} fill={colors[idx % colors.length]} radius={[6, 6, 0, 0]} />
              ))}
              {!groupedSeriesKeys.length && (
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {renderBars(data)}
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        );
      }
      case "clustered_bar": {
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={groupedData} layout="vertical" margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 20, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis type="number" tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis type="category" dataKey="category" width={isMobile ? 95 : 135} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <Tooltip />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              {groupedSeriesKeys.map((series, idx) => (
                <Bar key={series} dataKey={series} fill={colors[idx % colors.length]} radius={[0, 6, 6, 0]} />
              ))}
              {!groupedSeriesKeys.length && (
                <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                  {renderBars(data)}
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        );
      }
      case "stacked_bar": {
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={stackedData} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              {stackedSeriesKeys.map((series, idx) => (
                <Bar key={series} dataKey={series} stackId="stack" fill={colors[idx % colors.length]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        );
      }
      case "line":
      case "area": {
        const Chart = config.chart_type === "area" ? AreaChart : LineChart;
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <Chart data={data} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              {config.chart_type === "area" ? (
                <Area type="monotone" dataKey="value" stroke={colors[0]} fill={`${colors[0]}33`} strokeWidth={2} />
              ) : (
                <Line type="monotone" dataKey="value" stroke={colors[0]} strokeWidth={2} dot={{ r: 3 }} />
              )}
            </Chart>
          </ResponsiveContainer>
        );
      }
      case "pie":
      case "donut":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <PieChart>
              <Pie
                data={data}
                dataKey="value"
                nameKey="category"
                cx="50%"
                cy="50%"
                innerRadius={config.chart_type === "donut" ? (isMobile ? 48 : 60) : 0}
                outerRadius={isMobile ? 92 : 110}
                label={({ category, percent }: { category?: string; percent?: number }) =>
                  isMobile && !isExporting
                    ? `${(((percent ?? 0) as number) * 100).toFixed(0)}%`
                    : `${truncateCategory(category || "Category")}: ${(((percent ?? 0) as number) * 100).toFixed(0)}%`
                }
                labelLine={!isMobile || isExporting}
              >
                {renderBars(data)}
              </Pie>
              <Tooltip
                contentStyle={{
                  borderRadius: "10px",
                  border: "1px solid #e2e8f0",
                  boxShadow: "0 8px 24px rgba(15,23,42,0.14)",
                  fontSize: "12px",
                }}
                formatter={(
                  value: number | string,
                  _name: string,
                  payload: { payload?: { category?: string } }
                ) => [String(value), String(payload?.payload?.category || "Value")]}
              />
            </PieChart>
          </ResponsiveContainer>
        );
      case "scatter":
      case "bubble":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ScatterChart margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis type="number" dataKey="x" name={config.x_label || "X"} tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis type="number" dataKey="y" name={config.y_label || "Y"} tick={{ fontSize: axisFontSize, fill: tickColor }} />
              {config.chart_type === "bubble" && <ZAxis type="number" dataKey="z" range={[40, 380]} name="Size" />}
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              <Scatter
                data={data.map((item, idx) => ({
                  ...item,
                  x: Number(item.x ?? idx + 1),
                  y: Number(item.y ?? item.value ?? 0),
                  z: Number(item.z ?? item.size ?? item.value ?? 1),
                }))}
                fill={colors[0]}
              >
                {renderBars(data)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        );
      case "radar":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <RadarChart data={data} outerRadius={isMobile ? 90 : 110}>
              <PolarGrid />
              <PolarAngleAxis dataKey="category" tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <PolarRadiusAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              <Radar name={config.legend_title || "Value"} dataKey="value" stroke={colors[0]} fill={colors[0]} fillOpacity={0.28} />
            </RadarChart>
          </ResponsiveContainer>
        );
      case "heatmap":
        return (
          <div className="w-full overflow-auto">
            <div
              className="grid gap-1"
              style={{
                gridTemplateColumns: `minmax(72px, auto) repeat(${Math.max(1, heatmapXLabels.length)}, minmax(${isMobile ? 56 : 72}px, 1fr))`,
              }}
            >
              <div className="text-[10px] sm:text-xs text-slate-500 font-medium p-1">{config.y_label || "Y"}</div>
              {heatmapXLabels.map((xLabel) => (
                <div key={`hx-${xLabel}`} className="text-[10px] sm:text-xs text-slate-500 text-center p-1 truncate" title={xLabel}>
                  {truncateCategory(xLabel)}
                </div>
              ))}
              {heatmapYLabels.map((yLabel) => (
                <div key={`hy-row-${yLabel}`} className="contents">
                  <div className="text-[10px] sm:text-xs text-slate-500 p-1 truncate" title={yLabel}>
                    {truncateCategory(yLabel)}
                  </div>
                  {heatmapXLabels.map((xLabel) => {
                    const cell = heatmapCells.find((c) => c.x === xLabel && c.y === yLabel);
                    const value = cell?.value ?? 0;
                    const baseColor = colors[(cell?.colorIndex ?? 0) % colors.length];
                    const opacity = 0.18 + (Math.abs(value) / heatmapMax) * 0.82;
                    return (
                      <div
                        key={`hcell-${xLabel}-${yLabel}`}
                        className="h-10 sm:h-12 rounded-md border border-slate-100 flex items-center justify-center text-[10px] sm:text-xs font-medium text-slate-800"
                        style={{ backgroundColor: `${baseColor}${Math.round(opacity * 255).toString(16).padStart(2, "0")}` }}
                        title={`${xLabel} / ${yLabel}: ${value}`}
                      >
                        {value}
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        );
      case "pyramid":
      case "funnel":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <FunnelChart>
              <Tooltip />
              <Funnel dataKey="value" data={data} isAnimationActive nameKey="category">
                {data.map((entry, idx) => (
                  <Cell key={`funnel-cell-${idx}`} fill={colors[(entry.color_index ?? idx) % colors.length]} />
                ))}
              </Funnel>
            </FunnelChart>
          </ResponsiveContainer>
        );
      case "waterfall":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={waterfallData} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip formatter={(value: number | string, name: string) => (name === "deltaAbs" ? [String(value), "Change"] : [String(value), name])} />
              {shouldShowLegend && <Legend wrapperStyle={{ fontSize: axisFontSize, color: tickColor }} />}
              <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
              <Bar dataKey="base" stackId="wf" fill="transparent" />
              <Bar dataKey="deltaAbs" stackId="wf" name="Change">
                {waterfallData.map((entry, idx) => (
                  <Cell key={`wf-${idx}`} fill={entry.positive ? colors[(entry.color_index ?? idx) % colors.length] : "#ef4444"} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        );
      case "gantt":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={ganttData} layout="vertical" margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 20, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis type="number" tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis type="category" dataKey="category" width={isMobile ? 95 : 135} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <Tooltip />
              <Bar dataKey="startValue" stackId="g" fill="transparent" />
              <Bar dataKey="duration" stackId="g" name={config.legend_title || "Duration"}>
                {ganttData.map((entry, idx) => (
                  <Cell key={`g-${idx}`} fill={colors[(entry.color_index ?? idx) % colors.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
      case "histogram":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={data} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 20, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -18} textAnchor="end" height={isMobile ? 64 : 48} tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                {renderBars(data)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
      case "bullet":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ComposedChart data={data} layout="vertical" margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 20, left: isMobile ? 8 : 18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" domain={[0, Math.ceil(bulletMax * 1.15)]} tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis type="category" dataKey="category" width={isMobile ? 95 : 135} tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <Tooltip />
              <Bar dataKey="value" name={config.legend_title || "Actual"} radius={[0, 6, 6, 0]}>
                {renderBars(data)}
              </Bar>
              {data.some((d) => typeof d.target === "number") && (
                <Scatter
                  name="Target"
                  data={data.map((d, idx) => ({
                    category: d.category,
                    x: Number(d.target ?? d.value),
                    y: idx,
                  }))}
                  shape="cross"
                  fill="#0f172a"
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        );
      case "gauge":
        return (
          <div className="relative">
            <ResponsiveContainer width="100%" height={chartHeight}>
              <RadialBarChart cx="50%" cy="80%" innerRadius="60%" outerRadius="95%" barSize={18} data={[{ value: gaugePct }]} startAngle={180} endAngle={0}>
                <RadialBar dataKey="value" cornerRadius={10} fill={colors[0]} />
                <Tooltip formatter={(value: number | string) => [`${Number(value).toFixed(1)}%`, "Progress"]} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <div className="text-center mt-8">
                <p className="text-xl sm:text-2xl font-semibold text-slate-700">{gaugeRaw.toFixed(1)}</p>
                <p className="text-[11px] sm:text-xs text-slate-500">Range: {gaugeMin} to {gaugeMax}</p>
              </div>
            </div>
          </div>
        );
      case "diverging_bar":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={data} layout="vertical" margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 20, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis type="number" tick={{ fontSize: axisFontSize, fill: tickColor }} />
              <YAxis type="category" dataKey="category" width={isMobile ? 95 : 135} tick={{ fontSize: axisFontSize, fill: tickColor }} tickFormatter={(value) => truncateCategory(String(value))} />
              <Tooltip />
              <ReferenceLine x={0} stroke="#64748b" />
              <Bar dataKey="value" radius={[0, 6, 6, 0]}>
                {data.map((entry, idx) => (
                  <Cell key={`db-${idx}`} fill={Number(entry.value) >= 0 ? colors[(entry.color_index ?? idx) % colors.length] : "#ef4444"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
      case "venn":
        return (
          <div className="h-[270px] sm:h-[320px] w-full flex items-center justify-center">
            <svg width="320" height="220" viewBox="0 0 320 220" role="img" aria-label="Venn diagram">
              <circle cx="130" cy="110" r="68" fill={colors[0]} fillOpacity="0.45" stroke="#334155" />
              <circle cx="190" cy="110" r="68" fill={colors[1] || "#f59e0b"} fillOpacity="0.45" stroke="#334155" />
              <text x="95" y="40" fontSize="12" fill="#334155">{truncateCategory(vennValues.aLabel)}</text>
              <text x="185" y="40" fontSize="12" fill="#334155">{truncateCategory(vennValues.bLabel)}</text>
              <text x="95" y="112" fontSize="14" fill="#0f172a">{vennValues.a}</text>
              <text x="185" y="112" fontSize="14" fill="#0f172a">{vennValues.b}</text>
              <text x="151" y="112" fontSize="14" fill="#0f172a">{vennValues.overlap}</text>
            </svg>
          </div>
        );
      default:
        return (
          <div className="h-56 flex items-center justify-center text-sm text-gray-500 dark:text-gray-300">
            Unsupported chart type.
          </div>
        );
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-md p-4 mt-3 border border-gray-100 dark:bg-gray-900 dark:border-gray-700">
      <div className="flex flex-wrap justify-between items-start gap-3 mb-4">
        <h3 className="text-base sm:text-lg font-semibold text-gray-800 dark:text-gray-100">{config.title}</h3>
        <button
          onClick={handleDownload}
          disabled={downloading}
          className="flex items-center gap-1.5 px-3 py-2 text-xs sm:text-sm font-medium bg-gradient-to-r from-indigo-600 to-violet-600 text-white rounded-lg hover:from-indigo-700 hover:to-violet-700 disabled:opacity-60 disabled:cursor-not-allowed"
          title="Download chart as PNG"
        >
          {downloading ? "Saving..." : "Download PNG"}
        </button>
      </div>

      <div ref={chartRef} className="bg-white rounded-lg p-1 dark:bg-gray-900 overflow-x-auto">
        <div style={minCanvasWidth ? { minWidth: `${minCanvasWidth}px` } : undefined}>
          {renderChart()}
        </div>
      </div>

      {(config.chart_type === "pie" || config.chart_type === "donut") && shouldShowLegend && data.length > 0 && (
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1.5 text-[11px] sm:text-xs text-slate-600 dark:text-slate-200">
          {data.map((entry, index) => {
            const color = colors[(entry.color_index ?? index) % colors.length];
            const pct = pieTotal > 0 ? Math.round((Number(entry.value || 0) / pieTotal) * 100) : 0;
            return (
              <div key={`${entry.category}-${index}`} className="flex items-start gap-2 min-w-0">
                <span className="mt-[4px] h-2.5 w-2.5 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
                <span className="leading-4 break-words">
                  {truncateLegendLabel(String(entry.category || "Category"))} ({pct}%)
                </span>
              </div>
            );
          })}
        </div>
      )}

      {config.chart_type !== "pie" && config.chart_type !== "donut" && (config.x_label || config.y_label) && (
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] sm:text-xs text-slate-500 dark:text-slate-300">
          {config.x_label && <span>X-axis: {config.x_label}</span>}
          {config.y_label && <span>Y-axis: {config.y_label}</span>}
        </div>
      )}

      {config.note && (
        <p className="text-xs text-gray-500 mt-3 italic border-l-2 border-indigo-200 pl-3 dark:text-gray-300 dark:border-indigo-500">
          {config.note}
        </p>
      )}
    </div>
  );
}
