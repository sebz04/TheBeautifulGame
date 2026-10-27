import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { setLang } from "./i18n/i18n";
import Match from "./pages/Match";
import MatchPicker from "./pages/MatchPicker";
import { useStore } from "./state/store";

export default function App() {
  const lang = useStore((s) => s.prefs.lang);
  useEffect(() => setLang(lang), [lang]);
  return (
    <BrowserRouter>
      <Routes>
        {/* The welcome page arrives in TASK-23.7; until then the start is the match list. */}
        <Route path="/" element={<Navigate to="/matches" replace />} />
        <Route path="/matches" element={<MatchPicker />} />
        <Route path="/match/:id" element={<Match />} />
        <Route path="*" element={<Navigate to="/matches" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
