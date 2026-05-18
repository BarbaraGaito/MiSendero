import React, { useEffect } from "react";
import HomeScreen from "../mobile/screens/HomeScreen";
import { initDB } from "../database/database";

export default function App() {

  useEffect(() => {
    initDB();
  }, []);

  return <HomeScreen />;
}