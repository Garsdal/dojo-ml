import { useMemo } from "react";
import type { KnowledgeAtom } from "@/types";

export interface KnowledgeEvolutionPoint {
  index: number;
  label: string;
  atomId: string;
  cumulative: number;
  isUpdate: boolean;
  confidence: number;
}

/**
 * Derives a knowledge evolution timeline from existing atom data.
 * Since there's no dedicated backend endpoint, we approximate from atoms' version numbers.
 * Atoms with version > 1 are treated as updates; version === 1 as new atoms.
 * We use the order they appear in the list as a proxy for time order.
 *
 * TODO: Replace with GET /domains/{id}/knowledge/evolution when backend endpoint is added.
 */
export function useKnowledgeEvolution(atoms: KnowledgeAtom[] | undefined): KnowledgeEvolutionPoint[] {
  return useMemo(() => {
    if (!atoms || atoms.length === 0) return [];

    let cumulative = 0;
    return atoms.map((atom, i) => {
      const isUpdate = atom.version > 1;
      if (!isUpdate) cumulative += 1;
      return {
        index: i + 1,
        label: `#${i + 1}`,
        atomId: atom.id,
        cumulative,
        isUpdate,
        confidence: atom.confidence,
      };
    });
  }, [atoms]);
}
