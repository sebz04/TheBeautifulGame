import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Match from "./pages/Match";
import MatchPicker from "./pages/MatchPicker";

export default function App() {
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
