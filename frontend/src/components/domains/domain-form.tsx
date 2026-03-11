import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { Domain } from "@/types";

interface DomainFormProps {
  onSubmit: (data: {
    name: string;
    description: string;
    prompt: string;
  }) => Promise<Domain | void>;
  isLoading?: boolean;
}

export function DomainForm({ onSubmit, isLoading }: DomainFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    await onSubmit({ name: name.trim(), description, prompt });
    setName("");
    setDescription("");
    setPrompt("");
  };

  return (
    <Card className="rounded-xl">
      <CardHeader>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          Create Research Domain
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Input
              placeholder="Domain name (e.g. Sentiment Analysis)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-secondary/50"
            />
          </div>
          <div>
            <Input
              placeholder="Brief description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="bg-secondary/50"
            />
          </div>
          <div>
            <Textarea
              placeholder="Steering prompt for the AI agent (optional)"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="bg-secondary/50 min-h-[80px] resize-none"
            />
          </div>
          <Button type="submit" disabled={!name.trim() || isLoading}>
            {isLoading ? "Creating…" : "Create Domain"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
