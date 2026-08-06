import React, { useEffect } from "react";
import OfflineMapsSearchScreen from "../mobile/screens/OfflineMapsSearchScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <OfflineMapsSearchScreen />;
}