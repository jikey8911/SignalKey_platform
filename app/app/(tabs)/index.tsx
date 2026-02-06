import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { fetchConfig, fetchSignals } from '../../lib/api';
import { Chart } from '../../components/Chart';
import { useRouter } from 'expo-router';

export default function Dashboard() {
  const { user } = useAuth();
  const router = useRouter();
  const [refreshing, setRefreshing] = useState(false);
  const [stats, setStats] = useState({ signals: 0, activeBots: 0 });

  const loadData = async () => {
    try {
       // Mock stats for now or fetch real counts
       const signals = await fetchSignals(user?.openId);
       setStats({ signals: signals.length, activeBots: 0 });
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
      <ScrollView
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
      >
        <View className="mb-6">
          <Text className="text-2xl font-bold text-foreground">Dashboard</Text>
          <Text className="text-muted-foreground">Welcome back, {user?.name}</Text>
        </View>

        <View className="flex-row gap-4 mb-6">
           <Card className="flex-1 bg-primary/10 border-primary/20">
             <Text className="text-sm text-muted-foreground">Signals</Text>
             <Text className="text-2xl font-bold text-primary">{stats.signals}</Text>
           </Card>
           <Card className="flex-1 bg-emerald-500/10 border-emerald-500/20">
             <Text className="text-sm text-muted-foreground">Active Bots</Text>
             <Text className="text-2xl font-bold text-emerald-500">{stats.activeBots}</Text>
           </Card>
        </View>

        <Text className="text-lg font-semibold text-foreground mb-4">Market Overview</Text>
        <Chart height={300} symbol="BTCUSDT" timeframe="1h" />

        <Text className="text-lg font-semibold text-foreground mb-4 mt-6">Tools</Text>
        <View className="flex-row gap-4 mb-6">
           <Button title="Backtest" variant="outline" onPress={() => router.push('/backtest')} className="flex-1" />
           <Button title="Training" variant="outline" onPress={() => router.push('/training')} className="flex-1" />
           <Button title="Telegram" variant="outline" onPress={() => router.push('/telegram')} className="flex-1" />
        </View>

      </ScrollView>
    </SafeAreaView>
  );
}
