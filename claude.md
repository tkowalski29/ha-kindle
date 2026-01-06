# Notatki rozwojowe - Ha-Kindle

## Ikonki dla Kindle

**WAŻNE:** Ikonki powinny być jako UTF-8 emoji, aby Kindle je poprawnie wyświetlał.

### Obsługiwane ikony UTF-8 (emoji):

#### Urządzenia:
- 💡 Światło (on)
- ⚫ Światło (off)
- 🔘 Przełącznik (on)
- ⚪ Przełącznik (off)
- 🌀 Wentylator (on)
- ⭕ Wentylator (off)
- 🌡️ Termostat/Climate
- 🧹 Odkurzacz
- 🔒 Zamek (locked)
- 🔓 Zamek (unlocked)
- 📂 Roleta (open)
- 📁 Roleta (closed)
- 📊 Sensor

#### Pomieszczenia:
- 🍳 Kuchnia
- 🚿 Łazienka
- 💼 Biuro
- 🌿 Balkon/Taras

### NIE używać ikon MDI (Material Design Icons) ani emoji UTF-8

**WAŻNE:** Kindle e-ink NIE wspiera:
- ❌ Emoji UTF-8 (renderowane jako custom font glyphs)
- ❌ Ikony SVG
- ❌ Custom fonts (Font Awesome, MDI, etc.)
- ❌ Wszystko renderowane w domyślnej czcionce systemowej Kindle

### ✅ Rozwiązania działające na Kindle:

#### 1. Małe obrazki PNG (zalecane)
- Czarno-białe ikony jako małe pliki PNG
- Wysokiego kontrastu (minimum 4.5:1 ratio)
- Rozmiar: 24x24px lub 32x32px
- Lokalizacja: `/static/icons/`
- Przykład: `<img src="/static/icons/light.png" alt="Światło">`

#### 2. Proste symbole ASCII
```
[O] Światło ON     [=] Zamek zamknięty
[X] Światło OFF    [-] Zamek otwarty
[+] Temperatura    [~] Wentylator
[?] Nieznany       [!] Alert
```

#### 3. Tekstowe etykiety
```
SW: Switch
LI: Light
CL: Climate
VC: Vacuum
```

### Implementacja:

W szablonach kart używaj mapowania ikon:
```python
icon_map = {
    'light': {'on': '💡', 'off': '⚫'},
    'switch': {'on': '🔘', 'off': '⚪'},
    'vacuum': {'on': '🧹', 'off': '🧹'},
    # ...
}
```

Dla custom ikon z HA (card.icon):
- Jeśli `card.icon` zawiera `mdi:` - zmapować na odpowiedni emoji UTF-8
- Domyślny fallback: ❓

## Kindle Screen Specifications

### Kindle Paperwhite (11th & 12th gen):
- **Rozdzielczość**: 1264×1680 (12th gen) lub 1236×1648 (11th gen)
- **Aspect ratio**: 3:4 (portret/pionowy)
- **PPI**: 300
- **Ekran**: 6.8-7 cali
- **Orientacja domyślna**: Portret (pionowa)

### Implikacje dla layoutu:
- Ekran jest **węższy niż wyższy** (portret)
- Layout side-by-side (2 kolumny) działa dopiero powyżej 1300px szerokości
- Dla Kindle w orientacji portret: sekcje jedna pod drugą
- Dla Kindle w landscape (obrócony): możliwe sekcje obok siebie

## Architektura

### Struktura szablonów:
- `templates/cards/` - szablony dla różnych typów kart Lovelace
  - `heading.html` - nagłówki sekcji
  - `thermostat.html` - karty climate/thermostat
  - `tile.html` - uniwersalne karty tile
  - `button.html` - przyciski/akcje

### Renderowanie Lovelace:
- Pełna struktura sections z Home Assistant
- Grid layout zgodny z `max_columns` i `grid_options`
- Side-by-side sections dla lepszego wykorzystania ekranu
