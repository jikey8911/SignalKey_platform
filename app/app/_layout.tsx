import { Stack } from 'expo-router';
import { AuthProvider } from '../context/AuthContext';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import "../global.css";

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <AuthProvider>
        <Stack screenOptions={{
          headerStyle: { backgroundColor: '#0f172a' },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: 'bold' },
        }}>
          <Stack.Screen name="(auth)" options={{ headerShown: false }} />
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="backtest" options={{ presentation: 'modal', headerShown: true, title: 'Backtest' }} />
          <Stack.Screen name="training" options={{ headerShown: true, title: 'AI Training' }} />
          <Stack.Screen name="telegram" options={{ headerShown: true, title: 'Telegram Console' }} />
        </Stack>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
