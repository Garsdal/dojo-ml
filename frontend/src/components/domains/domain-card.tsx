import { useNavigate } from "react-router-dom";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { StateBadge } from "@/components/state-badge";
import type { Domain } from "@/types";

interface DomainCardProps {
  domain: Domain;
}

export function DomainCard({ domain }: DomainCardProps) {
  const navigate = useNavigate();

  return (
    <Card
      className="rounded-xl cursor-pointer hover:bg-secondary/30 transition-colors"
      onClick={() => navigate(`/domains/${domain.id}`)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{domain.name}</CardTitle>
          <StateBadge state={domain.status} />
        </div>
        {domain.description && (
          <CardDescription className="text-xs line-clamp-2">
            {domain.description}
          </CardDescription>
        )}
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>{domain.experiment_ids.length} experiments</span>
          <span>{domain.tools.length} tools</span>
          <span>{new Date(domain.created_at).toLocaleDateString()}</span>
        </div>
      </CardContent>
    </Card>
  );
}
