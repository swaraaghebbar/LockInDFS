import { useAuth } from './AuthContext.jsx';
import LoginPage from './pages/LoginPage.jsx';
import AdminDashboard from './pages/AdminDashboard.jsx';
import UserDashboard from './pages/UserDashboard.jsx';

export default function App() {
  const { user, loading, isAdmin } = useAuth();

  if (loading) {
    return (
      <div className="auth-loading-screen">
        <div className="auth-loading-logo" />
        <p className="loading-text">Loading secure session…</p>
      </div>
    );
  }

  if (!user) {
    return <LoginPage />;
  }

  if (isAdmin) {
    return <AdminDashboard />;
  }

  return <UserDashboard />;
}
