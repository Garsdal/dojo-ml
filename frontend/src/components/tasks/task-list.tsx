import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { StateBadge } from "@/components/state-badge";
import { useTasks } from "@/hooks/use-tasks";
import type { Task } from "@/types";

interface TaskListProps {
  onSelect: (task: Task) => void;
  selectedId?: string;
}

export function TaskList({ onSelect, selectedId }: TaskListProps) {
  const { data: tasks, error, isLoading } = useTasks();

  if (isLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <p className="text-sm text-red-400">
        Failed to load tasks: {error.message}
      </p>
    );
  }

  if (!tasks || tasks.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-8 text-center">
        No tasks yet. Create one above.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[120px]">ID</TableHead>
          <TableHead>Prompt</TableHead>
          <TableHead className="w-[100px]">Status</TableHead>
          <TableHead className="w-[100px]">Experiments</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {tasks.map((task) => (
          <TableRow
            key={task.id}
            onClick={() => onSelect(task)}
            className={`cursor-pointer ${
              selectedId === task.id ? "bg-muted" : ""
            }`}
          >
            <TableCell className="font-mono text-xs">
              {task.id.slice(0, 8)}&hellip;
            </TableCell>
            <TableCell className="max-w-[300px] truncate">
              {task.prompt}
            </TableCell>
            <TableCell>
              <StateBadge state={task.status} />
            </TableCell>
            <TableCell className="text-xs font-mono">
              {task.experiments.length}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
