import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { fetchConfig, fetchSignals, fetchBots } from '../../lib/api';
import { Chart } from '../../components/Chart';
import { useRouter } from 'expo-router';

import { TouchableOpacity } from 'react-native';
import { Activity, Zap, TrendingUp, BarChart3, Bell, Settings as SettingsIcon } from 'lucide-react-native';

export default function Dashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState({ signals: 0, activeBots: 0, totalPnL: 0 });

  const loadData = async () => {
    try {
      const [signalsData, botsData] = await Promise.all([
        fetchSignals(user?.openId),
        fetchBots(user?.openId)
      ]);

      const pnl = botsData?.reduce((acc: number, bot: any) => acc + (bot.pnl || 0), 0) || 0;

      setStats({
        signals: signalsData?.length || 0,
        activeBots: botsData?.filter((b: any) => b.status === 'RUNNING' || b.status === 'active').length || 0,
        totalPnL: pnl
      });
    } catch (e) {
      console.error(e);
    }
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
      <View className="px-4 py-4 border-b border-gray-800 bg-slate-950 flex-row justify-between items-center">
        <View>
          <Text className="text-2xl font-black text-white uppercase italic">SignalKey</Text>
          <Text className="text-[10px] text-primary font-bold uppercase tracking-widest">Premium Trading</Text>
        </View>
        <TouchableOpacity onPress={() => router.push('/settings')}>
          <SettingsIcon size={20} color="#94a3b8" />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
      >
        <View className="mb-6 flex-row justify-between items-end">
          <View>
            <Text className="text-gray-500 text-xs">Bienvenido,</Text>
            <Text className="text-xl font-bold text-white">{user?.name}</Text>
          </View>
          <View className="bg-emerald-500/10 px-3 py-1 rounded-full border border-emerald-500/20">
            <Text className="text-emerald-500 text-[10px] font-bold">CONECTADO</Text>
          </View>
        </View>

        {/* PnL Card */}
        <Card className="mb-6 bg-slate-900 border-gray-800 p-6 overflow-hidden">
          <View className="absolute -right-4 -top-4 opacity-10">
            <TrendingUp size={120} color="#22c55e" />
          </View>
          <Text className="text-gray-400 text-xs uppercase font-bold mb-1">P&L Global Acumulado</Text>
          <View className="flex-row items-baseline gap-2">
            <Text className={`text-4xl font-black ${stats.totalPnL >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
              {stats.totalPnL > 0 ? '+' : ''}{stats.totalPnL.toFixed(2)}%
            </Text>
            <Text className="text-gray-500 text-sm">USDT</Text>
          </View>
        </Card>

        {/* Quick Stats */}
        <View className="flex-row gap-4 mb-6">
          <Card className="flex-1 bg-slate-900 border-gray-800 p-4">
            <View className="flex-row justify-between items-center mb-2">
              <Text className="text-[10px] text-gray-500 uppercase font-bold">Señales</Text>
              <Zap size={14} color="#3b82f6" />
            </View>
            <Text className="text-2xl font-black text-white">{stats.signals}</Text>
          </Card>
          <Card className="flex-1 bg-slate-900 border-gray-800 p-4">
            <View className="flex-row justify-between items-center mb-2">
              <Text className="text-[10px] text-gray-500 uppercase font-bold">Bots Activos</Text>
              <Activity size={14} color="#10b981" />
            </View>
            <Text className="text-2xl font-black text-white">{stats.activeBots}</Text>
          </Card>
        </View>

        <Text className="text-xs text-gray-500 uppercase font-bold mb-4 px-1">Resumen de Mercado</Text>
        <Chart height={200} symbol="BTCUSDT" timeframe="1h" />

        <Text className="text-xs text-gray-500 uppercase font-bold mb-4 mt-8 px-1">Acceso Rápido</Text>
        <View className="flex-row flex-wrap gap-3 mb-10">
          {[
            { label: 'Analítica', icon: <BarChart3 size={18} color="#fff" />, route: '/analytics', color: 'bg-emerald-600' },
            { label: 'Backtest', icon: <Activity size={18} color="#fff" />, route: '/backtest', color: 'bg-blue-600' },
            { label: 'Telegram', icon: <Bell size={18} color="#fff" />, route: '/telegram', color: 'bg-sky-600' },
          ].map((item) => (
            <TouchableOpacity
              key={item.label}
              onPress={() => router.push(item.route as any)}
              className={`${item.color} p-4 rounded-2xl items-center justify-center flex-[1_0_28%] shadow-lg`}
            >
              <View className="mb-2">{item.icon}</View>
              <Text className="text-white font-black text-[10px] uppercase">{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
