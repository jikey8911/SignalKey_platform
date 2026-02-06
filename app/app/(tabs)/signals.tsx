import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, RefreshControl, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { fetchSignals, approveSignal } from '../../lib/api';
import { format } from 'date-fns';

export default function SignalsScreen() {
  const { user } = useAuth();
  const [signals, setSignals] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const loadSignals = async () => {
    try {
      const data = await fetchSignals(user?.openId);
      setSignals(data || []);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadSignals();
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await loadSignals();
    setRefreshing(false);
  };

  const handleApprove = async (signalId: string) => {
      try {
          const res = await approveSignal(signalId);
          if (res.success) {
              Alert.alert("Success", "Signal approved and bot started.");
              loadSignals();
          } else {
              Alert.alert("Error", res.message || "Failed to approve signal");
          }
      } catch (e) {
          Alert.alert("Error", "Failed to connect to server");
      }
  };

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4">
      <View className="flex-row justify-between items-center mb-2">
         <View className="flex-row items-center gap-2">
            <Text className="text-lg font-bold text-foreground">{item.symbol}</Text>
            <Text className={`text-xs font-bold px-2 py-0.5 rounded ${item.decision === 'BUY' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-destructive/20 text-destructive'}`}>
              {item.decision}
            </Text>
         </View>
         <Text className="text-xs text-muted-foreground">{format(new Date(item.createdAt), 'MMM d, HH:mm')}</Text>
      </View>

      <Text className="text-sm text-foreground mb-3" numberOfLines={2}>{item.reasoning}</Text>

      <View className="flex-row justify-between items-center">
        <Text className="text-xs text-muted-foreground">Confidence: {Math.round(item.confidence * 100)}%</Text>
        {item.status === 'NEW' && (
          <Button
            title="Approve"
            variant="primary"
            className="h-8 px-4"
            onPress={() => handleApprove(item.id || item._id)}
          />
        )}
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
      <View className="px-4 py-2 border-b border-border">
         <Text className="text-xl font-bold text-foreground">Signals</Text>
      </View>
      <FlatList
        data={signals}
        renderItem={renderItem}
        keyExtractor={(item) => item.id || item._id}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
        ListEmptyComponent={
           <Text className="text-center text-muted-foreground mt-10">No signals found.</Text>
        }
      />
    </SafeAreaView>
  );
}
