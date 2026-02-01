import React, { useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
} from 'chart.js';

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend
);

const Analytics = () => {
    const [equityData, setEquityData] = useState<any>(null);
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
            const labels = Array.from({ length: 30 }, (_, i) => `Day ${i + 1}`);
            const dataPoints = [];
            let balance = 10000;
            for (let i = 0; i < 30; i++) {
                const change = (Math.random() - 0.45) * 200; // Slight uptrend bias
                balance += change;
                dataPoints.push(balance);
            }

            setEquityData({
                labels,
                datasets: [
                    {
                        label: 'Equity Curve (Real + Sim)',
                        data: dataPoints,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.5)',
                        tension: 0.3
                    }
                ]
            });

            setStats({
                totalReturn: ((balance - 10000) / 10000) * 100,
                maxDrawdown: 5.2, // Mock
                winRate: 58.5,
                totalTrades: 42
            });
        };

        generateMockData();
        // In real impl: fetch from /api/analytics/equity
    }, []);

    const options = {
        responsive: true,
        plugins: {
            legend: {
                position: 'top' as const,
                labels: { color: '#e5e7eb' }
            },
            title: {
                display: true,
                text: 'Account Growth (Equity)',
                color: '#e5e7eb',
                font: { size: 16 }
            },
        },
        scales: {
            x: {
                grid: { color: 'rgba(255, 255, 255, 0.1)' },
                ticks: { color: '#9ca3af' }
            },
            y: {
                grid: { color: 'rgba(255, 255, 255, 0.1)' },
                ticks: { color: '#9ca3af' }
            }
        }
    };

    return (
        <div className="p-6 bg-slate-900 min-h-screen text-white">
            <h1 className="text-3xl font-bold mb-6 text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                Performance Analytics
            </h1>

            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
                <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-lg">
                    <h3 className="text-gray-400 text-sm">Total Return</h3>
                    <p className={`text-2xl font-bold ${stats.totalReturn >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {stats.totalReturn.toFixed(2)}%
                    </p>
                </div>
                <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-lg">
                    <h3 className="text-gray-400 text-sm">Max Drawdown</h3>
                    <p className="text-2xl font-bold text-rose-400">
                        -{stats.maxDrawdown}%
                    </p>
                </div>
                <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-lg">
                    <h3 className="text-gray-400 text-sm">Win Rate</h3>
                    <p className="text-2xl font-bold text-blue-400">
                        {stats.winRate}%
                    </p>
                </div>
                <div className="bg-slate-800 p-4 rounded-xl border border-slate-700 shadow-lg">
                    <h3 className="text-gray-400 text-sm">Total Trades</h3>
                    <p className="text-2xl font-bold text-gray-200">
                        {stats.totalTrades}
                    </p>
                </div>
            </div>

            <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 shadow-lg h-[500px]">
                {equityData ? <Line options={options} data={equityData} /> : <p>Loading chart...</p>}
            </div>
        </div>
    );
};

export default Analytics;
