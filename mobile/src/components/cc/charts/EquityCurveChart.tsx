import React from "react";
import { View } from "react-native";
import Svg, { Path, Rect } from "react-native-svg";
import { useTheme } from "../../../utils/useTheme";
import type { EquityPoint } from "../../../commandCenter/types";

function clamp01(x: number): number {
  if (!isFinite(x)) return 0;
  return Math.max(0, Math.min(1, x));
}

function pathFrom(points: { x: number; y: number }[]): string {
  if (!points.length) return "";
  const [p0, ...rest] = points;
  let d = `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)}`;
  for (const p of rest) d += ` L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
  return d;
}

export function EquityCurveChart({ data, height = 140 }: { data: EquityPoint[]; height?: number }) {
  const theme = useTheme();
  const width = 320; // svg viewBox width; scales to container

  if (!data.length) return <View style={{ height }} />;

  const navs = data.map((p) => p.navUsd);
  const min = Math.min(...navs);
  const max = Math.max(...navs);
  const span = Math.max(1e-9, max - min);

  const pts = data.map((p, i) => {
    const x = (i / Math.max(1, data.length - 1)) * width;
    const y = (1 - clamp01((p.navUsd - min) / span)) * height;
    return { x, y };
  });

  const line = pathFrom(pts);
  const area = `${line} L ${width.toFixed(2)} ${height.toFixed(2)} L 0 ${height.toFixed(2)} Z`;

  // Very lightweight regime overlay: faint bands where regime changes.
  const bands: { x: number; w: number }[] = [];
  let last = data[0].regime ?? "";
  let start = 0;
  for (let i = 1; i < data.length; i++) {
    const r = data[i].regime ?? "";
    if (r !== last) {
      const x0 = (start / Math.max(1, data.length - 1)) * width;
      const x1 = (i / Math.max(1, data.length - 1)) * width;
      bands.push({ x: x0, w: Math.max(2, x1 - x0) });
      start = i;
      last = r;
    }
  }
  // last segment
  const x0 = (start / Math.max(1, data.length - 1)) * width;
  bands.push({ x: x0, w: Math.max(2, width - x0) });

  return (
    <View style={{ height, width: "100%" }}>
      <Svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`}>
        {bands.map((b, idx) => (
          <Rect
            key={idx}
            x={b.x}
            y={0}
            width={b.w}
            height={height}
            fill={idx % 2 === 0 ? "rgba(255,255,255,0.02)" : "rgba(34,211,238,0.03)"}
          />
        ))}
        <Path d={area} fill={theme.colors.chartFill0} />
        <Path d={line} stroke={theme.colors.chartLine} strokeWidth={2.2} fill="none" />
      </Svg>
    </View>
  );
}
