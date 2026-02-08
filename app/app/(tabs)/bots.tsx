import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, RefreshControl, FlatList, Alert, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { fetchBots, stopBot } from '../../lib/api';

export default function BotsScreen() {
  const { user } = useAuth();
  const [bots, setBots] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const loadBots = async () => {
    try {
      const data = await fetchBots(user?.openId);
      setBots(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadBots();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadBots();
    setRefreshing(false);
  };

  const handleStopBot = async (botId: string) => {
    Alert.alert(
      "Detener Bot",
      "¿Estás seguro de que quieres detener este bot?",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Detener", style: "destructive", onPress: async () => {
            try {
              await stopBot(botId);
              loadBots();
            } catch (e) {
              Alert.alert("Error", "No se pudo detener el bot");
            }
          }
        }
      ]
    );
  };

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4 bg-slate-900 border-gray-800 p-4">
      <View className="flex-row justify-between items-start mb-3">
        <View className="flex-1">
          <View className="flex-row items-center gap-2 mb-1">
            <Text className="text-lg font-bold text-white">{item.symbol}</Text>
            <View className={`px-2 py-0.5 rounded ${item.mode === 'real' ? 'bg-red-500/20' : 'bg-blue-500/20'}`}>
              <Text className={`text-[10px] font-bold ${item.mode === 'real' ? 'text-red-400' : 'text-blue-400'}`}>
                {item.mode === 'real' ? 'LIVE' : 'SIM'}
              </Text>
            </View>
          </View>
          <Text className="text-xs text-gray-500">{item.strategy_name || item.strategy}</Text>
        </View>
        <View className="items-end">
          <View className={`h-2 w-2 rounded-full mb-1 ${item.status === 'active' || item.status === 'RUNNING' ? 'bg-emerald-500 shadow-sm shadow-emerald-500' : 'bg-gray-600'}`} />
          <Text className="text-[10px] text-gray-500 uppercase">{item.status}</Text>
        </View>
      </View>

      <View className="flex-row justify-between items-end mt-2 pt-3 border-t border-gray-800/50">
        <View className="flex-row gap-6">
          <View>
            <Text className="text-[10px] text-gray-500 uppercase mb-1">PnL %</Text>
            <Text className={`text-lg font-black ${item.pnl >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
              {item.pnl > 0 ? '+' : ''}{item.pnl?.toFixed(2)}%
            </Text>
          </View>
          <View>
            <Text className="text-[10px] text-gray-500 uppercase mb-1">Balance</Text>
            <Text className="text-sm font-bold text-gray-300">
              ${item.config?.initial_balance?.toFixed(0) || item.amount || '---'}
            </Text>
          </View>
        </View>

        <TouchableOpacity
          onPress={() => handleStopBot(item.id || item._id)}
          className="bg-red-500/10 border border-red-500/20 px-4 py-2 rounded-lg"
        >
          <Text className="text-red-500 font-bold text-xs">Detener</Text>
        </TouchableOpacity>
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
      <View className="px-4 py-4 border-b border-gray-800 bg-slate-950">
        <Text className="text-2xl font-black text-white uppercase italic">Bots Activos</Text>
      </View>
      <FlatList
        data={bots}
        renderItem={renderItem}
        keyExtractor={(item) => item.id || item._id}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
        ListEmptyComponent={
          !isLoading ? (
            <View className="mt-20 items-center">
              <Text className="text-gray-500 italic">No hay bots activos.</Text>
              <Text className="text-gray-600 text-xs mt-2">Crea uno desde el Strategy Lab en la web.</Text>
            </View>
          ) : null
        }
      />
    </SafeAreaView>
  );
}
