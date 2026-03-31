"use client";

/**
 * Sidebar with project info, live response count, and suggested questions.
 * On mobile: hidden by default, slides in when toggled via parent.
 */

import { useEffect, useState } from "react";
import { fetchStats } from "@/lib/api";

interface Props {
  onSuggest: (q: string) => void;
  isOpen: boolean;
  onClose: () => void;
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

export default function Sidebar({ onSuggest, isOpen, onClose }: Props) {
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

  const handleSuggest = (q: string) => {
    onSuggest(q);
    onClose(); // auto-close sidebar on mobile after clicking a suggestion
  };

  return (
    <>
      {/* Mobile backdrop overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-20 md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar panel */}
      <aside
        className={`
          fixed top-0 left-0 h-full z-30 w-72 bg-white border-r border-gray-200
          flex flex-col overflow-y-auto transition-transform duration-300
          md:relative md:translate-x-0 md:flex-shrink-0
          ${isOpen ? "translate-x-0 shadow-xl" : "-translate-x-full"}
        `}
      >
        {/* Header / branding */}
        <div className="p-5 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <span className="text-2xl">🌿</span>
              <span className="text-xs font-semibold text-brand-700 uppercase tracking-wider">
                Survey Chatbot
              </span>
            </div>
            {/* Close button — mobile only */}
            <button
              onClick={onClose}
              className="md:hidden p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              aria-label="Close menu"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <h1 className="text-sm font-bold text-gray-900 leading-snug">
            Awareness &amp; Readiness: Sustainable Alternatives to Plastic Bags
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
                onClick={() => handleSuggest(q)}
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
    </>
  );
}
