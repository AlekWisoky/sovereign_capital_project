import React, { useMemo } from "react";
import Svg, { Circle, Line, Text as SvgText } from "react-native-svg";
import type { Leg } from "../../utils/types";
import { useTheme } from "../../utils/useTheme";
import { fmtShortHash } from "../../utils/format";

export function RouteGraph(props: { width: number; height: number; path: readonly string[]; legs: readonly Leg[] }) {
  const theme = useTheme();
  const { width, height, path, legs } = props;

  const nodes = useMemo(() => {
    const n = Math.max(2, path.length);
    const pad = 18;
    const usable = Math.max(1, width - pad * 2);
    const step = usable / (n - 1);
    return path.map((tok, i) => ({ tok, x: pad + i * step, y: height / 2 }));
  }, [path, width, height]);

  return (
    <Svg width={width} height={height}>
      {nodes.slice(0, -1).map((a, i) => {
        const b = nodes[i + 1];
        const dex = legs[i]?.dex ?? "";
        const dexLabel = String(dex).toUpperCase();
        const mx = (a.x + b.x) / 2;
        return (
          <React.Fragment key={`e_${i}`}>
            <Line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={theme.colors.border} strokeWidth={2} />
            <SvgText x={mx} y={a.y - 10} fontSize={10} fill={theme.colors.textMuted} textAnchor="middle">
              {dexLabel}
            </SvgText>
          </React.Fragment>
        );
      })}

      {nodes.map((n, i) => (
        <React.Fragment key={`n_${i}`}>
          <Circle cx={n.x} cy={n.y} r={10} fill={theme.colors.surface2} stroke={theme.colors.cyan} strokeWidth={2} />
          <SvgText x={n.x} y={n.y + 26} fontSize={10} fill={theme.colors.textFaint} textAnchor="middle">
            {fmtShortHash(n.tok, 4)}
          </SvgText>
        </React.Fragment>
      ))}
    </Svg>
  );
}
