import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, Time, CandlestickSeries } from 'lightweight-charts';

interface Candle {
    time: number; // Unix timestamp in seconds or milliseconds
    open: number;
    high: number;
    low: number;
    close: number;
}

interface Trade {
    time: number;
    price: number;
    side: 'BUY' | 'SELL';
    label?: string;
}

interface TradingViewChartProps {
    data: Candle[];
    trades?: Trade[];
    colors?: {
        backgroundColor?: string;
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
    };
    height?: number;
}

export const TradingViewChart: React.FC<TradingViewChartProps> = ({
    data,
    trades = [],
    colors = {},
    height = 400
}) => {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);
    const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

    const {
        backgroundColor = '#1e222d', // Default dark
        textColor = '#DDD',
        upColor = '#26a69a',
        downColor = '#ef5350',
    } = colors as any;

    // 1. Initialization Effect - Create Chart Once
    useEffect(() => {
        if (!chartContainerRef.current) return;

        // Cleanup previous instance if any (safety check)
        if (chartRef.current) {
            chartRef.current.remove();
        }

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: backgroundColor },
                textColor,
            },
            width: chartContainerRef.current.clientWidth,
            height: height,
            grid: {
                vertLines: { color: 'rgba(197, 203, 206, 0.1)' },
                horzLines: { color: 'rgba(197, 203, 206, 0.1)' },
            },
            timeScale: {
                timeVisible: true,
                secondsVisible: false,
            },
        });

        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: upColor,
            downColor: downColor,
            borderVisible: false,
            wickUpColor: upColor,
            wickDownColor: downColor,
        });

        seriesRef.current = candlestickSeries;
        chartRef.current = chart;

        // Resize observer
        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            if (chartRef.current) {
                chartRef.current.remove();
                chartRef.current = null;
                seriesRef.current = null;
            }
        };
    }, [height, backgroundColor, textColor]); // Only re-run if visual config changes

    // 2. Data Update Effect - Update Series
    useEffect(() => {
        if (!seriesRef.current || !data) return;

        // Fix data format (ensure time is typically in seconds for LW Charts unless specified)
        // Checks timestamps: if > 1e11 likely ms, so divide by 1000
        const formattedData = data.map(d => ({
            ...d,
            time: (d.time > 10000000000 ? d.time / 1000 : d.time) as Time
        })).sort((a, b) => (a.time as number) - (b.time as number));

        // Remove duplicates if any
        const uniqueData = formattedData.filter((v, i, a) =>
            i === a.findIndex(t => t.time === v.time)
        );

        seriesRef.current.setData(uniqueData);

        // Markers for trades
        if (trades && trades.length > 0) {
            const markers = trades.map(t => ({
                time: (t.time > 10000000000 ? t.time / 1000 : t.time) as Time,
                position: t.side === 'BUY' ? 'belowBar' : 'aboveBar',
                color: t.side === 'BUY' ? '#2196F3' : '#FF9800',
                shape: t.side === 'BUY' ? 'arrowUp' : 'arrowDown',
                text: t.side === 'BUY' ? (t.label || 'BUY') : (t.label || 'SELL'),
                size: 2, // Ensure visibility
            }));

            // Sort markers by time
            markers.sort((a, b) => (a.time as number) - (b.time as number));

            console.log("Setting Markers:", markers.length, "First:", markers[0]);

            if (typeof (seriesRef.current as any).setMarkers === 'function') {
                (seriesRef.current as any).setMarkers(markers);
            }
        } else {
            if (typeof (seriesRef.current as any).setMarkers === 'function') {
                (seriesRef.current as any).setMarkers([]);
            }
        }

        // Only fit content on initial data load or significant changes if desired
        // chartRef.current?.timeScale().fitContent(); 

    }, [data, trades]);

    return (
        <div
            ref={chartContainerRef}
            className="w-full relative overflow-hidden rounded-lg border border-white/10"
        />
    );
};
