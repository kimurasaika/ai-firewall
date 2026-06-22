import { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "https://localhost:9443";

export default function Login() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [tempToken, setTempToken] = useState(null);
  const [error, setError] = useState("");

  async function handleLogin(e) {
    e.preventDefault();
    setError("");
    try {
      const res = await axios.post(`${API}/v1/auth/login`, { username, password });
      setTempToken(res.data.temp_token);
    } catch {
      setError("Invalid username or password");
    }
  }

  async function handleMFA(e) {
    e.preventDefault();
    setError("");
    try {
      const res = await axios.post(`${API}/v1/auth/mfa`, {
        temp_token: tempToken,
        totp_code: totpCode,
      });
      localStorage.setItem("dlp_token", res.data.access_token);
      navigate("/");
    } catch {
      setError("Invalid MFA code");
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="bg-gray-900 text-white rounded-xl p-8 w-full max-w-sm shadow-2xl">
        <h1 className="text-2xl font-bold mb-6 text-center">AI Firewall Admin</h1>
        {error && <p className="text-red-400 text-sm mb-4 text-center">{error}</p>}

        {!tempToken ? (
          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <input
              className="bg-gray-800 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
            />
            <input
              type="password"
              className="bg-gray-800 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-500 rounded py-2 font-semibold text-sm transition"
            >
              Login
            </button>
          </form>
        ) : (
          <form onSubmit={handleMFA} className="flex flex-col gap-4">
            <p className="text-gray-400 text-sm text-center">Enter your authenticator code</p>
            <input
              className="bg-gray-800 rounded px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 text-center tracking-widest"
              placeholder="000000"
              maxLength={6}
              value={totpCode}
              onChange={e => setTotpCode(e.target.value)}
              required
            />
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-500 rounded py-2 font-semibold text-sm transition"
            >
              Verify
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
