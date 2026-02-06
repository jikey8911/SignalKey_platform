import React, { useState } from 'react';
import { View, Text, Image, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { useAuth } from '../../context/AuthContext';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { Link } from 'expo-router';

export default function LoginScreen() {
  const { signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async () => {
    setIsLoading(true);
    setError('');
    try {
      await signIn({ username, password });
    } catch (e: any) {
      setError('Invalid credentials');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      className="flex-1 bg-background"
    >
      <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 24 }}>
        <View className="items-center mb-8">
          <View className="w-20 h-20 bg-primary/20 rounded-full items-center justify-center mb-4">
             {/* Logo placeholder */}
             <Text className="text-4xl">⚡</Text>
          </View>
          <Text className="text-3xl font-bold text-foreground">SignalKey</Text>
          <Text className="text-muted-foreground mt-2">Sign in to your account</Text>
        </View>

        <View className="space-y-4 w-full max-w-sm mx-auto">
          <Input
            label="Username"
            value={username}
            onChangeText={setUsername}
            autoCapitalize="none"
          />
          <Input
            label="Password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
          />

          {error ? <Text className="text-destructive text-center">{error}</Text> : null}

          <Button
            title="Sign In"
            onPress={handleLogin}
            isLoading={isLoading}
            className="mt-4"
          />
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
