export const CHART_COLORS = {
  historical: "rgba(54, 162, 235, 1)", // Solid blue
  forecast: "rgba(75, 192, 192, 1)",   // Teal
  confidenceBand: "rgba(75, 192, 192, 0.2)", // Translucent shading
  anomaly: "rgba(255, 99, 132, 1)", // Red
};

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value);
}
