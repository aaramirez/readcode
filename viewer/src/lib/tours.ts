// Tour player navigation (steps are 1-based, as in the route tour/<id>/<step>).

/** The step to show for a requested step: 1 by default, clamped to 1..total (0 if empty). */
export function clampStep(total: number, step: number | undefined): number {
  if (total <= 0) return 0;
  if (step === undefined) return 1;
  return Math.min(Math.max(1, step), total);
}

/** Previous and next step numbers around `step` (null at the bounds). */
export function stepNav(total: number, step: number): { prev: number | null; next: number | null } {
  const cur = clampStep(total, step);
  if (cur === 0) return { prev: null, next: null };
  return { prev: cur > 1 ? cur - 1 : null, next: cur < total ? cur + 1 : null };
}
