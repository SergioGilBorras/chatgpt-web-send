# chatgpt-web-send

Paquete Python y CLI para **enviar prompts a conversaciones existentes de ChatGPT** desde un navegador donde el usuario inicia sesión. Se centra en el envío: **no lee el historial, mensajes anteriores ni respuestas**.

> Proyecto no oficial: automatiza la web de ChatGPT con Playwright, no usa la API de OpenAI. Los cambios de la interfaz pueden romper el funcionamiento y la automatización está sujeta a las condiciones de uso aplicables. No evita verificaciones, CAPTCHAs ni controles de acceso.

## Requisitos

- Python 3.10 o posterior.
- Cuenta de ChatGPT, accesible en el navegador.
- Chromium instalado con Playwright.

## Instalación

Desde el repositorio:

    git clone https://github.com/SergioGilBorras/chatgpt-web-send.git
    cd chatgpt-web-send
    python -m pip install -e .
    python -m playwright install chromium

## 1. Inicio de sesión

    chatgpt-web-send login

Se abre Chromium. **Inicia sesión manualmente en la ventana** y después **pulsa Enter en la terminal**. El perfil local de Chromium conservará la sesión para futuros envíos. El paquete no pide credenciales ni lee cookies.

Perfil predeterminado: **~/.chatgpt-web-send/profile**. Se puede cambiar con la opción **--profile-dir RUTA** o la variable de entorno **CHATGPT_WEB_SEND_PROFILE_DIR**.

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
| --timeout SEGUNDOS | Espera del editor; 30 s de forma predeterminada |
| --completion-timeout SEGUNDOS | Espera de los controles de generación; 300 s |
| --no-wait | Termina después de confirmar que se vació el editor |
| --keep-open | Conserva la ventana hasta pulsar Enter |
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

1. Usa un perfil local y persistente de Chromium.
2. Navega a **https://chatgpt.com/c/ID** y valida que permanece en esa URL.
3. Interactúa exclusivamente con el campo de composición y los controles de enviar/detener.
4. No consulta el historial, no lee mensajes ni respuestas, no intercepta tráfico y no utiliza endpoints internos del sitio.
5. No reintenta un envío de estado dudoso, para evitar mensajes duplicados.

**submitted=True** significa que el campo de escritura se vació después de enviar: **no es prueba de ejecución en el servidor**. **completed=True** significa que se observó aparecer y desaparecer el control de detener; **completed=None** significa que no pudo verificarse el final.

La conversación debe existir y ser accesible con la cuenta iniciada. Si caduca la sesión, ejecuta de nuevo **login**. Los cambios de UI o medidas antiautomatización pueden impedir su uso. Para una integración oficial y más estable considera la [API de OpenAI](https://platform.openai.com/docs/).

## Desarrollo

    python -m pip install -e '.[dev]'
    python -m pytest -q
    python -m chatgpt_web_send --help

Las pruebas unitarias simulan Playwright; no abren ChatGPT ni necesitan credenciales. CI ejecuta los tests en Python 3.10, 3.11, 3.12 y 3.13.

## Licencia

MIT. Consulta [LICENSE](LICENSE).
