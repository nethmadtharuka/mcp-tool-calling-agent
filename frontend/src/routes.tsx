import type { RouteObject } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ExecutionIndexPage, ExecutionPage } from "./pages/ExecutionPage";
import { HistoryPage } from "./pages/HistoryPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { ProvidersPage } from "./pages/ProvidersPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ToolsPage } from "./pages/ToolsPage";
import { WorkspacePage } from "./pages/WorkspacePage";

export const routes: RouteObject[] = [
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <WorkspacePage /> },
      { path: "execution", element: <ExecutionIndexPage /> },
      { path: "execution/:runId", element: <ExecutionPage /> },
      { path: "history", element: <HistoryPage /> },
      { path: "tools", element: <ToolsPage /> },
      { path: "providers", element: <ProvidersPage /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
];
