import {
  BarChart,
  Bar,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts'
import { demoValuation } from '@/data/mockStocks'

export default function ScenarioChart() {
  return (
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <BarChart
        data={demoValuation.scenarios}
        margin={{ top: 15, right: 10, bottom: 0, left: -17 }}
        accessibilityLayer={false}
      >
        <XAxis
          dataKey="name"
          axisLine={false}
          tickLine={false}
          tick={{
            fontSize: 'var(--font-size-label)',
            fontWeight: 'var(--font-weight-label)',
            fill: 'var(--subtle-foreground)',
          }}
        />
        <YAxis
          domain={[0, 650]}
          ticks={[0, 200, 400, 600]}
          axisLine={false}
          tickLine={false}
          tick={{
            fontSize: 'var(--font-size-label)',
            fontWeight: 'var(--font-weight-label)',
            fill: 'var(--subtle-foreground)',
          }}
          tickFormatter={(value) => `$${value}`}
        />
        <ReferenceLine
          y={demoValuation.marketPrice}
          stroke="#a3a3a3"
          strokeDasharray="4 4"
        />
        <Bar
          dataKey="value"
          barSize={38}
          radius={[3, 3, 0, 0]}
          isAnimationActive={false}
        >
          {demoValuation.scenarios.map((scenario) => (
            <Cell key={scenario.name} fill={scenario.color} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
