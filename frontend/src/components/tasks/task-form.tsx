import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { createTask } from "@/hooks/use-tasks";
import { useSWRConfig } from "swr";

export function TaskForm() {
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mutate } = useSWRConfig();

  async function handleSubmit() {
    if (!prompt.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createTask(prompt);
      setPrompt("");
      mutate("/tasks");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create task");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="rounded-xl">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          New Task
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Textarea
          placeholder="Describe your ML experiment task..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="min-h-[100px] rounded-lg bg-muted/50 border-border"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <Button
          onClick={handleSubmit}
          disabled={!prompt.trim() || loading}
          className="rounded-lg"
        >
          {loading ? "Running..." : "Run Task"}
        </Button>
      </CardContent>
    </Card>
  );
}
