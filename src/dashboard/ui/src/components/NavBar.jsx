import { Link, useNavigate } from "react-router-dom";

export default function NavBar() {
  const navigate = useNavigate();
  function logout() {
    localStorage.removeItem("dlp_token");
    navigate("/login");
  }
  return (
    <nav className="bg-gray-900 text-white px-6 py-3 flex items-center justify-between">
      <div className="flex gap-6 items-center">
        <span className="font-bold text-lg tracking-tight">AI Firewall</span>
        <Link to="/" className="text-gray-300 hover:text-white text-sm">Dashboard</Link>
        <Link to="/whitelist" className="text-gray-300 hover:text-white text-sm">Whitelist</Link>
        <Link to="/audit" className="text-gray-300 hover:text-white text-sm">Audit Log</Link>
      </div>
      <button
        onClick={logout}
        className="text-sm text-gray-400 hover:text-white transition"
      >
        Logout
      </button>
    </nav>
  );
}
