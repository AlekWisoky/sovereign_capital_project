import React, { useMemo } from "react";
import Svg, { Path, Defs, LinearGradient, Stop } from "react-native-svg";
import { useTheme } from "../../../utils/useTheme";

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

export function AreaChart(props: { width: number; height: number; data: readonly number[] }) {
  const theme = useTheme();
  const { width, height, data } = props;

  const d = useMemo(() => {
    const n = data.length;
    if (n < 2) return "";
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const pts = data.map((v, i) => {
      const x = (i / (n - 1)) * width;
      const y = height - clamp01((v - min) / range) * height;
      return { x, y };
    });

    let path = `M ${pts[0].x.toFixed(2)} ${pts[0].y.toFixed(2)}`;
    for (let i = 1; i < pts.length; i += 1) {
      path += ` L ${pts[i].x.toFixed(2)} ${pts[i].y.toFixed(2)}`;
    }
    // close to baseline for fill
    path += ` L ${pts[pts.length - 1].x.toFixed(2)} ${height.toFixed(2)} L ${pts[0].x.toFixed(2)} ${height.toFixed(2)} Z`;
    return path;
  }, [data, width, height]);

  if (!d) return null;

  return (
    <Svg width={width} height={height}>
      <Defs>
        <LinearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={theme.colors.cyan} stopOpacity={0.35} />
          <Stop offset="1" stopColor={theme.colors.violet} stopOpacity={0.05} />
        </LinearGradient>
      </Defs>
      <Path d={d} fill="url(#grad)" stroke={theme.colors.chartLine} strokeWidth={2} />
    </Svg>
  );
}
