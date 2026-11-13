import { handleWorkspaceTraversal } from "./app/workspace/workspace-history-events";

// Register before hydration: Next.js must not clear editors before a traversal is approved.
window.addEventListener("popstate", handleWorkspaceTraversal, true);
