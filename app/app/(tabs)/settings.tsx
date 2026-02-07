import React from 'react';
import { View, Text, ScrollView, Switch } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../../context/AuthContext';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';

export default function SettingsScreen() {
  const { user, signOut } = useAuth();

  return (
    <SafeAreaView className="flex-1 bg-background">
      <ScrollView contentContainerStyle={{ padding: 16 }}>
        <Text className="text-2xl font-bold text-foreground mb-6">Settings</Text>

        <Card className="mb-6">
          <View className="mb-4">
             <Text className="text-sm text-muted-foreground">User Profile</Text>
             <Text className="text-lg text-foreground font-medium">{user?.name}</Text>
             <Text className="text-sm text-muted-foreground">{user?.openId}</Text>
          </View>
        </Card>

        <Text className="text-lg font-semibold text-foreground mb-4">Preferences</Text>

        <Card className="mb-6">
           <View className="flex-row justify-between items-center py-2">
             <Text className="text-foreground">Dark Mode</Text>
             <Switch value={true} trackColor={{ true: '#3b82f6' }} />
           </View>
           <View className="flex-row justify-between items-center py-2">
             <Text className="text-foreground">Notifications</Text>
             <Switch value={true} trackColor={{ true: '#3b82f6' }} />
           </View>
        </Card>

        <Button title="Sign Out" variant="destructive" onPress={signOut} />

        <Text className="text-center text-xs text-muted-foreground mt-8">SignalKey Mobile v1.0.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}
