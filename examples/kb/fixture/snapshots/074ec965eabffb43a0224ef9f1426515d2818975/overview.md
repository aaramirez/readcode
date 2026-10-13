# Fixture multilenguaje

Un repositorio pequeño pensado para ejercitar readcode con **Python, TypeScript, Go y SQL**.
No es un sistema integrado: son tres programas que comparten un dominio (facturas) pero no
código. Desde este commit el dominio incluye **reembolsos**.

[[archify:arquitectura]]

## Las piezas

| Pieza | Lenguaje | Qué hace | Por dónde empezar |
|---|---|---|---|
| `app/` | Python | Autentica, factura y (nuevo) reembolsa | [[ref:app/main.py#main]] |
| `web/` | TypeScript | Consulta y reembolsa facturas en una API HTTP externa | [[ref:web/src/index.ts:L3]] |
| `worker/` | Go | Cola FIFO en memoria con un ejemplo de uso | [[ref:worker/main.go#main]] |
| `db/` | SQL | Esquema `users`/`invoices` (aún sin uso) | [[ref:db/schema.sql#invoices]] |

## El flujo principal

```mermaid
flowchart LR
    main["app/main.py<br/>main()"] -->|"1"| auth["auth.process"]
    main -->|"2"| billing["billing.process"]
    billing --> total["compute_total"]
    billing --> inv["models.Invoice"]
    refunds["refunds.process_refund"] -.->|"aún sin llamar"| refund["billing.refund"]
    refund -->|"total negativo"| inv
    inv -. "espejo" .-> ts["web/src/types.ts<br/>Invoice"]
    inv -. "espejo" .-> sql["db/schema.sql<br/>invoices"]
```

1. [[ref:app/main.py#main]] llama a [[ref:app/services/auth.py#process]], que añade un token al
   usuario.
2. Después llama a [[ref:app/services/billing.py#process]], que suma los importes con
   [[ref:app/services/billing.py#compute_total]] y construye un [[ref:app/models.py#Invoice]].
3. El camino inverso, [[ref:app/services/refunds.py#process_refund]] →
   [[ref:app/services/billing.py#refund]], existe pero ningún punto de entrada lo usa todavía.

## Ideas clave para leerlo

- **Dos funciones `process`.** Están en módulos distintos y se distinguen por el módulo
  (`auth.process`, `billing.process`). Una referencia sin ruta como [[ref:#process]] es ambigua.
- **Un reembolso es una factura negativa.** No hay modelo `Refund`; el signo del total marca la
  diferencia, y nada valida ese signo.
- **El modelo `Invoice` existe tres veces**: en Python, en TypeScript y como tabla SQL, y las
  tres copias no coinciden del todo (`owner` es un nombre en Python y un `user_id` en SQL).
- **La seguridad es simbólica**: el token se genera con `hash()` y nadie lo verifica.
- **El worker está aislado**: su cola ([[ref:worker/queue.go#Queue]]) es en memoria y no
  tolera colas vacías ni concurrencia.

## Recorridos

- *Flujo de facturación*: de `main()` al total, y el camino inverso del reembolso.
- *Worker y su cola*: cómo funciona la cola FIFO en Go y sus límites.
