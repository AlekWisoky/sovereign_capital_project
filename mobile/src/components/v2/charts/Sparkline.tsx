import React, { useMemo } from "react";
import Svg, { Path } from "react-native-svg";
import { useTheme } from "../../../utils/useTheme";

function clamp01(x: number): number {
  return Math.max(0, Math.min(1, x));
}

export function Sparkline(props: { width: number; height: number; data: readonly number[]; tone?: "neutral" | "good" | "danger" }) {
  const theme = useTheme();
  const { width, height, data } = props;
  const tone = props.tone ?? "neutral";
  const stroke = tone === "good" ? theme.colors.good : tone === "danger" ? theme.colors.danger : theme.colors.cyan;

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
    return path;
  }, [data, width, height]);

  if (!d) return null;
  return (
    <Svg width={width} height={height}>
      <Path d={d} stroke={stroke} strokeWidth={2} fill="none" opacity={0.9} />
    </Svg>
  );
}
