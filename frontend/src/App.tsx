import { Routes, Route } from "react-router-dom";
import { Shell } from "@/components/layout/shell";
import DomainOverviewPage from "@/pages/domain-overview";
import DomainDetailPage from "@/pages/domain-detail";
import KnowledgeOverviewPage from "@/pages/knowledge-overview";

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<DomainOverviewPage />} />
        <Route path="domains/:id" element={<DomainDetailPage />} />
        <Route path="knowledge" element={<KnowledgeOverviewPage />} />
      </Route>
    </Routes>
  );
}
