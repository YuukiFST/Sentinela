---
harness: claude
session: 3b9e5f17-6d2c-4e8a-a0f4-00000eva3d0m
part: 1
turns: 3
started: 2026-10-04T10:00:00.000Z
ended: 2026-10-04T10:45:00.000Z
cwd: C:\Users\dev\Desktop\shop
branch: feat/18-shipping-fee
---

# Coding session 2026-10-04 (0eva3d0m, part 1)

Captured by `omoikane/bin/session-capture.py`, no LLM involved. Agent notes are clipped, not summarised.

## Files edited

- `src/checkout/shipping.py`
- `src/checkout/total.py`
- `tests/test_shipping.py`

## Turn 1

### Prompt

Adiciona o frete no checkout: R$ 12,90 fixo pra pedido abaixo de R$ 150, grátis acima disso. Coloca em src/checkout/shipping.py e soma no total.

### Edited

- `src/checkout/shipping.py`
- `src/checkout/total.py`
- `tests/test_shipping.py`

### Commands

```
python -m pytest tests/test_shipping.py
```

### Agent notes

`shipping_fee(subtotal: float) -> float` returns `12.9` below `150.0` and `0.0` above; `order_total` adds it to the subtotal. Tests cover 149.99, 150.00 and 200.00.

## Turn 2

### Prompt

De novo isso? Valor monetário é centavos inteiros, já tá combinado, e você usou float no frete. Corrige.

### Edited

- `src/checkout/shipping.py`
- `tests/test_shipping.py`

### Agent notes

`shipping_fee(subtotal_cents: int) -> int` now returns `1290` below `15000` and `0` from `15000` up; tests use integer cents. Searched `src/` for other `float` amounts: none left.

## Turn 3

### Prompt

Beleza, roda os testes e fecha.

### Commands

```
python -m pytest
```

### Agent notes

All 17 tests pass.
