import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { fetchUser, TOKEN_KEY, login as apiLogin, register as apiRegister } from '../lib/api';
import { useRouter, useSegments } from 'expo-router';

interface AuthContextType {
  user: any | null;
  isLoading: boolean;
  signIn: (data: any) => Promise<void>;
  signUp: (data: any) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({} as AuthContextType);

export function useAuth() {
  return useContext(AuthContext);
}

function useProtectedRoute(user: any) {
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    const inAuthGroup = segments[0] === '(auth)';

    if (
      // If the user is not signed in and the initial segment is not anything in the auth group.
      !user &&
      !inAuthGroup
    ) {
      // Redirect to the sign-in page.
      router.replace('/(auth)/login');
    } else if (user && inAuthGroup) {
      // Redirect away from the sign-in page.
      router.replace('/(tabs)/');
    }
  }, [user, segments]);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    async function loadUser() {
      try {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        if (token) {
          const userData = await fetchUser();
          if (userData) {
            setUser(userData);
          } else {
            // Token invalid
            await SecureStore.deleteItemAsync(TOKEN_KEY);
          }
        }
      } catch (e) {
        console.error("Auth load error:", e);
      } finally {
        setIsLoading(false);
      }
    }
    loadUser();
  }, []);

  useProtectedRoute(user);

  const signIn = async (data: any) => {
    try {
      const res = await apiLogin(data);
      if (res.token) {
        await SecureStore.setItemAsync(TOKEN_KEY, res.token);
        setUser(res.user);
        router.replace('/(tabs)/');
      }
    } catch (e) {
      throw e;
    }
  };

  const signUp = async (data: any) => {
    try {
      const res = await apiRegister(data);
      if (res.token) {
        await SecureStore.setItemAsync(TOKEN_KEY, res.token);
        setUser(res.user);
        router.replace('/(tabs)/');
      }
    } catch (e) {
      throw e;
    }
  };

  const signOut = async () => {
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    setUser(null);
    router.replace('/(auth)/login');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        signIn,
        signUp,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
