# Auditoria de partes SNMF sin incendios reportados

Se revisaron 633 PDF oficiales archivados. Un dia se acepta como negativo del **registro de incendios reportados** solo si el hash del PDF coincide con el manifiesto, el texto contiene la frase exacta "No se reportaron incendios en el territorio nacional", la fecha impresa coincide con la fecha archivada y el extractor no encuentra eventos en ese parte.

El criterio verifico **32 dias** (256 registros fecha-sector para los ocho sectores) en 2023: 4, 2024: 27, 2025: 1. Los archivos con fecha interna distinta, conflicto con eventos parseados o sin texto legible se conservan como desconocidos.

Esto permite contar negativos mas solidos para el objetivo "incendio cercano reportado por SNMF". No demuestra ausencia fisica de fuego, no da hora de ignicion y no permite afirmar precision de un predictor por si solo. Las fechas pueden incluir ocho sectores del mismo dia, pero no son ocho observaciones independientes de incendio.

La lista detallada, hashes, URL de cada PDF y regla de clasificacion estan en [el JSON reproducible](fire-snmf-national-no-fire-report-audit.json). Se reproduce con [`audit_snmf_national_no_fire_reports.py`](../../training/python/audit_snmf_national_no_fire_reports.py).
