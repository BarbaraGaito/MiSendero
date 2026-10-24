# Auditoría de FIRED Argentina 2000–2024

## Qué encontramos

El repositorio público de FIREDpy enlaza un producto de perímetros para Argentina que cubre noviembre de 2000 a julio de 2024. El registro de CU Scholar identifica un archivo `argentina.zip` de 440.719.081 bytes y un DOI `10.25810/h8f7-bn68`. La ficha dice que incluye polígonos por evento y por día, generados con FIREDpy a partir del producto de área quemada MODIS MCD64A1 y parámetros de agrupación de un píxel y cinco días. La ficha DataCite del DOI declara licencia CC BY 4.0; la página del repositorio también incluye un campo genérico `In Copyright`, así que conviene conservar la atribución del DOI y aclarar la diferencia antes de redistribuir el archivo.

La misma tabla oficial de FIREDpy ofrece una versión anterior para Argentina, 2001–2021, además de la versión ampliada 2000–2024. La publicación metodológica documenta polígonos diarios y por evento. Probé también el enlace de la versión anterior: el registro `5t34sk58k` respondió HTTP 403. Es una variante temporalmente menor, no una fuente nueva de años recientes, y tampoco se pudo adquirir en esta sesión.

Es una fuente útil para agrupar detecciones satelitales en episodios y comparar eventos históricos con pronósticos GOES o meteorológicos. No es una confirmación de campo: hereda limitaciones del insumo MODIS MCD64A1 y su algoritmo de delineación. DataCite registra CC BY 4.0, mientras que la ficha muestra además un estado de derechos genérico `In Copyright`; debe citarse el DOI y aclararse esa diferencia antes de redistribuirlo.

## Prueba de acceso en esta sesión

Se pudo consultar la ficha y verificar título, cobertura, descripción, DOI, nombre y tamaño del archivo. La descarga del endpoint `/downloads/nc580p36j` respondió HTTP 403 tanto con `curl` como con una solicitud con referer; no quedó un archivo descargado. Por lo tanto, no se ejecutó el cruce espacial ni se añadieron casos al conjunto de evaluación. El bloqueo es del acceso al binario desde este entorno, no evidencia de que el enlace no exista.

La alternativa inmediatamente reproducible sigue siendo el tile mensual ESA FireCCI51 ya adquirido y cruzado con el parte SNMF de Mburucuyá de 2022. Ese cruce documenta una coincidencia espacial y temporal para un único episodio, no la precisión del predictor.

## Fuentes

- [Repositorio de FIREDpy y tabla de productos por país](https://github.com/earthlab/firedpy)
- [Versión Argentina 2001–2021 (enlace CU Scholar)](https://scholar.colorado.edu/concern/datasets/5t34sk58k)
- [Ficha FIRED Argentina 2000–2024 y descarga](https://scholar.colorado.edu/concern/datasets/td96k4315)
- [DOI del conjunto](https://doi.org/10.25810/h8f7-bn68)
- [Metadatos DataCite del DOI, con la licencia declarada](https://api.datacite.org/dois/10.25810/h8f7-bn68)
- [Artículo sobre perímetros nacionales FIRED 2001–2021](https://www.nature.com/articles/s41597-022-01572-3)
- [Producto MODIS MCD64A1 v6.1](https://lpdaac.usgs.gov/products/mcd64a1v061/)

## Próximo paso de validación

Si se consigue el ZIP mediante descarga manual autorizada o una vía alternativa oficial, comprobar el checksum publicado, revisar el acuerdo de uso y congelar antes del cruce una regla de distancia/tiempo con los eventos SNMF. Contar episodios únicos, mantener los fuegos fuera de cobertura como desconocidos y reportar por separado sensibilidad del evento, avisos sin coincidencia y precisión solo cuando exista una cohorte completa de ventanas positivas y negativas adjudicadas. El archivo por sí solo no permite certificar precisión ni adelanto de avisos.
