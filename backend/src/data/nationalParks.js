// Only explicitly reviewed national-park trails are eligible. Geography or a
// matching word in a location is not evidence of park membership.
const checkedAt = "2026-10-11";
const glaciares = "https://www.argentina.gob.ar/parquesnacionales/patagonia-austral";
const condorito = "https://www.argentina.gob.ar/parquesnacionales/centro/parque-nacional-quebrada-del-condorito";
const nh = "https://nahuelhuapi.gov.ar";
const apn = "https://www.argentina.gob.ar/parquesnacionales";
const lanin = `${apn}/regionpatagonia/parque-nacional-lanin`;
const alerces = `${apn}/regionpatagonia/parque-nacional-los-alerces`;
const palmar = `${apn}/centro/parque-nacional-el-palmar`;
const aconquija = `${apn}/region-noroeste/parque-nacional-aconquija`;
const iguazu = `${apn}/nea/parque-nacional-iguazu`;
const fuego = `${apn}/patagonia-austral/parque-nacional-tierra-del-fuego`;
const fuegoSendas = `${apn}/patagonia-austral/senderos-del-parque-nacional-tierra-del-fuego`;
const lihue = `${apn}/regionpatagonia/parque-nacional-lihue-calel`;
const quijadas = `${apn}/centro/parque-nacional-sierra-de-las-quijadas`;
const recommendations = `${apn}/recomendaciones-para-tu-visita`;
const parks = [
  {
    slug: "nahuel-huapi", name: "Parque Nacional Nahuel Huapi", provinces: ["Rio Negro", "Neuquen"],
    scope: "Sendero a Refugio Frey desde Villa Catedral", checked_at: checkedAt,
    website_url: `${nh}/`, notices_url: `${nh}/`,
    registration: {
      requirement: "always", required_months: [],
      summary: "Registro de trekking obligatorio y gratuito antes de la caminata. La inscripcion no reemplaza consultar si el sendero esta habilitado.",
      form_url: "https://forms.gle/sGNVrn7DmpEjfmNf9",
      source_url: `${nh}/registros-trekking-escalada-esqui-travesia/`,
    },
    access: { text: "Consultar a informes o guardaparques sobre actividades autorizadas y estado del sendero; reprogramar ante mal tiempo o cierres.", source_url: `${nh}/recomendaciones-y-seguridad/` },
    rules: { items: ["Circular por sendas marcadas y regresar con todos los residuos.", "No ingresar con mascotas, usar drones ni fumar."], source_url: `${nh}/recomendaciones-y-seguridad/` },
    overnight: { text: "Acampar solo en lugares habilitados y senalizados. Consultar disponibilidad y condiciones del refugio antes de planificar una noche; el registro de trekking no reserva alojamiento.", source_url: `${nh}/camping-y-alojamiento/`, booking_url: null },
    fire: { text: "Prohibido hacer fuego fuera de campings organizados. No hacer fogones en el sendero ni en la montana; consultar restricciones vigentes antes de usar un calentador.", source_url: `${nh}/2026/01/12/seccional-gutierrez-un-area-muy-visitada-que-requiere-compromiso-y-cuidado-de-todos/` },
    contact: { name: "Informes del Parque", phone: "+542944423111", email: "informesnh@apn.gob.ar", source_url: `${nh}/registros-trekking-escalada-esqui-travesia/` },
    weather_area: "Zona cordillerana de Bariloche y alrededores del Cerro Catedral, Rio Negro.",
    trails: ["Refugio Frey desde Villa Catedral"],
  },
  {
    slug: "los-glaciares", name: "Parque Nacional Los Glaciares", provinces: ["Santa Cruz"],
    scope: "Zona Norte: miradores de los Condores y las Aguilas, El Chalten", checked_at: checkedAt,
    website_url: `${glaciares}/parque-nacional-los-glaciares`, notices_url: `${glaciares}/parque-nacional-los-glaciares`,
    registration: {
      requirement: "seasonal", required_months: [5, 6, 7, 8, 9],
      summary: "Para recorrer senderos, el registro es obligatorio de mayo a septiembre. Escalada y trekking en areas remotas requieren registro tambien fuera de esa temporada. Para estos miradores fuera de invierno, consultar al Centro de Visitantes si corresponde el formulario de areas remotas o un registro presencial.",
      form_url: "https://docs.google.com/forms/d/e/1FAIpQLSfP8lEz5ry97gEK6fzx2mlu1NAhPwBx8cRlnSZOH8mx8iUMHA/viewform",
      source_url: `${glaciares}/parque-nacional-los-glaciares/actividades`,
    },
    access: { text: "Consultar el estado de las sendas antes de salir. Entre mayo y septiembre pueden presentar hielo, barro y nieve; APN exige bastones y crampones en temporada invernal.", source_url: `${glaciares}/recomendaciones-para-visitar-el-parque-nacional-los-glaciares` },
    rules: { items: ["Caminar solo por senderos habilitados y regresar antes de que oscurezca.", "No ingresar con mascotas ni usar drones. Retirar todos los residuos.", "No caminar ni patinar sobre lagunas congeladas."], source_url: `${glaciares}/recomendaciones-para-visitar-el-parque-nacional-los-glaciares` },
    overnight: { text: "En Zona Norte, los campamentos De Agostini, Capri y Poincenot requieren reserva. No son areas de acampe de estos miradores; consultar al parque antes de cambiar el itinerario.", source_url: `${glaciares}/recomendaciones-para-visitar-el-parque-nacional-los-glaciares`, booking_url: "https://amigospnlosglaciares.org/" },
    fire: { text: "Zona Norte: prohibido hacer fuego. Solo se admiten calentadores a gas en areas de acampe habilitadas y bajo supervision.", source_url: `${glaciares}/recomendaciones-para-visitar-el-parque-nacional-los-glaciares` },
    contact: { name: "Centro de Visitantes Ceferino Fonzo", phone: "+542962493004", email: "informeszonanorte@apn.gob.ar", source_url: `${glaciares}/parque-nacional-los-glaciares/actividades` },
    weather_area: "Zona cordillerana de El Chalten, Santa Cruz. Seleccionar el area de la salida en el mapa del SMN.",
    trails: ["Mirador de los Condores - El Chalten", "Mirador de las Aguilas - El Chalten"],
  },
  {
    slug: "quebrada-del-condorito", name: "Parque Nacional Quebrada del Condorito", provinces: ["Cordoba"],
    scope: "Sector Noreste: Balcon Norte desde La Pampilla", checked_at: checkedAt,
    website_url: `${condorito}`, notices_url: "https://quebradadelcondorito.com.ar/",
    registration: {
      requirement: "always", required_months: [],
      summary: "Registro previo obligatorio y gratuito para visitantes del sector Noreste. Sin guia: un responsable registra el vehiculo y sus acompanantes; en omnibus, hasta seis personas. Si vas con guia habilitado, el registro lo realiza el prestador: no duplicarlo.",
      form_url: "https://forms.gle/6dRTLT7HLXU9dpwn9",
      source_url: "https://quebradadelcondorito.com.ar/registros/",
    },
    access: { text: "Tranquera: octubre a marzo, 8 a 20 h; abril a septiembre, 9 a 18 h. El horario general no garantiza ingreso al Balcon Norte ni habilitacion del sendero. Confirmar el horario limite de ese recorrido y el estado de la RP34 antes de viajar.", source_url: `${condorito}/horarios-como-llegar` },
    rules: { items: ["No ingresar con mascotas ni usar drones. Retirar los residuos.", "No nadar en el Rio de los Condoritos ni salir de sendas habilitadas.", "Balcon Sur: acceso solo con guia habilitado; no confundir con esta ruta al Balcon Norte."], source_url: "https://quebradadelcondorito.com.ar/horarios-acceso-el-parque-nacional-quebrada-del-condorito/" },
    overnight: { text: "La Canada: acampe agreste sin servicios, con permiso adicional al registro de ingreso. Ingreso para acampar hasta las 16 h. La Trinidad requiere consulta especial y presencia de guardaparques; Rodolfo Gimenez y San Miguel, guia o prestador habilitado.", source_url: `${condorito}/alojamiento`, booking_url: "https://forms.gle/Kh9wpP8s5bJMDfmg8" },
    fire: { text: "Prohibido hacer fuego en todo el parque. Cocinar solo con calentadores portatiles homologados; llevar calentador es obligatorio para pernoctar.", source_url: "https://quebradadelcondorito.com.ar/horarios-acceso-el-parque-nacional-quebrada-del-condorito/" },
    contact: { name: "Intendencia (consultas administrativas)", phone: "+543541532153", email: "quebradadelcondorito@apn.gob.ar", source_url: `${condorito}` },
    weather_area: "Pampa de Achala, sierras altas de Cordoba; no utilizar solo el pronostico de la ciudad de Cordoba.",
    trails: ["Quebrada del Condorito - Balcon Norte"],
  },
  {
    slug: "lanin", name: "Parque Nacional Lanin", provinces: ["Neuquen"],
    scope: "Sector Tromen: Volcan Lanin, base a Refugio BIM", checked_at: checkedAt,
    website_url: lanin, notices_url: "https://www.pnlanin.com.ar/",
    registration: {
      requirement: "always", mode: "online", required_months: [],
      summary: "Registro previo obligatorio. El parque publica un registro especifico para el ascenso al volcan Lanin. Antes de subir al Refugio BIM, confirmar con guardaparques la modalidad, el equipo exigido y los horarios para ese tramo; registrarse no garantiza habilitacion ni una plaza en el refugio.",
      form_url: "https://www.qsistemas.com.ar/lanin/", source_url: "https://www.pnlanin.com.ar/",
    },
    access: { text: "Consultar el estado del acceso por Tromen y del tramo a refugios antes de viajar. La caminata al BIM no habilita continuar a la cumbre.", source_url: `${lanin}/actividades` },
    rules: { items: ["Seguir la senda sin atajos y respetar las indicaciones de guardaparques.", "En terreno montanoso, circular con precaucion por posibles desprendimientos de roca."], source_url: "https://www.pnlanin.com.ar/Recomendaciones.php" },
    overnight: { text: "Hay campamentos y refugios en el parque. Coordinar disponibilidad y condiciones del BIM antes de planificar una noche; el registro de ascenso no reserva alojamiento.", source_url: `${lanin}/alojamiento`, booking_url: null },
    fire: { text: "Los fogones solo pueden usarse donde el parque lo autorice. Confirmar las restricciones de Tromen y del refugio antes de cocinar.", source_url: `${lanin}/alojamiento` },
    contact: { name: "Informes del Parque", phone: "+542972427233", email: "informeslanin@apn.gob.ar", source_url: lanin },
    weather_area: "Sector Tromen y volcan Lanin, zona cordillerana de Neuquen.",
    trails: ["Volcan Lanin - Base a Refugio BIM"],
  },
  {
    slug: "los-alerces", name: "Parque Nacional Los Alerces", provinces: ["Chubut"],
    scope: "Pasarela del Rio Arrayanes, Lahuan Solitario y Puerto Chucao", checked_at: checkedAt,
    website_url: alerces, notices_url: alerces,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "Consultar en el Centro de Informes o con guardaparques las condiciones del Lahuan Solitario y Puerto Chucao. El registro obligatorio se aplica a las sendas que lo requieren; confirmar si corresponde para la actividad y el itinerario elegido.",
      form_url: null, source_url: `${alerces}/actividades`,
    },
    access: { text: "El Lahuan Solitario se recorre desde la pasarela del Rio Arrayanes. Consultar habilitacion de la senda y acceso al sector antes de salir.", source_url: `${alerces}/actividades` },
    rules: { items: ["Respetar la carteleria y caminar por las sendas habilitadas.", "Planificar el regreso con luz natural, sin tomar atajos."], source_url: `${recommendations}/senderismo` },
    overnight: { text: "En Lago Verde hay campamentos organizados y agrestes. Consultar disponibilidad y servicios con el prestador antes de viajar; no instalar una carpa en la senda a Puerto Chucao.", source_url: `${alerces}/alojamiento`, booking_url: null },
    fire: { text: "Fuego solo en sectores autorizados, sujeto a restricciones vigentes. Consultar al parque antes de usar fogones o calentadores.", source_url: `${recommendations}/fuego` },
    contact: { name: "Uso Publico del Parque", phone: "+5492945548973", email: "usopublicolosalerces@apn.gob.ar", source_url: `${alerces}/actividades` },
    weather_area: "Lago Verde, Rio Arrayanes y Puerto Chucao, cordillera de Chubut.",
    trails: ["Lahuan Solitario - Puerto Chucao"],
  },
  {
    slug: "el-palmar", name: "Parque Nacional El Palmar", provinces: ["Entre Rios"],
    scope: "Sendero El Mollar, junto al camping del parque", checked_at: checkedAt,
    website_url: palmar, notices_url: palmar,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "El Mollar es un sendero junto al camping. Consultar sus condiciones en el Centro de Visitantes. El registro obligatorio publicado para el Sendero de la Selva corresponde a otro recorrido; confirmar los requisitos antes de cambiar el itinerario.",
      form_url: null, source_url: `${palmar}/actividades`,
    },
    access: { text: "El Mollar se encuentra junto al camping. Consultar horarios de ingreso y estado del sendero antes de visitar el parque.", source_url: `${palmar}/actividades` },
    rules: { items: ["El Mollar permite conocer el manejo de especies exoticas: respetar la carteleria y las tareas de conservacion.", "No circular en bicicleta por senderos peatonales ni por areas de valor historico."], source_url: `${palmar}/actividades` },
    overnight: { text: "Camping organizado dentro del parque, con sanitarios y servicios. Consultar tarifas, disponibilidad y reservas con el camping antes de planificar el pernocte.", source_url: `${palmar}/alojamiento`, booking_url: null },
    fire: { text: "Parrillas y fogones habilitados en Camping El Palmar. Confirmar disponibilidad y restricciones antes de utilizarlos; no hacer fuego en el sendero.", source_url: `${palmar}/actividades` },
    contact: { name: "Intendencia del Parque", phone: null, email: "elpalmar@apn.gob.ar", source_url: palmar },
    weather_area: "Ubajay y Parque Nacional El Palmar, Entre Rios.",
    trails: ["Sendero El Mollar - El Palmar"],
  },
  {
    slug: "aconquija", name: "Parque Nacional Aconquija", provinces: ["Tucuman"],
    scope: "Portal Cochuna: Laguna del Tesoro", checked_at: checkedAt,
    website_url: aconquija, notices_url: aconquija,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "Antes de recorrer Laguna del Tesoro, consultar al parque los requisitos de registro, la habilitacion de la senda y la necesidad de guia para la salida prevista. Si se contrata un guia, elegir uno habilitado por el parque.",
      form_url: null, source_url: `${aconquija}/actividades`,
    },
    access: { text: "El sendero comienza detras del estacionamiento del Portal Cochuna y cruza varios arroyos. Consultar las condiciones de los cruces antes de iniciar, especialmente despues de lluvias.", source_url: `${aconquija}/actividades` },
    rules: { items: ["Seguir la senda habilitada y respetar la carteleria.", "Calcular ida y regreso con luz natural; no tomar atajos."], source_url: `${recommendations}/senderismo` },
    overnight: { text: "APN publica camping Santa Rosa y La Mesada en Portal Campo de los Alisos, no en este itinerario de Cochuna. Para pernoctar en la salida a Laguna del Tesoro, consultar previamente lugares autorizados y requisitos con el parque.", source_url: `${aconquija}/alojamiento`, booking_url: null },
    fire: { text: "Fuego solo en sitios habilitados y con autorizacion vigente. Consultar especificamente las restricciones de Portal Cochuna antes de cocinar.", source_url: `${recommendations}/fuego` },
    contact: { name: "Informacion al Visitante", phone: "+5493865358562", email: "aconquija@apn.gob.ar", source_url: aconquija },
    weather_area: "Portal Cochuna y Laguna del Tesoro, zona montanosa de Tucuman.",
    trails: ["Laguna del Tesoro - Aconquija"],
  },
  {
    slug: "iguazu", name: "Parque Nacional Iguazu", provinces: ["Misiones"],
    scope: "Sendero Macuco y Salto Arrechea", checked_at: checkedAt,
    website_url: iguazu, notices_url: iguazu,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "Solicitar en el Centro de Visitantes la informacion y el folleto del Macuco. Confirmar las condiciones de ingreso y si corresponde registro para la salida prevista; la entrada al parque no sustituye otros permisos de actividad.",
      form_url: null, source_url: `${iguazu}/actividades`,
    },
    access: { text: "El Macuco es peatonal y agreste. Consultar su habilitacion y horario de ingreso antes de recorrerlo; los horarios generales de Cataratas no garantizan acceso a esta senda.", source_url: `${iguazu}/actividades` },
    rules: { items: ["Recorrer el Macuco unicamente a pie.", "Seguir las precauciones sobre fauna silvestre del folleto especifico entregado en el Centro de Visitantes."], source_url: `${iguazu}/actividades` },
    overnight: { text: "La oferta publicada dentro del parque es el hotel Gran Melia. Los campings y otros alojamientos se encuentran en Puerto Iguazu; no planificar acampe sobre el Sendero Macuco.", source_url: `${iguazu}/alojamiento`, booking_url: null },
    fire: { text: "No hacer fogones en el Macuco. El uso de fuego se limita a sitios expresamente autorizados y depende de las restricciones del parque.", source_url: `${recommendations}/fuego` },
    contact: { name: "Informes del Parque", phone: "+543757420722", email: "iguazu@apn.gob.ar", source_url: `${iguazu}/contacto` },
    weather_area: "Puerto Iguazu y Parque Nacional Iguazu, norte de Misiones.",
    trails: ["Sendero Macuco - Salto Arrechea"],
  },
  {
    slug: "tierra-del-fuego", name: "Parque Nacional Tierra del Fuego", provinces: ["Tierra del Fuego"],
    scope: "Senda Costera y Lago Acigami - Hito XXIV", checked_at: checkedAt,
    website_url: fuego, notices_url: fuego,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "Consultar con guardaparques los requisitos de la Senda Costera o Hito XXIV y confirmar su habilitacion. Los permisos de otras actividades o senderos no sustituyen la consulta sobre el recorrido elegido.",
      form_url: null, source_url: fuegoSendas,
    },
    access: { text: "APN publica temporada de noviembre a abril para ambas sendas. Costera parte de Ensenada Zaratiegui; Hito XXIV parte del estacionamiento de Acigami. Confirmar estado y condiciones actuales antes de viajar.", source_url: fuegoSendas },
    rules: { items: ["Respetar las cabeceras y la senalizacion de la senda elegida.", "Hito XXIV comparte el inicio con Cerro Guanaco: continuar por la bifurcacion hacia la costa del lago, sin confundir los recorridos."], source_url: fuegoSendas },
    overnight: { text: "Campamentos gratuitos en Rio Pipo, Ensenada y Laguna Verde/Cauquenes, disponibles de noviembre a abril. APN indica que no requieren reserva previa y que se ocupan por orden de llegada; reconfirmar disponibilidad. Acampar solo en lugares autorizados.", source_url: `${fuego}/alojamiento`, booking_url: null },
    fire: { text: "No encender fuego en las sendas. Consultar a guardaparques que fogones estan autorizados y las restricciones por peligro de incendio.", source_url: `${recommendations}/fuego` },
    contact: { name: "Intendencia del Parque", phone: "+542901577931", email: "tierradelfuego@apn.gob.ar", source_url: fuego },
    weather_area: "Ushuaia, costa del canal Beagle y Lago Acigami, Tierra del Fuego.",
    trails: ["Senda Costera - Tierra del Fuego", "Lago Acigami - Hito XXIV"],
  },
  {
    slug: "lihue-calel", name: "Parque Nacional Lihue Calel", provinces: ["La Pampa"],
    scope: "Sendero Namuncura y ascenso al Cerro Alto", checked_at: checkedAt,
    website_url: lihue, notices_url: lihue,
    registration: {
      requirement: "always", mode: "in_person", required_months: [],
      summary: "Todos los senderos requieren registro obligatorio presencial en el Centro de Visitantes del parque. Registrarse antes de iniciar Namuncura o continuar hacia Cerro Alto y confirmar las condiciones del recorrido.",
      form_url: null, source_url: `${lihue}/actividades`,
    },
    access: { text: "Namuncura comienza en el area de acampe y conecta con el ascenso a Cerro Alto. Informarse en el Centro de Visitantes sobre horarios y estado de ambas sendas.", source_url: `${lihue}/actividades` },
    rules: { items: ["Respetar la senalizacion y recorrer solo sendas habilitadas.", "Planificar el retorno con luz natural, sin tomar atajos."], source_url: `${recommendations}/senderismo` },
    overnight: { text: "Hay area de camping y sector para casas rodantes con banos y duchas. La Ruta Natural indica reservar el lugar con anticipacion: coordinar con el parque y reconfirmar disponibilidad antes de viajar.", source_url: "https://www.larutanatural.gob.ar/es/imperdible/32/parque-nacional-lihue-calel", booking_url: null },
    fire: { text: "Fuego solo en sitios habilitados y segun restricciones vigentes. Confirmar autorizacion del fogon con el parque antes de usarlo.", source_url: `${recommendations}/fuego` },
    contact: { name: "Intendencia del Parque", phone: "+542952416213", email: "lihuecalel@apn.gob.ar", source_url: lihue },
    weather_area: "Sierras de Lihue Calel y sector de RN152, La Pampa.",
    trails: ["Sendero Namuncura", "Cerro Alto desde Namuncura"],
  },
  {
    slug: "sierra-de-las-quijadas", name: "Parque Nacional Sierra de las Quijadas", provinces: ["San Luis"],
    scope: "Senderos Miradores y Guanacos", checked_at: checkedAt,
    website_url: quijadas, notices_url: quijadas,
    registration: {
      requirement: "consult", mode: "consult", required_months: [],
      summary: "Los requisitos dependen de la senda: Guanacos requiere registro previo presencial en la Oficina de Informes del acceso. Miradores es autoguiado; consultar sus horarios y condiciones antes de ingresar.",
      form_url: null, source_url: `${quijadas}/actividades`,
    },
    registration_by_trail: {
      "Sendero Guanacos - Sierra de las Quijadas": {
        requirement: "always", mode: "in_person", required_months: [],
        summary: "Registro previo obligatorio en la Oficina de Informes, en el acceso al parque. Guanacos es un trekking agreste autoguiado; confirmar los horarios de inicio y regreso de la temporada antes de salir.",
        form_url: null, source_url: `${quijadas}/actividades`,
      },
      "Miradores de Sierra de las Quijadas": {
        requirement: "consult", mode: "consult", required_months: [],
        summary: "Miradores es el sendero autoguiado principal. Consultar en Informes los horarios y las condiciones de ingreso; el registro previo publicado para Guanacos corresponde a otro recorrido.",
        form_url: null, source_url: `${quijadas}/actividades`,
      },
    },
    access: { text: "Los horarios de trekking cambian segun la epoca del ano. Confirmar en Informes los limites de ingreso y regreso de Miradores o Guanacos, especialmente en verano.", source_url: `${quijadas}/actividades` },
    rules: { items: ["Respetar sendas, carteleria y horarios indicados.", "Recorrer con luz natural y sin atajos."], source_url: `${recommendations}/senderismo` },
    overnight: { text: "La ficha de vehiculos recreativos de APN informa que el parque esta sin pernocte operativo. Consultar al parque antes de planificar una noche y prever alojamiento fuera del area protegida.", source_url: "https://www.argentina.gob.ar/node/439097", booking_url: null },
    fire: { text: "Fuego solo en lugares habilitados y bajo las restricciones vigentes. La presencia de fogones no implica autorizacion para usarlos.", source_url: `${recommendations}/fuego` },
    contact: { name: "Intendencia del Parque", phone: "+542664732762", email: "sierradelasquijadas@apn.gob.ar", source_url: quijadas },
    weather_area: "Hualtaran y Sierra de las Quijadas, noroeste de San Luis.",
    trails: ["Miradores de Sierra de las Quijadas", "Sendero Guanacos - Sierra de las Quijadas"],
  },
];

module.exports = parks;
