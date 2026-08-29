# Panel

> Read in English: [dashboard.md](../en/dashboard.md)

El panel es la pantalla de inicio de tu agencia: lo primero que ves al iniciar sesión. Resume la actividad de cada cliente, agente y canal en un solo lugar, y se adapta al rango de fechas que elijas.

## Rango de fechas

Un selector en la esquina superior derecha controla la ventana que usan las gráficas y los contadores. Las opciones son **7, 14, 30 y 90 días**, con 14 por defecto. Cambiarlo vuelve a cargar las métricas para la nueva ventana.

## Próximos pasos

Hasta que tu espacio de trabajo esté configurado, una lista de bienvenida te guía por las primeras tareas: crear un cliente, crear un agente y conectar un canal. Los dos primeros pasos se marcan solos en cuanto tienes al menos un cliente y un agente.

## Métricas principales

En la parte superior hay cuatro tarjetas, cada una con un total más una línea secundaria:

- **Clientes** — total de clientes, con cuántos están activos.
- **Agentes** — total de agentes, con cuántos están activos.
- **Conversaciones** — total de conversaciones de todos los canales.
- **Canales** — total de canales de WhatsApp, con cuántos están conectados.

## Actividad

El panel de actividad grafica las **nuevas conversaciones por día** durante la ventana seleccionada en un gráfico de barras (relleno con ceros, para que aparezca cada día aunque no haya tráfico). Junto a él, dos contadores cubren la misma ventana: total de **mensajes** y conversaciones **atendidas por una persona** (las que se pasaron a modo humano para que un operador responda desde la bandeja). Consulta [Bandeja de entrada](inbox.md).

## Agentes destacados

Una lista ordenada muestra tus agentes más activos por número de conversaciones en la ventana, hasta cinco. Cada fila enlaza directamente a ese agente. Consulta [Agentes](agents.md).

## Uso de tokens por modelo

Este panel desglosa el consumo por modelo durante la ventana, hasta seis modelos, ordenados por total de tokens. Cada fila muestra el nombre del modelo y una barra con su total, y el encabezado del panel muestra los tokens agregados de **entrada** (↓) y **salida** (↑) de toda la ventana. Refleja el uso real registrado por cada petición, así que permanece vacío hasta que tus agentes empiecen a responder.

## Agentes recientes

Al final se listan los cinco agentes creados más recientemente con su cliente y estado, además de un enlace a la lista completa de [Agentes](agents.md).
