import { LineChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid, BarChart, Bar, Cell } from "recharts";
import { colorForScore } from "@/lib/risk";

export const ScoreSparkline = ({ data, height = 80 }: { data: { date: string; score: number }[]; height?: number }) => (
  <ResponsiveContainer width="100%" height={height}>
    <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
      <Line type="monotone" dataKey="score" stroke="hsl(var(--primary))" strokeWidth={2} dot={false} />
      <Tooltip
        contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
        labelStyle={{ color: "hsl(var(--muted-foreground))" }}
        formatter={(v: number) => [`${v}`, "Risk score"]}
      />
    </LineChart>
  </ResponsiveContainer>
);

export const TrendChart = ({
  data, height = 220, dataKey = "score", label = "Risk score",
}: { data: any[]; height?: number; dataKey?: string; label?: string }) => (
  <ResponsiveContainer width="100%" height={height}>
    <LineChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
      <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
      <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} domain={[0, 100]} />
      <Tooltip
        contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
        formatter={(v: number) => [v, label]}
      />
      <Line type="monotone" dataKey={dataKey} stroke="hsl(var(--primary))" strokeWidth={2.5} dot={false} />
    </LineChart>
  </ResponsiveContainer>
);

export const ScoreBarChart = ({
  data, height = 260,
}: { data: { name: string; score: number }[]; height?: number }) => (
  <ResponsiveContainer width="100%" height={height}>
    <BarChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 24 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
      <XAxis dataKey="name" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} interval={0} angle={-30} textAnchor="end" height={50} />
      <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} domain={[0, 100]} />
      <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }} />
      <Bar dataKey="score" radius={[6, 6, 0, 0]}>
        {data.map((d, i) => (
          <Cell key={i} fill={colorForScore(d.score)} />
        ))}
      </Bar>
    </BarChart>
  </ResponsiveContainer>
);
