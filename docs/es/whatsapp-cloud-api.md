# Conectar la API de WhatsApp Business Cloud

> Read in English: [whatsapp-cloud-api.md](../en/whatsapp-cloud-api.md)

Esta guía explica cómo conectar el número de WhatsApp de un cliente a
OpenLivery usando la **API oficial de WhatsApp Business Cloud** (alojada por
Meta): desde crear la app en Meta hasta pegar las credenciales en OpenLivery
y salir a producción. Es independiente del canal WhatsApp QR — un cliente
puede tener ambos conectados en números distintos.

Al final habrás ingresado cuatro valores en OpenLivery:

| Valor | De dónde sale |
| --- | --- |
| **ID del número de teléfono** | Portal de desarrolladores de Meta → WhatsApp → API Setup |
| **ID de la cuenta de WhatsApp Business** (opcional) | La misma pantalla del ID del número |
| **Token de acceso permanente** | Un *usuario del sistema* de Business Suite (paso 4) |
| **Secreto de la app** | App Dashboard → App settings → Basic |

## 1. Requisitos previos

Antes de la configuración técnica, asegúrate de tener:

- Un **portafolio comercial de Meta** (antes Business Manager) en buen estado:
  - **Verificación del negocio** completada — revísala en
    **Settings > Business Info > Verification Status**.
  - Un **método de pago** vinculado a la cuenta de WhatsApp dentro de
    Business Suite para cubrir los costos de conversación.
- Un número de teléfono que pueda recibir un SMS o una llamada de
  verificación y que **no** esté registrado actualmente en las apps de
  WhatsApp/WhatsApp Business.
- Una instancia de OpenLivery accesible por **HTTPS público** (Meta solo
  entrega webhooks a URLs HTTPS), con el cliente creado y un agente asignado.
- **Una app de Meta por cliente.** Una app de Meta tiene una sola URL de
  callback, y OpenLivery le da la suya a cada canal, así que una app no puede
  servir a dos clientes: la URL que registres es la única que recibe. El tráfico
  que llega de un número que no es el del canal se ignora en vez de contestarlo
  con el agente equivocado, así que una app compartida se ve como mensajes que
  nunca llegan.

## 2. Crear la app de Meta

