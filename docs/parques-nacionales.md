# Fichas institucionales de Parques Nacionales

Cobertura verificada el 11/10/2026: once parques y quince senderos del catalogo.
Incluye Nahuel Huapi, Los Glaciares, Quebrada del Condorito, Lanin, Los Alerces,
El Palmar, Aconquija, Iguazu, Tierra del Fuego, Lihue Calel y Sierra de las
Quijadas. No se infiere pertenencia por provincia,
nombre o proximidad: las relaciones se definen explicitamente en
`backend/src/data/nationalParks.js` y se persisten mediante la migracion 007.

La ficha debe incluir fuentes institucionales verificadas para registro,
acceso, normas, pernocte, fuego y contacto. Cada resumen enlaza su fuente;
los formularios externos estan enlazados por esas instituciones. Se conserva
el mismo formato para todos, con informacion especifica por parque y sector.
Parques provinciales, senderos privados y Laguna Esmeralda no se vinculan.

## Acceso y almacenamiento

- Explorar -> Parques Nacionales -> ficha -> formulario o fuente oficial.
- Detalle del sendero: acceso debajo de Altimetria; las estadisticas no cambian.
- Antes de salir: recordatorio del requisito institucional y acceso a la ficha.
- API publica: `/api/national-parks` y `/api/national-parks/:slug`.
- `/api/trails` y `/api/trails/:id` incluyen `national_park` o `null`.
- Las fichas consultadas se guardan en SQLite. Los mapas descargados tambien
  contienen la ficha del parque; sin conexion se muestran como copias guardadas.
- Las descargas anteriores se actualizan al consultar el sendero con conexion,
  incluso cuando guardaron `national_park: null`, conservando la geometria
  descargada si coincide con la actual.

## Modalidades de registro

- Online: Nahuel Huapi, Los Glaciares, Quebrada del Condorito y Lanin. Lanin
  enlaza el sistema de ascenso al volcan, no un formulario para otra actividad.
- Presencial obligatorio: Namuncura y Cerro Alto en el Centro de Visitantes
  de Lihue Calel; Guanacos en la Oficina de Informes de Sierra de las Quijadas.
- Consulta de requisitos: los restantes recorridos. No se publica un formulario
  inventado ni se extiende a ellos la obligatoriedad documentada para otra senda.
- `registration_by_trail` permite requisitos distintos dentro del mismo parque.
  El detalle y la pantalla previa al inicio seleccionan la entrada del sendero.
- Los contactos sin telefono institucional publicado muestran solo correo.

Las temporadas de Tierra del Fuego corresponden a Costera/Hito XXIV y a sus
campamentos publicados, no a una habilitacion en tiempo real. El pernocte de
Aconquija distingue Campo de los Alisos del itinerario en Portal Cochuna.
Sierra de las Quijadas enlaza el aviso oficial de pernocte no operativo y
Lihue Calel la informacion de reserva anticipada de La Ruta Natural.

## Limites de verificacion

Las fichas son resenas documentadas, no datos institucionales en tiempo real.
Recargar la API no cambia la fecha de revision de las fuentes. Despues de
30 dias se muestra un aviso de reconfirmacion de requisitos.

No hay integracion automatica de avisos de cierres ni alertas del SMN en esta
implementacion. `live_status` los declara `not_integrated`; la habilitacion
actual permanece sin verificar. Los botones abren el sitio del parque y
el portal del SMN para la consulta real. Nunca se deduce "abierto" o "sin
alertas" de una lista vacia, un reporte comunitario o del clima Open-Meteo.

El formulario se completa fuera de MiSendero. Abrirlo no comprueba envio,
aceptacion ni permiso. La app no recibe respuestas ni guarda datos de ese
registro. En Los Glaciares se distingue la obligatoriedad de mayo a septiembre
y las actividades en areas remotas; el formulario publicado corresponde a
uso de montana en areas remotas, por lo que para miradores fuera de invierno
se indica consultar al Centro de Visitantes. Las reglas de fuego corresponden
a Zona Norte, no se generalizan al sector sur.

El aviso al contacto de emergencia sigue siendo independiente y obligatorio.
No se agrego un bloqueo de inicio basado en abrir un formulario o en un
estado institucional que no esta verificado.

Para ampliar la cobertura, revisar las fuentes primarias de cada sector y
actividad, agregar la ficha completa y los nombres exactos de los senderos,
actualizar `checked_at`, ejecutar tests y luego migracion/seed. No publicar
alertas historicas como actuales ni mantener una prohibicion temporal sin
verificar su vigencia.
