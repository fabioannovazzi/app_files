# Ejecutar un caso sintético de transformación societaria

La explicación y una práctica breve requieren unos 5–8 minutos. El procesamiento y tus preguntas pueden alargar la sesión.

Habla con el docente mediante la voz estándar de Codex. En la conversación de trabajo, abierta en la ventana contigua, la función ejecuta el caso con los archivos preparados y muestra resultados reales. El docente sigue esos resultados: puedes interrumpir, preguntar y cambiar el ritmo.

Utiliza el material preparado para enseñar un primer uso completo. Selecciona 3–4 funciones pertinentes durante la incorporación; después, empieza por lo que el usuario quiera hacer hoy. Adapta el ritmo y las explicaciones. Crea ejemplos personalizados cuando ayuden, con el mismo workflow y entradas revisadas. Lee execution-request.json, utiliza el caso local realmente vinculado y explica los resultados verificados de la conversación de trabajo. No inventes resultados, respuestas del usuario ni confirmaciones de comprensión. Abrir el kit no completa la lección.

## 1. Cuándo utilizarla · 45 s

Relaciona la función con una tarea profesional concreta.

Preparar y revisar un expediente sintético, seguir sus evidencias y reabrir decisiones cuando cambia un pasivo.

Officina Selce SNC, empresa inventada, considera una SRL. Dos socios tienen derechos distintos de capital, voto y beneficios. La valoración llega después de la lista de acreedores.

Prototipo italiano con datos inventados en Codex desktop y Work local donde esté admitido. Cowork no ofrece este curso. El expediente nativo sigue en italiano. Sin calificación jurídica o fiscal, firma autenticada, integración Studio Archive ni presentación oficial.

## 2. Archivos y petición · 60 s

Abre los archivos en la ventana de trabajo y muestra cómo pedir el resultado.

Abre files/input/case.json, participants.json y creditors.json. Reserva valuation.json para el segundo paso y valuation-update.json para el cambio final. Null significa desconocido, nunca cero o consentimiento; las cadenas numéricas son exactas. No uses clientes reales.

Vera, guíame por el caso sintético Officina Selce: importa primero encargo, socios y acreedores, muestra qué falta para el capital y después incorpora la valoración. Propón conclusiones vinculadas a evidencias, muestra decisiones pendientes de revisión y exporta sin acciones externas.

## 3. Ejecutar el trabajo · 105 s

Explica el paso que se está ejecutando y espera su resultado real.

En el chat de trabajo, Vera lee el procedimiento instalado y crea una carpeta sintética local nueva. Importa los tres primeros archivos como evidencias. Propón ramas separadas para capital, recopilación de acreedores y fiscalidad. El capital depende de la valoración aún no recibida; la recopilación puede continuar, pero liberación y oposición siguen siendo cuestiones distintas. Exporta esta versión.

Importa valuation.json. El modelo propone cálculos, derechos y conclusiones con dependencias documentales exactas y motivos comprobables. Examina cobertura y reparto de capital, separando capital/voto/beneficios y valores contable/estimado/fiscal. No inventes autoridades jurídicas: las cuestiones fiscales y los acuses ausentes siguen abiertos. Muestra propuesta, resumen criptográfico y expediente antes de revisar.

Registra únicamente decisiones expresadas realmente por el participante, con revisor, motivo y resumen criptográfico; etiqueta cualquier simulación. Conserva la exportación. Reimporta valuation-update.json con el mismo ID de valoración: capital pasa a stale y la recopilación independiente sigue vigente. El documento no actualiza cálculos antiguos: corrige datos numéricos y conclusiones, vuelve a someterlos y solicita una decisión nueva. Abre dossier.md, case.json, manifest.json y history/.

Durante la lección, la conversación de trabajo ejecuta la función y produce el resultado. Si un paso no está disponible, explica qué falta y deja la lección incompleta.

## 4. Utilizar el resultado · 75 s

Abre el documento recién producido y muestra por dónde empezar a leerlo.

Expediente Markdown y JSON versionado con documentos, dependencias, importes, derechos, bloqueos, cuestiones abiertas y decisiones; manifiesto de hashes.

Exportaciones anteriores e historial encadenado, más informe local legible sobre datos que llegan al modelo. Los archivos preparados no son resultados ejecutados.

Sigue una conclusión hasta evidence/<hash> y su documento original. Comprueba importes exactos y derechos distintos. Un margen aritmético no es una reserva distribuible. Una recepción desconocida no demuestra liberación ni resultado de oposición. La revisión registrada no autentica al revisor y aprueba como máximo la preparación sintética.

## 5. Parar y comprobar · 45 s

Haz estas comprobaciones en los momentos indicados durante el trabajo.

Antes de la valoración, identifica la rama bloqueada y la que puede recopilar datos; encuentra una recepción y una base fiscal ausentes.

Antes de decidir, comprueba la evidencia y las tres cuotas de cada socio. Tras el cambio, muestra stale y una decisión independiente conservada.

Estas pausas ayudan a aprender a utilizar la función. No son un examen de detalles técnicos.

## 6. Ahora prueba tú · 60 s

Deja que el usuario formule la petición y acompaña su intento.

Crea un segundo caso con files/practice/, conservando la demostración. Usa activos 640000 y pasivos 270000; repite importación, propuesta y revisión. Después importa valuation-update.json con pasivos 305000 bajo el mismo ID. Identifica ramas stale, corrige cobertura y conclusiones, solicita nueva revisión y exporta sin cerrar cuestiones fiscales ni inventar recepciones.

En la demostración comprueba patrimonio neto 450000, margen 350000 y capital 60000/40000; con pasivos 310000 comprueba 390000/290000 tras revisar. En la práctica comprueba 370000/270000 y después 335000/235000. Encuentra votos 1/2–1/2, beneficios 7/10–3/10, decisión anterior en history, bloqueo fiscal y hashes del expediente. Son criterios de revisión, no resultados ya ejecutados.

Repite solo con datos sintéticos, carpeta nueva y skill Vera realmente instalada. Un piloto profesional supervisado todavía requiere calificación y aceptación. Explicación y prueba breve: 5–8 minutos; revisión y práctica completa pueden durar más. Perfil, progreso y archivos siguen locales; el modelo nativo puede leer documentos seleccionados, así que el procesamiento no es exclusivamente local.

El kit contiene archivos ficticios y un guion preparado. Los resultados de la demostración y la práctica proceden de nuevas ejecuciones de la función actual.

La biblioteca, el perfil y el progreso permanecen en tu ordenador y no se envían a Mparanza. La voz y los contenidos leídos en la conversación se procesan mediante tu cuenta OpenAI: almacenamiento local no significa inferencia sin conexión.
