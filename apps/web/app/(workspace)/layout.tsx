import { Suspense } from "react";
import WorkspaceShell from "../components/workspace-shell";

// The shell stays mounted across workspace routes (sidebar, loaded records,
// analysis polling); it reads the active view from the URL.
export default function WorkspaceLayout() {
  return (
    <Suspense fallback={null}>
      <WorkspaceShell />
    </Suspense>
  );
}
