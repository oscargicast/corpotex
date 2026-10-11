# Guion del chat de rol: Gerente y taller (para extraer el estilo)

Para qué: el agente de WhatsApp escribe con el estilo del Gerente, y ese estilo se extrae de chats reales entre el Gerente y sus proveedores. Hoy el único chat real es este. Dura 15 a 20 min por WhatsApp, Oscar como Gerente de Corpotex y Valeria como dueña o encargada de un taller de costura de Piura. Después, el sistema lee este chat (solo este, desde hoy) y arma el perfil.

Reglas:

- Sin guion palabra por palabra: lo que importa es cómo escribe Oscar de verdad (tú o usted, muletillas, emojis, cuánto insiste). Que sea natural.
- Es un pedido inventado, anterior al de la demo. No es el pedido que se cancela en vivo: la cancelación NO se ensaya aquí.
- Valeria hace de "Confecciones del Norte", taller de costura en Piura. No hace falta nombre de persona: el bot saluda sin nombre.
- Nada de datos personales de verdad: montos y fechas inventados.
- Mensajes cortos, como en WhatsApp real: varios seguidos está bien.

## Situaciones que tiene que cubrir (en este orden)

| # | Situación | Oscar (Gerente) | Valeria (taller) |
|---|---|---|---|
| 1 | Proponer el pedido | Le propone 500 polos escolares, al precio de siempre (inventa uno, por ejemplo S/ 4.50 por polo) y para una fecha (por ejemplo, en 8 días). Corpotex no pide cotización: propone. | Pregunta algo del pedido (tallas, si va con cuello, cuándo llega la tela) y acepta la fecha o pide un par de días más. |
| 2 | Acordar fecha | Cierra la fecha. | Confirma. |
| 3 | Pide subir el precio | Responde "lo veo y te confirmo" o parecido: no acepta ni rechaza en el chat. | Dice que la tela está más gruesa y pide S/ 0.50 más por polo. |
| 4 | Seguimiento al día 3 | Pregunta cómo va, como lo haría de verdad (puede insistir una vez si no responde rápido). | Responde con un avance ("ya van 200"). |
| 5 | Foto de avance | Agradece, comenta algo de la foto. | Manda una foto cualquiera de ropa o del taller (no hace falta que sea real de polos). |
| 6 | Problema chico | Lo resuelve o lo deja en pausa ("mañana te digo"). | Avisa que le faltó hilo de un color o algo menor. |
| 7 | Entrega y cierre | Coordina el recojo, confirma el pago del saldo (50% adelanto, 50% a la entrega, por Yape) y agradece. | Avisa que está listo, coordina la hora. |

## Lo que NO hay que hacer

- No ensayar la cancelación del pedido (es la escena en vivo del domingo).
- No usar nombres de personas reales ni de talleres reales.
- No mandar datos de contacto, RUC ni números de cuenta.

## Después del chat: extraer y aprobar el estilo (P2.3)

Oscar avisa al orquestador "chat listo" y hace esto en el dashboard, en `/onboarding/style`. Valeria no tiene que hacer nada más hasta la demo.

Antes, una sola vez:

- En claude.ai, Settings → Privacy, revisa el ajuste que permite usar tus chats para mejorar los modelos.
- La cuenta de Claude tiene que estar conectada en Configuración.
- En Proveedores → Confecciones del Norte, el número de Valeria tiene que estar activo (el seed ya lo deja así).

### Paso a paso

1. **Leer desde:** pon la fecha de hoy (10/10). Así se lee solo el chat de rol, nada anterior.
2. **Extraer estilo** → **Extraer**. Confecciones del Norte pasa por "Leyendo el chat", "Analizando" y "Listo" (cerca de 1 min). Los demás proveedores quedan en "Sin celular": es normal, porque solo tienen el número del simulador.
3. **Leer desde:** cámbiala a **01/07/2026** antes del paso siguiente. Los chats inventados de Lima y México son de julio a octubre; con 10/10 no se leería ningún mensaje.
4. **Agregar chat (.txt)**, una vez por archivo, con los chats de `backend/agent/persona/fixtures/`:
   - `textiles-lima-norte.txt`: autor "Gerente", proveedor "Textiles Lima Norte S.A.C.".
   - `hilados-del-bajio.txt`: autor "Gerente", proveedor "Hilados del Bajío".

   Cada uno se suma al borrador (unos 30 s); no lo reemplaza.
5. **Revisa el borrador** en la vista previa:
   - Que suene a ti: tú o usted con Valeria, tus muletillas, tus emojis.
   - Que los ejemplos (burbujas) no tengan nombres, teléfonos ni montos (los montos salen como `<MONTO>`).
   - Que nada prometa pagos ni hable "del Gerente" en tercera persona.
   - Que las notas de Confecciones del Norte, Textiles Lima Norte e Hilados del Bajío tengan Trato, Tono, Insistencia y, si se ve en el chat, Horario.

   Lo que no te guste, edítalo y **Guardar borrador**.
6. **Aprobar**. Si algo no pasa la validación, aparece la lista de problemas: corrige y vuelve a aprobar. En `/style` queda una versión "Onboarding".
7. **Prueba:** en el simulador, como Confecciones del Norte, escribe "buenas, ¿cómo va todo?" y compara la respuesta con la de antes.

### Qué debería cambiar en el bot

Ilustrativo: lo exacto depende de cómo escribas en el chat.

- **Antes** (estilo base, notas "Trato de usted"): "buenos días, ¿cómo está? ¿y la familia? le paso un pedido de 300 polos a S/ 4.50 la unidad, para el jueves 22/10. ¿me confirma si se puede? 🙏"
- **Después**, si en el chat tuteas a Valeria y escribes, por ejemplo, "hola! te tengo 300 polos…": "hola, ¿qué tal? te tengo 300 polos a S/ 4.50 como siempre, para el jueves 22/10. ¿te animas?". Además, las notas de Confecciones del Norte pasan a "Trato: tú…".

### Para dejarlo listo para aprobar en vivo

El domingo, antes de las 9:00: abre `/onboarding/style` y aprieta **Guardar borrador** sin cambiar nada. Queda en "Borrador", con el mismo contenido, para aprobarlo en vivo antes de la escena de WhatsApp. Hasta ese momento, el bot sigue con el último estilo aprobado. No vuelvas a extraer en vivo: gasta la suscripción.

## Para la demo (domingo 9:00)

Valeria vuelve a ser "Confecciones del Norte" por WhatsApp. El bot (escribiendo como Oscar) le propone un pedido; ella acepta, manda una foto de avance y, cuando Oscar le haga una seña, escribe que no va a poder terminar ("se me malogró la máquina"). Eso dispara la redistribución que ve el jurado.
