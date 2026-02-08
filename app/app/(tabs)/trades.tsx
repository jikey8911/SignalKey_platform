import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { fetchTrades } from '../../lib/api';
import { format } from 'date-fns';

import { TrendingUp, TrendingDown, DollarSign, Activity } from 'lucide-react-native';

export default function TradesScreen() {
  const { user } = useAuth();
  const [trades, setTrades] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const loadTrades = async () => {
    try {
      const data = await fetchTrades(user?.openId);
      setTrades(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTrades();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadTrades();
    setRefreshing(false);
  };

  const totalPnL = trades.reduce((acc, trade) => acc + (trade.pnl || 0), 0);
  const winRate = trades.length > 0
    ? (trades.filter(t => t.pnl > 0).length / trades.length) * 100
    : 0;

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4 bg-slate-900 border-gray-800 p-4">
      <View className="flex-row justify-between items-center mb-3">
        <View className="flex-row items-center gap-2">
          <Text className="text-lg font-bold text-white">{item.symbol}</Text>
          <View className={`px-2 py-0.5 rounded ${item.side === 'BUY' ? 'bg-emerald-500/10' : 'bg-red-500/10'}`}>
            <Text className={`text-[10px] font-bold ${item.side === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
              {item.side}
            </Text>
          </View>
        </View>
        <View className={`px-2 py-0.5 rounded ${item.isDemo ? 'bg-amber-500/10' : 'bg-emerald-500/10'}`}>
          <Text className={`text-[10px] font-bold ${item.isDemo ? 'text-amber-400' : 'text-emerald-400'}`}>
            {item.isDemo ? 'DEMO' : 'REAL'}
          </Text>
        </View>
      </View>

      <View className="flex-row justify-between mb-4">
        <View>
          <Text className="text-[10px] text-gray-500 uppercase">Precio</Text>
          <Text className="text-sm font-mono text-gray-300">${item.price}</Text>
        </View>
        <View className="items-center">
          <Text className="text-[10px] text-gray-500 uppercase">Cantidad</Text>
          <Text className="text-sm font-mono text-gray-300">{item.amount}</Text>
        </View>
        <View className="items-end">
          <Text className="text-[10px] text-gray-500 uppercase">PnL</Text>
          <Text className={`text-sm font-bold ${item.pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
            {item.pnl ? `${item.pnl > 0 ? '+' : ''}${item.pnl.toFixed(2)}%` : '---'}
          </Text>
        </View>
      </View>

      <View className="flex-row justify-between items-center pt-3 border-t border-gray-800/50">
        <Text className="text-[10px] text-gray-500">
          {new Date(item.timestamp || item.createdAt).toLocaleString()}
        </Text>
        <Text className="text-[10px] text-gray-600 uppercase font-bold">{item.status || 'Completado'}</Text>
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
      <View className="px-4 py-4 border-b border-gray-800 bg-slate-950">
        <Text className="text-2xl font-black text-white uppercase italic">Historial de Trades</Text>
      </View>

      <View className="p-4 flex-row gap-4">
        <Card className="flex-1 bg-primary/10 border-primary/20 p-3">
          <View className="flex-row justify-between items-center mb-1">
            <Text className="text-[10px] text-gray-400">P&L Total</Text>
            <TrendingUp size={12} color="#3b82f6" />
          </View>
          <Text className="text-lg font-black text-white">${totalPnL.toFixed(2)}</Text>
        </Card>
        <Card className="flex-1 bg-emerald-500/10 border-emerald-500/20 p-3">
          <View className="flex-row justify-between items-center mb-1">
            <Text className="text-[10px] text-gray-400">Win Rate</Text>
            <Activity size={12} color="#10b981" />
          </View>
          <Text className="text-lg font-black text-white">{winRate.toFixed(1)}%</Text>
        </Card>
      </View>

      <FlatList
        data={trades}
        renderItem={renderItem}
        keyExtractor={(item) => item.id || item._id}
        contentContainerStyle={{ padding: 16, paddingTop: 0 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
        ListEmptyComponent={
          !isLoading ? (
            <View className="mt-20 items-center">
              <Text className="text-gray-500 italic">No hay trades registrados.</Text>
            </View>
          ) : null
        }
      />
    </SafeAreaView>
  );
}
