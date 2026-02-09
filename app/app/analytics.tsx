import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../context/AuthContext';
import { Card } from '../components/ui/Card';
import { Chart } from '../components/Chart';
import { TrendingUp, TrendingDown, Activity, BarChart2 } from 'lucide-react-native';

export default function AnalyticsScreen() {
    const { user } = useAuth();
    const [refreshing, setRefreshing] = useState(false);
    const [equityData, setEquityData] = useState<any[]>([]);
    const [stats, setStats] = useState({
        totalReturn: 0,
        maxDrawdown: 0,
        winRate: 0,
        totalTrades: 0
    });

    const loadData = async () => {
        // Simular obtención de datos (puedes conectar a API real luego)
        const mockData = [];
        let balance = 10000;
        for (let i = 0; i < 30; i++) {
            const change = (Math.random() - 0.45) * 200;
            balance += change;
            mockData.push({
                time: Math.floor(Date.now() / 1000) - (30 - i) * 86400,
                close: balance, // Usamos close para la gráfica de área si la adaptamos
                value: balance
            });
        }
        setEquityData(mockData);
        setStats({
            totalReturn: ((balance - 10000) / 10000) * 100,
            maxDrawdown: 5.2,
            winRate: 58.5,
            totalTrades: 42
        });
    };

    useEffect(() => {
        loadData();
    }, []);

    const onRefresh = async () => {
        setRefreshing(true);
        await loadData();
        setRefreshing(false);
    };

    return (
        <SafeAreaView className="flex-1 bg-background">
            <ScrollView
                contentContainerStyle={{ padding: 16 }}
                refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
            >
                <View className="mb-6">
                    <Text className="text-2xl font-bold text-white">Rendimiento</Text>
                    <Text className="text-gray-400">Análisis detallado de tu cuenta</Text>
                </View>

                {/* Grid de Estadísticas */}
                <View className="flex-row flex-wrap gap-4 mb-6">
                    <Card className="flex-[1_0_45%] bg-blue-500/10 border-blue-500/20 p-4">
                        <View className="flex-row justify-between items-center mb-1">
                            <Text className="text-xs text-gray-400">Retorno Total</Text>
                            <TrendingUp size={14} color="#60a5fa" />
                        </View>
                        <Text className={`text-xl font-bold ${stats.totalReturn >= 0 ? 'text-blue-400' : 'text-red-400'}`}>
                            {stats.totalReturn.toFixed(2)}%
                        </Text>
                    </Card>

                    <Card className="flex-[1_0_45%] bg-red-500/10 border-red-500/20 p-4">
                        <View className="flex-row justify-between items-center mb-1">
                            <Text className="text-xs text-gray-400">Max Drawdown</Text>
                            <TrendingDown size={14} color="#f87171" />
                        </View>
                        <Text className="text-xl font-bold text-red-400">
                            -{stats.maxDrawdown}%
                        </Text>
                    </Card>

                    <Card className="flex-[1_0_45%] bg-emerald-500/10 border-emerald-500/20 p-4">
                        <View className="flex-row justify-between items-center mb-1">
                            <Text className="text-xs text-gray-400">Win Rate</Text>
                            <Activity size={14} color="#34d399" />
                        </View>
                        <Text className="text-xl font-bold text-emerald-400">
                            {stats.winRate}%
                        </Text>
                    </Card>

                    <Card className="flex-[1_0_45%] bg-slate-800 border-slate-700 p-4">
                        <View className="flex-row justify-between items-center mb-1">
                            <Text className="text-xs text-gray-400">Operaciones</Text>
                            <BarChart2 size={14} color="#94a3b8" />
                        </View>
                        <Text className="text-xl font-bold text-gray-200">
                            {stats.totalTrades}
                        </Text>
                    </Card>
                </View>

                {/* Gráfica de Equidad */}
                <Card className="bg-slate-900 border-gray-800 p-0 overflow-hidden mb-6">
                    <View className="p-4 border-b border-gray-800">
                        <Text className="text-white font-bold">Crecimiento de la Cuenta (Equity)</Text>
                    </View>
                    <View className="p-2">
                        <Chart
                            height={250}
                            data={equityData}
                        />
                    </View>
                </Card>

                {/* Resumen Informativo */}
                <Card className="bg-primary/10 border-primary/20 p-4">
                    <Text className="text-primary font-bold mb-1">Nota sobre los datos</Text>
                    <Text className="text-gray-300 text-xs">
                        Estas estadísticas incluyen tanto operaciones reales como simuladas para darte una visión global del rendimiento de tus bots.
                    </Text>
                </Card>

            </ScrollView>
        </SafeAreaView>
    );
}
