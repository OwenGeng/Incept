"use client";

import { useEffect, useRef } from "react";

const PALETTE = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"];

export interface HBarRow {
  label: string;
  barWidth: number;      // 0-100
  displayValue: string;  // text shown at bar end and in tooltip
  color?: string;
}

interface EHBarProps {
  rows: HBarRow[];
  /** Defaults to max(120, rows.length × 44) */
  height?: number;
}

export function EHBar({ rows, height }: EHBarProps) {
  const ref = useRef<HTMLDivElement>(null);
  const h = height ?? Math.max(120, rows.length * 44);

  useEffect(() => {
    if (!ref.current) return;

    let disposed = false;
    let chart: import("echarts").ECharts | undefined;

    const init = async () => {
      const echarts = await import("echarts");
      if (disposed || !ref.current) return;

      chart = echarts.init(ref.current, null, { renderer: "svg" });

      chart.setOption({
        tooltip: {
          trigger: "axis",
          axisPointer: { type: "shadow" },
          formatter: (params: unknown) => {
            const list = params as Array<{
              marker: string;
              name: string;
              data: { displayValue: string };
            }>;
            const p = list[0];
            return `${p.marker}<b>${p.name}</b>: ${p.data.displayValue}`;
          },
          backgroundColor: "#ffffff",
          borderColor: "#EDF0F7",
          borderWidth: 1,
          textStyle: { color: "#1F2230", fontSize: 12 },
          extraCssText:
            "box-shadow:0 4px 16px rgba(31,34,48,.10);border-radius:12px;padding:8px 12px;",
        },
        grid: { left: 12, right: 56, top: 4, bottom: 4, containLabel: true },
        xAxis: { type: "value", max: 100, show: false },
        yAxis: {
          type: "category",
          data: rows.map((r) => r.label),
          axisLine: { show: false },
          axisTick: { show: false },
          axisLabel: { color: "#1F2230", fontSize: 13, margin: 10 },
        },
        series: [
          {
            type: "bar",
            barMaxWidth: 20,
            barMinHeight: 4,
            itemStyle: { borderRadius: [0, 6, 6, 0] },
            label: {
              show: true,
              position: "right",
              distance: 6,
              color: "#8B92A8",
              fontSize: 11,
              fontWeight: "bold",
              formatter: (params: unknown) => {
                const p = params as { data: { displayValue: string } };
                return p.data.displayValue;
              },
            },
            emphasis: {
              itemStyle: { shadowBlur: 8, shadowColor: "rgba(0,0,0,.12)" },
            },
            showBackground: true,
            backgroundStyle: { color: "#F1F3FA", borderRadius: [0, 6, 6, 0] },
            data: rows.map((r, i) => ({
              value: r.barWidth,
              displayValue: r.displayValue,
              itemStyle: { color: r.color ?? PALETTE[i % PALETTE.length] },
            })),
          },
        ],
      });
    };

    const handleResize = () => chart?.resize();
    window.addEventListener("resize", handleResize);

    init();

    return () => {
      disposed = true;
      window.removeEventListener("resize", handleResize);
      chart?.dispose();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(rows), h]);

  return <div ref={ref} style={{ height: h, width: "100%" }} />;
}
