import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useKnowledgeSearch } from "@/hooks/use-knowledge";
import { KnowledgeList } from "./knowledge-list";
import { Search } from "lucide-react";
import type { KnowledgeAtom } from "@/types";

interface KnowledgeSearchProps {
  onSelect: (atom: KnowledgeAtom) => void;
  selectedId?: string;
}

export function KnowledgeSearch({
  onSelect,
  selectedId,
}: KnowledgeSearchProps) {
  const [inputValue, setInputValue] = useState("");
  const [query, setQuery] = useState("");
  const { data: results, isLoading } = useKnowledgeSearch(query);

  function handleSearch() {
    setQuery(inputValue);
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Input
          placeholder="Search knowledge base..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()}
          className="rounded-lg"
        />
        <Button
          onClick={handleSearch}
          disabled={!inputValue.trim()}
          variant="secondary"
          className="rounded-lg"
        >
          <Search className="h-4 w-4 mr-2" />
          Search
        </Button>
      </div>
      {isLoading && (
        <p className="text-sm text-muted-foreground">Searching...</p>
      )}
      {query && results && (
        <div>
          <p className="text-xs text-muted-foreground mb-2">
            {results.length} result{results.length !== 1 ? "s" : ""} for &ldquo;
            {query}&rdquo;
          </p>
          <KnowledgeList
            atoms={results}
            onSelect={onSelect}
            selectedId={selectedId}
          />
        </div>
      )}
    </div>
  );
}
