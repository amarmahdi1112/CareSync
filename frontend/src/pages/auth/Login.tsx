import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useNotifications } from '../../components/ui/NotificationContainer';
import { api } from '../../api/client';
import logoSvg from '../../assets/images/svgs/Logo_flat.svg';

const Login: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login } = useAuth();
  const { addNotification } = useNotifications();
  const navigate = useNavigate();
  const location = useLocation();

  const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard';

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    try {
      const { access_token: token, user } = await api.auth.login(email, password);
      const mappedUser = {
        id: user.id,
        email: user.email,
        firstName: user.first_name,
        lastName: user.last_name,
        role: user.role.name,
        organizationId: user.organization_id || undefined,
      };
      login(mappedUser, token);
      addNotification({
        type: 'success',
        title: 'Login Successful',
        message: `Welcome back, ${user.first_name}!`
      });
      navigate(from, { replace: true });
    } catch (error) {
      console.error('Login error:', error);
      addNotification({
        type: 'error',
        title: 'Login Failed',
        message: error instanceof Error ? error.message : 'Please check your credentials and try again.'
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto">
      <div className="bg-white py-8 px-6 shadow rounded-lg sm:px-10">
        <div className="mb-8 text-center">
          <div className="flex justify-center mb-4">
            <img src={logoSvg} alt="CareSync Logo" className="h-12 w-auto" />
          </div>
          <h2 className="heading-md text-gray-900">Sign in to CareSync</h2>
          <p className="mt-2 body-sm text-gray-600">Welcome back! Please sign in to your account.</p>
        </div>
        
        <form onSubmit={handleSubmit} className="space-y-6">
          <div>
            <label htmlFor="email" className="block body-sm text-medium text-gray-700">
              Email
            </label>
            <div className="mt-1">
              <input
                id="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                type="email"
                required
                className="input"
                placeholder="Enter your email"
              />
            </div>
          </div>
          
          <div>
            <label htmlFor="password" className="block body-sm text-medium text-gray-700">
              Password
            </label>
            <div className="mt-1">
              <input
                id="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                required
                className="input"
                placeholder="Enter your password"
              />
            </div>
          </div>
          
          <div>
            <button
              type="submit"
              disabled={isLoading}
              className="btn btn-primary w-full"
            >
              {isLoading && <span className="spinner mr-2"></span>}
              {isLoading ? 'Signing in...' : 'Sign in'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;
