"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import styles from "./public-site.module.css";

type ThemeMode = "carbon" | "classic-dark" | "classic-light";
type AccentColor = "green" | "gold" | "maroon" | "purple";
type ThemeSettings = { theme: ThemeMode; accent: AccentColor; setTheme: (theme: ThemeMode) => void; setAccent: (accent: AccentColor) => void };

const ThemeContext = createContext<ThemeSettings | null>(null);
const themes: { value: ThemeMode; label: string }[] = [
  { value: "carbon", label: "Carbon Black" },
  { value: "classic-dark", label: "Classic Dark" },
  { value: "classic-light", label: "Classic Light" },
];
const accents: { value: AccentColor; label: string }[] = [
  { value: "green", label: "Brand Green" },
  { value: "gold", label: "Gold" },
  { value: "maroon", label: "Maroon" },
  { value: "purple", label: "Purple" },
];

function isTheme(value: string | null): value is ThemeMode {
  return themes.some((theme) => theme.value === value);
}

function isAccent(value: string | null): value is AccentColor {
  return accents.some((accent) => accent.value === value);
}

export function PublicAppearance({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<ThemeMode>("carbon");
  const [accent, setAccent] = useState<AccentColor>("green");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const savedTheme = localStorage.getItem("gnk-theme");
        const savedAccent = localStorage.getItem("gnk-accent");
        if (isTheme(savedTheme)) setTheme(savedTheme);
        if (isAccent(savedAccent)) setAccent(savedAccent);
      } catch {
        // Keep the default theme when browser storage is unavailable.
      }
      setReady(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      localStorage.setItem("gnk-theme", theme);
      localStorage.setItem("gnk-accent", accent);
    } catch {
      // Theme changes still apply for this page when browser storage is unavailable.
    }
  }, [theme, accent, ready]);

  return <ThemeContext.Provider value={{ theme, accent, setTheme, setAccent }}><div className={styles.site} data-theme={theme} data-accent={accent}>{children}</div></ThemeContext.Provider>;
}

export function ThemeControls() {
  const settings = useContext(ThemeContext);
  if (!settings) return null;

  return (
    <div className="theme-controls" aria-label="Appearance settings">
      <label>
        <span>Theme</span>
        <select aria-label="Theme" value={settings.theme} onChange={(event) => settings.setTheme(event.target.value as ThemeMode)}>
          {themes.map((theme) => <option key={theme.value} value={theme.value}>{theme.label}</option>)}
        </select>
      </label>
      <label>
        <span>Accent</span>
        <select aria-label="Accent color" value={settings.accent} onChange={(event) => settings.setAccent(event.target.value as AccentColor)}>
          {accents.map((accent) => <option key={accent.value} value={accent.value}>{accent.label}</option>)}
        </select>
      </label>
    </div>
  );
}
