import sys
import re
from datetime import datetime, date
from pathlib import Path
from typing import Tuple

import pandas as pd

FOODS_CSV = Path('foods.csv')
LOG_CSV = Path('food_log.csv')


class QuantityParseError(ValueError):
    """Raised when a serving string cannot be parsed."""


def load_foods(path: Path) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"Could not find {path}.") from exc

    if 'name' not in df.columns:
        raise SystemExit("The foods.csv file must contain a 'name' column.")

    numeric_columns = [
        'protein',
        'fat',
        'carbohydrate',
        'calories',
        'fibre',
        'sodium',
    ]
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0)
        else:
            df[column] = 0
    return df


def parse_quantity(raw: str) -> Tuple[float, str]:
    match = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*([a-zA-Z]*)\s*$", raw)
    if not match:
        raise QuantityParseError(
            "Please provide the quantity as '<amount><unit>' (e.g. 50g)."
        )
    amount = float(match.group(1))
    unit = match.group(2).lower() or 'g'

    if unit in {'g', 'gram', 'grams'}:
        grams = amount
        normalized = f"{amount:g} g"
    elif unit in {'kg', 'kilogram', 'kilograms'}:
        grams = amount * 1000
        normalized = f"{amount:g} kg"
    elif unit in {'mg', 'milligram', 'milligrams'}:
        grams = amount / 1000
        normalized = f"{amount:g} mg"
    else:
        raise QuantityParseError(
            "Unsupported unit. Please use g, mg, or kg for weight."
        )

    return grams, normalized


def find_food(df: pd.DataFrame, query: str) -> pd.Series:
    normalized_query = query.strip().lower()
    if not normalized_query:
        raise ValueError('Food name cannot be empty.')

    matches = df[df['name'].str.lower() == normalized_query]
    if matches.empty:
        matches = df[df['name'].str.contains(normalized_query, case=False, na=False)]

    if matches.empty:
        raise KeyError(
            f"Food '{query}' not found in the database. Please check the name and try again."
        )
    if len(matches) > 1:
        print("Multiple matches found. Using the first one:")
        display_columns = [col for col in ['name', 'brand', 'category'] if col in matches.columns]
        print(matches[display_columns].to_string(index=False))

    return matches.iloc[0]


def log_entry(entry: dict) -> None:
    columns = [
        'timestamp',
        'food',
        'serving',
        'protein',
        'fat',
        'carbohydrate',
        'calories',
        'fibre',
        'sodium',
    ]
    df = pd.DataFrame([entry], columns=columns)
    header = not LOG_CSV.exists()
    df.to_csv(LOG_CSV, mode='a', header=header, index=False)


def summarize_today() -> pd.Series:
    if not LOG_CSV.exists():
        return pd.Series(dtype=float)

    log_df = pd.read_csv(LOG_CSV, parse_dates=['timestamp'])
    if log_df.empty:
        return pd.Series(dtype=float)

    today = date.today()
    mask = log_df['timestamp'].dt.date == today
    today_entries = log_df.loc[mask]

    if today_entries.empty:
        return pd.Series(dtype=float)

    return today_entries[['calories', 'protein', 'fat', 'carbohydrate', 'fibre', 'sodium']].sum()


def main() -> None:
    foods = load_foods(FOODS_CSV)
    print('Meal Logger')
    print("Enter meals in the format 'food name, quantity' (e.g., 'almonds, 50g').")
    print("Type 'done' when you are finished.\n")

    while True:
        try:
            user_input = input('Meal: ').strip()
        except (EOFError, KeyboardInterrupt):
            print('\nExiting meal logger.')
            break

        if not user_input or user_input.lower() == 'done':
            break

        if ',' not in user_input:
            print("Please use the format 'food name, quantity'.")
            continue

        food_name, quantity_str = user_input.split(',', 1)
        food_name = food_name.strip()
        quantity_str = quantity_str.strip()

        try:
            grams, normalized_serving = parse_quantity(quantity_str)
            food_row = find_food(foods, food_name)
        except QuantityParseError as exc:
            print(exc)
            continue
        except KeyError as exc:
            print(exc)
            continue
        except ValueError as exc:
            print(exc)
            continue

        factor = grams / 100
        nutrients = {
            nutrient: float(food_row.get(nutrient, 0)) * factor
            for nutrient in ['protein', 'fat', 'carbohydrate', 'calories', 'fibre', 'sodium']
        }

        entry = {
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'food': food_row.get('name', food_name),
            'serving': normalized_serving,
            **nutrients,
        }
        log_entry(entry)

        print(
            'Logged: {food} ({serving}) - Calories: {calories:.2f} kcal, '
            'Protein: {protein:.2f} g, Fat: {fat:.2f} g, Carbs: {carbohydrate:.2f} g, '
            'Fibre: {fibre:.2f} g, Sodium: {sodium:.2f} mg'.format(**entry)
        )

    totals = summarize_today()
    if totals.empty:
        print('No entries logged for today.')
    else:
        print('\nToday\'s totals:')
        print(f"Calories: {totals['calories']:.2f} kcal")
        print(f"Protein: {totals['protein']:.2f} g")
        print(f"Fat: {totals['fat']:.2f} g")
        print(f"Carbohydrates: {totals['carbohydrate']:.2f} g")
        print(f"Fibre: {totals['fibre']:.2f} g")
        print(f"Sodium: {totals['sodium']:.2f} mg")


if __name__ == '__main__':
    try:
        main()
    except SystemExit as exc:
        print(exc)
        sys.exit(1)
