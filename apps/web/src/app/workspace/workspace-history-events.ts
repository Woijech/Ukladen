type TraversalHandler = (event: PopStateEvent) => void;

let handler: TraversalHandler | undefined;

export function handleWorkspaceTraversal(event: PopStateEvent) {
  handler?.(event);
}

export function subscribeWorkspaceTraversal(next: TraversalHandler) {
  handler = next;
  return () => { if (handler === next) handler = undefined; };
}
