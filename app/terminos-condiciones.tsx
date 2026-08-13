// app/terminos-condiciones.tsx
import React, { useEffect } from "react";
import TermsScreen from "../mobile/screens/TermsScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <TermsScreen />;
}
