import { useQuery } from "@tanstack/react-query";
import axios from "axios";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";

const API = import.meta.env.VITE_API_URL || "https://localhost:9443";
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem("dlp_token")}` });

function StatCard({ label, value, color = "text-white" }) {
  return (
    <div className="bg-gray-800 rounded-xl p-5 flex flex-col gap-1">
      <span className="text-gray-400 text-xs uppercase tracking-widest">{label}</span>
      <span className={`text-3xl font-bold ${color}`}>{value ?? "—"}</span>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["stats"],
    queryFn: () =>
      axios.get(`${API}/v1/stats`, { headers: authHeader() }).then(r => r.data),
    refetchInterval: 30_000,
  });

  const entityData = data
    ? Object.entries(data.top_entity_types).map(([k, v]) => ({ name: k, count: v }))
    : [];

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold text-white">Last 24 Hours</h2>

      {isLoading && <p className="text-gray-400">Loading…</p>}
      {error && <p className="text-red-400">Failed to load stats</p>}

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Redactions" value={data?.total_redactions_24h} color="text-blue-400" />
        <StatCard label="Sessions" value={data?.total_sessions_24h} color="text-green-400" />
        <StatCard
          label="Deanon Misses"
          value={data?.deanon_miss_count_24h}
          color={data?.deanon_miss_count_24h > 0 ? "text-yellow-400" : "text-white"}
        />
      </div>

      {entityData.length > 0 && (
        <div className="bg-gray-800 rounded-xl p-5">
          <h3 className="text-gray-300 text-sm mb-4">Redactions by Entity Type</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={entityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <YAxis tick={{ fill: "#9ca3af", fontSize: 12 }} />
              <Tooltip
                contentStyle={{ background: "#1f2937", border: "none", color: "#f9fafb" }}
              />
              <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
