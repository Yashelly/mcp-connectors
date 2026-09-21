"""Value parsing shared by the two independently observed car adapters."""
import re
from ..parsing import clean, number


def year(value):
    match = re.search(r"\b(19\d{2}|20\d{2})\b", value or "")
    return int(match[1]) if match else None


def mileage(value):
    return int(number(value)) if value and re.search(r"\d[\d\s]*\s*km\b", value) else None


def price_fields(raw):
    raw = clean(raw)
    return {"price": number(raw), "currency": "EUR" if raw and "€" in raw else None, "price_raw": raw}


def make_model(title):
    for make in ("Land Rover", "Alfa Romeo", "Aston Martin", "DS Automobiles", "Rolls-Royce"):
        if title.startswith(make + " "):
            return make, title[len(make) + 1:]
    pieces = title.split(" ", 1)
    return pieces[0], pieces[1] if len(pieces) > 1 else None


def parameter_values(values):
    fuel = next((v for v in values if re.match(r"Dyzelinas|Benzinas|Elektra|Dujos|Bioetanolis|Vandenilis|Etanolis", v)), None)
    transmission = next((v for v in values if v in {"Automatinė", "Mechaninė"}), None)
    engine = next((v for v in values if re.search(r"\bkW\b|\bl\.|\bL\b|cm³", v)), None)
    odometer = next((v for v in values if re.search(r"\bkm\b", v)), None)
    return {"fuel": fuel, "transmission": transmission, "engine": engine, "mileage_km": mileage(odometer)}
