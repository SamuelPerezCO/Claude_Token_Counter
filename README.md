**Español** · [English](README.en.md)

# Claude Token Counter

Un medidor local de uso para Claude Code. Ejecuta el `.exe`, escanea el código QR
que imprime en la consola y consulta desde tu celular cuánto has usado de tu
límite de sesión y de tu límite semanal.

Inspirado en [Clawdmeter](https://github.com/HermannBjorgvin/Clawdmeter), que
muestra las mismas cifras en una pantalla ESP32 de escritorio. Este proyecto
reemplaza el hardware por un pequeño servidor web local, así que sirve cualquier
dispositivo con navegador.

```
  Claude Code Usage Meter v1.0.0
  polling Anthropic every 60s

  On this computer:  http://localhost:8765
  On your phone:     http://192.168.1.10:8765

  Phone must be on the same Wi-Fi network.

  Scan to open on your phone:

  █▀▀▀▀▀▀▀█ ▀▀█▀██▀███▀▀▀▀▀▀▀█
  █ █▀▀▀█ █ █   ██▀▀▀ █ █▀▀▀█ █
  ...
```

## Cómo funciona

La API de Claude no tiene un endpoint de uso. Las cifras viajan en las
**cabeceras de respuesta** de cualquier petición común, así que esta aplicación:

1. Lee tu token OAuth de Claude Code desde `~/.claude/.credentials.json`
2. Envía la petición más pequeña posible a `POST /v1/messages`
   (`claude-haiku-4-5`, `max_tokens: 1`, cuerpo `"hi"`) y descarta la respuesta
3. Interpreta las cabeceras de límite de uso que llegaron:

| Cabecera | Significado |
|---|---|
| `anthropic-ratelimit-unified-status` | `allowed` / `allowed_warning` / `rejected` |
| `anthropic-ratelimit-unified-5h-utilization` | uso de la sesión, como fracción (`0.21` = 21%) |
| `anthropic-ratelimit-unified-5h-reset` | reinicio de la sesión, en segundos Unix |
| `anthropic-ratelimit-unified-7d-utilization` | uso semanal, como fracción |
| `anthropic-ratelimit-unified-7d-reset` | reinicio semanal, en segundos Unix |
| `anthropic-ratelimit-unified-overage-utilization` | uso excedente, si tu plan lo tiene |
| `anthropic-ratelimit-unified-representative-claim` | qué ventana te está limitando ahora |

La autenticación usa `Authorization: Bearer <token>` más la cabecera
`anthropic-beta: oauth-2025-04-20`. Un token OAuth **no** funciona como
`x-api-key`.

**Costo:** cada consulta gasta ~8 tokens de entrada y 1 de salida en Haiku. Con el
intervalo por defecto de 60 segundos es un error de redondeo, pero no es
literalmente cero, y la petición de sondeo cuenta dentro de los mismos límites que
reporta.

## Cómo ejecutarlo

El `.exe` compilado **no** está en este repositorio: los binarios no van en git,
así que `dist/` está ignorado. Eso significa que `build_exe.ps1` por sí solo no
hace nada, porque es un script de compilación y compila el código fuente que está
junto a él. De cualquier forma necesitas el repositorio completo.

### Compilar el .exe (requiere Python una sola vez)

```powershell
git clone https://github.com/SamuelPerezCO/Claude_Token_Counter.git
cd Claude_Token_Counter
.\build_exe.ps1          # genera dist\claude-meter.exe
.\dist\claude-meter.exe
```

Python solo hace falta para *compilar*. El ejecutable resultante es autónomo, así
que el equipo donde se ejecute no necesita tener nada instalado.

### O ejecutarlo directamente desde el código fuente

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m claude_meter
```

### Compartirlo con otra persona

Envíale únicamente el `dist\claude-meter.exe` ya compilado: no tiene
dependencias. Vale la pena advertirle dos cosas:

- **Windows SmartScreen mostrará una advertencia la primera vez.** El ejecutable
  no está firmado, así que Windows muestra *"Windows protegió su PC"* hasta que
  haga clic en **Más información → Ejecutar de todas formas**. Quitar esa
  advertencia exige un certificado de firma de código de pago.
- **Lee las credenciales de quien lo ejecuta, no las tuyas.** El binario no lleva
  ningún token incrustado. Quien lo ejecute verá *su* propio uso, tomado de *su*
  `~/.claude/.credentials.json`, y necesita haber iniciado sesión en Claude Code
  al menos una vez para que funcione.

### Opciones

| Parámetro | Por defecto | Notas |
|---|---|---|
| `--port N` | `8765` | Cámbialo si otro programa ya ocupa el puerto |
| `--host ADDR` | `0.0.0.0` | Usa `127.0.0.1` para dejarlo fuera de la red |
| `--interval N` | `60` | Segundos entre consultas |
| `--open` | apagado | Abre el panel en tu navegador al iniciar |
| `--no-qr` | apagado | Omite el código QR |
| `--verbose` | apagado | Registra cada petición HTTP |

## Requisitos previos

Debes haber iniciado sesión en Claude Code al menos una vez, para que exista
`~/.claude/.credentials.json`. Si el token ya venció, ejecuta `claude` una vez
para renovarlo: esta aplicación deliberadamente nunca renueva ni escribe en ese
archivo.

Si el archivo está en una ubicación distinta, apunta `CLAUDE_CREDENTIALS_PATH`
hacia él.

## Nota sobre la exposición en red

Por defecto se enlaza a `0.0.0.0`, que es justamente lo que permite el acceso
desde el celular. Eso significa que **cualquier persona en tu red local puede
abrir el panel**. No hay autenticación.

Lo que esa persona vería: tus porcentajes de uso y las horas de reinicio. Lo que
no puede obtener: tu token OAuth, que nunca sale del proceso local y nunca se
incluye en ninguna respuesta HTTP. Aun así, en una red que no controlas
(cafetería, coworking, hotel), ejecútalo con `--host 127.0.0.1` y úsalo solo en
ese equipo.

## Endpoints

| Ruta | Propósito |
|---|---|
| `/` | El panel |
| `/api/usage` | Estado actual en JSON |
| `/api/refresh` | Pide una consulta inmediata |
| `/healthz` | Verificación de que sigue vivo |

## El panel

Diseñado con la paleta de Claude: superficies crema cálidas, acento naranja y la
tipografía Styrene/Tiempos. Tres decisiones de diseño que vale la pena explicar,
porque ninguna fue arbitraria:

- **El acento es `#cc785c`, no `#d97757`.** El naranja de Claude más conocido
  mide 2.96:1 de contraste contra la superficie crema, apenas por debajo del
  mínimo de 3:1 para legibilidad; el tono "book cloth" sí lo supera. El modo
  oscuro usa `#d97757`, que sí cumple contra la superficie oscura.
- **Todas las cifras van en sans, aunque los títulos sean serif.** Styrene y
  Tiempos son tipografías con licencia comercial y no se pueden incrustar, así
  que se declaran primero en la pila de fuentes con alternativas de respaldo.
  Georgia, la alternativa más probable a Tiempos, usa cifras de estilo antiguo en
  las que el 3, 4, 5, 7 y 9 bajan de la línea base, lo que haría que un
  porcentaje grande se viera desalineado.
- **El estado nunca depende solo del color.** El verde de "Allowed" y el rojo de
  "Rate limited" son casi idénticos bajo deuteranopía (ΔE 4.1), así que la
  etiqueta de estado siempre lleva un ícono *y* una palabra.

El uso se muestra con barras de medición y no con gráficos de aguja o de torta,
porque el dato es una sola proporción contra un límite, que es justo para lo que
sirve una barra de medición.

## Estructura

```
claude_meter/
  __main__.py      CLI, mensaje de inicio, código QR
  credentials.py   ubica y lee el token OAuth
  usage.py         la petición de sondeo, el análisis de cabeceras y el hilo de consulta
  server.py        el servidor HTTP
  netinfo.py       detección de IP en la red local, generación del QR
  static/
    index.html     el panel (un solo archivo, sin paso de compilación)
```

El panel consulta `/api/usage` cada 5 segundos, pero eso solo lee un estado ya
guardado en tu equipo: a Anthropic se le consulta según el temporizador de
`--interval`, no en cada carga de página. Las cuentas regresivas avanzan en el
navegador y se corrigen contra el reloj del equipo servidor, así que siguen
siendo correctas incluso si la hora de tu celular está desajustada.
