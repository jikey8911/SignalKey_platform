import React, { useEffect, useState } from 'react';
import { View, Text, FlatList, RefreshControl, Alert, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { fetchSignals, approveSignal } from '../../lib/api';
import { Zap, Clock, CheckCircle, XCircle, AlertCircle } from 'lucide-react-native';

export default function SignalsScreen() {
  const { user } = useAuth();
  const [signals, setSignals] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const loadSignals = async () => {
    try {
      const data = await fetchSignals(user?.openId);
      setSignals(data || []);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
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
        Alert.alert("Éxito", "Señal aprobada y ejecución iniciada");
        loadSignals();
      } else {
        Alert.alert("Error", res.message);
      }
    } catch (e) {
      Alert.alert("Error", "No se pudo aprobar la señal");
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'processing': return 'text-blue-400';
      case 'accepted': return 'text-emerald-400';
      case 'rejected': return 'text-red-400';
      case 'executing': return 'text-orange-400';
      case 'completed': return 'text-emerald-500';
      default: return 'text-gray-400';
    }
  };

  const renderItem = ({ item }: { item: any }) => (
    <Card className="mb-4 bg-slate-900 border-gray-800 p-0 overflow-hidden">
      <View className="p-4 border-b border-gray-800/50 flex-row justify-between items-center">
        <View className="flex-row items-center gap-2">
          <Text className="text-xl font-bold text-white">{item.symbol}</Text>
          <View className={`px-2 py-0.5 rounded ${item.decision === 'BUY' ? 'bg-emerald-500/20' : 'bg-red-500/20'}`}>
            <Text className={`text-[10px] font-bold ${item.decision === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
              {item.decision}
            </Text>
          </View>
        </View>
        <View className="flex-row items-center gap-1">
          <Text className={`text-[10px] font-bold uppercase ${getStatusColor(item.status)}`}>
            {item.status}
          </Text>
        </View>
      </View>

      <View className="p-4">
        {/* Confianza */}
        <View className="mb-4">
          <View className="flex-row justify-between mb-1">
            <Text className="text-[10px] text-gray-500 uppercase">Confianza IA</Text>
            <Text className="text-[10px] text-white font-bold">{Math.round((item.confidence || 0) * 100)}%</Text>
          </View>
          <View className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
            <View
              className="h-full bg-primary"
              style={{ width: `${(item.confidence || 0) * 100}%` }}
            />
          </View>
        </View>

        {/* Razonamiento */}
        {item.reasoning && (
          <View className="bg-slate-800/50 p-3 rounded-lg mb-4">
            <Text className="text-xs text-gray-300 italic">"{item.reasoning}"</Text>
          </View>
        )}

        <View className="flex-row justify-between items-center">
          <Text className="text-[10px] text-gray-500">{new Date(item.createdAt).toLocaleString()}</Text>
          {['processing', 'accepted', 'rejected'].includes(item.status) && (
            <TouchableOpacity
              onPress={() => handleApprove(item.id || item._id)}
              className="bg-primary/20 border border-primary/30 px-3 py-1.5 rounded-lg flex-row items-center gap-2"
            >
              <Zap size={12} color="#3b82f6" />
              <Text className="text-primary font-bold text-[10px]">Aprobar</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </Card>
  );

  return (
    <SafeAreaView className="flex-1 bg-background">
      <View className="px-4 py-4 border-b border-gray-800 bg-slate-950 flex-row justify-between items-center">
        <Text className="text-2xl font-black text-white uppercase italic">Señales IA</Text>
        <TouchableOpacity onPress={onRefresh}>
          <Text className="text-primary text-xs font-bold">Refrescar</Text>
        </TouchableOpacity>
      </View>
      <FlatList
        data={signals}
        renderItem={renderItem}
        keyExtractor={(item) => item.id || item._id}
        contentContainerStyle={{ padding: 16 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#fff" />}
        ListEmptyComponent={
          !isLoading ? (
            <View className="mt-20 items-center">
              <Text className="text-gray-500 italic">No hay señales disponibles.</Text>
            </View>
          ) : null
        }
      />
    </SafeAreaView>
  );
}
