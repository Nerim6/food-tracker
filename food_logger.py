"""Command-line meal logging utility for foods.csv.

This script loads the food database from ``foods.csv`` using pandas, allows
logging meals with custom serving sizes, appends entries to ``food_log.csv``,
and prints a macro summary for the current day.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

DATA_FILE = Path("foods.csv")
LOG_FILE = Path("food_log.csv")
REQUIRED_COLUMNS = {
    "name",
    "brand",
    "category",
    "protein",
    "fat",
    "carbohydrate",
    "calories",
    "fibre",
    "sodium",
}
REFERENCE_AMOUNT_GRAMS = 100.0


class FoodLookupError(Exception):
    """Raised when a requested food item cannot be found in the database."""


@dataclass
class MealEntry:
    food_name: str
    serving_display: str
    macros: Dict[str, float]
    timestamp: datetime

    def to_record(self) -> Dict[str, object]:
        record = {
            "timestamp": self.timestamp.isoformat(timespec="seconds"),
            "food": self.food_name,
            "serving": self.serving_display,
        }
        record.update(self.macros)
        return record


def load_food_database() -> pd.DataFrame:
    """Load ``foods.csv`` and validate its structure."""
    try:
        df = pd.read_csv(DATA_FILE)
    except FileNotFoundError:
        print(f"Error: {DATA_FILE} was not found in {Path.cwd()}.")
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Error reading {DATA_FILE}: {exc}")
        sys.exit(1)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        print(
            "Error: The following required columns are missing from "
            f"{DATA_FILE}: {', '.join(sorted(missing))}."
        )
        sys.exit(1)

    df = df.copy()
    df["name_normalized"] = df["name"].str.strip().str.lower()
    return df


def parse_quantity(quantity_str: str) -> float:
    """Convert an input like ``"50g"`` or ``"30"`` into grams."""
    cleaned = quantity_str.strip().lower().replace("grams", "g").replace("gram", "g")
    cleaned = cleaned.replace("milliliters", "ml").replace("milliliter", "ml")
    cleaned = cleaned.replace("millilitres", "ml").replace("millilitre", "ml")

    num = ""
    unit = ""
    for char in cleaned:
        if char.isdigit() or char == ".":
            num += char
        elif not char.isspace():
            unit += char

    if not num:
        raise ValueError(
            "Unable to parse quantity. Please provide a numeric amount such as '50g'."
        )

    try:
        amount = float(num)
    except ValueError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid number in serving size: {quantity_str}") from exc

    unit = unit or "g"
    if unit not in {"g", "ml"}:
        raise ValueError(
            "Unsupported unit. Please use grams (g). Milliliters (ml) are accepted "
            "for liquids, assuming density of water."
        )

    return amount


def lookup_food(df: pd.DataFrame, food_name: str) -> pd.Series:
    """Find a food row by name (case-insensitive)."""
    name = food_name.strip().lower()
    matches = df[df["name_normalized"] == name]

    if matches.empty:
        raise FoodLookupError(f"'{food_name}' was not found in {DATA_FILE}.")

    if len(matches) > 1:
        print(
            f"Warning: multiple entries found for '{food_name}'. Using the first match."
        )

    return matches.iloc[0]


def calculate_macros(row: pd.Series, amount_in_grams: float) -> Dict[str, float]:
    """Scale nutritional information to match the serving size."""
    scale = amount_in_grams / REFERENCE_AMOUNT_GRAMS
    nutrient_columns = [
        "protein",
        "fat",
        "carbohydrate",
        "calories",
        "fibre",
        "sodium",
    ]

    macros: Dict[str, float] = {}
    for col in nutrient_columns:
        value = row.get(col)
        try:
            macros[col] = round(float(value) * scale, 2)
        except (TypeError, ValueError):
            macros[col] = float("nan")
    return macros


def save_entries(entries: Iterable[MealEntry]) -> None:
    if not entries:
        return

    df = pd.DataFrame([entry.to_record() for entry in entries])
    header = not LOG_FILE.exists()
    df.to_csv(LOG_FILE, mode="a", header=header, index=False)


def summarize_today() -> Optional[pd.Series]:
    if not LOG_FILE.exists():
        return None

    try:
        log_df = pd.read_csv(LOG_FILE, parse_dates=["timestamp"])
    except Exception as exc:  # pragma: no cover - defensive
        print(f"Warning: Could not read {LOG_FILE}: {exc}")
        return None

    today = date.today()
    log_df = log_df[log_df["timestamp"].dt.date == today]
    if log_df.empty:
        return None

    totals = log_df[[
        "calories",
        "protein",
        "fat",
        "carbohydrate",
        "fibre",
        "sodium",
    ]].sum(numeric_only=True)
    return totals


def main() -> None:
    foods_df = load_food_database()

    print("Enter meals in the format 'food name, amount' (e.g., 'Almonds, 50g').")
    print("Press Enter on an empty line or type 'done' when finished.\n")

    entries: list[MealEntry] = []
    while True:
        try:
            user_input = input("Meal entry: ").strip()
        except EOFError:  # pragma: no cover - interactive guard
            break

        if not user_input or user_input.lower() in {"done", "exit", "quit"}:
            break

        if "," not in user_input:
            print("Please separate the food name and amount with a comma.")
            continue

        food_name, quantity_str = [part.strip() for part in user_input.split(",", 1)]
        if not food_name or not quantity_str:
            print("Both food name and quantity are required.")
            continue

        try:
            amount = parse_quantity(quantity_str)
        except ValueError as exc:
            print(f"Error: {exc}")
            continue

        try:
            food_row = lookup_food(foods_df, food_name)
        except FoodLookupError as exc:
            print(f"Error: {exc}")
            continue

        macros = calculate_macros(food_row, amount)
        entry = MealEntry(
            food_name=food_row["name"],
            serving_display=f"{amount:g} g",
            macros=macros,
            timestamp=datetime.now(),
        )
        entries.append(entry)

        print("Logged:")
        for key, value in entry.macros.items():
            print(f"  {key.title()}: {value}")
        print()

    save_entries(entries)

    totals = summarize_today()
    if totals is None:
        print("No entries logged for today yet.")
    else:
        print("Today's totals:")
        for nutrient, value in totals.items():
            print(f"  {nutrient.title()}: {round(value, 2)}")


if __name__ == "__main__":
    main()
