import { useMemo } from 'react';
import { useCommandCenter } from '../commandCenter/useCommandCenter';
import { chooseFocusedFamily, sortFamiliesForOperator } from '../state/launchStore';

export function useLaunchReadiness() {
  const cc = useCommandCenter();
  return useMemo(() => {
    const launch = cc.snapshot?.launch;
    return {
      mode: launch?.currentLaunchMode ?? 'V1_ONLY',
      nextFamily: launch?.nextRecommendedFamily ?? '',
      activeFamilies: launch?.activeFamilies ?? [],
      blockedFamilies: launch?.blockedFamilies ?? {},
      families: sortFamiliesForOperator(launch?.families ?? []),
      recommendation: launch?.recommendation,
      rollbackRecommendation: launch?.rollbackRecommendation ?? '',
      focusedFamily: chooseFocusedFamily(launch),
    };
  }, [cc.snapshot]);
}
