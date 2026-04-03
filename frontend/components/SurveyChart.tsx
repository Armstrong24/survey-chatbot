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
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
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

    try {
      const dataUrl = await toPng(chartRef.current, {
        quality: 1,
        backgroundColor: "#ffffff",
        pixelRatio: 2,
        cacheBust: true,
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
  const needsWideCanvas = ["bar", "horizontal_bar", "line", "area", "stacked_bar"].includes(
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
              margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}
            >
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              {isHorizontal ? (
                <>
                  <XAxis type="number" label={isMobile ? undefined : { value: config.y_label || "", position: "insideBottom", offset: -8 }} tick={{ fontSize: isMobile ? 10 : 12 }} />
                  <YAxis type="category" dataKey="category" width={isMobile ? 90 : 120} label={isMobile ? undefined : { value: config.x_label || "", angle: -90, position: "insideLeft" }} tick={{ fontSize: isMobile ? 10 : 12 }} />
                </>
              ) : (
                <>
                  <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -20} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: isMobile ? 10 : 12 }} label={isMobile ? undefined : { value: config.x_label || "", position: "insideBottom", offset: -8 }} />
                  <YAxis tick={{ fontSize: isMobile ? 10 : 12 }} label={isMobile ? undefined : { value: config.y_label || "", angle: -90, position: "insideLeft" }} />
                </>
              )}
              <Tooltip formatter={(value: number | string) => [String(value), config.legend_title || "Value"]} />
              {config.show_legend && <Legend />}
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {renderBars(data)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        );
      }
      case "stacked_bar": {
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart data={stackedData} margin={{ top: 10, right: isMobile ? 8 : 18, bottom: isMobile ? 36 : 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -20} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: isMobile ? 10 : 12 }} />
              <YAxis tick={{ fontSize: isMobile ? 10 : 12 }} />
              <Tooltip />
              {config.show_legend && <Legend wrapperStyle={{ fontSize: isMobile ? 10 : 12 }} />}
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
              <XAxis dataKey="category" interval={0} angle={isMobile ? -32 : -20} textAnchor="end" height={isMobile ? 64 : 50} tick={{ fontSize: isMobile ? 10 : 12 }} label={isMobile ? undefined : { value: config.x_label || "", position: "insideBottom", offset: -8 }} />
              <YAxis tick={{ fontSize: isMobile ? 10 : 12 }} label={isMobile ? undefined : { value: config.y_label || "", angle: -90, position: "insideLeft" }} />
              <Tooltip />
              {config.show_legend && <Legend wrapperStyle={{ fontSize: isMobile ? 10 : 12 }} />}
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
                  isMobile
                    ? `${(((percent ?? 0) as number) * 100).toFixed(0)}%`
                    : `${category || "Category"}: ${(((percent ?? 0) as number) * 100).toFixed(0)}%`
                }
                labelLine={!isMobile}
              >
                {renderBars(data)}
              </Pie>
              <Tooltip
                formatter={(
                  value: number | string,
                  _name: string,
                  payload: { payload?: { category?: string } }
                ) => [String(value), String(payload?.payload?.category || "Value")]}
              />
              {config.show_legend && <Legend wrapperStyle={{ fontSize: isMobile ? 10 : 12 }} />}
            </PieChart>
          </ResponsiveContainer>
        );
      case "scatter":
        return (
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ScatterChart margin={{ top: 10, right: isMobile ? 8 : 18, bottom: 25, left: isMobile ? 8 : 18 }}>
              {config.show_grid && <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />}
              <XAxis type="number" dataKey="x" name={config.x_label || "X"} tick={{ fontSize: isMobile ? 10 : 12 }} />
              <YAxis type="number" dataKey="y" name={config.y_label || "Y"} tick={{ fontSize: isMobile ? 10 : 12 }} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              {config.show_legend && <Legend wrapperStyle={{ fontSize: isMobile ? 10 : 12 }} />}
              <Scatter data={data} fill={colors[0]}>
                {renderBars(data)}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
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

      {config.note && (
        <p className="text-xs text-gray-500 mt-3 italic border-l-2 border-indigo-200 pl-3 dark:text-gray-300 dark:border-indigo-500">
          {config.note}
        </p>
      )}
    </div>
  );
}
