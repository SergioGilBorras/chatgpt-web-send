# chatgpt-web-send

Versión del paquete: **0.1.2** (diagnóstico del navegador, ventana de tamaño nativo, descargas y acceso manual a la sesión habitual).

Paquete Python y CLI para **enviar prompts a conversaciones existentes de ChatGPT** desde un navegador donde el usuario inicia sesión. Se centra en el envío: **no lee el historial, mensajes anteriores ni respuestas**.

> Proyecto no oficial: automatiza la web de ChatGPT con Playwright, no usa la API de OpenAI. Los cambios de la interfaz pueden romper el funcionamiento y la automatización está sujeta a las condiciones de uso aplicables. No evita verificaciones, CAPTCHAs ni controles de acceso.

## Requisitos

- Python 3.10 o posterior.
- Cuenta de ChatGPT, accesible en el navegador.
- Chromium instalado con Playwright. Opcionalmente, Chrome o Edge ya instalados.

## Instalación

Desde el repositorio:

    git clone https://github.com/SergioGilBorras/chatgpt-web-send.git
    cd chatgpt-web-send
    python -m pip install -e .
    python -m playwright install chromium

## Dos modos de navegador: tu sesión habitual o automatización

**Modo manual, navegador habitual:** abre el Chrome, Edge u otro navegador que tengas configurado como predeterminado, **con tu perfil personal existente**, sus marcadores, historial, descargas y sesión ya iniciada. No usa Playwright ni lee la conversación; tendrás que escribir o pegar y enviar el mensaje tú mismo.

```powershell
chatgpt-web-send open
chatgpt-web-send open --conversation-id "TU_ID"
```

**Modo automatizado:** utiliza Playwright para insertar y enviar el texto en el editor, con Chrome/Edge real si lo seleccionas. La ventana tiene **tamaño nativo** (sin viewport artificial de 1280 × 900), permite descargas y las exporta a tu carpeta **Descargas** (o la indicada con `--downloads-dir`) para que permanezcan después de cerrar el navegador. El navegador almacena historial, favoritos y cookies en su **perfil propio persistente**. No comparte por defecto la sesión ni el historial del navegador personal, y eso es deliberado.

**Por qué no mezclar ambos perfiles:** Chrome 136+ y Playwright no admiten automatizar directamente el directorio de datos principal del navegador. Intentarlo puede hacer que Chrome falle al arrancar o que el perfil se bloquee. El paquete rechaza expresamente `--profile-dir` si apunta al perfil predeterminado de Chrome o Edge. No copias ni transfieras cookies o perfiles entre navegadores.

### Comprobar Edge o Chrome antes de enviar

```powershell
# Diagnóstico: arranca Edge y muestra su User-Agent REAL y el perfil utilizado.
chatgpt-web-send doctor --browser-channel msedge --keep-open

# Después utiliza el MISMO canal para autenticarte y enviar.
chatgpt-web-send login --browser-channel msedge
chatgpt-web-send send --browser-channel msedge --conversation-id "TU_ID" --prompt "Prueba" --keep-open
```

Para Chrome cambia `msedge` por `chrome`. El diagnóstico muestra el canal elegido, el User-Agent que comunica el navegador y las rutas de perfil y descargas. **Si Edge no está instalado o no arranca, aparecerá un error antes de enviar contenido.** No se modifica ni falsifica el User-Agent.

## 1. Inicio de sesión

    chatgpt-web-send login

Se abre Chromium. **Inicia sesión manualmente en la ventana** y después **pulsa Enter en la terminal**. El perfil local de Chromium conservará la sesión para futuros envíos. El paquete no pide credenciales ni lee cookies.

Perfil predeterminado con Chromium: **~/.chatgpt-web-send/profile**. Puede cambiarse mediante **--profile-dir RUTA** o **CHATGPT_WEB_SEND_PROFILE_DIR**.

### Compatibilidad: Chrome o Edge realmente instalados

Playwright permite ejecutar Google Chrome o Microsoft Edge **con sus propios binarios y User-Agent reales**, sin falsificar cabeceras ni esconder la automatización. Esta opción sirve para comprobar compatibilidad de navegador y **no garantiza solucionar el CAPTCHA**.

```powershell
chatgpt-web-send login --browser-channel msedge
chatgpt-web-send send --browser-channel msedge --conversation-id "TU_ID" --prompt "Prueba ficticia" --keep-open
```

