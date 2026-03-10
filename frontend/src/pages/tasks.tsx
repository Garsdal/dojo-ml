import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TaskForm } from "@/components/tasks/task-form";
import { TaskList } from "@/components/tasks/task-list";
import { TaskDetail } from "@/components/tasks/task-detail";
import type { Task } from "@/types";

export default function TasksPage() {
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Tasks</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Create and manage ML experiment tasks
        </p>
      </div>

      <TaskForm />

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                All Tasks
              </CardTitle>
            </CardHeader>
            <CardContent>
              <TaskList
                onSelect={setSelectedTask}
                selectedId={selectedTask?.id}
              />
            </CardContent>
          </Card>
        </div>
        <div>
          {selectedTask ? (
            <TaskDetail task={selectedTask} />
          ) : (
            <Card className="rounded-xl">
              <CardContent className="py-8">
                <p className="text-sm text-muted-foreground text-center">
                  Select a task to view details
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
