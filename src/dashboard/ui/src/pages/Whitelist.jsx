import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "https://localhost:9443";
const authHeader = () => ({ Authorization: `Bearer ${localStorage.getItem("dlp_token")}` });

export default function Whitelist() {
  const qc = useQueryClient();
  const [newDomain, setNewDomain] = useState("");
  const [newProvider, setNewProvider] = useState("");

  const { data = [], isLoading } = useQuery({
    queryKey: ["whitelist"],
    queryFn: () => axios.get(`${API}/v1/whitelist`, { headers: authHeader() }).then(r => r.data),
  });

  const addMutation = useMutation({
    mutationFn: (entry) =>
      axios.post(`${API}/v1/whitelist`, entry, { headers: authHeader() }),
    onSuccess: () => { qc.invalidateQueries(["whitelist"]); setNewDomain(""); setNewProvider(""); },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ domain, active }) =>
      axios.patch(`${API}/v1/whitelist/${encodeURIComponent(domain)}`, { active }, { headers: authHeader() }),
    onSuccess: () => qc.invalidateQueries(["whitelist"]),
  });

  const deleteMutation = useMutation({
    mutationFn: (domain) =>
      axios.delete(`${API}/v1/whitelist/${encodeURIComponent(domain)}`, { headers: authHeader() }),
    onSuccess: () => qc.invalidateQueries(["whitelist"]),
  });

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold text-white">LLM Domain Whitelist</h2>

      <div className="bg-gray-800 rounded-xl p-5 flex gap-3 items-end">
        <div className="flex flex-col gap-1 flex-1">
          <label className="text-xs text-gray-400">Domain</label>
          <input
            className="bg-gray-700 rounded px-3 py-2 text-sm text-white outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="api.example.ai"
            value={newDomain}
            onChange={e => setNewDomain(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1 w-36">
          <label className="text-xs text-gray-400">Provider</label>
          <input
            className="bg-gray-700 rounded px-3 py-2 text-sm text-white outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="openai"
            value={newProvider}
            onChange={e => setNewProvider(e.target.value)}
          />
        </div>
        <button
          onClick={() => addMutation.mutate({ domain: newDomain, provider: newProvider, active: true })}
          disabled={!newDomain || !newProvider}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 rounded px-4 py-2 text-sm font-semibold text-white transition"
        >
          Add
        </button>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading…</p>
      ) : (
        <div className="bg-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 text-xs uppercase border-b border-gray-700">
                <th className="px-4 py-3 text-left">Domain</th>
                <th className="px-4 py-3 text-left">Provider</th>
                <th className="px-4 py-3 text-center">Active</th>
                <th className="px-4 py-3 text-center">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.map(entry => (
                <tr key={entry.domain} className="border-b border-gray-700 hover:bg-gray-750">
                  <td className="px-4 py-3 text-white font-mono">{entry.domain}</td>
                  <td className="px-4 py-3 text-gray-300">{entry.provider}</td>
                  <td className="px-4 py-3 text-center">
                    <span className={`inline-block w-2 h-2 rounded-full ${entry.active ? "bg-green-400" : "bg-gray-600"}`} />
                  </td>
                  <td className="px-4 py-3 text-center flex justify-center gap-2">
                    <button
                      onClick={() => toggleMutation.mutate({ domain: entry.domain, active: !entry.active })}
                      className="text-xs text-blue-400 hover:text-blue-300"
                    >
                      {entry.active ? "Disable" : "Enable"}
                    </button>
                    <button
                      onClick={() => deleteMutation.mutate(entry.domain)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
