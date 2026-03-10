import { Routes, Route } from "react-router-dom";
import { Shell } from "@/components/layout/shell";
import DashboardPage from "@/pages/dashboard";
import TasksPage from "@/pages/tasks";
import ExperimentsPage from "@/pages/experiments";
import KnowledgePage from "@/pages/knowledge";
import AgentPage from "@/pages/agent";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="experiments" element={<ExperimentsPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="agent" element={<AgentPage />} />
      </Route>
    </Routes>
  );
}
