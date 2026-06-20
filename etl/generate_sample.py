"""Generate a synthetic credit-card transactions dataset.

The output matches the public Sparkov / Kaggle "Credit Card Transactions"
dataset (kartik2112/fraud-detection, fraudTrain.csv) column-for-column, so the
rest of the pipeline behaves identically whether you load this file or the real
Kaggle download. Use this for an instant, offline demo; swap in the real
fraudTrain.csv whenever you like (see README).

Usage:
    python etl/generate_sample.py                       # 200 customers, 20k rows
    python etl/generate_sample.py --rows 50000 --out data/transactions.csv
"""
from __future__ import annotations

import argparse
import csv
import os
import random
from datetime import datetime, timedelta

SEED = 42

FIRST_NAMES = [
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael",
    "Linda", "William", "Elizabeth", "David", "Susan", "Aoife", "Conor",
    "Niamh", "Sean", "Emma", "Liam", "Grace", "Oisin",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Murphy", "Kelly", "O'Brien", "Ryan", "Walsh", "McCarthy",
    "Doyle", "Nguyen", "Patel", "Kim", "Rossi", "Schmidt",
]
JOBS = [
    "Accountant", "Software developer", "Nurse", "Teacher", "Civil engineer",
    "Chef", "Electrician", "Pharmacist", "Data analyst", "Architect",
    "Plumber", "Graphic designer", "Mechanic", "Solicitor", "Physiotherapist",
]

# (city, state, zip, lat, long, city_pop)
CITIES = [
    ("Dublin", "OH", "43017", 40.0992, -83.1141, 49328),
    ("Columbus", "OH", "43004", 39.9612, -82.9988, 905748),
    ("Austin", "TX", "78701", 30.2672, -97.7431, 978908),
    ("Denver", "CO", "80202", 39.7392, -104.9903, 727211),
    ("Portland", "OR", "97201", 45.5152, -122.6784, 654741),
    ("Boston", "MA", "02108", 42.3601, -71.0589, 692600),
    ("Seattle", "WA", "98101", 47.6062, -122.3321, 744955),
    ("Atlanta", "GA", "30303", 33.7490, -84.3880, 498715),
    ("Phoenix", "AZ", "85004", 33.4484, -112.0740, 1680992),
    ("Nashville", "TN", "37201", 36.1627, -86.7816, 689447),
    ("Raleigh", "NC", "27601", 35.7796, -78.6382, 467665),
    ("Madison", "WI", "53703", 43.0731, -89.4012, 259680),
    ("Boise", "ID", "83702", 43.6150, -116.2023, 235684),
    ("Tucson", "AZ", "85701", 32.2226, -110.9747, 542629),
    ("Omaha", "NE", "68102", 41.2565, -95.9345, 486051),
]

# category -> (min_amount, max_amount) — categories mirror the Sparkov set.
CATEGORIES = {
    "grocery_pos": (5, 200),
    "grocery_net": (5, 150),
    "gas_transport": (10, 120),
    "shopping_pos": (10, 400),
    "shopping_net": (10, 600),
    "entertainment": (8, 150),
    "food_dining": (8, 120),
    "health_fitness": (10, 250),
    "home": (15, 500),
    "kids_pets": (5, 180),
    "misc_pos": (3, 100),
    "misc_net": (3, 120),
    "personal_care": (5, 90),
    "travel": (40, 1500),
}

MERCHANT_STEMS = [
    "Kirlin and Sons", "Schumm PLC", "Kuhn LLC", "Boyer-Reichert", "Rau and Sons",
    "Predovic Inc", "Hauck-Mertz", "Stokes Group", "Heller-Langosh", "Cormier LLC",
    "Lind-Buckridge", "Effertz and Sons", "Goyette Inc", "Reilly Group", "Doyle Ltd",
    "Walsh-Murphy", "Kelly Holdings", "Ryan Brothers", "Nolan and Co", "OBrien Mart",
    "Greenfield Foods", "Summit Outdoors", "Harbor Travel", "Bright Pharmacy", "Cedar Diner",
]


def make_cc_num() -> str:
    """16-digit card number; first digit drives the brand in dim_account."""
    first = random.choice("3456")
    rest = "".join(random.choice("0123456789") for _ in range(15))
    return first + rest


def random_dob() -> str:
    start = datetime(1950, 1, 1)
    end = datetime(2001, 12, 31)
    d = start + timedelta(days=random.randint(0, (end - start).days))
    return d.strftime("%Y-%m-%d")


def build_customers(n: int) -> list[dict]:
    customers = []
    for _ in range(n):
        city, state, zip_code, lat, lon, pop = random.choice(CITIES)
        customers.append({
            "cc_num": make_cc_num(),
            "first": random.choice(FIRST_NAMES),
            "last": random.choice(LAST_NAMES),
            "gender": random.choice(["M", "F"]),
            "street": f"{random.randint(1, 9999)} {random.choice(LAST_NAMES)} {random.choice(['St', 'Ave', 'Rd', 'Ln'])}",
            "city": city,
            "state": state,
            "zip": zip_code,
            "lat": lat,
            "long": lon,
            "city_pop": pop,
            "job": random.choice(JOBS),
            "dob": random_dob(),
        })
    return customers


FIELDNAMES = [
    "trans_index", "trans_date_trans_time", "cc_num", "merchant", "category",
    "amt", "first", "last", "gender", "street", "city", "state", "zip",
    "lat", "long", "city_pop", "job", "dob", "trans_num", "unix_time",
    "merch_lat", "merch_long", "is_fraud",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--customers", type=int, default=200)
    parser.add_argument("--rows", type=int, default=20000)
    parser.add_argument("--out", default="data/transactions.csv")
    parser.add_argument("--fraud-rate", type=float, default=0.005)
    args = parser.parse_args()

    random.seed(SEED)
    customers = build_customers(args.customers)
    merchants = [("fraud_" + stem, random.choice(list(CATEGORIES))) for stem in MERCHANT_STEMS]

    start = datetime(2019, 1, 1)
    end = datetime(2020, 12, 31, 23, 59, 59)
    span_seconds = int((end - start).total_seconds())

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for i in range(args.rows):
            cust = random.choice(customers)
            merch_name, category = random.choice(merchants)
            lo, hi = CATEGORIES[category]
            ts = start + timedelta(seconds=random.randint(0, span_seconds))
            writer.writerow({
                "trans_index": i,
                "trans_date_trans_time": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "cc_num": cust["cc_num"],
                "merchant": merch_name,
                "category": category,
                "amt": round(random.uniform(lo, hi), 2),
                "first": cust["first"],
                "last": cust["last"],
                "gender": cust["gender"],
                "street": cust["street"],
                "city": cust["city"],
                "state": cust["state"],
                "zip": cust["zip"],
                "lat": cust["lat"],
                "long": cust["long"],
                "city_pop": cust["city_pop"],
                "job": cust["job"],
                "dob": cust["dob"],
                "trans_num": "%032x" % random.getrandbits(128),
                "unix_time": int(ts.timestamp()),
                "merch_lat": round(cust["lat"] + random.uniform(-0.5, 0.5), 6),
                "merch_long": round(cust["long"] + random.uniform(-0.5, 0.5), 6),
                "is_fraud": 1 if random.random() < args.fraud_rate else 0,
            })

    print(f"Wrote {args.rows:,} transactions for {args.customers} customers -> {args.out}")


if __name__ == "__main__":
    main()
