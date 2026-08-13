// app/onboarding-experiencia.tsx
import React, { useEffect } from "react";
import ExperienceOnboardingScreen from "../mobile/screens/ExperienceOnboardingScreen";
import { initDB } from "../database/database";

export default function App() {
  useEffect(() => {
    initDB();
  }, []);

  return <ExperienceOnboardingScreen />;
}
