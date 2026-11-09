// Match manual navigation without undoing an in-progress Next/Back transition.
export function tutorialStepForRoute(steps, index, route, pendingRoute = null) {
  if (index === null || !steps[index]) return null;
  if (pendingRoute && route !== pendingRoute) return index;
  const matches = step => step.route === route || step.routes?.includes(route);
  if (matches(steps[index])) return index;
  const matchingIndex = steps.findIndex(matches);
  return matchingIndex < 0 ? index : matchingIndex;
}
