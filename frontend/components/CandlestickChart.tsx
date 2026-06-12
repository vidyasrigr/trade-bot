"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  HistogramData,
  ColorType,
  CrosshairMode,
} from "lightweight-charts";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface ChartProps {
  symbol: string;
}

export function CandlestickChart({ symbol }: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [ema, setEma] = useState({ e8: true, e21: true, e50: true, e200: false });
  const emaSeriesRefs = useRef<Record<string, ISeriesApi<"Line">>>({});

  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0f172a" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1e293b" },
        horzLines: { color: "#1e293b" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#1e293b" },
      timeScale: { borderColor: "#1e293b", timeVisible: true },
      width: containerRef.current.clientWidth,
      height: 420,
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderUpColor: "#22c55e",
      borderDownColor: "#ef4444",
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Fetch OHLCV data
    fetchChartData(symbol, chart, candleSeries);

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [symbol]);

  const fetchChartData = async (
    sym: string,
    chart: IChartApi,
    candleSeries: ISeriesApi<"Candlestick">
  ) => {
    try {
      // Use yfinance via backend proxy or direct fetch
      const resp = await fetch(`${API}/market/ohlcv/${sym}?period=6mo`);
      if (!resp.ok) return;
      const data = await resp.json();

      const candles: CandlestickData[] = data.ohlcv.map((d: {
        date: string; open: number; high: number; low: number; close: number;
      }) => ({
        time: d.date,
        open: d.open,
        high: d.high,
        low: d.low,
        close: d.close,
      }));

      candleSeries.setData(candles);
      chart.timeScale().fitContent();
    } catch (e) {
      console.error("Chart data fetch failed:", e);
    }
  };

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* EMA toggles */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
        <span className="text-gray-400 text-xs font-medium mr-2">EMAs:</span>
        {[
          { key: "e8", label: "8", color: "#f59e0b" },
          { key: "e21", label: "21", color: "#3b82f6" },
          { key: "e50", label: "50", color: "#a855f7" },
          { key: "e200", label: "200", color: "#ec4899" },
        ].map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => setEma(prev => ({ ...prev, [key]: !prev[key as keyof typeof ema] }))}
            className={`px-2 py-0.5 rounded text-xs font-mono transition ${
              ema[key as keyof typeof ema]
                ? "opacity-100"
                : "opacity-30"
            }`}
            style={{ color, border: `1px solid ${color}` }}
          >
            EMA{label}
          </button>
        ))}
        <div className="ml-auto text-gray-400 text-xs font-bold">{symbol}</div>
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
