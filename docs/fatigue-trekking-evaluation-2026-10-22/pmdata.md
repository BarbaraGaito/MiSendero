# PMData: auditoría de actividades y etiquetas originales

Fecha: 22 de octubre de 2026. [Descripción de Simula](https://datasets.simula.no/pmdata/), [depósito original OSF](https://osf.io/vx4bk/), [artículo de los autores](https://doi.org/10.1145/3339825.3394926).

Se descargaron los **16 CSV originales `pmsys/srpe.csv`**, comprobando cada SHA-256 contra los metadatos oficiales de OSF. Se recorrieron todas las páginas de la API; no se tomó la primera página de diez participantes como conjunto completo. También se comprobó que el inventario contiene un `heart_rate.json` de Fitbit para cada participante, sin descargar esas series grandes. Los CSV y las respuestas de inventario están en `training/data/raw/pmdata-audit/`, excluidos de Git. [Auditoría reproducible y hashes](pmdata-activities-audit.json), [script](../../training/python/audit_pmdata_activities.py).

## Qué se encontró

- **16 participantes y 783 sesiones** en los archivos de esfuerzo.
- 772 sesiones tienen un valor original de esfuerzo entre 1 y 10; 11 tienen ese campo vacío.
- Las únicas etiquetas de actividad presentes son `individual`, `team`, `running`, `soccer`, `endurance` y `strength`. Una sesión puede tener varias etiquetas: sus recuentos no deben sumarse como deportes excluyentes.
- Hay 402 sesiones con etiqueta `running`, 257 con `endurance`, 170 con `strength` y 12 con `soccer`. Las combinaciones exactas por participante constan en el informe.
- **Ninguna sesión está identificada explícitamente como `walking`, `hiking` o `trekking`.** Las 11 sesiones de `p16` usan el literal `{}` como actividad; se conserva esa ausencia sin asignarles un deporte.

Esto no demuestra que nadie haya caminado durante los cinco meses. Significa que los archivos de respuesta no permiten identificar y reservar un conjunto de trekking etiquetado. Tampoco se puede convertir `endurance` en senderismo ni suponer que `running` ocurrió al aire libre.

## Por qué no se entrenó un detector de fatiga de trekking

El archivo `srpe.csv` contiene `end_date_time`, `activity_names`, `perceived_exertion` y `duration_min`. Su referencia describe el **esfuerzo de una sesión completada**; no ofrece una serie de evaluaciones de fatiga durante una excursión. La valoración diaria de fatiga en `wellness.csv` es otro resultado y no debe copiarse como etiqueta a todas las ventanas de pulso de ese día.

Aunque existen archivos de pulso de reloj, el inventario no comprueba todavía su cobertura, sincronización con las respuestas ni la ubicación de cada actividad. No se entrenó un modelo, no se rellenaron etiquetas faltantes ni se informó una precisión para trekking. PMData podría servir para otra pregunta sobre esfuerzo por sesión o bienestar diario; esta auditoría no autoriza esas cifras como detección de fatiga durante la marcha.

La página actual de Simula declara CC BY 4.0, pero el [archivo original `license.txt` de OSF](https://osf.io/download/ywdvx/) y el artículo declaran **CC BY-NC 4.0**. Se comprobó el texto de 266 bytes, SHA-256 `5286eaa9817ddf25ad61158793c91ca2d4097220160d9f4be678d29d8db260ba`. El informe registra esta discrepancia de procedencia; no presume que la mención más permisiva sustituya el archivo original.

Reproducción: `python training/python/audit_pmdata_activities.py`, solo biblioteca estándar de Python. La auditoría verifica los hashes, conserva los nombres originales de actividad y cuenta también las sesiones incompletas.
