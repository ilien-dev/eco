# Eco · guía de uso del logotipo

## La idea

Eco era una oréade, una ninfa de los montes. Hera la condenó a repetir solo las últimas palabras que oía, y cuando se consumió por Narciso quedó únicamente su voz entre las rocas. El símbolo es esa montaña: dos picos con una cueva y, dentro, un arco que repite al de fuera. Es la voz que vuelve, igual que Eco devuelve en tu texto las palabras que la gente busca.

## Piezas

| Archivo | Uso |
|---|---|
| `eco-symbol-tile.svg` | Marca a color para fondos claros: símbolo en tinta sobre un cuadrado lima |
| `eco-symbol-tile-small.svg` | La misma, con el corte pequeño, para menos de 32 px (favicon) |
| `eco-symbol.svg` | Símbolo en lima, para fondos oscuros, de 32 px en adelante |
| `eco-symbol-small.svg` | Corte para tamaños pequeños (menos de 32 px): sin el arco interior y con la cueva algo mayor |
| `eco-horizontal.svg` | Logotipo horizontal para fondos claros (cuadrado lima + palabra): cabeceras, README, web |
| `eco-stacked.svg` | Logotipo apilado para fondos claros: espacios cuadrados, portadas |
| `eco-wordmark.svg` | Solo la palabra, cuando el símbolo ya aparece cerca |
| `lockups/*-on-dark.svg` | Versiones a color para fondos oscuros: símbolo lima y palabra en papel |
| `lockups/*-black.svg`, `*-white.svg`, `*-mono-c4f03a.svg` | Versiones a una tinta |
| `symbol/` | Símbolo en negro, blanco, lima, tinta, cuadrado, favicon e icono de app. `eco-symbol-square.svg`, `eco-symbol-favicon.svg` y `eco-symbol-mono-c4f03a.svg` son lima sobre transparente: solo para fondos oscuros. Para la pestaña del navegador se usa `web/favicon.svg` (el cuadrado lima) |
| `web/` | `favicon.ico`, `favicon.svg`, PNG de 16 a 512 px, `site.webmanifest` y `head-snippet.html` |
| `presentation.html` | Presentación con maquetas (README, terminal, web, icono, pegatina, perfil social) |
| `source/` | Scripts que generan todo lo anterior (`build.py`, `web_icons.py`) |

La palabra se escribe en minúsculas, «eco». Las letras están dibujadas a medida como trazados, no con una fuente: los extremos de la c y de la e se cortan con la misma inclinación que las laderas de la montaña.

## Colores

| Nombre | HEX | RGB | Uso |
|---|---|---|---|
| Lima | `#C4F03A` | 196 240 58 | Color de marca: el cuadrado de la marca, el símbolo sobre fondo oscuro, superficies del informe |
| Lima oscuro | `#4A6600` | 74 102 0 | Solo texto pequeño y líneas sobre fondo claro; nunca el logotipo |
| Tinta | `#151515` | 21 21 21 | Palabra, textos, símbolo dentro del cuadrado, fondos oscuros |
| Papel | `#F4F4F2` | 244 244 242 | Fondos claros, palabra sobre fondo oscuro |
| Gris | `#E8E8E6` | 232 232 230 | Fondo del informe en tema claro |

Son los colores del informe HTML de eco (estructura «Mapa»), que es donde más se ve la marca. El informe añade dos acentos solo para gráficos, siempre con forma y etiqueta: violeta `#6D5BFF` (`#9C8FFF` en oscuro) para las palabras de apoyo y naranja `#FF5F0F` para las frases largas.

Contrastes: tinta sobre lima 13,8:1; lima sobre tinta 12,9:1; lima oscuro sobre papel 6,0:1. El lima sobre blanco o papel se queda en 1,1:1: por eso en fondos claros el lima nunca es trazo ni texto, solo superficie. No hay equivalencia Pantone comprobada; si hace falta imprimir, pide una prueba de color.

## Espacio libre y tamaños mínimos

- **Unidad u:** la mitad del ancho de la cueva (el 19 % del ancho de la montaña).
- **Espacio libre:** como mínimo u alrededor de cualquier versión. En el logotipo horizontal, la separación entre símbolo y palabra también es u.
- **Mínimos:** símbolo, 16 px usando el corte pequeño (el principal, desde 32 px); horizontal, 96 px de ancho en pantalla y 25 mm impreso; apilado, 48 px de ancho.

## Fondos

- Blanco, papel o gris: la versión con cuadrado lima (`eco-horizontal.svg`, `eco-stacked.svg`, `eco-symbol-tile.svg`).
- Tinta o cualquier fondo oscuro: `*-on-dark.svg` (lima y papel) o la versión blanca.
- Lima: solo la versión en tinta (`symbol/eco-symbol-mono-151515.svg`), sin cuadrado.
- Fotografía: solo a una tinta, y únicamente sobre una zona tranquila de la imagen.

## Lo que no hay que hacer

- Cambiar las proporciones entre símbolo y palabra, o la distancia entre ellos.
- Estirar, girar, inclinar o añadir sombras, contornos o degradados.
- Usar otro color que no esté en la paleta, o poner el símbolo en lima directamente sobre un fondo claro.
- Escribir la palabra con una fuente en lugar de usar el trazado.
- Usar el símbolo principal por debajo de 32 px (hay que usar el corte pequeño).
- Usar el lima oscuro para el logotipo: es solo para texto y líneas.

## Pendiente

- Búsqueda de marcas registradas: no está hecha. Antes de usarlo en público conviene revisar bases de datos de marcas y hacer una búsqueda inversa de imágenes; los símbolos de montaña son frecuentes.
- La versión blanca no está adelgazada: sobre fondo oscuro se ve un poco más pesada. Para usos críticos conviene un ajuste a mano.
- Los iconos de app usan el corte pequeño.
- El lima queda cerca del verde que suele asociarse a la ecología. Lo separan el tono ácido y la tinta, pero conviene tenerlo presente.
- Muy pequeño, el símbolo puede leerse como una M.
- Hay otras marcas de desarrollo con dos picos (Nuxt, Code Climate). Puestas una al lado de la otra se distinguen por la cueva, la base maciza y el color, pero conviene tenerlo presente.
- En la presentación, la maqueta de terminal (`eco --version`, `Eco 1.0.0`, `eco search`) y el usuario `@eco` son textos de relleno de la plantilla, no comandos ni cuentas reales.

Para regenerarlo todo: `LOGO_SKILL=<carpeta del skill logo-design> CHROME=<ruta a chrome.exe> python source/export_all.py`.
