import { useState } from "react";
import {
  BarChart,
  Bar,
  Cell,
  CartesianGrid,
  LabelList,
  XAxis,
  YAxis,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  marketPriceDistance,
  marketDistanceColor,
} from "@/lib/valuationChartColors";
import { dollars, percent } from "@/lib/financialFormatting";

function ComparisonBarLabel({ viewBox, value, index, models, compact }) {
  const { x, y, width, height } = viewBox ?? {};
  if (![x, y, width, height].every(Number.isFinite)) return null;
  const model = models[index];
  const formatted = dollars(value);
  return (
    <g pointerEvents="none">
      {compact && (
        <>
          <rect
            x={x}
            y={y - 27}
            width={model.name.length * 8}
            height={20}
            fill="#fff"
          />
          <text x={x} y={y - 10} fill="#333333" fontSize={13} fontWeight={500}>
            {model.name}
          </text>
        </>
      )}
      <rect
        x={x + width + 6}
        y={y + height / 2 - 11}
        width={formatted.length * 8 + 4}
        height={22}
        fill="#fff"
      />
      <text
        className="comparison-value-label"
        x={x + width + 10}
        y={y + height / 2}
        dominantBaseline="middle"
        fill="#333333"
        fontSize={13}
        fontWeight={500}
      >
        {formatted}
      </text>
    </g>
  );
}

function ComparisonTooltip({ active, payload }) {
  const model = payload?.[0]?.payload;
  if (!active || !model) return null;
  return (
    <div className="research-comparison-tooltip">
      <strong>{model.fullName}</strong>
      <p>
        Estimated fair value <span>{dollars(model.value)}</span>
      </p>
      <p>
        Absolute difference <span>{percent(model.distance)}</span>
      </p>
      <small>
        {model.enabled
          ? "Enabled model"
          : "Excluded from the weighted estimate"}
      </small>
    </div>
  );
}

export default function ComparisonChart({
  results,
  enabled,
  fairValue,
  marketPrice,
}) {
  const [chartWidth, setChartWidth] = useState(0);
  const compact = chartWidth < 520;
  const data = results
    .filter((result) => result.status === "valid")
    .map((result) => ({
      id: result.id,
      name: result.shortName,
      fullName: result.name,
      value: result.fairValue,
      distance: marketPriceDistance(result.fairValue, marketPrice),
      enabled: enabled[result.id],
    }));
  const chartHeight = Math.max(200, data.length * (compact ? 70 : 52) + 48);
  const valuePadding = Math.max(
    92,
    ...data.map((model) => dollars(model.value).length * 8 + 24),
  );
  if (!data.length)
    return (
      <p className="research-empty-chart">
        No available model estimates to compare.
      </p>
    );
  return (
    <ResponsiveContainer
      width="100%"
      height={chartHeight}
      minWidth={0}
      onResize={(width) => setChartWidth(width)}
    >
      <BarChart
        data={data}
        layout="vertical"
        margin={{
          top: compact ? 24 : 8,
          right: valuePadding,
          left: 8,
          bottom: 8,
        }}
        accessibilityLayer
      >
        <CartesianGrid
          horizontal={false}
          stroke="#e5e7eb"
          strokeDasharray="3 4"
        />
        <XAxis
          type="number"
          domain={[
            0,
            (dataMax) =>
              Math.max(
                dataMax,
                Number.isFinite(marketPrice) ? marketPrice : 0,
                fairValue ?? 0,
              ) * 1.12,
          ]}
          tickFormatter={(value) => `$${Math.round(value)}`}
          tickCount={compact ? 3 : 6}
          minTickGap={20}
          tick={{
            fill: "var(--subtle-foreground)",
            fontSize: 12,
            fontWeight: 500,
          }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          hide={compact}
          width={compact ? 0 : 150}
          tickMargin={12}
          interval={0}
          tick={{
            fill: "#333333",
            fontSize: 14,
            fontWeight: 500,
          }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<ComparisonTooltip />} cursor={{ fill: "#fafafa" }} />
        {Number.isFinite(marketPrice) && marketPrice > 0 && (
          <ReferenceLine
            x={marketPrice}
            stroke="#444444"
            strokeDasharray="5 4"
            strokeWidth={2}
          />
        )}
        {Number.isFinite(fairValue) && (
          <ReferenceLine x={fairValue} stroke="#2563eb" strokeWidth={2} />
        )}
        <Bar
          dataKey="value"
          barSize={28}
          radius={[5, 5, 5, 5]}
          isAnimationActive={false}
        >
          {data.map((item) => (
            <Cell key={item.id} fill={marketDistanceColor(item.distance)} />
          ))}
          <LabelList
            dataKey="value"
            content={<ComparisonBarLabel models={data} compact={compact} />}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
