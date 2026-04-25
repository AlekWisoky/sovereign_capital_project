import React from "react";
import { View } from "react-native";
import Svg, { Path } from "react-native-svg";
import { useTheme } from "../../../utils/useTheme";

type Point = { x: number; y: number };

function pathFrom(points: Point[]): string {
  if (!points.length) return "";
  const [p0, ...rest] = points;
  let d = `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)}`;
  for (const p of rest) d += ` L ${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
  return d;
}

export function MultiLineChart(props: {
  a: number[];
  b: number[];
  height?: number;
}) {
  const theme = useTheme();
  const height = props.height ?? 120;
  const width = 320;
  const n = Math.max(props.a.length, props.b.length);
  if (!n) return <View style={{ height }} />;

  const all = [...props.a, ...props.b].filter((x) => isFinite(x));
  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = Math.max(1e-9, max - min);

  function pts(series: number[]): Point[] {
    return Array.from({ length: n }).map((_, i) => {
      const v = Number(series[i] ?? series[series.length - 1] ?? 0);
      const x = (i / Math.max(1, n - 1)) * width;
      const y = (1 - (v - min) / span) * height;
      return { x, y };
    });
  }

  const da = pathFrom(pts(props.a));
  const db = pathFrom(pts(props.b));

  return (
    <View style={{ height, width: "100%" }}>
      <Svg width="100%" height="100%" viewBox={`0 0 ${width} ${height}`}>
        <Path d={da} stroke={theme.colors.cyan} strokeWidth={2.2} fill="none" />
        <Path d={db} stroke={theme.colors.violet} strokeWidth={2.2} fill="none" />
      </Svg>
    </View>
  );
}
