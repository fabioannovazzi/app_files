# Antes del gráfico, establecer qué significan los datos

Un recorrido guiado de unos 6 minutos y medio. La activación de voz, los procesos externos y el ejercicio opcional requieren tiempo adicional.

Habla con el docente mediante la voz estándar de Codex. En la segunda conversación, abierta al lado, examina los archivos y el resultado. Ambas siguen vinculadas; puedes interrumpir, preguntar por qué o reducir el ritmo cuando quieras.

Utiliza este material preparado. No reescribas la lección ni inventes resultados. Habla en turnos breves, deja tiempo para observar y escucha respuestas reales. No muestres la solución antes del intento. Los tiempos incluyen observación y diálogo. Mostrar estos archivos no completa demostración, práctica ni comprensión en el registro local. El docente elige por pertinencia únicamente dentro del catálogo de su producto.

## 1. Tu objetivo · 45 s

Escucha la petición. Relaciona el caso con un trabajo que ya haces.

El conjunto ficticio informa ventas netas de EUR 40.000 en enero y EUR 50.000 en febrero. Falta Discount separado. Las notas confirman que Sales ya incluye descuentos; restarlos otra vez sería incorrecto.

Clara, muestra la evolución de ventas y explica qué datos utilizas.

## 2. Los datos de partida · 60 s

Mira los documentos en la otra conversación. Identifica un dato útil y una información que falta.

R1 contiene dos meses; R2 define Sales como neto. Discount falta como medida separada, no consta como cero.

[["2026-01", "EUR 40.000", "Ventas netas"], ["2026-02", "EUR 50.000", "Ventas netas"], ["Discount separado", "Ausente", "Ya reflejado en Sales"]]

## 3. Cómo trabaja el workflow · 75 s

Sigue los tres pasos. Detente en la decisión que cambia el resultado.

Ejecuta la recepción del conjunto e inspecciona datos, perfil y notas. Revisa significado, agregación y funciones Sales, Discount y COGS; las cabeceras solas no bastan.
Selecciona una capacidad compatible y renderiza mediante el adaptador de Clara conservando petición efectiva y prueba de salida.
Abre el resultado y verifica valores, unidades, periodos y conclusión. Reutiliza un contrato semántico estable compatible en futuras cargas en vez de reconstruir significados cada vez.

## 4. Leer el resultado · 90 s

Abre el ejemplo en la segunda conversación. Vincula cada conclusión con su fuente.

Pasan de EUR 40.000 a EUR 50.000: EUR 10.000 o 25 % más. No están disponibles descuentos separados ni costes.

[["Enero", "EUR 40.000", "R1 · ventas netas"], ["Febrero", "EUR 50.000", "R1 · ventas netas"], ["Variación", "+EUR 10.000 · +25 %", "Base enero EUR 40.000"]]

## 5. La comprobación clave · 75 s

Antes de mostrar la respuesta, explica qué comprobarías.

Compatibilidad técnica y corrección semántica son controles distintos. Columnas válidas pueden tener una correspondencia comercial equivocada.

Sin columna Discount, ¿podemos afirmar que no se concedieron descuentos?

Comparar el razonamiento: No. Sales es neto y no se aporta la medida separada. La ausencia de columna no demuestra ausencia de descuentos.

## 6. Probar juntos · 45 s

Decide si prefieres practicar ahora o guardar el ejemplo para tu próximo encargo.

Añade marzo con la misma definición de Sales y verifica reutilización del contrato y gráfico actualizado.

Selecciona CSV, Excel o Parquet con notas de métricas. Los informes Real/Presupuesto usan la vía presupuestaria propia de Clara dentro de este workflow.

Este es un ejemplo didáctico preparado, no un comprobante de una nueva ejecución. Las fuentes y decisiones son ficticias; no se presupone aprobación profesional. Con tus archivos, el workflow actual realiza sus comprobaciones y conserva los resultados reales.

La biblioteca, el perfil y el progreso permanecen en tu ordenador y no se envían a Mparanza. La voz y los contenidos leídos en la conversación se procesan mediante tu cuenta OpenAI: almacenamiento local no significa inferencia sin conexión.
