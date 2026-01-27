
'use client';

import { useState } from 'react';
import { LoginPage } from '@/components/dashboard/login-page';
import { MainDashboard, User } from '@/components/dashboard/main-dashboard';

export default function Home() {
  const [user, setUser] = useState<User | null>(null);

  const handleLogin = (userData: User) => {
    setUser(userData);
  };

  const handleLogout = () => {
    setUser(null);
  };

  // Show login page if not authenticated
  if (!user) {
    return <LoginPage onLogin={handleLogin} />;
  }

  // Show main dashboard if authenticated
  return (
    <MainDashboard
      user={user}
      onLogout={handleLogout}
    />
  );
}
