import { useEffect, useState } from "react";
import { router } from "expo-router";
import LoginScreen from "../mobile/screens/LoginScreen";
import SplashScreen01 from "../mobile/screens/initial-flow/SplashScreen01";
import { initDB } from "../database/database";
import { getAuthSession } from "../services/authSession";

export default function App() {
  const [showLogin, setShowLogin] = useState(false);

  useEffect(() => {
    const startApp = async () => {
      const minimumSplashTime = new Promise((resolve) => {
        setTimeout(resolve, 1800);
      });

      const sessionPromise = async () => {
        await initDB();
        return getAuthSession();
      };

      const [, session] = await Promise.all([
        minimumSplashTime,
        sessionPromise(),
      ]);

      if (session) {
        router.replace("/inicio");
        return;
      }

      setShowLogin(true);
    };

    startApp();
  }, []);

  if (showLogin) {
    return <LoginScreen />;
  }

  return <SplashScreen01 />;
}
