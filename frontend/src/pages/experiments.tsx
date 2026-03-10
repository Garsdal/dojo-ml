import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ExperimentList } from "@/components/experiments/experiment-list";
import { ExperimentDetail } from "@/components/experiments/experiment-detail";
import type { Experiment } from "@/types";

export default function ExperimentsPage() {
  const [selectedExperiment, setSelectedExperiment] =
    useState<Experiment | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Experiments</h1>
        <p className="text-muted-foreground text-sm mt-1">
          View and inspect experiment results
        </p>
      </div>

      <div className="grid gap-6 grid-cols-1 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card className="rounded-xl">
            <CardHeader>
              <CardTitle className="text-sm font-medium text-muted-foreground">
                All Experiments
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ExperimentList
                onSelect={setSelectedExperiment}
                selectedId={selectedExperiment?.id}
              />
            </CardContent>
          </Card>
        </div>
        <div>
          {selectedExperiment ? (
            <ExperimentDetail experiment={selectedExperiment} />
          ) : (
            <Card className="rounded-xl">
              <CardContent className="py-8">
                <p className="text-sm text-muted-foreground text-center">
                  Select an experiment to view details
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
