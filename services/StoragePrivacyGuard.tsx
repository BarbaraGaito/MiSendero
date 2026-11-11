import { PropsWithChildren, useEffect, useState } from "react";
import { AppState, Modal, Text, View } from "react-native";
import { suspendProtectedStorage, resumeProtectedStorage } from "../database/connection";

export function StoragePrivacyGuard({children}: PropsWithChildren) {
  const [covered,setCovered]=useState(AppState.currentState !== 'active');
  const [error,setError]=useState(false);
  useEffect(() => {
    let mounted=true;
    const change=(state:typeof AppState.currentState) => {
      if (state !== 'active') {
        setCovered(true);
        void suspendProtectedStorage().catch(() => { if(mounted) setError(true); });
      } else {
        void resumeProtectedStorage().then(() => { if(mounted && AppState.currentState === 'active') {setCovered(false);setError(false);} }).catch(() => {if(mounted)setError(true);});
      }
    };
    change(AppState.currentState);
    const listener=AppState.addEventListener('change',change);
    return () => {mounted=false;listener.remove();};
  },[]);
  return <>{children}<Modal visible={covered} animationType="none" onRequestClose={()=>{}}>
    <View style={{flex:1,backgroundColor:'#F7FAF7',alignItems:'center',justifyContent:'center',padding:24}}>
      <Text accessibilityRole="header">MiSendero</Text>
      <Text>{error ? 'No se pudo liberar el almacenamiento protegido. Cerrá y volvé a abrir la app con el equipo desbloqueado.' : 'Volvé a la app con el equipo desbloqueado para consultar tus datos.'}</Text>
    </View>
  </Modal></>;
}
