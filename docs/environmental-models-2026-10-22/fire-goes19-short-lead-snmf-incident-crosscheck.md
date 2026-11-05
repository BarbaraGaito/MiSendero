# Cruce de alertas GOES de 1 hora con partes SNMF

Con el corte diagn?stico 0,5 aparecieron 8 episodios de alerta en enero de 2026. Al cruzar sus intervalos contra partes SNMF de fechas ?1 d?a, 5 episodios encontraron incidentes reportados dentro de 10 km y 7 dentro de 20 km. Esos episodios correspondieron a 1 incidentes ?nicos a 10 km y 2 a 20 km; por lo tanto, los episodios repetidos no son fuegos independientes.

Los episodios sin reporte cercano son [8]. Se describen como no emparejados; la falta de un parte pr?ximo no confirma ausencia f?sica de fuego. El informe diario no contiene la hora de ignici?n y no demuestra que la alerta haya precedido al inicio del incendio.

Este cruce no estima precisi?n porque la cobertura SNMF es incompleta y la cohorte fue seleccionada por las alertas del modelo. El resultado GOES a nivel de ruta-hora tampoco equivale a detecci?n de incendio f?sico. Ver [JSON reproducible con distancias, incidentes e hashes](fire-goes19-short-lead-snmf-incident-crosscheck.json) y [evaluaci?n por horizonte](fire-goes19-short-lead-route-sector-evaluation.md).

Reproducci?n: [`audit_goes_short_lead_snmf_incidents.py`](../../training/python/audit_goes_short_lead_snmf_incidents.py). Fuentes: [reportes diarios SNMF](https://www.argentina.gob.ar/servicio-nacional-de-manejo-del-fuego) y geometr?as completas privadas del cat?logo local.
