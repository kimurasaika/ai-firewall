import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "https://localhost:9443";
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem("dlp_token")}` });

export default function AuditLog() {
  const [hours, setHours] = useState(24);
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading, error } = useQuery({
    queryKey: ["audit", hours, eventType, page],
    queryFn: () => {
      const params = new URLSearchParams({ hours, page, page_size: 50 });
      if (eventType) params.append("event_type", eventType);
      return axios.get(`${API}/v1/audit?${params}`, { headers: authHeader() }).then(r => r.data);
    },
  });

  const entries = data?.entries ?? [];
  const totalPages = data ? Math.ceil(data.total / 50) : 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white">Audit Log</h2>
        <div className="flex gap-3">
          <select
            className="bg-gray-800 text-gray-300 text-sm rounded px-3 py-1.5 border border-gray-700"
            value={hours}
            onChange={e => { setHours(Number(e.target.value)); setPage(1); }}
          >
            <option value={1}>Last 1 hour</option>
            <option value={24}>Last 24 hours</option>
            <option value={168}>Last 7 days</option>
            <option value={720}>Last 30 days</option>
          </select>
          <select
            className="bg-gray-800 text-gray-300 text-sm rounded px-3 py-1.5 border border-gray-700"
            value={eventType}
            onChange={e => { setEventType(e.target.value); setPage(1); }}
          >
            <option value="">All events</option>
            <option value="redact">redact</option>
            <option value="deanon_miss">deanon_miss</option>
          </select>
        </div>
      </div>

      {isLoading && <p className="text-gray-400">Loading…</p>}
      {error && <p className="text-red-400">Failed to load audit log</p>}

      <div className="bg-gray-800 rounded-xl overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-400 uppercase border-b border-gray-700">
              <th className="px-4 py-3 text-left">Time</th>
              <th className="px-4 py-3 text-left">Event</th>
              <th className="px-4 py-3 text-left">Session</th>
              <th className="px-4 py-3 text-left">Entity</th>
              <th className="px-4 py-3 text-left">Token</th>
              <th className="px-4 py-3 text-left">Source IP</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.id} className="border-b border-gray-700 hover:bg-gray-750">
                <td className="px-4 py-2 text-gray-400 whitespace-nowrap">
                  {new Date(e.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2">
                  <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                    e.event_type === "deanon_miss" ? "bg-yellow-900 text-yellow-300" : "bg-blue-900 text-blue-300"
                  }`}>
                    {e.event_type}
                  </span>
                </td>
                <td className="px-4 py-2 text-gray-400 font-mono text-xs truncate max-w-28">
                  {e.session_id?.slice(0, 8)}…
                </td>
                <td className="px-4 py-2 text-gray-300">{e.entity_type ?? "—"}</td>
                <td className="px-4 py-2 text-gray-300 font-mono">{e.token ?? "—"}</td>
                <td className="px-4 py-2 text-gray-400">{e.source_ip ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-3 py-1 bg-gray-800 rounded text-sm text-gray-300 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="text-gray-400 text-sm py-1">{page} / {totalPages}</span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
            className="px-3 py-1 bg-gray-800 rounded text-sm text-gray-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
