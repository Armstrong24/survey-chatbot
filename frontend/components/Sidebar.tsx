"use client";

/**
 * Left sidebar with project info, live response count, and suggested questions.
 */

import { useEffect, useState } from "react";
import { fetchStats } from "@/lib/api";

interface Props {
  onSuggest: (q: string) => void;
}

const SUGGESTED_QUESTIONS = [
  "What percentage of respondents are students?",
  "What is the most common age group?",
  "How many people own a reusable bag?",
  "What are the top 2 reasons people still use plastic bags?",
  "What would encourage most people to switch to eco-bags?",
  "How harmful do people think plastic is for Pune? (avg rating)",
  "At what price point do most people refuse plastic bags?",
  "Where do people get plastic bags most often?",
];

export default function Sidebar({ onSuggest }: Props) {
  const [totalResponses, setTotalResponses] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  // Poll for live response count every 30 seconds
  useEffect(() => {
    const load = async () => {
      try {
        const stats = await fetchStats();
        setTotalResponses(stats.total_responses);
        setError(false);
      } catch {
        setError(true);
      } finally {
        setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="w-72 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col overflow-y-auto">
      {/* Header / branding */}
      <div className="p-5 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-2xl">🌿</span>
          <span className="text-xs font-semibold text-brand-700 uppercase tracking-wider">
            Survey Chatbot
          </span>
        </div>
        <h1 className="text-sm font-bold text-gray-900 leading-snug">
          Awareness & Readiness: Sustainable Alternatives to Plastic Bags
        </h1>
        <p className="text-xs text-gray-500 mt-1.5 leading-relaxed">
          Pune, India — Ask any question about the survey data and get
          real-time, calculated answers.
        </p>
      </div>

      {/* Live response counter */}
      <div className="m-4 p-4 rounded-xl bg-brand-50 border border-brand-200">
        <p className="text-xs text-brand-700 font-medium uppercase tracking-wider mb-1">
          Total Live Responses
        </p>
        {loading ? (
          <div className="h-8 w-16 bg-brand-200 animate-pulse rounded" />
        ) : error ? (
          <p className="text-sm text-red-500">Could not load</p>
        ) : (
          <p className="text-3xl font-bold text-brand-700">
            {totalResponses?.toLocaleString()}
          </p>
        )}
        <p className="text-xs text-brand-600 mt-1 opacity-70">
          Updates every 30 seconds
        </p>
      </div>

      {/* Suggested questions */}
      <div className="px-4 pb-4 flex-1">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          Try asking
        </p>
        <div className="flex flex-col gap-1.5">
          {SUGGESTED_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => onSuggest(q)}
              className="text-left text-xs text-gray-600 hover:text-brand-700 hover:bg-brand-50 px-3 py-2 rounded-lg transition-colors border border-transparent hover:border-brand-200"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-gray-100 text-center">
        <p className="text-xs text-gray-400">
          Data from Google Forms · Powered by Gemini
        </p>
      </div>
    </aside>
  );
}
