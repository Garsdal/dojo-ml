import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { KnowledgeEvolutionPoint } from "@/hooks/use-knowledge-evolution";

interface TooltipPayloadEntry {
  value: number;
  payload: KnowledgeEvolutionPoint;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="bg-white border border-soft-fawn/30 rounded-xl px-3 py-2 shadow-sm text-xs space-y-0.5">
      <div className="font-semibold text-blackberry">{point.cumulative} atoms</div>
      <div className="text-grey">{point.isUpdate ? "Update" : "New atom"}</div>
      <div className="text-grey">Confidence: {Math.round(point.confidence * 100)}%</div>
    </div>
  );
}

interface KnowledgeEvolutionChartProps {
  data: KnowledgeEvolutionPoint[];
}

export function KnowledgeEvolutionChart({ data }: KnowledgeEvolutionChartProps) {
  if (data.length === 0) {
    return (
      <p className="text-sm text-grey">
        No knowledge yet. Knowledge accumulates as the agent runs experiments.
      </p>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-soft-fawn/20 p-4">
      <h3 className="font-heading font-semibold text-blackberry text-sm mb-4">
        Knowledge Accumulation
      </h3>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
          <defs>
            <linearGradient id="knowledgeGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8BBF9F" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#8BBF9F" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(214,186,115,0.15)" />
          <XAxis
            dataKey="index"
            tick={{ fontSize: 10, fill: "#857E7B" }}
            tickLine={false}
            axisLine={{ stroke: "rgba(214,186,115,0.2)" }}
          />
          <YAxis
            tick={{ fontSize: 10, fill: "#857E7B" }}
            tickLine={false}
            axisLine={false}
            allowDecimals={false}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="cumulative"
            stroke="#8BBF9F"
            strokeWidth={2}
            fill="url(#knowledgeGradient)"
            dot={{ r: 3, fill: "#8BBF9F", strokeWidth: 0 }}
            activeDot={{ r: 5, fill: "#59344F", strokeWidth: 0 }}
          />
        </AreaChart>
      </ResponsiveContainer>
      <p className="text-xs text-grey text-center mt-1">Cumulative new knowledge atoms</p>
    </div>
  );
}
