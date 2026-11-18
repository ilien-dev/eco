<p align="center"><a href="README.md">English</a> · <b>Español</b></p>

# Eco: investigación de palabras clave y SEO para tu README y tu sitio web

Eco es un skill para agentes de IA como Claude Code y Codex. Encuentra las palabras que la
gente escribe cuando busca lo que hace tu proyecto, las pone en el README o en el sitio donde
Google y la búsqueda de GitHub las leen, y comprueba el resultado con un script en vez de
fiarse de lo que dice el agente.

Trabaja sobre lo único que controlas: tu propio texto. Los enlaces desde otros sitios, la
antigüedad del dominio y las menciones externas quedan fuera de su alcance, y lo dice.

## Qué hace

1. **Lee el proyecto** (repo, documentación, sitio) y anota para quién es y cómo busca esa
   gente. Si el proyecto es tan de nicho que nadie lo busca por su nombre, busca los problemas
   y las alternativas más cercanas que la gente sí busca.
2. **Investiga palabras clave por idioma**: el autocompletado de Google, Bing y DuckDuckGo, la búsqueda de
   repositorios de GitHub (con la posición actual de tu repo) y las páginas y READMEs de la
   competencia.
3. **Arma un mapa de palabras clave**: primarias, secundarias, long-tail y descartadas, cada una
   con la investigación que la respalda y los lugares donde debe aparecer (título, meta
   descripción, H1, primer párrafo, encabezados, texto alternativo, preguntas frecuentes, About
   y topics de GitHub).
4. **Reescribe el texto** para que esas palabras queden donde cuentan, sin relleno y sin
   afirmaciones que el proyecto no pueda respaldar.
5. **Ofrece [Quirón](https://github.com/ilien-dev/quiron)**, un humanizador, para el texto
   nuevo. Puedes saltarlo; si no está instalado, Eco ofrece instalarlo.
6. **Comprueba que nada se rompió**: cada palabra clave, enlace interno y ancla sobrevive a la
   humanización. Si chocan, ganan las palabras clave.
7. **Entrega un informe** con el mismo formato cada vez.

## Medido, no descrito

`scripts/eco.py` (Python 3.9 o posterior, solo la biblioteca estándar) guarda cada paso en
`.eco/` y se niega a generar el informe hasta que cada comprobación pasa:

- la investigación tiene profundidad suficiente: respuestas no vacías de autocompletado de
  varias familias de búsquedas por idioma, competidores y búsquedas en GitHub;
- la evidencia de cada frase está de verdad en los archivos de la investigación;
- las palabras clave primarias están en sus lugares, sin alertas de relleno;
- la línea base es el texto original, guardado antes de cualquier cambio;
- el mapa de palabras clave no cambió entre la foto previa a la humanización y la final;
- nada se perdió tras la humanización, y el informe vuelve a auditar los archivos que describe.

## Instalación

```sh
npx skills add ilien-dev/eco
```

O, dentro de Claude Code, como plugin:

```
/plugin marketplace add ilien-dev/eco
/plugin install eco@eco
```

## Uso

Abre tu agente en el proyecto y pide:

```
/eco haz que este README aparezca cuando la gente busque lo que hace
```

Eco nunca hace commit, push ni cambia el About de GitHub por su cuenta. Los cambios fuera del
repo se proponen como un comando `gh repo edit` exacto.

## Por qué Eco

En la mitología griega, Eco era una ninfa que solo podía repetir las últimas palabras que decían
los demás. Ese es todo el trabajo: escuchar las palabras que usa la gente al buscar y hacer que
tu proyecto las repita. Como los demás proyectos del mismo autor, toma su nombre de la mitología.

## Límites

- Google Suggest muestra que la gente escribe una frase, no cuánta gente. Si tienes datos de
  Search Console o Trends, regístralos como evidencia y Eco los usa.
- La búsqueda de repositorios de GitHub lee por defecto el nombre, el About y los topics, no el
  README, y pesa mucho las estrellas. Eco propone el About y los topics; el nombre y las
  estrellas son tuyos.
- Versión 0.1.0: probado en cuatro proyectos por una sola persona, todos en Claude Code. Aún no
  se probaron la instalación interactiva de Quirón, un proyecto sin repo ni otros agentes.

## Licencia

MIT, ver [LICENSE](LICENSE).