También admite `--browser-channel chrome` si tienes Google Chrome instalado. Usa **el mismo canal** al iniciar sesión y al enviar. Se utilizan perfiles de sesión persistentes separados para no modificar el perfil Chromium anterior: `~/.chatgpt-web-send/profile-msedge` y `~/.chatgpt-web-send/profile-chrome`. Si proporcionas un `--profile-dir` manual, utiliza un directorio independiente por navegador y no lo abras simultáneamente en otra aplicación.

Cuando una aplicación crea `ChatGPTWeb()` directamente (por ejemplo un host Python), puede seleccionar el navegador mediante `CHATGPT_WEB_SEND_BROWSER_CHANNEL=msedge` o `chrome` antes de arrancar. En PowerShell: `$env:CHATGPT_WEB_SEND_BROWSER_CHANNEL = "msedge"`. Para futuras sesiones de Windows: `setx CHATGPT_WEB_SEND_BROWSER_CHANNEL msedge` y reinicia la aplicación. **Un instalador de Betterbird empaquetado previamente con PyInstaller no recibe automáticamente el código actualizado:** necesitará reconstruirse y publicarse después de integrar esta mejora.

El inicio de sesión es manual. Si ChatGPT sigue solicitando verificación humana, la herramienta se detiene; no intenta saltarse ni reintentar ese control.


**Importante:** ese directorio contiene datos sensibles de sesión. No lo subas nunca a Git, no lo compartas y no ejecutes dos procesos que utilicen el mismo perfil a la vez. Playwright utiliza un perfil propio, no reutiliza automáticamente la sesión de tu navegador habitual.

## 2. Enviar un prompt

De una URL de conversación como esta:

    https://chatgpt.com/c/67f12345-aaaa-bbbb-cccc-123456789abc

copia **solo el ID** (la parte después de /c/). Ejecuta:

    chatgpt-web-send send --conversation-id "67f12345-aaaa-bbbb-cccc-123456789abc" --prompt "Analiza esta idea"

También puedes usar un archivo UTF-8 o la entrada estándar:

    chatgpt-web-send send --conversation-id "MI_ID" --prompt-file prompt.txt
    chatgpt-web-send send --conversation-id "MI_ID" --stdin < prompt.txt

Para dejar el navegador abierto y comprobar visualmente el resultado:

    chatgpt-web-send send --conversation-id "MI_ID" --prompt "Hola" --keep-open

Opciones:

| Opción | Descripción |
| --- | --- |
| --profile-dir RUTA | Directorio de sesión persistente (login y send) |
| --browser-channel chrome/msedge | Ejecuta Chrome o Edge instalados sin falsificar User-Agent |
| --downloads-dir RUTA | Guarda las descargas del navegador en esta carpeta; por defecto `~/Downloads` |
| doctor [--keep-open] | Abre el navegador y muestra canal real, User-Agent, perfil y carpeta de descargas |
| open [--conversation-id ID] | Abre tu navegador habitual; debes enviar el mensaje manualmente |
| --timeout SEGUNDOS | Espera del editor; 60 s de forma predeterminada |
| --completion-timeout SEGUNDOS | Espera de los controles de generación; 300 s |
| --no-wait | Termina después de confirmar que se vació el editor |
| --keep-open | Conserva la ventana hasta pulsar Enter, incluso si falla el envío |
| --headless | Navegador sin ventana; requiere sesión ya iniciada |

El comando **send** abre la conversación solicitada, escribe el prompt y pulsa el botón de envío (o Enter si no aparece). Comprueba únicamente que se vacíe el editor. Por defecto observa también el **botón de detener generación**, si está disponible, para detectar cuándo desaparece. **Nunca recupera el texto generado.**

Si el sitio no expone ese indicador, no puede garantizarse que la generación haya finalizado. Con **--no-wait** se cerrará pronto la pestaña y la generación podría interrumpirse; úsalo solo si aceptas ese riesgo.

## API Python

    from chatgpt_web_send import ChatGPTWeb

    with ChatGPTWeb() as client:
        result = client.send(
            conversation_id="67f12345-aaaa-bbbb-cccc-123456789abc",
            prompt="Analiza esta idea y enumera riesgos",
        )
        print(result.submitted)  # True: el editor quedó vacío
        print(result.completed)  # True: se vio finalizar; None: desconocido

Para autenticarte manualmente desde Python:

    with ChatGPTWeb() as client:
        client.open_login()
        input("Inicia sesión en la ventana y pulsa Enter...")

Puedes configurar **ChatGPTWeb(profile_dir="...", headless=False, timeout=30)** y llamar a **send(..., wait=True, completion_timeout=300)**.

## Privacidad y funcionamiento

