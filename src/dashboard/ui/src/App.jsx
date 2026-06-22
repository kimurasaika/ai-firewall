import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "./pages/Dashboard";
import Whitelist from "./pages/Whitelist";
import AuditLog from "./pages/AuditLog";
import Login from "./pages/Login";
import NavBar from "./components/NavBar";

const queryClient = new QueryClient();

function PrivateRoutes() {
  const token = localStorage.getItem("dlp_token");
  if (!token) return <Navigate to="/login" replace />;
  return (
    <>
      <NavBar />
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/whitelist" element={<Whitelist />} />
          <Route path="/audit" element={<AuditLog />} />
        </Routes>
      </main>
    </>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/*" element={<PrivateRoutes />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
