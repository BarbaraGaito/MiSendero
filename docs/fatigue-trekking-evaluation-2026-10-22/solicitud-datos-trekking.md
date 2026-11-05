# Solicitud preparada de datos individuales de trekking

Fuente: [Koshimizu et al., 2026](https://www.frontiersin.org/journals/sports-and-active-living/articles/10.3389/fspor.2025.1669574/full). El artículo describe 20 participantes, una subida real, pulso, esfuerzo percibido y fatiga muscular; indica que los datos brutos pueden ser facilitados por los autores. **No se envió ningún mensaje ni se obtuvo todavía este conjunto de datos.**

Texto propuesto para el autor de correspondencia:

> Subject: Request for de-identified participant-level data from the trekking-pole hiking study
>
> Dear Dr. Koshimizu,
>
> I am conducting a computer-science thesis on evaluating wearable-based estimates of exertion and fatigue during hiking. Your study, “Adaptive gait transition in trekking pole-assisted hiking due to fatigue and staircase height elevation,” is particularly relevant because it recorded heart rate, perceived exertion, and muscle fatigue along a real uphill trail. The article states that raw data can be made available by the authors.
>
> Would you be able to share a de-identified table with one row per participant and recording spot containing: a stable anonymous participant ID; the recording spot or route phase; elapsed minutes since the start of the hike or timestamps sufficient to derive it; the 10-second heart-rate value or trace; the original RPE and muscle-fatigue ratings; the exact scale wording and scoring for each rating; and missing-value indicators? A short description of when the ratings were taken relative to the HR segment would help us avoid using future information. If any fields are unavailable, the available original fields would still be useful to audit.
>
> Please also let me know the permitted research uses, citation, and whether the de-identified data may be redistributed with the thesis or only analyzed locally. We would cite your article and data as you specify.
>
> Thank you for considering this request.

Antes de usar cualquier archivo recibido, verificar que las filas correspondan a mediciones reales, que pulso y respuesta se puedan emparejar sin ambigüedad, que haya IDs para separar personas y que la licencia permita el uso de tesis. Con respuestas de fatiga muscular se evaluaría o entrenaría un **modelo de fatiga muscular**; las predicciones Borg de esfuerzo del modelo actual solo se compararían con una escala compatible y documentada. Un conjunto de 20 personas permitiría una prueba exploratoria, con incertidumbre considerable y sin garantizar generalización a otros senderos.
