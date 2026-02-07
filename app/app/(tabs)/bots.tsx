import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, RefreshControl, FlatList, Alert } from 'react-native';
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
        "Stop Bot",
        "Are you sure you want to stop this bot?",
        [
            { text: "Cancel", style: "cancel" },
            { text: "Stop", style: "destructive", onPress: async () => {
                try {
                    await stopBot(botId);
                    // Optimistic update or refresh
                    loadBots();
                } catch (e) {
                    Alert.alert("Error", "Failed to stop bot");
                }
            }}
        ]
    );
  };

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4">
      <View className="flex-row justify-between items-start mb-2">
        <View>
          <Text className="text-lg font-bold text-foreground">{item.symbol} {item.direction}</Text>
          <Text className="text-sm text-muted-foreground">{item.strategy}</Text>
        </View>
        <View className={`px-2 py-1 rounded-full ${item.status === 'RUNNING' ? 'bg-emerald-500/20' : 'bg-destructive/20'}`}>
          <Text className={`text-xs font-bold ${item.status === 'RUNNING' ? 'text-emerald-500' : 'text-destructive'}`}>
            {item.status}
          </Text>
        </View>
      </View>

      <View className="flex-row justify-between mt-2">
         <View>
           <Text className="text-xs text-muted-foreground">PnL</Text>
           <Text className={`font-mono ${item.pnl >= 0 ? 'text-emerald-500' : 'text-destructive'}`}>
             {item.pnl}%
           </Text>
         </View>
         <Button
            title="Stop"
            variant="destructive"
            className="h-8 px-3"
            onPress={() => handleStopBot(item.id || item._id)}
         />
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
       <View className="px-4 py-2 border-b border-border">
         <Text className="text-xl font-bold text-foreground">Active Bots</Text>
       </View>
       <FlatList
         data={bots}
         renderItem={renderItem}
         keyExtractor={(item) => item.id || item._id}
         contentContainerStyle={{ padding: 16 }}
         refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
         ListEmptyComponent={
           !isLoading ? (
             <Text className="text-center text-muted-foreground mt-10">No active bots found.</Text>
           ) : null
         }
       />
    </SafeAreaView>
  );
}
