/**
 * A single chat message bubble.
 * User messages appear on the right (green), AI messages on the left (white).
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface Props {
  message: Message;
}

function normalizeMessageContent(content: string): string {
  let text = content;

  // Convert HTML line breaks/tags to plain readable text.
  text = text.replace(/<br\s*\/?>/gi, "\n");
  text = text.replace(/<\/(p|div|li|tr|h1|h2|h3|h4|h5|h6)>/gi, "\n");
  text = text.replace(/<[^>]+>/g, "");

  // Normalize odd spacing chars that often appear in LLM output.
  text = text
    .replace(/[\u00A0\u202F\u2007]/g, " ")
    .replace(/[\u200B\u200C\u200D\uFEFF]/g, "");

  // Convert common math-like tokens to simpler readable text.
  text = text.replace(/\\times/g, "*");
  text = text.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, "($1)/($2)");

  // If model wraps formula in [ ... ], show it as plain text block.
  text = text.replace(/\[\s*((?:.|\n)*?\\frac(?:.|\n)*?)\s*\]/g, "$1");

  // Collapse over-spaced output while keeping paragraph breaks readable.
  text = text.replace(/[ \t]+\n/g, "\n");
  text = text.replace(/\n{3,}/g, "\n\n");

  return text.trim();
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const content = isUser ? message.content : normalizeMessageContent(message.content);

  return (
    <div
      className={`flex items-end gap-2 msg-appear ${
        isUser ? "flex-row-reverse" : "flex-row"
      }`}
    >
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shadow-sm ${
          isUser
            ? "bg-gray-700 text-white"
            : "bg-brand-600 text-white"
        }`}
      >
        {isUser ? "You" : "AI"}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl shadow-sm text-sm leading-relaxed ${
          isUser
            ? "bg-brand-600 text-white rounded-br-sm"
            : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm dark:bg-gray-900 dark:border-gray-700 dark:text-gray-100"
        }`}
      >
        <div className="chat-markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
