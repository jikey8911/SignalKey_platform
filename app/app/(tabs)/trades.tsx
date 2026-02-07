import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { fetchTrades } from '../../lib/api';
import { format } from 'date-fns';

export default function TradesScreen() {
  const { user } = useAuth();
  const [trades, setTrades] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadTrades = async () => {
    try {
      const data = await fetchTrades(user?.openId);
      setTrades(data || []);
    } catch (e) {
      console.error(e);
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

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4">
      <View className="flex-row justify-between items-center mb-2">
         <Text className="font-bold text-foreground">{item.symbol}</Text>
         <Text className={`font-mono ${item.side === 'BUY' ? 'text-emerald-500' : 'text-destructive'}`}>
           {item.side}
         </Text>
      </View>
      <View className="flex-row justify-between mb-1">
         <Text className="text-muted-foreground text-sm">Price</Text>
         <Text className="text-foreground text-sm font-mono">{item.price}</Text>
      </View>
      <View className="flex-row justify-between mb-1">
         <Text className="text-muted-foreground text-sm">Amount</Text>
         <Text className="text-foreground text-sm font-mono">{item.amount}</Text>
      </View>
      <View className="flex-row justify-between mt-2 pt-2 border-t border-border">
         <Text className="text-xs text-muted-foreground">{format(new Date(item.timestamp || item.createdAt), 'yyyy-MM-dd HH:mm')}</Text>
         <Text className={`text-xs font-bold ${item.pnl > 0 ? 'text-emerald-500' : item.pnl < 0 ? 'text-destructive' : 'text-muted-foreground'}`}>
           {item.pnl ? `PnL: ${item.pnl}` : ''}
         </Text>
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
      <View className="px-4 py-2 border-b border-border">
         <Text className="text-xl font-bold text-foreground">Trade History</Text>
      </View>
      <FlatList
        data={trades}
        renderItem={renderItem}
        keyExtractor={(item) => item.id || item._id}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
        ListEmptyComponent={
           <Text className="text-center text-muted-foreground mt-10">No trades found.</Text>
        }
      />
    </SafeAreaView>
  );
}
