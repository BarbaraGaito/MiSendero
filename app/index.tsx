import { useEffect, useState } from "react";
import { router } from "expo-router";
import LoginScreen from "../mobile/screens/LoginScreen";
import SplashScreen01 from "../mobile/screens/initial-flow/SplashScreen01";
import { initDB } from "../database/database";
import { getAuthSession } from "../services/authSession";

export default function App() {
  const [showLogin, setShowLogin] = useState(false);
  const [startupError, setStartupError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let splashTimer: ReturnType<typeof setTimeout>;
    let startupTimer: ReturnType<typeof setTimeout>;
    setShowLogin(false);
    setStartupError(false);
    const startApp = async () => {
      const minimumSplashTime = new Promise((resolve) => {
        splashTimer = setTimeout(resolve, 1800);
      });

      const sessionPromise = async () => {
        await initDB();
        return getAuthSession();
      };

      const [, session] = await Promise.race([
        Promise.all([minimumSplashTime, sessionPromise()]),
        new Promise<never>((_, reject) => {
          startupTimer = setTimeout(() => reject(new Error("startup-timeout")), 20000);
        }),
      ]);
      if (!active) return;

      if (session) {
        router.replace("/inicio");
        return;
      }

      setShowLogin(true);
    };

    void startApp().catch(() => {
      if (active) setStartupError(true);
    }).finally(() => {
      clearTimeout(splashTimer);
      clearTimeout(startupTimer);
    });
    return () => {
      active = false;
      clearTimeout(splashTimer);
      clearTimeout(startupTimer);
    };
  }, [attempt]);

  if (showLogin) {
    return <LoginScreen />;
  }

  return <SplashScreen01 startupError={startupError} onRetry={() => setAttempt(value => value + 1)} />;
}