1. Entra al portal de [Meta for Developers](https://developers.facebook.com/).
2. Haz clic en **Create App**.
3. Como tipo de app elige **Other** y luego **Business**.
4. Dentro del App Dashboard busca el producto **WhatsApp** y haz clic en
   **Set Up**.
5. Cuando lo pida, vincula la app con tu **portafolio comercial verificado**.

## 3. Configurar el número de WhatsApp

1. En el portal de desarrolladores ve a **WhatsApp > API Setup**.
2. **Add phone number** y sigue los pasos para agregar el número del negocio.
3. Elige un **nombre visible** que represente claramente la marca (por
   ejemplo, "Di Pizza Gourmet").
   - Meta revisa este nombre. Si lo rechaza, usa **Edit Display Name** para
     dar uno más específico y menos genérico.
4. Completa la **verificación por SMS o llamada** del número.
5. Copia el **Phone number ID** que aparece en esta pantalla — es el que
   pegarás en OpenLivery. El **ID de la cuenta de WhatsApp Business**
   (WABA ID) aparece en la misma pantalla y es opcional en OpenLivery.

## 4. Generar el token de acceso permanente

El token que muestra la pantalla de API Setup caduca en 24 horas. Para una
conexión permanente, créalo con un usuario del sistema:

1. Ve a **Meta Business Suite > Settings > Users > System Users**.
2. Selecciona un **usuario del sistema administrador** existente, o crea uno.
3. Haz clic en **Assign Assets**, elige **Apps**, selecciona tu app de
   WhatsApp y habilita **Full Control (Manage App)**.
4. Haz clic en **Generate New Token**, selecciona la app y marca estos
   permisos:
   - `whatsapp_business_messaging`
   - `whatsapp_business_management`
5. **Copia el token de inmediato y guárdalo en un lugar seguro** — Meta no lo
   volverá a mostrar. Este es el **token de acceso permanente** para
   OpenLivery.

## 5. Obtener el secreto de la app

1. En el App Dashboard ve a **App settings > Basic**.
2. Haz clic en **Show** junto a **App secret** y cópialo.

OpenLivery usa el secreto de la app para validar la firma HMAC de cada
webhook que envía Meta, de modo que las solicitudes que no vienen realmente
de Meta se rechazan.

## 6. Ingresar las credenciales en OpenLivery

1. En OpenLivery abre **Clientes**, elige el cliente y en su pestaña de
   **Canales** abre la tarjeta **WhatsApp API** (también accesible desde la
   página **Canales**).
2. Selecciona el **agente** que responderá este número.
3. Completa:
   - **ID del número de teléfono** (del paso 3)
   - **ID de la cuenta de WhatsApp Business** — opcional
   - **Token de acceso permanente** (del paso 4)
   - **Secreto de la app** (del paso 5)
4. Haz clic en **Guardar credenciales**. El token y el secreto se cifran en
   reposo y son de solo escritura: la API nunca los devuelve, y dejarlos en
   blanco en un guardado posterior conserva los valores almacenados.

## 7. Registrar el webhook

En la misma página del canal, OpenLivery muestra una **URL de callback** y un
**token de verificación** con botones de copiado:

1. En el portal de desarrolladores de Meta ve a **WhatsApp > Configuration**.
2. Pega la **URL de callback** y el **token de verificación**, y guarda. Meta
   llama la URL una vez para verificar el handshake — debe funcionar antes de
   poder continuar.
3. En **Webhooks**, haz clic en **Manage** y suscríbete al campo
   **`messages`**.

> La URL de callback se construye con la dirección pública de la instancia,
> así que la instancia debe ser accesible por HTTPS en esa URL. Si el
> handshake falla, revisa la sección de solución de problemas.

## 8. Conectar y salir a producción

1. De vuelta en OpenLivery haz clic en **Conectar y verificar**. OpenLivery
   valida las credenciales contra la Graph API y captura el número y su
   nombre verificado; el estado del canal cambia a **conectado**.
2. En el portal de desarrolladores cambia el **App Mode** de **Development**
   a **Live** (barra superior) para permitir el tráfico real de clientes.
3. Envía un mensaje de WhatsApp al número: el agente asignado debería
   responder, y la conversación aparece en el Inbox de OpenLivery.

## 9. Solución de problemas

- **Error de autorización** — normalmente un token caducado o permisos
  faltantes (`whatsapp_business_messaging`). Genera un nuevo token permanente
  (paso 4) y guárdalo de nuevo en OpenLivery.
- **Nombre visible pendiente o rechazado** — asegúrate de que el nombre
  visible coincida con el nombre legal del negocio o con la marca del sitio
  web.
- **Pago requerido** — el método de pago debe estar asignado específicamente
  a la **cuenta de WhatsApp** en Business Suite, no solo a la cuenta
  publicitaria general.
- **La verificación del webhook falla** — el token de verificación pegado en
  Meta debe coincidir exactamente con el que muestra OpenLivery, y la URL de
  callback debe ser accesible desde internet por HTTPS. En instancias
  self-hosted, revisa que `FRONTEND_URL` apunte a la dirección pública de la
  app.
- **No llegan mensajes** — confirma que el número del payload es el de este
  canal: una app compartida entre dos clientes entrega todo a una sola URL de
  callback, y el tráfico de otro número se descarta a propósito (mira
  [Requisitos previos](#1-requisitos-previos)). Después confirma la suscripción
  al campo de webhook **`messages`** (paso 7) y que la app esté en modo **Live**; en modo
  Development Meta solo entrega tráfico de números de prueba. La tarjeta del
  canal en OpenLivery muestra el último error del webhook, si lo hay.
- **Llegan mensajes pero el agente no responde** — el canal está conectado
  pero el agente asignado puede estar inactivo o sin la API key de su
  proveedor; la tarjeta del canal muestra la razón exacta en **último
  error**.