1. Usa un perfil local persistente de Chromium, Chrome o Edge, separado de tu perfil personal cuando hay automatización.
2. Navega a **https://chatgpt.com/c/ID** y valida que permanece en esa URL.
3. Interactúa exclusivamente con el campo de composición y los controles de enviar/detener.
4. No consulta el historial, no lee mensajes ni respuestas, no intercepta tráfico y no utiliza endpoints internos del sitio.
5. No reintenta un envío de estado dudoso, para evitar mensajes duplicados.

**submitted=True** significa que el campo de escritura se vació después de enviar: **no es prueba de ejecución en el servidor**. **completed=True** significa que se observó aparecer y desaparecer el control de detener; **completed=None** significa que no pudo verificarse el final.

La conversación debe existir y ser accesible con la cuenta iniciada. Si caduca la sesión, ejecuta de nuevo **login**. Los cambios de UI o medidas antiautomatización pueden impedir su uso. Para una integración oficial y más estable considera la [API de OpenAI](https://platform.openai.com/docs/).

## Verificaciones humanas repetidas (CAPTCHA)

Si ChatGPT muestra reiteradamente una pantalla de **verificación humana**, el sitio puede no estar aceptando esa sesión automatizada. **No significa necesariamente que la contraseña o las cookies sean incorrectas.**

En esta versión el cliente detecta señales claras de una pantalla de verificación mediante **el título o la ruta de la página**, se detiene con un error `HumanVerificationRequiredError` y **no rellena ni envía el prompt**. No lee mensajes ni respuestas ni intenta completar, saltarse o repetir automáticamente el CAPTCHA. Un desafío que no sea reconocible por esos indicadores puede seguir apareciendo como un error genérico de editor.

Para diagnosticarlo sin exponer datos privados:

1. Ejecuta `chatgpt-web-send login` con el navegador visible y confirma manualmente que accedes a ChatGPT y que puedes ver el editor **antes de pulsar Enter**. La sesión se almacena en `~/.chatgpt-web-send/profile` o en `CHATGPT_WEB_SEND_PROFILE_DIR`, no en el navegador habitual.
2. Comprueba que `login` y `send` usan exactamente el **mismo directorio de perfil y usuario de Windows**. No abras dos procesos simultáneos con ese perfil.
3. Si el desafío reaparece, no insistas con un bucle de reintentos. Usa `--keep-open` en una prueba con texto ficticio para inspeccionar la pantalla y comprobar que estás en la cuenta correcta.
4. Actualiza la versión normal de Chromium/Playwright por sus canales oficiales si hay incompatibilidades y revisa ajustes de conexión, filtros o extensiones de seguridad, **sin intentar ocultar que el proceso está automatizado**.
5. Si el sitio no permite automatizar esa sesión, utiliza la **[API oficial de OpenAI](https://platform.openai.com/docs/)** para un envío programático estable. Esta API **no equivale a escribir en una conversación existente de la web ChatGPT**, por lo que esa alternativa requiere rediseñar el flujo.

Falsificar el `User-Agent`, las huellas del navegador, los indicadores de Playwright o automatizar la resolución de CAPTCHAs **no forma parte de este proyecto**. Las esperas actuales de Playwright ya siguen la disponibilidad real del editor y del botón: pausas aleatorias no garantizan evitar verificaciones.

## Desarrollo

    python -m pip install -e '.[dev]'
    python -m pytest -q
    python -m chatgpt_web_send --help

Las pruebas unitarias simulan Playwright; no abren ChatGPT ni necesitan credenciales. CI ejecuta los tests en Python 3.10, 3.11, 3.12 y 3.13.

## Licencia

MIT. Consulta [LICENSE](LICENSE).


## Solución de problemas: no se encuentra el editor

Si `send` devuelve *composer not visible*, Playwright ha agotado el tiempo esperando a que aparezca el editor **visible**. Puede deberse a carga lenta, sesión caducada, conversación no accesible, ventana de consentimiento o cambios de interfaz. El paquete admite tanto editores `contenteditable` como `textarea`, omitiendo los campos ocultos.

Desde PowerShell:

~~~powershell
chatgpt-web-send send --conversation-id "TU_ID" --prompt "Hola desde Python" --timeout 90 --keep-open
~~~

Con `--keep-open` se conserva la ventana **también en caso de error**, hasta pulsar Enter. Puedes comprobar manualmente la URL final y posibles avisos, sin que el programa lea la conversación. Si hace falta, repite `chatgpt-web-send login`.

La espera se aplica a la aparición del editor, no a la lectura de mensajes. Si el mensaje pudiera haberse enviado y la confirmación falla, la herramienta **no reintenta automáticamente** para evitar duplicados.
