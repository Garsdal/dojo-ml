import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { KnowledgeList } from "@/components/knowledge/knowledge-list";
import { KnowledgeSearch } from "@/components/knowledge/knowledge-search";
import type { KnowledgeAtom } from "@/types";

export default function KnowledgePage() {
  const [selectedAtom, setSelectedAtom] = useState<KnowledgeAtom | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Knowledge</h1>
        <p className="text-muted-foreground text-sm mt-1">
          Browse and search the knowledge base
        </p>
      </div>

      <Card className="rounded-xl">
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Search Knowledge
          </CardTitle>
        </CardHeader>
        <CardContent>
          <KnowledgeSearch
            onSelect={setSelectedAtom}
            selectedId={selectedAtom?.id}
          />
        </CardContent>
      </Card>

      <Separator />

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                All Knowledge Atoms
              </CardTitle>
            </CardHeader>
            <CardContent>
              <KnowledgeList
                onSelect={setSelectedAtom}
                selectedId={selectedAtom?.id}
              />
            </CardContent>
          </Card>
        </div>
        <div>
          {selectedAtom ? (
            <Card className="rounded-xl">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Atom Detail
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-xs text-muted-foreground mb-1">ID</p>
                  <p className="font-mono text-sm">{selectedAtom.id}</p>
                </div>
                <Separator />
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Context</p>
                  <p className="text-sm">{selectedAtom.context}</p>
                </div>
                <Separator />
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Claim</p>
                  <p className="text-sm">{selectedAtom.claim}</p>
                </div>
                <Separator />
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Action</p>
                  <p className="text-sm">{selectedAtom.action}</p>
                </div>
                <Separator />
                <div>
                  <p className="text-xs text-muted-foreground mb-1">
                    Confidence
                  </p>
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-foreground/60 rounded-full"
                        style={{
                          width: `${selectedAtom.confidence * 100}%`,
                        }}
                      />
                    </div>
                    <span className="font-mono text-sm">
                      {(selectedAtom.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
                {selectedAtom.evidence_ids.length > 0 && (
                  <>
                    <Separator />
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">
                        Evidence IDs
                      </p>
                      <div className="space-y-1">
                        {selectedAtom.evidence_ids.map((id) => (
                          <p key={id} className="font-mono text-xs">
                            {id}
                          </p>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card className="rounded-xl">
              <CardContent className="py-8">
                <p className="text-sm text-muted-foreground text-center">
                  Select an atom to view details
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
