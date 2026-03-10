import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ToolHint } from "@/types";
import { Plus, X } from "lucide-react";

interface AgentPromptFormProps {
  onSubmit: (prompt: string, toolHints: ToolHint[]) => void;
  isLoading?: boolean;
}

export function AgentPromptForm({ onSubmit, isLoading }: AgentPromptFormProps) {
  const [prompt, setPrompt] = useState("");
  const [toolHints, setToolHints] = useState<ToolHint[]>([]);
  const [showHintForm, setShowHintForm] = useState(false);
  const [hintName, setHintName] = useState("");
  const [hintDescription, setHintDescription] = useState("");
  const [hintSource, setHintSource] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    onSubmit(prompt.trim(), toolHints);
  };

  const addHint = () => {
    if (!hintName.trim() || !hintDescription.trim()) return;
    setToolHints((prev) => [
      ...prev,
      {
        name: hintName.trim(),
        description: hintDescription.trim(),
        source: hintSource.trim(),
      },
    ]);
    setHintName("");
    setHintDescription("");
    setHintSource("");
    setShowHintForm(false);
  };

  const removeHint = (index: number) => {
    setToolHints((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Textarea
        placeholder="Describe your ML research task... e.g. 'Improve accuracy of Boston housing prediction. Start with linear regression, then try advanced models. Target: R² > 0.85'"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        className="min-h-[100px] resize-none"
        disabled={isLoading}
      />

      {/* Tool hints */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">
            Tool Hints (optional)
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setShowHintForm(!showHintForm)}
            disabled={isLoading}
          >
            <Plus className="h-3 w-3 mr-1" />
            Add Hint
          </Button>
        </div>

        {toolHints.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {toolHints.map((hint, i) => (
              <div
                key={i}
                className="flex items-center gap-1 rounded-md bg-secondary px-2 py-1 text-xs"
              >
                <span className="font-medium">{hint.name}</span>
                <button
                  type="button"
                  onClick={() => removeHint(i)}
                  className="ml-1 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {showHintForm && (
          <Card className="rounded-lg">
            <CardHeader className="py-3 px-4">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                New Tool Hint
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3 space-y-2">
              <Input
                placeholder="Name (e.g. fetch_dataset)"
                value={hintName}
                onChange={(e) => setHintName(e.target.value)}
                className="text-sm"
              />
              <Input
                placeholder="Description"
                value={hintDescription}
                onChange={(e) => setHintDescription(e.target.value)}
                className="text-sm"
              />
              <Input
                placeholder="Source URL (optional)"
                value={hintSource}
                onChange={(e) => setHintSource(e.target.value)}
                className="text-sm"
              />
              <div className="flex gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={addHint}
                >
                  Add
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setShowHintForm(false)}
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      <Button type="submit" disabled={!prompt.trim() || isLoading}>
        {isLoading ? "Starting..." : "Start Research"}
      </Button>
    </form>
  );
}
