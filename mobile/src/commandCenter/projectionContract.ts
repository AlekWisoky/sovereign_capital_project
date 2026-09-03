    observedTruthFamily: summaryContract?.truthFamily,
    observedReadModel: summaryContract?.readModel,
    fallbackUsed: Boolean(expectation.fallbackUsed),
  };
}

export function mergeProjectionCompatibility(
  sources: Record<string, ProjectionCompatibility | undefined>,
): ProjectionCompatibility | undefined {
  const normalized = Object.fromEntries(
    Object.entries(sources).filter(([, value]) => Boolean(value)),
  ) as Record<string, ProjectionCompatibility>;
  if (!Object.keys(normalized).length) return undefined;
  const reasonCodes = Object.entries(normalized).flatMap(([name, value]) =>
    value.reasonCodes.map((code) => `${name}:${code}`),
  );
  const degraded = Object.values(normalized).some((value) => value.status === "degraded");
  const warning = Object.values(normalized).some((value) => value.status === "warning");
  return {
    status: degraded ? "degraded" : warning ? "warning" : "canonical",
    reasonCodes,
    sources: normalized,
  };
}

export function projectionCompatibilityAlert(
  compatibility: ProjectionCompatibility | undefined,
  tsMs: number,
): AlertItem | undefined {
  if (!compatibility || compatibility.status === "canonical") return undefined;
  const severity = compatibility.status === "degraded" ? "danger" : "warn";
  const detail = compatibility.reasonCodes.length
    ? compatibility.reasonCodes.join(" · ")
    : compatibility.status;
  return {
    id: `projection-compatibility-${tsMs}`,
    tsMs,
    severity,
    title: "Projection compatibility drift",
    detail,
  };
}
