"use client";

import { useEffect, useState } from "react";

type ThemeMode = "light" | "dark" | "system";

const STORAGE_KEY = "theme-preference";

function getSystemTheme(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(mode: ThemeMode) {
  const root = document.documentElement;
  const resolved = mode === "system" ? getSystemTheme() : mode;
  root.classList.toggle("dark", resolved === "dark");
  root.setAttribute("data-theme", mode);
}

export default function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeMode>("system");

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    const initial: ThemeMode = saved === "light" || saved === "dark" || saved === "system"
      ? saved
      : "system";

    setTheme(initial);
    applyTheme(initial);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");

    const onSystemChange = () => {
      if (theme === "system") {
        applyTheme("system");
      }
    };

    media.addEventListener("change", onSystemChange);
    return () => media.removeEventListener("change", onSystemChange);
  }, [theme]);

  const onChange = (nextTheme: ThemeMode) => {
    setTheme(nextTheme);
    localStorage.setItem(STORAGE_KEY, nextTheme);
    applyTheme(nextTheme);
  };

  return (
    <label className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-300">
      <span className="hidden sm:inline">Theme</span>
      <select
        value={theme}
        onChange={(e) => onChange(e.target.value as ThemeMode)}
        className="rounded-md border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 outline-none transition-colors focus:ring-2 focus:ring-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100"
        aria-label="Theme mode"
      >
        <option value="light">Light</option>
        <option value="dark">Dark</option>
        <option value="system">System</option>
      </select>
    </label>
  );
}
