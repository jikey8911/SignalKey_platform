import React, { useEffect, useState } from 'react';
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';

const Analytics = () => {
    const [equityData, setEquityData] = useState<any[]>([]);
    const [stats, setStats] = useState({
        totalReturn: 0,
        maxDrawdown: 0,
        winRate: 0,
        totalTrades: 0
    });

    // Mock data for initial visualization (since backend endpoint might need updates)
    useEffect(() => {
        // Simulate fetching data
        const generateMockData = () => {
            const dataPoints = [];
            let balance = 10000;
            for (let i = 0; i < 30; i++) {
                const change = (Math.random() - 0.45) * 200; // Slight uptrend bias
                balance += change;
                dataPoints.push({
                    date: `Day ${i + 1}`,
                    equity: balance
                });
            }

            setEquityData(dataPoints);

            setStats({
                totalReturn: ((balance - 10000) / 10000) * 100,
                maxDrawdown: 5.2, // Mock calculated value
                winRate: 58.5,
                totalTrades: 42
            });
        };

        generateMockData();
        // In real impl: fetch from /api/analytics/equity
    }, []);

    return (
        <div className="p-6 bg-background min-h-screen text-foreground">
            <h1 className="text-3xl font-bold mb-6 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 tracking-tighter uppercase italic">
                Performance <span className="text-blue-500">Analytics</span>
            </h1>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div className="bg-slate-900/60 backdrop-blur-xl p-4 rounded-xl border border-white/5 shadow-lg">
                    <h3 className="text-slate-500 text-[10px] font-bold uppercase tracking-wider">Total Return</h3>
                    <p className={`text-2xl font-black ${stats.totalReturn >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {stats.totalReturn.toFixed(2)}%
                    </p>
                </div>
                <div className="bg-slate-900/60 backdrop-blur-xl p-4 rounded-xl border border-white/5 shadow-lg">
                    <h3 className="text-slate-500 text-[10px] font-bold uppercase tracking-wider">Max Drawdown</h3>
                    <p className="text-2xl font-black text-rose-400">
                        -{stats.maxDrawdown}%
                    </p>
                </div>
                <div className="bg-slate-900/60 backdrop-blur-xl p-4 rounded-xl border border-white/5 shadow-lg">
                    <h3 className="text-slate-500 text-[10px] font-bold uppercase tracking-wider">Win Rate</h3>
                    <p className="text-2xl font-black text-blue-400">
                        {stats.winRate}%
                    </p>
                </div>
                <div className="bg-slate-900/60 backdrop-blur-xl p-4 rounded-xl border border-white/5 shadow-lg">
                    <h3 className="text-slate-500 text-[10px] font-bold uppercase tracking-wider">Total Trades</h3>
                    <p className="text-2xl font-black text-white">
                        {stats.totalTrades}
                    </p>
                </div>
            </div>

            <div className="bg-slate-900/60 backdrop-blur-xl p-6 rounded-xl border border-white/5 shadow-lg h-[500px]">
                <h3 className="text-xl font-semibold mb-4 text-gray-200">Account Growth (Equity)</h3>
                {equityData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart
                            data={equityData}
                            margin={{
                                top: 5,
                                right: 30,
                                left: 20,
                                bottom: 5,
                            }}
                        >
                            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                            <XAxis dataKey="date" stroke="#9ca3af" />
                            <YAxis stroke="#9ca3af" />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#1f2937', borderColor: '#374151', color: '#f3f4f6' }}
                                itemStyle={{ color: '#f3f4f6' }}
                            />
                            <Legend />
                            <Line
                                type="monotone"
                                dataKey="equity"
                                stroke="#10b981"
                                activeDot={{ r: 8 }}
                                strokeWidth={2}
                                dot={false}
                                name="Equity Value ($)"
                            />
                        </LineChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="flex h-full items-center justify-center">
                        <p className="text-gray-400">Loading chart data...</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Analytics;
