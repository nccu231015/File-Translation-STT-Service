
'use client';

import { LoginPage } from '@/components/dashboard/login-page';
import { MainDashboard } from '@/components/dashboard/main-dashboard';
import { useUser } from '@/context/user-context';

export default function Home() {
  const { user, logout } = useUser();

  if (!user) {
    return <LoginPage onLogin={() => { }} />;
  }

  return <MainDashboard user={user} onLogout={logout} />;
}
