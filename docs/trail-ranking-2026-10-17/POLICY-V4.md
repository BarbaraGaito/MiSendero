# Recomendación con alternativas: política v4

Revisión del 17/10/2026. Se cambió el código local; no se modificó AWS, RDS, credenciales ni el entorno de producción.

## Comportamiento

La ubicación es obligatoria. Si hay fichas utilizables en ese destino, se devuelve un único sendero aunque cambien tiempo, dificultad o paisaje. Se prioriza la experiencia del perfil; si ninguna opción cumple ese nivel, se conserva el nivel menos exigente disponible y se advierte que lo supera. Dentro de ese grupo se priorizan coincidencias exactas y luego paisaje, tiempo y dificultad. Ni el modelo ni el fallback pueden elegir otra ciudad.

La tarjeta muestra **«Te sugerimos una alternativa en este destino»**, explica que no encontró una coincidencia exacta y detalla las diferencias reales. No se alteran atributos para simular coincidencia. No se agrega chat ni se vuelve a preguntar la experiencia.

Se conservan los aliases y calificadores geográficos. Un nombre ambiguo o posiblemente mal escrito pide aclaración; no se cambia silenciosamente a otra ciudad.

## Catálogo utilizable

La base local tiene 51 fichas. Antes solo se admitían 34; se excluían diez fichas antiguas sin procedencia y siete con estimaciones o referencias de tiempo no reconocidas. Ahora participan las **51**, preservando sus limitaciones:

- 41 tienen fuentes estructuradas admitidas; 10 se identifican como `catalogVerification: catalog_only`, fuentes vacías y `checkedAt: null`, con aviso de documentación pendiente.
- En 11 no está confirmado si el tiempo incluye el regreso. No se afirma coincidencia con un tiempo total. Proximidad y minutos se mantienen nulos en sus vectores del modelo. El tipo de itinerario desconocido se indica como `unknown`.
- Se admiten las estimaciones documentadas, identificándolas como tales.
- Se interpretan formatos existentes como `4 a 5 h`, `30 a 45 min` y `1 h 30 min a 2 h`.

Siguen rechazándose datos esenciales inválidos, fuentes suministradas no admitidas, distancias no positivas y duraciones ininterpretables. No se inventan atributos para garantizar resultados. La garantía de alternativa se aplica a solicitudes válidas y destinos reconocidos con fichas utilizables; errores de red, autenticación, alcance o ambigüedad conservan su tratamiento.

## Entrenamiento

Se regeneró el dataset y se ejecutó el entrenamiento de scikit-learn. Resultado: **cero valoraciones etiquetadas, `insufficient_real_data`, `trained: false`, métricas nulas y ningún modelo de producción**. Ver [el informe](policy-v4-training-status.json).

El catálogo aporta características, no etiquetas de preferencia personal. No se generaron valoraciones ficticias ni se presentó el fallback como ML entrenado. La selección flexible ya funciona con la referencia determinista. El pipeline está listo para etiquetas reales consentidas de usuarios o expertos; exige volver a preparar y evaluar con la política v4. Los artefactos anteriores se rechazan por versión/hash. El contrato de etiquetas y los mínimos están en [la documentación de ML](../../backend/ml/README.md).

## Validación

- Backend completo: 20 suites / 221 pruebas aprobadas.
- Encuesta y servicio móvil: 38 pruebas aprobadas.
- Python: 7 pruebas aprobadas. El ajuste sintético solo comprueba el pipeline en directorios temporales, sin modelo de producción ni evidencia de precisión.
- TypeScript de app y backend: aprobado.
- [Cobertura funcional local](policy-v4-coverage.json): **19.152 combinaciones**, 504 por cada una de 38 ubicaciones, cero listas vacías y cero salidas del destino. Esto prueba comportamiento del software, no precisión real del modelo. Estas consultas no son etiquetas de entrenamiento.
- HTTP autenticado con PostgreSQL local: consulta principal y tres búsquedas incompatibles en Bariloche, Mendoza y Neuquén devolvieron registros reales en el destino. Cero escrituras de base de datos.

```powershell
npm --prefix backend test -- --runInBand
npm test -- --runInBand DiscoverTrailScreen trailAssistant
npm run typecheck
py -m unittest discover -s backend/ml/tests -v
npm --prefix backend run ranking:coverage
npm --prefix backend run ranking:smoke
npm --prefix backend run ranking:prepare
py backend/ml/train.py --catalog training/data/trail-ranking/catalog.json --prepared training/data/trail-ranking/prepared --output backend/ml/artifacts/OTRA-VERSION
```

Sin etiquetas el último comando termina con código 2 y guarda el estado sin artefacto. Los comandos locales de cobertura y smoke rechazan RDS.

## Archivos principales

`backend/src/ai/`: selección, referencias, contrato, características y explicaciones. `backend/ml/ranking.py`: referencia Python consistente. `backend/scripts/prepareTrailRanking.js`, `auditRecommendationCoverage.js` y `smokeTrailRanking.js`: datos y verificación. `mobile/components/TrailRecommendationCard.tsx` y `services/trailAssistant.ts`: cartel y contrato móvil. Se actualizaron sus pruebas, el snapshot y la documentación.

## Actualizar AWS y Expo

El paquete **`recomendador-flexible-v4-20261017.tar.gz`** contiene el código del recomendador, los scripts y Python. No contiene secretos, dependencias, modelos sintéticos, seeds ni migraciones. La corrección anterior de fotos/mapas tiene su paquete separado.

Desde PowerShell, usar la clave y usuario habituales:

```powershell
scp -i "C:\RUTA\TU-CLAVE.pem" .\recomendador-flexible-v4-20261017.tar.gz USUARIO_EC2@18.218.87.168:~/
ssh -i "C:\RUTA\TU-CLAVE.pem" USUARIO_EC2@18.218.87.168
```

En EC2:

```bash
sudo systemctl show misendero.service -p WorkingDirectory -p EnvironmentFiles
cd /RUTA/REAL/DEL/BACKEND
tar -czf ~/recomendador-antes-v4.tar.gz src/ai src/routes/ai.routes.js dist/ai tsconfig.ai.json
tar -xzf ~/recomendador-flexible-v4-20261017.tar.gz
npm run build
sudo systemctl restart misendero.service
sudo systemctl is-active misendero.service
sudo journalctl -u misendero.service -n 40 --no-pager
```

Reiniciar **solo si la compilación pasó**. Si falta una carpeta de respaldo, revisar la versión instalada antes de extraer. No cambiar Nginx, conexión RDS o variables de entorno. Python no es obligatorio para el fallback.

Actualizar también el cliente: versiones anteriores pueden rechazar fichas `catalog_only`/`unknown`. Desde el código local actualizado:

```powershell
npx expo start --clear
```

Se conserva la URL de AWS. Probar Bariloche con cascadas y menos de una hora; Mendoza con lago y dificultad fácil; y un destino sin registros. Los primeros deben devolver opciones locales con el cartel de diferencias; el último no debe sustituirse por otra ciudad.

Si falla el despliegue, restaurar `~/recomendador-antes-v4.tar.gz` dentro del backend y reiniciar el servicio. No ejecutar seeds, migraciones ni restauraciones de RDS para revertir este cambio. No se agregaron variables de entorno ni APIs pagas.
