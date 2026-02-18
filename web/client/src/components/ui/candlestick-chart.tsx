import React, { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';

interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface Signal {
  createdAt: string | number;
  price?: number;
  decision: 'BUY' | 'SELL' | 'HOLD';
  type?: string; // For compatibility with socket signals
  side?: string; // For compatibility
  label?: string;
}

interface CandlestickChartProps {
  candles: Candle[];
  signals?: Signal[];
  height?: number;
  width?: number;
}

export const CandlestickChart = ({ candles, signals = [], height = 300, width = 800 }: CandlestickChartProps) => {
  const [zoom, setZoom] = useState(1);
  const [panIndex, setPanIndex] = useState(0);
  const [selectedSignal, setSelectedSignal] = useState<Signal | null>(null);

  // Reset zoom/pan when candles change
  useEffect(() => {
    setZoom(1);
    setPanIndex(0);
  }, [candles]);

  const visibleCount = Math.floor(candles.length / zoom);
  const safePanIndex = Math.max(0, Math.min(panIndex, candles.length - visibleCount));
  const visibleCandles = candles.slice(safePanIndex, safePanIndex + visibleCount);

  if (visibleCandles.length === 0) return <div className="h-64 flex items-center justify-center text-slate-500">No data to display</div>;

  const minPrice = Math.min(...visibleCandles.map(c => c.low)) * 0.995;
  const maxPrice = Math.max(...visibleCandles.map(c => c.high)) * 1.005;
  const priceRange = maxPrice - minPrice || 1;

  const padding = 40;
  const chartHeight = height;
  const chartWidth = 1000; // Reference width for viewBox

  const priceToY = (price: number) => {
    return chartHeight - ((price - minPrice) / priceRange) * (chartHeight - padding * 2) - padding;
  };

  const indexToX = (i: number) => {
    return (i / visibleCandles.length) * (chartWidth - padding * 2) + padding;
  };

  const candleWidth = chartWidth / visibleCandles.length;

  return (
    <div className="relative border border-white/5 rounded-lg bg-slate-950/50 overflow-hidden">
      {/* Controls Overlay */}
      <div className="absolute top-2 right-2 flex gap-2 z-10">
        <Button variant="secondary" size="sm" className="h-7 w-7 p-0 bg-slate-800/80" onClick={() => setZoom(z => Math.max(1, z - 1))}>-</Button>
        <span className="bg-slate-900/80 px-2 py-1 rounded text-[10px] flex items-center font-mono">x{zoom}</span>
        <Button variant="secondary" size="sm" className="h-7 w-7 p-0 bg-slate-800/80" onClick={() => setZoom(z => Math.min(20, z + 1))}>+</Button>
      </div>

      {/* Pan Slider */}
      {zoom > 1 && (
        <div className="absolute bottom-2 left-10 right-10 z-10">
          <input
            type="range"
            min={0}
            max={candles.length - visibleCount}
            value={safePanIndex}
            onChange={(e) => setPanIndex(parseInt(e.target.value))}
            className="w-full opacity-50 hover:opacity-100 transition-opacity accent-blue-500"
          />
        </div>
      )}

      <svg width="100%" height={height} viewBox={`0 0 ${chartWidth} ${chartHeight}`} className="w-full">
        {/* Grid Lines & Price Labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = chartHeight - (ratio * (chartHeight - padding * 2)) - padding;
          const price = minPrice + ratio * priceRange;
          return (
            <g key={`grid-${ratio}`}>
              <line x1={padding} y1={y} x2={chartWidth - padding} y2={y} stroke="white" strokeOpacity="0.05" strokeDasharray="5,5" />
              <text x={5} y={y + 4} fontSize="10" fill="#64748b" className="font-mono">
                ${price.toFixed(price < 1 ? 4 : 2)}
              </text>
            </g>
          );
        })}

        {/* Candles */}
        {visibleCandles.map((candle, i) => {
          const x = indexToX(i) + candleWidth / 2;
          const openY = priceToY(candle.open);
          const closeY = priceToY(candle.close);
          const highY = priceToY(candle.high);
          const lowY = priceToY(candle.low);
          const isGreen = candle.close >= candle.open;
          const color = isGreen ? '#10b981' : '#ef4444';

          return (
            <g key={`candle-${i}`}>
              <line x1={x} y1={highY} x2={x} y2={lowY} stroke={color} strokeWidth="1" />
              <rect
                x={x - (candleWidth * 0.35)}
                y={Math.min(openY, closeY)}
                width={candleWidth * 0.7}
                height={Math.max(1, Math.abs(closeY - openY))}
                fill={color}
                fillOpacity="0.6"
                stroke={color}
                strokeWidth="1"
              />
            </g>
          );
        })}

        {/* Signals */}
        {signals.map((sig, idx) => {
          const sigTime = typeof sig.createdAt === 'string' ? new Date(sig.createdAt).getTime() : (sig.createdAt > 2000000000 ? sig.createdAt : sig.createdAt * 1000);

          // Find the nearest candle for this signal
          // Signals might not align perfectly with candle timestamps
          const candleIndex = candles.findIndex(c => {
              const cTime = c.time * 1000;
              return Math.abs(cTime - sigTime) < 3600000; // Within 1 hour
          });

          if (candleIndex === -1) return null;
          if (candleIndex < safePanIndex || candleIndex >= safePanIndex + visibleCount) return null;

          const visibleIndex = candleIndex - safePanIndex;
          const x = indexToX(visibleIndex) + candleWidth / 2;

          const decision = sig.decision || sig.type || sig.side || 'HOLD';
          const label = sig.label || '';

          const isBuy = decision.toString().toUpperCase().includes('BUY') ||
                        decision.toString().toUpperCase().includes('LONG') ||
                        label.toUpperCase().includes('BUY') ||
                        label.toUpperCase().includes('LONG');

          const isSell = decision.toString().toUpperCase().includes('SELL') ||
                         decision.toString().toUpperCase().includes('SHORT') ||
                         label.toUpperCase().includes('SELL') ||
                         label.toUpperCase().includes('SHORT');

          const isDca = label.toUpperCase().includes('DCA');

          if (!isBuy && !isSell && !isDca) return null;

          const price = sig.price || candles[candleIndex].close;
          const y = priceToY(price);

          let markerColor = isBuy ? '#3b82f6' : '#f59e0b';
          if (isDca) markerColor = '#10b981'; // Green for DCA as it's adding to position

          return (
            <g
              key={`sig-${idx}`}
              className="cursor-pointer"
              onClick={() => setSelectedSignal(sig)}
            >
              <circle
                cx={x}
                cy={y}
                r={candleWidth * 0.6 > 8 ? 8 : candleWidth * 0.6}
                fill={markerColor}
                stroke="white"
                strokeWidth={isDca ? 2 : 1}
              />
              <text x={x} y={isBuy ? y + 15 : y - 10} fontSize="10" textAnchor="middle" fill={markerColor} fontWeight="bold" className="font-mono">
                {isDca ? '◆' : (isBuy ? '▲' : '▼')}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Tooltip for selected signal */}
      {selectedSignal && (
        <div className="absolute bottom-12 left-4 p-2 bg-slate-900 border border-white/10 rounded text-[10px] text-white z-20 shadow-xl">
           <div className="font-bold border-b border-white/5 pb-1 mb-1">SIGNAL DETAILS</div>
           <div>Type: {selectedSignal.decision || selectedSignal.type || selectedSignal.side}</div>
           <div>Price: ${selectedSignal.price?.toFixed(2)}</div>
           <div>Time: {new Date(selectedSignal.createdAt).toLocaleString('es-CO', { timeZone: 'America/Bogota' })}</div>
           <button className="mt-1 text-blue-400 hover:text-blue-300" onClick={() => setSelectedSignal(null)}>Close</button>
        </div>
      )}
    </div>
  );
};
