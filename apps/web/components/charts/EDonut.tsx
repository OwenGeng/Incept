"use client";

import { useEffect, useRef } from "react";

const PALETTE = ["#3a86ff", "#8338ec", "#ff006e", "#fb5607", "#ffbe0b"];

export interface DonutRow {
  label: string;
  /** Display string shown in legend and tooltip (e.g. "72%") */
  value: string;
  /** Numeric proportion used to size the arc */
  amount: number;
  color?: string;
}

interface EDonutProps {
  rows: DonutRow[];
  height?: number;
}

export function EDonut({ rows, height = 200 }: EDonutProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;

    // Keep reference so cleanup can dispose even if init is async
    let disposed = false;
    let chart: import("echarts").ECharts | undefined;

    const init = async () => {
      const echarts = await import("echarts");
      if (disposed || !ref.current) return;

      chart = echarts.init(ref.current, null, { renderer: "svg" });

      const seriesData = rows.map((row, i) => ({
        name: row.label,
        value: row.amount,
        // store display string for tooltip formatter
        displayValue: row.value,
        itemStyle: { color: row.color ?? PALETTE[i % PALETTE.length] },
      }));

      chart.setOption({
        tooltip: {
          trigger: "item",
          formatter: (params: unknown) => {
            const p = params as {
              marker: string;
              name: string;
              data: { displayValue: string };
              percent: number;
            };
            return `${p.marker}<b>${p.name}</b><br/>${p.data.displayValue} (${p.percent.toFixed(1)}%)`;
          },
          backgroundColor: "#ffffff",
          borderColor: "#EDF0F7",
          borderWidth: 1,
          textStyle: { color: "#1F2230", fontSize: 12 },
          extraCssText:
            "box-shadow:0 4px 16px rgba(31,34,48,.10);border-radius:12px;padding:8px 12px;",
        },
        legend: {
          type: "scroll",
          orient: "vertical",
          right: "2%",
          top: 8,
          bottom: 8,
          icon: "circle",
          itemWidth: 8,
          itemHeight: 8,
          itemGap: 8,
          pageIconSize: 10,
          pageTextStyle: { fontSize: 10 },
          formatter: (name: string) => {
            const row = rows.find((r) => r.label === name);
            return `{nm|${name}}  {vl|${row?.value ?? ""}}`;
          },
          textStyle: {
            rich: {
              nm: { color: "#1F2230", fontSize: 12 },
              vl: { color: "#8B92A8", fontSize: 11, fontWeight: "bold" },
            },
          },
        },
        series: [
          {
            type: "pie",
            radius: ["42%", "70%"],
            center: ["32%", "50%"],
            avoidLabelOverlap: false,
            label: { show: false },
            emphasis: {
              scale: true,
              scaleSize: 6,
              label: { show: false },
              itemStyle: { shadowBlur: 16, shadowColor: "rgba(0,0,0,.12)" },
            },
            data: seriesData,
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
  }, [JSON.stringify(rows), height]);

  return <div ref={ref} style={{ height, width: "100%" }} />;
}
