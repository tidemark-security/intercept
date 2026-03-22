"use client";
/*
 * Bar Chart Component
 * Uses recharts for data visualization
 */

import React from "react";
import {
  BarChart as RechartsBarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/utils/cn";

const DEFAULT_COLORS = [
  "#b6e600",
  "#f3ff90",
  "#8db800",
  "#e5ff50",
  "#6a8b00",
  "#d0ff00",
];

export interface BarChartProps {
  className?: string;
  data: Array<Record<string, unknown>>;
  dataKeys: string[];
  xAxisKey?: string;
  colors?: string[];
  stacked?: boolean;
  showGrid?: boolean;
  showLegend?: boolean;
  showTooltip?: boolean;
  barRadius?: number;
}

const BarChart = React.forwardRef<HTMLDivElement, BarChartProps>(
  function BarChart(
    {
      className,
      data,
      dataKeys,
      xAxisKey = "name",
      colors = DEFAULT_COLORS,
      stacked = false,
      showGrid = true,
      showLegend = true,
      showTooltip = true,
      barRadius = 4,
    }: BarChartProps,
    ref
  ) {
    return (
      <div ref={ref} className={cn("h-80 w-full", className)}>
        <ResponsiveContainer width="100%" height="100%">
          <RechartsBarChart data={data}>
            {showGrid && (
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            )}
            <XAxis
              dataKey={xAxisKey}
              stroke="#9ca3af"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#9ca3af"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            {showTooltip && (
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1f2937",
                  border: "1px solid #374151",
                  borderRadius: "8px",
                  color: "#f9fafb",
                }}
              />
            )}
            {showLegend && <Legend />}
            {dataKeys.map((key, index) => (
              <Bar
                key={key}
                dataKey={key}
                fill={colors[index % colors.length]}
                stackId={stacked ? "stack" : undefined}
                radius={[barRadius, barRadius, 0, 0]}
              />
            ))}
          </RechartsBarChart>
        </ResponsiveContainer>
      </div>
    );
  }
);

export { BarChart };
