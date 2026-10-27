import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { setLang } from "./i18n/i18n";
import Match from "./pages/Match";
import MatchPicker from "./pages/MatchPicker";
import Welcome from "./pages/Welcome";
import { useStore } from "./state/store";

export default function App() {
  const lang = useStore((s) => s.prefs.lang);
  useEffect(() => setLang(lang), [lang]);
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/welcome" element={<Welcome forceSetup />} />
        <Route path="/matches" element={<MatchPicker />} />
        <Route path="/match/:id" element={<Match />} />
        <Route path="*" element={<Navigate to="/matches" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
