import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { fetchMe, getGoogleLoginUrl, logoutUser } from './api.js';

const AuthContext = createContext({
  user: null,
  loading: true,
  isAdmin: false,
  login: () => {},
  logout: () => {},
  refetchUser: () => {},
});

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const data = await fetchMe();
      setUser(data);
    } catch (e) {
      console.error('Auth check error:', e);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = useCallback(() => {
    window.location.href = getGoogleLoginUrl();
  }, []);

  const logout = useCallback(async () => {
    try {
      await logoutUser();
    } catch (e) {
      console.error('Logout error:', e);
    } finally {
      setUser(null);
      window.location.href = '/';
    }
  }, []);

  const value = {
    user,
    loading,
    isAdmin: !!user?.is_admin,
    login,
    logout,
    refetchUser: checkAuth,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
