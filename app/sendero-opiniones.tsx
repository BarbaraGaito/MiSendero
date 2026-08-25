import React, { useEffect } from "react";
import { initDB } from "../database/database";
import TrailReviewsScreen from "../mobile/screens/TrailReviewsScreen";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <TrailReviewsScreen />;
}
