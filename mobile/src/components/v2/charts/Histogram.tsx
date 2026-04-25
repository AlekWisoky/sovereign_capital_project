import React, { useMemo } from "react";
import Svg, { Rect } from "react-native-svg";
import { useTheme } from "../../../utils/useTheme";

export function Histogram(props: { width: number; height: number; bins: readonly number[] }) {
  const theme = useTheme();
  const { width, height, bins } = props;

  const bars = useMemo(() => {
    if (bins.length === 0) return [];
    const max = Math.max(...bins, 1);
    const barW = width / bins.length;
    return bins.map((v, i) => {
      const h = (v / max) * height;
      return { x: i * barW, y: height - h, w: Math.max(1, barW - 2), h };
    });
  }, [bins, width, height]);

  if (!bars.length) return null;

  return (
    <Svg width={width} height={height}>
      {bars.map((b, idx) => (
        <Rect
          key={idx}
          x={b.x}
          y={b.y}
          width={b.w}
          height={b.h}
          rx={4}
          fill={theme.colors.chartLine}
          opacity={0.65}
        />
      ))}
    </Svg>
  );
}
