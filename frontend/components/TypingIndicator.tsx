/**
 * Animated three-dot typing indicator shown while the AI is calculating.
 */
export default function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 msg-appear">
      {/* AI Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center text-white text-xs font-bold shadow-sm">
        AI
      </div>

      {/* Bubble */}
      <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm dark:bg-gray-900 dark:border-gray-700">
        <div className="flex items-center gap-1.5 h-5">
          <span className="w-2 h-2 rounded-full bg-brand-500 dot-bounce" />
          <span className="w-2 h-2 rounded-full bg-brand-500 dot-bounce" />
          <span className="w-2 h-2 rounded-full bg-brand-500 dot-bounce" />
        </div>
      </div>
    </div>
  );
}
