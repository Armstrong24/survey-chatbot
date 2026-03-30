"use client";

/**
 * Main chat page.
 *
 * Layout:
 *   ┌─────────────┬───────────────────────────────────┐
 *   │   Sidebar   │         Chat Area                 │
 *   │  (info +    │  ┌─────────────────────────────┐  │
 *   │  suggested  │  │       Messages list         │  │
 *   │  questions) │  └─────────────────────────────┘  │
 *   │             │  ┌─────────────────────────────┐  │
 *   │             │  │       Input bar             │  │
 *   │             │  └─────────────────────────────┘  │
 *   └─────────────┴───────────────────────────────────┘
 */

import { useEffect, useRef, useState, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import Sidebar from "@/components/Sidebar";
import MessageBubble, { Message } from "@/components/MessageBubble";
import TypingIndicator from "@/components/TypingIndicator";
import { sendMessage, clearChat } from "@/lib/api";

// Generate a unique session ID per browser tab (persists across page refresh)
function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = sessionStorage.getItem("chatSessionId");
  if (!id) {
    id = uuidv4();
    sessionStorage.setItem("chatSessionId", id);
  }
  return id;
}

const WELCOME_MESSAGE: Message = {
  id: "welcome",
  role: "assistant",
  content:
    "Hello! I'm your survey data analyst 🌿\n\n" +
    "I have live access to the Pune plastic bag survey responses. " +
    "You can ask me anything — percentages, counts, comparisons, trends.\n\n" +
    "Try: \"What percentage of respondents are students?\" or " +
    "\"What's the most common reason people still use plastic bags?\"",
  timestamp: new Date(),
};

export default function ChatPage() {
  const [messages, setMessages]   = useState<Message[]>([WELCOME_MESSAGE]);
  const [input, setInput]         = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError]         = useState<string | null>(null);
  const [sessionId]               = useState(getSessionId);

  const bottomRef  = useRef<HTMLDivElement>(null);
  const inputRef   = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Send a message (called by both form submit and sidebar suggestion clicks)
  const handleSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      setError(null);
      setInput("");

      // Add user message immediately
      const userMsg: Message = {
        id:        uuidv4(),
        role:      "user",
        content:   trimmed,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);

      try {
        const data = await sendMessage(trimmed, sessionId);

        const aiMsg: Message = {
          id:        uuidv4(),
          role:      "assistant",
          content:   data.response,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, aiMsg]);
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Something went wrong.";
        setError(msg);
      } finally {
        setIsLoading(false);
        // Re-focus input after response
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    },
    [isLoading, sessionId]
  );

  // Handle Enter key (Shift+Enter = new line, Enter = send)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend(input);
    }
  };

  // Clear chat — wipes UI messages and backend memory
  const handleClear = async () => {
    setMessages([WELCOME_MESSAGE]);
    setError(null);
    setInput("");
    await clearChat(sessionId).catch(() => {}); // Silently ignore if offline
  };

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* ----------------------------------------------------------------- */}
      {/* Sidebar                                                             */}
      {/* ----------------------------------------------------------------- */}
      <Sidebar onSuggest={(q) => handleSend(q)} />

      {/* ----------------------------------------------------------------- */}
      {/* Main chat area                                                      */}
      {/* ----------------------------------------------------------------- */}
      <main className="flex flex-col flex-1 overflow-hidden">

        {/* Top bar */}
        <header className="flex items-center justify-between px-6 py-3 bg-white border-b border-gray-200 shadow-sm flex-shrink-0">
          <div>
            <h2 className="text-sm font-semibold text-gray-800">
              Plastic Bag Survey — Data Chat
            </h2>
            <p className="text-xs text-gray-400">
              Ask questions in plain English · Answers calculated live
            </p>
          </div>

          {/* Clear chat button */}
          <button
            onClick={handleClear}
            disabled={isLoading}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-red-500 border border-gray-200 hover:border-red-300 rounded-lg px-3 py-1.5 transition-colors disabled:opacity-40"
          >
            {/* Trash icon */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
            >
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14H6L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4h6v2" />
            </svg>
            Clear chat
          </button>
        </header>

        {/* ---------------------------------------------------------------- */}
        {/* Messages list                                                      */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex-1 overflow-y-auto chat-scroll px-6 py-6 space-y-4">

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Typing indicator while AI is thinking */}
          {isLoading && <TypingIndicator />}

          {/* Error banner */}
          {error && (
            <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-700 msg-appear">
              <span className="text-base">⚠️</span>
              <div>
                <p className="font-medium">Error from the AI backend</p>
                <p className="text-red-600 mt-0.5 text-xs">{error}</p>
                <p className="text-red-500 mt-1 text-xs">
                  Make sure the backend is running and your .env is configured.
                </p>
              </div>
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={bottomRef} />
        </div>

        {/* ---------------------------------------------------------------- */}
        {/* Input bar                                                          */}
        {/* ---------------------------------------------------------------- */}
        <div className="flex-shrink-0 border-t border-gray-200 bg-white px-6 py-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend(input);
            }}
            className="flex items-end gap-3"
          >
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              placeholder="Ask anything about the survey data… (Enter to send)"
              className="flex-1 resize-none rounded-xl border border-gray-300 bg-gray-50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent disabled:opacity-50 placeholder-gray-400 max-h-40 leading-relaxed"
              style={{ minHeight: "48px" }}
              onInput={(e) => {
                // Auto-grow textarea
                const el = e.currentTarget;
                el.style.height = "auto";
                el.style.height = Math.min(el.scrollHeight, 160) + "px";
              }}
            />

            {/* Send button */}
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="flex-shrink-0 w-11 h-11 rounded-xl bg-brand-600 hover:bg-brand-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white flex items-center justify-center transition-colors shadow-sm"
              aria-label="Send message"
            >
              {isLoading ? (
                /* Spinner */
                <svg
                  className="w-4 h-4 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12" cy="12" r="10"
                    stroke="currentColor" strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 00-8 8h4z"
                  />
                </svg>
              ) : (
                /* Send arrow */
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth={2.5}
                >
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              )}
            </button>
          </form>

          <p className="text-center text-xs text-gray-400 mt-2">
            Answers are calculated live from your Google Sheet · Shift+Enter for new line
          </p>
        </div>
      </main>
    </div>
  );
}
